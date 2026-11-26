# PMS — Portable Media Search

**Built with AI.** Search your photos, videos, and audio with plain
words — not folders, not filenames, not dates.

---

You know the feeling: thousands of photos collected over years, spread
across phones, cameras, and hard drives. You *know* that photo of the
birthday cake exists somewhere. Finding it by hand — scrolling,
remembering, guessing filenames — is painful.

**PMS fixes that.** It runs the **EmbeddingGemma-2** multimodal AI model
locally (via [llama.cpp](https://github.com/ggml-org/llama.cpp)), turns
every image, video, and audio file in your folder into a semantic
vector, and lets you search your whole collection with natural language:

> *"a red sports car in the rain"* → the photo you were looking for.

Everything runs on your machine. No cloud, no API keys, no data leaves
your network. Your media stays yours.

## Deploy

The fastest way is Docker — one command, your media folder mounted, a
gallery in your browser:

```bash
docker run -d -p 9090:9090 \
  -v /path/to/your/media:/media:ro \
  -v pms-data:/data \
  ghcr.io/drbiobit/pms:cpu
```

Then open **http://localhost:9090**. First boot builds the index
automatically; every boot after that is instant.

| You want… | …so use |
|-----------|---------|
| Quick Docker deploy | [`docs/deployment.md`](docs/deployment.md) — images, compose file, GPU setup |
| NVIDIA GPU (fast indexing) | `ghcr.io/drbiobit/pms:cuda` |
| AMD GPU | `ghcr.io/drbiobit/pms:rocm` |
| ARM64 server | `ghcr.io/drbiobit/pms:cpu-arm64` |
| Run natively (no Docker) | `./run.sh` — full-screen TUI, one command |
| How it works | [`docs/architecture.md`](docs/architecture.md) |
| Every file explained | [`docs/files.md`](docs/files.md) |
| Day-to-day usage | [`docs/usage.md`](docs/usage.md) |

**Container images** are built on every push and published to
[GitHub Releases](https://github.com/drbiobit/Project-PMS/releases) —
pin `pms:cpu`, `pms:cuda`, `pms:rocm`, or an exact `pms:sha-…` build.

## How it works (30 seconds)

1. **Embed** — each media file becomes a 768-dimensional vector with
   EmbeddingGemma-2 (text, image, and video/audio all share one space).
2. **Store** — vectors live in a local SQLite database. Indexing is
   incremental: re-runs only touch new files.
3. **Search** — your query is embedded the same way; cosine similarity
   ranks the collection. Milliseconds, even at 10,000+ files.

```
 media folder ──▶ llama-server (EmbeddingGemma-2) ──▶ SQLite ──▶ gallery UI
                    768-d vectors per file              cosine search
```

## Features

- 🖼️ **Multimodal** — images, videos (`.mov`, `.mp4`), and audio
  (`.wav`, `.mp3`, `.flac`) in one index
- 🎨 **Gallery UI** — responsive photo-archive layout, full-page lightbox
  with keyboard, swipe, zoom, and one-click download
- 🎛 **Self-contained control plane** — the web app manages everything:
  settings, one-click reindex with live progress, server start/stop.
  One port, no separate API.
- 📦 **Portable** — one Docker image; CPU, NVIDIA CUDA, and AMD ROCm
  variants
- ⚡ **Fast at scale** — built for 10,000+ files; incremental indexing
- 🔒 **Private** — 100% local: model, database, and server all on your
  hardware

## Repository layout

```
app.py            the web app — gallery, search, settings, reindex, server control
common.py         shared core (embedding client, SQLite, cosine rank)
build_index.py    the indexer
search.py         CLI semantic search
tui.py            full-screen terminal UI (optional)
run.sh            one-command local deploy
config.json       runtime configuration
templates/        the gallery UI
static/           self-hosted fonts
Dockerfile        Ubuntu image (cpu / cuda / rocm variants)
entrypoint.sh     container boot sequence
docker-compose.yml  self-hosted compose file
docs/             full documentation
```

## License

MIT
