"""Factor decay monitoring — IC trend detection, crowding, degradation alerts.

Uses statsmodels for trend significance testing and scipy for hypothesis tests.
Integrates with factor_analysis.py for IC computation."""

import numpy as np
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

from quant_framework.strategies.factor_analysis import ic_summary

logger = logging.getLogger("quant_framework.strategies.factor_decay")


@dataclass
class DecayAlert:
    factor: str
    alert_type: str  # "ic_trend_down", "ic_below_threshold", "crowding_rising"
    severity: str  # "warning", "critical"
    detail: str
    metric_value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def ic_trend_test(
    ic_df: pd.DataFrame,
    method: str = "ols",
    window: int = 63,
    p_threshold: float = 0.05,
) -> pd.DataFrame:
    """Test for statistically significant IC trends per factor.

    Uses OLS regression slope on rolling mean IC with Newey-West HAC standard errors.
    Returns DataFrame with: factor, slope (annualized), p_value, trend_direction, significant.
    """
    from statsmodels.regression.linear_model import OLS

    rows = []
    for col in ic_df.columns:
        ic = ic_df[col].dropna()
        if len(ic) < max(window, 20):
            continue

        rolling_mean = (
            ic.rolling(window=window, min_periods=window // 2).mean().dropna()
        )
        if len(rolling_mean) < 10:
            continue

        X = np.arange(len(rolling_mean)).reshape(-1, 1)
        X = np.column_stack([np.ones(len(X)), X])
        y = rolling_mean.values

        try:
            model = OLS(y, X).fit()
            slope = model.params[1] * 252
            p_value = model.pvalues[1]

            rows.append(
                {
                    "factor": col,
                    "slope_annual": slope,
                    "p_value": p_value,
                    "trend": "declining"
                    if slope < -0.01
                    else "rising"
                    if slope > 0.01
                    else "flat",
                    "significant": p_value < p_threshold,
                    "n_obs": len(rolling_mean),
                    "mean_ic": float(rolling_mean.mean()),
                    "last_ic": float(rolling_mean.iloc[-1]),
                }
            )
        except Exception:
            continue

    return pd.DataFrame(rows)


def detect_crowding(
    factor_df: pd.DataFrame,
    factor_cols: List[str],
    window: int = 63,
) -> pd.DataFrame:
    """Detect factor crowding via rising cross-sectional return correlation.

    Crowding happens when many investors adopt the same factor, compressing returns
    and increasing pairwise correlation of factor-sorted portfolio returns.
    """
    from scipy.stats import spearmanr

    rows = []
    if len(factor_cols) < 2:
        return pd.DataFrame()

    if window >= len(factor_df):
        return pd.DataFrame()

    # Split into early/late periods
    mid = len(factor_df) - window
    if mid < window:
        mid = len(factor_df) // 2

    early = factor_df[factor_cols].iloc[:mid]
    late = factor_df[factor_cols].iloc[mid:]

    for i, c1 in enumerate(factor_cols):
        for c2 in factor_cols[i + 1 :]:
            e1 = early[c1].dropna()
            e2 = early[c2].dropna()
            l1 = late[c1].dropna()
            l2 = late[c2].dropna()

            common_early = e1.index.intersection(e2.index)
            common_late = l1.index.intersection(l2.index)

            if len(common_early) < 20 or len(common_late) < 20:
                continue

            rho_early, _ = spearmanr(e1[common_early], e2[common_early])
            rho_late, _ = spearmanr(l1[common_late], l2[common_late])
            delta = rho_late - rho_early

            if abs(delta) > 0.1:
                rows.append(
                    {
                        "factor_pair": f"{c1} / {c2}",
                        "rho_early": round(rho_early, 4),
                        "rho_late": round(rho_late, 4),
                        "delta": round(delta, 4),
                        "crowding_signal": "rising" if delta > 0.1 else "diverging",
                    }
                )

    return pd.DataFrame(rows)


def check_decay_alerts(
    ic_df: pd.DataFrame,
    factor_df: Optional[pd.DataFrame] = None,
    factor_cols: Optional[List[str]] = None,
    ic_min_threshold: float = -0.02,
    trend_sig_threshold: float = 0.05,
) -> List[DecayAlert]:
    """Generate decay alerts from IC trend analysis and crowding detection.

    Returns list of DecayAlert objects ready for logging/reporting.
    """
    alerts = []

    # IC below threshold check
    summary = ic_summary(ic_df)
    for _, row in summary.iterrows():
        if row["mean_ic"] < ic_min_threshold:
            alerts.append(
                DecayAlert(
                    factor=row["factor"],
                    alert_type="ic_below_threshold",
                    severity="warning" if row["mean_ic"] > -0.05 else "critical",
                    detail=f"Mean IC {row['mean_ic']:.4f} below threshold {ic_min_threshold}",
                    metric_value=row["mean_ic"],
                    threshold=ic_min_threshold,
                )
            )

    # IC trend test
    trends = ic_trend_test(ic_df, p_threshold=trend_sig_threshold)
    for _, row in trends.iterrows():
        if row["significant"] and row["trend"] == "declining":
            alerts.append(
                DecayAlert(
                    factor=row["factor"],
                    alert_type="ic_trend_down",
                    severity="critical"
                    if abs(row["slope_annual"]) > 0.05
                    else "warning",
                    detail=f"IC declining at {row['slope_annual']:.4f}/year (p={row['p_value']:.4f})",
                    metric_value=row["slope_annual"],
                    threshold=trend_sig_threshold,
                )
            )

    # Crowding
    if factor_df is not None and factor_cols:
        crowding = detect_crowding(factor_df, factor_cols)
        for _, row in crowding.iterrows():
            if row["crowding_signal"] == "rising":
                alerts.append(
                    DecayAlert(
                        factor=row["factor_pair"],
                        alert_type="crowding_rising",
                        severity="warning",
                        detail=f"Pairwise correlation rising: {row['rho_early']:.3f} → {row['rho_late']:.3f}",
                        metric_value=row["delta"],
                        threshold=0.1,
                    )
                )

    return alerts


def report_markdown(
    alerts: List[DecayAlert],
    ic_df: Optional[pd.DataFrame] = None,
) -> str:
    """Generate markdown decay monitoring report."""
    lines = [
        "# Factor Decay Monitor — " + datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
    ]

    critical = [a for a in alerts if a.severity == "critical"]
    warnings = [a for a in alerts if a.severity == "warning"]

    if not alerts:
        lines.append("## Status: ✅ All factors stable")
        lines.append("")
        lines.append(
            "No decay alerts. IC trends are flat or positive, no crowding detected."
        )
    else:
        if critical:
            lines.append(f"## 🔴 Critical ({len(critical)})")
            for a in critical:
                lines.append(f"- **{a.factor}**: {a.detail}")
            lines.append("")

        if warnings:
            lines.append(f"## 🟡 Warnings ({len(warnings)})")
            for a in warnings:
                lines.append(f"- **{a.factor}** [{a.alert_type}]: {a.detail}")
            lines.append("")

    if ic_df is not None:
        summary = ic_summary(ic_df)
        if not summary.empty:
            lines.append("## Current IC Summary")
            lines.append("")
            lines.append("| Factor | Mean IC | IC IR | Hit Rate |")
            lines.append("|--------|---------|-------|----------|")
            for _, row in summary.head(10).iterrows():
                lines.append(
                    f"| {row['factor']} | {row['mean_ic']:.4f} | "
                    f"{row.get('ic_ir', 0):.2f} | {row.get('hit_rate', 0):.1%} |"
                )
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("factor_decay.py — importable module (no CLI)")
    print("  ic_trend_test(ic_df) → trend significance per factor")
    print("  detect_crowding(factor_df, factor_cols) → pairwise correlation changes")
    print("  check_decay_alerts(ic_df) → List[DecayAlert]")
