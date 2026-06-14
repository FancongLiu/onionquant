#!/usr/bin/env python3
"""
MU Position Calculator - Stop-Loss Ladder, Pyramid Add-On, Trailing Stop
109 shares MU @ $995.74 cost, ~$39,500 equity, IBKR broker
Output: EXACT IBKR order tickets with verified math.
"""

import io
import math
import sys

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# === CONSTANTS ===
SHARES = 109
COST_BASIS = 995.74
CURRENT_PRICE = 995.00
EQUITY = 39500.0
MARGIN_REQ = 0.65          # 65% margin requirement (35% equity needed)
MAINTENANCE = 0.35         # 35% maintenance margin
MAX_LEVERAGE = 1 / 0.35    # 2.857x
ATR = 86.0
ATR_PCT = ATR / CURRENT_PRICE
MA_20 = 880.0
TARGET_EQ_STOP = 0.42      # Target equity ratio after stop-loss
TARGET_EQ_PYRAMID = 0.37   # Minimum equity ratio after pyramid add
PYRAMID_DEPLOY = 0.70      # Use 70% of max buying power
TRAIL_PCT = 0.10           # 10% trail from peak

FOMC_CLOSE = "2026-06-15"
EARNINGS_CLOSE = "2026-06-23"

# Derived
market_value = SHARES * CURRENT_PRICE
loan = market_value - EQUITY
equity_ratio = EQUITY / market_value
leverage = market_value / EQUITY

print("=" * 80)
print("SECTION 1: EXACT POSITION MATH")
print("=" * 80)
print(f"Shares:       {SHARES}")
print(f"Cost Basis:   ${COST_BASIS:,.2f}")
print(f"Current Px:   ${CURRENT_PRICE:,.2f}")
print(f"Market Value: ${market_value:,.2f}")
print(f"Equity:       ${EQUITY:,.2f}")
print(f"Loan:         ${loan:,.2f}")
print(f"Equity Ratio: {equity_ratio*100:.2f}%")
print(f"Leverage:     {leverage:.3f}x (Max: {MAX_LEVERAGE:.3f}x)")
print(f"Daily ATR:    ${ATR} ({ATR_PCT*100:.2f}%)")
print()

# Margin call prices
print("--- Margin Call Prices ---")
for maint in [0.25, 0.30, 0.35]:
    p_call = loan / (SHARES * (1 - maint))
    drop = (CURRENT_PRICE - p_call) / CURRENT_PRICE * 100
    print(f"  {maint*100:.0f}% Maint: ${p_call:,.2f} (drop {drop:.1f}% / {(CURRENT_PRICE-p_call)/ATR:.2f} ATR)")

p_call_35 = loan / (SHARES * (1 - 0.35))
dist_dollar = CURRENT_PRICE - p_call_35
dist_atr = dist_dollar / ATR
print(f"\n  >>> DISTANCE TO 35% MARGIN CALL: ${dist_dollar:,.2f} = {dist_atr:.2f} ATR <<<")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def shares_to_sell(cur_shares, price, cur_loan, target_ratio):
    """How many shares to sell to reach target equity ratio."""
    equity = cur_shares * price - cur_loan
    if equity <= 0:
        return cur_shares
    # (cur_shares*P - cur_loan) / ((cur_shares - S)*P) = target_ratio
    # S = (cur_loan - cur_shares*P*(1-target_ratio)) / (target_ratio * P)
    num = cur_loan - cur_shares * price * (1 - target_ratio)
    den = target_ratio * price
    if den <= 0:
        return cur_shares
    s = num / den
    s = math.ceil(s)
    s = max(0, min(s, cur_shares))
    return s

def verify_sell(cur_shares, price, cur_loan, sell_n):
    new_shares = cur_shares - sell_n
    new_loan = cur_loan - sell_n * price
    new_mv = new_shares * price
    new_eq = new_mv - new_loan
    new_ratio = new_eq / new_mv if new_mv > 0 else 0
    return new_shares, new_loan, new_mv, new_eq, new_ratio

