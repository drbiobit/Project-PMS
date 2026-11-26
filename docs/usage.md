# Usage

## The web app

Open `http://localhost:9090` (Docker) or `http://127.0.0.1:9090` (local).
The web app is the **single interface** — gallery, search, settings,
indexing, and server control all live here on one port.

### Gallery tab

- **The gallery opens on your whole collection** — no query needed.
  Browse it like a photo archive: larger tiles, 2–5 columns depending
  on screen width, works on phones.
- **Search** — describe what you're looking for in plain words:
  *"a birthday cake"*, *"my dog on the beach"*, *"a street in the rain"*.
  Results are ranked by semantic similarity, each with a score.
  The results cap has an **All (∞)** option.
- **The lightbox** — click any tile for the full-page viewer:
  - `←` / `→` (or the on-screen buttons, or swipe on mobile) to browse
  - `Esc` or the Close button to go back
  - click a photo to zoom in, click again to zoom out
  - videos and audio play right in the viewer
  - **Download** button saves the original file

### Settings tab

- **Index** — one click to (re)index the collection, with a live
  progress bar: encoded / skipped / failed / total + the current file.
- **Collection** — point PMS at a different media folder, set the
  vector dimension, image token budget, video FPS, query prefix, and
  the default result count. **Reset database** wipes the index.
- **Server** — the embedding server's status is shown in the header
  (green dot = running). Restart it from Settings after changing
  server-affecting settings.

The app auto-starts the embedding server on boot, so there is nothing
to configure before the gallery works.

## The terminal (local only)

```bash
./run.sh
```

A full-screen TUI walks you through:

1. **Config** — media folder, vector dimension, image token budget,
   video FPS, query prefix, top-N. Arrow keys to edit, Enter to accept.
   Your choices are saved to `config.json`.
2. **Embedding server** — starts `llama-server` with the pinned model.
3. **Indexing** — live `+++++` progress bars: encoded / skipped / failed.
4. **Web app** — launches Flask and opens your browser.

`./run.sh stop` shuts the server and web app down. They run detached,
so closing the TUI doesn't kill them.

## The CLI (local only)

```bash
# index a folder (incremental — safe to re-run)
python build_index.py --media ./media --db media.db

# semantic search
python search.py "a red sports car in the rain" --top 5
```

Both read `config.json` for server/model settings; `--media` and `--db`
override the folder and database paths.

## Configuration

`config.json` is the single source of truth:

| Key | Meaning |
|-----|---------|
| `media_folder` | Folder to index (relative to the project) |
| `db_path` | SQLite database file |
| `server.*` | `llama-server` host/port, model + mmproj paths, context, image tokens, video FPS |
| `embedding.dim` | Vector dimension (768 for EmbeddingGemma-2) |
| `embedding.query_prefix` | Prepend the model's search instruction to queries (recommended on) |
| `web.host` / `web.port` / `web.top_n` | Web app bind + default result count |

The TUI edits this file; in Docker it's generated from environment
variables at boot.

## Supported media

| Kind | Extensions |
|------|-----------|
| Images | `.jpg` `.jpeg` `.png` `.webp` |
| Video | `.mov` `.mp4` |
| Audio | `.wav` `.mp3` `.flac` |

Everything else in the media folder is ignored.

## Performance expectations

- **Images:** ~0.1–0.5 s each on CPU (Metal/CUDA much faster).
- **10,000 images:** roughly 30–90 minutes for the first index on CPU.
- **Video:** slower — frames are extracted and larger payloads are sent.
- **Re-indexing:** incremental, so only new/changed files are embedded.
- **Search:** milliseconds — it's one matrix multiply over the table.
