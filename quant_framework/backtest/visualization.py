#!/usr/bin/env python3
"""Backtest visualization — equity curves, drawdowns, heatmaps, rolling metrics.

Uses matplotlib (object-oriented API). All charts take pd.Series/DataFrame inputs
from the backtest harness or execution simulator."""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
from typing import Optional, Dict, Tuple


# ── Style defaults ───────────────────────────────────────
plt.rcParams.update(
    {
        "figure.facecolor": "#1a1a2e",
        "axes.facecolor": "#16213e",
        "axes.edgecolor": "#0f3460",
        "axes.labelcolor": "#e0e0e0",
        "text.color": "#e0e0e0",
        "xtick.color": "#a0a0a0",
        "ytick.color": "#a0a0a0",
        "grid.color": "#2a2a4e",
        "grid.alpha": 0.6,
        "legend.facecolor": "#1a1a2e",
        "legend.edgecolor": "#0f3460",
        "figure.titlesize": 14,
        "axes.titlesize": 12,
    }
)
COLORS = {
    "equity": "#00d2ff",
    "drawdown": "#ff6b6b",
    "benchmark": "#f0c040",
    "positive": "#00d2ff",
    "negative": "#ff6b6b",
    "watermark": "#e94560",
}


def equity_curve(
    equity: pd.Series,
    benchmark: Optional[pd.Series] = None,
    title: str = "Equity Curve",
    figsize: Tuple[int, int] = (14, 6),
) -> plt.Figure:
    """Plot equity curve with optional benchmark overlay."""
    fig, ax = plt.subplots(figsize=figsize)
    eq_norm = equity / equity.iloc[0]
    ax.plot(
        eq_norm.index,
        eq_norm.values,
        color=COLORS["equity"],
        linewidth=1.5,
        label="Strategy",
    )
    ax.fill_between(
        eq_norm.index,
        1,
        eq_norm.values,
        where=(eq_norm.values >= 1),
        color=COLORS["equity"],
        alpha=0.15,
    )
    ax.fill_between(
        eq_norm.index,
        1,
        eq_norm.values,
        where=(eq_norm.values < 1),
        color=COLORS["drawdown"],
        alpha=0.15,
    )

    if benchmark is not None:
        bm_norm = benchmark / benchmark.iloc[0]
        ax.plot(
            bm_norm.index,
            bm_norm.values,
            color=COLORS["benchmark"],
            linewidth=1,
            linestyle="--",
            alpha=0.8,
            label="Benchmark",
        )

    ax.axhline(y=1, color="white", linewidth=0.5, linestyle="--", alpha=0.3)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel("Normalized Value (1.0 = start)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def drawdown_plot(
    equity: pd.Series, top_n: int = 5, figsize: Tuple[int, int] = (14, 6)
) -> plt.Figure:
    """Underwater plot showing drawdowns over time."""
    peak = equity.expanding().max()
    dd = (equity - peak) / peak

    fig, ax = plt.subplots(figsize=figsize)
    ax.fill_between(dd.index, 0, dd.values, color=COLORS["drawdown"], alpha=0.4)
    ax.plot(dd.index, dd.values, color=COLORS["drawdown"], linewidth=0.8)

    # Mark top-N drawdown troughs
    if len(dd) > 0:
        troughs = dd.nsmallest(top_n)
        for d, v in troughs.items():
            ax.annotate(
                f"{v:.1%}",
                (d, v),
                textcoords="offset points",
                xytext=(0, -12),
                ha="center",
                fontsize=8,
                color=COLORS["drawdown"],
            )

    ax.axhline(y=0, color="white", linewidth=0.5, alpha=0.3)
    ax.set_title("Drawdown (Underwater Plot)", fontweight="bold")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def monthly_returns_heatmap(
    returns: pd.Series, figsize: Tuple[int, int] = (12, 8)
) -> plt.Figure:
    """Monthly returns heatmap (years × months)."""
    if isinstance(returns.index, pd.DatetimeIndex):
        idx = returns.index
    else:
        idx = pd.to_datetime(returns.index)

    monthly = returns.groupby([idx.year, idx.month]).apply(lambda x: (1 + x).prod() - 1)
    matrix = monthly.unstack()
    matrix.columns = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ][: len(matrix.columns)]

    fig, ax = plt.subplots(figsize=figsize)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "quant_cmap", [COLORS["drawdown"], "#1a1a2e", COLORS["equity"]]
    )
    vmax = max(abs(matrix.max().max()), abs(matrix.min().min()), 0.01)
    im = ax.imshow(matrix.values, aspect="auto", cmap=cmap, vmin=-vmax, vmax=vmax)

    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=0)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)

    for y in range(len(matrix.index)):
        for x in range(len(matrix.columns)):
            val = matrix.iloc[y, x]
            if not np.isnan(val):
                ax.text(
                    x,
                    y,
                    f"{val:.1%}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if abs(val) > vmax * 0.4 else "#a0a0a0",
                )

    ax.set_title("Monthly Returns Heatmap", fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    fig.tight_layout()
    return fig


def rolling_metrics(
    returns: pd.Series, window: int = 63, figsize: Tuple[int, int] = (14, 8)
) -> plt.Figure:
    """Rolling Sharpe, volatility, and cumulative return."""
    ppy = 252
    roll_ret = returns.rolling(window).mean() * ppy
    roll_vol = returns.rolling(window).std() * np.sqrt(ppy)
    roll_sharpe = (roll_ret - 0.02) / roll_vol.replace(0, np.nan)

    fig, axes = plt.subplots(3, 1, figsize=figsize, sharex=True)

    axes[0].plot(returns.index, roll_sharpe.values, color=COLORS["equity"], linewidth=1)
    axes[0].axhline(y=0, color="white", linewidth=0.5, alpha=0.3)
    axes[0].set_title(f"Rolling Sharpe Ratio ({window}-day)", fontweight="bold")
    axes[0].set_ylabel("Sharpe")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(returns.index, roll_vol.values, color=COLORS["watermark"], linewidth=1)
    axes[1].set_title(f"Rolling Volatility ({window}-day)", fontweight="bold")
    axes[1].set_ylabel("Annualized Vol")
    axes[1].yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    axes[1].grid(True, alpha=0.3)

    cum = (1 + returns).cumprod()
    axes[2].plot(cum.index, cum.values, color=COLORS["equity"], linewidth=1.2)
    axes[2].fill_between(cum.index, 1, cum.values, alpha=0.15, color=COLORS["equity"])
    axes[2].axhline(y=1, color="white", linewidth=0.5, alpha=0.3)
    axes[2].set_title("Cumulative Return", fontweight="bold")
    axes[2].set_ylabel("Growth of $1")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def annual_returns(
    returns: pd.Series, figsize: Tuple[int, int] = (12, 5)
) -> plt.Figure:
    """Annual returns bar chart with cumulative overlay."""
    if isinstance(returns.index, pd.DatetimeIndex):
        idx = returns.index
    else:
        idx = pd.to_datetime(returns.index)

    annual = returns.groupby(idx.year).apply(lambda x: (1 + x).prod() - 1)

    fig, ax = plt.subplots(figsize=figsize)
    colors = [COLORS["equity"] if v >= 0 else COLORS["drawdown"] for v in annual.values]
    ax.bar(
        range(len(annual)),
        annual.values,
        color=colors,
        alpha=0.85,
        edgecolor="white",
        linewidth=0.3,
    )
    ax.set_xticks(range(len(annual)))
    ax.set_xticklabels(annual.index)
    ax.set_title("Annual Returns", fontweight="bold")
    ax.set_ylabel("Return")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.axhline(y=0, color="white", linewidth=0.5, alpha=0.3)

    for i, v in enumerate(annual.values):
        ax.text(
            i,
            v + (0.02 if v >= 0 else -0.04),
            f"{v:.1%}",
            ha="center",
            fontsize=9,
            color="white",
        )

    ax.grid(True, alpha=0.2, axis="y")
    fig.tight_layout()
    return fig


def return_distribution(
    returns: pd.Series, figsize: Tuple[int, int] = (12, 5)
) -> plt.Figure:
    """Return distribution histogram with normal overlay."""
    r = returns.dropna().values
    mu, sigma = float(np.mean(r)), float(np.std(r))

    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(
        r * 100,
        bins=50,
        density=True,
        alpha=0.7,
        color=COLORS["equity"],
        edgecolor="white",
        linewidth=0.2,
    )
    x = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
    ax.plot(
        x * 100,
        1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((x - mu) / sigma) ** 2),
        color=COLORS["watermark"],
        linewidth=2,
        label=f"Normal (μ={mu:.4f}, σ={sigma:.4f})",
    )

    ax.axvline(x=0, color="white", linewidth=0.5, alpha=0.3)
    ax.axvline(x=mu * 100, color=COLORS["benchmark"], linewidth=0.5, linestyle="--")
    ax.set_title("Return Distribution", fontweight="bold")
    ax.set_xlabel("Daily Return (%)")
    ax.set_ylabel("Density")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.2, axis="y")

    # Skew/kurtosis annotation
    from scipy.stats import skew, kurtosis

    s = float(skew(r, bias=False))
    k = float(kurtosis(r, bias=False))
    ax.text(
        0.02,
        0.95,
        f"Skew: {s:.3f}  |  Ex-Kurt: {k:.3f}",
        transform=ax.transAxes,
        fontsize=9,
        color="#a0a0a0",
        verticalalignment="top",
    )

    fig.tight_layout()
    return fig


def full_report(
    equity: pd.Series,
    returns: pd.Series,
    benchmark: Optional[pd.Series] = None,
    output_dir: str = "company/reports",
    prefix: str = "backtest",
) -> Dict[str, Path]:
    """Generate full visualization report — all charts saved as PNG."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}

    figs = {
        "equity": equity_curve(equity, benchmark),
        "drawdown": drawdown_plot(equity),
        "monthly_heatmap": monthly_returns_heatmap(returns),
        "rolling_metrics": rolling_metrics(returns),
        "annual_returns": annual_returns(returns),
        "return_dist": return_distribution(returns),
    }

    for name, fig in figs.items():
        path = out / f"{prefix}_{name}.png"
        fig.savefig(str(path), dpi=120, bbox_inches="tight", facecolor="#1a1a2e")
        plt.close(fig)
        paths[name] = path

    return paths


def _make_demo_equity(n: int = 504, seed: int = 42) -> Tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    returns = pd.Series(rng.normal(0.0006, 0.012, n), index=dates)
    equity = (1 + returns).cumprod()
    return equity, returns


def main():
    equity, returns = _make_demo_equity(504)
    paths = full_report(equity, returns, prefix="demo")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print("Done — all charts saved.")


if __name__ == "__main__":
    main()
