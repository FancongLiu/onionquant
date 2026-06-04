"""
harness.py — 统一回测框架 (Unified Backtest Harness)

支持两种模式:
  1. vectorized — 向量化回测 (快, 适合日频策略)
  2. event_driven — 事件驱动 (Backtrader Cerebro, 适合日内策略)

所有指标使用 empyrical 计算, 不手搓 Sharpe/MaxDD/Calmar 等。

Usage:
    python harness.py --signals signals.parquet --prices prices.parquet
"""

import argparse
import warnings
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import empyrical as ep

warnings.filterwarnings("ignore")


def vectorized_backtest(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    capital: float = 100_000,
    commission: float = 0.001,
    ppy: int = 252,
) -> Dict:
    """向量化回测: 信号 × 收益 = 策略收益。

    Args:
        prices: T×N DataFrame of close prices (dates × tickers)
        signals: T×N DataFrame of position weights (-1..1), must align with prices
        capital: initial capital
        commission: per-trade commission rate (e.g. 0.001 = 10 bps)
        ppy: periods per year (252 = daily)

    Returns:
        dict with metrics, equity_curve, turnover
    """
    common_dates = prices.index.intersection(signals.index)
    common_tickers = prices.columns.intersection(signals.columns)
    if len(common_dates) < 20 or len(common_tickers) == 0:
        return {
            "error": f"insufficient overlap: {len(common_dates)} dates, {len(common_tickers)} tickers"
        }

    p = prices.loc[common_dates, common_tickers]
    s = signals.loc[common_dates, common_tickers].fillna(0)

    rets = p.pct_change().fillna(0)
    turnover = s.diff().abs().sum(axis=1)
    port_ret = (s.shift(1).fillna(0) * rets).sum(axis=1)
    port_ret -= turnover * commission

    equity = capital * (1 + port_ret).cumprod()
    port_ret_clean = port_ret.dropna()

    metrics = _compute_metrics(port_ret_clean, equity, ppy, capital)
    metrics["equity_curve"] = [round(float(v), 2) for v in equity.values]
    metrics["equity_dates"] = [str(d) for d in equity.index]
    return metrics


def signal_backtest(
    returns: pd.Series,
    weights: pd.Series,
    capital: float = 100_000,
    commission: float = 0.001,
    ppy: int = 252,
) -> Dict:
    """单资产信号回测: 信号方向 × 收益率。

    Args:
        returns: asset returns
        weights: position weights (-1..1), same index as returns
    """
    common = returns.dropna().index.intersection(weights.dropna().index)
    if len(common) < 20:
        return {"error": f"insufficient data: {len(common)} rows"}

    r = returns.loc[common]
    w = weights.loc[common]
    turnover = w.diff().abs().fillna(0)
    port_ret = w.shift(1).fillna(0) * r - turnover * commission
    equity = capital * (1 + port_ret).cumprod()

    return _compute_metrics(port_ret.dropna(), equity, ppy, capital)


def event_driven_backtest(
    ohlcv: pd.DataFrame,
    strategy_class,
    capital: float = 100_000,
    commission: float = 0.001,
    **strategy_kwargs,
) -> Dict:
    """事件驱动回测 (Backtrader Cerebro 引擎).

    Args:
        ohlcv: DataFrame with columns [open, high, low, close, volume] and datetime index
        strategy_class: Backtrader Strategy class
        capital: initial capital
        commission: per-share or per-trade commission
        **strategy_kwargs: passed to strategy_class

    Returns:
        dict with metrics from Backtrader analyzers
    """
    try:
        import backtrader as bt
    except ImportError:
        return {"error": "backtrader not installed"}

    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_class, **strategy_kwargs)
    cerebro.broker.setcash(capital)
    cerebro.broker.setcommission(commission=commission)

    # Build data feed
    df = ohlcv.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = 0
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, annualize=True
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    results = cerebro.run()
    strat = results[0]
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    rets_analysis = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    final_value = cerebro.broker.getvalue()
    total_return = (final_value - capital) / capital

    return {
        "initial_capital": capital,
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 4),
        "sharpe": round(sharpe.get("sharperatio", 0) or 0, 2),
        "max_drawdown": round(drawdown.get("max", {}).get("drawdown", 0) / 100, 4),
        "annual_return": round(rets_analysis.get("rnorm100", 0) / 100, 4),
        "total_trades": trades.get("total", {}).get("total", 0),
        "won_trades": trades.get("won", {}).get("total", 0),
        "win_rate": round(
            trades.get("won", {}).get("total", 0)
            / max(trades.get("total", {}).get("total", 1), 1),
            4,
        ),
    }


