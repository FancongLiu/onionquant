"""MU real-time risk calculator"""
import yfinance as yf

mu = yf.Ticker('MU')
info = mu.info
price = info.get('currentPrice') or info.get('regularMarketPrice')
prev = info.get('previousClose') or info.get('regularMarketPreviousClose')
high52 = info.get('fiftyTwoWeekHigh')

print(f"MU Current: ${price:.2f}")
print(f"Previous Close: ${prev:.2f}")
print(f"Day Change: {(price-prev)/prev*100:.2f}%")
print(f"52w High: ${high52:.2f}")
print(f"Distance to ATH: {(price-high52)/high52*100:.2f}%")
print(f"New ATH? {'YES!!!' if price > high52 else 'Not yet'}")

# Position
shares = 118
cost = 1037
equity = 49889
current_val = shares * price
pnl = current_val - (shares * cost)
pnl_pct = (price - cost) / cost * 100
leverage = current_val / equity

print(f"\n=== Your Position ===")
print(f"Shares: {shares}")
print(f"Cost/share: ${cost}")
print(f"Current Price: ${price:.2f}")
print(f"Total Value: ${current_val:,.0f}")
print(f"Unrealized PnL: ${pnl:,.0f} ({pnl_pct:.1f}%)")
print(f"Equity: ${equity:,}")
print(f"Leverage: {leverage:.2f}x")

# Options expected move
try:
    expirations = mu.options
    near = [e for e in expirations if e >= '2026-06-23'][:1]
    if near:
        opt = mu.option_chain(near[0])
        calls = opt.calls
        puts = opt.puts
        atm_call = calls.iloc[(calls['strike'] - price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts['strike'] - price).abs().argsort()[:1]]
        straddle = float(atm_call['ask'].iloc[0]) + float(atm_put['ask'].iloc[0])
        em_pct = straddle / price * 100
        down_price = price * (1 - em_pct/100)
        up_price = price * (1 + em_pct/100)
        
        print(f"\n=== Options Expected Move ({near[0]}) ===")
        print(f"ATM Straddle: ${straddle:.2f}")
        print(f"Expected Move: +/- {em_pct:.1f}%")
        print(f"Downside target: ${down_price:.0f}")
        print(f"Upside target: ${up_price:.0f}")
        print(f"Your cost ${cost} is {'ABOVE' if cost > down_price else 'BELOW'} downside target")
        
        # Scenarios
        print(f"\n=== Scenario Analysis ===")
        # Best case
        best_val = shares * up_price
        best_equity = equity + (best_val - current_val)
        print(f"BULL (+{em_pct:.1f}%): Value ${best_val:,.0f} | Equity ${best_equity:,.0f} | PnL +${best_val - shares*cost:,.0f}")
        
        # Worst case  
        worst_val = shares * down_price
        worst_equity = equity + (worst_val - current_val)
        print(f"BEAR (-{em_pct:.1f}%): Value ${worst_val:,.0f} | Equity ${worst_equity:,.0f} | PnL ${worst_val - shares*cost:,.0f}")
        
        # Cost basis scenario
        cost_val = shares * cost
        cost_equity = equity + (cost_val - current_val)
        cost_drop = (cost - price) / price * 100
        print(f"COST BASIS ({cost_drop:.1f}% drop): Value ${cost_val:,.0f} | Equity ${cost_equity:,.0f} | PnL $0")
        
        # -20% crash
        crash_price = price * 0.80
        crash_val = shares * crash_price
        crash_equity = equity + (crash_val - current_val)
        print(f"CRASH (-20%): Value ${crash_val:,.0f} | Equity ${crash_equity:,.0f}")
        print(f"  Leverage at crash: {crash_val/crash_equity:.2f}x" if crash_equity > 0 else "  MARGIN CALL!")
except Exception as e:
    print(f"Options error: {e}")

# Quick comparison: sell 40 shares scenario
print(f"\n=== Sell 40 Shares Scenario ===")
sell_shares = 40
sell_value = sell_shares * price
keep_shares = shares - sell_shares
keep_value = keep_shares * price
new_equity = equity  # selling doesn't change equity (just converts to cash)
new_leverage = keep_value / new_equity
print(f"Sell 40 shares @ ${price:.2f} = ${sell_value:,.0f} cash")
print(f"Keep {keep_shares} shares = ${keep_value:,.0f}")
print(f"New leverage: {new_leverage:.2f}x")
print(f"Locked profit: ${(price - cost) * sell_shares:,.0f}")
