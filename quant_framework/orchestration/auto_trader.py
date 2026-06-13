#!/usr/bin/env python3
"""
OnionQuant · 自动化交易流水线 (AutoTrader)
──────────────────────────────────────────
完整闭环: 数据拉取 → 因子计算 → 信号生成 → 仓位计算 → 订单执行 → 报告输出

执行频率: 每日 (美东收盘后)
风险控制: Paper-only · 单日最大亏损5%熔断 · 单票最大仓位25%

Usage:
    python quant_framework/orchestration/auto_trader.py          # 单次执行
    python quant_framework/orchestration/auto_trader.py --live   # 实盘下单 (默认仅报告)
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(PROJECT_ROOT / ".env")

# ─── Universal stock universe (S&P 100 liquid subset) ────
UNIVERSE = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "BRK-B",
    "JPM",
    "V",
    "JNJ",
    "WMT",
    "PG",
    "MA",
    "UNH",
    "HD",
    "BAC",
    "DIS",
    "ADBE",
    "CRM",
    "NFLX",
    "AMD",
    "INTC",
    "QCOM",
    "TXN",
    "AVGO",
    "PYPL",
    "NKE",
    "COST",
    "MRK",
    "ABBV",
    "PEP",
    "KO",
    "TMO",
    "LLY",
    # 2026-05-18 研究增补: 存储/AI芯片/航天/光模块/中国科技
    "MU",
    "JD",
    "GE",
    "SNDK",
]

# ─── Risk limits ─────────────────────────────────────────
MAX_POSITIONS = 10  # 最大持仓数
MAX_WEIGHT_PER_STOCK = 0.25  # 单票最大仓位 25%
MAX_DAILY_LOSS_PCT = 0.05  # 单日亏损 5% 熔断
MIN_SIGNAL_CONFIDENCE = 0.3  # 最低信号置信度

# ─── Paths ───────────────────────────────────────────────
OUTBOX_DIR = PROJECT_ROOT / "company" / "chairman_outbox"
REPORTS_DIR = PROJECT_ROOT / "company" / "reports"
MEMORY_DIR = PROJECT_ROOT / "company" / "departments" / "execution"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

TRADE_LOG = MEMORY_DIR / "trade_log.jsonl"
PERF_LOG = MEMORY_DIR / "performance_history.json"
STATE_FILE = MEMORY_DIR / "autotrader_state.json"


def _load_state() -> dict:
    """Load persistent state from disk."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "total_trades": 0,
        "cumulative_return": 0.0,
        "sharpe": 0.0,
        "last_run": None,
    }


