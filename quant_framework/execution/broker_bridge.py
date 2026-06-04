"""Broker bridge — paper trading connector (Alpaca Markets / IBKR).

T867: Live trading bridge skeleton. Paper-only by default.
Credentials from .env: ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER (true/false).

Usage:
    bridge = BrokerBridge()
    bridge.place_order("AAPL", 10, "buy", "market")
    positions = bridge.get_positions()
    orders = bridge.get_orders(status="open")
"""

import os
import logging
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logger = logging.getLogger("quant_framework.execution.broker_bridge")

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop", "stop_limit"]
TimeInForce = Literal["day", "gtc", "opg", "cls", "ioc", "fok"]


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    status: str
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    submitted_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None


@dataclass
class Position:
    symbol: str
    qty: float
    market_value: Optional[float] = None
    avg_entry_price: Optional[float] = None
    unrealized_pl: Optional[float] = None


class BrokerBridge:
    """Paper trading broker interface.

    Defaults to Alpaca Markets paper trading. Credentials loaded from env vars.
    Falls back to a no-op recorder if no credentials are configured.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.paper = paper if self.api_key else True
        self._client = None
        self._connected = False
        self._order_log: List[Dict] = []  # fallback recorder

        if self.api_key and self.secret_key:
            self._connect()
        else:
            logger.info("BrokerBridge: no Alpaca credentials — using recorder mode")

    def _connect(self) -> bool:
        """Initialize Alpaca TradingClient for paper trading."""
        try:
            from alpaca.trading.client import TradingClient

            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            # Verify connectivity
            account = self._client.get_account()
            self._connected = True
            logger.info(
                f"BrokerBridge connected (paper={self.paper}): "
                f"status={account.status}, buying_power=${float(account.buying_power):,.0f}"
            )
            return True
        except Exception as e:
            logger.warning(f"BrokerBridge connection failed: {e}")
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide = "buy",
        order_type: OrderType = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = "day",
    ) -> OrderResult:
        """Place an order. Falls back to recording if not connected."""
        if not self.is_connected:
            return self._record_order(symbol, qty, side, order_type)

        try:
            from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
            from alpaca.trading.enums import (
                OrderSide as AlpacaSide,
                TimeInForce as AlpacaTIF,
            )

            side_enum = AlpacaSide.BUY if side == "buy" else AlpacaSide.SELL

            if order_type == "market":
                req = MarketOrderRequest(
                    symbol=symbol.upper(),
                    qty=qty,
                    side=side_enum,
                    time_in_force=AlpacaTIF.DAY,
                )
            elif order_type == "limit" and limit_price is not None:
                req = LimitOrderRequest(
                    symbol=symbol.upper(),
                    qty=qty,
                    side=side_enum,
                    limit_price=limit_price,
                    time_in_force=AlpacaTIF.DAY,
                )
            else:
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    order_type=order_type,
                    status="rejected",
                    error=f"Unsupported order type or missing price: {order_type}",
                )

            resp = self._client.submit_order(req)
            logger.info(f"Order placed: {resp.id} {side} {qty} {symbol} @ {order_type}")
            return OrderResult(
                order_id=str(resp.id),
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                status=resp.status,
                filled_qty=float(resp.filled_qty or 0),
                filled_avg_price=float(resp.filled_avg_price)
                if resp.filled_avg_price
                else None,
            )
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                status="error",
                error=str(e),
            )

    def get_positions(self) -> List[Position]:
        """Get current positions."""
        if not self.is_connected:
            return []

        try:
            positions = self._client.get_all_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    market_value=float(p.market_value) if p.market_value else None,
                    avg_entry_price=float(p.avg_entry_price)
                    if p.avg_entry_price
                    else None,
                    unrealized_pl=float(p.unrealized_pl) if p.unrealized_pl else None,
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"get_positions failed: {e}")
            return []

    def get_orders(self, status: str = "open", limit: int = 50) -> List[OrderResult]:
        """Query orders by status (open, closed, all)."""
        if not self.is_connected:
            return self._order_log  # type: ignore

        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            status_map = {
                "open": QueryOrderStatus.OPEN,
                "closed": QueryOrderStatus.CLOSED,
                "all": QueryOrderStatus.ALL,
            }
            req = GetOrdersRequest(
                status=status_map.get(status, QueryOrderStatus.OPEN), limit=limit
            )
            orders = self._client.get_orders(req)
            return [
                OrderResult(
                    order_id=str(o.id),
                    symbol=o.symbol,
                    side=o.side.value,
                    qty=float(o.qty),
                    order_type=o.type.value,
                    status=o.status,
                )
                for o in orders
            ]
        except Exception as e:
            logger.error(f"get_orders failed: {e}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID."""
        if not self.is_connected:
            return False
        try:
            self._client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def get_account_summary(self) -> Dict:
        """Get account summary (buying power, portfolio value, etc.)."""
        if not self.is_connected:
            return {"connected": False, "mode": "recorder"}

        try:
            acc = self._client.get_account()
            return {
                "connected": True,
                "mode": "paper" if self.paper else "live",
                "status": acc.status,
                "buying_power": float(acc.buying_power),
                "portfolio_value": float(acc.portfolio_value),
                "cash": float(acc.cash),
                "equity": float(acc.equity),
                "daytrade_count": acc.daytrade_count,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def _record_order(
        self, symbol: str, qty: float, side: str, order_type: str
    ) -> OrderResult:
        """Fallback: record order locally without execution."""
        import uuid

        oid = str(uuid.uuid4())[:8]
        entry = {
            "order_id": oid,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "status": "recorded",
            "time": datetime.now().isoformat(),
        }
        self._order_log.append(entry)
        logger.info(f"Order recorded (no broker): {oid} {side} {qty} {symbol}")
        return OrderResult(
            order_id=oid,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="recorded",
        )


if __name__ == "__main__":
    bridge = BrokerBridge()
    print(f"Connected: {bridge.is_connected}")
    summary = bridge.get_account_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if not bridge.is_connected:
        r = bridge.place_order("AAPL", 10, "buy", "market")
        print(f"Test order: {r.order_id} {r.status}")
