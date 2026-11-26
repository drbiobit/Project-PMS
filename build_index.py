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
    estimate_tokens,
    load_config,
    make_client,
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


def _embed_one(client, kind: str, path: str):
    return {
        "image": client.embed_image,
        "video": client.embed_video,
        "audio": client.embed_audio,
    }[kind](path)


def _make_batches(items, batch_size: int, max_tokens: int, cfg: dict):
    """Group items into batches bounded by file count AND estimated token budget.

    `items` is a list of (relpath, abspath, kind, mtime, (w, h, d)). A new
    batch starts when adding the next file would exceed `batch_size` files or
    push the running token estimate past `max_tokens` (so a batch of large
    video/audio can't overflow the server's context window).
    """
    batches = []
    current = []
    current_tokens = 0
    for item in items:
        kind = item[2]
        duration = item[4][2]
        est = estimate_tokens(kind, {"duration": duration}, cfg)
        if current and (len(current) >= batch_size
                        or current_tokens + est > max_tokens):
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(item)
        current_tokens += est
    if current:
        batches.append(current)
    return batches


def run_indexing(cfg: dict, on_progress: Optional[ProgressFn] = None) -> dict:
    """Index the configured media folder. Returns a summary dict.

    Embedding is BATCHED: groups of up to `batch_size` files (also bounded by
    an estimated token budget) are sent to the server in a single request. If
    a batch fails, the group is retried one file at a time so a single bad
    file can't poison the whole batch.
    """
    media_folder = os.path.abspath(cfg["media_folder"])
    db_path = os.path.abspath(cfg["db_path"])
    emb = cfg["embedding"]
    batch_size = int(emb.get("batch_size", 8))
    max_batch_tokens = int(emb.get("max_batch_tokens", 7000))
    client = make_client(cfg)

    files = list(iter_media(media_folder))
    total = len(files)
    done = skipped = failed = 0
    started = time.time()

    db_count = 0
    with MediaDB(db_path) as db:
        # Pass 1: collect the files that actually need embedding (with metadata).
        to_embed = []  # (relpath, abspath, kind, mtime, (w, h, d))
        for relpath, abspath, kind in files:
            mtime = os.path.getmtime(abspath)
            current = os.path.basename(abspath)
            if db.is_indexed(relpath, mtime):
                skipped += 1
                if on_progress:
                    on_progress(done, total, skipped, failed, current, "skip", started)
                continue
            width, height, duration = get_metadata(kind, abspath)
            to_embed.append((relpath, abspath, kind, mtime,
                             (width, height, duration)))

        # Pass 2: embed in batches, upserting as we go.
        for batch in _make_batches(to_embed, batch_size, max_batch_tokens, cfg):
            try:
                vecs = client.embed_batch([(k, p) for _, p, k, _, _ in batch])
                ok = True
            except Exception:
                ok = False
            if ok:
                for (relpath, abspath, kind, mtime, (w, h, d)), vec in zip(batch, vecs):
                    db.upsert(
                        path=relpath,
                        filename=os.path.basename(abspath),
                        kind=kind,
                        width=w,
                        height=h,
                        duration=d,
                        size_bytes=os.path.getsize(abspath),
                        mtime=mtime,
                        embedding=vec,
                    )
                    done += 1
                    if on_progress:
                        on_progress(done, total, skipped, failed,
                                     os.path.basename(abspath), kind, started)
            else:
                # Batch failed -> retry one at a time to isolate the bad file(s).
                for (relpath, abspath, kind, mtime, (w, h, d)) in batch:
                    current = os.path.basename(abspath)
                    try:
                        vec = _embed_one(client, kind, abspath)
                        db.upsert(
                            path=relpath,
                            filename=os.path.basename(abspath),
                            kind=kind,
                            width=w,
                            height=h,
                            duration=d,
                            size_bytes=os.path.getsize(abspath),
                            mtime=mtime,
                            embedding=vec,
                        )
                        done += 1
                    except Exception as e:
                        failed += 1
                        current = f"{current}  ({type(e).__name__}: {e})"
                    if on_progress:
                        on_progress(done, total, skipped, failed, current, kind, started)

        db_count = db.count()

    return {
        "total": total,
        "encoded": done,
        "skipped": skipped,
        "failed": failed,
        "seconds": time.time() - started,
        "db_count": db_count,
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
    return make_client(cfg).healthy()


if __name__ == "__main__":
    main()
