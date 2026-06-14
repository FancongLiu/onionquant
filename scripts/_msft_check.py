import io
import sys

import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

msft = yf.Ticker('MSFT')
info = msft.info

items = [
    ('现价', 'currentPrice'),
    ('前收', 'regularMarketPreviousClose'),
    ('52W高', 'fiftyTwoWeekHigh'),
    ('52W低', 'fiftyTwoWeekLow'),
    ('Forward P/E', 'forwardPE'),
    ('Trailing P/E', 'trailingPE'),
    ('PEG', 'pegRatio'),
    ('Beta', 'beta'),
]
for label, key in items:
    val = info.get(key, 'N/A')
    print(f'{label}: {val}')

print(f'市值: ${info.get("marketCap", 0)/1e12:.2f}T')
print(f'营收TTM: ${info.get("totalRevenue", 0)/1e9:.0f}B')
print(f'毛利率: {info.get("grossMargins", 0)*100:.1f}%')
print(f'FCF: ${info.get("freeCashflow", 0)/1e9:.1f}B')
print(f'股息率: {info.get("dividendYield", 0)*100:.2f}%')

d = yf.download('MSFT', period='6mo', progress=False)
c = d['Close']
latest = float(c.iloc[-1])
ath = float(c.max())
print(f'\n6月ATH: ${ath:.0f}')
print(f'ATH回撤: {(latest/ath-1)*100:.1f}%')
print(f'1月回报: {(latest/float(c.iloc[-21])-1)*100:.1f}%' if len(c)>=21 else 'N/A')
print(f'MA20: ${float(c.tail(20).mean()):.0f}')
print(f'MA50: ${float(c.tail(50).mean()):.0f}')