# ─── Metrics (empyrical) ─────────────────────────────────────────
def _compute_metrics(
    returns: pd.Series, equity: pd.Series, ppy: int, capital: float
) -> Dict:
    """使用 empyrical 计算所有标准指标。"""
    r = returns.dropna()
    if len(r) < 2:
        return {"error": "insufficient returns data"}

    ann_ret = float(ep.annual_return(r, annualization=ppy))
    ann_vol = float(ep.annual_volatility(r, annualization=ppy))
    sharpe = float(ep.sharpe_ratio(r, risk_free=0.02 / ppy, annualization=ppy))
    sortino = float(ep.sortino_ratio(r, annualization=ppy))
    calmar = float(ep.calmar_ratio(r, annualization=ppy))
    max_dd = float(ep.max_drawdown(r))
    cvar_95 = float(ep.conditional_value_at_risk(r, cutoff=0.05))
    omega = float(ep.omega_ratio(r, annualization=ppy))
    stability = float(ep.stability_of_timeseries(r))

    # Win/loss stats
    win_mask = r > 0
    win_rate = float(win_mask.mean())
    avg_win = float(r[win_mask].mean()) if win_mask.any() else 0
    avg_loss = float(r[~win_mask].mean()) if (~win_mask).any() else 0
    profit_factor = (
        abs(avg_win * win_mask.sum() / (avg_loss * (~win_mask).sum()))
        if (~win_mask).any() and avg_loss != 0
        else np.inf
    )

    return {
        "initial_capital": capital,
        "final_value": round(float(equity.iloc[-1]), 2),
        "total_return": round(float(equity.iloc[-1] / capital - 1), 4),
        "annual_return": round(ann_ret, 4),
        "annual_volatility": round(ann_vol, 4),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown": round(max_dd, 4),
        "cvar_95": round(cvar_95, 4),
        "omega_ratio": round(omega, 2),
        "stability": round(stability, 4),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_factor": round(profit_factor, 2) if profit_factor < 1e6 else 999.0,
        "n_periods": len(r),
    }


def compare_strategies(results: Dict[str, Dict]) -> pd.DataFrame:
    """比较多个策略的回测结果。

    Args:
        results: {strategy_name: metrics_dict}

    Returns:
        DataFrame with strategies as rows and metrics as columns
    """
    metrics = [
        "total_return",
        "annual_return",
        "annual_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "calmar_ratio",
        "win_rate",
        "profit_factor",
    ]
    rows = []
    for name, res in results.items():
        row = {"strategy": name}
        if "error" in res:
            row["error"] = res["error"]
        else:
            for m in metrics:
                row[m] = res.get(m, None)
        rows.append(row)
    return pd.DataFrame(rows)


# ─── Demo ─────────────────────────────────────────────────────────
def _make_demo_data(n: int = 500, seed: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate demo prices + signals for testing."""
    np.random.seed(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    prices = pd.DataFrame(
        {
            "ASSET_A": 100
            * (1 + np.random.normal(0.08 / 252, 0.20 / np.sqrt(252), n)).cumprod(),
            "ASSET_B": 100
            * (1 + np.random.normal(0.06 / 252, 0.25 / np.sqrt(252), n)).cumprod(),
            "ASSET_C": 100
            * (1 + np.random.normal(0.10 / 252, 0.30 / np.sqrt(252), n)).cumprod(),
        },
        index=dates,
    )

    # Simple momentum signal: long if 21d return > 0, weight proportional
    mom_a = prices["ASSET_A"].pct_change(21).shift(1)
    signals = pd.DataFrame(
        {
            "ASSET_A": np.tanh(mom_a / 0.05),
            "ASSET_B": 0.5,
            "ASSET_C": -0.3,
        },
        index=dates,
    ).fillna(0)

    return prices, signals


# ─── CLI ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Unified Backtest Harness (empyrical)")
    parser.add_argument(
        "--signals", help="Parquet/CSV of position weights (dates × tickers)"
    )
    parser.add_argument("--prices", help="Parquet/CSV of close prices")
    parser.add_argument(
        "--capital", type=float, default=100_000, help="Initial capital"
    )
    parser.add_argument(
        "--commission", type=float, default=0.001, help="Commission rate"
    )
    args = parser.parse_args()

    if args.signals and args.prices:
        sig = (
            pd.read_parquet(args.signals)
            if args.signals.endswith(".parquet")
            else pd.read_csv(args.signals, index_col=0, parse_dates=True)
        )
        prc = (
            pd.read_parquet(args.prices)
            if args.prices.endswith(".parquet")
            else pd.read_csv(args.prices, index_col=0, parse_dates=True)
        )
    else:
        print("No --signals/--prices; using demo data\n")
        prc, sig = _make_demo_data()

    result = vectorized_backtest(
        prc, sig, capital=args.capital, commission=args.commission
    )
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\n{'=' * 56}")
    print("  Backtest Results (empyrical)")
    print(f"{'=' * 56}")
    for k, v in result.items():
        if isinstance(v, float):
            print(
                f"  {k:22s}: {v:>12.4f}" if abs(v) < 100 else f"  {k:22s}: {v:>12,.2f}"
            )
        else:
            print(f"  {k:22s}: {v}")


if __name__ == "__main__":
    main()
