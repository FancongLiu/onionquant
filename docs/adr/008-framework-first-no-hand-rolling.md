# ADR-008: Framework-First Architecture (No Hand-Rolling Policy)

**Date**: 2026-06-13 | **Status**: Accepted

## Context

Every feature implementation faces the same fork: write custom code vs. integrate an existing library. The project spans quantitative finance, web scraping, data pipelines, factor computation, risk modeling, and agent orchestration — all domains with mature open-source ecosystems. Without a clear rule, the default instinct is to write from scratch (faster in the moment, slower in aggregate).

Options:
1. No policy — decide case-by-case
2. Framework-first — always search for existing tools before writing
3. Build-everything — custom code for maximum control

## Decision

Choose **Framework-First Architecture**: before writing any implementation, ask three gate questions:
1. Does GitHub have an existing library/tool for this?
2. Does a mature framework already solve this problem?
3. Am I about to "hand-roll" this?

Hand-rolling triggers: custom parsers, custom backtest loops, custom data pipelines, custom factor computation, custom risk models, custom scrapers. These must delegate to established frameworks.

Allowed exceptions: glue code (<50 lines connecting two frameworks), config/orchestration (YAML/CLI + framework calls), and project-specific business logic (e.g., CANSLIM screening criteria) where computation is delegated to frameworks.

## Rationale

- **Leverage**: The quant ecosystem alone has NautilusTrader (backtesting), VectorBT (vectorized analysis), Qlib (AI-driven factors), empyrical (risk metrics), Riskfolio-Lib (portfolio optimization), pandas-ta (technical indicators), yfinance (market data), OpenBB (data aggregation). Each represents person-years of battle-tested code.
- **Correctness**: Custom backtest loops are the #1 source of look-ahead bias and silent PnL errors. Framework backtests have been audited by thousands of users.
- **Velocity**: Writing a custom factor engine costs days; `qlib_factor_engine.py` wrapping Qlib costs hours. The difference compounds across dozens of features.
- **Chairman directive**: 2026-05-18 chairman explicitly mandated this policy after observing repeated hand-rolling patterns.

## Consequences

- ✅ Every feature starts with a GitHub/WebSearch for existing solutions
- ✅ Custom code is limited to project-specific glue, reducing bug surface
- ✅ Framework updates bring free improvements (bug fixes, new features)
- ❌ Learning curve for each new framework
- ❌ Dependency risk — framework abandonment requires migration
- ❌ Sometimes frameworks are overkill for simple tasks (mitigated by the <50-line glue exception)
