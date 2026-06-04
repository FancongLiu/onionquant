"""
alpha_vantage_fetcher.py — Alpha Vantage 新闻情绪数据采集
Fetch news sentiment data via Alpha Vantage NEWS_SENTIMENT endpoint.
"""

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.alphavantage.co/query"
MAX_RETRIES = 3
RETRY_DELAY = 5


def get_api_key() -> str:
    key = os.environ.get("ALPHA_VANTAGE_KEY")
    if not key:
        raise ValueError("Environment variable ALPHA_VANTAGE_KEY is not set")
    return key


def fetch_news_sentiment(
    tickers: str,
    api_key: str,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    limit: int = 50,
) -> Optional[pd.DataFrame]:
    """Fetch news sentiment for given tickers from Alpha Vantage."""
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": tickers,
        "apikey": api_key,
        "limit": limit,
    }
    if time_from:
        params["time_from"] = time_from
    if time_to:
        params["time_to"] = time_to

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "feed" not in data:
                logger.warning("Unexpected response: %s", list(data.keys()))
                return None

            records = []
            for item in data["feed"]:
                base = {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "time_published": item.get("time_published"),
                    "summary": item.get("summary"),
                    "overall_sentiment_score": item.get("overall_sentiment_score"),
                    "overall_sentiment_label": item.get("overall_sentiment_label"),
                }
                ticker_sents = item.get("ticker_sentiment", [])
                if ticker_sents:
                    for ts in ticker_sents:
                        rec = dict(base)
                        rec["ticker"] = ts.get("ticker")
                        rec["ticker_sentiment_score"] = ts.get("ticker_sentiment_score")
                        rec["ticker_sentiment_label"] = ts.get("ticker_sentiment_label")
                        records.append(rec)
                else:
                    records.append(base)

            df = pd.DataFrame(records)
            logger.info("Fetched %d news items for %s", len(df), tickers)
            return df

        except Exception as e:
            logger.warning("Attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    logger.error("Failed after %d attempts", MAX_RETRIES)
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch news sentiment from Alpha Vantage"
    )
    parser.add_argument(
        "--tickers", default="AAPL", help="Comma-separated tickers, e.g. AAPL,MSFT"
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max news items (max 1000)"
    )
    parser.add_argument("--time_from", help="Start time (YYYYMMDDTHHMM)")
    parser.add_argument("--time_to", help="End time (YYYYMMDDTHHMM)")
    parser.add_argument(
        "--output", default="news_sentiment.parquet", help="Output Parquet filename"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    api_key = get_api_key()
    logger.info("Fetching news sentiment for tickers: %s", args.tickers)
    df = fetch_news_sentiment(
        args.tickers, api_key, args.time_from, args.time_to, args.limit
    )
    if df is None or df.empty:
        logger.error("No data fetched.")
        return
    path = RAW_DIR / args.output
    df.to_parquet(path, index=False)
    logger.info("Saved %d rows to %s", len(df), path)


if __name__ == "__main__":
    main()
