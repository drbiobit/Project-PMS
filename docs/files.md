# Project files

Every file in the repository and what it does.

## Application

| File | Purpose |
|------|---------|
| `app.py` | The web app — PMS's single control plane. Gallery UI, semantic search, media streaming, **settings tab** (edit config), **reindex** with live progress, and **server start/stop**. It manages the `llama-server` subprocess itself and auto-starts it on boot. One port, everything local. |
| `common.py` | Shared core: config load/save, `EmbeddingClient` (talks to `llama-server` `/v1/embeddings`), `MediaDB` (SQLite access), `cosine_rank`. Used by the app, the indexer, the CLI, and the TUI. |
| `build_index.py` | The indexer. Walks the media folder, embeds every image/video/audio file not already in the DB, writes vectors to SQLite. CLI: `python build_index.py --media … --db …`. |
| `search.py` | Command-line semantic search: `python search.py "a dog in the rain" --top 5`. |
| `tui.py` | Full-screen terminal UI (Textual): interactive config and `+++++` progress bars. Optional — the web app now covers the same ground. |
| `run.sh` | The single local deploy command: launches the web app and opens the browser. `./run.sh stop` shuts it down. The web app handles the server and index itself. |
| `config.json` | Runtime configuration (media folder, ports, model paths, embedding settings, top-N). Edited from the web app's Settings tab; read by everything. |

## Web UI

| File | Purpose |
|------|---------|
| `templates/index.html` | The gallery: responsive 2–5 column grid, search bar, full-page lightbox with next/prev, arrow keys, swipe, and click-to-zoom. |
| `static/fonts.css` | Self-hosted fonts (Fraunces display serif + Instrument Sans UI) — no CDN, works offline and in Docker. |
| `static/fonts/*.woff2` | The font files (latin, latin-ext, vietnamese subsets). |

## Docker

| File | Purpose |
|------|---------|
| `Dockerfile` | Ubuntu 24.04 image. Build args pick the llama.cpp backend: `cpu-x64`, `cpu-arm64`, `cuda-x64` (NVIDIA), `rocm-x64` (AMD). Bakes in the pinned llama.cpp binary + EmbeddingGemma-2 Q5 model. |
| `entrypoint.sh` | Container boot: writes `config.json` from env vars, starts `llama-server`, waits for health, builds the index (incremental), serves the gallery. |
| `docker-compose.yml` | One service: mount your media folder, persistent index volume, port 5000. GPU variants documented inline. |
| `.dockerignore` | Keeps the build context clean (no `media/`, `venv/`, `models/`, …). |
| `requirements.txt` | Python deps for the container: flask, numpy, requests. |
| `scripts/fetch_llama.py` | Dev tool: prints the newest llama.cpp release + download URL for a given asset pattern (used when bumping the pinned version in `Dockerfile`). |

## CI

| File | Purpose |
|------|---------|
| `.github/workflows/docker-publish.yml` | On every push to `main`: builds and pushes all four images to GHCR — `pms:cpu`, `pms:cpu-arm64`, `pms:cuda`, `pms:rocm` (+ `pms:latest`). |

## Docs

| File | Purpose |
|------|---------|
| `README.md` | Project home: what PMS is, why it exists, quick deploy links. |
| `docs/README.md` | Docs index. |
| `docs/architecture.md` | How PMS works under the hood. |
| `docs/files.md` | This file. |
| `docs/deployment.md` | Docker deployment guide. |
| `docs/usage.md` | Day-to-day usage guide. |

## Not in the repo (gitignored)

| Path | Why |
|------|-----|
| `media/` | Your personal media — never committed. |
| `models/` | Multi-GB model files — downloaded, not committed. |
| `llama.cpp/` | Local llama.cpp build — downloaded, not committed. |
| `venv/` | Local Python environment. |
| `media.db`, `*.pid`, `*.log` | Runtime artifacts. |
| `references/` | Local research material. |
