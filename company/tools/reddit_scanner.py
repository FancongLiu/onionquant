#!/usr/bin/env python3
"""
reddit_scanner.py — Reddit 实时扫描器 (公开 JSON 端点, 无需 API Key!)

数据源:
  - Reddit 公开 .json 端点: reddit.com/r/{sub}/search.json (无需注册/无需API Key!)
  - ApeWisdom: 每小时热度排行 (作为补充)
  - PullPush.io: 历史存档 (回退方案)

方法来源: TickerPulse AI v3.0 (GitHub, MIT License)
速率限制: Reddit 公开端点 ~90 requests/10 min

Usage:
    python company/tools/reddit_scanner.py --ticker NVDA
    python company/tools/reddit_scanner.py --watchlist
    python company/tools/reddit_scanner.py --cross-validate NVDA 5
"""

import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "company" / "sentiment_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── 追踪的子版块 ───
TRACKED_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "pennystocks",
    "StockMarket",
    "options",
    "thetagang",
    "Daytrading",
]

# ─── AI 产业链 ticker ───
AI_CHAIN_TICKERS = [
    "LITE",
    "COHR",
    "SIVEF",
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

# ─── 关键词情绪 ───
_POSITIVE_KW = {
    "bullish",
    "moon",
    "rocket",
    "buy",
    "calls",
    "long",
    "squeeze",
    "undervalued",
    "breakout",
    "rally",
    "gain",
    "profit",
    "surge",
    "diamond hands",
    "hold",
    "yolo",
    "green",
    "tendies",
    "rip",
}
_NEGATIVE_KW = {
    "bearish",
    "puts",
    "short",
    "sell",
    "crash",
    "dump",
    "overvalued",
    "loss",
    "red",
    "bag",
    "bagholder",
    "drop",
    "tank",
    "plunge",
    "recession",
    "bankrupt",
    "fraud",
    "scam",
    "rug pull",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class _RateLimiter:
    """Reddit 公开端点速率限制: 90 requests / 600s."""

    def __init__(self, max_requests: int = 90, window_seconds: int = 600):
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def wait_if_needed(self):
        with self._lock:
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self._window]
            if len(self._timestamps) >= self._max:
                wait_time = self._window - (now - self._timestamps[0]) + 0.5
                if wait_time > 0:
                    print(f"  [RATE] Reddit rate limit, sleeping {wait_time:.0f}s...")
                    time.sleep(wait_time)
            self._timestamps.append(time.time())


_rate_limiter = _RateLimiter()


class RedditScanner:
    """Reddit 实时扫描器 — 公开 JSON, 无需 API Key."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def search_ticker(
        self,
        ticker: str,
        subreddits: list[str] | None = None,
        limit: int = 25,
        time_filter: str = "week",
    ) -> list[dict]:
        """搜索 Reddit 帖子 (公开 JSON, 无需认证).

        Args:
            ticker: 股票代码
            subreddits: 子版块列表 (默认: WSB + stocks + investing + ...)
            limit: 每个子版块最多返回数
            time_filter: hour/day/week/month/year/all
        """
        if subreddits is None:
            subreddits = TRACKED_SUBREDDITS

        all_posts = []
        for sub_name in subreddits:
            posts = self._search_subreddit(sub_name, ticker, limit, time_filter)
            all_posts.extend(posts)
            time.sleep(0.8)  # 子版块间间隔

        # 去重
        seen_ids = set()
        unique = []
        for p in all_posts:
            pid = p.get("id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                unique.append(p)

        unique.sort(
            key=lambda p: p.get("score", 0) + p.get("num_comments", 0), reverse=True
        )
        return unique

    def _search_subreddit(
        self,
        subreddit: str,
        ticker: str,
        limit: int,
        time_filter: str,
    ) -> list[dict]:
        """搜索单个子版块."""
        _rate_limiter.wait_if_needed()

        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": ticker,
            "sort": "new",
            "limit": limit,
            "restrict_sr": "on",
            "t": time_filter,
        }

        try:
            resp = self.session.get(url, params=params, timeout=15)
        except Exception as e:
            print(f"  [WARN] Reddit r/{subreddit} connection error: {e}")
            return []

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"  [RATE] Reddit 429 r/{subreddit}, retry after {retry_after}s")
            time.sleep(retry_after)
            _rate_limiter.wait_if_needed()
            try:
                resp = self.session.get(url, params=params, timeout=15)
            except Exception:
                return []

        if resp.status_code != 200:
            return []

        data = resp.json()
        children = data.get("data", {}).get("children", [])

        posts = []
        for child in children:
            post_data = child.get("data", {})
            title = post_data.get("title", "")
            selftext = post_data.get("selftext", "")

            # 验证 ticker 确实被提到
            combined = f"{title} {selftext}".upper()
            if not re.search(rf"\$?{re.escape(ticker)}\b", combined):
                continue

            # 关键词情绪
            full_text = f"{title} {selftext}".lower()
            pos = sum(1 for kw in _POSITIVE_KW if kw in full_text)
            neg = sum(1 for kw in _NEGATIVE_KW if kw in full_text)
            total_kw = pos + neg
            if total_kw > 0:
                sentiment_score = (pos - neg) / total_kw
            else:
                sentiment_score = 0.0
            sentiment_score = max(-1.0, min(1.0, sentiment_score))

            if sentiment_score > 0.2:
                sentiment_label = "positive"
            elif sentiment_score < -0.2:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"

            created_utc = post_data.get("created_utc", 0)
            created_str = (
                datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
                if created_utc
                else ""
            )

            posts.append(
                {
                    "id": post_data.get("id", ""),
                    "subreddit": subreddit,
                    "title": title,
                    "selftext": selftext[:300],
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "upvote_ratio": post_data.get("upvote_ratio", 0.5),
                    "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
                    "author": post_data.get("author", "[deleted]"),
                    "created_utc": created_utc,
                    "created_at": created_str,
                    "sentiment_score": round(sentiment_score, 3),
                    "sentiment_label": sentiment_label,
                }
            )

        return posts

    def count_mentions(
        self,
        ticker: str,
        subreddits: list[str] | None = None,
        time_filter: str = "week",
    ) -> dict:
        """统计 Reddit 提及量 (帖子+情绪)."""
        posts = self.search_ticker(
            ticker, subreddits, limit=25, time_filter=time_filter
        )
        total_score = sum(p.get("score", 0) for p in posts)
        total_comments = sum(p.get("num_comments", 0) for p in posts)
        sentiments = [p.get("sentiment_score", 0) for p in posts]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

        positive = sum(1 for p in posts if p.get("sentiment_label") == "positive")
        negative = sum(1 for p in posts if p.get("sentiment_label") == "negative")
        neutral = sum(1 for p in posts if p.get("sentiment_label") == "neutral")

        sub_counts = {}
        for p in posts:
            sub = p.get("subreddit", "")
            sub_counts[sub] = sub_counts.get(sub, 0) + 1

        if len(posts) >= 15:
            buzz = "[HOT] Reddit 极热"
        elif len(posts) >= 6:
            buzz = "[WARM] Reddit 热"
        elif len(posts) >= 2:
            buzz = "[MILD] 有讨论"
        else:
            buzz = "[COLD] Reddit 无人讨论"

        return {
            "ticker": ticker,
            "total_posts": len(posts),
            "total_score": total_score,
            "total_comments": total_comments,
            "avg_sentiment": round(avg_sentiment, 3),
            "positive_pct": round(positive / max(len(posts), 1) * 100, 1),
            "negative_pct": round(negative / max(len(posts), 1) * 100, 1),
            "buzz_level": buzz,
            "subreddit_breakdown": sub_counts,
            "top_posts": posts[:10],
        }

    def cross_validate(self, ticker: str, apewisdom_rank_change: int) -> dict:
        """交叉验证: ApeWisdom + Reddit 公开搜索."""
        data = self.count_mentions(ticker, time_filter="week")

        confirmed = False
        if abs(apewisdom_rank_change) >= 3 and data["total_posts"] >= 3:
            confirmed = True
            rec = "CONFIRMED: Reddit mentions confirm ApeWisdom signal"
        elif data["total_posts"] >= 5:
            confirmed = True
            rec = (
                "Reddit has discussion but ApeWisdom not yet picking up — early signal?"
            )
        elif abs(apewisdom_rank_change) >= 5 and data["total_posts"] < 3:
            confirmed = False
            rec = "ApeWisdom signal strong but Reddit sparse — may be noise"
        else:
            rec = "No significant signal on either platform"

        return {
            "ticker": ticker,
            "apewisdom_signal": apewisdom_rank_change,
            "reddit_posts": data["total_posts"],
            "reddit_score": data["total_score"],
            "reddit_sentiment": data["avg_sentiment"],
            "buzz_level": data["buzz_level"],
            "confirmed": confirmed,
            "recommendation": rec,
            "top_posts": data["top_posts"][:5],
        }

    def scan_watchlist(self, tickers: list[str] | None = None) -> list[dict]:
        """批量扫描 AI 产业链."""
        if tickers is None:
            tickers = AI_CHAIN_TICKERS

        print(
            f"\n  [>] Reddit scan: {len(tickers)} tickers (public JSON, no API key)..."
        )
        results = []
        for i, ticker in enumerate(tickers):
            data = self.count_mentions(ticker, time_filter="week")
            if data["total_posts"] > 0:
                results.append(data)
            if (i + 1) % 5 == 0:
                print(f"    ... {i + 1}/{len(tickers)}")
        results.sort(key=lambda x: x["total_posts"], reverse=True)
        return results


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant Reddit Scanner (Public JSON)")
    p.add_argument("--ticker", type=str, help="搜索单个 ticker")
    p.add_argument("--watchlist", action="store_true", help="扫描 AI 产业链")
    p.add_argument(
        "--cross-validate",
        type=str,
        metavar="TICKER",
        help="交叉验证 (ApeWisdom + Reddit)",
    )
    p.add_argument(
        "--apewisdom-delta", type=int, default=0, help="ApeWisdom rank_change 值"
    )
    p.add_argument("--subreddits", type=str, default="", help="指定子版块 (逗号分隔)")
    args = p.parse_args()

    scanner = RedditScanner()

    if args.ticker:
        sub_list = (
            [s.strip() for s in args.subreddits.split(",") if s.strip()]
            if args.subreddits
            else None
        )
        data = scanner.count_mentions(args.ticker.upper(), subreddits=sub_list)
        print(f"\n{'=' * 55}")
        print(f"  Reddit: ${args.ticker.upper()} (公开JSON, 无需API)")
        print(f"{'=' * 55}")
        print(
            f"  帖子: {data['total_posts']} | 总分: {data['total_score']} | "
            f"评论: {data['total_comments']}"
        )
        print(
            f"  情绪: {data['avg_sentiment']:.2f} "
            f"(+{data['positive_pct']}%/-{data['negative_pct']}%)"
        )
        print(f"  热度: {data['buzz_level']}")
        if data["top_posts"]:
            print("\n  [=] 最热帖子:")
            for post in data["top_posts"][:5]:
                flair = (
                    f" [{post['sentiment_label']}]"
                    if post["sentiment_label"] != "neutral"
                    else ""
                )
                print(
                    f"  [{post['score']}↑] r/{post['subreddit']}{flair} — {post['title'][:90]}"
                )

    elif args.cross_validate:
        ticker = args.cross_validate.upper()
        result = scanner.cross_validate(ticker, args.apewisdom_delta)
        print(
            f"  {ticker}: Reddit {result['reddit_posts']}帖 | "
            f"确认:{result['confirmed']} | {result['recommendation']}"
        )

    elif args.watchlist:
        hot = scanner.scan_watchlist()
        print(f"\n{'=' * 55}")
        print("  Reddit 热度排行 (AI产业链)")
        print(f"{'=' * 55}")
        for r in hot:
            if r["total_posts"] >= 2:
                print(
                    f"\n  {r['ticker']:<6} {r['buzz_level']:<16} "
                    f"{r['total_posts']:>2}帖 | sentiment:{r['avg_sentiment']:.2f}"
                )
                if r["top_posts"]:
                    print(f"         {r['top_posts'][0]['title'][:90]}")

    else:
        # 默认显示 WSB 热点
        for t in ["NVDA", "MU", "LITE"]:
            data = scanner.count_mentions(t)
            print(
                f"${t}: {data['total_posts']} posts | sentiment:{data['avg_sentiment']:.2f} | {data['buzz_level']}"
            )
