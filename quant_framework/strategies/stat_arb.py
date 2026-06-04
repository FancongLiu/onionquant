"""
stat_arb.py — 统计套利: 协整配对交易 (Cointegration Pair Trading)

使用 statsmodels 进行协整检验 (Engle-Granger) + OLS 对冲比率估计。
不手搓协整检验/回归 — 全部委托 statsmodels。

Usage:
    python stat_arb.py --input prices.parquet --pairs pairs.csv
"""

import argparse
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm

warnings.filterwarnings("ignore")


def find_cointegrated_pairs(prices: pd.DataFrame, pvalue_threshold: float = 0.05) -> pd.DataFrame:
    """扫描所有股票对，返回通过协整检验的配对。

    Args:
        prices: DataFrame of close prices, columns = tickers, index = dates
        pvalue_threshold: max p-value for cointegration

    Returns:
        DataFrame with columns: ticker1, ticker2, pvalue, hedge_ratio, half_life
    """
    tickers = list(prices.columns)
    n = len(tickers)
    results = []

    for i in range(n):
        for j in range(i + 1, n):
            t1, t2 = tickers[i], tickers[j]
            pair_data = prices[[t1, t2]].dropna()
            if len(pair_data) < 60:
                continue
            try:
                _, pvalue, _ = coint(pair_data[t1], pair_data[t2])
                if pvalue <= pvalue_threshold:
                    hedge = _estimate_hedge_ratio(pair_data[t1], pair_data[t2])
                    hl = _estimate_half_life(pair_data[t1], hedge, pair_data[t2])
                    results.append({
                        "ticker1": t1, "ticker2": t2,
                        "pvalue": round(pvalue, 6),
                        "hedge_ratio": round(hedge, 4),
                        "half_life": round(hl, 1),
                    })
            except Exception:
                continue

    return pd.DataFrame(results).sort_values("pvalue")


def _estimate_hedge_ratio(y: pd.Series, x: pd.Series) -> float:
    """OLS: y = alpha + beta * x, 返回 beta (对冲比率)."""
    x_sm = sm.add_constant(x)
    model = sm.OLS(y, x_sm).fit()
    return float(model.params.iloc[1])


def _estimate_half_life(y: pd.Series, hedge: float, x: pd.Series) -> float:
    """估计价差的均值回归半衰期 (Ornstein-Uhlenbeck 过程)."""
    spread = y - hedge * x
    spread_lag = spread.shift(1)
    spread_diff = spread.diff()
    df = pd.DataFrame({"s": spread, "s_lag": spread_lag, "ds": spread_diff}).dropna()
    if len(df) < 10:
        return np.inf
    x_sm = sm.add_constant(df["s_lag"])
    model = sm.OLS(df["ds"], x_sm).fit()
    theta = float(model.params.iloc[1])
    if theta >= 0:
        return np.inf
    return -np.log(2) / theta


def compute_spread(y: pd.Series, hedge: float, x: pd.Series) -> pd.Series:
    """计算配对价差: spread = y - hedge * x."""
    return y - hedge * x


