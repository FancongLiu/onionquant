# ADR-001: Claude Code Persistent Session as Agent Runtime

**Date**: 2026-06-13 | **Status**: Accepted

## Context

需要 24/7 运行的 Agent 系统处理董事长信箱消息。选项：
1. 每消息新启动 Claude Code 进程（`claude -p` 无 session）
2. Claude Code `--session-id` 持久会话
3. LangGraph StateGraph 自建 Agent 循环

## Decision

选择 **Claude Code `--session-id` 持久会话**。

## Rationale

- 复用上下文缓存：CLAUDE.md + memory 文件首次加载后缓存命中 ~90%
- 对话历史自然累积，后续消息记住之前讨论的内容
- 每服务器启动生成新 UUID，避免会话冲突
- 失败时自动回退到上下文注入 DeepSeek API
- Anthropic 官方支持，非社区 hack

## Consequences

- ✅ 每条后续消息 token 成本极低（缓存命中 90%+）
- ✅ 同一会话内多轮记忆，Agent 不会"失忆"
- ❌ 每服务器重启 = 新会话 = 历史清空
- ❌ 并发消息需要排队（同一 session 不支持并发）
