#!/usr/bin/env python3
"""
Background task scheduler — runs Python scripts on a cron-like schedule.
Replaces CronCreate for non-AI tasks to avoid cold-start Claude sessions.

Runs wechat_sync (5min), sentiment_hourly, research_publisher (30min 13-20 1-5),
daily pipeline (6:07 1-5).

Zero AI token consumption — pure Python subprocess.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

from scripts._subprocess_utils import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Docker / container: use the system Python; Windows dev: use .venv
_VENV_CANDIDATES = [
    PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",  # Windows
    PROJECT_ROOT / ".venv" / "bin" / "python",           # Linux/macOS venv
]
VENV_PYTHON = str(
    next((p for p in _VENV_CANDIDATES if p.exists()), __import__("sys").executable)
)


def run_script(script_name: str, args: list = None, timeout: int = 120) -> bool:
    script_path = PROJECT_ROOT / "scripts" / script_name
    if not script_path.exists():
        print(f"[SKIP] {script_name} not found", flush=True)
        return False
    try:
        cmd = [VENV_PYTHON, str(script_path)] + (args or [])
        env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
        result = run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        status = "OK" if result.returncode == 0 else f"ERR({result.returncode})"
        print(f"[{status}] {script_name}", flush=True)
        if result.stdout:
            for line in result.stdout.strip().split("\n")[:5]:
                print(f"  {line}", flush=True)
        if result.stderr:
            for line in result.stderr.strip().split("\n")[:3]:
                print(f"  stderr: {line}", flush=True)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {script_name}", flush=True)
        return False
    except Exception as e:
        print(f"[ERROR] {script_name}: {e}", flush=True)
        return False


def should_run(cron_spec: str, now: datetime) -> bool:
    """Minimal cron parser: minute,hour,dow with */N, comma, single values."""
    minute_part, hour_part, _, _, dow_part = cron_spec.split()

    def match(field: str, value: int) -> bool:
        if field == "*":
            return True
        for part in field.split(","):
            if "/" in part:
                step = int(part.split("/")[1])
                if value % step == 0:
                    return True
            elif "-" in part:
                lo, hi = map(int, part.split("-"))
                if lo <= value <= hi:
                    return True
            else:
                if int(part) == value:
                    return True
        return False

    return (
        match(minute_part, now.minute)
        and match(hour_part, now.hour)
        and match(dow_part, now.isoweekday())  # 1=Mon, 7=Sun
    )


def main():
    print(f"[{datetime.now().isoformat()}] Background scheduler started", flush=True)

    # Task definitions: (cron_spec, script_name, [args], timeout_seconds)
    tasks = [
        ("2,7,12,17,22,27,32,37,42,47,52,57 * * * *", "wechat_sync_push.py", [], 60),
        ("9 22,23,0,1,2,3 * * 1-5", "sentiment_hourly_push.py", [], 120),
        ("7 6 * * 1-5", "run_pipeline.py", [], 600),
        ("0,30 13-20 * * 1-5", "research_publisher.py", [], 120),
        # Market monitor every 60min during US extended hours (14:00-04:00 BJT)
        (
            "17 14,15,16,17,18,19,20,21,22,23,0,1,2,3 * * 1-5",
            "market_monitor.py",
            ["--once"],
            120,
        ),
        # Heat collector — every 60 min all day (zero AI tokens)
        ("7 * * * *", "heat_collector.py", ["--once"], 120),
        # Auto git commit — twice daily (10:07 morning + 22:07 evening BJT)
        ("7 10,22 * * *", "auto_git_commit.py", [], 120),
        # Health monitor — twice daily (08:03 + 20:03 BJT), auto-recover if server down
        ("3 8,20 * * *", "health_monitor.py", [], 60),
        # Content reviewer — twice daily (09:13 + 21:13 BJT), no AI tokens
        ("13 9,21 * * *", "content_review.py", [], 60),
        # Self-evolution cycle — every 6 hours (03:17, 09:17, 15:17, 21:17 BJT)
        ("17 3,9,15,21 * * *", "self_evolve.py", [], 360),
    ]

    print(f"Watching {len(tasks)} tasks", flush=True)
    last_run = {script: 0 for _, script, _, _ in tasks}

    while True:
        now = datetime.now()
        for cron_spec, script, args, timeout in tasks:
            if should_run(cron_spec, now):
                sec_since = now.timestamp() - last_run[script]
                if sec_since >= 55:  # Avoid double-fire within same minute
                    print(
                        f"\n[{now.strftime('%H:%M:%S')}] Running {script}", flush=True
                    )
                    run_script(script, args, timeout)
                    last_run[script] = now.timestamp()
        time.sleep(30)


if __name__ == "__main__":
    main()
