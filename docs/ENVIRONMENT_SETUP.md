# OnionQuant Environment Setup

## Recommended Near-Term Mode

Use one backend runtime and one AI runtime:

- Backend: `company/server.py` + `scripts/background_scheduler.py`
- AI: current interactive Codex/Claude session only
- Avoid: AI cron loops, `claude -p` polling loops, Flash fallback, duplicate Python daemons
- Self-evolution proposals go to `company/evolution_queue/` and do not auto-trigger AI

## Windows Runtime

Start or restart the local backend:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_onionquant.ps1 -Restart
```

Stop the local backend:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_onionquant.ps1
```

Status is written to:

```text
company\runtime\process_status.json
```

## WSL Target Runtime

For better Linux tooling and UTF-8 behavior, bootstrap a WSL-native copy:

```bash
bash scripts/wsl_bootstrap_onionquant.sh
```

Preferred final location:

```text
~/onionquant
```

Avoid running heavy file operations from `/mnt/e/...` long-term. Use `/mnt/e/...`
only as a migration source or Windows interop path.

## Token Guardrails

Token-consuming daemon scripts are disabled by default.

Enable only intentionally:

```bash
export ONIONQUANT_ALLOW_AI_DAEMON=1
export ONIONQUANT_ALLOW_RESEARCH_ITERATION=1
export ONIONQUANT_ENABLE_WSL_AI_DAEMON=1
```

Default Python scheduler tasks are non-AI and should remain zero-token.
