"""
Inbox Message Processor — Event-Driven, Zero Polling
Extracted from server.py to keep server under 2000 lines.

Handles the full inbox lifecycle:
  1. POST /api/inbox → write message file
  2. Background task: Claude Code (primary) or DeepSeek (fallback)
  3. ACK + REPLY written to outbox
  4. Harness Engine quality gates (non-blocking)
  5. Message moved to processed/
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

# These are imported lazily by server.py caller to avoid circular imports
# PROJECT_ROOT, INBOX_DIR, OUTBOX_DIR, PROCESSED_DIR, CTX_STATE_PATH, etc.

URGENT_KEYWORDS = ["紧急", "urgent", "URGENT", "urgent", "interrupt", "立刻", "马上"]
STOCK_REQUEST_KEYWORDS = [
    "分析", "目标价", "走势", "趋势", "风险", "回撤",
    "持仓", "交易", "买入", "卖出", "止损", "因子",
    "财报", "催化剂", "评级", "估值", "期权", "波动",
    "NVDA", "AMD", "MU", "INTC", "TSLA", "AAPL", "DXYZ",
    "股票", "标的", "行情", "技术面", "基本面",
]

# ── Headroom context compression ──────────────────────────────
# DeepSeek V4 context window: 128K (deepseek-chat) / 1M (deepseek-v4-pro via Claude Code)
# Headroom = context_window - (system_prompt + context + user_message)
# We target 60%+ headroom for the LLM to think and generate a response.

DEEPSEEK_CHAT_WINDOW = 128_000  # deepseek-chat model
HEADROOM_TARGET_RATIO = 0.6  # aim for 60% free context window
MAX_ASSEMBLED_CONTEXT_TOKENS = int(DEEPSEEK_CHAT_WINDOW * (1 - HEADROOM_TARGET_RATIO) * 0.5)  # ~25K for context

# Per-section token budgets (for _assemble_context)
SECTION_BUDGETS = {
    "claude_md": 800,      # CLAUDE.md core rules
    "memory": 500,         # MemPalace semantic results
    "task_queue": 200,     # pending task summary
    "interrupt": 300,      # interrupt context
    "total": 1800,         # hard cap on assembled context
}


def _compress_text_for_budget(text: str, max_tokens: int) -> str:
    """Compress text to fit within a token budget by truncating to sentence boundaries.

    Uses sentence-aware truncation: splits on Chinese/English sentence delimiters
    (。！？\n. ! ?) and accumulates sentences until the budget is reached.
    Falls back to character-based truncation if no sentence boundaries found.
    """
    if not text:
        return ""
    est = _estimate_tokens(text)
    if est <= max_tokens:
        return text

    # Sentence-aware truncation
    sentences = __import__("re").split(r'(?<=[。！？\n\.!\?])', text)
    result_parts = []
    used = 0
    for sent in sentences:
        sent_est = _estimate_tokens(sent)
        if used + sent_est > max_tokens:
            break
        result_parts.append(sent)
        used += sent_est
    if result_parts:
        return "".join(result_parts)

    # Fallback: character-based with CJK-awareness
    return text[:max_tokens * 2]  # rough: ~2 chars per token for CJK-heavy text


def _measure_headroom(system_tokens: int, user_tokens: int,
                      context_window: int = DEEPSEEK_CHAT_WINDOW) -> dict:
    """Measure context window headroom for an LLM call.

    Returns dict with used_tokens, free_tokens, headroom_pct, and a warning flag.
    """
    used = system_tokens + user_tokens
    free = max(context_window - used, 0)
    pct = free / context_window if context_window > 0 else 0
    return {
        "used_tokens": used,
        "free_tokens": free,
        "headroom_pct": round(pct, 3),
        "low_headroom": pct < HEADROOM_TARGET_RATIO,
    }


def _infer_priority(text: str) -> str:
    p0_kw = ["紧急", "urgent", "立刻", "马上", "爆仓", "止损", "崩盘", "暴跌"]
    p1_kw = ["分析", "持仓", "建议", "报告", "研究", "策略", "交易", "买入", "卖出"]
    if any(kw in text for kw in p0_kw):
        return "P0"
    if any(kw in text.lower() for kw in p1_kw):
        return "P1"
    return "P2"


def _is_urgent(text: str) -> bool:
    return any(kw in text for kw in URGENT_KEYWORDS)


def _extract_keywords(text: str) -> set[str]:
    upper = text.upper()
    tickers = set(re.findall(r'\b[A-Z]{2,5}\b', upper))
    tickers |= set(re.findall(r'\b[A-Z]{2,4}\d{2,4}\b', upper))
    topics = set(re.findall(r'(分析|回测|因子|持仓|交易|风险|报告|研究|监控|'
                            r'NVDA|AMD|MU|INTC|DXYZ|SOX|SMH|QQQ|SPY|TSLA|'
                            r'MI\d+|H\d+|B\d+|HBM|DRAM|NAND|'
                            r'期权|财报|罢工|美联储|利率|CPI|GDP|VIX|'
                            r'目标价|走势|趋势|量产|进展|催化剂)', upper))
    return tickers | topics


def _similarity(task_a: dict, task_b: dict) -> float:
    kw_a = _extract_keywords(task_a.get("full_text", "") + " " + task_a.get("preview", ""))
    kw_b = _extract_keywords(task_b.get("full_text", "") + " " + task_b.get("preview", ""))
    if not kw_a or not kw_b:
        return 0.0
    return len(kw_a & kw_b) / len(kw_a | kw_b)


def _is_stock_request(text: str) -> bool:
    return any(kw.upper() in text.upper() for kw in STOCK_REQUEST_KEYWORDS)


def _assemble_context(project_root: Path, task_queue_file: Path, ctx_state_path: Path,
                      query: str = "", max_memory_tokens: int = 600) -> str:
    """Assemble project context for LLM calls with per-section token budgets.

    Each section has a token budget (SECTION_BUDGETS). Sections are assembled
    independently and compressed to fit their budget. The total assembled context
    is capped at SECTION_BUDGETS['total'].
    """
    parts = []

    # Section 1: CLAUDE.md core rules (budget: ~800 tokens)
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        claude = claude_md.read_text(encoding="utf-8")
        essential_sections = []
        capture = False
        for line in claude.split("\n"):
            if line.startswith("## ") and any(kw in line for kw in ["铁律", "通信", "量化", "环境", "领域"]):
                capture = True
            elif line.startswith("## ") and not any(kw in line for kw in ["铁律", "通信", "量化", "环境", "领域"]):
                capture = False
            if capture:
                essential_sections.append(line)
        if essential_sections:
            raw = "## 项目核心规则\n" + "\n".join(essential_sections[:80])
            compressed = _compress_text_for_budget(raw, SECTION_BUDGETS["claude_md"])
            parts.append(compressed)

    # Section 2: MemPalace semantic memory (budget: ~500 tokens)
    memory_context = _get_memory_context(project_root, query, SECTION_BUDGETS["memory"])
    if memory_context:
        parts.append("## 关键记忆\n" + _compress_text_for_budget(memory_context, SECTION_BUDGETS["memory"]))

    # Section 3: Task queue (budget: ~200 tokens)
    if task_queue_file.exists():
        try:
            queue = json.loads(task_queue_file.read_text(encoding="utf-8"))
            tasks = queue.get("tasks", [])
            if tasks:
                task_lines = [f"- [{t.get('priority','?')}] {t.get('preview','')[:80]}" for t in tasks[:5]]
                raw = f"## 当前任务队列 ({len(tasks)} 个)\n" + "\n".join(task_lines)
                parts.append(_compress_text_for_budget(raw, SECTION_BUDGETS["task_queue"]))
        except Exception:
            pass

    # Section 4: Interrupt context (budget: ~300 tokens)
    if ctx_state_path.exists():
        try:
            ctx = json.loads(ctx_state_path.read_text(encoding="utf-8"))
            key_info = {k: ctx[k] for k in ["interrupted_task", "urgent_reason", "pending_actions"]
                        if k in ctx and ctx[k]}
            if key_info:
                raw = "## 中断上下文\n" + json.dumps(key_info, ensure_ascii=False, indent=2)
                parts.append(_compress_text_for_budget(raw, SECTION_BUDGETS["interrupt"]))
        except Exception:
            pass

    # Assemble and apply total budget cap
    assembled = "\n\n".join(parts) if parts else ""
    return _compress_text_for_budget(assembled, SECTION_BUDGETS["total"])


# ── MemPalace memory context builder ──────────────────────────

_MEM_PALACE = None  # lazy singleton


def _get_memory_context(project_root: Path, query: str = "", max_tokens: int = 600) -> str:
    """Retrieve semantically relevant memories using MemPalace.

    When query is non-empty, uses LSA/TF-IDF semantic search to find
    memories relevant to the query. When query is empty, falls back to
    blind top-N file reading. Returns a formatted context string.
    """
    global _MEM_PALACE

    # Resolve the actual memory directory (Claude-managed, not project-root/memory/)
    mem_dir = project_root / ".claude" / "projects" / "-mnt-e-2026-AgentStudy-Python-code" / "memory"
    if not mem_dir.exists():
        return ""

    if _MEM_PALACE is None:
        try:
            from infrastructure.mem_palace import MemPalace
            _MEM_PALACE = MemPalace(memory_dir=mem_dir)
        except Exception:
            return ""

    palace = _MEM_PALACE
    if not palace.cards:
        return ""

    if query.strip():
        # Semantic search: find memories relevant to the query
        try:
            return palace.build_context(query, max_tokens=max_tokens)
        except Exception:
            pass

    # Fallback: blind top-N (no query available)
    try:
        top_cards = sorted(palace.cards.values(), key=lambda c: len(c.content), reverse=True)[:8]
        lines = []
        for card in top_cards:
            snippet = card.description or card.content[:120].replace("\n", " ")
            lines.append(f"- [{card.room}] {card.name}: {snippet}")
        return "\n".join(lines[:15])
    except Exception:
        return ""


def setup(project_root: Path, task_queue_file: Path, outbox_dir: Path,
          deepseek_api_key: str, ctx_state_path: Path, langgraph_reports_dir: Path):
    """Initialize the inbox processor with project paths. Called once from server.py."""
    globals()["_PROJECT_ROOT"] = project_root
    globals()["_TASK_QUEUE_FILE"] = task_queue_file
    globals()["_OUTBOX_DIR"] = outbox_dir
    globals()["_DEEPSEEK_API_KEY"] = deepseek_api_key
    globals()["_CTX_STATE_PATH"] = ctx_state_path
    globals()["_LANGGRAPH_REPORTS_DIR"] = langgraph_reports_dir
    globals()["_CLAUDE_SESSION_ID"] = str(__import__("uuid").uuid4())
    globals()["_SESSION_INITIALIZED"] = project_root / "company" / ".claude_session_ready"
    globals()["_TOKEN_LOG"] = project_root / "logs" / "token_usage.jsonl"
    globals()["_TOKEN_LOG"].parent.mkdir(parents=True, exist_ok=True)


def _log_token_usage(source: str, input_tokens: int, output_tokens: int, cost_est: float,
                     message_id: str = "", headroom: dict | None = None):
    """Log token usage per inbox message for observability. Appends JSON line to token log.

    When headroom is provided, includes context window headroom metrics
    (used/free tokens, headroom percentage, low-headroom warning flag).
    """
    import json as _json
    from datetime import datetime as _dt
    entry = {"ts": _dt.now().isoformat(), "source": source,
             "input_tokens": input_tokens, "output_tokens": output_tokens,
             "cost_est": cost_est, "message_id": message_id}
    if headroom:
        entry["headroom"] = headroom
    try:
        with open(globals().get("_TOKEN_LOG"), "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    BPE tokenizers (DeepSeek, GPT-4, Claude): CJK chars ≈ 1–1.5 tokens each,
    non-CJK ≈ 4 chars/token. This is more accurate than a flat chars//3 heuristic.
    """
    import re as _re

    cjk = len(_re.findall(r'[一-鿿㐀-䶿　-〿＀-￯]', text))
    non_cjk = max(len(text) - cjk, 0)
    # CJK: ~1.3 tokens/char (average for common BPE tokenizers on Chinese text)
    # Non-CJK: ~4 chars/token (standard for English code/markdown)
    return max(int(cjk / 1.3 + non_cjk / 4), 1)


