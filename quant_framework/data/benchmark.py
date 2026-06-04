#!/usr/bin/env python3
"""Data source quality benchmarking — compare latency, completeness, accuracy.

Benchmarks yfinance vs alpha_vantage (if key available) on real tickers.
Generates a comparison report with per-source metrics."""

import time
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SourceResult:
    source: str
    latency_s: float
    rows: int
    expected_rows: int
    tickers_fetched: int
    tickers_requested: int
    missing_dates: int = 0
    duplicate_rows: int = 0
    null_pct: float = 0.0
    price_outlier_pct: float = 0.0
    error: Optional[str] = None


def benchmark_single(
    ticker: str, start: str, end: str, source: str = "yfinance"
) -> SourceResult:
    """Benchmark a single ticker fetch from one source."""
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_single

    expected = len(pd.date_range(start, end, freq="B"))

    t0 = time.perf_counter()
    try:
        df = fetch_single(ticker, start, end, source=source)
        latency = time.perf_counter() - t0

        if df is None or df.empty:
            return SourceResult(source=source, latency_s=round(latency, 4),
                               rows=0, expected_rows=expected,
                               tickers_fetched=0, tickers_requested=1,
                               error="No data returned")

        rows = len(df)
        dates = set(pd.to_datetime(df["date"]).dt.date)
        expected_dates = set(pd.date_range(start, end, freq="B").date)
        missing = len(expected_dates - dates)
        dups = rows - df.drop_duplicates(subset=["date"]).shape[0]
        null_pct = round(df.isnull().sum().sum() / max(df.size, 1) * 100, 2)

        # Price outliers: returns > 20% in a day
        if "close" in df.columns and len(df) > 1:
            rets = df.sort_values("date")["close"].pct_change().dropna()
            outlier_pct = round((abs(rets) > 0.20).mean() * 100, 2)
        else:
            outlier_pct = 0.0

        return SourceResult(
            source=source, latency_s=round(latency, 4),
            rows=rows, expected_rows=expected,
            tickers_fetched=1, tickers_requested=1,
            missing_dates=missing, duplicate_rows=dups,
            null_pct=null_pct, price_outlier_pct=outlier_pct,
        )

    except Exception as e:
        latency = time.perf_counter() - t0
        return SourceResult(source=source, latency_s=round(latency, 4),
                           rows=0, expected_rows=expected,
                           tickers_fetched=0, tickers_requested=1,
                           error=str(e)[:120])


def benchmark_multi(
    tickers: List[str], start: str, end: str
) -> pd.DataFrame:
    """Benchmark multiple tickers across available sources."""
    results = []
    sources = ["yfinance"]

    # Try alpha_vantage if key available
    import os
    if os.environ.get("ALPHA_VANTAGE_KEY"):
        sources.append("alpha_vantage")

    for ticker in tickers:
        for src in sources:
            result = benchmark_single(ticker, start, end, src)
            results.append(result)

    rows = []
    for r in results:
        rows.append({
            "ticker": ticker if "ticker" in dir() else "?",
            "source": r.source,
            "latency_s": r.latency_s,
            "rows": r.rows,
            "expected": r.expected_rows,
            "completeness_pct": round(r.rows / max(r.expected_rows, 1) * 100, 1),
            "missing_dates": r.missing_dates,
            "duplicates": r.duplicate_rows,
            "null_pct": r.null_pct,
            "outlier_pct": r.price_outlier_pct,
            "error": r.error or "",
        })

    return pd.DataFrame(rows)


