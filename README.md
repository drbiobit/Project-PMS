# Search Media

A local, private, semantic media search system. Point it at a folder of
**images, videos, and audio**; it embeds every file with the local
**EmbeddingGemma-2** model (via `llama.cpp`) and lets you search it with plain
English — *"a red sports car in the rain"*, *"a dog barking"*, *"sunset over
the ocean"* — across all three modalities at once.

Everything runs on your machine. No cloud, no API keys, no data leaves your
disk.

---

## Quickstart

```bash
./run.sh
```

That's it. The full-screen TUI walks you through:

1. **Configure** — pick your settings (arrow keys)
2. **Brain** — starts `llama-server` (loads the model once, on Metal)
3. **Indexing** — embeds every file in your media folder (with a live `+++++` bar)
4. **Web + Done** — launches the web app and opens your browser

After that, type queries in the browser and get a grid of matching images,
video players, and audio players, each with a similarity score.

To stop the running server + web app:

```bash
./run.sh stop
```

---

## How it works

```
                 ┌─────────────────────────────────────────────┐
                 │  run.sh  →  tui.py  (the full-screen TUI)    │
                 └─────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                         ▼                        ▼
   ① llama-server            ② build_index.py           ③ app.py
     "the brain"               "the indexer"              "the web app"
     (C++ / Metal, port 8080)  (embeds every file,        (Flask, port 5000)
     EmbeddingGemma-2)          stores vectors in          (you type a query,
                                media.db)                  it ranks & shows a grid)
          ▲                         │                        ▲
          │                         ▼                        │
          └────── same 768-d space ─┴──── media.db (SQLite) ─┘
```

**The key idea: one brain, shared.** The model is loaded *once* in the C++
`llama-server` (fast, on Apple Metal). Python never loads the model — it only
sends HTTP requests to the brain. Both the indexer and the web app talk to the
same server, so index-time and search-time embeddings always agree.

**Index once, search fast.** The expensive part (embedding 10,000 files)
happens *once* in the indexer. After that, every search is just: embed the
query (~0.5 s) + compare vectors in memory (instant). Searches stay fast even
at 10,000+ files.

**Incremental.** Each file is tracked by `path + mtime` in SQLite. Re-run the
indexer and only *new/changed* files get embedded. Add 50 photos → only those
50 are processed. This is what makes 10,000+ files manageable.

**SQLite, zero services.** All vectors live in one `media.db` file. No
PostgreSQL, no vector database, nothing extra to install or keep running.

---

## The TUI (full-screen)

`./run.sh` opens a full-screen terminal app that fills your whole terminal.

### Configure screen

Arrow-key editor for every setting:

| Key | Action |
|---|---|
| `↑` / `↓` | move selection |
| `←` / `→` | cycle the value (e.g. dim 768 → 512 → 256) |
| typing | edit the **Media folder** (free text) |
| `Backspace` | delete a character (media folder) |
| `Enter` | save config & start |
| `Esc` | quit |

What you pick here is written straight into `config.json`, so it persists and
is used by every component.

### Progress screens

- **Brain** — a `+++++` bar while `llama-server` loads the model.
- **Indexing** — a live `+++++` bar with `done/total`, skipped, failed,
  files/sec, and the last file processed.
- **Web + Done** — starts the web app, opens the browser, shows the URL.

The `+++++` bar uses `+` for filled and `-` for empty, exactly as you asked.

---

## Configuration

All settings live in **`config.json`** (edited via the TUI, or directly):

```jsonc
{
  "media_folder": "./media",     // folder to index (also the TUI's "Media folder")
  "db_path": "media.db",        // the SQLite index

  "server": {
    "host": "127.0.0.1",
    "port": 8080,
    "binary": "llama.cpp/llama-b12774/llama-server",
    "model": "models/embeddinggemma/embeddinggemma-2-BF16.gguf",
    "mmproj": "models/embeddinggemma/mmproj-BF16.gguf",
    "image_tokens": 280,        // 280 / 560 / 1120  → image detail
    "video_fps": 1.0,           // 1 / 2 / 4          → video detail
    "pooling": "mean",          // model default
    "normalize": 2,             // L2 (model default)
    "ctx_size": 8192,           // model context window
    "ubatch": 1024              // lifts the image-token cap past 256
  },

  "embedding": {
    "dim": 768,                 // 768 / 512 / 256   → quality vs size
    "query_prefix": true,       // true / false      → A/B the task prefix
    "query_prefix_text": "task: search result | query: {query}"
  },

  "web": {
    "host": "127.0.0.1",
    "port": 5000,
    "top_n": 10                 // default results per search
  }
}
```

### What each knob does

