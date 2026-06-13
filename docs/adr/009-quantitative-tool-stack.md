# ADR-009: Quantitative Tool Stack Selection

**Date**: 2026-06-13 | **Status**: Accepted

## Context

The quantitative research pipeline requires: market data ingestion, factor computation, strategy backtesting, risk analysis, portfolio optimization, and knowledge graph construction. Each domain has multiple competing libraries. The stack must work within a Python monorepo on WSL, with zero-cost or low-cost data sources, and produce institutional-grade metrics (Sharpe, MaxDD, Calmar).

Options evaluated:
- **Backtesting**: NautilusTrader vs. Backtrader vs. VectorBT vs. Zipline-Reloaded
- **Factors**: Qlib vs. Alphalens vs. custom numpy/pandas
- **Risk**: empyrical vs. Riskfolio-Lib vs. pyfolio
- **Data**: yfinance vs. OpenBB vs. Alpha Vantage vs. polygon.io
- **Graph**: NetworkX vs. Neo4j vs. Kuzu

## Decision

| Domain | Choice | Rationale |
|--------|--------|-----------|
| Event-driven backtest | `bt` (pmorissette) | Lightweight, flexible tree structure, good for binary catalyst events |
| Vectorized backtest | VectorBT | Fast for factor screening across large universes |
| Factor engine | Qlib (Microsoft) | AI-driven alpha mining, production-grade factor computation |
| Factor analysis | Alphalens (Quantopian) | IC analysis, quantile returns, turnover — industry standard |
| Risk metrics | `empyrical` | Sharpe, MaxDD, Calmar, VaR — one function call each |
| Portfolio optimization | Riskfolio-Lib | Mean-variance, CVaR, risk parity, hierarchical risk parity |
| Market data | `yfinance` | Free, reliable, Python-native, covers global equities |
| Alternative data | Agent-Reach (proposed) | Chinese social media (Bilibili, Xiaohongshu, WeChat) |
| Knowledge graph | NetworkX + Neo4j (hybrid) | NetworkX for in-memory analysis (303 nodes, 850 edges); Neo4j for persistent graph storage |
| Technical indicators | `pandas-ta` | 200+ indicators, pandas-native, active maintenance |
| ML regime detection | `statsmodels` (Markov Switching) | Battle-tested econometrics, no GPU needed |

## Rationale

- **Maturity over novelty**: All chosen tools have 5+ years of community use. Quantopian's stack (Alphalens, empyrical, pyfolio) was audited by institutional investors before the company shut down — the code is battle-hardened.
- **Cost structure**: yfinance is free and covers 95% of use cases. Alpha Vantage is the free fallback. No Bloomberg terminal, no $2000/month data feeds.
- **Python-native**: Every tool is Python-first, installable via pip, and works in WSL without Docker/Kubernetes.
- **Composability**: Each tool does one thing well. empyrical computes ratios, Riskfolio-Lib optimizes weights, bt runs the backtest. They compose through pandas DataFrames — no monolithic framework lock-in.
- **Escape hatches**: VectorBT for fast screening → bt for detailed event simulation → NautilusTrader (reserved) for live trading. Progressive commitment to complexity.

## Consequences

- ✅ Full quant pipeline from data to deployment in pure Python
- ✅ Zero licensing cost for the core stack
- ✅ Each component independently upgradeable
- ❌ No unified framework — glue code required between tools
- ❌ yfinance rate limits on heavy scanning days (mitigated by caching)
- ❌ NetworkX in-memory graph won't scale past ~10K nodes (Neo4j escape hatch ready)
- ❌ Qlib requires Chinese market data setup for A-share factors
