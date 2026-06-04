#!/usr/bin/env python3
"""
Tunnel URL 自动同步守护进程 — 零 AI token
- 启动并监控 cloudflared 进程
- 检测新 tunnel URL → 更新 context_state.json → 微信推送
- cloudflared 崩溃自动重启
- 纯脚本，不消耗 AI token
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows GBK terminal workaround
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ── config ──────────────────────────────────────────────
CLOUDFLARED = os.path.expandvars(r"C:\Users\28462\cloudflared.exe")
LOCAL_PORT = 8765
CTX_STATE = (
    PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"
)
LAST_URL_FILE = PROJECT_ROOT / "company" / ".last_tunnel_url"

CORP_ID = os.getenv("WECHAT_CORP_ID", "")
AGENT_ID = int(os.getenv("WECHAT_AGENT_ID", "0"))
SECRET = os.getenv("WECHAT_SECRET", "")

BEIJING_TZ = timezone(timedelta(hours=8))
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# ── WeChat API ──────────────────────────────────────────
_token_cache = {"token": "", "expires_at": 0}


def _get_token():
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 120:
        return _token_cache["token"]
    r = requests.get(
        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}",
        timeout=10,
    )
    data = r.json()
    if data.get("errcode") == 0:
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200)
        return _token_cache["token"]
    raise RuntimeError(f"gettoken failed: {data}")


def push_url_via_wechat(url: str):
    """Send new tunnel URL to chairman via WeChat. Zero AI tokens."""
    ts = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    msg = (
        f"[{ts} 北京时间]\n"
        f"Tunnel URL updated\n\n"
        f"New: {url}\n\n"
        f"Dashboard: {url}\n"
        f"WeChat Callback: {url}/api/wechat/callback"
    )
    try:
        token = _get_token()
        body = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {"content": msg},
        }
        r = requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
            json=body,
            timeout=10,
        )
        result = r.json()
        if result.get("errcode") == 0:
            print(f"  WeChat pushed OK: {url}")
            return True
        else:
            print(f"  WeChat push failed: {result}")
            return False
    except Exception as e:
        print(f"  WeChat push error: {e}")
        return False


# ── URL sync ────────────────────────────────────────────
def update_context_state(url: str):
    try:
        data = json.loads(CTX_STATE.read_text(encoding="utf-8"))
        data.setdefault("key_context", {})["tunnel_url"] = url
        data["last_updated"] = datetime.now(BEIJING_TZ).isoformat()
        CTX_STATE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("  context_state.json updated")
    except Exception as e:
        print(f"  Failed to update context_state.json: {e}")


def on_new_url(url: str):
    """Called when a new tunnel URL is detected."""
    print(f"\n{'=' * 50}")
    print(f"  New tunnel URL: {url}")
    update_context_state(url)
    LAST_URL_FILE.write_text(url, encoding="utf-8")
    push_url_via_wechat(url)
    print(f"{'=' * 50}\n")


# ── cloudflared process manager ─────────────────────────
def run_cloudflared():
    """Run cloudflared, yield lines from stderr, restart on crash."""
    while True:
        print(f"  Starting cloudflared --url localhost:{LOCAL_PORT} ...")
        try:
            proc = subprocess.Popen(
                [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{LOCAL_PORT}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stderr:
                yield line
            # If we get here, process exited
            rc = proc.wait()
            print(f"  cloudflared exited (code={rc}), restarting in 5s...")
        except Exception as e:
            print(f"  cloudflared error: {e}, restarting in 5s...")
        time.sleep(5)


def main():
    print("Tunnel Sync - cloudflared watchdog + URL push")
    print(f"  cloudflared: {CLOUDFLARED}")
    print(f"  local port: {LOCAL_PORT}")

    if not all([CORP_ID, AGENT_ID, SECRET]):
        print("  WARNING: WeChat credentials missing, URL push disabled")
        print("  Set WECHAT_CORP_ID/WECHAT_AGENT_ID/WECHAT_SECRET in .env")

    last_url = None
    if LAST_URL_FILE.exists():
        last_url = LAST_URL_FILE.read_text(encoding="utf-8").strip()
        print(f"  Last known URL: {last_url}")

    for line in run_cloudflared():
        # cloudflared prints URL on stderr in this format:
        # |  https://xxxxx.trycloudflare.com  |
        m = URL_PATTERN.search(line)
        if m:
            url = m.group(0)
            if url != last_url:
                on_new_url(url)
                last_url = url


if __name__ == "__main__":
    main()
