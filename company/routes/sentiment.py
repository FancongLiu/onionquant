"""Sentiment routes — DXYZ + storage stock news & social sentiment."""

from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["sentiment"])

SENTIMENT_TICKERS = ["DXYZ", "MU", "WDC", "INTC", "AMD"]


def _yf_news(ticker: str, max_items: int = 10) -> list:
    """Fetch news from yfinance (no API key needed)."""
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        news = t.news[:max_items] if hasattr(t, "news") else []
        items = []
        for n in news:
            content = n.get("content", n)
            items.append(
                {
                    "title": content.get("title", content.get("summary", "")),
                    "source": content.get("source", content.get("provider", "")),
                    "published": content.get("pubDate", ""),
                    "url": content.get("canonicalUrl", content.get("url", "")),
                }
            )
        return items
    except Exception:
        return []


def _price_sentiment(ticker: str) -> dict:
    """Compute simple sentiment from recent price action."""
    try:
        import yfinance as yf
    except Exception:
        return {}
    try:
        hist = yf.Ticker(ticker).history("1mo")["Close"]
        if len(hist) < 10:
            return {}
        close = float(hist.iloc[-1])
        ma5 = float(hist.rolling(5).mean().iloc[-1])
        ma20 = float(hist.rolling(20).mean().iloc[-1]) if len(hist) >= 20 else ma5
        ret_5d = float(hist.pct_change(5).iloc[-1] * 100)
        ret_1m = float(hist.pct_change(len(hist) - 1).iloc[-1] * 100)
        vol_ratio = float(hist.iloc[-5:].std() / hist.std()) if hist.std() > 0 else 1.0
        trend = (
            "bullish"
            if close > ma5 > ma20
            else ("bearish" if close < ma5 < ma20 else "neutral")
        )
        return {
            "close": round(close, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ret_5d_pct": round(ret_5d, 2),
            "ret_1m_pct": round(ret_1m, 2),
            "vol_ratio": round(vol_ratio, 2),
            "trend": trend,
        }
    except Exception:
        return {}


@router.get("/api/sentiment/dxyz")
async def api_sentiment_dxyz():
    """DXYZ sentiment snapshot — news + price action."""
    price = _price_sentiment("DXYZ")
    news = _yf_news("DXYZ", 5)
    return {
        "ticker": "DXYZ",
        "updated": datetime.now().isoformat(),
        "price": price,
        "news": news,
        "news_count": len(news),
    }


@router.get("/api/sentiment/watchlist")
async def api_sentiment_watchlist():
    """All watchlist stocks sentiment summary."""
    results = {}
    for t in SENTIMENT_TICKERS:
        results[t] = {
            "price": _price_sentiment(t),
            "news_count": len(_yf_news(t, 3)),
        }
    return {
        "tickers": SENTIMENT_TICKERS,
        "updated": datetime.now().isoformat(),
        "data": results,
    }
