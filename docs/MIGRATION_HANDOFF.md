# Migration Handoff — OnionQuant → Hermanos

**Date**: 2026-05-17 17:05 | **Status**: 92+ tasks complete, 3 blocked, 1 pending

## Project Architecture Overview

```
OnionQuant (虚拟量化公司)
├── quant_framework/     # 核心量化引擎 (42 modules, 10 subpackages)
├── infrastructure/      # 中间层 (API proxy, memory, model tier, pipeline)
├── company/             # 组织层 (dashboard, agents, server, inbox/outbox)
├── tests/               # 测试 (smoke + e2e, 80+ pass)
└── scripts/             # 运维脚本 (pipeline, dashboard update)
```

### Core Design Principles
1. **"不手搓" 铁律**: Every module uses mature frameworks (riskfolio-lib, sklearn, statsmodels, empyrical, alphalens, pandas-ta). Zero hand-rolled algorithms.
2. **权重向量接口模式**: All optimizer functions return `{"weights": [...], ...}` — the weight vector is the sole interface contract between modules.
3. **安全护栏**: `eval()`/`exec()` zero tolerance, credentials via env vars only, `yaml.safe_load()` only, risky operations require chairman outbox approval.
4. **3-tier agent architecture**: CEO → Department Leads → Specialists, with manifest-based (YAML) agent definitions.

---

## Completed Work (92+ Tasks)

### Quant Engine (`quant_framework/`)
| Module | Framework | Status |
|--------|-----------|--------|
| `risk/risk_metrics.py` | empyrical-reloaded 0.5.12 | ✅ |
| `risk/portfolio_optimizer.py` | riskfolio-lib 7.2.1 (MV, BL, BL-RP, BL-Bayesian, Kelly, Risk-Parity) | ✅ |
| `risk/covariance.py` | sklearn (Ledoit-Wolf, OAS, MCD, Factor Model, EW, graphical_lasso) | ✅ |
| `risk/stress_testing.py` | 8 historical crisis scenarios + Kupiec VaR backtest | ✅ |
| `risk/performance_attribution.py` | OLS factor regression + rolling + Brinson + contribution | ✅ |
| `risk/industry_attribution.py` | Barra risk attribution + risk budget decomposition | ✅ |
| `risk/drawdown_control.py` | pandas-ta (CPPI, vol targeting, stop loss) | ✅ |
| `strategies/qlib_factor_engine.py` | pyqlib 0.9.7 — 39 factors, safe pandas (no eval) | ✅ |
| `strategies/factor_analysis.py` | Rolling IC, IC decay, turnover, quantile returns | ✅ |
| `strategies/alpha_combiner.py` | IC/IR weighted + Bayesian shrinkage + regime-aware | ✅ |
| `strategies/ml_predictor.py` | sklearn (Ridge, RF, XGBoost) + time-series CV | ✅ |
| `strategies/optimizer.py` | skopt Bayesian optimization + Walk-Forward CV | ✅ |
| `strategies/regime_detector.py` | statsmodels MarkovRegression + rolling classification | ✅ |
| `strategies/stat_arb.py` | statsmodels cointegration + OLS hedge ratio + Z-score | ✅ |
| `strategies/canslim_screener.py` | YAML-configured 3-stage screening | ✅ |
| `strategies/intraday_momentum.py` | VWAP + Sigma + NoiseArea (backtrader compatible) | ✅ |
| `backtest/harness.py` | Vectorized + event-driven dual mode, empyrical metrics | ✅ |
| `backtest/analytics.py` | Win/loss, streaks, drawdown duration, monthly tables | ✅ |
| `backtest/visualization.py` | 6 chart types (equity, DD, heatmap, rolling, yearly, dist) | ✅ |
| `execution/order_simulator.py` | TWAP/VWAP + slippage + commission + position tracking | ✅ |
| `execution/position_sizer.py` | Kelly/Risk-Parity/Vol-Targeted/Equal-Weight | ✅ |
| `execution/rebalancer.py` | Calendar/threshold/hybrid + turnover constraint + tax-loss | ✅ |
| `execution/tca.py` | Pre-trade cost + implementation shortfall + Almgren-Chriss | ✅ |
| `data/data_quality.py` | 5 auto checks (NaN, freshness, outlier, completeness, lookahead) | ✅ |
| `data/benchmark.py` | Latency/completeness/accuracy + cross-source validation | ✅ |
| `reporting/report_generator.py` | Daily/weekly/monthly markdown reports | ✅ |
| `orchestration/seed_context.py` | Deterministic seed-first context (no LLM for data fetch) | ✅ |
| `logging_config.py` | Unified logging replacing print() | ✅ |