def max_pyramid_add(cur_shares, price, cur_loan, initial_equity):
    """Calculate max shares to add via pyramid, respecting both buying power and equity ratio."""
    mv_before = cur_shares * price
    equity_before = mv_before - cur_loan
    gain = equity_before - initial_equity
    if gain <= 0:
        return 0, 0.0

    # Max additional MV from gain
    max_add_mv = gain / MAINTENANCE
    deploy_mv = max_add_mv * PYRAMID_DEPLOY
    raw_add = math.floor(deploy_mv / price)

    # Equity ratio constraint after adding S shares:
    # New equity = equity_before + S*P*0.35
    # New MV = (cur_shares + S)*P
    # (equity_before + 0.35*S*P) / ((cur_shares + S)*P) >= TARGET_EQ_PYRAMID
    # equity_before + 0.35*S*P >= TARGET_EQ_PYRAMID * (cur_shares + S)*P
    # equity_before - TARGET_EQ_PYRAMID*cur_shares*P >= S*P*(TARGET_EQ_PYRAMID - 0.35)
    # S <= (equity_before - TARGET_EQ_PYRAMID*cur_shares*P) / (P*(TARGET_EQ_PYRAMID - 0.35))
    den2 = price * (TARGET_EQ_PYRAMID - MAINTENANCE)  # 0.37 - 0.35 = 0.02
    if den2 <= 0:
        max_eq = float('inf')
    else:
        num2 = equity_before - TARGET_EQ_PYRAMID * cur_shares * price
        max_eq = max(0, math.floor(num2 / den2))

    actual = min(raw_add, max_eq) if max_eq > 0 else 0
    return actual, gain


# ============================================================
# SECTION 2: STOP-LOSS LADDER
# ============================================================
print("\n" + "=" * 80)
print("SECTION 2: STOP-LOSS LADDER (Target: 42% equity ratio after each stop)")
print("=" * 80)

# Tier design rationale:
# - Tier 1 must be ABOVE 35% margin call ($973.25) but give breathing room
# - ATR spacing: need at least 0.5-1 ATR between tiers to avoid serial false triggers
# - But we're only 0.25 ATR from margin call, so Tier 1 must be tight
# - Use $980 as Tier 1 (above $973 margin call, ~0.17 ATR from current)

stop_design = [
    (980, "Tier 1 - Safety Stop (above 35% margin call at $973)"),
    (935, "Tier 2 - Trend Confirmation"),
    (880, "Tier 3 - 20MA Hard Floor (last defense)"),
]

cur_s = SHARES
cur_l = loan
stop_results = []

for price, label in stop_design:
    mv_before = cur_s * price
    eq_before = mv_before - cur_l
    ratio_before = eq_before / mv_before if mv_before > 0 else 0

    s = shares_to_sell(cur_s, price, cur_l, TARGET_EQ_STOP)
    new_s, new_l, new_mv, new_eq, new_ratio = verify_sell(cur_s, price, cur_l, s)

    drop = (CURRENT_PRICE - price) / CURRENT_PRICE * 100
    prev_px = stop_results[-1]['price'] if stop_results else CURRENT_PRICE
    atr_dist = (prev_px - price) / ATR

    # Check if margin call would trigger before this tier
    mc_price = cur_l / (cur_s * (1 - 0.35))
    mc_warning = f" *** MARGIN CALL AT ${mc_price:,.2f} - STOP IS BELOW MC! ***" if price < mc_price else ""

    print(f"{label}:")
    print(f"  Trigger: ${price:,.2f} ({drop:.1f}% drop, {atr_dist:.2f} ATR from prev)")
    print(f"  Before:  {cur_s} sh, MV ${mv_before:,.0f}, Eq ${eq_before:,.0f}, Ratio {ratio_before*100:.2f}%")
    print(f"  Action:  SELL {s} sh @ ${price:,.2f}")
    print(f"  After:   {new_s} sh, Loan ${new_l:,.0f}, Eq Ratio {new_ratio*100:.2f}%{mc_warning}")
    print()

    stop_results.append({
        'price': price, 'label': label, 'drop': drop, 'atr_dist': atr_dist,
        'shares_before': cur_s, 'ratio_before': ratio_before,
        'sell': s, 'shares_after': new_s, 'loan_after': new_l,
        'eq_after': new_eq, 'ratio_after': new_ratio
    })
    cur_s, cur_l = new_s, new_l

# ============================================================
# SECTION 3: PYRAMID ADD-ON
# ============================================================
print("=" * 80)
print("SECTION 3: PYRAMID ADD-ON (Formula: unrealized_gain / 0.35 * 70%)")
print("=" * 80)
print(f"Min equity ratio after add: {TARGET_EQ_PYRAMID*100:.0f}%")
print("Start from: $1,050+")
print()

pyramid_prices = [1050, 1090, 1130, 1170, 1210, 1250]
pyr_cur_s = SHARES
pyr_cur_l = loan
pyramid_results = []

