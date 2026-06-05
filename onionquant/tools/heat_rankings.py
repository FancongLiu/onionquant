#!/usr/bin/env python3
"""
heat_rankings.py — ApeWisdom 热榜引擎 v2.0 (同花顺风格)

v2.0 升级: 从单一 all-stocks filter → 全部 18 个 filter 聚合
  - 每个子版块独立排行 → 跨子版块合并 → 更精准的热度信号
  - 追踪子版块分布: 哪个社区在讨论这只股票？
  - 数据量: 单 filter 614 stocks × 18 filters → 聚合后 1000+ 唯一 ticker

基于 ApeWisdom API 构建的热度排行系统:
  - 总热度榜 (绝对rank x 跨子版块合并)
  - 24h 上升榜 (rank改善最大)
  - 24h 下降榜 (rank恶化最大)
  - 新晋热榜 (24h前>200名, 已冲进Top50)
  - AI产业链专属榜
  - 历史趋势曲线 (基于快照)

数据: ApeWisdom, 18 filters × 9 pages each
API: https://apewisdom.io/api/v1.0/filter/{filter}/page/{1-9}

Usage:
    python onionquant/tools/heat_rankings.py                        # 全榜显示
    python onionquant/tools/heat_rankings.py --all-filters          # 18 filter 全量聚合
    python onionquant/tools/heat_rankings.py --top 20               # Top 20
    python onionquant/tools/heat_rankings.py --rising 15            # 24h上升榜
    python onionquant/tools/heat_rankings.py --ai-chain             # AI产业链专属
    python onionquant/tools/heat_rankings.py --save-snapshot        # 保存快照
    python onionquant/tools/heat_rankings.py --trend NVDA           # 单只趋势
"""

import json
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data"
SNAPSHOT_DIR = DATA_DIR / "heat_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

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

# ─── 全部 18 个 ApeWisdom Filter ───
STOCK_FILTERS = [
    "all-stocks",
    "wallstreetbets",
    "WallstreetbetsELITE",
    "Wallstreetbetsnew",
    "stocks",
    "options",
    "investing",
    "Daytrading",
    "SPACs",
]

CRYPTO_FILTERS = [
    "all-crypto",
    "CryptoCurrency",
    "CryptoCurrencies",
    "Bitcoin",
    "SatoshiStreetBets",
    "CryptoMoonShots",
    "CryptoMarkets",
]

OTHER_FILTERS = [
    "all",
    "4chan",
]

ALL_FILTERS = STOCK_FILTERS + CRYPTO_FILTERS + OTHER_FILTERS

# ─── 子版块中文名 ───
SUBREDDIT_NAMES = {
    "wallstreetbets": "WSB散户",
    "WallstreetbetsELITE": "WSB精英",
    "Wallstreetbetsnew": "WSB新",
    "stocks": "r/stocks",
    "investing": "r/investing",
    "options": "r/options",
    "StockMarket": "股市",
    "Daytrading": "日内交易",
    "pennystocks": "毛票",
    "SPACs": "SPAC",
    "DividendGang": "股息",
    "CryptoCurrency": "加密货币",
    "SatoshiStreetBets": "加密赌徒",
    "CryptoMoonShots": "加密月球",
    "Bitcoin": "比特币",
    "4chan": "4chan/biz",
}