### Infrastructure (`infrastructure/`)
| Module | Description | Status |
|--------|-------------|--------|
| `api_proxy.py` | Token bucket rate limiter + retry + audit + provider failover | ✅ |
| `memory_store.py` | TF-IDF search + strength decay + SHA-256 dedup + token budget | ✅ |
| `model_tier.py` | TierRouter (QUICK/DEEP/LOCAL), 10 task categories, ~$0.13/day | ✅ |
| `quant_pipeline/assets.py` | Dagster assets (fetch → factor → quality → report) | ✅ |

### Company Layer (`company/`)
| Component | Description | Status |
|-----------|-------------|--------|
| `server.py` | FastAPI + SSE push + 6 API endpoints | ✅ |
| `quant_dashboard.html` | Real-time dashboard with 6 CSS animations | ✅ |
| `agents/manifest_schema.py` | YAML-based agent manifest system | ✅ |
| `agents/manifests/*.yaml` | 4 department manifests (ceo, extreme_drive, strategy, risk) | ✅ |
| `wechat_bot.py` | WeCom bidirectional bot (awaiting callback URL config) | ✅ |
| `reports/` | 15+ repo analyses, red team reviews, AEL/FinRL-X evaluations | ✅ |

---

## Pending / Unfinished Work

### T855: HTML Module Split (P2) — Last Actionable Task
- **What**: Split 1400-line `company/quant_dashboard.html` into separate CSS/JS/HTML files + `static/` directory
- **Priority**: P2 (low). Deferred 5+ cycles — dashboard is stable, chairman philosophy: "Preserve what works."
- **Risk**: Breaking a working dashboard for cosmetic refactoring
- **Recommendation**: Only execute if dashboard maintenance becomes painful, or if adding new features requires modular structure

### Blocked Items (Need Chairman Action)
| ID | Description | Blocker | Priority |
|----|-------------|---------|----------|
| W001 | Node.js installation (skills need npx) | Node.js not installed | Low |
| T602 | sentiment → FinDPO alternative | FinDPO has no pip package | Medium |
| W004 | WeChat callback URL config | Chairman must set callback URL in WeCom admin panel | Medium |

### 18 Outdated pip Packages
Key ones requiring attention:
- `pandas 2.3.3 → 3.0.3` (breaking: `future.infer_string` default, `DataFrame.applymap` rename)
- `numpy 2.2.6 → 2.4.x`
- `fastapi 0.128.8 → 0.136.x`
- **Rule**: No blind `pip install --upgrade`. Test in dev branch first.

---

## Active Cron Jobs (4 Durable)

These must be re-created in the new environment:

| Cron ID | Name | Schedule | Prompt |
|---------|------|----------|--------|
| `22208ed5` | Autonomous Loop | Every 1 min | `<<autonomous-loop-dynamic>>` |
| `9e37695b` | Iteration Engine | Every 15 min (13,28,43,58) | `🔄 持续迭代引擎` |
| `df16ad70` | Red Team Review | Every 30 min (7,37) | `🔴 红队审查模式` |
| `f1f0dd1d` | Market Data Refresh | Weekdays 5:37 AM (美东收盘后) | `📊 每日市场数据刷新` |

**Migration note**: These are durable cron jobs in Claude Code's scheduler. After migrating to hermanos, re-create them with `CronCreate`. The exact prompt text must match — it's how the loop identifies its task.

---

## Environment Requirements

### Python 3.12 + Virtual Env (.venv)
```
riskfolio-lib==7.2.1    # Portfolio optimization (MV, BL, Kelly, Risk-Parity)
scikit-learn             # Covariance estimation, ML models, TF-IDF
statsmodels==0.14.6      # Regime detection, cointegration, Markov switching
empyrical-reloaded==0.5.12  # Financial metrics
alphalens-reloaded==0.4.6   # Factor evaluation
pyqlib==0.9.7            # Factor engine (Alpha158/360 expressions)
pandas-ta==0.4.71b0      # Technical indicators
scipy==1.17.1            # Optimization, statistics
numpy==2.2.6             # Numeric foundation
pandas==2.3.3            # Data (do NOT upgrade to 3.0 without testing)
matplotlib==3.10.9       # Visualization
seaborn==0.13.2          # Heatmaps
fastapi==0.128.8         # Web server
uvicorn==0.40.0          # ASGI server
yfinance==1.3.0          # Market data (Yahoo Finance)
openbb-yfinance==1.6.2   # OpenBB provider
pandera==0.31.1          # Data validation
praw==7.8.1              # Reddit sentiment
pyyaml                   # Config/agent manifest loading (safe_load only)
python-dotenv==1.2.2     # .env loading
pycryptodome==3.23.0     # WeChat AES decryption
aiohttp==3.13.5          # Async HTTP (WeChat bot)
docker==7.1.0            # Docker SDK (TimescaleDB/Dagster)
```

