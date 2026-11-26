"""app.py — the web UI (Flask).

A thin server: it embeds the query via the running llama-server, ranks it
against the stored vectors in SQLite, and renders a results grid with
thumbnails / video players / audio players. It never loads the model itself.

Routes:
    GET  /                  search page (empty results)
    POST /search            embed query + rank + render results
    GET  /media/<path>      serve an original media file (safe)
    GET  /health            liveness probe (used by the TUI)
"""

from __future__ import annotations

import os

from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from common import (
    EmbeddingClient,
    MediaDB,
    cosine_rank,
    load_config,
    server_url,
)

CFG = load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
MEDIA_FOLDER = os.path.abspath(CFG["media_folder"])
DB_PATH = os.path.abspath(CFG["db_path"])


def _client() -> EmbeddingClient:
    emb = CFG["embedding"]
    return EmbeddingClient(
        base_url=server_url(CFG),
        dim=emb["dim"],
        query_prefix=emb["query_prefix"],
        query_prefix_text=emb["query_prefix_text"],
    )


def _do_search(query: str, top_n: int):
    """Return a list of result dicts, best first."""
    qvec = _client().embed_text(query)
    with MediaDB(DB_PATH) as db:
        paths, filenames, kinds, matrix = db.load_all()
    if matrix.size == 0:
        return []
    ranked = cosine_rank(matrix, qvec, top_n)
    results = []
    for idx, score in ranked:
        rel = paths[idx]
        results.append({
            "filename": filenames[idx],
            "kind": kinds[idx],
            "score": score,
            "url": "/media/" + rel.replace(os.sep, "/"),
        })
    return results


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", query="", results=[], top_n=CFG["web"]["top_n"],
                           media_count=_db_count(), error="")


@app.route("/search", methods=["POST"])
def search():
    query = (request.form.get("query") or "").strip()
    try:
        top_n = int(request.form.get("top") or CFG["web"]["top_n"])
    except ValueError:
        top_n = CFG["web"]["top_n"]
    top_n = max(1, min(top_n, 100))

    if not query:
        return render_template("index.html", query="", results=[], top_n=top_n,
                               media_count=_db_count(), error="")

    try:
        results = _do_search(query, top_n)
        error = ""
    except Exception as e:
        results = []
        error = f"Search failed: {type(e).__name__}: {e}"

    return render_template("index.html", query=query, results=results, top_n=top_n,
                           media_count=_db_count(), error=error)


@app.route("/media/<path:filename>")
def media(filename):
    # secure + send_from_directory both prevent path traversal
    return send_from_directory(MEDIA_FOLDER, secure_filename(filename))


@app.route("/health")
def health():
    return {"status": "ok", "media_count": _db_count()}


def _db_count() -> int:
    try:
        with MediaDB(DB_PATH) as db:
            return db.count()
    except Exception:
        return 0


if __name__ == "__main__":
    web = CFG["web"]
    app.run(host=web["host"], port=web["port"], debug=False)
