# ADR-010: File-Based Inbox/Outbox Communication Pattern

**Date**: 2026-06-13 | **Status**: Accepted

## Context

The Chairman (human user) and the Agent (AI) need bidirectional asynchronous communication. The Chairman sends instructions; the Agent sends questions, reports, and alerts. Both operate on different schedules — the Chairman checks in periodically, while the Agent runs continuous cron cycles.

Options:
1. WebSocket bidirectional channel (real-time, stateful)
2. REST API with polling (request/response)
3. Message queue (Redis Pub/Sub, RabbitMQ)
4. File-based inbox/outbox with SSE push to frontend

## Decision

Choose **file-based inbox/outbox** with **Server-Sent Events (SSE)** for push notifications to the frontend.

```
Chairman → Agent:  write company/chairman_inbox/*.md  →  Agent scans each cycle
Agent → Chairman:  write company/chairman_outbox/*.md →  SSE push → frontend badge
```

The frontend server (`onionquant/server.py` on port 8765) watches the outbox directory and pushes new files via SSE to the browser. The Agent scans the inbox at the start of each cycle (cron or user session).

## Rationale

- **Zero infrastructure**: No Redis, no RabbitMQ, no WebSocket server. Filesystem is already there, already backed up, already git-tracked (sensitive files gitignored).
- **Asynchronous by design**: The Chairman writes a message and closes the browser. The Agent picks it up on the next cron cycle. The Agent writes a report and moves on. The Chairman sees it whenever they open the frontend. No synchronous coupling.
- **Audit trail**: Every message is a Markdown file on disk. Full history searchable with `grep`. No messages lost in queue TTL or WebSocket disconnects.
- **Simple frontend**: SSE is a one-way HTTP stream — the browser opens a connection and receives events. No WebSocket handshake, no reconnection logic, no STOMP/ Socket.IO protocol layer.
- **File system as API**: The protocol is self-documenting. A new developer can understand the system by reading `ls company/chairman_inbox/` and `ls company/chairman_outbox/`. No Swagger docs needed.
- **ASK pattern**: When the Agent needs Chairman approval (risky operation, payment required, uncertain decision), it writes an `ASK_*.md` file and continues with other work. The Chairman sees the question, approves or rejects by writing a reply to the inbox. No polling loops, no blocking waits.

## Consequences

- ✅ Zero new infrastructure — filesystem + SSE are built-in
- ✅ Complete audit trail — every message is a file on disk
- ✅ Async decoupling — Chairman and Agent operate independently
- ✅ Simple debugging — read the files directly
- ❌ Latency bounded by cron interval (10min for inbox scan)
- ❌ No real-time bidirectional chat — not suitable for synchronous conversations
- ❌ File system inode pressure if outbox is not regularly cleaned (>10K files)
- ❌ No message ordering guarantees (filesystem sorting by name/date)
- ❌ Concurrent writes to same outbox file can corrupt (mitigated by single-writer Agent)
