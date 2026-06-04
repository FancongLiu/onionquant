#!/usr/bin/env python3
"""Performance attribution — decompose returns into factor contributions.

Uses statsmodels OLS for factor regression (Fama-French style attribution).
Separates alpha (idiosyncratic) from beta (factor-driven) returns."""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from datetime import datetime


def factor_regression(
    portfolio_returns: pd.Series,
    factor_returns: pd.DataFrame,
    intercept: bool = True,
) -> Dict:
    """Regress portfolio returns on factor returns (Fama-French style).

    Parameters
    ----------
    portfolio_returns: Series of portfolio returns
    factor_returns: DataFrame of factor returns (dates × factors)
    intercept: include alpha (intercept) term

    Returns dict with exposures, t-stats, r-squared, alpha.
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return {"error": "statsmodels required"}

    common = portfolio_returns.index.intersection(factor_returns.index)
    y = portfolio_returns.loc[common].values
    X = factor_returns.loc[common].values

    if len(common) < 20 or X.shape[1] == 0:
        return {"error": "Insufficient data (need 20+ observations)"}

    mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
    y, X = y[mask], X[mask]
    if len(y) < 20:
        return {"error": "Insufficient clean data"}

    if intercept:
        X = sm.add_constant(X)

    model = sm.OLS(y, X).fit()
    params = model.params
    tvalues = model.tvalues
    pvalues = model.pvalues

    exposures = {}
    tstats = {}
    pvals = {}
    col_names = (["alpha"] if intercept else []) + list(factor_returns.columns)
    for i, name in enumerate(col_names):
        exposures[name] = round(float(params[i]), 6)
        tstats[name] = round(float(tvalues[i]), 3)
        pvals[name] = round(float(pvalues[i]), 4)

    # Decompose returns
    factor_contributions = {}
    for name in factor_returns.columns:
        if name in exposures:
            factor_contributions[name] = round(
                float(exposures[name] * factor_returns[name].loc[common].mean()), 6
            )

    total_factor_return = sum(v for k, v in factor_contributions.items() if k != "alpha")

    return {
        "exposures": exposures,
        "t_statistics": tstats,
        "p_values": pvals,
        "r_squared": round(float(model.rsquared), 4),
        "adj_r_squared": round(float(model.rsquared_adj), 4),
        "alpha_annual": round(float(exposures.get("alpha", 0)) * 252, 6) if intercept else 0,
        "factor_contributions": factor_contributions,
        "total_factor_return_annual": round(float(total_factor_return) * 252, 6),
        "n_obs": len(y),
    }


def rolling_attribution(
    portfolio_returns: pd.Series,
    factor_returns: pd.DataFrame,
    window: int = 252,
    step: int = 21,
) -> pd.DataFrame:
    """Rolling factor exposure analysis.

    Returns DataFrame with rolling exposures over time.
    """
    results = []
    dates = portfolio_returns.index
    for i in range(window, len(dates), step):
        port_slice = portfolio_returns.iloc[i - window:i]
        reg = factor_regression(port_slice, factor_returns.loc[port_slice.index])
        if "error" in reg:
            continue
        row = {"date": dates[i], "r_squared": reg["r_squared"]}
        row.update(reg["exposures"])
        results.append(row)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results).set_index("date").sort_index()
    return df


def contribution_summary(attribution: Dict) -> pd.DataFrame:
    """Summarize factor contributions as a DataFrame."""
    if "error" in attribution:
        return pd.DataFrame()

    rows = []
    for factor, contrib in attribution.get("factor_contributions", {}).items():
        if factor not in {"alpha", "const"}:
            rows.append({
                "factor": factor,
                "daily_contribution": contrib,
                "annual_contribution": round(contrib * 252, 6),
                "exposure": attribution["exposures"].get(factor, 0),
                "t_stat": attribution["t_statistics"].get(factor, 0),
                "significant": attribution["p_values"].get(factor, 1) < 0.05,
            })

    if "alpha" in attribution.get("exposures", {}):
        rows.append({
            "factor": "alpha (idiosyncratic)",
            "daily_contribution": attribution["exposures"]["alpha"],
            "annual_contribution": attribution["alpha_annual"],
            "exposure": 0,
            "t_stat": attribution["t_statistics"].get("alpha", 0),
            "significant": attribution["p_values"].get("alpha", 1) < 0.05,
        })

    return pd.DataFrame(rows).sort_values("annual_contribution", ascending=False)


def brinson_attribution(
    portfolio_weights: pd.DataFrame,
    benchmark_weights: pd.DataFrame,
    asset_returns: pd.DataFrame,
    group_mapping: Optional[Dict[str, str]] = None,
) -> Dict:
    """Brinson performance attribution: allocation + selection + interaction.

    Parameters
    ----------
    portfolio_weights: DataFrame of portfolio weights (dates × tickers)
    benchmark_weights: DataFrame of benchmark weights (dates × tickers)
    asset_returns: DataFrame of asset returns (dates × tickers)
    group_mapping: ticker → sector/group label

    Returns dict with allocation_effect, selection_effect, interaction_effect.
    """
    common_dates = portfolio_weights.index.intersection(benchmark_weights.index).intersection(asset_returns.index)
    common_tickers = portfolio_weights.columns.intersection(benchmark_weights.columns).intersection(asset_returns.columns)

    if len(common_dates) < 2 or len(common_tickers) < 2:
        return {"error": "Insufficient overlapping data"}

    pw = portfolio_weights.loc[common_dates, common_tickers]
    bw = benchmark_weights.loc[common_dates, common_tickers]
    rets = asset_returns.loc[common_dates, common_tickers]

    # Without sector mapping, compute total effects
    if group_mapping is None or len(group_mapping) == 0:
        w_diff = pw - bw
        allocation = (bw * rets).sum(axis=1).mean()
        selection = (bw * rets).sum(axis=1).mean()
        interaction = (w_diff * rets).sum(axis=1).mean()
        return {
            "allocation_effect": round(float(allocation) * 252, 6),
            "selection_effect": round(float(selection) * 252, 6),
            "interaction_effect": round(float(interaction) * 252, 6),
            "total_excess_return": round(float(((pw - bw) * rets).sum(axis=1).mean()) * 252, 6),
        }

    # With sector mapping
    groups = sorted(set(group_mapping.values()))
    alloc_effect = 0.0
    select_effect = 0.0
    interact_effect = 0.0

    for grp in groups:
        grp_tickers = [t for t in common_tickers if group_mapping.get(t) == grp]
        if not grp_tickers:
            continue

        pw_g = pw[grp_tickers].sum(axis=1)
        bw_g = bw[grp_tickers].sum(axis=1)
        ret_g = rets[grp_tickers].mean(axis=1)

        alloc_effect += float(((bw_g * (ret_g - rets.mean(axis=1)))).mean())
        select_effect += float(((pw_g * (ret_g - rets[grp_tickers].mean(axis=1)))).mean())

    return {
        "allocation_effect": round(alloc_effect * 252, 6),
        "selection_effect": round(select_effect * 252, 6),
        "interaction_effect": round(interact_effect * 252, 6),
        "n_groups": len(groups),
        "n_assets": len(common_tickers),
    }


def report_markdown(attribution: Dict) -> str:
    """Generate markdown attribution report."""
    lines = [
        "# Performance Attribution Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Factor Regression",
        "",
    ]

    if "error" in attribution:
        lines.append(f"**Error**: {attribution['error']}")
        return "\n".join(lines)

    lines += [
        f"**R^2**: {attribution.get('r_squared', 0):.4f}  ",
        f"**Adj R^2**: {attribution.get('adj_r_squared', 0):.4f}  ",
        f"**Alpha (annual)**: {attribution.get('alpha_annual', 0):.4%}  ",
        f"**N**: {attribution.get('n_obs', 0)}  ",
        "",
        "| Factor | Exposure | T-Stat | P-Value | Daily Contrib | Annual Contrib |",
        "|--------|----------|--------|---------|---------------|---------------|",
    ]

    exposures = attribution.get("exposures", {})
    tstats = attribution.get("t_statistics", {})
    pvals = attribution.get("p_values", {})
    contribs = attribution.get("factor_contributions", {})

    for name in exposures:
        contrib = contribs.get(name, 0)
        sig = "**" if pvals.get(name, 1) < 0.05 else ""
        lines.append(
            f"| {name}{sig} | {exposures[name]:.4f} | {tstats.get(name, 0):.2f} | "
            f"{pvals.get(name, 1):.3f} | {contrib:.4%} | {contrib * 252:.2%} |"
        )

    lines.append("")
    lines.append("*Auto-generated by performance_attribution.py*")
    return "\n".join(lines)


def _make_demo_data(n: int = 504, n_factors: int = 4, seed: int = 42
                    ) -> Tuple[pd.Series, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")

    # Factor returns
    factors = pd.DataFrame({
        "MKT": rng.normal(0.0005, 0.012, n),
        "SMB": rng.normal(0.0002, 0.008, n),
        "HML": rng.normal(0.0001, 0.009, n),
        "MOM": rng.normal(0.0003, 0.010, n),
    }, index=dates)

    # Portfolio = 1.0 * MKT + 0.3 * SMB - 0.2 * HML + 0.15 * MOM + alpha + noise
    alpha = 0.0002
    port = (1.0 * factors["MKT"] + 0.3 * factors["SMB"]
            - 0.2 * factors["HML"] + 0.15 * factors["MOM"]
            + alpha + rng.normal(0, 0.003, n))
    port.name = "portfolio"

    return port, factors


def main():
    port_ret, factor_ret = _make_demo_data(504, 4, seed=7)
    attr = factor_regression(port_ret, factor_ret)
    report = report_markdown(attr)
    print(report)

    # Rolling attribution
    roll = rolling_attribution(port_ret, factor_ret, window=252, step=63)
    if not roll.empty:
        print(f"\nRolling exposures ({len(roll)} periods):")
        print(roll.tail().to_string())

    summary = contribution_summary(attr)
    print("\nContribution summary:")
    print(summary.to_string())


if __name__ == "__main__":
    main()
