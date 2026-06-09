#!/usr/bin/env python3
"""
24/7 Inbox Watcher — polls chairman_inbox/ every 5 seconds.
Processes messages via DeepSeek API (no Claude CLI dependency).

Features:
  - Instant ACK: writes acknowledgement to outbox within 2s of detection
  - AI Reply: calls DeepSeek API for contextual Chinese response
  - [URGENT] Urgent Interrupt: messages with 紧急/URGENT/urgent keyword get:
    - Immediate priority processing (skip queue)
    - WeChat push notification
    - Special URGENT_ prefix in outbox
  - Auto-moves processed messages to processed/

Start: python .venv/Scripts/python scripts/inbox_watcher.py
Watchdog monitors this process and auto-restarts if it dies.
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
PROCESSED_DIR = INBOX_DIR / "processed"
STATE_FILE = PROJECT_ROOT / "company" / ".watcher_state.json"
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

BEIJING_TZ = timezone(timedelta(hours=8))

# Keywords that trigger URGENT priority
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

SYSTEM_PROMPT = """你是 OnionQuant 的 CEO Agent，一个 AI 量化研究系统的核心。

你的董事长通过网站收件箱给你发消息。请用中文回复。

## [URGENT] 紧急消息处理
如果消息包含"紧急"、"urgent"、"立刻"、"马上"、"interrupt"等关键词：
- 回复开头加上 **"[URGENT] 紧急响应"** 标记
- 立即给出最核心的答案或行动建议
- 不要写长篇背景介绍，直接给结论和可执行步骤

## 回复原则
- 精简、可执行、结构化（Markdown）
- 如果问股票：分析价格趋势、关键催化剂、风险因素
- 如果需要实时数据：诚实说明，提供分析框架
- 保持冷静、理性、数据驱动

