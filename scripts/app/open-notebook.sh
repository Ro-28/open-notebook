#!/bin/bash
# Open Notebook local service controller (macOS).
#   open-notebook.sh start   -> start SurrealDB, API, worker, frontend (idempotent)
#   open-notebook.sh stop    -> stop everything started by this script
#   open-notebook.sh status  -> print what is running
#   open-notebook.sh logs    -> tail all logs
#
# State lives in data/app/ (pids + logs). Ports: SurrealDB 8000, API 5055, UI 3001, OpenMAIC 3100.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT/data/app"
LOG_DIR="$APP_DIR/logs"
PID_DIR="$APP_DIR/pids"
DB_DIR="$ROOT/surreal_data"
mkdir -p "$LOG_DIR" "$PID_DIR" "$DB_DIR"

SURREAL_PORT="${SURREAL_PORT:-8000}"
API_PORT="${API_PORT:-5055}"
UI_PORT="${UI_PORT:-3001}"
UI_URL="http://localhost:$UI_PORT"
MAIC_PORT="${OPENMAIC_PORT:-3100}"
MAIC_DIR="$ROOT/vendor/openmaic"
SUB_PROXY_PORT="${SUBSCRIPTION_PROXY_PORT:-3101}"

# Tell the API it runs under this launcher (enables POST /api/app/shutdown from the UI).
export OPEN_NOTEBOOK_LAUNCHER_SCRIPT="$ROOT/scripts/app/open-notebook.sh"

# GUI launches do not inherit the shell PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$ROOT" || exit 1

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*"; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

pid_of() { [ -f "$PID_DIR/$1.pid" ] && cat "$PID_DIR/$1.pid"; }

# A PID file or occupied port alone does not establish ownership (PID reuse).
owned_pid() { # service pid
  local name="$1" p="$2" cwd command started
  case "$p" in ''|*[!0-9]*) return 1 ;; esac
  [ "$p" -gt 1 ] && kill -0 "$p" 2>/dev/null || return 1
  cwd="$(lsof -a -p "$p" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')"
  case "$cwd" in "$ROOT"|"$ROOT/"*) ;; *) return 1 ;; esac
  started="$(ps -p "$p" -o lstart=)"
  if [ -f "$PID_DIR/$name.started" ]; then
    [ -n "$started" ] && [ "$started" = "$(cat "$PID_DIR/$name.started")" ] || return 1
  fi
  # Birth time prevents PID reuse; service identity is required for ALL PID files.
  command="$(ps -p "$p" -o command=)"
  case "$name" in
    frontend)
      case "$cwd" in "$ROOT/frontend"|"$ROOT/frontend/.next/standalone"|"$ROOT/frontend/.next/standalone/"*)
        case "$command" in "next-server (v"*|"node $ROOT/frontend/.next/standalone/"*server.js) return 0 ;; esac ;;
      esac ;;
    openmaic)
      [ "$cwd" = "$MAIC_DIR" ] || return 1
      case "$command" in "next-server (v"*|"pnpm start"|*"/pnpm start"|"node "*"/pnpm.cjs start") return 0 ;; esac ;;
    surrealdb|api|worker|subscription-proxy)
      [ "$cwd" = "$ROOT" ] || return 1
      case "$name:$command" in
        surrealdb:*"rocksdb://$DB_DIR/open_notebook.db"*|api:*"uvicorn api.main:app"*|worker:*"surreal-commands-worker --import-modules commands"*|subscription-proxy:*"$ROOT/scripts/app/subscription-proxy.py"*) return 0 ;;
      esac ;;
  esac
  return 1
}

alive() { local p; p="$(pid_of "$1")"; owned_pid "$1" "$p"; }

is_descendant() { # pid ancestor
  local p="$1"
  while [ -n "$p" ] && [ "$p" -gt 1 ] 2>/dev/null; do
    [ "$p" = "$2" ] && return 0
    p="$(ps -p "$p" -o ppid= | tr -d ' ')"
  done
  return 1
}

