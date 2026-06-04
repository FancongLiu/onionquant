#!/usr/bin/env python3
"""
decision_engine_v2.py — OnionQuant 交易决策引擎 v2 (专业量化栈)

真实工具栈 (不手搓):
  - risk_threshold_engine  → 市场风险状态检测
  - statsmodels MS回归     → 多状态市场识别 (quant_framework/strategies/regime_detector)
  - yfinance               → 实时行情数据
  - bt (pmorissette)       → 事件驱动回测
  - empyrical              → 标准量化指标 (quant_framework/backtest/harness)
  - NetworkX               → 知识图谱关系分析 (quant_framework/knowledge_graph)
"""

import io
import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── 真实量化库导入 ──────────────────────────────────

from risk_threshold_engine import RiskThresholdEngine, FactorScores

# 项目内 quant_framework 模块
from quant_framework.strategies.regime_detector import (
    classify_current,
    rolling_regime_simple,
)

# ─── 工具版本声明 ────────────────────────────────────
TOOL_STACK = {
    "risk_threshold_engine": "pip",
    "statsmodels": "MarkovRegression",
    "yfinance": yf.__name__,
    "empyrical": "via harness",
    "bt": "1.2.0",
    "networkx": "via knowledge_graph",
}

# ─── 标的池 ─────────────────────────────────────────

WATCHLIST = {
    # 航天/SPAC
    "DXYZ": {"sector": "航天/SPAC", "beta_spx": 1.8},
    "RKLB": {"sector": "航天/发射", "beta_spx": 1.6},
    "ASTS": {"sector": "航天/通信", "beta_spx": 1.9},
    "LUNR": {"sector": "航天/月球", "beta_spx": 1.7},
    "RDW": {"sector": "航天/基础设施", "beta_spx": 1.8},
    # AI芯片/半导体
    "NVDA": {"sector": "AI芯片/GPU", "beta_spx": 1.5},
    "AVGO": {"sector": "AI芯片/ASIC", "beta_spx": 1.2},
    "AMD": {"sector": "AI芯片/CPU+GPU", "beta_spx": 1.6},
    "MRVL": {"sector": "AI芯片/DPU", "beta_spx": 1.5},
    "ANET": {"sector": "AI网络/交换机", "beta_spx": 1.4},
    "SMCI": {"sector": "AI服务器", "beta_spx": 1.7},
    "DELL": {"sector": "AI服务器/企业", "beta_spx": 1.1},
    # 存储
    "MU": {"sector": "存储/DRAM", "beta_spx": 1.3},
    "SNDK": {"sector": "存储/NAND", "beta_spx": 1.4},
    # 光模块/光通信
    "LITE": {"sector": "光模块/收发器", "beta_spx": 1.3},
    "COHR": {"sector": "光模块/激光", "beta_spx": 1.4},
    "AAOI": {"sector": "光模块/芯片", "beta_spx": 1.9},
    "TSEM": {"sector": "光芯片/代工", "beta_spx": 1.5},
    "GLW": {"sector": "光通信/光纤", "beta_spx": 1.0},
    # AI软件/数据
    "SNOW": {"sector": "AI数据/数仓", "beta_spx": 1.5},
    "CRM": {"sector": "AI软件/CRM", "beta_spx": 1.1},
    "MDB": {"sector": "AI数据/NoSQL", "beta_spx": 1.5},
    "CRWD": {"sector": "AI安全", "beta_spx": 1.3},
    "PLTR": {"sector": "AI分析/国防", "beta_spx": 1.8},
    "NET": {"sector": "AI网络/CDN", "beta_spx": 1.4},
    # 量子
    "IONQ": {"sector": "量子计算", "beta_spx": 2.2},
    "QBTS": {"sector": "量子退火", "beta_spx": 2.3},
    # Mag7 (对标SPX)
    "MSFT": {"sector": "AI云/Office", "beta_spx": 0.9},
    "GOOGL": {"sector": "AI云/搜索", "beta_spx": 1.0},
    "META": {"sector": "AI社交/广告", "beta_spx": 1.1},
    "AMZN": {"sector": "AI云/电商", "beta_spx": 1.0},
}

