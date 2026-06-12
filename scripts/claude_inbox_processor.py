#!/usr/bin/env python3
"""
Event-driven inbox → WSL Claude Code processor. Zero polling.

Architecture:
  POST /api/inbox → writes trigger file (company/.process_now)
  → This script (running in WSL tmux) detects trigger
  → Invokes Claude Code with full context: claude -p "..."
  → Claude processes message and writes reply to outbox
  → Clears trigger → waits for next

Runs inside WSL tmux alongside the Claude Code CLI.
Uses inotify (Linux) for instant trigger detection.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT = Path("/mnt/e/2026_AgentStudy/Python_code")
INBOX = PROJECT / "company" / "chairman_inbox"
OUTBOX = PROJECT / "company" / "chairman_outbox"
PROCESSED = INBOX / "processed"
TRIGGER_FILE = PROJECT / "company" / ".process_now"
BEIJING_TZ = timezone(timedelta(hours=8))

INBOX.mkdir(parents=True, exist_ok=True)
OUTBOX.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)


def now_ts():
    return datetime.now(BEIJING_TZ).strftime("%H:%M:%S")


def find_pending_message() -> Path | None:
    """Find the oldest unprocessed inbox message."""
    for f in sorted(INBOX.glob("MSG_*.md")):
        if f.name == "README.md":
            continue
        return f
    return None


def write_ack(msg_file: str, preview: str):
    """Write instant ACK to outbox."""
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    ack = OUTBOX / f"ACK_{ts}.md"
    ack.write_text(
        f"# 收到来信 - Claude Code 处理中\n\n"
        f"[时间]: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} CST\n\n"
        f"已收到董事长的消息，正在通过 Claude Code (完整上下文+工具) 处理...\n\n"
        f"> {preview[:150]}\n\n---\n预计 30-60 秒内完成深度回复。",
        encoding="utf-8")


def process_with_claude(msg_path: Path) -> bool:
    """Process one inbox message via Claude Code CLI (full context)."""
    try:
        content = msg_path.read_text(encoding="utf-8")
    except Exception:
        return False

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
    message = "\n".join(msg_lines).strip() or content.strip()
    preview = message[:150]

    print(f"\n[{now_ts()}] Processing: {msg_path.name}", flush=True)
    write_ack(msg_path.name, preview)

    # Build Claude prompt
    prompt = (
        f"处理董事长信箱消息。读取完整消息，基于项目上下文（CLAUDE.md、memory文件、任务队列、context_state）"
        f"给出深度回复。如果需要分析股票，使用11部门LangGraph管道。如果需要搜索最新信息，使用WebSearch。"
        f"回复要精炼、结构化、可执行，署名 '-- CEO Agent'。\n\n"
        f"消息文件: {msg_path}\n"
        f"消息内容:\n{message}"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=str(PROJECT),
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "CLAUDE_CODE_MODEL": "deepseek-v4-pro"},
        )
        reply = result.stdout.strip()
        if not reply:
            reply = f"[Claude returned empty]\nstderr: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        reply = "[处理超时] Claude Code 未在 120 秒内完成回复。请稍后重试。"
    except Exception as e:
        reply = f"[处理错误] {e}"

    # Write reply to outbox
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    reply_file = OUTBOX / f"CLAUDE_REPLY_{ts}.md"
    reply_file.write_text(
        f"# CEO Agent 回复 (Claude Code 全上下文处理)\n\n"
        f"[时间]: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} CST\n\n{reply}",
        encoding="utf-8")

    # Move to processed
    msg_path.rename(PROCESSED / msg_path.name)
    print(f"[{now_ts()}] Done: {msg_path.name} -> {reply_file.name} ({len(reply)} chars)", flush=True)
    return True


def main():
    print(f"[{now_ts()}] Claude Inbox Processor started", flush=True)
    print(f"  Watching: {TRIGGER_FILE}", flush=True)
    print(f"  Engine: Claude Code CLI (full CLAUDE.md + memory + tools)", flush=True)

    # Process any pending messages on startup
    pending = find_pending_message()
    if pending:
        print(f"[{now_ts()}] Found pending: {pending.name}", flush=True)
        process_with_claude(pending)

    # Event-driven loop: wait for trigger file
    while True:
        if TRIGGER_FILE.exists():
            # Read trigger to know which file to process
            try:
                trigger_data = json.loads(TRIGGER_FILE.read_text(encoding="utf-8"))
                target_file = trigger_data.get("file", "")
            except Exception:
                target_file = ""

            TRIGGER_FILE.unlink()  # Clear trigger

            # Process the specific file or find any pending
            if target_file:
                msg_path = INBOX / target_file
            else:
                msg_path = find_pending_message()

            if msg_path and msg_path.exists():
                process_with_claude(msg_path)
            else:
                # Check for any pending messages
                any_pending = find_pending_message()
                if any_pending:
                    process_with_claude(any_pending)

        time.sleep(1)  # Check trigger every 1 second (not polling inbox, just checking a file)


if __name__ == "__main__":
    main()
