"""Tests for common.py — config, ranking, storage, embedding client, auth."""

from __future__ import annotations

import copy
import os

import numpy as np
import pytest

from common import (
    DEFAULT_CONFIG,
    EmbeddingClient,
    EmbeddingError,
    MediaDB,
    _deep_merge,
    cosine_rank,
    estimate_tokens,
    load_config,
    make_client,
    save_config,
    server_url,
    verify_credentials,
)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


def test_deep_merge_nested():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    override = {"b": {"y": 99, "z": 3}, "c": 4}
    out = _deep_merge(base, override)
    assert out == {"a": 1, "b": {"x": 1, "y": 99, "z": 3}, "c": 4}
    # original base is not mutated
    assert base == {"a": 1, "b": {"x": 1, "y": 2}}


def test_load_config_uses_defaults_when_missing(tmp_path):
    cfg = load_config(str(tmp_path / "does-not-exist.json"))
    assert cfg == DEFAULT_CONFIG


def test_load_config_merges_overrides(tmp_path):
    path = tmp_path / "config.json"
    save_config(str(path), {"web": {"port": 9090}, "custom": True})
    cfg = load_config(str(path))
    # override applied
    assert cfg["web"]["port"] == 9090
    assert cfg["custom"] is True
    # untouched defaults preserved
    assert cfg["embedding"]["dim"] == DEFAULT_CONFIG["embedding"]["dim"]
    assert cfg["web"]["host"] == DEFAULT_CONFIG["web"]["host"]


def test_server_url():
    assert server_url(DEFAULT_CONFIG) == "http://127.0.0.1:8080"


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


def test_cosine_rank_orders_by_similarity():
    # matrix rows: r0=[1,0], r1=[0,1], r2=[0.5,0.5]; query aligned with r0
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
    ranked = cosine_rank(matrix, [1.0, 0.0], top_n=2)
    assert [i for i, _ in ranked] == [0, 2]
    scores = [s for _, s in ranked]
    assert scores[0] > scores[1]
    assert pytest.approx(scores[0], abs=1e-6) == 1.0


def test_cosine_rank_empty_matrix():
    matrix = np.zeros((0, 0), dtype=np.float32)
    assert cosine_rank(matrix, [1.0, 0.0], top_n=5) == []


def test_cosine_rank_is_invariant_to_query_scale():
    # scaling the query must not change the ordering (both sides normalized)
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    a = cosine_rank(matrix, [1.0, 0.0], top_n=2)
    b = cosine_rank(matrix, [100.0, 0.0], top_n=2)
    assert [i for i, _ in a] == [i for i, _ in b]
    assert pytest.approx(a[0][1], abs=1e-6) == pytest.approx(b[0][1], abs=1e-6)


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


def _vec(dim=4):
    return [1.0 / dim] * dim


def test_media_db_upsert_count_and_load(tmp_path):
    db_path = str(tmp_path / "media.db")
    with MediaDB(db_path) as db:
        db.upsert(
            path="a.jpg", filename="a.jpg", kind="image",
            width=100, height=50, duration=None, size_bytes=10,
            mtime=1234.5, embedding=_vec(),
        )
        db.upsert(
            path="b.mp4", filename="b.mp4", kind="video",
            width=1920, height=1080, duration=12.0, size_bytes=999,
            mtime=4321.0, embedding=_vec(),
        )
        assert db.count() == 2
        paths, filenames, kinds, matrix = db.load_all()
        assert paths == ["a.jpg", "b.mp4"]
        assert kinds == ["image", "video"]
        assert matrix.shape == (2, 4)


def test_media_db_is_indexed_by_path_and_mtime(tmp_path):
    db_path = str(tmp_path / "media.db")
    with MediaDB(db_path) as db:
        db.upsert(
            path="a.jpg", filename="a.jpg", kind="image",
            width=None, height=None, duration=None, size_bytes=1,
            mtime=100.0, embedding=_vec(),
        )
        assert db.is_indexed("a.jpg", 100.0) is True
        # a changed mtime means "not indexed" → will be re-embedded
        assert db.is_indexed("a.jpg", 101.0) is False
        # an unknown path is not indexed
        assert db.is_indexed("zzz.jpg", 100.0) is False


def test_media_db_upsert_updates_existing_path(tmp_path):
    db_path = str(tmp_path / "media.db")
    with MediaDB(db_path) as db:
        db.upsert(
            path="a.jpg", filename="a.jpg", kind="image",
            width=None, height=None, duration=None, size_bytes=1,
            mtime=100.0, embedding=_vec(),
        )
        db.upsert(
            path="a.jpg", filename="a.jpg", kind="image",
            width=None, height=None, duration=None, size_bytes=2,
            mtime=200.0, embedding=_vec(),
        )
        # same path → still one row, updated mtime
        assert db.count() == 1
        assert db.is_indexed("a.jpg", 200.0) is True


# --------------------------------------------------------------------------- #
# Embedding client
# --------------------------------------------------------------------------- #


def test_truncate_normalizes_to_unit_length():
    client = EmbeddingClient(base_url="http://x", dim=3)
    out = client._truncate([3.0, 4.0, 0.0])
    assert pytest.approx(out[0], abs=1e-6) == 0.6
    assert pytest.approx(out[1], abs=1e-6) == 0.8
    assert pytest.approx(out[2], abs=1e-6) == 0.0
    # unit length
    assert pytest.approx(sum(v * v for v in out), abs=1e-6) == 1.0


