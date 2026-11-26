# Detailed Build Plan — Search Media

Local image search application: uses the **EmbeddingGemma-2** model to embed thousands of photos from a folder into a **SQLite** database, then returns the best-matching photos for free-text queries. Includes a small web app for querying in a browser.

---

## 1. Goal

- Index all photos in a user-specified folder (jpg/png/webp) into `media.db` (SQLite) using 768-dim embeddings from EmbeddingGemma-2.
- Given a text query (e.g. *"a red sports car in the rain"*), return the top-N most similar photos with their paths and similarity scores.
- Expose this as:
  1. A CLI search script (`search.py`), and
  2. A simple web app (Flask) with a text box and an image grid.

---

## 2. Environment Findings (verified)

| Item | Finding |
|---|---|
| Model | `embeddinggemma-2/` — **EmbeddingGemma-2** (Google DeepMind), 740M params, **768-dim** embeddings, multimodal (text + image + audio + video), MRL truncation (128/256/512/768d). Packaged in **sentence-transformers** format (`Transformer` → mean Pooling → Normalize). `model.safetensors` ≈ 1.5 GB. |
| venv | Python **3.14.3** (arm64, Apple M1), only `pip` installed — torch/sentence-transformers not yet installed. Network access works. |
| Photos | ⚠️ No photos folder exists in the project yet. **Action needed: user must specify the photos folder** (default: `./photos`). |
| Model quirks | • Requires **task instruction prefixes**: queries use `prompt_name="SearchQuery"` (`task: search result \| query: {query}`); **images are encoded with no prefix**. <br>• Audio encoder can be skipped: `config_kwargs={"audio_config": None}` → 440M instead of 740M (we only need text + image). <br>• Model config targets `transformers 5.18.0.dev0` — if the latest release fails to load the model, pin that version. |

---

## 3. Project Layout

```
search-media/
├── venv/                  # existing Python 3.14.3 venv
├── embeddinggemma-2/      # existing local model (1.5 GB)
├── photos/                # user's photos (to be provided)
├── media.db               # SQLite index (created by build_index.py)
├── build_index.py         # Phase 1 — indexer
├── search.py              # Phase 2 — CLI search
├── app.py                 # Phase 3 — web app
└── templates/
    └── index.html         # Phase 3 — search UI
```

---

## 4. Phases

### Phase 0 — Environment Setup (venv)

```bash
venv/bin/pip install torch sentence-transformers transformers pillow flask
```

