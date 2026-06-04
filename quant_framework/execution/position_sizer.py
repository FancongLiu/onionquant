#!/usr/bin/env python3
"""Position sizing — Kelly, risk-parity, volatility-targeted, equal-weight.

Integrates with Riskfolio-Lib for Kelly/risk-parity. All sizers take a
signals DataFrame + prices and return position weights or share counts."""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


def equal_weight(signals: pd.DataFrame, max_positions: int = 10) -> pd.Series:
    """Equal-weight position sizing: 1/N of capital per active signal.

    Returns Series[ticker] → weight (0 to 1).
    """
    active = signals[signals.get("signal", 0) == 1]
    if active.empty:
        return pd.Series(dtype=float)

    tickers = active["ticker"].unique()[:max_positions]
    w = 1.0 / len(tickers)
    return pd.Series(w, index=tickers)


def kelly_sizing(
    returns: pd.DataFrame, max_weight: float = 0.25, risk_aversion: float = 2.0
) -> pd.Series:
    """Kelly criterion position sizing via Riskfolio-Lib Utility optimization.

    Parameters
    ----------
    returns: DataFrame of returns (dates × tickers)
    max_weight: max weight per position
    risk_aversion: higher = more conservative (default 2.0 = half-Kelly)

    Returns
    -------
    Series[ticker] → weight
    """
    try:
        import riskfolio as rp

        port = rp.Portfolio(returns=returns, upperlng=max_weight, lowerlng=0.0)
        port.assets_stats(method_mu="hist", method_cov="hist")
        w_df = port.optimization(
            model="Classic",
            rm="MV",
            obj="Utility",
            kelly="approx",
            rf=0,
            l=risk_aversion,
        )
        if w_df is not None and "weights" in w_df:
            return w_df["weights"]
    except (ImportError, Exception):
        pass

    # Fallback: Kelly fractions with Ledoit-Wolf shrinkage (T954)
    mu = returns.mean().values
    try:
        from sklearn.covariance import LedoitWolf

        cov = LedoitWolf().fit(returns.values).covariance_
    except ImportError:
        cov = returns.cov().values
    try:
        from scipy.linalg import pinv
    except ImportError:
        pinv = np.linalg.pinv
    w = pinv(cov) @ mu
    w = np.maximum(w, 0)
    s = w.sum()
    if s > 0:
        w = w / s * max_weight
    return pd.Series(np.clip(w, 0, max_weight), index=returns.columns)


def risk_parity_sizing(returns: pd.DataFrame, max_weight: float = 0.30) -> pd.Series:
    """Risk-parity position sizing via Riskfolio-Lib HRP optimization.

    Falls back to inverse-volatility weighting if Riskfolio-Lib is unavailable.
    Returns Series[ticker] → weight.
    """
    try:
        import riskfolio as rp

        try:
            port = rp.Portfolio(returns=returns, upperlng=max_weight, lowerlng=0.0)
            port.assets_stats(method_mu="hist", method_cov="hist")
            w_df = port.optimization(model="Classic", rm="MV", obj="MinRisk", rf=0, l=0)
            if w_df is not None and "weights" in w_df:
                w = w_df["weights"]
                w = w.clip(upper=max_weight)
                w = w / w.sum()
                return w
        except Exception:
            # Fall through: HRP as alternative
            try:
                w_df = port.rp_optimization(model="Classic", rm="MV", rf=0, b=None)
                if w_df is not None and "weights" in w_df:
                    w = w_df["weights"]
                    w = w.clip(upper=max_weight)
                    w = w / w.sum()
                    return w
            except Exception:
                pass
    except ImportError:
        pass

    # Fallback: simple inverse-volatility weighting
    vols = returns.std()
    inv_vol = 1.0 / (vols.replace(0, np.nan))
    w = inv_vol / inv_vol.sum()
    w = w.clip(upper=max_weight)
    w = w / w.sum()  # re-normalize
    return w


def volatility_targeted_sizing(
    returns: pd.DataFrame,
    target_vol: float = 0.15,
    max_leverage: float = 2.0,
    lookback: int = 63,
) -> pd.Series:
    """Volatility-targeted position sizing.

    Scale each position so portfolio vol ≈ target_vol.
    Returns Series[ticker] → weight (may exceed 1.0 = leverage).
    """
    ppy = 252
    if len(returns) < lookback:
        return equal_weight_sizing(returns)

    recent = returns.tail(lookback)
    cov = recent.cov().values
    vols = recent.std().values

    # Equal risk contribution approximation
    inv_vol = 1.0 / np.maximum(vols, 1e-8)
    w_raw = inv_vol / inv_vol.sum()

    # Scale to target vol
    port_vol = np.sqrt(w_raw @ cov @ w_raw) * np.sqrt(ppy)
    scale = min(target_vol / max(port_vol, 1e-8), max_leverage)
    w = w_raw * scale

    return pd.Series(w, index=returns.columns)


def equal_weight_sizing(returns: pd.DataFrame) -> pd.Series:
    """Equal weight (1/N) sizing."""
    n = returns.shape[1]
    return pd.Series(np.full(n, 1.0 / n), index=returns.columns)