def get_token_usage_by_message(hours: int = 24) -> dict:
    """Aggregate token usage per inbox message from the token log.

    Returns {message_id: {total_input, total_output, cost_est, calls, sources}}.
    If hours=0, returns all records.
    """
    import json as _json
    from datetime import datetime as _dt, timedelta as _td
    token_log = globals().get("_TOKEN_LOG")
    if not token_log or not token_log.exists():
        return {}
    cutoff = _dt.now() - _td(hours=hours) if hours > 0 else None
    by_msg = {}
    try:
        for line in token_log.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except Exception:
                continue
            if cutoff:
                try:
                    ts = _dt.fromisoformat(entry.get("ts", ""))
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            mid = entry.get("message_id", "") or "__unknown__"
            if mid not in by_msg:
                by_msg[mid] = {"total_input": 0, "total_output": 0, "cost_est": 0.0,
                               "calls": 0, "sources": set()}
            agg = by_msg[mid]
            agg["total_input"] += entry.get("input_tokens", 0)
            agg["total_output"] += entry.get("output_tokens", 0)
            agg["cost_est"] += entry.get("cost_est", 0.0)
            agg["calls"] += 1
            agg["sources"].add(entry.get("source", ""))
        # Convert sets to lists for JSON serialization
        for v in by_msg.values():
            v["sources"] = list(v["sources"])
        return by_msg
    except Exception:
        return {}


