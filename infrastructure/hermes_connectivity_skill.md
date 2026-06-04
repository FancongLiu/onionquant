---
name: connectivity-guardian
description: 连通守护部 — 微信触发全链路巡检·状态查询·断联修复
---

# 连通守护部 (Connectivity Guardian)

## 触发条件
- 董事长微信发送: "连通状态" / "检查连接" / "系统在吗" / "能动吗"
- 董事长微信发送: "修复XX" (指定通道)
- Claude CLI outbox 出现 ALERT_connectivity_*.md

## 执行流程

### 状态查询 ("连通状态")
1. 执行: `~/onionquant-venv-312/bin/python /mnt/e/2026_AgentStudy/Python_code/scripts/connectivity_guardian.py`
2. 将结果整理成简短中文回复:

```
🔗 连通守护报告 (18:20 CST)
🟢 tmux会话: alive
🟢 微信网关: OK
🟢 前端面板: OK
🟢 消息流: 通畅
🟢 文件桥接: OK
🟢 AI接口: 可达
🟢 隧道: 1个运行中

全通道畅通 ✅
```

3. 有🔴则标注: "⚠️ X通道断裂,正在尝试修复..."

### 自动修复
- Hermes 死 → `pkill hermes` → `nohup hermes gateway run --replace`
- tmux 死 → `bash /mnt/e/2026_AgentStudy/Python_code/infrastructure/restore_onionquant.sh`
- 孤儿锁 → 删除超过30分钟的 .processing 文件

### 告警推送
- 关键通道(🔴)断裂且无法自愈 → 推送微信消息给董事长
- 格式: "🚨 OnionQuant 断联: [通道名] — [原因]。已尝试修复但失败。请检查。"

## 铁律
- 状态查询 3 秒内回复，不等慢检查
- 修复不重试超过 3 次
- 不可修复的告警只说事实，不吓唬
