#!/usr/bin/env python3
"""
TASK_TRACKER.md → Hermes Kanban auto-sync script.

Reads OnionQuant's TASK_TRACKER.md markdown file, parses task tables,
and syncs active tasks to the Hermes Kanban board.

Usage:
    python3 sync_task_tracker.py [--dry-run] [--board onionquant]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path("/mnt/e/2026_AgentStudy/Python_code")
TASK_TRACKER = PROJECT_ROOT / "TASK_TRACKER.md"

# Status mapping: TASK_TRACKER → kanban
STATUS_MAP = {
    "✅": "done",
    "🔵": "running",
    "🟢": "ready",
    "🆕": "ready",
    "🟡": "blocked",
    "🔴": "blocked",
    "⏳": "blocked",
    "⏸️": "blocked",
}

# Priority mapping: P0→1, P1→2, P2→3
PRIORITY_MAP = {"P0": 1, "P1": 2, "P2": 3}


def run_kanban(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run hermes kanban command."""
    cmd = ["hermes", "kanban"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=check)


def get_existing_tasks() -> Dict[str, dict]:
    """Fetch all kanban tasks, return {task_id_prefix → task_dict}.

    Matches by task ID prefix (e.g., 'T945' from 'T945: Alpaca WebSocket...').
    """
    try:
        result = subprocess.run(
            ["hermes", "kanban", "ls", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        tasks = json.loads(result.stdout)
        indexed = {}
        for t in tasks:
            title = t["title"]
            # Extract task ID from title prefix (e.g., 'T945:', 'W001:', etc.)
            match = re.match(r"(T\d+|W\d+|C\d+|B\d+)", title)
            key = match.group(1) if match else title
            # If duplicate key, keep the first (existing) one
            if key not in indexed:
                indexed[key] = t
        return indexed
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def parse_task_tracker(path: Path) -> List[dict]:
    """Parse TASK_TRACKER.md — only extract tasks from active Sprint sections.

    Active sprints are marked with 🟢 in the section header. Tasks within
    ✅ 已完成 sections are skipped entirely regardless of row content.
    """
    text = path.read_text(encoding="utf-8")
    tasks = []

    # Split into sections by ## headers
    sections = re.split(r"\n(?=## )", text)

    # Row pattern for table rows with priority+status columns
    # Matches: | ID | description | department | P? | status_with_emoji |
    row_pattern = re.compile(
        r"^\|\s*(T\d+|W\d+|C\d+|B\d+)\s*\|"
        r"\s*(.+?)\s*\|"
        r"\s*(.+?)\s*\|"
        r"\s*(P\d+|P0|P1|P2)?\s*\|"
        r"\s*(.+?)\s*\|",
        re.MULTILINE,
    )

    # Also match simpler table format: | ID | description | department | status |
    simple_row_pattern = re.compile(
        r"^\|\s*(T\d+|W\d+|C\d+|B\d+)\s*\|"
        r"\s*(.+?)\s*\|"
        r"\s*(.+?)\s*\|"
        r"\s*(.+?)\s*\|",
        re.MULTILINE,
    )

    active_emojis = {"🟢", "🆕", "🔵", "🟡", "🔴", "⏳", "⏸️"}

    for section in sections:
        # Skip completed/done/archived sections
        header = section.split("\n")[0] if section else ""
        # ONLY sync from 🟢 Sprint sections (active work)
        if "🟢" not in header:
            continue

        # Try 5-column format first (has priority)
        for match in row_pattern.finditer(section):
            task_id = match.group(1).strip()
            desc = match.group(2).strip()
            dept = match.group(3).strip()
            priority = match.group(4).strip() if match.group(4) else "P2"
            status_raw = match.group(5).strip()

            # Skip completed tasks
            if "✅" in status_raw and not any(
                e in status_raw for e in active_emojis - {"✅"}
            ):
                continue

            # Determine status
            status = "ready"
            for emoji, kanban_status in STATUS_MAP.items():
                if emoji in status_raw:
                    status = kanban_status
                    break

            if status == "done":
                continue

            tasks.append(
                {
                    "id": task_id,
                    "title": f"{task_id}: {desc[:80]}",
                    "body": f"Department: {dept}\nPriority: {priority}\nSource: TASK_TRACKER.md",
                    "department": dept,
                    "priority_str": priority,
                    "priority": PRIORITY_MAP.get(priority, 3),
                    "status": status,
                }
            )

        # Also try 4-column format (no priority column)
        for match in simple_row_pattern.finditer(section):
            task_id = match.group(1).strip()
            desc = match.group(2).strip()
            dept = match.group(3).strip()
            status_raw = match.group(4).strip()

            # Only process if this looks like a status cell (has an emoji)
            if not any(e in status_raw for e in active_emojis):
                continue

            status = "ready"
            for emoji, kanban_status in STATUS_MAP.items():
                if emoji in status_raw:
                    status = kanban_status
                    break

            if status == "done":
                continue

            # Avoid duplicates from 5-column match
            if any(t["id"] == task_id for t in tasks):
                continue

            tasks.append(
                {
                    "id": task_id,
                    "title": f"{task_id}: {desc[:80]}",
                    "body": f"Department: {dept}\nSource: TASK_TRACKER.md",
                    "department": dept,
                    "priority_str": "P2",
                    "priority": 3,
                    "status": status,
                }
            )

    return tasks


def sync_tasks(
    tasks: List[dict],
    existing: Dict[str, dict],
    dry_run: bool = False,
) -> Tuple[int, int, int]:
    """Sync tasks to Kanban. Returns (created, updated, skipped)."""
    created = updated = skipped = 0

    for task in tasks:
        title = task["title"]
        task_key = task["id"]

        if task_key in existing:
            existing_task = existing[task_key]
            kanban_id = existing_task["id"]
            current_status = existing_task["status"]

            # Update status if changed
            if current_status != task["status"] and task["status"] in (
                "done",
                "blocked",
                "ready",
                "running",
            ):
                if not dry_run:
                    if task["status"] == "done":
                        run_kanban("complete", kanban_id, check=False)
                    elif task["status"] == "blocked":
                        run_kanban("block", kanban_id, check=False)
                    # ready/running status updates handled by kanban lifecycle
                print(
                    f"  UPDATE {kanban_id}: {current_status} → {task['status']} ({task_key})"
                )
                updated += 1
            else:
                skipped += 1
        else:
            # Create new task
            if not dry_run:
                try:
                    result = subprocess.run(
                        [
                            "hermes",
                            "kanban",
                            "create",
                            task["title"],
                            "--body",
                            task["body"],
                            "--priority",
                            str(task["priority"]),
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        check=True,
                    )
                    # Extract kanban ID from output
                    out = result.stdout
                    match = re.search(r"t_\w{8}", out)
                    kanban_id = match.group(0) if match else "unknown"
                except subprocess.CalledProcessError as e:
                    print(f"  ERROR creating {task_key}: {e.stderr}")
                    continue

                # Set correct status
                if task["status"] == "blocked":
                    run_kanban("block", kanban_id, check=False)
                elif task["status"] == "done":
                    run_kanban("complete", kanban_id, check=False)

            print(
                f"  CREATE {task_key} → kanban [{task['status']}] (P{task['priority']})"
            )
            created += 1

    return created, updated, skipped


def main():
    parser = argparse.ArgumentParser(description="Sync TASK_TRACKER.md → Hermes Kanban")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    args = parser.parse_args()

    if not TASK_TRACKER.exists():
        print(f"ERROR: {TASK_TRACKER} not found", file=sys.stderr)
        sys.exit(1)

    print(f"📋 Parsing {TASK_TRACKER}...")
    tasks = parse_task_tracker(TASK_TRACKER)
    print(f"   Found {len(tasks)} active tasks")

    print("🔍 Fetching existing kanban tasks...")
    existing = get_existing_tasks()
    print(f"   Found {len(existing)} existing tasks")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Syncing...")
    created, updated, skipped = sync_tasks(tasks, existing, dry_run=args.dry_run)

    print(f"\n✅ Done: {created} created, {updated} updated, {skipped} unchanged")


if __name__ == "__main__":
    main()