def _write_outbox(prefix: str, title: str, body: str):
    outbox_dir = globals().get("_OUTBOX_DIR")
    now = datetime.now()
    filename = f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    (outbox_dir / filename).write_text(
        f"# {title}\n\n**时间**：{now.strftime('%Y-%m-%d %H:%M:%S')} CST\n\n{body}", encoding="utf-8")
    return filename


def _smart_add_to_queue(message_id: str, text: str, preview: str):
    tqf = globals().get("_TASK_QUEUE_FILE")
    new_task = {
        "id": message_id, "source": "inbox",
        "priority": _infer_priority(text), "preview": preview[:200],
        "full_text": text[:2000],
        "updates": [f"[{datetime.now().strftime('%m-%d %H:%M')}] {preview[:100]}"],
        "received_at": datetime.now().isoformat(),
    }
    queue = {"tasks": []}
    if tqf.exists():
        try: queue = json.loads(tqf.read_text(encoding="utf-8"))
        except: pass
    best_match, best_sim = None, 0.0
    for i, t in enumerate(queue.get("tasks", [])):
        sim = _similarity(new_task, t)
        if sim > best_sim: best_sim, best_match = sim, i
    if best_match is not None and best_sim > 0.25:
        existing = queue["tasks"][best_match]
        existing["full_text"] = (existing.get("full_text", "") + "\n\n[更新] " + text[:500])[:2000]
        existing.setdefault("updates", []).append(
            f"[{datetime.now().strftime('%m-%d %H:%M')}] {preview[:100]}")
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        if order.get(new_task["priority"], 2) < order.get(existing.get("priority", "P2"), 2):
            existing["priority"] = new_task["priority"]
        existing["merged_from"] = existing.get("merged_from", []) + [message_id]
        queue["tasks"][best_match] = existing
    else:
        queue.setdefault("tasks", []).append(new_task)
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    queue["tasks"].sort(key=lambda t: order.get(t.get("priority", "P2"), 2))
    tqf.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return best_match is not None and best_sim > 0.5


