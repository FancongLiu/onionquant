#!/usr/bin/env python3
"""
twitter_scanner.py — X/Twitter 扫描器 (tweepy + X API v2 Bearer Token)

凭据来源: onionquant/tools/HypeFinder/.env (董事长 2026-05-25 注册的 X Free Tier)

X API Free Tier 限制:
  - search_recent_tweets: ~100 requests/month (非常有限!)
  - 每次请求最多返回 100 条推文
  - 策略: 只在 ApeWisdom 出现强信号时做定向验证, 不搞大范围扫描

Usage:
    python onionquant/tools/twitter_scanner.py --ticker NVDA
    python onionquant/tools/twitter_scanner.py --ticker MU --count 50
"""

import os
import time
from datetime import datetime
from pathlib import Path

import tweepy
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HYPEFINDER_DIR = PROJECT_ROOT / "company" / "tools" / "HypeFinder"

# 加载 HypeFinder 的 .env (含 Twitter 凭据)
load_dotenv(HYPEFINDER_DIR / ".env")

BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# AI 产业链 ticker
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

# ─── 金融圈 KOL 账号 (用于定向抓取专家观点) ───
TRACKED_KOLS = [
    "Dansc2603",  # Daniel Sereda (SA分析师, 光模块/CPO专家)
    "JohanRosenqvist",  # 前 Danske Bank, SIVEF 重要推手
    # 可扩展更多
]


