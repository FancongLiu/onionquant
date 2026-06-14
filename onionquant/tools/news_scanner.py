#!/usr/bin/env python3
"""
news_scanner.py — 多源免费新闻热度扫描器 (零 API Key, 零注册)

数据源 (全部免费, 免注册):
  1. Finviz — 美股新闻聚合 (95+条/ticker, 20+来源: MarketWatch/DigiTimes/Barrons/Reuters等)
  2. Google News RSS — 全球新闻搜索 (10条/ticker)
  3. Yahoo Finance — 财经新闻+分析师评级

情绪分析: NLTK VADER (专为社交媒体/财经文本调优, 免费, 无需GPU)

Usage:
    python onionquant/tools/news_scanner.py --ticker NVDA
    python onionquant/tools/news_scanner.py --watchlist 10
    python onionquant/tools/news_scanner.py --ticker MU --sentiment
"""

import re
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# AI 产业链 ticker
AI_CHAIN_TICKERS = [
    "LITE",
    "COHR",
    "AAOI",
    "AVGO",
    "MRVL",
    "NVDA",
    "AMD",
    "INTC",
    "TSM",
    "FN",
    "MU",
    "SNDK",
    "RKLB",
    "ASTS",
    "LUNR",
    "RDW",
    "ANET",
    "CIEN",
]

# 催化剂关键词 (加权)
CATALYST_KEYWORDS = [
    ("earnings", 3.0),
    ("beat", 2.0),
    ("miss", -2.0),
    ("guidance", 2.0),
    ("upgrade", 2.5),
    ("downgrade", -2.5),
    ("buyback", 1.5),
    ("dividend", 0.5),
    ("IPO", 2.0),
    ("merger", 3.0),
    ("acquisition", 2.5),
    ("FDA", 3.0),
    ("approval", 2.5),
    ("contract", 2.0),
    ("partnership", 2.0),
    ("strike", -1.5),
    ("lawsuit", -2.0),
    ("investigation", -2.5),
    ("layoff", -1.5),
    ("bankruptcy", -4.0),
    ("record", 2.0),
    ("all-time high", 2.0),
    ("selloff", -1.5),
    ("rout", -2.0),
    ("plunge", -2.0),
    ("surge", 2.0),
    ("jump", 1.5),
    ("rally", 1.5),
    ("AI", 1.0),
    ("NVIDIA", 1.0),
    ("GPU", 1.0),
    ("CPO", 1.5),
    ("optical", 1.0),
    ("HBM", 1.0),
    ("packaging", 1.0),
]

# NLTK VADER 延迟加载
_nltk_ready = False


def _ensure_nltk():
    global _nltk_ready
    if _nltk_ready:
        return True
    try:
        import nltk

        nltk.data.path.append(str(PROJECT_ROOT / ".venv" / "nltk_data"))
        from nltk.sentiment import SentimentIntensityAnalyzer

        SentimentIntensityAnalyzer()  # 触发下载如需要
        _nltk_ready = True
        return True
    except Exception:
        return False


