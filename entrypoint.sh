#!/bin/bash
# PMS — Portable Media Search · container entrypoint
#
# Two deployment modes:
#
#   BUNDLED (default)   — the container starts its own llama-server and
#                         talks to it on 127.0.0.1.
#   EXTERNAL            — set PMS_EMBED_BASE_URL to point the app at an
#                         EXTERNAL locally-hosted OpenAI-compatible endpoint
#                         (Ollama, vLLM, a separate llama-server, a gateway).
#                         The bundled server is NOT started.
#
# Steps:
#   1. generate /app/config.json from environment
#   2. start the embedding server (bundled) OR check the external endpoint
#   3. wait for /health
#   4. build the SQLite index (incremental — fast on subsequent boots)
#   5. serve the gallery (foreground)
set -euo pipefail

MEDIA_DIR="${PMS_MEDIA_DIR:-/media}"
DATA_DIR="${PMS_DATA_DIR:-/data}"
PORT="${PMS_PORT:-9090}"
SERVER_PORT="${PMS_SERVER_PORT:-8080}"
TOP_N="${PMS_TOP_N:-100}"
AUTH_USER="${PMS_AUTH_USER:-admin}"
AUTH_PASS="${PMS_AUTH_PASS:-pms}"
# External OpenAI-compatible endpoint (empty = use the bundled server).
EMBED_BASE_URL="${PMS_EMBED_BASE_URL:-}"
EMBED_API_KEY="${PMS_EMBED_API_KEY:-}"
EMBED_MODEL="${PMS_EMBED_MODEL:-embeddinggemma-2}"

mkdir -p "$DATA_DIR"

log() { echo "[pms] $*"; }

# ── 1. config.json (container-specific) ────────────────────────────────
python3 - "$MEDIA_DIR" "$DATA_DIR" "$PORT" "$SERVER_PORT" "$TOP_N" \
          "$AUTH_USER" "$AUTH_PASS" "$EMBED_BASE_URL" "$EMBED_API_KEY" "$EMBED_MODEL" <<'PY'
import json, sys

(media, data, port, sport, top, user, password,
 base_url, api_key, model) = sys.argv[1:11]
cfg = {
    "media_folder": media,
    "db_path": f"{data}/media.db",
    "server": {
        "host": "127.0.0.1",
        "port": int(sport),
        "binary": "/opt/llama/llama-server",
        "model": "/models/embeddinggemma-2-UD-Q5_K_XL.gguf",
        "mmproj": "/models/mmproj-Q8_0.gguf",
        "image_tokens": 280,
        "video_fps": 1.0,
        "pooling": "mean",
        "normalize": 2,
        "ctx_size": 8192,
        "ubatch": 2048,
    },
    "embedding": {
        "dim": 768,
        "query_prefix": True,
        "query_prefix_text": "task: search result | query: {query}",
        "batch_size": 8,
        "max_batch_tokens": 7000,
        # External OpenAI-compatible endpoint. base_url empty = bundled server.
        "api_key": api_key,
        "model_name": model,
        "base_url": base_url,
    },
    "web": {
        "host": "0.0.0.0",
        "port": int(port),
        "top_n": int(top),
    },
    "auth": {
        "username": user,
        "password": password,
    },
}
with open("/app/config.json", "w") as f:
    json.dump(cfg, f, indent=2)
print(f"[pms] config.json written (media={media}, db={data}/media.db, "
      f"endpoint={'external ' + base_url if base_url else 'bundled'})")
PY

# ── 2+3. embedding endpoint: bundled server OR external ─────────────────
SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && { kill "$SERVER_PID" 2>/dev/null || true;
                            wait "$SERVER_PID" 2>/dev/null || true; }
}
trap cleanup EXIT

if [ -n "$EMBED_BASE_URL" ]; then
  # EXTERNAL mode: the endpoint is hosted elsewhere; just verify it answers.
  log "using EXTERNAL embedding endpoint: $EMBED_BASE_URL (model $EMBED_MODEL)"
  ready=0
  for _ in $(seq 1 60); do
    if curl -sf "$EMBED_BASE_URL/health" | grep -q ok; then ready=1; break; fi
    sleep 2
  done
  if [ "$ready" -ne 1 ]; then
    log "ERROR: external embedding endpoint not reachable at $EMBED_BASE_URL"
    exit 1
  fi
  log "external embedding endpoint ready."
else
  # BUNDLED mode: start our own llama-server.
  MODEL="/models/embeddinggemma-2-UD-Q5_K_XL.gguf"
  MMPROJ="/models/mmproj-Q8_0.gguf"
  LLAMA_LOG="$DATA_DIR/llama-server.log"
  log "starting llama-server (port $SERVER_PORT)…"
  /opt/llama/llama-server \
    --model "$MODEL" \
    --mmproj "$MMPROJ" \
    --embedding --pooling mean --embd-normalize 2 \
    --host 127.0.0.1 --port "$SERVER_PORT" \
    -c 8192 -ub 2048 --image-max-tokens 280 --video-fps 1 \
    > "$LLAMA_LOG" 2>&1 &
  SERVER_PID=$!

  log "waiting for embedding server…"
  ready=0
  for _ in $(seq 1 180); do
    if curl -sf "http://127.0.0.1:$SERVER_PORT/health" | grep -q ok; then
      ready=1
      break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      log "ERROR: llama-server exited early — log tail:"
      tail -30 "$LLAMA_LOG"
      exit 1
    fi
    sleep 1
  done
  if [ "$ready" -ne 1 ]; then
    log "ERROR: embedding server did not become healthy — log tail:"
    tail -30 "$LLAMA_LOG"
    exit 1
  fi
  log "embedding server ready."
fi

# ── 4. build the index (incremental) ────────────────────────────────────
if [ -d "$MEDIA_DIR" ]; then
  log "indexing $MEDIA_DIR (incremental — already-indexed files are skipped)…"
  python3 /app/build_index.py --config /app/config.json
else
  log "WARNING: $MEDIA_DIR is not mounted — starting with an empty gallery."
fi

# ── 5. serve the gallery ─────────────────────────────────────────────────
log "gallery listening on port $PORT"
exec python3 /app/app.py
