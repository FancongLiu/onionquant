#!/usr/bin/env python3
"""
realtime_data.py — 多源实时行情引擎

解决问题: 免费API假期后延时5/22数据, 芬恩线/Yahoo v8/Futures三源交叉验证.
市场状态自动检测, 预盘/盘后/休市清晰标记.

源:
  - Finnhub free tier: 实时美股报价, 60 calls/min
  - Yahoo Finance v8: preMarketPrice/postMarketPrice + futures
  - Alpha Vantage: GLOBAL_QUOTE (备用)

Usage:
  python onionquant/tools/realtime_data.py --tickers MU,INTC,MRVL
  python onionquant/tools/realtime_data.py --market-status
  python onionquant/tools/realtime_data.py --futures
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FINNHUB_KEY = "d8a88lpr01qn9847a3m0d8a88lpr01qn9847a3mg"
ALPHA_VANTAGE_KEY = "RIBXT3CS1A7NZMIG"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ET时区大致偏移 (不考虑夏令时切换, 对市场时间足够)
ET_OFFSET = timedelta(hours=-4)  # EDT = UTC-4
# 关键市场时间 (ET)
PREMARKET_START = 4  # 4:00 AM ET
REGULAR_START = 9  # 9:30 AM ET
REGULAR_END = 16  # 4:00 PM ET
AFTERHOURS_END = 20  # 8:00 PM ET


def _et_now() -> datetime:
    """当前ET时间."""
    return datetime.now(timezone.utc) + ET_OFFSET


def detect_market_session() -> dict:
    """检测当前市场状态 (美股).

    Returns dict with:
      - is_open: bool — regular session?
      - session: 'premarket' | 'regular' | 'afterhours' | 'closed'
      - holiday: str | None — holiday name if closed for holiday
      - next_session: str — next session description
    """
    et = _et_now()
    hour = et.hour + et.minute / 60.0
    weekday = et.weekday()  # 0=Mon, 6=Sun

    result = {
        "et_time": et.strftime("%Y-%m-%d %H:%M ET"),
        "utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "weekday": et.strftime("%A"),
        "is_open": False,
        "session": "closed",
        "holiday": None,
        "next_session": "",
    }

    # 先检查Finnhub市场日历
    try:
        r = requests.get(
            f"https://api.finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}",
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("holiday"):
                result["holiday"] = data["holiday"]
            result["is_open"] = data.get("isOpen", False)
            result["session"] = data.get("session") or "closed"
            if result["holiday"]:
                result["next_session"] = f"Next session after {result['holiday']}"
            elif (
                result["session"] == "closed" and weekday < 5 and hour < PREMARKET_START
            ):
                result["session"] = "closed"
                et_pre = et.replace(hour=PREMARKET_START, minute=0, second=0)
                result["next_session"] = (
                    f"Pre-market starts {et_pre.strftime('%H:%M ET')}"
                )
            return result
    except Exception:
        pass

    # 回退: 本地计算
    if weekday >= 5:
        result["session"] = "closed"
        result["next_session"] = "Monday pre-market 4:00 AM ET"
    elif hour < PREMARKET_START:
        result["session"] = "closed"
        et_pre = et.replace(hour=PREMARKET_START, minute=0, second=0)
        result["next_session"] = f"Pre-market starts {et_pre.strftime('%H:%M ET')}"
    elif hour < REGULAR_START:
        result["session"] = "premarket"
        result["next_session"] = "Market opens 9:30 AM ET"
    elif hour < REGULAR_END:
        result["session"] = "regular"
        result["is_open"] = True
        result["next_session"] = "Market closes 4:00 PM ET"
    elif hour < AFTERHOURS_END:
        result["session"] = "afterhours"
        result["next_session"] = "Next session tomorrow pre-market 4:00 AM ET"
    else:
        result["session"] = "closed"
        result["next_session"] = "Tomorrow pre-market 4:00 AM ET"

    return result


def fetch_futures() -> dict:
    """获取美股指数期货 (盘前方向标)."""
    futures_syms = {
        "ES=F": "S&P 500",
        "NQ=F": "Nasdaq 100",
        "YM=F": "Dow Jones",
        "RTY=F": "Russell 2000",
        "VIX=F": "VIX",
    }
    results = {}
    for sym, name in futures_syms.items():
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?"
                f"interval=1m&range=1d&includePrePost=true",
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            if r.status_code != 200:
                results[sym] = {"name": name, "error": f"HTTP {r.status_code}"}
                continue
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("previousClose")
            change = (price - prev) if (price and prev) else None
            pct = (change / prev * 100) if (change is not None and prev) else None
            results[sym] = {
                "name": name,
                "price": price,
                "prev_close": prev,
                "change": round(change, 2) if change else None,
                "change_pct": round(pct, 2) if pct else None,
                "time": meta.get("regularMarketTime"),
            }
        except Exception as e:
            results[sym] = {"name": name, "error": str(e)[:100]}
    return results


def finnhub_quote(ticker: str) -> dict | None:
    """Finnhub实时报价 (free tier, real-time during market hours)."""
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_KEY}",
            timeout=10,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        data = r.json()
        if data.get("c") is None:
            return {"error": "no data"}
        ts = data.get("t", 0)
        ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        return {
            "price": data["c"],
            "prev_close": data.get("pc"),
            "open": data.get("o"),
            "high": data.get("h"),
            "low": data.get("l"),
            "change": data.get("d"),
            "change_pct": data.get("dp"),
            "timestamp": ts,
            "timestamp_display": ts_dt.strftime("%Y-%m-%d %H:%M UTC")
            if ts_dt
            else None,
            "source": "Finnhub",
            "data_freshness": _classify_freshness(ts_dt) if ts_dt else "unknown",
        }
    except Exception as e:
        return {"error": str(e)[:100]}


def yahoo_prepost(ticker: str) -> dict | None:
    """Yahoo Finance v8 — 预盘/盘后价格."""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?"
            f"interval=1m&range=1d&includePrePost=true",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        meta = r.json()["chart"]["result"][0]["meta"]
        regular = meta.get("regularMarketPrice")
        pre_market = meta.get("preMarketPrice")
        post_market = meta.get("postMarketPrice")
        # 取最新的可用价格
        current = pre_market or post_market or regular
        prev = meta.get("previousClose")
        change = (current - prev) if (current and prev) else None
        pct = (change / prev * 100) if (change is not None and prev) else None
        ts = meta.get("regularMarketTime")
        ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        return {
            "price": current,
            "prev_close": prev,
            "pre_market": pre_market,
            "post_market": post_market,
            "regular_market": regular,
            "change": round(change, 2) if change else None,
            "change_pct": round(pct, 2) if pct else None,
            "timestamp": ts,
            "timestamp_display": ts_dt.strftime("%Y-%m-%d %H:%M UTC")
            if ts_dt
            else None,
            "source": "Yahoo Finance v8",
            "data_freshness": _classify_freshness(ts_dt) if ts_dt else "unknown",
        }
    except Exception as e:
        return {"error": str(e)[:100]}


def alpha_vantage_quote(ticker: str) -> dict | None:
    """Alpha Vantage GLOBAL_QUOTE (备用)."""
    try:
        r = requests.get(
            f"https://www.alphavantage.co/query?"
            f"function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}",
            timeout=10,
        )
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        data = r.json()
        gq = data.get("Global Quote", {})
        if not gq:
            return {"error": "no data (rate limit?)"}
        price = float(gq.get("05. price", 0)) if gq.get("05. price") else None
        prev = (
            float(gq.get("08. previous close", 0))
            if gq.get("08. previous close")
            else None
        )
        change = float(gq.get("09. change", 0)) if gq.get("09. change") else None
        pct_str = gq.get("10. change percent", "0%").replace("%", "")
        pct = float(pct_str) if pct_str else None
        return {
            "price": price,
            "prev_close": prev,
            "change": change,
            "change_pct": pct,
            "latest_day": gq.get("07. latest trading day"),
            "source": "Alpha Vantage",
            "data_freshness": "EOD" if gq.get("07. latest trading day") else "unknown",
        }
    except Exception as e:
        return {"error": str(e)[:100]}


def _classify_freshness(ts_dt: datetime) -> str:
    """分类数据新鲜度."""
    now = datetime.now(timezone.utc)
    age = now - ts_dt
    if age < timedelta(minutes=5):
        return "LIVE (<5min)"
    elif age < timedelta(hours=1):
        return "RECENT (<1h)"
    elif age < timedelta(hours=24):
        return f"STALE ({age.total_seconds() / 3600:.0f}h old)"
    else:
        return f"EOD ({ts_dt.strftime('%Y-%m-%d')})"


def get_realtime_quote(ticker: str) -> dict:
    """获取单只股票的最佳实时报价 (多源交叉验证).

    优先级: Finnhub (real-time) > Yahoo v8 (pre/post) > Alpha Vantage (EOD)
    """
    result = {
        "ticker": ticker.upper(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "market": detect_market_session(),
        "quotes": {},
    }

    # 1. Finnhub (首选 — 免费实时)
    fh = finnhub_quote(ticker)
    if fh and "error" not in fh:
        result["quotes"]["finnhub"] = fh
        result["best"] = fh

    # 2. Yahoo v8 (预盘/盘后)
    yh = yahoo_prepost(ticker)
    if yh and "error" not in yh:
        result["quotes"]["yahoo_v8"] = yh
        # Yahoo有pre/post价格时优先
        if yh.get("pre_market") or yh.get("post_market"):
            if "best" not in result or (
                result["best"].get("data_freshness", "").startswith("STALE")
                or result["best"].get("data_freshness", "").startswith("EOD")
            ):
                result["best"] = yh
        elif "best" not in result:
            result["best"] = yh

    # 3. Alpha Vantage (备用)
    av = alpha_vantage_quote(ticker)
    if av and "error" not in av:
        result["quotes"]["alpha_vantage"] = av
        if "best" not in result:
            result["best"] = av

    # 汇总摘要
    best = result.get("best", {})
    result["summary"] = {
        "price": best.get("price"),
        "prev_close": best.get("prev_close"),
        "change": best.get("change"),
        "change_pct": best.get("change_pct"),
        "source": best.get("source", "none"),
        "freshness": best.get("data_freshness", "no data"),
    }

    return result


def get_multi_quotes(tickers: list[str]) -> dict:
    """批量获取实时报价."""
    results = {}
    for t in tickers:
        results[t.upper()] = get_realtime_quote(t)
    return results


def format_quote_display(ticker: str, data: dict) -> str:
    """格式化单只股票显示."""
    s = data.get("summary", {})
    price = s.get("price")
    change = s.get("change")
    pct = s.get("change_pct")
    source = s.get("source", "?")
    freshness = s.get("freshness", "?")
    market = data.get("market", {})

    lines = [f"{ticker}: ${price:.2f}" if price else f"{ticker}: N/A"]
    if change is not None:
        sign = "+" if change >= 0 else ""
        lines.append(
            f"  Δ {sign}{change:.2f} ({sign}{pct:.2f}%)"
            if pct is not None
            else f"  Δ {sign}{change:.2f}"
        )
    lines.append(f"  src: {source} | {freshness}")
    if market.get("holiday"):
        lines.append(f"  HOLIDAY: {market['holiday']}")
    else:
        lines.append(f"  session: {market.get('session', '?')}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant Real-Time Data Engine")
    p.add_argument(
        "--tickers", type=str, default="MU,INTC,MRVL,NVDA", help="逗号分隔的股票代码"
    )
    p.add_argument("--market-status", action="store_true", help="只显示市场状态")
    p.add_argument("--futures", action="store_true", help="显示期货数据")
    p.add_argument("--json", action="store_true", help="JSON输出")
    args = p.parse_args()

    if args.market_status:
        ms = detect_market_session()
        if args.json:
            print(json.dumps(ms, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"ET: {ms['et_time']}")
            print(f"Session: {ms['session']} | Open: {ms['is_open']}")
            if ms.get("holiday"):
                print(f"HOLIDAY: {ms['holiday']}")
            print(f"Next: {ms['next_session']}")
    elif args.futures:
        futs = fetch_futures()
        if args.json:
            print(json.dumps(futs, indent=2, ensure_ascii=False, default=str))
        else:
            for sym, d in futs.items():
                if "error" in d:
                    print(f"{d['name']} ({sym}): ERROR {d['error']}")
                else:
                    chg = d.get("change", 0) or 0
                    pct = d.get("change_pct", 0) or 0
                    sign = "+" if chg >= 0 else ""
                    print(
                        f"{d['name']} ({sym}): {d.get('price')}  {sign}{chg} ({sign}{pct}%)"
                    )
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        ms = detect_market_session()
        if not args.json:
            print(
                f"=== Market: {ms['et_time']} | {ms['session']} | {'HOLIDAY: ' + ms['holiday'] if ms.get('holiday') else 'Open: ' + str(ms['is_open'])} ===\n"
            )
        for t in tickers:
            data = get_realtime_quote(t)
            if args.json:
                print(json.dumps({t: data}, indent=2, ensure_ascii=False, default=str))
            else:
                print(format_quote_display(t, data))
                print()

            if not args.json:
                # 10 calls/min rate limit
                time.sleep(0.5)
