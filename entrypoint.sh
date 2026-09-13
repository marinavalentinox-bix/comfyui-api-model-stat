#!/usr/bin/env bash
# Start Salad comfyui-api on 127.0.0.1:3001, expose 0.0.0.0:3000 via model_stat proxy.
set -euo pipefail
STAT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM_PORT="${UPSTREAM_PORT:-3001}"
PUBLIC_PORT="${PUBLIC_PORT:-3000}"

# Original image entrypoint/cmd typically listens on 3000; force upstream port via env if supported.
export PORT="${UPSTREAM_PORT}"
export HOST="127.0.0.1"
export WRAPPER_PORT="${UPSTREAM_PORT}"

# Start upstream in background. Prefer image's default binary/cmd.
if [[ -x /usr/local/bin/comfyui-api ]]; then
  /usr/local/bin/comfyui-api &
elif [[ -x /app/comfyui-api ]]; then
  /app/comfyui-api &
elif command -v node >/dev/null 2>&1 && [[ -f /app/dist/index.js ]]; then
  node /app/dist/index.js &
else
  # Fall through to whatever CMD was passed
  if [[ "$#" -gt 0 ]]; then
    "$@" &
  else
    echo "entrypoint: no upstream binary found; set CMD" >&2
    exit 1
  fi
fi
UPSTREAM_PID=$!

python3 "${STAT_DIR}/model_stat_server.py" \
  --bind 0.0.0.0 \
  --port "${PUBLIC_PORT}" \
  --proxy-upstream "127.0.0.1:${UPSTREAM_PORT}" &
STAT_PID=$!

cleanup() {
  kill "${STAT_PID}" "${UPSTREAM_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Prefer failing if upstream dies
wait -n "${UPSTREAM_PID}" "${STAT_PID}"
exit $?