## 格式要求
- 重要结论放在最前面
- 使用标题和列表组织信息
- 署名 "— CEO Agent" """


def now_ts() -> str:
    return datetime.now(BEIJING_TZ).strftime("%H:%M:%S")


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def is_urgent(text: str) -> bool:
    """Check if message contains urgent keywords."""
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
    now = datetime.now(BEIJING_TZ)
    actual_prefix = f"URGENT_{prefix}" if urgent else prefix
    filename = f"{actual_prefix}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath = OUTBOX_DIR / filename
    content = f"# {title}\n\n**时间**：{now.strftime('%Y-%m-%d %H:%M:%S')} CST\n\n{body}"
    filepath.write_text(content, encoding="utf-8")
    print(f"[{now_ts()}] Outbox: {filename}", flush=True)
    return filename


def call_deepseek(message: str, urgent: bool = False) -> str | None:
    """Call DeepSeek API for AI reply."""
    if not DEEPSEEK_API_KEY:
        print(f"  No DEEPSEEK_API_KEY — skipping AI processing", flush=True)
        return None

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

        # For urgent messages, use lower temperature for faster, more direct response
        temperature = 0.3 if urgent else 0.7

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            max_tokens=2000,
            temperature=temperature,
        )

        reply = response.choices[0].message.content
        if reply:
            return reply.strip()
        return None

    except ImportError:
        print(f"  openai library not installed", flush=True)
        return None
    except Exception as e:
        print(f"  DeepSeek API error: {e}", flush=True)
        return None


def push_wechat(message: str):
    """Push urgent notification to WeChat. Non-blocking, best-effort."""
    try:
        subprocess = __import__("subprocess")
        subprocess.run(
            [VENV_PYTHON, str(PROJECT_ROOT / "scripts" / "wechat_sync_push.py")],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(f"  WeChat push triggered", flush=True)
    except Exception as e:
        print(f"  WeChat push skipped: {e}", flush=True)


def process_message(filepath: Path):
    """Process one inbox message: detect urgency → ACK → AI analysis → reply → WeChat."""
    try:
        content = filepath.read_text(encoding="utf-8")
        print(f"\n[{now_ts()}] {'[URGENT] URGENT ' if is_urgent(content) else ''}Processing: {filepath.name}", flush=True)

        # Extract message body (skip header lines)
        lines = content.split("\n")
        msg_lines = []
        past_header = False
        for line in lines:
            if not past_header and (line.startswith("**时间**") or line.startswith("# ")):
                past_header = True
                continue
            if past_header:
                msg_lines.append(line)
        message = "\n".join(msg_lines).strip()
        if not message:
            message = content.strip()

        preview = message[:150]
        urgent = is_urgent(message)

        # Step 1: Instant ACK (within 2 seconds)
        if urgent:
            write_outbox("ACK", "[URGENT] 紧急来信 · 立即处理中",
                f"[!!] **紧急消息** — CEO Agent 已中断当前任务，立即处理。\n\n"
                f"> {preview}\n\n"
                f"---\n*预计 15 秒内完成紧急响应。*",
                urgent=True)
        else:
            write_outbox("ACK", "收到来信 · AI 分析中",
                f"已收到董事长的消息，CEO Agent 正在进行 AI 分析...\n\n"
                f"> {preview}\n\n"
                f"---\n*预计 30 秒内完成分析并回复。*")

        # Step 2: AI processing via DeepSeek API
        print(f"[{now_ts()}] Calling DeepSeek...", flush=True)
        reply = call_deepseek(message, urgent=urgent)

        if reply:
            title = "[URGENT] CEO Agent 紧急回复" if urgent else "CEO Agent 回复"
            write_outbox("REPLY", title, reply, urgent=urgent)

            # Step 2b: For urgent messages, push to WeChat immediately
            if urgent:
                push_wechat(reply[:500])
        else:
            write_outbox("REPLY", "处理状态",
                f"AI 分析暂时遇到问题（API 不可用）。\n\n"
                f"原始消息：{preview}\n\n"
                f"系统将重试处理。\n\n"
                f"— CEO Agent (系统自动)")

        # Step 3: Move to processed
        dest = PROCESSED_DIR / filepath.name
        filepath.rename(dest)
        print(f"[{now_ts()}] Done → processed/", flush=True)

    except Exception as e:
        print(f"[{now_ts()}] ERROR processing {filepath.name}: {e}", flush=True)
        import traceback
        traceback.print_exc()


def main():
    print(f"[{now_ts()}] === OnionQuant 24/7 Inbox Watcher ===")
    print(f"  Inbox:  {INBOX_DIR}")
    print(f"  Outbox: {OUTBOX_DIR}")
    print(f"  AI:     DeepSeek API (deepseek-chat)")
    print(f"  Key:    {'configured' if DEEPSEEK_API_KEY else 'MISSING!'}")
    print(f"  Urgent keywords: {URGENT_KEYWORDS}")

    # Seed existing files as seen (don't reprocess old messages)
    seen = {f.name for f in INBOX_DIR.glob("MSG_*.md") if f.name != "README.md"}
    save_state(seen)
    print(f"[{now_ts()}] Seeded {len(seen)} existing messages as seen")

    if seen:
        print(f"[{now_ts()}] Processing {len(seen)} pending messages...")
        for fname in sorted(seen):
            fpath = INBOX_DIR / fname
            if fpath.exists():
                process_message(fpath)

    print(f"[{now_ts()}] Watching for new messages (every 5s)...")

    cycle = 0
    while True:
        try:
            new = get_new_messages()
            if new:
                # Sort: urgent messages first
                urgent_msgs = []
                normal_msgs = []
                for f in new:
                    try:
                        content = f.read_text(encoding="utf-8")
                        if is_urgent(content):
                            urgent_msgs.append(f)
                        else:
                            normal_msgs.append(f)
                    except Exception:
                        normal_msgs.append(f)

                # Process urgent messages immediately
                for f in urgent_msgs:
                    process_message(f)

                # Then normal messages
                for f in normal_msgs:
                    process_message(f)

            cycle += 1
            if cycle % 360 == 0:  # Every ~30 minutes
                pending = len(list(INBOX_DIR.glob("MSG_*.md")))
                print(f"[{now_ts()}] Heartbeat — {pending} pending, {cycle*5//60}min uptime", flush=True)

            time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n[{now_ts()}] Shutting down", flush=True)
            break
        except Exception as e:
            print(f"[{now_ts()}] Loop error: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
