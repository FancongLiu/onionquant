# ADR-007: Single-Session + Agent Fork Architecture (Cache-First Scheduling)

**Date**: 2026-06-13 | **Status**: Accepted

## Context

The agent system must handle: direct user conversations, periodic research iteration (2h), inbox scanning (10min), and red-team code review (1h). The naive approach — spawn a new Claude Code process per task — burns tokens at cold-start rates every time.

DeepSeek V4-Pro pricing structure: cache hit = ¥0.025/1M tokens, cache miss = ¥3/1M tokens (120:1 ratio). Cold sessions only get system prompt cache hits (~10%); warm sessions with accumulated conversation history get ~99% cache hits from turn 2 onward.

Options:
1. Multiple independent CLI sessions (one per cron task)
2. Single persistent session with serial execution
3. Single persistent session + Agent fork for parallelism
4. LangGraph / custom loop with direct API calls

## Decision

Choose **Single Persistent Session + Agent Fork for parallelism**. The project maintains exactly 1 persistent session (VS Code plugin or WSL CLI), and all parallel work uses Agent sub-tasks which **fork** from the parent session, inheriting the full prompt prefix (system prompt, tools, CLAUDE.md, memory files).

## Rationale

- **Cache prefix inheritance**: Agent forks copy the parent's prompt prefix. Since the 5-dimension cache key (system prompt, tools, model, message prefix, thinking config) aligns perfectly between parent and fork, sub-Agents achieve 92-93% cache hit rates. Independent sessions would achieve ~10% (system prompt only).
- **Cost math**: 1 independent session per hour = 24 cold starts/day × ~30K prompt tokens × ¥3/M = ~¥2.16/day per cron. At 3 crons + inbox + redteam = ~¥10.80/day just for cold starts. Agent forks amortize the warm prefix: 3 parallel agents cost 1.1-1.5x the tokens of 1 serial run, not 3x.
- **Context accumulation**: The main session's conversation history builds a rich context that subsequent user interactions benefit from — 99% cache hits on follow-up messages. Independent sessions discard this accumulation each time.
- **Architecture clarity**: Crons are thin dispatchers — they claim a task lock, check for work, and either exit immediately (no work) or delegate to Agent forks. The heavy lifting always happens inside fork-sub-sessions that share the parent's cache.

## Consequences

- ✅ 95% reduction in daily AI calls (~48 vs ~983 pre-optimization)
- ✅ Daily cost ¥5-8 vs ¥30-50 pre-optimization (75% reduction)
- ✅ Concurrency via Agent fork without cache penalty
- ✅ Context continuity — direct user conversations benefit from cron-accumulated knowledge
- ❌ Single point of failure — if the main session crashes, all work stops (mitigated by watchdog + tmux auto-restart)
- ❌ Parallelism capped at ~3 agents (diminishing returns beyond 3 concurrent forks)
- ❌ Cannot distribute across machines — single-machine architecture
- ❌ Fork isolation is partial — agents share memory files, so concurrent writes need coordination