check_port() { # service port: never borrow an arbitrary listener
  port_busy "$2" || return 0
  local p owner
  owner="$(pid_of "$1")"
  if alive "$1"; then
    for p in $(lsof -t -nP -iTCP:"$2" -sTCP:LISTEN 2>/dev/null); do
      is_descendant "$p" "$owner" || { log "❌ $1 port $2 has an unowned listener; leaving it untouched"; return 1; }
    done
    return 0
  fi
  log "❌ $1 port $2 has an unowned listener; leaving it untouched"
  return 1
}

wait_port() { # name port seconds
  local i=0
  while ! port_busy "$2"; do
    sleep 1; i=$((i + 1))
    if [ "$i" -ge "$3" ]; then log "❌ $1 did not open port $2 in ${3}s (see $LOG_DIR/$1.log)"; return 1; fi
    if [ -f "$PID_DIR/$1.pid" ] && ! alive "$1"; then log "❌ $1 exited early (see $LOG_DIR/$1.log)"; return 1; fi
  done
  check_port "$1" "$2"
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
OPENMAIC_URL=http://localhost:$MAIC_PORT
EOF
  fi
}

start_bg() { # name command...
  local name="$1"; shift
  if alive "$name"; then log "• $name already running (pid $(pid_of "$name"))"; return 0; fi
  log "Starting $name"
  nohup "$@" >"$LOG_DIR/$name.log" 2>&1 &
  local p=$!
  echo "$p" >"$PID_DIR/$name.pid"
  ps -p "$p" -o lstart= >"$PID_DIR/$name.started"
}

start() {
  # Fail before starting dependencies or building if a required port is borrowed.
  check_port frontend "$UI_PORT" || return 1
  if alive frontend && ! port_busy "$UI_PORT"; then
    log "❌ Owned frontend is running but not on port $UI_PORT; stop/restart Open Notebook to migrate it (other services are untouched)"
    return 1
  fi
  check_port api "$API_PORT" || return 1
  check_port surrealdb "$SURREAL_PORT" || return 1
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
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    if alive frontend; then log "❌ Frontend is running; stop/restart Open Notebook before installing dependencies"; return 1; fi
    log "Installing frontend deps (npm install)"
    (cd frontend && npm install) >>"$LOG_DIR/setup.log" 2>&1 || { log "❌ npm install failed"; return 1; }
  fi
  # Next.js may nest the standalone tree (e.g. .next/standalone/Projects/open-notebook/frontend/server.js)
  find_server() { find "$ROOT/frontend/.next/standalone" -name server.js -not -path '*/node_modules/*' 2>/dev/null | head -1; }
  SERVER_JS="$(find_server)"
  if [ -z "$SERVER_JS" ] || [ "$ROOT/frontend/package.json" -nt "$SERVER_JS" ]; then
    if alive frontend; then log "❌ Frontend is running; stop/restart Open Notebook before rebuilding"; return 1; fi
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
  check_port frontend "$UI_PORT" || return 1
  if ! port_busy "$UI_PORT"; then
    start_bg frontend env PORT="$UI_PORT" HOSTNAME=127.0.0.1 INTERNAL_API_URL="http://127.0.0.1:$API_PORT" \
      node "$SERVER_JS"
    wait_port frontend "$UI_PORT" 60 || return 1
  fi

  # 5. Subscription bridge (ChatGPT + Claude OAuth) for OpenMAIC (optional)
  start_subscription_proxy || log "⚠️  subscription proxy not started; subscription models unavailable in Learn"

  # 6. OpenMAIC (Learn feature) — optional; skipped if the submodule is missing
  start_openmaic || log "⚠️  OpenMAIC not started; the Learn tab will be unavailable"

  log "✅ Open Notebook is up: $UI_URL  (API http://localhost:$API_PORT, Learn http://localhost:$MAIC_PORT)"
  echo "$UI_URL"
}

