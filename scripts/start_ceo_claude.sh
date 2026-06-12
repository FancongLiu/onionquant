#!/bin/bash
# Start 24/7 Claude Code Inbox Relay in WSL tmux
# Left pane:  claude_inbox_relay.sh (event-driven, detects trigger → claude -p)
# Right pane: manual Claude Code shell

PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
SESSION_NAME="ceo-24x7"

tmux kill-session -t "$SESSION_NAME" 2>/dev/null
sleep 1

cd "$PROJECT_DIR"
rm -f company/.process_now

# Left pane: Claude Code inbox relay
tmux new-session -d -s "$SESSION_NAME" \
  "echo '=== Claude Code Inbox Relay (24/7) ===';
   echo 'Architecture: trigger file → claude -p → outbox';
   echo 'Context: full CLAUDE.md + memory + WebSearch + LangGraph';
   bash scripts/claude_inbox_relay.sh;
   echo 'RELAY STOPPED - keeping shell';
   exec bash"

# Right pane: Manual Claude Code shell
tmux split-window -h -t "$SESSION_NAME" \
  "echo '=============================================';
   echo '  Claude Code CLI - Manual';
   echo '  Left: inbox relay (auto)';
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
