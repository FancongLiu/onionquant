#!/usr/bin/env python3
"""
Real-time inbox watcher — polls chairman_inbox/ every 3 seconds.
When new messages appear, triggers immediate AI processing via WSL claude -p.
Gives <1 minute WeChat reply latency (vs 10-30 min before).
"""

import subprocess
import time
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
SEEN_FILE = PROJECT_ROOT / "company" / "watcher_seen.json"
VENV_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(list(seen), ensure_ascii=False), encoding="utf-8")


def get_new_messages():
    """Return list of new inbox .md files (exclude README.md and processed/)."""
    if not INBOX_DIR.exists():
        return []
    seen = load_seen()
    new = []
    for f in sorted(INBOX_DIR.glob("*.md")):
        if f.name == "README.md":
            continue
        if f.name not in seen:
            new.append(f)
            seen.add(f.name)
    save_seen(seen)
    return new


def process_inbox():
    """Run Claude one-shot to process inbox messages, then push to WeChat."""
    new_msgs = get_new_messages()
    if not new_msgs:
        return

    print(
        f"\n[{datetime.now().strftime('%H:%M:%S')}] NEW MESSAGES: {[f.name for f in new_msgs]}",
        flush=True,
    )

    # Step 1: Run AI processing via WSL claude
    prompt = "CEO inbox: process ALL pending messages in company/chairman_inbox/ (excluding README.md). For each: read content, write response to chairman_outbox/RESP_*.md. Move processed files to processed/. Then exit."
    try:
        result = subprocess.run(
            [
                "wsl",
                "bash",
                "-c",
                f"cd /mnt/e/2026_AgentStudy/Python_code && echo '2' | claude -p '{prompt}' --model deepseek-v4-pro --dangerously-skip-permissions 2>&1",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        print(f"  Claude: {result.stdout.strip()[:200]}", flush=True)
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()[:200]}", flush=True)
    except subprocess.TimeoutExpired:
        print("  TIMEOUT (180s)", flush=True)
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)

    # Step 2: Push replies to WeChat
    try:
        subprocess.run(
            [VENV_PYTHON, str(PROJECT_ROOT / "scripts" / "wechat_sync_push.py")],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        pass


def main():
    print(f"[{datetime.now().isoformat()}] Inbox watcher started", flush=True)
    print(f"Watching: {INBOX_DIR}", flush=True)

    # Seed: mark all existing files as seen
    seen = set()
    for f in sorted(INBOX_DIR.glob("*.md")):
        if f.name != "README.md":
            seen.add(f.name)
    save_seen(seen)
    print(f"Seeded {len(seen)} existing files", flush=True)

    cycle = 0
    while True:
        cycle += 1
        new = get_new_messages()
        if new:
            process_inbox()

        # Every 30 cycles (~90s), clean up seen files no longer in inbox
        if cycle % 30 == 0:
            current = {f.name for f in INBOX_DIR.glob("*.md") if f.name != "README.md"}
            saved = load_seen()
            # Remove entries for files that were processed (moved to processed/)
            cleaned = {name for name in saved if name in current or name not in saved}
            save_seen(cleaned)
            cycle = 0

        time.sleep(3)


if __name__ == "__main__":
    main()
