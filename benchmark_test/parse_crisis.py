# -*- coding: utf-8 -*-
import json, datetime, io
out = io.StringIO()
def p(*a): print(*a, file=out)

for name, fn in [('MU', 'logs/MU_0616.json'), ('AVGO', 'logs/AVGO_0616.json')]:
    with open(fn, encoding='utf-8') as f:
        d = json.load(f)
    meta = d['chart']['result'][0]['meta']
    p('='*60)
    p(name, 'meta snapshot')
    p('='*60)
    rmt = meta['regularMarketTime']
    p(f'regularMarketPrice: {meta["regularMarketPrice"]}')
    p(f'regularMarketTime: {rmt} -> {datetime.datetime.utcfromtimestamp(rmt).strftime("%Y-%m-%d %H:%M UTC")} | {(datetime.datetime.utcfromtimestamp(rmt).hour-4):02d}:{datetime.datetime.utcfromtimestamp(rmt).minute:02d} EDT')
    p(f'DayHigh: {meta.get("regularMarketDayHigh")}  DayLow: {meta.get("regularMarketDayLow")}')
    p(f'Volume: {meta.get("regularMarketVolume")}')
    p(f'chartPreviousClose: {meta["chartPreviousClose"]}')
    # 算涨跌
    prev = meta['chartPreviousClose']
    cur = meta['regularMarketPrice']
    if prev:
        p(f'涨跌 vs prevClose: {(cur-prev)/prev*100:+.2f}%')
    res = d['chart']['result'][0]
    q = res['indicators']['quote'][0]
    ts = res.get('timestamp', [])
    if ts:
        p('--- intraday bars ---')
        for i,t in enumerate(ts):
            o,h,l,c,v = q['open'][i],q['high'][i],q['low'][i],q['close'][i],q['volume'][i]
            dt = datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d %H:%M UTC')
            p(f'{dt}  O={o} H={h} L={l} C={c} V={v}')
    p('')

# 持仓核算
p('='*60)
p('持仓核算')
p('='*60)
shares = 106
mktval = 116239
networth = 38650
price_now = mktval / shares
p(f'隐含现价 = {mktval}/{shares} = ${price_now:.2f}')
loan = mktval - networth
p(f'贷款 = {mktval} - {networth} = ${loan:.0f}')
lev = mktval / networth
p(f'杠杆 = {mktval}/{networth} = {lev:.3f}x')
# 保证金率融资比
margin_req = 0.65  # IBKR 65%
max_lev = 1/(1-margin_req)
p(f'最大允许杠杆 (65%保证金) = {max_lev:.3f}x')
p(f'融资比率 = {lev/max_lev*100:.2f}%')
# 强平价推导: E(P) = 106P - loan
# 融资率 R = (106P/(106P-loan))/max_lev
# 135%: 106P/(106P-loan) = 1.35*max_lev = 1.35*2.857 = 3.857
# 106P = 3.857*(106P-loan) -> 106P(1-3.857) = -3.857*loan -> P = 3.857*loan/(106*2.857)
import math
p('')
p('关键价位（E(P)=106P-loan 模型）:')
for r, label in [(1.0,'100% 危险线'),(1.1,'110% 止损一'),(1.35,'135% 强平')]:
    target_lev = r * max_lev
    # shares*P/(shares*P-loan) = target_lev -> shares*P = target_lev*(shares*P-loan)
    # shares*P(1-target_lev) = -target_lev*loan -> P = target_lev*loan/(shares*(target_lev-1))
    P = target_lev*loan/(shares*(target_lev-1))
    drop = (P-price_now)/price_now*100
    p(f'  融资率 {label}: P=${P:.2f}  (距现价 {drop:+.2f}%)')

with open('benchmark_test/mine/_crisis_output.txt','w',encoding='utf-8') as f:
    f.write(out.getvalue())
print('OK')