### Optional / Infrastructure
- Docker Desktop (TimescaleDB + Dagster)
- Node.js (only if skills system needed — W001)

---

## File Organization for Migration

### Must Preserve (Active Code)
```
quant_framework/          # 42 .py files — core quant engine
infrastructure/           # 5 .py files — middleware
company/
  server.py              # FastAPI dashboard server
  quant_dashboard.html   # Frontend (1400 lines)
  wechat_bot.py          # WeCom bot
  agents/                # Agent manifest system
  reports/               # Historical reports (reference)
  chairman_outbox/       # Pending outbox messages
  chairman_inbox/        # Inbox + processed/
config.py                # API keys config
TASK_TRACKER.md          # Task state (crucial for continuity)
CLAUDE.md                # Project instructions (loaded by Agent)
tests/
  test_smoke.py          # 80+ smoke tests
  test_e2e.py            # 6 e2e pipelines
scripts/
  run_pipeline.py        # E2E pipeline runner
  update_dashboard.py    # Dashboard updater
```

### Can Archive (Old/Renamed)
```
quant_company/           # Old Round 1-6 code (all migrated to quant_framework/)
agent_build.ipynb        # Old notebook
display_news.py          # Old scripts (migrated)
show_news.py             # Old scripts (migrated)
test_*.py (root level)   # Old tests (migrated to tests/)
```

### Git-Ignored / State
```
.venv/                   # Virtual environment (rebuild from requirements)
company/chairman_inbox/processed/  # Processed messages
.claude/                 # Claude Code state (cron jobs, settings)
```

---

## What Must Continue Running Post-Migration

1. **4 cron jobs** — re-create in hermanos environment
2. **`python company/server.py`** — dashboard on localhost:8765
3. **`python company/wechat_bot.py`** — if WeChat callback URL configured
4. **Docker compose** — if TimescaleDB/Dagster pipeline needed
5. **Daily data refresh** — pulls 25 tickers × ~250 rows from Yahoo Finance
6. **Smoke tests** — `pytest tests/test_smoke.py -x --timeout=300` (expect yfinance tests to occasionally fail on rate limits)

---

## Key Decisions & Rationale

| Decision | Rationale | Date |
|----------|-----------|------|
| FinRL-X DRL stack → Skip | riskfolio-lib convex optimization is more robust, faster, interpretable | 2026-05-17 |
| AEL bandit agent → Skip (mostly) | "Less is more": simplest variant Sharpe 2.13, added complexity degrades | 2026-05-17 |
| Black-Litterman via riskfolio-lib | Market-implied equilibrium + asset-level and factor-level (BLB) views | 2026-05-17 |
| Dual model tier (QUICK/DEEP) | Routine factor scans on cheap models, strategic decisions on quality models | 2026-05-17 |
| Seed-first context (no LLM for data) | Deterministic data pre-fetch before LLM calls, evidence with audit trail | 2026-05-17 |
| WeChat via direct callback (not iLink) | Simpler, fewer dependencies, wechat_bot.py is self-contained | 2026-05-17 |

---

## Migration Checklist

- [ ] Copy `quant_framework/`, `infrastructure/`, `company/`, `tests/`, `scripts/` to hermanos
- [ ] Copy `config.py`, `TASK_TRACKER.md`, `CLAUDE.md` to hermanos root
- [ ] Create `.venv/` with Python 3.12 + install all dependencies
- [ ] Run `pytest tests/test_smoke.py -x --timeout=300` — expect 80+/82 pass
- [ ] Start `python company/server.py` — verify http://localhost:8765 loads
- [ ] Re-create 4 cron jobs with same prompts
- [ ] Verify `python scripts/run_pipeline.py` runs end-to-end
- [ ] Review TASK_TRACKER.md for pending W004/T602/W001
- [ ] Decide on T855 (HTML split) — likely keep deferred
- [ ] Test WeChat bot: `python company/wechat_bot.py` (needs .env with WeCom credentials)
