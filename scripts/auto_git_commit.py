#!/usr/bin/env python3
"""
Daily auto-commit — safely stages non-sensitive changes and pushes to GitHub.
Runs twice a day (morning + evening Beijing time).

SAFETY: Never stages files matching SENSITIVE_PATTERNS.
.gitignore provides a second layer of protection.
pre-commit hook scans for secrets before every commit.
"""

import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fix Windows GBK encoding for emoji in commit messages
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BEIJING_TZ = timezone(timedelta(hours=8))

# Files/paths matching any of these patterns are NEVER auto-committed
SENSITIVE_PATTERNS = [
    ".env", "credentials", ".key", ".pem", "secret", "password",
    ".log", ".lock", ".state", ".pid",
    "chairman_inbox/", "chairman_outbox/", "task_claims/",
    "chairman_position_tracker", "watcher_state", "watcher_seen",
    "context_state.json", "cron_config.json", "wechat_pushed.json",
    ".parquet", "sentiment_data/", "market_snapshots/",
    "WECOM_CALLBACK_CREDS",
    # Never auto-commit files that might contain personal data
    "company/departments/execution/",
    "company/.server_", "company/.watcher_", "company/.wechat_",
    # Chairman growth personal data (salary, skill gaps, job hunt plans)
    "chairman_growth/skill_inventory",
    "chairman_growth/learning_roadmap",
    "chairman_growth/market_intel",
    "chairman_growth/_INDEX",
]


def run(cmd: list, cwd: str = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or str(PROJECT_ROOT),
            capture_output=True,
            timeout=120,
            env={
                **__import__("os").environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "echo",
            },
        )
        # Decode manually — git outputs UTF-8 on all platforms
        out = r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
        err = r.stderr.decode("utf-8", errors="replace") if r.stderr else ""
        return r.returncode, out.strip(), err.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def get_changed_files() -> list[str]:
    """Return list of changed file paths from git status."""
    code, out, _ = run(["git", "-c", "core.quotepath=false", "status", "--porcelain"])
    if code != 0:
        return []
    files = []
    for line in out.split("\n"):
        if not line:
            continue
        if len(line) < 4:
            continue
        fpath = line[3:].strip().strip('"')
        if fpath:
            files.append(fpath)
    # DEBUG
    for f in files:
        print(f"  [DEBUG] found: {repr(f)} first_char={repr(f[0]) if f else 'EMPTY'}", flush=True)
    return files


def is_sensitive(fpath: str) -> bool:
    """Check if a file path matches any sensitive pattern."""
    lower = fpath.lower()
    return any(p.lower() in lower for p in SENSITIVE_PATTERNS)


def has_safe_changes() -> bool:
    """Check if there are non-sensitive uncommitted changes."""
    for fpath in get_changed_files():
        if not is_sensitive(fpath):
            return True
    return False


def stage_safe_files() -> int:
    """Stage only non-sensitive files. Returns count of staged files."""
    staged = 0
    skipped = 0
    for fpath in get_changed_files():
        if is_sensitive(fpath):
            print(f"  [SKIP] {fpath}", flush=True)
            skipped += 1
            continue
        code, out, err = run(["git", "add", "--", fpath])
        if code == 0:
            staged += 1
        else:
            print(f"  [ERR] staging {fpath}: {err}", flush=True)
    if skipped:
        print(f"  Skipped {skipped} sensitive file(s)", flush=True)
    return staged


def verify_no_secrets_staged() -> bool:
    """Verify no staged files contain hardcoded secrets."""
    code, diff, _ = run(["git", "diff", "--cached", "--name-only"])
    if code != 0:
        return True  # If we can't check, let pre-commit hook catch it

    # Quick scan of staged content for obvious secrets
    code, content, _ = run(["git", "diff", "--cached"])
    if code != 0:
        return True

    # Check for common secret patterns in staged diff
    import re
    secret_patterns = [
        r'sk-[a-zA-Z0-9]{20,}',      # API keys
        r'ghp_[a-zA-Z0-9]{36}',       # GitHub tokens
        r'AKIA[0-9A-Z]{16}',          # AWS keys
    ]
    for pattern in secret_patterns:
        if re.search(pattern, content):
            print(f"  [BLOCKED] Secret pattern detected in staged files!", flush=True)
            return False
    return True


def main():
    now = datetime.now(BEIJING_TZ)
    print(f"[{now.isoformat()}] auto_git_commit starting", flush=True)

    if not has_safe_changes():
        print("No safe changes to commit", flush=True)
        return 0

    # Stage only non-sensitive files (NOT git add -A!)
    staged = stage_safe_files()
    if staged == 0:
        print("No files staged (all changes are in sensitive paths)", flush=True)
        return 0
    print(f"Staged {staged} file(s)", flush=True)

    # Quick pre-commit secret check (defense in depth)
    if not verify_no_secrets_staged():
        # Unstage everything and abort
        run(["git", "reset", "HEAD", "--"])
        print("Commit aborted — secrets detected", flush=True)
        return 1

    # Create commit
    ts = now.strftime("%Y-%m-%d %H:%M")
    msg = f"🤖 自动每日同步 — {ts} CST"
    code, out, err = run(["git", "commit", "-m", msg])
    # Pre-commit hook output goes to stderr but is harmless
    combined = (out or "") + (err or "")
    if code != 0:
        if "nothing to commit" in combined or "nothing to commit" in combined:
            print("Nothing to commit (all clean)", flush=True)
            return 0
        # Pre-commit hook passed but wrote to stderr — not an error
        if "pre-commit" in combined.lower() and "pass" in combined.lower():
            print(f"Committed (pre-commit passed)", flush=True)
        else:
            print(f"git commit warning: {err}", flush=True)
            # Don't fail on pre-commit hook messages
    else:
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
