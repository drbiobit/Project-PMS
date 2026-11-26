# AGENTS.md — how to work on this project

This file tells an AI agent (or a new human) how to read, run, and change
**PMS — Portable Media Search**. Read this first.

## What this project is

PMS is a **local-first, multimodal media search** tool. It embeds every
image, video, and audio file in a folder with the **EmbeddingGemma-2** model
(via [llama.cpp](https://github.com/ggml-org/llama.cpp)), stores the 768-d
vectors in **SQLite**, and serves a **Flask** gallery where you search with
plain-language queries. **Everything runs locally** — no cloud, no API keys,
no data leaves the machine.

The one-sentence data flow:

```
media folder ──▶ llama-server (EmbeddingGemma-2) ──▶ SQLite ──▶ Flask gallery
                     768-d vector per file                cosine search
```

## How to read it (start here)

Read in this order:

1. **`common.py`** — the shared core. Everything important lives here:
   config loading, the `EmbeddingClient` (talks to llama-server), `MediaDB`
   (SQLite), `cosine_rank` (search), `verify_credentials` (auth), and
   `make_client` / `estimate_tokens` (batching). If you change behavior, it
   probably starts here.
2. **`app.py`** — the Flask control plane. Routes: `/` (gallery), `/search`,
   `/media`, `/settings`, `/reindex`, `/server`, `/reset-db`, `/status`,
   `/health`, `/login`, `/logout`. Session-based auth (not HTTP Basic).
3. **`build_index.py`** — the indexer. Two passes: collect files needing
   embedding, then batch-embed them (`_make_batches`), with per-file failure
   isolation.
4. **`search.py`** — the CLI semantic search.
5. **`templates/index.html`** and **`templates/login.html`** — the UI
   (single-file HTML/CSS/JS, Jinja2 for `index.html`).
6. **`docs/`** — the full documentation: `architecture.md`,
   `deployment.md`, `usage.md`, `files.md`.

## Key files at a glance

| File | Role |
|------|------|
| `common.py` | Core: config, `EmbeddingClient`, `MediaDB`, `cosine_rank`, `make_client`, `estimate_tokens`, `verify_credentials` |
| `app.py` | Flask app + routes + session auth |
| `build_index.py` | Batched, failure-isolated indexer |
| `search.py` | CLI search |
| `tui.py` | Optional full-screen terminal UI (Textual) |
| `config.json` | Runtime config (server, media, embedding, web, auth) |
| `templates/` | Gallery + login UI |
| `static/` | Self-hosted fonts |
| `Dockerfile` | Ubuntu image (cpu/cuda/rocm/arm64 variants) |
| `Dockerfile.openai` | Slim app image that uses an **external** OpenAI endpoint |
| `Dockerfile.server` | Standalone embedding-server image |
| `entrypoint.sh` | Container boot (start server, generate config, index, serve) |
| `install.sh` | One-shot installer (`curl \| bash`) |
| `run.sh` | One-command local deploy |
| `tests/` | pytest suite |
| `scripts/download_models.sh` | Fetches the GGUF model files |

## How to run it

- **Tests** (the source of truth for behavior):
  ```bash
  ./venv/bin/python -m pytest tests/ -q
  ```
  All modules must import cleanly and all tests must pass.
- **Local (no Docker)**: `./run.sh` — starts llama-server + the web app.
- **Docker**: `docker run -d -p 9090:9090 -v /path/to/media:/media:ro -v pms-data:/data ghcr.io/drbiobit/pms:cpu`
- **One-shot**: `curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash`

## Conventions

- **Python 3.10+**, no heavy frameworks. Dependencies are pinned in
  `requirements.txt` (flask, numpy, requests, Pillow, textual, pytest).
- **Config is data, not code.** `common.DEFAULT_CONFIG` is the source of
  truth for defaults; `config.json` overrides it (deep-merged). Changing a
  default means editing `DEFAULT_CONFIG` *and* keeping `config.json` in sync.
- **The embedding endpoint is pluggable.** `make_client(cfg)` builds an
  `EmbeddingClient` from `embedding.base_url` (external) or `server_url`
  (bundled llama-server). Never hardcode a URL.
- **Auth is session-based.** `app.secret_key` is derived from the configured
  username/password so sessions survive restarts. `/health` and `/login` are
  the only unauthenticated routes.
- **Batching has safety checks.** `build_index._make_batches` bounds each
  batch by `batch_size` (count) **and** `max_batch_tokens` (token budget via
  `estimate_tokens`). A failed batch falls back to one-file-at-a-time so one
  bad file can't poison the rest.

## What NOT to do

- Don't add cloud services, API keys, or external data calls — the whole point
  is local-first.
- Don't break the `/health` endpoint — `install.sh` and the Docker
  healthcheck depend on it.
- Don't remove the `index.log` background write in `entrypoint.sh` — it's how
  users see indexing progress.
- Don't hardcode ports (default **9090**), model paths, or the embedding
  endpoint.
- Don't drop the tests — they're the safety net for the batching and auth
  logic.

## Where things live (paths)

- Models: `models/embeddinggemma/` (`embeddinggemma-2-UD-Q5_K_XL.gguf`,
  `mmproj-Q8_0.gguf`).
- Media: `media/` (configured by `config.json` → `media.dir`).
- Database: `data/media.db` (SQLite).
- Logs: `data/index.log` (indexing), `data/server.log` (llama-server).
- Repo: https://github.com/drbiobit/Project-PMS
