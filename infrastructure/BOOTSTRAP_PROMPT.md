# OnionQuant 24/7 自主巡航 — WSL 启动提示词

你正在 WSL Ubuntu 的 tmux 会话中运行 Claude Code CLI。本文件包含完整的启动指令。**粘贴到对话框发送即可。**

---

## Step 1：注册定时任务（一次性）

用 CronCreate 注册以下 5 个 durable 任务。**同一会话内注册，所有触发注入本会话，共享 session ID + 缓存。**

```
#1 inbox_scan
cron: */10 * * * *
durable: true
prompt: 扫描 company/chairman_inbox/，有新文件则读取、执行、移入 processed/。

#2 iteration_engine
cron: 17,47 * * * *
durable: true
prompt: 扫描项目状态，生成量化改进任务并写入 TASK_TRACKER.md。关注 DXYZ/存储/半导体/AI芯片/航天/光模块。如有更优标的更新 PIPELINE_TICKERS 行。

#3 redteam_review
cron: 3,33 * * * *
durable: true
prompt: 审查代码质量、安全风险、手搓代码检测。发现问题写 company/chairman_outbox/ALERT_redteam_*.md，无问题则无需操作。

#4 hourly_sentiment
cron: 9 22,23,0,1,2,3 * * 1-5
durable: true
prompt: 执行: cd /mnt/e/2026_AgentStudy/Python_code && ~/onionquant-venv-312/bin/python scripts/sentiment_hourly_push.py。标的: DXYZ, INTC, MU, WDC。报告写入 company/chairman_outbox/SENTINEL_hourly_*.md。

#5 daily_pipeline
cron: 7 6 * * 1-5
durable: true
prompt: 执行: cd /mnt/e/2026_AgentStudy/Python_code && ~/onionquant-venv-312/bin/python scripts/run_pipeline.py --mode full。标的列表从 TASK_TRACKER.md PIPELINE_TICKERS 行读取。报告写入 company/reports/pipeline_*.md。

#6 connectivity_guardian
cron: 55 * * * *
durable: true
prompt: 执行: cd /mnt/e/2026_AgentStudy/Python_code && ~/onionquant-venv-312/bin/python scripts/connectivity_guardian.py。输出读完后：全绿则无事；有🔴则执行自动修复（孤儿锁清理·Hermes重启·tmux恢复）。修复后重新检测。仍断裂则:1)写ALERT_connectivity到outbox 2)如Hermes通则推送微信告警给董事长。不可自动修复的(DeepSeek API/Cloudflared/跨文件系统)写outbox说明原因和影响。
```

## 时间线（每小时内错开，绝不重叠）

```
:00 ─── (空)
:03 ─── redteam_review
:09 ─── hourly_sentiment (仅交易时段)
:10 ─── inbox_scan
:17 ─── iteration_engine
:20 ─── inbox_scan
:30 ─── inbox_scan
:33 ─── redteam_review
:40 ─── inbox_scan
:47 ─── iteration_engine
:50 ─── inbox_scan
:55 ─── connectivity_guardian (7通道全链路巡检)
```

- 轻量任务（inbox）之间 ≥10 分钟
- 重型任务（iteration/redteam）之间 ≥14 分钟
- 同一时刻只有一条 cron 触发，串行排队，不会并发

## 环境

| 项 | 值 |
|----|-----|
| 项目根目录 | `/mnt/e/2026_AgentStudy/Python_code/` |
| Python venv | `~/onionquant-venv-312/` |
| 激活 | `source ~/onionquant-venv-312/bin/activate` |
| Python 版本 | 3.12 |
| 前端 | Windows localhost:8765（不在 WSL 跑）/ 外网 tunnel URL 见 context_state.json |

## 🔴 运行铁律

### 安全
- 不确定的事 → 写 `company/chairman_outbox/ASK_*.md`，**继续执行下一个任务，不停下等**
- 读到密钥/密码/Token → 只报告路径，不存储，写 outbox 报警
- 删文件前过 CLAUDE.md 安全协议 5 关检查
- 绝不 `git push --force` 到 main
- 禁止凭记忆手搓方案 → 先 GitHub + Web 搜索再答

### 执行力
- **不要停下来等回复** — 你是无人值守
- 需要董事长决策 → 写 outbox → 继续下一个任务
- 最多重试 3 次 → 失败写 `company/blocked/` → 继续下一个任务
- 每轮做完 → 更新 TASK_TRACKER.md 状态

### 上下文管理
- 每 10 轮自检：如果现在上下文被压缩，丢掉了什么？把丢不掉的东西写到文件
- 不依赖对话历史做长期记忆 → 用文件（TASK_TRACKER.md / memory / outbox）

## Step 2：手动启动首轮

注册完 cron 后，立即执行：
1. 扫描 `company/chairman_inbox/`，处理待办
2. 读取 TASK_TRACKER.md
3. 开始执行最高优先级任务

此后 cron 会定时注入消息，你自然形成巡航节奏。永远工作。
