#!/usr/bin/env python3
"""Portfolio rebalancing — calendar/threshold-based, turnover-constrained, tax-aware.

Handles target weight → trade list generation with configurable rebalancing
schedules and constraints. Integrates with position_sizer for weight calculation
and order_simulator for execution simulation."""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import timedelta


@dataclass
class RebalanceConfig:
    method: str = "threshold"  # "calendar" | "threshold" | "hybrid"
    calendar_freq: str = "M"   # "D" | "W" | "M" | "Q" | "Y" (pandas offset alias)
    drift_threshold: float = 0.05  # 5% absolute weight drift triggers rebalance
    max_turnover: float = 0.30     # max 30% one-way turnover
    min_trade_value: float = 100.0  # minimum trade size in USD
    buffer_zone: float = 0.02      # don't trade if within 2% of target
    transaction_cost_bp: float = 10.0  # assumed cost for turnover estimation
    enable_tlh: bool = False       # tax-loss harvesting
    tlh_short_term_days: int = 365  # US short-term vs long-term threshold
    tlh_min_loss: float = 0.05     # minimum loss to harvest (5%)


# ── Rebalance schedule ─────────────────────────────────────

def generate_calendar_dates(
    dates: pd.DatetimeIndex,
    freq: str = "M",
    start_date: Optional[str] = None,
) -> pd.DatetimeIndex:
    """Generate rebalance calendar dates.

    Parameters
    ----------
    dates: available trading dates
    freq: pandas frequency string ("W", "M", "Q", "Y")
    start_date: optional first rebalance date

    Returns DatetimeIndex of rebalance dates.
    """
    if start_date:
        start = pd.Timestamp(start_date)
    else:
        start = dates[0]

    # Generate candidate dates
    if freq == "W":
        candidates = pd.date_range(start, dates[-1], freq="W-FRI")
    elif freq == "M":
        candidates = pd.date_range(start, dates[-1], freq="BME")
    elif freq == "Q":
        candidates = pd.date_range(start, dates[-1], freq="BQE")
    elif freq == "Y":
        candidates = pd.date_range(start, dates[-1], freq="BYE")
    else:
        candidates = pd.date_range(start, dates[-1], freq="B")

    # Snap to nearest available trading date
    rebalance_dates = []
    for c in candidates:
        idx = dates.get_indexer([c], method="nearest")
        nearest = dates[idx[0]]
        if nearest not in rebalance_dates and nearest in dates:
            rebalance_dates.append(nearest)

    return pd.DatetimeIndex(sorted(set(rebalance_dates)))


def check_drift(
    current_weights: pd.Series,
    target_weights: pd.Series,
    threshold: float = 0.05,
) -> bool:
    """Check if portfolio drift exceeds rebalance threshold.

    Returns True if any asset's absolute weight deviation > threshold.
    """
    aligned = pd.concat([current_weights, target_weights], axis=1, keys=["current", "target"]).fillna(0.0)
    aligned = aligned.astype(float)
    drift = (aligned["current"] - aligned["target"]).abs()
    return bool((drift > threshold).any())


def should_rebalance(
    current_date: pd.Timestamp,
    current_weights: pd.Series,
    target_weights: pd.Series,
    last_rebalance_date: Optional[pd.Timestamp],
    next_calendar_date: Optional[pd.Timestamp],
    config: RebalanceConfig,
) -> bool:
    """Determine if rebalancing should occur.

    Returns True if: calendar date reached, OR drift exceeds threshold.
    For hybrid: rebalance on calendar if any drift > threshold/2.
    """
    if config.method == "calendar":
        if next_calendar_date is not None and current_date >= next_calendar_date:
            return True

    elif config.method == "threshold":
        if check_drift(current_weights, target_weights, config.drift_threshold):
            return True

    elif config.method == "hybrid":
        if next_calendar_date is not None and current_date >= next_calendar_date:
            half_threshold = config.drift_threshold / 2
            if check_drift(current_weights, target_weights, half_threshold):
                return True
        elif check_drift(current_weights, target_weights, config.drift_threshold):
            return True

    return False


# ── Trade list generation ──────────────────────────────────

