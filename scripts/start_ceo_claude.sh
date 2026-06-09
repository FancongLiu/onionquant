#!/bin/bash
# Start 24/7 OnionQuant backend in WSL tmux
# Uses WSL-native python3 (not Windows python.exe) to avoid path resolution issues.
#
# Left pane:  inbox_watcher.py (5s scan, zero AI tokens for file ops)
# Right pane: Claude Code CLI (manual claude -p "..." tasks)

PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
SESSION_NAME="ceo-24x7"

# Kill existing session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null
sleep 1

cd "$PROJECT_DIR"
rm -f company/.watcher_state.json

# Use .venv-linux python3 (has openai installed)
VENV="$PROJECT_DIR/.venv-linux/bin/python3"

tmux new-session -d -s "$SESSION_NAME" \
  "echo '=== inbox_watcher.py (Token-Optimized) ===';
   echo 'Scan: 5s (ZERO AI tokens)';
   echo 'Normal: queue (ZERO AI tokens)';
   echo 'Urgent: DeepSeek API';
   echo '';
   \$VENV scripts/inbox_watcher.py;
   echo '';
   echo '--- WATCHER STOPPED ---';
   exec bash"

# Right pane: Claude Code CLI for manual use
tmux split-window -h -t "$SESSION_NAME" \
  "echo '=============================================';
   echo '  Claude Code CLI';
   echo '  claude -p \\\"prompt\\\"  # one-shot task';
   echo '=============================================';
   exec bash"

sleep 3

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "OK: ceo-24x7 running in WSL"
else
    echo "FAIL: session did not start"
    exit 1
fi
