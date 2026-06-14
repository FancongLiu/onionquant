#!/usr/bin/env python3
"""
Technical Analysis: Memory/Semiconductor Stocks
MU (Micron), 005930.KS (Samsung Electronics), 000660.KS (SK Hynix)

Context: Wall Street banks restricted leverage on Samsung/SK Hynix/TSMC on June 12, 2026.
This script performs daily candlestick technical analysis on 6 months of data.

Outputs:
  - Console summary table
  - Markdown report: company/departments/strategy_research/tech_report_20260612.md
"""

import os
import sys
from datetime import datetime

import pandas as pd
import yfinance as yf

# ── Config ──────────────────────────────────────────────────────────────────
TICKERS = ["MU", "005930.KS", "000660.KS"]
TICKER_LABELS = {
    "MU": "Micron Technology",
    "005930.KS": "Samsung Electronics (Common)",
    "000660.KS": "SK Hynix",
}
PERIOD = "6mo"
REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "company", "departments", "strategy_research", "tech_report_20260612.md",
)

# ── Helper functions ────────────────────────────────────────────────────────


def download_single(ticker: str) -> pd.DataFrame:
    """Download 6mo of daily data for a single ticker, flatten columns."""
    print(f"  Downloading {ticker} ({TICKER_LABELS.get(ticker, '')}) ...")
    df = yf.download(ticker, period=PERIOD, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    # yfinance returns multi-level columns, squeeze to flat
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    # Ensure standard column names
    expected = ["Open", "High", "Low", "Close", "Volume"]
    for c in expected:
        if c not in df.columns:
            raise KeyError(f"Missing column '{c}' in {ticker} data")
    # Remove timezone info from index for cleaner output
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (MACD line, Signal line, Histogram)."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Return (middle, upper, lower) Bollinger Bands."""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


def support_resistance(df: pd.DataFrame, window: int = 20) -> dict:
    """
    Identify key support/resistance levels using local minima/maxima
    over the trailing window plus ATH and recent swing points.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Rolling local maxima (resistance)
    roll_max = high.rolling(window=window, center=True).max()
    resistance_levels = []
    for i in range(window, len(df) - window):
        if high.iloc[i] == roll_max.iloc[i]:
            resistance_levels.append(round(float(high.iloc[i]), 2))

    # Rolling local minima (support)
    roll_min = low.rolling(window=window, center=True).min()
    support_levels = []
    for i in range(window, len(df) - window):
        if low.iloc[i] == roll_min.iloc[i]:
            support_levels.append(round(float(low.iloc[i]), 2))

    # Deduplicate and sort (unique within 1%)
    def dedup_levels(levels: list, pct: float = 0.01):
        if not levels:
            return []
        levels = sorted(set(levels))
        result = [levels[0]]
        for lvl in levels[1:]:
            if lvl > result[-1] * (1 + pct):
                result.append(lvl)
        return result

    support = dedup_levels(support_levels)
    resistance = dedup_levels(resistance_levels)

    # Add ATH
    ath = round(float(high.max()), 2)
    if ath not in resistance:
        resistance.append(ath)
        resistance = sorted(set(resistance))

    last_close = round(float(close.iloc[-1]), 2)

    # Filter: nearest levels below/above current price
    support_below = [s for s in support if s < last_close]
    resistance_above = [r for r in resistance if r > last_close]

    # Take the 3 nearest
    support_below = sorted(support_below, reverse=True)[:3]
    resistance_above = sorted(resistance_above)[:3]

    return {
        "support": support_below,
        "resistance": resistance_above,
        "ath": ath,
        "close": last_close,
    }


def distribution_days(df: pd.DataFrame, threshold: float = -0.2) -> dict:
    """
    Count distribution days (down > threshold% on above-average volume)
    and accumulation days (up > threshold% on above-average volume).
    """
    close = df["Close"]
    volume = df["Volume"]
    avg_vol = volume.rolling(window=50).mean()
    daily_return = close.pct_change() * 100

    dist_days = df[(daily_return < threshold) & (volume > avg_vol)]
    accum_days = df[(daily_return > threshold) & (volume > avg_vol)]

    return {
        "distribution_count": len(dist_days),
        "accumulation_count": len(accum_days),
        "distribution_recent": [
            str(d.date()) for d in dist_days.index[-5:].tolist()
        ],
    }


def analyze_ticker(ticker: str, df: pd.DataFrame) -> dict:
    """Run full technical analysis on one ticker."""
    close = df["Close"]
    volume = df["Volume"]
    last_close = float(close.iloc[-1])
    last_date = str(df.index[-1].date())

    # Moving averages
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None

    # Distance from MAs
    vs_ma20 = (last_close / ma20 - 1) * 100
    vs_ma50 = (last_close / ma50 - 1) * 100
    vs_ma200 = (last_close / ma200 - 1) * 100 if ma200 else None

    # RSI
    rsi_series = compute_rsi(close)
    rsi = round(float(rsi_series.iloc[-1]), 1)

    # MACD
    macd_line, signal_line, histogram = compute_macd(close)
    macd_val = round(float(macd_line.iloc[-1]), 4)
    macd_signal_val = round(float(signal_line.iloc[-1]), 4)
    macd_hist = round(float(histogram.iloc[-1]), 4)
    macd_cross = "bullish" if macd_val > macd_signal_val else "bearish"

    # Bollinger
    bb_mid, bb_upper, bb_lower = compute_bollinger(close)
    bb_mid_val = round(float(bb_mid.iloc[-1]), 2)
    bb_upper_val = round(float(bb_upper.iloc[-1]), 2)
    bb_lower_val = round(float(bb_lower.iloc[-1]), 2)
    bb_position = (last_close - bb_lower_val) / (bb_upper_val - bb_lower_val) * 100
    bb_position = round(bb_position, 1)

    # Support / Resistance
    sr = support_resistance(df)

    # Volume trends
    avg_vol_20 = float(volume.tail(20).mean())
    avg_vol_50 = float(volume.tail(50).mean()) if len(df) >= 50 else avg_vol_20
    rel_vol = avg_vol_20 / avg_vol_50 if avg_vol_50 > 0 else 1.0

    dist_info = distribution_days(df)

    # Price performance
    pct_1w = (last_close / float(close.iloc[-6]) - 1) * 100 if len(df) >= 6 else None
    pct_1m = (last_close / float(close.iloc[-22]) - 1) * 100 if len(df) >= 22 else None
    pct_3m = (last_close / float(close.iloc[-66]) - 1) * 100 if len(df) >= 66 else None
    high_3m = round(float(df["High"].tail(66).max()), 2)
    low_3m = round(float(df["Low"].tail(66).min()), 2)
    ath = round(float(df["High"].max()), 2)

    return {
        "ticker": ticker,
        "name": TICKER_LABELS.get(ticker, ticker),
        "last_close": last_close,
        "last_date": last_date,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2) if ma200 else None,
        "vs_ma20_pct": round(vs_ma20, 1),
        "vs_ma50_pct": round(vs_ma50, 1),
        "vs_ma200_pct": round(vs_ma200, 1) if vs_ma200 is not None else None,
        "rsi14": rsi,
        "macd": macd_val,
        "macd_signal": macd_signal_val,
        "macd_hist": macd_hist,
        "macd_cross": macd_cross,
        "bb_mid": bb_mid_val,
        "bb_upper": bb_upper_val,
        "bb_lower": bb_lower_val,
        "bb_position_pct": bb_position,
        "support_levels": sr["support"],
        "resistance_levels": sr["resistance"],
        "ath": ath,
        "high_3m": high_3m,
        "low_3m": low_3m,
        "pct_1w": round(pct_1w, 1) if pct_1w is not None else None,
        "pct_1m": round(pct_1m, 1) if pct_1m is not None else None,
        "pct_3m": round(pct_3m, 1) if pct_3m is not None else None,
        "avg_vol_20d": int(avg_vol_20),
        "rel_vol_20v50": round(rel_vol, 2),
        "distribution_days": dist_info["distribution_count"],
        "accumulation_days": dist_info["accumulation_count"],
        "dist_recent_dates": dist_info["distribution_recent"],
    }


def rsi_interpretation(rsi: float) -> str:
    if rsi > 70:
        return "Overbought"
    elif rsi > 60:
        return "Bullish momentum"
    elif rsi > 40:
        return "Neutral"
    elif rsi > 30:
        return "Bearish momentum"
    else:
        return "Oversold"


def bb_interpretation(pos: float) -> str:
    if pos > 100:
        return "Above upper band (extreme)"
    elif pos > 80:
        return "Near upper band"
    elif pos > 50:
        return "Upper half"
    elif pos > 20:
        return "Lower half"
    else:
        return "Near/below lower band"


def ma_interpretation(vs_ma20: float, vs_ma50: float) -> str:
    if vs_ma20 > 0 and vs_ma50 > 0:
        return "Bullish (above both 20 & 50 MA)"
    elif vs_ma20 > 0:
        return "Near-term bullish (above 20, below 50)"
    elif vs_ma50 > 0:
        return "Mixed (below 20, above 50)"
    else:
        return "Bearish (below both 20 & 50 MA)"


def generate_report(results: list) -> str:
    """Generate a Markdown report string."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Memory/Semiconductor Technical Analysis Report",
        f"**Generated**: {now}",
        "**Context**: Wall Street banks restricted leverage on Samsung/SK Hynix/TSMC on June 12, 2026",
        "",
        "---",
        "",
    ]

    for r in results:
        ticker = r["ticker"]
        name = r["name"]
        lines.append(f"## {ticker} — {name}")
        lines.append("")
        lines.append("| Metric | Value | Interpretation |")
        lines.append("|--------|-------|----------------|")
        lines.append(f"| **Last Close** | {r['last_close']:,.2f} | {r['last_date']} |")
        lines.append(f"| **MA-20** | {r['ma20']:,.2f} | {r['vs_ma20_pct']:+.1f}% from close |")
        lines.append(f"| **MA-50** | {r['ma50']:,.2f} | {r['vs_ma50_pct']:+.1f}% from close |")

        if r["ma200"] is not None:
            lines.append(f"| **MA-200** | {r['ma200']:,.2f} | {r['vs_ma200_pct']:+.1f}% from close |")
        else:
            lines.append("| **MA-200** | N/A | < 200 days data |")

        lines.append(f"| **RSI-14** | {r['rsi14']} | {rsi_interpretation(r['rsi14'])} |")
        lines.append(f"| **MACD** | {r['macd']:.4f} | Signal: {r['macd_signal']:.4f} ({r['macd_cross']}) |")
        lines.append(f"| **MACD Histogram** | {r['macd_hist']:+.4f} | {'Rising' if r['macd_hist'] > 0 else 'Falling'} |")
        lines.append(f"| **Bollinger %B** | {r['bb_position_pct']:.1f}% | {bb_interpretation(r['bb_position_pct'])} |")
        lines.append(f"| **BB Upper** | {r['bb_upper']:,.2f} | — |")
        lines.append(f"| **BB Mid (20MA)** | {r['bb_mid']:,.2f} | — |")
        lines.append(f"| **BB Lower** | {r['bb_lower']:,.2f} | — |")
        lines.append("")

        # Support / Resistance
        if r["support_levels"]:
            lines.append("**Support Levels**: " + " | ".join(f"{s:,.2f}" for s in r["support_levels"]))
        else:
            lines.append("**Support Levels**: None detected below current price")
        if r["resistance_levels"]:
            lines.append("**Resistance Levels**: " + " | ".join(f"{s:,.2f}" for s in r["resistance_levels"]))
        else:
            lines.append("**Resistance Levels**: None detected above current price")

        lines.append("")

        lines.append("| Period | Return |")
        lines.append("|--------|--------|")
        lines.append(f"| 1 Week | {r['pct_1w']:+.1f}% |" if r['pct_1w'] is not None else "| 1 Week | N/A |")
        lines.append(f"| 1 Month | {r['pct_1m']:+.1f}% |" if r['pct_1m'] is not None else "| 1 Month | N/A |")
        lines.append(f"| 3 Month | {r['pct_3m']:+.1f}% |" if r['pct_3m'] is not None else "| 3 Month | N/A |")

        lines.append("")
        lines.append("| Range | High | Low |")
        lines.append("|-------|------|-----|")
        lines.append(f"| 3-Month | {r['high_3m']:,.2f} | {r['low_3m']:,.2f} |")
        lines.append(f"| All-Time (6mo) | {r['ath']:,.2f} | — |")
        lines.append("")

        lines.append("| Volume Metric | Value |")
        lines.append("|---------------|-------|")
        lines.append(f"| Avg Volume (20d) | {r['avg_vol_20d']:,} |")
        lines.append(f"| Rel Vol (20d vs 50d) | {r['rel_vol_20v50']:.2f}x |")
        lines.append(f"| Distribution Days | {r['distribution_days']} |")
        lines.append(f"| Accumulation Days | {r['accumulation_days']} |")
        lines.append("")

        lines.append(f"### Summary — {ticker}")
        lines.append("")
        summary_parts = []
        summary_parts.append(f"- Price is **{r['vs_ma20_pct']:+.1f}%** vs 20-day MA and **{r['vs_ma50_pct']:+.1f}%** vs 50-day MA")
        summary_parts.append(f"- RSI-14 at **{r['rsi14']}** — {rsi_interpretation(r['rsi14']).lower()}")
        summary_parts.append(f"- MACD is **{r['macd_cross']}** (histogram {r['macd_hist']:+.4f})")
        summary_parts.append(f"- Bollinger %B = **{r['bb_position_pct']:.1f}%** — {bb_interpretation(r['bb_position_pct']).lower()}")
        lines.extend(summary_parts)
        lines.append("")
        lines.append("---")
        lines.append("")

    # Overall assessment
    lines.append("## Overall Assessment")
    lines.append("")
    lines.append("| Ticker | Price | vs MA20 | vs MA50 | RSI-14 | MACD | BB %B |")
    lines.append("|--------|-------|---------|---------|--------|------|-------|")
    for r in results:
        lines.append(
            f"| {r['ticker']} | {r['last_close']:,.2f} | {r['vs_ma20_pct']:+.1f}% | {r['vs_ma50_pct']:+.1f}% "
            f"| {r['rsi14']} | {r['macd_cross']} | {r['bb_position_pct']:.1f}% |"
        )
    lines.append("")

    lines.append("### Key Observations (AI to expand)")
    lines.append("")
    lines.append("1. **MU** — ...")
    lines.append("2. **005930.KS (Samsung)** — ...")
    lines.append("3. **000660.KS (SK Hynix)** — ...")
    lines.append("")
    lines.append("---")
    lines.append("*Report auto-generated by scripts/tech_analysis_memory_stocks.py*")

    return "\n".join(lines)


