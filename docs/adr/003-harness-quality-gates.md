# ADR-003: Harness Quality Gates (Anthropic 2026 Pattern)

**Date**: 2026-06-13 | **Status**: Accepted

## Context

Agent 长期运行需要质量保障机制。无监督 Agent 可能：
- 自吹自擂（声称完成任务但实际没做）
- 质量退化（上下文积累导致输出变差）
- 重复踩坑（相同错误反复出现）

选项：
1. 纯人工审查每条回复
2. 自动化质量门（Anthropic cwc-long-running-agents 模式）
3. 无质量门（信任 Agent）

## Decision

选择 **Harness 四原语**（Anthropic 2026 官方模式）：
1. Default-FAIL 合约 — 标准初始 false，Agent 必须证明
2. PROGRESS.md 自维护 — Agent 读写自己的进度
3. Fresh Evaluator — 独立无写权限 Agent 审查产出
4. Auto-Skill 蒸馏 — 复杂任务沉淀为可复用 Skill

## Rationale

- 直接从 Anthropic 2026 cwc-long-running-agents 官方 Repo 借鉴
- 四原语加起来 <500 行代码，非重型框架
- Fresh Evaluator 使用独立 DeepSeek 调用，审查者与被审查者隔离
- Skill 蒸馏参考 Hermes Agent 的 Closed Learning Loop

## Consequences

- ✅ 每条回复自动评分 0-10，不合格的标记 EVAL
- ✅ Agent 崩溃后从 PROGRESS.md 恢复
- ✅ 重复模式自动提炼为 Skill
- ❌ Fresh Evaluator 增加额外 API 调用（~¥0.001/次）
