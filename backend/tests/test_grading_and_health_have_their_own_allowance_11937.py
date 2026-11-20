"""#11937: a grader's save and the health probe never share a reader's allowance.

Fable, 8:04 AM PT Wed Nov 11: Alex was stopped at card 27 of the Nov 11 slate
with "Not saved (429): Rate limit exceeded: 60/minute". The /grade page signs
in with the admin's Firebase ID token, which the limiter can't verify locally,
so every grade save keyed by client address into the anonymous 60/minute
bucket, the same bucket every reader page and every lane check from that
address spends. The router saw 67 requests in the 30 s before the first 429;
Alex was grading one card at a time. `/api/health` sat in the same bucket and
drew 429s too, and Speed's restart guard reads it every minute.

What must hold:
* a grading request (``/api/admin/ranking/...`` with a bearer) counts in its own
  bucket, so an address whose reader bucket is spent can still save a grade;
* that bucket is bounded too, and a request with no bearer gets no such bucket;
* ``/api/health`` counts in its own bucket, so reader traffic can't 429 it;
* the real admin token still lands in the admin bucket, as before.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.utils.rate_limit as rl
from app.utils.rate_limit import RateLimitMiddleware

ADDRESS = {"x-forwarded-for": "203.0.113.7"}
# A Firebase ID token: well-formed, but not one the limiter can verify locally.
FIREBASE = {"authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJ1aWQiOiJhbGV4In0.c2ln", **ADDRESS}


@pytest.fixture
def counted(monkeypatch):
    """The production (async Redis) path, with one counter per bucket key."""
    counts: dict[str, int] = {}

    async def hit(_cli, key, _now):
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rl, "_get_async_rl_redis", lambda: object())
    monkeypatch.setattr(rl, "_redis_fixed_window_hit", hit)
    monkeypatch.setattr(rl, "_trusted_ips", lambda: frozenset())
    monkeypatch.setattr(rl, "_ANON_MAX", 3)
    monkeypatch.setattr(rl, "_resolve_trusted_uid", lambda token: None)

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/feed")
    async def feed():
        return {"ok": True}

    @app.post("/api/admin/ranking/grades")
    async def grade():
        return {"status": "ok"}

    @app.get("/api/admin/ranking/grade-deck")
    async def deck():
        return {"items": []}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return TestClient(app), counts


def _spend_the_reader_bucket(client):
    for _ in range(3):
        assert client.get("/api/feed", headers=ADDRESS).status_code == 200
    assert client.get("/api/feed", headers=ADDRESS).status_code == 429


def test_a_grade_saves_after_the_address_spent_its_reader_allowance(counted):
    client, counts = counted
    _spend_the_reader_bucket(client)
    assert client.post("/api/admin/ranking/grades", headers=FIREBASE).status_code == 200
    assert client.get("/api/admin/ranking/grade-deck", headers=FIREBASE).status_code == 200
    assert counts["grading:203.0.113.7"] == 2
    # Grading never spent the reader bucket either.
    assert counts["203.0.113.7"] == 4


def test_the_grading_bucket_is_bounded(counted, monkeypatch):
    client, _ = counted
    monkeypatch.setattr(rl, "_GRADING_MAX", 2)
    codes = [client.post("/api/admin/ranking/grades", headers=FIREBASE).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_no_bearer_means_no_grading_bucket(counted):
    client, counts = counted
    _spend_the_reader_bucket(client)
    assert client.post("/api/admin/ranking/grades", headers=ADDRESS).status_code == 429
    assert not any(k.startswith("grading:") for k in counts)


def test_other_admin_paths_are_unchanged(counted):
    client, counts = counted
    _spend_the_reader_bucket(client)
    # Not the grading path: a Firebase token there keys by address, as before.
    assert client.get("/api/admin/status", headers=FIREBASE).status_code == 429


def test_reader_traffic_never_rate_limits_the_health_probe(counted):
    client, counts = counted
    _spend_the_reader_bucket(client)
    assert client.get("/api/health", headers=ADDRESS).status_code == 200
    assert counts["health:203.0.113.7"] == 1


def test_the_health_bucket_is_bounded(counted, monkeypatch):
    client, _ = counted
    monkeypatch.setattr(rl, "_HEALTH_MAX", 2)
    codes = [client.get("/api/health", headers=ADDRESS).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_the_real_admin_token_keeps_the_admin_bucket(counted, monkeypatch):
    client, counts = counted
    monkeypatch.setattr(rl, "_admin_bucket_key", lambda token: "admin:hash" if token == "real" else None)
    headers = {"authorization": "Bearer real", **ADDRESS}
    assert client.post("/api/admin/ranking/grades", headers=headers).status_code == 200
    assert counts == {"admin:hash": 1}
