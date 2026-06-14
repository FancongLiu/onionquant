import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Starting point
shares = 102
cost = 928.63
equity = 33282.54
price = 939.86
loan = shares * price - equity

# Margin: 65% req = 35% equity needed, leverage multiplier = 1/0.35
MARGIN = 0.35

# Pyramid steps
steps = [
    (960, 6),
    (980, 6),
    (1000, 5),
    (1030, 5),
    (1060, 5),
    (1089, 5),
    (1120, 4),
    (1150, 3),
]

print("MU 浮盈加仓完整链 (起点: 102股 @ $928.63, 净值 $33,283)")
print("=" * 70)
print(f"{'触发价':>6} {'买':>3} {'累计股':>5} {'市值':>10} {'净值':>10} {'贷款':>10} {'杠杆':>5} {'买力验证':>10}")
print("-" * 70)

prev_equity = equity
for px, buy in steps:
    # Calculate equity at this price BEFORE buying
    mv_before = shares * px
    equity_before = mv_before - loan

    # Available buying power
    added_equity = equity_before - prev_equity
    buying_power = added_equity / MARGIN if added_equity > 0 else 0
    max_buy = int(buying_power / px) if px > 0 else 0

    # Execute buy
    shares += buy
    loan += buy * px  # new shares bought on margin
    mv = shares * px
    equity_after = mv - loan
    leverage = mv / equity_after if equity_after > 0 else 999

    ok = "OK" if buy <= max_buy else f"NEED {buy-max_buy} more"

    print(f"${px:>5} {buy:>3}股 {shares:>5}股 ${mv:>8,.0f} ${equity_after:>8,.0f} ${loan:>8,.0f} {leverage:>4.1f}x 可买{max_buy}股 {ok}")
    prev_equity = equity_after

# Final summary
print()
print(f"如果全部触发: {shares}股 MU, 市值 ${shares*steps[-1][0]:,.0f}, 净值 ${equity_after:,.0f}")
print(f"起点净值 $33,283 → 终点净值 ${equity_after:,.0f} (+{(equity_after/33282.54-1)*100:.0f}%)")
print(f"MU 从 $940 → ${steps[-1][0]} (+{(steps[-1][0]/940-1)*100:.0f}%)")
