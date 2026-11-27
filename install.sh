#!/usr/bin/env bash
# PMS — Portable Media Search · one-shot installer / launcher
#
# Run it straight from GitHub (no clone needed):
#   curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash
#
# or, from a local clone:
#   ./install.sh
#
# What it does:
#   1. Checks that Docker is available — cancels cleanly if not.
#   2. Asks for your media folder.
#   3. Lets you pick a mode:
#        • bundled  — a self-contained image that runs its own embedding
#                     server (pick cuda / rocm / cpu / cpu-arm64).
#        • openai   — the slim app image pointed at a locally-hosted
#                     OpenAI-compatible endpoint (this installer builds the
#                     slim app + a standalone embedding server from source).
#   4. Asks for a username and password.
#   5. Writes .env + docker-compose.yml, starts the container(s) via
#      `docker compose up`, waits briefly for the gallery to answer /health,
#      and opens it in your browser.
set -euo pipefail

# ── colours (only when stdout is a tty) ───────────────────────────────────
if [ -t 1 ]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; CYAN=$'\e[36m'; OK=$'\e[32m'; WARN=$'\e[33m'; ERR=$'\e[31m'; RST=$'\e[0m'
else
  BOLD=""; DIM=""; CYAN=""; OK=""; WARN=""; ERR=""; RST=""
fi

info()  { printf '%s\n' "${BOLD}$*${RST}"; }
ok()    { printf '%s\n' "${OK}✓ $*${RST}"; }
warn()  { printf '%s\n' "${WARN}⚠ $*${RST}"; }
# cancel: a graceful, non-fatal stop (Docker missing, bad input, …).
cancel() { printf '\n%s\n' "${ERR}✗ $*${RST}" >&2; exit 0; }

# ── 0. banner ─────────────────────────────────────────────────────────────
# "Project-PMS" banner (hard-coded ASCII art, held in a Python raw string so
# no shell escaping is needed).
printf '\n'
BANNER=$(python3 -c 'print(r"""  ___             _         __    ___
  / _ \_______    (_)__ ____/ /_  / _ \__ _  ___
 / ___/ __/ _ \  / / -_) __/ __/ / ___/  '"'"' \(_-<
