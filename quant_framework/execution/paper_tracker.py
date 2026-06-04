"""
Paper Trading Performance Tracker — 独立的虚拟交易追踪系统。

不依赖 Alpaca。所有交易历史和绩效存在本地 JSON，
前端通过 /api/paper_performance 拉取展示。

同步董事长实际持仓 + 量化系统建议信号 → 模拟执行 → 追踪绩效。
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TRACKER_DIR = PROJECT_ROOT / "company" / "departments" / "execution"
TRACKER_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = TRACKER_DIR / "paper_portfolio.json"
HISTORY_FILE = TRACKER_DIR / "paper_performance_history.json"


class PaperPortfolio:
    """虚拟投资组合追踪器。"""

    def __init__(self):
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {
            "created_at": datetime.now().isoformat(),
            "initial_capital": 100_000.0,
            "cash": 100_000.0,
            "positions": {},  # {ticker: {shares, avg_cost, current_price, market_value, unrealized_pl, unrealized_pl_pct}}
            "trade_history": [],
            "total_trades": 0,
            "total_realized_pl": 0.0,
        }

    def save(self):
        STATE_FILE.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get_market_price(self, ticker: str) -> Optional[float]:
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            info = tk.fast_info
            return float(info.get("lastPrice", 0)) or None
        except Exception:
            return None

    def sync_chairman_position(self, ticker: str, shares: int, cost_basis: float):
        """同步董事长实际持仓到虚拟盘。"""
        price = self.get_market_price(ticker)
        if price is None:
            price = cost_basis

        market_value = shares * price
        cost_value = shares * cost_basis

        # Adjust cash: sell existing position first if needed
        old = self.state["positions"].get(ticker, {})
        if old:
            old_value = old.get("shares", 0) * old.get("avg_cost", 0)
            self.state["cash"] += old_value

        self.state["cash"] -= cost_value

        self.state["positions"][ticker] = {
            "shares": shares,
            "avg_cost": cost_basis,
            "current_price": price,
            "market_value": market_value,
            "unrealized_pl": market_value - cost_value,
            "unrealized_pl_pct": round((price / cost_basis - 1) * 100, 2),
            "synced_at": datetime.now().isoformat(),
        }
        self.save()

    def execute_trade(
        self,
        ticker: str,
        action: str,
        shares: int,
        price: Optional[float] = None,
        reason: str = "",
    ):
        """执行虚拟交易。action: buy/sell"""
        if price is None:
            price = self.get_market_price(ticker)
        if price is None:
            return {"error": f"Cannot get price for {ticker}"}

        total = shares * price

        if action == "buy":
            if total > self.state["cash"]:
                return {
                    "error": f"Insufficient cash: need {total}, have {self.state['cash']}"
                }
            self.state["cash"] -= total

            pos = self.state["positions"].get(
                ticker, {"shares": 0, "avg_cost": 0, "market_value": 0}
            )
            new_shares = pos["shares"] + shares
            new_cost = (pos["avg_cost"] * pos["shares"] + total) / new_shares
            self.state["positions"][ticker] = {
                "shares": new_shares,
                "avg_cost": round(new_cost, 2),
                "current_price": price,
                "market_value": new_shares * price,
                "unrealized_pl": new_shares * (price - new_cost),
                "unrealized_pl_pct": round((price / new_cost - 1) * 100, 2),
            }

        elif action == "sell":
            pos = self.state["positions"].get(ticker, {"shares": 0})
            if pos["shares"] < shares:
                return {
                    "error": f"Insufficient shares: have {pos['shares']}, need {shares}"
                }

            avg_cost = pos["avg_cost"]
            realized_pl = shares * (price - avg_cost)
            self.state["total_realized_pl"] += realized_pl
            self.state["cash"] += total

            remaining = pos["shares"] - shares
            if remaining > 0:
                self.state["positions"][ticker] = {
                    **pos,
                    "shares": remaining,
                    "market_value": remaining * price,
                    "unrealized_pl": remaining * (price - avg_cost),
                }
            else:
                self.state["positions"].pop(ticker, None)

        trade = {
            "timestamp": datetime.now().isoformat(),
            "ticker": ticker,
            "action": action,
            "shares": shares,
            "price": price,
            "total": total,
            "reason": reason,
        }
        self.state["trade_history"].append(trade)
        self.state["total_trades"] += 1
        self.save()
        return trade

    def mark_to_market(self):
        """更新所有持仓的市价。"""
        for ticker, pos in self.state["positions"].items():
            price = self.get_market_price(ticker)
            if price:
                pos["current_price"] = price
                pos["market_value"] = price * pos["shares"]
                pos["unrealized_pl"] = (
                    pos["market_value"] - pos["avg_cost"] * pos["shares"]
                )
                pos["unrealized_pl_pct"] = round((price / pos["avg_cost"] - 1) * 100, 2)
        self.save()

    def get_summary(self) -> dict:
        """获取投资组合摘要（前端用）。"""
        self.mark_to_market()
        total_equity = self.state["cash"]
        total_pl = self.state["total_realized_pl"]
        positions_detail = []

        for ticker, pos in self.state["positions"].items():
            total_equity += pos["market_value"]
            total_pl += pos.get("unrealized_pl", 0)
            positions_detail.append(
                {
                    "ticker": ticker,
                    "shares": pos["shares"],
                    "avg_cost": pos["avg_cost"],
                    "current_price": pos["current_price"],
                    "market_value": round(pos["market_value"], 2),
                    "unrealized_pl": round(pos.get("unrealized_pl", 0), 2),
                    "unrealized_pl_pct": pos.get("unrealized_pl_pct", 0),
                }
            )

        initial = self.state["initial_capital"]
        return {
            "initial_capital": initial,
            "total_equity": round(total_equity, 2),
            "cash": round(self.state["cash"], 2),
            "total_return_pct": round((total_equity / initial - 1) * 100, 2),
            "total_realized_pl": round(self.state["total_realized_pl"], 2),
            "total_unrealized_pl": round(total_pl - self.state["total_realized_pl"], 2),
            "positions": positions_detail,
            "total_trades": self.state["total_trades"],
            "last_updated": datetime.now().isoformat(),
        }

    def record_daily_snapshot(self):
        """记录每日快照到历史。"""
        history = []
        if HISTORY_FILE.exists():
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

        summary = self.get_summary()
        today = date.today().isoformat()

        # Don't duplicate same day
        if history and history[-1].get("date") == today:
            history[-1] = {"date": today, **summary}
        else:
            history.append({"date": today, **summary})

        HISTORY_FILE.write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return history


# ─── CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Performance Tracker")
    parser.add_argument(
        "--sync",
        nargs=3,
        metavar=("TICKER", "SHARES", "COST"),
        help="Sync chairman position to paper portfolio",
    )
    parser.add_argument(
        "--trade",
        nargs=4,
        metavar=("TICKER", "ACTION", "SHARES", "REASON"),
        help="Execute a virtual trade",
    )
    parser.add_argument(
        "--summary", action="store_true", help="Print portfolio summary"
    )
    parser.add_argument("--snapshot", action="store_true", help="Record daily snapshot")
    args = parser.parse_args()

    pf = PaperPortfolio()

    if args.sync:
        ticker, shares, cost = args.sync
        pf.sync_chairman_position(ticker, int(shares), float(cost))
        print(f"Synced {ticker}: {shares} shares @ {cost}")

    if args.trade:
        ticker, action, shares, reason = args.trade
        result = pf.execute_trade(ticker, action, int(shares), reason=reason)
        print(result)

    if args.summary:
        summary = pf.get_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.snapshot:
        pf.record_daily_snapshot()
        print("Daily snapshot recorded")
