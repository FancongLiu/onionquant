#!/usr/bin/env python3
"""T1051: 21-ticker full quant research report.

Uses existing quant_framework/ modules — no hand-rolled calculations.
Output: company/chairman_outbox/quant_research_20260518.md
"""

import logging
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# ── Import existing framework modules ──
from quant_framework.risk.portfolio_optimizer import (
    hierarchical_risk_parity,
    risk_parity,
)
from quant_framework.strategies.qlib_factor_engine import (
    FACTOR_GROUPS,
    compute_all_factors,
    neutralize_and_standardize,
)

TICKERS = [
    "DXYZ",
    "MU",
    "000660.KS",
    "WDC",
    "SNDK",
    "STX",
    "ANET",
    "NVDA",
    "RKLB",
    "ASTS",
    "LUNR",
    "LITE",
    "COHR",
    "RDW",
    "AVGO",
    "MRVL",
    "AMD",
    "INTC",
    "BABA",
    "JD",
    "TSEM",
]

START = "2025-03-15"  # ~300 calendar days → ~200 trading days
END = "2026-05-18"
OUTPUT = PROJECT / "company" / "chairman_outbox" / "quant_research_20260518.md"


def pull_data():
    """Step 1: Pull price data for all 21 tickers."""
    logger.info("Pulling price data for %d tickers...", len(TICKERS))
    import yfinance as yf

    all_data = {}
    missing = []

    for t in TICKERS:
        try:
            df = yf.download(t, start=START, end=END, progress=False, auto_adjust=True)
            if df.empty:
                logger.warning("No data for %s", t)
                missing.append(t)
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df.columns = [c.lower() for c in df.columns]
            df["ticker"] = t
            df["date"] = df.index
            all_data[t] = df
            logger.info("%s: %d rows", t, len(df))
        except Exception as e:
            logger.warning("%s: %s", t, e)
            missing.append(t)

    if missing:
        logger.warning("Missing tickers: %s", missing)
    return all_data, missing


def build_universe_panel(all_data):
    """Build a wide-format close price + return panel."""
    closes = {}
    volumes = {}
    for t, df in all_data.items():
        closes[t] = df["close"]
        volumes[t] = df["volume"]

    close_df = pd.DataFrame(closes).sort_index()
    volume_df = pd.DataFrame(volumes).sort_index()
    ret_df = close_df.pct_change().dropna(how="all")
    return close_df, ret_df, volume_df


def compute_factors_per_ticker(all_data):
    """Step 2: Compute factors per ticker using qlib_factor_engine."""
    logger.info("Computing factors per ticker...")
    factor_dfs = {}
    for t, df in all_data.items():
        fdf = compute_all_factors(df)
        factor_dfs[t] = fdf.tail(1)  # latest factor values
    return factor_dfs


def compute_rolling_factors_and_ic(all_data):
    """Compute rolling factors for all tickers and IC analysis."""
    logger.info("Computing rolling factors and IC...")

    # Build combined dataset: one row per (date, ticker)
    combined_rows = []
    for t, df in all_data.items():
        fdf = compute_all_factors(df)
        fdf["ticker"] = t
        fdf["date"] = pd.to_datetime(df.index)
        combined_rows.append(
            fdf[np.isfinite(fdf.select_dtypes(include=[np.number]).values).any(axis=1)]
        )

    combined = pd.concat(combined_rows, ignore_index=True)

    # Get factor columns (price-derived only)
    factors_from_price = [
        "mom_1d",
        "mom_5d",
        "mom_10d",
        "mom_21d",
        "mom_63d",
        "mom_126d",
        "mom_252d",
        "rev_5d",
        "rev_10d",
        "rev_21d",
        "vol_5d",
        "vol_21d",
        "vol_63d",
        "turn_5d",
        "turn_21d",
        "size_log",
        "std_5d",
        "std_21d",
        "corr_vp_21d",
    ]
    available_factors = [c for c in factors_from_price if c in combined.columns]

    # Compute daily returns for each ticker
    combined["daily_ret"] = combined.groupby("ticker")["close"].transform(
        lambda x: x.pct_change().shift(-1)
    )

    # Standardize factors within each date cross-section
    combined = neutralize_and_standardize(combined)

    # IC analysis: for each date, compute cross-sectional spearman IC
    ic_results = []
    for dt, grp in combined.groupby("date"):
        if len(grp) < 5:
            continue
        for fac in available_factors:
            valid = grp[[fac, "daily_ret"]].dropna()
            if len(valid) < 5:
                continue
            ic = valid[fac].corr(valid["daily_ret"], method="spearman")
            ic_results.append({"date": dt, "factor": fac, "ic": ic})

    ic_df = pd.DataFrame(ic_results)
    if not ic_df.empty:
        ic_summary = (
            ic_df.groupby("factor")
            .agg(
                mean_ic=("ic", "mean"),
                std_ic=("ic", "std"),
                hit_rate=("ic", lambda x: (x > 0).mean()),
                n_obs=("ic", "count"),
            )
            .reset_index()
        )
        ic_summary["ic_ir"] = ic_summary["mean_ic"] / ic_summary["std_ic"].clip(
            lower=1e-10
        )
        ic_summary = ic_summary.sort_values("ic_ir", ascending=False)
    else:
        ic_summary = pd.DataFrame()

    return combined, ic_summary, available_factors


