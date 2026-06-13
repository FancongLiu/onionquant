# ADR-005: Task Claim via Atomic mkdir (Filesystem Mutex)

**Date**: 2026-06-13 | **Status**: Accepted

## Context

Multiple cron sessions fire concurrently (inbox every 10min, research iteration every 2h, redteam code review). Each session must ensure it is the only one executing a given task type — overlapping execution would produce duplicate work, conflicting state writes, and wasted AI tokens.

Options:
1. Redis SETNX distributed lock
2. ZooKeeper ephemeral znodes
3. Database row-level lock (SELECT FOR UPDATE)
4. Filesystem atomic mkdir (POSIX Test-and-Set)

## Decision

Choose **atomic `mkdir` on the filesystem** — a single Python stdlib script (`scripts/task_claim.py`) with zero external dependencies.

## Rationale

- **Atomicity guaranteed by POSIX**: `mkdir()` with `exist_ok=False` is atomic on all filesystems (ext4, NTFS, APFS). If two processes race, exactly one succeeds — the other gets `FileExistsError`.
- **Zero dependencies**: Pure stdlib, no Redis/ZooKeeper/Postgres to install, configure, or maintain.
- **Deadlock prevention via TTL**: Each lock carries a 15-minute TTL. If the holding session crashes, the next contender detects the stale lock and reclaims it (moving the orphan to `_STALE_/` for audit trail).
- **OS-level analogy**: `.claim/` directory = mutex, `mkdir` = Test-and-Set, `rmdir` = release, TTL = deadlock prevention. This maps directly to well-understood OS primitives.
- **Single-machine deployment**: The agent system runs on one machine (WSL), making filesystem locks sufficient. No need for network-partition-tolerant distributed consensus.

## Consequences

- ✅ Zero operational overhead — no new services to run
- ✅ Crash-safe — orphan locks auto-reclaimed after 15min TTL
- ✅ Audit trail — stale locks moved to `_STALE_/` not silently deleted
- ✅ Git-ignorable — lock files in `company/task_claims/` are runtime-only
- ❌ Single-machine only — will not work across multiple hosts
- ❌ No priority queuing — first-come-first-served, no preemption
- ❌ Polling-only — no push notification when lock is released
