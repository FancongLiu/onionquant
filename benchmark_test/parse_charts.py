# -*- coding: utf-8 -*-
"""解析本地 yahoo chart JSON，输出 6/8-6/13 OHLC 表格 + 6/13 横向对比。纯本地，不联网。"""
import sys, json, datetime, io

files = {
    'MU':   'logs/MU_2026.json',
    'NVDA': 'logs/NVDA_2026.json',
    'INTC': 'logs/INTC_2026.json',
    'SNDK': 'logs/SNDK_2026.json',
    'AVGO': 'logs/AVGO_2026.json',
}

out = io.StringIO()
def p(*a):
    print(*a, file=out)

all_data = {}
for t, f in files.items():
    try:
        with open(f, encoding='utf-8') as fh:
            d = json.load(fh)
    except Exception as e:
        p(f'!!! {t} load error: {e}')
        continue
    try:
        res = d['chart']['result'][0]
    except Exception as e:
        p(f'!!! {t} parse error: {e}; keys={list(d.keys())}')
        if 'chart' in d and 'error' in d['chart']:
            p(f'    yahoo error: {d["chart"]["error"]}')
        continue
    ts = res['timestamp']
    q = res['indicators']['quote'][0]
    rows = []
    for i, tt in enumerate(ts):
        dt = datetime.datetime.utcfromtimestamp(tt).strftime('%Y-%m-%d')
        o, h, l, c, v = q['open'][i], q['high'][i], q['low'][i], q['close'][i], q['volume'][i]
        if c is None:
            continue
        rows.append((dt, o, h, l, c, v))
    all_data[t] = rows

p('=' * 80)
p('yfinance / yahoo chart API 真实数据 (2026-06-08 ~ 06-13)')
p('=' * 80)
p(f'{"Ticker":<7}{"Date":<12}{"Open":>9}{"High":>9}{"Low":>9}{"Close":>9}{"Volume":>16}{"DayRet%":>10}')
p('-' * 80)
for t in ['MU', 'NVDA', 'INTC', 'SNDK', 'AVGO']:
    rows = all_data.get(t, [])
    for i, (dt, o, h, l, c, v) in enumerate(rows):
        ret = ''
        if i > 0:
            pc = rows[i - 1][4]
            ret = f'{(c - pc) / pc * 100:+.2f}%'
        p(f'{t:<7}{dt:<12}{o:>9.2f}{h:>9.2f}{l:>9.2f}{c:>9.2f}{v:>16,.0f}{ret:>10}')
    p('-' * 80)

# 6/13 横向对比
p('')
p('=' * 80)
p('6/13 收盘涨跌幅横向对比 (相对 6/12 收盘)')
p('=' * 80)
p(f'{"Ticker":<7}{"6/12 Close":>13}{"6/13 Close":>13}{"DayRet%":>11}{"vs MU(pp)":>12}')
p('-' * 80)
rets = {}
for t in ['MU', 'NVDA', 'INTC', 'SNDK', 'AVGO']:
    data = all_data.get(t, [])
    if len(data) >= 2:
        c12 = data[-2][4]
        c13 = data[-1][4]
        r = (c13 - c12) / c12 * 100
        rets[t] = (c12, c13, r)
mu_r = rets.get('MU', (0, 0, 0))[2]
for t in ['MU', 'NVDA', 'INTC', 'SNDK', 'AVGO']:
    if t in rets:
        c12, c13, r = rets[t]
        diff = r - mu_r
        p(f'{t:<7}{c12:>13.2f}{c13:>13.2f}{r:>+10.2f}%{diff:>+11.2f}pp')

# 周累计
p('')
p('=' * 80)
p('本周 (6/9 ~ 6/13) 累计涨跌幅')
p('=' * 80)
for t in ['MU', 'NVDA', 'INTC', 'SNDK', 'AVGO']:
    data = all_data.get(t, [])
    if len(data) >= 2:
        c_start = data[0][4]
        c_end = data[-1][4]
        r = (c_end - c_start) / c_start * 100
        p(f'{t:<7} {data[0][0]} {c_start:.2f}  ->  {data[-1][0]} {c_end:.2f}   {r:+.2f}%')

with open('benchmark_test/mine/_data_output.txt', 'w', encoding='utf-8') as f:
    f.write(out.getvalue())
print('OK written')
