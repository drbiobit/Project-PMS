"""Shared core for the search-media system.

Everything the indexer, CLI search, web app, and TUI need lives here so the
embedding/DB logic has exactly one implementation:

  * config loading (config.json with sane defaults)
  * EmbeddingClient — HTTP calls to the running llama-server for
    text / image / video / audio, with MRL truncation + re-normalization
  * MediaDB — SQLite storage for embeddings (incremental by path + mtime)
  * cosine_rank — numpy ranking of stored vectors against a query vector

The model is loaded ONCE by llama-server (C++/Metal). Python never loads the
model; it only sends HTTP requests to the server.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
import base64
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import requests

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    "media_folder": "./media",
    "db_path": "media.db",
    "server": {
        "host": "127.0.0.1",
        "port": 8080,
        "binary": "llama.cpp/llama-b12774/llama-server",
        "model": "models/embeddinggemma/embeddinggemma-2-BF16.gguf",
        "mmproj": "models/embeddinggemma/mmproj-BF16.gguf",
        "image_tokens": 280,
        "video_fps": 1.0,
        "pooling": "mean",
        "normalize": 2,
        "ctx_size": 8192,
        "ubatch": 1024,
    },
    "embedding": {
        "dim": 768,
        "query_prefix": True,
        "query_prefix_text": "task: search result | query: {query}",
    },
    "web": {
        "host": "127.0.0.1",
        "port": 5000,
        "top_n": 10,
    },
}

# File extensions we know how to embed, grouped by modality.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mkv", ".webm"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base` (returns a new dict)."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = "config.json") -> dict:
    """Load config.json and merge over the defaults so missing keys are safe."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = _deep_merge(cfg, user_cfg)
    return cfg


def save_config(path: str, cfg: dict) -> None:
    """Write the config back to disk (used by the TUI after the user edits it)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def server_url(cfg: dict) -> str:
    s = cfg["server"]
    return f"http://{s['host']}:{s['port']}"


# --------------------------------------------------------------------------- #
# Embedding client
# --------------------------------------------------------------------------- #


class EmbeddingError(RuntimeError):
    pass


@dataclass
class EmbeddingClient:
    """Thin HTTP client for the running llama-server /embedding endpoint.

    Large media payloads are sent directly over HTTP via `requests` (no shell,
    so no 'argument list too long' problem). Vectors are truncated to the
    configured MRL dimension and re-normalized so index-time and search-time
    vectors are always comparable.
    """

    base_url: str
    dim: int
    query_prefix: bool = True
    query_prefix_text: str = "task: search result | query: {query}"
    timeout: float = 300.0

    def _post(self, payload: dict) -> list[float]:
        resp = requests.post(f"{self.base_url}/embedding", json=payload,
                              timeout=self.timeout)
        if resp.status_code != 200:
            raise EmbeddingError(f"server returned {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            vec = data[0]["embedding"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise EmbeddingError(f"unexpected response shape: {data!r}"[:300]) from e
        return self._truncate(vec)

    def _truncate(self, vec: list[float]) -> list[float]:
        """Truncate to the configured MRL dim and re-normalize to unit length."""
        arr = np.asarray(vec[: self.dim], dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()

    # -- modalities -------------------------------------------------------- #

    def embed_text(self, text: str) -> list[float]:
        """Embed a text query. Applies the task prefix when enabled."""
        content = (
            self.query_prefix_text.format(query=text)
            if self.query_prefix
            else text
        )
        return self._post({"content": content})

    def embed_image(self, path: str) -> list[float]:
        return self._embed_media(path, "image_data", "[img-1]")

    def embed_video(self, path: str) -> list[float]:
        return self._embed_media(path, "video_data", "[video-1]")

    def embed_audio(self, path: str) -> list[float]:
        return self._embed_media(path, "audio_data", "[audio-1]")

    def _embed_media(self, path: str, key: str, placeholder: str) -> list[float]:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        payload = {"content": placeholder, key: [{"id": 1, "data": b64}]}
        return self._post(payload)

    def healthy(self) -> bool:
        """True when the server's /health endpoint reports ok."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False


# --------------------------------------------------------------------------- #
# SQLite storage
# --------------------------------------------------------------------------- #

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT NOT NULL UNIQUE,
    filename   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    width      INTEGER,
    height     INTEGER,
    duration   REAL,
    size_bytes INTEGER,
    mtime      REAL,
    embedding  BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind);
"""


@dataclass
class MediaDB:
    """SQLite store for embeddings. Incremental: a file is skipped when its
    path and mtime are already present."""

    path: str

    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- incremental ------------------------------------------------------ #

    def is_indexed(self, path: str, mtime: float) -> bool:
        row = self._conn.execute(
            "SELECT mtime FROM media WHERE path = ?", (path,)
        ).fetchone()
        return row is not None and abs(row[0] - mtime) < 1e-6

    def upsert(self, *, path: str, filename: str, kind: str, width: Optional[int],
               height: Optional[int], duration: Optional[float], size_bytes: int,
               mtime: float, embedding: list[float]) -> None:
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        self._conn.execute(
            """
            INSERT INTO media (path, filename, kind, width, height, duration,
                               size_bytes, mtime, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                filename   = excluded.filename,
                kind       = excluded.kind,
                width      = excluded.width,
                height     = excluded.height,
                duration   = excluded.duration,
                size_bytes = excluded.size_bytes,
                mtime      = excluded.mtime,
                embedding  = excluded.embedding
            """,
            (path, filename, kind, width, height, duration, size_bytes, mtime, blob),
        )
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]

    # -- bulk load for search -------------------------------------------- #

    def load_all(self) -> tuple[list[str], list[str], list[str], np.ndarray]:
        """Return (paths, filenames, kinds, matrix) where matrix is (N, dim)."""
        rows = self._conn.execute(
            "SELECT path, filename, kind, embedding FROM media"
        ).fetchall()
        paths, filenames, kinds = [], [], []
        vecs = []
        for path, filename, kind, blob in rows:
            paths.append(path)
            filenames.append(filename)
            kinds.append(kind)
            n = len(blob) // 4
            vecs.append(struct.unpack(f"{n}f", blob))
        matrix = np.asarray(vecs, dtype=np.float32) if vecs else np.zeros((0, 0), dtype=np.float32)
        return paths, filenames, kinds, matrix


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


def cosine_rank(matrix: np.ndarray, query: list[float], top_n: int):
    """Rank stored vectors against a query vector by cosine similarity.

    Both sides are L2-normalized, so cosine similarity == dot product.
    Returns a list of (index, score) for the top_n matches, best first.
    """
    if matrix.size == 0:
        return []
    q = np.asarray(query, dtype=np.float32)
    nq = np.linalg.norm(q)
    if nq > 0:
        q = q / nq
    scores = matrix @ q
    order = np.argsort(scores)[::-1][:top_n]
    return [(int(i), float(scores[i])) for i in order]
