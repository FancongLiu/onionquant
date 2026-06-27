"""Macro + MU deep fundamentals"""
import yfinance as yf

print("=== MACRO ===")
for t in ['^VIX', '^GSPC', '^IXIC', 'QQQ', 'TLT', 'USO']:
    tk = yf.Ticker(t)
    info = tk.info
    price = info.get('currentPrice') or info.get('regularMarketPrice')
    prev = info.get('previousClose') or info.get('regularMarketPreviousClose')
    chg = (price-prev)/prev*100 if price and prev else 0
    print(f'{t:8s} ${price} {chg:+.1f}%')

print("\n=== MU DEEP FUNDAMENTALS ===")
mu = yf.Ticker('MU')
info = mu.info
metrics = [
    ('Revenue', 'totalRevenue'),
    ('Revenue/Share', 'revenuePerShare'),
    ('Q Earnings Growth', 'earningsQuarterlyGrowth'),
    ('Gross Margins', 'grossMargins'),
    ('EBITDA Margins', 'ebitdaMargins'),
    ('Operating Margins', 'operatingMargins'),
    ('Trailing P/E', 'trailingPE'),
    ('Price/Sales', 'priceToSalesTrailing12Months'),
    ('Enterprise/Revenue', 'enterpriseToRevenue'),
    ('Enterprise/EBITDA', 'enterpriseToEbitda'),
    ('Free Cash Flow', 'freeCashflow'),
    ('Operating Cash Flow', 'operatingCashflow'),
    ('ROE', 'returnOnEquity'),
    ('ROA', 'returnOnAssets'),
]
for label, key in metrics:
    val = info.get(key)
    if val is not None:
        if isinstance(val, float):
            print(f'{label:25s}: {val:>15,.2f}')
        else:
            print(f'{label:25s}: {val}')