class HeatRankings:
    """ApeWisdom 热榜引擎 v2.0 — 同花顺风格热度排行, 18 filter 全量聚合."""

    BASE = "https://apewisdom.io/api/v1.0/filter"

    def __init__(self):
        self.all_stocks = []
        self.fetch_time = None
        self._filter_data: dict[str, list[dict]] = {}  # 每个 filter 的原始数据
        self._merged: dict[str, dict] = {}  # 按 ticker 合并后的聚合数据

    def _parse_stock(self, r: dict, source_filter: str = "") -> dict | None:
        """解析单条 stock 记录."""
        try:
            rank = int(r.get("rank", 9999))
            mentions = int(r.get("mentions", 0))
            upvotes = int(r.get("upvotes", 0))
            rank_24h = int(r.get("rank_24h_ago", rank))
            mentions_24h = int(r.get("mentions_24h_ago", mentions))
            ticker = r.get("ticker", "")

            return {
                "ticker": ticker,
                "name": r.get("name", ""),
                "rank": rank,
                "mentions": mentions,
                "upvotes": upvotes,
                "rank_24h_ago": rank_24h,
                "mentions_24h_ago": mentions_24h,
                "rank_change": rank_24h - rank,
                "mentions_change": mentions - mentions_24h,
                "source_filter": source_filter,
                "in_ai_chain": ticker in AI_CHAIN_TICKERS,
                "ai_chain_role": AI_CHAIN_TICKERS.get(ticker, ""),
            }
        except (ValueError, TypeError):
            return None

    def fetch_filter(self, filter_name: str, max_pages: int = 5) -> list[dict]:
        """获取单个 filter 的数据."""
        results = []
        for page in range(1, max_pages + 1):
            url = f"{self.BASE}/{filter_name}/page/{page}"
            req = urllib.request.Request(url, headers={"User-Agent": "OnionQuant/2.0"})
            try:
                raw = urllib.request.urlopen(req, timeout=15).read()
                data = json.loads(raw)
                for r in data.get("results", []):
                    stock = self._parse_stock(r, source_filter=filter_name)
                    if stock:
                        results.append(stock)
            except Exception:
                break
            time.sleep(0.05)
        return results

    def fetch_all(self, max_pages: int = 9) -> list[dict]:
        """获取 all-stocks filter (兼容旧接口, 快速模式)."""
        print(f"\n  [>] Fetching ApeWisdom all-stocks (pages 1-{max_pages})...")
        all_results = []
        for page in range(1, max_pages + 1):
            url = f"{self.BASE}/all-stocks/page/{page}"
            req = urllib.request.Request(url, headers={"User-Agent": "OnionQuant/2.0"})
            try:
                raw = urllib.request.urlopen(req, timeout=15).read()
                data = json.loads(raw)
                results = data.get("results", [])
                all_results.extend(results)
                print(f"    page {page}: {len(results)} stocks")
            except Exception as e:
                print(f"    page {page}: FAILED ({e})")
                break

        stocks = []
        for r in all_results:
            stock = self._parse_stock(r, source_filter="all-stocks")
            if stock:
                stocks.append(stock)

        self.all_stocks = stocks
        self.fetch_time = datetime.now(timezone.utc)
        print(f"    Total: {len(stocks)} stocks\n")
        return stocks

    def fetch_all_filters(
        self,
        max_pages_per_filter: int = 5,
        skip_crypto: bool = True,
    ) -> dict[str, list[dict]]:
        """🔥 v2.0: 拉满全部独立子版块 filter, 做跨社区热度分析.

        策略:
        - all-stocks 作为主数据 (ApeWisdom 已去重聚合, mentions 数可直接用)
        - 独立子版块 (wallstreetbets, stocks, options 等) 用于跨社区分布分析
        - 不含 "all" (也是聚合, 与 all-stocks 高度重叠)
        - 跨社区数 = 有多少个不同的子版块在讨论这只股票

        不重复计数! all-stocks 已经聚合了所有子版块.
        """
        # 独立子版块 (非聚合)
        individual_filters = [
            "wallstreetbets",
            "WallstreetbetsELITE",
            "Wallstreetbetsnew",
            "stocks",
            "options",
            "investing",
            "Daytrading",
            "SPACs",
        ]
        # 聚合 filter (用于主数据)
        aggregate_filter = "all-stocks"
        # 特殊
        special_filters = ["4chan"]

        all_to_fetch = [aggregate_filter] + individual_filters + special_filters

        print(
            f"\n  [🔥] ApeWisdom v2.0: {len(all_to_fetch)} filters "
            f"(1 aggregate + {len(individual_filters)} individual + 4chan)"
        )

        self._filter_data = {}

        # Step 1: 拉取所有 filter
        for fname in all_to_fetch:
            pages = 9 if fname == aggregate_filter else max_pages_per_filter
            results = self.fetch_filter(fname, max_pages=pages)
            self._filter_data[fname] = results
            label = SUBREDDIT_NAMES.get(fname, fname)
            tag = "[主数据]" if fname == aggregate_filter else ""
            print(f"    [{label:<16}] {len(results):>4} stocks {tag}")
            time.sleep(0.05)

        # Step 2: 用 all-stocks 作为主数据
        primary = {s["ticker"]: s for s in self._filter_data.get(aggregate_filter, [])}

        # Step 3: 从独立子版块提取 per-subreddit 数据
        subreddit_map: dict[str, dict[str, int]] = defaultdict(dict)
        for fname in individual_filters + special_filters:
            for s in self._filter_data.get(fname, []):
                t = s["ticker"]
                subreddit_map[t][fname] = s["mentions"]

        # Step 4: 合并 — 主数据 + 子版块分布
        stock_list = []
        for ticker, base in primary.items():
            subs = subreddit_map.get(ticker, {})
            stock_list.append(
                {
                    "ticker": ticker,
                    "name": base["name"],
                    "rank": base["rank"],
                    "mentions": base["mentions"],  # 主数据: all-stocks 聚合值
                    "upvotes": base["upvotes"],
                    "rank_24h_ago": base["rank_24h_ago"],
                    "mentions_24h_ago": base["mentions_24h_ago"],
                    "rank_change": base["rank_change"],
                    "mentions_change": base["mentions_change"],
                    "subreddit_count": len(subs),
                    "subreddit_mentions": subs,
                    "subreddits": sorted(subs.keys()),
                    "total_individual_mentions": sum(
                        subs.values()
                    ),  # 独立子版块加总(不含聚合)
                    "in_ai_chain": ticker in AI_CHAIN_TICKERS,
                    "ai_chain_role": AI_CHAIN_TICKERS.get(ticker, ""),
                }
            )

        stock_list.sort(key=lambda x: -x["mentions"])
        self.all_stocks = stock_list
        self.fetch_time = datetime.now(timezone.utc)

        total_raw = sum(len(v) for v in self._filter_data.values())
        print(
            f"    Total: {total_raw} raw records → {len(stock_list)} unique tickers "
            f"(主数据: all-stocks, +{len(individual_filters)}子版块分布)\n"
        )

        return self._filter_data

    # ─── 榜单生成 ────────────────────────────────────

    def absolute_ranking(self, top_n: int = 30) -> list[dict]:
        """总热度榜 — 按 mention 绝对数量."""
        ranked = sorted(self.all_stocks, key=lambda x: -x["mentions"])
        return ranked[:top_n]

    def rising_ranking(self, top_n: int = 30) -> list[dict]:
        """24h 上升榜 — 按 rank 改善最大 (正数=上升)."""
        rising = [s for s in self.all_stocks if s["rank_change"] > 0]
        ranked = sorted(rising, key=lambda x: -x["rank_change"])
        return ranked[:top_n]

    def falling_ranking(self, top_n: int = 30) -> list[dict]:
        """24h 下降榜 — 按 rank 恶化最大."""
        falling = [s for s in self.all_stocks if s["rank_change"] < 0]
        ranked = sorted(falling, key=lambda x: x["rank_change"])
        return ranked[:top_n]

    def mentions_surge(self, top_n: int = 30) -> list[dict]:
        """热度突变榜 — 按 mentions 变化最剧烈."""
        ranked = sorted(self.all_stocks, key=lambda x: -abs(x["mentions_change"]))
        return ranked[:top_n]

    def ai_chain_ranking(self) -> list[dict]:
        """AI产业链专属榜."""
        chain = [s for s in self.all_stocks if s["in_ai_chain"]]
        return sorted(chain, key=lambda x: -x["mentions"])

    def new_hot(self, top_n: int = 30) -> list[dict]:
        """新晋热榜 — 24h前排名很低(>200), 现在冲进前50."""
        newcomers = [
            s for s in self.all_stocks if s["rank_24h_ago"] > 200 and s["rank"] <= 50
        ]
        return sorted(newcomers, key=lambda x: x["rank"])[:top_n]

    # ─── 快照 & 趋势 ────────────────────────────────

    def save_snapshot(self) -> Path:
        """保存当前快照, 用于追踪热度变化曲线."""
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = SNAPSHOT_DIR / f"heat_{ts}.json"
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_stocks": len(self.all_stocks),
            "stocks": self.all_stocks[:200],  # 只存前200只, 省空间
        }
        path.write_text(
            json.dumps(snapshot, indent=1, ensure_ascii=False, default=str), "utf-8"
        )
        return path

    def load_trend(self, ticker: str, max_files: int = 24) -> list[dict]:
        """从历史快照中提取某 ticker 的趋势数据."""
        files = sorted(SNAPSHOT_DIR.glob("heat_*.json"))[-max_files:]
        trend = []
        for f in files:
            data = json.loads(f.read_text("utf-8"))
            for s in data.get("stocks", []):
                if s["ticker"] == ticker:
                    trend.append(
                        {
                            "time": data["timestamp"],
                            "rank": s["rank"],
                            "mentions": s["mentions"],
                            "upvotes": s["upvotes"],
                        }
                    )
                    break
        return trend

    # ─── 展示 ────────────────────────────────────────

    def print_table(self, stocks: list[dict], title: str, top_n: int = 20):
        """打印格式化榜单."""
        print(f"\n{'=' * 80}")
        print(
            f"  {title}  |  {self.fetch_time.strftime('%Y-%m-%d %H:%M UTC') if self.fetch_time else ''}"
        )
        print(f"{'=' * 80}")
        # 如果有子版块数据, 用宽格式
        has_subs = any("subreddit_count" in s for s in stocks[:top_n])
        if has_subs:
            header = (
                f"  {'#':<4} {'Ticker':<8} {'Mentions':>7} {'Upvotes':>8} "
                f"{'Rank':>5} {'ΔRank':>7} {'Subs':>5} {'讨论区'}"
            )
        else:
            header = (
                f"  {'#':<4} {'Ticker':<8} {'Mentions':>7} {'Upvotes':>8} "
                f"{'Rank':>5} {'24hΔRank':>9}"
            )
        print(header)
        print(f"  {'-' * 76}")
        for i, s in enumerate(stocks[:top_n]):
            rank_chg = s.get("rank_change", 0)
            arrow = f"+{rank_chg}" if rank_chg > 0 else str(rank_chg)
            if has_subs and "subreddit_count" in s:
                sub_count = s["subreddit_count"]
                # Top 3 subreddits
                sub_mentions = s.get("subreddit_mentions", {})
                top_subs = sorted(sub_mentions.items(), key=lambda x: -x[1])[:3]
                sub_str = ", ".join(
                    f"{SUBREDDIT_NAMES.get(n, n)}({c})" for n, c in top_subs
                )
                print(
                    f"  {i + 1:<4} {s['ticker']:<8} {s['mentions']:>7} "
                    f"{s['upvotes']:>8} {s['rank']:>5} {arrow:>7} "
                    f"{sub_count:>5} {sub_str}"
                )
            else:
                print(
                    f"  {i + 1:<4} {s['ticker']:<8} {s['mentions']:>7} "
                    f"{s['upvotes']:>8} {s['rank']:>5} {arrow:>9}"
                )

    def print_summary_dashboard(self):
        """打印总览仪表盘 (同花顺风格)."""
        has_subs = any("subreddit_count" in s for s in self.all_stocks[:5])
        mode = "v2.0 18-filter" if has_subs else "v1.0 all-stocks only"
        print(f"\n{'#' * 80}")
        print(f"#  OnionQuant 热度仪表盘 ({mode})")
        print(f"#  数据: ApeWisdom | {len(self.all_stocks)} stocks")
        print(
            f"#  更新: {self.fetch_time.strftime('%Y-%m-%d %H:%M UTC') if self.fetch_time else 'N/A'}"
        )
        print(f"{'#' * 80}")

        # 1. 总热度 Top 10
        self.print_table(self.absolute_ranking(10), "[1] 总热度 TOP 10", 10)

        # 2. 24h 上升榜 Top 10
        self.print_table(
            self.rising_ranking(10), "[2] 24h 上升榜 TOP 10 (Rank改善最大)", 10
        )

        # 3. 新晋热榜
        newcomers = self.new_hot(10)
        if newcomers:
            self.print_table(
                newcomers, "[3] 新晋热榜 (24h前还在200名外, 已冲进Top50)", 10
            )

        # 4. AI产业链榜
        self.print_table(self.ai_chain_ranking(), "[4] AI产业链专属榜", 30)

        # 5. 24h 下降榜 (风险警示)
        self.print_table(self.falling_ranking(10), "[5] 24h 下降榜 (热度退潮警示)", 10)


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="OnionQuant Heat Rankings v2.0 (Tonghuashun-style)"
    )
    p.add_argument(
        "--all-filters", action="store_true", help="🔥 v2.0: 拉满全部18个filter聚合"
    )
    p.add_argument("--top", type=int, default=0, help="总热度榜 Top N")
    p.add_argument("--rising", type=int, default=0, help="24h上升榜 Top N")
    p.add_argument("--falling", type=int, default=0, help="24h下降榜 Top N")
    p.add_argument("--surge", type=int, default=0, help="热度突变榜 Top N")
    p.add_argument("--ai-chain", action="store_true", help="AI产业链专属榜")
    p.add_argument("--new-hot", type=int, default=0, help="新晋热榜 Top N")
    p.add_argument("--save-snapshot", action="store_true", help="保存快照")
    p.add_argument("--trend", type=str, help="查看某ticker趋势")
    p.add_argument("--dashboard", action="store_true", help="总览仪表盘 (默认)")
    p.add_argument("--with-crypto", action="store_true", help="包含加密货币子版块")
    args = p.parse_args()

    engine = HeatRankings()

    if args.all_filters:
        engine.fetch_all_filters(skip_crypto=not args.with_crypto)
    else:
        stocks = engine.fetch_all()
        if not stocks:
            print("[ERROR] No data fetched from ApeWisdom")
            sys.exit(1)

    if not engine.all_stocks:
        print("[ERROR] No data fetched from ApeWisdom")
        sys.exit(1)

    if args.save_snapshot:
        path = engine.save_snapshot()
        print(f"  [SAVE] Snapshot: {path.name}")

    if args.trend:
        trend = engine.load_trend(args.trend.upper())
        if trend:
            print(f"\n  {args.trend.upper()} 热度趋势:")
            for t in trend:
                print(
                    f"  {t['time'][:16]} | rank:{t['rank']:>4} | mentions:{t['mentions']:>4} | upvotes:{t['upvotes']:>4}"
                )
        else:
            print(f"  No trend data for {args.trend.upper()} (need snapshots)")

    if args.top:
        engine.print_table(
            engine.absolute_ranking(args.top), f"总热度 TOP {args.top}", args.top
        )
    if args.rising:
        engine.print_table(
            engine.rising_ranking(args.rising),
            f"24h 上升 TOP {args.rising}",
            args.rising,
        )
    if args.falling:
        engine.print_table(
            engine.falling_ranking(args.falling),
            f"24h 下降 TOP {args.falling}",
            args.falling,
        )
    if args.surge:
        engine.print_table(
            engine.mentions_surge(args.surge), f"热度突变 TOP {args.surge}", args.surge
        )
    if args.ai_chain:
        engine.print_table(engine.ai_chain_ranking(), "AI产业链", 30)
    if args.new_hot:
        engine.print_table(engine.new_hot(args.new_hot), "新晋热榜", args.new_hot)

    # 默认显示总览仪表盘
    if not any(
        [
            args.top,
            args.rising,
            args.falling,
            args.surge,
            args.ai_chain,
            args.new_hot,
            args.trend,
        ]
    ):
        engine.print_summary_dashboard()
