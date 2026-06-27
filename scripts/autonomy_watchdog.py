#!/usr/bin/env python3
"""Autonomy watchdog for the 24h self-evolution loop.

This script is deliberately pure Python and non-AI. It records heartbeat state,
checks whether the main agent has gone stale, and queues a recovery task that a
future Codex session can pick up. It never starts a new AI process by itself.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "company" / "runtime"
QUEUE_DIR = PROJECT_ROOT / "company" / "evolution_queue"
HEARTBEAT_FILE = RUNTIME_DIR / "agent_heartbeat.json"
STATUS_FILE = RUNTIME_DIR / "autonomy_status.json"
BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_TTL_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(BEIJING_TZ)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_heartbeat(session_id: str, status: str = "running", note: str = "") -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "status": status,
        "note": note,
        "pid": os.getpid(),
        "updated_at": _now_iso(),
        "updated_at_epoch": time.time(),
    }
    _write_json(HEARTBEAT_FILE, payload)
    return payload


def pending_recovery_tasks() -> list[Path]:
    if not QUEUE_DIR.exists():
        return []
    return sorted(QUEUE_DIR.glob("AUTO_EVOLVE_RECOVERY_*.md"), key=lambda p: p.stat().st_mtime)


def pending_evolution_tasks() -> list[Path]:
    if not QUEUE_DIR.exists():
        return []
    return sorted(QUEUE_DIR.glob("AUTO_EVOLVE*.md"), key=lambda p: p.stat().st_mtime)


def inspect(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict[str, Any]:
    heartbeat = _read_json(HEARTBEAT_FILE)
    now_epoch = time.time()
    age_seconds: float | None = None
    stale = True
    if heartbeat and isinstance(heartbeat.get("updated_at_epoch"), (int, float)):
        age_seconds = max(0.0, now_epoch - float(heartbeat["updated_at_epoch"]))
        stale = age_seconds > ttl_seconds

    status = {
        "checked_at": _now_iso(),
        "ttl_seconds": ttl_seconds,
        "heartbeat_path": str(HEARTBEAT_FILE.relative_to(PROJECT_ROOT)),
        "heartbeat": heartbeat,
        "heartbeat_age_seconds": age_seconds,
        "heartbeat_stale": stale,
        "pending_evolution_tasks": [str(p.relative_to(PROJECT_ROOT)) for p in pending_evolution_tasks()],
        "pending_recovery_tasks": [str(p.relative_to(PROJECT_ROOT)) for p in pending_recovery_tasks()],
    }
    _write_json(STATUS_FILE, status)
    return status


def queue_recovery_task(reason: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Path | None:
    status = inspect(ttl_seconds=ttl_seconds)
    if not status["heartbeat_stale"]:
        return None
    if pending_recovery_tasks():
        return None

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    task_path = QUEUE_DIR / f"AUTO_EVOLVE_RECOVERY_{_now().strftime('%Y%m%d_%H%M%S')}.md"
    task_path.write_text(
        "# AUTO_EVOLVE_RECOVERY 接班任务\n\n"
        f"时间：{_now_iso()}\n"
        f"原因：{reason}\n\n"
        "## 接班规则\n\n"
        "1. 先读取 `company/departments/execution/context_state.json`、"
        "`company/runtime/autonomy_status.json`、`company/runtime/agent_heartbeat.json`。\n"
        "2. 尝试获取 `python scripts/task_claim.py try autonomy`。获取失败立即退出。\n"
        "3. 每完成一个工作单元，运行 `python scripts/autonomy_watchdog.py heartbeat --session-id <id>`。\n"
        "4. 常态只保留一个主建设会话。并行只用于最多 2-3 个独立搜索/审查任务。\n"
        "5. 项目目录和 GitHub 仓库允许自动重构、提交、推送；禁止删除工作区外个人文件、花钱、真实下单、输出密钥值。\n"
        "6. 先恢复未完成 P0，再继续网站/GitHub/交易研究系统自动进化。\n\n"
        "## 最近状态\n\n"
        "```json\n"
        f"{json.dumps(status, ensure_ascii=False, indent=2)}\n"
        "```\n",
        encoding="utf-8",
    )
    return task_path


def main() -> int:
    parser = argparse.ArgumentParser(description="OnionQuant autonomy watchdog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    hb = sub.add_parser("heartbeat", help="write a main-agent heartbeat")
    hb.add_argument("--session-id", default="codex-main")
    hb.add_argument("--status", default="running")
    hb.add_argument("--note", default="")

    check = sub.add_parser("check", help="inspect heartbeat and queue state")
    check.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)

    qis = sub.add_parser("queue-if-stale", help="queue a recovery task if heartbeat is stale")
    qis.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)
    qis.add_argument("--reason", default="main agent heartbeat stale")

    args = parser.parse_args()

    if args.cmd == "heartbeat":
        print(json.dumps(write_heartbeat(args.session_id, args.status, args.note), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "check":
        print(json.dumps(inspect(args.ttl_seconds), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "queue-if-stale":
        queued = queue_recovery_task(args.reason, args.ttl_seconds)
        print(f"QUEUED:{queued}" if queued else "NOOP")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
