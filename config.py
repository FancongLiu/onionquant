"""
配置文件 - 存储API密钥等敏感信息
安全优先：API Key 优先从环境变量读取，回退到默认值
注意：不要将此文件提交到公共代码仓库
"""

import os
from dataclasses import dataclass, field
from typing import Optional


# ==================== 硅基流动API配置 ====================
@dataclass
class SiliconFlowConfig:
    """硅基流动 API 配置"""
    api_key: str = field(default_factory=lambda: os.getenv(
        "SILICONFLOW_API_KEY", "你的API_KEY填在这里"
    ))
    api_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    model_name: str = os.getenv("GLM_MODEL_NAME", "glm-4-flash")

    def is_configured(self) -> bool:
        """检查 API Key 是否已配置"""
        return bool(self.api_key) and self.api_key != "你的API_KEY填在这里"


# ==================== 新闻搜索配置 ====================
@dataclass
class NewsConfig:
    """新闻搜索配置"""
    search_days: int = 7
    max_per_keyword: int = 3
    max_for_briefing: int = 15


# ==================== 全局单例 ====================
siliconflow = SiliconFlowConfig()
news = NewsConfig()


# ==================== 便捷常量（向后兼容） ====================
SILICONFLOW_API_KEY = siliconflow.api_key
API_URL = siliconflow.api_url
MODEL_NAME = siliconflow.model_name
NEWS_SEARCH_DAYS = news.search_days
MAX_NEWS_PER_KEYWORD = news.max_per_keyword
MAX_NEWS_FOR_BRIEFING = news.max_for_briefing


# ==================== 自检 ====================
if __name__ == "__main__":
    print("=" * 50)
    print("配置自检")
    print("=" * 50)
    print(f"API Key 已配置: {siliconflow.is_configured()}")
    print(f"API URL:       {API_URL}")
    print(f"模型名称:      {MODEL_NAME}")
    print(f"搜索天数:      {NEWS_SEARCH_DAYS}")
    print(f"每关键词上限:  {MAX_NEWS_PER_KEYWORD}")
    print(f"简报上限:      {MAX_NEWS_FOR_BRIEFING}")
    print("=" * 50)
    print("✅ config.py 加载正常")