start_subscription_proxy() {
  # Bridges OpenMAIC to ChatGPT (Codex) + Claude subscriptions using Hermes' OAuth credentials, with failover.
  local py="$HOME/.hermes/hermes-agent/.venv/bin/python"
  [ -x "$py" ] || { log "• Hermes venv not found; subscription proxy skipped"; return 1; }
  check_port subscription-proxy "$SUB_PROXY_PORT" || return 1
  if ! port_busy "$SUB_PROXY_PORT"; then
    start_bg subscription-proxy "$py" "$ROOT/scripts/app/subscription-proxy.py" --port "$SUB_PROXY_PORT"
    wait_port subscription-proxy "$SUB_PROXY_PORT" 30 || return 1
  fi
}

start_openmaic() {
  [ -f "$MAIC_DIR/package.json" ] || { log "• vendor/openmaic missing (git submodule update --init)"; return 1; }
  check_port openmaic "$MAIC_PORT" || return 1
  local want_ancestors="$UI_URL" built_ancestors="" rebuild=0
  [ -f "$MAIC_DIR/.next/frame-ancestors" ] && built_ancestors="$(cat "$MAIC_DIR/.next/frame-ancestors")"
  if [ ! -f "$MAIC_DIR/.next/BUILD_ID" ] || [ "$MAIC_DIR/package.json" -nt "$MAIC_DIR/.next/BUILD_ID" ] || [ "$built_ancestors" != "$want_ancestors" ]; then rebuild=1; fi
  if alive openmaic; then
    if [ "$rebuild" = 1 ] || [ ! -d "$MAIC_DIR/node_modules" ] || ! port_busy "$MAIC_PORT"; then
      log "❌ OpenMAIC is running; stop/restart Open Notebook before rebuilding or changing its port"
      return 1
    fi
    log "• OpenMAIC already running; build untouched"
    return 0
  fi
  if [ ! -f "$MAIC_DIR/.env" ]; then
    log "Creating vendor/openmaic/.env"
    # Read a key from the environment or ~/.hermes/.env
    read_key() { local v="${!1:-}"; [ -z "$v" ] && [ -f "$HOME/.hermes/.env" ] && v="$(grep -E "^$1=" "$HOME/.hermes/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"; printf '%s' "$v"; }
    local cline_key
    cline_key="$(read_key CLINE_API_KEY)"
    {
      echo "# OpenMAIC sidecar config for Open Notebook's Learn feature (generated; edit freely)."
      echo "# Model strings are provider:model. Resolution: MODEL_ROUTES > DEFAULT_MODEL."
      echo
      if [ -n "$cline_key" ]; then
        echo "# --- Optional extra provider: Cline relay (OpenAI-compatible, pay-per-use)"
        echo "OPENAI_API_KEY=$cline_key"
        echo "OPENAI_BASE_URL=https://api.cline.bot/api/v1"
        echo "OPENAI_MODELS=z-ai/glm-5.3,deepseek/deepseek-v4-flash-0731"
        echo
      fi
      echo "# --- Subscriptions (OAuth, no API keys) via the local subscription-proxy started by this launcher."
      echo "# ChatGPT (Codex) + Claude through an OpenAI-compatible endpoint WITH automatic failover"
      echo "# (order: requested model -> gpt-6-astra -> claude-haiku-4-5). Registered as the 'openrouter' provider slot."
      echo "OPENROUTER_API_KEY=subscription"
      echo "OPENROUTER_BASE_URL=http://127.0.0.1:$SUB_PROXY_PORT/v1"
      echo "OPENROUTER_MODELS=gpt-6-astra,claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5-1"
      echo "# Teacher voice: OpenAI-compatible TTS served by the proxy (Microsoft Edge neural voices via edge-tts, free)"
      echo "TTS_OPENAI_API_KEY=subscription"
      echo "TTS_OPENAI_BASE_URL=http://127.0.0.1:$SUB_PROXY_PORT/v1"
      echo "# Claude subscription, native Anthropic API (streaming, thinking) — failover only within Claude models"
      echo "ANTHROPIC_API_KEY=subscription"
      echo "ANTHROPIC_BASE_URL=http://127.0.0.1:$SUB_PROXY_PORT/v1"
      echo "ANTHROPIC_MODELS=claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5-1"
      echo
      echo "# Default: Claude Haiku on the subscription (fast, cheap). Alternatives: anthropic:claude-sonnet-5,"
      echo "# openrouter:gpt-6-astra (ChatGPT). Per-stage: MODEL_ROUTES."
      echo "DEFAULT_MODEL=anthropic:claude-haiku-4-5-20251001"
      echo "# 'Web search' for classrooms = live retrieval from Open Notebook (SearXNG-compatible endpoint)"
      echo "SEARXNG_BASE_URL=http://127.0.0.1:$API_PORT/api/learn/searxng"
      echo "# Let Open Notebook embed classrooms in its Learn dialog"
      echo "ALLOWED_FRAME_ANCESTORS=$UI_URL"
    } >"$MAIC_DIR/.env"
  fi
  if [ ! -d "$MAIC_DIR/node_modules" ]; then
    log "Installing OpenMAIC deps (pnpm install, ~1 min)"
    (cd "$MAIC_DIR" && pnpm install --frozen-lockfile) >>"$LOG_DIR/setup.log" 2>&1 || { log "❌ pnpm install failed (see $LOG_DIR/setup.log)"; return 1; }
  fi
  # next.config.ts bakes ALLOWED_FRAME_ANCESTORS into the build: rebuild if it changed
  if [ "$rebuild" = 1 ]; then
    log "Building OpenMAIC (first run, several minutes)"
    (cd "$MAIC_DIR" && ALLOWED_FRAME_ANCESTORS="$want_ancestors" pnpm build) >>"$LOG_DIR/build-openmaic.log" 2>&1 || { log "❌ OpenMAIC build failed (see $LOG_DIR/build-openmaic.log)"; return 1; }
    printf '%s' "$want_ancestors" >"$MAIC_DIR/.next/frame-ancestors"
  fi
  check_port openmaic "$MAIC_PORT" || return 1
  if ! port_busy "$MAIC_PORT"; then
    start_bg openmaic env PORT="$MAIC_PORT" HOSTNAME=127.0.0.1 bash -c "cd '$MAIC_DIR' && exec pnpm start"
    wait_port openmaic "$MAIC_PORT" 90 || return 1
  fi
}

process_tree() { # descendants first, so parents can reap them
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do process_tree "$child"; done
  printf '%s\n' "$1"
}

stop_one() {
  local name="$1" p
  p="$(pid_of "$name")"
  if owned_pid "$name" "$p"; then
    log "Stopping $name (pid $p)"
    local target i remaining
    local targets=() started=()
    for target in $(process_tree "$p"); do
      targets+=("$target")
      started+=("$(ps -p "$target" -o lstart=)")
    done
    for target in "${targets[@]}"; do kill -TERM "$target" 2>/dev/null; done
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      remaining=0
      for target in "${targets[@]}"; do kill -0 "$target" 2>/dev/null && remaining=1; done
      [ "$remaining" = 0 ] && break
      sleep 0.5
    done
    for ((i=0; i<${#targets[@]}; i++)); do
      target="${targets[$i]}"
      # A child can outlive its parent; never signal a recycled PID.
      if [ -n "${started[$i]}" ] && [ "$(ps -p "$target" -o lstart=)" = "${started[$i]}" ]; then
        kill -KILL "$target" 2>/dev/null
      fi
    done
  fi
  rm -f "$PID_DIR/$name.pid" "$PID_DIR/$name.started"
}

stop() {
  for n in openmaic subscription-proxy frontend worker api surrealdb; do stop_one "$n"; done
  # No global process-name/port kills: only verified PID-file owners above.
  # The stay-open applet notices api: stopped in its idle handler and quits.
  # Do not kill arbitrary processes matching an app bundle name.
  log "🛑 Open Notebook stopped"
}

status() {
  for n in surrealdb api worker frontend subscription-proxy openmaic; do
    if alive "$n"; then echo "$n: running (pid $(pid_of "$n"))"; else echo "$n: stopped"; fi
  done
  for p in "$SURREAL_PORT" "$API_PORT" "$UI_PORT" "$SUB_PROXY_PORT" "$MAIC_PORT"; do port_busy "$p" && echo "port $p: listening" || echo "port $p: free"; done
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) tail -n 50 -F "$LOG_DIR"/*.log ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}"; exit 2 ;;
esac
