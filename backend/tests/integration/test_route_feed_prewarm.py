"""LAT-P001 — route-level proof that the pre-warm warms the key production reads.

The pre-warm's failure modes are all silent. Two of them can only be caught by
driving the REAL route:

1. **Key drift.** The warmer publishes under a key derived inside `get_feed`,
   after the server-side Discover defaulting has rewritten `event_pct`/`mode`.
   If the warmed key differed from the key a real request reads, the warmer would
   run, log success, and warm nothing. Here a real HTTP request records the key
   it reads and the warmer's resolved key is asserted equal to it.

2. **Warming without rebuilding.** `get_feed` short-circuits on the 300s `:stale`
   mirror. A warmer that went through that read would re-publish the same ageing
   payload forever and never refresh it — indistinguishable from working. Here
   the same stale entry that makes a real request return `stale_hit` must NOT
   satisfy the warmer.
"""

import json
from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import MagicMock

from app.utils import request_cache as _rc
from app.utils.feed_cache import FEED_PREWARM_KEY_SCOPE_KEY, feed_response_cache_key

pcp = import_module("app.tasks.precompute_category_pages")


_STALE_PAYLOAD = {
    "items": [{"type": "futures", "data": {"id": 99}}],
    "total": 1,
    "limit": 20,
    "offset": 0,
    "has_more": False,
}


class _RecordingRedis:
    """Records every key read; optionally answers the `:stale` mirror."""

    def __init__(self, *, stale_payload=None):
        self.reads: list[str] = []
        self._stale = json.dumps(stale_payload) if stale_payload is not None else None

    async def get(self, key):
        self.reads.append(key)
        if self._stale is not None and key.endswith(":stale"):
            return self._stale
        return None

    async def setex(self, *a, **k):
        return True

    @property
    def primary_reads(self) -> list[str]:
        return [k for k in self.reads if not k.endswith(":stale")]


async def _async(value):
    return value


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


def _install_redis(monkeypatch, fake):
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))


def _install_task_session(monkeypatch, db):
    @asynccontextmanager
    async def fake_session():
        yield db

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)


async def _run_warm_capturing_request(monkeypatch, shape, rc=None):
    """Run the warmer, returning (outcome, the Request it built)."""
    held = {}
    real_builder = pcp._build_prewarm_request

    def capture(scope_key):
        request = real_builder(scope_key)
        held["request"] = request
        return request

    monkeypatch.setattr(pcp, "_build_prewarm_request", capture)
    outcome = await pcp._prewarm_feed_shape(dict(shape), rc or MagicMock())
    return outcome, held["request"]


async def test_warmed_key_equals_the_key_a_real_discover_request_reads(
    client, mock_db, monkeypatch
):
    _reset_rc()
    fake = _RecordingRedis()
    _install_redis(monkeypatch, fake)

    # 1. The real first-paint request the Discover page issues, anonymously.
    resp = await client.get("/api/feed?limit=20&offset=0&event_pct=0.15")
    assert resp.status_code == 200
    read_key = fake.primary_reads[0]

    # 2. The warmer, on the shape it warms for Discover.
    _reset_rc()
    _install_task_session(monkeypatch, mock_db)
    shape = next(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover")
    _, request = await _run_warm_capturing_request(monkeypatch, shape)

    assert request.scope[FEED_PREWARM_KEY_SCOPE_KEY] == read_key, (
        "the warmer would publish under a key no Discover request reads"
    )
    # And it is the anonymous key — one warmed entry serves every first visitor.
    assert read_key == feed_response_cache_key(limit=20, offset=0, event_pct=0.15)


async def test_warmed_key_equals_the_key_a_real_sports_request_reads(
    client, mock_db, monkeypatch
):
    _reset_rc()
    fake = _RecordingRedis()
    _install_redis(monkeypatch, fake)

    resp = await client.get("/api/feed?limit=20&offset=0&mode=sports")
    assert resp.status_code == 200
    read_key = fake.primary_reads[0]

    _reset_rc()
    _install_task_session(monkeypatch, mock_db)
    shape = next(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "sports")
    _, request = await _run_warm_capturing_request(monkeypatch, shape)

    assert request.scope[FEED_PREWARM_KEY_SCOPE_KEY] == read_key, (
        "the warmer would publish under a key no Sports request reads"
    )
    assert read_key == feed_response_cache_key(limit=20, offset=0, mode="sports")


async def test_a_stale_entry_serves_requests_but_does_not_satisfy_the_warmer(
    client, mock_db, monkeypatch
):
    """The warmer must rebuild THROUGH a stale mirror, not be short-circuited by it.

    Same Redis state for both callers: a real request is served `stale_hit` from
    the mirror (fast — which is exactly what we want live traffic to get while a
    rebuild runs underneath), while the warmer ignores it and builds.
    """
    _reset_rc()
    fake = _RecordingRedis(stale_payload=_STALE_PAYLOAD)
    _install_redis(monkeypatch, fake)

    resp = await client.get("/api/feed?limit=20&offset=0&event_pct=0.15")
    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "stale_hit"
    assert resp.json()["total"] == 1, "sanity: the request really was served the mirror"

    # The warmer sees the SAME stale mirror.
    _reset_rc()
    _install_task_session(monkeypatch, mock_db)
    shape = next(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover")
    rc = MagicMock()
    outcome, _ = await _run_warm_capturing_request(monkeypatch, shape, rc=rc)

    # It built (against the empty mock DB) instead of adopting the stale payload.
    # Had it short-circuited it would have "succeeded" with the mirror's 1 item —
    # re-publishing an ageing payload and never refreshing it.
    assert outcome["outcome"] != "ok", (
        "warmer returned the stale mirror instead of rebuilding — the cache would "
        "never refresh"
    )
    assert outcome["outcome"] == "empty"
    rc.setex.assert_not_called()


async def test_prewarm_marker_cannot_be_set_over_http(client, monkeypatch):
    """A client that could force rebuilds would have a free DoS on the feed."""
    _reset_rc()
    fake = _RecordingRedis(stale_payload=_STALE_PAYLOAD)
    _install_redis(monkeypatch, fake)

    for attempt in (
        "/api/feed?limit=20&bainluck_feed_prewarm=true",
        "/api/feed?limit=20&_prewarm_rebuild=1",
    ):
        resp = await client.get(attempt)
        assert resp.status_code == 200
        assert resp.headers["x-feed-cache"] == "stale_hit", (
            f"{attempt} bypassed the cache read — the marker is client-reachable"
        )

    # Header form must be equally inert.
    resp = await client.get(
        "/api/feed?limit=20", headers={"bainluck-feed-prewarm": "true"}
    )
    assert resp.headers["x-feed-cache"] == "stale_hit"
