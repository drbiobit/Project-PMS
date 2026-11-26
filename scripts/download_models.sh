#!/bin/bash
# Download the EmbeddingGemma-2 GGUF files that config.json points at.
#
#   model:  embeddinggemma-2-UD-Q5_K_XL.gguf  (~1.5 GB, Q5_K_XL)
#   mmproj: mmproj-Q8_0.gguf                  (vision/audio projector, Q8_0)
#
# Both come from unsloth/embeddinggemma-2-GGUF on the Hugging Face Hub.
# Run from the repo root:  ./scripts/download_models.sh
set -euo pipefail

cd "$(dirname "$0")/.."

DEST="models/embeddinggemma"
HF="https://huggingface.co/unsloth/embeddinggemma-2-GGUF/resolve/main"

mkdir -p "$DEST"

download() {
  local name="$1"
  local url="$HF/$name"
  if [ -f "$DEST/$name" ]; then
    echo "✓ $name already present — skipping"
    return 0
  fi
  echo "↓ $name"
  curl -fL --retry 3 -o "$DEST/$name.part" "$url"
  mv "$DEST/$name.part" "$DEST/$name"
}

download "embeddinggemma-2-UD-Q5_K_XL.gguf"
download "mmproj-Q8_0.gguf"

echo "Done. Models in $DEST:"
ls -lh "$DEST"