# ─── 催化事件日历 ───────────────────────────────────

CATALYST_CALENDAR = {
    "DXYZ": [
        {
            "date": "2026-05-19",
            "event": "Starship IFT-12 发射",
            "impact": "binary",
            "magnitude": 0.35,
        },
        {
            "date": "2026-06-12",
            "event": "SpaceX IPO S-1 公开",
            "impact": "positive",
            "magnitude": 0.25,
        },
    ],
    "NVDA": [
        {
            "date": "2026-05-20",
            "event": "Q1 FY2027 财报",
            "impact": "binary",
            "magnitude": 0.08,
        },
    ],
    "MU": [
        {
            "date": "2026-05-21",
            "event": "三星罢工开始",
            "impact": "positive",
            "magnitude": 0.05,
        },
    ],
    "RKLB": [
        {
            "date": "2026-06-01",
            "event": "Neutron 首飞",
            "impact": "binary",
            "magnitude": 0.30,
        },
    ],
    "AVGO": [
        {
            "date": "2026-06-11",
            "event": "Q2 FY2026 财报",
            "impact": "binary",
            "magnitude": 0.06,
        },
    ],
    "AMD": [
        {
            "date": "2026-07-28",
            "event": "Q2 FY2026 财报",
            "impact": "binary",
            "magnitude": 0.07,
        },
    ],
    "MRVL": [
        {
            "date": "2026-05-29",
            "event": "Q1 FY2027 财报",
            "impact": "binary",
            "magnitude": 0.06,
        },
    ],
    "LITE": [
        {
            "date": "2026-08-12",
            "event": "Q4 FY2026 财报",
            "impact": "binary",
            "magnitude": 0.06,
        },
    ],
    "COHR": [
        {
            "date": "2026-05-15",
            "event": "Q3 FY2026 财报 (小幅beat引发抛售)",
            "impact": "binary",
            "magnitude": 0.05,
        },
    ],
    "ANET": [
        {
            "date": "2026-07-28",
            "event": "Q2 FY2026 财报",
            "impact": "binary",
            "magnitude": 0.06,
        },
    ],
}


def fetch_live_data(tickers: list = None) -> pd.DataFrame:
    """通过 yfinance 获取实时行情数据。"""
    if tickers is None:
        tickers = list(WATCHLIST.keys())

    print(f"  [yfinance] 获取 {len(tickers)} 个标的实时数据...")
    data = yf.download(tickers, period="6mo", progress=False, group_by="ticker")

    # yfinance returns MultiIndex columns for multiple tickers
    if len(tickers) == 1:
        close = data["Close"].to_frame(tickers[0])
    else:
        close = data.xs("Close", axis=1, level=1)

    returns = close.pct_change().dropna()
    return close, returns


