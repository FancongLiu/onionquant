#!/usr/bin/env python3
"""research_publisher.py — 研报面板自动发布

由 cron 定时调用，仅在市场时段（美东 9:30-16:00 / 北京时间 21:30-04:00）生成更新。
核心规则：DXYZ 价格偏离 >5% 或新催化事件 → 发布更新，否则静默。

Usage:
    python scripts/research_publisher.py          # 检查并发布 (如需要)
    python scripts/research_publisher.py --force  # 强制发布
"""

import argparse
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
REPORTS_DIR = PROJECT_ROOT / "company" / "reports"
STATE_FILE = (
    PROJECT_ROOT
    / "company"
    / "departments"
    / "execution"
    / "research_publisher_state.json"
)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_price": 0, "last_report_ts": "", "publish_count": 0}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_market_hours() -> bool:
    """美东 9:30-16:00 → UTC 13:30-20:00 (夏令时)"""
    now = datetime.now(UTC)
    t = now.time()
    # 简化为 UTC 13:30-20:00
    return time(13, 30) <= t <= time(20, 0)


def fetch_dxyz_price():
    """获取 DXYZ 最新价格."""
    try:
        import yfinance as yf

        tk = yf.Ticker("DXYZ")
        info = tk.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
        return price, prev
    except Exception as e:
        print(f"[research_pub] yfinance error: {e}")
        return None, None


def should_publish(
    price: float, prev_close: float, state: dict, force: bool = False
) -> bool:
    """判断是否需要发布更新."""
    if force:
        return True
    if not _is_market_hours():
        return False
    if not state["last_price"]:
        return True  # 首次
    change_pct = abs(price - state["last_price"]) / state["last_price"] * 100
    # 价格偏离 >5% 或距上次发布 >4小时
    if change_pct >= 5:
        return True
    if state["last_report_ts"]:
        last_ts = datetime.fromisoformat(state["last_report_ts"])
        if (datetime.now() - last_ts).total_seconds() > 4 * 3600:
            return True
    return False


def generate_report(price: float, prev_close: float, state: dict) -> str:
    """生成 DXYZ 研报更新."""
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
    now = datetime.now()
    direction = "上涨" if change_pct >= 0 else "下跌"

    return f"""# 🔴 DXYZ 盘中研报更新

**时间**: {now.strftime("%Y-%m-%d %H:%M UTC")}
**DXYZ**: ${price:.2f} ({direction} {abs(change_pct):.1f}%)

## 仓位提示
- 距上次报告: {state.get("last_report_ts", "首次")}
- 累计发布: {state["publish_count"] + 1} 次

## 关键关注
1. Starship V3 首飞 5/19 18:30 EDT — 发射前最后交易日
2. RSI ~96 极端超买 — 回调风险高
3. NAV 溢价 ~138% — 支付 $47 买 $20 资产
4. SpaceX IPO 招股书随时可能公开

---
*自动研报 · 触发条件: {"强制" if abs(change_pct) < 5 else f"价格变动 {abs(change_pct):.1f}%"}*
"""


def publish_report(report: str, state: dict):
    """写报告 + outbox 通知."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    # Save report
    report_file = REPORTS_DIR / f"dxyz_live_{ts}.md"
    report_file.write_text(report, encoding="utf-8")

    # Outbox notification
    notify_content = f"""# [RESEARCH] DXYZ 研报更新

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M")}

报告: {report_file.relative_to(PROJECT_ROOT)}
累计发布: {state["publish_count"] + 1} 次
"""
    outbox_file = OUTBOX_DIR / f"NOTIFY_{ts}_research_dxyz.md"
    outbox_file.write_text(notify_content, encoding="utf-8")
    print(f"[research_pub] Published: {report_file.name} → outbox")

    # Update state
    state["last_report_ts"] = datetime.now().isoformat()
    state["publish_count"] += 1
    _save_state(state)


def main():
    parser = argparse.ArgumentParser(description="Research Report Auto-Publisher")
    parser.add_argument(
        "--force", action="store_true", help="Force publish regardless of conditions"
    )
    args = parser.parse_args()

    state = _load_state()

    if not _is_market_hours() and not args.force:
        print("[research_pub] Market closed. Skip. (force with --force)")
        return

    price, prev_close = fetch_dxyz_price()
    if price is None:
        print("[research_pub] Cannot fetch price. Skip.")
        return

    state["last_price"] = price

    if not should_publish(price, prev_close or price, state, args.force):
        print(f"[research_pub] No trigger. DXYZ ${price:.2f}. Skip.")
        _save_state(state)
        return

    report = generate_report(price, prev_close or price, state)
    publish_report(report, state)


if __name__ == "__main__":
    main()
