---
name: it-tech-evolve
description: IT/Tech 部门自进化研究周期 — 扫描外部技术趋势 + 内部错误审计，产出报告并更新进度
version: 1.0.0
auto_generated: true
distilled_at: 2026-06-13 09:00 CST
source_task: IT/Tech 自进化研究
tool_calls_used: 8
---

# IT/Tech 自进化研究周期

## 触发条件
用户请求涉及: IT/Tech 自进化、技术趋势扫描、系统健康检查、进化周期

## 执行步骤

### Phase 1: OBSERVE (并行收集)
1. **WebSearch** — 搜索 `GitHub trending AI agent <当前月份年份>`，记录 3 个最相关新项目/技术
2. **Glob logs/** — 列出所有日志文件
3. **Read error logs** — 读取 `*_err.log` / `*_error.log`，提取最近的异常模式

### Phase 2: ANALYZE (匹配分析)
4. 对比新技术与 OnionQuant 当前架构（缓存策略、memory 桥接、SKILL.md、Agent 派发）
5. 判定每条技术的匹配度（高/中/低）并给出理由
6. 分析错误日志的根因、影响面、修复方向

### Phase 3: PROPOSE (产出报告)
7. 写 `TECH_REPORT_*.md` → `company/chairman_outbox/`（如果有新技术发现）
8. 写 `ALERT_*.md` → `company/chairman_outbox/`（如果有内部问题）
9. 写 `SENTINEL_*.md` → `company/chairman_outbox/`（如果一切正常）

### Phase 4: PERSIST (更新状态)
10. 更新 `company/harness/PROGRESS.md`：记录本次进化周期完成
11. 如果有 5 步以上的可复用模式 → 蒸馏为 skill 存入 `company/departments/it_tech/discovered_skills/`

## 报告命名规范
- `TECH_REPORT_YYYYMMDD_topic.md` — 新技术发现
- `ALERT_YYYYMMDD_issue.md` — 内部问题告警
- `SENTINEL_YYYYMMDD_status.md` — 系统正常哨兵

## 成功指标
- 至少 1 份报告产出（TECH_REPORT / ALERT / SENTINEL）
- PROGRESS.md 已更新
- 错误日志已审计

## 注意事项
- Phase 1 的 WebSearch 和 log read 可并行执行
- 报告写完后不需等董事长确认（outbox 自动推送）
- 如果 log 目录为空，跳过错误审计直接写 SENTINEL
