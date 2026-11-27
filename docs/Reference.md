# Media Embedding Reference — EmbeddingGemma-2 via llama.cpp

Everything verified by running the local model + reading the authoritative docs
(HuggingFace model card, gemma.ai multimodal guide, llama.cpp server README).

---

## 1. The model (EmbeddingGemma-2)

| Fact | Value |
|---|---|
| Params | 740M total (270M text backbone + 170M vision + 300M audio) |
| Output dim | **768** (native) |
| MRL truncation | 768 / 512 / 256 / 128 (quality near-lossless to 256d; 128d degrades multimodal) |
| Context window | **8,192 tokens** (shared across all modalities) |
| Pooling | **Mean pooling** |
| Precision | **bfloat16 or float32** (NOT float16 — returns NaN) |
| Modalities | text, image, video, audio (all in one shared 768-d space) |
| Our files | `embeddinggemma-2-UD-Q5_K_XL.gguf` (~1.5 GB, Q5_K_XL) + `mmproj-Q8_0.gguf` (vision/audio projector) |

### Token cost per modality (shared 8,192 budget)
| Modality | Cost | Max input |
|---|---|---|
| Text | 1 token/subword | 8,192 tokens |
| **Image** | **280 tokens/image (default)** | ~29 images (more at lower budget) |
| **Video** | **140 tokens/frame (default)** | ~58 frames |
| **Audio** | **25 tokens/second** | ~327 seconds |

### Task instruction prefixes (text ONLY — media gets none)
| Use case | Type | Query prefix | Document prefix |
|---|---|---|---|
| **Web / document search** | Asymmetric | `task: search result \| query: {query}` | `title: {title} \| text: {content}` |
| Question answering | Asymmetric | `task: question answering \| query: {q}` | `title: {t} \| text: {p}` |
| Fact checking | Asymmetric | `task: fact checking \| query: {claim}` | `title: {t} \| text: {e}` |
| Code search | Asymmetric | `task: code retrieval \| query: {q}` | `title: {t} \| text: {code}` |
| Classification | Symmetric | `task: classification \| query: {content}` | — |
| Clustering | Symmetric | `task: clustering \| query: {content}` | — |
| Similarity | Symmetric | `task: sentence similarity \| query: {content}` | — |

**For our app (text query → image/video):**
- Query (text): prepend `task: search result | query: {query}`
- Image / video / audio: **no prefix** (just the media)
- ⚠️ Prefix effect on **text→image** retrieval needs empirical validation (one synthetic test showed no benefit). Make it a configurable A/B toggle.

---

## 2. Running the server (verified)

```bash
./llama.cpp/llama-b12774/llama-server \
  --model models/embeddinggemma/embeddinggemma-2-UD-Q5_K_XL.gguf \
  --mmproj models/embeddinggemma/mmproj-Q8_0.gguf \
  --embedding --pooling mean --embd-normalize 2 \
  --host 127.0.0.1 --port 8080
```

Key flags (from server README):
| Flag | Default | Purpose |
|---|---|---|
| `--embedding` | off | Restrict to embedding-only (dedicated embedding model) |
| `--pooling` | model default (mean) | Pooling type: none/mean/cls/last/rank |
| `--embd-normalize` | 2 (L2/euclidean) | Embedding normalization |
| `-c, --ctx-size` | model (8192) | Context window |
| `-ub, --ubatch-size` | 512 | **Caps image tokens** (512 → image capped to 256 tokens) |
| `--image-max-tokens` | model | Per-image token budget (raise with `-ub`) |
| `--mtmd-batch-max-tokens` | 1024 | Max image tokens per batch |
| `--video-fps` | **4.0** | Video frame rate (model trained at **1.0**) |
| `--video-timestamp-interval` | 5000 ms | Text timestamp cadence in video |
| `--video-ffmpeg-dir` | PATH | Where ffmpeg/ffprobe live |
| `-np, --parallel` | auto | Server slots |
| `-cb, --cont-batching` | on | Continuous batching |

