#!/usr/bin/env python3
"""Data quality monitoring — automated checks for quant workflows.

Checks: NaN ratio, data freshness, lookahead bias, outlier detection, completeness.
Uses pandas/sklearn for statistical checks — no hand-rolled detection logic."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class QualityConfig:
    max_nan_ratio: float = 0.3
    max_staleness_days: int = 5
    outlier_z_threshold: float = 5.0
    min_rows_per_ticker: int = 20
    lookahead_window: int = 21  # check if any feature correlates with future returns


# ── 1. NaN Ratio Check ────────────────────────────────────

def check_nan_ratio(
    df: pd.DataFrame,
    max_nan_ratio: float = 0.3,
    group_col: Optional[str] = "ticker",
) -> Dict:
    """Check NaN ratio per column and per ticker.

    Returns dict with per-column NaN ratios and flag for excessive NaN.
    """
    if df.empty:
        return {"error": "Empty DataFrame"}

    # Per-column NaN ratio
    col_nan = df.isna().mean().sort_values(ascending=False)
    bad_cols = col_nan[col_nan > max_nan_ratio]
    ok_cols = col_nan[col_nan <= max_nan_ratio]

    # Per-ticker check
    ticker_nan = {}
    if group_col and group_col in df.columns:
        for ticker, grp in df.groupby(group_col):
            ratio = grp.isna().mean().mean()
            if ratio > max_nan_ratio:
                ticker_nan[ticker] = round(float(ratio), 4)

    return {
        "total_nan_ratio": round(float(df.isna().mean().mean()), 4),
        "n_bad_columns": len(bad_cols),
        "bad_columns": {k: round(float(v), 4) for k, v in bad_cols.items()},
        "ok_columns": len(ok_cols),
        "n_bad_tickers": len(ticker_nan),
        "bad_tickers": ticker_nan,
        "passed": len(bad_cols) == 0 and len(ticker_nan) == 0,
    }


# ── 2. Data Freshness Check ───────────────────────────────

def check_freshness(
    df: pd.DataFrame,
    date_col: str = "date",
    max_staleness_days: int = 5,
) -> Dict:
    """Check if data is recent enough for trading decisions.

    Returns dict with last date, staleness days, and flag.
    """
    if df.empty or date_col not in df.columns:
        return {"error": "No date column found"}

    dates = pd.to_datetime(df[date_col])
    last_date = dates.max()
    today = pd.Timestamp.now().normalize()
    staleness = (today - last_date.normalize()).days

    return {
        "last_date": last_date.strftime("%Y-%m-%d"),
        "staleness_days": staleness,
        "stale": staleness > max_staleness_days,
        "passed": staleness <= max_staleness_days,
        "n_unique_dates": dates.nunique(),
        "date_range_start": dates.min().strftime("%Y-%m-%d"),
    }


# ── 3. Lookahead Bias Detection ───────────────────────────

def check_lookahead_bias(
    df: pd.DataFrame,
    factor_cols: List[str],
    forward_return_col: str = "forward_return",
    window: int = 21,
    group_col: Optional[str] = "ticker",
) -> Dict:
    """Detect potential lookahead bias.

    For each factor, compute contemporaneous correlation with forward returns.
    If correlation is suspiciously high (|IC| > 0.3), the factor may contain
    future information (lookahead bias).

    Uses scipy.stats.spearmanr for robust correlation.
    """
    from scipy.stats import spearmanr

    if df.empty:
        return {"error": "Empty DataFrame"}

    valid_cols = [c for c in factor_cols if c in df.columns]
    if not valid_cols:
        return {"error": "No valid factor columns"}

    if forward_return_col not in df.columns:
        return {"error": f"'{forward_return_col}' column not found"}

    suspicious = {}
    clean = df[valid_cols + [forward_return_col]].dropna()
    if len(clean) < 20:
        return {"error": "Insufficient clean data"}

    for col in valid_cols:
        ic, pval = spearmanr(clean[col], clean[forward_return_col])
        if abs(ic) > 0.3:
            suspicious[col] = {"ic": round(float(ic), 4), "p_value": round(float(pval), 6)}

    return {
        "n_factors_checked": len(valid_cols),
        "n_suspicious": len(suspicious),
        "suspicious_factors": suspicious,
        "threshold": 0.3,
        "passed": len(suspicious) == 0,
        "note": "High |IC| may indicate lookahead bias or genuine predictive power. Investigate suspicious factors."
    }


# ── 4. Outlier Detection ──────────────────────────────────

def check_outliers(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    z_threshold: float = 5.0,
) -> Dict:
    """Detect outlier values using Z-score method.

    Uses sklearn.preprocessing.StandardScaler for standardization.
    """
    if df.empty:
        return {"error": "Empty DataFrame"}

    numeric = df.select_dtypes(include=[np.number])
    if columns:
        numeric = numeric[[c for c in columns if c in numeric.columns]]
    if numeric.empty:
        return {"error": "No numeric columns"}

    from sklearn.preprocessing import StandardScaler

    clean = numeric.dropna()
    if len(clean) < 10:
        return {"error": "Insufficient data"}

    scaler = StandardScaler()
    z_scores = pd.DataFrame(
        scaler.fit_transform(clean),
        index=clean.index,
        columns=clean.columns,
    )

    outlier_counts = (z_scores.abs() > z_threshold).sum()
    bad_cols = outlier_counts[outlier_counts > 0]
    total_outliers = int(outlier_counts.sum())

    return {
        "n_rows": len(clean),
        "n_cols": len(clean.columns),
        "total_outliers": total_outliers,
        "outlier_ratio": round(float(total_outliers / (len(clean) * len(clean.columns))), 6),
        "n_bad_columns": len(bad_cols),
        "bad_columns": {k: int(v) for k, v in bad_cols.items()},
        "z_threshold": z_threshold,
        "passed": total_outliers < len(clean) * 0.01,  # <1% outliers
    }


# ── 5. Data Completeness ──────────────────────────────────

def check_completeness(
    df: pd.DataFrame,
    expected_tickers: Optional[List[str]] = None,
    ticker_col: str = "ticker",
    date_col: str = "date",
    min_rows_per_ticker: int = 20,
) -> Dict:
    """Check data completeness: rows per ticker, date coverage, gaps."""
    if df.empty:
        return {"error": "Empty DataFrame"}

    results = {}

    # Rows per ticker
    if ticker_col in df.columns:
        counts = df.groupby(ticker_col).size()
        thin = counts[counts < min_rows_per_ticker]
        results["n_tickers"] = len(counts)
        results["n_thin_tickers"] = len(thin)
        results["thin_tickers"] = thin.to_dict() if len(thin) > 0 else {}
        results["avg_rows_per_ticker"] = round(float(counts.mean()), 1)
        results["min_rows"] = int(counts.min())

    # Missing tickers
    if expected_tickers and ticker_col in df.columns:
        present = set(df[ticker_col].unique())
        missing = set(expected_tickers) - present
        results["n_expected"] = len(expected_tickers)
        results["n_missing"] = len(missing)
        results["missing_tickers"] = sorted(missing)[:10]

    # Date gaps
    if date_col in df.columns:
        if ticker_col in df.columns:
            # Per ticker: check for gaps > 5 trading days
            gap_tickers = {}
            for t, grp in df.groupby(ticker_col):
                d = sorted(pd.to_datetime(grp[date_col]).unique())
                if len(d) > 1:
                    gaps = [(d[i + 1] - d[i]).days for i in range(len(d) - 1)]
                    max_gap = max(gaps)
                    if max_gap > 10:
                        gap_tickers[t] = max_gap
            results["n_gap_tickers"] = len(gap_tickers)
            results["max_gaps"] = dict(sorted(gap_tickers.items(), key=lambda x: -x[1])[:5])

    results["passed"] = (results.get("n_thin_tickers", 0) == 0 and
                         results.get("n_missing", 0) == 0 and
                         results.get("n_gap_tickers", 0) == 0)

    return results


# ── 6. Full Pipeline ──────────────────────────────────────

def run_quality_checks(
    df: pd.DataFrame,
    factor_cols: Optional[List[str]] = None,
    expected_tickers: Optional[List[str]] = None,
    forward_return_col: str = "forward_return",
    group_col: str = "ticker",
    date_col: str = "date",
    config: Optional[QualityConfig] = None,
) -> Dict:
    """Run all data quality checks and return comprehensive report.

    Returns dict with individual check results and overall pass/fail summary.
    """
    if config is None:
        config = QualityConfig()

    nan_check = check_nan_ratio(df, config.max_nan_ratio, group_col)
    freshness = check_freshness(df, date_col, config.max_staleness_days)
    outliers = check_outliers(df, factor_cols, config.outlier_z_threshold)
    completeness = check_completeness(df, expected_tickers, group_col, date_col,
                                      config.min_rows_per_ticker)

    # Lookahead check
    lookahead = {}
    if factor_cols and forward_return_col in df.columns:
        lookahead = check_lookahead_bias(df, factor_cols, forward_return_col,
                                         config.lookahead_window, group_col)

    # Overall status
    checks = {
        "nan": nan_check.get("passed", False),
        "freshness": freshness.get("passed", False),
        "outliers": outliers.get("passed", False),
        "completeness": completeness.get("passed", False),
        "lookahead": lookahead.get("passed", True),
    }
    all_pass = all(checks.values())

    return {
        "passed": all_pass,
        "check_results": checks,
        "nan_check": nan_check,
        "freshness": freshness,
        "outlier_check": outliers,
        "completeness": completeness,
        "lookahead_check": lookahead,
        "n_checks_passed": sum(checks.values()),
        "n_checks_total": len(checks),
    }


# ── Markdown Report ───────────────────────────────────────

def quality_report_markdown(result: Dict) -> str:
    """Generate markdown data quality report."""
    lines = [
        "# Data Quality Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Overall**: {'PASS PASSED' if result['passed'] else 'FAIL FAILED'} "
        f"({result['n_checks_passed']}/{result['n_checks_total']} checks)",
        "",
    ]

    # NaN
    nc = result.get("nan_check", {})
    if "error" not in nc:
        lines += [
            "## NaN Ratio Check",
            f"**Total NaN**: {nc.get('total_nan_ratio', 0):.2%} | "
            f"**Bad Columns**: {nc.get('n_bad_columns', 0)} | "
            f"**Bad Tickers**: {nc.get('n_bad_tickers', 0)}",
            f"**Status**: {'PASS' if nc.get('passed') else 'FAIL'}",
            "",
        ]

    # Freshness
    fr = result.get("freshness", {})
    if "error" not in fr:
        lines += [
            "## Data Freshness",
            f"**Last Date**: {fr.get('last_date', 'N/A')} | "
            f"**Staleness**: {fr.get('staleness_days', 0)} days | "
            f"**Date Range**: {fr.get('date_range_start', '')} → {fr.get('last_date', '')}",
            f"**Status**: {'PASS' if fr.get('passed') else 'FAIL'}",
            "",
        ]

    # Outliers
    oc = result.get("outlier_check", {})
    if "error" not in oc:
        lines += [
            "## Outlier Detection",
            f"**Total Outliers**: {oc.get('total_outliers', 0)} / "
            f"{oc.get('n_rows', 0) * oc.get('n_cols', 1)} cells "
            f"({oc.get('outlier_ratio', 0):.4%}) | "
            f"**Z Threshold**: {oc.get('z_threshold', 5)}",
            f"**Status**: {'PASS' if oc.get('passed') else 'FAIL'}",
            "",
        ]

    # Completeness
    cp = result.get("completeness", {})
    if "error" not in cp:
        lines += [
            "## Completeness",
            f"**Tickers**: {cp.get('n_tickers', 0)} | "
            f"**Avg Rows/Ticker**: {cp.get('avg_rows_per_ticker', 0)} | "
            f"**Thin Tickers**: {cp.get('n_thin_tickers', 0)} | "
            f"**Gap Tickers**: {cp.get('n_gap_tickers', 0)}",
            f"**Status**: {'PASS' if cp.get('passed') else 'FAIL'}",
            "",
        ]

    # Lookahead
    la = result.get("lookahead_check", {})
    if "error" not in la and la:
        lines += [
            "## Lookahead Bias",
            f"**Factors Checked**: {la.get('n_factors_checked', 0)} | "
            f"**Suspicious**: {la.get('n_suspicious', 0)}",
            f"**Status**: {'PASS' if la.get('passed') else 'FAIL'}",
            "",
        ]
        sus = la.get("suspicious_factors", {})
        if sus:
            lines.append("| Factor | IC | P-Value |")
            lines.append("|--------|-----|---------|")
            for f, v in sus.items():
                lines.append(f"| {f} | {v['ic']:.4f} | {v['p_value']:.4f} |")
            lines.append("")

    lines.append("*Auto-generated by data_quality.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────

def _make_demo_data(n: int = 252, n_tickers: int = 8, seed: int = 42
                    ) -> Tuple[pd.DataFrame, List[str]]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    tickers = [f"STK{i}" for i in range(n_tickers)]

    rows = []
    for date in dates:
        for ticker in tickers:
            rows.append({"date": date, "ticker": ticker})
    df = pd.DataFrame(rows)

    factor_cols = [f"factor_{i}" for i in range(6)]
    for fc in factor_cols:
        df[fc] = rng.normal(0, 1, len(df))

    df["forward_return"] = rng.normal(0.0005, 0.015, len(df))
    df["close"] = 100.0

    # Inject some NaN for realism
    mask = rng.random(len(df)) < 0.03
    df.loc[mask, "factor_3"] = np.nan

    # Inject an outlier
    df.loc[10, "factor_0"] = 15.0

    return df, factor_cols


def main():
    df, factor_cols = _make_demo_data(252, 8, seed=7)

    config = QualityConfig(max_nan_ratio=0.3, max_staleness_days=5)
    result = run_quality_checks(
        df, factor_cols=factor_cols, config=config,
        forward_return_col="forward_return",
    )

    print(quality_report_markdown(result))
    print(f"\nPassed: {result['passed']} ({result['n_checks_passed']}/{result['n_checks_total']})")


if __name__ == "__main__":
    main()