| Knob | Values | Effect |
|---|---|---|
| `embedding.dim` | 768 / 512 / 256 | MRL truncation. 768 = best quality; 512/256 = smaller vectors, tiny quality loss. (128 is text-only — avoid for media.) |
| `server.image_tokens` | 280 / 560 / 1120 | Image detail. Higher = sharper matches, slower indexing. 280 is the model's trained default. |
| `server.video_fps` | 1 / 2 / 4 | Video frame rate. 1 = trained default, fastest. Higher = more temporal detail, slower. |
| `embedding.query_prefix` | true / false | Prepends `task: search result \| query: …` to text queries. Toggle to A/B test. |
| `web.top_n` | any | Default number of results shown in the web UI. |

Change a value in the TUI (or `config.json`) and re-run `./run.sh`.

---

## Supported media

| Modality | Extensions |
|---|---|
| Image | `.jpg .jpeg .png .webp` |
| Video | `.mov .mp4 .m4v .mkv .webm` |
| Audio | `.wav .mp3 .m4a .flac .ogg .aac` |

All three live in the **same 768-dim space**, so one query can match an image,
a video, *and* an audio file together.

---

## Command-line tools

Beyond the TUI, each piece is a standalone CLI:

```bash
# Index a folder (incremental)
./venv/bin/python build_index.py --media ./media --db media.db

# Semantic search from the terminal
./venv/bin/python search.py --query "a red sports car in the rain" --top 10
```

Both require the `llama-server` to be running (the TUI starts it for you;
for standalone use, start it first — see Troubleshooting).

---

## Web app

The Flask app (port 5000) serves:

- `GET /` — the search page
- `POST /search` — embeds the query, ranks, renders the results grid
- `GET /media/<path>` — serves the original file (thumbnails, video, audio)
- `GET /health` — liveness probe (used by the TUI)

Results show a thumbnail for images, an inline video player for videos, and an
audio player for audio — each with its similarity score.

---

## File layout

```
search-media/
├── run.sh                 # the single deploy command
├── tui.py                 # full-screen TUI (front door)
├── common.py              # shared: config, embedding client, DB, ranking
├── build_index.py          # the indexer
├── search.py               # CLI search
├── app.py                  # Flask web app
├── templates/index.html    # web UI
├── config.json             # all settings
├── media/                  # your media (images, video, audio)
├── models/embeddinggemma/  # the GGUF model + vision projector
├── llama.cpp/llama-b12774/ # the C++ server binary
├── media.db                # the SQLite index (created on first run)
├── .server.pid / .web.pid  # PIDs of the detached processes
├── .server.log / .web.log  # logs of the detached processes
└── venv/                   # Python environment
```

---

## Scaling to 10,000+ files

- **First index** of 10,000 images: roughly 30–90 minutes on Apple Metal
  (images ~0.1–0.5 s each). Videos are slower (frame extraction + larger
  payloads).
- **Re-runs are fast** — incremental indexing only touches new/changed files.
- **Search is instant** — brute-force numpy cosine over 10,000 × 768 vectors
  is a few milliseconds. (An ANN index can be added later if the library
  grows far beyond this.)
- **Storage** — 768-d float32 ≈ 3 KB/vector → ~30 MB for 10,000 files. Trivial.

---

## Troubleshooting

**"llama-server is not running"** — start it manually (or just use `./run.sh`,
which starts it for you):

```bash
./llama.cpp/llama-b12774/llama-server \
  --model models/embeddinggemma/embeddinggemma-2-BF16.gguf \
  --mmproj models/embeddinggemma/mmproj-BF16.gguf \
  --embedding --pooling mean --embd-normalize 2 \
  --host 127.0.0.1 --port 8080 -c 8192 -ub 1024 \
  --image-max-tokens 280 --video-fps 1
```

**Port already in use** — change `server.port` / `web.port` in `config.json`,
or stop the old processes with `./run.sh stop`.

**A file failed to index** — the indexer skips failures and keeps going; check
`.server.log` for the cause (usually an unsupported/corrupt file).

**Slow first index** — expected. It's one-time; re-runs are incremental.

**Change a setting** — edit `config.json` (or use the TUI) and re-run `./run.sh`.

---

## Design notes & trade-offs

- **Why llama.cpp/GGUF and not `sentence-transformers`?** The model is
  already stored as GGUF and runs on the existing `llama-server` build — no
  `torch`/`transformers` stack, no Python model loading, fast on Metal.
- **Why one server for everything?** Indexer and web app share the same brain,
  so embeddings are consistent and the model loads once.
- **Why SQLite + brute-force numpy?** At 10,000–50,000 files it's simple,
  fast, and dependency-free. An ANN index is a later optimization, not a
  requirement.
- **Query prefix** — the model card recommends `task: search result \| query: …`
  for search. It's ON by default and toggleable so you can A/B it on your real
  media.
