#!/usr/bin/env python3
"""Backtest analytics — streak analysis, drawdown duration, monthly tables, rolling metrics.

Supplements harness.py metrics and visualization.py charts with numerical analysis
that can be used directly in reports."""


import numpy as np
import pandas as pd

# ── Streak Analysis ────────────────────────────────────────


def analyze_streaks(returns: pd.Series) -> dict:
    """Analyze winning/losing streaks from daily returns.

    Returns dict with max_win_streak, max_loss_streak, avg_win_streak,
    avg_loss_streak, streak_distribution (DataFrame).
    """
    r = returns.dropna()
    if len(r) < 2:
        return {"error": "Insufficient data"}

    win = r > 0
    loss = r < 0
    streaks = []
    current_type = None
    current_len = 0

    for is_win, is_loss in zip(win, loss):
        if is_win:
            new_type = "win"
        elif is_loss:
            new_type = "loss"
        else:
            if current_len > 0:
                streaks.append((current_type, current_len))
            current_type = None
            current_len = 0
            continue

        if new_type == current_type:
            current_len += 1
        else:
            if current_len > 0:
                streaks.append((current_type, current_len))
            current_type = new_type
            current_len = 1

    if current_len > 0 and current_type is not None:
        streaks.append((current_type, current_len))

    if not streaks:
        return {"error": "No streaks found"}

    win_streaks = [s[1] for s in streaks if s[0] == "win"]
    loss_streaks = [s[1] for s in streaks if s[0] == "loss"]

    return {
        "n_streaks": len(streaks),
        "max_win_streak": max(win_streaks) if win_streaks else 0,
        "max_loss_streak": max(loss_streaks) if loss_streaks else 0,
        "avg_win_streak": round(float(np.mean(win_streaks)), 2) if win_streaks else 0,
        "avg_loss_streak": round(float(np.mean(loss_streaks)), 2)
        if loss_streaks
        else 0,
        "median_win_streak": float(np.median(win_streaks)) if win_streaks else 0,
        "median_loss_streak": float(np.median(loss_streaks)) if loss_streaks else 0,
        "total_win_days": sum(win_streaks),
        "total_loss_days": sum(loss_streaks),
    }


# ── Drawdown Duration ──────────────────────────────────────


def analyze_drawdown_duration(equity: pd.Series) -> dict:
    """Analyze time underwater: duration, recovery, drawdown depth.

    Returns dict with drawdown statistics.
    """
    eq = equity.dropna()
    if len(eq) < 2:
        return {"error": "Insufficient data"}

    peak = eq.expanding().max()
    dd = (eq - peak) / peak
    in_dd = dd < -1e-8

    # Identify drawdown periods
    periods = []
    current_start = None
    current_start_idx = 0
    current_peak = eq.iloc[0]

    for i, (t, val) in enumerate(eq.items()):
        if val > current_peak:
            current_peak = val
            if current_start is not None:
                periods.append(
                    {
                        "start": current_start,
                        "end": t,
                        "duration_days": (
                            pd.Timestamp(t) - pd.Timestamp(current_start)
                        ).days
                        if hasattr(t, "days")
                        else i,
                        "peak": float(current_peak),
                        "trough": float(eq.iloc[current_start_idx : i + 1].min()),
                        "max_drawdown": float(
                            (eq.iloc[current_start_idx : i + 1].min() - current_peak)
                            / current_peak
                        ),
                    }
                )
                current_start = None
        elif in_dd.iloc[i] and current_start is None:
            current_start = t
            current_start_idx = i

    if current_start is not None and in_dd.iloc[-1]:
        periods.append(
            {
                "start": current_start,
                "end": eq.index[-1],
                "duration_days": len(eq) - current_start_idx,
                "peak": float(current_peak),
                "trough": float(eq.iloc[current_start_idx:].min()),
                "max_drawdown": float(
                    (eq.iloc[current_start_idx:].min() - current_peak) / current_peak
                ),
                "ongoing": True,
            }
        )

    # Compute simplified durations from daily drawdown flags
    dd_flags = in_dd.astype(int)
    dd_runs = (dd_flags.diff() != 0).cumsum()
    dd_durations = dd_flags.groupby(dd_runs).sum()
    dd_durations = dd_durations[dd_durations > 0]

    durations = dd_durations.values if len(dd_durations) > 0 else [0]

    return {
        "max_drawdown": float(dd.min()),
        "avg_drawdown": float(dd[dd < 0].mean()) if (dd < 0).any() else 0,
        "max_dd_duration_days": int(max(durations)),
        "avg_dd_duration_days": round(float(np.mean(durations)), 1),
        "median_dd_duration_days": float(np.median(durations)),
        "time_in_drawdown_pct": round(float((dd < -1e-8).mean()) * 100, 1),
        "n_drawdowns": len(dd_durations),
        "longest_dd_details": periods[-1] if periods else None,
    }