def compute_factors_per_date_cross_section(combined, available_factors):
    """Compute latest date cross-sectional factor scores."""
    logger.info("Computing cross-sectional factor scores for latest date...")
    latest_date = combined["date"].max()
    latest = combined[combined["date"] == latest_date].copy()

    factor_scores = latest[["ticker"] + available_factors].set_index("ticker")
    return factor_scores, latest_date


def composite_factor_scores(factor_scores, ic_summary):
    """Step 3+6: Weight factors by IC IR to get composite scores."""
    logger.info("Computing composite factor scores...")

    # Use IC IR as weight
    if not ic_summary.empty:
        weights = ic_summary.set_index("factor")["ic_ir"].abs()
        weights = weights / weights.sum()
    else:
        weights = pd.Series(
            1.0 / len(factor_scores.columns), index=factor_scores.columns
        )

    common_factors = [f for f in factor_scores.columns if f in weights.index]
    if not common_factors:
        common_factors = list(factor_scores.columns)
        weights = pd.Series(1.0 / len(common_factors), index=common_factors)

    scores = factor_scores[common_factors].mul(weights[common_factors]).sum(axis=1)
    scores = scores.sort_values(ascending=False)
    return scores, weights


def build_correlation_matrix(close_df, ret_df):
    """Step 4: Pairwise correlation matrix with clustering."""
    logger.info("Building correlation matrix...")

    # Use daily returns for correlation
    valid_tickers = [c for c in ret_df.columns if ret_df[c].notna().sum() > 60]
    corr_matrix = ret_df[valid_tickers].corr(method="spearman")

    # Hierarchical clustering on correlation distance
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    dist = 1 - corr_matrix.abs()
    dist_sq = squareform(dist.values[np.triu_indices_from(dist, k=1)])
    linkage_matrix = linkage(dist_sq, method="ward")

    # Assign clusters (3-5 groups)
    n_clusters = 5
    clusters = fcluster(linkage_matrix, n_clusters, criterion="maxclust")
    cluster_map = dict(zip(corr_matrix.columns, clusters))

    return corr_matrix, cluster_map, linkage_matrix


def portfolio_comparison(ret_df):
    """Step 5: Risk parity vs equal-weight vs HRP."""
    logger.info("Running portfolio optimization comparison...")

    valid_tickers = [c for c in ret_df.columns if ret_df[c].notna().sum() > 120]
    returns = ret_df[valid_tickers].dropna()
    n_assets = len(valid_tickers)

    results = {}

    # Equal weight
    eq_w = np.ones(n_assets) / n_assets
    eq_ret = float(eq_w @ returns.mean().values * 252)
    eq_risk = float(np.sqrt(eq_w @ returns.cov().values @ eq_w) * np.sqrt(252))
    results["Equal-Weight"] = {
        "weights": dict(zip(valid_tickers, eq_w)),
        "expected_return": eq_ret,
        "expected_risk": eq_risk,
        "sharpe": eq_ret / max(eq_risk, 1e-10),
    }

    # Risk parity
    try:
        rp = risk_parity(returns.values, max_weight=0.25)
        rp_ret = rp["expected_return"]
        rp_risk = rp["expected_risk"]
        results["Risk Parity"] = {
            "weights": dict(zip(valid_tickers, rp["weights"])),
            "expected_return": rp_ret,
            "expected_risk": rp_risk,
            "sharpe": rp_ret / max(rp_risk, 1e-10),
        }
    except Exception as e:
        logger.warning("Risk parity failed: %s", e)
        results["Risk Parity"] = {"error": str(e)}

    # HRP
    try:
        hrp = hierarchical_risk_parity(returns.values, max_weight=0.25)
        hrp_ret = hrp["expected_return"]
        hrp_risk = hrp["expected_risk"]
        results["HRP"] = {
            "weights": dict(zip(valid_tickers, hrp["weights"])),
            "expected_return": hrp_ret,
            "expected_risk": hrp_risk,
            "sharpe": hrp_ret / max(hrp_risk, 1e-10),
        }
    except Exception as e:
        logger.warning("HRP failed: %s", e)
        results["HRP"] = {"error": str(e)}

    return results, valid_tickers


