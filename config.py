"""
配置文件 - 存储API密钥等敏感信息
注意：不要将此文件提交到公共代码仓库
"""

# ==================== 硅基流动API配置 ====================
# 请在这里填入你的硅基流动API Key
SILICONFLOW_API_KEY = "你的API_KEY填在这里"  # ← 请替换为你的实际API Key

# GLM模型配置
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "glm-4-flash"  # 硅基流动上的GLM模型名称

# ==================== 其他配置 ====================
# 新闻搜索配置
NEWS_SEARCH_DAYS = 7  # 搜索最近几天的新闻
MAX_NEWS_PER_KEYWORD = 3  # 每个关键词最多获取多少条新闻
MAX_NEWS_FOR_BRIEFING = 15  # 生成简报时最多使用多少条新闻