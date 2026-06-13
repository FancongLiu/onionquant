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


def _assemble_context(project_root: Path, task_queue_file: Path, ctx_state_path: Path) -> str:
    """Assemble full project context for LLM calls. Zero AI tokens."""
    parts = []
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
            parts.append("## 项目核心规则\n" + "\n".join(essential_sections[:80]))
    memory_dir = project_root / "memory"
    if memory_dir.exists():
        mem_lines = []
        for mf in sorted(memory_dir.glob("*.md"))[:8]:
            try:
                content = mf.read_text(encoding="utf-8")[:300]
                name = mf.stem.replace("_", " ")
                mem_lines.append(f"- {name}: {content.split(chr(10))[0][:100]}")
            except Exception:
                pass
        if mem_lines:
            parts.append("## 关键记忆\n" + "\n".join(mem_lines[:15]))
    if task_queue_file.exists():
        try:
            queue = json.loads(task_queue_file.read_text(encoding="utf-8"))
            tasks = queue.get("tasks", [])
            if tasks:
                task_lines = [f"- [{t.get('priority','?')}] {t.get('preview','')[:80]}" for t in tasks[:5]]
                parts.append(f"## 当前任务队列 ({len(tasks)} 个)\n" + "\n".join(task_lines))
        except Exception:
            pass
    if ctx_state_path.exists():
        try:
            ctx = json.loads(ctx_state_path.read_text(encoding="utf-8"))
            key_info = {k: ctx[k] for k in ["interrupted_task", "urgent_reason", "pending_actions"]
                        if k in ctx and ctx[k]}
            if key_info:
                parts.append("## 中断上下文\n" + json.dumps(key_info, ensure_ascii=False, indent=2)[:500])
        except Exception:
            pass
    return "\n\n".join(parts) if parts else ""


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


def _call_deepseek(message: str) -> str | None:
    api_key = globals().get("_DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        pr = globals().get("_PROJECT_ROOT")
        tqf = globals().get("_TASK_QUEUE_FILE")
        ctx = globals().get("_CTX_STATE_PATH")
        context = _assemble_context(pr, tqf, ctx)
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"""你是 OnionQuant CEO Agent。请用中文回复。
{context}
## 回复原则
- 基于上述项目上下文回答，不凭空猜测
- 涉及持仓/决策时引用 memory 信息
- 精炼、结构化（Markdown）、可执行
- 署名: -- CEO Agent"""},
                {"role": "user", "content": message},
            ], max_tokens=1200, temperature=0.5)
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _call_claude_code(message: str) -> str | None:
    """Process via WSL Claude Code persistent session — 100% chat quality."""
    import subprocess as sp
    pr = globals().get("_PROJECT_ROOT")
    sid = globals().get("_CLAUDE_SESSION_ID")
    sinit = globals().get("_SESSION_INITIALIZED")

    prompt = (
        f"你是 OnionQuant CEO Agent。董事长通过信箱发来消息。请基于项目上下文给出深度回复。\n\n"
        f"消息:\n{message}\n\n"
        f"要求: 1.基于CLAUDE.md和memory文件的项目信息回答 2.如涉及股票分析使用11部门LangGraph管道 "
        f"3.如需最新信息直接使用WebSearch 4.直接执行搜索和分析不要写'我会去搜索'然后停下 "
        f"5.回复精炼结构化(Markdown)可执行 6.署名:-- CEO Agent"
    )
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
            return _call_deepseek(message)
        return reply
    except sp.TimeoutExpired:
        sinit.unlink(missing_ok=True)
        return _call_deepseek(message)
    except Exception:
        return _call_deepseek(message)


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

    reply = _call_claude_code(text)
    if not reply:
        reply = _call_deepseek(text)

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
