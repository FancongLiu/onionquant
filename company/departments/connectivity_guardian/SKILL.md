# 连通守护部 (Connectivity Guardian)

**代号**: CG · **优先级**: P0 基础设施 · **频率**: 每小时 (:55)

## 使命

确保董事长与 OnionQuant 之间的 7 条通信通道**永久畅通**。
发现断裂 → 自动修复 → 无法修复则告警 → 绝不停下等。

## 守护的 7 条通道

| # | 通道 | 检测方法 | 断裂后果 |
|---|------|---------|---------|
| 1 | WSL tmux 会话 | `tmux has-session -t onionquant` + Claude 进程存活 | Claude CLI 停止巡航 |
| 2 | Hermes 微信网关 | `curl localhost:8645/health` | 微信收不到回复 |
| 3 | Dashboard 前端 | `curl localhost:8765/api/status` (本地; 外网用户用 tunnel URL) | 网页打不开 |
| 4 | Inbox→Outbox 消息流 | 检查 .processing 孤儿锁 + 待处理消息年龄 | 董事长指令石沉大海 |
| 5 | WSL↔Windows 文件桥 | 读写测试 /mnt/e/ 跨文件系统 | 文件交换中断 |
| 6 | DeepSeek API | HEAD 请求 api.deepseek.com | Claude/Hermes 失智 |
| 7 | Cloudflared 隧道 | `pgrep cloudflared` | 外网无法访问 |

## 执行流程

### 定时巡检 (:55 每小时)
```
1. 运行 ~/onionquant-venv-312/bin/python scripts/connectivity_guardian.py
2. 查看输出 — 全部 🟢 则无事发生
3. 有 🔴 → 执行自动修复 → 再检
4. 修复失败 → 写 company/chairman_outbox/ALERT_connectivity_*.md
5. 特别严重 (tmux死/Hermes死) → 同时微信通知（如果微信还通的话）
```

### 自动修复能力
| 故障 | 修复动作 |
|------|---------|
| 孤儿 .processing 锁 | 清理超过30分钟的锁文件 |
| Hermes 进程死亡 | `pkill` → 清 lock → `nohup hermes gateway run` |
| tmux 会话死亡 | 执行 `infrastructure/restore_onionquant.sh` |
| Dashboard 死亡 | `kill` 旧进程 → 重新 `uvicorn` |

### 不可自动修复 → 告警
- DeepSeek API 全局宕机（等恢复）
- Cloudflared 隧道全部断裂（需手动重连）
- 跨文件系统 /mnt/e/ 不可访问（Windows 侧问题）

## 集成点

- **Cron**: 系统 crontab `55 * * * *` 或 Claude Code CronCreate 每小时触发
- **Hermes 技能**: 董事长微信发 "连通状态" → 立即巡检并回复
- **Inbox 桥接**: 检测到消息流断裂 → 优先修复 inbox/outbox 通道

## 铁律

1. 巡检绝对不能影响正在运行的 Claude CLI（只读检查，修复用独立进程）
2. 告警级别: 🔴 = 董事长可能已断联，必须立即修复
3. 每次巡检结果记录到 memory，供下次对比
4. 修复失败不重试超过 3 次 → 写告警等董事长
