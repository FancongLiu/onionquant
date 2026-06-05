# OnionQuant — Multi-Agent Quantitative Analysis System

A **layered multi-agent AI system** that organizes LLM-powered agents into a virtual company hierarchy for quantitative market analysis. 15+ specialized agents collaborate through LangGraph state graphs, with cost-aware model routing and persistent memory across sessions.

## Architecture

```
Chairman (User)
  └─ CEO Agent ── Task decomposition + priority scheduling
       ├─ Strategy Research Dept  ── Factor scanning, IC analysis
       ├─ Risk Management Dept    ── VaR/CVaR, stress testing, regime detection
       ├─ Sentiment Intel Dept    ── Reddit/Twitter/News multi-source NLP
       ├─ Data Engineering Dept   ── ETL pipeline, data quality monitoring
       ├─ Reporting Dept          ── Automated report generation + visualization
       └─ IT/Tech Dept            ── Cloudflare Tunnel, watchdog, health checks
```

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| **Dual-tier LLM routing** | Quick model (routine scanning) vs Deep model (strategic decisions) — ~80% cost reduction on high-volume tasks |
| **Agent fork with cache inheritance** | Sub-agents inherit parent session's prompt prefix — 92%+ cache hit rate, parallel overhead only 1.1-1.5x tokens |
| **Persistent memory with strength decay** | TF-IDF + cosine similarity retrieval, SHA-256 dedup, weekly decay — agents remember context across sessions without vector DB dependency |
| **Filesystem-based task locking** | `mkdir` atomic Test-and-Set for cron job coordination — zero external dependencies, 15-min TTL deadlock prevention |
| **Context persistence protocol** | ISR-like interrupt/save/resume — cron sessions recover execution state from JSON bridge file |

## Technical Stack

**Agent Framework**: LangGraph (StateGraph), LangChain, custom manifest schema for typed agent contracts

**Quantitative**: statsmodels (Markov Switching), sklearn (Ridge/RF/XGB), empyrical (Sharpe/MaxDD), Riskfolio-Lib, Alphalens

**Infrastructure**: FastAPI + SSE EventSource, Neo4j knowledge graph (303 nodes, 850 edges), PostgreSQL/TimescaleDB, Cloudflare Tunnel

**LLM**: DeepSeek V4-Pro, SiliconFlow GLM — cost-aware routing with 120:1 cache pricing ratio

**DevOps**: pre-commit hooks (secret scanning), ruff linter, pytest, background scheduler for Python cron jobs

## Project Structure

```
onionquant/          Main application package
├── agents/          Agent manifest schema + type system
├── api/             FastAPI route handlers (quant, risk, dashboard, sentiment, wechat)
├── departments/     Department agent implementations (15+ departments)
├── tools/           External data scanners (Reddit, Twitter, News, Google Trends)
├── infrastructure/  API proxy, knowledge graph, memory store, model tier router
├── server.py        FastAPI server with SSE push + watchdog
└── wechat_bot.py    Enterprise WeChat bot integration (AES-256-CBC)

quant_framework/     Quantitative computation engine
├── strategies/      Factor engines, regime detection (Markov Switching), portfolio optimizer
├── risk/            Risk threshold engine with deployment decision matrix
├── backtest/        Event-driven backtesting with PnL analytics + visualization
├── data/            Multi-source fetchers (Alpha Vantage, Reddit, News sentiment)
└── knowledge_graph/ NetworkX graph builder (ticker → factor → industry → catalyst)

company/             Runtime data only (gitignored)
├── chairman_inbox/  User → Agent message queue
├── chairman_outbox/ Agent → User SSE push queue
└── task_claims/     Distributed mutex locks for cron coordination

scripts/             CLI entry points + cron tasks
tests/               Test suite
docs/                Project documentation
```

## Quick Start

```bash
# 1. Clone and set up environment
git clone https://github.com/FancongLiu/Home-work.git
cd Home-work
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start the dashboard
python onionquant/server.py
# → http://localhost:8765

# 4. Run quant pipeline
python scripts/decision_engine_v2.py
```

## License

MIT License — see [LICENSE](LICENSE) file for details.
