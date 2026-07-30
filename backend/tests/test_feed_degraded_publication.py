"""Queue 283 Item 1 (C80 degraded-feed-publication) — a budget-truncated feed
build must never become shared truth, at the REAL /api/feed route.

C80 mechanical default: a degraded build (futures timeout / skipped-for-budget /
error) returns a MARKED partial payload to the current caller (and coalesced
waiters), but writes neither process last-good nor either Redis mirror, so the
last COMPLETE payload is preserved and the next same-key request rebuilds. A
complete build retains current cache behavior. Degradation is an explicit stage
result, never inferred from item count.

These tests drive the real route and assert on ``build_quality`` + the real
``request_cache`` publication calls — no source-string assertions.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.utils.request_cache as rc
from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


def _event_row(oid: int):
    row = MagicMock()
    row.id = oid
    row.home_team = "Celtics"
    row.away_team = "76ers"
    row.status = "live"
    row.sport_key = "basketball_nba"
    row.sport_id = 1
    row.sport_name = "Basketball"
    row.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    row.completed_at = None
    row.home_score = 55
    row.away_score = 52
    row.external_id = f"ext-{oid}"
    row.win_probability_sources = {"betting": {"home_probability": 0.55}}
    row.current_home_probability = 0.55
    row.current_away_probability = 0.45
    row.espn_game_id = None
    row.espn_data = None
    row.event_tags = []
    row.pulse_score = None
    row.pulse_label = None
    row.excite_index = None
    row.home_team_id = None
    row.away_team_id = None
    return row


def _seeded_session(events):
    session = AsyncMock()

    def make_result(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = (data or [None])[0] if data else None
        result.scalar_one_or_none.return_value = len(data) if data else 0
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = None
        return result

    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.first.return_value = None
    empty.scalar_one_or_none.return_value = 0
    empty.scalar.return_value = 0
    empty.fetchall.return_value = []
    empty.all.return_value = []
    empty.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "events" in s and events:
            return make_result(events)
        return empty

    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session


class _NoRedis:
    """A shared-redis stand-in that always misses on read (so the route builds)
    and records setex calls (so we can assert publication happened / was skipped)."""

    def __init__(self):
        self.setex_keys = []

    async def get(self, *a, **k):
        return None

    async def setex(self, key, ttl, val):
        self.setex_keys.append(key)
        return True


async def _drive_feed(events, *, futures_side_effect, redis, monkeypatch):
    """Run one real /api/feed request with the futures stage stubbed."""
    from app.main import app

    session = _seeded_session(events)

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    remembered: list[str] = []
    published: list = []

    orig_remember = rc.remember_last_good

    def spy_remember(key, payload):
        remembered.append(key)
        return orig_remember(key, payload)

    def spy_schedule(coro):
        published.append(coro)
        # Run the publish coroutine so setex actually fires (fresh + stale).
        return asyncio.ensure_future(coro)

    monkeypatch.setattr(rc, "remember_last_good", spy_remember)
    monkeypatch.setattr(rc, "schedule_background", spy_schedule)

    async def _get_redis():
        return redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)

    with patch("app.main.init_db", new_callable=AsyncMock), patch(
        "app.routes.feed._score_futures", new=AsyncMock(side_effect=futures_side_effect)
    ), patch(
        "app.routes.feed._score_sports_mode_futures",
        new=AsyncMock(side_effect=futures_side_effect),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/feed")

    app.dependency_overrides.clear()
    # Let any scheduled publish coroutines run.
    await asyncio.sleep(0)
    return resp, remembered, published


@pytest.mark.asyncio
async def test_complete_build_publishes_and_caches(monkeypatch):
    redis = _NoRedis()

    async def ok_futures(*a, **k):
        return []  # complete build, just no futures candidates

    resp, remembered, published = await _drive_feed(
        [_event_row(1)], futures_side_effect=ok_futures, redis=redis, monkeypatch=monkeypatch
    )
    body = resp.json()
    assert resp.status_code == 200
    assert "build_quality" not in body  # complete builds are unmarked
    assert remembered, "complete build must record process last-good"
    assert published, "complete build must publish to Redis"
    await asyncio.sleep(0)
    # both fresh + :stale mirrors written
    assert any(k.endswith(":stale") for k in redis.setex_keys)
    assert any(not k.endswith(":stale") for k in redis.setex_keys)


@pytest.mark.asyncio
async def test_futures_timeout_is_degraded_and_not_published(monkeypatch):
    redis = _NoRedis()
    resp, remembered, published = await _drive_feed(
        [_event_row(1)],
        futures_side_effect=asyncio.TimeoutError(),
        redis=redis,
        monkeypatch=monkeypatch,
    )
    body = resp.json()
    assert resp.status_code == 200                       # bounded partial returned
    assert body["build_quality"] == "degraded"
    assert body["degraded_reason"] == "futures_timeout"
    assert remembered == [], "degraded build must NOT write process last-good"
    assert published == [], "degraded build must NOT publish to Redis"
    assert redis.setex_keys == []


@pytest.mark.asyncio
async def test_futures_error_is_degraded_and_not_published(monkeypatch):
    redis = _NoRedis()
    resp, remembered, published = await _drive_feed(
        [_event_row(1)],
        futures_side_effect=ValueError("boom"),
        redis=redis,
        monkeypatch=monkeypatch,
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["build_quality"] == "degraded"
    assert body["degraded_reason"] == "futures_error"
    assert remembered == []
    assert published == []


@pytest.mark.asyncio
async def test_skipped_for_budget_is_degraded(monkeypatch):
    redis = _NoRedis()
    # Zero the total budget so the futures stage is skipped for budget before it
    # ever runs (the futures_skipped_budget state).
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)

    async def unused(*a, **k):
        raise AssertionError("futures should be skipped, not called")

    resp, remembered, published = await _drive_feed(
        [_event_row(1)], futures_side_effect=unused, redis=redis, monkeypatch=monkeypatch
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["build_quality"] == "degraded"
    assert body["degraded_reason"] == "futures_skipped_budget"
    assert remembered == []
    assert published == []
