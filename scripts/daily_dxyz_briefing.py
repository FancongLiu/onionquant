#!/usr/bin/env python3
"""daily_dxyz_briefing.py — Auto-generate DXYZ daily brief.

Fetches latest data, computes risk metrics, checks for news catalysts,
and writes a markdown report to company/reports/.

Usage:
    python scripts/daily_dxyz_briefing.py           # full report
    python scripts/daily_dxyz_briefing.py --quick   # price + vol only
    python scripts/daily_dxyz_briefing.py --alert   # alert if big moves

Cron: 0 18 * * 1-5  (weekdays after market close)
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "company" / "reports"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
SYMBOL = "DXYZ"


def fetch_data(symbol: str = SYMBOL) -> dict:
    """Fetch DXYZ price, fundamentals, and news."""
    ticker = yf.Ticker(symbol)

    # Price history
    hist = ticker.history("1mo")
    if hist.empty:
        return {"error": "No data from yfinance"}

    today = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else today

    change = float(today["Close"] - prev["Close"])
    change_pct = float(change / prev["Close"] * 100)
    vol_ratio = float(today["Volume"] / hist["Volume"].mean()) if len(hist) > 5 else 1.0

    # 1Y for metrics
    hist_1y = ticker.history("1y")["Close"]
    rets = hist_1y.pct_change().dropna()
    sharpe_1y = float(rets.mean() / rets.std() * (252 ** 0.5)) if len(rets) > 20 else 0
    vol_1y = float(rets.std() * (252 ** 0.5) * 100)
    maxdd_1y = float((hist_1y / hist_1y.cummax() - 1).min() * 100)

    # Current vs moving averages
    ma5 = float(hist["Close"].rolling(5).mean().iloc[-1])
    ma20 = float(hist["Close"].rolling(20).mean().iloc[-1]) if len(hist) >= 20 else ma5
    ma50 = float(hist_1y.rolling(50).mean().iloc[-1]) if len(hist_1y) >= 50 else ma20
    ma200 = float(hist_1y.rolling(200).mean().iloc[-1]) if len(hist_1y) >= 200 else ma50

    close = float(today["Close"])
    trend = "BULL" if (close > ma5 > ma20) else ("BEAR" if (close < ma5 < ma20) else "NEUTRAL")

    # RSI(14)
    delta = hist_1y.diff()
    gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
    loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
    rsi = float(100 - 100 / (1 + gain / loss)) if loss != 0 else 50

    # 5-day range
    high_5d = float(hist["High"].tail(5).max())
    low_5d = float(hist["Low"].tail(5).min())
    range_pct = float((high_5d - low_5d) / low_5d * 100)

    # News
    try:
        news = ticker.news[:5] if hasattr(ticker, "news") else []
    except Exception:
        news = []

    return {
        "symbol": symbol,
        "date": str(today.name.date()) if hasattr(today.name, "date") else str(datetime.now().date()),
        "close": close,
        "change": change,
        "change_pct": change_pct,
        "volume": int(today["Volume"]),
        "vol_ratio": vol_ratio,
        "high_5d": high_5d,
        "low_5d": low_5d,
        "range_5d_pct": range_pct,
        "trend": trend,
        "ma5": ma5,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "rsi_14": round(rsi, 1),
        "sharpe_1y": round(sharpe_1y, 2),
        "vol_1y": round(vol_1y, 1),
        "maxdd_1y": round(maxdd_1y, 1),
        "news": news,
        "alert": abs(change_pct) > 5 or vol_ratio > 2.0,
    }


def generate_report(data: dict, quick: bool = False) -> str:
    if "error" in data:
        return f"# DXYZ Daily Briefing ERROR\n**{data['error']}**"

    lines = [
        f"# DXYZ 每日快报",
        f"> {data['date']} | 收盘价 ${data['close']:.2f} | {data['change']:+.2f} ({data['change_pct']:+.1f}%)",
        "",
        "## 核心指标",
        "",
        "| 指标 | 值 | 信号 |",
        "|------|-----|------|",
        f"| 收盘价 | ${data['close']:.2f} | — |",
        f"| 日涨跌 | {data['change']:+.2f} ({data['change_pct']:+.1f}%) | {'🔴' if data['change_pct'] < -3 else '🟢' if data['change_pct'] > 3 else '🟡'} |",
        f"| 成交量 | {data['volume']:,} | {'🔴 放量' if data['vol_ratio'] > 2 else '🟡 放量' if data['vol_ratio'] > 1.5 else '🟢 正常'} ({data['vol_ratio']:.1f}x 均值) |",
        f"| 5日振幅 | {data['range_5d_pct']:.1f}% | — |",
        f"| 趋势 | {data['trend']} | — |",
        f"| RSI(14) | {data['rsi_14']:.0f} | {'🔴 超买' if data['rsi_14'] > 70 else '🟡 超卖' if data['rsi_14'] < 30 else '🟢 正常'} |",
        f"| MA5 | ${data['ma5']:.2f} | {'🟢 >价格' if data['ma5'] < data['close'] else '🔴 <价格'} |",
        f"| MA20 | ${data['ma20']:.2f} | {'🟢 >价格' if data['ma20'] < data['close'] else '🔴 <价格'} |",
        f"| MA50 | ${data['ma50']:.2f} | {'🟢 >价格' if data['ma50'] < data['close'] else '🔴 <价格'} |",
        f"| MA200 | ${data['ma200']:.2f} | {'🟢 >价格' if data['ma200'] < data['close'] else '🔴 <价格'} |",
        f"| 1Y Sharpe | {data['sharpe_1y']:.2f} | — |",
        f"| 1Y 波动率 | {data['vol_1y']:.1f}% | — |",
        f"| 1Y 最大回撤 | {data['maxdd_1y']:.1f}% | — |",
    ]

    if data.get("alert"):
        lines.append("")
        lines.append("## ⚠️ 提醒")
        if abs(data["change_pct"]) > 5:
            direction = "大涨" if data["change_pct"] > 0 else "大跌"
            lines.append(f"- 今日{direction} {data['change_pct']:+.1f}%，请关注原因")
        if data["vol_ratio"] > 2:
            lines.append(f"- 成交量是正常的 {data['vol_ratio']:.1f} 倍，可能有重大事件")

    if data.get("news") and not quick:
        lines.append("")
        lines.append("## 相关新闻")
        for n in data["news"][:5]:
            title = n.get("content", {}).get("title", n.get("title", "—"))
            lines.append(f"- {title}")

    lines.append("")
    lines.append(f"*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} | daily_dxyz_briefing.py*")
    return "\n".join(lines)


def write_alert(data: dict):
    """Write alert to outbox if big move detected."""
    if not data.get("alert"):
        return
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTBOX_DIR / f"ALERT_DXYZ_{ts}.md"
    path.write_text(
        f"# DXYZ 价格预警\n"
        f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**价格**: ${data['close']:.2f}\n"
        f"**涨跌**: {data['change_pct']:+.1f}%\n"
        f"**成交量**: {data['vol_ratio']:.1f}x 均值\n"
        f"\n请关注相关新闻和 SpaceX/Anthropic 催化剂。",
        encoding="utf-8",
    )
    print(f"  [ALERT] Outbox alert written to {path.name}")


def main():
    parser = argparse.ArgumentParser(description="DXYZ Daily Briefing Generator")
    parser.add_argument("--quick", action="store_true", help="Price + volume only")
    parser.add_argument("--alert", action="store_true", help="Alert mode: write to outbox if big move")
    args = parser.parse_args()

    print(f"DXYZ Daily Briefing — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    data = fetch_data()
    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)

    report = generate_report(data, quick=args.quick)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"daily_DXYZ_{datetime.now().strftime('%Y%m%d')}.md"
    path.write_text(report, encoding="utf-8")
    print(f"  Report: {path}")

    if args.alert and data.get("alert"):
        write_alert(data)

    print(report[:500])
    if len(report) > 500:
        print("  ... (truncated)")

    return data


if __name__ == "__main__":
    main()
