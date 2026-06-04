#!/bin/bash
# Start ONE persistent Claude session in WSL tmux for 24/7 CEO operation
# This single session accumulates cache → 99% hit rate on turn 2+
# All work goes through this session — no CronCreate, no claude -p

PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
SESSION_NAME="ceo-24x7"

cd "$PROJECT_DIR" || exit 1

# Kill any previous session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null

# Start new tmux session with Claude in interactive mode
# The CLAUDE.md instructions tell it to use ScheduleWakeup for self-pacing
tmux new-session -d -s "$SESSION_NAME" \
  "cd $PROJECT_DIR && claude --model deepseek-v4-pro --dangerously-skip-permissions 2>&1"

sleep 2

# Send the autonomous loop command to start 24/7 operation
# /loop (dynamic, no interval) + ScheduleWakeup = same session, cache accumulates
tmux send-keys -t "$SESSION_NAME" \
  "/loop Start autonomous CEO 24/7 mode. Every cycle: (1) Check company/chairman_inbox/ for pending *.md files — process each, write RESP_ to outbox, move to processed/. (2) Check TASK_TRACKER.md for pending work. (3) Do market research if >1h since last: use Agent forks for DXYZ+SpaceX, semis+NVDA+Samsung, aerospace+optical. (4) Push critical findings to WeChat via python scripts/wechat_sync_push.py. Self-pace with ScheduleWakeup. Keep cycle brief when idle. Stay in this session — cache 99% hit." \
  Enter

echo "CEO 24/7 session started: $SESSION_NAME"
tmux has-session -t "$SESSION_NAME" && echo "Status: RUNNING" || echo "Status: FAILED"
