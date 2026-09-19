#!/usr/bin/env bash
# All three layers. Starts and stops its own dev server for the smoke test.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
note() { printf '\n\033[1m%s\033[0m\n' "$1"; }

if [ ! -f planner/graph_cache.json ]; then
  note "building graph cache (~40s, first run only)"
  python3 -m planner.build_cache || exit 1
fi

note "1+2. planner and pipeline"
python3 -m unittest discover tests || fail=1

note "3. frontend typecheck, lint, build"
( cd frontend && npm run typecheck && npm run lint && npm run build ) || fail=1

note "4. frontend smoke"
# Needs both the planner service and the dev server; starts and stops its own.
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
if ! command -v node >/dev/null; then
  echo "  skipped: node not found"
elif ! "$PY" -c "import fastapi" 2>/dev/null; then
  echo "  skipped: fastapi not installed (.venv/bin/pip install fastapi uvicorn)"
else
  # Bind 127.0.0.1 explicitly: on macOS localhost resolves to ::1 first.
  "$PY" -m uvicorn planner.server:app --host 127.0.0.1 --port 8000 \
    >/tmp/unmapped-api.log 2>&1 & echo $! >/tmp/unmapped-api.pid
  ( cd frontend && npm run dev >/tmp/unmapped-dev.log 2>&1 & echo $! >/tmp/unmapped-dev.pid )
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null http://127.0.0.1:8000/places \
      && curl -sf -o /dev/null http://localhost:5173/ && break
    sleep 0.5
  done
  node tests/smoke_frontend.mjs || fail=1
  kill "$(cat /tmp/unmapped-dev.pid)" "$(cat /tmp/unmapped-api.pid)" 2>/dev/null
fi

note "$([ $fail -eq 0 ] && echo 'all green' || echo 'FAILURES above')"
exit $fail
