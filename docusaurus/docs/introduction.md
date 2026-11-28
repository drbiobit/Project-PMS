---
title: Introduction
sidebar_position: 0
---

# PMS — Documentation

Welcome to the **PMS** docs. PMS is a local-first, multimodal media search —
describe what you're looking for in plain words, and it finds the photo,
video, or audio clip you mean.

The whole engine is the **EmbeddingGemma-2** multimodal model running locally
via [llama.cpp](https://github.com/ggml-org/llama.cpp): every media file in
your folder becomes a 768-dimensional vector in a local SQLite database, and
your query is embedded the same way. Cosine similarity does the rest.

> 🗣️ *"a red sports car in the rain"* → 📸 the photo you were looking for.

## New here?

Start with the [Installer](/installer) to get it running in one command,
then use the [Architecture](/architecture) page to understand how it works
under the hood.

## Guides

| Document | What's inside |
|----------|---------------|
| [Installer](/installer) | The one-shot `install.sh` — what it asks, the two deployment modes, what it writes. |
| [Deployment](/deployment) | Docker images, GPU variants, compose, the OpenAI endpoint, and every env var. |
| [Architecture](/architecture) | The embedding engine, the database, and the search math. |
| [Usage](/usage) | The gallery, searching, the TUI, the CLI, and configuration. |
| [Files](/files) | Every file in the repository and what it does. |
| [Embedding Reference](/reference) | EmbeddingGemma-2 via llama.cpp — verified flags, request formats, and limits. |

## Quick links

- **Repository:** [github.com/drbiobit/Project-PMS](https://github.com/drbiobit/Project-PMS)
- **Docker image (ready to launch):** `ghcr.io/drbiobit/project-pms:cpu`
- **Releases:** [github.com/drbiobit/Project-PMS/releases](https://github.com/drbiobit/Project-PMS/releases)

## Launch in 30 seconds

```bash
curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash
# open http://localhost:9090 (default login: admin / pms)
```
