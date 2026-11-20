"""Tests for #13146: keep the last good copy when a Discover round-up read times out.

Covers:
1. Standing round-up timeout inside keep-time keeps the last good copy instead of
   leaving it out or clobbering the cache with a timeout refusal.
2. Fresh web dyno with empty local cache recovers the last good copy from Redis
   when a standing round-up refresh times out.
3. Past keep-time (non-live > 1800s, live > 300s) or past `valid_until` (65-A),
   the copy is NOT served; leaving it out is the last resort and is counted.
4. Transient exceptions and machinery grouping timeouts follow the same contract.
5. Rolling 10-minute failure stats prune entries older than 600s and surface on
   `/api/health` as `roundup_reads_10m`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.roundup_containers import (
    ROUNDUP_READ_FAILURE_WINDOW_S,
    ROUNDUP_STANDING_LIVE_STALE_TTL_S,
    ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S,
    RoundupMembers,
    RoundupProducer,
    _redis_cache_key,
    add_roundup_feed_items,
    evaluate_roundup_producer,
    get_roundup_read_failure_stats_10m,
    reset_roundup_cache_for_tests,
)


def _ordinary_deck(n: int = 25) -> list[dict[str, Any]]:
    return [
        {
            "type": "futures",
            "score": 80 - i,
            "reason": "test",
            "headline": f"Ordinary card {i}",
            "data": {
                "id": 50000 + i,
                "market_id": 50000 + i,
                "question": f"Ordinary market {i}",
                "sport": "politics" if i % 2 == 0 else "economics",
            },
        }
        for i in range(n)
    ]


def _make_standing_members(label: str, *, live_event: bool = False) -> RoundupMembers:
    if live_event:
        return RoundupMembers(
            members=[
                {
                    "type": "event",
                    "id": 7701,
                    "destination": "/events/7701",
                    "event_id": 7701,
                    "card": {
                        "id": 7701,
                        "name": f"Live Game {label}",
                        "status": "live",
                        "home_team": "Celtics",
                        "away_team": "Knicks",
                        "home_prob": 0.54,
                    },
                },
                {
                    "type": "event",
                    "id": 7702,
                    "destination": "/events/7702",
                    "event_id": 7702,
                    "card": {
                        "id": 7702,
                        "name": f"Scheduled Game {label}",
                        "status": "scheduled",
                        "home_team": "Lakers",
                        "away_team": "Heat",
                        "home_prob": 0.51,
                    },
                },
            ],
            title=f"Closest games ({label})",
            footer="2 games tonight",
        )
    return RoundupMembers(
        members=[
            {
                "id": 8801,
                "name": f"Market A ({label})",
                "top_outcome": "Yes",
                "probability": 0.62,
                "status": "open",
            },
            {
                "id": 8802,
                "name": f"Market B ({label})",
                "top_outcome": "No",
                "probability": 0.58,
                "status": "open",
            },
        ],
        title=f"This week's economic data ({label})",
        footer="2 releases this week",
    )


def _roundup_slugs_in(items: list[dict[str, Any]]) -> list[str]:
    return [
        it["data"]["collection_ref"]["slug"]
        for it in items
        if it.get("type") == "bundle" and it.get("data", {}).get("kind") == "roundup"
    ]


def _roundup_title_for(items: list[dict[str, Any]], slug: str) -> str | None:
    for it in items:
        if (
            it.get("type") == "bundle"
            and it.get("data", {}).get("collection_ref", {}).get("slug") == slug
        ):
            return str(it.get("headline") or it["data"].get("title") or "")
    return None


class _RollbackSession:
    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_standing_roundup_timeout_keeps_last_good_copy_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    mode = "v1"

    async def _produce(_db: Any) -> Any:
        if mode == "timeout":
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members(mode)

    producer = RoundupProducer(
        slug="roundup-this-weeks-economic-data",
        name="This week's economic data",
        kind="roundup",
        category="economics",
        section_title="Releases",
        footer="Economic releases",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    db = _RollbackSession()
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Initial good read caches copy v1.
    placed_v1 = await add_roundup_feed_items(_db := db, _ordinary_deck(), now=t0)
    assert _roundup_slugs_in(placed_v1) == [producer.slug]
    assert "v1" in (_roundup_title_for(placed_v1, producer.slug) or "")
    assert get_roundup_read_failure_stats_10m(now=t0)["failed"] == 0

    # 2. Past 60s fresh TTL (t0 + 120s), producer times out -> keeps last good copy v1!
    mode = "timeout"
    t1 = t0 + timedelta(seconds=120)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        placed_t1 = await add_roundup_feed_items(db, _ordinary_deck(), now=t1)
    assert _roundup_slugs_in(placed_t1) == [producer.slug]
    assert "v1" in (_roundup_title_for(placed_t1, producer.slug) or "")
    assert "kept last good copy" in caplog.text
    assert "keeping ordinary cards" not in caplog.text

    # 3. A second consecutive timeout (t0 + 240s) STILL keeps v1 (was NOT clobbered by refusal!).
    t2 = t0 + timedelta(seconds=240)
    placed_t2 = await add_roundup_feed_items(db, _ordinary_deck(), now=t2)
    assert _roundup_slugs_in(placed_t2) == [producer.slug]
    assert "v1" in (_roundup_title_for(placed_t2, producer.slug) or "")

    stats = get_roundup_read_failure_stats_10m(now=t2)
    assert stats["failed"] == 2
    assert stats["kept_last_good"] == 2
    assert stats["dropped_no_copy"] == 0

    # 4. When DB recovers (t0 + 300s), fresh v2 replaces v1 cleanly.
    mode = "v2"
    t3 = t0 + timedelta(seconds=300)
    placed_v2 = await add_roundup_feed_items(db, _ordinary_deck(), now=t3)
    assert _roundup_slugs_in(placed_v2) == [producer.slug]
    assert "v2" in (_roundup_title_for(placed_v2, producer.slug) or "")


@pytest.mark.asyncio
async def test_cold_web_process_recovers_standing_last_good_copy_from_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    redis_store: dict[str, str] = {}

    class _FakeRedis:
        async def get(self, key: str) -> str | None:
            return redis_store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            redis_store[key] = value
            return True

    fake_redis = _FakeRedis()

    async def _get_redis() -> _FakeRedis:
        return fake_redis

    class _OkRes:
        def __init__(self, value: Any) -> None:
            self.is_ok = True
            self.value = value

    async def _bounded(fn: Any, **_kwargs: Any) -> _OkRes:
        return _OkRes(await fn())

    monkeypatch.setattr("app.utils.request_cache.get_shared_async_redis", _get_redis)
    monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _bounded)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        AsyncMock(side_effect=lambda _db, cards, *_args, **_kw: cards),
    )

    should_hang = False

    async def _produce(_db: Any) -> Any:
        if should_hang:
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members("from-redis")

    producer = RoundupProducer(
        slug="roundup-gta-vi-album",
        name="GTA VI Album",
        kind="roundup",
        category="entertainment",
        section_title="Artists",
        footer="Featured artists",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    fi, cp = await evaluate_roundup_producer(producer, fake_session, now=t0)
    assert fi is not None and cp is not None
    assert _redis_cache_key(producer.slug) in redis_store

    # Simulate a brand-new web dyno restart: local process cache is empty, Redis still has copy.
    reset_roundup_cache_for_tests()
    should_hang = True
    t1 = t0 + timedelta(seconds=180)  # past 60s fresh TTL, within 1800s keep-time
    placed = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t1)
    assert _roundup_slugs_in(placed) == [producer.slug]
    assert "from-redis" in (_roundup_title_for(placed, producer.slug) or "")
    stats = get_roundup_read_failure_stats_10m(now=t1)
    assert stats["failed"] == 1
    assert stats["kept_last_good"] == 1
    assert stats["dropped_no_copy"] == 0
    # Redis entry was NOT overwritten with (None, None).
    stored = json.loads(redis_store[_redis_cache_key(producer.slug)])
    assert stored["feed_item"] is not None
    assert stored["container_payload"] is not None


@pytest.mark.asyncio
async def test_expired_keep_time_and_expired_valid_until_drop_as_last_resort_and_count(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    # 1. Non-live standing round-up past 1800s keep-time -> dropped and counted.
    hang = False

    async def _produce_non_live(_db: Any) -> Any:
        if hang:
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members("old")

    p_non_live = RoundupProducer(
        slug="roundup-old-non-live",
        name="Old non-live",
        kind="roundup",
        category="economics",
        section_title="Items",
        footer="Footer",
        produce=_produce_non_live,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p_non_live.slug: p_non_live}
    )

    db = _RollbackSession()
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    assert _roundup_slugs_in(await add_roundup_feed_items(db, _ordinary_deck(), now=t0)) == [
        p_non_live.slug
    ]

    hang = True
    t_past = t0 + timedelta(seconds=ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S + 10)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        placed_past = await add_roundup_feed_items(db, _ordinary_deck(), now=t_past)
    assert _roundup_slugs_in(placed_past) == []
    assert "Discover round-up read failed for roundup-old-non-live; keeping ordinary cards" in caplog.text
    stats = get_roundup_read_failure_stats_10m(now=t_past)
    assert stats["failed"] == 1
    assert stats["kept_last_good"] == 0
    assert stats["dropped_no_copy"] == 1

    # 2. Live standing round-up uses the tighter 300s keep-time.
    reset_roundup_cache_for_tests()
    hang_live = False

    async def _produce_live(_db: Any) -> Any:
        if hang_live:
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members("live-slate", live_event=True)

    p_live = RoundupProducer(
        slug="roundup-closest-games-tonight",
        name="Closest games tonight",
        kind="roundup",
        category="sports",
        section_title="Closest games",
        footer="2 games",
        produce=_produce_live,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p_live.slug: p_live}
    )
    assert _roundup_slugs_in(await add_roundup_feed_items(db, _ordinary_deck(), now=t0)) == [
        p_live.slug
    ]
    hang_live = True
    # Inside 300s -> kept.
    t_live_ok = t0 + timedelta(seconds=120)
    assert _roundup_slugs_in(
        await add_roundup_feed_items(db, _ordinary_deck(), now=t_live_ok)
    ) == [p_live.slug]
    # Past 300s -> dropped.
    t_live_expired = t0 + timedelta(seconds=ROUNDUP_STANDING_LIVE_STALE_TTL_S + 10)
    assert (
        _roundup_slugs_in(
            await add_roundup_feed_items(db, _ordinary_deck(), now=t_live_expired)
        )
        == []
    )
    stats_live = get_roundup_read_failure_stats_10m(now=t_live_expired)
    assert stats_live["kept_last_good"] == 1
    assert stats_live["dropped_no_copy"] == 1

    # 3. Dated producer past valid_until NEVER serves a stale copy (65-A).
    reset_roundup_cache_for_tests()
    hang_dated = False

    async def _produce_dated(_db: Any) -> Any:
        if hang_dated:
            raise RuntimeError("transient db error")
        return _make_standing_members("dated")

    p_dated = RoundupProducer(
        slug="roundup-dated-window",
        name="Dated window",
        kind="roundup",
        category="politics",
        section_title="Items",
        footer="Footer",
        produce=_produce_dated,
        rule={"valid_until": (t0 + timedelta(seconds=100)).isoformat()},
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p_dated.slug: p_dated}
    )
    assert _roundup_slugs_in(await add_roundup_feed_items(db, _ordinary_deck(), now=t0)) == [
        p_dated.slug
    ]
    hang_dated = True
    # At t0 + 150s (> valid_until, even though < 1800s keep-time) -> returns None.
    assert (
        _roundup_slugs_in(
            await add_roundup_feed_items(
                db, _ordinary_deck(), now=t0 + timedelta(seconds=150)
            )
        )
        == []
    )


@pytest.mark.asyncio
async def test_transient_error_keeps_last_good_and_10m_window_prunes_and_surfaces_on_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")

    fail_now = False

    async def _produce(_db: Any) -> Any:
        if fail_now:
            raise RuntimeError("transient query failure")
        return _make_standing_members("steady")

    producer = RoundupProducer(
        slug="roundup-rt-scores",
        name="RT scores",
        kind="roundup",
        category="entertainment",
        section_title="Movies",
        footer="Reviews",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    db = _RollbackSession()
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    assert _roundup_slugs_in(await add_roundup_feed_items(db, _ordinary_deck(), now=t0)) == [
        producer.slug
    ]

    fail_now = True
    t1 = t0 + timedelta(seconds=90)
    placed = await add_roundup_feed_items(db, _ordinary_deck(), now=t1)
    assert _roundup_slugs_in(placed) == [producer.slug]
    assert get_roundup_read_failure_stats_10m(now=t1) == {
        "window_seconds": 600,
        "failed": 1,
        "kept_last_good": 1,
        "dropped_no_copy": 0,
    }

    # Older than 10 minutes -> pruned to 0.
    t_after = t1 + timedelta(seconds=ROUNDUP_READ_FAILURE_WINDOW_S + 1)
    assert get_roundup_read_failure_stats_10m(now=t_after) == {
        "window_seconds": 600,
        "failed": 0,
        "kept_last_good": 0,
        "dropped_no_copy": 0,
    }

    # /api/health surfaces `roundup_reads_10m` cleanly without extra I/O.
    from app.routes import health as health_route

    class _Conn:
        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def execute(self, *_args: Any) -> None:
            return None

    class _FakeEngine:
        def connect(self) -> _Conn:
            return _Conn()

    fake_rc = MagicMock()
    fake_rc.ping.return_value = True
    monkeypatch.setattr("app.services.database.engine", _FakeEngine())
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_rc)

    resp = await health_route.api_health_check()
    body = json.loads(resp.body.decode("utf-8"))
    assert "roundup_reads_10m" in body
    assert set(body["roundup_reads_10m"].keys()) == {
        "window_seconds",
        "failed",
        "kept_last_good",
        "dropped_no_copy",
    }


@pytest.mark.asyncio
async def test_stage_budget_exhausted_keeps_local_last_good_for_remaining_producers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.2
    )

    slow_first = False

    async def _p1_prod(_db: Any) -> Any:
        if slow_first:
            await asyncio.sleep(0.06)
        return _make_standing_members("p1")

    async def _p2_prod(_db: Any) -> Any:
        return _make_standing_members("p2")

    p1 = RoundupProducer(
        slug="roundup-first",
        name="First",
        kind="roundup",
        category="economics",
        section_title="First",
        footer="First",
        produce=_p1_prod,
    )
    p2 = RoundupProducer(
        slug="roundup-second",
        name="Second",
        kind="roundup",
        category="politics",
        section_title="Second",
        footer="Second",
        produce=_p2_prod,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p1.slug: p1, p2.slug: p2}
    )

    db = _RollbackSession()
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    # Warm both producers cleanly.
    initial = await add_roundup_feed_items(db, _ordinary_deck(), budget_seconds=5.0, now=t0)
    assert set(_roundup_slugs_in(initial)) == {p1.slug, p2.slug}

    # Past 60s fresh TTL, p1 burns the 0.03s stage budget, leaving remaining <= 0 for p2.
    # p2 still keeps its local last good copy instead of disappearing!
    slow_first = True
    t1 = t0 + timedelta(seconds=120)
    placed = await add_roundup_feed_items(
        db,
        _ordinary_deck(),
        budget_seconds=0.03,
        stage_budget_seconds=0.03,
        now=t1,
    )
    assert set(_roundup_slugs_in(placed)) == {p1.slug, p2.slug}
    stats = get_roundup_read_failure_stats_10m(now=t1)
    assert stats["kept_last_good"] >= 1
    assert stats["dropped_no_copy"] == 0
