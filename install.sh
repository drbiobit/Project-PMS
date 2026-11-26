#!/usr/bin/env bash
# PMS — Portable Media Search · one-shot installer / launcher
#
# Run it straight from GitHub (no clone needed):
#   curl -fsSL https://raw.githubusercontent.com/drbiobit/search-media/main/install.sh | bash
#
# or, from a local clone:
#   ./install.sh
#
# What it does:
#   1. Detects the hardware (NVIDIA GPU / AMD GPU / ARM or x86 CPU) and picks
#      the matching image.
#   2. Asks for your media folder, username and password.
#   3. Writes .env + docker-compose.yml for you.
#   4. Pulls the image, starts the container, and waits — with a live
#      spinner while it boots and a live progress readout while it indexes.
#   5. Opens the gallery in your browser when it's ready.
set -euo pipefail

# ── colours (only when stdout is a tty) ───────────────────────────────────
if [ -t 1 ]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; OK=$'\e[32m'; WARN=$'\e[33m'; ERR=$'\e[31m'; RST=$'\e[0m'
else
  BOLD=""; DIM=""; OK=""; WARN=""; ERR=""; RST=""
fi

info() { printf '%s\n' "${BOLD}$*${RST}"; }
ok()   { printf '%s\n' "${OK}✓ $*${RST}"; }
warn() { printf '%s\n' "${WARN}⚠ $*${RST}"; }
die()  { printf '%s\n' "${ERR}✗ $*${RST}" >&2; exit 1; }

# Spinner: spins a character in the margin while $SPIN_MSG is shown.
SPIN_PID=""
start_spinner() {
  SPIN_MSG="${1:-working…}"
  ( local s='|/-\ '
    while :; do
      printf '\r [%c] %s' "${s:0:1}" "$SPIN_MSG"
      s="${s:1}$s:0:1"
      sleep 0.1
    done ) &
  SPIN_PID=$!
}
stop_spinner() {
  [ -n "$SPIN_PID" ] && { kill "$SPIN_PID" 2>/dev/null || true; wait "$SPIN_PID" 2>/dev/null || true; }
  SPIN_PID=""
  printf '\r%*s\r' $(( ${#SPIN_MSG} + 5 )) ''
}

# ── 0. banner + prerequisites ────────────────────────────────────────────
printf '\n'
info "PMS · Portable Media Search — installer"
info "----------------------------------------"

command -v docker >/dev/null 2>&1 \
  || die "Docker not found. Install it first: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 \
  || die "Docker isn't running. Start Docker and try again."
# Pick the compose command: the v2 plugin ('docker compose') if present,
# otherwise the standalone v1 binary ('docker-compose').
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Neither 'docker compose' nor 'docker-compose' is available. Update Docker."
fi

# ── 1. detect hardware → pick the image ───────────────────────────────────
detect_variant() {
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    printf 'cuda'
  elif [ -e /dev/kfd ] && command -v rocm-smi >/dev/null 2>&1 \
       && rocm-smi >/dev/null 2>&1; then
    printf 'rocm'
  else
    case "$(uname -m)" in
      aarch64|arm64) printf 'cpu-arm64' ;;
      *)             printf 'cpu' ;;
    esac
  fi
}

VARIANT="$(detect_variant)"
IMAGE="ghcr.io/drbiobit/pms:${VARIANT}"
case "$VARIANT" in
  cuda)      HW="NVIDIA GPU (CUDA)" ;;
  rocm)      HW="AMD GPU (ROCm)" ;;
  cpu-arm64) HW="CPU (ARM / Apple Silicon)" ;;
  *)         HW="CPU (x86_64)" ;;
esac
info "Hardware: ${HW}  →  image ${IMAGE}"

# ── 2. gather inputs ──────────────────────────────────────────────────────
printf '\n'
read -r -p "Media folder path  [default: ./media]: " MEDIA_DIR
MEDIA_DIR="${MEDIA_DIR:-./media}"
read -r -p "Username           [default: admin]: " PMS_USER
PMS_USER="${PMS_USER:-admin}"
read -r -s -p "Password           [default: pms]: " PMS_PASS
PMS_PASS="${PMS_PASS:-pms}"
printf '\n'

# Resolve to an absolute path so the compose file is location-independent.
case "$MEDIA_DIR" in
  /*) : ;;
  *)  MEDIA_DIR="$PWD/$MEDIA_DIR" ;;
esac
[ -d "$MEDIA_DIR" ] || warn "Media folder '$MEDIA_DIR' doesn't exist yet — it will be created empty."
mkdir -p "$MEDIA_DIR"

# ── 3. write .env + docker-compose.yml ────────────────────────────────────
# PMS_MEDIA_DIR is the path INSIDE the container (/media); the host path
# ${MEDIA_DIR} is mounted onto it in the compose file below.
cat > .env <<EOF
PMS_MEDIA_DIR=/media
PMS_PORT=9090
PMS_TOP_N=100
PMS_AUTH_USER=${PMS_USER}
PMS_AUTH_PASS=${PMS_PASS}
EOF

cat > docker-compose.yml <<EOF
services:
  pms:
    image: ${IMAGE}
    ports:
      - "9090:9090"
    volumes:
      - ${MEDIA_DIR}:/media:ro
      - pms-data:/data
    env_file: .env
    restart: unless-stopped
volumes:
  pms-data:
EOF
ok "wrote .env and docker-compose.yml"

# ── 4. get the image (use it if already local, otherwise pull) ───────────
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  ok "image ${IMAGE} already present"
else
  start_spinner "pulling ${IMAGE} (first run only)…"
  if docker pull "$IMAGE"; then
    stop_spinner
    ok "image ready"
  else
    stop_spinner
    die "couldn't pull ${IMAGE} — check your network and try again"
  fi
fi

# ── 5. start the container ────────────────────────────────────────────────
info "starting the container…"
$COMPOSE up -d

# ── 6. wait for ready, streaming the indexing progress ────────────────────
health() { curl -sf "http://localhost:9090/health" 2>/dev/null; }

# The gallery comes up first; indexing then runs in the background and the
# web UI shows its live progress. We just wait for the app to answer /health.
start_spinner "starting the gallery…"
ready=0
for _ in $(seq 1 300); do
  if health | grep -q '"status":"ok"'; then ready=1; break; fi
  sleep 2
done
stop_spinner
[ "$ready" -eq 1 ] || die "the container didn't become ready in time — inspect with: $COMPOSE logs pms"
ok "gallery is up"

# ── 7. open the browser ────────────────────────────────────────────────────
URL="http://localhost:9090"
info "Your gallery is live at:  ${BOLD}${URL}${RST}"
info "Login:  ${BOLD}${PMS_USER}${RST} / ${BOLD}${PMS_PASS}${RST}"
case "$(uname)" in
  Darwin) open "$URL" 2>/dev/null || true ;;
  Linux)  xdg-open "$URL" 2>/dev/null || true ;;
esac

printf '\n'
ok "done — the gallery should be opening in your browser."
info "Stop it later with:  docker compose down"
printf '\n'
