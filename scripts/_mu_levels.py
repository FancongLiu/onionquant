import io
import sys

import numpy as np
import yfinance as yf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

mu = yf.download('MU', period='3mo', progress=False)
c, h, l, v = mu['Close'], mu['High'], mu['Low'], mu['Volume']

latest = float(c.iloc[-1])
ma20 = float(c.tail(20).mean())
ma50 = float(c.tail(50).mean())
bb_std = float(c.tail(20).std())
bb_upper = ma20 + 2*bb_std
bb_lower = ma20 - 2*bb_std

swing_low = 864.0
swing_high = 1089.0
diff = swing_high - swing_low
fib_382 = swing_high - diff * 0.382
fib_500 = swing_high - diff * 0.500
fib_618 = swing_high - diff * 0.618

delta = c.diff()
gain = delta.where(delta>0,0.0).rolling(14).mean()
loss = (-delta.where(delta<0,0.0)).rolling(14).mean()
rsi = float(100-(100/(1+(gain/loss).iloc[-1])))

tr = np.maximum(h - l, np.maximum(abs(h - c.shift()), abs(l - c.shift())))
atr14 = float(tr.tail(14).mean())
atr_pct = (atr14/latest)*100

print(f'现价: {latest:.0f} | 今高: {float(h.iloc[-1]):.0f} | 今低: {float(l.iloc[-1]):.0f}')
print(f'MA20: {ma20:.0f} (+{(latest/ma20-1)*100:.1f}%) | MA50: {ma50:.0f} (+{(latest/ma50-1)*100:.1f}%)')
print(f'BB上轨: {bb_upper:.0f} | BB下轨: {bb_lower:.0f}')
print(f'Fib 38.2%: {fib_382:.0f} | 50%: {fib_500:.0f} | 61.8%: {fib_618:.0f}')
print(f'ATR(14): {atr14:.0f} ({atr_pct:.1f}%) | 1xATR stop: {latest-atr14:.0f} | 2xATR stop: {latest-2*atr14:.0f}')
print(f'RSI(14): {rsi:.1f}')

# Volume context
vol_ma = float(v.tail(20).mean())
print(f'量比: {float(v.iloc[-1])/vol_ma:.1f}x')

# Key levels cluster
print()
print('=== 关键价位 ===')
# Pivot highs in last 30d
highs_30d = sorted([float(h.iloc[i]) for i in range(max(0,len(h)-30), len(h)) if float(h.iloc[i]) > latest], reverse=True)
lows_30d = sorted([float(l.iloc[i]) for i in range(max(0,len(l)-30), len(l)) if float(l.iloc[i]) < latest])
print(f'上方阻力(最近): {[f"${x:.0f}" for x in highs_30d[:5]]}')
print(f'下方支撑(最近): {[f"${x:.0f}" for x in lows_30d[-5:]]}')
