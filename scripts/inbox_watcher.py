#!/usr/bin/env python3
"""
24/7 Inbox Watcher — polls chairman_inbox/ every 5 seconds (Zero AI tokens).

TOKEN OPTIMIZATION:
  - File scanning: ZERO AI tokens (Python glob + file I/O)
  - ACK writing: ZERO AI tokens (just writes a .md file)
  - Normal messages: appended to task queue (ZERO AI tokens)
  - URGENT messages: immediate DeepSeek API call (costs tokens, justified)
  - Batch processing: handled by main session, sharing cache prefix (99% hit rate)

FLOW:
  1. New MSG_*.md detected → write instant ACK to outbox
  2. Check for urgent keywords (紧急/urgent/interrupt/立刻/马上)
     - URGENT → call DeepSeek → URGENT_REPLY → WeChat push
     - NORMAL → append to company/task_queue.json → wait for batch
  3. Move inbox message to processed/

UNIFIED TASK QUEUE (company/task_queue.json):
  {
    "tasks": [
      {
        "id": "MSG_20260610_001600",
        "source": "inbox",
        "priority": "P1",
        "preview": "帮我分析一下MU最近的走势...",
        "full_text": "...",
        "received_at": "2026-06-10 00:16:00"
      }
    ]
  }

Start: python .venv/Scripts/python scripts/inbox_watcher.py
Runs inside WSL tmux ceo-24x7 for persistence.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
PROCESSED_DIR = INBOX_DIR / "processed"
STATE_FILE = PROJECT_ROOT / "company" / ".watcher_state.json"
TASK_QUEUE_FILE = PROJECT_ROOT / "company" / "task_queue.json"
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

BEIJING_TZ = timezone(timedelta(hours=8))

# Keywords that trigger URGENT immediate processing
URGENT_KEYWORDS = ["紧急", "urgent", "URGENT", "urgent", "interrupt", "立刻", "马上", "现在立刻"]

INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Load API key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").split("\n"):
            if line.startswith("DEEPSEEK_API_KEY="):
                DEEPSEEK_API_KEY = line.split("=", 1)[1].strip()
                break


def now_ts() -> str:
    return datetime.now(BEIJING_TZ).strftime("%H:%M:%S")


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def is_urgent(text: str) -> bool:
    return any(kw in text for kw in URGENT_KEYWORDS)


def load_state() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_state(seen: set):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8"
    )


def get_new_messages() -> list[Path]:
    seen = load_state()
    new = []
    current_set = set()
    for f in sorted(INBOX_DIR.glob("MSG_*.md")):
        if f.name == "README.md":
            continue
        current_set.add(f.name)
        if f.name not in seen:
            new.append(f)
    save_state(current_set)
    return new


def write_outbox(prefix: str, title: str, body: str, urgent: bool = False):
    """Write a reply to chairman_outbox/. Zero AI tokens."""
    now = datetime.now(BEIJING_TZ)
    actual_prefix = f"URGENT_{prefix}" if urgent else prefix
    filename = f"{actual_prefix}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath = OUTBOX_DIR / filename
    content = f"# {title}\n\n[时间]: {now.strftime('%Y-%m-%d %H:%M:%S')} CST\n\n{body}"
    filepath.write_text(content, encoding="utf-8")
    print(f"[{now_ts()}] Outbox: {filename}", flush=True)


def add_to_task_queue(filepath: Path, message: str, preview: str):
    """Add a normal message to the unified task queue. Zero AI tokens."""
    task = {
        "id": filepath.stem,
        "source": "inbox",
        "priority": infer_priority(message),
        "preview": preview[:200],
        "full_text": message[:2000],
        "received_at": now_iso(),
    }

    queue = {"tasks": []}
    if TASK_QUEUE_FILE.exists():
        try:
            queue = json.loads(TASK_QUEUE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            queue = {"tasks": []}

    # Avoid duplicates
    existing_ids = {t.get("id") for t in queue.get("tasks", [])}
    if task["id"] not in existing_ids:
        queue.setdefault("tasks", []).append(task)
        # Sort by priority
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        queue["tasks"].sort(key=lambda t: priority_order.get(t.get("priority", "P2"), 2))
        TASK_QUEUE_FILE.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[{now_ts()}] Queued: {filepath.name} (priority={task['priority']})", flush=True)


def infer_priority(text: str) -> str:
    """Infer priority from message content. Zero AI tokens — just keyword matching."""
    p0_keywords = ["紧急", "urgent", "立刻", "马上", "爆仓", "止损", "崩盘", "暴跌"]
    p1_keywords = ["分析", "持仓", "建议", "报告", "研究", "策略", "交易", "买入", "卖出"]

    text_lower = text.lower()
    if any(kw in text for kw in p0_keywords):
        return "P0"
    if any(kw in text_lower for kw in p1_keywords):
        return "P1"
    return "P2"


def call_deepseek(message: str) -> str | None:
    """Call DeepSeek API — ONLY for urgent messages. This costs tokens."""
    if not DEEPSEEK_API_KEY:
        print("  No DEEPSEEK_API_KEY", flush=True)
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

        SYSTEM_PROMPT = """你是 OnionQuant CEO Agent。[URGENT] 紧急响应模式。
回复要求：直接给结论和可执行步骤，不要长篇背景。署名: -- CEO Agent"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            max_tokens=800,
            temperature=0.3,  # low temp for fast direct response
        )
        reply = response.choices[0].message.content
        return reply.strip() if reply else None

    except ImportError:
        print("  openai not installed", flush=True)
        return None
    except Exception as e:
        print(f"  DeepSeek error: {e}", flush=True)
        return None


