"""build_index.py — walk a media folder, embed every file via the running
llama-server, and store the vectors in SQLite.

Incremental: a file is skipped when its path + mtime are already in the DB,
so re-runs only process new/changed files. This is what makes 10,000+ files
manageable.

Run standalone:
    ./venv/bin/python build_index.py --media ./media --db media.db

The TUI imports `run_indexing` and passes a progress callback.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Callable, Optional

from common import (
    AUDIO_EXTS,
    IMAGE_EXTS,
    VIDEO_EXTS,
    EmbeddingClient,
    MediaDB,
    load_config,
    server_url,
)

ProgressFn = Callable[[int, int, int, int, str, str, float], None]


# --------------------------------------------------------------------------- #
# Metadata helpers
# --------------------------------------------------------------------------- #


def image_dims(path: str):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0], im.size[1], None
    except Exception:
        return None, None, None


def ffprobe(path: str):
    """Return (width, height, duration) via ffprobe; None on failure."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json", path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = data.get("format", {}).get("duration")
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = None
        return stream.get("width"), stream.get("height"), duration
    except Exception:
        return None, None, None


def get_metadata(kind: str, path: str):
    if kind == "image":
        return image_dims(path)
    return ffprobe(path)


# --------------------------------------------------------------------------- #
# File discovery
# --------------------------------------------------------------------------- #


def kind_for(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def iter_media(media_folder: str):
    """Yield (relpath, abspath, kind) for every supported file, sorted."""
    for root, _dirs, files in os.walk(media_folder):
        for name in sorted(files):
            kind = kind_for(name)
            if kind is None:
                continue
            abspath = os.path.join(root, name)
            relpath = os.path.relpath(abspath, media_folder)
            yield relpath, abspath, kind


# --------------------------------------------------------------------------- #
# Indexing
# --------------------------------------------------------------------------- #


def run_indexing(cfg: dict, on_progress: Optional[ProgressFn] = None) -> dict:
    """Index the configured media folder. Returns a summary dict."""
    media_folder = os.path.abspath(cfg["media_folder"])
    db_path = os.path.abspath(cfg["db_path"])
    emb = cfg["embedding"]
    client = EmbeddingClient(
        base_url=server_url(cfg),
        dim=emb["dim"],
        query_prefix=emb["query_prefix"],
        query_prefix_text=emb["query_prefix_text"],
    )

    files = list(iter_media(media_folder))
    total = len(files)
    done = skipped = failed = 0
    started = time.time()

    with MediaDB(db_path) as db:
        for i, (relpath, abspath, kind) in enumerate(files, start=1):
            mtime = os.path.getmtime(abspath)
            current = os.path.basename(abspath)

            if db.is_indexed(relpath, mtime):
                skipped += 1
                if on_progress:
                    on_progress(done, total, skipped, failed, current, "skip", started)
                continue

            width = height = duration = None
            try:
                width, height, duration = get_metadata(kind, abspath)
                vec = {
                    "image": client.embed_image,
                    "video": client.embed_video,
                    "audio": client.embed_audio,
                }[kind](abspath)
                db.upsert(
                    path=relpath,
                    filename=os.path.basename(abspath),
                    kind=kind,
                    width=width,
                    height=height,
                    duration=duration,
                    size_bytes=os.path.getsize(abspath),
                    mtime=mtime,
                    embedding=vec,
                )
                done += 1
            except Exception as e:  # keep going; report the failure
                failed += 1
                current = f"{current}  ({type(e).__name__}: {e})"

            if on_progress:
                on_progress(done, total, skipped, failed, current, kind, started)

    return {
        "total": total,
        "encoded": done,
        "skipped": skipped,
        "failed": failed,
        "seconds": time.time() - started,
        "db_count": db.count(),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print_progress(done, total, skipped, failed, current, kind, started):
    elapsed = time.time() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    bar_len = 40
    frac = done / total if total else 0
    filled = int(frac * bar_len)
    bar = "+" * filled + "-" * (bar_len - filled)
    sys.stdout.write(
        f"\r  {bar} {frac:3.0%}  {done}/{total}  "
        f"skip {skipped}  fail {failed}  {rate:.1f}/s  {current[:40]}"
    )
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="Index a media folder into SQLite.")
    ap.add_argument("--config", default="config.json", help="path to config.json")
    ap.add_argument("--media", default=None, help="override media folder")
    ap.add_argument("--db", default=None, help="override db path")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.media:
        cfg["media_folder"] = args.media
    if args.db:
        cfg["db_path"] = args.db

    if not client_healthy(cfg):
        sys.exit("llama-server is not running on " + server_url(cfg) +
                 " — start it first (or run ./run.sh).")

    print(f"Indexing {cfg['media_folder']} → {cfg['db_path']}")
    summary = run_indexing(cfg, on_progress=_print_progress)
    print()
    print(
        f"✓ done: {summary['encoded']} encoded, {summary['skipped']} skipped, "
        f"{summary['failed']} failed in {summary['seconds']:.1f}s "
        f"({summary['db_count']} total in DB)"
    )


def client_healthy(cfg) -> bool:
    emb = cfg["embedding"]
    client = EmbeddingClient(
        base_url=server_url(cfg),
        dim=emb["dim"],
        query_prefix=emb["query_prefix"],
        query_prefix_text=emb["query_prefix_text"],
    )
    return client.healthy()


if __name__ == "__main__":
    main()
