#!/usr/bin/env python3
"""sentiment_hourly_push.py — 交易时段每小时舆情推送到微信/outbox.

覆盖: DXYZ, INTC, MU (董事长核心持仓)
频率: 美股交易时段每小时 (ET 9:30-16:00 → 北京 21:30-04:00)
输出: company/chairman_outbox/SENTINEL_*.md → WeChat + SSE 推送

Usage:
    python scripts/sentiment_hourly_push.py              # full report
    python scripts/sentiment_hourly_push.py --quick      # price only, no news
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
WATCH_TICKERS = ["DXYZ", "INTC", "MU", "WDC"]


def _fetch_one(ticker: str) -> dict:
    """Single fetch attempt — factored out for retry."""
    t = yf.Ticker(ticker)
    hist = t.history("5d")
    if hist.empty:
        raise RuntimeError("empty history")
    close = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
    change_pct = float((close - prev_close) / prev_close * 100)
    vol = int(hist["Volume"].iloc[-1])
    avg_vol = float(hist["Volume"].mean())
    vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
    high = float(hist["High"].iloc[-1])
    low = float(hist["Low"].iloc[-1])
    range_pct = float((high - low) / low * 100)
    ma5 = float(hist["Close"].rolling(5).mean().iloc[-1]) if len(hist) >= 5 else close
    news_headlines = []
    try:
        for n in t.news[:3]:
            news_headlines.append(n.get("content", n).get("title", "")[:120])
    except Exception:
        pass
    return {
        "ticker": ticker,
        "close": round(close, 2),
        "change_pct": round(change_pct, 2),
        "vol_ratio": round(vol_ratio, 1),
        "range_pct": round(range_pct, 1),
        "above_ma5": close > ma5,
        "ma5": round(ma5, 2),
        "news": news_headlines[:3],
        "alert": abs(change_pct) > 5 or vol_ratio > 2.5,
    }


def fetch_snapshot(ticker: str, retries: int = 3) -> dict:
    """Fetch with retry — yfinance intermittently returns empty history."""
    last_err = ""
    for attempt in range(retries):
        try:
            return _fetch_one(ticker)
        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
    return {"ticker": ticker, "error": last_err}


def generate_report(snapshots: list) -> str:
    now = datetime.now()
    lines = [
        f"# 📡 每小时舆情快报",
        f"> {now.strftime('%Y-%m-%d %H:%M')} 北京时间",
        "",
        "| 股票 | 价格 | 涨跌 | 量比 | 振幅 | MA5 | 提醒 |",
        "|------|------|------|------|------|-----|------|",
    ]
    alerts = []
    for s in snapshots:
        if "error" in s:
            lines.append(f"| {s['ticker']} | — | — | — | — | — | ❌ {s['error']} |")
            continue
        alert_tag = "🔴" if s.get("alert") else ""
        ma_tag = "✅" if s.get("above_ma5") else "⬇️"
        lines.append(
            f"| **{s['ticker']}** | ${s['close']:.2f} | {s['change_pct']:+.1f}% | "
            f"{s['vol_ratio']:.1f}x | {s['range_pct']:.1f}% | {ma_tag} ${s['ma5']:.2f} | {alert_tag} |"
        )
        if s.get("alert"):
            alerts.append(f"🔴 {s['ticker']}: {s['change_pct']:+.1f}%, 量比 {s['vol_ratio']:.1f}x")

    lines.append("")
    lines.append("## 关键新闻标题")
    for s in snapshots:
        if s.get("news"):
            lines.append(f"\n**{s['ticker']}**:")
            for n in s["news"]:
                lines.append(f"- {n}")

    if alerts:
        lines.insert(5, f"\n## ⚠️ 异常提醒\n")
        for a in alerts:
            lines.insert(6, f"- {a}")
        lines.insert(7, "")

    lines.append(f"\n---\n*自动生成 · 下一份整点后推送*")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    print(f"Sentiment push — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    snapshots = [fetch_snapshot(t) for t in WATCH_TICKERS]
    report = generate_report(snapshots)

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = OUTBOX_DIR / f"SENTINEL_hourly_{ts}.md"
    path.write_text(report, encoding="utf-8")
    print(f"  Report → {path}")
    print(f"  Tickers: {len([s for s in snapshots if 'error' not in s])}/{len(snapshots)}")

    # Alert summary
    alerts = [s for s in snapshots if s.get("alert")]
    if alerts:
        alert_names = ", ".join(f"{s['ticker']}({s['change_pct']:+.1f}%)" for s in alerts)
        print(f"  ⚠️ ALERTS: {alert_names}")


if __name__ == "__main__":
    main()
