#!/usr/bin/env python3
"""Queue a bounded self-evolution task for the persistent agent session.

This script is intentionally pure Python. It may be called by
background_scheduler.py, but it must not start a fresh AI process. The actual
AI work should happen inside the long-lived inbox-processing session so prompt
cache and project context are preserved.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVOLVE_QUEUE_DIR = PROJECT_ROOT / "company" / "evolution_queue"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
PROGRESS_FILE = PROJECT_ROOT / "company" / "harness" / "PROGRESS.md"
LOGS_DIR = PROJECT_ROOT / "logs"
BEIJING_TZ = timezone(timedelta(hours=8))

sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task_claim import release, try_acquire


def _now() -> datetime:
    return datetime.now(BEIJING_TZ)


def _ts() -> str:
    return _now().strftime("%Y%m%d_%H%M%S")


def _existing_pending_task() -> Path | None:
    """Return an unprocessed auto-evolution task if one is already queued."""
    EVOLVE_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    pending = sorted(EVOLVE_QUEUE_DIR.glob("AUTO_EVOLVE_*.md"), key=lambda p: p.stat().st_mtime)
    return pending[0] if pending else None


def _latest_log_hint() -> str:
    if not LOGS_DIR.exists():
        return "(logs directory missing)"
    files = sorted(
        (p for p in LOGS_DIR.glob("*.log") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return "(no log files found)"
    return "\n".join(f"- {p.name} ({p.stat().st_size} bytes)" for p in files[:8])


def _build_task() -> str:
    now = _now().strftime("%Y-%m-%d %H:%M:%S %Z")
    progress_hint = (
        PROGRESS_FILE.read_text(encoding="utf-8", errors="replace")[:1200]
        if PROGRESS_FILE.exists()
        else "(PROGRESS.md missing)"
    )
    return f"""# AUTO_EVOLVE 自进化任务

时间：{now}
来源：`scripts/self_evolve.py`（background_scheduler 纯 Python 触发）

## 执行原则

1. 必须在当前持久会话内处理，不要启动新的 `claude -p`、`codex -p`、CronCreate 或独立 AI 轮询。
2. 先读 `company/departments/execution/context_state.json`、`company/harness/PROGRESS.md` 和最近日志。
3. 只选择一个可验证、低风险的改进点；优先修复重复失败、编码、调度、行情数据、质量门问题。
4. 不读取或复述 `.env` / token / credential；发现密钥只写安全告警路径，不复制值。
5. 不 `git push`、不 `--no-verify`、不 `git add -A`；如需提交，先向董事长汇报变更范围。
6. 完成后更新 `company/harness/PROGRESS.md`，并在 `company/chairman_outbox/` 写一份结果报告。

## 本轮建议观察点

最近日志文件：
{_latest_log_hint()}

当前 harness 摘要：

```text
{progress_hint}
```

## 验收标准

- 至少给出一个明确的问题、根因、修改或不修改的理由。
- 如修改代码，运行最小验证命令并报告结果。
- 如不修改代码，说明阻塞条件和下一步最小动作。
"""


def queue_task() -> Path | None:
    pending = _existing_pending_task()
    if pending:
        print(f"[SKIP] pending auto-evolve task exists: {pending.name}", flush=True)
        return None

    EVOLVE_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    task_path = EVOLVE_QUEUE_DIR / f"AUTO_EVOLVE_{_ts()}.md"
    task_path.write_text(_build_task(), encoding="utf-8")
    print(f"[OK] queued {task_path}", flush=True)
    return task_path


def main() -> int:
    acquired, reason = try_acquire("self_evolve")
    if not acquired:
        print(f"[SKIP] self_evolve lock not acquired: {reason}", flush=True)
        return 0

    try:
        queued = queue_task()
        if queued is None:
            return 0

        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        notice = OUTBOX_DIR / f"SENTINEL_self_evolve_queued_{_ts()}.md"
        notice.write_text(
            "# 🧬 自进化任务已入队\n\n"
            f"- 任务：`{queued.relative_to(PROJECT_ROOT)}`\n"
            "- 触发器：`scripts/background_scheduler.py`\n"
            "- 模式：纯 Python 入队；不会自动触发 AI，需要人工确认后再处理。\n",
            encoding="utf-8",
        )
        return 0
    finally:
        ok, msg = release("self_evolve")
        print(f"[LOCK] release self_evolve: {ok} {msg}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
