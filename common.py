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
        "model": "models/embeddinggemma/embeddinggemma-2-UD-Q5_K_XL.gguf",
        "mmproj": "models/embeddinggemma/mmproj-Q8_0.gguf",
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
        # Batching: max files per request, and a token budget so a batch of
        # large media can't overflow the server's context window.
        "batch_size": 8,
        "max_batch_tokens": 7000,
        # OpenAI-compatible endpoint. `base_url` (when set) points the app at
        # an EXTERNAL locally-hosted endpoint (Ollama, vLLM, a separate
        # llama-server, a gateway) instead of the bundled one; `api_key` is
        # sent as a Bearer token; `model_name` is the model id to request.
        "api_key": "",
        "model_name": "embeddinggemma-2",
        "base_url": "",
    },
    "web": {
        "host": "127.0.0.1",
        "port": 9090,
        "top_n": 10,
        "tile_size": 240,
    },
    "auth": {
        "username": "admin",
        "password": "pms",
    },
}

# File extensions we know how to embed, grouped by modality.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".mkv", ".webm"}
# llama.cpp embeddings accept wav/mp3/flac; other formats need conversion first
AUDIO_EXTS = {".wav", ".mp3", ".flac"}


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


def make_client(cfg: dict) -> "EmbeddingClient":
    """Build an EmbeddingClient from config.

    Uses `embedding.base_url` when set (an external OpenAI-compatible
    endpoint such as Ollama/vLLM/a separate llama-server), otherwise the
    bundled server's URL. Sends `embedding.api_key` as a Bearer token and
    requests `embedding.model_name`.
    """
    emb = cfg["embedding"]
    base_url = (emb.get("base_url") or server_url(cfg)).rstrip("/")
    # The client appends "/v1/embeddings" to base_url. OpenAI-compatible
    # endpoints are usually referenced as ".../v1", so strip a trailing /v1
    # to avoid a doubled path segment.
    if base_url.endswith("/v1"):
        base_url = base_url[: -len("/v1")]
    return EmbeddingClient(
        base_url=base_url,
        dim=emb["dim"],
        model_name=emb.get("model_name", "embeddinggemma-2"),
        query_prefix=emb["query_prefix"],
        query_prefix_text=emb["query_prefix_text"],
        api_key=emb.get("api_key", ""),
    )


def verify_credentials(cfg: dict, username: str, password: str) -> bool:
    """Check Basic-Auth credentials against the configured user/password.

    Constant-time comparison to avoid a trivial timing side-channel.
    """
    import hmac

    auth = cfg.get("auth", {})
    expected_user = auth.get("username", "")
    expected_pass = auth.get("password", "")
    return (
        hmac.compare_digest(username, expected_user)
        and hmac.compare_digest(password, expected_pass)
    )


# --------------------------------------------------------------------------- #
# Embedding client
# --------------------------------------------------------------------------- #


class EmbeddingError(RuntimeError):
    pass


# Supported media types, mapped from extension.
IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
VIDEO_MIME = {
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}
AUDIO_FORMAT = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".flac": "flac",
}


def _ext_of(path):
    return os.path.splitext(path)[1].lower()


