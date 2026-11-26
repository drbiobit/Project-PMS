# Improved Build Plan — Search Media (llama.cpp / GGUF)

Local media search: embeds **images AND videos** from a folder into **SQLite** using
**EmbeddingGemma-2** (via `llama-server`), then returns the best-matching files for
free-text queries. One `run.sh` deploys the whole thing; a small Flask web app shows results.

---

## 0. Why this differs from `detailed-plan.md`

| Original plan assumption | Reality (verified) |
|---|---|
| Model is `sentence-transformers` format (`.safetensors`, needs `torch`) | Model is **GGUF** for **llama.cpp** (`embeddinggemma-2-BF16.gguf` + `mmproj-BF16.gguf`) |
| Needs `torch`, `sentence-transformers`, `transformers`, 1.5 GB download | **None of that.** We talk to `llama-server`'s `/embedding` endpoint over HTTP |
| Images only (jpg/png/webp) | **Images + videos** (`.mov`/`.mp4`) — verified working |
| Python does the embedding | `llama-server` (C++, Metal) does the embedding; Python just orchestrates |

**Verified by running the model:**
- `POST /embedding` text → **768-dim** vector ✅
- `POST /embedding` image → **768-dim** vector ✅  (`{"content":"[img-1]","image_data":[{"id":1,"data":"<b64>"}]}`)
- `POST /embedding` video → **768-dim** vector ✅  (`{"content":"[video-1]","video_data":[{"id":1,"data":"<b64>"}]}`)
- Large files (5.5 MB MOV) → write JSON payload to a temp file, `curl -d @file` ✅
- Runs on **Metal** (fast on M1) ✅
- `ffmpeg` present at `/opt/homebrew/bin/ffmpeg` (server uses it for video frames) ✅

---

## 1. Architecture

```
run.sh  (ONE command — the "deploy" button)
  ├─ 1. start llama-server      (background, port 8080, --embedding --mmproj)
  ├─ 2. build_index.py          (walk folder → POST each file to /embedding → SQLite)
  ├─ 3. app.py + templates/     (Flask web UI: text box → results grid, port 5000)
  └─ 4. open browser            → http://localhost:5000
```

The **llama-server is the single "brain."** Both the indexer and the web app call its
`/embedding` endpoint. Nothing in Python loads the model.

---

## 2. Components

### 2a. `llama-server` (the embedding engine)
```bash
./llama.cpp/llama-b12774/llama-server \
  --model models/embeddinggemma/embeddinggemma-2-BF16.gguf \
  --mmproj models/embeddinggemma/mmproj-BF16.gguf \
  --embedding --pooling mean --embd-normalize 2 \
  --host 127.0.0.1 --port 8080
```
Request formats (all return a 768-dim vector):
- **Text:**  `{"content": "a red sports car in the rain"}`
- **Image:** `{"content":"[img-1]","image_data":[{"id":1,"data":"<base64>"}]}`
- **Video:** `{"content":"[video-1]","video_data":[{"id":1,"data":"<base64>"}]}`

### 2b. `build_index.py` (the indexer)
```bash
venv/bin/python build_index.py --media ./media --db media.db
```
- Walk the folder; accept `.jpg .jpeg .png .webp .mov .mp4`.
- For each file, build the right payload (image or video) and POST to `/embedding`.
  - **Large files:** write the JSON payload to a temp file, send with `curl -d @file`
    (avoids the "argument list too long" shell limit).
- Store each embedding as `float32 × 768` BLOB.
- **Incremental / resume-safe:** skip files whose `path + mtime` are already in the DB.
- Progress log: `i/N  <filename>  (encoded/skipped)`.

### 2c. `search.py` (CLI search)
```bash
venv/bin/python search.py --query "a red sports car in the rain" --top 10 --db media.db
```
1. Embed the query (text format) via `/embedding`.
2. Load all embeddings from SQLite into a numpy matrix `(N, 768)`.
3. Cosine similarity (normalize + dot), sort descending, print top-N:
   ```
   0.9123  ./media/IMG_E4633.JPG
   0.8874  ./media/IMG_4169.MOV
   ```

### 2d. `app.py` + `templates/index.html` (web app)
```bash
venv/bin/python app.py   # → http://localhost:5000
```
| Route | Method | Behavior |
|---|---|---|
| `/` | GET | Search page: text input + results grid. |
| `/search` | POST | Embed query via `/embedding`, rank against DB, render grid. |
| `/media/<path>` | GET | Serve the original file (image or video) by safe path. |

- Flask does **no** model loading — it calls the running `llama-server`.
- UI: search box on top; responsive grid below; each result shows a thumbnail
  (image, or a poster frame for videos) + filename + score.

---

## 3. SQLite schema

```sql
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,          -- 'image' | 'video'
    width INTEGER,
    height INTEGER,
    duration REAL,               -- seconds (video only)
    size_bytes INTEGER,
    mtime REAL,
    embedding BLOB NOT NULL      -- float32 × 768
);
```

---

## 4. `run.sh` (the single deploy script)

```bash
#!/usr/bin/env bash
# usage: ./run.sh [media_folder]     (default: ./media)
set -euo pipefail
MEDIA="${1:-./media}"

# 1. start llama-server if not already running on :8080
# 2. venv/bin/python build_index.py --media "$MEDIA" --db media.db
# 3. venv/bin/python app.py  (background)
# 4. open http://localhost:5000
```

One command: `./run.sh` → server up, index built, web app live, browser open.

---

## 5. Validation

1. **Smoke test** on the existing `media/` (17 images + 4 videos):
   - Index all 21 files.
   - Query something specific (e.g. a subject only in 1–2 files) → correct file in top 3.
2. **Incremental:** re-run indexer with no changes → all skipped. Add 1 file → only it encoded.
3. **Web end-to-end:** open `http://localhost:5000`, submit a query, verify grid + thumbnails.
4. **Performance:** time the index; record files/second.

---

## 6. Performance notes (for the 10,000+ goal)

- **Images:** ~0.1–0.5 s each on Metal → 10,000 ≈ 30–90 min first run.
- **Videos:** slower (ffmpeg frame extraction + more tokens) → a large video library
  can take hours. Plan for a long first index.
- **Incremental + resume** makes every re-run fast (only new/changed files).
- If the library grows past ~100k, add an ANN index (e.g. `sqlite-vector`) later.
  For 10,000–50,000, brute-force numpy cosine over the in-memory matrix is fine.

---

## 7. Risks

1. **Port conflicts** — 8080 (server) / 5000 (web). `run.sh` checks before binding.
2. **Large video payloads** — use temp-file JSON + `curl -d @file` (verified).
3. **Long first index at 10,000+** — mitigated by incremental + resume + progress log.
4. **Server must stay running** — `run.sh` (re)starts it; web app depends on it.

---

## 8. Build order

| # | Task | Deliverable |
|---|---|---|
| 1 | `run.sh` scaffolding + server start/health check | server up on :8080 |
| 2 | `build_index.py` + SQLite schema | `media.db` with indexed files |
| 3 | `search.py` CLI | ranked results in terminal |
| 4 | `app.py` + `templates/index.html` | browser search UI |
| 5 | Validation (smoke, incremental, perf, end-to-end) | confirmed working system |
