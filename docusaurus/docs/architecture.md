---
title: Architecture
sidebar_position: 3
---

# PMS — Architecture

PMS has three layers: an **embedding engine**, a **database**, and a
**search UI**. All of it runs locally.

## 1. The embedding engine

The engine is [`llama-server`](https://github.com/ggml-org/llama.cpp) —
llama.cpp's OpenAI-compatible HTTP server — running the
**EmbeddingGemma-2** model in GGUF format.

- **Model:** `embeddinggemma-2-UD-Q5_K_XL.gguf` (~1.5 GB, Q5_K_XL
  quantization) + `mmproj-Q8_0.gguf` (the vision/audio projection layer).
- **Why GGUF/llama.cpp:** no `torch`, no `sentence-transformers`, no GPU
  driver in Python. One native binary, works on CPU, NVIDIA CUDA, and AMD
  ROCm.
- **Multimodal:** the same model embeds text, images, and video/audio
  into one shared 768-dimensional space, so "a red sports car in the
  rain" (text) matches a photo of exactly that.

Key server flags (see `entrypoint.sh` / `run.sh`):

| Flag | Value | Why |
|------|-------|-----|
| `--embedding` | on | embedding mode (no token generation) |
| `--pooling mean` | mean | mean-pooled token embeddings |
| `--embd-normalize 2` | L2 | normalized vectors → cosine = dot product |
| `-c 8192` | ctx | room for the largest media payloads |
| `-ub 2048` | ubatch | batch size that fits video token counts |
| `--image-max-tokens 280` | 280 | the model's trained image token budget |
| `--video-fps 1` | 1 fps | the model's trained video sampling rate |

### Request format

The server exposes `POST /v1/embeddings`. Media is sent as base64
data-URIs inside typed content parts:

```jsonc
// text
{"input": ["task: search result | query: a birthday cake"]}

// image
{"input": [{"content": [{"type": "image_url",
          "image_url": {"url": "data:image/jpeg;base64,…"}}]}]}

// video
{"input": [{"content": [{"type": "input_video",
          "input_video": {"url": "data:video/quicktime;base64,…"}}]}]}

// audio
{"input": [{"content": [{"type": "input_audio",
          "input_audio": {"data": "…base64…", "format": "wav"}}]}]}
```

The response is `data[0].embedding` — a 768-float vector.

### The query prefix

EmbeddingGemma-2 is instruction-tuned. For search, the model card
recommends prefixing queries with `task: search result | query: …`.
PMS does this by default (toggle in `config.json`); it measurably
improves cross-modal similarity.

## 2. The database

A single SQLite file (`media.db`) with one table:

```sql
CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,     -- path relative to the media folder
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,            -- image | video | audio
    width INTEGER, height INTEGER,
    duration REAL,
    size_bytes INTEGER,
    mtime REAL,
    embedding BLOB NOT NULL        -- 768 × float32
);
```

- **Incremental indexing:** a file is skipped when its path + mtime are
  already in the table. Adding 50 photos to a 10,000-photo library
  embeds 50 files, not 10,050.
- **Scale:** at 10,000 files the DB is ~25 MB (768 × 4 bytes × 10,000).
  Brute-force cosine over 10,000–50,000 vectors is milliseconds on a
  laptop, so no ANN index is needed at this scale.

## 3. The search

Search is one embedding call + one matrix multiplication:

```
score(file) = cosine(query_vector, file_vector)
```

Vectors are L2-normalized, so cosine is a plain dot product — computed
with NumPy over the whole table, then the top *n* rows are returned.

The Flask app is deliberately thin: it never loads the model itself, it
just talks to the running `llama-server` over HTTP. That means the web
app, the CLI, and the TUI all share one engine and one database.

## Data flow

```
indexing:   media file → base64 → /v1/embeddings → 768-d vector → SQLite
searching:  query text → /v1/embeddings → 768-d vector → cosine vs all rows
serving:    Flask → SQLite rows → HTML gallery → /media/<file> streams the file
```
