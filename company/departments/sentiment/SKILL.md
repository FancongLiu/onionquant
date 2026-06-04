---
name: sentiment-intelligence
description: 舆情分析部 — 实时舆情·热度曲线·情感因子·新闻聚合 (yfinance_news + Google Trends + StockTwits + Reddit + FinBERT)
---

# 舆情分析部 (Sentiment Intelligence Department)

## 工具栈

| 工具 | 用途 | 状态 |
|------|------|------|
| `yfinance` news | 免费新闻标题+摘要 (已接入) | ✅ |
| `pytrends` (Google Trends) | 搜索热度曲线 (已接入) | ✅ |
| StockTwits API | 用户自标 Bullish/Bearish (免费, 待修复) | ⚠️ |
| Reddit PRAW | WSB等论坛舆情 (免费个人版) | ⚠️ 需配置 key |
| FinBERT (transformers) | 专业金融情感 NLP (待安装) | ❌ |
| Alpha Vantage NEWS_SENTIMENT | 专业新闻情感 (免费25次/天) | ⚠️ 需配置 key |

## 输出因子

| 因子 | 数据源 | 更新频率 | 权重建议 |
|------|--------|----------|----------|
| `sentiment_score` | yfinance news + FinBERT | 每10分钟 | 15% |
| `heat_trend` | Google Trends 7d变化率 | 每小时 | 10% |
| `social_sentiment` | StockTwits Bull/Bear ratio | 每10分钟 | 10% |
| `reddit_mentions` | Reddit 提及量变化 | 每小时 | 5% |
| `news_volume` | yfinance news 文章数 | 每10分钟 | 5% |

## 触发条件

- Cron: 每10分钟更新舆情因子
- Cron: 每小时推送舆情变化 (sentiment_hourly_push.py)
- 董事长指令: "舆情" / "热度" / "市场情绪"
- 决策引擎每次运行时自动拉取最新舆情因子

## 执行流程

```
1. yfinance.get_news(ticker) → 标题列表
2. FinBERT.score_text(title) → pos/neg/neu 分数 (fallback: 关键词)
3. pytrends.interest_over_time() → 7天搜索热度变化率
4. StockTwits.fetch(ticker) → Bull/Bear ratio
5. aggregate_sentiments() → 加权舆情分 (-1 到 +1)
6. 写入 sentiment 因子 → decision_engine_v2 自动读取
```

## 铁律

- 舆情因子是辅助，不替代量化和风控
- 极端舆情 (>80% bullish 或 >80% bearish) → 写 ALERT 到 outbox
- 禁止仅凭舆情做交易决策 — 必须结合量化+风控
