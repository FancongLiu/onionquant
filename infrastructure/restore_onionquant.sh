#!/bin/bash
# restore_onionquant.sh — WSL 重启后恢复 24/7 自主巡航
# 用法: bash restore_onionquant.sh

SESSION="onionquant"
PROJECT_DIR="/mnt/e/2026_AgentStudy/Python_code"
VENV_PATH="$HOME/onionquant-venv-312"

echo "=== OnionQuant 24/7 恢复脚本 ==="
echo "时间: $(date)"

# 1. 检查 tmux 会话是否已存在
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "⚠️  tmux 会话 '$SESSION' 已存在"
    echo "   进入: tmux attach -t $SESSION"
    echo "   杀掉重建: tmux kill-session -t $SESSION && bash $0"
    exit 0
fi

# 2. 验证项目目录
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 项目目录不存在: $PROJECT_DIR"
    exit 1
fi

# 3. 验证 Python venv
if [ ! -f "$VENV_PATH/bin/python" ]; then
    echo "❌ Python venv 不存在: $VENV_PATH"
    echo "   重建: uv venv --python 3.12 $VENV_PATH && $VENV_PATH/bin/pip install -r $PROJECT_DIR/requirements.txt"
    exit 1
fi

# 4. 验证 claude CLI
if ! command -v claude &> /dev/null; then
    echo "❌ claude CLI 未安装"
    exit 1
fi

# 5. 验证 cron 运行
if ! pgrep cron > /dev/null; then
    echo "⚠️  cron 未运行，尝试启动..."
    sudo service cron start
fi

# 6. 启动 tmux 会话
echo "🚀 启动 tmux 会话 '$SESSION'..."
tmux new-session -d -s "$SESSION" -c "$PROJECT_DIR" bash

# 7. 启动 Claude CLI（带权限跳过 + 非交互模式）
sleep 1
tmux send-keys -t "$SESSION" "claude --dangerously-skip-permissions" Enter
echo "Claude CLI 启动中..."
sleep 8

# 8. 处理首次 Trust 提示（API key → No, Security → Yes）
tmux send-keys -t "$SESSION" "2" Enter
sleep 2
tmux send-keys -t "$SESSION" "1" Enter
sleep 5

# 9. 注入任务指令
echo "📋 注入任务指令..."
tmux send-keys -t "$SESSION" -l "你是WSL tmux里的Claude Code永续会话。你有完整权限，可自由编辑文件和运行命令。永远不停工作。立即：1)扫描inbox处理来信 2)读TASK_TRACKER.md 3)执行最高优先级任务并实际修改代码 4)完成后更新TASK_TRACKER.md 5)不确定的事写outbox 6)永不停止。Python用~/onionquant-venv-312/bin/python。开始。"
tmux send-keys -t "$SESSION" Enter

echo ""
echo "✅ 恢复完成！"
echo "   tmux 会话: $SESSION"
echo "   进入观察:  tmux attach -t $SESSION"
echo "   退出观察:  Ctrl+B D"
echo "   验证存活:  tmux capture-pane -t $SESSION -p | tail -20"
