# OnionQuant Auto-Evolve System

This document defines the first baseline for 24h autonomous evolution.

## Goal

Continuously improve OnionQuant as both:

- a job-search portfolio that demonstrates AI agent engineering ability, and
- a US equity research system with real data, backtests, risk controls, and reports.

The loop runs at machine cadence, not human day/night cadence.

## Permission Model

Allowed without per-change user review:

- Change, delete, or replace files inside `E:\2026_AgentStudy\Python_code`.
- Change the matching GitHub repository, including branches, workflow files, commits, pushes, and merges.
- Refactor architecture when evidence shows the current design is weak.
- Update the website, documentation, tests, CI, quant research pipeline, reports, and internal dashboards.

Hard stops:

- Do not delete, move, or overwrite unrelated personal files outside the workspace.
- Do not spend money or enable paid services.
- Do not place real trades.
- Do not output, copy, or archive secret values.
- Do not use `git push --force` unless the user explicitly asks for it in that turn.

## Operating Loop

Each autonomous cycle should do one bounded work unit:

1. Observe: read `context_state.json`, task tracker, runtime status, GitHub status, tests, logs, and queue files.
2. Select: pick the highest-value P0/P1 task for job-search or trading-system quality.
3. Build: make a focused change on a `codex/` branch.
4. Verify: run the smallest meaningful tests, lint, endpoint checks, or page checks.
5. Red-team: check safety, secrets, accidental destructive actions, and fake progress.
6. Publish: commit and push when verification passes.
7. Record: update `context_state.json`, task tracker/progress notes, and a concise report.

## Roles

- Commander: chooses the next task and keeps the loop bounded.
- Product reviewer: asks whether the change helps job search or demo clarity.
- Quant researcher: asks whether trading outputs are supported by data and risk controls.
- Engineer: implements code and keeps modules maintainable.
- Test owner: requires executable verification.
- Red team: challenges safety, security, and hidden regressions.
- Interviewer: asks whether the result is explainable to a hiring manager.
- Publisher: commits, pushes, and records.

These are review lenses inside the same controlled loop, not unlimited parallel sessions.

## Liveness

AI sessions are not trusted to keep themselves alive.

- `scripts/autonomy_watchdog.py heartbeat` writes `company/runtime/agent_heartbeat.json`.
- `scripts/autonomy_watchdog.py queue-if-stale` checks the heartbeat and queues one recovery task when stale.
- `scripts/background_scheduler.py` runs the watchdog every 10 minutes as a pure Python task.
- `scripts/task_claim.py try autonomy` is the single-main-session lock.

If the upstream AI service is unavailable, Python jobs continue and the next recovery cycle should retry later rather than spinning many sessions.

## Concurrency

Default: one main builder session.

Parallelism is allowed only for 2-3 independent research/review tasks when it clearly improves speed. Code edits, tests, commits, and merges remain serialized through the autonomy lock.