# ── Monthly / Annual Returns Tables ────────────────────────


def monthly_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Generate monthly returns table (years × months) as DataFrame.

    Returns DataFrame with years as rows and months as columns.
    """
    r = returns.dropna()
    idx = r.index if isinstance(r.index, pd.DatetimeIndex) else pd.to_datetime(r.index)

    monthly = r.groupby([idx.year, idx.month]).apply(lambda x: (1 + x).prod() - 1)
    matrix = monthly.unstack()
    cols = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }
    matrix.columns = [cols.get(c, str(c)) for c in matrix.columns]
    annual = r.groupby(idx.year).apply(lambda x: (1 + x).prod() - 1)
    matrix["Annual"] = [annual.loc[y] for y in matrix.index]
    matrix.index.name = "Year"
    return matrix


def annual_returns_table(returns: pd.Series) -> pd.DataFrame:
    """Annual returns with volatility and Sharpe."""
    r = returns.dropna()
    idx = r.index if isinstance(r.index, pd.DatetimeIndex) else pd.to_datetime(r.index)

    annual_ret = r.groupby(idx.year).apply(lambda x: (1 + x).prod() - 1)
    annual_vol = r.groupby(idx.year).apply(lambda x: float(x.std() * np.sqrt(252)))
    annual_sharpe = (annual_ret - 0.02) / annual_vol.replace(0, np.nan)

    return pd.DataFrame(
        {
            "return": annual_ret,
            "volatility": annual_vol,
            "sharpe": annual_sharpe,
        }
    )


# ── Profit/Loss Ratio ──────────────────────────────────────


def profit_loss_ratio(returns: pd.Series) -> dict:
    """Detailed profit/loss analysis with tail analysis."""
    r = returns.dropna().values
    if len(r) < 5:
        return {"error": "Insufficient data"}

    wins = r[r > 0]
    losses = r[r < 0]
    n_wins = len(wins)
    n_losses = len(losses)

    avg_win = float(np.mean(wins)) if n_wins > 0 else 0
    avg_loss = float(np.mean(losses)) if n_losses > 0 else 0
    plr = abs(avg_win / avg_loss) if avg_loss != 0 else np.inf

    gross_win = float(np.sum(wins))
    gross_loss = float(abs(np.sum(losses)))
    pf = gross_win / gross_loss if gross_loss > 0 else np.inf

    # Tail: top/bottom 5% returns
    q95 = float(np.percentile(r, 95))
    q5 = float(np.percentile(r, 5))
    tail_ratio = abs(q95 / q5) if q5 != 0 else np.inf

    return {
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": round(float(n_wins / len(r)), 4),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_loss_ratio": round(plr, 4) if plr < 1e6 else 999.0,
        "profit_factor": round(pf, 4) if pf < 1e6 else 999.0,
        "gross_win": round(gross_win, 6),
        "gross_loss": round(gross_loss, 6),
        "largest_win": round(float(np.max(wins)), 6) if n_wins > 0 else 0,
        "largest_loss": round(float(np.min(losses)), 6) if n_losses > 0 else 0,
        "tail_ratio_95_05": round(tail_ratio, 4) if tail_ratio < 1e6 else 999.0,
    }


# ── Rolling Metrics DataFrame ──────────────────────────────


def rolling_metrics_df(
    returns: pd.Series, windows: list[int] | None = None
) -> pd.DataFrame:
    """Compute rolling Sharpe, vol, return, VaR as DataFrame.

    Args:
        returns: daily returns
        windows: list of window lengths (default: [21, 63, 126])

    Returns DataFrame with columns like sharpe_63, vol_63, etc.
    """
    if windows is None:
        windows = [21, 63, 126]

    r = returns.dropna()
    ppy = 252
    results = {}

    for w in windows:
        roll_ret = r.rolling(w).mean() * ppy
        roll_vol = r.rolling(w).std() * np.sqrt(ppy)
        roll_sharpe = (roll_ret - 0.02) / roll_vol.replace(0, np.nan)
        roll_var95 = r.rolling(w).quantile(0.05)

        results[f"sharpe_{w}"] = roll_sharpe
        results[f"vol_{w}"] = roll_vol
        results[f"return_{w}"] = roll_ret
        results[f"var95_{w}"] = roll_var95

    return pd.DataFrame(results, index=r.index)


# ── Full Analytics Report ──────────────────────────────────


def full_analytics(returns: pd.Series, equity: pd.Series, ppy: int = 252) -> dict:
    """Run all backtest analytics and return comprehensive dict.

    Returns dict with: pl_ratio, streaks, drawdown_duration,
    monthly_table, annual_table, rolling_df.
    """
    return {
        "pl_ratio": profit_loss_ratio(returns),
        "streaks": analyze_streaks(returns),
        "drawdown_duration": analyze_drawdown_duration(equity),
        "monthly_table": monthly_returns_table(returns),
        "annual_table": annual_returns_table(returns),
        "rolling_df": rolling_metrics_df(returns),
    }


# ── Markdown Report ────────────────────────────────────────


def analytics_report_markdown(analytics: dict) -> str:
    """Generate markdown report from full_analytics output."""
    from datetime import datetime

    lines = [
        "# Backtest Analytics Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Profit/Loss
    pl = analytics.get("pl_ratio", {})
    if pl and "error" not in pl:
        lines += [
            "## Profit / Loss Analysis",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Win Rate | {pl['win_rate']:.2%} |",
            f"| # Wins / # Losses | {pl['n_wins']} / {pl['n_losses']} |",
            f"| Avg Win | {pl['avg_win']:.4%} |",
            f"| Avg Loss | {pl['avg_loss']:.4%} |",
            f"| Profit/Loss Ratio | {pl['profit_loss_ratio']:.2f} |",
            f"| Profit Factor | {pl['profit_factor']:.2f} |",
            f"| Largest Win | {pl['largest_win']:.4%} |",
            f"| Largest Loss | {pl['largest_loss']:.4%} |",
            f"| Tail Ratio (95/05) | {pl['tail_ratio_95_05']:.2f} |",
            "",
        ]

    # Streaks
    st = analytics.get("streaks", {})
    if st and "error" not in st:
        lines += [
            "## Streak Analysis",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Max Win Streak | {st['max_win_streak']} days |",
            f"| Max Loss Streak | {st['max_loss_streak']} days |",
            f"| Avg Win Streak | {st['avg_win_streak']} days |",
            f"| Avg Loss Streak | {st['avg_loss_streak']} days |",
            f"| Total Win Days | {st['total_win_days']} |",
            f"| Total Loss Days | {st['total_loss_days']} |",
            "",
        ]

    # Drawdown Duration
    dd = analytics.get("drawdown_duration", {})
    if dd and "error" not in dd:
        lines += [
            "## Drawdown Duration Analysis",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Max DD | {dd['max_drawdown']:.2%} |",
            f"| Max DD Duration | {dd['max_dd_duration_days']} days |",
            f"| Avg DD Duration | {dd['avg_dd_duration_days']} days |",
            f"| Median DD Duration | {dd['median_dd_duration_days']} days |",
            f"| Time in Drawdown | {dd['time_in_drawdown_pct']}% |",
            f"| # Drawdown Events | {dd['n_drawdowns']} |",
            "",
        ]

    # Monthly table
    mt = analytics.get("monthly_table")
    if mt is not None and not mt.empty:
        lines += ["## Monthly Returns", ""]
        lines.append(mt.to_markdown(floatfmt=".2%"))
        lines.append("")

    # Annual table
    at = analytics.get("annual_table")
    if at is not None and not at.empty:
        lines += ["## Annual Returns", ""]
        lines.append(at.to_markdown(floatfmt=".4f"))
        lines.append("")

    lines.append("*Auto-generated by analytics.py*")
    return "\n".join(lines)


# ── Demo ────────────────────────────────────────────────────


def _make_demo_data(n: int = 504, seed: int = 42) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    returns = pd.Series(rng.normal(0.0006, 0.012, n), index=dates)
    equity = (1 + returns).cumprod()
    return returns, equity


def main():
    returns, equity = _make_demo_data(504, seed=7)

    analytics = full_analytics(returns, equity)
    print(analytics_report_markdown(analytics))

    # Print key insights
    pl = analytics["pl_ratio"]
    st = analytics["streaks"]
    dd = analytics["drawdown_duration"]
    print("\nKey Insights:")
    print(f"  P/L Ratio: {pl['profit_loss_ratio']:.2f}")
    print(f"  Win Rate: {pl['win_rate']:.2%}")
    print(f"  Max Win Streak: {st['max_win_streak']}d")
    print(f"  Max Loss Streak: {st['max_loss_streak']}d")
    print(f"  Max DD: {dd['max_drawdown']:.2%} ({dd['max_dd_duration_days']}d)")
    print(f"  Time in DD: {dd['time_in_drawdown_pct']}%")


if __name__ == "__main__":
    main()
