# -*- coding: utf-8 -*-
import json, datetime, io
out = io.StringIO()
def p(*a): print(*a, file=out)

# 5分钟数据
with open('logs/MU_0616_5m.json', encoding='utf-8') as f:
    d = json.load(f)
res = d['chart']['result'][0]
meta = res['meta']
ts = res['timestamp']
q = res['indicators']['quote'][0]

p('='*70)
p('MU 6/16 5分钟K线（Yahoo API 真实数据）')
p('='*70)
p(f'meta regularMarketPrice: {meta["regularMarketPrice"]}')
p(f'meta DayHigh: {meta.get("regularMarketDayHigh")}  DayLow: {meta.get("regularMarketDayLow")}')
p(f'chartPreviousClose: {meta["chartPreviousClose"]}')
p('')
p(f'{"时间(EDT)":<18}{"Open":>9}{"High":>9}{"Low":>9}{"Close":>9}{"Volume":>12}{"涨跌":>9}')
p('-'*70)

prev_close = meta['chartPreviousClose']
bars = []
peak_price = 0
peak_time = ''
peak_vol = 0
total_vol = 0
for i,t in enumerate(ts):
    o,h,l,c,v = q['open'][i],q['high'][i],q['low'][i],q['close'][i],q['volume'][i]
    if c is None: continue
    edt = datetime.datetime.utcfromtimestamp(t)
    edt_str = edt.strftime('%m-%d %H:%M')
    ret = (c-prev_close)/prev_close*100 if prev_close else 0
    bars.append((edt_str,o,h,l,c,v,ret))
    if v: total_vol += v
    # 找高点
    if h and h > peak_price:
        peak_price = h
        peak_time = edt_str
        peak_vol = v
    vs = f'{v:,.0f}' if v else 'N/A'
    p(f'{edt_str:<18}{o:>9.2f}{h:>9.2f}{l:>9.2f}{c:>9.2f}{vs:>12}{ret:>+8.2f}%')
    prev_close = c

p('-'*70)
p(f'总成交量(5min bars): {total_vol:,.0f}')
p(f'⚡ 盘中最高点: {peak_time}  价格 ${peak_price:.2f}  当时5min量 {peak_vol:,.0f}')

# 分析：高点后是否放量下跌
if bars:
    peak_idx = next((i for i,b in enumerate(bars) if b[1]>=peak_price-1 or b[2]>=peak_price-1), 0)
    p('')
    p('=== 高点前后成交量对比 ===')
    p(f'高点前5根平均量: {sum(b[5] for b in bars[max(0,peak_idx-5):peak_idx] if b[5])/max(1,peak_idx-max(0,peak_idx-5)):,.0f}')
    p(f'高点后5根平均量: {sum(b[5] for b in bars[peak_idx:peak_idx+5] if b[5])/max(1,min(5,len(bars)-peak_idx)):,.0f}')

with open('benchmark_test/mine/_mu_0616_5m_output.txt','w',encoding='utf-8') as f:
    f.write(out.getvalue())
print('OK bars:', len(bars))
