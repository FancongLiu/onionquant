#!/usr/bin/env python
"""
诊断脚本：测试 notebook 中的实际关键词是否能搜索成功
"""
from ddgs import DDGS
import time

print("=" * 70)
print("关键词搜索诊断 - 逐个测试 notebook 中的每个关键词")
print("=" * 70)

keywords = [
    'AI 大模型 最新发布',
    'AI 融资 投资 2026',
    'OpenAI 发布 GPT',
    'Google Gemini 发布',
    'Anthropic 产品 更新',
    'AI 芯片 新 投资',
    '生成式 AI 监管 政策',
    'AI 企业化 应用 投资 合作'
]

# 同时也测试英文版本
english_keywords = [
    'AI latest model release',
    'AI funding investment 2026',
    'OpenAI GPT release',
    'Google Gemini release',
    'Anthropic product update',
    'AI chip investment',
    'Generative AI regulation policy',
    'AI enterprise application investment'
]

print("\n[组 1] 测试中文关键词：")
print("-" * 70)
success_count = 0
for i, kw in enumerate(keywords, 1):
    try:
        print(f"{i}. '{kw}' ... ", end='', flush=True)
        ddgs = DDGS()
        results = list(ddgs.news(kw, max_results=2))
        if results:
            print(f"✅ 成功！获得 {len(results)} 条新闻")
            print(f"   标题: {results[0].get('title', '无')[:60]}...")
            success_count += 1
        else:
            print("⚠️  无结果（可能被过滤）")
    except Exception as e:
        print(f"❌ 失败")
        print(f"   错误: {type(e).__name__}: str(e)[:80]")
    time.sleep(1)  # 避免速率限制

print(f"\n[组 1 小结] 中文关键词：{success_count}/{len(keywords)} 成功")

print("\n[组 2] 测试英文关键词：")
print("-" * 70)
success_count = 0
for i, kw in enumerate(english_keywords, 1):
    try:
        print(f"{i}. '{kw}' ... ", end='', flush=True)
        ddgs = DDGS()
        results = list(ddgs.news(kw, max_results=2))
        if results:
            print(f"✅ 成功！获得 {len(results)} 条新闻")
            print(f"   标题: {results[0].get('title', '无')[:60]}...")
            success_count += 1
        else:
            print("⚠️  无结果")
    except Exception as e:
        print(f"❌ 失败")
        print(f"   错误: {type(e).__name__}")
    time.sleep(1)

print(f"\n[组 2 小结] 英文关键词：{success_count}/{len(english_keywords)} 成功")

print("\n" + "=" * 70)
print("分析建议：")
print("- 如果中文全失败，英文成功 → 改用英文关键词")
print("- 如果两者都有失败 → 加入重试和延迟机制")
print("- 如果选择性失败 → 某些关键词可能被限制（如中文特殊词汇）")
print("=" * 70)