def print_summary_table(results: list):
    """Print a compact console summary."""
    header = f"{'Ticker':<12} {'Close':>12} {'MA20':>10} {'MA50':>10} {'RSI':>6} {'MACD':>8} {'BB%B':>6} {'1W':>7} {'1M':>7} {'Dist':>5}"
    sep = "-" * len(header)
    print("\n" + "=" * len(header))
    print("  TECHNICAL ANALYSIS SUMMARY — Memory/Semiconductor Stocks")
    print("=" * len(header))
    print(header)
    print(sep)
    for r in results:
        pct_1w = f"{r['pct_1w']:+.1f}%" if r['pct_1w'] is not None else "N/A"
        pct_1m = f"{r['pct_1m']:+.1f}%" if r['pct_1m'] is not None else "N/A"
        print(
            f"{r['ticker']:<12} {r['last_close']:>12,.2f} {r['vs_ma20_pct']:>+9.1f}% "
            f"{r['vs_ma50_pct']:>+9.1f}% {r['rsi14']:>6.1f} {r['macd_cross']:>8} "
            f"{r['bb_position_pct']:>5.1f}% {pct_1w:>7} {pct_1m:>7} {r['distribution_days']:>5}"
        )
    print(sep)

    # Support / Resistance summary
    print("\n  SUPPORT / RESISTANCE LEVELS:")
    for r in results:
        sup = ", ".join(f"{s:,.0f}" for s in r["support_levels"]) if r["support_levels"] else "None below"
        res = ", ".join(f"{s:,.0f}" for s in r["resistance_levels"]) if r["resistance_levels"] else "None above"
        print(f"  {r['ticker']:<12} Support: {sup}")
        print(f"  {'':12} Resistance: {res}")

    print("\n  MOVING AVERAGE ALIGNMENT:")
    for r in results:
        print(f"  {r['ticker']:<12} {r['last_close']:>12,.2f} vs MA20={r['ma20']:,.2f}  MA50={r['ma50']:,.2f}"
              + (f"  MA200={r['ma200']:,.2f}" if r['ma200'] else ""))

    print("\n" + "=" * len(header))


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("  MEMORY/SEMICONDUCTOR TECHNICAL ANALYSIS")
    print("  MU · 005930.KS (Samsung) · 000660.KS (SK Hynix)")
    print(f"  Data period: {PERIOD}")
    print("=" * 70)

    results = []
    for ticker in TICKERS:
        print(f"\n[{ticker}] Fetching 6 months of daily data ...")
        try:
            df = download_single(ticker)
            print(f"  Got {len(df)} rows from {df.index[0].date()} to {df.index[-1].date()}")
            analysis = analyze_ticker(ticker, df)
            results.append(analysis)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if not results:
        print("No data to analyze. Exiting.")
        sys.exit(1)

    # Print console summary
    print_summary_table(results)

    # Generate and save markdown report
    report = generate_report(results)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n  Markdown report saved to: {REPORT_PATH}")
    print("=" * 70)

    # ── AI interpretation (inline) ──────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("  KEY FINDINGS (for AI to incorporate)")
    print("=" * 70)
    for r in results:
        print(f"\n  [{r['ticker']}] {r['name']}")
        print(f"    Close: {r['last_close']:,.2f}  |  Date: {r['last_date']}")
        print(f"    MA20:  {r['ma20']:,.2f}  ({r['vs_ma20_pct']:+.1f}%)")
        print(f"    MA50:  {r['ma50']:,.2f}  ({r['vs_ma50_pct']:+.1f}%)")
        if r['ma200']:
            print(f"    MA200: {r['ma200']:,.2f}  ({r['vs_ma200_pct']:+.1f}%)")
        print(f"    RSI-14: {r['rsi14']}  |  MACD: {r['macd_cross']} (hist={r['macd_hist']:+.4f})")
        print(f"    BB %B: {r['bb_position_pct']:.1f}%  |  Upper={r['bb_upper']:,.2f}  Lower={r['bb_lower']:,.2f}")
        print(f"    Support: {r['support_levels']}")
        print(f"    Resistance: {r['resistance_levels']}")
        print(f"    1W: {r['pct_1w']:+.1f}%  |  1M: {r['pct_1m']:+.1f}%  |  3M: {r['pct_3m']:+.1f}%")
        print(f"    ATH: {r['ath']:,.2f}  |  3M Range: {r['low_3m']:,.2f} - {r['high_3m']:,.2f}")
        print(f"    Distribution days: {r['distribution_days']}  |  Accumulation: {r['accumulation_days']}")


if __name__ == "__main__":
    main()
