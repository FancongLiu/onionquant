#!/usr/bin/env python3
"""checkpoint.py — 中断上下文持久化工具

Save/restore execution context across cron sessions.
Usage:
    python scripts/checkpoint.py save    # Save current context
    python scripts/checkpoint.py restore # Restore and print pending actions
    python scripts/checkpoint.py push "<action>"  # Add to pending_actions
    python scripts/checkpoint.py pop     # Remove top pending action
    python scripts/checkpoint.py show    # Print current state
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent.parent / "company" / "departments" / "execution" / "context_state.json"


def load():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return _default_state()


def _default_state():
    return {
        "version": "1.0",
        "protocol": "Context Persistence Protocol",
        "description": "Cron sessions read this file first to restore context, then update it after work.",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "pending_actions": [],
        "key_context": {},
        "session_stack": [],
    }


def save(state):
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[checkpoint] Saved. {len(state['pending_actions'])} pending actions.")


def cmd_save(args):
    state = load()
    if args.context:
        state["key_context"].update(args.context)
    if args.action:
        state["pending_actions"].insert(0, args.action)
    save(state)


def cmd_restore(args):
    state = load()
    print("## Restored Context")
    print(f"Last updated: {state['last_updated']}")
    if state["key_context"]:
        print("\n### Key Context")
        for k, v in state["key_context"].items():
            print(f"- {k}: {v}")
    if state["pending_actions"]:
        print(f"\n### Pending Actions ({len(state['pending_actions'])})")
        for i, action in enumerate(state["pending_actions"]):
            prefix = "🔴" if "P0" in action else "🟡" if "P1" in action else "🟢"
            print(f"  {prefix} {action}")
    else:
        print("\n(No pending actions)")


def cmd_push(args):
    state = load()
    state["pending_actions"].insert(0, args.action)
    save(state)


def cmd_pop(args):
    state = load()
    if state["pending_actions"]:
        removed = state["pending_actions"].pop(0)
        print(f"[checkpoint] Popped: {removed}")
    save(state)


def cmd_show(args):
    state = load()
    print(json.dumps(state, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Context Checkpoint Tool")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("show", help="Print current state")

    p_save = sub.add_parser("save", help="Save context snapshot")
    p_save.add_argument("--context", nargs="*", help="key=value pairs to update key_context")
    p_save.add_argument("--action", help="Action to add to pending_actions")

    sub.add_parser("restore", help="Restore and print pending actions")

    p_push = sub.add_parser("push", help="Add action to pending_actions")
    p_push.add_argument("action", help="Action description")

    sub.add_parser("pop", help="Remove top pending action")

    args = parser.parse_args()
    if args.cmd == "save":
        # Parse --context key=value pairs
        if args.context:
            ctx = {}
            for kv in args.context:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    ctx[k] = v
            args.context = ctx
        cmd_save(args)
    elif args.cmd == "restore":
        cmd_restore(args)
    elif args.cmd == "push":
        cmd_push(args)
    elif args.cmd == "pop":
        cmd_pop(args)
    elif args.cmd == "show":
        cmd_show(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
