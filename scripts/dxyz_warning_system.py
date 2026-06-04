#!/usr/bin/env python3
"""T981: DXYZ RSI过热+Starship 5/19预警系统

监控 DXYZ 关键风险指标, 超阈值时写入 chairman_outbox 预警.
由 cron 每 15-30 分钟触发, 或手动运行.

Usage:
    python scripts/dxyz_warning_system.py
    python scripts/dxyz_warning_system.py --once  # 单次检查不循环
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from quant_framework.data.fetchers.yfinance_fetcher import fetch_batch

logger = logging.getLogger(__name__)


# ── 预警阈值配置 ──────────────────────────────────────────

THRESHOLDS = {
    "rsi": {
        "extreme": 90,       # 极端超买 → 🔴 P0 告警
        "overbought": 75,    # 超买 → 🟡 P1 提醒
        "oversold": 30,      # 超卖 → 🟡 P1 提醒
    },
    "nav_premium": {
        "extreme": 2.0,      # NAV溢价>200% → 🔴
        "high": 1.0,         # NAV溢价>100% → 🟡
    },
    "intraday_drop": -0.15,  # 日内跌幅>15% → 🔴
    "intraday_spike": 0.20,  # 日内涨幅>20% → 🟡
    "volume_spike": 3.0,     # 成交量为20日均量3倍 → 🟡
}

# NAV 参考值 (DXYZ Q3 2025 报告)
NAV_PER_SHARE = 20.0  # 每股净资产 (含SpaceX等私有公司估值)


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI (Wilder's smoothing method)."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def fetch_dxyz_data() -> pd.DataFrame:
    """Fetch DXYZ daily data (regular hours OHLCV)."""
    try:
        df = fetch_batch(["DXYZ"], start="2026-04-01", end=None, source="auto")
        if df is None or df.empty:
            logger.warning("DXYZ data fetch returned empty")
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error("DXYZ fetch failed: %s", e)
        return pd.DataFrame()


def fetch_dxyz_extended_hours() -> pd.DataFrame:
    """Fetch DXYZ intraday with pre/post-market data (4am-8pm ET).

    Returns DataFrame with DatetimeIndex covering extended hours.
    Useful for detecting after-hours moves and pre-market gaps.
    """
    try:
        import yfinance as yf
        t = yf.Ticker("DXYZ")
        df = t.history(period="5d", interval="5m", prepost=True)
        if df is None or df.empty:
            logger.warning("DXYZ extended hours fetch empty")
            return pd.DataFrame()
        return df
    except Exception as e:
        logger.error("DXYZ extended hours fetch failed: %s", e)
        return pd.DataFrame()


def check_warnings(df: pd.DataFrame) -> list[dict]:
    """Run all warning checks, return list of alerts."""
    alerts = []

    if df.empty:
        return alerts

    # Ticker filter
    dxyz = df[df["ticker"] == "DXYZ"].copy()
    if dxyz.empty:
        return alerts

    dxyz = dxyz.sort_values("date")
    latest = dxyz.iloc[-1]
    price = float(latest["close"])

    # ── RSI 检查 ──
    if len(dxyz) >= 15:
        dxyz["rsi"] = compute_rsi(dxyz["close"], 14)
        rsi = float(dxyz["rsi"].iloc[-1])

        if rsi >= THRESHOLDS["rsi"]["extreme"]:
            alerts.append({
                "level": "🔴 P0",
                "indicator": "RSI极端超买",
                "value": f"{rsi:.1f}",
                "threshold": f">{THRESHOLDS['rsi']['extreme']}",
                "action": "考虑减仓50%+; 历史RSI>90后7日平均回撤-18%",
            })
        elif rsi >= THRESHOLDS["rsi"]["overbought"]:
            alerts.append({
                "level": "🟡 P1",
                "indicator": "RSI超买",
                "value": f"{rsi:.1f}",
                "threshold": f">{THRESHOLDS['rsi']['overbought']}",
                "action": "设追踪止损-10%; 警惕回调",
            })
        elif rsi <= THRESHOLDS["rsi"]["oversold"]:
            alerts.append({
                "level": "🟡 P1",
                "indicator": "RSI超卖",
                "value": f"{rsi:.1f}",
                "threshold": f"<{THRESHOLDS['rsi']['oversold']}",
                "action": "超卖反弹机会, 考虑分批建仓",
            })

    # ── NAV 溢价检查 ──
    nav_premium = (price / NAV_PER_SHARE) - 1.0
    if nav_premium >= THRESHOLDS["nav_premium"]["extreme"]:
        alerts.append({
            "level": "🔴 P0",
            "indicator": "NAV溢价极端",
            "value": f"{nav_premium:.0%}",
            "threshold": f">{THRESHOLDS['nav_premium']['extreme']:.0%}",
            "action": "溢价>200%, 均值回归风险极高; 参考NAV≈$20",
        })
    elif nav_premium >= THRESHOLDS["nav_premium"]["high"]:
        alerts.append({
            "level": "🟡 P1",
            "indicator": "NAV溢价偏高",
            "value": f"{nav_premium:.0%}",
            "threshold": f">{THRESHOLDS['nav_premium']['high']:.0%}",
            "action": "关注溢价收缩风险; ATM增发稀释中",
        })

    # ── 日内波动检查 ──
    if "open" in latest.index:
        day_return = (price / float(latest["open"])) - 1.0
        if day_return <= THRESHOLDS["intraday_drop"]:
            alerts.append({
                "level": "🔴 P0",
                "indicator": "日内暴跌",
                "value": f"{day_return:.1%}",
                "threshold": f"<{THRESHOLDS['intraday_drop']:.0%}",
                "action": "检查是否有Starship/SpaceX负面新闻; 评估止损执行",
            })
        elif day_return >= THRESHOLDS["intraday_spike"]:
            alerts.append({
                "level": "🟡 P1",
                "indicator": "日内急涨",
                "value": f"{day_return:.1%}",
                "threshold": f">{THRESHOLDS['intraday_spike']:.0%}",
                "action": "追高风险; 等待回踩再加仓",
            })

    # ── 成交量异常检查 ──
    if "volume" in dxyz.columns and len(dxyz) >= 21:
        avg_vol = dxyz["volume"].iloc[-21:-1].mean()
        cur_vol = float(dxyz["volume"].iloc[-1])
        if avg_vol > 0 and cur_vol / avg_vol >= THRESHOLDS["volume_spike"]:
            alerts.append({
                "level": "🟡 P1",
                "indicator": "成交量异常放大",
                "value": f"{cur_vol / avg_vol:.1f}x",
                "threshold": f">{THRESHOLDS['volume_spike']:.0f}x",
                "action": "恐慌/狂热信号; 结合价格方向判断",
            })

    return alerts


def check_extended_hours(ext_df: pd.DataFrame, regular_close: float) -> list[dict]:
    """Check pre-market and after-hours moves for anomalies.

    Extended hours timings (ET):
      - Pre-market:  4:00am - 9:30am
      - After-hours: 4:00pm - 8:00pm

    Args:
        ext_df: Intraday DataFrame with prepost=True (DatetimeIndex)
        regular_close: Last regular-hours close price
    """
    alerts = []
    if ext_df.empty or len(ext_df) < 2:
        return alerts

    ext_df = ext_df.copy()
    if ext_df.index.tz is None:
        ext_df.index = ext_df.index.tz_localize("US/Eastern")
    else:
        ext_df.index = ext_df.index.tz_convert("US/Eastern")

    now_et = pd.Timestamp.now(tz="US/Eastern")

    # ── After-hours check: 4pm-8pm ET ──
    ah_mask = (ext_df.index.hour >= 16) | (ext_df.index.hour < 4)
    ah_data = ext_df[ah_mask]
    if not ah_data.empty:
        last_ah = ah_data.iloc[-1]
        ah_move = (float(last_ah["Close"]) / regular_close) - 1.0
        if abs(ah_move) >= 0.05:  # 5%+ move in after-hours
            direction = "↑" if ah_move > 0 else "↓"
            alerts.append({
                "level": "🔴 P0" if abs(ah_move) >= 0.10 else "🟡 P1",
                "indicator": f"盘后异动 {direction}",
                "value": f"{ah_move:+.1%}",
                "threshold": ">±5%",
                "action": "盘后大幅波动; 检查SpaceX/Starship相关催化剂新闻",
            })

    # ── Pre-market check: 4am-9:30am ET ──
    pm_mask = (ext_df.index.hour >= 4) & (ext_df.index.hour < 9)
    pm_data = ext_df[pm_mask]
    if not pm_data.empty and now_et.hour >= 4:
        last_pm = pm_data.iloc[-1]
        pm_move = (float(last_pm["Close"]) / regular_close) - 1.0
        if abs(pm_move) >= 0.05:
            direction = "↑" if pm_move > 0 else "↓"
            alerts.append({
                "level": "🔴 P0" if abs(pm_move) >= 0.10 else "🟡 P1",
                "indicator": f"盘前异动 {direction}",
                "value": f"{pm_move:+.1%}",
                "threshold": ">±5%",
                "action": "盘前大幅波动; 可能预示开盘跳空",
            })

    # ── 24h high-low range check ──
    all_high = float(ext_df["High"].max())
    all_low = float(ext_df["Low"].min())
    full_range = (all_high / all_low) - 1.0
    if full_range >= 0.15:  # 15%+ range over 5 days
        alerts.append({
            "level": "🟡 P1",
            "indicator": "扩展时段振幅过大",
            "value": f"{full_range:.1%}",
            "threshold": ">15% (5日)",
            "action": "扩展时段流动性差, 大振幅=高不确定性",
        })

    return alerts


def write_alert(alerts: list[dict], price: float) -> Path | None:
    """Write alert to chairman_outbox."""
    if not alerts:
        return None

    outbox_dir = PROJECT_ROOT / "company" / "chairman_outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    lines = [
        f"# 🚨 DXYZ 预警 — {len(alerts)} 项触发",
        f"**时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**DXYZ 价格**: ${price:.2f}",
        f"**NAV 溢价**: {(price / NAV_PER_SHARE - 1) * 100:.0f}%",
        "",
        "| 级别 | 指标 | 当前值 | 阈值 | 建议动作 |",
        "|------|------|--------|------|---------|",
    ]
    for a in alerts:
        lines.append(f"| {a['level']} | {a['indicator']} | {a['value']} | {a['threshold']} | {a['action']} |")

    lines += [
        "",
        "---",
        f"**Starship V3 发射**: 5/19 22:30 UTC (倒计时~{(datetime(2026, 5, 19, 22, 30, tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600:.0f}h)",
        f"**NVDA 财报**: 5/20 盘后",
        "",
        "*DXYZ预警系统 T981 自动生成*",
    ]

    path = outbox_dir / f"ALERT_DXYZ_warning_{ts}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="DXYZ Warning System (T981)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=900, help="Check interval in seconds (default: 900)")
    args = parser.parse_args()

    import time as time_mod

    while True:
        try:
            df = fetch_dxyz_data()
            if df.empty:
                logger.warning("No DXYZ data available")
            else:
                dxyz_df = df[df["ticker"] == "DXYZ"].sort_values("date")
                price = float(dxyz_df["close"].iloc[-1])
                alerts = check_warnings(df)

                # Extended hours check
                ext_df = fetch_dxyz_extended_hours()
                if not ext_df.empty:
                    ext_alerts = check_extended_hours(ext_df, price)
                    alerts.extend(ext_alerts)

                if alerts:
                    path = write_alert(alerts, price)
                    logger.warning("⚠️  %d alerts triggered → %s", len(alerts), path.name if path else "none")
                else:
                    if len(dxyz_df) >= 15:
                        rsi = float(compute_rsi(dxyz_df["close"], 14).iloc[-1])
                        logger.info("✅ DXYZ $%.2f | RSI %.1f | NAV溢价 %.0f%% — all clear",
                                    price, rsi, (price / NAV_PER_SHARE - 1) * 100)
                    else:
                        logger.info("✅ DXYZ $%.2f — all clear (insufficient data for RSI)", price)
        except Exception as e:
            logger.error("DXYZ warning check failed: %s", e)

        if args.once:
            break
        time_mod.sleep(args.interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