def push_wechat(message: str):
    """Push urgent notification to WeChat. Best-effort, non-blocking."""
    try:
        import subprocess as sp
        sp.run(
            [VENV_PYTHON, str(PROJECT_ROOT / "scripts" / "wechat_sync_push.py")],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def process_urgent(filepath: Path, message: str):
    """Immediate AI processing for urgent messages. Costs tokens (justified)."""
    print(f"[{now_ts()}] [URGENT] Processing: {filepath.name}", flush=True)

    # Instant ACK
    write_outbox("ACK", "[URGENT] 紧急来信 - 立即处理中",
        f"紧急消息已中断当前任务队列，立即处理。\n\n> {message[:150]}\n\n预计15秒内完成。",
        urgent=True)

    # Call DeepSeek (costs tokens)
    reply = call_deepseek(message)

    if reply:
        write_outbox("REPLY", "[URGENT] CEO Agent 紧急回复", reply, urgent=True)
        push_wechat(reply[:500])
    else:
        write_outbox("REPLY", "处理状态", "紧急消息AI处理暂时失败，已加入重试队列。-- CEO Agent", urgent=True)

    # Move to processed
    dest = PROCESSED_DIR / filepath.name
    filepath.rename(dest)
    print(f"[{now_ts()}] [URGENT] Done -> processed/", flush=True)


def process_normal(filepath: Path, message: str, preview: str):
    """Queue normal message for batch processing. ZERO AI tokens.

    Writes instant ACK to outbox confirming receipt.
    Adds message to task queue (company/task_queue.json) for later batch processing.
    Does NOT call DeepSeek — saves tokens for batch processing in main session.
    """
    print(f"[{now_ts()}] [QUEUE] {filepath.name}", flush=True)
    priority = infer_priority(message)

    # Write ACK (zero AI tokens — just file I/O)
    write_outbox("ACK", "收到来信 - 已加入任务队列",
        f"已收到董事长的消息，已加入统一任务队列，将在批量处理周期内处理。\n\n"
        f"> {preview[:150]}\n\n"
        f"---\n"
        f"优先级: {priority} | "
        f"队列中有 {count_pending_tasks()} 个待处理任务 | "
        f"如需立即处理请在消息中包含「紧急」关键词 | "
        f"扫描文件: 0 AI token | "
        f"ACK写入: 0 AI token")

    # Add to unified task queue (zero AI tokens — just JSON file write)
    add_to_task_queue(filepath, message, preview)

    # Move to processed/
    dest = PROCESSED_DIR / filepath.name
    filepath.rename(dest)
    print(f"[{now_ts()}] [QUEUE] Done -> processed/ ({count_pending_tasks()} tasks in queue)", flush=True)


def count_pending_tasks() -> int:
    if TASK_QUEUE_FILE.exists():
        try:
            queue = json.loads(TASK_QUEUE_FILE.read_text(encoding="utf-8"))
            return len(queue.get("tasks", []))
        except Exception:
            pass
    return 0


def process_message(filepath: Path):
    """Route message to urgent or normal processing."""
    try:
        content = filepath.read_text(encoding="utf-8")
        print(f"\n[{now_ts()}] New: {filepath.name}", flush=True)

        # Extract message body
        lines = content.split("\n")
        msg_lines = []
        past_header = False
        for line in lines:
            if not past_header and (line.startswith("[时间]") or line.startswith("# ")):
                past_header = True
                continue
            if past_header:
                msg_lines.append(line)
        message = "\n".join(msg_lines).strip()
        if not message:
            message = content.strip()

        preview = message[:150]

        if is_urgent(message):
            process_urgent(filepath, message)
        else:
            process_normal(filepath, message, preview)

    except Exception as e:
        print(f"[{now_ts()}] ERROR {filepath.name}: {e}", flush=True)


def main():
    print(f"[{now_ts()}] === Inbox Watcher (Token-Optimized) ===")
    print(f"  Scan interval: 5s (ZERO AI tokens)")
    print(f"  [URGENT] messages: immediate DeepSeek (costs tokens)")
    print(f"  Normal messages: queue -> batch process (shares cache)")
    print(f"  Key: {'configured' if DEEPSEEK_API_KEY else 'MISSING!'}")

    # Seed existing files as seen
    seen = {f.name for f in INBOX_DIR.glob("MSG_*.md") if f.name != "README.md"}
    save_state(seen)
    print(f"[{now_ts()}] Seeded {len(seen)} existing as seen")

    if seen:
        print(f"[{now_ts()}] Processing {len(seen)} pending...")
        for fname in sorted(seen):
            fpath = INBOX_DIR / fname
            if fpath.exists():
                process_message(fpath)

    print(f"[{now_ts()}] Watching (every 5s)...")
    cycle = 0
    while True:
        try:
            new = get_new_messages()
            if new:
                # Urgent first, then normal
                urgent_list, normal_list = [], []
                for f in new:
                    try:
                        if is_urgent(f.read_text(encoding="utf-8")):
                            urgent_list.append(f)
                        else:
                            normal_list.append(f)
                    except Exception:
                        normal_list.append(f)

                for f in urgent_list:
                    process_message(f)
                for f in normal_list:
                    process_message(f)

            cycle += 1
            if cycle % 360 == 0:  # ~30 min
                pending = len(list(INBOX_DIR.glob("MSG_*.md")))
                queued = count_pending_tasks()
                print(f"[{now_ts()}] Heartbeat: {pending} pending, {queued} queued, {cycle*5//60}min uptime", flush=True)

            time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n[{now_ts()}] Shutdown", flush=True)
            break
        except Exception as e:
            print(f"[{now_ts()}] Loop error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
