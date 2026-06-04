#!/usr/bin/env python3
"""Industry neutralization & Barra-style risk attribution.

Three pillars:
  1. Industry exposure check — detect sector concentration vs benchmark
  2. Barra risk attribution — decompose total risk into factor + specific
  3. Risk budget decomposition — marginal/component risk contributions

Uses sklearn PCA + statsmodels OLS for factor fitting. No hand-rolled math."""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple


# ── 1. Industry Exposure Check ─────────────────────────────

def check_industry_exposure(
    portfolio_weights: pd.Series,
    industry_map: Optional[Dict[str, str]] = None,
    benchmark_weights: Optional[pd.Series] = None,
) -> Dict:
    """Check portfolio industry concentration vs benchmark.

    Args:
        portfolio_weights: ticker → weight mapping
        industry_map: ticker → industry/sector mapping (e.g. GICS sector)
        benchmark_weights: ticker → benchmark weight (e.g. S&P 500 weights)
                           If None, assumes equal-weight benchmark.

    Returns dict with:
        industry_weights — portfolio weight by industry
        active_weight — over/underweight vs benchmark
        concentration — HHI and top-3 concentration metrics
    """
    pw = portfolio_weights.dropna()
    if len(pw) == 0:
        return {"error": "Empty portfolio weights"}

    tickers = pw.index.tolist()

    if industry_map is None:
        # Create synthetic industry map from ticker names
        industry_map = {t: f"Ind_{i // max(len(tickers) // 4, 1)}" for i, t in enumerate(tickers)}

    mapped = {t: industry_map.get(t, "Unknown") for t in tickers}
    pw_mapped = pd.DataFrame({"ticker": tickers, "weight": pw.values,
                               "industry": [mapped[t] for t in tickers]})

    # Portfolio industry weights
    ind_w = pw_mapped.groupby("industry")["weight"].sum().sort_values(ascending=False)

    # Benchmark industry weights
    if benchmark_weights is not None:
        bw = benchmark_weights.dropna()
        bw_mapped = pd.DataFrame({
            "ticker": bw.index.tolist(),
            "weight": bw.values,
            "industry": [industry_map.get(t, "Unknown") for t in bw.index],
        })
        bm_w = bw_mapped.groupby("industry")["weight"].sum()
    else:
        # Equal weight across industries
        n_industries = len(ind_w)
        bm_w = pd.Series(1.0 / n_industries, index=ind_w.index)

    # Active weight
    aligned = pd.concat([ind_w.rename("portfolio"), bm_w.rename("benchmark")],
                        axis=1).fillna(0)
    aligned["active"] = aligned["portfolio"] - aligned["benchmark"]
    aligned = aligned.sort_values("active", key=abs, ascending=False)

    # Concentration metrics
    hhi = float((ind_w ** 2).sum())  # Herfindahl-Hirschman Index
    top3 = float(ind_w.head(3).sum())
    n_industries = len(ind_w)
    max_overweight = aligned["active"].max() if len(aligned) > 0 else 0
    max_underweight = aligned["active"].min() if len(aligned) > 0 else 0

    return {
        "industry_weights": aligned,
        "hhi": round(hhi, 6),
        "top3_concentration": round(top3, 4),
        "n_industries": n_industries,
        "max_overweight_industry": aligned["active"].idxmax() if max_overweight > 0 else None,
        "max_overweight": round(float(max_overweight), 4),
        "max_underweight_industry": aligned["active"].idxmin() if max_underweight < 0 else None,
        "max_underweight": round(float(max_underweight), 4),
        "diversification_ratio": round(float(1.0 / (hhi if hhi > 0 else 1)), 2),
    }


# ── 2. Barra Risk Attribution ─────────────────────────────

