"""Tests for app.py — Basic-Auth guard and route behavior.

Uses the Flask test client. The module under test loads the repo's
config.json (which defines the auth credentials), so tests authenticate
with those same credentials.
"""

from __future__ import annotations

import base64

import pytest

import app as app_module


def _auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_health_is_exempt_from_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_root_requires_auth(client):
    r = client.get("/")
    assert r.status_code == 401
    assert "Basic" in r.headers.get("WWW-Authenticate", "")


def test_root_with_correct_auth(client):
    r = client.get("/", headers=_auth_header("admin", "pms"))
    assert r.status_code == 200


def test_root_with_wrong_password(client):
    r = client.get("/", headers=_auth_header("admin", "wrong"))
    assert r.status_code == 401


def test_root_with_wrong_user(client):
    r = client.get("/", headers=_auth_header("root", "pms"))
    assert r.status_code == 401


def test_status_requires_auth(client):
    r = client.get("/status")
    assert r.status_code == 401
    r = client.get("/status", headers=_auth_header("admin", "pms"))
    assert r.status_code == 200
    body = r.get_json()
    assert "server" in body and "index" in body and "media_count" in body


def test_search_requires_auth(client):
    r = client.post("/search", data={"query": "a red car"})
    assert r.status_code == 401


def test_www_authenticate_header_present(client):
    r = client.get("/")
    assert r.headers.get("WWW-Authenticate") == 'Basic realm="PMS"'
