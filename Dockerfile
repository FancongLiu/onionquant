# OnionQuant — Docker image
#   docker build -t onionquant .
#   docker run -p 8765:8765 --env-file .env onionquant          # server
#   docker run --env-file .env onionquant scheduler              # background tasks

FROM python:3.12-slim

LABEL org.opencontainers.image.title="OnionQuant"
LABEL org.opencontainers.image.description="Quantitative research & multi-agent dashboard"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System deps: curl for healthcheck ──
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# ── Python deps (cacheable layer) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code (order: least-changed → most-changed for cache) ──
COPY pyproject.toml .
COPY infrastructure/ infrastructure/
COPY quant_framework/ quant_framework/
COPY onionquant/ onionquant/
COPY scripts/ scripts/
COPY company/ company/

# Runtime directories
RUN mkdir -p /app/company/task_claims \
    /app/company/chairman_inbox/processed \
    /app/company/chairman_outbox \
    /app/company/sentiment_data/collector

# ── Dual-mode entrypoint ──
COPY <<'ENTRY' /entrypoint.sh
#!/bin/bash
set -euo pipefail
MODE="${1:-server}"
case "$MODE" in
  server)
    echo "[onionquant] Starting dashboard server on :8765"
    exec python onionquant/server.py
    ;;
  scheduler)
    echo "[onionquant] Starting background task scheduler"
    exec python scripts/background_scheduler.py
    ;;
  *)
    echo "Usage: docker run onionquant [server|scheduler]"
    exit 1
    ;;
esac
ENTRY

RUN chmod +x /entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["/entrypoint.sh"]
CMD ["server"]
