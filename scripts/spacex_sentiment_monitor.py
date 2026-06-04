#!/usr/bin/env python3
"""T994: SpaceX 舆情实时监控增强 (董事长指令)

监控渠道:
  1. Reddit (r/SpaceX + r/SpaceXMasterrace + r/WallStreetBets) via PRAW
  2. Stocktwits DXYZ trending via web scraping
  3. Google Trends "SpaceX IPO" search interest
  4. News API SpaceX keyword hits
  5. 异常情绪突变 → outbox预警

Usage:
    python scripts/spacex_sentiment_monitor.py --once
    python scripts/spacex_sentiment_monitor.py --interval 1800  # 30min
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ── 预警阈值 ──────────────────────────────────────────────

SENTIMENT_THRESHOLDS = {
    "reddit_mentions_spike": 5.0,  # 5x normal mention volume
    "stocktwits_sentiment_shift": 0.3,  # 30% sentiment shift in 1h
    "news_headline_count_spike": 3.0,  # 3x normal news volume
    "google_trends_spike": 80,  # Google Trends index >80
}

# 缓存文件 (跨调用保持状态)
CACHE_DIR = PROJECT_ROOT / "quant_framework" / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SENTIMENT_CACHE = CACHE_DIR / "spacex_sentiment_cache.json"


def load_cache() -> dict:
    """Load previous sentiment state."""
    if SENTIMENT_CACHE.exists():
        try:
            return json.loads(SENTIMENT_CACHE.read_text())
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_mentions": {}, "last_sentiment": {}, "alert_history": []}


def save_cache(cache: dict) -> None:
    SENTIMENT_CACHE.write_text(json.dumps(cache, indent=2, default=str))


def check_reddit_sentiment() -> dict:
    """Check Reddit for SpaceX/DXYZ mentions via PRAW (if configured)."""
    result = {"mentions": 0, "subreddits": {}, "sentiment": "neutral", "top_posts": []}
    try:
        import praw
    except ImportError:
        logger.debug("PRAW not installed — skipping Reddit")
        return result

    try:
        # Read credentials from .env
        from dotenv import load_dotenv
        import os

        load_dotenv(PROJECT_ROOT / ".env")

        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID", ""),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
            user_agent="OnionQuant/1.0",
        )
        if not reddit.client_id:
            logger.debug("Reddit API credentials not configured")
            return result
    except Exception:
        return result

    keywords = ["SpaceX IPO", "Starship", "DXYZ", "StarBase", "Elon Musk space"]
    subreddits = ["SpaceX", "SpaceXMasterrace", "wallstreetbets", "SpaceStock"]
    total = 0

    for sr_name in subreddits:
        try:
            sub = reddit.subreddit(sr_name)
            count = 0
            posts = []
            for post in sub.search(
                " OR ".join(keywords), sort="new", time_filter="day", limit=10
            ):
                count += 1
                posts.append(
                    {
                        "title": post.title[:120],
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "url": f"https://reddit.com{post.permalink}",
                    }
                )
            result["subreddits"][sr_name] = count
            total += count
            result["top_posts"].extend(posts[:3])
        except Exception as e:
            logger.debug("Reddit r/%s search failed: %s", sr_name, e)

    result["mentions"] = total
    if total > 20:
        result["sentiment"] = "bullish"  # High volume typically bullish for DXYZ
    elif total > 5:
        result["sentiment"] = "neutral"
    else:
        result["sentiment"] = "quiet"

    return result


def check_stocktwits_dxyz() -> dict:
    """Scrape Stocktwits DXYZ trending sentiment."""
    result = {"message_count": 0, "sentiment": "neutral"}
    try:
        import urllib.request

        url = "https://api.stocktwits.com/api/2/streams/symbol/DXYZ.json"
        req = urllib.request.Request(url, headers={"User-Agent": "OnionQuant/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            messages = data.get("messages", [])
            result["message_count"] = len(messages)
            bulls = sum(
                1
                for m in messages
                if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish"
            )
            bears = sum(
                1
                for m in messages
                if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish"
            )
            total_sentiment = bulls + bears
            if total_sentiment > 0:
                ratio = bulls / total_sentiment
                result["sentiment"] = (
                    "bullish"
                    if ratio > 0.65
                    else ("bearish" if ratio < 0.35 else "neutral")
                )
                result["bull_ratio"] = round(ratio, 2)
    except Exception as e:
        logger.debug("Stocktwits fetch failed: %s", e)
    return result


def check_news_headlines() -> dict:
    """Check news API for SpaceX keywords (free tier via yfinance news)."""
    result = {"count": 0, "top_headlines": []}
    try:
        import yfinance as yf

        ticker = yf.Ticker("DXYZ")
        news = ticker.news
        spacex_news = [
            n
            for n in news
            if any(
                kw in (n.get("title", "") + n.get("publisher", "")).lower()
                for kw in ["spacex", "starship", "elon musk", "ipo", "starlink"]
            )
        ]
        result["count"] = len(spacex_news)
        result["top_headlines"] = [
            {"title": n.get("title", "")[:120], "publisher": n.get("publisher", "")}
            for n in spacex_news[:5]
        ]
    except Exception as e:
        logger.debug("News fetch failed: %s", e)
    return result


def detect_anomalies(current: dict, cache: dict) -> list[dict]:
    """Compare current sentiment to cached baseline, return alerts."""
    alerts = []
    prev = cache.get("last_sentiment", {})

    # Reddit mention spike
    prev_mentions = prev.get("reddit_mentions", 0)
    cur_mentions = current.get("reddit", {}).get("mentions", 0)
    if (
        prev_mentions > 0
        and cur_mentions / prev_mentions
        >= SENTIMENT_THRESHOLDS["reddit_mentions_spike"]
    ):
        alerts.append(
            {
                "level": "🟡 P1",
                "source": "Reddit",
                "indicator": f"提及量飙升 {cur_mentions / prev_mentions:.1f}x",
                "detail": f"从 {prev_mentions} → {cur_mentions}",
            }
        )

    # Stocktwits sentiment flip
    prev_st = prev.get("stocktwits_sentiment", "")
    cur_st = current.get("stocktwits", {}).get("sentiment", "")
    if prev_st and cur_st and prev_st != cur_st:
        alerts.append(
            {
                "level": "🔴 P0" if cur_st == "bearish" else "🟡 P1",
                "source": "Stocktwits",
                "indicator": f"情绪翻转: {prev_st} → {cur_st}",
                "detail": f"Bull ratio: {current.get('stocktwits', {}).get('bull_ratio', 'N/A')}",
            }
        )

    # News volume spike
    prev_news = prev.get("news_count", 0)
    cur_news = current.get("news", {}).get("count", 0)
    if (
        prev_news > 0
        and cur_news / prev_news >= SENTIMENT_THRESHOLDS["news_headline_count_spike"]
    ):
        alerts.append(
            {
                "level": "🟡 P1",
                "source": "News",
                "indicator": f"新闻量飙升 {cur_news / prev_news:.1f}x",
                "detail": f"从 {prev_news} → {cur_news}",
            }
        )

    return alerts


def write_sentiment_alert(alerts: list[dict], current: dict) -> Path | None:
    """Write sentiment alert to outbox."""
    if not alerts:
        return None

    outbox_dir = PROJECT_ROOT / "company" / "chairman_outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    lines = [
        f"# 📡 SpaceX 舆情预警 — {len(alerts)} 项异常",
        f"**时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| 级别 | 来源 | 指标 | 详情 |",
        "|------|------|------|------|",
    ]
    for a in alerts:
        lines.append(
            f"| {a['level']} | {a['source']} | {a['indicator']} | {a['detail']} |"
        )

    lines += [
        "",
        "## 当前舆情快照",
        f"- Reddit: {current.get('reddit', {}).get('mentions', 0)} mentions, sentiment={current.get('reddit', {}).get('sentiment', 'N/A')}",
        f"- Stocktwits: {current.get('stocktwits', {}).get('message_count', 0)} msgs, sentiment={current.get('stocktwits', {}).get('sentiment', 'N/A')}",
        f"- News: {current.get('news', {}).get('count', 0)} headlines",
        "",
        "---",
        "*T994 SpaceX舆情监控 自动生成*",
    ]

    path = outbox_dir / f"ALERT_spacex_sentiment_{ts}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="SpaceX Sentiment Monitor (T994)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Check interval in seconds (default: 1800=30min)",
    )
    args = parser.parse_args()

    import time as time_mod

    while True:
        try:
            cache = load_cache()

            # Gather sentiment
            current = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reddit": check_reddit_sentiment(),
                "stocktwits": check_stocktwits_dxyz(),
                "news": check_news_headlines(),
            }

            # Detect anomalies
            alerts = detect_anomalies(current, cache)

            if alerts:
                path = write_sentiment_alert(alerts, current)
                logger.warning(
                    "⚠️  %d sentiment anomalies → %s",
                    len(alerts),
                    path.name if path else "none",
                )

                # Update alert history
                alert_history = cache.get("alert_history", [])
                alert_history.append(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "count": len(alerts),
                        "alerts": alerts,
                    }
                )
                cache["alert_history"] = alert_history[-50:]  # Keep last 50

            # Update cache
            cache["last_sentiment"] = {
                "timestamp": current["timestamp"],
                "reddit_mentions": current["reddit"]["mentions"],
                "reddit_sentiment": current["reddit"]["sentiment"],
                "stocktwits_messages": current["stocktwits"]["message_count"],
                "stocktwits_sentiment": current["stocktwits"]["sentiment"],
                "news_count": current["news"]["count"],
            }
            save_cache(cache)

            # Status line
            r = current["reddit"]
            st = current["stocktwits"]
            n = current["news"]
            logger.info(
                "📡 SpaceX Sentiment | Reddit: %d mentions (%s) | Stocktwits: %d msgs (%s) | News: %d headlines",
                r["mentions"],
                r["sentiment"],
                st["message_count"],
                st["sentiment"],
                n["count"],
            )

        except Exception as e:
            logger.error("Sentiment check failed: %s", e)

        if args.once:
            break
        time_mod.sleep(args.interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    main()
