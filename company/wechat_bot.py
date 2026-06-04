#!/usr/bin/env python3
"""
OnionQuant · 企业微信出站机器人
- 监控 chairman_outbox/ → 推送到董事长微信
- Hermes wecom_callback (WSL:8645) 负责入站消息处理
- 本模块仅负责出站推送，无需回调 URL

凭证: 项目根目录 .env (WECHAT_CORP_ID / WECHAT_AGENT_ID / WECHAT_SECRET)
启动: python company/wechat_bot.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows GBK 终端可能无法输出 emoji
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BEIJING_TZ = timezone(timedelta(hours=8))
CTX_STATE = PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"


def _ts() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _get_dashboard_url() -> str:
    """Read tunnel URL from context_state.json, fall back to localhost."""
    try:
        data = json.loads(CTX_STATE.read_text(encoding="utf-8"))
        return data.get("key_context", {}).get("tunnel_url", "http://localhost:8765")
    except Exception:
        return "http://localhost:8765"

CORP_ID = os.getenv("WECHAT_CORP_ID", "")
AGENT_ID = os.getenv("WECHAT_AGENT_ID", "")
SECRET = os.getenv("WECHAT_SECRET", "")

INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin"

_token_cache: dict = {"token": "", "expires_at": 0}


async def get_access_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 120:
        return _token_cache["token"]
    async with aiohttp.ClientSession() as session:
        url = f"{WECOM_API}/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
        async with session.get(url) as resp:
            data = await resp.json()
            if data.get("errcode") == 0:
                _token_cache["token"] = data["access_token"]
                _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200)
                return _token_cache["token"]
            raise RuntimeError(f"gettoken failed: {data}")


async def send_text(user_id: str, content: str) -> dict:
    token = await get_access_token()
    body = {"touser": user_id, "msgtype": "text", "agentid": int(AGENT_ID), "text": {"content": content}}
    async with aiohttp.ClientSession() as session:
        url = f"{WECOM_API}/message/send?access_token={token}"
        async with session.post(url, json=body) as resp:
            return await resp.json()


async def send_markdown(user_id: str, content: str) -> dict:
    token = await get_access_token()
    body = {"touser": user_id, "msgtype": "markdown", "agentid": int(AGENT_ID), "markdown": {"content": content}}
    async with aiohttp.ClientSession() as session:
        url = f"{WECOM_API}/message/send?access_token={token}"
        async with session.post(url, json=body) as resp:
            return await resp.json()


async def push_outbox(filepath: Path):
    """Read outbox file and push to WeChat."""
    text = filepath.read_text(encoding="utf-8")
    title = filepath.stem
    priority = "中"
    for line in text.split("\n")[:15]:
        if "**优先级**" in line:
            priority = "高" if "高" in line else ("低" if "低" in line else "中")
    emoji = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(priority, "📌")
    preview = text.strip()[:120]
    ts = _ts()
    msg = f"[{ts} 北京时间]\n{emoji} [Agent] 新消息\n**{title}**\n优先级: {priority}\n{preview}\n\n→ {_get_dashboard_url()} 查看详情"
    await send_text("@all", msg)


_seen: set = set()


async def outbox_watcher(interval: float = 5.0):
    """Poll outbox directory, push new files to WeChat."""
    print(f"  📤 监控 {OUTBOX_DIR}")
    while True:
        try:
            for f in sorted(OUTBOX_DIR.glob("*.md")):
                if f.name not in _seen:
                    _seen.add(f.name)
                    print(f"  📤 推送: {f.name}")
                    await push_outbox(f)
        except Exception as e:
            print(f"  ⚠️ Watcher error: {e}")
        await asyncio.sleep(interval)


async def send_daily_report():
    """Generate and push daily summary."""
    asks = list(OUTBOX_DIR.glob("ASK_*.md"))
    notifs = list(OUTBOX_DIR.glob("NOTIFY_*.md"))
    pending = [f for f in INBOX_DIR.glob("*.md") if f.name != "README.md"]
    report = (
        f"# 📊 OnionQuant 日报\n"
        f"> {_ts()} 北京时间\n\n"
        f"**待决策**: {len(asks)} 项\n"
        f"**通知**: {len(notifs)} 条\n"
        f"**待处理指令**: {len(pending)} 条\n\n"
        f"→ [打开仪表盘]({_get_dashboard_url()})"
    )
    await send_markdown("@all", report)


async def main():
    if not all([CORP_ID, AGENT_ID, SECRET]):
        print("❌ 缺少微信凭证，请检查 .env 文件")
        print(f"   CORP_ID={'✅' if CORP_ID else '❌'}")
        print(f"   AGENT_ID={'✅' if AGENT_ID else '❌'}")
        print(f"   SECRET={'✅' if SECRET else '❌'}")
        return

    print("🧅 OnionQuant · 企业微信出站机器人")
    print("   Hermes 入站: WSL port 8645 (wecom_callback)")
    print("   本模块出站: outbox → 微信推送")
    await outbox_watcher()


if __name__ == "__main__":
    asyncio.run(main())