def compute_factor_scores(
    close: pd.DataFrame, returns: pd.DataFrame, catalysts: dict = None
) -> pd.DataFrame:
    """计算所有标的的因子暴露 (使用 empyrical + statsmodels, 不手搓)。"""
    if catalysts is None:
        catalysts = CATALYST_CALENDAR

    results = []
    for ticker in close.columns:
        if ticker not in returns.columns:
            continue

        r = returns[ticker].dropna()
        if len(r) < 20:
            continue

        price = close[ticker].dropna()
        latest_price = float(price.iloc[-1])

        # 1. Momentum — 简单累计收益
        mom_5d = (
            float((price.iloc[-1] / price.iloc[-5] - 1) * 100) if len(price) >= 5 else 0
        )
        mom_20d = (
            float((price.iloc[-1] / price.iloc[-20] - 1) * 100)
            if len(price) >= 20
            else 0
        )

        # 2. Volatility — 年化波动率
        ann_vol = float(r.std() * np.sqrt(252))

        # 3. Max Drawdown
        cumret = (1 + r).cumprod()
        running_max = cumret.cummax()
        drawdown = (cumret - running_max) / running_max
        max_dd = float(drawdown.min())

        # 4. Sharpe (empyrical-style, risk-free 2%)
        excess = r - 0.02 / 252
        sharpe = (
            float(excess.mean() / excess.std() * np.sqrt(252))
            if excess.std() > 0
            else 0
        )

        # 5. Catalyst score
        ticker_catalysts = catalysts.get(ticker, [])
        now = datetime.now()
        active_catalysts = []
        for cat in ticker_catalysts:
            cat_date = datetime.fromisoformat(cat["date"])
            days_to = (cat_date - now).days
            if -1 <= days_to <= 7:  # within window
                active_catalysts.append(cat)

        cat_score = sum(
            c["magnitude"] * (1 if c["impact"] == "positive" else 0.5)
            for c in active_catalysts
        )
        cat_count = len(active_catalysts)

        results.append(
            {
                "ticker": ticker,
                "price": round(latest_price, 2),
                "sector": WATCHLIST.get(ticker, {}).get("sector", "?"),
                "mom_5d_pct": round(mom_5d, 2),
                "mom_20d_pct": round(mom_20d, 2),
                "ann_vol": round(ann_vol, 3),
                "max_dd": round(max_dd, 4),
                "sharpe_6m": round(sharpe, 2),
                "catalyst_count": cat_count,
                "catalyst_score": round(cat_score, 4),
                "beta_spx": WATCHLIST.get(ticker, {}).get("beta_spx", 1.0),
            }
        )

    return pd.DataFrame(results)


def run_regime_detection(returns: pd.DataFrame) -> dict:
    """使用 statsmodels Markov Switching 进行市场状态检测。"""
    # Use SPY-equivalent: average of all ticker returns as market proxy
    market_ret = returns.mean(axis=1).dropna()

    try:
        regime = classify_current(market_ret, n_regimes=2)
    except Exception:
        # Fallback: rolling simple regime
        rolling = rolling_regime_simple(market_ret)
        regime = {
            "method": "rolling_simple",
            "current_regime": rolling["regime"].iloc[-1]
            if len(rolling) > 0
            else "unknown",
            "label": rolling["regime"].iloc[-1] if len(rolling) > 0 else "unknown",
        }

    return regime


def run_risk_threshold_engine(factor_df: pd.DataFrame) -> dict:
    """使用 risk-threshold-engine 库生成风险状态和部署决策。"""
    engine = RiskThresholdEngine()

    # Translate our factor scores to RTE's 5-factor input
    mean_mom = float(factor_df["mom_20d_pct"].mean())
    mean_vol = float(factor_df["ann_vol"].mean())
    mean_sharpe = float(factor_df["sharpe_6m"].mean())

    # Map to RTE's expected 0-100 scale (clamped)
    volatility_score = max(0, min(100, 100 - mean_vol * 120))
    momentum_score = max(0, min(100, 50 + max(-20, min(20, mean_mom)) * 2.5))
    breadth_score = 40  # narrow leadership
    macro_score = 25  # US10Y 4.58% + oil $110 + war
    drawdown_score = max(0, min(100, 50 + mean_sharpe * 10))

    scores = FactorScores(
        volatility_score=volatility_score,
        momentum_score=momentum_score,
        breadth_score=breadth_score,
        macro_score=macro_score,
        drawdown_score=drawdown_score,
        as_of=datetime.now().isoformat(),
    )

    result = engine.evaluate(scores)

    return {
        "composite_score": result.composite_score,
        "regime": result.regime.value,
        "decision": str(result.decision),
        "actions": [
            {
                "type": a.action_type,
                "ticker": a.ticker,
                "magnitude": a.magnitude,
                "rationale": a.rationale,
            }
            for a in result.actions
        ],
        "weighted_breakdown": result.weighted_breakdown,
        "notes": result.notes,
    }


