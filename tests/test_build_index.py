"""Tests for build_index.py — file discovery, modality classification, batching."""

from __future__ import annotations

import copy
import os

import pytest

import build_index
from build_index import _make_batches, iter_media, kind_for, run_indexing
from common import DEFAULT_CONFIG, MediaDB


# --------------------------------------------------------------------------- #
# kind_for
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("photo.jpg", "image"),
        ("photo.JPEG", "image"),
        ("photo.png", "image"),
        ("photo.webp", "image"),
        ("clip.mp4", "video"),
        ("clip.MOV", "video"),
        ("clip.mkv", "video"),
        ("clip.webm", "video"),
        ("voice.wav", "audio"),
        ("voice.mp3", "audio"),
        ("voice.flac", "audio"),
        ("notes.txt", None),
        ("archive.zip", None),
        ("noext", None),
    ],
)
def test_kind_for(name, kind):
    assert kind_for(name) == kind


# --------------------------------------------------------------------------- #
# iter_media
# --------------------------------------------------------------------------- #


def test_iter_media_yields_supported_files_sorted(tmp_path):
    # build a small nested media folder
    (tmp_path / "sub").mkdir()
    for name in ("b.jpg", "a.mp4", "c.txt", "d.wav"):
        (tmp_path / name).write_text("x")
    (tmp_path / "sub" / "e.png").write_text("x")

    found = list(iter_media(str(tmp_path)))
    relpaths = [rel for rel, _abs, _kind in found]
    # only supported extensions appear
    assert "c.txt" not in relpaths
    assert "b.jpg" in relpaths
    assert "a.mp4" in relpaths
    assert "d.wav" in relpaths
    assert os.path.join("sub", "e.png") in relpaths
    # deterministic: sorted per directory
    assert relpaths == sorted(relpaths)


def test_iter_media_empty_folder(tmp_path):
    assert list(iter_media(str(tmp_path))) == []


def test_iter_media_abs_paths_resolve(tmp_path):
    found = list(iter_media(str(tmp_path)))
    (tmp_path / "x.jpg").write_text("x")
    found = list(iter_media(str(tmp_path)))
    rel, abspath, kind = found[0]
    assert os.path.isabs(abspath)
    assert kind == "image"
    assert abspath == os.path.join(str(tmp_path), rel)


# --------------------------------------------------------------------------- #
# Batching
# --------------------------------------------------------------------------- #


class FakeClient:
    """Stand-in for EmbeddingClient: records batch vs single-file calls."""

    def __init__(self, fail_batch=False):
        self.fail_batch = fail_batch
        self.batch_calls = 0
        self.single_calls = 0

    def embed_batch(self, items):
        self.batch_calls += 1
        if self.fail_batch:
            raise RuntimeError("batch failed")
        return [[1.0, 0.0, 0.0, 0.0] for _ in items]

    def embed_image(self, path):
        self.single_calls += 1
        return [1.0, 0.0, 0.0, 0.0]

    def embed_video(self, path):
        self.single_calls += 1
        return [1.0, 0.0, 0.0, 0.0]

    def embed_audio(self, path):
        self.single_calls += 1
        return [1.0, 0.0, 0.0, 0.0]


def _image_items(n):
    return [(f"{i}.jpg", f"/x/{i}.jpg", "image", 1.0, (None, None, None))
            for i in range(n)]


def test_make_batches_count_limit():
    # 10 items, batch_size 4, generous token budget -> 4, 4, 2
    batches = _make_batches(_image_items(10), 4, 10_000, DEFAULT_CONFIG)
    assert [len(b) for b in batches] == [4, 4, 2]


def test_make_batches_token_limit():
    # each image costs 280 tokens; budget 1000 -> 3 per batch (4th would be 1120)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["server"]["image_tokens"] = 280
    batches = _make_batches(_image_items(7), 100, 1000, cfg)
    assert [len(b) for b in batches] == [3, 3, 1]


def test_run_indexing_batch_success(tmp_path, monkeypatch):
    media = tmp_path / "media"; media.mkdir()
    for i in range(5):
        (media / f"{i}.jpg").write_bytes(b"x")
    db = tmp_path / "media.db"
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["media_folder"] = str(media)
    cfg["db_path"] = str(db)
    cfg["embedding"]["batch_size"] = 10  # all 5 fit in one batch
    fake = FakeClient(fail_batch=False)
    monkeypatch.setattr(build_index, "make_client", lambda cfg: fake)
    summary = run_indexing(cfg)
    assert summary["encoded"] == 5
    assert summary["failed"] == 0
    assert fake.batch_calls == 1  # a single batched request
    with MediaDB(str(db)) as d:
        assert d.count() == 5


def test_run_indexing_batch_fallback_isolates_failures(tmp_path, monkeypatch):
    media = tmp_path / "media"; media.mkdir()
    for i in range(5):
        (media / f"{i}.jpg").write_bytes(b"x")
    db = tmp_path / "media.db"
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["media_folder"] = str(media)
    cfg["db_path"] = str(db)
    cfg["embedding"]["batch_size"] = 10
    fake = FakeClient(fail_batch=True)  # the batch blows up...
    monkeypatch.setattr(build_index, "make_client", lambda cfg: fake)
    summary = run_indexing(cfg)
    # ...so we retry one file at a time and still embed all 5
    assert summary["encoded"] == 5
    assert summary["failed"] == 0
    assert fake.batch_calls == 1
    assert fake.single_calls == 5
