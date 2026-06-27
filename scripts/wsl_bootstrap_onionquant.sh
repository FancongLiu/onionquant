#!/usr/bin/env bash
set -euo pipefail

ROOT="${ONIONQUANT_ROOT:-$HOME/onionquant}"
SOURCE_ROOT="${ONIONQUANT_SOURCE_ROOT:-/mnt/e/2026_AgentStudy/Python_code}"

echo "OnionQuant WSL bootstrap"
echo "Target: $ROOT"
echo "Source: $SOURCE_ROOT"

if [ ! -d "$ROOT/.git" ]; then
  echo "Creating WSL-native workspace..."
  mkdir -p "$(dirname "$ROOT")"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '.git' \
      --exclude '.venv' \
      --exclude '.venv-linux' \
      --exclude '__pycache__' \
      --exclude '.pytest_cache' \
      "$SOURCE_ROOT/" "$ROOT/"
  else
    cp -a "$SOURCE_ROOT" "$ROOT"
  fi
fi

cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m venv .venv-linux
. .venv-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "WSL environment ready."
echo "Run: cd $ROOT && . .venv-linux/bin/activate && python company/server.py"
