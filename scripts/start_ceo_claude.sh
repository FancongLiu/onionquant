#!/bin/bash
# Start 24/7 OnionQuant Backend in WSL tmux
# Pane 0: background_scheduler (10 tasks incl. self-evolve every 6h)
# Pane 1: Claude Code CLI (manual use)

PROJECT="/mnt/e/2026_AgentStudy/Python_code"
SESSION="ceo-24x7"
PYTHON="$PROJECT/.venv-linux/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$PROJECT/.venv/Scripts/python.exe"
fi

tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1
cd "$PROJECT"
rm -f company/.process_now

tmux new-session -d -s "$SESSION" \
  "echo '=== Scheduler (10 tasks, self-evolve every 6h) ===';
   $PYTHON scripts/background_scheduler.py;
   echo 'STOPPED - shell alive';
   exec bash"

tmux split-window -h -t "$SESSION" \
  "echo '=== Claude Code CLI ===';
   echo 'claude -p prompt  # one-shot';
   exec bash"

sleep 3
tmux has-session -t "$SESSION" 2>/dev/null && echo "OK: $SESSION" || echo "FAIL"
