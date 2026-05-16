#!/usr/bin/env python
import sys
import urllib.request
import urllib.error

print("=" * 50)
print("网络诊断：Python 能否访问外网")
print("=" * 50)

# 测试 1：用 urllib 访问 DuckDuckGo（不需要 requests）
print("\n[测试 1] 尝试访问 DuckDuckGo (urllib)...")
try:
    response = urllib.request.urlopen('https://duckduckgo.com', timeout=5)
    print(f"✅ 成功！状态码: {response.status}")
except urllib.error.URLError as e:
    print(f"❌ 失败: URLError")
    print(f"   原因: {e.reason}")
except Exception as e:
    print(f"❌ 失败: {type(e).__name__}")
    print(f"   错误信息: {e}")

# 测试 2：尝试用 ddgs 库搜索（简单查询）
print("\n[测试 2] 尝试用 ddgs 库搜索 'AI news'...")
try:
    from ddgs import DDGS
    ddgs = DDGS()
    print("   正在搜索中（这可能需要等待...）")
    results = list(ddgs.news("AI news", max_results=1))
    if results:
        print(f"✅ 成功！获得 1 条结果")
        title = results[0].get('title', '无')[:50]
        print(f"   标题: {title}...")
    else:
        print(f"⚠️  无结果返回")
except Exception as e:
    print(f"❌ 失败: {type(e).__name__}")
    print(f"   错误信息: {e}")

print("\n[测试 3] 尝试用 ddgs 库搜索中文关键词 'AI'...")
try:
    from ddgs import DDGS
    ddgs = DDGS()
    print("   正在搜索中（这可能需要等待...）")
    results = list(ddgs.news("AI", max_results=1))
    if results:
        print(f"✅ 成功！获得 1 条结果")
        title = results[0].get('title', '无')[:50]
        print(f"   标题: {title}...")
    else:
        print(f"⚠️  无结果返回")
except Exception as e:
    print(f"❌ 失败: {type(e).__name__}")
    print(f"   错误信息: {e}")

print("\n" + "=" * 50)
