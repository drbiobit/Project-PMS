# 🔍 PMS — Portable Media Search

Search your photos, videos, and audio with **plain words** — not folders, not
filenames, not dates. **100% local, no cloud, no API keys.**

PMS runs the **EmbeddingGemma-2** multimodal AI model locally (via
[llama.cpp](https://github.com/ggml-org/llama.cpp)), turns every image, video,
and audio file in your folder into a semantic vector, and lets you search your
whole collection with natural language:

> 🗣️ *"a red sports car in the rain"* → 📸 the photo you were looking for.

## 🚀 Quick start

The fastest way — one command detects your hardware, pulls the right image,
asks where your media is, and opens the gallery:

```bash
curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash
```

Or plain Docker:

```bash
docker run -d -p 9090:9090 \
  -v /path/to/your/media:/media:ro \
  -v pms-data:/data \
  ghcr.io/drbiobit/pms:cpu
```

Then open **http://localhost:9090** (default login `admin` / `pms`).

## ⚙️ How it works

1. **🔢 Embed** — each media file becomes a 768-dimensional vector with
   EmbeddingGemma-2.
2. **🗄️ Store** — vectors live in a local SQLite database (incremental).
3. **🔎 Search** — your query is embedded the same way; cosine similarity
   ranks the collection.

```
 media folder ──▶ llama-server (EmbeddingGemma-2) ──▶ SQLite ──▶ gallery UI
                    768-d vectors per file              cosine search
```

## 📚 Explore the docs

- **[Architecture](architecture.md)** — how it all fits together.
- **[Deployment](deployment.md)** — Docker, GPU, compose, endpoints.
- **[Usage](usage.md)** — day-to-day usage.
- **[Files](files.md)** — every file explained.

## ✨ Highlights

- 🖼️ Multimodal — images, videos, and audio in one index.
- 🎨 Responsive gallery with a full-page lightbox (zoom, pan, swipe).
- 🔐 Private login screen.
- 📦 Portable — one Docker image (CPU / CUDA / ROCm / ARM64).
- 🔌 Pluggable embedding endpoint (any local OpenAI-compatible server).
- 🔒 100% local — your media never leaves your machine.
