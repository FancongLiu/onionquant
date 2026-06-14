#!/usr/bin/env python3
"""Sync TASK_TRACKER.md status to Hermes Kanban board.

Parses TASK_TRACKER.md, extracts task counts and pending items,
then updates the Hermes Kanban via CLI. Run from WSL.

Usage:
    python3 scripts/sync_kanban.py [--dry-run]
"""

import subprocess
from scripts._subprocess_utils import run, Popen
import sys
import re
from pathlib import Path

TASK_TRACKER = Path(__file__).parent.parent / "TASK_TRACKER.md"
BOARD = "onionquant"


def run_kanban(*args):
    cmd = ["hermes", "kanban", "--board", BOARD] + list(args)
    result = run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return f"ERR: {result.stderr.strip()[:100]}"
    return result.stdout.strip()


def parse_tracker():
    text = TASK_TRACKER.read_text(encoding="utf-8")

    # Extract counts from overview table
    counts = {}
    for match in re.finditer(r"\|\s*(✅|🔵|🟢|🟡|⏳|🔴)\s*([^|]+)\|\s*(\d+)", text):
        label = match.group(2).strip()
        num = int(match.group(3))
        counts[label] = num

    # Extract sprint tasks with status
    sprints = {}
    current_sprint = None
    for line in text.splitlines():
        sprint_match = re.match(r"## 🟢 新任务.*(Sprint \d+)", line)
        if sprint_match:
            current_sprint = sprint_match.group(1)
            sprints[current_sprint] = []
            continue
        if current_sprint and line.startswith("| T"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 5:
                sprints[current_sprint].append(
                    {
                        "id": parts[0],
                        "desc": parts[1],
                        "dept": parts[2],
                        "priority": parts[3],
                        "status": parts[4] if len(parts) > 4 else "",
                    }
                )

    # Extract waiting items
    waiting = []
    in_waiting = False
    for line in text.splitlines():
        if "⏳ 等待董事长" in line or "等待董事长决策" in line:
            in_waiting = True
            continue
        if in_waiting and line.startswith("##"):
            break
        if in_waiting and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if (
                parts
                and parts[0]
                and not parts[0].startswith("---")
                and not parts[0].startswith("ID")
            ):
                waiting.append(parts)

    # Determine active tasks (🆕 or not ✅)
    active = []
    for sprint_name, tasks in sprints.items():
        for t in tasks:
            if "✅" not in t["status"] and "⏸" not in t["status"]:
                active.append(t)

    return counts, active, waiting


def status_to_kanban(status_str):
    if "✅" in status_str:
        return "done"
    if "🔵" in status_str:
        return "in_progress"
    if "🆕" in status_str:
        return "ready"
    if "⏳" in status_str or "⏸" in status_str:
        return "triage"
    return "ready"


def main():
    dry = "--dry-run" in sys.argv
    counts, active, waiting = parse_tracker()

    print("=== TASK_TRACKER.md → Kanban Sync ===")
    print(f"Board: {BOARD}")
    print(f"Completed: {counts.get('已完成', '?')}")
    print(f"Active tasks (not done): {len(active)}")
    print(f"Waiting on chairman: {len(waiting)}")
    if dry:
        print("[DRY RUN — no changes]")

    # Scan existing Kanban task titles to avoid duplicates
    existing = run_kanban("list")
    existing_titles = set()
    existing_task_map = {}  # title_prefix → kanban_id
    for line in existing.splitlines():
        cols = [c.strip() for c in line.split("│")]
        if len(cols) >= 3:
            kanban_id = cols[0].strip()
            title_part = cols[2].strip() if len(cols) > 2 else ""
            if kanban_id.startswith("t_"):
                existing_titles.add(title_part)
                existing_task_map[title_part] = kanban_id

    created = 0
    for task in active[:10]:
        tid = task["id"]
        title = f"{tid}: {task['desc']}"
        kanban_status = status_to_kanban(task["status"])

        if kanban_status == "done":
            # Complete in Kanban if exists
            for et, ek in existing_task_map.items():
                if tid in et and ek:
                    if dry:
                        print(f"  [dry] complete {tid}: {ek}")
                    else:
                        run_kanban("complete", ek)
            continue

        # Skip if similar task already in Kanban
        if title in existing_titles or any(tid in t for t in existing_titles):
            print(f"  [skip] {tid} already in Kanban")
            continue

        if dry:
            print(f"  [dry] create {tid}: {task['desc'][:60]} → {kanban_status}")
            created += 1
            continue

        priority_num = task["priority"].replace("P", "")
        result = run_kanban(
            "create",
            "--body",
            f"Dept: {task['dept']} | Priority: {task['priority']} | {task['status']}",
            "--priority",
            priority_num,
            "--idempotency-key",
            f"sprint-{tid}",
            title,
        )
        if kanban_status == "triage":
            # parse task id from result and block it
            pass
        print(f"  create {tid}: {result[:120]}")
        created += 1

    print(f"Synced: {created} new, skipped: {len(active) - created} existing/done")


if __name__ == "__main__":
    main()
