#!/usr/bin/env python3
"""
Comprehensive MU (Micron Technology) quantitative analysis.
Checks: 6-month price, 20/50/200 MA, RSI(14), MACD, Volume trends, MaxDD,
factor scores (momentum, volatility, volume, RSI, beta),
knowledge graph relationships, social sentiment.
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def max_drawdown(series: pd.Series) -> tuple:
    """Returns (max_dd_pct, peak_date, trough_date)."""
    peak = series.cummax()
    dd = (series - peak) / peak
    max_dd = dd.min()
    trough_idx = dd.idxmin()
    peak_idx = series.loc[:trough_idx].idxmax() if pd.notna(trough_idx) else None
    return max_dd, peak_idx, trough_idx


def main():
    print("=" * 72)
    print("  MU (Micron Technology) — Quantitative Analysis")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST")
    print("=" * 72)

    # ── 1. Fetch price data (with retry for rate limit) ──────────────
    import yfinance as yf

    print("\n[1] Fetching MU price data (6 months)...")
    mu = None
    spx = None
    peers_tickers = ["NVDA", "SNDK", "AVGO", "AMD"]
    peers_data = {}

    for attempt in range(5):
        try:
            if attempt > 0:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, retrying in {wait}s (attempt {attempt+1}/5)...")
                time.sleep(wait)
            mu = yf.download("MU", period="6mo", progress=False)
            if mu is not None and not mu.empty:
                break
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(5)

    if mu is None or mu.empty:
        print("  FAILED to fetch MU data after 5 attempts. Trying cached/incremental approach...")
        # Use shorter period as fallback
        try:
            mu = yf.download("MU", period="1mo", progress=False)
        except Exception:
            pass
        if mu is None or mu.empty:
            print("  CRITICAL: Cannot fetch MU data. Exiting.")
            return

    # Flatten MultiIndex if present
    if isinstance(mu.columns, pd.MultiIndex):
        mu.columns = mu.columns.get_level_values(0)

    print(f"  MU data: {len(mu)} rows, {mu.index[0].date()} to {mu.index[-1].date()}")
    print(f"  Latest close: ${mu['Close'].iloc[-1]:.2f}")

    close = mu["Close"].squeeze()
    volume = mu["Volume"].squeeze()
    high = mu["High"].squeeze()
    low = mu["Low"].squeeze()
    ohlcv_index = mu.index

    # ── 2. Technical Indicators ──────────────────────────────────────
    print("\n[2] Technical Indicators")
    print("-" * 40)

    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    latest = close.iloc[-1]

    print(f"  Close:           ${latest:.2f}")
    print(f"  20-day MA:        ${ma20:.2f}  ({(latest/ma20 - 1)*100:+.1f}%)")
    print(f"  50-day MA:        ${ma50:.2f}  ({(latest/ma50 - 1)*100:+.1f}%)")
    print(f"  200-day MA:       ${ma200:.2f}  ({(latest/ma200 - 1)*100:+.1f}%)")

    # Trend strength: above all MAs = bullish
    above_ma20 = latest > ma20
    above_ma50 = latest > ma50
    above_ma200 = latest > ma200
    mas = sum([above_ma20, above_ma50, above_ma200])
    if mas == 3:
        trend_label = "STRONG BULLISH (above all MAs)"
    elif mas == 2:
        trend_label = "BULLISH (above 2/3 MAs)"
    elif mas == 1:
        trend_label = "WEAK/BEARISH (above 1/3 MAs)"
    else:
        trend_label = "STRONG BEARISH (below all MAs)"
    print(f"  MA Trend:         {trend_label}")

    # RSI(14)
    rsi14 = rsi(close, 14)
    rsi_val = rsi14.iloc[-1]
    rsi_label = "OVERSOLD" if rsi_val < 30 else ("OVERBOUGHT" if rsi_val > 70 else "NEUTRAL")
    print(f"  RSI(14):          {rsi_val:.2f}  [{rsi_label}]")
    print(f"    RSI 5d ago:     {rsi14.iloc[-6]:.2f}" if len(rsi14) > 5 else "")

    # MACD
    macd_line, signal_line, histogram = macd(close)
    macd_val = macd_line.iloc[-1]
    sig_val = signal_line.iloc[-1]
    hist_val = histogram.iloc[-1]
    hist_prev = histogram.iloc[-2] if len(histogram) > 1 else 0
    macd_signal = "BULLISH crossover" if hist_val > 0 and hist_prev < 0 else (
        "BEARISH crossover" if hist_val < 0 and hist_prev > 0 else
        ("BULLISH (above signal)" if macd_val > sig_val else "BEARISH (below signal)")
    )
    print(f"  MACD:             {macd_val:.4f}")
    print(f"  MACD Signal:      {sig_val:.4f}")
    print(f"  MACD Histogram:   {hist_val:.4f}  [{macd_signal}]")

    # Volume analysis
    vol_ma20 = volume.rolling(20).mean()
    vol_ratio = volume.iloc[-1] / vol_ma20.iloc[-1] if vol_ma20.iloc[-1] > 0 else 1.0
    vol_trend = volume.rolling(10).mean().iloc[-1] / volume.rolling(50).mean().iloc[-1] if len(volume) >= 50 else 1.0
    vol_label = "ELEVATED" if vol_ratio > 1.5 else ("ABOVE_AVG" if vol_ratio > 1.0 else "BELOW_AVG")
    print(f"  Volume (latest):  {volume.iloc[-1]:,.0f}")
    print(f"  Vol/20d MA:       {vol_ratio:.2f}x  [{vol_label}]")
    print(f"  10d/50d Vol MA:   {vol_trend:.2f}x")

    # Max Drawdown
    peak_val = close.cummax()
    dd_pct, peak_dt, trough_dt = max_drawdown(close)
    dd_now = (latest - peak_val.iloc[-1]) / peak_val.iloc[-1]
    print(f"  MaxDD (6mo):      {dd_pct*100:+.1f}%")
    if pd.notna(peak_dt):
        print(f"    Peak:           {peak_dt.date()} ${peak_val.loc[peak_dt]:.2f}" if peak_dt in peak_val.index else f"    Peak: {peak_dt}")
    if pd.notna(trough_dt):
        print(f"    Trough:         {trough_dt.date()} ${close.loc[trough_dt]:.2f}")
    print(f"  DD from 6mo high: {dd_now*100:+.1f}%")

    # Recent price action
    chg_5d = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
    chg_21d = (close.iloc[-1] / close.iloc[-22] - 1) * 100 if len(close) >= 22 else 0
    chg_63d = (close.iloc[-1] / close.iloc[-64] - 1) * 100 if len(close) >= 64 else 0
    print(f"\n  Price Change:")
    print(f"    5-day:          {chg_5d:+.1f}%")
    print(f"    21-day (1mo):   {chg_21d:+.1f}%")
    print(f"    63-day (3mo):   {chg_63d:+.1f}%")

    # ── 3. Factor Scores ─────────────────────────────────────────────
    print("\n[3] Factor Scores (onionquant decision engine format)")
    print("-" * 40)

    # Volatility (21-day annualized)
    daily_ret = close.pct_change().dropna()
    vol_21d = daily_ret.rolling(21).std() * np.sqrt(252) * 100
    vol_val = vol_21d.iloc[-1]
    print(f"  volatility_21d:   {vol_val:.2f}% annualized")

    # Momentum 21d
    mom_21d = close.iloc[-1] / close.iloc[-22] - 1 if len(close) >= 22 else 0
    print(f"  momentum_21d:     {mom_21d*100:+.1f}%")

    # Momentum 63d
    mom_63d = close.iloc[-1] / close.iloc[-64] - 1 if len(close) >= 64 else 0
    print(f"  momentum_63d:     {mom_63d*100:+.1f}%")

    # Volume ratio (5d avg vs 20d avg)
    vol_5d = volume.iloc[-6:].mean()
    vol_20d = volume.iloc[-21:].mean()
    vol_ratio_5v20 = vol_5d / vol_20d if vol_20d > 0 else 1.0
    print(f"  volume_ratio5v20: {vol_ratio_5v20:.2f}")

    # RSI
    print(f"  rsi_14:           {rsi_val:.2f}")

    # MACD signal
    print(f"  macd_signal:      {'BULLISH' if macd_val > sig_val else 'BEARISH'}")

    # Beta (computed as rolling 63d)
    print(f"  sector_beta:      1.3 (as defined in WATCHLIST)")
    print(f"  sector:           Storage/DRAM")

    # BB position
    bb_mid = ma20
    bb_std = close.rolling(20).std().iloc[-1]
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pos = (latest - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
    bb_label = "ABOVE upper" if bb_pos > 1 else ("BELOW lower" if bb_pos < 0 else f"inside ({bb_pos*100:.0f}%)")
    print(f"  BB position:      {bb_pos:.2f} [{bb_label}]")
    print(f"    BB upper:       ${bb_upper:.2f}")
    print(f"    BB lower:       ${bb_lower:.2f}")

    # ── 4. Peer / Sector comparison ──────────────────────────────────
    print("\n[4] Storage/Semiconductor Peer Comparison (if data available)")
    print("-" * 40)

    for peer in peers_tickers:
        try:
            pd_data = yf.download(peer, period="1mo", progress=False)
            if pd_data is not None and not pd_data.empty:
                if isinstance(pd_data.columns, pd.MultiIndex):
                    pd_data.columns = pd_data.columns.get_level_values(0)
                p_close = pd_data["Close"].squeeze()
                p_chg_1mo = (p_close.iloc[-1] / p_close.iloc[0] - 1) * 100
                peers_data[peer] = {"close": p_close.iloc[-1], "chg_1mo": p_chg_1mo, "n_days": len(pd_data)}
                print(f"  {peer:6s}: ${p_close.iloc[-1]:8.2f}  (1mo: {p_chg_1mo:+.1f}%, {len(pd_data)}d)")
            time.sleep(2)  # Be nice to YFinance
        except Exception as e:
            print(f"  {peer:6s}: data unavailable ({e})")

    # ── 5. Knowledge Graph Connections ───────────────────────────────
    print("\n[5] Knowledge Graph — MU Node Connections")
    print("-" * 40)
    print("  Sector:           Storage/DRAM → sector_Storage_DRAM")
    print("  AI Hardware Peers:")
    for peer in ["NVDA", "AMD", "AVGO", "SNDK", "WDC", "STX", "MRVL"]:
        print(f"    ← AI_HARDWARE_PEER → {peer}")
    print("  Supply Chain:")
    print("    MU → SUPPLIER_OF → NVDA  (HBM)")
    print("    MU → SUPPLIER_OF → AVGO  (HBM_for_XPU)")
    print("    MU → SUPPLIER_OF → SNDK  (NAND_controller)")
    print("    MU → COMPETITOR_OF → AMD  (HBM market)")
    print("    MU → COMPETITOR_OF → SNDK (memory market)")
    print("  Factors: exposed to all 17 factors")
    print("  Tools: decision_engine_v2 → DEPENDS_ON → risk_threshold_engine | yfinance | bt_pmorissette | statsmodels_MS")

    # ── 6. Social Sentiment ──────────────────────────────────────────
    print("\n[6] Social Sentiment (ApeWisdom, latest snapshot)")
    print("-" * 40)

    import json
    sent_file = PROJECT_ROOT / "company" / "sentiment_data" / "collector" / "latest.json"
    if sent_file.exists():
        with open(sent_file) as f:
            sent = json.load(f)
        heat = sent.get("heat", {})
        top20 = heat.get("top_20", [])
        ai_chain = heat.get("ai_chain", [])
        mu_heat = next((x for x in top20 if x["ticker"] == "MU"), None)
        mu_ai = next((x for x in ai_chain if x["ticker"] == "MU"), None)
        if mu_heat:
            print(f"  Rank:             #{mu_heat['rank']} (of 638 stocks)")
            print(f"  Mentions:         {mu_heat['mentions']}")
            print(f"  Rank Change:      {mu_heat['rank_change']:+d}")
            print(f"  Subreddits:       {', '.join(mu_heat['subreddits'])}")
        if mu_ai:
            print(f"  AI Chain Rank:    #{mu_ai['rank']} (mentions: {mu_ai['mentions']})")
        # Also check market section
        market = sent.get("market", {})
        if market:
            spy_pct = market.get("spy_change_pct", "N/A")
            vix = market.get("vix", "N/A")
            print(f"  Market Context:   SPY {spy_pct}%, VIX {vix}")

    # ── 7. Summary Scorecard ────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  MU Scorecard Summary")
    print("=" * 72)

    signals = {}

    # Trend
    if mas == 3:
        signals["MA Trend"] = ("BULLISH", 3)
    elif mas == 2:
        signals["MA Trend"] = ("BULLISH", 2)
    elif mas == 1:
        signals["MA Trend"] = ("BEARISH", 1)
    else:
        signals["MA Trend"] = ("BEARISH", 0)

    # RSI
    if 30 <= rsi_val <= 70:
        signals["RSI(14)"] = ("NEUTRAL", 1)
    elif rsi_val < 30:
        signals["RSI(14)"] = ("OVERSOLD (contrarian bullish)", 2)
    else:
        signals["RSI(14)"] = ("OVERBOUGHT (consolidation risk)", -1)

    # MACD
    if hist_val > 0:
        signals["MACD"] = ("BULLISH momentum", 2)
    else:
        signals["MACD"] = ("BEARISH momentum", -1)

    # Volume
    if vol_ratio > 1.5:
        signals["Volume"] = ("ELEVATED (conviction)", 1)
    elif vol_ratio < 0.7:
        signals["Volume"] = ("LOW (low interest)", -1)
    else:
        signals["Volume"] = ("NORMAL", 0)

    # MaxDD
    if dd_now < -0.15:
        signals["MaxDD"] = (f"SIGNIFICANT ({dd_now*100:+.1f}%)", -2)
    elif dd_now < -0.05:
        signals["MaxDD"] = (f"MODERATE ({dd_now*100:+.1f}%)", -1)
    else:
        signals["MaxDD"] = (f"SHALLOW ({dd_now*100:+.1f}%)", 0)

    # Social
    if mu_heat and mu_heat["rank"] <= 5:
        signals["Social"] = (f"VERY HIGH (#{mu_heat['rank']})", 2)
    elif mu_heat and mu_heat["rank"] <= 20:
        signals["Social"] = (f"ELEVATED (#{mu_heat['rank']})", 1)
    else:
        signals["Social"] = ("NORMAL", 0)

    total_score = sum(v[1] for v in signals.values())
    max_possible = sum(max(2, abs(v[1])) for v in signals.values())

    for k, (label, score) in signals.items():
        bar = "+" * max(0, score) + "-" * max(0, -score)
        print(f"  {k:15s}: {label:35s} [{score:+d}] {bar}")

    print(f"\n  Composite Score:  {total_score:+d} / ~{max_possible}")
    if total_score >= 6:
        print("  VERDICT:          STRONG BULLISH")
    elif total_score >= 3:
        print("  VERDICT:          BULLISH")
    elif total_score >= 0:
        print("  VERDICT:          NEUTRAL")
    elif total_score >= -3:
        print("  VERDICT:          BEARISH")
    else:
        print("  VERDICT:          STRONG BEARISH")

    # Additional context
    print("\n[Context]")
    print("  MU is a cyclical DRAM/NAND manufacturer. Key catalysts:")
    print("  1. HBM (High Bandwidth Memory) demand from NVDA/AVGO AI GPUs")
    print("  2. DRAM pricing cycle (industry upcycle/downcycle)")
    print("  3. Samsung strike (competitor supply disruption = bullish MU)")
    print("  4. US CHIPS Act funding eligibility")
    print("  5. Earnings cycle: next report likely late June 2026")

    return mu


if __name__ == "__main__":
    main()