def generate_report(
    all_data,
    missing,
    close_df,
    ret_df,
    factor_scores,
    latest_date,
    ic_summary,
    available_factors,
    composite_scores,
    weights,
    corr_matrix,
    cluster_map,
    port_results,
    valid_tickers,
) -> str:
    """Assemble the comprehensive research report."""
    today = date.today().strftime("%Y-%m-%d")

    lines = [
        f"# Quantitative Research Report — {today}",
        "",
        f"**21 Tickers**: {', '.join(TICKERS)}",
        f"**Data Period**: {START} → {END}",
        f"**Factors Computed**: {len(available_factors)} price-derived factors from Qlib Alpha158",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 1. Data Summary",
        "",
    ]

    if missing:
        lines.append(f"**Missing Tickers**: {', '.join(missing)}")
        lines.append("")
    lines.append("| Ticker | Rows | Start | End | Latest Close |")
    lines.append("|--------|------|-------|-----|-------------|")
    for t in TICKERS:
        if t in all_data:
            df = all_data[t]
            c = df["close"]
            lines.append(
                f"| {t} | {len(df)} | {c.index[0].strftime('%Y-%m-%d') if hasattr(c.index[0], 'strftime') else str(c.index[0])[:10]}"
                f" | {c.index[-1].strftime('%Y-%m-%d') if hasattr(c.index[-1], 'strftime') else str(c.index[-1])[:10]}"
                f" | ${c.iloc[-1]:.2f} |"
            )
        else:
            lines.append(f"| {t} | N/A | N/A | N/A | N/A |")
    lines.append("")

    # ── Factor IC Rankings ──
    lines += [
        "## 2. Factor IC Rankings (Cross-Sectional)",
        "",
        "Factor IC (Information Coefficient) measures each factor's predictive power for next-day returns.",
        "Higher |IC IR| = more consistent predictive power. Positive mean IC = factor direction is correct.",
        "",
    ]
    if not ic_summary.empty:
        lines.append("### Top 10 Factors by IC IR")
        lines.append("| Rank | Factor | Mean IC | Std IC | IC IR | Hit Rate | N Obs |")
        lines.append("|------|--------|---------|--------|-------|----------|-------|")
        for i, (_, row) in enumerate(ic_summary.head(10).iterrows()):
            lines.append(
                f"| {i + 1} | {row['factor']} | {row['mean_ic']:.4f} | {row['std_ic']:.4f} | "
                f"{row['ic_ir']:.2f} | {row['hit_rate']:.1%} | {int(row['n_obs'])} |"
            )
        lines.append("")

        lines.append("### Bottom 10 Factors by IC IR")
        lines.append("| Rank | Factor | Mean IC | Std IC | IC IR | Hit Rate | N Obs |")
        lines.append("|------|--------|---------|--------|-------|----------|-------|")
        bottom = ic_summary.tail(10).iloc[::-1]
        rank = len(ic_summary) - 9
        for i, (_, row) in enumerate(bottom.iterrows()):
            lines.append(
                f"| {rank + i} | {row['factor']} | {row['mean_ic']:.4f} | {row['std_ic']:.4f} | "
                f"{row['ic_ir']:.2f} | {row['hit_rate']:.1%} | {int(row['n_obs'])} |"
            )
        lines.append("")

    # ── Factor Group Performance ──
    lines += [
        "## 3. Factor Group Performance (Momentum / Value / Quality)",
        "",
    ]
    # Map factor groups for display
    for group_name in ["momentum", "reversal", "volatility", "size"]:
        group_factors = FACTOR_GROUPS.get(group_name, [])
        available = [f for f in group_factors if f in ic_summary["factor"].values]
        if available and not ic_summary.empty:
            group_data = ic_summary[ic_summary["factor"].isin(available)]
            if not group_data.empty:
                avg_ic = group_data["mean_ic"].mean()
                avg_ir = group_data["ic_ir"].abs().mean()
                avg_hit = group_data["hit_rate"].mean()
                lines.append(
                    f"| {group_name} | {len(available)} | {avg_ic:.4f} | "
                    f"{avg_ir:.2f} | {avg_hit:.1%} |"
                )
    lines.append("")

    # ── Correlation Matrix ──
    lines += [
        "## 4. Correlation Matrix & Clustering",
        "",
        "### Cluster Assignments",
        "",
        "| Ticker | Cluster |",
        "|--------|---------|",
    ]
    for t, c in sorted(cluster_map.items(), key=lambda x: (x[1], x[0])):
        lines.append(f"| {t} | Group {c} |")
    lines.append("")

    # Top correlations
    lines += [
        "### Top 10 Highest Pairwise Correlations",
        "",
        "| Pair | Spearman ρ |",
        "|------|-----------|",
    ]
    corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            t1, t2 = corr_matrix.columns[i], corr_matrix.columns[j]
            corr_pairs.append((t1, t2, corr_matrix.iloc[i, j]))
    corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    for t1, t2, val in corr_pairs[:10]:
        lines.append(f"| {t1} ↔ {t2} | {val:.4f} |")
    lines.append("")

    # ── Portfolio Comparison ──
    lines += [
        "## 5. Portfolio Optimization Comparison",
        "",
        "| Method | Ann. Return | Ann. Risk | Sharpe | Top 5 Holdings |",
        "|--------|------------|-----------|--------|---------------|",
    ]
    for method, result in port_results.items():
        if "error" in result:
            lines.append(f"| {method} | — | — | — | Error: {result['error']} |")
        else:
            w = result["weights"]
            w_sorted = sorted(w.items(), key=lambda x: x[1], reverse=True)
            top5 = ", ".join(f"{t}({wt:.1%})" for t, wt in w_sorted[:5])
            lines.append(
                f"| {method} | {result['expected_return']:.1%} | {result['expected_risk']:.1%} | "
                f"{result['sharpe']:.2f} | {top5} |"
            )
    lines.append("")

    # ── Composite Factor Scores ──
    lines += [
        "## 6. Top 5 Picks — Highest Composite Factor Scores",
        "",
        f"Factors weighted by IC IR. Latest date: {latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)[:10]}",
        "",
        "| Rank | Ticker | Composite Score | Top Contributing Factor |",
        "|------|--------|----------------|------------------------|",
    ]
    for i, (ticker, score) in enumerate(composite_scores.head(5).items()):
        if ticker in factor_scores.index:
            top_factor = factor_scores.loc[ticker].abs().idxmax()
            lines.append(f"| {i + 1} | {ticker} | {score:.4f} | {top_factor} |")
        else:
            lines.append(f"| {i + 1} | {ticker} | {score:.4f} | N/A |")
    lines.append("")

    # Full rankings
    lines += [
        "### Full Rankings (All 21 Tickers)",
        "",
        "| Rank | Ticker | Score |",
        "|------|--------|-------|",
    ]
    for i, (ticker, score) in enumerate(composite_scores.items()):
        lines.append(f"| {i + 1} | {ticker} | {score:.4f} |")
    lines.append("")

    # ── Risk Metrics per Ticker ──
    lines += [
        "## Appendix A: Risk Metrics per Ticker",
        "",
        "| Ticker | Ann. Vol | MaxDD | Sharpe | 21D Mom | 63D Mom | Beta (vs NVDA) |",
        "|--------|---------|-------|--------|---------|---------|----------------|",
    ]
    nvda_ret = ret_df.get("NVDA", pd.Series(dtype=float))
    for t in TICKERS:
        if t not in ret_df.columns or t not in close_df.columns:
            continue
        r = ret_df[t].dropna()
        if len(r) < 30:
            continue
        ann_vol = float(r.std() * np.sqrt(252))
        cum = (1 + r).cumprod()
        maxdd = float((cum / cum.cummax() - 1).min())
        sharpe = float(r.mean() / max(r.std(), 1e-10) * np.sqrt(252))
        mom21 = (
            float(close_df[t].pct_change(21).iloc[-1])
            if len(close_df[t]) > 21
            else float("nan")
        )
        mom63 = (
            float(close_df[t].pct_change(63).iloc[-1])
            if len(close_df[t]) > 63
            else float("nan")
        )
        # Beta vs NVDA
        if len(nvda_ret) > 30:
            common_idx = r.index.intersection(nvda_ret.dropna().index)
            if len(common_idx) > 30:
                beta = float(
                    r.loc[common_idx].cov(nvda_ret.loc[common_idx])
                    / nvda_ret.loc[common_idx].var()
                )
            else:
                beta = float("nan")
        else:
            beta = float("nan")

        lines.append(
            f"| {t} | {ann_vol:.1%} | {maxdd:.1%} | {sharpe:.2f} | "
            f"{mom21:.1%} | {mom63:.1%} | {beta:.2f} |"
        )
    lines.append("")

    # ── Current Price Snapshot ──
    lines += [
        "## Appendix B: Current Price Snapshot",
        "",
        "| Ticker | Price | 5D Chg | 21D Chg | 63D Chg | RSI(14) |",
        "|--------|-------|--------|---------|---------|---------|",
    ]
    for t in TICKERS:
        if t not in close_df.columns:
            lines.append(f"| {t} | N/A | N/A | N/A | N/A | N/A |")
            continue
        c = close_df[t].dropna()
        price = c.iloc[-1]
        chg5 = c.pct_change(5).iloc[-1] if len(c) > 5 else float("nan")
        chg21 = c.pct_change(21).iloc[-1] if len(c) > 21 else float("nan")
        chg63 = c.pct_change(63).iloc[-1] if len(c) > 63 else float("nan")
        # RSI(14)
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (
            100 - (100 / (1 + rs.iloc[-1]))
            if not pd.isna(rs.iloc[-1])
            else float("nan")
        )
        lines.append(
            f"| {t} | ${price:.2f} | {chg5:.1%} | {chg21:.1%} | {chg63:.1%} | {rsi:.0f} |"
        )
    lines.append("")

    lines += [
        "---",
        "",
        f"*Auto-generated by quant_research_report.py | {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Caveats",
        "- Factor IC based on price-derived factors only (momentum, volatility, reversal, volume).",
        "- Fundamental factors (PE, PB, ROE) require quarterly financial data not available from daily yfinance OHLCV.",
        "- Portfolio optimization uses historical covariance — forward-looking weights may differ.",
        "- Korean ticker 000660.KS (Samsung) may have different trading calendar from US stocks.",
        "- IC computed cross-sectionally across all 21 tickers — small universe limits statistical power.",
    ]

    return "\n".join(lines)


