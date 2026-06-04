"""
memory_sync.py — 记忆自动同步脚本
从项目状态文件(TASK_TRACKER + TIMELINE + _INDEX.md)自动更新 Claude Code memory 文件

由持续迭代引擎 cron (每15分钟) 或手动触发。
"""

import re
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).resolve().parent.parent
MEMORY_DIR = (
    Path.home() / ".claude" / "projects" / "e--2026-AgentStudy-Python-code" / "memory"
)


def sync_project_state():
    """从 TASK_TRACKER.md 同步任务计数到 memory/project_state.md"""
    tracker = PROJECT / "TASK_TRACKER.md"
    if not tracker.exists():
        return

    text = tracker.read_text(encoding="utf-8")
    completed = len(
        re.findall(r"✅.*完成|✅.*实施|✅.*替换|✅.*创建|✅.*研究|✅.*增强", text)
    )
    in_progress = len(re.findall(r"🔵.*进行中", text))

    memory_file = MEMORY_DIR / "project_state.md"
    if memory_file.exists():
        content = memory_file.read_text(encoding="utf-8")
        content = re.sub(r"\d+任务完成", f"{completed}任务完成", content)
        content = re.sub(r"\d+个进行中", f"{in_progress}个进行中", content)
        content = re.sub(
            r"originSessionId: [^\n]+",
            f"originSessionId: auto-sync-{datetime.now().strftime('%Y%m%d-%H%M')}",
            content,
        )
        memory_file.write_text(content, encoding="utf-8")
        print(
            f"  ✓ project_state.md synced ({completed} done, {in_progress} in progress)"
        )

    return completed, in_progress


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] memory_sync running...")
    sync_project_state()
    print("  ✓ memory sync complete")


if __name__ == "__main__":
    main()