def benchmark_cross_source(
    tickers: List[str], start: str, end: str
) -> Dict:
    """Cross-source accuracy comparison — compare prices from different sources.

    Returns per-ticker price difference statistics between sources.
    """
    from quant_framework.data.fetchers.yfinance_fetcher import fetch_batch

    yf_data = fetch_batch(tickers, start, end, source="yfinance")
    if yf_data is None or yf_data.empty:
        return {"error": "No yfinance data"}

    # Try alpha vantage
    av_data = None
    import os
    if os.environ.get("ALPHA_VANTAGE_KEY"):
        try:
            av_data = fetch_batch(tickers, start, end, source="alpha_vantage")
        except Exception:
            pass

    comparison = {}
    for ticker in tickers:
        yf_t = yf_data[yf_data["ticker"] == ticker].set_index("date").sort_index()
        yf_t = yf_t[~yf_t.index.duplicated()]

        if av_data is not None:
            av_t = av_data[av_data["ticker"] == ticker].set_index("date").sort_index()
            av_t = av_t[~av_t.index.duplicated()]
            common = yf_t.index.intersection(av_t.index)
            if len(common) > 5 and "close" in yf_t.columns and "close" in av_t.columns:
                diff = (yf_t.loc[common, "close"] - av_t.loc[common, "close"]).dropna()
                comparison[ticker] = {
                    "n_common_dates": len(common),
                    "mean_diff": round(float(diff.mean()), 4),
                    "max_abs_diff": round(float(diff.abs().max()), 4),
                    "correlation": round(float(yf_t.loc[common, "close"].corr(av_t.loc[common, "close"])), 6),
                }

    return {
        "n_tickers_compared": len(comparison),
        "per_ticker": comparison,
        "yfinance_rows": len(yf_data),
        "alpha_vantage_rows": len(av_data) if av_data is not None else 0,
    }


def summary_report(benchmark_df: pd.DataFrame) -> str:
    """Generate a markdown summary report from benchmark results."""
    if benchmark_df.empty:
        return "No benchmark data."

    lines = [
        "# Data Source Benchmark Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Tickers tested**: {benchmark_df['ticker'].nunique()}",
        "",
        "## Per-Source Summary",
        "",
        "| Source | Avg Latency | Completeness | Missing | Dups | Null% | Outlier% | Errors |",
        "|--------|-------------|--------------|---------|------|-------|----------|--------|",
    ]

    for src in sorted(benchmark_df["source"].unique()):
        subset = benchmark_df[benchmark_df["source"] == src]
        avg_latency = subset["latency_s"].mean()
        avg_completeness = subset["completeness_pct"].mean()
        avg_missing = subset["missing_dates"].mean()
        avg_dups = subset["duplicates"].mean()
        avg_null = subset["null_pct"].mean()
        avg_outlier = subset["outlier_pct"].mean()
        n_errors = (subset["error"] != "").sum()

        lines.append(
            f"| {src} | {avg_latency:.2f}s | {avg_completeness:.0f}% | "
            f"{avg_missing:.0f} | {avg_dups:.0f} | {avg_null:.1f}% | "
            f"{avg_outlier:.1f}% | {n_errors} |"
        )

    lines.append("")
    lines.append("## Per-Ticker Detail")
    lines.append("")
    lines.append("| Ticker | Source | Latency | Rows | Completeness | Null% | Error |")
    lines.append("|--------|--------|---------|------|-------------|-------|-------|")

    for _, row in benchmark_df.iterrows():
        err = row["error"][:60] if row["error"] else "-"
        lines.append(
            f"| {row['ticker']} | {row['source']} | {row['latency_s']:.2f}s | "
            f"{row['rows']} | {row['completeness_pct']:.0f}% | "
            f"{row['null_pct']:.1f}% | {err} |"
        )

    return "\n".join(lines)


def main():
    """Run a quick benchmark on major tickers."""
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    start = "2025-01-01"
    end = "2025-03-31"

    print("Benchmarking data sources...")
    df = benchmark_multi(tickers, start, end)

    if df.empty:
        print("No results (network issue?)")
        return

    print("\nPer-source summary:")
    for src in sorted(df["source"].unique()):
        sub = df[df["source"] == src]
        errs = (sub["error"] != "").sum()
        print(f"  {src}: latency={sub['latency_s'].mean():.2f}s, "
              f"completeness={sub['completeness_pct'].mean():.0f}%, "
              f"errors={errs}/{len(sub)}")

    # Cross-source comparison
    comp = benchmark_cross_source(tickers, start, end)
    if "error" not in comp:
        print(f"\nCross-source comparison: {comp['n_tickers_compared']} tickers")
        for t, info in comp.get("per_ticker", {}).items():
            print(f"  {t}: mean_diff={info['mean_diff']:.4f}, corr={info['correlation']:.6f}")

    # Save report
    report = summary_report(df)
    from pathlib import Path
    out = Path("company/reports/benchmark_report.md")
    out.write_text(report, encoding="utf-8")
    print(f"\nReport saved to {out}")


if __name__ == "__main__":
    main()
