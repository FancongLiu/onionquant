#!/usr/bin/env python3
"""
Simple watcher that auto-commits local changes in the repository.

Usage:
  python scripts/auto_commit_agent.py

Environment variables:
  AGENT_AUTO_COMMIT_AUTHOR  - optional: author name/email in format "Name <email>"
  AGENT_AUTO_COMMIT_MESSAGE - optional: commit message (default: "Auto-commit by agent")
  AGENT_AUTO_COMMIT_PUSH    - optional: if 'true' the script will push after commit
  AGENT_AUTO_COMMIT_INTERVAL- optional: polling interval seconds (default 5)

This script is intentionally simple (no external deps). Run it in background
while you edit files in VS Code to automatically commit changes.
"""

import os
import subprocess
import time
import argparse


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def has_changes(repo_root):
    r = run(["git", "status", "--porcelain"], cwd=repo_root)
    return bool(r.stdout.strip())


def do_commit(repo_root, message, author=None):
    # stage all changes
    r = run(["git", "add", "-A"], cwd=repo_root)
    if r.returncode != 0:
        print("git add failed:", r.stderr)
        return False

    commit_cmd = ["git", "commit", "-m", message]
    if author:
        commit_cmd += ["--author", author]

    r = run(commit_cmd, cwd=repo_root)
    if r.returncode != 0:
        # nothing to commit or error
        if "nothing to commit" in r.stdout + r.stderr:
            print("Nothing to commit.")
            return False
        print("git commit failed:", r.stderr)
        return False

    print("Committed:", message)
    return True


def do_push(repo_root):
    r = run(["git", "push"], cwd=repo_root)
    if r.returncode != 0:
        print("git push failed:", r.stderr)
        return False
    print("Pushed to remote")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=float(os.environ.get("AGENT_AUTO_COMMIT_INTERVAL", 5)), help="Polling interval seconds")
    parser.add_argument("--message", default=os.environ.get("AGENT_AUTO_COMMIT_MESSAGE", "Auto-commit by agent"))
    parser.add_argument("--author", default=os.environ.get("AGENT_AUTO_COMMIT_AUTHOR"))
    parser.add_argument("--push", action="store_true", help="Push after commit")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    print("Watching repo for changes:", repo_root)
    try:
        while True:
            if has_changes(repo_root):
                committed = do_commit(repo_root, args.message, args.author)
                if committed and args.push:
                    do_push(repo_root)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopping watcher")


if __name__ == '__main__':
    main()
