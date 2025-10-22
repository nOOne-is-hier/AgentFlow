#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Prefer uv if available
if command -v uv >/dev/null 2>&1; then
  uv venv -p 3.11 || true
  uv pip install -r backend/requirements.txt
  uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
else
  python -m venv .venv || true
  source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
  pip install -U pip
  pip install -r backend/requirements.txt
  uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
fi
