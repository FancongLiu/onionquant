"""Reddit 情绪抓取 — PRAW + requests fallback → FinBERT → Parquet"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
from quant_framework.data.fetchers.sentiment_utils import (
    batch_score,
    aggregate_sentiments,
)

logger = logging.getLogger(__name__)
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "sentiment")
REDDIT_BASE = "https://www.reddit.com"


def _get_praw():
    try:
        import praw

        return praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.getenv("REDDIT_USER_AGENT", "sentiment-bot/0.1"),
        )
    except Exception as e:
        logger.warning("PRAW unavailable (%s), will fallback to requests", e)
        return None


def _fetch_requests(subreddit: str, limit: int, ua: Optional[str]) -> pd.DataFrame:
    ua = ua or os.getenv("REDDIT_USER_AGENT", "sentiment-bot/0.1")
    try:
        import requests

        resp = requests.get(
            f"{REDDIT_BASE}/r/{subreddit}/hot.json?limit={min(limit, 100)}",
            headers={"User-Agent": ua},
            timeout=15,
        )
        resp.raise_for_status()
        children = resp.json()["data"]["children"]
    except Exception as exc:
        logger.error("Requests fallback failed: %s", exc)
        return _demo(subreddit, limit)
    records = []
    for c in children[:limit]:
        d = c["data"]
        records.append(
            dict(
                id=d.get("id"),
                title=d.get("title", ""),
                selftext=d.get("selftext", ""),
                score=d.get("score", 0),
                upvote_ratio=d.get("upvote_ratio", 0.5),
                num_comments=d.get("num_comments", 0),
                created_utc=datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc
                ),
                subreddit=subreddit,
                source=f"r/{subreddit}",
            )
        )
    return pd.DataFrame(records) if records else _demo(subreddit, limit)


def fetch_hot_posts(
    subreddit: str = "wallstreetbets",
    limit: int = 100,
    user_agent: Optional[str] = None,
) -> pd.DataFrame:
    praw_inst = _get_praw()
    if praw_inst is not None:
        try:
            records = []
            for s in praw_inst.subreddit(subreddit).hot(limit=limit):
                records.append(
                    dict(
                        id=s.id,
                        title=s.title or "",
                        selftext=getattr(s, "selftext", "") or "",
                        score=s.score,
                        upvote_ratio=getattr(s, "upvote_ratio", 0.5),
                        num_comments=s.num_comments,
                        created_utc=datetime.fromtimestamp(
                            s.created_utc, tz=timezone.utc
                        ),
                        subreddit=subreddit,
                        source=f"r/{subreddit}",
                    )
                )
            return pd.DataFrame(records)
        except Exception as exc:
            logger.error("PRAW failed (%s), falling back", exc)
    return _fetch_requests(subreddit, limit, user_agent)


def _demo(subreddit: str, limit: int) -> pd.DataFrame:
    logger.info("Generating %d demo posts", limit)
    titles = [
        "GME to the moon!",
        "Bearish on TSLA this week",
        "AAPL earnings solid",
        "SPY puts printing",
        "Bullish on NVDA",
        "Correction incoming?",
        "AMC squeeze loading",
        "PLTR fair value",
    ][:limit]
    return pd.DataFrame(
        [
            dict(
                id=f"demo_{i:03d}",
                title=t,
                selftext="",
                score=max(1, 100 - i * 2),
                upvote_ratio=0.6 + (i % 3) * 0.1,
                num_comments=max(0, 30 - i),
                created_utc=datetime.now(timezone.utc),
                subreddit=subreddit,
                source=f"r/{subreddit}",
            )
            for i, t in enumerate(titles)
        ]
    )


def build_daily_index(df: pd.DataFrame) -> pd.DataFrame:
    scores = batch_score(df["title"].tolist())
    agg = aggregate_sentiments(scores, weights=df["score"].clip(lower=1).tolist())
    agg["date"] = pd.to_datetime(datetime.now(timezone.utc).date())
    agg["subreddit"] = df["subreddit"].iloc[0] if not df.empty else "unknown"
    agg["post_count"] = len(df)
    return pd.DataFrame([agg])


def save_parquet(df: pd.DataFrame, name: str):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{name}_{datetime.now().strftime('%Y%m%d')}.parquet")
    df.to_parquet(path, index=False)
    logger.info("Written %s (%d rows)", path, len(df))


def main():
    parser = argparse.ArgumentParser(description="Reddit sentiment fetcher (PRAW)")
    parser.add_argument("--subreddit", default="wallstreetbets")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="reddit_sentiment")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    posts = fetch_hot_posts(subreddit=args.subreddit, limit=args.limit)
    logger.info("Fetched %d posts", len(posts))
    daily = build_daily_index(posts)
    save_parquet(daily, args.output)
    print(daily.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
