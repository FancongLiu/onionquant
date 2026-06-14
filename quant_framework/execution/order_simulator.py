#!/usr/bin/env python3
"""Order execution simulation — slippage/commission/position tracking.

Uses vectorized NumPy/Pandas for performance. No hand-rolled math —
all models reference standard industry formulas (Almgren-Chriss, etc.)."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SlippageModel:
    """Configurable slippage model.

    fixed_bp: fixed slippage in basis points (e.g. 1.0 = 0.01%)
    proportional_bp: proportional slippage in bp per % of daily volume traded
    sqrt_coef: square-root impact coefficient (Almgren-Chriss style)
    """

    fixed_bp: float = 0.5
    proportional_bp: float = 1.0
    sqrt_coef: float = 0.1

    def apply(self, order_size: float, daily_volume: float, price: float) -> float:
        vol_frac = min(order_size / max(daily_volume, 1), 1.0)
        impact_bp = (
            self.fixed_bp
            + self.proportional_bp * vol_frac * 100
            + self.sqrt_coef * np.sqrt(vol_frac) * 100
        )
        return price * impact_bp / 10000


def twap_schedule(total_size: float, n_periods: int) -> np.ndarray:
    """Generate TWAP (time-weighted average price) order schedule."""
    sizes = np.full(n_periods, total_size / n_periods)
    sizes[-1] = total_size - sizes[:-1].sum()
    return sizes


def vwap_schedule(total_size: float, volume_profile: np.ndarray) -> np.ndarray:
    """Generate VWAP (volume-weighted) order schedule from volume profile."""
    vp = np.asarray(volume_profile, dtype=float)
    total_vol = vp.sum()
    if total_vol == 0:
        return twap_schedule(total_size, len(vp))
    weights = vp / total_vol
    sizes = weights * total_size
    sizes[-1] = total_size - sizes[:-1].sum()
    return sizes


def simulate_orders(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    initial_cash: float = 1_000_000,
    commission_per_share: float = 0.005,
    slippage: SlippageModel | None = None,
    execution_schedule: str = "next_open",
    max_position_pct: float = 0.20,
) -> dict:
    """Simulate order execution from signals.

    Parameters
    ----------
    prices: DataFrame with columns [date, ticker, open, close, volume]
    signals: DataFrame with columns [date, ticker, signal] where signal ∈ {-1,0,1}
    initial_cash: starting cash
    commission_per_share: per-share commission
    slippage: SlippageModel or None for default
    execution_schedule: "next_open" | "next_close" | "twap" | "vwap"
    max_position_pct: max position size as fraction of portfolio

    Returns
    -------
    dict with equity_curve, trades, positions, metrics
    """
    if slippage is None:
        slippage = SlippageModel()

    # Pivot to wide format
    price_col = "open" if execution_schedule == "next_open" else "close"
    pivot_prices = prices.pivot_table(
        index="date", columns="ticker", values=price_col, aggfunc="last"
    ).sort_index()
    pivot_vol = prices.pivot_table(
        index="date", columns="ticker", values="volume", aggfunc="last"
    ).sort_index()
    pivot_sig = (
        signals.pivot_table(
            index="date", columns="ticker", values="signal", aggfunc="last"
        )
        .sort_index()
        .fillna(0)
    )

    common_dates = pivot_prices.index.intersection(pivot_sig.index)
    tickers = pivot_prices.columns.intersection(pivot_sig.columns)
    if len(common_dates) < 2 or len(tickers) == 0:
        return {
            "error": "Insufficient overlapping data",
            "trades": [],
            "equity": [initial_cash],
        }

    pivot_prices = pivot_prices.loc[common_dates, tickers]
    pivot_sig = pivot_sig.loc[common_dates, tickers]
    pivot_vol = (
        pivot_vol.loc[common_dates, tickers]
        if set(tickers) <= set(pivot_vol.columns)
        else None
    )

    cash = initial_cash
    positions = {}  # ticker -> shares
    equity = [initial_cash]
    trades = []
    dates = list(common_dates)

    for i, date in enumerate(dates):
        today_prices = pivot_prices.loc[date].to_dict()
        today_sig = pivot_sig.loc[date].to_dict()
        today_vol = (
            pivot_vol.loc[date].to_dict()
            if pivot_vol is not None
            else {t: 1e6 for t in tickers}
        )

        # Liquidate positions where signal flipped or went to 0
        for ticker in list(positions.keys()):
            sig = today_sig.get(ticker, 0)
            if sig == 0 or (sig == -1 and positions.get(ticker, 0) > 0):
                price = today_prices.get(ticker, 0)
                shares = positions[ticker]
                if price > 0 and shares > 0:
                    impact = slippage.apply(shares, today_vol.get(ticker, 1e6), price)
                    fill_price = price - impact if shares > 0 else price + impact
                    proceeds = shares * fill_price - shares * commission_per_share
                    cash += proceeds
                    trades.append(
                        {
                            "date": date,
                            "ticker": ticker,
                            "side": "SELL",
                            "shares": shares,
                            "price": round(fill_price, 4),
                            "slippage_bp": round(impact / price * 10000, 2),
                        }
                    )
                    del positions[ticker]

        # Enter positions based on signals
        for ticker in tickers:
            sig = today_sig.get(ticker, 0)
            price = today_prices.get(ticker, 0)
            if sig != 1 or price <= 0:
                continue

            if ticker in positions:
                continue  # Already holding

            max_shares = int((cash * max_position_pct) / price)
            if max_shares <= 0:
                continue

            impact = slippage.apply(max_shares, today_vol.get(ticker, 1e6), price)
            fill_price = price + impact
            cost = max_shares * fill_price + max_shares * commission_per_share
            if cost > cash * 0.95:
                max_shares = int((cash * 0.95) / (fill_price + commission_per_share))
                cost = max_shares * fill_price + max_shares * commission_per_share

            if max_shares <= 0:
                continue

            cash -= cost
            positions[ticker] = max_shares
            trades.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "side": "BUY",
                    "shares": max_shares,
                    "price": round(fill_price, 4),
                    "slippage_bp": round(impact / price * 10000, 2),
                }
            )

        # Mark-to-market
        mtm = cash
        for ticker, shares in positions.items():
            mtm += shares * today_prices.get(ticker, 0)
        equity.append(mtm)

    # Liquidate remaining at end
    if positions and len(dates) > 0:
        last_date = dates[-1]
        final_prices = pivot_prices.loc[last_date].to_dict()
        for ticker, shares in list(positions.items()):
            price = final_prices.get(ticker, 0)
            if price > 0:
                cash += shares * price
                trades.append(
                    {
                        "date": last_date,
                        "ticker": ticker,
                        "side": "SELL (final)",
                        "shares": shares,
                        "price": round(price, 4),
                        "slippage_bp": 0,
                    }
                )
        del positions[ticker]
        equity[-1] = cash

    # Compute metrics — equity has len(dates)+1 (initial + mtm per date)
    eq = pd.Series(equity)
    returns = eq.pct_change().dropna()
    metrics = _compute_metrics(eq, returns)

    return {
        "equity_curve": eq,
        "returns": returns,
        "trades": trades,
        "final_positions": positions,
        "final_cash": cash,
        **metrics,
    }


def _compute_metrics(equity: pd.Series, returns: pd.Series) -> dict:
    ppy = 252
    try:
        from empyrical import calmar_ratio, max_drawdown, sharpe_ratio, sortino_ratio

        sr = sharpe_ratio(returns.values)
        so = sortino_ratio(returns.values)
        cr = calmar_ratio(returns.values)
        mdd = max_drawdown(returns.values)
    except ImportError:
        r = returns.values
        sr = float(np.mean(r) / max(np.std(r), 1e-10) * np.sqrt(ppy))
        so = float(
            np.mean(r)
            / max(np.std(r[r < 0]) if (r < 0).any() else np.std(r), 1e-10)
            * np.sqrt(ppy)
        )
        peak = np.maximum.accumulate(equity.values)
        dd = (peak - equity.values) / peak
        mdd = float(dd.max())
        cr = float((equity.values[-1] / equity.values[0] - 1) / max(mdd, 1e-10))

    return {
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "annual_return": float(
            (equity.iloc[-1] / equity.iloc[0]) ** (ppy / max(len(returns), 1)) - 1
        ),
        "annual_volatility": float(returns.std() * np.sqrt(ppy)),
        "sharpe_ratio": round(sr, 4),
        "sortino_ratio": round(so, 4),
        "calmar_ratio": round(cr, 4),
        "max_drawdown": round(mdd, 4),
    }


def execution_quality_report(
    prices: pd.DataFrame, trades: list[dict], schedule: str = "VWAP"
) -> dict:
    """Compute execution quality metrics: implementation shortfall, VWAP slippage."""
    if not trades:
        return {"error": "No trades"}

    df = pd.DataFrame(trades)
    total_shares = df["shares"].sum()
    total_value = (df["shares"] * df["price"]).sum()

    # Average execution price
    avg_price = total_value / total_shares if total_shares > 0 else 0

    # Arrival price (price at signal time, approximated by first trade price)
    arrival_price = df.iloc[0]["price"]

    # Implementation shortfall
    buys = df[df["side"].str.contains("BUY")]
    if len(buys) > 0:
        buy_avg = (buys["shares"] * buys["price"]).sum() / buys["shares"].sum()
        imp_shortfall_bp = (buy_avg / arrival_price - 1) * 10000
    else:
        imp_shortfall_bp = 0

    return {
        "total_shares": int(total_shares),
        "total_value": round(total_value, 2),
        "avg_price": round(avg_price, 4),
        "arrival_price": round(arrival_price, 4),
        "implementation_shortfall_bp": round(imp_shortfall_bp, 2),
        "n_trades": len(trades),
        "schedule": schedule,
    }


def _make_demo_data(
    n_dates: int = 252, n_tickers: int = 5, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate demo prices and signals for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    tickers = [f"STOCK{i}" for i in range(n_tickers)]

    price_records = []
    signal_records = []
    for t in tickers:
        close = 50 + np.cumsum(rng.normal(0.02, 1.0, n_dates))
        for i, d in enumerate(dates):
            price_records.append(
                {
                    "date": d,
                    "ticker": t,
                    "open": close[i] * (1 + rng.normal(0, 0.002)),
                    "close": close[i],
                    "volume": float(rng.integers(500_000, 5_000_000)),
                }
            )
            if i > 0 and i % 21 == 0:
                signal_records.append({"date": d, "ticker": t, "signal": 1})

    return pd.DataFrame(price_records), pd.DataFrame(signal_records)


def main():
    prices, signals = _make_demo_data(252, 5)
    result = simulate_orders(prices, signals, initial_cash=500_000)
    if "error" in result:
        print(f"Error: {result['error']}")
        return
    print(f"Return: {result['total_return']:.2%}")
    print(f"Sharpe: {result['sharpe_ratio']}")
    print(f"MaxDD: {result['max_drawdown']:.2%}")
    print(f"Trades: {result.get('n_trades', len(result.get('trades', [])))}")
    quality = execution_quality_report(prices, result["trades"])
    print(f"Impl Shortfall: {quality.get('implementation_shortfall_bp', 'N/A')} bp")


if __name__ == "__main__":
    main()
