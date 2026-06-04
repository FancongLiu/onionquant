"""
Shared state and helpers for server route modules.
Imported by route files and server.py.
"""
import asyncio
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

# SSE subscribers
subscribers: list[asyncio.Queue] = []


async def notify_all(event: str, data: dict):
    """Push event to all connected SSE clients."""
    payload = {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}
    dead = []
    for q in subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        subscribers.remove(q)


QUANT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "BAC", "DIS",
    "ADBE", "CRM", "NFLX", "AMD", "INTC", "QCOM", "TXN", "AVGO",
    "PYPL", "NKE", "COST", "MRK", "ABBV", "PEP", "KO", "TMO", "LLY",
]

QUANT_FACTOR_NAMES = [
    "mom_1d", "mom_5d", "mom_21d", "mom_63d", "mom_126d", "mom_252d",
    "rev_5d", "rev_10d", "rev_21d",
    "vol_5d", "vol_21d", "vol_63d",
    "turn_5d", "turn_21d",
    "size_log", "val_bp", "val_ep",
    "roe", "roa", "gross_margin",
    "corr_5d", "corr_21d",
    "beta_63d", "beta_252d",
    "rsi_14", "bb_width",
]

RISK_LIMITS = {
    "var95_daily": 0.03,
    "max_drawdown": 0.20,
    "sharpe_min": 0.0,
    "vol_max": 0.40,
}


def _try_or_fallback(live_fn, fallback: dict):
    """Try live_fn(), return fallback on any exception."""
    try:
        result = live_fn()
        if result is not None:
            return result
    except Exception:
        pass
    return fallback


# ─── WeChat config ──────────────────────────────────────

WECHAT_CORP_ID = os.getenv("WECHAT_CORP_ID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
WECHAT_AGENT_ID = os.getenv("WECHAT_AGENT_ID", "")
WECHAT_CONFIGURED = bool(WECHAT_CORP_ID and WECHAT_SECRET and WECHAT_AGENT_ID)

wechat_status = {
    "configured": WECHAT_CONFIGURED,
    "connected": False,
    "last_push": None,
    "push_count": 0,
    "push_errors": 0,
    "last_error": None,
}
