#!/bin/bash
# PMS — Portable Media Search
#
# One command: start the web app (which manages the embedding server
# and the index itself), then open the browser.
#
#   ./run.sh          start everything + open browser
#   ./run.sh stop     stop the web app and the embedding server
#
# The web app is the single interface: gallery, search, settings,
# reindex, and server control all live in the browser on one port.
set -e
cd "$(dirname "$0")"

WEB_PID_FILE=".web.pid"

if [ "${1:-}" = "stop" ]; then
  if [ -f "$WEB_PID_FILE" ]; then
    kill "$(cat "$WEB_PID_FILE")" 2>/dev/null || true
    rm -f "$WEB_PID_FILE"
  fi
  # stop a server the web app started (child process, already gone with it)
  pkill -f "llama-server" 2>/dev/null || true
  echo "PMS stopped."
  exit 0
fi

PORT=$(./venv/bin/python -c "import json; print(json.load(open('config.json'))['web']['port'])")

if [ -f "$WEB_PID_FILE" ] && kill -0 "$(cat "$WEB_PID_FILE")" 2>/dev/null; then
  echo "PMS is already running at http://127.0.0.1:$PORT"
  open "http://127.0.0.1:$PORT" 2>/dev/null || xdg-open "http://127.0.0.1:$PORT" || true
  exit 0
fi

nohup ./venv/bin/python app.py > .web.log 2>&1 &
echo $! > "$WEB_PID_FILE"

# wait for the app to come up
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "PMS running at http://127.0.0.1:$PORT"
open "http://127.0.0.1:$PORT" 2>/dev/null || xdg-open "http://127.0.0.1:$PORT" || true
