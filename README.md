# 刘范聪 — AI 全栈工程师

📱 **13297373078** | 📧 **liufancong2002@163.com** | 🔗 **[github.com/FancongLiu](https://github.com/FancongLiu)** | 🌐 **[onionoffice.xyz](https://onionoffice.xyz)**

---

## OnionQuant — Multi-Agent AI 研究平台

独立设计并实现的 **Multi-Agent 层级协作系统**。将 AI Agent 组织为类公司层级结构——CEO 负责任务分解，**15+ 个虚拟部门 Agent** 并行协作，覆盖从数据采集到分析报告的完整链路。

**技术栈**: Python · FastAPI · LangChain · LangGraph · DeepSeek · Cloudflare Tunnel · NetworkX · Pandas

**核心特性**:
- **Multi-Agent 协作引擎**: CEO → 部门 Agent 并行 Fork，任务优先级调度 + 死锁检测 + 超时熔断
- **Agent Fork 缓存继承**: 子任务共享父会话缓存前缀，92%+ 缓存命中率，并行开销仅 1.1-1.5x token
- **自动化数据管道**: 多源采集 → Pandas 清洗 → 统计分析 → 可视化报告，全链路自动闭环
- **知识图谱增强**: NetworkX 构建，关联标的 → 催化剂 → 供应链 → 宏观指标
- **实时双向通信**: SSE EventSource 推送 + 微信企业 API AES-256-CBC 加密
- **自愈运维**: Watchdog 30s 心跳 + Cloudflare Tunnel 双通道冗余 + 开机自启

**在线演示**: https://onionoffice.xyz （Agent 持续运行中）

---

## 项目结构

```
Python_code/
├── company/                  # 15+ 部门 Agent 系统 + Web Dashboard
│   ├── server.py             # FastAPI 主服务 (20+ REST endpoints)
│   ├── homepage.html         # 个人主页
│   ├── chairman_dashboard.html # 系统监控台
│   ├── chairman_office.html  # 董事办 (inbox/outbox)
│   ├── departments/          # 部门 Agent 工作区
│   ├── tools/                # 数据采集工具 (Reddit/Twitter/News/Heat)
│   └── routes/               # API 路由 (quant/risk/sentiment/wechat)
├── quant_framework/          # 量化引擎
│   ├── strategies/           # 因子计算 · 策略 · 状态检测
│   ├── backtest/             # 回测引擎 + 可视化
│   ├── risk/                 # 风控 (协方差/归因/压力测试)
│   ├── execution/            # 订单模拟 · 仓位管理
│   └── knowledge_graph/      # 图数据库 + Graph RAG
├── infrastructure/           # Docker · Dagster · 知识图谱
├── scripts/                  # 运维脚本 (watchdog/monitor/scheduler)
└── tests/                    # E2E + Smoke 测试
```

## 快速开始

```bash
# 启动服务
cd company && python server.py

# 市场监控
python scripts/market_monitor.py --once

# 决策引擎
python scripts/decision_engine_v2.py
```

## 导航

- [公司架构](COMPANY_STRUCTURE.md) · [研究路线](RESEARCH_ROADMAP.md) · [知识图谱](KNOWLEDGE_GRAPH.md) · [任务追踪](TASK_TRACKER.md)