class TwitterScanner:
    """X/Twitter 扫描器 — 定向验证, 非大范围扫描."""

    def __init__(self):
        self.client = None
        self.request_count = 0
        self.last_request_time = None
        self._init_client()

    def _init_client(self):
        if not BEARER_TOKEN:
            print("[ERROR] TWITTER_BEARER_TOKEN 未设置 — 检查 HypeFinder/.env")
            return
        try:
            self.client = tweepy.Client(bearer_token=BEARER_TOKEN)
            print("[OK] Twitter API client initialized (Bearer Token)")
        except Exception as e:
            print(f"[ERROR] Twitter client init failed: {e}")

    def _rate_limit_wait(self):
        """X API free tier 限速: 请求之间留间隔."""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < 2.0:  # 至少2秒间隔
                time.sleep(2.0 - elapsed)
        self.last_request_time = datetime.now()
        self.request_count += 1

    def search_ticker(
        self,
        ticker: str,
        max_results: int = 50,
        hours: int = 24,
    ) -> dict:
        """搜索 X 上关于某 ticker 的推文 ($TICKER 格式).

        Returns:
          {
            "ticker": str,
            "tweet_count": int,
            "total_likes": int, "total_retweets": int, "total_replies": int,
            "total_engagement": int,
            "top_tweets": list[dict],
            "kol_tweets": list[dict],   # 来自追踪的 KOL
            "buzz_level": str,
            "error": str | None,
          }
        """
        result = {
            "ticker": ticker,
            "tweet_count": 0,
            "total_likes": 0,
            "total_retweets": 0,
            "total_replies": 0,
            "total_engagement": 0,
            "top_tweets": [],
            "kol_tweets": [],
            "buzz_level": "❄️ 无数据",
            "error": None,
        }

        if not self.client:
            result["error"] = "Twitter client not initialized"
            return result

        self._rate_limit_wait()

        try:
            query = f"${ticker} -is:retweet lang:en"
            tweets = tweepy.Paginator(
                self.client.search_recent_tweets,
                query=query,
                max_results=min(100, max_results),
                tweet_fields=["created_at", "public_metrics", "author_id"],
                user_fields=["username"],
                expansions=["author_id"],
            ).flatten(limit=max_results)

            # Build author lookup map
            # Paginator doesn't return includes directly, we collect manually

            all_tweets = []
            for tweet in tweets:
                metrics = tweet.public_metrics or {}
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)
                replies = metrics.get("reply_count", 0)

                tweet_data = {
                    "id": str(tweet.id),
                    "text": tweet.text[:200],
                    "created_at": str(tweet.created_at) if tweet.created_at else "",
                    "author_id": str(tweet.author_id) if tweet.author_id else "",
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                    "engagement": likes + retweets * 2 + replies,  # 转推权重×2
                }
                all_tweets.append(tweet_data)

                result["total_likes"] += likes
                result["total_retweets"] += retweets
                result["total_replies"] += replies
                result["total_engagement"] += tweet_data["engagement"]

            result["tweet_count"] = len(all_tweets)

            # 排序: 按互动量
            all_tweets.sort(key=lambda x: x["engagement"], reverse=True)
            result["top_tweets"] = all_tweets[:10]

            # 识别 KOL 推文
            for t in all_tweets:
                if t["author_id"] in TRACKED_KOLS:
                    result["kol_tweets"].append(t)

            # 热度评级
            total = result["tweet_count"]
            if total >= 50:
                result["buzz_level"] = "🔥🔥🔥 X极热"
            elif total >= 20:
                result["buzz_level"] = "🔥🔥 X热"
            elif total >= 8:
                result["buzz_level"] = "🔥 X温"
            elif total >= 2:
                result["buzz_level"] = "⚪ 有讨论"
            else:
                result["buzz_level"] = "❄️ X上无人讨论"

        except tweepy.TooManyRequests:
            result["error"] = "X API rate limit exceeded"
        except tweepy.Unauthorized:
            result["error"] = "X API 认证失败 — Bearer Token 无效或过期"
        except Exception as e:
            result["error"] = str(e)

        return result

    def cross_validate(self, ticker: str, apewisdom_rank_change: int) -> dict:
        """交叉验证: ApeWisdom 信号 + X 平台确认.

        只在 ApeWisdom 信号较强 (Δrank > 3) 时调用, 省 API 额度.
        """
        x_data = self.search_ticker(ticker, max_results=30)

        confirmed = False
        if x_data["tweet_count"] >= 5 and abs(apewisdom_rank_change) >= 3:
            confirmed = True
            rec = "✅ X平台确认 — 双源验证通过, 信号可靠"
        elif x_data["tweet_count"] >= 5:
            confirmed = True
            rec = "👀 X平台有讨论但ApeWisdom未动 — 可能是X端早期信号"
        elif abs(apewisdom_rank_change) >= 3:
            confirmed = False
            rec = "⚠️ ApeWisdom有信号但X平台未确认 — 可能仅为Reddit内部讨论"
        else:
            rec = "— 双平台均无显著信号"

        return {
            "ticker": ticker,
            "apewisdom_rank_change": apewisdom_rank_change,
            "x_tweet_count": x_data["tweet_count"],
            "x_engagement": x_data["total_engagement"],
            "x_buzz": x_data["buzz_level"],
            "x_has_kol": len(x_data["kol_tweets"]) > 0,
            "x_top_tweet": x_data["top_tweets"][0]["text"][:120]
            if x_data["top_tweets"]
            else "",
            "x_error": x_data["error"],
            "confirmed": confirmed,
            "recommendation": rec,
        }

    def search_kol_tweets(self, kol_username: str, max_results: int = 20) -> list[dict]:
        """搜索特定 KOL 最近的推文 (用于定向抓取专家观点)."""
        if not self.client:
            return []

        self._rate_limit_wait()

        try:
            tweets = tweepy.Paginator(
                self.client.search_recent_tweets,
                query=f"from:{kol_username} -is:retweet",
                max_results=min(100, max_results),
                tweet_fields=["created_at", "public_metrics"],
            ).flatten(limit=max_results)

            results = []
            for tweet in tweets:
                metrics = tweet.public_metrics or {}
                results.append(
                    {
                        "id": str(tweet.id),
                        "text": tweet.text[:200],
                        "created_at": str(tweet.created_at) if tweet.created_at else "",
                        "likes": metrics.get("like_count", 0),
                        "retweets": metrics.get("retweet_count", 0),
                    }
                )
            return results

        except Exception as e:
            print(f"  [ERROR] KOL search '{kol_username}': {e}")
            return []

    def get_request_stats(self) -> dict:
        return {
            "requests_made": self.request_count,
            "last_request": str(self.last_request_time)
            if self.last_request_time
            else "none",
        }


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="OnionQuant X/Twitter Scanner")
    p.add_argument("--ticker", type=str, required=True, help="搜索ticker (如 NVDA, MU)")
    p.add_argument("--count", type=int, default=50, help="最大推文数")
    p.add_argument(
        "--cross-validate",
        type=int,
        default=0,
        help="ApeWisdom rank_change 值 (用于交叉验证)",
    )
    p.add_argument("--kol", type=str, help="搜索特定 KOL 的推文")
    args = p.parse_args()

    scanner = TwitterScanner()

    if args.kol:
        tweets = scanner.search_kol_tweets(args.kol)
        print(f"\n  @{args.kol} 最近推文 ({len(tweets)}条):")
        for t in tweets[:10]:
            print(f"  [{t['likes']}❤️ {t['retweets']}🔁] {t['text'][:120]}")

    elif args.cross_validate:
        result = scanner.cross_validate(args.ticker.upper(), args.cross_validate)
        print(f"\n{'=' * 55}")
        print(f"  交叉验证: {result['ticker']}")
        print(f"{'=' * 55}")
        print(f"  X推文: {result['x_tweet_count']} | 互动: {result['x_engagement']}")
        print(f"  X热度: {result['x_buzz']}")
        print(f"  确认: {result['confirmed']}")
        print(f"  建议: {result['recommendation']}")
        if result["x_error"]:
            print(f"  ⚠️ 错误: {result['x_error']}")

    else:
        result = scanner.search_ticker(args.ticker.upper(), max_results=args.count)
        print(f"\n{'=' * 55}")
        print(f"  X/Twitter 扫描: ${args.ticker.upper()}")
        print(f"{'=' * 55}")
        print(f"  推文数: {result['tweet_count']}")
        print(
            f"  总互动: {result['total_engagement']} "
            f"(❤️{result['total_likes']} 🔁{result['total_retweets']} 💬{result['total_replies']})"
        )
        print(f"  热度: {result['buzz_level']}")
        if result["kol_tweets"]:
            print(f"  🎯 KOL 覆盖: {len(result['kol_tweets'])} 条")
        if result["error"]:
            print(f"  ⚠️ 错误: {result['error']}")
        if result["top_tweets"]:
            print("\n  🔥 最热推文:")
            for t in result["top_tweets"][:5]:
                print(f"  [{t['engagement']}] {t['text'][:130]}")
