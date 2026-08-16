#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR=${PROJECT_DIR:-/opt/ltx-suite}
COMFYUI_DIR=${COMFYUI_DIR:-/opt/workspace-internal/ComfyUI}
WORKSPACE_DIR=${WORKSPACE_DIR:-/workspace}
PY=${PYTHON_BIN:-/venv/main/bin/python}
LOG=/var/log/portal/ltx-suite.log
STATUS_PORT=18188
mkdir -p /var/log/portal "$WORKSPACE_DIR"
touch "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "============================================================"
echo " LTX 2.3 / 10Eros / Goon Machine - RTX 5090 bootstrap"
echo " Build SHA: ${LTX_BUILD_SHA:-unknown}"
echo " $(date -Is)"
echo "============================================================"

export PROJECT_DIR COMFYUI_DIR WORKSPACE_DIR
export HF_HOME=${HF_HOME:-$WORKSPACE_DIR/.cache/huggingface}
export OLLAMA_MODELS=${OLLAMA_MODELS:-$WORKSPACE_DIR/.cache/ollama/models}
export OLLAMA_HOST=${OLLAMA_HOST:-127.0.0.1:11434}
export OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE:-0s}
export PYTHONUNBUFFERED=1

"$PY" "$PROJECT_DIR/scripts/prepare_runtime.py"

STATUS_LOG="$LOG" STATUS_PORT="$STATUS_PORT" "$PY" "$PROJECT_DIR/scripts/status_server.py" &
STATUS_PID=$!
cleanup_status(){ kill "$STATUS_PID" 2>/dev/null || true; wait "$STATUS_PID" 2>/dev/null || true; }
trap cleanup_status EXIT

"$PY" "$PROJECT_DIR/scripts/preflight.py"

TG_PID=""
start_telegram() {
  local token="${TELEGRAM_BOT_TOKEN:-}"
  echo "[telegram] token_present=$([[ -n "$token" ]] && echo yes || echo no) enable_flag=${ENABLE_TELEGRAM_BOT:-unset}"
  if [[ -z "$token" ]]; then
    echo "[telegram] not started: TELEGRAM_BOT_TOKEN is empty"
    return 0
  fi

  local tg_http
  tg_http=$(curl -sS -o /tmp/telegram-getme.json -w '%{http_code}' --connect-timeout 8 --max-time 15 \
    "https://api.telegram.org/bot${token}/getMe" || true)
  if [[ "$tg_http" != "200" ]] || ! jq -e '.ok == true' /tmp/telegram-getme.json >/dev/null 2>&1; then
    echo "[telegram] ERROR: Telegram Bot API check failed (HTTP=${tg_http:-000}). Check token and host access to api.telegram.org"
    return 0
  fi

  local username
  username=$(jq -r '.result.username // "unknown"' /tmp/telegram-getme.json 2>/dev/null || echo unknown)
  echo "[telegram] API OK: @${username}; starting polling worker now"
  "$PY" "$PROJECT_DIR/bot/telegram_bot.py" >>"$LOG" 2>&1 &
  TG_PID=$!
  sleep 2
  if ! kill -0 "$TG_PID" 2>/dev/null; then
    echo "[telegram] ERROR: worker exited during startup"
    wait "$TG_PID" || true
    TG_PID=""
  else
    echo "[telegram] worker running pid=$TG_PID"
  fi
}

# Start Telegram immediately, before the expensive model bootstrap. /start and /status
# remain responsive while weights are downloading.
start_telegram

# Ollama is needed by the supplied Goon Machine workflow prompt-generation nodes.
mkdir -p "$OLLAMA_MODELS"
echo "[ollama] starting server"
ollama serve >>"$LOG" 2>&1 &
OLLAMA_PID=$!
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi
  sleep 1
done
OLLAMA_MODEL=${OLLAMA_MODEL:-satgeze/gemma4-12b-uncensored-1m:latest}
echo "[ollama] pulling $OLLAMA_MODEL (cached under /workspace for this instance)"
ollama pull "$OLLAMA_MODEL"

"$PY" "$PROJECT_DIR/scripts/download_models.py"
"$PY" "$PROJECT_DIR/scripts/prepare_workflows.py"

echo "[bootstrap] all required assets are ready"
echo "[bootstrap] workflows: $WORKSPACE_DIR/user/default/workflows"
echo "[bootstrap] output:    $WORKSPACE_DIR/output"

cleanup_status
trap - EXIT
sleep 1

cd "$COMFYUI_DIR"
ARGS=(main.py --listen 127.0.0.1 --port 18188 --disable-auto-launch --preview-method auto --enable-cors-header '*')
if "$PY" main.py --help 2>&1 | grep -q -- '--reserve-vram'; then
  ARGS+=(--reserve-vram "${COMFY_RESERVE_VRAM:-2}")
fi

echo "[comfyui] starting web UI on Portal tunnel"
"$PY" "${ARGS[@]}" &
COMFY_PID=$!

READY=0
for i in $(seq 1 180); do
  if ! kill -0 "$COMFY_PID" 2>/dev/null; then
    echo "[comfyui] process exited unexpectedly"
    wait "$COMFY_PID"
    exit 1
  fi
  if curl -fsS http://127.0.0.1:18188/system_stats >/dev/null 2>&1; then
    HTTP=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
      --data '{}' http://127.0.0.1:18188/workflow/convert || true)
    if [[ "$HTTP" != "000" && "$HTTP" != "404" ]]; then
      READY=1
      break
    fi
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "[comfyui] ERROR: ComfyUI or /workflow/convert did not become ready"
  kill "$COMFY_PID" 2>/dev/null || true
  wait "$COMFY_PID" 2>/dev/null || true
  [[ -n "$TG_PID" ]] && kill "$TG_PID" 2>/dev/null || true
  exit 1
fi

echo "[comfyui] READY"

set +e
wait "$COMFY_PID"
EXIT_CODE=$?
set -e
if [[ -n "$TG_PID" ]]; then
  kill "$TG_PID" 2>/dev/null || true
  wait "$TG_PID" 2>/dev/null || true
fi
exit "$EXIT_CODE"
