#!/usr/bin/env python
"""
显示爬取的新闻内容（不发邮件）
"""
import time
from ddgs import DDGS

def get_ai_news(days=7, max_per_kw=4):
    print("🔍 正在搜索全球AI最新动态和投资新闻...")
    keywords = [
        'AI model release 2026',
        'AI funding investment 2026',
        'OpenAI GPT latest',
        'Google Gemini news',
        'Anthropic Claude update',
        'AI chip investment news',
        'AI regulation policy',
        'AI enterprise application'
    ]
    all_news = []
    
    for i, kw in enumerate(keywords, 1):
        try:
            print(f"  [{i}/8] 搜索 '{kw}' ... ", end='', flush=True)
            ddgs = DDGS(timeout=15)
            results = list(ddgs.news(kw, max_results=max_per_kw))
            all_news.extend(results)
            print(f"✅ 获得 {len(results)} 条")
        except Exception as e:
            print(f"⚠️ 错误：{type(e).__name__}")
            time.sleep(1)
            continue
    
    # 去重
    unique = []
    titles = set()
    for n in all_news:
        t = n.get('title','').strip()
        if t and t not in titles:
            titles.add(t)
            unique.append(n)
    
    return unique

# 获取并显示新闻
news = get_ai_news()
print(f"\n{'='*80}")
print(f"共获得 {len(news)} 条独特新闻")
print(f"{'='*80}\n")

for i, n in enumerate(news, 1):
    title = n.get('title', '无标题')
    url = n.get('url', '无链接')
    source = n.get('source', '未知来源')
    date = n.get('date', '未知日期')
    
    print(f"{i}. 【{source}】{title}")
    print(f"   时间: {date}")
    print(f"   链接: {url}")
    print()
