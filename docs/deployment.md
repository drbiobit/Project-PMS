# Deployment

PMS ships as a Docker image. The image is built by GitHub Actions on
every push to `main` and published to **GHCR** (GitHub Container
Registry). The container images are attached to **GitHub Releases**, so
you can grab the exact image you want from the Releases page.

## Images

| Tag | Backend | Architecture | Use when |
|-----|---------|--------------|----------|
| `pms:cpu` (also `pms:latest`) | CPU | x86_64 | Default. Any machine. |
| `pms:cpu-arm64` | CPU | aarch64 | ARM servers (Graviton, Apple silicon hosts). |
| `pms:cuda` | NVIDIA CUDA | x86_64 | NVIDIA GPU — fastest indexing for big libraries. |
| `pms:rocm` | AMD ROCm | x86_64 | AMD GPU. |

Every image also gets a `pms:sha-<commit>` tag so you can pin an exact
build.

What's baked into each image:

- Ubuntu 24.04 + Python 3 + Flask/NumPy/requests
- The pinned `llama-server` binary for the chosen backend
- `embeddinggemma-2-UD-Q5_K_XL.gguf` + `mmproj-Q8_0.gguf` (EmbeddingGemma-2
  Q5, from `unsloth/embeddinggemma-2-GGUF`)

Nothing is downloaded at container start — the first boot just builds
your index.

## Quick start

```bash
# 1. get the image
docker pull ghcr.io/drbiobit/pms:cpu

# 2. run it, pointing at your media folder
docker run -d -p 9090:9090 \
  -v /path/to/your/media:/media:ro \
  -v pms-data:/data \
  --name pms ghcr.io/drbiobit/pms:cpu

# 3. open http://localhost:9090
```

The first boot embeds your whole collection (a few minutes for a few
thousand photos; longer for video-heavy libraries). The index is stored
in the `pms-data` volume, so restarts are instant — only new files get
embedded.

Indexing is **batched**: the engine embeds several files per request
(`embedding.batch_size`, default 8) bounded by a token budget
(`embedding.max_batch_tokens`), with per-file fallback if a batch fails.
This is much faster than one request per file and is safe for large
libraries.

## docker compose

The repo includes a ready-made `docker-compose.yml`:

```yaml
services:
  pms:
    image: ghcr.io/drbiobit/pms:cpu
    ports:
      - "9090:9090"
    volumes:
      - ./media:/media:ro      # ← your media folder
      - pms-data:/data          # persistent index
    restart: unless-stopped
volumes:
  pms-data:
```

```bash
mkdir -p media   # put your photos in here (or point the volume elsewhere)
docker compose up -d
```

### NVIDIA GPU

```yaml
services:
  pms:
    image: ghcr.io/drbiobit/pms:cuda
    ports:
      - "9090:9090"
    volumes:
      - ./media:/media:ro
      - pms-data:/data
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### AMD GPU

Same, with `image: ghcr.io/drbiobit/pms:rocm` and the `rocm` device
reservation for your AMD stack.

## Configuration (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `PMS_MEDIA_DIR` | `/media` | Mounted media folder |
| `PMS_DATA_DIR` | `/data` | Where `media.db` + logs live |
| `PMS_PORT` | `9090` | Gallery port |
| `PMS_SERVER_PORT` | `8080` | Internal embedding server port |
| `PMS_TOP_N` | `100` | Default number of gallery items / search results |
| `PMS_AUTH_USER` | `admin` | Web app Basic-Auth username |
| `PMS_AUTH_PASS` | `pms` | Web app Basic-Auth password |
| `PMS_EMBED_BASE_URL` | _(empty)_ | External OpenAI-compatible endpoint. Empty = bundled server. |
| `PMS_EMBED_API_KEY` | _(empty)_ | Bearer token sent to the endpoint (if it requires one). |
| `PMS_EMBED_MODEL` | `embeddinggemma-2` | Model id requested from the endpoint. |

### Locally hosted OpenAI endpoint (second image)

The standard image bundles its own `llama-server`. If you'd rather run the
embedding engine separately — on a GPU box, as a shared service, or via
Ollama/vLLM — use the **slim app image** (`Dockerfile.openai`), which ships
no engine and points at an external OpenAI-compatible endpoint instead.

The repo ships a matching server image (`Dockerfile.server`) that runs
`llama-server` with the same EmbeddingGemma-2 GGUF models as a standalone
`/v1/embeddings` endpoint, and a `docker-compose.openai.yml` that wires the
two together:

```bash
docker build -f Dockerfile.server -t pms-embed-server:cpu .
docker build -f Dockerfile.openai  -t pms:openai .
docker compose -f docker-compose.openai.yml up
# → gallery on http://localhost:9090 (login admin / pms)
```

The app side is configured entirely through environment variables
(`PMS_EMBED_BASE_URL`, `PMS_EMBED_API_KEY`, `PMS_EMBED_MODEL`), so you can
swap in any OpenAI-compatible endpoint — Ollama, vLLM, a gateway — without
touching the app image.

## Local (no Docker)

If you'd rather run natively:

```bash
./run.sh          # TUI: config → server → index → web app → browser
./run.sh stop     # shut it all down
```

See [usage.md](usage.md) for the full local workflow.

## Updating the llama.cpp pin

The `Dockerfile` pins a specific llama.cpp release (`ARG LLAMA_BUILD`).
To bump it:

```bash
python3 scripts/fetch_llama.py '^llama-b[0-9]+-bin-ubuntu-x64\.tar\.gz$'
# → b12801  https://github.com/ggml-org/llama.cpp/releases/download/b12801/…
```

Update `LLAMA_BUILD` (and the CUDA/ROCm asset names if the toolchain
versions changed), commit, push — CI rebuilds all four images.
