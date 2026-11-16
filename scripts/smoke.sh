#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT"

API="${API:-http://127.0.0.1:8000/api}"

echo "== health =="
curl -sf "$API/health" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('service')=='aqt-api', d; print(d)"

echo "== backtest =="
curl -sf -X POST "$API/backtests" \
  -H 'Content-Type: application/json' \
  -d '{"strategy_id":"ma_cross_demo","symbol":"600519","start":"2023-01-01","end":"2025-12-31"}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print('run', d['id'], 'return', d['metrics']['total_return'], 'trades', d['metrics']['trade_count'])"

echo "== enable strategy + paper tick =="
curl -sf -X POST "$API/strategies/ma_cross_demo/toggle" \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true}' >/dev/null
curl -sf -X POST "$API/paper/tick" | python -m json.tool

echo "== account / positions / orders =="
curl -sf "$API/account" | python -m json.tool
curl -sf "$API/positions" | python -c "import sys,json; print('positions', len(json.load(sys.stdin)))"
curl -sf "$API/orders" | python -c "import sys,json; print('orders', len(json.load(sys.stdin)))"

echo "== small sim order =="
curl -sf -X POST "$API/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"000001","side":"BUY","quantity":100}' \
  | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('success'), d; print('filled', d['filled_quantity'], '@', d['filled_price'])"

echo "== risk reject oversized order =="
curl -sf -X POST "$API/orders" \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"600519","side":"BUY","quantity":1000000,"price":2000}' \
  | python -m json.tool
curl -sf "$API/risk/events?limit=3" | python -c "import sys,json; ev=json.load(sys.stdin); print('risk_events', len(ev)); print(ev[0]['event_type'] if ev else 'none')"

echo "SMOKE OK"