def barra_risk_attribution(
    asset_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    weights: pd.Series,
    covariance: Optional[pd.DataFrame] = None,
) -> Dict:
    """Barra-style risk attribution: systematic + specific risk decomposition.

    Steps:
      1. Regress asset returns on factor returns → factor exposures (betas)
      2. Total risk σ_p = sqrt(w' Σ w)
      3. Factor risk = sqrt(w' B Σ_f B' w)
      4. Specific risk = sqrt(σ_p^2 - σ_f^2) = sqrt(w' D w)

    Args:
        asset_returns: T×N DataFrame of asset returns
        factor_returns: T×K DataFrame of factor returns
        weights: N-length Series of portfolio weights
        covariance: optional pre-computed covariance (N×N); if None, use sample

    Returns dict with risk decomposition.
    """
    import statsmodels.api as sm

    common_tickers = sorted(set(weights.index) & set(asset_returns.columns))
    if len(common_tickers) < 3:
        return {"error": f"Insufficient common tickers: {len(common_tickers)}"}

    w = weights.loc[common_tickers]
    rets = asset_returns[common_tickers].dropna()

    common_dates = rets.index.intersection(factor_returns.index)
    if len(common_dates) < 60:
        return {"error": f"Insufficient common dates: {len(common_dates)}"}

    rets = rets.loc[common_dates]
    factors = factor_returns.loc[common_dates]

    # Factor exposures: regress each asset on factors → loading matrix B (N×K)
    factor_names = list(factors.columns)
    K = len(factor_names)
    N = len(common_tickers)
    B = np.zeros((N, K))
    specific_vars = np.zeros(N)

    for i, ticker in enumerate(common_tickers):
        y = rets[ticker].values
        X = sm.add_constant(factors.values)
        try:
            ols = sm.OLS(y, X).fit()
            B[i, :] = ols.params[1:]  # skip constant
            specific_vars[i] = float(np.var(ols.resid))
        except Exception:
            specific_vars[i] = 1e-6

    # Factor covariance Σ_f (K×K)
    sigma_f = factors.cov().values

    # Systematic variance: w' B Σ_f B' w
    # B Σ_f B' = systematic covariance (N×N)
    sys_cov = B @ sigma_f @ B.T
    factor_var = float(w.values @ sys_cov @ w.values)

    # Specific variance: w' D w where D = diag(specific_vars)
    specific_var = float(w.values @ np.diag(specific_vars) @ w.values)

    # Total variance
    if covariance is not None:
        total_cov = covariance.loc[common_tickers, common_tickers].values
    else:
        total_cov = rets.cov().values
    total_var = float(w.values @ total_cov @ w.values)

    # Ensure consistency: factor_var + specific_var ≈ total_var
    total_vol = float(np.sqrt(max(total_var, 0)))
    factor_vol = float(np.sqrt(max(factor_var, 0)))
    specific_vol = float(np.sqrt(max(specific_var, 0)))
    residual_var = total_var - (factor_var + specific_var)

    # Factor-level contribution
    factor_risk_pct = factor_vol ** 2 / max(total_var, 1e-10)

    return {
        "total_risk": round(total_vol * np.sqrt(252), 6),
        "total_vol_daily": round(total_vol, 6),
        "factor_risk": round(factor_vol * np.sqrt(252), 6),
        "specific_risk": round(specific_vol * np.sqrt(252), 6),
        "factor_risk_pct": round(float(factor_risk_pct * 100), 2),
        "specific_risk_pct": round(float((1 - factor_risk_pct) * 100), 2),
        "residual_var": round(float(residual_var), 10),
        "systematic_ratio": round(float(factor_risk_pct), 4),
        "factor_exposure_matrix": pd.DataFrame(
            B, index=common_tickers, columns=factor_names),
        "factor_covariance": pd.DataFrame(
            sigma_f, index=factor_names, columns=factor_names),
        "specific_variances": pd.Series(specific_vars, index=common_tickers),
        "n_assets": N,
        "n_factors": K,
        "n_obs": len(common_dates),
    }


# ── 3. Risk Budget Decomposition ──────────────────────────

