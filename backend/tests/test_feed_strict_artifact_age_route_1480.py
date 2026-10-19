"""#1480 N-strict, at the route: a page built from an aged shared game reading
publishes with that age already spent — on a non-live page as well as a live one.

`test_feed_shared_game_inputs_1480.py` holds the arithmetic. This file drives one
real `GET /api/feed` (the `test_feed_live_cache_ceiling` rig) and reads the TTLs
the build actually wrote to Redis at both of its publish seams: the response
cache (fresh + :stale) and the page base (fresh + :stale).
"""

import time as time_module
from datetime import datetime, timedelta, timezone

import pytest

import app.utils.principal_independent_cache as pic
import app.utils.request_cache as rc
from app.utils.feed_cache import (
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    FEED_RESPONSE_TTL_ANON_SECONDS,
)
from app.utils.feed_cache import payload_contains_live_event
from tests.test_feed_live_cache_ceiling import (
    SHARED_KEY,
    _drive_feed,
    _live_event_row,
    _SeededRedis,
)


def _seed(monkeypatch, *, counted_age_s=None, strict_age_s=None):
    """Seed real origins into the route's own sinks at their binding seams.

    A strict (game-reading) artifact is in BOTH sinks, as `_note_age` records it;
    a `concepts`-style artifact is in the counted sink only.
    """
    import app.routes.feed as feed_mod

    real_bind = feed_mod._bind_shared_reuse_sink
    real_strict = pic.bind_strict_age_sink

    def _bind(reuse, tiers, origins):
        for age in (counted_age_s, strict_age_s):
            if age is not None:
                origins.append(time_module.monotonic() - age)
        return real_bind(reuse, tiers, origins)

    def _bind_strict(sink):
        if strict_age_s is not None:
            sink.append(time_module.monotonic() - strict_age_s)
        return real_strict(sink)

    monkeypatch.setattr(feed_mod, "_bind_shared_reuse_sink", _bind)
    monkeypatch.setattr(pic, "bind_strict_age_sink", _bind_strict)


def _row(status):
    """The CERT-1864 rig's row, which the real scorer accepts."""
    row = _live_event_row(1)
    if status == "scheduled":
        row.status = "scheduled"
        row.commence_time = datetime.now(timezone.utc) + timedelta(hours=2)
        row.home_score = None
        row.away_score = None
        row.period = None
    return row


def _stub_enrichment(monkeypatch):
    """As `_drive_live_feed`: without logos the noise filter drops the game."""
    import app.routes.feed as feed_mod

    async def _enrich(db, items):
        for item in items:
            if item.get("type") == "event":
                item["data"]["home_team_data"] = {"id": 1, "logo_url": "h.png"}
                item["data"]["away_team_data"] = {"id": 2, "logo_url": "a.png"}

    monkeypatch.setattr(feed_mod, "enrich_event_team_data", _enrich)


def _ttls(redis):
    """{key-kind: ttl} for the two publications this build wrote."""
    out = {}
    for key, ttl, _ in redis.setex_calls:
        if key == SHARED_KEY:
            out["fresh"] = ttl
        elif key == f"{SHARED_KEY}:stale":
            out["stale"] = ttl
        elif "page_base" in key or "pagebase" in key:
            if key.endswith(":stale"):
                out["base_stale"] = ttl
            elif "last_good" not in key and "lastgood" not in key:
                out["base_fresh"] = ttl
    return out


async def _publish(monkeypatch, status, **seed):
    rc._reset_last_good_for_tests()
    _seed(monkeypatch, **seed)
    _stub_enrichment(monkeypatch)
    redis = _SeededRedis()
    resp = await _drive_feed(redis=redis, monkeypatch=monkeypatch, events=[_row(status)])
    assert resp.status_code == 200
    body = resp.json()
    # Not vacuous: the page carries the game, and is live exactly when asked.
    assert any(i.get("type") == "event" for i in body["items"]), body
    assert payload_contains_live_event(body) is (status == "live")
    rc._reset_last_good_for_tests()
    ttls = _ttls(redis)
    assert {"fresh", "stale"} <= set(ttls), (
        f"the build did not publish the response cache: {redis.setex_calls!r}"
    )
    return ttls


@pytest.mark.asyncio
@pytest.mark.usefixtures("opening_seating_off")
async def test_a_non_live_page_from_an_aged_reading_publishes_inside_300(monkeypatch):
    ttls = await _publish(monkeypatch, "scheduled", strict_age_s=30.0)
    # 30 s spent (rounded up, plus however long the build took).
    assert ttls["stale"] <= FEED_RESPONSE_STALE_TTL_SECONDS - 30
    assert ttls["stale"] >= FEED_RESPONSE_STALE_TTL_SECONDS - 35
    assert ttls["fresh"] <= ttls["stale"]
    for kind in ("base_fresh", "base_stale"):
        if kind in ttls:
            assert ttls[kind] <= FEED_RESPONSE_STALE_TTL_SECONDS - 30, kind


@pytest.mark.asyncio
@pytest.mark.usefixtures("opening_seating_off")
async def test_the_page_base_publication_also_spends_the_strict_age(monkeypatch):
    ttls = await _publish(monkeypatch, "scheduled", strict_age_s=30.0)
    assert "base_stale" in ttls, "this rig no longer publishes a page base"
    assert ttls["base_stale"] <= FEED_RESPONSE_STALE_TTL_SECONDS - 30


@pytest.mark.asyncio
@pytest.mark.usefixtures("opening_seating_off")
async def test_a_non_live_page_from_a_fresh_build_keeps_the_full_window(monkeypatch):
    """Control: nothing aged consumed -> the old TTLs exactly."""
    ttls = await _publish(monkeypatch, "scheduled", strict_age_s=0.0)
    assert ttls["fresh"] == FEED_RESPONSE_TTL_ANON_SECONDS
    assert ttls["stale"] >= FEED_RESPONSE_STALE_TTL_SECONDS - 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("opening_seating_off")
async def test_a_non_live_page_from_an_aged_concepts_artifact_is_unchanged(monkeypatch):
    """Control: the live-only rule for `concepts`/`canonical_counts` is untouched."""
    ttls = await _publish(monkeypatch, "scheduled", counted_age_s=30.0)
    assert ttls["fresh"] == FEED_RESPONSE_TTL_ANON_SECONDS
    assert ttls["stale"] == FEED_RESPONSE_STALE_TTL_SECONDS


@pytest.mark.asyncio
@pytest.mark.usefixtures("opening_seating_off")
async def test_a_live_page_from_an_aged_reading_stays_under_sixty(monkeypatch):
    ttls = await _publish(monkeypatch, "live", strict_age_s=30.0)
    assert ttls["stale"] <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS - 30
    assert ttls["fresh"] <= ttls["stale"]
