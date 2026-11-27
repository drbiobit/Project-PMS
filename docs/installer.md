# Installer

The fastest way to run PMS is the one-shot installer, `install.sh`. It
checks Docker, walks you through a few questions, writes a
`docker-compose.yml` for you, and starts the gallery — no YAML editing.

```bash
curl -fsSL https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh | bash
```

Or, from a local clone of the repo (needed for the OpenAI mode, which
builds images from source):

```bash
git clone https://github.com/drbiobit/Project-PMS.git
cd Project-PMS
./install.sh
```

---

## What it asks

| Step | Prompt | Default |
|------|--------|---------|
| 1. Media folder | Where your photos/videos/audio live | `./media` |
| 2. Mode | `1` Bundled · `2` OpenAI endpoint | Bundled |
| 3. Backend / image | Which image or build variant to use | CPU (x86_64) |
| 4. Username | Login for the gallery | `admin` |
| 5. Password | Login for the gallery (hidden input) | `pms` |

Press **Enter** on any prompt to accept the default.

---

## Deployment modes

### Bundled (recommended)

A single self-contained image that runs its own `llama-server`. Picked from
pre-built images published to GHCR:

| Choice | Image |
|--------|-------|
| CUDA — NVIDIA GPU | `ghcr.io/drbiobit/project-pms:cuda` |
| ROCm — AMD GPU | `ghcr.io/drbiobit/project-pms:rocm` |
| CPU — x86_64 | `ghcr.io/drbiobit/project-pms:cpu` |
| CPU — ARM / Apple Silicon | `ghcr.io/drbiobit/project-pms:cpu-arm64` |

The installer pulls the chosen image (or uses it if already local).

### OpenAI endpoint

The **slim app image** (`Dockerfile.openai`) with no engine, pointed at a
locally-hosted OpenAI-compatible endpoint. The installer **builds two images
from the current directory** (a clone of the repo is required):

- `project-pms:openai` — the slim app (`Dockerfile.openai`)
- `pms-embed-server:<backend>` — a standalone embedding server
  (`Dockerfile.server`), built for the backend you choose (CUDA / ROCm / CPU /
  ARM64)

Then it writes a two-service compose file (app + embedding) and brings both
up. These images are built from source, not pulled from GHCR.

---

## What it writes

The installer drops two files in the current directory:

- **`.env`** — your media path, port, and the username/password you entered.
- **`docker-compose.yml`** — the service definition. The container is always
  named **`project-pms`** (so `docker stop project-pms` works). If either
  file already exists, it's backed up as `<name>.bak-<timestamp>` first.

---

## After it runs

The installer waits until the gallery answers `/health`, prints the URL and
your login, and opens the browser:

```
Your gallery is live at:  http://localhost:9090
Login:  admin / <your-password>
```

**Manage it later:**

```bash
docker compose down          # stop it (keeps your index in the pms-data volume)
docker compose up -d         # start it again (re-indexing is incremental)
docker compose logs pms      # watch the logs
```

To change the port, re-run `./install.sh` with `PMS_PORT=<port> ./install.sh`
(or edit `PMS_PORT` in `.env` / the compose file).

> 📖 For manual, non-installer deployments (raw `docker run`, GPU device
> reservations, the full env-var reference, and the OpenAI compose file), see
> [Deployment](deployment.md).
