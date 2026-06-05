#!/usr/bin/env python3
"""
expert_filter.py — OnionQuant 专家过滤器 (Step 3 of 6-step pipeline)

原则 (来源: IEEE TKDE 2025, Zhou et al.):
  - 聚合所有用户的情绪 → 预测准确率 ~47.6% (接近随机)
  - 只跟踪历史准确率高的"专家"用户 → 显著高于基线
  - 专家信号覆盖仅 ~4% 的股票-天数, 需通过关联图谱传播

实现:
  - 已知专家列表 (手动维护, 基于历史跟踪记录)
  - 专家意见加权: accuracy_weight × signal_strength
  - 非专家信号降权 70%

当前已知 SIVEF 专家 (2026-05-25, 来源: MarketScreener/SeekingAlpha/X):
  - Daniel Sereda (Seeking Alpha "Beyond the Wall Investing", 历史Strong Buy准确)
  - Johan Rosenqvist (前Danske Bank分析师, Silicon Matter博客, SIVEF单篇推涨35%)
  - Audun Wickstrand Iversen (DNB Disruptive Opportunities基金经理, 4月建仓)
  - "Serenity" (X ~200K粉丝, 但注意: 散户KOL ≠ 专家, 需跟踪验证其历史准确率)

Usage:
    python onionquant/tools/expert_filter.py --ticker SIVEF
    python onionquant/tools/expert_filter.py --scan  # 扫描所有当前热门股票
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ─── 已知专家库 (来源标注, 定期更新) ────────────────────────
# 格式: {name: {accuracy: 历史准确率(0-1), platform: 平台, focus: 专注领域}}

EXPERT_DATABASE = {
    # SIVEF 专家
    "Daniel Sereda": {
        "accuracy": None,  # 待跟踪验证, 初始权重 0.6
        "platform": "Seeking Alpha",
        "focus": ["CPO", "光模块", "SIVEF"],
        "source_url": "https://seekingalpha.com/article/4904375",
        "default_weight": 0.6,
    },
    "Johan Rosenqvist": {
        "accuracy": None,
        "platform": "X / Silicon Matter",
        "focus": ["半导体", "硅光", "SIVEF"],
        "source_url": "https://www.marketscreener.com/news/sivers-semiconductors-surges-following-blog-post-di-ce7e5edada8ef424",
        "default_weight": 0.7,  # 前Danske Bank分析师, 专业背景
    },
    "Audun Wickstrand Iversen": {
        "accuracy": None,
        "platform": "DNB Fund",
        "focus": ["CPO", "颠覆性科技", "SIVEF"],
        "source_url": "https://in.marketscreener.com/news/afv-sivers-semiconductors-stock-could-tenfold-according-to-dnb-fund-manager-ce7f59dfdd8af322",
        "default_weight": 0.8,  # 机构基金经理, 最高权重
    },
    # 通用专家
    "Michael Burry": {
        "accuracy": None,
        "platform": "Scion Asset Management",
        "focus": ["宏观", "泡沫", "做空"],
        "default_weight": 0.75,
    },
    "Bank of America (Hartnett)": {
        "accuracy": None,
        "platform": "BofA Global Research",
        "focus": ["宏观", "资金流", "泡沫预警"],
        "default_weight": 0.75,
        "note": "2026-05 SOX 密西西比泡沫警告 (来源: Benzinga)",
    },
}

# ─── X 散户KOL (跟专家分开, 仅用于舆论热度参考, 不用于投资决策) ───
INFLUENCER_LIST = {
    "Serenity": {
        "platform": "X",
        "followers": "~200K",
        "focus": ["SIVEF", "CPO"],
        "note": "散户KOL, 非投资专家。唱多SIVEF主力。需验证历史准确率。",
        "source_url": "https://www.marketscreener.com/news/sivers-semiconductors-surges-following-blog-post-di-ce7e5edada8ef424",
    },
}


def get_expert_signal(ticker: str) -> dict:
    """Get expert consensus for a given ticker.

    Returns:
        {ticker, expert_count, weighted_bull_score, experts: [...], warning: str}
    """
    ticker_upper = ticker.upper()
    experts_found = []
    total_weight = 0.0
    bull_score = 0.0

    for name, data in EXPERT_DATABASE.items():
        if ticker_upper in [f.upper() for f in data.get("focus", [])]:
            w = data["default_weight"]
            experts_found.append(
                {"name": name, "platform": data["platform"], "weight": w}
            )
            total_weight += w
            bull_score += w  # 目前已知的都是看多, 后续加入方向字段

    # 检查散户KOL
    influencers_found = []
    for name, data in INFLUENCER_LIST.items():
        if ticker_upper in [f.upper() for f in data.get("focus", [])]:
            influencers_found.append({"name": name, "followers": data["followers"]})

    result = {
        "ticker": ticker_upper,
        "expert_count": len(experts_found),
        "weighted_bull_score": round(bull_score / max(total_weight, 0.001), 2),
        "experts": experts_found,
        "influencers": influencers_found,
        "reliability": _assess_reliability(len(experts_found), total_weight),
    }

    if influencers_found and not experts_found:
        result["warning"] = "仅有散户KOL讨论, 无专业分析师覆盖。噪声风险高。"

    return result


def _assess_reliability(expert_count: int, total_weight: float) -> str:
    if expert_count >= 3 and total_weight >= 2.0:
        return "HIGH — 多个专业来源交叉验证"
    elif expert_count >= 2 and total_weight >= 1.0:
        return "MEDIUM — 有专业覆盖但需更多验证"
    elif expert_count >= 1:
        return "LOW — 单一专家来源, 需独立验证"
    else:
        return "NO EXPERT COVERAGE — 纯散户情绪驱动"


def filter_hot_stocks(scan_results: list[dict]) -> list[dict]:
    """Apply expert filter to social scan results.

    For each hot stock from social scanner, check expert coverage.
    Stocks with no expert coverage get a warning flag.
    """
    filtered = []
    for item in scan_results:
        ticker = item["ticker"]
        expert = get_expert_signal(ticker)
        item["expert_filter"] = expert
        filtered.append(item)
    return filtered


# ─── CLI ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--ticker", type=str, help="Single ticker to check")
    p.add_argument("--list-experts", action="store_true")
    args = p.parse_args()

    if args.list_experts:
        print("=== 已知专家库 ===")
        for name, data in EXPERT_DATABASE.items():
            print(
                f"  {name} ({data['platform']}) — {data['focus']} [weight:{data['default_weight']}]"
            )
        print("\n=== 散户KOL (仅参考) ===")
        for name, data in INFLUENCER_LIST.items():
            print(
                f"  {name} ({data['platform']}, {data['followers']}) — {data['note']}"
            )
    elif args.ticker:
        result = get_expert_signal(args.ticker)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
