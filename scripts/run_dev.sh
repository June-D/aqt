#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

export PYTHONPATH="$ROOT"

DEV_UI=0
if [[ "${1:-}" == "--dev-ui" ]]; then
  DEV_UI=1
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install --registry=https://registry.npmjs.org/)
fi

if [[ "$DEV_UI" -eq 1 ]]; then
  (cd frontend && npm run dev) &
  UI_PID=$!
  trap 'kill $UI_PID 2>/dev/null || true' EXIT
else
  (cd frontend && npm run build)
fi

mkdir -p data/cache
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
