"""OHLCV standardization, quality checks, and ticker mapping."""

import logging
from typing import Dict

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

logger = logging.getLogger(__name__)

_OHLCV_SCHEMA = pa.DataFrameSchema(
    columns={
        "open": pa.Column(float, pa.Check.ge(0), nullable=True),
        "high": pa.Column(float, pa.Check.ge(0), nullable=True),
        "low": pa.Column(float, pa.Check.ge(0), nullable=True),
        "close": pa.Column(float, pa.Check.ge(0), nullable=True),
        "volume": pa.Column(float, pa.Check.ge(0), nullable=True),
    },
    checks=[
        pa.Check(
            lambda d: d["high"] >= d[["open", "close"]].max(axis=1),
            name="high_ge_open_close",
            ignore_na=True,
        ),
        pa.Check(
            lambda d: d["low"] <= d[["open", "close"]].min(axis=1),
            name="low_le_open_close",
            ignore_na=True,
        ),
    ],
)
# Standard OHLCV column mapping (source -> target)
OHLCV_COLUMN_MAP: Dict[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj close": "close",
    "adjusted close": "close",
    "volume": "volume",
}
# Chinese name -> ticker mapping
CN_TICKER_MAP: Dict[str, str] = {
    "苹果": "AAPL",
    "微软": "MSFT",
    "谷歌": "GOOGL",
    "亚马逊": "AMZN",
    "特斯拉": "TSLA",
    "英伟达": "NVDA",
    "脸书": "META",
    "元界": "META",
    "阿里巴巴": "BABA",
    "腾讯": "TCEHY",
    "百度": "BIDU",
    "京东": "JD",
    "拼多多": "PDD",
    "台积电": "TSM",
    "伯克希尔": "BRK.B",
    "摩根大通": "JPM",
    "维萨": "V",
}


def standardize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize OHLCV column names to lowercase."""
    df = df.copy()
    rename = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in OHLCV_COLUMN_MAP:
            rename[col] = OHLCV_COLUMN_MAP[cl]
    df = df.rename(columns=rename)
    logger.info("Renamed columns: %s", rename)
    return df


def check_data_quality(df: pd.DataFrame) -> Dict[str, object]:
    """Quality checks with Pandera schema validation (manual fallback)."""
    report: Dict[str, object] = {
        "rows": len(df),
        "columns": list(df.columns),
        "missing_summary": {},
        "outliers": {},
    }
    report["missing_summary"] = df.isnull().sum()[lambda s: s > 0].to_dict()
    for col in df.select_dtypes(include=["number"]).columns:
        mean, std = df[col].mean(), df[col].std()
        if pd.notna(std) and std:
            oo = df[abs(df[col] - mean) > 5 * std]
            if not oo.empty:
                report["outliers"][col] = {
                    "count": len(oo),
                    "threshold": f"{mean - 5 * std:.2f} ~ {mean + 5 * std:.2f}",
                }
    ohlc_cols = {"open", "high", "low", "close", "volume"} & set(df.columns)
    if ohlc_cols:
        try:
            _OHLCV_SCHEMA.validate(df, lazy=True)
            report["schema_valid"] = True
        except SchemaErrors as e:
            report["schema_valid"] = False
            report["schema_errors"] = str(e)
            logger.warning("Pandera validation failed: %s", e)
    else:
        report["schema_valid"] = "no_ohlc_columns"
    if report["missing_summary"]:
        logger.warning("Missing values found: %s", report["missing_summary"])
    if report["outliers"]:
        logger.warning("Outliers found: %s", list(report["outliers"].keys()))
    return report


def normalize_ticker(ticker: str) -> str:
    """Convert Chinese name or raw ticker to standard uppercase."""
    ticker = ticker.strip()
    if ticker in CN_TICKER_MAP:
        t = CN_TICKER_MAP[ticker]
        logger.info("Mapped '%s' -> '%s'", ticker, t)
        return t
    return ticker.upper()


def normalize_ticker_list(tickers: list) -> list:
    """Normalize a list of tickers (mixed Chinese names and symbols)."""
    return [normalize_ticker(t) for t in tickers]


def add_ticker_column(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Add a standardized ticker column to the DataFrame."""
    df = df.copy()
    df["ticker"] = normalize_ticker(ticker)
    return df