def _call_deepseek(message: str, message_id: str = "") -> str | None:
    api_key = globals().get("_DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        pr = globals().get("_PROJECT_ROOT")
        tqf = globals().get("_TASK_QUEUE_FILE")
        ctx = globals().get("_CTX_STATE_PATH")
        context = _assemble_context(pr, tqf, ctx, query=message)
        system_prompt = f"你是 OnionQuant CEO Agent。用中文回复。\n{context}\n\n回复原则: 基于上下文,精炼结构化Markdown,署名 -- CEO Agent"
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ], max_tokens=1200, temperature=0.5)
        reply = resp.choices[0].message.content.strip()
        usage = resp.usage
        if usage:
            input_tok = usage.prompt_tokens or 0
            output_tok = usage.completion_tokens or 0
            cost = (input_tok * 0.025 + output_tok * 3) / 1_000_000
            headroom = _measure_headroom(input_tok, 0, DEEPSEEK_CHAT_WINDOW)
            _log_token_usage("deepseek", input_tok, output_tok, cost, message_id,
                           headroom=headroom)
        return reply
    except Exception:
        return None


def _call_claude_code(message: str, message_id: str = "") -> str | None:
    """Process via WSL Claude Code persistent session — pre-injected context for caching."""
    import subprocess as sp
    pr = globals().get("_PROJECT_ROOT")
    sid = globals().get("_CLAUDE_SESSION_ID")
    sinit = globals().get("_SESSION_INITIALIZED")
    tqf = globals().get("_TASK_QUEUE_FILE")
    ctx = globals().get("_CTX_STATE_PATH")

    # Pre-assemble compressed context so Claude Code doesn't re-read files
    context = _assemble_context(pr, tqf, ctx, query=message)

    prompt = (
        f"[CEO Agent] 董事长信箱消息。以下是预注入的项目上下文:\n\n"
        f"{context}\n\n"
        f"─── 消息 ───\n{message}\n\n"
        f"要求: 基于上述上下文+memory+WebSearch深度回复。涉及股票用LangGraph管道。"
        f"直接执行不停顿。Markdown可执行回复。署名 -- CEO Agent"
    )

    # Measure headroom before call
    est_system = _estimate_tokens(prompt)
    headroom = _measure_headroom(est_system, 0, DEEPSEEK_CHAT_WINDOW)

    try:
        prompt_file = pr / "company" / ".claude_prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        wsl_path = "/mnt/e/2026_AgentStudy/Python_code/company/.claude_prompt.txt"
        session_flag = f"--session-id {sid}"
        if not sinit.exists():
            sinit.write_text(datetime.now().isoformat())
        cmd = (f"cd /mnt/e/2026_AgentStudy/Python_code && "
               f'claude -p "$(cat {wsl_path})" {session_flag} '
               f"--model deepseek-v4-pro --dangerously-skip-permissions 2>&1")
        result = sp.run(
            ["wsl", "-e", "bash", "-c", cmd], cwd=str(pr),
            capture_output=True, encoding="utf-8", errors="replace", timeout=180)
        reply = (result.stdout or "").strip()
        try: prompt_file.unlink()
        except: pass
        if not reply or len(reply) < 20:
            return _call_deepseek(message, message_id)
        # Estimate token usage (Claude Code via subprocess doesn't return usage)
        est_input = _estimate_tokens(prompt)
        est_output = _estimate_tokens(reply)
        est_cost = (est_input * 0.025 + est_output * 3) / 1_000_000
        _log_token_usage("claude_code", est_input, est_output, est_cost, message_id,
                       headroom=headroom)
        return reply
    except sp.TimeoutExpired:
        sinit.unlink(missing_ok=True)
        return _call_deepseek(message, message_id)
    except Exception:
        return _call_deepseek(message, message_id)


