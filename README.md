# 🧅 OnionQuant — Multi-Agent AI Quantitative Analysis System

<div align="center">

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/FancongLiu/onionquant/actions)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

**A production-grade multi-agent AI system that organizes 15+ LLM-powered agents into a virtual company for quantitative market analysis — with cost-aware model routing, persistent cross-session memory, and real-time SSE push notifications.**

[Live Demo](https://onionoffice.xyz) · [Architecture](#architecture) · [Quick Start](#quick-start) · [Technical Decisions](#key-technical-decisions)

</div>

---

## What is this?

OnionQuant is an **AI-native quantitative research platform** that demonstrates how LLM agents can collaborate at scale. Unlike single-agent chatbots, it models a complete **virtual company hierarchy** — a CEO agent decomposes high-level research goals into department-level tasks, each handled by specialized agents with domain-specific tools and prompts.

**For AI engineers**: this project showcases agent orchestration patterns (LangGraph state graphs, Agent Fork cache inheritance, dual-tier LLM routing), persistent memory without vector databases, and a complete production deployment (FastAPI + SSE + Cloudflare Tunnel + WeChat integration).

**For quant researchers**: it provides a full factor research pipeline — multi-source data ingestion → factor computation → IC analysis → regime detection → risk threshold scoring → deployment decision matrix.

## Architecture (2026 Production Pattern)

```
┌──────────────────────────────────────────────────────────────┐
│  L4: Evolution Layer (Self-Improving)                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Observe → Analyze → Propose → Execute → Remember         │ │
│  │ Harness Engine: Default-FAIL + Fresh Evaluator + Skill   │ │
│  │ Auto-distill: 5+ tool calls → reusable SKILL.md          │ │
│  │ PROGRESS.md: agent reads/writes own state                │ │
│  └─────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  L3: State Layer (File-as-State)                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ task_queue.json · context_state.json · PROGRESS.md       │ │
│  │ test_contract.json · skills/ · LangGraph SqliteSaver     │ │
│  │ Scale path: File → Redis → Postgres/DynamoDB            │ │
│  └─────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  L2: Orchestration Layer                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Claude Code persistent session (--session-id UUID)       │ │
│  │ Simple → direct Claude  |  Complex → LangGraph 11-dept   │ │
│  │ inbox/outbox → event-driven, zero polling                │ │
│  └─────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  L1: Interface Layer                                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Web Dashboard · Mobile · WeChat · SSE real-time push     │ │
│  │ Cloudflare Tunnel · Basic Auth · AES-256-CBC             │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Department Architecture (LangGraph 11-Node Pipeline)

```
┌─────────────────────────────────────────────────────────────┐
│                     Chairman (User)                          │
│              Web Dashboard / WeChat / Phone                  │
└─────────────────────┬───────────────────────────────────────┘
                      │ POST /api/inbox
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  CEO Agent (LangGraph StateGraph)                            │
│  Task decomposition → Priority scheduling → Agent dispatch  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Dual-Tier LLM Router                       ││
│  │  Quick tier (routine scan)  vs  Deep tier (strategic)   ││
│  │  ~80% cost reduction on high-volume tasks               ││
│  └─────────────────────────────────────────────────────────┘│
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐
│Strategy│ │ Risk │ │Sentiment│ │Data │ │Report│ │IT/Tech   │
│Research│ │ Mgmt │ │ Intel  │ │ Eng  │ │ Gen  │ │Infra     │
└──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────────┘
    │         │         │         │         │          │
    ▼         ▼         ▼         ▼         ▼          ▼
 Factor    VaR/CVaR  Reddit/   ETL     Auto-    Cloudflare
 Scanning  Stress    Twitter/  Pipeline Report   Tunnel
 IC        Regime    News NLP  Quality  Vizzes   Watchdog
 Analysis  Detection           Monitor           Health Check
```

**Data Flow:**
```
Data Sources (yfinance/Reddit/News) → quant_framework/
→ Factor computation + Regime detection → Risk Threshold Engine
→ Deployment decision matrix → CEO Agent → Chairman Dashboard (SSE)
```

## Key Technical Decisions

| Decision | Rationale | Impact |
|----------|-----------|--------|
| **Agent Fork with cache inheritance** | Sub-agents inherit parent's prompt prefix (system prompt + tools + CLAUDE.md + memory) | 92%+ cache hit rate, 1.1-1.5x parallel token overhead vs 8-12x for cold-start sessions |
| **Dual-tier LLM routing** | Routine scanning on fast/cheap models, strategic reasoning on deep models | ~80% cost reduction on high-volume polling tasks |
| **Filesystem-based task locking** | `mkdir()` atomic Test-and-Set for distributed cron coordination | Zero external dependencies, 15-min TTL deadlock prevention |
| **Persistent memory without vector DB** | TF-IDF + cosine similarity + SHA-256 dedup + weekly strength decay | Cross-session context retention at zero infrastructure cost |
| **ISR-like context persistence** | Interrupt/Save/Resume protocol via JSON bridge file | Cron sessions recover 95%+ execution context without conversation history |
| **SSE over WebSocket** | Server-Sent Events for unidirectional push | Simpler than WebSocket, native `EventSource` browser support, auto-reconnect |

## Technical Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Agent Framework** | LangGraph, LangChain, Custom Manifest Schema | Agent state graphs, typed contracts, tool binding |
| **Quant Engine** | statsmodels, sklearn, empyrical, Riskfolio-Lib, Alphalens | Regime detection, factor IC, portfolio optimization |
| **Data Pipeline** | pandas, yfinance, PRAW, newspaper3k | Multi-source data ingestion + ETL |
| **Knowledge Graph** | NetworkX (303 nodes, 850+ edges) | Ticker ↔ Factor ↔ Industry ↔ Catalyst graph |
| **RAG (Semantic Search)** | BGE-M3 + ChromaDB + BM25 | Hybrid retrieval over 70+ historical research reports |
| **API Server** | FastAPI + SSE (EventSourceResponse) | REST API + real-time push notifications |
| **LLM Backend** | DeepSeek V4-Pro, SiliconFlow GLM | Cost-aware routing (120:1 cache price ratio) |
| **Infrastructure** | Cloudflare Tunnel, Watchdog (30s heartbeat), Docker, background_scheduler | 24/7 deployment with auto-recovery |
| **DevOps** | pytest, ruff, pre-commit (secret scanning), GitHub Actions | Code quality + CI |

## Quick Start

### Prerequisites
- Python 3.12+
- Git

### Installation

```bash
git clone https://github.com/FancongLiu/onionquant.git
cd onionquant
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your DeepSeek API key and WeChat credentials (optional)
```

### Start the Dashboard

```bash
python company/server.py
# → Dashboard: http://localhost:8765
# → Chairman Office: http://localhost:8765/office
```

### Run Analysis

```bash
# Market monitoring pipeline (factors + risk + regime)
python scripts/market_monitor.py --once

# Full decision engine (all tickers, all factors)
python scripts/decision_engine_v2.py

# Build knowledge graph
python -c "from quant_framework.knowledge_graph.quant_graph_builder import build_quant_knowledge_graph; build_quant_knowledge_graph()"
```

## Project Structure

```
onionquant/           Main application package (agent system + API)
├── agents/           Manifest schema, typed agent contracts
├── api/              FastAPI routes (quant, risk, dashboard, sentiment, wechat)
├── departments/      15+ specialized agent departments
├── tools/            External scanners (Reddit, Twitter, News, Trends)
├── infrastructure/   API proxy, KG, memory store, model tier router
├── server.py         FastAPI + SSE push + auth middleware
└── wechat_bot.py     Enterprise WeChat integration (AES-256-CBC)

quant_framework/      Quantitative computation engine
├── strategies/       Factor engines, regime detection (Markov Switching)
├── risk/             Risk threshold engine + deployment decision matrix
├── backtest/         Event-driven backtesting + PnL analytics
├── data/             Multi-source fetchers + ETL pipeline
└── knowledge_graph/  NetworkX graph builder

company/              Runtime data (all gitignored)
├── chairman_inbox/   User → Agent message queue
├── chairman_outbox/  Agent → User SSE push queue
└── task_claims/      Distributed mutex locks

scripts/              CLI entry points + cron tasks + watchdog
tests/                Test suite (smoke + e2e)
docs/                 Project documentation
infrastructure/       KG schema, memory store, model tier config
```

## Key Features

### 1. Multi-Agent Orchestration
- **CEO Agent** decomposes high-level goals into sub-tasks
- **15+ department agents** with domain-specific tools and prompts
- **LangGraph StateGraph** for complex agent workflows
- **Agent Fork** pattern: parallel sub-agents inherit parent cache (92%+ hit rate)

### 2. Cost-Aware Intelligence
- **Dual-tier routing**: cheap models for routine scans, deep models for strategy
- **Prompt cache optimization**: stable prefix design, dynamic content at tail
- **120:1 cache price ratio** exploited systematically (DeepSeek V4-Pro)

### 3. Persistent Memory
- **Cross-session memory** without vector database dependency
- **TF-IDF + cosine similarity** retrieval with SHA-256 dedup
- **ISR-like context persistence** for cron session state recovery

### 4. Real-Time Communication
- **SSE push** (not polling) for frontend updates
- **Inbox/Outbox system**: user sends message → Agent processes → reply pushed via SSE
- **WeChat Enterprise integration** for mobile notifications

### 5. Production Operations
- **Watchdog** (30s heartbeat) monitors all services, auto-restarts on failure
- **Auto-healing** health checks recover deleted files + restart server
- **Pre-commit hooks** scan for secrets before every commit
- **Cloudflare Tunnel** for secure external access without opening ports

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check .

# Format
ruff format .

# Pre-commit (runs automatically on commit)
pre-commit install
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas where help is especially valuable:
- Unit tests for factor computation modules
- Documentation improvements
- Additional data source integrations
- Backtesting framework enhancements

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">
Built with 🧅 by <a href="https://github.com/FancongLiu">Fancong Liu</a>
</div>
