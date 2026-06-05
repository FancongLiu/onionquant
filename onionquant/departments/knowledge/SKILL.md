---
name: knowledge-management
description: 知识管理部 — 知识图谱维护·记忆文件管理·夜间做梦迭代·经验沉淀 (networkx + graph_rag + memory_sync)
---

# 知识管理部 (Knowledge Management Department)

## 工具栈

| 工具 | 用途 |
|------|------|
| `networkx` + `quant_graph_builder.py` | 股票关联图谱 + 量化工具依赖图 |
| `graph_rag.py` | 基于知识图谱的问答 |
| `scripts/update_knowledge_graph.py` | 定期更新图谱 |
| `scripts/memory_sync.py` | 记忆文件同步到 KG |
| `neo4j_store.py` | Neo4j 图数据库存储 (可选) |

## 管辖范围

- **知识图谱**: 股票关联网络 + 技术栈依赖图 + 因子关系图
- **记忆系统**: `C:\Users\28462\.claude\projects\e--2026-AgentStudy-Python-code\memory\` 下的所有 memory 文件
- **夜间做梦**: 每日复盘 → 提炼经验 → 更新权重 → 清理冗余
- **经验沉淀**: 交易决策→结果对比→成功/失败编码为规则

## 触发条件

- Cron: 每日 `python scripts/update_knowledge_graph.py` (凌晨)
- 夜间做梦: 北京时间 04:30 执行记忆压缩 + 策略迭代
- 董事长指令: "图谱" / "关联" / "记忆"

## 夜间"做梦"流程 (北京时间 04:30)

```
1. 读取当日所有 DECISION_v2_*.json → 决策记录
2. 对比当日实际价格走势 → 评分差异
3. 差异 > 阈值 → 标记为"需要反思"
4. 反思: 哪个因子误判了? 为什么?
5. 提炼为经验规则 → 存入 memory/
6. 更新 CATALYST_CALENDAR (如果有新事件)
7. 更新 WATCHLIST (如果有新标的)
8. 清理 48h 前的临时文件
9. 压缩当天对话记录 → 保留关键决策到 memory
10. 输出 DREAM_REPORT_*.md → chairman_outbox
```

## 铁律

- 不做梦 → 不进化。每天必须迭代。
- 经验编码为规则时标注置信度 (LOW/MEDIUM/HIGH)
- 知识图谱节点 24h 内未更新 → 标为 stale
- 记忆文件按类型组织，不堆积大文件
