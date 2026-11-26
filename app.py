"""app.py — PMS web app: the single control plane.

One port, everything local. The web app is the only interface:

  - gallery + semantic search over the media collection
  - settings tab: edit the media folder and embedding settings
  - reindex: trigger indexing from the UI with live progress
  - server: start / stop the llama-server embedding engine

The app manages the llama-server subprocess itself — no separate API,
no TUI required. run.sh just launches this app and opens the browser.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

import requests
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.utils import secure_filename

from build_index import run_indexing
from common import (
    EmbeddingClient,
    MediaDB,
    cosine_rank,
    load_config,
    make_client,
    save_config,
    server_url,
    verify_credentials,
)

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
CFG = load_config(CONFIG_PATH)


# --------------------------------------------------------------------------- #
# Embedding server lifecycle
# --------------------------------------------------------------------------- #

_server_proc: subprocess.Popen | None = None
_log_file = None


def _server_cmd() -> list[str]:
    s = CFG["server"]
    return [
        s["binary"],
        "--model", os.path.abspath(s["model"]),
        "--mmproj", os.path.abspath(s["mmproj"]),
        "--embedding", "--pooling", "mean", "--embd-normalize", "2",
        "--host", s["host"], "--port", str(s["port"]),
        "-c", str(s["ctx_size"]), "-ub", str(s["ubatch"]),
        "--image-max-tokens", str(s["image_tokens"]),
        "--video-fps", str(s["video_fps"]),
    ]


def server_running() -> bool:
    """True when the embedding server answers /health."""
    try:
        r = requests.get(server_url(CFG) + "/health", timeout=3)
        return r.ok
    except Exception:
        return False


def start_server() -> str:
    """Start llama-server as a child process and wait for it to be healthy."""
    global _server_proc, _log_file
    if server_running():
        return "already running"
    _log_file = open(os.path.join(BASE, ".server.log"), "ab")
    _server_proc = subprocess.Popen(
        _server_cmd(), stdout=_log_file, stderr=subprocess.STDOUT,
    )
    for _ in range(180):
        if server_running():
            return "started"
        if _server_proc.poll() is not None:
            return "failed to start — see .server.log"
        time.sleep(1)
    return "started (still warming up)"


def stop_server() -> str:
    """Stop the llama-server child process (if we started it)."""
    global _server_proc, _log_file
    if _server_proc is not None and _server_proc.poll() is None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
    _server_proc = None
    if _log_file is not None:
        _log_file.close()
        _log_file = None
    return "stopped"


# --------------------------------------------------------------------------- #
# Indexing (background thread with live progress)
# --------------------------------------------------------------------------- #

_index_lock = threading.Lock()
_index_state = {
    "running": False,
    "done": 0,
    "total": 0,
    "skipped": 0,
    "failed": 0,
    "current": "",
    "seconds": 0.0,
    "db_count": 0,
}


def _on_progress(done, total, skipped, failed, current, kind, started):
    with _index_lock:
        _index_state.update(
            done=done, total=total, skipped=skipped,
            failed=failed, current=current,
        )


def _index_worker():
    try:
        summary = run_indexing(CFG, on_progress=_on_progress)
        with _index_lock:
            _index_state.update(
                done=summary["encoded"], total=summary["total"],
                skipped=summary["skipped"], failed=summary["failed"],
                seconds=summary["seconds"], db_count=summary["db_count"],
                current="",
            )
    except Exception as e:
        with _index_lock:
            _index_state["current"] = f"ERROR: {type(e).__name__}: {e}"
    finally:
        with _index_lock:
            _index_state["running"] = False


def start_indexing() -> str:
    with _index_lock:
        if _index_state["running"]:
            return "already running"
        _index_state.update(running=True, done=0, total=0, skipped=0,
                            failed=0, current="starting…", seconds=0.0)
    threading.Thread(target=_index_worker, daemon=True).start()
    return "started"


# --------------------------------------------------------------------------- #
# Search + gallery
# --------------------------------------------------------------------------- #

def _client() -> EmbeddingClient:
    return make_client(CFG)


def _result_rows(paths, filenames, kinds, indices, scores):
    results = []
    for idx, score in zip(indices, scores):
        results.append({
            "filename": filenames[idx],
            "kind": kinds[idx],
            "score": score,
            "url": "/media/" + paths[idx].replace(os.sep, "/"),
        })
    return results


def _do_search(query: str, top_n: int):
    """Return a list of result dicts, best first. top_n<=0 means all."""
    qvec = _client().embed_text(query)
    with MediaDB(DB_PATH()) as db:
        paths, filenames, kinds, matrix = db.load_all()
    if matrix.size == 0:
        return []
    n = len(paths) if top_n <= 0 else top_n
    ranked = cosine_rank(matrix, qvec, n)
    return _result_rows(paths, filenames, kinds,
                        [i for i, _ in ranked], [s for _, s in ranked])


def _all_media(top_n: int):
    """Gallery view: the whole collection (capped), no query needed."""
    with MediaDB(DB_PATH()) as db:
        paths, filenames, kinds, matrix = db.load_all()
    if matrix.size == 0:
        return []
    n = len(paths) if top_n <= 0 else min(top_n, len(paths))
    rows = _result_rows(paths, filenames, kinds, list(range(n)), [0.0] * n)
    for r in rows:
        r["score"] = None  # gallery view: no scores to show
    return rows


def DB_PATH() -> str:
    return os.path.abspath(CFG["db_path"])


def _db_count() -> int:
    try:
        with MediaDB(DB_PATH()) as db:
            return db.count()
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #

app = Flask(__name__)

# Routes that must stay reachable without credentials: health checks from
# run.sh / Docker and the browser's status polling.
AUTH_EXEMPT = {"/health"}


@app.before_request
def _require_auth():
    """Enforce HTTP Basic Auth on every route except the exempt set."""
    if request.path in AUTH_EXEMPT:
        return None
    auth = request.authorization
    if auth is None or not verify_credentials(CFG, auth.username, auth.password):
        resp = Response("Authentication required", status=401)
        resp.headers["WWW-Authenticate"] = 'Basic realm="PMS"'
        return resp
    return None


@app.route("/")
def index():
    try:
        top_n = int(request.args.get("top", CFG["web"]["top_n"]))
    except ValueError:
        top_n = CFG["web"]["top_n"]
    if top_n < 0:
        top_n = CFG["web"]["top_n"]
    results = _all_media(top_n)
    return render_template("index.html", query="", results=results,
                           top_n=top_n,
                           media_count=_db_count(), error="",
                           cfg=CFG)


@app.route("/search", methods=["POST"])
def search():
    query = (request.form.get("query") or "").strip()
    try:
        top_n = int(request.form.get("top") or CFG["web"]["top_n"])
    except ValueError:
        top_n = CFG["web"]["top_n"]
    if top_n < 0:
        top_n = CFG["web"]["top_n"]  # 0 = All (∞)

    if not query:
        return render_template("index.html", query="", results=[], top_n=top_n,
                               media_count=_db_count(), error="", cfg=CFG)

    try:
        results = _do_search(query, top_n)
        error = ""
    except Exception as e:
        results = []
        error = f"Search failed: {type(e).__name__}: {e}"

    return render_template("index.html", query=query, results=results,
                           top_n=top_n,
                           media_count=_db_count(), error=error, cfg=CFG)


@app.route("/media/<path:filename>")
def media(filename):
    # secure + send_from_directory both prevent path traversal
    folder = os.path.abspath(CFG["media_folder"])
    return send_from_directory(folder, secure_filename(filename))


@app.route("/settings", methods=["POST"])
def save_settings():
    f = request.form
    try:
        CFG["media_folder"] = f.get("media_folder", CFG["media_folder"]).strip()
        CFG["embedding"]["dim"] = int(f.get("dim", CFG["embedding"]["dim"]))
        CFG["embedding"]["batch_size"] = int(
            f.get("batch_size", CFG["embedding"]["batch_size"]))
        CFG["server"]["image_tokens"] = int(f.get("image_tokens", CFG["server"]["image_tokens"]))
        CFG["server"]["video_fps"] = float(f.get("video_fps", CFG["server"]["video_fps"]))
        CFG["embedding"]["query_prefix"] = f.get("query_prefix") == "on"
        CFG["web"]["top_n"] = int(f.get("top_n", CFG["web"]["top_n"]))
        save_config(CONFIG_PATH, CFG)
    except (ValueError, KeyError):
        pass  # keep previous values on bad input
    return redirect("/")


@app.route("/reindex", methods=["POST"])
def reindex():
    return jsonify({"status": start_indexing()})


@app.route("/server/start", methods=["POST"])
def server_start():
    return jsonify({"status": start_server()})


@app.route("/server/stop", methods=["POST"])
def server_stop():
    return jsonify({"status": stop_server()})


@app.route("/reset-db", methods=["POST"])
def reset_db():
    path = DB_PATH()
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"status": "reset"})


@app.route("/status")
def status():
    with _index_lock:
        idx = dict(_index_state)
    return jsonify({
        "server": server_running(),
        "index": idx,
        "media_count": _db_count(),
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "media_count": _db_count()})


if __name__ == "__main__":
    # Auto-start the embedding server if it isn't running, so the app is
    # self-contained: one process, one port, everything local.
    if not server_running():
        threading.Thread(target=start_server, daemon=True).start()
    web = CFG["web"]
    app.run(host=web["host"], port=web["port"], debug=False)