@dataclass
class EmbeddingClient:
    """Thin HTTP client for the running llama-server /v1/embeddings endpoint.

    Verified working format (llama.cpp >= build ~11457, EmbeddingGemma 2):
      text  -> plain string in the input array
      image -> {"content":[{"type":"image_url","image_url":{"url":"data:<mime>;base64,<b64>"}}]}
      video -> {"content":[{"type":"input_video","input_video":{"url":"data:<mime>;base64,<b64>"}}]}
      audio -> {"content":[{"type":"input_audio","input_audio":{"data":"<b64>","format":"wav|mp3|flac"}}]}

    Large media payloads are sent directly over HTTP via `requests` (no shell).
    Vectors are truncated to the configured MRL dimension and re-normalized so
    index-time and search-time vectors are always comparable.
    """

    base_url: str
    dim: int
    model_name: str = "embeddinggemma-2"
    query_prefix: bool = True
    query_prefix_text: str = "task: search result | query: {query}"
    timeout: float = 300.0
    api_key: str = ""
    _model_cache: str = ""

    def _headers(self) -> dict:
        """Request headers. Adds an Authorization bearer token when an API key
        is configured, so the client works against any OpenAI-compatible
        endpoint (llama-server, Ollama, vLLM, a local gateway, ...)."""
        h: dict = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _model(self) -> str:
        # Cache the model id reported by the server so we send the right name.
        if self._model_cache:
            return self._model_cache
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=10,
                             headers=self._headers())
            data = r.json()
            models = data.get("data") or data  # OpenAI shape or bare list
            if isinstance(models, list) and models:
                self._model_cache = models[0].get("id") or self.model_name
                return self._model_cache
        except Exception:
            pass
        return self.model_name

    def _post(self, payload: dict) -> list[float]:
        resp = requests.post(f"{self.base_url}/v1/embeddings", json=payload,
                              timeout=self.timeout, headers=self._headers())
        if resp.status_code != 200:
            raise EmbeddingError(f"server returned {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            vec = data["data"][0]["embedding"]
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
        payload = {"model": self._model(), "input": [content]}
        return self._post(payload)

    def embed_image(self, path: str) -> list[float]:
        return self.embed_batch([("image", path)])[0]

    def embed_video(self, path: str) -> list[float]:
        return self.embed_batch([("video", path)])[0]

    def embed_audio(self, path: str) -> list[float]:
        return self.embed_batch([("audio", path)])[0]

    def embed_batch(self, items: list[tuple[str, str]]) -> list[list[float]]:
        """Embed a list of (kind, path) items in ONE request.

        The OpenAI-compatible /v1/embeddings endpoint accepts a multi-item
        `input` array and returns one embedding per item, in order. Batching
        cuts N HTTP round-trips to N/batch_size and lets the engine process the
        group in a single forward pass.

        Returns a list of truncated+normalized vectors, one per item.
        """
        if not items:
            return []
        content = [{"content": [self._content_part(kind, path)]}
                   for kind, path in items]
        payload = {"model": self._model(), "input": content}
        resp = requests.post(f"{self.base_url}/v1/embeddings", json=payload,
                             timeout=self.timeout, headers=self._headers())
        if resp.status_code != 200:
            raise EmbeddingError(
                f"server returned {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            embeddings = [d["embedding"] for d in data["data"]]
        except (KeyError, TypeError) as e:
            raise EmbeddingError(
                f"unexpected response shape: {data!r}"[:300]) from e
        if len(embeddings) != len(items):
            raise EmbeddingError(
                f"expected {len(items)} embeddings, got {len(embeddings)}")
        return [self._truncate(v) for v in embeddings]

    def _content_part(self, kind: str, path: str) -> dict:
        """Build the typed content part for one media item."""
        ext = _ext_of(path)
        if kind == "image":
            mime = IMAGE_MIME.get(ext)
            if mime is None:
                raise EmbeddingError(f"unsupported image type: {ext}")
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"}}
        if kind == "video":
            mime = VIDEO_MIME.get(ext)
            if mime is None:
                raise EmbeddingError(f"unsupported video type: {ext}")
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"type": "input_video",
                    "input_video": {"url": f"data:{mime};base64,{b64}"}}
        if kind == "audio":
            fmt = AUDIO_FORMAT.get(ext)
            if fmt is None:
                raise EmbeddingError(
                    f"unsupported audio type: {ext} (wav/mp3/flac supported)")
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"type": "input_audio",
                    "input_audio": {"data": b64, "format": fmt}}
        raise EmbeddingError(f"unknown media kind: {kind}")

    def healthy(self) -> bool:
        """True when the server's /health endpoint reports ok."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False


# --------------------------------------------------------------------------- #
# Token estimation (for batch sizing)
# --------------------------------------------------------------------------- #

# Approximate token cost per unit, from the EmbeddingGemma-2 model card:
#   image -> image_tokens (a fixed budget per image)
#   video -> ~140 tokens per sampled frame
#   audio -> ~25 tokens per second
VIDEO_TOKENS_PER_FRAME = 140
AUDIO_TOKENS_PER_SECOND = 25


def estimate_tokens(kind: str, metadata, cfg: dict) -> int:
    """Rough token cost of one media item, used to size a batch so it stays
    inside the server's context window (see `max_batch_tokens`)."""
    server = cfg["server"]
    duration = (metadata or {}).get("duration") or 0.0
    if kind == "image":
        return int(server.get("image_tokens", 280))
    if kind == "video":
        return int(duration * server.get("video_fps", 1.0)
                   * VIDEO_TOKENS_PER_FRAME) + 1
    if kind == "audio":
        return int(duration * AUDIO_TOKENS_PER_SECOND) + 1
    return 0


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
