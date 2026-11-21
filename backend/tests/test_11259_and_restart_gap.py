"""Regression tests for #11259 and the post-restart grouping/round-up gap."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.feed_cache import (
    FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS,
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS,
    base_from_last_good,
    dumps_feed_cache,
    encode_base_last_good,
    feed_page_base_last_good_max_age_s,
    payload_contains_live_event,
    strip_live_and_started_items_for_last_good,
)
from app.utils.roundup_containers import (
    ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
    ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S,
    RoundupMembers,
    RoundupProducer,
    _redis_cache_key,
    add_roundup_feed_items,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
)

NOW = 1_750_000_000.0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _wire_base(items: list[dict], *, age_s: float) -> bytes:
    payload = {
        "items": items,
        "total": len(items),
        FEED_PAGE_BASE_BUILT_AT_FIELD: NOW - age_s,
    }
    return encode_base_last_good(json.dumps(payload))


def test_11259_six_hour_emergency_retention_strips_live_and_started_cards_only() -> None:
    assert FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS == 21600
    items = [
        {"type": "futures", "data": {"id": 101, "status": "open"}},
        {"type": "event", "data": {"id": 201, "status": "live"}},
        {
            "type": "event",
            "data": {"id": 202, "status": "scheduled", "commence_time": _iso(NOW - 30)},
        },
        {
            "type": "event",
            "data": {"id": 203, "status": "scheduled", "commence_time": _iso(NOW + 3600)},
        },
        {
            "type": "bundle",
            "data": {
                "id": "machinery-nba-night",
                "items": [{"type": "event", "data": {"id": 204, "status": "live"}}],
            },
        },
        {
            "type": "bundle",
            "data": {
                "id": "machinery-fed-and-macro",
                "items": [{"type": "futures", "data": {"id": 102, "status": "open"}}],
            },
        },
    ]

    # Mixed deck strips live/started cards BEFORE write, so the written copy
    # holds zero live cards and derives 6h TTL through the #2216 live helper;
    # live-only deck stays live and clamps to 60s.
    stripped_mixed = strip_live_and_started_items_for_last_good(
        {"items": items, "total": len(items)}, now=NOW
    )
    assert payload_contains_live_event(stripped_mixed) is False
    assert (
        feed_page_base_last_good_max_age_s(
            live=payload_contains_live_event(stripped_mixed)
        )
        == 21600
    )
    assert [it["data"]["id"] for it in stripped_mixed["items"]] == [
        101,
        203,
        "machinery-fed-and-macro",
    ]

    live_only = {
        "items": [{"type": "event", "data": {"id": 201, "status": "live"}}],
        "total": 1,
    }
    stripped_live_only = strip_live_and_started_items_for_last_good(live_only, now=NOW)
    assert payload_contains_live_event(stripped_live_only) is True
    assert (
        feed_page_base_last_good_max_age_s(
            live=payload_contains_live_event(stripped_live_only)
        )
        == FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
    )

    # At 3 hours old (past 60s live ceiling, within 6h emergency window):
    # live game (201), kicked-off game (202), and live bundle (machinery-nba-night)
    # are stripped; futures (101), upcoming game (203), and non-live grouping stay.
    base, origin = base_from_last_good(_wire_base(items, age_s=3 * 3600), now=NOW)
    assert base is not None and origin == NOW - 3 * 3600
    kept_ids = [it["data"]["id"] for it in base["items"]]
    assert kept_ids == [101, 203, "machinery-fed-and-macro"]
    assert base["total"] == 3

    # Past 6 hours: fails closed.
    assert base_from_last_good(_wire_base(items, age_s=21601), now=NOW) == (None, None)


def test_11259_emergency_copy_written_with_live_game_has_no_live_score_after_61s() -> None:
    """Fable verdict #13307: write a page with a live game + score into the
    emergency copy, read it back after 61 seconds, and verify no live score
    exists in either the stored blob or the read-back page."""
    written_at = NOW
    page_with_live_game = {
        "items": [
            {"type": "futures", "data": {"id": 501, "name": "Fed decision", "status": "open"}},
            {
                "type": "event",
                "data": {
                    "id": 999,
                    "home_team": "Celtics",
                    "away_team": "76ers",
                    "status": "live",
                    "home_score": 88,
                    "away_score": 84,
                },
            },
            {
                "type": "event",
                "data": {
                    "id": 998,
                    "home_team": "Lakers",
                    "away_team": "Knicks",
                    "status": "scheduled",
                    "commence_time": _iso(written_at + 30),  # starts before t+61s
                    "home_score": 0,
                    "away_score": 0,
                },
            },
            {
                "type": "event",
                "data": {
                    "id": 997,
                    "home_team": "Bulls",
                    "away_team": "Heat",
                    "status": "scheduled",
                    "commence_time": _iso(written_at + 3600),
                },
            },
        ],
        "total": 4,
        FEED_PAGE_BASE_BUILT_AT_FIELD: written_at,
    }

    # Write path strips live & already-started cards before persisting for 6h.
    lg_body = strip_live_and_started_items_for_last_good(
        page_with_live_game, now=written_at
    )
    lg_json = dumps_feed_cache(lg_body)
    lg_ttl = feed_page_base_last_good_max_age_s(
        live=payload_contains_live_event(lg_body)
    )
    assert lg_ttl == FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS
    assert '"home_score": 88' not in lg_json and '"home_score":88' not in lg_json
    assert payload_contains_live_event(lg_body) is False

    wire = encode_base_last_good(lg_json)

    # Read back 61 seconds later: live game (999) is absent AND the game that
    # crossed kickoff at t+30s (998) is stripped at read time; non-live items survive.
    served, origin = base_from_last_good(wire, now=written_at + 61.0)
    assert served is not None and origin == written_at
    assert payload_contains_live_event(served) is False
    served_ids = [it["data"]["id"] for it in served["items"]]
    assert served_ids == [501, 997]
    for it in served["items"]:
        data = it["data"]
        assert str(data.get("status") or "").lower() not in {"live", "in_progress", "halftime"}
        assert "home_score" not in data and "away_score" not in data


@pytest.mark.asyncio
async def test_restart_hydrates_groupings_and_standing_roundups_via_single_mget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S == 21600.0
    assert ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S == 21600.0
    reset_roundup_cache_for_tests()

    redis_store: dict[str, bytes] = {}
    get_calls: list[str] = []
    mget_calls: list[list[str]] = []

    class _FakeRedis:
        async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
            redis_store[key] = value.encode("utf-8") if isinstance(value, str) else value
            return True

        async def get(self, key: str) -> Any:
            get_calls.append(key)
            return redis_store.get(key)

        async def mget(self, keys: list[str]) -> list[Any]:
            mget_calls.append(list(keys))
            return [redis_store.get(k) for k in keys]

        async def hset(self, *_a: Any, **_kw: Any) -> int:
            return 1

        async def hdel(self, *_a: Any, **_kw: Any) -> int:
            return 1

        async def expire(self, *_a: Any, **_kw: Any) -> bool:
            return True

    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.utils.request_cache.get_shared_async_redis",
        AsyncMock(return_value=fake_redis),
    )

    def _members(label: str, mid: int) -> RoundupMembers:
        return RoundupMembers(
            members=[
                {
                    "type": "market",
                    "id": mid,
                    "destination": {
                        "kind": "market",
                        "id": mid,
                        "web": f"/futures/{mid}",
                        "api": f"/api/futures/{mid}",
                    },
                    "card": {
                        "id": mid,
                        "name": f"{label} market",
                        "status": "open",
                        "top_outcomes": [
                            {"id": mid * 10, "name": "Yes", "probability": 0.65}
                        ],
                    },
                }
            ],
            rows=[{"label": label, "value": 0.65, "rendered_percent": 65}],
            footer="Test footer",
            title=f"{label} title",
        )

    db_calls = {"mach": 0, "standing": 0}

    async def _prod_mach(_db: Any) -> RoundupMembers:
        db_calls["mach"] += 1
        return _members("Fed", 5001)

    async def _prod_standing(_db: Any) -> RoundupMembers:
        db_calls["standing"] += 1
        return _members("Standing", 5002)

    p_mach = RoundupProducer(
        slug="machinery-fed-and-macro",
        name="Fed & Macro",
        kind="roundup",
        category="economics",
        section_title="Fed",
        footer="Fed",
        produce=_prod_mach,
    )
    p_standing = RoundupProducer(
        slug="roundup-standing-restart",
        name="Standing",
        kind="roundup",
        category="politics",
        section_title="Standing",
        footer="Standing",
        produce=_prod_standing,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
        {p_mach.slug: p_mach, p_standing.slug: p_standing},
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()
    t0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Warm both into Redis before the simulated dyno restart.
    await evaluate_roundup_producer(p_mach, fake_session, now=t0)
    await evaluate_roundup_producer(p_standing, fake_session, now=t0)
    assert _redis_cache_key(p_mach.slug) in redis_store
    assert _redis_cache_key(p_standing.slug) in redis_store

    # Simulate a Heroku release restart + 90-minute gap (past old 30m TTL, within 6h).
    reset_roundup_cache_for_tests()
    get_calls.clear()
    mget_calls.clear()
    db_calls["mach"] = 0
    db_calls["standing"] = 0

    t1 = t0 + timedelta(minutes=90)
    deck = [
        {"type": "futures", "score": 50, "data": {"id": i, "name": f"M{i}"}}
        for i in range(1, 20)
    ]
    placed = await add_roundup_feed_items(
        fake_session, deck, now=t1, include_machinery=True
    )
    served_slugs = [
        ((it.get("data") or {}).get("collection_ref") or {}).get("slug")
        for it in placed
        if it.get("type") == "bundle"
    ]
    assert p_mach.slug in served_slugs
    assert p_standing.slug in served_slugs
    # Hydrated from ONE batched MGET with zero sequential Redis GETs or DB hits.
    assert len(mget_calls) == 1
    assert get_calls == []
    assert db_calls == {"mach": 0, "standing": 0}
