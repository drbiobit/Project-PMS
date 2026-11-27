# 🔍 PMS — Portable Media Search

> **Search your photos, videos, and audio with plain words** — not folders,
> not filenames, not dates. 100% local, no cloud, no API keys.

[![GitHub repo](https://img.shields.io/badge/GitHub-drbiobit%2Fsearch-media-111?logo=github)](https://github.com/drbiobit/Project-PMS)
[![Docker](https://img.shields.io/badge/Docker-GHCR-2496ed?logo=docker)](https://github.com/drbiobit/Project-PMS/pkgs/container/pms)
[![Python](https://img.shields.io/badge/Python-3.10+-0078D4?logo=python&logoColor=white)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue)](#license)

---

## 💡 The idea

You know the feeling: thousands of photos collected over years, spread across
phones, cameras, and hard drives. You *know* that photo of the birthday cake
exists somewhere. Finding it by hand — scrolling, remembering, guessing
filenames — is painful.

**PMS fixes that.** It runs the **EmbeddingGemma-2** multimodal AI model
locally (via [llama.cpp](https://github.com/ggml-org/llama.cpp)), turns every
image, video, and audio file in your folder into a semantic vector, and lets
you search your whole collection with natural language:

> 🗣️ *"a red sports car in the rain"* → 📸 the photo you were looking for.

Everything runs on your machine. **No cloud, no API keys, no data leaves your
network.** Your media stays yours. 🔒

---

## 🚀 Quick start (one command)

The fastest way to get running — one command checks Docker, asks where your
media is, lets you pick the image (and whether to run a local OpenAI
endpoint), asks for a username/password, and opens the gallery:

```bash
curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash
```

That's it. 🎉 You'll be pointed at **http://localhost:9090** with a login
screen using the username/password you chose.

📖 Full walkthrough of the installer: [`docs/installer.md`](docs/installer.md).

### Prefer plain Docker?

```bash
docker run -d -p 9090:9090 \
  -v /path/to/your/media:/media:ro \
  -v pms-data:/data \
  ghcr.io/drbiobit/project-pms:cpu
```

Then open **http://localhost:9090**. First boot builds the index
automatically; every boot after that is instant. ⚡

| You want… | …so use |
|-----------|---------|
| 🐳 One-shot install | `curl … install.sh \| bash` (above) |
| 📖 Docker deployment | [`docs/deployment.md`](docs/deployment.md) — images, compose, GPU setup |
| 🎮 NVIDIA GPU (fast) | `ghcr.io/drbiobit/project-pms:cuda` |
| 🎮 AMD GPU | `ghcr.io/drbiobit/project-pms:rocm` |
| 🍏 Apple Silicon / ARM64 | `ghcr.io/drbiobit/project-pms:cpu-arm64` |
| 🖥️ Run natively (no Docker) | `./run.sh` — one command |
| 🧠 How it works | [`docs/architecture.md`](docs/architecture.md) |
| 📁 Every file explained | [`docs/files.md`](docs/files.md) |
| 🕹️ Day-to-day usage | [`docs/usage.md`](docs/usage.md) |

**Container images** are built on every push and published to
[GitHub Releases](https://github.com/drbiobit/Project-PMS/releases) —
pin `project-pms:cpu`, `project-pms:cuda`, `project-pms:rocm`, or an exact `project-pms:sha-…` build.

---

## ⚙️ How it works (30 seconds)

1. **🔢 Embed** — each media file becomes a 768-dimensional vector with
   EmbeddingGemma-2 (text, image, and video/audio all share one space).
2. **🗄️ Store** — vectors live in a local SQLite database. Indexing is
   incremental: re-runs only touch new files.
3. **🔎 Search** — your query is embedded the same way; cosine similarity
   ranks the collection. Milliseconds, even at 10,000+ files.

```
  media folder ──▶ llama-server (EmbeddingGemma-2) ──▶ SQLite ──▶ gallery UI
                     768-d vectors per file              cosine search
```

---

## ✨ Features

- 🖼️ **Multimodal** — images, videos (`.mov`, `.mp4`), and audio
  (`.wav`, `.mp3`, `.flac`) in one index
- 🎨 **Gallery UI** — responsive (phone → laptop → tablet), full-page lightbox
  with keyboard, swipe, **mouse zoom + drag-pan**, and one-click download
- 🔐 **Login screen** — private gallery behind a sign-in page (session-based)
- 🎛 **Self-contained control plane** — the web app manages everything:
  settings, one-click reindex with live progress, server start/stop.
  One port, no separate API.
- 📏 **Adjustable grid** — resize the gallery tiles to taste (120–480px)
- 📦 **Portable** — one Docker image; CPU, NVIDIA CUDA, and AMD ROCm variants
- ⚡ **Fast at scale** — built for 10,000+ files; batched, incremental indexing
- 🔌 **Pluggable endpoint** — point the app at any local OpenAI-compatible
  server (Ollama, vLLM, a separate llama-server) via one env var
- 🔒 **Private** — 100% local: model, database, and server all on your hardware

---

## 📁 Repository layout

```
app.py            the web app — gallery, search, settings, reindex, server control
common.py         shared core (embedding client, SQLite, cosine rank)
build_index.py    the indexer (batched, failure-isolated)
search.py         CLI semantic search
tui.py            full-screen terminal UI (optional)
run.sh            one-command local deploy
install.sh        one-shot installer (curl | bash)
config.json       runtime configuration
templates/        the gallery + login UI
static/           self-hosted fonts
Dockerfile        Ubuntu image (cpu / cuda / rocm variants)
Dockerfile.openai slim app image that uses an external OpenAI endpoint
Dockerfile.server standalone embedding-server image
entrypoint.sh     container boot sequence
docker-compose.yml  self-hosted compose file
docker-compose.openai.yml  app + external endpoint compose
docs/             full documentation
tests/            pytest suite
```

---

## 📄 Documentation

📚 The full documentation site lives in [`docs/`](docs/):

- [`docs/architecture.md`](docs/architecture.md) — how it all fits together
- [`docs/deployment.md`](docs/deployment.md) — Docker, GPU, compose, endpoints
- [`docs/usage.md`](docs/usage.md) — day-to-day usage
- [`docs/files.md`](docs/files.md) — every file explained

## 🤖 For AI agents

Working on this repo? Read [`AGENTS.md`](AGENTS.md) first — it's the map for the
codebase (start at `common.py`). A few things that will save you time:

- **Everything is local-first.** No cloud, no API keys, no external calls. Don't add any.
- **Config is data, not code.** `common.DEFAULT_CONFIG` is the source of truth; `config.json` deep-merges over it. Change a default in *both*.
- **The embedding endpoint is pluggable.** Build it with `make_client(cfg)` — never hardcode a URL.
- **`/health` is load-bearing.** `install.sh` and the Docker healthcheck poll it. Don't break it.
- **Tests are the safety net.** `./venv/bin/python -m pytest tests/ -q` must pass before you call anything done.

---

## 📝 License

[Apache License 2.0](LICENSE) — free to use, modify, and share.