async def process_message(filepath: Path, text: str, urgent_flag: bool = False, notify_fn=None):
    """Process one inbox message. Called from server.py background task."""
    is_urgent = urgent_flag or _is_urgent(text)
    preview = text[:150]

    ack_prefix = "URGENT_ACK" if is_urgent else "ACK"
    ack_title = "[URGENT] 紧急来信 - Claude Code 处理中" if is_urgent else "收到来信 - Claude Code 处理中"
    ack_body = (
        f"{'[!!] 紧急消息已中断当前任务，' if is_urgent else ''}Claude Code (全上下文+工具) 处理中...\n\n"
        f"> {preview}\n\n---\n预计 30-60 秒内完成深度回复。")
    _write_outbox(ack_prefix, ack_title, ack_body)

    if notify_fn:
        await notify_fn("outbox_new", {"type": "urgent_ack" if is_urgent else "ack_queued", "preview": preview})

    msg_id = filepath.stem  # e.g., "MSG_20260613_143021"
    reply = _call_claude_code(text, msg_id)
    if not reply:
        reply = _call_deepseek(text, msg_id)

    if reply:
        reply_prefix = "URGENT_REPLY" if is_urgent else "REPLY"
        reply_title = "[URGENT] CEO Agent 回复 (Claude Code)" if is_urgent else "CEO Agent 回复 (Claude Code)"
        _write_outbox(reply_prefix, reply_title, reply)
        if notify_fn:
            await notify_fn("outbox_new", {"type": "reply", "preview": reply[:100]})
        try:
            from scripts.harness_engine import HarnessEngine
            engine = HarnessEngine()
            tid = engine.start_task(preview[:80])
            result = engine.complete_task(reply, preview, tool_count=1, task_id=tid)
            if result["verdict"] == "NEEDS_WORK" and result["findings"]:
                _write_outbox("EVAL", "质量审查发现",
                    f"Fresh Evaluator 审查结果:\n评分: {result['score']}/10\n"
                    f"问题:\n" + "\n".join(f"- {f}" for f in result["findings"]))
                if notify_fn:
                    await notify_fn("outbox_new", {"type": "eval", "preview": f"Quality: {result['score']}/10"})
        except Exception:
            pass

    # Move to processed — same directory, just subfolder
    processed_dir = filepath.parent / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    dest = processed_dir / filepath.name
    if filepath.exists():
        filepath.rename(dest)
