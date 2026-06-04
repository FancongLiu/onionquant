---
name: department-cron-prompts
description: 6部门对应的 cron 提示词模板，每个 cron 启动时加载对应部门 SKILL
---

# Cron 提示词模板 (部门驱动)

## Inbox 扫描 (每10分钟, :00/:10/:20...)
**部门**: 执行交易部 + 策略研究部
**提示词**:
```
[部门: 执行交易部] 扫描 company/chairman_inbox/ 待处理消息。
1. task_claim.py try inbox → SKIPPED? 退出
2. 列出 *.md 待处理文件
3. 0个→release退出 | 1个→直接处理 | 2-5个→并行Agent每文件1个
4. 处理完移入 processed/ → release
铁律: 按董事长指令优先级 P0→P3 排序。P0=涉及持仓/交易/风险 立即处理。
```

## 迭代引擎 (每30分钟, :17/:47)
**部门**: 策略研究部 + 舆情分析部
**提示词**:
```
[部门: 策略研究部+舆情分析部] 5并行WebSearch Agent:
1. DXYZ+SpaceX IPO+S-1 最新进展
2. Starship IFT-12 状态 (5/21 06:30北京)
3. 存储/半导体 (MU/SNDK/NVDA/SOX) 催化更新
4. 航天 (RKLB/ASTS/LUNR/RDW) 行业动态
5. 光模块+AI芯片 (LITE/COHR/TSEM/AVGO/MRVL/AMD) 新闻+舆情
汇总→更新 TASK_TRACKER + context_state + CATALYST_CALENDAR
铁律: 搜索时间用北京时间。所有搜索加 site:github.com OR site:reuters.com OR site:bloomberg.com
```

## 红队审查 (每30分钟, :33/:03)
**部门**: 风险管理部
**提示词**:
```
[部门: 风险管理部] 4并行Grep Agent代码安全扫描:
1. shell=True + os.system + subprocess风险
2. eval()/exec()/__import__/pickle.load
3. 硬编码密钥 (api_key/password/token/secret)
4. innerHTML未转义/XSS/命令注入
汇总→有问题写ALERT到outbox，无问题回clean。
额外: 检查 WATCHLIST beta_spx 是否匹配当前波动率实际值。
```

## 舆情推送 (每小时, :42)
**部门**: 舆情分析部
**提示词**:
```
[部门: 舆情分析部] 全量舆情因子更新:
1. python -c "from quant_framework.data.fetchers.reddit_sentiment import fetch_hot_posts; ..." (如API可用)
2. pytrends Google Trends 热度曲线 (7d变化率)
3. StockTwits Bull/Bear ratio (待修)
4. yfinance news批量→FinBERT评分
5. 汇总舆情因子→写入 sentiment_cache.json
6. 有极端信号 (>80%单向) → 微信推送
```

## 每日管道 (工作日, 美东盘后=北京时间04:00)
**部门**: 知识管理部 + 策略研究部
**提示词**:
```
[部门: 知识管理部] 每日复盘+知识迭代:
1. python scripts/decision_engine_v2.py (全量31标的)
2. python scripts/binary_catalyst_backtest.py (DXYZ+其他催化)
3. python scripts/update_knowledge_graph.py (更新关联图谱)
4. 对比历史决策 vs 实际走势 → 反思差异
5. 更新记忆: 成功的规则→强化, 失败的规则→衰减
6. 清理48h+旧文件
7. 写 DREAM_REPORT_YYYYMMDD.md → chairman_outbox
铁律: 不跳过任何一步。每步输出到日志。
```

## 连通守护 (每小时, :55)
**部门**: 连通守护部
**提示词**:
```
[部门: 连通守护部] 7通道巡检:
1. tmux会话存活检查
2. Hermes微信网关 health check
3. Dashboard前端 curl localhost:8765/api/status (本地检查; 外网用 tunnel URL)
4. Inbox/Outbox消息流断流检测
5. WSL↔Windows文件桥读写测试
6. DeepSeek API连通性
7. Cloudflared隧道进程检查
全绿→无事/有红→自动修复→修复失败→写ALERT+微信通知
```
