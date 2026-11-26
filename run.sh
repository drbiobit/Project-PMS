#!/usr/bin/env bash
# run.sh — the single deploy command for search-media.
#
#   ./run.sh            interactive deploy (TUI: config → server → index → web)
#   ./run.sh stop       stop the running server + web app
#
# The TUI (tui.py) does everything: starts llama-server, indexes the media
# folder, launches the web app, and opens the browser. The server and web app
# keep running after the TUI exits (detached background processes).
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "stop" ]; then
  exec venv/bin/python tui.py stop
fi

exec venv/bin/python tui.py "$@"
