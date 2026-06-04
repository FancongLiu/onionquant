#!/bin/bash
# wsl_cron_wakeup.sh — cron 唤醒 Claude CLI 在 tmux 中的会话
# 被 crontab 每 5 分钟调用一次
# 放在 WSL 原生文件系统: ~/wsl_cron_wakeup.sh

SESSION="onionquant"

# 检查 tmux 会话是否存活
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    RESTORE="/mnt/e/2026_AgentStudy/Python_code/infrastructure/restore_onionquant.sh"
    if [ -f "$RESTORE" ]; then
        echo "$(date -Iseconds): dead session, running restore" >> /tmp/onionquant_wakeups.log
        bash "$RESTORE" >> /tmp/onionquant_restore.log 2>&1
    fi
    exit 0
fi

# 直接发送提示词（不 Ctrl+C，避免中断正在执行的 bash 命令）
# Claude CLI 会在当前任务完成后读取 stdin 中的这条消息
tmux send-keys -t "$SESSION" -l "继续执行自主巡航：扫描 inbox、执行任务、更新状态。不要停。"
sleep 0.2
tmux send-keys -t "$SESSION" Enter

echo "$(date -Iseconds): wake-up sent" >> /tmp/onionquant_wakeups.log
