# ADR-006: Context Persistence Protocol (Interrupt-Service-Routine Pattern)

**Date**: 2026-06-13 | **Status**: Accepted

## Context

Cron-triggered sessions are stateless — each firing starts a fresh Claude Code process with no access to the previous session's conversation history. The agent must remember: pending tasks, portfolio positions, market events in progress, and what research was underway.

Options:
1. Dump full conversation context to a file and reload (context injection)
2. Structured JSON state checkpoint + memory file bridge (ISR pattern)
3. LangGraph persistence layer (SqliteSaver / PostgresSaver)
4. External task queue (Celery / Redis Queue)

## Decision

Choose the **Interrupt-Service-Routine (ISR) pattern**: `context_state.json` checkpoint file + `memory/` directory files as the cross-session bridge mechanism.

## Rationale

- **OS ISR analogy**: Like an interrupt service routine, each session saves its "register state" before yielding and restores it on entry. `pending_actions` = interrupt queue, `key_context` = register file.
- **Two-tier persistence**: Frequently-changing operational state goes to `context_state.json` (lightweight JSON, ~50KB). Stable knowledge/decisions go to `memory/` files (Markdown with frontmatter, cross-referenced).
- **Human-readable**: JSON and Markdown are debuggable without tooling. If a session fails to restore, a human (or human + AI) can read the file and continue manually.
- **Progressive commitment**: State moves from `pending_actions` → `key_context` → `memory/` as confidence increases. Hot operational state stays in the fast JSON path; cold stable learnings graduate to memory files.
- **Session decoupling**: Memory files are shared across all sessions (crons, user sessions, Agent sub-tasks). `context_state.json` is the volatile session handoff surface.

## Consequences

- ✅ Zero new infrastructure — filesystem already exists
- ✅ Crash recovery — session can resume from exact interruption point
- ✅ Progressive state graduation prevents stale operational data in long-term memory
- ❌ Manual discipline required — agent must write checkpoints, no auto-save
- ❌ No atomic multi-field updates — partial writes possible if process dies mid-write
- ❌ State drift risk — if a session exits without checkpointing, next session sees stale state
- ❌ Write-on-read pattern not supported — memory files are append/update, not queryable
