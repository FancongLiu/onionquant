#!/usr/bin/env python3
"""
inbox_scanner.py — 原子化收件箱扫描器

消除 .processing 孤儿锁文件问题。
cron 时间线已保证不重叠，无需锁机制。
流程: 扫描 → 原子移动 → 读取 → 交给 Claude CLI 处理
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

STALE_TIMEOUT_MINUTES = 30


def clean_stale_locks():
    """清理超过30分钟的孤儿 .processing 锁文件"""
    cutoff = datetime.now() - timedelta(minutes=STALE_TIMEOUT_MINUTES)
    for lock in PROCESSED_DIR.glob("*.processing"):
        mtime = datetime.fromtimestamp(lock.stat().st_mtime)
        if mtime < cutoff:
            lock.unlink(missing_ok=True)
            print(f"[clean] 清理孤儿锁: {lock.name}")
    # Also clean locks in inbox
    for lock in INBOX_DIR.glob("*.processing"):
        mtime = datetime.fromtimestamp(lock.stat().st_mtime)
        if mtime < cutoff:
            lock.unlink(missing_ok=True)
            print(f"[clean] 清理孤儿锁(inbox): {lock.name}")


def scan_inbox():
    """扫描 inbox，返回待处理消息列表。已移到 processed/ 并返回路径。"""
    clean_stale_locks()

    messages = []
    for f in sorted(INBOX_DIR.glob("MSG_*.md")):
        if f.name == "README.md":
            continue
        # 跳过已有锁的文件（可能正在被其他进程处理）
        lock_file = PROCESSED_DIR / f"{f.name}.processing"
        if lock_file.exists():
            mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
            age = (datetime.now() - mtime).total_seconds() / 60
            print(f"[skip] {f.name} — 锁文件存在 ({age:.0f}min)，跳过")
            continue

        # 创建锁
        lock_file.write_text(str(datetime.now().isoformat()))

        # 原子性移动到 processed/
        dest = PROCESSED_DIR / f.name
        f.rename(dest)

        messages.append(
            {
                "name": f.name,
                "path": str(dest),
                "preview": dest.read_text(encoding="utf-8")[:200],
            }
        )

    return messages


def mark_done(filename):
    """标记消息处理完成"""
    lock = PROCESSED_DIR / f"{filename}.processing"
    lock.unlink(missing_ok=True)
    done = PROCESSED_DIR / f"{filename}.done"
    done.write_text(datetime.now().isoformat())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--mark-done":
        if len(sys.argv) < 3:
            print("Usage: inbox_scanner.py --mark-done <filename>")
            sys.exit(1)
        mark_done(sys.argv[2])
        return

    messages = scan_inbox()
    if not messages:
        print("[]")
        return

    # 输出 JSON 供 Claude CLI 消费
    print(json.dumps(messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
