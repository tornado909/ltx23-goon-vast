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

# Ollama is needed by the Goon workflow prompt-generation nodes.
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

# Hand the same Portal URL over from the bootstrap page to ComfyUI.
cleanup_status
trap - EXIT
sleep 1

cd "$COMFYUI_DIR"
ARGS=(main.py --listen 127.0.0.1 --port 18188 --disable-auto-launch --preview-method auto)
if "$PY" main.py --help 2>&1 | grep -q -- '--reserve-vram'; then
  ARGS+=(--reserve-vram "${COMFY_RESERVE_VRAM:-2}")
fi

echo "[comfyui] starting web UI on Portal tunnel"
"$PY" "${ARGS[@]}" &
COMFY_PID=$!

# Wait until both ComfyUI and the workflow-converter endpoint are ready before starting Telegram.
READY=0
for i in $(seq 1 180); do
  if ! kill -0 "$COMFY_PID" 2>/dev/null; then
    echo "[comfyui] process exited unexpectedly"
    wait "$COMFY_PID"
    exit 1
  fi
  if curl -fsS http://127.0.0.1:18188/system_stats >/dev/null 2>&1; then
    # A POST with invalid data is expected to fail, but a non-404 response proves the route exists.
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
  exit 1
fi

echo "[comfyui] READY"
TG_PID=""
if [[ "${ENABLE_TELEGRAM_BOT:-0}" =~ ^(1|true|TRUE|yes|YES)$ ]]; then
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "[telegram] ENABLE_TELEGRAM_BOT=1 but TELEGRAM_BOT_TOKEN is empty; bot not started"
  else
    echo "[telegram] starting polling worker"
    "$PY" "$PROJECT_DIR/bot/telegram_bot.py" >>"$LOG" 2>&1 &
    TG_PID=$!
  fi
fi

set +e
wait "$COMFY_PID"
EXIT_CODE=$?
set -e
if [[ -n "$TG_PID" ]]; then
  kill "$TG_PID" 2>/dev/null || true
  wait "$TG_PID" 2>/dev/null || true
fi
exit "$EXIT_CODE"
