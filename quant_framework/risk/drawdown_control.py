"""drawdown_control.py — 回撤控制: CPPI, 移动止损(ATR), 波动率目标, 固定止损.

v2: ATR 计算使用 pandas-ta (pure Python, 无需C库), Wilder's EMA 平滑.
    CPPI / volatility_targeting / fixed_stop_loss 保留 numpy 实现 (纯数学).
"""

import numpy as np
import pandas as pd


def _compute_atr(high, low, close, period=14):
    """使用 pandas-ta 计算 Average True Range (Wilder's smoothing)."""
    import pandas_ta as ta

    df = pd.DataFrame({"high": high, "low": low, "close": close})
    result = ta.atr(df["high"], df["low"], df["close"], length=period, mamode="rma")
    return result.values


# ---- 1. CPPI ----
def cppi(
    equity_curve,
    floor_pct=0.80,
    multiplier=3.0,
    risky_return=None,
    safe_return=0.02 / 252,
):
    eq = np.asarray(equity_curve, dtype=float)
    T = len(eq)
    floor = floor_pct * eq[0]
    if risky_return is not None:
        rsk = np.asarray(risky_return, dtype=float)
        eq_s = np.zeros(T)
        fl = np.zeros(T)
        cush = np.zeros(T)
        rw = np.zeros(T)
        eq_s[0] = eq[0]
        fl[0] = floor
        for t in range(1, T):
            cush[t - 1] = max(eq_s[t - 1] - fl[t - 1], 0)
            exposure = multiplier * cush[t - 1]
            w_r = min(exposure / eq_s[t - 1], 1.0) if eq_s[t - 1] > 0 else 0
            rw[t] = w_r
            ret = w_r * rsk[t - 1] + (1 - w_r) * safe_return
            eq_s[t] = eq_s[t - 1] * (1 + ret)
            fl[t] = floor * (1 + safe_return) ** t
        return {
            "equity": eq_s,
            "risky_weight": rw,
            "floor": fl,
            "cushion": cush,
            "exposure": exposure,
        }
    cush = np.zeros(T)
    rw = np.zeros(T)
    for t in range(T):
        c = max(eq[t] - floor, 0)
        cush[t] = c
        rw[t] = min(multiplier * c / eq[t], 1.0) if eq[t] > 0 else 0
    return {
        "equity": eq,
        "risky_weight": rw,
        "floor": np.full(T, floor),
        "cushion": cush,
        "exposure": multiplier * cush,
    }


# ---- 2. 移动止损 ----
def moving_stop_loss(equity_curve, lookback=20, multiplier=2.0, ohlc=None):
    """
    移动止损: 支持两种模式
    - ohlc DataFrame (含 high/low/close): pandas-ta ATR (Wilder's EMA)
    - ohlc=None: 历史波动率止损 (hist vol × price)

    v2: ATR 改用 pandas-ta 计算, 替代手搓 True Range 循环.
    """
    eq = np.asarray(equity_curve, dtype=float)
    T = len(eq)
    pk = np.maximum.accumulate(eq)
    sl = np.zeros(T)
    sig = np.ones(T, dtype=int)

    if ohlc is not None:
        high = np.asarray(ohlc["high"], dtype=float)
        low = np.asarray(ohlc["low"], dtype=float)
        close = np.asarray(ohlc["close"], dtype=float)
        atr = _compute_atr(high, low, close, period=lookback)
        atr = np.nan_to_num(atr, nan=np.nanmean(atr))
        for t in range(1, T):
            sl[t] = pk[t] - atr[t] * multiplier
            if sig[t - 1] == 0:
                sig[t] = 0
            elif eq[t] < sl[t]:
                sig[t] = 0
        return {
            "stop_level": sl,
            "signal": sig,
            "trailing_peak": pk,
            "drawdown_from_peak": (eq - pk) / pk,
            "atr": atr,
        }
    else:
        rets = np.diff(eq) / eq[:-1]
        vol_est = np.zeros(T)
        for t in range(1, T):
            if t <= lookback:
                r = rets[: max(t, 1)]
                vol_est[t] = np.std(r, ddof=1) * eq[t] if len(r) >= 2 else 0.0
            else:
                r = rets[t - lookback : t]
                vol_est[t] = np.std(r, ddof=1) * eq[t]
            sl[t] = pk[t] - vol_est[t] * multiplier
            if sig[t - 1] == 0:
                sig[t] = 0
            elif eq[t] < sl[t]:
                sig[t] = 0
        return {
            "stop_level": sl,
            "signal": sig,
            "trailing_peak": pk,
            "drawdown_from_peak": (eq - pk) / pk,
            "hist_vol_est": vol_est,
        }


# ---- 3. 波动率目标 ----
def volatility_targeting(
    returns, target_vol=0.15, lookback=21, max_leverage=1.0, ppy=252
):
    r = np.asarray(returns, dtype=float)
    s = pd.Series(r)
    roll_std = s.rolling(window=lookback, min_periods=2).std(ddof=1) * np.sqrt(ppy)
    exp_std = s.expanding(min_periods=2).std(ddof=1) * np.sqrt(ppy)
    rv_series = roll_std.fillna(exp_std).fillna(target_vol)
    rv = rv_series.values
    pos = np.minimum(target_vol / (rv + 1e-10), max_leverage)
    sr = pos * r
    return {
        "position": pos,
        "realized_vol": rv,
        "scaled_returns": sr,
        "target_vol": target_vol,
    }


# ---- 4. 固定止损 ----
def fixed_stop_loss(equity_curve, drawdown_limit=0.10):
    eq = np.asarray(equity_curve, dtype=float)
    pk = np.maximum.accumulate(eq)
    dd = (pk - eq) / pk
    sig = np.ones(len(eq), dtype=int)
    trig = False
    for t in range(1, len(eq)):
        if trig:
            sig[t] = 0
        elif dd[t] >= drawdown_limit:
            sig[t] = 0
            trig = True
    return {"signal": sig, "drawdown": dd, "limit": drawdown_limit}


if __name__ == "__main__":
    np.random.seed(42)
    T = 500
    dv = 0.20 / np.sqrt(252)
    dd_ = 0.10 / 252
    sr = np.random.normal(dd_, dv, T)
    eq = 100 * np.cumprod(1 + sr)
    print("=" * 60, "\n回撤控制模块示例\n", "=" * 60)
    # CPPI
    cr = cppi(eq, 0.80, 3, risky_return=sr)
    print(
        f"\n[1] CPPI: 最终净值={cr['equity'][-1]:.2f}, "
        f"平均仓位={np.mean(cr['risky_weight']):.2%}"
    )
    # 移动止损 (无 OHLC → 历史波动率)
    ms = moving_stop_loss(eq)
    print(f"[2] 波动率止损: 期末信号={'持仓' if ms['signal'][-1] == 1 else '已止损'}")
    # 固定止损
    fs = fixed_stop_loss(eq, 0.10)
    print(
        f"[3] 固定止损(10%): 触发={'是' if fs['signal'][-1] == 0 else '否'}, "
        f"最大回撤={np.max(fs['drawdown']):.2%}"
    )
    # 波动率目标
    vt = volatility_targeting(sr, 0.15)
    vt_v = np.std(vt["scaled_returns"]) * np.sqrt(252)
    print(
        f"[4] 波动率目标: 调整后波动率={vt_v:.2%} (目标15%), "
        f"仓位范围={np.min(vt['position']):.2%}~{np.max(vt['position']):.2%}"
    )