for price in pyramid_prices:
    mv_before = pyr_cur_s * price
    eq_before = mv_before - pyr_cur_l
    ratio_before = eq_before / mv_before if mv_before > 0 else 0

    add_n, gain = max_pyramid_add(pyr_cur_s, price, pyr_cur_l, EQUITY)

    if add_n > 0:
        add_mv = add_n * price
        add_loan = add_n * price * (1 - MAINTENANCE)
        new_s = pyr_cur_s + add_n
        new_l = pyr_cur_l + add_loan
        new_mv = new_s * price
        new_eq = new_mv - new_l
        new_ratio = new_eq / new_mv if new_mv > 0 else 0
        limit_str = "(buying power limited)" if add_n < gain/MAINTENANCE*PYRAMID_DEPLOY/price else ""
    else:
        add_n = 0
        new_s, new_l, new_mv, new_eq, new_ratio = pyr_cur_s, pyr_cur_l, mv_before, eq_before, ratio_before
        limit_str = "(no buying power)"

    gain_pct = (price - CURRENT_PRICE) / CURRENT_PRICE * 100

    print(f"--- Pyramid @ ${price} ({gain_pct:+.1f}% from entry) ---")
    print(f"  Before: {pyr_cur_s} sh, MV ${mv_before:,.0f}, Eq ${eq_before:,.0f}, Ratio {ratio_before*100:.2f}%")
    print(f"  Unrealized Gain: ${gain:,.0f}")
    if add_n > 0:
        print(f"  Action: BUY {add_n} sh @ ${price} (+${add_mv:,.0f} MV, +${add_loan:,.0f} loan) {limit_str}")
        print(f"  After:  {new_s} sh, MV ${new_mv:,.0f}, Loan ${new_l:,.0f}, Eq Ratio {new_ratio*100:.2f}%")
    else:
        print(f"  Action: NO ADD {limit_str}")
    print()

    pyramid_results.append({
        'price': price, 'shares_before': pyr_cur_s, 'ratio_before': ratio_before,
        'gain': gain, 'add': add_n, 'shares_after': new_s,
        'loan_after': new_l, 'eq_after': new_eq, 'ratio_after': new_ratio,
        'gain_pct': gain_pct
    })

    # Update for next tier (accumulate)
    pyr_cur_s = new_s
    pyr_cur_l = new_l

# ============================================================
# SECTION 4: TRAILING STOP
# ============================================================
print("=" * 80)
print("SECTION 4: TRAILING STOP (10% from peak, hard floor at 37% equity)")
print("=" * 80)

# The hard floor is the price at which equity ratio = 37%.
# At current position: P_floor = loan / (0.63 * SHARES)
hf_current = loan / (0.63 * SHARES)
print(f"Current 37% Hard Floor: ${hf_current:,.2f}")
print(f"Current Price:          ${CURRENT_PRICE:,.2f}")
if hf_current > CURRENT_PRICE:
    print(f"  >>> NOTE: Hard floor (${hf_current:,.2f}) is ABOVE current price.")
    print(f"  >>> Position is already below 37% equity ratio (at {equity_ratio*100:.2f}%).")
    print("  >>> Hard floor is MOOT - already breached. Trail stop takes precedence.")
print()

print(f"{'Peak':>7}  {'10% Trail':>10}  {'37% HardFlr':>11}  {'Active Stop':>11}  {'Shares':>7}  {'Loan':>12}")
print("-" * 75)

# Track cumulative state through peaks
ts_s = SHARES
ts_l = loan

# Starting peak = current price
peaks_and_stops = []

for i, peak in enumerate([CURRENT_PRICE] + pyramid_prices):
    trail = peak * (1 - TRAIL_PCT)
    hf = ts_l / (0.63 * ts_s) if ts_s > 0 else 0
    active = max(trail, hf)

    print(f"${peak:>6,.0f}  ${trail:>9,.2f}  ${hf:>10,.2f}  ${active:>10,.2f}  {ts_s:>7}  ${ts_l:>11,.0f}")

    peaks_and_stops.append({
        'peak': peak, 'trail_stop': trail, 'hard_floor': hf,
        'active_stop': active, 'shares': ts_s, 'loan': ts_l
    })

    # If this is a pyramid tier, apply the add for next peak
    if peak in pyramid_prices and peak > CURRENT_PRICE:
        for pr in pyramid_results:
            if pr['price'] == peak and pr['add'] > 0:
                ts_s += pr['add']
                ts_l += pr['add'] * peak * (1 - MAINTENANCE)
                break

print()

# Summary of trailing stop logic
print("Trailing Stop Rules:")
print(f"  1. Trail = Peak * {(1-TRAIL_PCT)*100:.0f}%")
print("  2. Hard Floor = price where equity ratio = 37%")
print("  3. Active Stop = max(Trail, Hard Floor)")
print("  4. Update peak after each pyramid fill")
print("  5. If price closes below Active Stop: trigger stop-loss ladder")

