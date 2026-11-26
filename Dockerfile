# PMS — Portable Media Search
#
# One Ubuntu image, four llama.cpp backends, selected at build time:
#
#   LLAMA_VARIANT   backend                              arch
#   -------------   ---------------------------------  ----------------
#   cpu-x64         CPU (default)                        x86_64
#   cpu-arm64       CPU                                  aarch64
#   cuda-x64        NVIDIA CUDA (latest CUDA build)      x86_64
#   rocm-x64        AMD ROCm (latest ROCm build)         x86_64
#
# Build:
#   docker build --build-arg LLAMA_VARIANT=cuda-x64 -t pms:cuda .
#
# Run:
#   docker run -p 9090:9090 -v /path/to/media:/media -v pms-data:/data pms:cpu
#
# The image downloads at build time:
#   - the newest llama.cpp release that ships binary assets
#     (the pinned "latest" release is a pointer with no binaries, so the
#     build walks releases back until it finds real assets)
#   - EmbeddingGemma-2 Q5_K_XL + mmproj Q8_0 from unsloth/embeddinggemma-2-GGUF

FROM ubuntu:24.04

# Pinned llama.cpp release (b12776) — update deliberately when you want a
# newer engine. The CUDA/ROCm toolchain versions are pinned with it.
ARG LLAMA_BUILD=b12776
ARG LLAMA_VARIANT=cpu-x64

ENV DEBIAN_FRONTEND=noninteractive

# ── system dependencies ────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl python3 python3-pip libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── application code ───────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py common.py build_index.py search.py entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh
COPY templates/ templates/
COPY static/ static/

# ── downloads: llama.cpp + both model files, fetched in parallel ───────
# Running the three downloads concurrently cuts build time from the sum
# of the three to the slowest one.
RUN set -eux; \
    case "${LLAMA_VARIANT}" in \
      cpu-x64)   ASSET="llama-${LLAMA_BUILD}-bin-ubuntu-x64.tar.gz" ;; \
      cpu-arm64) ASSET="llama-${LLAMA_BUILD}-bin-ubuntu-arm64.tar.gz" ;; \
      cuda-x64)  ASSET="llama-${LLAMA_BUILD}-bin-ubuntu-cuda-13.5-x64.tar.gz" ;; \
      rocm-x64)  ASSET="llama-${LLAMA_BUILD}-bin-ubuntu-rocm-10.0-x64.tar.gz" ;; \
      *) echo "unsupported LLAMA_VARIANT: ${LLAMA_VARIANT}"; exit 1 ;; \
    esac; \
    URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_BUILD}/${ASSET}"; \
    HF="https://huggingface.co/unsloth/embeddinggemma-2-GGUF/resolve/main"; \
    echo "llama.cpp ${LLAMA_BUILD} (${LLAMA_VARIANT})"; \
    mkdir -p /models; \
    ( curl -fL --retry 3 "$URL" -o /tmp/llama.tar.gz ) & P_LLAMA=$!; \
    ( curl -fL --retry 3 "$HF/embeddinggemma-2-UD-Q5_K_XL.gguf" -o /models/embeddinggemma-2-UD-Q5_K_XL.gguf ) & P_MODEL=$!; \
    ( curl -fL --retry 3 "$HF/mmproj-Q8_0.gguf" -o /models/mmproj-Q8_0.gguf ) & P_MMPROJ=$!; \
    wait "$P_LLAMA" "$P_MODEL" "$P_MMPROJ"; \
    tar -xzf /tmp/llama.tar.gz -C /opt; \
    ln -sfn /opt/llama-${LLAMA_BUILD} /opt/llama; \
    rm -rf /tmp/llama.tar.gz /tmp/llama-*

# ── runtime ────────────────────────────────────────────────────────────
VOLUME ["/data"]
ENV PMS_MEDIA_DIR=/media \
    PMS_DATA_DIR=/data \
    PMS_PORT=9090 \
    PMS_SERVER_PORT=8080 \
    PMS_TOP_N=100 \
    PMS_AUTH_USER=admin \
    PMS_AUTH_PASS=pms
EXPOSE 9090
ENTRYPOINT ["/app/entrypoint.sh"]
