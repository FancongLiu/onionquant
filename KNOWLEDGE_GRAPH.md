# 🧠 OnionQuant Knowledge Graph — Expert Edition

> **Last updated**: 2026-05-18 08:00 UTC (Neo4j KG added)
> **Modules**: 35 Python files across 7 subpackages | **Tests**: 69 smoke + 6 E2E | **Tasks done**: 86

---

## 1. Technical Stack — Evaluated vs Chosen

### Data Pipeline
| Component | Evaluated | Chosen | Why |
|-----------|----------|--------|-----|
| Data fetcher | yfinance, Alpha Vantage, Polygon.io, OpenBB | **yfinance** (MVP) → **OpenBB** (prod) | yfinance free but unreliable for production; OpenBB unified API |
| File format | CSV, HDF5, Parquet, Feather | **Parquet** | Columnar + compression + pandas native |
| DataFrame | pandas, Polars, cuDF | **pandas** (MVP) → **Polars** (scale) | pandas ecosystem first; Polars for 10M+ rows |
| Time-series DB | TimescaleDB, InfluxDB, ClickHouse | **TimescaleDB** (planned) | PostgreSQL-based, SQL-native |
| Orchestration | Airflow, Dagster, Prefect | **Dagster** (planned) | Asset-based, Pythonic, better for quant workloads |

### Backtesting
| Component | Evaluated | Chosen | Why |
|-----------|----------|--------|-----|
| Engine | Backtrader, Zipline, VectorBT, NautilusTrader, LEAN | **NautilusTrader** (primary) + **Backtrader** (legacy) | Rust core for speed; Backtrader kept for existing strategies |
| Metrics | Custom → empyrical | **empyrical** | Standard library, avoids hand-rolled Sharpe/MaxDD |
| Viz | matplotlib, plotly, altair | **matplotlib** (dark theme) | Object-oriented API, full control |

### Risk & Portfolio
| Component | Evaluated | Chosen | Why |
|-----------|----------|--------|-----|
| Covariance | Sample, Ledoit-Wolf, OAS, EWMA, Factor Model, MCD | **All 7 methods** via sklearn | Different regimes favor different estimators |
| Optimization | Mean-Variance, Risk Parity, Kelly, CPPI | **Riskfolio-Lib** (planned) | Production-grade convex optimization |
| Stress testing | Custom scenarios | **8 historical crises** (2008 GFC, 2020 COVID, etc.) | Empirically validated |
| VaR backtesting | Binomial, Kupiec POF, Christoffersen | **Kupiec POF** | Standard regulatory method |

### ML / AI
| Component | Evaluated | Chosen | Why |
|-----------|----------|--------|-----|
| Factor→Return model | Ridge, RandomForest, XGBoost, LightGBM, NN | **Ridge/RF/XGB** via sklearn | scikit-learn standard, no DL overhead |
| CV method | k-fold, GroupKFold, TimeSeriesSplit | **Walk-forward expanding window** | No lookahead bias |
| Ensemble | Simple avg, IC-weighted, IC-IR, Bayesian, Regime | **All 5 methods** in alpha_combiner.py | Context-dependent |
| Feature importance | coef_, feature_importances_, SHAP | **coef_ + feature_importances_** | Built-in, sufficient |

---

## 1.5. Knowledge Graph Framework — Neo4j + LangChain (方案A)

