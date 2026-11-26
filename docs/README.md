# PMS Documentation

Portable Media Search — a local, private, AI-powered search over your own
photos, videos, and audio.

| Document | What it covers |
|----------|----------------|
| [architecture.md](architecture.md) | How PMS works: the embedding pipeline, the database, the search math |
| [files.md](files.md) | Every file in the project and what it does |
| [deployment.md](deployment.md) | Docker self-hosting: images, GPU variants, compose, GitHub Releases |
| [usage.md](usage.md) | Day-to-day use: the gallery, searching, the TUI, the CLI, configuration |

## 60-second overview

```
 your media folder
        │
        ▼
 ┌─────────────────────┐      ┌──────────────────────────┐
 │  llama-server        │      │  SQLite (media.db)       │
 │  EmbeddingGemma-2    │─────▶│  one 768-d vector/file   │
 │  (GGUF, local)       │      └──────────────────────────┘
 └─────────────────────┘                 │
                                          ▼
                                   ┌─────────────────┐
                                   │  Flask gallery   │
                                   │  cosine search   │
                                   └─────────────────┘
```

1. **Embed** — each image, video, and audio file is turned into a 768-
   dimensional vector by [EmbeddingGemma-2](https://huggingface.co/google
   /gemma-3-1b-pt-sft) (a multimodal embedding model) running locally via
   [llama.cpp](https://github.com/ggml-org/llama.cpp).
2. **Store** — vectors live in a SQLite database next to your media.
   Indexing is incremental: re-runs only embed new files.
3. **Search** — your query is embedded the same way, and every stored
   vector is scored with cosine similarity. Best matches first.

Everything runs on your machine. No cloud, no API keys, no data leaves
your network.