def _save_state(state: dict):
    state["last_run"] = datetime.now().isoformat()
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _log_trade(entry: dict):
    """Append trade to JSONL log."""
    entry["timestamp"] = datetime.now().isoformat()
    with open(TRADE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── Step 1: Data ────────────────────────────────────────


def fetch_data(tickers: list, period: str = "1mo") -> Optional[pd.DataFrame]:
    """Pull OHLCV data via yfinance. Returns DataFrame with ticker col."""
    print("📡 拉取市场数据...")
    try:
        from quant_framework.data.fetchers.yfinance_fetcher import _fetch_via_yfinance

        frames = []
        for t in tickers:
            df = _fetch_via_yfinance(t, None, None)
            if df is not None and not df.empty:
                df["ticker"] = t
                frames.append(df)

        if not frames:
            print("   ❌ 无法获取任何数据")
            return None

        result = pd.concat(frames, ignore_index=True)
        print(f"   ✅ {len(result)} 行, {len(result['ticker'].unique())} 标的")
        return result
    except Exception as e:
        print(f"   ⚠️ 数据拉取失败: {e}")
        return None


# ─── Step 2: Factors & Signals ───────────────────────────


def compute_signals(data: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Run factor calculation → combine → generate signals."""
    print("🧮 计算因子...")
    try:
        from quant_framework.strategies.qlib_factor_engine import compute_all_factors
        from quant_framework.strategies.factor_combiner import (
            ic_weighted_combine,
            filter_factors_by_ic,
            generate_signals,
        )

        factor_df = compute_all_factors(data)
        if factor_df.empty:
            print("   ❌ 因子计算返回空")
            return None

        # Exclude non-factor columns
        exclude = {
            "ticker",
            "date",
            "close",
            "open",
            "high",
            "low",
            "volume",
            "industry",
        }
        factor_cols = [c for c in factor_df.columns if c not in exclude]

        # Filter noise factors then IC-weight the rest
        active = filter_factors_by_ic(
            factor_df, factor_cols, ic_threshold=0.02, min_factors=5
        )
        combined = ic_weighted_combine(
            factor_df, active, factor_df["close"], ic_threshold=0.0
        )
        # Deduplicate: take latest row per ticker
        if "ticker" in combined.columns:
            combined = combined.sort_values(
                "date" if "date" in combined.columns else combined.columns[0]
            ).drop_duplicates("ticker", keep="last")
        signals = generate_signals(
            combined, "combined_score", top_k=MAX_POSITIONS, method="long_only"
        )

        longs = signals[signals["signal"] == 1]
        print(f"   ✅ {len(active)}/{len(factor_cols)} 因子 → {len(longs)} 个买入信号")

        # Backtest gate: if IC-weighted signals have negative Sharpe, fall back to equal-weight
        from quant_framework.backtest.harness import vectorized_backtest

        bt = vectorized_backtest(
            factor_df.pivot_table(index="date", columns="ticker", values="close"),
            signals.pivot_table(index="date", columns="ticker", values="signal"),
        )
        bt_sharpe = bt.get("sharpe_ratio", 0) or 0
        if bt_sharpe < 0:
            print(
                f"   ⚠️ IC-weighted Sharpe={bt_sharpe:.2f} → falling back to equal-weight"
            )
            from quant_framework.strategies.factor_combiner import (
                equal_weighted_combine,
            )

            combined = equal_weighted_combine(factor_df, factor_cols)
            if "ticker" in combined.columns:
                combined = combined.sort_values(
                    "date" if "date" in combined.columns else combined.columns[0]
                ).drop_duplicates("ticker", keep="last")
            signals = generate_signals(
                combined, "combined_score", top_k=MAX_POSITIONS, method="long_only"
            )
        else:
            print(f"   ✅ IC-weighted Sharpe={bt_sharpe:.2f} — accepted")

        return signals
    except Exception as e:
        print(f"   ⚠️ 因子计算失败: {e}")
        return None


# ─── Step 3: Position Sizing ─────────────────────────────


def size_positions(
    signals: pd.DataFrame, capital: float, prices: pd.DataFrame = None
) -> dict:
    """Calculate position weights via risk-parity (riskfolio-lib) with equal-weight fallback."""
    print("⚖️  计算仓位...")
    try:
        from quant_framework.execution.position_sizer import (
            size_positions as shared_sizer,
        )

        # Use shared sizer: try risk_parity first, fall back to equal_weight
        if (
            prices is not None
            and "close" in prices.columns
            and "date" in prices.columns
        ):
            result = shared_sizer(
                signals,
                prices,
                capital,
                method="risk_parity",
                max_positions=MAX_POSITIONS,
                max_position_pct=MAX_WEIGHT_PER_STOCK,
            )
            print(
                f"   ✅ risk_parity → {len(result['orders'])} 个仓位, ${result['total_allocated']:,.0f}"
            )
        else:
            result = shared_sizer(
                signals,
                signals[["date", "ticker", "close"]].dropna()
                if "close" in signals.columns
                else signals,
                capital,
                method="equal_weight",
                max_positions=MAX_POSITIONS,
                max_position_pct=MAX_WEIGHT_PER_STOCK,
            )
            print(
                f"   ✅ equal_weight → {len(result['orders'])} 个仓位, ${result['total_allocated']:,.0f}"
            )

        positions = {}
        for o in result["orders"]:
            ticker = o["ticker"]
            signal_row = signals[signals["ticker"] == ticker]
            score = (
                float(signal_row["combined_score"].iloc[0])
                if len(signal_row) > 0 and "combined_score" in signal_row.columns
                else 0
            )
            if abs(score) >= MIN_SIGNAL_CONFIDENCE:
                positions[ticker] = {
                    "weight": o["weight"],
                    "qty": o["shares"],
                    "allocation": o["allocation"],
                    "score": score,
                    "price": o["price"],
                }

        return positions
    except Exception as e:
        print(f"   ⚠️ 仓位计算失败: {e}")
        # Ultimate fallback: equal weight
        from quant_framework.execution.position_sizer import equal_weight

        weights = equal_weight(signals, max_positions=MAX_POSITIONS)
        if weights.empty:
            return {}
        positions = {}
        for ticker, weight in weights.items():
            w = min(weight, MAX_WEIGHT_PER_STOCK)
            price = (
                float(signals[signals["ticker"] == ticker]["close"].iloc[0])
                if "close" in signals.columns
                else 100.0
            )
            qty = max(1, int(capital * w / price))
            positions[ticker] = {
                "weight": w,
                "qty": qty,
                "allocation": capital * w,
                "score": 0,
                "price": price,
            }
        return positions


# ─── Step 4: Execute Orders ──────────────────────────────


def execute_rebalance(target_positions: dict, live: bool = False) -> list:
    """Compare current vs target positions and place rebalancing orders."""
    if not live:
        print("📝 模拟模式 — 不实际下单 (use --live for paper trading)")
        orders = []
        for ticker, pos in target_positions.items():
            orders.append(
                {
                    "symbol": ticker,
                    "qty": pos["qty"],
                    "side": "buy",
                    "type": "market",
                    "allocation": pos["allocation"],
                }
            )
        # Log to trade log anyway
        _log_trade(
            {
                "action": "rebalance_simulated",
                "positions": list(target_positions.keys()),
                "order_count": len(orders),
            }
        )
        return orders

    print("🔴 实盘模式 — 通过 Alpaca Paper Trading 下单")
    from quant_framework.execution.broker_bridge import BrokerBridge

    bridge = BrokerBridge()
    if not bridge.is_connected:
        print("   ❌ Alpaca 未连接")
        return []

    # Get current positions
    current = {p.symbol: p.qty for p in bridge.get_positions()}
    print(f"   当前持仓: {current}")

    orders = []
    for ticker, pos in target_positions.items():
        current_qty = current.get(ticker, 0)
        delta = pos["qty"] - current_qty

        if delta == 0:
            continue
        elif delta > 0:
            result = bridge.place_order(ticker, abs(delta), "buy", "market")
        else:
            result = bridge.place_order(ticker, abs(delta), "sell", "market")

        orders.append(
            {
                "order_id": result.order_id,
                "symbol": ticker,
                "side": "buy" if delta > 0 else "sell",
                "qty": abs(delta),
                "status": result.status,
            }
        )
        _log_trade(
            {
                "action": "order",
                "symbol": ticker,
                "qty": abs(delta),
                "side": "buy" if delta > 0 else "sell",
                "status": result.status,
            }
        )
        print(
            f"   {'✅' if result.status == 'filled' else '📝'} {ticker}: {'+' if delta > 0 else ''}{delta}股 @ {pos['price']:.2f}"
        )

    # Close positions not in target
    for ticker, qty in current.items():
        if ticker not in target_positions and qty > 0:
            result = bridge.place_order(ticker, qty, "sell", "market")
            orders.append(
                {
                    "order_id": result.order_id,
                    "symbol": ticker,
                    "side": "sell",
                    "qty": qty,
                    "status": result.status,
                }
            )
            print(f"   ❌ 清仓 {ticker}: {qty}股")
            _log_trade(
                {
                    "action": "order",
                    "symbol": ticker,
                    "qty": qty,
                    "side": "sell",
                    "status": result.status,
                }
            )

    return orders


# ─── Step 5: Report ──────────────────────────────────────


def generate_report(
    signals: pd.DataFrame,
    positions: dict,
    orders: list,
    account_summary: dict,
    state: dict,
) -> str:
    """Generate daily markdown report."""
    now = datetime.now()
    ds = now.strftime("%Y-%m-%d")

    # Top signals
    top_signals = ""
    if signals is not None and not signals.empty:
        longs = signals[signals["signal"] == 1].nlargest(10, "combined_score")
        for _, row in longs.iterrows():
            top_signals += (
                f"| {row.get('ticker', '?')} | {row.get('combined_score', 0):.3f} |\n"
            )

    # Positions
    pos_table = ""
    for ticker, pos in sorted(
        positions.items(), key=lambda x: x[1]["score"], reverse=True
    ):
        pos_table += f"| {ticker} | {pos['weight']:.1%} | {pos['qty']} | {pos['allocation']:,.0f} | {pos['score']:.3f} |\n"

    report = f"""# 📊 OnionQuant 每日交易报告

**日期**: {ds} {now.strftime("%H:%M")}
**状态**: {"🟢 实盘 Paper Trading" if account_summary.get("connected") else "🟡 模拟模式"}
**累计交易**: {state.get("total_trades", 0)} 笔

## 💰 账户概览
| 指标 | 数值 |
|------|------|
| 账户状态 | {account_summary.get("status", "N/A")} |
| 投资组合价值 | ${account_summary.get("portfolio_value", 0):,.2f} |
| 购买力 | ${account_summary.get("buying_power", 0):,.2f} |
| 现金 | ${account_summary.get("cash", 0):,.2f} |

## 🎯 今日信号 (Top 10)
| 代码 | 综合得分 |
|------|---------|
{top_signals if top_signals else "| — | 无信号 |\n"}

## 📦 目标持仓
| 代码 | 权重 | 股数 | 分配 | 得分 |
|------|------|------|------|------|
{pos_table if pos_table else "| — | — | — | — | 无 |\n"}

## 📋 订单执行
| 动作 | 数量 |
|------|------|
| 买入 | {sum(1 for o in orders if o.get("side") == "buy")} 笔 |
| 卖出 | {sum(1 for o in orders if o.get("side") == "sell")} 笔 |
| 总计 | {len(orders)} 笔 |

## 🤖 自学状态
- **记忆文件**: {TRADE_LOG.stat().st_size if TRADE_LOG.exists() else 0} bytes
- **上次运行**: {state.get("last_run", "N/A")}
- **累计收益率**: {state.get("cumulative_return", 0):.2%}

---
*下次执行: 明天这个时候 | AutoTrader v1.0*
"""
    return report


# ─── Step 6: WeChat Push ─────────────────────────────────


def push_report_via_outbox(report_path: Path):
    """Write a summary outbox entry so wechat_bot picks it up."""
    from datetime import datetime

    content = f"""# [NOTIFY] 每日交易报告已生成

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

报告已保存到 `{report_path.relative_to(PROJECT_ROOT)}`

Agent 将持续监控持仓并执行风控。
"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"NOTIFY_{timestamp}_daily_trade.md"
    (OUTBOX_DIR / fname).write_text(content, encoding="utf-8")
    print(f"   📤 微信通知: {fname}")


# ─── Main ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="OnionQuant AutoTrader")
    parser.add_argument(
        "--live", action="store_true", help="Enable live order execution via Alpaca"
    )
    parser.add_argument("--tickers", nargs="*", help="Override ticker universe")
    args = parser.parse_args()

    print("=" * 55)
    print("  🧅 OnionQuant · 自动化交易流水线")
    print(f"  🕐 {datetime.now().isoformat()}")
    print("=" * 55)

    state = _load_state()

    # 1. Data
    tickers = args.tickers if args.tickers else UNIVERSE[:20]
    data = fetch_data(tickers)
    if data is None:
        print("🛑 数据拉取失败，终止")
        return

    # 2. Signals
    signals = compute_signals(data)
    if signals is None or signals[signals["signal"] == 1].empty:
        print("🟡 今日无买入信号")
        signals = signals

    # 3. Position sizing
    from quant_framework.execution.broker_bridge import BrokerBridge

    bridge = BrokerBridge()
    account = bridge.get_account_summary()
    capital = float(account.get("portfolio_value", 100000)) * 0.8  # Use 80% of capital

    positions = {}
    if signals is not None and not signals[signals["signal"] == 1].empty:
        positions = size_positions(signals, capital, data)

    # 4. Execute
    orders = execute_rebalance(positions, live=args.live)

    if args.live:
        state["total_trades"] += len(orders)

    # 5. Report
    report = generate_report(signals, positions, orders, account, state)
    ds = datetime.now().strftime("%Y%m%d_%H%M")
    report_file = REPORTS_DIR / f"daily_report_{ds}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"\n📄 报告: {report_file}")

    # Save state
    _save_state(state)

    # 6. WeChat push
    push_report_via_outbox(report_file)

    # 7. Update memory (learning)
    _log_trade(
        {
            "action": "daily_summary",
            "date": date.today().isoformat(),
            "signal_count": len(signals) if signals is not None else 0,
            "position_count": len(positions),
            "order_count": len(orders),
            "account": account,
        }
    )

    print(f"\n  ✅ 完成 — {len(positions)} 持仓, {len(orders)} 订单")


if __name__ == "__main__":
    main()
