#!/usr/bin/env python3
"""Factor performance analysis — IC decay, turnover, quantile returns.

Uses pandas/numpy for all calculations. Integrates with the factor engine
and factor combiner for end-to-end factor evaluation."""

from datetime import datetime

import numpy as np
import pandas as pd


def rolling_ic(
    factor_df: pd.DataFrame,
    factor_cols: list[str],
    forward_returns: pd.Series,
    window: int = 21,
) -> pd.DataFrame:
    """Compute rolling Information Coefficient (Spearman rank correlation)
    between each factor and forward returns.

    Returns DataFrame with rolling IC for each factor.
    """
    results = {}
    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        ic_series = pd.Series(np.nan, index=factor_df.index)

        for i in range(window, len(factor_df)):
            f_slice = factor_df[col].iloc[i - window : i]
            r_slice = forward_returns.iloc[i - window : i]
            valid = f_slice.notna() & r_slice.notna()
            if valid.sum() < 10:
                continue
            ic_series.iloc[i] = f_slice[valid].corr(r_slice[valid], method="spearman")

        results[col] = ic_series

    return pd.DataFrame(results, index=factor_df.index)


def ic_summary(ic_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize IC statistics per factor.

    Returns DataFrame with: mean_ic, ic_ir (IC / IC_std), hit_rate (% positive IC),
    max_ic, min_ic, ic_decay (half-life of IC).
    """
    rows = []
    for col in ic_df.columns:
        ic = ic_df[col].dropna()
        if len(ic) < 10:
            continue
        mean_ic = float(ic.mean())
        std_ic = float(ic.std())
        ic_ir = mean_ic / max(std_ic, 1e-10)
        hit = float((ic > 0).mean())

        # IC decay: autocorrelation-based half-life
        decay = _estimate_decay(ic)

        rows.append(
            {
                "factor": col,
                "mean_ic": round(mean_ic, 6),
                "std_ic": round(std_ic, 6),
                "ic_ir": round(ic_ir, 4),
                "hit_rate": round(hit, 4),
                "max_ic": round(float(ic.max()), 4),
                "min_ic": round(float(ic.min()), 4),
                "ic_decay_days": round(decay, 1),
                "n_obs": len(ic),
            }
        )

    return pd.DataFrame(rows).sort_values("ic_ir", ascending=False)


def _estimate_decay(series: pd.Series, max_lag: int = 60) -> float:
    """Estimate IC half-life via autocorrelation decay."""
    s = series.dropna()
    if len(s) < max_lag:
        return float("nan")
    autos = [s.autocorr(lag=i) for i in range(1, min(max_lag, len(s) // 2))]
    for i, ac in enumerate(autos):
        if ac is not None and ac < 0.5:
            return float(i + 1)
    return float("nan")


def factor_turnover(
    factor_df: pd.DataFrame,
    factor_cols: list[str],
    window: int = 21,
) -> pd.DataFrame:
    """Compute factor turnover — how much factor decile rankings change period-to-period.

    Higher turnover = factor signals are less stable.
    """
    results = {}
    for col in factor_cols:
        if col not in factor_df.columns:
            continue
        rank = factor_df[col].rank(pct=True)
        turnover = rank.diff(window).abs().rolling(window * 2).mean()
        results[col] = turnover

    return pd.DataFrame(results, index=factor_df.index)


def turnover_summary(turnover_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize turnover per factor."""
    rows = []
    for col in turnover_df.columns:
        t = turnover_df[col].dropna()
        if len(t) < 10:
            continue
        rows.append(
            {
                "factor": col,
                "mean_turnover": round(float(t.mean()), 4),
                "max_turnover": round(float(t.max()), 4),
                "stability": round(1.0 - float(t.mean()), 4),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_turnover")


def quantile_returns(
    factor_df: pd.DataFrame,
    factor_col: str,
    returns: pd.Series,
    n_quantiles: int = 5,
) -> pd.DataFrame:
    """Compute forward returns by factor quantile.

    Returns DataFrame with cumulative return per quantile.
    """
    if factor_col not in factor_df.columns:
        return pd.DataFrame()

    combined = pd.DataFrame(
        {"factor": factor_df[factor_col], "return": returns}
    ).dropna()
    if len(combined) < n_quantiles * 5:
        return pd.DataFrame()

    combined["quantile"] = pd.qcut(
        combined["factor"], n_quantiles, labels=False, duplicates="drop"
    )
    if combined["quantile"].nunique() < 2:
        return pd.DataFrame()

    cum_returns = combined.groupby("quantile")["return"].apply(
        lambda x: (1 + x).cumprod()
    )
    return cum_returns.unstack(level=0)


def quantile_spread_summary(
    factor_df: pd.DataFrame,
    factor_cols: list[str],
    returns: pd.Series,
    top_q: int = 4,
    bottom_q: int = 0,
    n_quantiles: int = 5,
) -> pd.DataFrame:
    """Compute long-short quantile spread return for each factor.

    top_q - bottom_q spread (e.g., Q5 - Q1 return).
    """
    rows = []
    for col in factor_cols:
        combined = pd.DataFrame({"factor": factor_df[col], "return": returns}).dropna()
        if len(combined) < n_quantiles * 5:
            continue
        try:
            combined["q"] = pd.qcut(
                combined["factor"], n_quantiles, labels=False, duplicates="drop"
            )
            top = combined[combined["q"] == top_q]["return"]
            bot = combined[combined["q"] == bottom_q]["return"]
            if len(top) > 0 and len(bot) > 0:
                spread_ret = float((1 + top).prod() - (1 + bot).prod())
                rows.append(
                    {
                        "factor": col,
                        "top_quantile_return": round(float((1 + top).prod() - 1), 4),
                        "bottom_quantile_return": round(float((1 + bot).prod() - 1), 4),
                        "spread_return": round(spread_ret, 4),
                    }
                )
        except (ValueError, IndexError):
            continue

    return pd.DataFrame(rows).sort_values("spread_return", ascending=False)


def factor_correlation_heatmap(
    factor_df: pd.DataFrame,
    factor_cols: list[str],
) -> pd.DataFrame:
    """Compute factor correlation matrix for redundancy detection."""
    valid = [c for c in factor_cols if c in factor_df.columns]
    if len(valid) < 2:
        return pd.DataFrame()
    return factor_df[valid].corr(method="spearman")


def full_analysis(
    factor_df: pd.DataFrame,
    returns: pd.Series,
    factor_cols: list[str] | None = None,
    ic_window: int = 21,
    n_quantiles: int = 5,
) -> dict:
    """Run complete factor performance analysis.

    Returns dict with ic_summary, turnover_summary, quantile_spread, correlation_matrix.
    """
    if factor_cols is None:
        factor_cols = [
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
            }
        ]

    # Compute forward returns (next day)
    if isinstance(returns, pd.Series):
        fwd = returns.shift(-1)
    else:
        fwd = pd.Series(returns).shift(-1)

    ic_df = rolling_ic(factor_df, factor_cols, fwd, window=ic_window)
    ic_sum = ic_summary(ic_df)

    turnover_df = factor_turnover(factor_df, factor_cols, window=ic_window)
    to_sum = turnover_summary(turnover_df)

    q_spread = quantile_spread_summary(
        factor_df, factor_cols, returns, n_quantiles=n_quantiles
    )
    corr_matrix = factor_correlation_heatmap(factor_df, factor_cols)

    # Overall assessment
    if not ic_sum.empty:
        top_factor = ic_sum.iloc[0]["factor"]
        top_ic_ir = ic_sum.iloc[0]["ic_ir"]
        avg_hit = ic_sum["hit_rate"].mean()
    else:
        top_factor, top_ic_ir, avg_hit = "N/A", 0, 0

    return {
        "ic_summary": ic_sum,
        "turnover_summary": to_sum,
        "quantile_spread": q_spread,
        "correlation_matrix": corr_matrix,
        "assessment": {
            "top_factor": top_factor,
            "top_ic_ir": round(top_ic_ir, 4),
            "avg_hit_rate": round(avg_hit, 2),
            "n_factors_analyzed": len(ic_sum),
            "caveat": "Results based on historical data; IC decay indicates potential crowding.",
        },
    }


def report_markdown(analysis: dict) -> str:
    """Generate a markdown report from full_analysis output."""
    assess = analysis.get("assessment", {})
    lines = [
        "# Factor Performance Analysis Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Top Factor**: {assess.get('top_factor', 'N/A')} (IC IR: {assess.get('top_ic_ir', 0)})",
        f"**Avg Hit Rate**: {assess.get('avg_hit_rate', 0):.1%}",
        f"**Factors Analyzed**: {assess.get('n_factors_analyzed', 0)}",
        f"**Caveat**: {assess.get('caveat', '')}",
        "",
        "## IC Summary",
        "",
    ]

    ic = analysis.get("ic_summary")
    if ic is not None and not ic.empty:
        lines.append(
            "| Factor | Mean IC | IC IR | Hit Rate | Max IC | Min IC | Decay (days) |"
        )
        lines.append(
            "|--------|---------|-------|----------|--------|--------|-------------|"
        )
        for _, r in ic.head(15).iterrows():
            lines.append(
                f"| {r['factor']} | {r['mean_ic']:.4f} | {r['ic_ir']:.2f} | "
                f"{r['hit_rate']:.2f} | {r['max_ic']:.3f} | {r['min_ic']:.3f} | "
                f"{r['ic_decay_days']:.0f} |"
            )

    lines.append("")
    lines.append("## Quantile Spread (Top-Bottom)")
    lines.append("")
    qs = analysis.get("quantile_spread")
    if qs is not None and not qs.empty:
        lines.append("| Factor | Top Q Return | Bottom Q Return | Spread |")
        lines.append("|--------|-------------|----------------|--------|")
        for _, r in qs.head(10).iterrows():
            lines.append(
                f"| {r['factor']} | {r['top_quantile_return']:.2%} | "
                f"{r['bottom_quantile_return']:.2%} | {r['spread_return']:.2%} |"
            )

    lines.append("")
    lines.append("## Turnover Summary")
    lines.append("")
    to = analysis.get("turnover_summary")
    if to is not None and not to.empty:
        lines.append("| Factor | Mean Turnover | Stability |")
        lines.append("|--------|--------------|-----------|")
        for _, r in to.head(10).iterrows():
            lines.append(
                f"| {r['factor']} | {r['mean_turnover']:.4f} | {r['stability']:.4f} |"
            )

    lines.append("")
    lines.append("*Auto-generated by factor_analysis.py*")
    return "\n".join(lines)


def _make_demo_data(
    n: int = 504, n_factors: int = 5, seed: int = 42
) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    factor_data = {}
    for i in range(n_factors):
        factor_data[f"factor_{i}"] = rng.normal(0, 1, n)
    factor_df = pd.DataFrame(factor_data)
    returns = pd.Series(rng.normal(0.0005, 0.015, n))
    return factor_df, returns


def main():
    factor_df, returns = _make_demo_data(504, 5, seed=7)
    analysis = full_analysis(factor_df, returns)
    report = report_markdown(analysis)
    print(report[:1500])


if __name__ == "__main__":
    main()
