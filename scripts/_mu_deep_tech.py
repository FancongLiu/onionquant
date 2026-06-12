import yfinance as yf, sys, io, numpy as np
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

mu = yf.download('MU', period='1mo', interval='1h', progress=False)
c, o, h, l, v = mu['Close'], mu['Open'], mu['High'], mu['Low'], mu['Volume']

print('='*70)
print('  MU 日K + 时K 深度技术分析')
print('='*70)

# --- DAILY CANDLE ANALYSIS (last 10 days) ---
daily = yf.download('MU', period='1mo', progress=False)
dc, do_, dh, dl, dv = daily['Close'], daily['Open'], daily['High'], daily['Low'], daily['Volume']

print('\n【日K分析 — 近10日】')
print(f'{"日期":>6} {"开":>6} {"高":>6} {"低":>6} {"收":>6} {"涨跌":>7} {"振幅":>6} {"量(亿)"}')
print('-'*75)
for i in range(max(0,len(dc)-10), len(dc)):
    date = do_.index[i].strftime('%m/%d')
    op, hi, lo, cl = float(do_.iloc[i]), float(dh.iloc[i]), float(dl.iloc[i]), float(dc.iloc[i])
    vol = float(dv.iloc[i])
    chg = (cl/float(dc.iloc[i-1])-1)*100 if i>0 else 0
    rng = (hi/lo-1)*100
    # Volume comparison
    avg_vol = float(dv.iloc[max(0,i-19):i+1].mean()) if i>=3 else vol
    vol_note = '放量' if vol>avg_vol*1.3 else ('缩量' if vol<avg_vol*0.7 else '正常')
    print(f'{date} {op:6.0f} {hi:6.0f} {lo:6.0f} {cl:6.0f} {chg:+6.1f}% {rng:5.1f}%  {vol/1e6:4.0f}M {vol_note}')

# --- KEY SUPPORT/RESISTANCE ---
print('\n【关键价位】')
ma20 = float(dc.tail(20).mean())
ma50 = float(dc.tail(50).mean()) if len(dc)>=50 else float('nan')
ma200 = float(dc.tail(200).mean()) if len(dc)>=200 else float('nan')
ath = float(dc.max())
recent_high = float(dc.tail(5).max())
recent_low = float(dc.tail(5).min())
print(f'20MA: ${ma20:.0f}  50MA: ${ma50:.0f}  200MA: ${ma200:.0f}')
print(f'ATH: ${ath:.0f}  近5日高: ${recent_high:.0f}  近5日低: ${recent_low:.0f}')

# --- RSI ---
delta = dc.diff()
gain = delta.where(delta>0,0.0).rolling(14).mean()
loss = (-delta.where(delta<0,0.0)).rolling(14).mean()
rs = gain/loss
rsi = float(100-(100/(1+rs.iloc[-1])))
print(f'RSI(14): {rsi:.1f}')

# --- MACD ---
ema12 = dc.ewm(span=12).mean()
ema26 = dc.ewm(span=26).mean()
macd = ema12 - ema26
signal = macd.ewm(span=9).mean()
hist = macd - signal
print(f'MACD: {float(macd.iloc[-1]):.1f}  Signal: {float(signal.iloc[-1]):.1f}  Hist: {float(hist.iloc[-1]):.1f}')
print(f'MACD趋势: {"转正↑" if float(hist.iloc[-1])>float(hist.iloc[-2]) else "仍在恶化↓"}')

# --- Volume Profile (last 5 days) ---
print('\n【量价关系 — 近5日】')
for i in range(max(0,len(dc)-5), len(dc)):
    date = do_.index[i].strftime('%m/%d')
    cl = float(dc.iloc[i])
    vol = float(dv.iloc[i])
    prev_cl = float(dc.iloc[i-1]) if i>0 else cl
    price_up = cl > prev_cl
    vol_prev = float(dv.iloc[i-1]) if i>0 else vol
    vol_up = vol > vol_prev
    # Healthy: price up + vol up (accumulation) OR price down + vol down (orderly selling)
    signal = ''
    if price_up and vol_up:
        signal = '量价齐升-机构吸筹'
    elif price_up and not vol_up:
        signal = '价升量缩-反弹乏力'
    elif not price_up and vol_up:
        signal = '价跌量增-恐慌抛售'
    else:
        signal = '量价齐缩-抛压减轻'
    print(f'  {date}: C${cl:.0f} 量{vol/1e6:.0f}M | {signal}')

# --- HOURLY: last 10 hours ---
print('\n【时K分析 — 最近10小时】')
for i in range(max(0,len(c)-10), len(c)):
    dt = o.index[i].strftime('%m/%d %H:%M')
    op, hi, lo, cl = float(o.iloc[i]), float(h.iloc[i]), float(l.iloc[i]), float(c.iloc[i])
    vol = float(v.iloc[i])
    chg = (cl/float(c.iloc[i-1])-1)*100 if i>0 else 0
    # Candle type
    body = abs(cl-op)
    total_r = hi-lo
    if total_r > 0:
        lower_ratio = (min(cl,op)-lo)/total_r
        upper_ratio = (hi-max(cl,op))/total_r
        if lower_ratio > 0.5: ctype = 'T锤子'
        elif upper_ratio > 0.5: ctype = '倒T'
        elif body/total_r < 0.2: ctype = '十字'
        elif cl > op: ctype = '阳'
        else: ctype = '阴'
    else:
        ctype = '-'
    print(f'  {dt} O{op:.0f} H{hi:.0f} L{lo:.0f} C{cl:.0f} {chg:+.1f}% 量{vol/1e6:.1f}M [{ctype}]')

# --- Accumulation/Distribution ---
print('\n【筹码分布判断】')
# Chaikin Money Flow (21-period)
mfm = ((dc - dl) - (dh - dc)) / (dh - dl)
mfm = mfm.replace([np.inf, -np.inf], 0).fillna(0)
mfv = mfm * dv
cmf = mfv.rolling(21).sum() / dv.rolling(21).sum()
latest_cmf = float(cmf.iloc[-1])
print(f'CMF(21): {latest_cmf:+.3f} | {"资金流入-机构吸筹" if latest_cmf>0.05 else ("资金流出-机构派发" if latest_cmf<-0.05 else "中性")}')

# Price position vs MAs
latest = float(dc.iloc[-1])
print(f'\n价格 vs 均线:')
for ma_name, ma_val in [('20MA', ma20), ('50MA', ma50)]:
    pct = (latest/ma_val-1)*100
    print(f'  vs {ma_name}: {pct:+.1f}%')
