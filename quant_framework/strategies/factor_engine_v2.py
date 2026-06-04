"""
factor_engine_v2.py — Enhanced Factor Engine (T1050)

Enhancements over qlib_factor_engine.py:
  1. Auto symbol standardization — normalize ticker formats across yfinance/OpenBB/Alpha Vantage
  2. PCA concentration risk detector — flag when top 3 PCs explain >80% variance
  3. Cross-ticker supply chain correlation matrix — hidden concentration for 21 PIPELINE_TICKERS
  4. One-click factor verification — run all 39 factors, IC ranking, flag |IC|<0.02 or decay>20%

Safe: no eval(), no exec(), no pickle.load(). Uses sklearn for PCA, pandas/numpy for compute.

Usage:
    python factor_engine_v2.py --verify                    # one-click verification
    python factor_engine_v2.py --pca --input data.parquet  # PCA risk check
    python factor_engine_v2.py --corr-matrix                # supply chain correlation
    python factor_engine_v2.py --all --input data.parquet   # full suite
"""

import argparse
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─── Import existing safe factor engine ───
from quant_framework.strategies.qlib_factor_engine import (
    FACTOR_REGISTRY,
    FACTOR_GROUPS,
    compute_all_factors,
    neutralize_and_standardize,
)
from quant_framework.strategies.factor_analysis import ic_summary as _ic_summary_base

# ─── 1. Auto Symbol Standardization ───

# Exchange suffix patterns (source → canonical)
EXCHANGE_SUFFIX_MAP = {
    ".KS": ".KS",   # Korea KOSPI
    ".KQ": ".KQ",   # Korea KOSDAQ
    ".T":  ".T",    # Tokyo
    ".L":  ".L",    # London
    ".HK": ".HK",   # Hong Kong
    ".TW": ".TW",   # Taiwan
    ".SZ": ".SZ",   # Shenzhen
    ".SS": ".SS",   # Shanghai
    ".DE": ".DE",   # Xetra/Frankfurt
    ".PA": ".PA",   # Paris
    ".SW": ".SW",   # Swiss
}

# Ticker normalization table: (yfinance, OpenBB, AlphaVantage) → canonical
# Key: any variant → Value: canonical form
_TICKER_ALIASES = {
    "BRK.B":  "BRK-B",
    "BRK/B":  "BRK-B",
    "BRK-B":  "BRK-B",
    "BF.B":   "BF-B",
    "BF/B":   "BF-B",
    "BF-B":   "BF-B",
}

# Special cases: tickers that need exchange suffix normalization
# OpenBB strips suffixes, yfinance keeps them — we canonicalize to yfinance format
_TICKER_EXCHANGE_NORMALIZE: Dict[str, str] = {
    # Korean stocks: always append .KS for KOSPI, .KQ for KOSDAQ
    "005930": "005930.KS",   # Samsung Electronics
    "000660": "000660.KS",   # SK Hynix
    "035420": "035420.KQ",   # NAVER
    "035720": "035720.KQ",   # Kakao
}


def normalize_ticker(ticker: str, target_source: str = "yfinance") -> str:
    """Normalize a ticker symbol to the canonical format for a given data source.

    Handles:
      - BRK.B → BRK-B (yfinance)
      - BRK-B → BRK.B (OpenBB)
      - 000660 → 000660.KS (append KOSPI suffix)
      - 000660.KS → 000660.KS (pass-through)

    Args:
        ticker: Raw ticker string from any source
        target_source: "yfinance", "openbb", or "alphavantage"

    Returns:
        Normalized ticker string
    """
    t = ticker.strip().upper()

    # Step 1: Check explicit alias table
    if t in _TICKER_ALIASES:
        t = _TICKER_ALIASES[t]

    # Step 2: Handle dot-vs-dash for class shares (generic pattern)
    # e.g., "BF.B" → "BF-B" for yfinance
    if target_source == "yfinance" and "." in t and not any(
        t.endswith(suffix) for suffix in EXCHANGE_SUFFIX_MAP
    ):
        t = t.replace(".", "-")

    # Step 3: Normalize exchange suffix based on target
    if target_source == "yfinance":
        # yfinance needs exchange suffixes
        base = t.split(".")[0] if "." in t else t
        if base in _TICKER_EXCHANGE_NORMALIZE:
            t = _TICKER_EXCHANGE_NORMALIZE[base]
    elif target_source == "openbb":
        # OpenBB strips exchange suffixes for US stocks
        if any(t.endswith(suffix) for suffix in EXCHANGE_SUFFIX_MAP):
            # Keep known non-US suffixes for OpenBB as-is
            pass
        if "-" in t and not any(t.endswith(suffix) for suffix in EXCHANGE_SUFFIX_MAP):
            t = t.replace("-", ".")

    return t