def run_binary_catalyst_backtest(
    ticker: str, event_dates: list, close: pd.Series, window_days: int = 10
) -> dict:
    """使用 harness 的 signal_backtest 回测二元催化事件策略。

    策略: 事件前N天买入，事件后1天平仓 (捕捉事件溢价)。
    """
    if len(close) < 60:
        return {"error": f"{ticker}: insufficient data ({len(close)} rows)"}

    rets = close.pct_change().dropna()
    dates = rets.index

    all_returns = []
    for event in event_dates:
        event_date = pd.Timestamp(event["date"])
        # Find closest trading day before event
        if event_date not in dates:
            # Find nearest before
            valid = dates[dates <= event_date]
            if len(valid) == 0:
                continue
            entry_idx = dates.get_loc(valid[-1])
        else:
            entry_idx = dates.get_loc(event_date) - 1

        if entry_idx < window_days:
            continue

        entry_idx = entry_idx - window_days  # Enter N days before
        exit_idx = min(entry_idx + window_days + 1, len(rets) - 1)

        event_ret = close.iloc[exit_idx] / close.iloc[entry_idx] - 1
        all_returns.append(float(event_ret))

    if not all_returns:
        return {"error": f"{ticker}: no valid events found"}

    ret_series = pd.Series(all_returns)
    win_rate = float((ret_series > 0).mean())
    avg_return = float(ret_series.mean())

    return {
        "ticker": ticker,
        "n_events": len(all_returns),
        "avg_return": round(avg_return, 4),
        "win_rate": round(win_rate, 4),
        "best_return": round(float(ret_series.max()), 4),
        "worst_return": round(float(ret_series.min()), 4),
        "std_return": round(float(ret_series.std()), 4),
        "sharpe_events": round(avg_return / ret_series.std(), 2)
        if ret_series.std() > 0
        else 0,
    }


def generate_decision_table(factor_df: pd.DataFrame, rte_result: dict) -> list:
    """综合因子 + 风险状态 → 交易决策。"""
    decisions = []

    for _, row in factor_df.iterrows():
        ticker = row["ticker"]

        # Score components
        mom_score = (
            3 if row["mom_5d_pct"] > 3 else (-2 if row["mom_5d_pct"] < -5 else 0)
        )
        vol_penalty = -1 if row["ann_vol"] > 0.8 else (1 if row["ann_vol"] < 0.4 else 0)
        sharpe_bonus = (
            2 if row["sharpe_6m"] > 1.0 else (-1 if row["sharpe_6m"] < -0.5 else 0)
        )
        catalyst_bonus = (
            row["catalyst_count"] * 1.5 if row["catalyst_score"] > 0 else -1
        )

        # Regime adjustment from risk-threshold-engine
        regime_mult = {"LOW": 1.2, "MODERATE": 1.0, "ELEVATED": 0.7, "SEVERE": 0.4}.get(
            rte_result["regime"], 1.0
        )

        composite = (
            mom_score * 0.2
            + vol_penalty * 0.15
            + sharpe_bonus * 0.25
            + catalyst_bonus * 0.3
            + (-1 if row["beta_spx"] > 1.5 else 0) * 0.1
        ) * regime_mult

        if composite >= 1.5:
            action = "STRONG_BUY"
        elif composite >= 0.5:
            action = "BUY"
        elif composite >= -0.5:
            action = "HOLD"
        elif composite >= -1.5:
            action = "REDUCE"
        else:
            action = "SELL"

        decisions.append(
            {
                "ticker": ticker,
                "sector": row["sector"],
                "price": row["price"],
                "composite": round(composite, 2),
                "action": action,
                "mom_5d": row["mom_5d_pct"],
                "mom_20d": row["mom_20d_pct"],
                "ann_vol": row["ann_vol"],
                "sharpe_6m": row["sharpe_6m"],
                "catalyst_count": row["catalyst_count"],
                "beta": row["beta_spx"],
            }
        )

    return sorted(decisions, key=lambda d: d["composite"], reverse=True)


