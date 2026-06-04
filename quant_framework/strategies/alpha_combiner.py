#!/usr/bin/env python3
"""Alpha signal combiner — sophisticated multi-signal blending.

Supports IC-weighted, IC-IR-weighted, Bayesian shrinkage, decay-adjusted,
regime-aware, and turnover-constrained alpha combination.

Integrates with qlib_factor_engine (factors), factor_analysis (IC metrics),
and regime_detector (market regimes)."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from scipy.stats import spearmanr


# ── Helpers ─────────────────────────────────────────────────


def _rolling_spearman(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Compute rolling Spearman rank correlation between two series."""
    combined = pd.DataFrame({"a": a, "b": b}).dropna()
    result = pd.Series(np.nan, index=a.index)
    if len(combined) < window:
        return result
    combined["_r"] = np.nan
    for i in range(window - 1, len(combined)):
        wa = combined["a"].iloc[i - window + 1 : i + 1]
        wb = combined["b"].iloc[i - window + 1 : i + 1]
        if wa.nunique() < 2 or wb.nunique() < 2:
            continue
        combined.iloc[i, combined.columns.get_loc("_r")] = spearmanr(wa, wb)[0]
    aligned = combined["_r"].dropna()
    result.loc[aligned.index] = aligned
    return result


# ── Core weighting methods ─────────────────────────────────


def ic_weighted(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    forward_returns: pd.Series,
    window: int = 252,
    floor: float = 0.1,
) -> pd.DataFrame:
    """Weight factors by trailing Information Coefficient magnitude.

    weight_i = max(|IC_i|, floor * mean(|IC|)) / sum(max(|IC|, floor))

    Parameters
    ----------
    factor_df: DataFrame with factor columns
    factor_cols: factor column names to combine
    forward_returns: forward-looking returns for IC estimation
    window: trailing window for IC estimation
    floor: minimum relative weight floor

    Returns factor_df with added 'combined_score' column.
    """
    result = factor_df.copy()
    ic_series = {}

    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        fwd_aligned = pd.DataFrame(
            {
                "f": factor_df[col],
                "r": forward_returns,
            }
        ).dropna()

        if len(fwd_aligned) < 20:
            ic_series[col] = pd.Series(0.0, index=factor_df.index)
            continue

        ic_series[col] = (
            _rolling_spearman(fwd_aligned["f"], fwd_aligned["r"], window)
            .reindex(factor_df.index)
            .fillna(0.0)
        )

    if not ic_series:
        return result

    ic_df = pd.DataFrame(ic_series)
    abs_ic = ic_df.abs()
    mean_abs = abs_ic.mean(axis=1).replace(0, 1e-10)
    floor_vals = mean_abs * floor

    # Apply floor — clip each column individually
    floored = pd.DataFrame(index=abs_ic.index)
    for c in abs_ic.columns:
        floored[c] = abs_ic[c].clip(lower=floor_vals)
    weights = floored.div(floored.sum(axis=1).replace(0, 1), axis=0)

    result["combined_score"] = 0.0
    for col in factor_cols:
        if col in weights.columns:
            result["combined_score"] += factor_df[col].fillna(0) * weights[col]

    return result


def ic_ir_weighted(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    forward_returns: pd.Series,
    estimation_window: int = 504,
    rolling_window: int = 63,
) -> pd.DataFrame:
    """Weight factors by IC/IR (mean_ic / std_ic) over the estimation window.

    More stable than pure IC-weighting since it accounts for IC consistency.
    """
    result = factor_df.copy()
    icir_weights = {}

    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        fwd_aligned = pd.DataFrame(
            {
                "f": factor_df[col],
                "r": forward_returns,
            }
        ).dropna()

        if len(fwd_aligned) < 20:
            continue

        rolling_ic = _rolling_spearman(
            fwd_aligned["f"], fwd_aligned["r"], rolling_window
        )
        expanding_mean = rolling_ic.expanding(min_periods=60).mean()
        expanding_std = rolling_ic.expanding(min_periods=60).std().replace(0, 1e-10)
        icir = (expanding_mean / expanding_std).fillna(0)
        icir_weights[col] = icir.reindex(factor_df.index).fillna(0.0)

    if not icir_weights:
        return result

    wdf = pd.DataFrame(icir_weights)
    wdf = wdf.clip(lower=0)
    weights = wdf.div(wdf.sum(axis=1).replace(0, 1), axis=0)

    result["combined_score"] = 0.0
    for col in factor_cols:
        if col in weights.columns:
            result["combined_score"] += factor_df[col].fillna(0) * weights[col]

    return result


