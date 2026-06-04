"""新闻情绪聚合（Alpha Vantage NEWS_SENTIMENT API）→ Parquet"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import pandas as pd
from quant_framework.data.fetchers.sentiment_utils import aggregate_sentiments

logger = logging.getLogger(__name__)
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "sentiment")
DEFAULT_TICKERS = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "GME"]


def fetch_news_sentiment(
    tickers: List[str], days: int = 7, api_key: Optional[str] = None
) -> pd.DataFrame:
    key = api_key or os.getenv("ALPHA_VANTAGE_KEY")
    if not key:
        logger.warning("未设置 ALPHA_VANTAGE_KEY，使用演示数据")
        return _demo_data(tickers, days)
    try:
        import requests

        resp = requests.get(
            "https://www.alphavantage.co/query",
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ",".join(tickers),
                "apikey": key,
                "limit": max(50, days * 10),
                "sort": "LATEST",
            },
            timeout=20,
        )
        resp.raise_for_status()
        feeds = resp.json().get("feed", [])
    except Exception as exc:
        logger.error("请求失败: %s", exc)
        return _demo_data(tickers, days)
    if not feeds:
        return _demo_data(tickers, days)
    records = []
    for article in feeds:
        ts = _parse_ts(article.get("time_published", ""))
        if ts and ts < datetime.now(timezone.utc) - timedelta(days=days):
            continue
        for ts_item in article.get("ticker_sentiment", []):
            records.append(
                {
                    "ticker": ts_item.get("ticker", ""),
                    "title": article.get("title", ""),
                    "summary": article.get("summary", ""),
                    "source": article.get("source", ""),
                    "published_at": ts,
                    "av_sentiment_score": _sf(ts_item.get("ticker_sentiment_score")),
                    "av_sentiment_label": ts_item.get("ticker_sentiment_label", ""),
                    "relevance_score": _sf(ts_item.get("relevance_score")),
                }
            )
    return pd.DataFrame(records) if records else _demo_data(tickers, days)


def _parse_ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _sf(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


_FALLBACK_HEADLINES = {
    "SPY": [
        "S&P 500 rallies on strong earnings reports",
        "Market volatility spikes amid Fed uncertainty",
        "Index funds continue to attract record inflows",
        "Broad market sell-off on recession fears",
        "S&P 500 reaches new all-time high",
        "Investors rotate into defensive sectors",
    ],
    "QQQ": [
        "Tech stocks surge on AI boom optimism",
        "Nasdaq falls as rate hike concerns weigh",
        "Cloud computing sector shows robust growth",
        "Semiconductor stocks lead market rally",
        "Big Tech earnings beat Wall Street expectations",
        "Tech sell-off on valuation concerns",
    ],
    "AAPL": [
        "Apple unveils new product line to strong reception",
        "iPhone sales exceed analyst forecasts",
        "Apple services revenue hits record high",
        "Supply chain concerns weigh on Apple stock",
    ],
    "TSLA": [
        "Tesla deliveries beat quarterly estimates",
        "EV competition intensifies in key markets",
        "Tesla announces new battery technology breakthrough",
        "Regulatory scrutiny on self-driving features",
    ],
    "NVDA": [
        "NVIDIA reports explosive data center revenue growth",
        "AI chip demand continues to outstrip supply",
        "NVIDIA unveils next-generation GPU architecture",
        "Analysts raise price targets on AI momentum",
    ],
    "GME": [
        "GameStop reports surprise quarterly profit",
        "Retail traders return to meme stocks",
        "GameStop transforms business model toward e-commerce",
        "Meme stock volatility attracts regulatory attention",
    ],
}


def _demo_data(tickers: List[str], days: int) -> pd.DataFrame:
    logger.info("无API key — 使用 FinBERT fallback 分析市场标题")
    from quant_framework.data.fetchers.sentiment_utils import score_text

    base = datetime.now(timezone.utc)
    records = []
    for sym in tickers[:6]:
        headlines = _FALLBACK_HEADLINES.get(sym, _FALLBACK_HEADLINES["SPY"])
        for d in range(min(days, len(headlines))):
            title = headlines[d % len(headlines)]
            scores = score_text(title)
            score = scores.get("positive", 0) - scores.get("negative", 0)
            label = "Bullish" if score > 0 else ("Bearish" if score < 0 else "Neutral")
            records.append(
                {
                    "ticker": sym,
                    "title": title,
                    "summary": f"[FinBERT fallback] pos={scores['positive']:.3f} neg={scores['negative']:.3f}",
                    "source": "FinBERT-fallback",
                    "published_at": base - timedelta(days=d),
                    "av_sentiment_score": round(score, 4),
                    "av_sentiment_label": label,
                    "relevance_score": 0.5,
                }
            )
    return pd.DataFrame(records)


def aggregate_by_ticker(df: pd.DataFrame, window_days: int = 5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["published_at"].dt.date)
    pos = df["av_sentiment_score"].clip(0, 1)
    neg = (-df["av_sentiment_score"]).clip(0, 1)
    df["positive"], df["negative"], df["neutral"] = pos, neg, 1 - pos - neg

    grouped = (
        df.groupby(["ticker", "date"])
        .apply(
            lambda g: pd.Series(
                aggregate_sentiments(
                    g[["positive", "negative", "neutral"]].to_dict("records"),
                    weights=g["relevance_score"].tolist(),
                )
            )
        )
        .reset_index()
    )
    grouped = grouped.sort_values(["ticker", "date"])
    for col in ["weighted_score", "positive_ratio", "negative_ratio"]:
        grouped[f"rolling_{col}"] = grouped.groupby("ticker")[col].transform(
            lambda s: s.rolling(window_days, min_periods=1).mean()
        )
    grouped["window_days"] = window_days
    return grouped


def save_parquet(df: pd.DataFrame, name: str):
    os.makedirs(RAW_DIR, exist_ok=True)
    p = os.path.join(RAW_DIR, f"{name}_{datetime.now().strftime('%Y%m%d')}.parquet")
    df.to_parquet(p, index=False)
    logger.info("已写入 %s (%d 行)", p, len(df))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--output", default="news_sentiment")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    raw = fetch_news_sentiment(tickers=args.tickers, days=args.days)
    agg = aggregate_by_ticker(raw, window_days=args.window)
    if agg.empty:
        return 1
    save_parquet(agg, args.output)
    print(agg.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
