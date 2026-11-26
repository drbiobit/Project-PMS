"""Tests for app.py — session-based auth and route behavior.

Uses the Flask test client. The module under test loads the repo's
config.json (which defines the auth credentials), so tests log in with
those same credentials (admin / pms).
"""

from __future__ import annotations

import pytest

import app as app_module


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def logged_in(client):
    """The same test client, with a valid login session established."""
    with client.session_transaction() as sess:
        sess["authed"] = True
        sess["user"] = "admin"
    return client


def test_health_is_exempt_from_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_login_page_is_exempt(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Sign in" in r.data


def test_root_redirects_to_login_when_unauthenticated(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_root_with_session(client, logged_in):
    r = logged_in.get("/")
    assert r.status_code == 200


def test_login_post_valid_credentials(client):
    r = client.post("/login", data={"username": "admin", "password": "pms"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    with client.session_transaction() as sess:
        assert sess.get("authed") is True


def test_login_post_wrong_password(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 200
    assert b"Invalid username or password." in r.data


def test_login_post_wrong_user(client):
    r = client.post("/login", data={"username": "root", "password": "pms"})
    assert r.status_code == 200
    assert b"Invalid username or password." in r.data


def test_logout_clears_session(logged_in):
    r = logged_in.get("/logout")
    assert r.status_code == 302
    assert r.headers["Location"] == "/login"
    with logged_in.session_transaction() as sess:
        assert "authed" not in sess


def test_status_requires_auth(client):
    r = client.get("/status")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_status_with_session(logged_in):
    r = logged_in.get("/status")
    assert r.status_code == 200
    body = r.get_json()
    assert "server" in body and "index" in body and "media_count" in body


def test_search_requires_auth(client):
    r = client.post("/search", data={"query": "a red car"})
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_login_redirects_home_when_already_authed(logged_in):
    r = logged_in.get("/login")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
