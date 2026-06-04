# OnionQuant WSL 24/7 自主巡航 — 部署记录

**部署时间**: 2026-05-18 02:50 CST
**状态**: ✅ 运行中

## 架构

```
Windows 11
  ├── VS Code Claude Code 插件 (可关闭)
  │
  └── WSL Ubuntu 26.04
        ├── tmux session "onionquant" (Claude CLI v2.1.143 常驻)
        │     └── deepseek-v4-pro[1m] · 项目: /mnt/e/2026_AgentStudy/Python_code
        ├── Python 3.12.13 venv: ~/onionquant-venv-312/
        └── cron: */5 * * * * bash ~/wsl_cron_wakeup.sh
              └── tmux send-keys → Claude CLI 被唤醒
```

## 关键文件

| 文件 | 位置 | 用途 |
|------|------|------|
| BOOTSTRAP_PROMPT.md | infrastructure/ | 启动提示词+上下文溢出策略 |
| restore_onionquant.sh | infrastructure/ | WSL重启后恢复脚本 |
| wsl_cron_wakeup.sh | ~/wsl_cron_wakeup.sh | cron每5分钟唤醒 |
| crontab | `crontab -l` | */5 * * * * bash ~/wsl_cron_wakeup.sh |
| Python venv | ~/onionquant-venv-312/ | Python 3.12.13 + 全部依赖 |

## 运维命令

```bash
# 进入观察
tmux attach -t onionquant

# 退出观察
Ctrl+B D

# 查看状态
tmux capture-pane -t onionquant -p -S - | tail -30

# 检查存活
tmux has-session -t onionquant && echo "ALIVE"

# 查看唤醒日志
cat /tmp/onionquant_wakeups.log

# 重启后恢复
bash /mnt/e/2026_AgentStudy/Python_code/infrastructure/restore_onionquant.sh

# 手动唤醒
bash ~/wsl_cron_wakeup.sh
```

## 上下文管理

- Claude Code 自动压缩（到上限触发）
- 每轮任务后更新 TASK_TRACKER.md + outbox SUMMARY
- 压缩后靠 CLAUDE.md + memory 文件恢复
- 动态内容放 prompt 末尾，稳定前缀享受全局缓存