def compute_trades(
    current_weights: pd.Series,
    target_weights: pd.Series,
    current_prices: pd.Series,
    portfolio_value: float,
    config: RebalanceConfig,
    current_positions: Optional[pd.Series] = None,
    cost_basis: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Generate trade list from weight drift.

    Parameters
    ----------
    current_weights: current portfolio weights (ticker → weight)
    target_weights: desired portfolio weights (ticker → weight)
    current_prices: latest prices per ticker
    portfolio_value: total portfolio market value
    config: RebalanceConfig
    current_positions: optional current share counts
    cost_basis: optional cost basis per ticker (for TLH)

    Returns DataFrame with columns: ticker, action, shares, value, weight_delta, reason.
    """
    all_tickers = sorted(set(list(current_weights.index) + list(target_weights.index)))
    weighted = pd.DataFrame({
        "ticker": all_tickers,
        "current_weight": [current_weights.get(t, 0.0) for t in all_tickers],
        "target_weight": [target_weights.get(t, 0.0) for t in all_tickers],
        "price": [current_prices.get(t, np.nan) for t in all_tickers],
    }).set_index("ticker")

    weighted["weight_delta"] = weighted["target_weight"] - weighted["current_weight"]
    weighted["value_delta"] = weighted["weight_delta"] * portfolio_value

    # Apply buffer zone — don't trade small deviations
    buffer = config.buffer_zone
    within_buffer = weighted["weight_delta"].abs() <= buffer
    weighted.loc[within_buffer, "weight_delta"] = 0.0
    weighted.loc[within_buffer, "value_delta"] = 0.0

    # Compute shares
    weighted["target_shares"] = np.floor(
        weighted["target_weight"] * portfolio_value / weighted["price"].replace(0, np.nan)
    )

    if current_positions is not None:
        weighted["current_shares"] = current_positions.reindex(all_tickers).fillna(0)
    else:
        weighted["current_shares"] = np.floor(
            weighted["current_weight"] * portfolio_value / weighted["price"].replace(0, np.nan)
        )

    weighted["share_delta"] = weighted["target_shares"] - weighted["current_shares"]

    # Apply minimum trade size
    weighted["trade_value"] = (weighted["share_delta"].abs() * weighted["price"]).fillna(0)
    too_small = weighted["trade_value"] < config.min_trade_value
    weighted.loc[too_small, "share_delta"] = 0.0
    weighted.loc[too_small, "trade_value"] = 0.0

    # Classify actions
    def classify(shares, delta_pct):
        if abs(shares) < 1e-6:
            return "hold"
        elif shares > 0:
            return "buy"
        else:
            return "sell"

    weighted["action"] = [
        classify(s, w) for s, w in zip(weighted["share_delta"], weighted["weight_delta"])
    ]

    # Tax-loss harvesting overlay
    if config.enable_tlh and cost_basis is not None:
        weighted = _apply_tlh_overlay(weighted, current_prices, cost_basis, config)

    # Apply turnover constraint
    turnover = weighted["trade_value"].sum() / (2 * portfolio_value)  # one-way
    if turnover > config.max_turnover:
        scale = config.max_turnover / max(turnover, 1e-10)
        weighted["share_delta"] = (weighted["share_delta"] * scale).round(0)
        weighted["trade_value"] = (weighted["share_delta"].abs() * weighted["price"]).fillna(0)
        weighted["action"] = [
            classify(s, w) for s, w in zip(weighted["share_delta"], weighted["weight_delta"])
        ]

    # Build trade list (non-hold only)
    trades = weighted[weighted["action"] != "hold"].reset_index()
    trades["reason"] = "drift"  # will be overridden for TLH

    return trades[["ticker", "action", "share_delta", "trade_value", "weight_delta", "reason"]].rename(
        columns={"share_delta": "shares", "weight_delta": "weight_change"}
    )


def _apply_tlh_overlay(
    weighted: pd.DataFrame,
    current_prices: pd.Series,
    cost_basis: pd.Series,
    config: RebalanceConfig,
) -> pd.DataFrame:
    """Tax-loss harvesting: sell positions with significant unrealized losses."""
    result = weighted.copy()

    for ticker in result.index:
        if ticker not in cost_basis.index or ticker not in current_prices.index:
            continue

        basis = cost_basis.get(ticker, 0)
        price = current_prices.get(ticker, 0)
        if basis <= 0 or price <= 0:
            continue

        loss_pct = (price - basis) / basis

        if loss_pct < -config.tlh_min_loss and result.loc[ticker, "action"] in {"sell", "hold"}:
            # Harvest the loss — increase sell quantity
            result.loc[ticker, "action"] = "sell"
            result.loc[ticker, "share_delta"] = -result.loc[ticker, "current_shares"]
            result.loc[ticker, "trade_value"] = abs(result.loc[ticker, "share_delta"]) * price
            result.loc[ticker, "reason"] = "tlh"

    return result


# ── Rebalance execution ────────────────────────────────────

@dataclass
class RebalanceResult:
    date: pd.Timestamp
    trades: pd.DataFrame
    turnover_pct: float
    estimated_cost_bp: float
    n_buys: int
    n_sells: int
    n_holds: int
    triggered_by: str  # "calendar" | "drift" | "hybrid"
    tlh_trades: int = 0


def run_rebalance(
    date: pd.Timestamp,
    current_weights: pd.Series,
    target_weights: pd.Series,
    current_prices: pd.Series,
    portfolio_value: float,
    config: RebalanceConfig,
    current_positions: Optional[pd.Series] = None,
    cost_basis: Optional[pd.Series] = None,
) -> RebalanceResult:
    """Execute a single rebalance event.

    Returns RebalanceResult with trade list and summary statistics.
    """
    # Check if we should rebalance
    last_date = None  # tracked externally via calling code
    next_cal = None

    if config.method in ("calendar", "hybrid"):
        cal_dates = generate_calendar_dates(
            pd.DatetimeIndex([date - timedelta(days=60), date + timedelta(days=60)]),
            config.calendar_freq,
        )
        future = cal_dates[cal_dates > date]
        next_cal = future[0] if len(future) > 0 else None

    triggered = should_rebalance(date, current_weights, target_weights, last_date, next_cal, config)

    if not triggered:
        return RebalanceResult(
            date=date, trades=pd.DataFrame(), turnover_pct=0,
            estimated_cost_bp=0, n_buys=0, n_sells=0, n_holds=len(current_weights),
            triggered_by="none",
        )

    trades = compute_trades(current_weights, target_weights, current_prices,
                            portfolio_value, config, current_positions, cost_basis)

    turnover = float(trades["trade_value"].sum() / max(portfolio_value, 1)) if not trades.empty else 0
    cost_bp = turnover * config.transaction_cost_bp

    n_buys = int((trades["action"] == "buy").sum()) if not trades.empty else 0
    n_sells = int((trades["action"] == "sell").sum()) if not trades.empty else 0
    n_tlh = int((trades.get("reason", "") == "tlh").sum()) if not trades.empty else 0

    # Determine trigger type
    adrift = check_drift(current_weights, target_weights, config.drift_threshold)
    if config.method == "calendar" and adrift:
        triggered_by = "calendar"
    elif adrift:
        triggered_by = "drift"
    else:
        triggered_by = "calendar"

    return RebalanceResult(
        date=date, trades=trades, turnover_pct=round(turnover * 100, 4),
        estimated_cost_bp=round(cost_bp, 2), n_buys=n_buys, n_sells=n_sells,
        n_holds=int((trades["action"] == "hold").sum()) if not trades.empty else 0,
        triggered_by=triggered_by, tlh_trades=n_tlh,
    )


def simulate_rebalance_series(
    dates: pd.DatetimeIndex,
    weight_history: pd.DataFrame,
    target_weights: pd.DataFrame,
    price_history: pd.DataFrame,
    portfolio_values: pd.Series,
    config: RebalanceConfig,
    position_history: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Simulate rebalancing over a historical period.

    Returns DataFrame with one row per rebalance event.
    """
    results = []
    last_rebalance = None
    calendar_dates = generate_calendar_dates(dates, config.calendar_freq) if config.method != "threshold" else pd.DatetimeIndex([])

    for i, date in enumerate(dates):
        if date not in weight_history.index or date not in price_history.index:
            continue

        cur_weights = weight_history.loc[date]
        cur_prices = price_history.loc[date]
        tgt_weights = target_weights.loc[date] if date in target_weights.index else target_weights.iloc[-1]
        port_val = portfolio_values.loc[date] if date in portfolio_values.index else portfolio_values.iloc[-1]

        next_cal = None
        if len(calendar_dates) > 0:
            future = calendar_dates[calendar_dates >= date]
            next_cal = future[0] if len(future) > 0 else None

        if should_rebalance(date, cur_weights, tgt_weights, last_rebalance, next_cal, config):
            result = run_rebalance(date, cur_weights, tgt_weights, cur_prices, port_val, config)
            if result.triggered_by != "none" and not result.trades.empty:
                results.append(result)
                last_rebalance = date

    if not results:
        return pd.DataFrame()

    rows = []
    for r in results:
        rows.append({
            "date": r.date,
            "n_buys": r.n_buys,
            "n_sells": r.n_sells,
            "turnover_pct": r.turnover_pct,
            "estimated_cost_bp": r.estimated_cost_bp,
            "triggered_by": r.triggered_by,
            "tlh_trades": r.tlh_trades,
        })
    return pd.DataFrame(rows).set_index("date").sort_index()


def estimate_rebalance_cost(
    trades: pd.DataFrame,
    portfolio_value: float,
    spread_bp: float = 5.0,
    market_impact_bp_per_pct: float = 2.0,
) -> Dict:
    """Estimate total rebalance cost: spread + market impact.

    Returns dict with cost breakdown.
    """
    if trades.empty:
        return {"total_cost_bp": 0, "spread_cost_bp": 0, "impact_cost_bp": 0, "n_trades": 0}

    turnover_pct = float(trades["trade_value"].sum() / portfolio_value)
    spread_cost = spread_bp * turnover_pct * 2  # both sides
    impact_cost = market_impact_bp_per_pct * turnover_pct * 100

    return {
        "total_cost_bp": round(spread_cost + impact_cost, 2),
        "spread_cost_bp": round(spread_cost, 2),
        "impact_cost_bp": round(impact_cost, 2),
        "n_trades": len(trades),
        "turnover_pct": round(turnover_pct * 100, 4),
    }


def report_markdown(result: RebalanceResult) -> str:
    """Generate markdown rebalance report."""
    lines = [
        "# Portfolio Rebalance Report",
        f"**Date**: {result.date.strftime('%Y-%m-%d')}  ",
        f"**Trigger**: {result.triggered_by}  ",
        f"**Turnover**: {result.turnover_pct:.2f}%  ",
        f"**Est. Cost**: {result.estimated_cost_bp:.1f} bp  ",
        "",
        f"**Buys**: {result.n_buys} | **Sells**: {result.n_sells} | "
        f"**Holds**: {result.n_holds} | **TLH**: {result.tlh_trades}",
        "",
    ]

    if result.trades.empty:
        lines.append("No trades required.")
        return "\n".join(lines)

    lines += [
        "| Ticker | Action | Shares | Value | Weight Δ | Reason |",
        "|--------|--------|--------|-------|----------|--------|",
    ]

    for _, t in result.trades.iterrows():
        lines.append(
            f"| {t['ticker']} | {t['action']} | {t['shares']:.0f} | "
            f"${t['trade_value']:,.0f} | {t.get('weight_change', 0):.2%} | "
            f"{t.get('reason', 'drift')} |"
        )

    lines.append("")
    lines.append("*Auto-generated by rebalancer.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────

def _make_demo_data(
    n_dates: int = 252, n_tickers: int = 5, seed: int = 42,
) -> Tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")

    prices = pd.DataFrame(index=dates)
    for i in range(n_tickers):
        ticker = f"T{i}"
        prices[ticker] = 100 + np.cumsum(rng.normal(0.05, 1.5, n_dates))

    # Simulate drifting weights from equal-weight start
    tickers = [f"T{i}" for i in range(n_tickers)]
    weights = pd.DataFrame(index=dates, columns=tickers)
    weights.iloc[0] = 1.0 / n_tickers
    for d in range(1, n_dates):
        ret = prices.iloc[d] / prices.iloc[d - 1] - 1
        prev_val = weights.iloc[d - 1] * (1 + ret)
        weights.iloc[d] = prev_val / prev_val.sum()

    target = pd.DataFrame(index=dates, columns=tickers)
    target.iloc[:] = [0.3, 0.25, 0.20, 0.15, 0.10]

    port_val = pd.Series(100_000 * (1 + rng.normal(0.0005, 0.01, n_dates)).cumprod(), index=dates)

    return dates, weights, target, prices, port_val


def main():
    dates, weights, target, prices, port_val = _make_demo_data(252, 5, seed=7)

    # Threshold rebalance
    config = RebalanceConfig(method="threshold", drift_threshold=0.05, max_turnover=0.30)
    events = simulate_rebalance_series(dates, weights, target, prices, port_val, config)
    print(f"Threshold rebalance: {len(events)} events over {len(dates)} days")
    if not events.empty:
        print(f"Avg turnover: {events['turnover_pct'].mean():.2f}%")
        print(f"Avg cost: {events['estimated_cost_bp'].mean():.1f} bp")

    # Single rebalance demo
    result = run_rebalance(
        dates[126], weights.iloc[126], target.iloc[126],
        prices.iloc[126], port_val.iloc[126], config,
    )
    print(f"\nSingle rebalance at {result.date.date()}:")
    print(report_markdown(result))


if __name__ == "__main__":
    main()