def normalize_ticker_batch(
    tickers: List[str],
    target_source: str = "yfinance",
) -> List[str]:
    """Batch-normalize a list of tickers."""
    return [normalize_ticker(t, target_source) for t in tickers]


def detect_source_mismatch(ticker: str) -> Optional[str]:
    """Detect if a ticker appears to be from an unexpected source format.

    Returns the likely source, or None if ambiguous.
    """
    t = ticker.strip()
    if "-" in t and "." not in t and not t.endswith("-"):
        # Dash-separated: likely yfinance format (BRK-B)
        return "yfinance"
    if "." in t and any(
        t.endswith(suffix) for suffix in EXCHANGE_SUFFIX_MAP
    ):
        # Exchange suffix with dot: likely yfinance or Alpha Vantage
        return "yfinance"
    if "." in t and t.count(".") == 1 and t[-2] == ".":
        # Single dot before last char (BRK.B): likely OpenBB
        return "openbb"
    return None


# ─── 2. PCA Concentration Risk Detector ───

def pca_concentration_check(
    factor_returns: pd.DataFrame,
    variance_threshold: float = 0.80,
    n_top_components: int = 3,
) -> Dict:
    """Check if top N principal components explain > threshold of factor return variance.

    High PCA concentration means most factors are driven by a few common sources —
    the factor set has hidden concentration risk.

    Args:
        factor_returns: DataFrame of factor returns (rows=time, cols=factor names)
        variance_threshold: Flag if top PCs exceed this fraction (default 0.80)
        n_top_components: Number of top PCs to check (default 3)

    Returns:
        Dict with: concentrated (bool), top_pc_var (float), pc_summary (DataFrame),
                   alert_level (str), interpretation (str)
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    # Drop columns with insufficient data
    df = factor_returns.dropna(axis=1, thresh=max(10, len(factor_returns) // 2))
    df = df.dropna(axis=0, how="any")

    n_factors = df.shape[1]
    if n_factors < n_top_components:
        return {
            "concentrated": False,
            "alert_level": "info",
            "top_pc_var": np.nan,
            "n_factors": n_factors,
            "n_obs": len(df),
            "interpretation": f"Too few factors ({n_factors}) for PCA with {n_top_components} components.",
            "pc_summary": pd.DataFrame(),
        }

    # Standardize
    X = StandardScaler().fit_transform(df.values)

    # PCA
    pca = PCA()
    pca.fit(X)

    # Cumulative variance of top N components
    top_var = float(pca.explained_variance_ratio_[:n_top_components].sum())
    concentrated = top_var > variance_threshold

    # Alert level
    if top_var > 0.90:
        alert_level = "critical"
    elif top_var > variance_threshold:
        alert_level = "warning"
    else:
        alert_level = "ok"

    # Interpret
    if concentrated:
        n = n_top_components
        interpretation = (
            f"CONCENTRATION DETECTED: Top {n} PCs explain {top_var:.1%} of variance — "
            f"the {n_factors}-factor set is driven by only {n} independent sources. "
            f"Diversify factor portfolio or apply orthogonalization."
        )
    else:
        interpretation = (
            f"OK: Top {n_top_components} PCs explain {top_var:.1%} of variance — "
            f"factor set has reasonable diversification across {n_factors} factors."
        )

    # Per-component summary
    pc_summary = pd.DataFrame({
        "component": [f"PC{i+1}" for i in range(min(10, n_factors))],
        "var_explained": pca.explained_variance_ratio_[:10],
        "var_cumulative": np.cumsum(pca.explained_variance_ratio_[:10]),
    })
    pc_summary["var_explained"] = pc_summary["var_explained"].round(4)
    pc_summary["var_cumulative"] = pc_summary["var_cumulative"].round(4)

    # Top factor loadings per PC
    loadings = pd.DataFrame(
        pca.components_[:n_top_components].T,
        index=df.columns,
        columns=[f"PC{i+1}" for i in range(n_top_components)],
    )

    return {
        "concentrated": concentrated,
        "alert_level": alert_level,
        "top_pc_var": top_var,
        "n_factors": n_factors,
        "n_obs": len(df),
        "interpretation": interpretation,
        "pc_summary": pc_summary,
        "pc_loadings": loadings,
    }


def pca_concentration_report(result: Dict) -> str:
    """Generate a markdown report from PCA check results."""
    lines = [
        "## PCA Concentration Risk Check",
        "",
        f"**Variable explained by top PCs**: {result.get('top_pc_var', 0):.1%}",
        f"**Alert level**: {result.get('alert_level', 'unknown')}",
        f"**Factors analyzed**: {result.get('n_factors', 0)}",
        f"**Observations**: {result.get('n_obs', 0)}",
        "",
        f"> {result.get('interpretation', '')}",
        "",
    ]

    pc_summary = result.get("pc_summary")
    if pc_summary is not None and not pc_summary.empty:
        lines.append("| Component | Var Explained | Cumulative |")
        lines.append("|-----------|--------------|------------|")
        for _, row in pc_summary.iterrows():
            lines.append(
                f"| {row['component']} | {row['var_explained']:.2%} | {row['var_cumulative']:.2%} |"
            )
        lines.append("")

    return "\n".join(lines)


# ─── 3. Cross-Ticker Supply Chain Correlation Matrix ───

PIPELINE_TICKERS = [
    "DXYZ", "MU", "000660.KS", "WDC", "SNDK", "STX",
    "ANET", "NVDA",
    "RKLB", "ASTS", "LUNR",
    "LITE", "COHR", "RDW",
    "AVGO", "MRVL", "AMD", "INTC",
    "BABA", "JD", "TSEM",
]

# Supply chain cluster labels
SUPPLY_CHAIN_CLUSTERS = {
    "DXYZ": "Space/IPO",
    "MU": "Storage/Memory",
    "000660.KS": "Storage/Memory",
    "WDC": "Storage/Memory",
    "SNDK": "Storage/Memory",
    "STX": "Storage/Memory",
    "ANET": "AI/Networking",
    "NVDA": "AI/Semis",
    "RKLB": "Space",
    "ASTS": "Space",
    "LUNR": "Space",
    "LITE": "Optical/AI",
    "COHR": "Optical/AI",
    "RDW": "Space",
    "AVGO": "AI/Semis",
    "MRVL": "AI/Semis",
    "AMD": "AI/Semis",
    "INTC": "AI/Semis",
    "BABA": "China/Tech",
    "JD": "China/Tech",
    "TSEM": "Optical/AI",
}


def build_correlation_matrix(
    returns_df: pd.DataFrame,
    tickers: Optional[List[str]] = None,
    min_obs: int = 30,
) -> Tuple[pd.DataFrame, Dict]:
    """Build cross-ticker daily return correlation matrix and identify hidden concentration.

    Args:
        returns_df: DataFrame of daily returns (rows=dates, cols=ticker symbols)
        tickers: Subset of tickers to include (default: all PIPELINE_TICKERS found)
        min_obs: Minimum observations required per ticker

    Returns:
        (correlation_matrix, concentration_report)
    """
    if tickers is None:
        tickers = [t for t in PIPELINE_TICKERS if t in returns_df.columns]

    available = [t for t in tickers if t in returns_df.columns]
    missing = [t for t in tickers if t not in returns_df.columns]

    if len(available) < 3:
        return pd.DataFrame(), {
            "error": f"Need at least 3 tickers, found {len(available)}",
            "missing": missing,
            "clusters": [],
        }

    sub = returns_df[available].dropna(how="all")
    sub = sub.loc[sub.notna().sum(axis=1) >= max(3, len(available) // 2)]

    if len(sub) < min_obs:
        return pd.DataFrame(), {
            "error": f"Insufficient observations: {len(sub)} < {min_obs}",
            "missing": missing,
            "clusters": [],
        }

    corr_matrix = sub.corr(method="spearman")

    # Identify high-correlation clusters (r > 0.6)
    high_corr_pairs = []
    for i, t1 in enumerate(corr_matrix.columns):
        for t2 in corr_matrix.columns[i + 1:]:
            r = corr_matrix.loc[t1, t2]
            if abs(r) > 0.6:
                cluster1 = SUPPLY_CHAIN_CLUSTERS.get(t1, "Other")
                cluster2 = SUPPLY_CHAIN_CLUSTERS.get(t2, "Other")
                high_corr_pairs.append({
                    "ticker1": t1,
                    "ticker2": t2,
                    "correlation": round(r, 4),
                    "cluster1": cluster1,
                    "cluster2": cluster2,
                    "cross_cluster": cluster1 != cluster2,
                })

    high_corr_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    # Compute average intra-cluster and inter-cluster correlation
    clusters = list(set(
        SUPPLY_CHAIN_CLUSTERS.get(t, "Other") for t in available
    ))
    cluster_stats = {}
    for cl in clusters:
        members = [t for t in available if SUPPLY_CHAIN_CLUSTERS.get(t, "Other") == cl]
        if len(members) < 2:
            continue
        intra_corr = corr_matrix.loc[members, members].values
        mask = ~np.eye(len(members), dtype=bool)
        cluster_stats[cl] = {
            "members": members,
            "n_members": len(members),
            "mean_intra_corr": round(float(intra_corr[mask].mean()), 4),
            "max_intra_corr": round(float(intra_corr[mask].max()), 4),
        }

    # Inter-cluster correlation
    inter_cluster_pairs = []
    for i, c1 in enumerate(clusters):
        for c2 in clusters[i + 1:]:
            m1 = [t for t in available if SUPPLY_CHAIN_CLUSTERS.get(t, "Other") == c1]
            m2 = [t for t in available if SUPPLY_CHAIN_CLUSTERS.get(t, "Other") == c2]
            if not m1 or not m2:
                continue
            inter = corr_matrix.loc[m1, m2].values
            inter_cluster_pairs.append({
                "cluster1": c1,
                "cluster2": c2,
                "mean_inter_corr": round(float(inter.mean()), 4),
                "max_inter_corr": round(float(inter.max()), 4),
            })

    inter_cluster_pairs.sort(key=lambda x: abs(x["mean_inter_corr"]), reverse=True)

    # Flags
    flags = []
    for pair in high_corr_pairs[:10]:
        if pair["cross_cluster"]:
            flags.append(
                f"HIDDEN LINK: {pair['ticker1']}({pair['cluster1']}) ↔ "
                f"{pair['ticker2']}({pair['cluster2']}) r={pair['correlation']:.3f} — "
                f"Cross-cluster correlation suggests supply-chain exposure not captured by sector labels."
            )

    for cl, stats in cluster_stats.items():
        if stats["mean_intra_corr"] > 0.5:
            flags.append(
                f"INTRA-CLUSTER: {cl} has mean intra-cluster r={stats['mean_intra_corr']:.3f}"
                f" across {stats['n_members']} tickers — potential concentration."
            )

    concentration_report = {
        "n_tickers": len(available),
        "n_pairs_high_corr": len(high_corr_pairs),
        "missing_tickers": missing,
        "high_corr_pairs": high_corr_pairs,
        "cluster_stats": cluster_stats,
        "inter_cluster_pairs": inter_cluster_pairs,
        "flags": flags,
        "avg_pairwise_corr": round(
            float(corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()), 4
        ),
    }

    return corr_matrix, concentration_report


def correlation_matrix_report(corr_matrix: pd.DataFrame, report: Dict) -> str:
    """Generate markdown report for supply chain correlation analysis."""
    if report.get("error"):
        return f"## Supply Chain Correlation\n\n**Error**: {report['error']}"

    lines = [
        "## Cross-Ticker Supply Chain Correlation",
        "",
        f"**Tickers analyzed**: {report.get('n_tickers', 0)}",
        f"**High-correlation pairs (|r|>0.6)**: {report.get('n_pairs_high_corr', 0)}",
        f"**Average pairwise correlation**: {report.get('avg_pairwise_corr', 0):.4f}",
    ]

    if report.get("missing_tickers"):
        lines.append(f"**Missing (no data)**: {', '.join(report['missing_tickers'])}")
    lines.append("")

    # Flags
    flags = report.get("flags", [])
    if flags:
        lines.append("### Concentration Flags")
        lines.append("")
        for f in flags:
            lines.append(f"- {f}")
        lines.append("")

    # High-correlation pairs
    pairs = report.get("high_corr_pairs", [])
    if pairs:
        lines.append("### Top Cross-Ticker Correlations")
        lines.append("")
        lines.append("| Ticker 1 | Ticker 2 | r | Cluster 1 | Cluster 2 | Cross? |")
        lines.append("|----------|----------|---|-----------|-----------|--------|")
        for p in pairs[:15]:
            lines.append(
                f"| {p['ticker1']} | {p['ticker2']} | {p['correlation']:.3f} | "
                f"{p['cluster1']} | {p['cluster2']} | {'⚠ Yes' if p['cross_cluster'] else 'No'} |"
            )
        lines.append("")

    # Cluster stats
    cluster_stats = report.get("cluster_stats", {})
    if cluster_stats:
        lines.append("### Intra-Cluster Correlation")
        lines.append("")
        lines.append("| Cluster | Members | Mean r | Max r |")
        lines.append("|---------|---------|--------|-------|")
        for cl, stats in sorted(cluster_stats.items()):
            lines.append(
                f"| {cl} | {stats['n_members']} | {stats['mean_intra_corr']:.3f} | "
                f"{stats['max_intra_corr']:.3f} |"
            )
        lines.append("")

    # Inter-cluster
    inter = report.get("inter_cluster_pairs", [])
    if inter:
        lines.append("### Inter-Cluster Correlation (Hidden Links)")
        lines.append("")
        lines.append("| Cluster 1 | Cluster 2 | Mean r | Max r |")
        lines.append("|-----------|-----------|--------|-------|")
        for p in inter[:10]:
            lines.append(
                f"| {p['cluster1']} | {p['cluster2']} | {p['mean_inter_corr']:.3f} | "
                f"{p['max_inter_corr']:.3f} |"
            )
        lines.append("")

    return "\n".join(lines)


# ─── 4. One-Click Factor Verification ───

def verify_all_factors(
    factor_df: pd.DataFrame,
    returns: pd.Series,
    ic_abs_threshold: float = 0.02,
    decay_threshold: float = 0.20,
) -> Dict:
    """One-click verification: run all 39 factors, output IC ranking, flag weak factors.

    Args:
        factor_df: DataFrame with all factor columns computed
        returns: Series of forward returns (same index as factor_df)
        ic_abs_threshold: Flag factors with |mean IC| below this (default 0.02)
        decay_threshold: Flag factors with IC decay rate > this fraction (default 0.20)

    Returns:
        Dict with: ic_ranking, flagged_weak, flagged_decay, summary_stats, verification_passed
    """
    factor_cols = [c for c in factor_df.columns if c in FACTOR_REGISTRY]
    if not factor_cols:
        return {
            "error": "No factor columns found in DataFrame",
            "ic_ranking": pd.DataFrame(),
            "flagged_weak": [],
            "flagged_decay": [],
            "verification_passed": False,
        }

    # Align factor data with returns
    common_idx = factor_df.index.intersection(returns.index)
    if len(common_idx) < 20:
        return {
            "error": f"Insufficient common observations: {len(common_idx)}",
            "ic_ranking": pd.DataFrame(),
            "flagged_weak": [],
            "flagged_decay": [],
            "verification_passed": False,
        }

    f_sub = factor_df.loc[common_idx, factor_cols]
    r_sub = returns.loc[common_idx]

    # Compute IC per factor (Spearman rank correlation with forward returns)
    ic_rows = []
    for col in factor_cols:
        f_vals = f_sub[col]
        valid = f_vals.notna() & r_sub.notna()
        if valid.sum() < 10:
            continue
        ic = f_vals[valid].corr(r_sub[valid], method="spearman")

        # Compute rolling IC for decay estimation
        rolling_ics = []
        window = min(63, len(f_vals[valid]) // 2)
        for i in range(window, len(f_vals[valid])):
            f_slice = f_vals[valid].iloc[i - window:i]
            r_slice = r_sub[valid].iloc[i - window:i]
            ric = f_slice.corr(r_slice, method="spearman")
            if not np.isnan(ric):
                rolling_ics.append(ric)

        # Decay rate: slope of rolling IC (negative = declining)
        decay_rate = 0.0
        if len(rolling_ics) > 10:
            slope = np.polyfit(range(len(rolling_ics)), rolling_ics, 1)[0]
            decay_rate = -slope / max(abs(np.mean(rolling_ics)), 1e-10)

        _, direction = FACTOR_REGISTRY.get(col, (None, 0))
        group = "unknown"
        for g, names in FACTOR_GROUPS.items():
            if col in names:
                group = g
                break

        ic_rows.append({
            "factor": col,
            "group": group,
            "direction": {1: "long", -1: "short"}.get(direction, "neutral"),
            "mean_ic": round(ic, 4),
            "abs_ic": round(abs(ic), 4),
            "decay_rate": round(decay_rate, 4),
            "n_obs": int(valid.sum()),
            "ic_weak": abs(ic) < ic_abs_threshold,
            "decay_flagged": decay_rate > decay_threshold,
        })

    ic_ranking = pd.DataFrame(ic_rows).sort_values("abs_ic", ascending=False)

    flagged_weak = ic_ranking[ic_ranking["ic_weak"]].to_dict("records") if not ic_ranking.empty else []
    flagged_decay = ic_ranking[ic_ranking["decay_flagged"]].to_dict("records") if not ic_ranking.empty else []

    n_weak = len(flagged_weak)
    n_decay = len(flagged_decay)
    n_passed = len(ic_ranking) - n_weak - n_decay

    # Group-level summary
    group_stats = {}
    if not ic_ranking.empty:
        for g in ic_ranking["group"].unique():
            g_df = ic_ranking[ic_ranking["group"] == g]
            group_stats[g] = {
                "n_factors": len(g_df),
                "mean_abs_ic": round(float(g_df["abs_ic"].mean()), 4),
                "best_factor": g_df.iloc[0]["factor"],
                "best_ic": g_df.iloc[0]["abs_ic"],
                "n_weak": int(g_df["ic_weak"].sum()),
            }

    verification_passed = n_weak == 0 and n_decay == 0

    return {
        "ic_ranking": ic_ranking,
        "flagged_weak": flagged_weak,
        "flagged_decay": flagged_decay,
        "n_total": len(ic_ranking),
        "n_passed": n_passed,
        "n_weak": n_weak,
        "n_decay": n_decay,
        "group_stats": group_stats,
        "ic_abs_threshold": ic_abs_threshold,
        "decay_threshold": decay_threshold,
        "verification_passed": verification_passed,
    }


def verification_report(result: Dict) -> str:
    """Generate markdown verification report."""
    if result.get("error"):
        return f"## Factor Verification\n\n**Error**: {result['error']}"

    passed = result.get("verification_passed", False)
    status_icon = "✅ PASSED" if passed else "⚠️ FLAGGED"

    lines = [
        f"## Factor Verification — {status_icon}",
        "",
        f"**Factors evaluated**: {result.get('n_total', 0)} / {len(FACTOR_REGISTRY)} registered",
        f"**Clean factors**: {result.get('n_passed', 0)}",
        f"**Weak IC (|IC| < {result.get('ic_abs_threshold', 0.02):.2f})**: {result.get('n_weak', 0)}",
        f"**Decay flagged (decay > {result.get('decay_threshold', 0.20):.0%})**: {result.get('n_decay', 0)}",
        "",
    ]

    # IC Ranking Table
    ic_ranking = result.get("ic_ranking")
    if ic_ranking is not None and not ic_ranking.empty:
        lines.append("### IC Ranking (All Factors)")
        lines.append("")
        lines.append("| Rank | Factor | Group | Direction | |IC| | Decay | Status |")
        lines.append("|------|--------|-------|-----------|-----|-------|--------|")
        for i, (_, row) in enumerate(ic_ranking.iterrows()):
            status_parts = []
            if row["ic_weak"]:
                status_parts.append("WEAK")
            if row["decay_flagged"]:
                status_parts.append("DECAY")
            status = ", ".join(status_parts) if status_parts else "OK"
            status_str = f"⚠️ {status}" if status_parts else "OK"

            lines.append(
                f"| {i + 1} | {row['factor']} | {row['group']} | {row['direction']} | "
                f"{row['abs_ic']:.4f} | {row['decay_rate']:.4f} | {status_str} |"
            )
        lines.append("")

    # Weak IC factors
    flagged_weak = result.get("flagged_weak", [])
    if flagged_weak:
        lines.append("### ⚠️ Weak IC Factors (|IC| below threshold)")
        lines.append("")
        for f in flagged_weak:
            lines.append(f"- **{f['factor']}** ({f['group']}): |IC| = {f['abs_ic']:.4f}, n = {f['n_obs']}")
        lines.append("")

    # Decay flagged
    flagged_decay = result.get("flagged_decay", [])
    if flagged_decay:
        lines.append("### ⚠️ Decay Flagged (IC decaying > threshold)")
        lines.append("")
        for f in flagged_decay:
            lines.append(f"- **{f['factor']}** ({f['group']}): decay rate = {f['decay_rate']:.4f}")
        lines.append("")

    # Group summary
    group_stats = result.get("group_stats", {})
    if group_stats:
        lines.append("### Group-Level Summary")
        lines.append("")
        lines.append("| Group | N Factors | Mean |IC| | Best Factor | Best |IC| | N Weak |")
        lines.append("|-------|-----------|----------|-------------|-----------|--------|")
        for g, stats in sorted(group_stats.items()):
            lines.append(
                f"| {g} | {stats['n_factors']} | {stats['mean_abs_ic']:.4f} | "
                f"{stats['best_factor']} | {stats['best_ic']:.4f} | {stats['n_weak']} |"
            )
        lines.append("")

    return "\n".join(lines)


# ─── Full Suite Runner ───

def run_full_suite(
    df: pd.DataFrame,
    returns: Optional[pd.Series] = None,
    tickers: Optional[List[str]] = None,
) -> Dict:
    """Run all 4 T1050 enhancements and return combined results.

    Args:
        df: OHLCV DataFrame with multi-ticker data (must have 'ticker' column or single-ticker)
        returns: Optional pre-computed returns series
        tickers: Optional ticker list for correlation matrix

    Returns:
        Dict with: symbol_report, pca_result, corr_result, verify_result, combined_report (str)
    """
    results = {}

    # 1. Symbol standardization check
    if tickers:
        normalized = normalize_ticker_batch(tickers)
        mismatches = []
        for orig, norm in zip(tickers, normalized):
            if orig != norm:
                mismatches.append(f"{orig} → {norm}")
        results["symbol_report"] = {
            "n_tickers": len(tickers),
            "n_normalized": len(mismatches),
            "mismatches": mismatches,
        }
    else:
        results["symbol_report"] = {"n_tickers": 0, "n_normalized": 0, "mismatches": []}

    # 2. Compute factors first (needed for PCA + verification)
    factor_df = compute_all_factors(df)

    if returns is None:
        returns = df.get("close", pd.Series(dtype=float)).pct_change().shift(-1)

    # 3. PCA concentration check
    factor_cols = [c for c in factor_df.columns if c in FACTOR_REGISTRY]
    if len(factor_cols) >= 3:
        results["pca_result"] = pca_concentration_check(factor_df[factor_cols])
    else:
        results["pca_result"] = {"error": f"Need >=3 factor columns, got {len(factor_cols)}"}

    # 4. Supply chain correlation matrix
    if tickers:
        # Compute returns per ticker from df
        if "ticker" in df.columns:
            returns_by_ticker = {}
            for t in df["ticker"].unique():
                t_df = df[df["ticker"] == t].set_index("date") if "date" in df.columns else df[df["ticker"] == t]
                if "close" in t_df.columns and len(t_df) > 30:
                    returns_by_ticker[t] = t_df["close"].pct_change().dropna()
            if returns_by_ticker:
                returns_df = pd.DataFrame(returns_by_ticker)
                corr_matrix, corr_report = build_correlation_matrix(returns_df, tickers)
                results["corr_result"] = {
                    "corr_matrix": corr_matrix,
                    "report": corr_report,
                }
            else:
                results["corr_result"] = {"error": "No return data available for tickers"}
        else:
            results["corr_result"] = {"error": "DataFrame missing 'ticker' column"}
    else:
        results["corr_result"] = {"error": "No tickers provided"}

    # 5. Factor verification
    verif = verify_all_factors(factor_df, returns)
    results["verify_result"] = verif

    # 6. Combined report
    lines = [
        "# T1050 Factor Engine v2 — Full Suite Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 1. Symbol Standardization",
        f"Tickers checked: {results['symbol_report']['n_tickers']}, "
        f"Normalized: {results['symbol_report']['n_normalized']}",
    ]
    if results["symbol_report"]["mismatches"]:
        lines.append("")
        for m in results["symbol_report"]["mismatches"]:
            lines.append(f"  - {m}")

    lines.append("")
    lines.append("---")
    lines.append("")

    # PCA
    pca = results.get("pca_result", {})
    if pca.get("error"):
        lines.append(f"## 2. PCA Check\n\n**Skipped**: {pca['error']}")
    else:
        lines.append(pca_concentration_report(pca))

    lines.append("")
    lines.append("---")
    lines.append("")

    # Correlation
    corr = results.get("corr_result", {})
    if corr.get("error"):
        lines.append(f"## 3. Supply Chain Correlation\n\n**Skipped**: {corr['error']}")
    elif "report" in corr:
        lines.append(correlation_matrix_report(corr["corr_matrix"], corr["report"]))

    lines.append("")
    lines.append("---")
    lines.append("")

    # Verification
    lines.append(verification_report(results.get("verify_result", {})))

    results["combined_report"] = "\n".join(lines)
    return results


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(
        description="Factor Engine v2 — T1050 Enhancements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python factor_engine_v2.py --verify --input data.parquet
  python factor_engine_v2.py --pca --input data.parquet
  python factor_engine_v2.py --corr-matrix --input data.parquet --tickers DXYZ,MU,NVDA
  python factor_engine_v2.py --all --input data.parquet --output report.md
        """,
    )
    parser.add_argument("--input", default=None, help="Input parquet/csv file with OHLCV data")
    parser.add_argument("--output", default=None, help="Output file for report (markdown)")
    parser.add_argument("--verify", action="store_true", help="Run one-click factor verification")
    parser.add_argument("--pca", action="store_true", help="Run PCA concentration risk check")
    parser.add_argument("--corr-matrix", action="store_true", help="Run supply chain correlation matrix")
    parser.add_argument("--all", action="store_true", help="Run full suite")
    parser.add_argument("--tickers", default=None, help="Comma-separated ticker list (default: PIPELINE_TICKERS)")
    parser.add_argument("--ic-threshold", type=float, default=0.02, help="|IC| threshold for weak flag")
    parser.add_argument("--decay-threshold", type=float, default=0.20, help="Decay rate threshold")
    parser.add_argument("--pca-threshold", type=float, default=0.80, help="PCA variance threshold")
    parser.add_argument("--normalize", default=None, help="Normalize a ticker symbol and print")
    args = parser.parse_args()

    tickers = PIPELINE_TICKERS
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]

    # Quick normalize
    if args.normalize:
        for source in ["yfinance", "openbb", "alphavantage"]:
            print(f"  {args.normalize} → {source}: {normalize_ticker(args.normalize, source)}")
        return

    # Load data if needed
    df = None
    if args.input:
        df = pd.read_parquet(args.input) if args.input.endswith(".parquet") else pd.read_csv(args.input)

    if args.verify:
        if df is None:
            print("Error: --verify requires --input")
            return
        factor_df = compute_all_factors(df)
        returns = df.get("close", pd.Series(dtype=float)).pct_change().shift(-1)
        result = verify_all_factors(factor_df, returns, args.ic_threshold, args.decay_threshold)
        report = verification_report(result)
        if args.output:
            with open(args.output, "w") as f:
                f.write(report)
            print(f"Verification report → {args.output}")
        else:
            print(report)

    elif args.pca:
        if df is None:
            print("Error: --pca requires --input")
            return
        factor_df = compute_all_factors(df)
        factor_cols = [c for c in factor_df.columns if c in FACTOR_REGISTRY]
        result = pca_concentration_check(factor_df[factor_cols], args.pca_threshold)
        print(pca_concentration_report(result))

    elif args.corr_matrix:
        if df is None:
            print("Error: --corr-matrix requires --input")
            return
        if "ticker" not in df.columns:
            print("Error: input must have 'ticker' column for correlation matrix")
            return
        returns_by_ticker = {}
        for t in df["ticker"].unique():
            t_df = df[df["ticker"] == t]
            if "close" in t_df.columns and len(t_df) > 30:
                returns_by_ticker[t] = t_df["close"].pct_change().dropna()
        returns_df = pd.DataFrame(returns_by_ticker)
        corr_matrix, report = build_correlation_matrix(returns_df, tickers)
        print(correlation_matrix_report(corr_matrix, report))

    elif args.all:
        if df is None:
            print("Error: --all requires --input")
            return
        returns = df.get("close", pd.Series(dtype=float)).pct_change().shift(-1) if "close" in df.columns else None
        results = run_full_suite(df, returns, tickers)
        report = results["combined_report"]
        if args.output:
            with open(args.output, "w") as f:
                f.write(report)
            print(f"Full suite report → {args.output}")
        else:
            print(report)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
