#!/usr/bin/env python3
"""
微信自动回复机器人 — 实时监控收件箱，零 token 轮询。
- 新消息到达 → 3 秒内检测
- 关键词匹配 → Python 直接回复（零 AI token）
- 复杂指令 → 调用 Claude CLI → 微信回复
- 由 background_scheduler.py 启动，常驻运行
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_ROOT / "company" / "chairman_inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
load_dotenv(PROJECT_ROOT / ".env")

BEIJING_TZ = timezone(timedelta(hours=8))
WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin"
CORP_ID = os.getenv("WECHAT_CORP_ID", "")
SECRET = os.getenv("WECHAT_SECRET", "")
AGENT_ID = os.getenv("WECHAT_AGENT_ID", "")

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ─── Keyword auto-replies (zero AI tokens) ───

KEYWORD_RULES = {
    "持仓": lambda: get_position_reply(),
    "仓位": lambda: get_position_reply(),
    "价格": lambda: get_price_reply(),
    "涨": lambda: get_price_reply(),
    "跌": lambda: get_price_reply(),
    "测试": lambda: "✅ 自动回复系统正常",
    "hi": lambda: (
        "👋 董事长好！系统在线。\n\n指令示例:\n• 持仓/价格 — 查看持仓\n• 研报 — 触发深度研究\n• 帮我查XXX — AI 查询"
    ),
    "hello": lambda: "👋 系统在线，随时待命。",
    "状态": lambda: get_status_reply(),
    "研报": lambda: trigger_research(),
}


def _ts():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _get_token():
    r = requests.get(
        f"{WECOM_API}/gettoken?corpid={CORP_ID}&corpsecret={SECRET}", timeout=10
    )
    return r.json().get("access_token", "")


def _send_wechat(text):
    """Send text message to WeChat. Returns True on success."""
    if not all([CORP_ID, SECRET, AGENT_ID]):
        print(f"[{_ts()}] WeChat not configured")
        return False
    token = _get_token()
    if not token:
        return False
    body = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": int(AGENT_ID),
        "text": {"content": text[:2000]},  # WeChat limit ~2048 chars
    }
    r = requests.post(
        f"{WECOM_API}/message/send?access_token={token}", json=body, timeout=10
    )
    result = r.json()
    ok = result.get("errcode") == 0
    if not ok:
        print(f"[{_ts()}] Send failed: {result}")
    return ok


# ─── Keyword handlers ───


def get_position_reply():
    ctx_path = (
        PROJECT_ROOT / "company" / "departments" / "execution" / "context_state.json"
    )
    try:
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        pos = ctx.get("key_context", {}).get("chairman_position", "未知")
        macro = ctx.get("key_context", {}).get("macro", "")
        mu = ctx.get("key_context", {}).get("mu_fundamentals", "")
        entry = ctx.get("key_context", {}).get("mu_entry_plan", "")
        updated = ctx.get("last_updated", "")
        return f"📊 持仓状态\n\n{pos}\n\n📈 MU: {mu[:200]}\n\n🎯 入场计划: {entry[:200]}\n\n🌍 宏观: {macro[:200]}\n\n更新: {updated}"
    except Exception as e:
        return f"读取持仓失败: {e}"


def get_price_reply():
    try:
        import yfinance as yf

        tickers = ["MU", "NVDA", "INTC", "SNDK", "AMD", "AVGO"]
        lines = []
        for t in tickers:
            try:
                tk = yf.Ticker(t)
                info = tk.info or {}
                px = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                prev = (
                    info.get("regularMarketPreviousClose")
                    or info.get("previousClose")
                    or px
                )
                chg = ((px - prev) / prev * 100) if prev else 0
                sign = "+" if chg >= 0 else ""
                lines.append(f"{t}: ${px:.2f} ({sign}{chg:.1f}%)")
            except Exception:
                lines.append(f"{t}: N/A")
        return "💹 实时报价\n\n" + "\n".join(lines)
    except Exception as e:
        return f"获取价格失败: {e}"


def get_status_reply():
    return f"🟢 系统在线\n\n🕐 {_ts()}\n🌐 https://onionoffice.xyz\n\n后台: WSL tmux ceo-24x7"


def trigger_research():
    """Kick off a quick Claude research and report back."""
    # Return immediately, Claude will send result separately
    subprocess.Popen(
        [
            "claude",
            "-p",
            "--model",
            "deepseek-v4-pro",
            "--dangerously-skip-permissions",
            "Quick research for chairman (WeChat request). Search: MU price, NVDA, Samsung strike vote (starts May 22 KST), market movers. Write BRIEF to company/chairman_outbox/BRIEF_$(date +%Y%m%d_%H%M).md and run python scripts/wechat_sync_push.py. Under 200 words. No crons.",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "🔬 已触发深度研究，结果将推送到微信，请稍候..."


# ─── AI passthrough for unmatched messages ───


def ai_process(content: str, from_user: str):
    """Forward unmatched message to MSG_ inbox for next Claude cycle. Zero AI tokens here."""
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    inbox_file = INBOX_DIR / f"MSG_wechat_{ts}.md"
    inbox_file.write_text(
        f"# 董事长微信指令\n\n"
        f"**时间**：{datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**来源**：企业微信 (from={from_user})\n\n"
        f"**内容**：\n{content}\n",
        encoding="utf-8",
    )
    return f'🤖 指令已收到，稍后回复。\n\n📝 "{content[:150]}"\n\n💡 常用关键词: 持仓 | 价格 | 研报 | 状态'


# ─── Main loop ───


def process_message(filepath: Path):
    """Read a WX_*.json message, match keywords, reply."""
    try:
        msg = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return

    content = msg.get("content", "").strip().lower()
    from_user = msg.get("from_user", "")

    if not content:
        return

    print(f"[{_ts()}] Message: '{msg.get('content', '')[:50]}' from {from_user}")

    # Keyword matching
    reply = None
    for keyword, handler in KEYWORD_RULES.items():
        if keyword in content:
            try:
                reply = handler()
            except Exception as e:
                reply = f"处理失败: {e}"
            break

    # No keyword match → AI
    if reply is None:
        reply = ai_process(msg.get("content", ""), from_user)

    # Send reply
    if reply:
        _send_wechat(reply)

    # Move to processed
    try:
        dest = PROCESSED_DIR / filepath.name
        filepath.rename(dest)
    except OSError:
        pass


def main():
    print(f"[{_ts()}] WeChat auto-reply started")
    print(f"  Inbox: {INBOX_DIR}")
    print(f"  Keywords: {list(KEYWORD_RULES.keys())}")

    # Track processed files to avoid duplicates
    seen = set()

    # Initialize: mark existing files as seen
    for f in INBOX_DIR.glob("WX_*.json"):
        seen.add(f.name)

    while True:
        try:
            for f in sorted(INBOX_DIR.glob("WX_*.json")):
                if f.name not in seen:
                    process_message(f)
                    seen.add(f.name)
            time.sleep(3)  # Poll every 3 seconds, zero cost
        except KeyboardInterrupt:
            print(f"\n[{_ts()}] Stopped")
            break
        except Exception as e:
            print(f"[{_ts()}] Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
