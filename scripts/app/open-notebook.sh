#!/bin/bash
# Open Notebook local service controller (macOS).
#   open-notebook.sh start   -> start SurrealDB, API, worker, frontend (idempotent)
#   open-notebook.sh stop    -> stop everything started by this script
#   open-notebook.sh status  -> print what is running
#   open-notebook.sh logs    -> tail all logs
#
# State lives in data/app/ (pids + logs). Ports: SurrealDB 8000, API 5055, UI 3000.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT/data/app"
LOG_DIR="$APP_DIR/logs"
PID_DIR="$APP_DIR/pids"
DB_DIR="$ROOT/surreal_data"
mkdir -p "$LOG_DIR" "$PID_DIR" "$DB_DIR"

SURREAL_PORT="${SURREAL_PORT:-8000}"
API_PORT="${API_PORT:-5055}"
UI_PORT="${UI_PORT:-3000}"
UI_URL="http://localhost:$UI_PORT"

# GUI launches do not inherit the shell PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$ROOT" || exit 1

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*"; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

pid_of() { [ -f "$PID_DIR/$1.pid" ] && cat "$PID_DIR/$1.pid"; }

alive() { local p; p="$(pid_of "$1")"; [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

wait_port() { # name port seconds
  local i=0
  while ! port_busy "$2"; do
    sleep 1; i=$((i + 1))
    if [ "$i" -ge "$3" ]; then log "❌ $1 did not open port $2 in ${3}s (see $LOG_DIR/$1.log)"; return 1; fi
    if [ -f "$PID_DIR/$1.pid" ] && ! alive "$1"; then log "❌ $1 exited early (see $LOG_DIR/$1.log)"; return 1; fi
  done
  return 0
}

ensure_env() {
  if [ ! -f "$ROOT/.env" ]; then
    log "Creating .env"
    local key
    key="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)"
    cat >"$ROOT/.env" <<EOF
OPEN_NOTEBOOK_ENCRYPTION_KEY=$key
SURREAL_URL=ws://localhost:$SURREAL_PORT/rpc
SURREAL_USER=root
SURREAL_PASSWORD=root
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
API_HOST=127.0.0.1
API_PORT=$API_PORT
API_RELOAD=false
EOF
  fi
}

start_bg() { # name command...
  local name="$1"; shift
  if alive "$name"; then log "• $name already running (pid $(pid_of "$name"))"; return 0; fi
  log "Starting $name"
  nohup "$@" >"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$PID_DIR/$name.pid"
}

start() {
  ensure_env
  set -a; . "$ROOT/.env"; set +a

  # 1. SurrealDB (reuse if something already listens, e.g. brew service)
  if port_busy "$SURREAL_PORT"; then
    log "• SurrealDB port $SURREAL_PORT already in use — reusing"
  else
    # Migrations use SurrealDB v2 syntax; prefer a v2 binary if present.
    SURREAL_BIN="$(command -v surreal2 || command -v surreal)"
    [ -z "$SURREAL_BIN" ] && { log "❌ surreal binary not found (brew install surrealdb/tap/surreal)"; return 1; }
    start_bg surrealdb "$SURREAL_BIN" start --log info --user "$SURREAL_USER" --pass "$SURREAL_PASSWORD" \
      --bind "127.0.0.1:$SURREAL_PORT" "rocksdb://$DB_DIR/open_notebook.db"
    wait_port surrealdb "$SURREAL_PORT" 30 || return 1
  fi

  # 2. Python deps + API
  if [ ! -d "$ROOT/.venv" ]; then log "Installing Python deps (uv sync)"; uv sync >>"$LOG_DIR/setup.log" 2>&1 || { log "❌ uv sync failed"; return 1; }; fi
  if port_busy "$API_PORT" && ! alive api; then
    log "• API port $API_PORT already in use — reusing"
  else
    start_bg api uv run --no-sync --env-file "$ROOT/.env" uvicorn api.main:app --host 127.0.0.1 --port "$API_PORT"
    wait_port api "$API_PORT" 90 || return 1
  fi

  # 3. Background worker (podcasts, async jobs)
  start_bg worker uv run --no-sync --env-file "$ROOT/.env" surreal-commands-worker --import-modules commands

  # 4. Frontend (production standalone build, built once)
  if [ ! -d "$ROOT/frontend/node_modules" ]; then log "Installing frontend deps (npm install)"; (cd frontend && npm install) >>"$LOG_DIR/setup.log" 2>&1 || { log "❌ npm install failed"; return 1; }; fi
  # Next.js may nest the standalone tree (e.g. .next/standalone/Projects/open-notebook/frontend/server.js)
  find_server() { find "$ROOT/frontend/.next/standalone" -name server.js -not -path '*/node_modules/*' 2>/dev/null | head -1; }
  SERVER_JS="$(find_server)"
  if [ -z "$SERVER_JS" ] || [ "$ROOT/frontend/package.json" -nt "$SERVER_JS" ]; then
    log "Building frontend (first run, ~1-2 min)"
    (cd frontend && npm run build) >>"$LOG_DIR/build.log" 2>&1 || { log "❌ frontend build failed (see $LOG_DIR/build.log)"; return 1; }
    SERVER_JS="$(find_server)"
    [ -z "$SERVER_JS" ] && { log "❌ standalone server.js not found after build"; return 1; }
    # standalone output needs static assets + public copied next to server.js
    SERVER_DIR="$(dirname "$SERVER_JS")"
    rm -rf "$SERVER_DIR/.next/static" "$SERVER_DIR/public"
    cp -R frontend/.next/static "$SERVER_DIR/.next/static"
    [ -d frontend/public ] && cp -R frontend/public "$SERVER_DIR/public"
  fi
  if port_busy "$UI_PORT" && ! alive frontend; then
    log "• UI port $UI_PORT already in use — reusing"
  else
    start_bg frontend env PORT="$UI_PORT" HOSTNAME=127.0.0.1 INTERNAL_API_URL="http://127.0.0.1:$API_PORT" \
      node "$SERVER_JS"
    wait_port frontend "$UI_PORT" 60 || return 1
  fi

  log "✅ Open Notebook is up: $UI_URL  (API http://localhost:$API_PORT)"
  echo "$UI_URL"
}

stop_one() {
  local name="$1" p
  p="$(pid_of "$name")"
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    log "Stopping $name (pid $p)"
    # kill the whole process group children too (uv -> python, node)
    pkill -TERM -P "$p" 2>/dev/null
    kill -TERM "$p" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$p" 2>/dev/null && { pkill -KILL -P "$p" 2>/dev/null; kill -KILL "$p" 2>/dev/null; }
  fi
  rm -f "$PID_DIR/$name.pid"
}

stop() {
  for n in frontend worker api surrealdb; do stop_one "$n"; done
  # safety net: anything still holding our ports that we spawned from this repo
  pkill -f "$ROOT/frontend/.next/standalone/.*server.js" 2>/dev/null
  pkill -f "uvicorn api.main:app --host 127.0.0.1 --port $API_PORT" 2>/dev/null
  pkill -f "surreal-commands-worker --import-modules commands" 2>/dev/null
  pkill -f "rocksdb://$DB_DIR/open_notebook.db" 2>/dev/null
  log "🛑 Open Notebook stopped"
}

status() {
  for n in surrealdb api worker frontend; do
    if alive "$n"; then echo "$n: running (pid $(pid_of "$n"))"; else echo "$n: stopped"; fi
  done
  for p in "$SURREAL_PORT" "$API_PORT" "$UI_PORT"; do port_busy "$p" && echo "port $p: listening" || echo "port $p: free"; done
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) tail -n 50 -F "$LOG_DIR"/*.log ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}"; exit 2 ;;
esac