def size_positions(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    capital: float,
    method: str = "equal_weight",
    max_positions: int = 10,
    max_position_pct: float = 0.20,
    **kwargs,
) -> Dict:
    """Convert signals + capital into sized orders.

    Parameters
    ----------
    signals: DataFrame with [date, ticker, signal]
    prices: DataFrame with [date, ticker, close] (or pivot-friendly)
    capital: available cash
    method: "equal_weight" | "kelly" | "risk_parity" | "vol_targeted"
    max_positions: max number of concurrent positions
    max_position_pct: cap on single position as fraction of capital

    Returns
    -------
    dict with orders (list of {ticker, shares, weight, price}), weights Series
    """
    # Get latest signal date
    latest_date = signals["date"].max()
    latest_signals = signals[signals["date"] == latest_date]
    buys = latest_signals[latest_signals.get("signal", 0) == 1]

    if buys.empty:
        return {"orders": [], "weights": pd.Series(dtype=float), "method": method}

    active_tickers = buys["ticker"].unique()[:max_positions]
    n = len(active_tickers)
    if n == 0:
        return {"orders": [], "weights": pd.Series(dtype=float), "method": method}

    # Get latest prices for active tickers
    if "ticker" in prices.columns:
        latest_prices = prices[prices["date"] == prices["date"].max()]
        price_map = latest_prices.set_index("ticker")["close"].to_dict()
    else:
        price_map = prices.iloc[-1].to_dict()

    # Compute weights
    if method == "kelly" or method == "risk_parity":
        # Build returns matrix for active tickers
        pivot = prices.pivot_table(
            index="date", columns="ticker", values="close", aggfunc="last"
        ).sort_index()
        common = [t for t in active_tickers if t in pivot.columns]
        if len(common) < 2:
            weights = (
                pd.Series(1.0 / len(common), index=common)
                if common
                else pd.Series(dtype=float)
            )
        elif method == "kelly":
            rets = pivot[common].pct_change().dropna()
            weights = kelly_sizing(rets, max_weight=max_position_pct, **kwargs)
        else:
            rets = pivot[common].pct_change().dropna()
            weights = risk_parity_sizing(rets, max_weight=max_position_pct, **kwargs)
    elif method == "vol_targeted":
        pivot = prices.pivot_table(
            index="date", columns="ticker", values="close", aggfunc="last"
        ).sort_index()
        common = [t for t in active_tickers if t in pivot.columns]
        rets = pivot[common].pct_change().dropna() if common else pd.DataFrame()
        weights = (
            volatility_targeted_sizing(rets, **kwargs)
            if not rets.empty
            else pd.Series(dtype=float)
        )
    else:  # equal_weight
        weights = equal_weight(signals, max_positions=max_positions)
        # Align with active_tickers
        weights = weights.reindex(active_tickers).fillna(0)
        w_sum = weights.sum()
        if w_sum > 0:
            weights = weights / w_sum

    # Convert weights to orders
    orders = []
    for ticker in weights.index:
        w = weights.get(ticker, 0)
        if w <= 0:
            continue
        price = price_map.get(ticker, 0)
        if price <= 0:
            continue
        allocation = min(w, max_position_pct) * capital
        shares = int(allocation / price)
        if shares > 0:
            orders.append(
                {
                    "ticker": ticker,
                    "shares": shares,
                    "weight": round(w, 6),
                    "price": round(price, 4),
                    "allocation": round(shares * price, 2),
                }
            )

    return {
        "orders": orders,
        "weights": weights,
        "method": method,
        "total_allocated": round(sum(o["allocation"] for o in orders), 2),
        "capital": capital,
    }


def _make_demo_data(
    n: int = 252, n_tickers: int = 5, seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    tickers = [f"STK{i}" for i in range(n_tickers)]
    price_records = []
    signal_records = []
    for t in tickers:
        close = 50 + np.cumsum(rng.normal(0.05, 1.2, n))
        for i, d in enumerate(dates):
            price_records.append({"date": d, "ticker": t, "close": close[i]})
    # Signal all tickers on latest date
    for t in tickers[:3]:
        signal_records.append({"date": dates[-1], "ticker": t, "signal": 1})
    return pd.DataFrame(price_records), pd.DataFrame(signal_records)


def main():
    prices, signals = _make_demo_data(252, 5, seed=7)

    for method in ["equal_weight", "kelly", "risk_parity", "vol_targeted"]:
        result = size_positions(signals, prices, capital=100_000, method=method)
        orders = result["orders"]
        logger.info(
            "%s: %d orders, allocated $%s",
            method,
            len(orders),
            f"{result['total_allocated']:,.0f}",
        )
        for o in orders:
            logger.info(
                "  %s: %d shares @ $%.2f (%.4f) = $%s",
                o["ticker"],
                o["shares"],
                o["price"],
                o["weight"],
                f"{o['allocation']:,.2f}",
            )


if __name__ == "__main__":
    main()
