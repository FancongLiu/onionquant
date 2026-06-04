#!/usr/bin/env python3
"""
微信出站同步推送 — 轮询 chairman_outbox/ 通过 requests 推送到企业微信。
替代 wechat_bot.py (aiohttp在Windows上不稳定)。
由 cron 每 5 分钟调用一次。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BEIJING_TZ = timezone(timedelta(hours=8))
CTX_STATE = (
    PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"
)


def _ts() -> str:
    """Beijing time timestamp YYYY-MM-DD HH:MM:SS"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _dashboard_url() -> str:
    """Read tunnel URL from context_state.json."""
    try:
        data = json.loads(CTX_STATE.read_text(encoding="utf-8"))
        return data.get("key_context", {}).get("tunnel_url", "")
    except Exception:
        return ""


CORP_ID = os.getenv("WECHAT_CORP_ID", "")
AGENT_ID = int(os.getenv("WECHAT_AGENT_ID", "0"))
SECRET = os.getenv("WECHAT_SECRET", "")
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
SEEN_FILE = PROJECT_ROOT / "company" / "wechat_pushed.json"
LOCK_DIR = PROJECT_ROOT / "company" / ".wechat_locks"

_token = {"token": "", "expires_at": 0}


def get_token():
    if _token["token"] and time.time() < _token["expires_at"] - 120:
        return _token["token"]
    r = requests.get(
        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}",
        timeout=10,
    )
    data = r.json()
    if data.get("errcode") == 0:
        _token["token"] = data["access_token"]
        _token["expires_at"] = time.time() + data.get("expires_in", 7200)
        return _token["token"]
    raise RuntimeError(f"gettoken failed: {data}")


def send_text(user_id: str, content: str):
    token = get_token()
    body = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": content},
    }
    r = requests.post(
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
        json=body,
        timeout=10,
    )
    return r.json()


def send_markdown(user_id: str, content: str):
    token = get_token()
    body = {
        "touser": user_id,
        "msgtype": "markdown",
        "agentid": AGENT_ID,
        "markdown": {"content": content},
    }
    r = requests.post(
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
        json=body,
        timeout=10,
    )
    return r.json()


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(list(seen), ensure_ascii=False), encoding="utf-8")


# Only push replies, alerts, and status to WeChat — NOT research briefs/sentinels/reports.
# White papers and market analysis stay on the dashboard, not pushed to mobile.
WECHAT_WHITELIST = ("RESP_", "ALERT_")


def push_outbox():
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    pushed = 0
    for f in sorted(OUTBOX_DIR.glob("*.md")):
        if f.name in seen:
            continue
        if not f.name.startswith(WECHAT_WHITELIST):
            seen.add(f.name)
            continue
        # Atomic per-file lock: prevent duplicate pushes from concurrent processes
        lock_file = LOCK_DIR / f.name
        if lock_file.exists():
            # Check TTL — stale locks (>5min) are reclaimed
            try:
                age = time.time() - lock_file.stat().st_mtime
                if age < 300:
                    continue  # Another process is handling this
                lock_file.unlink()
            except Exception:
                continue
        try:
            lock_file.write_text(str(os.getpid()))
        except Exception:
            continue
        text = f.read_text(encoding="utf-8")
        title = f.stem
        preview = text.strip()[:200]
        dashboard = _dashboard_url()
        ts = _ts()
        content = f"[{ts} 北京时间]\n[{title}]\n{preview}"
        if dashboard:
            content += f"\n\n→ {dashboard} 查看详情"
        if len(content) > 4000:
            content = content[:4000] + "\n..."
        result = send_text("@all", content)
        if result.get("errcode") == 0:
            seen.add(f.name)
            pushed += 1
            print(f"  Pushed: {f.name}")
        else:
            print(f"  FAILED: {f.name} -> {result}")
        # Release lock
        try:
            lock_file.unlink()
        except Exception:
            pass
    save_seen(seen)
    return pushed


if __name__ == "__main__":
    try:
        n = push_outbox()
        print(f"{datetime.now().isoformat()} pushed={n}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