def generate_signals(spread: pd.Series, entry_z: float = 2.0,
                     exit_z: float = 0.5, lookback: int = 60) -> pd.DataFrame:
    """Z-score 法生成交易信号。

    Args:
        spread: 价差序列
        entry_z: 入场 Z-score 阈值
        exit_z: 出场 Z-score 阈值
        lookback: Z-score 滚动窗口

    Returns:
        DataFrame with columns: zscore, signal (1=long spread, -1=short spread, 0=flat)
    """
    roll_mean = spread.rolling(lookback, min_periods=lookback // 2).mean()
    roll_std = spread.rolling(lookback, min_periods=lookback // 2).std()
    zscore = (spread - roll_mean) / roll_std

    signal = pd.Series(0, index=spread.index)
    pos = 0
    for i in range(1, len(zscore)):
        z = zscore.iloc[i]
        if pos == 0:
            if z > entry_z:
                pos = -1  # short spread (y overvalued vs x)
            elif z < -entry_z:
                pos = 1   # long spread (y undervalued vs x)
        elif pos == 1 and z > -exit_z:
            pos = 0
        elif pos == -1 and z < exit_z:
            pos = 0
        signal.iloc[i] = pos

    return pd.DataFrame({"zscore": zscore, "signal": signal}, index=spread.index)


def backtest_pair(spread: pd.Series, signal: pd.Series) -> pd.DataFrame:
    """简易配对交易回测。

    Returns:
        DataFrame with columns: spread_ret, strat_ret, strat_equity
    """
    spread_ret = spread.diff()
    strat_ret = signal.shift(1).fillna(0) * spread_ret
    strat_equity = (1 + strat_ret).cumprod()
    return pd.DataFrame({
        "spread_ret": spread_ret,
        "strat_ret": strat_ret,
        "strat_equity": strat_equity,
    }, index=spread.index)


def backtest_summary(result: pd.DataFrame, ppy: int = 252) -> dict:
    """返回回测摘要统计量。"""
    rets = result["strat_ret"].dropna()
    if len(rets) < 2:
        return {"error": "insufficient data"}
    ann_ret = float(np.mean(rets) * ppy)
    ann_vol = float(np.std(rets, ddof=1) * np.sqrt(ppy))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum_ret = float(np.prod(1 + rets) - 1)
    max_dd = float((result["strat_equity"] / result["strat_equity"].cummax() - 1).min())
    return {
        "annual_return": round(ann_ret, 4),
        "annual_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 2),
        "cumulative_return": round(cum_ret, 4),
        "max_drawdown": round(max_dd, 4),
        "n_days": len(rets),
    }


def run_pair(prices: pd.DataFrame, ticker1: str, ticker2: str,
             entry_z: float = 2.0, exit_z: float = 0.5,
             lookback: int = 60, train_ratio: float = 0.5) -> dict:
    """对单对股票运行完整配对交易流水线。

    Args:
        prices: 含 ticker1/ticker2 列的收盘价 DataFrame
        ticker1, ticker2: 股票代码
        entry_z, exit_z: Z-score 阈值
        lookback: Z-score 滚动窗口
        train_ratio: 对冲比率估计用数据比例 (前 train_ratio)

    Returns:
        dict with hedge_ratio, half_life, coint_pvalue, signal_count, summary
    """
    pair = prices[[ticker1, ticker2]].dropna()
    if len(pair) < 100:
        return {"error": f"insufficient data: {len(pair)} rows"}

    split = int(len(pair) * train_ratio)
    train, test = pair.iloc[:split], pair.iloc[split:]

    # Cointegration test on training data
    _, pvalue, _ = coint(train[ticker1], train[ticker2])
    hedge = _estimate_hedge_ratio(train[ticker1], train[ticker2])
    hl = _estimate_half_life(train[ticker1], hedge, train[ticker2])

    # Out-of-sample spread and signals
    spread = compute_spread(test[ticker1], hedge, test[ticker2])
    sig_df = generate_signals(spread, entry_z=entry_z, exit_z=exit_z, lookback=lookback)
    bt = backtest_pair(spread, sig_df["signal"])
    summary = backtest_summary(bt)
    summary["coint_pvalue"] = round(pvalue, 6)
    summary["hedge_ratio"] = round(hedge, 4)
    summary["half_life"] = round(hl, 1)
    summary["signal_pct"] = round((sig_df["signal"].abs() > 0).mean() * 100, 1)

    return summary


# ─── Demo data ──────────────────────────────────────────────────
def _make_demo_prices(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic cointegrated pair prices for demonstration."""
    np.random.seed(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    y = 100 + np.cumsum(np.random.normal(0, 0.8, n))
    x = (y - 5) / 2 + np.random.normal(0, 0.3, n)
    return pd.DataFrame({"STOCK_A": y, "STOCK_B": x}, index=dates)


# ─── CLI ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Cointegration Pair Trading (statsmodels)")
    parser.add_argument("--input", help="Input parquet/csv with close prices")
    parser.add_argument("--ticker1", default="STOCK_A", help="First ticker")
    parser.add_argument("--ticker2", default="STOCK_B", help="Second ticker")
    parser.add_argument("--entry-z", type=float, default=2.0)
    parser.add_argument("--exit-z", type=float, default=0.5)
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--scan", action="store_true", help="Scan all pairs for cointegration")
    parser.add_argument("--pvalue", type=float, default=0.05, help="Max p-value for pair scan")
    args = parser.parse_args()

    if args.input:
        df = pd.read_parquet(args.input) if args.input.endswith(".parquet") else pd.read_csv(args.input)
    else:
        print("No --input provided; using synthetic cointegrated pair demo\n")
        df = _make_demo_prices()

    if args.scan:
        pairs = find_cointegrated_pairs(df, args.pvalue)
        if pairs.empty:
            print("No cointegrated pairs found.")
            return
        print(f"Found {len(pairs)} cointegrated pairs (p < {args.pvalue}):")
        print(pairs.to_string(index=False))
        return

    # Single pair
    result = run_pair(df, args.ticker1, args.ticker2,
                      entry_z=args.entry_z, exit_z=args.exit_z,
                      lookback=args.lookback)
    print(f"\n{'='*56}")
    print(f"  Pair Trade: {args.ticker1} vs {args.ticker2}")
    print(f"{'='*56}")
    for k, v in result.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
