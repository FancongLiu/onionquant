#!/usr/bin/env python3
"""
heat_collector.py — 热度数据持续采集器 (零 AI token, 纯 Python)

每 30 分钟采集一轮:
  - ApeWisdom v2.0 18-filter 全量热度
  - MarketHeat 成交量 + Finviz 异常量榜
  - 保存快照到 sentiment_data/ 用于趋势分析

运行方式:
  python scripts/heat_collector.py                    # 前台运行, Ctrl+C 停止
  python scripts/heat_collector.py --once             # 只跑一轮
  python scripts/heat_collector.py --interval 15      # 每15分钟一轮

设计: 作为 background_scheduler.py 的子进程或独立运行.
      全部数据采集用 Python, 不消耗 AI token.
"""

import json
import sys
import time
import signal
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data" / "collector"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── 配置 ───
INTERVAL_MINUTES = 30
AI_CHAIN_TICKERS = [
    "NVDA", "AMD", "INTC", "TSM", "AVGO", "MRVL",
    "MU", "LITE", "COHR", "AAOI",
    "ANET", "CIEN",
    "RKLB", "ASTS", "LUNR", "RDW",
]

running = True


def handle_sigint(sig, frame):
    global running
    print("\n  [STOP] Graceful shutdown...")
    running = False


signal.signal(signal.SIGINT, handle_sigint)


def collect_heat_rankings() -> dict | None:
    """采集 ApeWisdom 热度数据."""
    try:
        from company.tools.heat_rankings import HeatRankings
        engine = HeatRankings()
        engine.fetch_all_filters(max_pages_per_filter=5)
        # 提取核心数据
        ai_chain = [s for s in engine.all_stocks if s.get("in_ai_chain")]
        ai_chain.sort(key=lambda x: -x["mentions"])
        top_20 = engine.absolute_ranking(20)
        rising = [s for s in engine.all_stocks
                  if s.get("rank_change", 0) > 3 and s["mentions"] >= 5]
        rising.sort(key=lambda x: -x["rank_change"])

        return {
            "source": "ApeWisdom v2.0",
            "total_stocks": len(engine.all_stocks),
            "top_20": [{"ticker": s["ticker"], "mentions": s["mentions"],
                         "rank": s["rank"], "rank_change": s["rank_change"],
                         "subreddits": s.get("subreddits", [])[:5]}
                       for s in top_20],
            "ai_chain": [{"ticker": s["ticker"], "mentions": s["mentions"],
                           "rank": s["rank"], "rank_change": s["rank_change"],
                           "subreddit_count": s.get("subreddit_count", 0)}
                         for s in ai_chain],
            "rising_10": [{"ticker": s["ticker"], "mentions": s["mentions"],
                            "rank_change": s["rank_change"]}
                          for s in rising[:10]],
        }
    except Exception as e:
        print(f"  [ERR] ApeWisdom: {e}")
        return None


def collect_market_heat() -> dict | None:
    """采集市场热力数据."""
    try:
        from company.tools.market_heat import MarketHeat
        mh = MarketHeat()
        vol_results = mh.unusual_volume_scan(AI_CHAIN_TICKERS)
        vol_results.sort(key=lambda x: -x["volume_ratio"])
        finviz = mh.finviz_screener("unusual_volume")

        return {
            "source": "MarketHeat",
            "volume_heat": [{"ticker": r["ticker"],
                              "volume_ratio": r["volume_ratio"],
                              "current_volume": r["current_volume"],
                              "price_change_pct": r["price_change_pct"],
                              "heat_level": r["heat_level"]}
                            for r in vol_results],
            "finviz_unusual": [{"ticker": r["ticker"],
                                 "change_pct": r.get("change_pct", "?")}
                               for r in finviz[:15]],
        }
    except Exception as e:
        print(f"  [ERR] MarketHeat: {e}")
        return None


def collect_round() -> dict:
    """执行一轮完整采集."""
    ts = datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*55}")
    print(f"  [COLLECT] {ts_str}")
    print(f"{'='*55}")

    heat = collect_heat_rankings()
    market = collect_market_heat()

    snapshot = {
        "timestamp": ts.isoformat(),
        "timestamp_display": ts_str,
        "heat": heat,
        "market": market,
    }

    # 保存快照
    filename = ts.strftime("%Y%m%d_%H%M") + "_heat.json"
    path = DATA_DIR / filename
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), "utf-8")

    # 更新最新快照链接
    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), "utf-8")

    # 打印摘要
    if heat:
        ai = heat["ai_chain"]
        print(f"\n  AI链 Top 5:")
        for s in ai[:5]:
            chg = f"+{s['rank_change']}" if s['rank_change'] > 0 else str(s['rank_change'])
            print(f"  {s['ticker']:<6} mentions:{s['mentions']:>4} "
                  f"rank:{s['rank']:>4} Δ24h:{chg:>5} subs:{s['subreddit_count']}")

    if market:
        vol = market["volume_heat"]
        unusual = [v for v in vol if v["volume_ratio"] >= 1.5]
        if unusual:
            print(f"\n  放量 (>1.5x):")
            for v in unusual[:5]:
                print(f"  {v['ticker']:<6} {v['volume_ratio']:.1f}x "
                      f"({v['current_volume']:,}) price:{v['price_change_pct']:+.1f}%")

    snapshot_count = len(list(DATA_DIR.glob('*.json')))
    print(f"\n  [SAVE] {path.name}  ({snapshot_count} snapshots total)")
    return snapshot


def main_loop(interval_minutes: int = INTERVAL_MINUTES):
    """持续采集主循环."""
    print(f"  OnionQuant Heat Collector")
    print(f"  Interval: {interval_minutes} min")
    print(f"  Output: {DATA_DIR}")
    print(f"  Press Ctrl+C to stop\n")

    round_num = 0
    while running:
        round_num += 1
        print(f"\n  >>> Round {round_num} <<<")
        try:
            collect_round()
        except Exception as e:
            print(f"  [FATAL] Round {round_num} failed: {e}")

        if not running:
            break

        # 等间隔 (每秒检查一次 running 状态, 可快速响应 Ctrl+C)
        print(f"\n  [WAIT] Next round in {interval_minutes} min...")
        for _ in range(interval_minutes * 60):
            if not running:
                break
            time.sleep(1)

    print(f"\n  [DONE] {round_num} rounds completed. Data saved to {DATA_DIR}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="OnionQuant Heat Collector")
    p.add_argument("--once", action="store_true", help="只跑一轮, 不循环")
    p.add_argument("--interval", type=int, default=INTERVAL_MINUTES,
                   help=f"采集间隔(分钟), 默认 {INTERVAL_MINUTES}")
    args = p.parse_args()

    if args.once:
        collect_round()
    else:
        main_loop(args.interval)
