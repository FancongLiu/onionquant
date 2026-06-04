"""portfolio_optimizer.py — 组合优化: Mean-Variance, Risk Parity,
HRP, Black-Litterman, Kelly Criterion.
使用 Riskfolio-Lib (github.com/dcajasn/Riskfolio-Lib) 和
PyPortfolioOpt (github.com/PyPortfolio/PyPortfolioOpt) 替代手搓实现。"""

import numpy as np
import pandas as pd
import riskfolio as rp
from pypfopt import HRPOpt, BlackLittermanModel
from sklearn.covariance import LedoitWolf


def _shrunk_cov(returns: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf shrinkage covariance — more robust than np.cov."""
    if returns.shape[0] < 5 or returns.shape[1] < 2:
        return np.cov(returns, rowvar=False, ddof=1)
    lw = LedoitWolf().fit(returns)
    return lw.covariance_


def _port_ret_risk(w, mu_d, cov_d):
    """计算年化收益与年化风险"""
    return float(w @ mu_d * 252), float(np.sqrt(w @ cov_d @ w) * np.sqrt(252))


# ---- 1. Mean-Variance ----
def mean_variance_optimize(returns, max_weight=1.0):
    r = np.asarray(returns, dtype=float)
    df = pd.DataFrame(r)
    port = rp.Portfolio(returns=df, upperlng=max_weight, lowerlng=0.0)
    port.assets_stats(method_mu="hist", method_cov="hist")
    w_df = port.optimization(model="Classic", rm="MV", obj="Sharpe", rf=0, l=0)
    w = w_df["weights"].values
    pret, prisk = _port_ret_risk(w, port.mu.values.flatten(), port.cov.values)
    return {"weights": w, "expected_return": pret, "expected_risk": prisk}


# ---- 2. Risk Parity ----
def risk_parity(returns, max_weight=1.0):
    r = np.asarray(returns, dtype=float)
    df = pd.DataFrame(r)
    port = rp.Portfolio(returns=df, upperlng=max_weight, lowerlng=0.0)
    port.assets_stats(method_mu="hist", method_cov="hist")
    w_df = port.rp_optimization(model="Classic", rm="MV")
    w = w_df["weights"].values
    pret, prisk = _port_ret_risk(w, port.mu.values.flatten(), port.cov.values)
    return {"weights": w, "expected_return": pret, "expected_risk": prisk}


# ---- 3. HRP ----
def hierarchical_risk_parity(returns, max_weight=1.0):
    r = np.asarray(returns, dtype=float)
    df = pd.DataFrame(r)
    hrp = HRPOpt(df)
    w_dict = hrp.optimize()
    w = np.array(list(w_dict.values()))
    w = np.clip(w, 0, max_weight)
    w /= w.sum()
    md = np.mean(r, axis=0)
    cd = _shrunk_cov(r)
    pret, prisk = _port_ret_risk(w, md, cd)
    return {"weights": w, "expected_return": pret, "expected_risk": prisk}


# ---- 4. Black-Litterman ----
def black_litterman(returns, views=None, confidences=None, tau=0.05, max_weight=1.0):
    r = np.asarray(returns, dtype=float)
    T, N = r.shape
    tickers = [f"A{i}" for i in range(N)]
    cd = _shrunk_cov(r)
    md = np.mean(r, axis=0)
    S = pd.DataFrame(cd * 252, index=tickers, columns=tickers)
    pi = pd.Series(md * 252, index=tickers)

    if views is None:
        w = np.ones(N) / N
        pret, prisk = _port_ret_risk(w, md, cd)
        return {"weights": w, "expected_return": pret, "expected_risk": prisk}

    K = len(views)
    # P 矩阵 (K×N): 方向
    P_arr = np.zeros((K, N))
    Q_arr = np.zeros(K)
    view_conf = []
    view_items = list(views.items())
    for i, (asset_idx, (direction, magnitude)) in enumerate(view_items):
        P_arr[i, asset_idx] = direction
        Q_arr[i] = magnitude  # 年化预期收益
        view_conf.append(confidences.get(asset_idx, 0.5) if confidences else 0.5)

    # Omega: 以 view 收益率的方差缩放
    c_annual = cd * 252
    omega_arr = np.diag(
        [
            (1 - vc) / vc * (P_arr[i] @ c_annual @ P_arr[i])
            for i, vc in enumerate(view_conf)
        ]
    )
    P_df = pd.DataFrame(P_arr, columns=tickers)
    Q_s = pd.Series(Q_arr, index=[f"v{i}" for i in range(K)])
    omega_df = pd.DataFrame(
        omega_arr,
        index=[f"v{i}" for i in range(K)],
        columns=[f"v{i}" for i in range(K)],
    )
    bl = BlackLittermanModel(S, pi=pi, P=P_df, Q=Q_s, omega=omega_df, tau=tau)
    w_dict = bl.bl_weights()
    w = np.array([w_dict[t] for t in tickers])
    w = np.clip(w, 0, max_weight)
    w /= w.sum()
    pret, prisk = _port_ret_risk(w, md, cd)
    return {"weights": w, "expected_return": pret, "expected_risk": prisk}


# ---- 4b. Black-Litterman (riskfolio-lib) ----
def black_litterman_rp(
    returns,
    views=None,
    view_confidences=None,
    tau=0.05,
    delta=1.0,
    rf=0.0,
    max_weight=1.0,
):
    """Black-Litterman via riskfolio-lib — asset-level views using market-implied equilibrium.

    Args:
        returns: (T, N) numpy array of daily returns.
        views: dict {asset_index: (direction, magnitude)} or None for equilibrium.
        view_confidences: dict {asset_index: confidence 0-1} — higher = more confident.
        tau: uncertainty scaling of prior (default 0.05 = 5% uncertainty).
        delta: risk aversion for implied equilibrium returns.
        rf: risk-free rate.
        max_weight: single-asset weight cap.

    Returns:
        dict with weights, expected_return, expected_risk, implied_equilibrium, posterior_mu.

    Key difference from PyPortfolioOpt BL:
      - riskfolio-lib computes market-implied equilibrium returns from covariance + market weights.
      - Returns posterior covariance alongside posterior mean.
      - Supports Meucci's non-bayesian reference model alternative.
    """
    r = np.asarray(returns, dtype=float)
    T, N = r.shape
    tickers = [f"A{i}" for i in range(N)]
    df = pd.DataFrame(r, columns=tickers)

    # Market-implied equilibrium: equal-weight prior
    w_eq = np.ones(N) / N
    cov_matrix = df.cov().values * 252
    mu_hist = df.mean().values * 252
    # Implied equilibrium: pi = delta * Sigma * w_eq (reverse optimization)
    pi_implied = delta * cov_matrix @ w_eq

    # Build views: P (KxN pick matrix), Q (K view returns)
    if views is None:
        w = w_eq.copy()
        pret, prisk = _port_ret_risk(w, mu_hist, cov_matrix / 252)
        return {
            "weights": w,
            "expected_return": pret,
            "expected_risk": prisk,
            "implied_equilibrium": dict(zip(tickers, pi_implied)),
        }

    K = len(views)
    P_arr = np.zeros((K, N))
    Q_arr = np.zeros(K)
    for i, (asset_idx, (direction, magnitude)) in enumerate(views.items()):
        P_arr[i, asset_idx] = direction
        Q_arr[i] = magnitude

    P_df = pd.DataFrame(P_arr, columns=tickers)
    Q_s = pd.Series(Q_arr)

    # riskfolio-lib black_litterman
    try:
        bl_result = rp.black_litterman(
            X=df,
            w=w_eq,
            P=P_df,
            Q=Q_s,
            delta=delta,
            rf=rf,
            eq=True,
            method_mu="hist",
            method_cov="hist",
        )
        # bl_result is typically a dict with 'mu' (posterior) and 'cov'
        if isinstance(bl_result, dict):
            mu_post = bl_result.get("mu", pi_implied)
            cov_post = bl_result.get("cov", cov_matrix)
        else:
            mu_post = bl_result
            cov_post = cov_matrix
    except Exception:
        # Fallback: PyPortfolioOpt BL (already working)
        return black_litterman(
            returns,
            views=views,
            confidences=view_confidences,
            tau=tau,
            max_weight=max_weight,
        )

    # Optimize using Riskfolio-Lib (not hand-rolled pinv)
    mu_d = np.asarray(mu_post) / 252
    cov_d = np.asarray(cov_post) / 252
    N_valid = min(len(mu_d), len(cov_d))
    mu_d = mu_d[:N_valid]
    cov_d = cov_d[:N_valid, :N_valid]
    tickers_valid = tickers[:N_valid]
    try:
        port_post = rp.Portfolio(
            returns=df.iloc[:, :N_valid], upperlng=max_weight, lowerlng=0.0
        )
        port_post.mu = pd.DataFrame(mu_d[:, None], index=tickers_valid)
        port_post.cov = pd.DataFrame(cov_d, index=tickers_valid, columns=tickers_valid)
        w_df = port_post.optimization(model="Classic", rm="MV", obj="Sharpe", rf=0, l=0)
        w = w_df["weights"].values
    except Exception:
        # Fallback: closed-form MV if optimization fails
        try:
            inv_cov = np.linalg.pinv(cov_d)
            ones = np.ones(N_valid)
            w = inv_cov @ mu_d / (ones @ inv_cov @ mu_d)
            w = np.clip(w, 0, max_weight)
            w /= w.sum()
        except np.linalg.LinAlgError:
            w = np.ones(N_valid) / N_valid

    pret, prisk = _port_ret_risk(w, mu_d, cov_d)
    return {
        "weights": w,
        "expected_return": pret,
        "expected_risk": prisk,
        "implied_equilibrium": dict(zip(tickers[:N_valid], pi_implied[:N_valid])),
        "posterior_mu": dict(zip(tickers[:N_valid], mu_d * 252)),
    }


def black_litterman_bayesian(
    returns,
    factor_exposures,
    factor_returns,
    factor_views=None,
    factor_view_confidences=None,
    delta=1.0,
    rf=0.0,
    max_weight=1.0,
):
    """Bayesian Black-Litterman (BLB) via riskfolio-lib — factor-level views.

    Args:
        returns: (T, N) asset daily returns.
        factor_exposures: (N, K) factor loading matrix (B).
        factor_returns: (T, K) factor daily returns (F).
        factor_views: dict {factor_idx: (direction, magnitude)} — views on factors.
        factor_view_confidences: dict {factor_idx: confidence 0-1}.
        delta: risk aversion.
        rf: risk-free rate.
        max_weight: single-asset weight cap.

    Returns:
        dict with weights, expected_return, expected_risk, prior_alpha, posterior_alpha.

    Key insight: views on FACTORS (e.g., "momentum will outperform") flow through
    factor exposures to asset-level posterior returns. More robust than asset views
    because factor relationships are more stable.
    """
    r = np.asarray(returns, dtype=float)
    F = np.asarray(factor_returns, dtype=float)
    B = np.asarray(factor_exposures, dtype=float)

    T_a, N = r.shape
    K = F.shape[1]
    tickers = [f"A{i}" for i in range(N)]

    df_assets = pd.DataFrame(r, columns=tickers)

    # Factor views
    if factor_views:
        K_views = len(factor_views)
        P_f = np.zeros((K_views, K))
        Q_f = np.zeros(K_views)
        for i, (f_idx, (direction, magnitude)) in enumerate(factor_views.items()):
            P_f[i, f_idx] = direction
            Q_f[i] = magnitude
        P_f_df = pd.DataFrame(P_f)
        Q_f_s = pd.Series(Q_f)
    else:
        P_f_df = None
        Q_f_s = None

    try:
        port = rp.Portfolio(returns=df_assets)

        # BLB: use factor model to derive prior, then apply factor views
        blb = port.blfactors_stats(
            flavor="BLB",
            B=B,
            P_f=P_f_df,
            Q_f=Q_f_s,
            rf=rf,
            delta=delta,
            eq=True,
            method_mu="hist",
            method_cov="hist",
        )

        # Optimize using Riskfolio-Lib (port already has posterior from blfactors_stats)
        w_df = port.optimization(model="Classic", rm="MV", obj="Sharpe", rf=0, l=0)
        w = w_df["weights"].values

        # Compute return/risk from posterior stats
        mu_post = blb.get("mu", df_assets.mean().values)
        cov_post = blb.get("cov", df_assets.cov().values)
        mu_d = np.asarray(mu_post) / 252
        cov_d = np.asarray(cov_post) / 252
        pret, prisk = _port_ret_risk(w, mu_d, cov_d)
        return {
            "weights": w,
            "expected_return": pret,
            "expected_risk": prisk,
            "factor_model": "BLB",
            "n_factors": K,
        }
    except Exception:
        # Fallback to asset-level BL
        return black_litterman_rp(returns, delta=delta, rf=rf, max_weight=max_weight)


# ---- 4c. Unified BL entry point ----
def bl_optimize(returns, views=None, factor_data=None, method="auto", **kwargs):
    """Unified Black-Litterman optimization — auto-selects best variant.

    Args:
        returns: (T, N) asset daily returns.
        views: dict {asset_idx: (direction, annual_return)} — asset-level views.
        factor_data: optional dict with 'exposures' (N,K) and 'returns' (T,K) and
                     optional 'views' {factor_idx: (direction, magnitude)}.
        method: 'auto' | 'asset' | 'bayesian' | 'riskfolio'.

    Returns:
        dict with weights, expected_return, expected_risk, and method_used.
    """
    if method == "auto":
        if factor_data and "exposures" in factor_data and "returns" in factor_data:
            method = "bayesian"
        else:
            method = "riskfolio"

    if method == "bayesian":
        fv = factor_data.get("views") if factor_data else None
        result = black_litterman_bayesian(
            returns,
            factor_exposures=factor_data["exposures"],
            factor_returns=factor_data["returns"],
            factor_views=fv,
            **kwargs,
        )
    elif method == "riskfolio":
        result = black_litterman_rp(returns, views=views, **kwargs)
    else:
        result = black_litterman(returns, views=views, **kwargs)

    result["method_used"] = method
    return result


# ---- 5. Kelly ----
def kelly_criterion(returns, max_weight=1.0, risk_aversion=2.0):
    """Kelly/Log-Utility 组合优化，使用 Riskfolio-Lib。
    risk_aversion 越高越保守 (默认 2.0，近似原 fraction=0.25)."""
    r = np.asarray(returns, dtype=float)
    df = pd.DataFrame(r)
    port = rp.Portfolio(returns=df, upperlng=max_weight, lowerlng=0.0)
    port.assets_stats(method_mu="hist", method_cov="hist")
    w_df = port.optimization(
        model="Classic", rm="MV", obj="Utility", kelly="approx", rf=0, l=risk_aversion
    )
    w = w_df["weights"].values
    pret, prisk = _port_ret_risk(w, port.mu.values.flatten(), port.cov.values)
    return {"weights": w, "expected_return": pret, "expected_risk": prisk}


if __name__ == "__main__":
    np.random.seed(42)
    n_a, n_p = 5, 1000
    means = np.array([0.12, 0.10, 0.08, 0.15, 0.06]) / 252
    vols = np.array([0.20, 0.18, 0.15, 0.25, 0.12]) / np.sqrt(252)
    corr = np.eye(n_a)
    corr[0, 1] = corr[1, 0] = 0.6
    corr[0, 2] = corr[2, 0] = 0.3
    corr[1, 2] = corr[2, 1] = 0.4
    cs = np.outer(vols, vols) * corr
    np.fill_diagonal(cs, vols**2)
    sr = np.random.multivariate_normal(means, cs, n_p)
    methods = [
        ("Mean-Variance", mean_variance_optimize(sr)),
        ("Risk Parity", risk_parity(sr)),
        ("HRP", hierarchical_risk_parity(sr)),
        ("BL(no views)", black_litterman(sr)),
        ("Kelly(25%)", kelly_criterion(sr)),
    ]
    print("=" * 72, "\n组合优化对比\n", "=" * 72)
    print(f"{'方法':20s}{'年化收益':>10s}{'年化风险':>10s}{'权重':>30s}")
    print("-" * 72)
    for n_, r_ in methods:
        ws = ", ".join([f"{x:.2f}" for x in r_["weights"]])
        print(
            f"{n_:20s}{r_['expected_return']:>10.4f}"
            f"{r_['expected_risk']:>10.4f}  [{ws}]"
        )
