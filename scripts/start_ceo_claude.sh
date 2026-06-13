#!/bin/bash
# Start 24/7 OnionQuant Backend in WSL tmux (WSL-native: better I/O performance)
# Pane 0: continuous_evolve.py (linear loop, finish one -> next, no timers)
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
rm -f company/.process_now company/.stop_evolve

tmux new-session -d -s "$SESSION" \
  "echo '=== Continuous Evolution Daemon (WSL-native Linux) ===';
   echo 'Mode: linear loop, no timers, no interrupts';
   echo 'Python: $PYTHON';
   echo '';
   $PYTHON scripts/continuous_evolve.py;
   echo 'STOPPED - keeping shell alive';
   exec bash"

tmux split-window -h -t "$SESSION" \
  "echo '=== Claude Code CLI (Manual) ===';
   echo 'claude -p prompt  # one-shot';
   exec bash"

sleep 3
tmux has-session -t "$SESSION" 2>/dev/null && echo "OK: $SESSION" || echo "FAIL"
