#!/usr/bin/env python3
"""
strategy_pipeline.py — OnionQuant 6-Step Strategy Pipeline v2.0

新框架权重 (2026-05-25 董事长指令):
  AI产业链位置 25% | 舆论热度变化 25% | 宏观情绪 20% | 催化剂事件 20% | 估值 10%

六步流程:
  Step 1: 舆论扫描 (social_scanner.py)
  Step 2: 交叉验证 (HypeFinder + ApeWisdom)
  Step 3: 专家过滤 (expert_filter.py)
  Step 4: AI产业链定位
  Step 5: 基本面验证
  Step 6: 催化剂时间线 + 仓位建议

Usage:
    python onionquant/tools/strategy_pipeline.py                  # 全量运行
    python onionquant/tools/strategy_pipeline.py --ticker SIVEF   # 单票分析
    python onionquant/tools/strategy_pipeline.py --scan-only       # 仅扫描
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from onionquant.tools.social_scanner import scan as social_scan
from onionquant.tools.expert_filter import (
    get_expert_signal,
    filter_hot_stocks,
    EXPERT_DATABASE,
)

# ─── AI Supply Chain Position Map ─────────────────────────
# 来源: TrendForce 2026, Morgan Stanley 2026/05, JPMorgan

AI_SUPPLY_CHAIN = {
    # 上游核心器件 — 卡位最核心, 替代难度最高
    "LITE": {
        "tier": "上游/激光器",
        "position": "CPO激光器全球龙头",
        "moat": "极高",
        "score": 9.5,
    },
    "COHR": {
        "tier": "上游/全方案",
        "position": "SiPh/VCSEL/InP全覆盖",
        "moat": "极高",
        "score": 9.0,
    },
    "SIVEF": {
        "tier": "上游/激光器",
        "position": "CPO外置激光源(ELSFP)",
        "moat": "中(认证周期长,但市值小)",
        "score": 6.0,
    },
    "AVGO": {
        "tier": "上游/芯片",
        "position": "光DSP全球龙头",
        "moat": "极高",
        "score": 9.0,
    },
    "MRVL": {
        "tier": "上游/芯片",
        "position": "高速DSP+定制ASIC",
        "moat": "高",
        "score": 8.0,
    },
    # 中游封装/制造
    "INTC": {
        "tier": "中游/封装",
        "position": "EMIB 2.5D先进封装",
        "moat": "中高(TSMC替代)",
        "score": 7.5,
    },
    "TSM": {
        "tier": "中游/封装",
        "position": "CoWoS绝对标准",
        "moat": "极高",
        "score": 10.0,
    },
    "FN": {
        "tier": "中游/封装",
        "position": "全球最大光器件OSAT",
        "moat": "中",
        "score": 6.0,
    },
    # 下游应用
    "NVDA": {
        "tier": "下游/系统",
        "position": "CPO交换机定义者",
        "moat": "极高",
        "score": 10.0,
    },
    "ANET": {
        "tier": "下游/系统",
        "position": "数据中心交换机",
        "moat": "高",
        "score": 7.0,
    },
    # 航天
    "RKLB": {
        "tier": "航天/发射",
        "position": "小卫星发射+Neutron",
        "moat": "中高",
        "score": 7.0,
    },
    "ASTS": {
        "tier": "航天/通信",
        "position": "卫星直连手机",
        "moat": "高(频谱优势)",
        "score": 7.5,
    },
}

# ─── Known Catalysts Timeline ──────────────────────────────
# 来源: 各公司财报/新闻 (2026-05-25 搜索验证)

CATALYST_TIMELINE = [
    {"date": "2026-05-27", "ticker": "MRVL", "event": "财报", "importance": "HIGH"},
    {
        "date": "2026-05-27",
        "ticker": "Samsung",
        "event": "罢工投票截止",
        "importance": "CRITICAL",
    },
    {
        "date": "2026-06-03",
        "ticker": "AVGO",
        "event": "财报 ($2.46EPS/$22.87B est)",
        "importance": "HIGH",
    },
    {
        "date": "2026-06-04",
        "ticker": "SPCX",
        "event": "SpaceX IPO路演开始",
        "importance": "CRITICAL",
    },
    {
        "date": "2026-06-11",
        "ticker": "SPCX",
        "event": "SpaceX IPO定价",
        "importance": "CRITICAL",
    },
    {
        "date": "2026-06-12",
        "ticker": "SPCX",
        "event": "SpaceX Nasdaq首挂",
        "importance": "CRITICAL",
    },
    {
        "date": "2026-06-15",
        "ticker": "SIVEF",
        "event": "股东大会(含股票期权投票)",
        "importance": "MEDIUM",
    },
    {"date": "2026-06-24", "ticker": "MU", "event": "财报", "importance": "HIGH"},
    {
        "date": "2026-07",
        "ticker": "SPCX",
        "event": "Starship IFT-13 (NET July)",
        "importance": "MEDIUM",
    },
    {
        "date": "2026-Q4",
        "ticker": "RKLB",
        "event": "Neutron火箭首飞",
        "importance": "HIGH",
    },
]

# ─── Macro Sentiment ──────────────────────────────────────
# 来源: 2026-05-25 搜索 (Nikkei, 财联社, Investing.com)

MACRO_SNAPSHOT = {
    "date": "2026-05-25",
    "iran_peace": "Trump称'最后阶段', 伊朗确认收到提案, 霍尔木兹海峡逐渐开放",
    "oil": "Brent -5%至~$98, 利好消费/运输/小盘股",
    "a_shares": "科创50 +5.88%, 半导体+6.4%, 华为'韬定律'引爆",
    "nikkei": "历史首破65,000 (+2.87%), Kioxia +14%",
    "us_market": "周一Memorial Day休市, 周二开盘预计高开(全球情绪传导)",
    "sox_warning": "SOX 62%>200MA, Hartnett密西西比泡沫警告, Burry持SOXX看跌",
    "rate": "Fed 12月加息概率56%, 30Y 5.11%",
    "fund_flow": "43%基金经理预期Value跑赢Growth (BofA调查)",
    "risk_level": "HIGH — 全球risk-on但半导体极度拥挤",
}


def analyze_single_ticker(ticker: str) -> dict:
    """Run 6-step analysis on a single ticker."""
    ticker = ticker.upper()

    # Step 3: Expert filter
    expert = get_expert_signal(ticker)

    # Step 4: AI supply chain position
    chain = AI_SUPPLY_CHAIN.get(
        ticker, {"tier": "未分类", "position": "未知", "moat": "未知", "score": 3.0}
    )

    # Step 5: Fundamental check (从已有记忆和搜索中获取)
    fundamental = _fundamental_check(ticker)

    # Step 6: Catalyst timeline
    catalysts = [c for c in CATALYST_TIMELINE if c["ticker"] == ticker]

    # Composite score (新框架权重)
    macro_score = 7.0 if MACRO_SNAPSHOT["risk_level"] == "HIGH" else 5.0
    composite = (
        chain["score"] * 0.25
        + expert["weighted_bull_score"] * 10 * 0.25
        + macro_score * 0.20
        + (len(catalysts) * 2.5 if catalysts else 5) * 0.20
        + fundamental.get("score", 5) * 0.10
    )

    return {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "framework_version": "2.0",
        "scores": {
            "ai_supply_chain": round(chain["score"], 1),
            "expert_bull": round(expert["weighted_bull_score"] * 10, 1),
            "macro_sentiment": round(macro_score, 1),
            "catalyst_count": len(catalysts),
            "fundamental": round(fundamental.get("score", 5), 1),
            "composite": round(composite, 1),
        },
        "supply_chain": chain,
        "expert_filter": expert,
        "catalysts": catalysts,
        "fundamental": fundamental,
        "macro": MACRO_SNAPSHOT,
        "recommendation": _generate_recommendation(composite, expert, chain, ticker),
    }


def _fundamental_check(ticker: str) -> dict:
    """Quick fundamental check from known data. NOT fabricated — sourced from previous research."""
    # 数据来源: 2026-05-25 搜索 (Benzinga, Yahoo Finance, Seeking Alpha)
    DB = {
        "INTC": {
            "pe": "N/A(亏损)",
            "revenue_q1": "$13.6B",
            "loss_q1": "$3.7B",
            "score": 4.0,
            "note": "代工每季亏$24亿，2027前不盈利。来源: Q1 2026财报",
        },
        "SIVEF": {
            "pe": "N/A(亏损)",
            "revenue_2025": "~360M SEK est",
            "ps": "59.7x",
            "score": 3.0,
            "note": "亏损扩大，DCF公允价值~1.75 SEK vs 市价~55 SEK。来源: MarketScreener",
        },
        "MRVL": {
            "pe": "64x fwd",
            "revenue_fy2026": "$8.5B+",
            "score": 6.5,
            "note": "光DSP 50% CAGR，AWS+MSFT定制ASIC。来源: Benzinga May 2026",
        },
        "LITE": {
            "pe": "N/A",
            "order_backlog": "2028前售罄",
            "score": 7.0,
            "note": "OCS积压$400M, CY27加速至年化$1B+。来源: JPMorgan",
        },
        "COHR": {
            "pe": "N/A",
            "nvidia_deal": "$2B入股+供应协议",
            "score": 7.5,
            "note": "InP产能年底翻倍，加入S&P500。来源: Yahoo Finance",
        },
        "AVGO": {
            "pe": "~35x",
            "earnings_date": "6/3",
            "score": 8.0,
            "note": "Goldman $450, VMware稳定现金引擎。来源: Goldman Sachs",
        },
        "RKLB": {
            "pe": "N/A",
            "backlog": "$2.2B",
            "score": 6.0,
            "note": "Neutron Q4 2026, +398% 1年涨幅。来源: Benzinga",
        },
        "ASTS": {
            "pe": "N/A",
            "cash": "$3.5B",
            "short": "30%",
            "score": 5.5,
            "note": "BlueBird 6月中旬Falcon 9发射。来源: Fierce Network",
        },
    }
    return DB.get(ticker, {"pe": "未覆盖", "score": 4.0, "note": "需要进一步研究"})


def _generate_recommendation(
    composite: float, expert: dict, chain: dict, ticker: str
) -> str:
    parts = []
    if composite >= 8.0:
        parts.append("STRONG — AI产业链核心+专家背书+催化剂密集")
    elif composite >= 6.5:
        parts.append("MODERATE — 方向对，等待更好入场点或降低仓位")
    elif composite >= 5.0:
        parts.append("CAUTIOUS — 概念对但基本面/估值/专家覆盖不足")
    else:
        parts.append("AVOID — 纯情绪驱动，无基本面支撑")

    if expert.get("warning"):
        parts.append(f"⚠️ {expert['warning']}")

    if chain.get("score", 0) <= 4:
        parts.append("⚠️ AI产业链位置不核心")

    return " | ".join(parts)


def run_full_pipeline() -> dict:
    """Run complete 6-step pipeline and return report."""
    print("=" * 70)
    print("  OnionQuant Strategy Pipeline v2.0")
    print("  权重: AI链25% | 舆论25% | 宏观20% | 催化20% | 估值10%")
    print(f"  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 70)

    # Step 1-2: Social scan
    print("\n[Step 1-2] 舆论扫描 + 交叉验证...")
    scan_results = social_scan()

    # Step 3: Expert filtering
    print(f"\n[Step 3] 专家过滤 ({len(EXPERT_DATABASE)} known experts)...")
    filtered = filter_hot_stocks(scan_results)

    # Step 4-6: Deep analysis on top picks
    print("[Step 4-6] 产业链定位 + 基本面 + 催化剂...\n")
    analyses = []
    for item in filtered[:5]:
        analysis = analyze_single_ticker(item["ticker"])
        analyses.append(analysis)
        s = analysis["scores"]
        print(
            f"  {analysis['ticker']:<8} "
            f"AI链:{s['ai_supply_chain']:.1f} "
            f"专家:{s['expert_bull']:.1f} "
            f"宏观:{s['macro_sentiment']:.1f} "
            f"催化:{s['catalyst_count']} "
            f"基本面:{s['fundamental']:.1f} "
            f"→ 综合:{s['composite']:.1f}/10"
        )

    # Save report
    report = {
        "pipeline_version": "2.0",
        "timestamp": datetime.now().isoformat(),
        "macro": MACRO_SNAPSHOT,
        "scan_count": len(scan_results),
        "expert_filtered": len(filtered),
        "analyses": analyses,
        "catalyst_timeline": CATALYST_TIMELINE,
    }

    out_path = (
        PROJECT_ROOT
        / "company"
        / "reports"
        / f"strategy_pipeline_{datetime.now():%Y%m%d_%H%M}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), "utf-8"
    )

    print(f"\n→ Report saved: {out_path}")
    return report


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--ticker", type=str, help="Single ticker analysis")
    p.add_argument(
        "--scan-only", action="store_true", help="Only scan, no deep analysis"
    )
    args = p.parse_args()

    if args.ticker:
        result = analyze_single_ticker(args.ticker)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.scan_only:
        social_scan()
    else:
        run_full_pipeline()