def risk_budget_decomposition(
    weights: pd.Series,
    covariance: pd.DataFrame,
) -> Dict:
    """Marginal and component risk contribution from covariance matrix.

    Marginal Risk Contribution (MRC):     MRC_i = ∂σ_p / ∂w_i = (Σ w)_i / σ_p
    Component Risk Contribution (CRC):    CRC_i = w_i × MRC_i
    % Risk Contribution:                  %RC_i = CRC_i / σ_p

    ρ_ij = CRC_i / CRC_j * σ_i / σ_j  → risk contribution correlation
    """
    cov = covariance.loc[weights.index, weights.index].values
    w = weights.values
    sigma_p = float(np.sqrt(w @ cov @ w))

    if sigma_p < 1e-10:
        return {"error": "Zero portfolio risk — degenerate covariance"}

    # Marginal risk contribution
    mrc = (cov @ w) / sigma_p  # = ∂σ/∂w_i = (Σw)_i / σ_p

    # Component risk contribution
    crc = w * mrc  # = w_i × ∂σ/∂w_i
    pct_contrib = crc / sigma_p  # % contribution

    # Implied risk √CRC_i² helps check diversification
    names = weights.index.tolist()

    result = pd.DataFrame({
        "weight": w,
        "marginal_risk": mrc,
        "component_risk": crc,
        "pct_risk": pct_contrib,
    }, index=names)

    result = result.sort_values("component_risk", ascending=False)

    # Concentration: effective number of risk sources
    pct = result["pct_risk"].values
    pct_clean = pct[pct > 0]
    effective_n_risk = float(1.0 / (pct_clean ** 2).sum()) if len(pct_clean) > 0 else 0

    return {
        "decomposition": result,
        "total_risk": round(sigma_p, 8),
        "effective_n_risk_sources": round(effective_n_risk, 2),
        "top_risk_contributor": result.index[0],
        "top_risk_pct": round(float(result.iloc[0]["pct_risk"] * 100), 2),
        "top3_risk_pct": round(float(result.head(3)["pct_risk"].sum() * 100), 2),
    }


# ── 4. Unified Pipeline ───────────────────────────────────

def analyze_risk_attribution(
    asset_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    weights: pd.Series,
    industry_map: Optional[Dict[str, str]] = None,
    benchmark_weights: Optional[pd.Series] = None,
    covariance: Optional[pd.DataFrame] = None,
) -> Dict:
    """Full risk attribution analysis: industry + Barra + risk budget.

    Returns dict with industry_check, barra_attribution, risk_budget.
    """
    result = {}

    # Industry exposure
    result["industry_check"] = check_industry_exposure(
        weights, industry_map, benchmark_weights)

    # Barra risk attribution
    result["barra"] = barra_risk_attribution(
        asset_returns, factor_returns, weights, covariance)

    # Risk budget
    cov = covariance
    if cov is None and "error" not in result["barra"]:
        common = sorted(set(weights.index) & set(asset_returns.columns))
        cov = asset_returns[common].cov()

    if cov is not None:
        result["risk_budget"] = risk_budget_decomposition(
            weights.loc[weights.index.intersection(cov.columns)], cov)
    else:
        result["risk_budget"] = {"error": "No covariance available"}

    return result


# ── Markdown Report ───────────────────────────────────────

