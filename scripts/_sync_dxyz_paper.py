import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quant_framework.execution.broker_bridge import BrokerBridge

bridge = BrokerBridge()
print("Connected:", bridge.is_connected)

r = bridge.place_order("DXYZ", 585, "buy", "market")
print("DXYZ order:", r.status, r.error or "")

positions = bridge.get_positions()
print("Positions:", len(positions))
for p in positions:
    print(f"  {p.symbol}: {p.qty} shares")

account = bridge.get_account_summary()
print("Portfolio value:", account.get("portfolio_value"))
print("Cash:", account.get("cash"))
