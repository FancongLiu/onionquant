from ddgs import DDGS
import json

ddgs = DDGS(timeout=15)
results = list(ddgs.news("AI news 2026", max_results=6))

print(f"\n【成功获得 {len(results)} 条新闻】\n")
for i, news in enumerate(results, 1):
    title = news.get('title', '无标题')
    url = news.get('url', '无链接')
    print(f"{i}. {title}")
    print(f"   {url}\n")
