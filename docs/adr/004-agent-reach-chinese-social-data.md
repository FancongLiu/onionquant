# ADR-004: Agent-Reach for Chinese Social Media Data

**Date**: 2026-06-13 | **Status**: Proposed

## Context

Sentiment Intel Department 需要中文社交平台数据（Bilibili、小红书、微信、知乎）
来增强针对 A 股/中概股的舆情分析。当前数据源主要是 Reddit/Twitter 等英文平台。

Agent-Reach (26K ★, Panniantong/Agent-Reach) 是第一个支持中文平台
零 API 费用的 Agent 搜索工具。

## Decision

Proposed: 集成 Agent-Reach 到 Sentiment Intel Department 工具链。

## Evaluation

- ✅ 零 API 费用（CLI 工具，非付费 API）
- ✅ 覆盖 Bilibili、小红书、微信公众号（当前完全缺失的数据源）
- ✅ 26K stars，活跃维护
- ✅ Python CLI，与现技术栈兼容
- ❌ 非官方工具（个人开发者），可靠性待验证
- ❌ 依赖外部平台反爬策略，可能不稳定

## Status

Proposed — 需要先在测试环境验证稳定性后再集成到生产管道。
优先级：P1（中概股/中国相关政策分析场景触发）
