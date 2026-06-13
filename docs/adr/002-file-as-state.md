# ADR-002: File-as-State for Agent State Management

**Date**: 2026-06-13 | **Status**: Accepted

## Context

Agent 系统需要跨会话持久化状态：任务队列、中断恢复、进度跟踪。选项：
1. Redis / PostgreSQL 外部存储
2. 文件系统 JSON（File-as-State）
3. SQLite 嵌入式数据库

## Decision

选择 **File-as-State（文件系统 JSON）** 作为主状态存储，LangGraph SqliteSaver 作为复杂工作流断点。

## Rationale

- 单机部署，不需要分布式状态
- 零外部依赖，运维成本为零
- 人类可读可编辑，调试方便
- 明确升级路径：文件 → Redis → Postgres/DynamoDB（按规模）
- Anthropic 2026 cwc-long-running-agents 官方推荐模式
- LangGraph 复杂工作流用 SqliteSaver（非文件 JSON），恰当的关注点分离

## Consequences

- ✅ 零运维开销，零新依赖
- ✅ git 可审计（敏感文件已 gitignore）
- ❌ 不支持多机并发
- ❌ 无原生查询能力（复杂查询靠 Python 读取后处理）
