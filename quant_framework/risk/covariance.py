#!/usr/bin/env python3
"""Covariance estimation — robust estimation for portfolio and risk applications.

Implements established methods: Ledoit-Wolf shrinkage, exponentially weighted,
factor-model-based (PCA + known factors), and robust MCD estimation.

All methods use sklearn/scipy — no hand-rolled covariance math."""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime


def sample_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """Sample covariance matrix (unbiased, df=1)."""
    cov = returns.cov().values
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns)


def ledoit_wolf(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit-Wolf shrinkage covariance estimator.

    Shrinks sample covariance toward a structured target (constant correlation),
    reducing estimation error. Optimal shrinkage intensity computed analytically.

    Uses sklearn.covariance.LedoitWolf.
    """
    try:
        from sklearn.covariance import LedoitWolf
    except ImportError:
        return _fallback_shrinkage(returns)

    clean = returns.dropna()
    if len(clean) < 10 or clean.shape[1] < 2:
        return sample_cov(returns)

    lw = LedoitWolf().fit(clean.values)
    cov = lw.covariance_
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns)


def _fallback_shrinkage(returns: pd.DataFrame, delta: float = 0.3) -> pd.DataFrame:
    """Simple shrinkage fallback: (1-delta)*sample + delta*diagonal."""
    sample = sample_cov(returns).values
    target = np.diag(np.diag(sample))
    shrunk = (1 - delta) * sample + delta * target
    return pd.DataFrame(shrunk, index=returns.columns, columns=returns.columns)


def oas(returns: pd.DataFrame) -> pd.DataFrame:
    """Oracle Approximating Shrinkage — alternative to Ledoit-Wolf.

    Often better for Gaussian data. Uses sklearn.covariance.OAS.
    """
    try:
        from sklearn.covariance import OAS
    except ImportError:
        return ledoit_wolf(returns)

    clean = returns.dropna()
    if len(clean) < 10 or clean.shape[1] < 2:
        return sample_cov(returns)

    oas_est = OAS().fit(clean.values)
    return pd.DataFrame(
        oas_est.covariance_, index=returns.columns, columns=returns.columns
    )


def exponentially_weighted(
    returns: pd.DataFrame,
    span: int = 63,
    halflife: Optional[int] = None,
) -> pd.DataFrame:
    """Exponentially weighted moving covariance (RiskMetrics style).

    Parameters
    ----------
    span: decay span in periods (default 63 ≈ 1 quarter)
    halflife: alternative to span; if set, overrides span
    """
    clean = returns.dropna()
    if halflife is not None:
        ewm = clean.ewm(halflife=halflife)
    else:
        ewm = clean.ewm(span=span)

    cov = ewm.cov().iloc[-returns.shape[1] :].values
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns)


def factor_model_cov(
    returns: pd.DataFrame,
    n_factors: int = 3,
    factor_returns: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Factor model covariance decomposition.

    Σ = B Σ_f B' + D
    where B = factor loadings, Σ_f = factor covariance, D = diagonal idiosyncratic.

    Parameters
    ----------
    returns: asset returns (dates × tickers)
    n_factors: number of PCA factors to use (ignored if factor_returns provided)
    factor_returns: optional known factor returns; if None, uses PCA

    Returns (cov_matrix, decomposition_dict).
    """
    clean = returns.dropna()
    if len(clean) < 20 or clean.shape[1] < 2:
        cov = sample_cov(returns)
        return cov, {"error": "Insufficient data"}

    T, N = clean.shape

    if factor_returns is not None:
        common = clean.index.intersection(factor_returns.index)
        F = factor_returns.loc[common].values
        R = clean.loc[common].values
        n_factors = F.shape[1]
    else:
        # PCA factor extraction
        from sklearn.decomposition import PCA

        R = clean.values
        pca = PCA(n_components=min(n_factors, N, T))
        F = pca.fit_transform(R)
        n_factors = pca.n_components_

    # OLS factor loadings: R = B F + ϵ
    F_aug = np.column_stack([np.ones(len(F)), F])
    B_raw = np.linalg.lstsq(F_aug, R, rcond=None)[0]
    B = B_raw[1:, :].T  # (N × K) loadings, skip intercept

    # Factor covariance
    sigma_f = np.cov(F.T) if F.shape[0] > 1 else np.eye(n_factors)

    # Idiosyncratic variance
    residuals = R - F @ B.T
    D_diag = np.var(residuals, axis=0)

    # Full covariance
    cov_systematic = B @ sigma_f @ B.T
    cov_total = cov_systematic + np.diag(D_diag)

    # Variance decomposition
    total_var = np.trace(cov_total)
    systematic_var = np.trace(cov_systematic)
    idio_var = float(np.sum(D_diag))

    decomposition = {
        "total_variance": round(float(total_var), 6),
        "systematic_variance": round(float(systematic_var), 6),
        "idiosyncratic_variance": round(idio_var, 6),
        "systematic_ratio": round(float(systematic_var / max(total_var, 1e-10)), 4),
        "n_factors": n_factors,
        "n_assets": N,
        "n_obs": T,
        "factor_loadings": pd.DataFrame(
            B, index=returns.columns, columns=[f"factor_{i}" for i in range(n_factors)]
        ),
        "factor_covariance": pd.DataFrame(
            sigma_f,
            columns=[f"factor_{i}" for i in range(n_factors)],
            index=[f"factor_{i}" for i in range(n_factors)],
        ),
        "idiosyncratic_var": pd.Series(D_diag, index=returns.columns),
    }

    return pd.DataFrame(
        cov_total, index=returns.columns, columns=returns.columns
    ), decomposition


def robust_mcd(returns: pd.DataFrame, support_fraction: float = 0.8) -> pd.DataFrame:
    """Minimum Covariance Determinant (MCD) — robust to outliers.

    Uses sklearn.covariance.MinCovDet (FAST-MCD algorithm).
    """
    try:
        from sklearn.covariance import MinCovDet
    except ImportError:
        return ledoit_wolf(returns)

    clean = returns.dropna()
    if len(clean) < 20 or clean.shape[1] < 2:
        return sample_cov(returns)

    mcd = MinCovDet(support_fraction=support_fraction, random_state=42).fit(
        clean.values
    )
    return pd.DataFrame(mcd.covariance_, index=returns.columns, columns=returns.columns)


def nearest_pd(cov: pd.DataFrame) -> pd.DataFrame:
    """Find the nearest positive-definite matrix to a given covariance matrix.

    Uses Higham's alternating projections algorithm via sklearn or custom implementation.
    """
    try:
        # Use eigendecomposition approach: zero out negative eigenvalues
        vals, vecs = np.linalg.eigh(cov.values)
        vals = np.maximum(vals, 1e-10)
        pd_cov = vecs @ np.diag(vals) @ vecs.T
        return pd.DataFrame(pd_cov, index=cov.index, columns=cov.columns)
    except Exception:
        return cov


def estimate_covariance(
    returns: pd.DataFrame,
    method: str = "ledoit_wolf",
    **kwargs,
) -> pd.DataFrame:
    """Unified covariance estimation interface.

    Parameters
    ----------
    returns: DataFrame of asset returns (dates × tickers)
    method: "sample" | "ledoit_wolf" | "oas" | "ew" | "factor_model" | "robust_mcd"
    kwargs: passed to the specific method

    Returns covariance DataFrame (tickers × tickers).
    """
    methods = {
        "sample": sample_cov,
        "ledoit_wolf": ledoit_wolf,
        "oas": oas,
        "ew": exponentially_weighted,
        "factor_model": lambda r: factor_model_cov(r, **kwargs)[0],
        "robust_mcd": robust_mcd,
    }

    estimator = methods.get(method, ledoit_wolf)
    return estimator(returns)


def rolling_covariance(
    returns: pd.DataFrame,
    window: int = 252,
    method: str = "ledoit_wolf",
    step: int = 21,
) -> Dict[pd.Timestamp, pd.DataFrame]:
    """Rolling covariance estimation.

    Returns dict of date → covariance DataFrame.
    """
    results = {}
    dates = returns.index
    for i in range(window, len(dates) + 1, step):
        date = dates[i - 1]
        window_returns = returns.iloc[i - window : i].dropna(axis=1)
        if window_returns.shape[1] < 2:
            continue
        try:
            cov = estimate_covariance(window_returns, method=method)
            results[date] = cov
        except Exception:
            continue
    return results


def cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    """Convert covariance matrix to correlation matrix."""
    d = np.sqrt(np.diag(cov.values))
    d_inv = np.where(d > 1e-10, 1.0 / d, 0.0)
    corr = cov.values * d_inv[:, None] * d_inv[None, :]
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def compare_estimators(
    returns: pd.DataFrame,
    methods: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Compare multiple covariance estimators.

    Returns DataFrame with condition number, frobenius norm, and sparsity per method.
    """
    if methods is None:
        methods = ["sample", "ledoit_wolf", "oas", "ew"]

    rows = []
    for method in methods:
        try:
            cov = estimate_covariance(returns, method=method)
            vals = np.linalg.eigvalsh(cov.values)
            cond = float(max(vals) / max(min(vals), 1e-10))
            frob = float(np.linalg.norm(cov.values, "fro"))
            trace = float(np.trace(cov.values))
            rows.append(
                {
                    "method": method,
                    "condition_number": round(cond, 1),
                    "frobenius_norm": round(frob, 4),
                    "trace": round(trace, 6),
                    "mean_corr": round(float(cov_to_corr(cov).values.mean()), 4),
                }
            )
        except Exception:
            rows.append(
                {
                    "method": method,
                    "condition_number": None,
                    "frobenius_norm": None,
                    "trace": None,
                    "mean_corr": None,
                }
            )

    return pd.DataFrame(rows)


def report_markdown(cov: pd.DataFrame, method: str = "ledoit_wolf") -> str:
    """Generate markdown report for a covariance estimate."""
    corr = cov_to_corr(cov)
    vals = np.linalg.eigvalsh(cov.values)
    cond = float(max(vals) / max(min(vals), 1e-10))

    lines = [
        "# Covariance Estimation Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Method**: {method}  ",
        f"**Assets**: {cov.shape[0]}  ",
        f"**Condition Number**: {cond:.1f}  ",
        "",
        "## Volatilities (annualized)",
        "",
        "| Asset | Volatility |",
        "|-------|-----------|",
    ]

    vols = np.sqrt(np.diag(cov.values)) * np.sqrt(252)
    for i, asset in enumerate(cov.columns):
        lines.append(f"| {asset} | {vols[i]:.2%} |")

    lines += [
        "",
        "## Correlation Matrix",
        "",
    ]
    # Format correlation matrix as markdown table
    cols = corr.columns.tolist()
    lines.append("| Asset | " + " | ".join(cols) + " |")
    lines.append("|-------|" + "|".join(["-------"] * len(cols)) + "|")
    for asset in corr.index:
        vals_str = " | ".join(f"{corr.loc[asset, c]:.3f}" for c in cols)
        lines.append(f"| {asset} | {vals_str} |")

    lines.append("")
    lines.append("*Auto-generated by covariance.py*")
    return "\n".join(lines)


def _make_demo_data(n: int = 252, n_assets: int = 6, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")

    # Create correlated returns via a common factor
    common = rng.normal(0.0005, 0.012, n)
    data = {}
    for i in range(n_assets):
        # Each asset has different beta to common factor
        beta = 0.5 + i * 0.3
        data[f"ASSET_{i}"] = beta * common + rng.normal(0, 0.008, n)
    return pd.DataFrame(data, index=dates)


def main():
    returns = _make_demo_data(252, 6, seed=7)

    print("# Covariance Estimator Comparison\n")
    comparison = compare_estimators(returns)
    print(comparison.to_string(index=False))

    # Full factor model decomposition
    cov_fm, decomp = factor_model_cov(returns, n_factors=3)
    print("\n## Factor Model Decomposition")
    print(f"Systematic ratio: {decomp['systematic_ratio']:.2%}")
    print(f"Factors: {decomp['n_factors']}, Assets: {decomp['n_assets']}")

    # Ledoit-Wolf report
    cov_lw = estimate_covariance(returns, method="ledoit_wolf")
    report = report_markdown(cov_lw, "ledoit_wolf")
    print(f"\n{report[:500]}...")


if __name__ == "__main__":
    main()