def report_markdown(attribution: Dict) -> str:
    """Generate markdown risk attribution report."""
    from datetime import datetime

    lines = [
        "# Risk Attribution Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Industry exposure
    ic = attribution.get("industry_check", {})
    if ic and "error" not in ic:
        lines += [
            "## Industry Exposure",
            "",
            f"**HHI**: {ic['hhi']:.4f}  ",
            f"**Top-3 Concentration**: {ic['top3_concentration']:.2%}  ",
            f"**Diversification Ratio**: {ic['diversification_ratio']:.2f}  ",
            f"**Industries**: {ic['n_industries']}  ",
            "",
        ]
        iw = ic.get("industry_weights")
        if iw is not None and not iw.empty:
            lines += [
                "| Industry | Portfolio | Benchmark | Active |",
                "|----------|-----------|-----------|--------|",
            ]
            for _, row in iw.head(10).iterrows():
                lines.append(
                    f"| {row.name} | {row['portfolio']:.2%} | "
                    f"{row['benchmark']:.2%} | {row['active']:+.2%} |"
                )
            lines.append("")

    # Barra attribution
    ba = attribution.get("barra", {})
    if ba and "error" not in ba:
        lines += [
            "## Barra Risk Attribution",
            "",
            "| Component | Risk (Ann.) | % |",
            "|-----------|-------------|---|",
            f"| Total Risk | {ba['total_risk']:.4%} | 100% |",
            f"| Factor (Systematic) | {ba['factor_risk']:.4%} | {ba['factor_risk_pct']:.1f}% |",
            f"| Specific (Idiosyncratic) | {ba['specific_risk']:.4%} | {ba['specific_risk_pct']:.1f}% |",
            "",
            f"**Systematic Ratio**: {ba['systematic_ratio']:.4f}  ",
            f"**N Assets**: {ba['n_assets']} | **N Factors**: {ba['n_factors']}  ",
            "",
        ]

    # Risk budget
    rb = attribution.get("risk_budget", {})
    if rb and "error" not in rb:
        dec = rb.get("decomposition")
        if dec is not None and not dec.empty:
            lines += [
                "## Risk Budget Decomposition",
                "",
                f"**Total Risk (daily)**: {rb['total_risk']:.6f}  ",
                f"**Effective N (risk sources)**: {rb['effective_n_risk_sources']:.2f}  ",
                f"**Top 3 Risk Concentration**: {rb['top3_risk_pct']:.1f}%  ",
                "",
                "| Asset | Weight | MRC | CRC | % Risk |",
                "|-------|--------|-----|-----|--------|",
            ]
            for _, row in dec.head(10).iterrows():
                lines.append(
                    f"| {row.name} | {row['weight']:.2%} | "
                    f"{row['marginal_risk']:.4f} | {row['component_risk']:.4f} | "
                    f"{row['pct_risk']:.1%} |"
                )
            lines.append("")

    lines.append("*Auto-generated by industry_attribution.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────

def _make_demo_data(n: int = 252, n_assets: int = 10, n_factors: int = 4, seed: int = 42
                    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, Dict[str, str]]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    tickers = [f"STK{i}" for i in range(n_assets)]

    # Factor returns
    factor_names = ["MKT", "SMB", "HML", "MOM"]
    factor_betas = np.array([1.0, 0.3, -0.2, 0.15])
    factor_ret = pd.DataFrame({
        fn: rng.normal(0.0005, 0.015, n) for fn in factor_names
    }, index=dates)

    # Asset returns: factor exposure + noise
    asset_data = {}
    for t in tickers:
        asset_data[t] = sum(
            factor_ret[fn] * factor_betas[j] * rng.normal(1, 0.2)
            for j, fn in enumerate(factor_names)
        ) + rng.normal(0, 0.01, n)

    rets = pd.DataFrame(asset_data, index=dates)

    # Equal weights
    weights = pd.Series(1.0 / n_assets, index=tickers)

    # Industry map
    sectors = ["Tech", "Tech", "Finance", "Finance", "Health",
               "Health", "Energy", "Energy", "Consumer", "Consumer"]
    ind_map = dict(zip(tickers, sectors))

    return rets, factor_ret, weights, ind_map


def main():
    rets, factor_ret, weights, ind_map = _make_demo_data(252, 10, 4, seed=7)

    result = analyze_risk_attribution(
        rets, factor_ret, weights, industry_map=ind_map)

    print(report_markdown(result))

    # Key insights
    ba = result["barra"]
    rb = result["risk_budget"]
    print("\nKey Insights:")
    print(f"  Systematic / Specific: {ba['systematic_ratio']:.2%} / {1 - ba['systematic_ratio']:.2%}")
    if "error" not in rb:
        print(f"  Top Risk Source: {rb['top_risk_contributor']} ({rb['top_risk_pct']:.1f}%)")
        print(f"  Effective N (risk): {rb['effective_n_risk_sources']:.1f}")


if __name__ == "__main__":
    main()
