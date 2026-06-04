#!/usr/bin/env python3
"""
market_monitor.py — OnionQuant 市场监控守护进程
─────────────────────────────────────────────
每 5 分钟: 数据 → 因子 → 风险 → 催化 → 持仓 → 决策 → 推送

模式:
  python scripts/market_monitor.py --once    # 单次 (cron)
  python scripts/market_monitor.py --loop    # 持续循环 (tmux daemon)
  python scripts/market_monitor.py --push    # 强制推送当前状态

工具栈: yfinance + risk_threshold_engine + statsmodels + catalyst_decision_model
       + decision_engine_v2 + knowledge_graph + wechat_bot
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
STATE_FILE = (
    PROJECT_ROOT / "company" / "departments" / "execution" / "monitor_state.json"
)
POSITION_MEMORY = Path(
    os.path.expanduser(
        "~/.claude/projects/e--2026-AgentStudy-Python-code/memory/chairman_position.md"
    )
)

# ─── 真实工具导入 ──────────────────────────────────
from risk_threshold_engine import RiskThresholdEngine, FactorScores
from quant_framework.strategies.regime_detector import (
    classify_current,
    rolling_regime_simple,
)
from quant_framework.strategies.catalyst_decision_model import (
    evaluate_position,
    dxyz_catalysts,
)
from quant_framework.knowledge_graph.quant_graph_builder import SECTOR_MAP

# ─── 配置 ─────────────────────────────────────────

WATCHLIST = [
    "DXYZ",
    "MU",
    "NVDA",
    "COHR",
    "RKLB",
    "LITE",
    "AVGO",
    "SNDK",
    "ASTS",
    "LUNR",
]
MACRO_SYMBOLS = ["^VIX", "^TNX", "CL=F"]  # VIX, 10Y, Crude Oil

# 触发推送的阈值
PRICE_MOVE_THRESHOLD = 0.03  # 5分钟内涨跌 3% → 推送
STOP_LOSS_PROXIMITY = 0.05  # 距止损 5% → 推送
REGIME_CHANGE_THRESHOLD = 15  # RTE 综合分变化 >15 → 推送

# ─── 市场时段 ─────────────────────────────────────


def market_session() -> str:
    """判断当前市场时段 (ET)."""
    now_et = datetime.utcnow() - timedelta(hours=4)  # EDT = UTC-4
    h = now_et.hour + now_et.minute / 60
    d = now_et.weekday()  # 0=Mon, 6=Sun

    if d >= 5:  # Saturday/Sunday (except Sunday 20:00+)
        if d == 6 and h >= 20:
            return "pre_market"  # Sunday evening
        return "weekend"

    if h < 4:
        return "overnight"
    elif h < 9.5:
        return "pre_market"
    elif h < 16:
        return "regular"
    elif h < 20:
        return "after_hours"
    else:
        return "overnight"


def session_emoji(session: str) -> str:
    return {
        "pre_market": "🌅",
        "regular": "📈",
        "after_hours": "🌙",
        "overnight": "💤",
        "weekend": "📴",
    }.get(session, "❓")


# ─── 自适应间隔 ─────────────────────────────────────
# 动态调整监控频率: 越接近催化事件 / 越紧张 → 越频繁

# 催化事件时间窗口 (从 CATALYST_CALENDAR 读取, 这里定义简化版)
CATALYST_WINDOWS = [
    {
        "event": "Starship IFT-12",
        "date": "2026-05-19",
        "time_et": "18:30",
        "tickers": ["DXYZ"],
    },
    {
        "event": "NVDA Q1 财报",
        "date": "2026-05-20",
        "time_et": "16:20",
        "tickers": ["NVDA"],
    },
    {"event": "三星罢工", "date": "2026-05-21", "time_et": "09:00", "tickers": ["MU"]},
]

# 最小间隔 (不能短于一轮分析耗时 ~14s + 缓冲)
MIN_INTERVAL = 60  # 1 分钟
MAX_INTERVAL = 1800  # 30 分钟
CYCLE_BUFFER = 20  # 分析耗时 + 缓冲 (秒)


def catalyst_proximity_hours() -> float:
    """返回距离最近催化事件的小时数。无事件返回 999。"""
    now = datetime.utcnow()
    closest_h = 999.0
    for cat in CATALYST_WINDOWS:
        try:
            cat_dt = datetime.strptime(
                f"{cat['date']} {cat['time_et']}", "%Y-%m-%d %H:%M"
            )
            delta_h = (cat_dt - now).total_seconds() / 3600
            if delta_h < -2:  # 已经过了 2 小时以上
                continue
            closest_h = min(closest_h, max(0, delta_h))
        except ValueError:
            continue
    return closest_h


def adaptive_interval(
    session: str, urgency: str = "normal", user_override: int = None
) -> int:
    """根据市场时段 + 催化接近度 + 紧急度, 计算合适的监控间隔。

    Parameters
    ----------
    session: market_session() 返回值
    urgency: 上一轮分析的紧急度
    user_override: 用户指定的间隔 (None=自动)

    Returns
    -------
    间隔秒数
    """
    if user_override:
        return max(MIN_INTERVAL, user_override)

    cat_hours = catalyst_proximity_hours()
    has_catalyst = cat_hours < 24

    # 基础间隔 (按市场时段)
    base = {
        "weekend": MAX_INTERVAL,  # 30min — 没开盘
        "overnight": 900,  # 15min
        "pre_market": 600 if has_catalyst else 900,  # 10/15min
        "regular": 600,  # 10min — 正常交易
        "after_hours": 900,  # 15min
    }.get(session, MAX_INTERVAL)

    # 催化接近 → 加速
    if cat_hours < 1:
        base = 60  # 1min — 发射/财报前1小时
    elif cat_hours < 3:
        base = 120  # 2min
    elif cat_hours < 6:
        base = 180  # 3min

    # 紧急度 → 加速
    if urgency == "critical":
        base = max(MIN_INTERVAL, base // 2)
    elif urgency == "urgent":
        base = max(MIN_INTERVAL, base // 1.5)

    return max(MIN_INTERVAL, min(MAX_INTERVAL, int(base)))


def interval_reason(interval: int) -> str:
    """解释为何选择此间隔。"""
    session = market_session()
    cat_h = catalyst_proximity_hours()
    parts = [f"时段={session}"]
    if cat_h < 24:
        parts.append(f"最近催化={cat_h:.1f}h")
    return ", ".join(parts)


# ─── 数据获取 ─────────────────────────────────────


def fetch_market_data() -> dict:
    """拉取所有需要的数据。"""
    session = market_session()

    # 近期日线 (用于因子计算) — 始终获取
    try:
        daily = yf.download(WATCHLIST, period="6mo", progress=False)
    except Exception:
        daily = None

    # 提取最新日线收盘价
    prices = {}
    if daily is not None and not daily.empty:
        for t in WATCHLIST:
            try:
                if "Close" in daily.columns.levels[0]:
                    series = daily.xs("Close", axis=1, level=1)[t].dropna()
                else:
                    series = (
                        daily["Close"][t].dropna()
                        if t in daily["Close"].columns
                        else None
                    )
                if series is not None and len(series) > 0:
                    prices[t] = round(float(series.iloc[-1]), 2)
            except (KeyError, IndexError):
                pass

    # 尝试获取盘前/实时价格
    pre_market_prices = {}
    if session in ("pre_market", "regular", "after_hours"):
        for t in WATCHLIST:
            try:
                tk = yf.Ticker(t)
                info = tk.fast_info
                # 优先: 盘前价 > 实时价 > 昨日收盘
                pre = (
                    getattr(info, "pre_market_price", None)
                    or getattr(info, "regular_market_price", None)
                    or getattr(info, "previous_close", None)
                )
                if pre and pre > 0:
                    pre_market_prices[t] = round(float(pre), 2)
            except Exception:
                pass

    # 如果 yfinance fast_info 失败, 用 download 的 1d/5m 数据
    if not pre_market_prices:
        try:
            live = yf.download(WATCHLIST, period="1d", interval="5m", progress=False)
            if live is not None and not live.empty:
                for t in WATCHLIST:
                    try:
                        if "Close" in live.columns.levels[0]:
                            last = (
                                live.xs("Close", axis=1, level=1)[t].dropna().iloc[-1]
                            )
                        elif t in live["Close"].columns:
                            last = live["Close"][t].dropna().iloc[-1]
                        else:
                            continue
                        pre_market_prices[t] = round(float(last), 2)
                    except (KeyError, IndexError):
                        pass
        except Exception:
            pass

    # 如果以上都没获取到, 用日线收盘价
    if not pre_market_prices:
        pre_market_prices = dict(prices)

    # VIX, 10Y, Oil — 从日线获取最近值
    macro = {}
    try:
        macro_data = yf.download(MACRO_SYMBOLS, period="5d", progress=False)
        if macro_data is not None and not macro_data.empty:
            for sym in MACRO_SYMBOLS:
                try:
                    if "Close" in macro_data.columns.levels[0]:
                        val = (
                            macro_data.xs("Close", axis=1, level=1)[sym]
                            .dropna()
                            .iloc[-1]
                        )
                    elif sym in macro_data["Close"].columns:
                        val = macro_data["Close"][sym].dropna().iloc[-1]
                    else:
                        continue
                    macro[sym] = round(float(val), 2)
                except (KeyError, IndexError):
                    pass
    except Exception:
        pass

    return {
        "prices": prices,
        "pre_market": pre_market_prices,
        "macro": macro,
        "daily": daily,
        "fetched_at": datetime.now().isoformat(),
    }


# ─── 分析管道 ─────────────────────────────────────


def analyze_pipeline(data: dict, positions: dict) -> dict:
    """跑完整分析管道: 因子 → 风险 → 催化 → 决策。"""
    results = {}

    # 1. 因子评分 (decision_engine_v2 逻辑)
    if data["daily"] is not None:
        try:
            from scripts.decision_engine_v2 import compute_factor_scores

            close, returns = None, None
            daily = data["daily"]
            if "Close" in daily.columns.levels[0]:
                close = daily.xs("Close", axis=1, level=1)
            returns = close.pct_change().dropna() if close is not None else None
            if close is not None and returns is not None:
                factor_df = compute_factor_scores(close, returns)
                results["factors"] = factor_df.to_dict(orient="records")
        except Exception as e:
            results["factor_error"] = str(e)[:100]

    # 2. 风险状态 (risk_threshold_engine)
    try:
        engine = RiskThresholdEngine()
        scores = FactorScores(
            volatility_score=35,
            momentum_score=45,
            breadth_score=40,
            macro_score=25,
            drawdown_score=55,
            as_of=datetime.now().isoformat(),
        )
        rte = engine.evaluate(scores)
        results["risk_regime"] = {
            "composite": rte.composite_score,
            "regime": rte.regime.value,
            "decision": str(rte.decision),
            "actions": [
                {"type": a.action_type, "rationale": a.rationale} for a in rte.actions
            ],
        }
    except Exception as e:
        results["risk_error"] = str(e)[:100]

    # 3. 市场状态 (statsmodels Markov)
    try:
        if data["daily"] is not None and "Close" in data["daily"].columns:
            daily = data["daily"]
            close = (
                daily.xs("Close", axis=1, level=1)
                if "Close" in daily.columns.levels[0]
                else daily["Close"]
            )
            market_ret = close.pct_change().mean(axis=1).dropna()
            regime = classify_current(market_ret, n_regimes=2)
            results["market_regime"] = regime
    except Exception as e:
        results["regime_error"] = str(e)[:100]
        # fallback: rolling simple
        try:
            if data["daily"] is not None:
                daily = data["daily"]
                close = (
                    daily.xs("Close", axis=1, level=1)
                    if "Close" in daily.columns.levels[0]
                    else daily["Close"]
                )
                market_ret = close.pct_change().mean(axis=1).dropna()
                rolling = rolling_regime_simple(market_ret)
                results["market_regime"] = {
                    "method": "rolling",
                    "label": rolling["regime"].iloc[-1],
                }
        except Exception:
            pass

    # 4. 持仓催化分析
    for pos_ticker, pos_info in positions.items():
        try:
            current_price = data["prices"].get(pos_ticker) or data["pre_market"].get(
                pos_ticker
            )
            if not current_price:
                continue

            if pos_ticker == "DXYZ":
                catalysts = dxyz_catalysts()
            else:
                catalysts = []

            decision = evaluate_position(
                ticker=pos_ticker,
                current_price=current_price,
                cost_basis=pos_info["cost_basis"],
                shares=pos_info["shares"],
                catalysts=catalysts,
                max_position_pct=1.0,
                max_loss_pct=-0.20,
                nav_premium_pct=(current_price / 24.56 - 1)
                if pos_ticker == "DXYZ"
                else None,
            )

            results[f"position_{pos_ticker}"] = {
                "ticker": pos_ticker,
                "current_price": current_price,
                "cost_basis": pos_info["cost_basis"],
                "shares": pos_info["shares"],
                "pnl_pct": round((current_price / pos_info["cost_basis"] - 1) * 100, 1),
                "pnl_usd": round(
                    pos_info["shares"] * (current_price - pos_info["cost_basis"]), 0
                ),
                "recommended_action": decision.recommended_action,
                "position_pct": decision.position_pct,
                "stop_loss": decision.stop_loss,
                "take_profit": decision.take_profit,
                "expected_return_pct": decision.expected_return_pct,
                "expected_value": decision.expected_value,
                "risk_reward_ratio": decision.risk_reward_ratio,
                "key_risk": decision.key_risk,
                "catalyst_timeline": decision.catalyst_timeline,
            }
        except Exception as e:
            results[f"position_error_{pos_ticker}"] = str(e)[:100]

    # 5. 价格异动检测
    results["price_alerts"] = _detect_price_moves(data, positions)

    # 6. 供应链接入
    try:
        chain = {}
        for t in WATCHLIST:
            if t in SECTOR_MAP:
                chain[t] = {"sector": SECTOR_MAP[t]}
        results["supply_chain"] = chain
    except Exception:
        pass

    results["analyzed_at"] = datetime.now().isoformat()
    results["session"] = market_session()
    return results


def _detect_price_moves(data: dict, positions: dict) -> list:
    """检测显著价格异动。"""
    alerts = []
    pre = data.get("pre_market", {})
    prices = data.get("prices", {})

    for t in WATCHLIST:
        current = pre.get(t) or prices.get(t)
        if not current:
            continue

        # 检查是否有历史对比 (从 state file)
        prev_state = load_previous_state()
        prev_prices = prev_state.get("last_prices", {})
        if t in prev_prices:
            move = (current - prev_prices[t]) / prev_prices[t]
            if abs(move) >= PRICE_MOVE_THRESHOLD:
                alerts.append(
                    {
                        "ticker": t,
                        "move_pct": round(move * 100, 1),
                        "from_price": prev_prices[t],
                        "to_price": current,
                        "direction": "up" if move > 0 else "down",
                    }
                )

    return alerts


# ─── 决策合成 ─────────────────────────────────────


def synthesize_decision(analysis: dict, positions: dict) -> dict:
    """将所有分析结果合成为一个可执行的决策。"""
    actions = []
    reasons = []
    urgency = "normal"  # normal / urgent / critical

    risk = analysis.get("risk_regime", {})
    regime = risk.get("regime", "UNKNOWN")

    # 处理每个持仓
    for ticker, pos in positions.items():
        pos_key = f"position_{ticker}"
        pos_data = analysis.get(pos_key, {})

        if not pos_data:
            continue

        action = pos_data.get("recommended_action", "持有")
        pnl_pct = pos_data.get("pnl_pct", 0)

        # 聚合理由
        ticker_reasons = []

        # 催化模型理由
        ev_ret = pos_data.get("expected_return_pct", 0)
        kelly_pos = pos_data.get("position_pct", 1.0)
        if ev_ret > 10:
            ticker_reasons.append(
                f"催化EV +{ev_ret:.0f}%, Kelly建议{kelly_pos:.0%}仓位"
            )
        elif ev_ret < -5:
            ticker_reasons.append(f"催化EV {ev_ret:.0f}%, 负期望")
            urgency = "urgent"

        # 风险状态理由
        if regime == "ELEVATED":
            ticker_reasons.append("风险状态ELEVATED, 建议减量")
            if action == "持有":
                action = "减仓观望"
        elif regime == "SEVERE":
            ticker_reasons.append("⚠️ 风险状态SEVERE")
            urgency = "critical"
            action = "减仓"

        # 价格异动理由
        for alert in analysis.get("price_alerts", []):
            if alert["ticker"] == ticker:
                ticker_reasons.append(
                    f"{'涨' if alert['direction'] == 'up' else '跌'} {abs(alert['move_pct']):.1f}% "
                    f"(${alert['from_price']:.2f}→${alert['to_price']:.2f})"
                )

        # 止损接近
        stop_loss = pos_data.get("stop_loss", 0)
        current_price = pos_data.get("current_price", 0)
        if stop_loss > 0 and current_price > 0:
            distance = (current_price - stop_loss) / current_price
            if distance < STOP_LOSS_PROXIMITY:
                ticker_reasons.append(f"⚡ 距止损仅 {distance:.1%} (${stop_loss:.2f})")
                urgency = "critical"

        # 浮盈锁利提示
        if pnl_pct > 15:
            ticker_reasons.append(f"浮盈 +{pnl_pct:.1f}%, 考虑锁利")

        actions.append(
            {
                "ticker": ticker,
                "action": action,
                "position_pct": pos_data.get("position_pct", 1.0),
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "stop_loss": stop_loss,
                "take_profit": pos_data.get("take_profit", 0),
                "reasons": ticker_reasons,
            }
        )
        reasons.extend(ticker_reasons)

    # 宏观理由
    if regime != "LOW":
        reasons.append(f"宏观: {regime} (RTE {risk.get('composite', '?')})")
    for a in risk.get("actions", []):
        reasons.append(f"风控: {a['type']} — {a['rationale']}")

    # 市场状态理由
    market_regime = analysis.get("market_regime", {})
    if market_regime.get("label"):
        reasons.append(f"市场: {market_regime['label']}")

    # 催化时间线
    for ticker in positions:
        pos_key = f"position_{ticker}"
        pos_data = analysis.get(pos_key, {})
        timeline = pos_data.get("catalyst_timeline", [])
        for t in timeline:
            reasons.append(f"📅 {t}")

    return {
        "timestamp": datetime.now().isoformat(),
        "session": analysis.get("session", "unknown"),
        "urgency": urgency,
        "actions": actions,
        "reasons": reasons[:8],  # 最多 8 条理由
        "macro": {
            "regime": regime,
            "rte_score": risk.get("composite", 0),
            "market_label": market_regime.get("label", "?"),
        },
    }


# ─── 推送 ────────────────────────────────────────


def push_decision(decision: dict, force: bool = False):
    """推送决策到董事长微信 (通过 outbox)。"""
    prev = load_previous_state()

    # 检查是否需要推送
    prev_actions = prev.get("last_actions", [])
    current_actions = decision.get("actions", [])

    # 提取 key: ticker→action 映射
    prev_map = {a["ticker"]: a["action"] for a in prev_actions}
    curr_map = {a["ticker"]: a["action"] for a in current_actions}

    changed = prev_map != curr_map
    is_urgent = decision["urgency"] in ("urgent", "critical")

    if not changed and not is_urgent and not force:
        return None  # 无变化, 静默

    # 构建消息
    session = decision["session"]
    emoji = session_emoji(session)
    now_bjt = (datetime.utcnow() + timedelta(hours=8)).strftime("%m/%d %H:%M")

    lines = [
        f"## {emoji} OnionQuant {now_bjt} BJT",
        "",
    ]

    urgency_icon = {"normal": "ℹ️", "urgent": "⚡", "critical": "🔴"}.get(
        decision["urgency"], ""
    )
    if is_urgent:
        lines.append(f"**{urgency_icon} {decision['urgency'].upper()}**")
        lines.append("")

    # 每个持仓的建议
    for a in current_actions:
        action_icon = {
            "加仓": "🟢",
            "持有": "🟡",
            "持有观望": "🟡",
            "减仓": "🟠",
            "减仓观望": "🟠",
            "清仓": "🔴",
        }.get(a["action"], "⚪")

        lines.append(f"**{a['ticker']}** — {action_icon} {a['action']}")
        lines.append(
            f"${a['current_price']:.2f} | 浮盈 {a['pnl_pct']:+.1f}% | 仓位建议 {a['position_pct']:.0%}"
        )
        if a.get("stop_loss"):
            lines.append(f"止损 ${a['stop_loss']:.2f} | 止盈 ${a['take_profit']:.2f}")

        for r in a.get("reasons", [])[:3]:
            lines.append(f"> {r}")
        lines.append("")

    # 宏观
    macro = decision.get("macro", {})
    lines.append(
        f"**宏观**: {macro.get('regime', '?')} (RTE {macro.get('rte_score', '?')}) | 市场: {macro.get('market_label', '?')}"
    )

    # 理由摘要
    if decision.get("reasons"):
        lines.append("")
        lines.append("**要点**:")
        for r in decision["reasons"][:5]:
            lines.append(f"• {r}")

    msg = "\n".join(lines)

    # 写入 outbox → wechat_bot 5 秒内拾取
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"MARKET_{ts}_{decision['urgency']}.md"
    filepath = OUTBOX_DIR / filename
    filepath.write_text(msg, encoding="utf-8")

    # 保存状态
    save_current_state(decision)

    return filepath


# ─── 状态持久化 ───────────────────────────────────


def load_previous_state() -> dict:
    """加载上次的决策状态。"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_current_state(decision: dict):
    """保存当前决策状态。"""
    prices = {}
    for a in decision.get("actions", []):
        prices[a["ticker"]] = a.get("current_price", 0)

    state = {
        "last_actions": [
            {"ticker": a["ticker"], "action": a["action"]}
            for a in decision.get("actions", [])
        ],
        "last_prices": prices,
        "last_push": decision.get("timestamp", ""),
        "last_session": decision.get("session", ""),
        "last_urgency": decision.get("urgency", "normal"),
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── 持仓读取 ─────────────────────────────────────


def load_positions() -> dict:
    """从记忆文件读取当前持仓。"""
    positions = {}
    # 硬编码当前已知持仓 (从 memory/chairman_position.md 同步)
    # 也可从 POSITION_MEMORY 文件中解析
    positions["DXYZ"] = {
        "ticker": "DXYZ",
        "shares": 585,
        "cost_basis": 47.62,
        "value": 585 * 47.62,  # $27,857.70
    }
    return positions


# ─── 主循环 ────────────────────────────────────────


def run_once(force_push: bool = False):
    """执行一次完整的监控周期。"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始监控周期...")
    print(f"  时段: {market_session()} ({session_emoji(market_session())})")

    # 1. 获取数据
    print("  📡 获取市场数据...")
    data = fetch_market_data()
    prices = data.get("pre_market") or data.get("prices", {})
    print(f"  价格已获取: {len(prices)} 标的")
    for t, p in list(prices.items())[:5]:
        print(f"    {t}: ${p:.2f}")

    # 2. 加载持仓
    positions = load_positions()
    print(f"  持仓: {len(positions)} 个")

    # 3. 分析
    print("  🔬 运行分析管道...")
    analysis = analyze_pipeline(data, positions)

    # 打印分析摘要
    for ticker in positions:
        pos_key = f"position_{ticker}"
        if pos_key in analysis:
            p = analysis[pos_key]
            print(
                f"    {ticker}: {p['recommended_action']} | EV {p['expected_return_pct']:+.1f}% | "
                f"PnL {p['pnl_pct']:+.1f}% | 止损 ${p['stop_loss']:.2f}"
            )

    risk = analysis.get("risk_regime", {})
    print(f"  风险: {risk.get('regime', '?')} ({risk.get('composite', '?')})")

    # 4. 合成决策
    print("  🎯 合成决策...")
    decision = synthesize_decision(analysis, positions)
    print(f"  紧急度: {decision['urgency']} | 操作数: {len(decision['actions'])}")

    # 5. 推送
    result = push_decision(decision, force=force_push)
    if result:
        print(f"  ✅ 已推送 → {result.name}")
    else:
        print("  🔇 无变化, 静默")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 周期完成")
    return analysis, decision


def check_inbox_commands() -> Optional[int]:
    """扫描 inbox 中是否有董事长发来的监控频率指令。

    识别关键词:
      "高频监控" / "1分钟" → 60s
      "加速" / "跑快点" → 120s
      "恢复常态" / "正常" → None (取消覆盖)
      "慢一点" / "省点钱" → 600s
    """
    inbox_dir = PROJECT_ROOT / "company" / "chairman_inbox"
    if not inbox_dir.exists():
        return None

    for f in sorted(inbox_dir.glob("MSG_*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue

        # 检查是否在最近 5 分钟内
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if (datetime.now() - mtime).total_seconds() > 300:
            continue

        text_lower = text.lower()
        if any(kw in text_lower for kw in ["高频监控", "高频模式"]):
            return 60
        if any(kw in text_lower for kw in ["1分钟", "一分钟", "每分钟"]):
            return 60
        if any(kw in text_lower for kw in ["加速", "跑快点", "紧张", "盯着"]):
            return 120
        if any(kw in text_lower for kw in ["恢复常态", "正常", "默认频率"]):
            return None  # 取消覆盖
        if any(kw in text_lower for kw in ["慢一点", "省点钱", "低频"]):
            return 600

    return None


def run_loop(interval: int = None):
    """持续循环监控 (自适应间隔)。

    Parameters
    ----------
    interval: 固定间隔(秒)。None=自适应, 指定值=覆盖。
    """
    print("🔄 启动市场监控循环 (自适应间隔)")
    print("  停止: Ctrl+C")
    print(f"  最小间隔: {MIN_INTERVAL}s | 最大间隔: {MAX_INTERVAL}s")
    print("  一轮分析耗时: ~14s")
    print()

    last_urgency = "normal"
    user_override = interval  # None=自适应

    while True:
        t0 = time.time()

        try:
            _, decision = run_once()
            last_urgency = decision.get("urgency", "normal")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            import traceback

            traceback.print_exc()
            last_urgency = "normal"

        # 检查用户指令
        cmd = check_inbox_commands()
        if cmd is not None:
            user_override = cmd
            print(f"  📩 收到指令 → 固定间隔 {cmd}s")
        elif cmd is None and user_override is not None:
            # "恢复常态" 被检测到 → cmd=None 但 user_override 可能还有值
            cmd_text = None
            inbox_dir = PROJECT_ROOT / "company" / "chairman_inbox"
            if inbox_dir.exists():
                for f in sorted(inbox_dir.glob("MSG_*.md")):
                    try:
                        text = f.read_text(encoding="utf-8")
                        if any(kw in text for kw in ["恢复常态", "正常", "默认频率"]):
                            cmd_text = "恢复常态"
                    except Exception:
                        pass
            if cmd_text:
                user_override = None
                print("  📩 收到指令 → 恢复自适应频率")

        # 计算间隔
        session = market_session()
        interval_s = adaptive_interval(session, last_urgency, user_override)

        elapsed = time.time() - t0
        sleep_s = max(0, interval_s - elapsed)

        # 频率信息
        marker = "⚡" if interval_s <= 60 else ("🔶" if interval_s <= 180 else "🔹")
        print(f"  {marker} 下次: {sleep_s:.0f}s 后 ({interval_reason(interval_s)})")
        if user_override:
            print(
                f"     (用户覆盖中, 否则自适应: {adaptive_interval(session, last_urgency)}s)"
            )

        time.sleep(sleep_s)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OnionQuant Market Monitor")
    parser.add_argument("--once", action="store_true", help="单次执行")
    parser.add_argument("--loop", action="store_true", help="持续循环 (自适应间隔)")
    parser.add_argument("--push", action="store_true", help="强制推送")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="固定间隔(秒)。不指定则自适应: 催化前1h→60s, 正常→10min, 周末→30min",
    )
    args = parser.parse_args()

    if args.loop:
        run_loop(interval=args.interval)
    else:
        run_once(force_push=args.push)


if __name__ == "__main__":
    main()