# ============================================================
# SECTION 5: PRE-FOMC ADJUSTMENT
# ============================================================
print("\n" + "=" * 80)
print(f"SECTION 5: PRE-FOMC ADJUSTMENT (Close {FOMC_CLOSE})")
print("=" * 80)
print()
print("FOMC = elevated volatility, possible gap risk.")
print()
print("RECOMMENDED ADJUSTMENTS:")
print()
print("1. TIGHTEN STOP-LOSS LADDER:")
print("   - Raise Tier 1 from $980 to $985 (wider margin-call buffer)")
print("   - Reduce Tier spacing from ~$45 to ~$55 (post-FOMC volatility)")
print("   - Consider 7% trailing stop instead of 10% for duration of FOMC week")
print()
print("2. HALT PYRAMID ADDS:")
print("   - Cancel all GTC pyramid orders before FOMC close")
print("   - Re-activate after first post-FOMC daily close confirms direction")
print()
print("3. PRE-FOMC DELEVERAGING (optional, if concerned):")
for p in [990, 995, 1000]:
    s = shares_to_sell(SHARES, p, loan, 0.45)
    ns, nl, nmv, neq, nr = verify_sell(SHARES, p, loan, s)
    print(f"   At ${p}: Sell {s} sh -> {ns} sh remaining, Eq Ratio {nr*100:.1f}%")
print()
print("4. POST-FOMC (June 16 open):")
print("   - Re-assess direction; re-activate pyramid orders if trend resumes")
print("   - Restore standard 10% trailing stop")

# ============================================================
# SECTION 6: PRE-EARNINGS ADJUSTMENT
# ============================================================
print("\n" + "=" * 80)
print(f"SECTION 6: PRE-EARNINGS ADJUSTMENT (Close {EARNINGS_CLOSE})")
print("=" * 80)
print()
print("Earnings: maximum gap risk. Must deleverage significantly.")
print()
print("1. DELEVERAGE TO 50%+ EQUITY RATIO BEFORE CLOSE:")
for p in [950, 980, 1000, 1020]:
    s = shares_to_sell(SHARES, p, loan, 0.50)
    ns, nl, nmv, neq, nr = verify_sell(SHARES, p, loan, s)
    print(f"   At ${p}: Sell {s} sh -> {ns} sh, Eq Ratio {nr*100:.1f}%")
print()
print("2. POST-EARNINGS RE-ENTRY PROTOCOL:")
print("   - Wait for 15-min candle close after earnings")
print("   - Gap up >5%: re-enter 50% of original position size")
print("   - Gap up 0-5%: wait for 30-min consolidation, enter 33%")
print("   - Gap down: NO re-entry; wait for support test")
print()
print("3. OPTIONAL PROTECTIVE PUT:")
print("   - Buy 1 MU put contract, -10% OTM strike, nearest monthly expiry")
print("   - Cost: ~3-5% of position notional")
print("   - Protects against >10% overnight gap")

# ============================================================
# IBKR ORDER TICKETS
# ============================================================

print("\n" + "=" * 80)
print("IBKR ORDER TICKETS -- STOP-LOSS LADDER (GTC)")
print("=" * 80)
print(f"""
Account:      IBKR Margin
Underlying:   MU (Micron Technology)
Position:     {SHARES} shares @ ${COST_BASIS:,.2f} cost
Current Px:   ${CURRENT_PRICE:,.2f}
Equity Ratio: {equity_ratio*100:.2f}%
""")

for i, t in enumerate(stop_results):
    print(f"{'─'*60}")
    print(f"STOP-LOSS #{i+1}: {t['label']}")
    print(f"{'─'*60}")
    print("  Action:        SELL")
    print("  Order Type:    STP (Stop)")
    print(f"  Stop Price:    ${t['price']:,.2f}")
    print(f"  Quantity:      {t['sell']} shares")
    print("  Time-in-Force: GTC")
    print("  Route:         SMART")
    print(f"  Post-fill:     {t['shares_after']} shares, Eq Ratio {t['ratio_after']*100:.2f}%")
    print()

print("=" * 80)
print("IBKR ORDER TICKETS -- PYRAMID ADD-ON (GTC, Conditional)")
print("=" * 80)
print("""
NOTE: These are STOP-LIMIT BUY orders. Each triggers only if price
      closes above the specified level. Orders are INDEPENDENT;
      cancel unfilled lower-tier orders once a higher tier fills.
      Alternatively: use price alerts and enter manually.
""")

# Accumulate through pyramid for ticket display
ticket_s = SHARES
ticket_l = loan

