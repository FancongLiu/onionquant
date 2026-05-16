#!/usr/bin/env python
"""
快速诊断：对比中文 vs 英文关键词
"""
from ddgs import DDGS
import time

print("=" * 60)
print("快速诊断：中文 vs 英文关键词")
print("=" * 60)

tests = [
    ("英文：简单", "AI news"),
    ("中文：简单", "AI 新闻"),
    ("英文：长", "OpenAI GPT model release"),
    ("中文：长", "AI 大模型 最新发布"),
]

for label, kw in tests:
    print(f"\n测试 [{label}] '{kw}'")
    print("-" * 60)
    try:
        print("  正在搜索...", end='', flush=True)
        start = time.time()
        ddgs = DDGS()
        results = list(ddgs.news(kw, max_results=1))
        elapsed = time.time() - start
        
        if results:
            title = results[0].get('title', '无')[:50]
            print(f" ✅ 成功！耗时 {elapsed:.1f}秒")
            print(f"  标题: {title}...")
        else:
            print(f" ⚠️  无结果（耗时 {elapsed:.1f}秒）")
    except Exception as e:
        elapsed = time.time() - start
        print(f" ❌ 失败（耗时 {elapsed:.1f}秒）")
        print(f"  错误: {type(e).__name__}")
        print(f"  详情: {str(e)[:100]}")
    
    time.sleep(2)  # 间隔避免限制

print("\n" + "=" * 60)
print("分析：")
print("- 如果英文都成功，中文都失败 → 问题是中文关键词编码/限制")
print("- 如果长关键词慢/失败 → 问题可能是 URL 长度或速率限制")
print("- 如果中文有的成功 → 可能是特定词汇被限制（如'监管'）")
print("=" * 60)