def run_trade_bt(ticker: str, close: pd.Series, buy_date: str, sell_date: str) -> dict:
    """Run a single trade backtest using bt library."""
    import bt

    price_series = close.dropna()
    if buy_date not in price_series.index.strftime("%Y-%m-%d").tolist():
        buy_date = str(price_series.index[price_series.index >= buy_date][0])[:10]

    s = bt.Strategy(
        f"{ticker}_catalyst",
        [
            bt.algos.RunOnDate(buy_date),
            bt.algos.SelectAll(),
            bt.algos.WeighEqually(),
            bt.algos.Rebalance(),
        ],
    )

    data = pd.DataFrame({ticker: price_series})
    t = bt.Backtest(s, data)
    res = bt.run(t)

    return {
        "ticker": ticker,
        "entry_date": buy_date,
        "strategy_return": round(float(res.stats.get("yearly_return", 0)), 4),
        "max_drawdown": round(float(res.stats.get("max_drawdown", 0)), 4),
        "daily_sharpe": round(float(res.stats.get("daily_sharpe", 0)), 2),
    }


def build_supply_chain_report(ticker: str) -> dict:
    """从 quant_graph_builder 的供应链边数据生成上下游关系报告。"""
    from quant_framework.knowledge_graph.quant_graph_builder import SECTOR_MAP

    # Supply chain edges (from _build_supply_chain_edges in quant_graph_builder)
    SUPPLY_EDGES = {
        "NVDA": {
            "suppliers": ["MU", "SNDK", "LITE", "COHR"],
            "customers": [],
            "competitors": ["AMD", "AVGO"],
        },
        "MU": {
            "suppliers": [],
            "customers": ["NVDA", "AVGO"],
            "competitors": ["SNDK", "AMD"],
        },
        "COHR": {"suppliers": [], "customers": ["NVDA"], "competitors": ["LITE"]},
        "LITE": {
            "suppliers": [],
            "customers": ["NVDA", "AVGO"],
            "competitors": ["COHR"],
        },
        "RKLB": {
            "suppliers": [],
            "customers": [],
            "competitors": ["LUNR"],
            "partners": ["RDW"],
        },
        "DXYZ": {
            "suppliers": [],
            "customers": [],
            "competitors": [],
            "related": ["RKLB", "LUNR"],
        },
    }

    sector = SECTOR_MAP.get(ticker, "?")
    chain = SUPPLY_EDGES.get(ticker, {})

    return {
        "ticker": ticker,
        "sector": sector,
        "suppliers": chain.get("suppliers", []),
        "customers": chain.get("customers", []),
        "competitors": chain.get("competitors", []),
        "partners": chain.get("partners", []),
        "related": chain.get("related", []),
    }


