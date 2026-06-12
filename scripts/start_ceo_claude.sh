#!/bin/bash
# Start 24/7 OnionQuant backend in WSL tmux
# Left: claude_inbox_processor.py (event-driven, waits for trigger file)
# Right: Claude Code CLI shell (manual or auto-invoked by processor)

PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
SESSION_NAME="ceo-24x7"
PYTHON="$PROJECT_DIR/.venv-linux/bin/python3"

tmux kill-session -t "$SESSION_NAME" 2>/dev/null
sleep 1

cd "$PROJECT_DIR"
rm -f company/.process_now company/.watcher_state.json

# Left pane: Claude inbox processor (event-driven trigger watcher)
tmux new-session -d -s "$SESSION_NAME" \
  "echo '=== Claude Inbox Processor ===';
   echo 'Engine: Claude Code CLI (full CLAUDE.md + memory + tools)';
   echo 'Mode: event-driven (trigger file, not polling)';
   echo '';
   $PYTHON scripts/claude_inbox_processor.py;
   echo '';
   echo '--- PROCESSOR STOPPED ---';
   exec bash"

# Right pane: Claude Code CLI for manual tasks + research iteration
tmux split-window -h -t "$SESSION_NAME" \
  "echo '=============================================';
   echo '  Claude Code CLI';
   echo '  Left: inbox processor (auto)';
   echo '  claude -p \\\"prompt\\\"  # one-shot';
   echo '=============================================';
   exec bash"

sleep 3
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "OK: $SESSION_NAME running"
else
    echo "FAIL"
    exit 1
fi
