#!/usr/bin/env python3
"""
google_trends.py — Google Trends 热度引擎 (亿级搜索量, 免费)

数据源: Google Trends (pytrends)
- 真正的海量用户行为数据 — 每天几十亿次搜索
- 对比同花顺: Google 搜索量 >> 同花顺用户行为量
- 学术证据: Google Trends 搜索量对股价波动有预测能力 (Preis et al. 2013, Nature)

Usage:
    python company/tools/google_trends.py --ai-chain
    python company/tools/google_trends.py --ticker NVDA
    python company/tools/google_trends.py --rising
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data" / "google_trends"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AI_CHAIN_TICKERS = [
    "NVDA", "AMD", "INTC", "TSM", "AVGO", "MRVL",
    "MU", "LITE", "COHR", "AAOI",
    "ANET", "CIEN",
    "RKLB", "ASTS", "LUNR", "RDW",
]

# ─── 搜索词优化: 加 "stock" 去除噪音 ───
def _stock_kw(ticker: str) -> str:
    """NVDA → 'NVDA stock' 避免搜索到其他含义."""
    ambiguous = {"LITE", "COHR", "FN", "ANET", "CIEN", "RDW", "MU", "RKLB"}
    if ticker in ambiguous:
        return f"{ticker} stock"
    return ticker


class GoogleTrendsHeat:
    """Google Trends 热度引擎 — 基于数十亿次真实搜索行为."""

    def __init__(self):
        self.pytrends = TrendReq(hl="en-US", tz=360, timeout=30)
        self._cache: dict[str, dict] = {}

    # ─── 单 ticker 搜索趋势 ───

    def get_interest(self, ticker: str, timeframe: str = "today 7-d") -> dict:
        """获取单个 ticker 的搜索兴趣度.

        Returns:
            {
                "ticker": "NVDA",
                "current_interest": 85,       # 当前相对兴趣值 (0-100)
                "peak_interest": 100,          # 周期内峰值
                "avg_interest": 72.3,          # 周期内均值
                "trend": "rising",             # rising/falling/stable
                "change_pct": +18.5,           # 变化百分比
                "daily_data": [...],           # 每日数据点
                "related_queries": [...],      # 相关搜索词 (热门方向)
            }
        """
        kw = _stock_kw(ticker)
        try:
            self.pytrends.build_payload(
                kw_list=[kw],
                timeframe=timeframe,
                geo="US",
                gprop="",
            )
            interest_df = self.pytrends.interest_over_time()
            if interest_df.empty:
                return self._empty_result(ticker)

            values = interest_df[kw].values
            current = float(values[-1]) if len(values) > 0 else 0
            peak = float(values.max())
            avg = float(values.mean())

            # 趋势: 最近3天 vs 前3天
            if len(values) >= 6:
                recent = values[-3:].mean()
                earlier = values[:-3].mean()
                if earlier > 0:
                    change_pct = (recent - earlier) / earlier * 100
                else:
                    change_pct = 0.0
                if change_pct > 10:
                    trend = "rising"
                elif change_pct < -10:
                    trend = "falling"
                else:
                    trend = "stable"
            else:
                change_pct = 0.0
                trend = "stable"

            # 收集每日数据
            daily = []
            for idx, val in interest_df[kw].items():
                if val > 0:
                    daily.append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "interest": int(val),
                    })

            # 相关搜索词
            related = self._get_related_queries(kw)

            return {
                "ticker": ticker,
                "search_term": kw,
                "current_interest": round(current, 1),
                "peak_interest": round(peak, 1),
                "avg_interest": round(avg, 1),
                "trend": trend,
                "change_pct": round(change_pct, 1),
                "daily_data": daily,
                "related_queries": related,
                "data_volume": "GOOGLE_SCALE",  # 十亿级
            }
        except Exception as e:
            print(f"  [WARN] Google Trends {ticker}: {e}")
            return self._empty_result(ticker)

    def _empty_result(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "search_term": _stock_kw(ticker),
            "current_interest": 0,
            "peak_interest": 0,
            "avg_interest": 0,
            "trend": "no_data",
            "change_pct": 0.0,
            "daily_data": [],
            "related_queries": [],
            "data_volume": "GOOGLE_SCALE",
        }

    def _get_related_queries(self, kw: str) -> list[dict]:
        """获取相关搜索词 (揭示市场在搜什么方向)."""
        try:
            related = self.pytrends.related_queries()
            rising = related.get(kw, {}).get("rising", pd.DataFrame())
            if rising is None or rising.empty:
                return []
            results = []
            for _, row in rising.head(10).iterrows():
                results.append({
                    "query": row.get("query", ""),
                    "value": int(row.get("value", 0)),
                })
            return results
        except Exception:
            return []

    # ─── 批量对比 ───

    def compare_tickers(
        self, tickers: list[str], timeframe: str = "today 7-d",
    ) -> list[dict]:
        """对比多个 ticker 的相对搜索热度.

        Google Trends 限制每次最多5个关键词对比.
        我们用 NVDA 作为基准锚定, 分批对比.
        """
        results = []
        # 先拿 NVDA 做基准
        base = self.get_interest("NVDA", timeframe)
        base_val = base["current_interest"]
        results.append(base)

        # 分批对比 (每批5个)
        batch_size = 5
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            kw_list = [_stock_kw(t) for t in batch]
            try:
                self.pytrends.build_payload(
                    kw_list=kw_list,
                    timeframe=timeframe,
                    geo="US",
                    gprop="",
                )
                interest_df = self.pytrends.interest_over_time()
                if interest_df.empty:
                    continue

                for t in batch:
                    kw = _stock_kw(t)
                    if kw not in interest_df.columns:
                        continue
                    values = interest_df[kw].values
                    current = float(values[-1]) if len(values) > 0 else 0
                    peak = float(values.max())
                    avg = float(values.mean())

                    results.append({
                        "ticker": t,
                        "search_term": kw,
                        "current_interest": round(current, 1),
                        "peak_interest": round(peak, 1),
                        "avg_interest": round(avg, 1),
                        "relative_to_nvda": round(current / max(base_val, 1), 2),
                        "data_volume": "GOOGLE_SCALE",
                    })
                time.sleep(2)  # Google Trends rate limit
            except Exception as e:
                print(f"  [WARN] Google Trends batch {batch}: {e}")

        results.sort(key=lambda x: x["current_interest"], reverse=True)
        return results

    # ─── 上升榜 ───

    def rising_leaders(
        self, tickers: list[str], threshold_pct: float = 15.0,
    ) -> list[dict]:
        """找出搜索热度正在飙升的 ticker."""
        rising = []
        for ticker in tickers:
            data = self.get_interest(ticker, timeframe="today 7-d")
            if data["trend"] == "rising" and data["change_pct"] >= threshold_pct:
                rising.append(data)
            time.sleep(1.5)

        rising.sort(key=lambda x: -x["change_pct"])
        return rising

    # ─── 全量快照 ───

    def full_scan(self, tickers: list[str] | None = None) -> dict:
        """全量 Google Trends 扫描 + 排行."""
        if tickers is None:
            tickers = AI_CHAIN_TICKERS

        print(f"\n  [>] Google Trends: {len(tickers)} tickers (GOOGLE-SCALE data)...")
        comparison = self.compare_tickers(tickers)
        rising = self.rising_leaders(tickers)

        # 热度排行
        hot = [t for t in comparison if t["current_interest"] >= 5]
        hot.sort(key=lambda x: -x["current_interest"])

        # 保存快照
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        snapshot = {
            "timestamp": ts,
            "total_tickers_scanned": len(tickers),
            "data_scale": "GOOGLE — billions of daily searches, US geo-filtered",
            "hot_ranking": hot,
            "rising_leaders": rising,
            "full_comparison": comparison,
        }
        path = DATA_DIR / f"google_trends_{ts}.json"
        path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), "utf-8")

        return snapshot

    # ─── 打印仪表盘 ───

    def print_dashboard(self, snapshot: dict):
        """打印 Google Trends 热榜."""
        hot = snapshot["hot_ranking"]
        rising = snapshot["rising_leaders"]

        print(f"\n{'='*60}")
        print(f"  GOOGLE TRENDS HEAT — US Search Interest (7-day)")
        print(f"  Data Scale: Billions of daily searches → millions of stock queries")
        print(f"{'='*60}")

        print(f"\n  >> 搜索热度 TOP 10:")
        for i, s in enumerate(hot[:10]):
            rel = s.get("relative_to_nvda", 0)
            print(f"  {i+1}. {s['ticker']:<6} interest:{s['current_interest']:>6.1f} "
                  f"peak:{s['peak_interest']:>6.1f} vsNVDA:{rel:.2f}x")

        print(f"\n  >> 搜索量飙升榜 (Google Trends rising):")
        if rising:
            for i, s in enumerate(rising[:10]):
                related_str = ""
                if s.get("related_queries"):
                    top_q = s["related_queries"][:3]
                    related_str = " | " + ", ".join(
                        q["query"] for q in top_q
                    )
                print(f"  {i+1}. {s['ticker']:<6} Δ{ s['change_pct']:+.1f}% "
                      f"interest:{s['current_interest']:.1f}{related_str}")
        else:
            print("  (no tickers with >15% search surge in past 7 days)")


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="OnionQuant Google Trends Heat Engine")
    p.add_argument("--ticker", type=str, help="单票深度搜索趋势")
    p.add_argument("--ai-chain", action="store_true", help="AI产业链全量扫描")
    p.add_argument("--rising", action="store_true", help="飙升榜")
    p.add_argument("--compare", type=str, help="对比多个ticker (逗号分隔)")
    args = p.parse_args()

    gt = GoogleTrendsHeat()

    if args.ticker:
        data = gt.get_interest(args.ticker.upper())
        print(f"\n  Google Trends: ${args.ticker.upper()}")
        print(f"  当前搜索兴趣: {data['current_interest']} (峰值: {data['peak_interest']})")
        print(f"  趋势: {data['trend']} ({data['change_pct']:+.1f}%)")
        print(f"  数据规模: {data['data_volume']}")
        if data["related_queries"]:
            print(f"  相关热搜:")
            for q in data["related_queries"][:5]:
                print(f"    ↑{q['value']}% {q['query']}")
        if data["daily_data"]:
            print(f"  每日趋势:")
            for d in data["daily_data"]:
                bar = "█" * int(d["interest"] / 2)
                print(f"    {d['date']} {bar} {d['interest']}")

    elif args.compare:
        tickers = [t.strip().upper() for t in args.compare.split(",")]
        results = gt.compare_tickers(tickers)
        results.sort(key=lambda x: -x["current_interest"])
        print(f"\n  Google Trends Comparison (锚定 NVDA):")
        for r in results:
            rel = r.get("relative_to_nvda", "?")
            print(f"  {r['ticker']:<6} interest:{r['current_interest']:>6.1f} "
                  f"peak:{r['peak_interest']:>6.1f} vsNVDA:{rel}x")

    elif args.rising:
        rising = gt.rising_leaders(AI_CHAIN_TICKERS)
        print(f"\n  Google Trends 飙升榜 (Δ>15%):")
        for r in rising:
            print(f"  {r['ticker']:<6} Δ{r['change_pct']:+.1f}% "
                  f"interest:{r['current_interest']:.1f}")

    elif args.ai_chain:
        snapshot = gt.full_scan(AI_CHAIN_TICKERS)
        gt.print_dashboard(snapshot)
        print(f"\n  [SAVE] {DATA_DIR}")

    else:
        # 默认: 快速展示 AI 链 top 8
        results = gt.compare_tickers(AI_CHAIN_TICKERS[:8])
        results.sort(key=lambda x: -x["current_interest"])
        print(f"\n  Google Trends Quick View:")
        for r in results:
            print(f"  {r['ticker']:<6} interest:{r['current_interest']:>6.1f} "
                  f"peak:{r['peak_interest']:>6.1f}")
