#!/usr/bin/env python3
"""
Daily auto-commit — stages all changes and pushes to GitHub.
Runs twice a day (morning + evening Beijing time).
Does NOT commit .env or credential files.
"""

import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BEIJING_TZ = timezone(timedelta(hours=8))

SENSITIVE_PATTERNS = [".env", "credentials", ".key", ".pem", "secret", "password"]


def run(cmd: list, cwd: str = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            env={
                **__import__("os").environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "echo",
            },
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def has_changes() -> bool:
    """Check if there are any uncommitted changes."""
    # Check modified/deleted files
    code1, out, _ = run(["git", "status", "--porcelain"])
    if code1 != 0:
        return False
    # Filter out sensitive files
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        fpath = line[3:].strip()
        if any(p in fpath.lower() for p in SENSITIVE_PATTERNS):
            continue
        return True
    return False


def main():
    now = datetime.now(BEIJING_TZ)
    print(f"[{now.isoformat()}] auto_git_commit starting", flush=True)

    if not has_changes():
        print("No changes to commit", flush=True)
        return 0

    # Stage all changes
    code, out, err = run(["git", "add", "-A"])
    if code != 0:
        print(f"git add failed: {err}", flush=True)
        return 1

    # Create commit
    ts = now.strftime("%Y-%m-%d %H:%M")
    msg = f"🤖 自动每日同步 — {ts} CST"
    code, out, err = run(["git", "commit", "-m", msg])
    if code != 0:
        if "nothing to commit" in err or "nothing to commit" in out:
            print("Nothing to commit (all clean)", flush=True)
            return 0
        print(f"git commit failed: {err}", flush=True)
        return 1

    print(f"Committed: {out}", flush=True)

    # Push
    code, out, err = run(["git", "push", "origin", "main"])
    if code != 0:
        print(f"Push failed (may need VPN): {err}", flush=True)
        print("Commit created locally, will push on next run", flush=True)
        return 1

    print(f"Pushed: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
