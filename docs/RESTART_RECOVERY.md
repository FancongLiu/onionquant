# 🔄 重启恢复文档

> 此文件用于 PC 重启后快速恢复 OnionQuant 全部服务。
> 用户在 Claude Code 会话中说"我重启了"时，Agent 读取此文件执行恢复流程。

## 重启前状态快照

| 服务 | 说明 |
|------|------|
| Dashboard Server | `python company/server.py` → port 8765 |
| Tunnel | `python scripts/tunnel_sync.py` 管理 cloudflared |
| 定时任务 | `python scripts/background_scheduler.py` |
| 微信出站 | background_scheduler 每5分钟调 wechat_sync_push.py |
| VS Code | 主会话入口，Claude Code 在此运行 |

## Agent 恢复流程（用户说"我重启了"后执行）

### Step 1: 验证服务状态
```
curl localhost:8765/api/status → 应返回 401 (OK)
```

### Step 2: 如果 server 没跑，启动它
```
start "OnionQuant-Server" /MIN .venv\Scripts\python company\server.py
```

### Step 3: 如果 tunnel 没跑，启动 tunnel_sync
```
start "Tunnel-Sync" /MIN .venv\Scripts\python scripts\tunnel_sync.py
```

### Step 4: 如果 background_scheduler 没跑，启动它
```
start "BgScheduler" /MIN .venv\Scripts\python scripts\background_scheduler.py
```

### Step 5: 验证完整链路
```
1. curl localhost:8765/api/status → 401 ✓
2. cloudflared 进程存在 ✓
3. 微信发测试消息 ✓
4. 告知用户当前 tunnel URL ✓
```

## 诊断命令

| 检查项 | 命令 |
|--------|------|
| 端口占用 | `netstat -ano \| findstr :8765` |
| Python 进程 | `tasklist \| findstr python` |
| cloudflared | `tasklist \| findstr cloudflared` |
| tunnel URL | `cat company\.last_tunnel_url` 或查看 cf 日志 |

## 用户偏好

- 消息必须有北京时间戳 `[YYYY-MM-DD HH:MM:SS 北京时间]`
- 链接必须用 tunnel URL，禁用 localhost
- 详细报告 → dashboard，精简要点 → 微信
