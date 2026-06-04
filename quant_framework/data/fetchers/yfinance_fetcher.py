"""Fetch US stock daily OHLCV data. Primary: OpenBB (pip install openbb). Fallback: yfinance."""
import argparse
import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
MAX_RETRIES, RETRY_DELAY = 3, 5


def _fetch_via_openbb(ticker: str, start: str, end: Optional[str]) -> Optional[pd.DataFrame]:
    """Fetch via OpenBB Platform SDK, trying multiple providers in order."""
    try:
        from openbb import obb
    except ImportError:
        logger.warning("OpenBB not installed. Install: pip install openbb (or pip install \"openbb[all]\")")
        return None

    # fmp has a free tier; polygon/alpha_vantage free w/ API key; None = user default
    for attempt in range(1, MAX_RETRIES + 1):
        for prov in ("fmp", "polygon", "alpha_vantage", None):
            try:
                kwargs = dict(symbol=ticker, start_date=start, end_date=end)
                if prov:
                    kwargs["provider"] = prov
                data = obb.equity.price.historical(**kwargs).to_dataframe()
                if data is None or data.empty:
                    continue
                data.columns = [c.lower() for c in data.columns]
                if "date" not in data.columns:
                    data = data.reset_index()
                data["date"] = pd.to_datetime(data["date"]).dt.date
                data["ticker"] = ticker.upper()
                keep = ["date", "open", "high", "low", "close", "volume", "ticker"]
                data = data[[c for c in keep if c in data.columns]]
                logger.info("OpenBB [%s] %s: %d rows", prov or "default", ticker, len(data))
                return data
            except Exception:
                continue
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)
    logger.warning("OpenBB exhausted for %s", ticker)
    return None


def _fetch_via_yfinance(ticker: str, start: str, end: Optional[str]) -> Optional[pd.DataFrame]:
    """Fallback: yfinance (legacy)."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed (needed as fallback)")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df.empty:
                logger.warning("yfinance: no data for %s", ticker)
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]
            df.columns = [c.lower() for c in df.columns]
            df["ticker"] = ticker.upper()
            df = df.reset_index()
            date_col = next(c for c in df.columns if "date" in c.lower() or c == "index")
            df = df.rename(columns={date_col: "date"})
            df["date"] = pd.to_datetime(df["date"]).dt.date
            logger.info("yfinance %s: %d rows", ticker, len(df))
            return df
        except Exception as exc:
            logger.warning("yfinance attempt %d/%d for %s: %s", attempt, MAX_RETRIES, ticker, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    logger.error("yfinance exhausted for %s", ticker)
    return None


def fetch_single(ticker: str, start: str, end: Optional[str], source: str = "auto") -> Optional[pd.DataFrame]:
    """Dispatch single-ticker fetch by source strategy."""
    if source == "yfinance":
        return _fetch_via_yfinance(ticker, start, end)
    data = _fetch_via_openbb(ticker, start, end)
    if data is None and source == "auto":
        logger.info("OpenBB unavailable, falling back to yfinance for %s", ticker)
        data = _fetch_via_yfinance(ticker, start, end)
    return data


def fetch_batch(tickers, start: str, end: Optional[str], source: str = "auto") -> pd.DataFrame:
    """Fetch multiple tickers and concatenate."""
    frames = [fetch_single(t.strip(), start, end, source) for t in tickers if t.strip()]
    frames = [df for df in frames if df is not None]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    logger.info("Total rows: %d", len(result))
    return result


def save_parquet(df: pd.DataFrame, filename: str):
    path = RAW_DIR / filename
    df.to_parquet(path, index=False)
    logger.info("Saved to %s", path)


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch US stock daily OHLCV (OpenBB + yfinance fallback)")
    parser.add_argument("--tickers", required=True, help="Comma-separated, e.g. AAPL,MSFT")
    parser.add_argument("--start", default="2020-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--output", default="us_stocks.parquet", help="Output Parquet filename")
    parser.add_argument("--source", default="auto", choices=["openbb", "yfinance", "auto"],
                        help="Data source: openbb, yfinance, auto (try openbb first)")
    return parser.parse_args()


def main():
    args = parse_args()
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    logger.info("Starting fetch: %s | source=%s", tickers, args.source)
    df = fetch_batch(tickers, args.start, args.end, args.source)
    if df.empty:
        logger.error("No data fetched, exiting.")
        return
    save_parquet(df, args.output)
    logger.info("Done.")


if __name__ == "__main__":
    main()
