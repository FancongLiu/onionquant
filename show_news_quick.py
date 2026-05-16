#!/usr/bin/env python
"""
快速显示部分新闻内容
"""
import time
from ddgs import DDGS

print("🔍 快速获取新闻样本...\n")

# 只获取前 3 个关键词的新闻
keywords = [
    'AI model release 2026',
    'AI funding investment 2026',
    'OpenAI GPT latest',
]

all_news = []
for kw in keywords:
    try:
        print(f"搜索 '{kw}' ... ", end='', flush=True)
        ddgs = DDGS(timeout=15)
        results = list(ddgs.news(kw, max_results=2))
        all_news.extend(results)
        print(f"✅")
        time.sleep(1)
    except Exception as e:
        print(f"⚠️")

# 去重
unique = []
titles = set()
for n in all_news:
    t = n.get('title','').strip()
    if t and t not in titles:
        titles.add(t)
        unique.append(n)

print(f"\n{'='*100}")
print(f"共获得 {len(unique)} 条新闻\n")

for i, n in enumerate(unique, 1):
    title = n.get('title', '无标题')
    url = n.get('url', '无链接')
    
    print(f"{i}. {title}")
    print(f"   🔗 {url}\n")
