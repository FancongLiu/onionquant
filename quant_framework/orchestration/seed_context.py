#!/usr/bin/env python3
"""Seed-First context builder — deterministic data pre-fetch before agent reasoning.

Pattern from opensre's seed-first ReAct loop:
  1. Before calling LLM, deterministically fetch real data (ground truth)
  2. Seed results injected as structured context — LLM starts from facts, not guesses
  3. Evidence accumulated with metadata (key, data, source, timestamp) for audit

This prevents hallucination of market data, factor values, and risk metrics
in agent decision-making. For a quant system, this is critical — trading decisions
must be based on actual data, not LLM-invented numbers.

Pure Python, integrates with existing quant_framework modules.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Evidence Record ────────────────────────────────────────


@dataclass
class Evidence:
    """A single piece of evidence from deterministic data fetch.

    Pattern: opensre's evidence dict with key/data/tool_name/source/loop_iteration.
    """

    key: str  # unique identifier for this evidence
    data: Any  # the actual data (DataFrame, dict, Series, float)
    source: str  # which module/function produced this
    category: str = (
        "market_data"  # market_data | factor | risk | portfolio | fundamental
    )
    timestamp: str = ""  # when this evidence was collected
    loop_iteration: int = 0  # which reasoning loop iteration
    ttl_seconds: int = 300  # how long this evidence is valid
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def age_seconds(self) -> float:
        try:
            ts = datetime.fromisoformat(self.timestamp)
            return (datetime.now() - ts).total_seconds()
        except (ValueError, TypeError):
            return float("inf")

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds < self.ttl_seconds

    def summarize(self) -> dict:
        """Produce a compact summary for LLM context injection."""
        summary = {
            "key": self.key,
            "source": self.source,
            "category": self.category,
            "age_s": round(self.age_seconds, 1),
        }
        data = self.data
        if isinstance(data, pd.DataFrame):
            summary["shape"] = data.shape
            summary["columns"] = list(data.columns)[:15]
            summary["preview"] = data.head(3).to_dict("records")
        elif isinstance(data, pd.Series):
            summary["dtype"] = str(data.dtype)
            summary["length"] = len(data)
            if len(data) <= 5:
                summary["values"] = data.to_dict()
            else:
                summary["stats"] = {
                    "mean": round(float(data.mean()), 6),
                    "std": round(float(data.std()), 6),
                    "min": round(float(data.min()), 6),
                    "max": round(float(data.max()), 6),
                }
        elif isinstance(data, dict):
            summary.update(data)
        elif isinstance(data, (int, float, str, bool)):
            summary["value"] = data
        return summary


# ── Seed Context Builder ───────────────────────────────────


class SeedContext:
    """Accumulate evidence from deterministic data fetches before agent reasoning.

    Usage:
        ctx = SeedContext()
        ctx.seed("market_prices", lambda: fetch_prices(["AAPL"]),
                 source="yfinance_fetcher", category="market_data")
        ctx.seed("factor_values", lambda: compute_factors(df),
                 source="factor_engine", category="factor")

        # Build LLM-ready context
        prompt_context = ctx.build_context()

        # Audit trail
        ctx.save_audit("evidence_trail.json")
    """

    def __init__(self, max_evidence: int = 20):
        self.evidence: list[Evidence] = []
        self.max_evidence = max_evidence
        self.loop_iteration = 0
        self.errors: list[dict] = []

    def seed(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        source: str = "unknown",
        category: str = "market_data",
        ttl_seconds: int = 300,
        metadata: dict[str, Any] | None = None,
    ) -> Evidence | None:
        """Deterministically fetch data and record as evidence.

        Args:
            key: Unique identifier for this evidence.
            fetch_fn: Callable that returns the data. MUST be deterministic (no LLM).
            source: Which module/function produced this.
            category: market_data | factor | risk | portfolio | fundamental.
            ttl_seconds: How long before this evidence is considered stale.
            metadata: Additional context.

        Returns:
            Evidence record, or None if fetch failed.

        Pattern from opensre: seed calls are deterministic, never involve LLM.
        The LLM only sees evidence summaries AFTER all seeds are collected.
        """
        if len(self.evidence) >= self.max_evidence:
            return None

        try:
            data = fetch_fn()
            evidence = Evidence(
                key=key,
                data=data,
                source=source,
                category=category,
                ttl_seconds=ttl_seconds,
                loop_iteration=self.loop_iteration,
                metadata=metadata or {},
            )
            self.evidence.append(evidence)
            return evidence
        except Exception as e:
            self.errors.append(
                {
                    "key": key,
                    "source": source,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return None

    def seed_or_skip(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        max_age_seconds: int = 300,
        **kwargs,
    ) -> Evidence | None:
        """Seed data only if existing evidence for this key is stale or missing."""
        existing = self.get(key)
        if existing and existing.age_seconds < max_age_seconds:
            return existing
        return self.seed(key, fetch_fn, **kwargs)

    def get(self, key: str) -> Evidence | None:
        """Retrieve evidence by key."""
        for e in self.evidence:
            if e.key == key:
                return e
        return None

    def get_category(self, category: str) -> list[Evidence]:
        return [e for e in self.evidence if e.category == category]

    def build_context(self, max_tokens: int = 4000, include_raw: bool = False) -> str:
        """Build LLM-ready context string from all seed evidence.

        Args:
            max_tokens: Rough token budget for evidence summaries.
            include_raw: If True, include raw data dicts (more detail, more tokens).

        Returns:
            Structured context string for injection into agent system prompt.
        """
        if not self.evidence:
            return ""

        lines = [
            "## Seed Context (Deterministic Data Pre-Fetch)",
            f"**Evidence items**: {len(self.evidence)} | **Loop**: {self.loop_iteration}",
            f"**Fresh**: {sum(1 for e in self.evidence if e.is_fresh)}/{len(self.evidence)}",
            f"**Errors**: {len(self.errors)}",
            "",
        ]

        token_estimate = 0
        for e in self.evidence:
            lines.append(f"### {e.key}")
            lines.append(
                f"- **Source**: {e.source} | **Category**: {e.category} | **Age**: {e.age_seconds:.0f}s"
            )

            summary = e.summarize()
            if include_raw:
                lines.append(
                    f"```json\n{json.dumps(summary, indent=2, ensure_ascii=False)}\n```"
                )
                token_estimate += len(json.dumps(summary)) // 4
            else:
                # Compact: key stats only
                if "stats" in summary:
                    s = summary["stats"]
                    lines.append(
                        f"  mean={s['mean']:.4f} std={s['std']:.4f} min={s['min']:.4f} max={s['max']:.4f}"
                    )
                elif "value" in summary:
                    lines.append(f"  value={summary['value']}")
                elif "shape" in summary:
                    lines.append(
                        f"  shape={summary['shape']} cols={summary['columns'][:8]}"
                    )
                    if "preview" in summary:
                        lines.append(
                            f"  preview={json.dumps(summary['preview'], ensure_ascii=False)[:200]}"
                        )
                token_estimate += 50

            if token_estimate > max_tokens:
                lines.append("*(truncated — token budget exceeded)*")
                break

        if self.errors:
            lines.append("### Errors During Pre-Fetch")
            for err in self.errors:
                lines.append(f"- [{err['key']}] {err['error']}")

        lines.append(f"\n*Seed context generated {datetime.now().isoformat()}*")
        return "\n".join(lines)

    def build_compact(self) -> str:
        """Ultra-compact context (<500 tokens) for fast-mode agents."""
        if not self.evidence:
            return ""

        items = []
        for e in self.evidence:
            s = e.summarize()
            compact = f"[{e.key}] {e.source}"
            if "stats" in s:
                compact += f" mean={s['stats']['mean']:.4f}"
            elif "value" in s:
                compact += f" ={s['value']}"
            items.append(compact)

        return " | ".join(items)

    # ── Audit ──────────────────────────────────────────────

    def save_audit(self, path: Path) -> None:
        """Save full evidence trail as JSON for audit/replay."""
        audit = {
            "generated_at": datetime.now().isoformat(),
            "loop_iteration": self.loop_iteration,
            "n_evidence": len(self.evidence),
            "n_errors": len(self.errors),
            "evidence": [
                {
                    "key": e.key,
                    "source": e.source,
                    "category": e.category,
                    "timestamp": e.timestamp,
                    "age_s": e.age_seconds,
                    "summary": e.summarize(),
                }
                for e in self.evidence
            ],
            "errors": self.errors,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def clear(self):
        self.evidence.clear()
        self.errors.clear()
        self.loop_iteration += 1


# ── Seed Context Factory for Quant Domain ──────────────────


class QuantSeedContext(SeedContext):
    """Pre-configured seed context for quant trading decisions.

    Seeds market data, factor values, risk metrics, and portfolio state
    before any agent reasoning about trading decisions.

    Usage:
        ctx = QuantSeedContext()
        ctx.seed_all(["AAPL", "MSFT", "GOOGL"])
        prompt = ctx.build_context()
    """

    def seed_market_data(
        self, tickers: list[str], fetcher=None, lookback_days: int = 252
    ) -> bool:
        """Seed OHLCV + returns for tickers."""
        from quant_framework.data.fetchers.yfinance_fetcher import fetch_ohlcv

        def _fetch():
            dfs = {}
            for t in tickers:
                try:
                    df = fetch_ohlcv(t, period=f"{lookback_days}d")
                    if not df.empty:
                        dfs[t] = df
                except Exception:
                    pass
            return dfs

        evidence = self.seed_or_skip(
            f"market_data_{len(tickers)}tickers",
            _fetch,
            source="yfinance_fetcher",
            category="market_data",
            ttl_seconds=300,
        )
        return evidence is not None

    def seed_factors(
        self, df: pd.DataFrame, factor_columns: list[str] | None = None
    ) -> bool:
        """Seed factor values and basic stats."""
        if factor_columns is None:
            # Auto-detect numeric columns that look like factors
            factor_columns = [
                c
                for c in df.select_dtypes(include=[np.number]).columns
                if c not in ("open", "high", "low", "close", "volume", "adj_close")
            ]

        def _fetch():
            if df.empty:
                return {"error": "empty dataframe"}
            stats = {}
            for col in factor_columns:
                if col in df.columns:
                    series = df[col].dropna()
                    if len(series) > 10:
                        stats[col] = {
                            "mean": float(series.mean()),
                            "std": float(series.std()),
                            "skew": float(series.skew()),
                            "recent": float(series.iloc[-1]),
                        }
            return stats

        evidence = self.seed_or_skip(
            f"factors_{len(factor_columns)}cols",
            _fetch,
            source="factor_calculator",
            category="factor",
            ttl_seconds=600,
        )
        return evidence is not None

    def seed_risk_metrics(self, returns: pd.Series) -> bool:
        """Seed risk metrics from returns."""
        from quant_framework.risk.risk_metrics import (
            cvar,
            sharpe_ratio,
            sortino_ratio,
            var_historical,
        )

        def _fetch():
            return {
                "var_95": var_historical(returns, 0.95),
                "cvar_95": cvar(returns, 0.95),
                "sharpe": sharpe_ratio(returns),
                "sortino": sortino_ratio(returns),
            }

        evidence = self.seed_or_skip(
            "risk_metrics",
            _fetch,
            source="risk_metrics",
            category="risk",
            ttl_seconds=600,
        )
        return evidence is not None

    def seed_all(
        self, tickers: list[str], lookback_days: int = 252, include_risk: bool = True
    ) -> str:
        """Run full seed pipeline for typical quant decision.

        Returns compact context string ready for agent prompt injection.
        """
        # 1. Market data
        self.seed_market_data(tickers, lookback_days=lookback_days)

        # 2. Risk metrics (from any available returns)
        if include_risk:
            market = self.get(f"market_data_{len(tickers)}tickers")
            if market and isinstance(market.data, dict):
                for ticker, df in market.data.items():
                    if "close" in df.columns:
                        returns = df["close"].pct_change().dropna()
                        if len(returns) > 20:
                            self.seed_risk_metrics(returns)
                            break

        return self.build_compact()


# ── Decorator: ensure seed context ─────────────────────────


def require_seed_context(method_name: str = "run"):
    """Class decorator: inject seed context before agent method execution.

    Pattern: ensures any agent that makes trading decisions first
    seeds the required data. Prevents LLM hallucination of market data.
    """

    def decorator(cls):
        original_run = getattr(cls, method_name, None)
        if original_run is None:
            return cls

        @wraps(original_run)
        def wrapped_run(self, *args, **kwargs):
            if not hasattr(self, "_seed_ctx") or self._seed_ctx is None:
                self._seed_ctx = QuantSeedContext()
                self._seed_ctx.seed_all(self.get_tickers())
            return original_run(self, *args, **kwargs)

        setattr(cls, method_name, wrapped_run)
        return cls

    return decorator


# ── Demo ────────────────────────────────────────────────────


def main():
    rng = np.random.default_rng(42)

    ctx = SeedContext()

    # Seed 1: simulated market data
    ctx.seed(
        "market_prices",
        lambda: pd.DataFrame(
            {
                "close": 100 + np.cumsum(rng.normal(0.05, 1.5, 252)),
                "volume": rng.integers(1000, 10000, 252),
            },
            index=pd.date_range("2024-01-01", periods=252, freq="B"),
        ),
        source="yfinance_fetcher",
        category="market_data",
    )

    # Seed 2: factor stats
    ctx.seed(
        "factor_momentum",
        lambda: {
            "mean": 0.0012,
            "std": 0.034,
            "recent": 0.008,
            "ic": 0.045,
            "ic_ir": 0.62,
        },
        source="factor_engine",
        category="factor",
    )

    # Seed 3: risk metrics
    ctx.seed(
        "risk_metrics",
        lambda: {
            "var_95": -0.022,
            "cvar_95": -0.035,
            "max_drawdown": -0.15,
            "sharpe": 1.2,
            "sortino": 1.8,
        },
        source="risk_metrics",
        category="risk",
    )

    print(ctx.build_context(max_tokens=2000))
    print("\n--- Compact ---")
    print(ctx.build_compact())


if __name__ == "__main__":
    main()
