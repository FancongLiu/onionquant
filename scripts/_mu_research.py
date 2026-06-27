"""MU 财报前深度研究 — 数据采集脚本"""
import yfinance as yf
import json

mu = yf.Ticker('MU')

# === Options Chain ===
try:
    expirations = mu.options
    print('Options expirations:', expirations[:8])
except Exception as e:
    print('Options error:', e)
    expirations = []

near_term = [e for e in expirations if e >= '2026-06-23'][:3]
print('Near-term expirations:', near_term)

for exp in near_term[:2]:
    try:
        opt = mu.option_chain(exp)
        calls = opt.calls
        puts = opt.puts

        # ATM strikes
        atm_calls = calls.iloc[(calls['strike'] - 1195).abs().argsort()[:5]]
        atm_puts = puts.iloc[(puts['strike'] - 1195).abs().argsort()[:5]]

        print(f'\n=== Expiration: {exp} ===')
        print('--- Near-ATM Calls ---')
        for _, row in atm_calls.iterrows():
            print(f"  Strike {row['strike']}: Bid={row['bid']} Ask={row['ask']} Last={row['lastPrice']} Vol={row['volume']} OI={row['openInterest']} IV={row['impliedVolatility']}")

        print('--- Near-ATM Puts ---')
        for _, row in atm_puts.iterrows():
            print(f"  Strike {row['strike']}: Bid={row['bid']} Ask={row['ask']} Last={row['lastPrice']} Vol={row['volume']} OI={row['openInterest']} IV={row['impliedVolatility']}")

        total_call_vol = int(opt.calls['volume'].sum())
        total_put_vol = int(opt.puts['volume'].sum())
        total_call_oi = int(opt.calls['openInterest'].sum())
        total_put_oi = int(opt.puts['openInterest'].sum())
        print(f'Put/Call Vol: {total_put_vol}/{total_call_vol} = {total_put_vol/total_call_vol:.2f}' if total_call_vol > 0 else 'Put/Call Vol: N/A')
        print(f'Put/Call OI: {total_put_oi}/{total_call_oi} = {total_put_oi/total_call_oi:.2f}' if total_call_oi > 0 else 'Put/Call OI: N/A')
    except Exception as e:
        print(f'Error for {exp}: {e}')

# === Expected Move (ATM straddle) ===
try:
    weekly_exp = near_term[0] if near_term else None
    if weekly_exp:
        opt = mu.option_chain(weekly_exp)
        # Find ATM call and put
        calls = opt.calls
        puts = opt.puts
        atm_call = calls.iloc[(calls['strike'] - 1195).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts['strike'] - 1195).abs().argsort()[:1]]
        straddle_price = float(atm_call['ask'].iloc[0]) + float(atm_put['ask'].iloc[0])
        expected_move = straddle_price / 1195 * 100
        print(f'\n=== Expected Move (ATM Straddle) ===')
        print(f'ATM Call Ask: {float(atm_call["ask"].iloc[0])}')
        print(f'ATM Put Ask: {float(atm_put["ask"].iloc[0])}')
        print(f'Straddle Price: {straddle_price:.2f}')
        print(f'Expected Move: +/- {expected_move:.1f}%')
        print(f'Expected Move $: +/- {straddle_price:.2f}')
except Exception as e:
    print(f'Expected move error: {e}')

# === Analyst Ratings Summary ===
print('\n=== MU Key Metrics ===')
info = mu.info
print(f"Current: {info.get('currentPrice')}")
print(f"Forward P/E: {info.get('forwardPE')}")
print(f"PEG: {info.get('pegRatio')}")
print(f"Price/Book: {info.get('priceToBook')}")
print(f"Revenue Growth: {info.get('revenueGrowth')}")
print(f"Earnings Growth: {info.get('earningsGrowth')}")
print(f"Debt/Equity: {info.get('debtToEquity')}")
print(f"ROE: {info.get('returnOnEquity')}")
print(f"Target Mean: {info.get('targetMeanPrice')}")
print(f"Target High: {info.get('targetHighPrice')}")
print(f"Target Low: {info.get('targetLowPrice')}")
print(f"Recommendation: {info.get('recommendationKey')}")
print(f"# Analysts: {info.get('numberOfAnalystOpinions')}")
print(f"Short %: {info.get('shortPercentOfFloat')}")
print(f"Short Ratio: {info.get('shortRatio')}")
print(f"Beta: {info.get('beta')}")
print(f"52w High: {info.get('fiftyTwoWeekHigh')}")
print(f"52w Low: {info.get('fiftyTwoWeekLow')}")
print(f"Earnings Date: {info.get('earningsDates')}")

# === Compare sectors: daily change ===
print('\n=== Sector Comparison (Today) ===')
tickers = {
    'MU': 'Micron', 'AVGO': 'Broadcom', 'NVDA': 'NVIDIA', 
    'INTC': 'Intel', 'WDC': 'WDC', 'AMD': 'AMD',
    'SMH': 'VanEck Semi', 'SOXX': 'iShares Semi', 'SPCX': 'SpaceX ETF'
}
for t, name in tickers.items():
    tk = yf.Ticker(t)
    info2 = tk.info
    price = info2.get('currentPrice') or info2.get('regularMarketPrice')
    prev = info2.get('previousClose') or info2.get('regularMarketPreviousClose')
    if price and prev:
        chg = (price - prev) / prev * 100
        high52 = info2.get('fiftyTwoWeekHigh', 0)
        pct_ath = (price - high52) / high52 * 100 if high52 else 0
        print(f"{name:15s} ${price:>10.2f}  {chg:>+6.1f}%  from ATH: {pct_ath:>+6.1f}%")