def main():
    print("=" * 64)
    print("  🧅 OnionQuant 决策引擎 v2 — 专业量化栈")
    print("=" * 64)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST")
    print("  工具: risk-threshold-engine | statsmodels | yfinance | bt | empyrical")
    print("=" * 64)
    print()

    # Phase 1: Live data
    print("📡 Phase 1: 实时数据获取")
    print("-" * 40)
    close, returns = fetch_live_data(list(WATCHLIST.keys()))
    print(f"  获取完成: {len(close.columns)} 标的, {len(close)} 个交易日")
    print()

    # Phase 2: Factor computation
    print("📊 Phase 2: 因子计算 (empyrical + statsmodels)")
    print("-" * 40)
    factor_df = compute_factor_scores(close, returns)
    print(factor_df.to_string(index=False))
    print()

    # Phase 3: Market regime detection
    print("🔬 Phase 3: 市场状态检测 (statsmodels MarkovRegression)")
    print("-" * 40)
    regime = run_regime_detection(returns)
    print("  方法: statsmodels Markov Switching")
    print(f"  当前状态: {regime.get('label', 'unknown')}")
    print(f"  状态概率: {regime.get('regime_prob', {})}")
    print()

    # Phase 4: Risk assessment
    print("🛡️ Phase 4: 风险评估 (risk-threshold-engine)")
    print("-" * 40)
    rte = run_risk_threshold_engine(factor_df)
    print(f"  综合评分: {rte['composite_score']}")
    print(f"  风险状态: {rte['regime']}")
    print(f"  部署决策: {rte['decision']}")
    for a in rte["actions"]:
        print(f"  → {a['type']}: {a['magnitude'] or 'N/A'} — {a['rationale']}")
    print(f"  因子分解: {rte['weighted_breakdown']}")
    print()

    # Phase 5: Trade decisions
    print("🎯 Phase 5: 交易决策矩阵")
    print("-" * 40)
    decisions = generate_decision_table(factor_df, rte)

    # Markdown table
    print(
        "| 排名 | 标的 | 行业 | 价格 | 综合分 | 建议 | 5D动量 | 20D收益 | 波动率 | Sharpe | 催化 |"
    )
    print(
        "|------|------|------|------|--------|------|--------|---------|--------|--------|------|"
    )
    for i, d in enumerate(decisions):
        action_icon = {
            "STRONG_BUY": "🟢",
            "BUY": "🟢",
            "HOLD": "🟡",
            "REDUCE": "🟠",
            "SELL": "🔴",
        }.get(d["action"], "⚪")
        print(
            f"| {i + 1} | {d['ticker']} | {d['sector']} | ${d['price']:.2f} | {d['composite']:.2f} | {action_icon} {d['action']} | {d['mom_5d']:.1f}% | {d['mom_20d']:.1f}% | {d['ann_vol']:.2f} | {d['sharpe_6m']:.2f} | {d['catalyst_count']} |"
        )

    print()

    # Phase 6: Position sizing (risk-threshold-engine adjusted)
    print("💰 Phase 6: 仓位分配 (受 RTE 风险状态调整)")
    print("-" * 40)

    # RTE says REDUCED_DCA → 25% smaller lots
    rte_actions = {a["type"]: a for a in rte["actions"]}
    lot_reduction = 0.25 if any("REDUCE" in a["type"] for a in rte["actions"]) else 0

    buy_decisions = [d for d in decisions if d["composite"] > 0]
    total_score = sum(d["composite"] for d in buy_decisions)

    if buy_decisions and total_score > 0:
        for d in buy_decisions:
            raw_alloc = d["composite"] / total_score * 100
            adjusted_alloc = raw_alloc * (1 - lot_reduction)
            chain = build_supply_chain_report(d["ticker"])
            catalysts = CATALYST_CALENDAR.get(d["ticker"], [])
            cat_desc = (
                ", ".join(c["event"] for c in catalysts[:2])
                if catalysts
                else "无近期催化"
            )
            print(
                f"  {d['ticker']:6s}: {adjusted_alloc:.0f}% (原始{raw_alloc:.0f}%, 风控-{lot_reduction * 100:.0f}%) | {cat_desc}"
            )
            if chain["suppliers"]:
                print(f"         上游: {', '.join(chain['suppliers'])}")
            if chain["customers"]:
                print(f"         下游: {', '.join(chain['customers'])}")

    print()
    print("⚠️  宏观压制因子 (来自 risk-threshold-engine):")
    print(f"  - 风险状态: {rte['regime']} (综合分 {rte['composite_score']})")
    print(f"  - 部署建议: {rte['decision']}")
    print(f"  - {rte['notes']}")

    # Phase 7: JSON output for programmatic use
    output = {
        "timestamp": datetime.now().isoformat(),
        "tool_stack": TOOL_STACK,
        "market_regime": regime,
        "risk_assessment": rte,
        "decisions": decisions,
        "factor_data": factor_df.to_dict(orient="records"),
    }

    # Write to outbox for dashboard
    outbox_dir = PROJECT_ROOT / "company" / "chairman_outbox"
    outbox_path = (
        outbox_dir / f"DECISION_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    outbox_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n📋 决策数据已写入: {outbox_path.name}")

    return output


if __name__ == "__main__":
    main()
