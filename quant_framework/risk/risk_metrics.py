"""risk_metrics.py — 风险指标: VaR/CVaR/最大回撤分析/
波动率/下行波动率/Sharpe/Sortino/Calmar/Beta.
使用 empyrical-reloaded (https://github.com/stefan-jansen/empyrical-reloaded)
替代手搓实现。"""

import numpy as np
from scipy.stats import norm, skew, kurtosis
import empyrical as ep


def _excess_kurtosis(x):
    """超额峰度（Fisher 定义, 正态分布=0）"""
    if len(x) < 4:
        return 0.0
    return float(kurtosis(x, bias=False))


# ---- VaR ----
def var_historical(returns, cl=0.95):
    return float(ep.value_at_risk(np.asarray(returns), cutoff=1 - cl))


def var_parametric(returns, cl=0.95):
    """empyrical 无参数化 VaR, 用 scipy 实现"""
    r = np.asarray(returns)
    mu, s = np.mean(r), np.std(r, ddof=1)
    z = float(np.abs(norm.ppf(1 - cl)))
    return mu - z * s


def var_cornish_fisher(returns, cl=0.95):
    """empyrical 无 Cornish-Fisher VaR, 用 scipy + 自定义实现"""
    r = np.asarray(returns)
    mu, s = np.mean(r), np.std(r, ddof=1)
    sk = float(skew(r, bias=False))
    ku = float(kurtosis(r, bias=False))  # excess kurtosis
    z = float(np.abs(norm.ppf(1 - cl)))
    z_cf = (
        z
        + (z**2 - 1) * sk / 6
        + (z**3 - 3 * z) * ku / 24
        - (2 * z**3 - 5 * z) * sk**2 / 36
    )
    return mu - s * z_cf


# ---- CVaR ----
def cvar(returns, cl=0.95):
    return float(ep.conditional_value_at_risk(np.asarray(returns), cutoff=1 - cl))


# ---- 回撤 ----
def max_drawdown(equity):
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 2:
        return 0.0
    rets = np.diff(eq) / eq[:-1]
    return float(ep.max_drawdown(rets))


def drawdown_analysis(equity):
    """empyrical 无此细化分析, 保留 numpy 实现"""
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 2:
        return {
            k: 0
            for k in (
                "max_drawdown",
                "start_idx",
                "end_idx",
                "recovery_idx",
                "duration",
            )
        }
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    end = int(np.argmin(dd))
    start = int(np.argmax(eq[: end + 1])) if end > 0 else 0
    rec = np.where(eq[end:] >= eq[start])[0]
    rec_idx = int(end + rec[0]) if len(rec) > 0 else len(eq) - 1
    return {
        "max_drawdown": float(dd[end]),
        "start_idx": start,
        "end_idx": end,
        "recovery_idx": rec_idx,
        "duration": rec_idx - start,
    }


# ---- 波动率 ----
def ann_vol(returns, ppy=252):
    return (
        float(ep.annual_volatility(np.asarray(returns), annualization=ppy))
        if len(returns) >= 2
        else 0.0
    )


def downside_vol(returns, target=0, ppy=252):
    return (
        float(
            ep.downside_risk(
                np.asarray(returns), required_return=target, annualization=ppy
            )
        )
        if len(returns) >= 2
        else 0.0
    )


# ---- 比率 ----
def sharpe_ratio(returns, rfr=0.02, ppy=252):
    if len(returns) < 2:
        return 0.0
    # empyrical 的 risk_free 是日频
    return float(
        ep.sharpe_ratio(np.asarray(returns), risk_free=rfr / ppy, annualization=ppy)
    )


def sortino_ratio(returns, rfr=0.02, target=0, ppy=252):
    # 注: 原实现同时使用 rfr 与 target 有歧义; 现用 empyrical 标准 Sortino,
    # required_return=target 作为最低可接受收益(MAR)
    return float(
        ep.sortino_ratio(np.asarray(returns), required_return=target, annualization=ppy)
    )


def calmar_ratio(returns, ppy=252):
    return float(ep.calmar_ratio(np.asarray(returns), annualization=ppy))


def beta(returns, mkt):
    return float(ep.beta(np.asarray(returns), np.asarray(mkt)))


# ---- 汇总 ----
def risk_metrics_summary(
    returns, market_returns=None, equity_curve=None, ppy=252, cl=0.95, rfr=0.02
):
    if equity_curve is None:
        equity_curve = np.cumprod(1 + np.asarray(returns))
    r = np.asarray(returns, dtype=float)
    eq = np.asarray(equity_curve, dtype=float)
    dd = drawdown_analysis(eq)
    out = {
        "年化收益(%)": ep.annual_return(r, annualization=ppy) * 100,
        "年化波动率(%)": ann_vol(r, ppy) * 100,
        "下行波动率(%)": downside_vol(r, 0, ppy) * 100,
        "Sharpe": sharpe_ratio(r, rfr, ppy),
        "Sortino": sortino_ratio(r, rfr, 0, ppy),
        "Calmar": calmar_ratio(r, ppy),
        "最大回撤(%)": dd["max_drawdown"] * 100,
        "回撤开始": dd["start_idx"],
        "回撤结束": dd["end_idx"],
        "回撤恢复": dd["recovery_idx"],
        "回撤持续(期)": dd["duration"],
        "VaR(Hist,%)": var_historical(r, cl) * 100,
        "VaR(Param,%)": var_parametric(r, cl) * 100,
        "VaR(CF,%)": var_cornish_fisher(r, cl) * 100,
        "CVaR(%)": cvar(r, cl) * 100,
        "偏度": float(skew(r, bias=False)),
        "超额峰度": _excess_kurtosis(r),
    }
    if market_returns is not None:
        out["Beta"] = beta(r, np.asarray(market_returns, dtype=float))
    return out


if __name__ == "__main__":
    np.random.seed(42)
    s = np.random.normal(0.12 / 252, 0.20 / np.sqrt(252), 1000)
    m = np.random.normal(0.08 / 252, 0.15 / np.sqrt(252), 1000)
    eq = np.cumprod(1 + s)
    res = risk_metrics_summary(s, m, eq)
    print("=" * 60, "\n风险指标计算示例\n", "=" * 60)
    for k, v in res.items():
        print(f"  {k:20s} : {v:>12.4f}" if isinstance(v, float) else f"  {k:20s} : {v}")
