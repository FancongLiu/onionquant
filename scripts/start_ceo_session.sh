#!/bin/bash
# Start 24/7 CEO services in WSL tmux
# - inbox_watcher.py: instant ACK + calls claude -p for AI replies
# Survives terminal close (Ctrl+B, D to detach)
#
# Usage: bash scripts/start_ceo_session.sh

PROJECT_DIR="e:/2026_AgentStudy/Python_code"
SESSION_NAME="ceo-24x7"

# Kill existing session if any
tmux kill-session -t "$SESSION_NAME" 2>/dev/null
sleep 1

# Start new tmux session running the inbox watcher
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_DIR" \
  ".venv/Scripts/python scripts/inbox_watcher.py; bash"

echo "CEO 24/7 session started in tmux: $SESSION_NAME"
echo "  Attach: tmux attach -t $SESSION_NAME"
echo "  Detach: Ctrl+B then D"
echo "  Kill:  tmux kill-session -t $SESSION_NAME"

# Verify
sleep 2
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Status: RUNNING"
else
  echo "Status: FAILED TO START"
fi