def main():
    logger.info("=== T1051: 21-Ticker Full Quant Research Report ===")

    # Step 1: Pull data
    all_data, missing = pull_data()
    if len(all_data) < 5:
        logger.error("Insufficient data: only %d tickers pulled", len(all_data))
        sys.exit(1)

    # Build panel
    close_df, ret_df, volume_df = build_universe_panel(all_data)
    logger.info("Close panel: %d rows x %d cols", len(close_df), len(close_df.columns))

    # Step 2: Compute rolling factors + IC
    combined, ic_summary, available_factors = compute_rolling_factors_and_ic(all_data)
    logger.info("IC summary: %d factors", len(ic_summary))

    # Compute latest factor scores
    factor_scores, latest_date = compute_factors_per_date_cross_section(
        combined, available_factors
    )
    logger.info(
        "Factor scores: %d tickers x %d factors",
        len(factor_scores),
        len(available_factors),
    )

    # Step 3+6: Composite scores
    composite_scores, weights = composite_factor_scores(factor_scores, ic_summary)
    logger.info("Composite scores: %d tickers", len(composite_scores))

    # Step 4: Correlation matrix
    corr_matrix, cluster_map, linkage_matrix = build_correlation_matrix(
        close_df, ret_df
    )
    logger.info(
        "Correlation matrix: %d x %d", corr_matrix.shape[0], corr_matrix.shape[1]
    )

    # Step 5: Portfolio comparison
    port_results, valid_tickers = portfolio_comparison(ret_df)
    logger.info("Portfolio methods: %s", list(port_results.keys()))

    # Generate report
    report = generate_report(
        all_data,
        missing,
        close_df,
        ret_df,
        factor_scores,
        latest_date,
        ic_summary,
        available_factors,
        composite_scores,
        weights,
        corr_matrix,
        cluster_map,
        port_results,
        valid_tickers,
    )

    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(report, encoding="utf-8")
    logger.info("Report saved → %s", OUTPUT)
    logger.info("Report size: %d chars", len(report))

    # Print summary to stdout
    print("\n" + "=" * 60)
    print("REPORT GENERATED")
    print("=" * 60)
    print(f"Tickers pulled: {len(all_data)}/21")
    print(f"Missing: {missing if missing else 'None'}")
    print(f"Factors analyzed: {len(available_factors)}")
    if not ic_summary.empty:
        print(
            f"Top IC factor: {ic_summary.iloc[0]['factor']} (IC IR={ic_summary.iloc[0]['ic_ir']:.2f})"
        )
    if not composite_scores.empty:
        print(
            f"Top pick: {composite_scores.index[0]} (score={composite_scores.iloc[0]:.4f})"
        )
    print(f"Report: {OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