def bayesian_shrinkage_weights(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    forward_returns: pd.Series,
    shrinkage: float = 0.3,
    window: int = 252,
) -> pd.DataFrame:
    """Bayesian shrinkage: shrink IC estimates toward zero (prior = no alpha).

    shrunk_IC = (1 - shrinkage) * IC + shrinkage * 0
    weight_i = |shrunk_IC_i| / sum(|shrunk_IC|)

    Higher shrinkage → more conservative, closer to equal-weight.
    """
    result = factor_df.copy()
    ic_dict = {}

    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        fwd_aligned = pd.DataFrame(
            {
                "f": factor_df[col],
                "r": forward_returns,
            }
        ).dropna()

        if len(fwd_aligned) < 20:
            continue

        ic_dict[col] = (
            _rolling_spearman(fwd_aligned["f"], fwd_aligned["r"], window)
            .reindex(factor_df.index)
            .fillna(0.0)
        )

    if not ic_dict:
        return result

    ic_df = pd.DataFrame(ic_dict)
    # Shrink toward zero
    shrunk_ic = ic_df * (1 - shrinkage)
    abs_ic = shrunk_ic.abs()
    weights = abs_ic.div(abs_ic.sum(axis=1).replace(0, 1), axis=0)

    result["combined_score"] = 0.0
    for col in factor_cols:
        if col in weights.columns:
            result["combined_score"] += factor_df[col].fillna(0) * weights[col]

    return result


# ── Signal decay adjustment ─────────────────────────────────


def decay_adjusted_scores(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    decay_half_lives: Dict[str, float],
) -> pd.DataFrame:
    """Adjust factor scores by estimated decay half-life.

    Factors with shorter half-life get their scores decayed more rapidly
    when the signal is stale (last observation carries less weight).

    This is a cross-sectional adjustment: each factor's score is scaled by
    exp(-ln(2) / half_life) relative to a daily rebalancing baseline.
    """
    result = factor_df.copy()
    for col in factor_cols:
        if col not in factor_df.columns or col not in decay_half_lives:
            continue
        half_life = max(decay_half_lives[col], 1)
        decay_factor = np.exp(-np.log(2) / half_life)
        if col + "_raw" not in result.columns:
            result[col + "_raw"] = result[col].copy()
        result[col + "_decay"] = result[col] * decay_factor
    return result


# ── Turnover-constrained blending ───────────────────────────