for pr in pyramid_results:
    if pr['add'] > 0:
        print(f"{'─'*60}")
        print(f"PYRAMID ADD @ ${pr['price']:,} ({pr['gain_pct']:+.1f}% from entry)")
        print(f"{'─'*60}")
        print(f"  Condition:     MU closes above ${pr['price']:,} (daily)")
        print("  Action:        BUY")
        print(f"  Order Type:    STP LMT (Stop: ${pr['price']:,}, Limit: ${pr['price']+5:,.2f})")
        print(f"  Quantity:      {pr['add']} shares")
        print("  Time-in-Force: GTC")
        print("  Route:         SMART")
        print(f"  Before:        {pr['shares_before']} sh, Eq Ratio {pr['ratio_before']*100:.2f}%")
        print(f"  After:         {pr['shares_after']} sh, Eq Ratio {pr['ratio_after']*100:.2f}%")
        print(f"  New Loan:      ${pr['loan_after']:,.0f}")
        print()

# ============================================================
# FINAL SUMMARY
# ============================================================
print("=" * 80)
print("CRITICAL WARNINGS & SUMMARY")
print("=" * 80)
print(f"""
  Current Equity Ratio:  {equity_ratio*100:.2f}%
  35% Margin Call:       ${p_call_35:,.2f} ({dist_dollar:,.0f} = {dist_atr:.2f} ATR away)
  37% Hard Floor:        ${hf_current:,.2f} (ALREADY BREACHED at current price)
  10% Trail from $995:   ${CURRENT_PRICE*(1-TRAIL_PCT):,.2f}
  20MA:                  ${MA_20:,.0f}
  ATH:                   $1,089

  POSITION STATUS: EXTREMELY TIGHT
  - Only 0.25 ATR (${dist_dollar:,.0f}) from 35% margin call
  - A single -1 ATR day ($86) would breach margin call level
  - Tier 1 stop at $980 triggers BEFORE margin call — CRITICAL to have this in place

  STOP-LOSS SUMMARY:
  Tier 1 @ $980: Sell 18 sh -> 91 sh, Eq Ratio {stop_results[0]['ratio_after']*100:.1f}%
  Tier 2 @ $935: Sell {stop_results[1]['sell']} sh -> {stop_results[1]['shares_after']} sh, Eq Ratio {stop_results[1]['ratio_after']*100:.1f}%
  Tier 3 @ $880: Sell {stop_results[2]['sell']} sh -> {stop_results[2]['shares_after']} sh, Eq Ratio {stop_results[2]['ratio_after']*100:.1f}%

  PYRAMID ADD-ON SUMMARY:
""")
cum_s = SHARES
for pr in pyramid_results:
    if pr['add'] > 0:
        print(f"  @ ${pr['price']:,}: +{pr['add']} sh -> {pr['shares_after']} sh, Eq {pr['ratio_after']*100:.1f}%")

print(f"""
  TRAILING STOP (from current $995 peak):
  - 10% Trail: ${CURRENT_PRICE*(1-TRAIL_PCT):,.2f}
  - 37% Hard Floor: ${hf_current:,.2f} (BREACHED — trail stop takes precedence)
  - Active Stop: ${CURRENT_PRICE*(1-TRAIL_PCT):,.2f}

  EVENT ADJUSTMENTS:
  - FOMC ({FOMC_CLOSE}): Tighten stops, halt pyramid, optional pre-deleverage
  - Earnings ({EARNINGS_CLOSE}): MUST deleverage to 50%+ equity ratio before close
""")

# Verification: check all stop-loss ladder tiers produce 42%+ equity ratio
print("=" * 80)
print("MATH VERIFICATION")
print("=" * 80)
all_ok = True
for i, t in enumerate(stop_results):
    ok = t['ratio_after'] >= 0.419  # Allow 0.1% rounding tolerance
    status = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  Stop #{i+1} @ ${t['price']}: After ratio {t['ratio_after']*100:.2f}% — {status}")
for i, pr in enumerate(pyramid_results):
    if pr['add'] > 0:
        ok = pr['ratio_after'] >= TARGET_EQ_PYRAMID - 0.001
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  Pyramid @ ${pr['price']}: After ratio {pr['ratio_after']*100:.2f}% — {status}")

if all_ok:
    print("\n  ALL TARGETS MET. Math verified.")
else:
    print("\n  SOME TARGETS FAILED. Review above.")

print()
print("DISCLAIMER: These are calculated order tickets. Verify in TWS/IBKR Mobile")
print("before submitting. Market conditions change. GTC orders may need adjustment.")