Verification steps:
1. Load the model locally (no downloads):
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer("./embeddinggemma-2", config_kwargs={"audio_config": None})
   ```
2. Encode one text query with `prompt_name="SearchQuery"` → assert output is a 768-dim vector.
3. Encode one image (PIL) → assert output is a 768-dim vector.
4. Check the device: try `device="mps"` (Apple Metal) for speed; fall back to CPU.

**Risks:**
- Python 3.14 + torch: if no compatible torch wheel exists, recreate the venv with system Python 3.12 instead.
- MPS + bfloat16: if torch's MPS backend has issues with bf16, run the model in fp32 on MPS or CPU (still fine for this workload).

### Phase 1 — Indexer: `build_index.py`

Purpose: walk the photos folder, embed every image, and store vectors in SQLite.

**CLI:**
```bash
venv/bin/python build_index.py --photos ./photos --db media.db
```

**SQLite schema:**
```sql
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    size_bytes INTEGER,
    mtime REAL,
    embedding BLOB NOT NULL   -- float32 × 768 bytes
);
```

**Implementation details:**
- Walk the photos folder; accept `.jpg`, `.jpeg`, `.png`, `.webp`.
- Open images with `Pillow` (`Image.open(...).convert("RGB")`).
- Encode in batches (32–64 images per call): `model.encode([pil_images], batch_size=32)`.
  - **No prompt/prefix for images** (per model docs).
- Store each embedding as `np.float32(vec).tobytes()` in the `embedding` BLOB.
- **Idempotent / incremental**: before encoding, check the DB by path; skip files whose path + mtime are already indexed. This makes re-runs fast for new/changed photos only.
- Log progress: `i/N  <filename>  (skipped/encoded)`.
- Expected performance: ~1 s/image on M1 CPU → ~15–20 min for 10k photos (faster with MPS).

**Data size estimate:** 10,000 photos × 768 dims × 4 bytes ≈ **30 MB** — trivial for SQLite.

### Phase 2 — Search CLI: `search.py`

**CLI:**
```bash
venv/bin/python search.py --query "a red sports car in the rain" --top 10 --db media.db
```

**Implementation details:**
1. Load the model (audio encoder skipped).
2. Embed the query: `model.encode(query, prompt_name="SearchQuery")` — **this is the task-steered prefix for search retrieval; omitting it reduces quality**.
3. Load all embeddings from SQLite into a numpy matrix `(N, 768)` float32.
4. Compute cosine similarity: normalize query and vectors, then dot product.
5. Sort descending; print top-N:
   ```
   0.9123  ./photos/vacation_2024/0042.jpg
   0.8874  ./photos/vacation_2024/0101.jpg
   ...
   ```

### Phase 3 — Web App: `app.py` + `templates/index.html`

**Run:**
```bash
venv/bin/python app.py    # → http://localhost:5000
```

**Flask endpoints:**
| Route | Method | Behavior |
|---|---|---|
| `/` | GET | Render the search page: text input, submit button, results grid. |
| `/search` | POST | Read `query` + `top` (default 10); embed query with `SearchQuery` prefix; rank against DB; render results grid. |
| `/photo/<path>` | GET | Serve the original image file via `send_from_directory` (URL-safe path handling). |

**Design:**
- Model loaded **once at startup** (warm cache); search request time = encode query (~0.5 s) + in-memory similarity.
- Simple, clean UI: search box at top, responsive image grid below, filename + score shown per result.
- Keep dependencies minimal: Flask only.

### Phase 4 — Validation

1. **Smoke test (small sample):**
   - Copy ~50 photos into `photos/` (or use a small subfolder).
   - Index them, then run queries that target specific subjects (e.g., query something that only appears in 1–2 of the sample photos).
   - **Pass condition:** the known correct photo ranks in the top 3.
2. **Incremental indexing:**
   - Re-run the indexer with no changes → confirm all files are skipped.
   - Add 5 new photos → confirm only those 5 are encoded.
3. **Full-index performance:**
   - Time the index over the full photos folder; record images/second.
4. **Web end-to-end:**
   - Open `http://localhost:5000`, submit a query, verify results load in the grid and images render.

---

## 5. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| SQLite BLOB for vectors | No external vector DB needed for thousands of photos; zero extra services; BLOB = 4 bytes × 768 dims per image. |
| In-memory numpy similarity search | 10k × 768 × 4 B ≈ 30 MB — trivially fast per query. If the library grows to 100k+ photos, add an ANN index (e.g., `sqlite-vector`) as a future phase. |
| Full 768-d vectors | Best retrieval quality. MRL truncation (512d/256d) is available as a tunable option if storage or speed ever matters. |
| `sentence-transformers` | The model ships in this format, so it loads **fully offline** from the local folder — no Hugging Face downloads. |
| Task prefix `SearchQuery` for queries only | Per the model's best-practices docs; images get no prefix. Skipping the prefix measurably reduces retrieval precision. |
| Skip audio encoder (`config_kwargs={"audio_config": None}`) | We only need text + image → 440M instead of 740M, less memory, faster load. |
| Flask over FastAPI | Fewer dependencies, simpler for a local tool; the search logic is the same either way. |
| Idempotent indexing (path + mtime) | New photos can be added without re-encoding the whole library. |

---

## 6. Open Items / Risks

1. **Photos folder location** — does not exist yet; user must specify the path (default `./photos`).
2. **Python 3.14 + torch compatibility** — verify during Phase 0; fallback: recreate venv with system Python 3.12.
3. **MPS + bfloat16** — fallback to fp32 on MPS or CPU if needed.
4. **Very large folders (100k+)** — out of scope for now; would need ANN indexing and possibly chunked DB scans.

---

## 7. Build Order (summary)

| # | Task | Deliverable |
|---|---|---|
| 1 | Phase 0: install deps, verify model loads + encodes text/image | working venv, smoke test script |
| 2 | Phase 1: `build_index.py` + DB schema | `media.db` with indexed photos |
| 3 | Phase 2: `search.py` CLI | ranked query results in terminal |
| 4 | Phase 3: Flask web app + template | browser-based search UI |
| 5 | Phase 4: validation (smoke test, incremental index, perf, end-to-end) | confirmed working system |