def test_truncate_respects_dim():
    client = EmbeddingClient(base_url="http://x", dim=2)
    out = client._truncate([1.0, 0.0, 9.9, 9.9])  # extra dims dropped
    assert len(out) == 2


def test_truncate_zero_vector_unchanged():
    client = EmbeddingClient(base_url="http://x", dim=2)
    out = client._truncate([0.0, 0.0])
    assert out == [0.0, 0.0]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


def test_verify_credentials_correct():
    assert verify_credentials(DEFAULT_CONFIG, "admin", "pms") is True


def test_verify_credentials_wrong_password():
    assert verify_credentials(DEFAULT_CONFIG, "admin", "nope") is False


def test_verify_credentials_wrong_user():
    assert verify_credentials(DEFAULT_CONFIG, "root", "pms") is False


def test_verify_credentials_missing_auth_block():
    # a config with no auth block rejects everything
    assert verify_credentials({}, "admin", "pms") is False


# --------------------------------------------------------------------------- #
# Batching + OpenAI-compatible endpoint
# --------------------------------------------------------------------------- #


def _fake_post(calls, n_return):
    """Build a fake requests.post that records the payload and returns
    `n_return` embeddings (to test length-mismatch handling)."""
    def fake_post(url, json=None, timeout=None, headers=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        n = len(json["input"]) if json is not None else 0
        n = min(n, n_return)

        class R:
            status_code = 200

            def json(self):
                return {"data": [{"embedding": [1.0, 0.0, 0.0, 0.0]}
                                 for _ in range(n)]}
        return R()
    return fake_post


def test_embed_batch_builds_multi_item_payload(tmp_path, monkeypatch):
    import common
    a = tmp_path / "a.jpg"; a.write_bytes(b"x")
    b = tmp_path / "b.mp4"; b.write_bytes(b"y")
    calls = {}
    monkeypatch.setattr(common.requests, "post", _fake_post(calls, 10))
    client = EmbeddingClient(base_url="http://x", dim=4, model_name="m")
    client._model_cache = "m"  # skip the /v1/models lookup
    out = client.embed_batch([("image", str(a)), ("video", str(b))])
    assert len(out) == 2
    assert all(len(v) == 4 for v in out)
    # one request carrying both items, typed correctly
    assert len(calls["json"]["input"]) == 2
    assert calls["json"]["input"][0]["content"][0]["type"] == "image_url"
    assert calls["json"]["input"][1]["content"][0]["type"] == "input_video"


def test_embed_batch_raises_on_length_mismatch(tmp_path, monkeypatch):
    import common
    a = tmp_path / "a.jpg"; a.write_bytes(b"x")
    calls = {}
    # server returns only 1 embedding for 2 requested items
    monkeypatch.setattr(common.requests, "post", _fake_post(calls, 1))
    client = EmbeddingClient(base_url="http://x", dim=4, model_name="m")
    client._model_cache = "m"
    with pytest.raises(EmbeddingError):
        client.embed_batch([("image", str(a)), ("image", str(a))])


def test_embed_batch_sends_api_key_header(tmp_path, monkeypatch):
    import common
    a = tmp_path / "a.jpg"; a.write_bytes(b"x")
    calls = {}
    monkeypatch.setattr(common.requests, "post", _fake_post(calls, 10))
    client = EmbeddingClient(base_url="http://x", dim=4, model_name="m",
                             api_key="sekret")
    client._model_cache = "m"
    client.embed_batch([("image", str(a))])
    assert calls["headers"].get("Authorization") == "Bearer sekret"


def test_embed_batch_empty_returns_empty():
    client = EmbeddingClient(base_url="http://x", dim=4, model_name="m")
    assert client.embed_batch([]) == []


def test_estimate_tokens_image():
    cfg = DEFAULT_CONFIG
    assert estimate_tokens("image", None, cfg) == cfg["server"]["image_tokens"]


def test_estimate_tokens_video():
    cfg = DEFAULT_CONFIG
    # 10s * 1fps * 140 tokens/frame + 1
    assert estimate_tokens("video", {"duration": 10.0}, cfg) == int(10.0 * 140) + 1


def test_estimate_tokens_audio():
    cfg = DEFAULT_CONFIG
    # 10s * 25 tokens/second + 1
    assert estimate_tokens("audio", {"duration": 10.0}, cfg) == int(10.0 * 25) + 1


def test_make_client_uses_bundled_server_by_default():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    c = make_client(cfg)
    assert c.base_url == "http://127.0.0.1:8080"
    assert c.api_key == ""
    assert c.model_name == "embeddinggemma-2"


def test_make_client_uses_external_base_url_and_key():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["embedding"]["base_url"] = "http://ollama:11434/v1"
    cfg["embedding"]["api_key"] = "k"
    cfg["embedding"]["model_name"] = "nomic-embed-text"
    c = make_client(cfg)
    # A trailing "/v1" is stripped because the client appends "/v1/embeddings".
    assert c.base_url == "http://ollama:11434"
    assert c.api_key == "k"
    assert c.model_name == "nomic-embed-text"


def test_make_client_base_url_without_v1_is_unchanged():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["embedding"]["base_url"] = "http://host:8080"
    c = make_client(cfg)
    assert c.base_url == "http://host:8080"