class NewsScanner:
    """多源免费新闻扫描器."""

    def __init__(self):
        self.last_request = None

    def _rate_limit(self, delay: float = 1.5):
        if self.last_request:
            elapsed = (datetime.now() - self.last_request).total_seconds()
            if elapsed < delay:
                time.sleep(delay - elapsed)
        self.last_request = datetime.now()

    def _fetch(self, url: str, timeout: int = 15) -> str:
        self._rate_limit()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        try:
            return (
                urllib.request.urlopen(req, timeout=timeout)
                .read()
                .decode("utf-8", errors="replace")
            )
        except Exception:
            return ""

    # ─── Finviz ───────────────────────────────────────
    def fetch_finviz_news(self, ticker: str) -> list[dict]:
        """从 Finviz 抓取新闻标题 (免费, 免登录, 95+条/ticker).

        Finviz 聚合 20+ 来源: MarketWatch, DigiTimes, Barrons, Reuters,
        Yahoo Finance, Bloomberg, Stocktwits, GuruFocus, WSJ 等.
        """
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        html = self._fetch(url)
        if not html:
            return []

        news = []
        # Finviz 新闻在 <table class="fullview-news-outer"> 中
        # 每行格式: <tr><td width="130">{date}</td><td><a href="{url}" target="_blank">{title}</a><span>{source}</span></td></tr>

        # 用正则提取新闻行
        pattern = re.compile(
            r'<td[^>]*width="130"[^>]*>(.*?)</td>\s*'
            r'<td[^>]*>.*?href="(.*?)"[^>]*>(.*?)</a>.*?<span[^>]*>(.*?)</span>',
            re.DOTALL,
        )

        for match in pattern.finditer(html):
            date_str = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            link = match.group(2).strip()
            title = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            source = re.sub(r"<[^>]+>", "", match.group(4)).strip()

            if title and len(title) > 10:  # 过滤太短的
                news.append(
                    {
                        "title": title,
                        "source": source,
                        "date": date_str,
                        "link": link,
                    }
                )

        return news

    # ─── Google News RSS ──────────────────────────────
    def fetch_google_news(self, ticker: str) -> list[dict]:
        """Google News RSS 搜索 (免费, 免注册)."""
        url = (
            f"https://news.google.com/rss/search?"
            f"q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
        )
        xml = self._fetch(url)
        if not xml:
            return []

        news = []
        # 简易 RSS 解析 (避免依赖 feedparser)
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        title_pat = re.compile(r"<title>(.*?)</title>")
        pubdate_pat = re.compile(r"<pubDate>(.*?)</pubDate>")
        source_pat = re.compile(r"<source[^>]*>(.*?)</source>")

        for item_match in item_pattern.finditer(xml):
            item = item_match.group(1)
            title_m = title_pat.search(item)
            pubdate_m = pubdate_pat.search(item)
            source_m = source_pat.search(item)

            if title_m:
                title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                # 去掉末尾 " - SourceName"
                title = re.sub(r"\s*-\s*\w+$", "", title)
                news.append(
                    {
                        "title": title,
                        "source": source_m.group(1) if source_m else "Google News",
                        "date": pubdate_m.group(1) if pubdate_m else "",
                        "link": "",
                    }
                )

        return news

    # ─── 情绪分析 ─────────────────────────────────────
    def analyze_sentiment(self, headlines: list[str]) -> dict:
        """VADER 情绪分析 (免费, 无需API Key).

        专为社交媒体/财经文本调优.
        若 VADER 不可用 → 回退到关键词计数.
        """
        if _ensure_nltk():
            return self._vader_sentiment(headlines)
        else:
            return self._keyword_sentiment(headlines)

    def _vader_sentiment(self, headlines: list[str]) -> dict:
        from nltk.sentiment import SentimentIntensityAnalyzer

        sia = SentimentIntensityAnalyzer()

        scores = []
        pos_count = neg_count = neu_count = 0
        for h in headlines:
            s = sia.polarity_scores(h)
            scores.append(s["compound"])
            if s["compound"] >= 0.05:
                pos_count += 1
            elif s["compound"] <= -0.05:
                neg_count += 1
            else:
                neu_count += 1

        avg = sum(scores) / len(scores) if scores else 0
        return {
            "avg_compound": round(avg, 3),
            "positive_pct": round(pos_count / len(headlines) * 100, 1)
            if headlines
            else 0,
            "negative_pct": round(neg_count / len(headlines) * 100, 1)
            if headlines
            else 0,
            "neutral_pct": round(neu_count / len(headlines) * 100, 1)
            if headlines
            else 0,
            "sentiment_label": "Bullish"
            if avg > 0.1
            else "Bearish"
            if avg < -0.1
            else "Neutral",
            "total_headlines": len(headlines),
        }

    def _keyword_sentiment(self, headlines: list[str]) -> dict:
        """关键词加权情绪 (VADER 的回退方案)."""
        total_score = 0
        for h in headlines:
            lower = h.lower()
            for kw, weight in CATALYST_KEYWORDS:
                if kw.lower() in lower:
                    total_score += weight

        avg = total_score / len(headlines) if headlines else 0
        return {
            "avg_compound": round(avg, 3),
            "positive_pct": 0,
            "negative_pct": 0,
            "neutral_pct": 100,
            "sentiment_label": "Bullish"
            if avg > 0.5
            else "Bearish"
            if avg < -0.5
            else "Neutral",
            "total_headlines": len(headlines),
            "method": "keyword_fallback",
        }

    # ─── 催化剂检测 ───────────────────────────────────
    def detect_catalysts(self, headlines: list[str]) -> list[dict]:
        """从新闻标题中检测催化剂事件."""
        detected = []
        for h in headlines:
            lower = h.lower()
            for kw, weight in CATALYST_KEYWORDS:
                if kw.lower() in lower and abs(weight) >= 2.0:
                    detected.append(
                        {
                            "keyword": kw,
                            "weight": weight,
                            "headline": h[:150],
                        }
                    )
                    break  # 每条标题只记最重要的关键词
        return detected

    # ─── 综合扫描 ─────────────────────────────────────
    def scan_ticker(self, ticker: str) -> dict:
        """对单个 ticker 执行多源新闻扫描."""
        # Finviz 新闻 (主力)
        finviz_news = self.fetch_finviz_news(ticker)

        # Google News (补充)
        google_news = self.fetch_google_news(ticker)

        all_headlines = [n["title"] for n in finviz_news] + [
            n["title"] for n in google_news
        ]

        # 去重
        all_headlines = list(dict.fromkeys(all_headlines))

        sentiment = self.analyze_sentiment(all_headlines)
        catalysts = self.detect_catalysts(all_headlines)

        # 新闻热度: 新闻数量 + 来源多样性
        sources = set(n["source"] for n in finviz_news if n["source"])
        news_volume = len(all_headlines)
        if news_volume >= 50:
            buzz = "[HOT] 新闻极热"
        elif news_volume >= 20:
            buzz = "[WARM] 新闻热"
        elif news_volume >= 8:
            buzz = "[MILD] 有关注"
        else:
            buzz = "[COLD] 新闻冷"

        return {
            "ticker": ticker,
            "timestamp": datetime.now(UTC).isoformat(),
            "news_count": news_volume,
            "finviz_count": len(finviz_news),
            "google_count": len(google_news),
            "sources_count": len(sources),
            "sources": sorted(sources)[:15],
            "buzz_level": buzz,
            "sentiment": sentiment,
            "catalysts": catalysts,
            "top_headlines": [n["title"] for n in (finviz_news + google_news)[:10]],
        }

    def scan_watchlist(
        self, tickers: list[str] | None = None, max_items: int = 20
    ) -> list[dict]:
        """批量扫描关注列表, 按新闻热度排序."""
        if tickers is None:
            tickers = AI_CHAIN_TICKERS

        print(f"\n  [>] News scan: {len(tickers)} tickers (Finviz + Google News)...")
        results = []
        for i, ticker in enumerate(tickers[:max_items]):
            r = self.scan_ticker(ticker)
            if r["news_count"] > 0:
                results.append(r)
            if (i + 1) % 5 == 0:
                print(f"    ... {i + 1}/{min(len(tickers), max_items)}")

        results.sort(key=lambda x: x["news_count"], reverse=True)
        return results

    def get_trending_by_news(
        self, tickers: list[str] | None = None, top_n: int = 10
    ) -> list[dict]:
        """快速获取新闻最多的 N 只股票."""
        if tickers is None:
            tickers = AI_CHAIN_TICKERS
        all_results = self.scan_watchlist(tickers)
        return all_results[:top_n]


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant Multi-Source News Scanner")
    p.add_argument("--ticker", type=str, help="扫描单个 ticker")
    p.add_argument(
        "--watchlist",
        type=int,
        default=0,
        metavar="N",
        help="扫描 AI 产业链关注列表, 显示前 N 个",
    )
    p.add_argument("--sentiment", action="store_true", help="显示情绪分析详情")
    p.add_argument("--catalysts", action="store_true", help="显示催化剂检测详情")
    args = p.parse_args()

    scanner = NewsScanner()

    if args.ticker:
        result = scanner.scan_ticker(args.ticker.upper())
        print(f"\n{'=' * 55}")
        print(f"  News Scanner: ${args.ticker.upper()}")
        print("  数据源: Finviz + Google News RSS (全部免费)")
        print(f"{'=' * 55}")
        print(
            f"  新闻总数: {result['news_count']} "
            f"(Finviz:{result['finviz_count']} + Google:{result['google_count']})"
        )
        print(f"  来源数量: {result['sources_count']}")
        print(f"  热度: {result['buzz_level']}")
        print(
            f"  情绪: {result['sentiment']['sentiment_label']} "
            f"(compound:{result['sentiment']['avg_compound']})"
        )
        print("\n  [=] 头条新闻:")
        for h in result["top_headlines"][:10]:
            print(f"  - {h[:120]}")

        if args.catalysts and result["catalysts"]:
            print("\n  [!] 检测到催化剂:")
            for c in result["catalysts"][:8]:
                sign = "+" if c["weight"] > 0 else ""
                print(
                    f"  {sign}{c['weight']:.1f} [{c['keyword']}] {c['headline'][:100]}"
                )

        if args.sentiment:
            s = result["sentiment"]
            print("\n  [=] 情绪分布:")
            print(
                f"  Positive: {s['positive_pct']}%  |  "
                f"Negative: {s['negative_pct']}%  |  "
                f"Neutral: {s['neutral_pct']}%"
            )

    elif args.watchlist:
        trending = scanner.get_trending_by_news(top_n=args.watchlist)
        print(f"\n{'=' * 55}")
        print("  新闻热度排行 (AI产业链, Finviz+Google News)")
        print(f"{'=' * 55}")
        for i, r in enumerate(trending):
            print(
                f"\n  #{i + 1} {r['ticker']:<6} {r['buzz_level']:<16} "
                f"{r['news_count']:>3}条 ({r['sources_count']}来源)"
            )
            print(
                f"      情绪: {r['sentiment']['sentiment_label']:<8} "
                f"(compound:{r['sentiment']['avg_compound']:.3f})"
            )
            if r["catalysts"]:
                cats = ", ".join(c["keyword"] for c in r["catalysts"][:3])
                print(f"      催化剂: {cats}")
            if r["top_headlines"]:
                print(f"      {r['top_headlines'][0][:100]}")

    else:
        # 默认: 显示 NVDA 和 MU 作为示例
        for t in ["NVDA", "MU"]:
            result = scanner.scan_ticker(t)
            print(
                f"${t}: {result['news_count']}条新闻 | "
                f"情绪:{result['sentiment']['sentiment_label']} "
                f"({result['sentiment']['avg_compound']}) | {result['buzz_level']}"
            )
