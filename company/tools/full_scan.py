#!/usr/bin/env python3
"""
full_scan.py — OnionQuant 全源扫描引擎 v3.0 (一条命令, 全部数据源)

数据源 (全部免费/免注册):
  Level 1 — 热度排行 (预建, 同花顺风格):
    heat_rankings.py → ApeWisdom 18-filter v2.0 · 总榜/上升榜/新晋榜/AI链榜/社区分布

  Level 2 — 市场热力 (真实交易数据, 百万-亿级):
    market_heat.py → yfinance 异常成交量 + 期权大单 + Finviz screener

  Level 3 — Reddit 实时:
    reddit_scanner.py → Reddit 公开 JSON · 8个子版块 · 关键词情绪

  Level 4 — 新闻情绪:
    news_scanner.py → Finviz 100条/ticker · 26+来源

  Level 5 — 交叉验证:
    四源交叉验证 (ApeWisdom + Volume + Reddit + News) → 信号确认

Usage:
    python company/tools/full_scan.py                    # 完整仪表盘
    python company/tools/full_scan.py --ticker MU        # 单票深度分析
    python company/tools/full_scan.py --ai-chain         # AI产业链速查
    python company/tools/full_scan.py --quick            # 快速模式 (热度+市场)
    python company/tools/full_scan.py --save             # 保存快照
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AI_CHAIN_TICKERS = {
    "LITE": "上游/激光器-CPO龙头",
    "COHR": "上游/全方案-SiPh+VCSEL+InP",
    "SIVEF": "上游/激光器-CPO外置光源(OTC)",
    "AAOI": "上游/收发器-1.6T光模块",
    "AVGO": "上游/光DSP-全球龙头",
    "MRVL": "上游/光DSP+定制ASIC",
    "NVDA": "下游/CPO交换机定义者",
    "AMD": "中游/AI芯片-CPU+GPU",
    "INTC": "中游/封装-EMIB 2.5D",
    "TSM": "中游/封装-CoWoS标准",
    "FN": "中游/封装-光器件OSAT",
    "MU": "上游/HBM-HBM3E/4",
    "SNDK": "上游/NAND-闪存",
    "RKLB": "航天/发射-小卫星+Neutron",
    "ASTS": "航天/通信-卫星直连手机",
    "LUNR": "航天/月球-NASA CLPS",
    "RDW": "航天/基础设施-轨道DC",
    "ANET": "下游/网络-数据中心交换机",
    "CIEN": "下游/网络-光网络DCI",
}


class FullScanner:
    """全源扫描引擎 v3.0 — 一站式获取所有热度数据."""

    def __init__(self):
        self.heat = None
        self.market = None
        self.reddit = None
        self.news = None
        self.results = {}

    def init(self, use_multi_filter: bool = True):
        """延迟初始化各模块."""
        print("[INIT] Loading scanners...")
        try:
            from company.tools.heat_rankings import HeatRankings

            self.heat = HeatRankings()
            self._use_multi_filter = use_multi_filter
            tag = "v2.0 18-filter" if use_multi_filter else "v1.0 all-stocks"
            print(f"  [OK] HeatRankings ({tag})")
        except Exception as e:
            print(f"  [WARN] HeatRankings: {e}")

        try:
            from company.tools.market_heat import MarketHeat

            self.market = MarketHeat()
            print("  [OK] MarketHeat (volume + options flow)")
        except Exception as e:
            print(f"  [WARN] MarketHeat: {e}")

        try:
            from company.tools.reddit_scanner import RedditScanner

            self.reddit = RedditScanner()
            print("  [OK] RedditScanner (public JSON, no API key)")
        except Exception as e:
            print(f"  [WARN] RedditScanner: {e}")

        try:
            from company.tools.news_scanner import NewsScanner

            self.news = NewsScanner()
            print("  [OK] NewsScanner (Finviz, 100 articles/ticker)")
        except Exception as e:
            print(f"  [WARN] NewsScanner: {e}")

        print()

    def run_heat_dashboard(self):
        """Level 1: 热度仪表盘 (ApeWisdom v2.0)."""
        if not self.heat:
            return
        print("\n" + "#" * 65)
        mode = "v2.0 18-FILTER" if getattr(self, "_use_multi_filter", True) else "v1.0"
        print(f"#  LEVEL 1: HEAT RANKINGS ({mode})")
        print("#" * 65)

        if getattr(self, "_use_multi_filter", True):
            self.heat.fetch_all_filters()
        else:
            self.heat.fetch_all(max_pages=8)
        stocks = self.heat.all_stocks

        # 总热度 Top 10
        absolute = self.heat.absolute_ranking(10)
        print("\n  >> 总热度 TOP 10 (跨子版块聚合):")
        for i, s in enumerate(absolute):
            subs = ", ".join(s.get("subreddits", [])[:3])
            print(
                f"  {i + 1}. {s['ticker']:<6} mentions:{s['mentions']:>4} "
                f"rank:{s['rank']:>4} upvotes:{s['upvotes']:>5} | {subs}"
            )

        # 24h 上升榜
        rising = [
            s for s in stocks if s.get("rank_change", 0) > 3 and s["mentions"] >= 5
        ]
        rising.sort(key=lambda x: -x["rank_change"])
        print("\n  >> 24h 上升榜 (mentions>=5, Δrank>3):")
        for i, s in enumerate(rising[:10]):
            ai_tag = " [AI]" if s["in_ai_chain"] else ""
            sub_count = s.get("subreddit_count", 0)
            print(
                f"  {i + 1}. {s['ticker']:<6} mentions:{s['mentions']:>4} "
                f"Δrank:+{s['rank_change']:<4} subs:{sub_count}{ai_tag}"
            )

        # AI 链排行
        ai_chain = [s for s in stocks if s["in_ai_chain"]]
        ai_chain.sort(key=lambda x: -x["mentions"])
        print("\n  >> AI产业链热度:")
        for i, s in enumerate(ai_chain):
            chg = (
                f"+{s['rank_change']}"
                if s["rank_change"] > 0
                else str(s["rank_change"])
            )
            subs = ", ".join(s.get("subreddits", [])[:3])
            print(
                f"  {s['ticker']:<6} mentions:{s['mentions']:>4} rank:{s['rank']:>4} "
                f"Δ24h:{chg:>5} subs:{s.get('subreddit_count', 0)} | {subs}"
            )

        self.results["heat"] = {
            "total_stocks": len(stocks),
            "top_10": absolute,
            "rising_10": rising[:10],
            "ai_chain": ai_chain,
        }

    def run_market_heat(self, tickers: list[str] | None = None):
        """Level 2: 市场热力 — 真实交易数据. 百万-亿级数据量."""
        if not self.market:
            return
        print(f"\n{'#' * 65}")
        print("#  LEVEL 2: MARKET HEAT (Real Trading Data)")
        print("#  Scale: millions of shares/day → GENUINE BIG DATA")
        print(f"{'#' * 65}")

        if tickers is None:
            tickers = list(AI_CHAIN_TICKERS.keys())

        vol_results = self.market.unusual_volume_scan(tickers)
        unusual = [r for r in vol_results if r["is_unusual"]]
        vol_results.sort(key=lambda x: -x["volume_ratio"])

        print("\n  >> 成交量热度 (AI链, 当前量 vs 10日均量):")
        for i, r in enumerate(vol_results[:12]):
            icon = (
                "🔴"
                if r["volume_ratio"] >= 3
                else "🟡"
                if r["volume_ratio"] >= 2
                else ""
            )
            price_sign = "+" if r["price_change_pct"] > 0 else ""
            print(
                f"  {i + 1}. {r['ticker']:<6} {icon} {r['volume_ratio']:.1f}x "
                f"({r['current_volume']:,} shrs) "
                f"{price_sign}{r['price_change_pct']:.1f}% {r['heat_level']}"
            )

        # Finviz 全市场异常量
        finviz = self.market.finviz_screener("unusual_volume")
        ai_in_finviz = [r for r in finviz if r["ticker"] in AI_CHAIN_TICKERS]
        print(f"\n  >> Finviz 全市场异常量榜{' (AI链)' if ai_in_finviz else ''}:")
        for r in finviz[:10]:
            tag = " [AI]" if r["ticker"] in AI_CHAIN_TICKERS else ""
            print(f"  {r['ticker']:<6} {r.get('change_pct', '?'):>8}{tag}")

        self.results["market"] = {
            "volume_heat": vol_results,
            "unusual_count": len(unusual),
            "finviz_unusual": finviz,
            "ai_in_finviz": ai_in_finviz,
        }

    def run_reddit_scan(self, tickers: list[str] | None = None):
        """Level 3: Reddit 实时."""
        if not self.reddit:
            return
        print(f"\n{'#' * 65}")
        print("#  LEVEL 3: REDDIT REAL-TIME (Public JSON)")
        print(f"{'#' * 65}")

        if tickers is None:
            tickers = list(AI_CHAIN_TICKERS.keys())

        results = []
        for ticker in tickers:
            data = self.reddit.count_mentions(ticker, time_filter="week")
            if data["total_posts"] >= 2:
                results.append(data)
                print(
                    f"  {ticker:<6} {data['total_posts']:>2}帖 "
                    f"score:{data['total_score']:>5} "
                    f"sent:{data['avg_sentiment']:+.2f} "
                    f"+{data['positive_pct']}% {data['buzz_level']}"
                )

        results.sort(key=lambda x: x["total_posts"], reverse=True)
        self.results["reddit"] = results
        print(
            f"\n  Reddit coverage: {len(results)}/{len(tickers)} tickers with discussion"
        )

    def run_news_scan(self, tickers: list[str] | None = None):
        """Level 4: 新闻情绪."""
        if not self.news:
            return
        print(f"\n{'#' * 65}")
        print("#  LEVEL 4: NEWS SENTIMENT (Finviz)")
        print(f"{'#' * 65}")

        if tickers is None:
            tickers = list(AI_CHAIN_TICKERS.keys())[:10]

        results = []
        for ticker in tickers:
            r = self.news.scan_ticker(ticker)
            if r["news_count"] > 0:
                results.append(r)
                print(
                    f"  {ticker:<6} {r['news_count']:>3}条 "
                    f"sent:{r['sentiment']['avg_compound']:+.2f} "
                    f"{r['sentiment']['sentiment_label']:<8} "
                    f"{r['buzz_level']}"
                )
            time.sleep(1.5)

        results.sort(key=lambda x: x["news_count"], reverse=True)
        self.results["news"] = results

    def run_cross_validation(self, top_n: int = 16):
        """Level 5: 四源交叉验证 (ApeWisdom + Volume + Reddit + News)."""
        print(f"\n{'#' * 65}")
        print("#  LEVEL 5: CROSS-VALIDATION (4 sources)")
        print(f"{'#' * 65}")

        heat_data = self.results.get("heat", {})
        market_data = self.results.get("market", {})
        reddit_data = {r["ticker"]: r for r in self.results.get("reddit", [])}
        news_data = {r["ticker"]: r for r in self.results.get("news", [])}
        vol_data = {r["ticker"]: r for r in market_data.get("volume_heat", [])}

        ai_chain = heat_data.get("ai_chain", [])[:top_n]

        print(
            f"\n  {'Ticker':<6} {'ApeWis':>6} {'Volume':>7} {'Reddit':>7} {'News':>7} {'Signal':<20}"
        )
        print(f"  {'-' * 60}")

        for s in ai_chain:
            ticker = s["ticker"]
            ape_score = s.get("rank_change", 0)
            reddit_count = reddit_data.get(ticker, {}).get("total_posts", 0)
            news_sent = (
                news_data.get(ticker, {}).get("sentiment", {}).get("avg_compound", 0)
            )
            vol = vol_data.get(ticker, {})
            vol_ratio = vol.get("volume_ratio", 1.0)

            # 四源信号确认
            signals = 0
            if ape_score > 3:
                signals += 1
            if vol_ratio >= 1.5:
                signals += 1
            if reddit_count >= 3:
                signals += 1
            if news_sent > 0.1:
                signals += 1

            if signals >= 4:
                strength = "STRONG BUY [4/4]"
            elif signals >= 3:
                strength = "STRONG BUY [3/4]"
            elif signals >= 2:
                strength = "BUY [2/4]"
            elif signals >= 1:
                strength = "WATCH [1/4]"
            else:
                strength = "NO SIGNAL"

            ape_str = f"+{ape_score}" if ape_score > 0 else str(ape_score)
            vol_str = f"{vol_ratio:.1f}x" if vol_ratio > 0 else "N/A"
            print(
                f"  {ticker:<6} Δ{ape_str:>5} {vol_str:>7} "
                f"{reddit_count:>3}帖/{reddit_data.get(ticker, {}).get('total_score', 0):>4}分 "
                f"{news_sent:>+.2f}  {strength:<20}"
            )

            s["cross_signal"] = signals
            s["cross_recommendation"] = strength

    def run_full(self, save: bool = False, skip_slow: bool = False):
        """执行完整扫描."""
        start = time.time()
        print(f"\n{'=' * 65}")
        print("  OnionQuant FULL SCAN ENGINE v3.0")
        print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("  Sources: ApeWisdom(v2) + MarketHeat + Reddit + Finviz News")
        print("  Cost: FREE (no API keys, no registration)")
        print("  Data Scale: social(Reddit) + trading(millions of shares) + news")
        print(f"{'=' * 65}")

        self.run_heat_dashboard()
        self.run_market_heat()

        if not skip_slow:
            self.run_reddit_scan()
            self.run_news_scan()

        self.run_cross_validation()

        elapsed = time.time() - start
        print(f"\n{'=' * 65}")
        print(f"  SCAN COMPLETE in {elapsed:.0f}s")
        print(
            f"  Data sources: 4 | Tickers tracked: 600+ | AI chain: {len(AI_CHAIN_TICKERS)}"
        )
        print(f"{'=' * 65}")

        if save:
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            path = DATA_DIR / f"full_scan_{ts}.json"
            path.write_text(
                json.dumps(self.results, indent=2, ensure_ascii=False, default=str),
                "utf-8",
            )
            print(f"\n  [SAVE] {path}")

    def deep_dive(self, ticker: str):
        """单票深度分析 — 四源交叉."""
        ticker = ticker.upper()
        print(f"\n{'=' * 55}")
        print(f"  DEEP DIVE: ${ticker}")
        print(f"{'=' * 55}")

        # ApeWisdom
        if self.heat:
            if getattr(self, "_use_multi_filter", True):
                self.heat.fetch_all_filters()
            else:
                self.heat.fetch_all(max_pages=8)
            stock = next(
                (s for s in self.heat.all_stocks if s["ticker"] == ticker), None
            )
            if stock:
                subs = ", ".join(stock.get("subreddits", [])[:5])
                print(
                    f"\n  [1] ApeWisdom: rank #{stock['rank']} | "
                    f"mentions:{stock['mentions']} | Δ24h:{stock['rank_change']:+d}"
                )
                print(
                    f"       upvotes:{stock['upvotes']} | "
                    f"subreddits({stock.get('subreddit_count', 0)}): {subs}"
                )

        # Market Heat
        if self.market:
            vol = self.market.unusual_volume_scan([ticker])
            if vol:
                v = vol[0]
                print(
                    f"\n  [2] Market: {v['current_volume']:,} shares "
                    f"({v['volume_ratio']:.1f}x avg) | "
                    f"price:{v['price_change_pct']:+.1f}% | {v['heat_level']}"
                )
            opt = self.market.options_flow_scan(ticker)
            if opt["unusual_trades"] > 0:
                print(
                    f"       Options: {opt['unusual_trades']} unusual trades | "
                    f"C:${opt['call_premium']:,.0f} P:${opt['put_premium']:,.0f} "
                    f"| {opt['flow_bias']}"
                )
                for t in opt["top_trades"][:3]:
                    print(
                        f"       {t['side']} ${t['strike']} {t['expiration']} "
                        f"prem:${t['premium']:,.0f} ratio:{t['vol_oi_ratio']}x"
                    )

        # Reddit
        if self.reddit:
            data = self.reddit.count_mentions(ticker, time_filter="week")
            print(
                f"\n  [3] Reddit: {data['total_posts']} posts | "
                f"score:{data['total_score']} | sent:{data['avg_sentiment']:+.2f}"
            )
            if data["top_posts"]:
                for p in data["top_posts"][:5]:
                    s = p.get("sentiment_label", "neutral")
                    tag = f" [{s}]" if s != "neutral" else ""
                    print(
                        f"  [{p['score']}↑] r/{p['subreddit']}{tag} — {p['title'][:80]}"
                    )

        # News
        if self.news:
            r = self.news.scan_ticker(ticker)
            print(
                f"\n  [4] News: {r['news_count']} articles | "
                f"sent:{r['sentiment']['avg_compound']:+.2f} | {r['sentiment']['sentiment_label']}"
            )
            if r["catalysts"]:
                print("  [!] Catalysts:")
                for c in r["catalysts"][:5]:
                    sign = "+" if c["weight"] > 0 else ""
                    print(
                        f"  {sign}{c['weight']:.1f} [{c['keyword']}] {c['headline'][:80]}"
                    )


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant Full Scan Engine v3.0")
    p.add_argument("--ticker", type=str, help="单票深度分析")
    p.add_argument("--ai-chain", action="store_true", help="AI产业链速查")
    p.add_argument("--save", action="store_true", help="保存快照")
    p.add_argument(
        "--quick", action="store_true", help="快速模式 (热度+市场, 跳过Reddit/News)"
    )
    p.add_argument("--v1", action="store_true", help="使用 v1.0 单filter模式")
    args = p.parse_args()

    scanner = FullScanner()
    scanner.init(use_multi_filter=not args.v1)

    if args.ticker:
        if getattr(scanner, "_use_multi_filter", True):
            scanner.heat.fetch_all_filters()
        else:
            scanner.heat.fetch_all(max_pages=8)
        scanner.deep_dive(args.ticker)
    elif args.ai_chain:
        scanner.run_heat_dashboard()
        scanner.run_market_heat()
        scanner.run_cross_validation(top_n=20)
    elif args.quick:
        scanner.run_heat_dashboard()
        scanner.run_market_heat()
    else:
        scanner.run_full(save=args.save, skip_slow=args.quick)