> **Decision**: 2026-05-18 董事长批准直接采用方案A (Neo4j + LangChain)
> **Status**: ✅ Implemented — `infrastructure/knowledge_graph.py` + `infrastructure/kg_schema.py`

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Knowledge Graph Engine                  │
│  infrastructure/knowledge_graph.py (Connection/CRUD)     │
│  infrastructure/kg_schema.py     (Node/Rel types)        │
├─────────────────────────────────────────────────────────┤
│  Neo4j (bolt://localhost:7687 or AuraDB)                 │
│  ┌─ Stock ──[:IN_INDUSTRY]── Industry                   │
│  ├─ Stock ──[:HAS_FACTOR]── Factor                      │
│  ├─ Stock ──[:CORRELATES_WITH]── Stock                  │
│  ├─ Stock ──[:MENTIONED_IN]── Report                    │
│  └─ Stock ──[:TRIGGERED]── Event / RiskAlert            │
└─────────────────────────────────────────────────────────┘
```

### Node Types (7)

| Node | Label | Unique Key | Purpose |
|------|-------|-----------|---------|
| Stock | `Stock` | `ticker` | US equity instrument |
| Factor | `Factor` | `name` | Alpha signal (momentum/reversal/vol/...) |
| Industry | `Industry` | `name` | Sector classification (AI_CHIPS/STORAGE/SPACE/...) |
| Report | `Report` | `path` | Research/trade/pipeline report |
| Event | `Event` | `uid` | Catalyst (earnings/launch/macro) |
| Agent | `Agent` | `name` | Department AI agent |
| RiskAlert | `RiskAlert` | `uid` | Premium/dilution/overbought/... alert |

### Relationship Types (7)

| Relationship | From | To | Properties |
|-------------|------|-----|------------|
| `CORRELATES_WITH` | Stock | Stock | `rho`, `window` |
| `HAS_FACTOR` | Stock | Factor | `value`, `date` |
| `IN_INDUSTRY` | Stock | Industry | — |
| `MENTIONED_IN` | Stock | Report | `sentiment` |
| `TRIGGERED` | Stock | Event / RiskAlert | — |
| `DEPENDS_ON` | Factor | Factor | — |
| `SUPPLIES_TO` | Stock | Industry | `relationship` |

### Usage

```python
from infrastructure.knowledge_graph import KnowledgeGraph, ingest_all

# Connect (auto-reads NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD from .env)
kg = KnowledgeGraph()
kg.init_schema()

# Full ingestion
stats = ingest_all(tickers, price_df, factor_df)
# → {'stock': 16, 'factor': 27, 'industry': 9, 'report': 5, ...}

# Query
kg.query_stock_factors("NVDA")         # NVDA's top factors by IC
kg.query_correlation_chain("MU","NVDA") # Shortest path between MU and NVDA
kg.query_industry_network("AI_CHIPS")   # All AI chip stocks + factor links
```

### Setup

```bash
# 1. Install Neo4j Desktop or AuraDB Free (neo4j.com)
# 2. Set env vars in .env:
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
# 3. Python deps already installed:
pip install neo4j langchain-neo4j neo4j-graphrag
```

### CLI

```bash
python infrastructure/knowledge_graph.py init            # Init schema + industries
python infrastructure/knowledge_graph.py ingest --tickers NVDA,MU,DXYZ
python infrastructure/knowledge_graph.py stats           # Node/edge counts
python infrastructure/knowledge_graph.py query --query-ticker NVDA
```

---

## 2. Module Dependency Graph

```
data/fetchers/          strategies/            risk/
├─ yfinance_fetcher.py  ├─ factor_calculator.py ├─ risk_metrics.py
├─ alpha_vantage_fetcher├─ factor_combiner.py   ├─ portfolio_optimizer.py
├─ news_sentiment.py    ├─ factor_analysis.py   ├─ drawdown_control.py
└─ data_utils.py        ├─ alpha_combiner.py    ├─ stress_testing.py
                        ├─ ml_predictor.py      ├─ performance_attribution.py
data/pipeline/          ├─ qlib_factor_engine.py├─ covariance.py
├─ pipeline.py          ├─ stat_arb.py          └─ industry_attribution.py
└─ safe_pandas.py       ├─ canslim_screener.py
                        ├─ market_regime.py     backtest/
execution/              ├─ param_optimizer.py   ├─ harness.py
├─ order_simulator.py   ├─ position_sizer.py    ├─ visualization.py
├─ tca.py               └─ alpha_combiner.py    └─ analytics.py
├─ rebalancer.py
└─ execution_simulator.py                       reporting/
                                                └─ report_generator.py
```

### Key cross-module dependencies
- `alpha_combiner.py` ← depends on `factor_calculator.py` (for factor columns)
- `ml_predictor.py` ← depends on `factor_calculator.py` (for input factors)
- `industry_attribution.py` ← depends on `covariance.py` (for risk budget)
- `performance_attribution.py` ← uses `statsmodels.OLS` (not hand-rolled)
- `harness.py` ← uses `empyrical` for all metrics
- `analytics.py` ← consumes output of `harness.py`
- `report_generator.py` ← consumes output of ALL modules

---

## 3. Decision History — What We Chose and Why

### Architecture Decisions
| ID | Decision | Date | Rationale |
|----|----------|------|-----------|
| AD-01 | CEO+SubAgent architecture | 2026-05-17 | One CEO agent dispatches to 16 department agents; avoids context fragmentation |
| AD-02 | `company/` + `quant_framework/` separation | 2026-05-17 | Org structure separate from quant code; clean seam |
| AD-03 | inbox/outbox communication pattern | 2026-05-17 | Async, file-based, no polling; SSE push for real-time |
| AD-04 | "不手搓" iron rule | 2026-05-17 | Must use mature frameworks (sklearn, scipy, statsmodels, empyrical); no custom math |
| AD-05 | Auto-approval ON for non-security | 2026-05-17 | Chairman approved; security guardrails unchanged |
| AD-06 | Vertical slice TDD | 2026-05-17 | One test→one impl per cycle; test behavior not implementation |

### Strategy Decisions
| ID | Decision | Date | Rationale |
|----|----------|------|-----------|
| SD-01 | Multi-factor + ML hybrid | 2026-05-17 | Pure factor misses nonlinear; pure ML overfits; hybrid is robust |
| SD-02 | Walk-forward CV only | 2026-05-17 | NO k-fold for time series — lookahead bias is unforgivable |
| SD-03 | IC-weighted alpha blending | 2026-05-17 | IC-weighted, IC-IR, Bayesian shrinkage, regime-aware — all available |
| SD-04 | Factor neutralization | 2026-05-17 | Industry + market cap neutralization via OLS orthogonalization |

### Infrastructure Decisions
| ID | Decision | Date | Rationale |
|----|----------|------|-----------|
| ID-01 | Windows + Python 3.12 | 2026-05-17 | Chairman's environment |
| ID-02 | 4 durable cron jobs | 2026-05-17 | 1min autonomous + 15min iteration + 30min red team + weekday data |
| ID-03 | `company/server.py` on port 8765 | 2026-05-17 | FastAPI + SSE + watchdog file monitoring |

---

## 4. Rejected Approaches — What We Know Doesn't Work

| Approach | Why Rejected | What We Use Instead |
|----------|-------------|---------------------|
| Hand-rolled covariance (numpy-only) | Error-prone, no shrinkage | sklearn.covariance.LedoitWolf/OAS/MinCovDet |
| Hand-rolled factor regression (numpy.linalg) | No t-stats, p-values, R^2 | statsmodels.OLS |
| k-fold CV for time series | Lookahead bias | Walk-forward expanding window |
| pandas `rolling().corr(method='spearman')` | pandas DOES NOT support this | scipy.stats.spearmanr with manual loop |
| Backtrader for new projects | Ecosystem declining | NautilusTrader (Rust core) |
| yfinance for production | Unreliable, no SLA | OpenBB / Polygon.io |
| Pure DL (LSTM/Transformer) for factor prediction | Overkill for linear factor→return | sklearn Ridge/RF/XGB first, DL only if needed |
| brinson_attribution without group mapping | Only asset-level; no sector view | Group-level Brinson decomposition |

---

## 5. Known Bugs / Limitations Discovered

| ID | Bug | Status | Workaround |
|----|-----|--------|------------|
| KB-01 | pandas `rolling().corr(method='spearman')` → TypeError | Permanent | `_rolling_spearman()` helper in alpha_combiner.py |
| KB-02 | `\xb2` (²) in print → UnicodeEncodeError on Windows GBK | Fixed | Use `^2` instead of `\xb2` |
| KB-03 | `pd.concat([Series, Series], axis=1).fillna(0)` → object dtype | Fixed | `.fillna(0.0).astype(float)` |
| KB-04 | position_sizer returns dict without 'total_allocated' when no buys | Fixed | Use `.get('total_allocated', 0)` |
| KB-05 | `to_markdown()` needs `tabulate` package | Workaround | Install tabulate pip package |
| KB-06 | Windows GBK stdout can't print emoji | Workaround | Wrap stdout with utf-8 TextIOWrapper |

---

## 6. Factor Knowledge Base

### Factor Categories Built
| Category | Factors | Module |
|----------|---------|--------|
| Momentum | mom_1d, mom_5d, mom_21d, mom_63d, mom_126d, mom_252d | factor_calculator.py |
| Reversal | rev_5d, rev_10d, rev_21d | factor_calculator.py |
| Volatility | vol_5d, vol_21d, vol_63d | factor_calculator.py |
| Turnover/Liquidity | turn_5d, turn_21d | factor_calculator.py |
| Size/Value | size_log, val_bp, val_ep | factor_calculator.py |
| Quality | roe, roa, gross_margin | factor_calculator.py |
| Correlation | corr_5d, corr_21d | factor_calculator.py |
| Beta | beta_63d, beta_252d | factor_calculator.py |
| Technical | rsi_14, bb_width | factor_calculator.py |

### Factor Processing Pipeline
1. **Compute**: `compute_all()` → raw factor values per ticker×date
2. **Neutralize**: OLS orthogonalization vs industry + market cap (qlib_factor_engine.py)
3. **Standardize**: Z-score + 3-sigma winsorize (factor_calculator.py)
4. **Combine**: Equal-weight, IC-weighted, IC-IR, Bayesian, Regime-aware (alpha_combiner.py)
5. **Analyze**: IC decay, IC IR, hit rate, turnover (factor_analysis.py)

### Factor IC Knowledge
- IC computed via Spearman rank correlation (NOT Pearson — robust to outliers)
- IC decay halflife measured empirically per factor
- Rolling IC windows: 21d, 63d, 126d, 252d
- IC IR = mean(IC) / std(IC) — measures signal consistency

---

## 7. Risk Model Knowledge Base

### Risk Metrics Implemented
| Metric | Source | Method |
|--------|--------|--------|
| VaR (Historical) | risk_metrics.py | nth percentile of return distribution |
| CVaR / ES | risk_metrics.py | Mean of returns below VaR threshold |
| Max Drawdown | risk_metrics.py | Peak-to-trough via expanding max |
| Sharpe Ratio | risk_metrics.py | (mean(ret) - rf) / std(ret); rf=2% |
| Sortino Ratio | risk_metrics.py | (mean(ret) - rf) / std(neg_ret) |
| Calmar Ratio | risk_metrics.py | ann_return / abs(max_dd) |
| Omega Ratio | risk_metrics.py | sum(pos)/sum(neg) |

### Covariance Estimation Methods
| Method | Source | When to Use |
|--------|--------|-------------|
| Sample covariance | sklearn | N >> T (many obs, few assets) |
| Ledoit-Wolf shrinkage | sklearn.covariance.LedoitWolf | N ≈ T (comparable) |
| OAS | sklearn.covariance.OAS | N > T (many assets) |
| EWMA | manual via pandas ewm | Regime shifts, recent data matters |
| Factor Model (PCA) | sklearn PCA + decomposition | Structural risk decomposition |
| Robust MCD | sklearn.covariance.MinCovDet | Outlier-prone data |
| Nearest PSD | eigendecomposition | Fix non-PSD matrices |

### Barra Risk Attribution
- **Factor risk** = sqrt(w' B Σ_f B' w) — systematic, from factor exposures
- **Specific risk** = sqrt(w' D w) — idiosyncratic, from regression residuals
- **Systematic ratio** = factor_var / total_var — what % of risk is factor-driven
- Factor exposures B estimated via OLS per asset (statsmodels)

### Risk Budget Decomposition
- **MRC** (Marginal Risk Contribution) = ∂σ/∂w_i = (Σw)_i / σ_p
- **CRC** (Component Risk Contribution) = w_i × MRC_i
- **%Risk** = CRC_i / σ_p
- Derived from covariance matrix — no hand-rolled differentiation

---

## 8. Execution Knowledge Base

### Market Impact Model
- **Almgren-Chriss** square-root model in tca.py
- Permanent impact: linear in trade size
- Temporary impact: sqrt(trade_size / ADV)
- Used in pre-trade cost estimation

### Implementation Shortfall (Perold 1988)
- **Delay cost**: price move between decision and first execution
- **Execution cost**: difference from arrival price during execution
- **Opportunity cost**: unfilled portion × terminal move

### Rebalancing
- **Calendar**: fixed schedule (daily/weekly/monthly)
- **Threshold**: drift-based trigger (±5% from target)
- **Hybrid**: calendar + emergency threshold
- Turnover constraints applied in rebalancer.py

---

## 9. Backtest Engine Knowledge Base

### Engine Architecture
| Mode | Engine | Speed | Use Case |
|------|--------|-------|----------|
| Vectorized | harness.py (numpy) | Fast | Daily frequency, factor strategies |
| Event-driven | Backtrader Cerebro | Medium | Intraday, order management, slippage |
| Production | NautilusTrader (Rust) | Fastest | Future upgrade path |

### Analytics Suite (analytics.py)
- **Streak analysis**: max_win_streak, max_loss_streak, avg streak lengths
- **Drawdown duration**: time underwater, recovery analysis, DD event count
- **Monthly returns**: years × months matrix with annual totals
- **Rolling metrics**: 21d/63d/126d Sharpe, vol, VaR as DataFrames
- **P/L ratio**: profit factor, tail ratio (95/05), gross win/loss

### Visualization (visualization.py)
- 6 chart types: equity curve, drawdown underwater, monthly heatmap, rolling metrics, annual bar chart, return distribution
- Dark theme (#1a1a2e background)
- matplotlib object-oriented API (no pyplot state machine)

---

## 10. ML Pipeline Knowledge Base

### Model Configurations
| Model | Best For | Limitations |
|-------|----------|-------------|
| Ridge (α=1.0) | Linear factor→return, interpretable | Cannot capture nonlinearities |
| RandomForest (n=100, depth=5) | Nonlinear, robust to outliers | Less interpretable |
| XGBoost (lr=0.05, depth=5) | Best accuracy, handles missing values | Requires xgboost package |

### Feature Importance Extraction
- Ridge/RF: `.coef_` (absolute values) or `.feature_importances_`
- Fallback: equal weight if model has neither
- Top-N features reported per CV fold

### Evaluation Metrics
- **IC** (Information Coefficient): Spearman correlation between prediction and actual
- **R^2**: coefficient of determination
- **Quantile spread**: mean return of top quintile − bottom quintile
- **Hit rate**: % of predictions with correct sign direction

---

## 11. Reporting Knowledge Base

### Report Types
| Type | Frequency | Content |
|------|-----------|---------|
| Daily Briefing | Trading days | P&L, signals, factor IC, positions |
| Weekly Report | Weekly | Performance, risk, factor performance, trades |
| Monthly Report | Monthly | Full attribution, stress test, factor analysis, TCA |

### Report Design Principles
1. **结论前置**: Conclusion first, evidence after
2. **一页纸原则**: Core conclusions ≤ 1 page
3. **架构图必备**: Every systematic plan must have architecture diagram
4. **风险标注**: Every plan must flag risks
5. **两步走**: Body in plain language; appendix for technical details

---

## 12. Open Source Survey — Key Findings

### Top-rated projects (Round 1 evaluation)
| Project | Rating | Key Strength | Concern |
|---------|--------|-------------|---------|
| Qlib (Microsoft) | 4.8/5 | End-to-end AI quant platform | Complex setup |
| NautilusTrader | 4.7/5 | Rust performance + Python API | Young ecosystem |
| Riskfolio-Lib | 4.5/5 | Modern portfolio optimization | Documentation gaps |
| Alphalens | 4.3/5 | Factor analysis standard | Unmaintained |
| Zipline-Reloaded | 3.2/5 | Well-documented | Declining, maintenance issues |

### Projects rejected
- vnpy: China-market focused, not for US equities
- backtesting.py: Too simple for multi-asset
- TensorTrade: RL-focused, not for factor strategies
- FinRL: Academic, not production-ready

---

## 13. Cross-Cutting Knowledge

### The "No Hand-Roll" Rule
- **Stats**: statsmodels (OLS, t-stats, p-values)
- **ML**: sklearn (Ridge, RF, XGBoost, LedoitWolf, MinCovDet)
- **Metrics**: empyrical (Sharpe, Sortino, Calmar, MaxDD)
- **Optimization**: scipy.optimize
- **Correlation**: scipy.stats.spearmanr, pearsonr
- **Covariance**: sklearn.covariance (LedoitWolf, OAS, MinCovDet)

### The "Vertical Slice" Rule
- One test → one implementation per cycle
- Test behavior (public API), not implementation (private methods)
- Only refactor when GREEN (tests passing)

### Security Guardrails
1. Never push --force to main/master
2. Never skip git hooks without explicit approval
3. Never read/write files outside project directory
4. Never store credentials/secrets
5. When uncertain → write outbox, skip task, continue to next

### Communication Conventions
- Default: professional, concise
- Caveman mode: ultra-compressed (~75% token reduction)
- All Chinese communication with chairman
- Department agents: autonomous, non-blocking

---

## 14. File Index — Where Everything Lives

### Core Framework (`quant_framework/`)
```
quant_framework/
├── __init__.py
├── data/
│   ├── __init__.py
│   ├── fetchers/
│   │   ├── yfinance_fetcher.py
│   │   ├── alpha_vantage_fetcher.py
│   │   ├── data_utils.py
│   │   └── news_sentiment.py
│   └── pipeline/
│       ├── pipeline.py
│       └── safe_pandas.py
├── strategies/
│   ├── __init__.py
│   ├── factor_calculator.py
│   ├── factor_combiner.py
│   ├── factor_analysis.py
│   ├── alpha_combiner.py
│   ├── ml_predictor.py
│   ├── qlib_factor_engine.py
│   ├── stat_arb.py
│   ├── canslim_screener.py
│   ├── canslim_config.yaml
│   ├── market_regime.py
│   ├── param_optimizer.py
│   └── position_sizer.py
├── risk/
│   ├── __init__.py
│   ├── risk_metrics.py
│   ├── portfolio_optimizer.py
│   ├── drawdown_control.py
│   ├── stress_testing.py
│   ├── performance_attribution.py
│   ├── covariance.py
│   └── industry_attribution.py
├── backtest/
│   ├── __init__.py
│   ├── harness.py
│   ├── visualization.py
│   └── analytics.py
├── execution/
│   ├── __init__.py
│   ├── order_simulator.py
│   ├── execution_simulator.py
│   ├── tca.py
│   └── rebalancer.py
└── reporting/
    ├── __init__.py
    └── report_generator.py
```

### Company Structure (`company/`)
```
company/
├── server.py
├── chairman_dashboard.html
├── quant_dashboard.html
├── chairman_inbox/          # Chairman → Agent messages
│   └── processed/           # Archived after processing
├── chairman_outbox/         # Agent → Chairman messages
├── reports/                 # Generated reports
├── departments/             # 16 department indexes
│   ├── strategy_research/
│   ├── academic_research/
│   ├── sentiment_intel/
│   ├── data_engineering/
│   ├── backtest_engine/
│   ├── risk_management/
│   ├── execution/
│   ├── open_source_research/
│   ├── it_tech/
│   ├── reporting/
│   ├── knowledge_management/
│   ├── ceo_office/
│   ├── extreme_drive/
│   ├── continuous_evolution/
│   ├── secretariat/
│   └── oversight_quality/
└── tests/
```

---

*Auto-generated by knowledge management department. Updated continuously by CEO agent.*