/_/  /_/  \___/_/ /\__/\__/\__/ /_/  /_/_/_/___/
             |___/""")')
while IFS= read -r line; do
  printf '%s\n' "${BOLD}${CYAN}${line}${RST}"
done <<< "$BANNER"
printf '%s\n' \
  "${DIM} Portable Media Search  ·  local-first multimodal search${RST}" \
  "${DIM} Search your photos, videos & audio with plain words${RST}" \
  "${DIM} 100% local  ·  no cloud  ·  no API keys${RST}"
printf '\n'

# ── 1. Docker availability (proceed, or cancel) ───────────────────────────
command -v docker >/dev/null 2>&1 \
  || cancel "Docker not found — install it first: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 \
  || cancel "Docker isn't running — start Docker, then run me again."
command -v curl >/dev/null 2>&1 \
  || cancel "curl not found — install it first (used to check the gallery is up)."
# Pick the compose command: the v2 plugin ('docker compose') if present,
# otherwise the standalone v1 binary ('docker-compose').
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  cancel "Neither 'docker compose' nor 'docker-compose' is available — update Docker."
fi

# ── 2. gather inputs ──────────────────────────────────────────────────────
# Prompts must read from the controlling terminal, NOT stdin: when the
# script arrives via a pipe (`curl … | bash`) stdin is the script itself,
# so a plain `read` would swallow lines of the script instead of input.
[ -r /dev/tty ] || cancel "no interactive terminal — run the installer from a terminal."

printf '\n'
read -r -p "Media folder path  [default: ./media]: " MEDIA_DIR < /dev/tty
MEDIA_DIR="${MEDIA_DIR:-./media}"

# Deployment mode.
printf '\n'
info "Pick a deployment mode:"
info "  1) Bundled — self-contained image, runs its own embedding server (recommended)"
info "  2) OpenAI  — slim app image + a locally-hosted OpenAI-compatible endpoint"
read -r -p "Choice [1-2, default 1]: " MODE_CHOICE < /dev/tty
case "${MODE_CHOICE:-1}" in
  2) MODE="openai" ;;
  *) MODE="bundled" ;;
esac

# Pick the backend image / build variant.
if [ "$MODE" = "openai" ]; then
  # The OpenAI mode builds two images FROM SOURCE: the slim app
  # (Dockerfile.openai) and a standalone embedding server
  # (Dockerfile.server, chosen by backend). These are not on GHCR.
  info "Pick the embedding-server backend (built from source):"
  info "  1) CUDA  — NVIDIA GPU"
  info "  2) ROCm  — AMD GPU"
  info "  3) CPU   — x86_64"
  info "  4) CPU   — ARM / Apple Silicon"
  read -r -p "Choice [1-4, default 3]: " VARIANT_CHOICE < /dev/tty
  case "${VARIANT_CHOICE:-3}" in
    1) BUILD_VARIANT="cuda-x64"  ;;
    2) BUILD_VARIANT="rocm-x64"  ;;
    3) BUILD_VARIANT="cpu-x64"   ;;
    4) BUILD_VARIANT="cpu-arm64" ;;
    *) BUILD_VARIANT="cpu-x64"   ;;
  esac
else
  # Bundled mode: pre-built images published to GHCR.
  info "Pick an image:"
  info "  1) CUDA  — NVIDIA GPU           ghcr.io/drbiobit/project-pms:cuda"
  info "  2) ROCm  — AMD GPU              ghcr.io/drbiobit/project-pms:rocm"
  info "  3) CPU   — x86_64               ghcr.io/drbiobit/project-pms:cpu"
  info "  4) CPU   — ARM / Apple Silicon  ghcr.io/drbiobit/project-pms:cpu-arm64"
  read -r -p "Choice [1-4, default 3]: " VARIANT_CHOICE < /dev/tty
  case "${VARIANT_CHOICE:-3}" in
    1) VARIANT="cuda" ;;
    2) VARIANT="rocm" ;;
    3) VARIANT="cpu" ;;
    4) VARIANT="cpu-arm64" ;;
    *) VARIANT="cpu" ;;
  esac
fi

read -r -p "Username           [default: admin]: " PMS_USER < /dev/tty
PMS_USER="${PMS_USER:-admin}"
read -r -s -p "Password           [default: pms]: " PMS_PASS < /dev/tty
PMS_PASS="${PMS_PASS:-pms}"
printf '\n'

# Expand a leading ~ ("~/Videos") — read -r doesn't.
case "$MEDIA_DIR" in
  "~")    MEDIA_DIR="$HOME" ;;
  "~/"*)  MEDIA_DIR="${HOME}/${MEDIA_DIR#"~/"}" ;;
esac
# Resolve to an absolute path so the compose file is location-independent.
case "$MEDIA_DIR" in
  /*) : ;;
  *)  MEDIA_DIR="$PWD/$MEDIA_DIR" ;;
esac
[ -d "$MEDIA_DIR" ] || warn "Media folder '$MEDIA_DIR' doesn't exist yet — it will be created empty."
mkdir -p "$MEDIA_DIR"

# ── 3. write .env + docker-compose.yml ────────────────────────────────────
# Host port the gallery is published on — override with PMS_PORT=<port>.
case "${PMS_PORT:-}" in
  "") PMS_PORT=9090 ;;
  *[!0-9]*) cancel "PMS_PORT must be a number (got '${PMS_PORT}')" ;;
esac
# Never clobber existing files (e.g. when running from a repo clone): back up.
for f in docker-compose.yml .env; do
  if [ -f "$f" ]; then
    bak="${f}.bak-$(date +%Y%m%d%H%M%S)"
    mv "$f" "$bak"
    warn "existing ${f} backed up to ${bak}"
  fi
done

if [ "$MODE" = "openai" ]; then
  # OpenAI mode: two services (app + embedding server). Both images are
  # built from the repo in the current directory.
  info "Deployment: OpenAI endpoint — building two images from source (first run only)…"
  APP_IMAGE="project-pms:openai"
  EMBED_IMAGE="pms-embed-server:${BUILD_VARIANT}"
  cat > .env <<EOF
PMS_MEDIA_DIR=/media
PMS_DATA_DIR=/data
PMS_PORT=${PMS_PORT}
PMS_TOP_N=100
PMS_AUTH_USER=${PMS_USER}
PMS_AUTH_PASS=${PMS_PASS}
PMS_EMBED_BASE_URL=http://embedding:8080/v1
PMS_EMBED_API_KEY=
PMS_EMBED_MODEL=embeddinggemma-2
EOF

  cat > docker-compose.yml <<EOF
services:
  embedding:
    image: ${EMBED_IMAGE}
    build:
      context: .
      dockerfile: Dockerfile.server
      args:
        LLAMA_VARIANT: ${BUILD_VARIANT}
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 30
  pms:
    image: ${APP_IMAGE}
    container_name: project-pms
    build:
      context: .
      dockerfile: Dockerfile.openai
    depends_on:
      embedding:
        condition: service_healthy
    ports:
      - "${PMS_PORT}:9090"
    volumes:
      - ${MEDIA_DIR}:/media:ro
      - pms-openai-data:/data
    env_file: .env
    restart: unless-stopped
volumes:
  pms-openai-data:
EOF
else
  # Bundled mode: a single self-contained image pulled from GHCR.
  IMAGE="ghcr.io/drbiobit/project-pms:${VARIANT}"
  info "Using image: ${BOLD}${IMAGE}${RST}"
  cat > .env <<EOF
PMS_MEDIA_DIR=/media
PMS_PORT=${PMS_PORT}
PMS_TOP_N=100
PMS_AUTH_USER=${PMS_USER}
PMS_AUTH_PASS=${PMS_PASS}
EOF

  cat > docker-compose.yml <<EOF
services:
  pms:
    image: ${IMAGE}
    container_name: project-pms
    ports:
      - "${PMS_PORT}:9090"
    volumes:
      - ${MEDIA_DIR}:/media:ro
      - pms-data:/data
    env_file: .env
    restart: unless-stopped
volumes:
  pms-data:
EOF
fi
ok "wrote .env and docker-compose.yml"

# ── 4. get the image(s) ───────────────────────────────────────────────────
if [ "$MODE" = "openai" ]; then
  info "building ${BOLD}${APP_IMAGE}${RST} and ${BOLD}${EMBED_IMAGE}${RST} (first run only)…"
  # `up -d` will build any image that lacks one; build explicitly for clearer progress.
  docker compose build
else
  if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    ok "image ${IMAGE} already present"
  else
    info "pulling ${IMAGE} (first run only)…"
    docker pull "$IMAGE" \
      || cancel "couldn't pull ${IMAGE} — check your network and try again"
    ok "image ready"
  fi
fi

# ── 5. start the container(s) ─────────────────────────────────────────────
info "starting…"
$COMPOSE up -d

# ── 6. wait briefly for ready ─────────────────────────────────────────────
health() { curl -sf "http://localhost:${PMS_PORT}/health" 2>/dev/null; }
info "waiting for the gallery to come up…"
ready=0
for _ in $(seq 1 90); do
  if health | grep -qE '"status"[[:space:]]*:[[:space:]]*"ok"'; then ready=1; break; fi
  sleep 2
done
[ "$ready" -eq 1 ] || cancel "the container didn't become ready in time — inspect with: $COMPOSE logs pms"
ok "gallery is up"

# ── 7. open the browser ────────────────────────────────────────────────────
URL="http://localhost:${PMS_PORT}"
info "Your gallery is live at:  ${BOLD}${URL}${RST}"
info "Login:  ${BOLD}${PMS_USER}${RST} / ${BOLD}${PMS_PASS}${RST}"
case "$(uname)" in
  Darwin) open "$URL" 2>/dev/null || true ;;
  Linux)  xdg-open "$URL" 2>/dev/null || true ;;
esac

printf '\n'
ok "done — the gallery should be opening in your browser."
info "Stop it later with:  ${COMPOSE} down"
printf '\n'