def turnover_constrained_combine(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    ic_summary_df: pd.DataFrame,
    max_turnover: float = 0.5,
    prev_weights: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Combine factors with a turnover constraint on resulting signals.

    Limits how much combined scores can change period-over-period.
    Uses a simple exponential blend: new = (1 - lambda) * target + lambda * old.

    Parameters
    ----------
    max_turnover: maximum allowed signal change (0-1, lower = less turnover)
    prev_weights: previous combined_score (for turnover calculation)
    """
    result = factor_df.copy()

    # Build target weights from IC summary
    ic_map = {}
    if not ic_summary_df.empty and "factor" in ic_summary_df.columns:
        for _, row in ic_summary_df.iterrows():
            ic_map[row["factor"]] = abs(row.get("mean_ic", 0))

    valid_cols = [c for c in factor_cols if c in factor_df.columns]
    if ic_map:
        total = sum(ic_map.get(c, 1.0 / len(valid_cols)) for c in valid_cols) or 1
        target_weights = {c: ic_map.get(c, 0.1) / total for c in valid_cols}
    else:
        target_weights = {c: 1.0 / len(valid_cols) for c in valid_cols}

    target_score = sum(
        factor_df[c].fillna(0) * target_weights.get(c, 0) for c in valid_cols
    )

    if prev_weights is not None and max_turnover < 1.0:
        blend = np.clip(1 - max_turnover, 0, 1)
        result["combined_score"] = (
            blend * prev_weights.fillna(0) + (1 - blend) * target_score
        )
    else:
        result["combined_score"] = target_score

    return result


# ── Regime-aware blending ───────────────────────────────────


def regime_aware_combine(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    regime_labels: pd.Series,
    regime_weights: Dict[int, Dict[str, float]],
    default_weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Combine factors with different weights per market regime.

    Parameters
    ----------
    regime_labels: Series of regime integer labels per date
    regime_weights: dict of regime_id → {factor_name: weight}
    default_weights: fallback if regime not in regime_weights

    Returns factor_df with 'combined_score' column.
    """
    result = factor_df.copy()
    result["combined_score"] = 0.0

    if default_weights is None:
        valid_cols = [c for c in factor_cols if c in factor_df.columns]
        default_weights = {c: 1.0 / max(len(valid_cols), 1) for c in valid_cols}

    regimes_present = regime_labels.dropna().unique()
    for regime_id in regimes_present:
        mask = regime_labels == regime_id
        if not mask.any():
            continue

        w = regime_weights.get(int(regime_id), default_weights)
        idx = mask[mask].index.intersection(result.index)

        score = 0.0
        for col in factor_cols:
            if col in factor_df.columns and col in w:
                score += factor_df.loc[idx, col].fillna(0) * w[col]

        result.loc[idx, "combined_score"] = score

    # Fill any remaining NaN with default
    nan_mask = result["combined_score"].isna()
    if nan_mask.any():
        for col in factor_cols:
            if col in factor_df.columns and col in default_weights:
                result.loc[nan_mask, "combined_score"] += (
                    factor_df.loc[nan_mask, col].fillna(0) * default_weights[col]
                )

    return result


# ── Unified pipeline ────────────────────────────────────────


@dataclass
class CombineConfig:
    method: str = (
        "ic_weighted"  # ic_weighted | ic_ir | bayesian | equal | regime | turnover
    )
    factor_cols: List[str] = field(default_factory=list)
    window: int = 252
    shrinkage: float = 0.3
    max_turnover: float = 0.5
    floor: float = 0.1
    regime_weights: Optional[Dict[int, Dict[str, float]]] = None
    decay_half_lives: Optional[Dict[str, float]] = None


def combine_alphas(
    factor_df: pd.DataFrame,
    forward_returns: pd.Series,
    config: Optional[CombineConfig] = None,
    regime_labels: Optional[pd.Series] = None,
    ic_summary_df: Optional[pd.DataFrame] = None,
    prev_scores: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Unified alpha combination pipeline.

    Parameters
    ----------
    factor_df: DataFrame with factor columns
    forward_returns: forward-looking returns
    config: CombineConfig (defaults to ic_weighted)
    regime_labels: required for regime_aware method
    ic_summary_df: required for turnover_constrained method
    prev_scores: optional previous combined_score for turnover blending

    Returns factor_df with 'combined_score' column.
    """
    if config is None:
        config = CombineConfig()

    factor_cols = config.factor_cols or [
        c
        for c in factor_df.columns
        if c
        not in {
            "date",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "industry",
            "combined_score",
            "signal",
        }
    ]

    if not factor_cols:
        return factor_df

    # Apply decay adjustment if configured
    if config.decay_half_lives:
        factor_df = decay_adjusted_scores(
            factor_df, factor_cols, config.decay_half_lives
        )
        decay_cols = [
            c + "_decay" for c in factor_cols if c + "_decay" in factor_df.columns
        ]
        if decay_cols:
            factor_cols = decay_cols

    method = config.method

    if method == "equal":
        result = factor_df.copy()
        valid = [c for c in factor_cols if c in factor_df.columns]
        if valid:
            result["combined_score"] = factor_df[valid].mean(axis=1)
        return result

    elif method == "ic_weighted":
        return ic_weighted(
            factor_df,
            factor_cols,
            forward_returns,
            window=config.window,
            floor=config.floor,
        )

    elif method == "ic_ir":
        return ic_ir_weighted(
            factor_df, factor_cols, forward_returns, estimation_window=config.window
        )

    elif method == "bayesian":
        return bayesian_shrinkage_weights(
            factor_df,
            factor_cols,
            forward_returns,
            shrinkage=config.shrinkage,
            window=config.window,
        )

    elif method == "turnover":
        if ic_summary_df is None:
            return ic_weighted(factor_df, factor_cols, forward_returns)
        return turnover_constrained_combine(
            factor_df,
            factor_cols,
            ic_summary_df,
            max_turnover=config.max_turnover,
            prev_weights=prev_scores,
        )

    elif method == "regime":
        if regime_labels is None:
            return ic_weighted(factor_df, factor_cols, forward_returns)
        return regime_aware_combine(
            factor_df, factor_cols, regime_labels, config.regime_weights or {}
        )

    else:
        return ic_weighted(factor_df, factor_cols, forward_returns)


# ── Evaluation helpers ──────────────────────────────────────


def estimate_ic_weights(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    forward_returns: pd.Series,
    window: int = 252,
) -> Dict[str, float]:
    """Estimate static IC-based weights for a snapshot (e.g., end-of-period)."""
    weights = {}
    valid = []
    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        fwd = pd.DataFrame({"f": factor_df[col], "r": forward_returns}).dropna()
        if len(fwd) < 20:
            continue
        ic = fwd["f"].corr(fwd["r"], method="spearman")
        weights[col] = abs(ic)
        valid.append(col)

    total = sum(weights.values()) or 1.0
    return {k: round(v / total, 6) for k, v in weights.items()}


def evaluate_combination(
    combined_score: pd.Series,
    forward_returns: pd.Series,
    n_quantiles: int = 5,
) -> Dict:
    """Evaluate a combined alpha score: quantile spread, IC, hit rate."""
    aligned = pd.DataFrame(
        {
            "score": combined_score,
            "fwd": forward_returns,
        }
    ).dropna()

    if len(aligned) < n_quantiles * 10:
        return {"error": "Insufficient data"}

    aligned["quantile"] = pd.qcut(aligned["score"], n_quantiles, labels=False)
    top = aligned[aligned["quantile"] == n_quantiles - 1]["fwd"].mean()
    bottom = aligned[aligned["quantile"] == 0]["fwd"].mean()
    spread = float(top - bottom)
    spread_t = float(
        (top - bottom)
        / max(aligned["fwd"].std() / np.sqrt(len(aligned) / n_quantiles), 1e-10)
    )

    ic = float(aligned["score"].corr(aligned["fwd"], method="spearman"))
    hit_rate = float(
        (
            (aligned["score"] > 0) & (aligned["fwd"] > 0)
            | (aligned["score"] < 0) & (aligned["fwd"] < 0)
        ).mean()
    )

    return {
        "ic": round(ic, 6),
        "hit_rate": round(hit_rate, 4),
        "quantile_spread": round(spread, 6),
        "spread_t_stat": round(spread_t, 3),
        "top_quantile_return": round(float(top), 6),
        "bottom_quantile_return": round(float(bottom), 6),
        "n_observations": len(aligned),
    }


def report_markdown(config: CombineConfig, evaluation: Dict) -> str:
    """Generate markdown report for the alpha combination."""
    lines = [
        "# Alpha Combination Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Method**: {config.method}  ",
        f"**Window**: {config.window} days  ",
        f"**N Factors**: {len(config.factor_cols)}  ",
        "",
        "## Combination Evaluation",
        "",
    ]

    if "error" in evaluation:
        lines.append(f"**Error**: {evaluation['error']}")
        return "\n".join(lines)

    lines += [
        f"**IC**: {evaluation.get('ic', 0):.4f}  ",
        f"**Hit Rate**: {evaluation.get('hit_rate', 0):.2%}  ",
        f"**Quantile Spread**: {evaluation.get('quantile_spread', 0):.4%}  ",
        f"**Spread T-Stat**: {evaluation.get('spread_t_stat', 0):.2f}  ",
        f"**N**: {evaluation.get('n_observations', 0)}  ",
        "",
        f"**Top Quantile Return**: {evaluation.get('top_quantile_return', 0):.4%}  ",
        f"**Bottom Quantile Return**: {evaluation.get('bottom_quantile_return', 0):.4%}  ",
        "",
    ]

    lines.append("*Auto-generated by alpha_combiner.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────


def _make_demo_data(
    n: int = 252, n_factors: int = 5, n_tickers: int = 10, seed: int = 42
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    tickers = [f"T{i}" for i in range(n_tickers)]

    rows = []
    for date in dates:
        for ticker in tickers:
            rows.append({"date": date, "ticker": ticker})

    df = pd.DataFrame(rows)

    # Create factors with varying predictive power
    for i in range(n_factors):
        # Higher i → stronger signal
        _signal_strength = 0.01 + i * 0.02
        df[f"factor_{i}"] = rng.normal(0, 1, len(df))

    # Forward returns: some dependence on factors
    noise = rng.normal(0, 0.02, len(df))
    df["close"] = 100.0  # placeholder
    forward_returns = (
        df["factor_0"] * 0.01
        + df["factor_1"] * 0.02
        + df["factor_2"] * 0.03
        + df["factor_3"] * 0.04
        + df["factor_4"] * 0.05
        + noise
    )

    # Regime labels for regime-aware testing
    regime_labels = pd.Series(
        np.where(np.arange(n) % 100 < 60, 0, 1),
        index=dates,
    )

    return df, pd.Series(forward_returns.values, index=df.index), regime_labels


def main():
    df, forward_returns, regime_labels = _make_demo_data(252, 5, 10, seed=7)
    factor_cols = [f"factor_{i}" for i in range(5)]

    # IC-weighted
    cfg = CombineConfig(method="ic_weighted", factor_cols=factor_cols, window=63)
    result = combine_alphas(df, forward_returns, cfg)
    eval_ = evaluate_combination(result["combined_score"], forward_returns)
    print(report_markdown(cfg, eval_))

    # Compare methods
    methods = ["equal", "ic_weighted", "ic_ir", "bayesian"]
    print("\n## Method Comparison\n")
    print("| Method | IC | Hit Rate | Spread | T-Stat |")
    print("|--------|-----|----------|--------|--------|")
    for method in methods:
        cfg2 = CombineConfig(method=method, factor_cols=factor_cols, window=63)
        r2 = combine_alphas(df, forward_returns, cfg2)
        ev = evaluate_combination(r2["combined_score"], forward_returns)
        if "error" not in ev:
            print(
                f"| {method} | {ev['ic']:.4f} | {ev['hit_rate']:.2%} | "
                f"{ev['quantile_spread']:.4%} | {ev['spread_t_stat']:.2f} |"
            )

    # Estimate static weights
    w = estimate_ic_weights(df, factor_cols, forward_returns)
    print(f"\nStatic IC weights: {w}")


if __name__ == "__main__":
    main()
