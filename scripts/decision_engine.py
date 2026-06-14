#!/usr/bin/env python3
"""
decision_engine.py — OnionQuant 交易决策引擎

基于多因子评分 + 催化事件加权 + 风险预算 → 生成交易建议。
参照: FinRL-X weight-centric 架构 + Risk-Threshold-Engine 因子模型
"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── 因子定义 ──────────────────────────────────────

# 每个因子的评分逻辑
FACTORS = {
    "momentum": {
        "weight": 0.20,
        "description": "短期动量 (5日/20日收益)",
        "positive": "5日收益 > 3% 且 20日收益 > 0%",
        "negative": "5日收益 < -5% 或 20日收益 < -10%",
    },
    "value": {
        "weight": 0.15,
        "description": "估值 (前向PE/PEG/NAV溢价)",
        "positive": "前向PE < 15x 或 PEG < 0.8",
        "negative": "前向PE > 50x 或 NAV溢价 > 100%",
    },
    "catalyst": {
        "weight": 0.30,
        "description": "催化事件密度与确定性",
        "positive": "48h内有高确定性催化且方向明确",
        "negative": "无催化或催化不确定性极高",
    },
    "sentiment": {
        "weight": 0.15,
        "description": "舆情与资金流向",
        "positive": "机构增持+分析师上调+散户情绪正面",
        "negative": "Citron做空+分析师下调+内部人卖出",
    },
    "macro_risk": {
        "weight": 0.20,
        "description": "宏观风险环境",
        "positive": "VIX < 15, 10Y < 4%, 油价稳定",
        "negative": "VIX > 25, 10Y > 4.5%, 油价 > $100, 战争风险",
    },
}


def score_ticker(ticker_data: dict) -> dict:
    """对单个标的进行多因子评分"""
    scores = {}
    details = {}

    # 1. Momentum
    mom_5d = ticker_data.get("return_5d") or 0
    mom_20d = ticker_data.get("return_20d") or 0
    if mom_5d > 3 and mom_20d > 0:
        scores["momentum"] = 3
        details["momentum"] = f"强动量: 5D+{mom_5d}% 20D+{mom_20d}%"
    elif mom_5d < -5 or mom_20d < -10:
        scores["momentum"] = -2
        details["momentum"] = f"弱动量: 5D{mom_5d}% 20D{mom_20d}%"
    else:
        scores["momentum"] = 0
        details["momentum"] = f"中性动量: 5D{mom_5d}% 20D{mom_20d}%"

    # 2. Value
    fwd_pe = ticker_data.get("fwd_pe", None)
    nav_premium = ticker_data.get("nav_premium", None)
    if fwd_pe and fwd_pe < 15:
        scores["value"] = 3
        details["value"] = f"低估值: PE {fwd_pe}x"
    elif fwd_pe and fwd_pe > 50:
        scores["value"] = -2
        details["value"] = f"高估值: PE {fwd_pe}x"
    elif nav_premium and nav_premium > 100:
        scores["value"] = -3
        details["value"] = f"极端溢价: NAV+{nav_premium}%"
    elif nav_premium and nav_premium > 50:
        scores["value"] = -1
        details["value"] = f"高溢价: NAV+{nav_premium}%"
    else:
        scores["value"] = 0
        details["value"] = "估值中性"

    # 3. Catalyst
    cat_count = len(ticker_data.get("catalysts", []))
    cat_quality = ticker_data.get("catalyst_quality", "medium")
    if cat_count >= 2 and cat_quality == "high":
        scores["catalyst"] = 4
        details["catalyst"] = f"多重高确定性催化: {cat_count}个"
    elif cat_count >= 1 and cat_quality in ("high", "medium"):
        scores["catalyst"] = 3
        details["catalyst"] = f"有催化: {cat_count}个 ({cat_quality})"
    elif cat_count >= 1:
        scores["catalyst"] = 1
        details["catalyst"] = f"弱催化: {cat_count}个 ({cat_quality})"
    else:
        scores["catalyst"] = -2
        details["catalyst"] = "无催化事件"

    # 4. Sentiment
    sent = ticker_data.get("sentiment", {})
    pos = sent.get("positive", 0)
    neg = sent.get("negative", 0)
    net = pos - neg
    if net >= 3:
        scores["sentiment"] = 2
    elif net >= 1:
        scores["sentiment"] = 1
    elif net <= -3:
        scores["sentiment"] = -3
    elif net <= -1:
        scores["sentiment"] = -1
    else:
        scores["sentiment"] = 0
    details["sentiment"] = f"舆情净分: {net} (多{pos}/空{neg})"

    # 5. Macro Risk
    macro = ticker_data.get("macro", {})
    vix = macro.get("vix", 18)
    us10y = macro.get("us10y", 4.5)
    oil = macro.get("oil", 100)
    war = macro.get("war_risk", False)

    macro_score = 0
    if vix < 15:
        macro_score += 2
    elif vix > 25:
        macro_score -= 2
    if us10y < 4.0:
        macro_score += 1
    elif us10y > 4.5:
        macro_score -= 1
    if oil > 100:
        macro_score -= 1
    if war:
        macro_score -= 3

    scores["macro_risk"] = macro_score
    details["macro_risk"] = (
        f"VIX={vix} 10Y={us10y}% 油=${oil} 战争={'是' if war else '否'}"
    )

    # Composite
    weighted = sum(scores[k] * FACTORS[k]["weight"] for k in FACTORS)
    max_possible = sum(
        max(3, FACTORS[k].get("_max", 3)) * FACTORS[k]["weight"] for k in FACTORS
    )

    return {
        "ticker": ticker_data.get("ticker", "???"),
        "scores": scores,
        "details": details,
        "composite": round(weighted, 2),
        "normalized": round(weighted / max_possible * 100, 0) if max_possible else 0,
    }


def generate_decision(results: list) -> dict:
    """根据多标的评分生成交易决策"""
    if not results:
        return {"action": "HOLD", "reason": "无评分数据"}

    ranked = sorted(results, key=lambda r: r["composite"], reverse=True)
    ranked[0]


    decisions = []
    for r in ranked:
        score = r["composite"]
        if score >= 1.5:
            action = "STRONG_BUY"
        elif score >= 0.5:
            action = "BUY"
        elif score >= -0.5:
            action = "HOLD"
        elif score >= -1.5:
            action = "REDUCE"
        else:
            action = "SELL"
        decisions.append({**r, "action": action})

    return {
        "timestamp": datetime.now().isoformat(),
        "decisions": decisions,
        "top_pick": ranked[0]["ticker"],
        "top_score": ranked[0]["composite"],
    }


# ─── 预置标的评分数据 ──────────────────────────────


def get_current_scores():
    """基于当前已知数据预填充标的评分"""
    tickers = [
        {
            "ticker": "DXYZ",
            "return_5d": -5.17,
            "return_20d": 114,
            "fwd_pe": None,
            "nav_premium": 92,
            "catalysts": ["Starship 5/19发射", "SpaceX IPO 6/12", "SpaceX S-1公开"],
            "catalyst_quality": "high",
            "sentiment": {"positive": 4, "negative": 3},  # 散户狂热 vs 分析师警告
            "macro": {"vix": 18.4, "us10y": 4.58, "oil": 110, "war_risk": True},
        },
        {
            "ticker": "MU",
            "return_5d": -6.6,
            "return_20d": 200,
            "fwd_pe": 7.1,
            "nav_premium": None,
            "catalysts": ["三星罢工5/21", "HBM4 Rubin独供", "Q3指引$33.5B"],
            "catalyst_quality": "high",
            "sentiment": {"positive": 5, "negative": 1},  # 37买/5持 vs Citron做空
            "macro": {"vix": 18.4, "us10y": 4.58, "oil": 110, "war_risk": True},
        },
        {
            "ticker": "NVDA",
            "return_5d": -4.4,
            "return_20d": None,
            "fwd_pe": 28,
            "nav_premium": None,
            "catalysts": ["Q1财报5/20盘后", "Q2指引预期$85-87B"],
            "catalyst_quality": "high",
            "sentiment": {"positive": 5, "negative": 0},
            "macro": {"vix": 18.4, "us10y": 4.58, "oil": 110, "war_risk": True},
        },
        {
            "ticker": "COHR",
            "return_5d": -5.6,
            "return_20d": 395,
            "fwd_pe": 42,
            "nav_premium": None,
            "catalysts": ["CPO H2 2026", "NVIDIA $2B投资"],
            "catalyst_quality": "medium",
            "sentiment": {"positive": 3, "negative": 0},
            "macro": {"vix": 18.4, "us10y": 4.58, "oil": 110, "war_risk": True},
        },
        {
            "ticker": "RKLB",
            "return_5d": -5.9,
            "return_20d": 240,
            "fwd_pe": None,
            "nav_premium": None,
            "catalysts": ["Neutron首飞", "SpaceX IPO板块重估"],
            "catalyst_quality": "medium",
            "sentiment": {"positive": 4, "negative": 0},
            "macro": {"vix": 18.4, "us10y": 4.58, "oil": 110, "war_risk": True},
        },
    ]

    results = [score_ticker(t) for t in tickers]
    return generate_decision(results)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        decision = get_current_scores()
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        return

    # Markdown report
    decision = get_current_scores()
    print(f"# 🎯 OnionQuant 决策矩阵 — {decision['timestamp'][:19]}")
    print()
    print("| 排名 | 标的 | 综合分 | 动量 | 估值 | 催化 | 舆情 | 宏观 | 建议 |")
    print("|------|------|--------|------|------|------|------|------|------|")
    for i, d in enumerate(decision["decisions"]):
        s = d["scores"]
        action_icon = {
            "STRONG_BUY": "🟢",
            "BUY": "🟢",
            "HOLD": "🟡",
            "REDUCE": "🟠",
            "SELL": "🔴",
        }[d["action"]]
        print(
            f"| {i + 1} | {d['ticker']} | {d['composite']:.2f} | {s['momentum']} | {s['value']} | {s['catalyst']} | {s['sentiment']} | {s['macro_risk']} | {action_icon} {d['action']} |"
        )

    print()
    print("## 建议仓位分配")
    print()
    total_weight = sum(max(0, d["composite"]) for d in decision["decisions"])
    for d in decision["decisions"]:
        if d["composite"] > 0:
            alloc = d["composite"] / total_weight * 100 if total_weight > 0 else 0
            print(
                f"- **{d['ticker']}** ({d['action']}): {alloc:.0f}% — {d['details']['catalyst']}"
            )
    print()
    print("## ⚠️ 当前宏观压制")
    print("- 美伊战争风险 (油价$110)")
    print("- 10Y 4.58% 压制高估值科技")
    print("- 三星罢工 5/21 存储供应链冲击")
    print("- Starship IFT-12 今晚二元催化")


if __name__ == "__main__":
    main()
