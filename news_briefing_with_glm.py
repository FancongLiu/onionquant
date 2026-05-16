#!/usr/bin/env python
"""
使用GLM-5.1大语言模型生成新闻简报
"""
import time
import requests
import json
from ddgs import DDGS

# ==================== 配置区域 ====================
# 请在这里填入你的硅基流动API Key
SILICONFLOW_API_KEY = "你的API_KEY填在这里"  # ← 请替换为你的实际API Key

# GLM-5.1模型配置
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "glm-4-flash"  # 硅基流动上的GLM模型名称

# ==================== 新闻获取 ====================
def get_ai_news(days=7, max_per_kw=3):
    """获取AI相关新闻"""
    print("🔍 正在搜索全球AI最新动态...")
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

# ==================== GLM-5.1 API调用 ====================
def generate_briefing_with_glm(news_list):
    """使用GLM-5.1生成新闻简报"""
    if not news_list:
        return "没有获取到新闻内容"
    
    # 准备新闻文本
    news_text = ""
    for i, news in enumerate(news_list[:15], 1):  # 限制最多15条新闻
        title = news.get('title', '无标题')
        source = news.get('source', '未知来源')
        date = news.get('date', '未知日期')
        news_text += f"{i}. 【{source}】{title} ({date})\n"
    
    # 构建提示词
    prompt = f"""你是一个专业的新闻编辑。请将以下新闻整理成简洁的简报，要求：

1. 每条新闻用1-2句话概括核心内容
2. 突出关键信息（公司、产品、金额、影响等）
3. 使用简洁、易懂的语言
4. 按重要性排序
5. 总字数控制在300-500字以内
6. 使用emoji让简报更生动

新闻内容：
{news_text}

请生成简报："""

    # 调用GLM-5.1 API
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的新闻编辑，擅长将复杂信息整理成简洁易懂的简报。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        print("\n🤖 正在调用GLM-5.1生成简报...")
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        briefing = result['choices'][0]['message']['content']
        
        return briefing
        
    except requests.exceptions.RequestException as e:
        return f"❌ API调用失败: {str(e)}"
    except KeyError as e:
        return f"❌ API响应格式错误: {str(e)}"
    except Exception as e:
        return f"❌ 生成简报时出错: {str(e)}"

# ==================== 主程序 ====================
def main():
    print("="*80)
    print("📰 AI新闻简报生成器 (使用GLM-5.1)")
    print("="*80)
    
    # 检查API Key
    if SILICONFLOW_API_KEY == "你的API_KEY填在这里":
        print("\n⚠️ 请先在脚本中填入你的硅基流动API Key！")
        print("   编辑文件，找到 SILICONFLOW_API_KEY 变量，填入你的API Key")
        return
    
    # 获取新闻
    news = get_ai_news()
    print(f"\n{'='*80}")
    print(f"✅ 共获得 {len(news)} 条独特新闻")
    print(f"{'='*80}\n")
    
    # 显示原始新闻（可选）
    print("📋 原始新闻列表：\n")
    for i, n in enumerate(news[:10], 1):  # 只显示前10条
        title = n.get('title', '无标题')
        source = n.get('source', '未知来源')
        print(f"{i}. 【{source}】{title}")
    
    if len(news) > 10:
        print(f"\n... 还有 {len(news)-10} 条新闻")
    
    # 生成简报
    print(f"\n{'='*80}")
    briefing = generate_briefing_with_glm(news)
    
    # 显示简报
    print("\n🎯 AI生成的新闻简报：\n")
    print("="*80)
    print(briefing)
    print("="*80)

if __name__ == "__main__":
    main()