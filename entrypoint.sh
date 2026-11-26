#!/bin/bash
# PMS — Portable Media Search · container entrypoint
#
# 1. generate /app/config.json from environment
# 2. start llama-server (EmbeddingGemma-2, multimodal embeddings)
# 3. wait for /health
# 4. build the SQLite index (incremental — fast on subsequent boots)
# 5. serve the gallery (foreground)
set -euo pipefail

MEDIA_DIR="${PMS_MEDIA_DIR:-/media}"
DATA_DIR="${PMS_DATA_DIR:-/data}"
PORT="${PMS_PORT:-5000}"
SERVER_PORT="${PMS_SERVER_PORT:-8080}"
TOP_N="${PMS_TOP_N:-100}"
MODEL="/models/embeddinggemma-2-UD-Q5_K_XL.gguf"
MMPROJ="/models/mmproj-Q8_0.gguf"

mkdir -p "$DATA_DIR"

log() { echo "[pms] $*"; }

# ── 1. config.json (container-specific) ────────────────────────────────
python3 - "$MEDIA_DIR" "$DATA_DIR" "$PORT" "$SERVER_PORT" "$TOP_N" <<'PY'
import json, sys

media, data, port, sport, top = sys.argv[1:6]
cfg = {
    "media_folder": media,
    "db_path": f"{data}/media.db",
    "server": {
        "host": "127.0.0.1",
        "port": int(sport),
        "binary": "/usr/local/bin/llama-server",
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
    },
    "web": {
        "host": "0.0.0.0",
        "port": int(port),
        "top_n": int(top),
    },
}
with open("/app/config.json", "w") as f:
    json.dump(cfg, f, indent=2)
print(f"[pms] config.json written (media={media}, db={data}/media.db)")
PY

# ── 2. start the embedding server ───────────────────────────────────────
LLAMA_LOG="$DATA_DIR/llama-server.log"
log "starting llama-server (port $SERVER_PORT)…"
llama-server \
  --model "$MODEL" \
  --mmproj "$MMPROJ" \
  --embedding --pooling mean --embd-normalize 2 \
  --host 127.0.0.1 --port "$SERVER_PORT" \
  -c 8192 -ub 2048 --image-max-tokens 280 --video-fps 1 \
  > "$LLAMA_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── 3. wait for health ───────────────────────────────────────────────────
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