**Tuning recommendations for our app:**
- `--video-fps 1` — match the model's training rate (4.0 default = 4× more frames = slower + more tokens).
- `-ub 1024` (or higher) — lifts the image token cap from 256 toward the 280 default / up to 1120 for max quality.
- Keep `--pooling mean --embd-normalize 2` (model defaults).
- 768-d vectors (full MRL) — storage is trivial; best multimodal quality.

---

## 3. `/embedding` request formats (ALL VERIFIED on the running server)

Response shape (all modalities): `[{"index":0,"embedding":[[<768 floats>]]}]` → vector is `d[0]["embedding"][0]`.

### Text
```json
{"content": "task: search result | query: a red sports car in the rain"}
```

### Image
```json
{"content": "[img-1]", "image_data": [{"id": 1, "data": "<base64>"}]}
```

### Video
```json
{"content": "[video-1]", "video_data": [{"id": 1, "data": "<base64>"}]}
```

### Audio
```json
{"content": "[audio-1]", "audio_data": [{"id": 1, "data": "<base64>"}]}
```

**Large-file rule (verified):** a 5.5 MB MOV → 7.3 MB base64 → **too long for a shell arg**
(`curl: Argument list too long`). **Fix:** write the JSON payload to a temp file and
`curl -d @file`. The indexer must always use file-based payloads for media.

---

## 4. Supported input formats

| Modality | Accepted | Notes |
|---|---|---|
| Image | jpg, jpeg, png, webp (anything ffmpeg/PIL decodes) | 280 tokens default; budget 70–1120 |
| Video | **mp4, mov** (ffmpeg-decodable) | 140 tokens/frame; 1 fps default; ~58 frames max |
| Audio | wav, mp3, m4a, flac (ffmpeg-decodable) | resampled to 16 kHz mono; 25 tokens/sec |
| Text | any UTF-8 string | with task prefix for queries |

Our `media/` folder: 17 JPG + 4 MOV → all supported.

---

## 5. Constraints & gotchas

1. **Long videos exceed context.** At 140 tokens/frame, ~58 frames ≈ 8,192 tokens. A 60-s
   video at 1 fps = 60 frames > budget → server downsamples/caps. Long clips get
   temporally downsampled (acceptable for search).
2. **Image token cap** is tied to `-ub`. Default 512 → 256 tokens/image. Raise `-ub` for
   higher fidelity.
3. **float16 = NaN.** Our GGUF is BF16 → safe.
4. **Prefix for text→image** unproven → A/B test on real photos.
5. **Server must stay up.** Indexer + web app both depend on it. `run.sh` owns its lifecycle.
6. **One item per `/embedding` call** (no batch endpoint). Indexer is sequential;
   incremental + resume is essential for 10,000+.

---

## 6. Verified by running the model

- [x] Server loads model + mmproj, `/health` OK
- [x] Text → 768-d vector
- [x] Image (256×256 PNG) → 768-d vector
- [x] Video (2-s synthetic + 5.5 MB real MOV) → 768-d vector, ~0.08 s
- [x] Audio (2-s wav) → 768-d vector
- [x] Large file via temp-file payload works
- [x] Query prefix vs no-prefix (synthetic): 0.626 vs 0.698 → needs real-photo validation
- [x] ffmpeg present at `/opt/homebrew/bin/ffmpeg`

---

## 7. Open items to validate during build

1. **Query prefix** on real photos (A/B: with/without `task: search result | query:`).
2. **Image token budget** (256 vs 280 vs 560) impact on retrieval quality vs speed.
3. **Video fps** (1 vs 4) impact on retrieval quality vs speed.
4. **First-index throughput** on the real `media/` (files/second) to extrapolate to 10,000+.
5. **End-to-end** web search quality on the 21 sample files.
