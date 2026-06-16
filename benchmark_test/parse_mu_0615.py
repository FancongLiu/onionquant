# -*- coding: utf-8 -*-
"""解析 MU 6/15 抓取数据 + 两周数据，输出形态分析所需信息。"""
import json, datetime, io

out = io.StringIO()
def p(*a): print(*a, file=out)

# 读 6/15 的 meta（含最新市场快照）
with open('logs/MU_0615_1d.json', encoding='utf-8') as f:
    d = json.load(f)
meta = d['chart']['result'][0]['meta']

p('='*70)
p('MU 市场快照 meta（Yahoo chart API）')
p('='*70)
p(f"regularMarketTime (unix): {meta['regularMarketTime']}")
p(f"  -> UTC: {datetime.datetime.utcfromtimestamp(meta['regularMarketTime']).strftime('%Y-%m-%d %H:%M:%S')}")
p(f"  -> EDT: {datetime.datetime.utcfromtimestamp(meta['regularMarketTime']+14400).strftime('%Y-%m-%d %H:%M:%S')} (注：本地EDT)")
p(f"regularMarketPrice: {meta['regularMarketPrice']}")
p(f"DayHigh: {meta.get('regularMarketDayHigh')}")
p(f"DayLow:  {meta.get('regularMarketDayLow')}")
p(f"Volume:  {meta.get('regularMarketVolume')}")
p(f"chartPreviousClose: {meta['chartPreviousClose']}")
p(f"52w High: {meta['fiftyTwoWeekHigh']}")
p(f"52w Low:  {meta['fiftyTwoWeekLow']}")
p(f"dataGranularity: {meta['dataGranularity']}")
p(f"pre-market period: {meta['currentTradingPeriod']['pre']['start']} - {meta['currentTradingPeriod']['pre']['end']}")
p(f"  pre start EDT: {datetime.datetime.utcfromtimestamp(meta['currentTradingPeriod']['pre']['start']+14400).strftime('%Y-%m-%d %H:%M:%S')}")
p(f"  pre end   EDT: {datetime.datetime.utcfromtimestamp(meta['currentTradingPeriod']['pre']['end']+14400).strftime('%Y-%m-%d %H:%M:%S')}")
p(f"regular period: {meta['currentTradingPeriod']['regular']['start']} - {meta['currentTradingPeriod']['regular']['end']}")
p(f"  reg start EDT: {datetime.datetime.utcfromtimestamp(meta['currentTradingPeriod']['regular']['start']+14400).strftime('%Y-%m-%d %H:%M:%S')}")
p(f"  reg end   EDT: {datetime.datetime.utcfromtimestamp(meta['currentTradingPeriod']['regular']['end']+14400).strftime('%Y-%m-%d %H:%M:%S')}")

# 关键判断
p('')
p('='*70)
p('关键判断')
p('='*70)
reg_start = meta['currentTradingPeriod']['regular']['start']
p(f"regular session 对应日期 (EDT): {datetime.datetime.utcfromtimestamp(reg_start+14400).strftime('%Y-%m-%d')}")
p(f"regularMarketPrice 来源时间 (EDT): {datetime.datetime.utcfromtimestamp(meta['regularMarketTime']+14400).strftime('%Y-%m-%d %H:%M:%S')}")
p('')
if meta['regularMarketTime'] < reg_start:
    p('>>> regularMarketTime < regular session start')
    p('>>> 说明：Yahoo 返回的快照是【上一个交易日 6/12 的收盘】，6/15 数据尚未更新')
else:
    p('>>> 数据已更新到 6/15')

# 两周数据
p('')
p('='*70)
p('MU 两周日K（含可能的 6/13、6/15）')
p('='*70)
with open('logs/MU_2wk_1d.json', encoding='utf-8') as f:
    d2 = json.load(f)
res = d2['chart']['result'][0]
ts = res['timestamp']
q = res['indicators']['quote'][0]
p(f"{'Date':<12}{'Open':>9}{'High':>9}{'Low':>9}{'Close':>9}{'Volume':>14}{'Ret%':>8}")
prev_c = None
for i, t in enumerate(ts):
    dt = datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')
    o,h,l,c,v = q['open'][i],q['high'][i],q['low'][i],q['close'][i],q['volume'][i]
    ret = ''
    if prev_c and c:
        ret = f'{(c-prev_c)/prev_c*100:+.2f}%'
    if c:
        prev_c = c
    vs = f'{v:,.0f}' if v else 'N/A'
    p(f"{dt:<12}{o:>9.2f}{h:>9.2f}{l:>9.2f}{c:>9.2f}{vs:>14}{ret:>8}")

with open('benchmark_test/mine/_mu_0615_output.txt','w',encoding='utf-8') as f:
    f.write(out.getvalue())
print('OK')
