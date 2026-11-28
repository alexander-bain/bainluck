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
    RoundupRefusal,
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
    t1 = t0 + timedelta(seconds=180)  # past 60s fresh TTL, within 6h keep-time
    placed = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t1)
    assert _roundup_slugs_in(placed) == [producer.slug]
    assert "from-redis" in (_roundup_title_for(placed, producer.slug) or "")
    # On a cold restart, the standing round-up hydrates directly from the
    # prefetched shared Redis copy with zero timeout or drop.
    stats = get_roundup_read_failure_stats_10m(now=t1)
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
        "had_nothing_to_show": 0,
    }

    # Older than 10 minutes -> pruned to 0.
    t_after = t1 + timedelta(seconds=ROUNDUP_READ_FAILURE_WINDOW_S + 1)
    assert get_roundup_read_failure_stats_10m(now=t_after) == {
        "window_seconds": 600,
        "failed": 0,
        "kept_last_good": 0,
        "dropped_no_copy": 0,
        "had_nothing_to_show": 0,
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
        "had_nothing_to_show",
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


class _ExpiringFakeRedis:
    """In-memory async Redis fake that enforces `ex` against a controllable clock."""

    def __init__(self, clock: list[float]) -> None:
        self._clock = clock
        self._store: dict[str, tuple[str, float | None]] = {}
        self.last_ex: dict[str, int | None] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        val, expires_at = entry
        if expires_at is not None and self._clock[0] >= expires_at:
            del self._store[key]
            return None
        return val

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        expires_at = self._clock[0] + float(ex) if ex is not None else None
        self._store[key] = (value, expires_at)
        self.last_ex[key] = ex
        return True


def _wire_fake_redis(monkeypatch: pytest.MonkeyPatch, fake_redis: Any) -> None:
    async def _get_redis() -> Any:
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


@pytest.mark.asyncio
async def test_pre_tipoff_copy_uses_live_keep_time_once_game_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 1 (#13184 review): a copy made 2 min before tip-off expires at 5 min, not 30 min."""
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    t0 = datetime(2026, 11, 20, 23, 58, 0, tzinfo=timezone.utc)
    tipoff = t0 + timedelta(minutes=2)
    clock = [t0.timestamp()]
    fake_redis = _ExpiringFakeRedis(clock)
    _wire_fake_redis(monkeypatch, fake_redis)

    hang = False

    async def _produce(_db: Any) -> Any:
        if hang:
            await asyncio.sleep(0.25)
            return None
        return RoundupMembers(
            members=[
                {
                    "type": "event",
                    "id": 9901,
                    "destination": "/events/9901",
                    "event_id": 9901,
                    "card": {
                        "id": 9901,
                        "name": "Celtics at Knicks",
                        "status": "scheduled",
                        "commence_time": tipoff.isoformat(),
                        "home_team": "Knicks",
                        "away_team": "Celtics",
                        "home_prob": 0.53,
                    },
                },
                {
                    "type": "event",
                    "id": 9902,
                    "destination": "/events/9902",
                    "event_id": 9902,
                    "card": {
                        "id": 9902,
                        "name": "Lakers at Heat",
                        "status": "scheduled",
                        "commence_time": (tipoff + timedelta(hours=1)).isoformat(),
                        "home_team": "Heat",
                        "away_team": "Lakers",
                        "home_prob": 0.51,
                    },
                },
            ],
            title="Closest games tonight (pre-tipoff)",
            footer="2 games tonight",
        )

    producer = RoundupProducer(
        slug="roundup-pre-tipoff-games",
        name="Closest games tonight",
        kind="roundup",
        category="sports",
        section_title="Games",
        footer="2 games",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    # Copy made 2 min before tip-off (status="scheduled" at build time -> stored stale_ttl_s=1800).
    assert _roundup_slugs_in(
        await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t0)
    ) == [producer.slug]

    hang = True
    # 4 min after copy (2 min into game, age=240s < 300s): KEPT.
    t_4m = t0 + timedelta(minutes=4)
    clock[0] = t_4m.timestamp()
    assert _roundup_slugs_in(
        await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t_4m)
    ) == [producer.slug]

    # 10 min, 25 min, 29 min after copy (8–27 min into game, age >= 300s): LEFT OUT
    # even though stored stale_ttl_s was 1800s (both local and cold-from-Redis paths).
    for mins in (10, 25, 29):
        t_later = t0 + timedelta(minutes=mins)
        clock[0] = t_later.timestamp()
        assert (
            _roundup_slugs_in(
                await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t_later)
            )
            == []
        ), f"pre-tipoff copy must not be kept at +{mins}m into live play"

    # Also verify a cold process reading directly from Redis respects the 5-min live clock cap.
    reset_roundup_cache_for_tests()
    t_10m = t0 + timedelta(minutes=10)
    clock[0] = t_10m.timestamp()
    assert (
        _roundup_slugs_in(
            await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t_10m)
        )
        == []
    )


@pytest.mark.asyncio
async def test_newer_shared_copy_beats_older_local_copy_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 2 (#13184 review): a 2-min shared copy beats a 20-min local copy."""
    from app.utils.roundup_containers import _roundup_local_cache

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    clock = [t0.timestamp()]
    fake_redis = _ExpiringFakeRedis(clock)
    _wire_fake_redis(monkeypatch, fake_redis)

    mode = "20min-old"

    async def _produce(_db: Any) -> Any:
        if mode == "timeout":
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members(mode)

    producer = RoundupProducer(
        slug="roundup-shared-beats-local",
        name="Shared beats local",
        kind="roundup",
        category="economics",
        section_title="Items",
        footer="Footer",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    # Process A warms at t0 -> holds 20-minute-old copy locally.
    await evaluate_roundup_producer(producer, fake_session, now=t0)
    process_a_local = _roundup_local_cache[(producer.slug, "live")]

    # Process B warms at t0 + 18 min -> writes 2-minute-old copy to shared Redis.
    reset_roundup_cache_for_tests()
    mode = "2min-new"
    t18 = t0 + timedelta(minutes=18)
    clock[0] = t18.timestamp()
    await evaluate_roundup_producer(producer, fake_session, now=t18)

    # Restore Process A's stale 20-min-old local cache; at t0 + 20 min, read hangs.
    _roundup_local_cache[(producer.slug, "live")] = process_a_local
    mode = "timeout"
    t20 = t0 + timedelta(minutes=20)
    clock[0] = t20.timestamp()
    placed = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t20)
    assert _roundup_slugs_in(placed) == [producer.slug]
    assert "2min-new" in (_roundup_title_for(placed, producer.slug) or "")


@pytest.mark.asyncio
async def test_withdrawn_roundup_in_shared_store_does_not_resurrect_from_old_local_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 3 (#13184 review): a proper withdrawal stays in Redis for keep-time so old local copies never return."""
    from app.utils.roundup_containers import RoundupRefusal, _roundup_local_cache

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    clock = [t0.timestamp()]
    fake_redis = _ExpiringFakeRedis(clock)
    _wire_fake_redis(monkeypatch, fake_redis)

    mode = "good-v1"
    produce_calls = 0

    async def _produce(_db: Any) -> Any:
        nonlocal produce_calls
        produce_calls += 1
        if mode == "refuse":
            return RoundupRefusal(["below_threshold"])
        if mode == "timeout":
            await asyncio.sleep(0.25)
            return None
        return _make_standing_members(mode)

    producer = RoundupProducer(
        slug="roundup-withdrawn-card",
        name="Withdrawn card",
        kind="roundup",
        category="politics",
        section_title="Items",
        footer="Footer",
        produce=_produce,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {producer.slug: producer}
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    # Process A warms at t0.
    await evaluate_roundup_producer(producer, fake_session, now=t0)
    process_a_local = _roundup_local_cache[(producer.slug, "live")]

    # Elsewhere at +10 min, the round-up is properly refused (withdrawn).
    reset_roundup_cache_for_tests()
    mode = "refuse"
    t10 = t0 + timedelta(minutes=10)
    clock[0] = t10.timestamp()
    fi_ref, cp_ref = await evaluate_roundup_producer(producer, fake_session, now=t10)
    assert fi_ref is None and cp_ref is None
    # Refusal stays in Redis as long as copies are kept (1800s), while retry TTL stays 60s.
    rkey = _redis_cache_key(producer.slug)
    assert fake_redis.last_ex[rkey] == int(ROUNDUP_STANDING_NON_LIVE_STALE_TTL_S)
    stored_ref = json.loads(await fake_redis.get(rkey) or "{}")
    assert stored_ref["ttl_s"] == 60.0

    # At +12 min (past the 60s retry window!), Process A holds its 12-min-old local copy and read hangs.
    _roundup_local_cache[(producer.slug, "live")] = process_a_local
    mode = "timeout"
    t12 = t0 + timedelta(minutes=12)
    clock[0] = t12.timestamp()
    calls_before = produce_calls
    placed_12 = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t12)
    assert produce_calls == calls_before + 1  # retry window stayed 60s, so it DID retry
    assert _roundup_slugs_in(placed_12) == []  # newer withdrawal beats old local copy!

    # And a third process with an old local copy at +13m30s (>60s after the timeout) STILL sees the withdrawal.
    _roundup_local_cache[(producer.slug, "live")] = process_a_local
    t13_5 = t0 + timedelta(minutes=13, seconds=30)
    clock[0] = t13_5.timestamp()
    placed_13_5 = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t13_5)
    assert _roundup_slugs_in(placed_13_5) == []


@pytest.mark.asyncio
async def test_budget_exhausted_reads_shared_store_for_newer_copy_and_withdrawal_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#13184 review (out-of-time branch): budget exhaustion checks Redis for newer copy, withdrawal, and fails closed on Redis error."""
    from app.utils.roundup_containers import RoundupRefusal, _roundup_local_cache

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.2
    )

    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    clock = [t0.timestamp()]
    fake_redis = _ExpiringFakeRedis(clock)
    _wire_fake_redis(monkeypatch, fake_redis)

    slow_first = False
    target_mode = "20min-old"

    async def _p1_prod(_db: Any) -> Any:
        if slow_first:
            await asyncio.sleep(0.06)
        return _make_standing_members("p1")

    async def _p2_prod(_db: Any) -> Any:
        if target_mode == "refuse":
            return RoundupRefusal(["below_threshold"])
        return _make_standing_members(target_mode)

    p1 = RoundupProducer(
        slug="roundup-slow-first",
        name="Slow first",
        kind="roundup",
        category="economics",
        section_title="First",
        footer="First",
        produce=_p1_prod,
    )
    p2 = RoundupProducer(
        slug="roundup-budget-target",
        name="Budget target",
        kind="roundup",
        category="politics",
        section_title="Second",
        footer="Second",
        produce=_p2_prod,
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p1.slug: p1, p2.slug: p2}
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    # Process A warms both at t0 -> holds 20-min-old copy of p2 locally.
    await evaluate_roundup_producer(p1, fake_session, now=t0)
    await evaluate_roundup_producer(p2, fake_session, now=t0)
    p2_local_old = _roundup_local_cache[(p2.slug, "live")]

    # Case A: Elsewhere at +18 min, Process B writes a 2-min-old copy of p2 to shared Redis.
    reset_roundup_cache_for_tests()
    target_mode = "2min-new"
    t18 = t0 + timedelta(minutes=18)
    clock[0] = t18.timestamp()
    await evaluate_roundup_producer(p2, fake_session, now=t18)

    # Restore Process A's 20-min-old local copy; at +20 min, p1 exhausts stage_budget_seconds.
    _roundup_local_cache[(p2.slug, "live")] = p2_local_old
    slow_first = True
    t20 = t0 + timedelta(minutes=20)
    clock[0] = t20.timestamp()
    placed_newer = await add_roundup_feed_items(
        fake_session,
        _ordinary_deck(),
        budget_seconds=0.03,
        stage_budget_seconds=0.03,
        now=t20,
    )
    assert p2.slug in _roundup_slugs_in(placed_newer)
    assert "2min-new" in (_roundup_title_for(placed_newer, p2.slug) or "")

    # Case B: Elsewhere at +18 min, p2 is properly withdrawn (refused).
    reset_roundup_cache_for_tests()
    target_mode = "refuse"
    clock[0] = t18.timestamp()
    fi_w, cp_w = await evaluate_roundup_producer(p2, fake_session, now=t18, force_refresh=True)
    assert fi_w is None and cp_w is None

    _roundup_local_cache[(p2.slug, "live")] = p2_local_old
    clock[0] = t20.timestamp()
    placed_withdrawn = await add_roundup_feed_items(
        fake_session,
        _ordinary_deck(),
        budget_seconds=0.03,
        stage_budget_seconds=0.03,
        now=t20,
    )
    assert p2.slug not in _roundup_slugs_in(placed_withdrawn)

    # Case C: Shared store read fails/times out on the budget-exhausted branch -> keep nothing.
    class _ErrRes:
        is_ok = False
        value = None

    async def _bounded_err(_fn: Any, **_kwargs: Any) -> _ErrRes:
        return _ErrRes()

    monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _bounded_err)
    _roundup_local_cache[(p2.slug, "live")] = p2_local_old
    placed_err = await add_roundup_feed_items(
        fake_session,
        _ordinary_deck(),
        budget_seconds=0.03,
        stage_budget_seconds=0.03,
        now=t20,
    )
    assert p2.slug not in _roundup_slugs_in(placed_err)


@pytest.mark.asyncio
async def test_machinery_grouping_with_kept_last_good_copy_is_not_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#13184 rebase rule: a machinery grouping whose last good copy was kept does NOT trip five-or-none."""
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    fail_last = False

    def _make_mach_prod(idx: int) -> RoundupProducer:
        slug = f"machinery-test-{idx}"

        async def _prod(_db: Any) -> Any:
            if idx == 5 and fail_last:
                await asyncio.sleep(0.25)
                return None
            return RoundupMembers(
                members=[
                    {"id": 91000 + idx * 10 + 1, "name": f"M{idx} A", "top_outcome": "Yes", "probability": 0.6, "status": "open"},
                    {"id": 91000 + idx * 10 + 2, "name": f"M{idx} B", "top_outcome": "No", "probability": 0.4, "status": "open"},
                ],
                title=f"Grouping {idx}",
                footer="",
                machinery_card={
                    "slug": slug,
                    "form_id": "contender_spotlight",
                    "kicker": "TEST",
                    "title": f"Grouping {idx}",
                    "subtitle": "",
                    "footer": "",
                    "destination_href": f"/collections/{slug}",
                    "section_count": 2,
                    "rows": [],
                },
            )

        return RoundupProducer(
            slug=slug,
            name=f"Grouping {idx}",
            kind="roundup",
            category="politics",
            section_title="Items",
            footer="",
            produce=_prod,
            enabled=lambda: True,
        )

    prods = {f"machinery-test-{i}": _make_mach_prod(i) for i in range(1, 6)}
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", prods)

    db = _RollbackSession()
    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    # Warm all 5 groupings.
    warm = await add_roundup_feed_items(
        db, _ordinary_deck(), now=t0, include_machinery=True, machinery_only=True
    )
    assert len(_roundup_slugs_in(warm)) == 5

    # Past 300s fresh TTL (within 1800s keep-time), #5 times out -> kept copy means NOT incomplete -> all 5 served!
    fail_last = True
    t1 = t0 + timedelta(seconds=420)
    # Force evaluate_roundup_producer to miss stale inside evaluate by testing exception on #5
    # (note allow_stale=True returns stale inside evaluate; test the error path via RuntimeError when cache expired isn't hit,
    # and test timeout when local cache is warm but evaluate times out).
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S", 60.0
    )
    placed = await add_roundup_feed_items(
        db, _ordinary_deck(), now=t1, include_machinery=True, machinery_only=True
    )
    assert len(_roundup_slugs_in(placed)) == 5


@pytest.mark.asyncio
async def test_nothing_to_show_splits_from_dropped_no_copy_across_timeout_error_and_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item 8: a round-up that cleanly had nothing to show must NOT inflate dropped_no_copy."""
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
    )

    t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    clock = [t0.timestamp()]
    fake_redis = _ExpiringFakeRedis(clock)
    _wire_fake_redis(monkeypatch, fake_redis)

    mode = "empty"

    async def _produce_empty_then_fail(_db: Any) -> Any:
        if mode == "empty":
            return RoundupRefusal((("standing", "no_qualifying_events"),))
        if mode == "timeout":
            await asyncio.sleep(0.25)
            return None
        raise RuntimeError("transient db error")

    p_quiet = RoundupProducer(
        slug="roundup-quiet-offseason",
        name="Offseason round-up",
        kind="roundup",
        category="sports",
        section_title="Games",
        footer="",
        produce=_produce_empty_then_fail,
    )

    async def _produce_cold_timeout(_db: Any) -> Any:
        await asyncio.sleep(0.25)
        return None

    p_lost = RoundupProducer(
        slug="roundup-actually-lost",
        name="Cold lost round-up",
        kind="roundup",
        category="economics",
        section_title="Markets",
        footer="",
        produce=_produce_cold_timeout,
    )

    fake_session = MagicMock(spec=AsyncSession)
    fake_session.rollback = AsyncMock()

    # 1. Warm p_quiet as cleanly empty at t0 -> stores nothing_to_show=True in local & Redis.
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {p_quiet.slug: p_quiet}
    )
    fi0, cp0 = await evaluate_roundup_producer(p_quiet, fake_session, now=t0)
    assert fi0 is None and cp0 is None
    stored = json.loads(fake_redis._store[_redis_cache_key(p_quiet.slug)][0])
    assert stored.get("nothing_to_show") is True
    assert stored.get("clean_empty") is not True  # distinct from worker-only machinery clean_empty

    # 2. Timeout past 60s fresh TTL (local cache hit) -> had_nothing_to_show=1, dropped_no_copy=0, failed=0!
    mode = "timeout"
    t1 = t0 + timedelta(seconds=120)
    clock[0] = t1.timestamp()
    await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t1)
    stats1 = get_roundup_read_failure_stats_10m(now=t1)
    assert stats1["had_nothing_to_show"] == 1
    assert stats1["dropped_no_copy"] == 0
    assert stats1["failed"] == 0

    # 3. Cold web dyno (local cache cleared) sees nothing_to_show from Redis on error -> still dropped_no_copy=0!
    reset_roundup_cache_for_tests()
    mode = "error"
    t2 = t0 + timedelta(seconds=180)
    clock[0] = t2.timestamp()
    await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t2)
    stats2 = get_roundup_read_failure_stats_10m(now=t2)
    assert stats2["had_nothing_to_show"] == 1
    assert stats2["dropped_no_copy"] == 0
    assert stats2["failed"] == 0

    # 4. Budget exhausted on p_quiet (with p_lost burning budget first) ->
    #    p_lost actually lost a card (dropped_no_copy=1, failed=1) while p_quiet records had_nothing_to_show=1!
    reset_roundup_cache_for_tests()
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
        {p_lost.slug: p_lost, p_quiet.slug: p_quiet},
    )
    t3 = t0 + timedelta(seconds=240)
    clock[0] = t3.timestamp()
    await add_roundup_feed_items(
        fake_session,
        _ordinary_deck(),
        budget_seconds=0.04,
        stage_budget_seconds=0.04,
        now=t3,
    )
    stats3 = get_roundup_read_failure_stats_10m(now=t3)
    assert stats3["dropped_no_copy"] == 1
    assert stats3["failed"] == 1
    assert stats3["had_nothing_to_show"] == 1


class TestTimeoutRefusalDoesNotPoisonSharedRedisAndReChecksLive:
    """#11259: a web dyno timing out must keep serving the last good copy, never
    overwrite shared Redis with a ``(None, None)`` refusal, re-check live Redis
    when prefetch missed or held an expired copy, and allow a newer valid shared
    copy to supersede its local cooldown.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("prefetch_state", ["missing", "expired"])
    async def test_timeout_rechecks_live_redis_when_prefetch_missed_or_expired(
        self,
        monkeypatch: pytest.MonkeyPatch,
        prefetch_state: str,
    ) -> None:
        reset_roundup_cache_for_tests()
        monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
        )

        t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        clock = [t0.timestamp()]
        fake_redis = _ExpiringFakeRedis(clock)
        _wire_fake_redis(monkeypatch, fake_redis)

        mode = "warm"

        async def _produce(_db: Any) -> Any:
            if mode == "hang_and_worker_writes":
                # Simulate worker-realtime finishing its pre-warm while the web
                # request is waiting on Postgres before hitting timeout.
                await _publish_worker_copy()
                await asyncio.sleep(0.25)
                return None
            return _make_standing_members(f"live-{mode}", live_event=True)

        producer = RoundupProducer(
            slug="roundup-closest-games-tonight",
            name="The closest games tonight",
            kind="roundup",
            category="sports",
            section_title="The 4 closest games",
            footer="4 games",
            produce=_produce,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {producer.slug: producer},
        )

        fake_session = MagicMock(spec=AsyncSession)
        fake_session.rollback = AsyncMock()

        if prefetch_state == "expired":
            # Populate Redis at t0 with a live copy whose keep-time (300s) has
            # already expired at t_read, while MGET still sees the expired blob.
            fi_old, cp_old = await evaluate_roundup_producer(
                producer, fake_session, now=t0
            )
            assert fi_old is not None and cp_old is not None
            # Bypass Redis TTL eviction by storing an expired-keep entry directly.
            rkey = _redis_cache_key(producer.slug)
            old_raw = json.loads(fake_redis._store[rkey][0])
            old_raw["built_at"] = (t0 - timedelta(seconds=600)).timestamp()
            fake_redis._store[rkey] = (json.dumps(old_raw), clock[0] + 3600)
            reset_roundup_cache_for_tests()
        else:
            reset_roundup_cache_for_tests()

        t_read = t0 + timedelta(seconds=60)
        clock[0] = t_read.timestamp()
        mode = "hang_and_worker_writes"

        # Because worker-realtime writes at clock[0] during _produce, clear the
        # web process's local cache via a separate publish helper that only
        # populates Redis rather than pre-seeding the same process's local dict.
        async def _publish_worker_copy_redis_only() -> None:
            saved = fake_redis._store.get(_redis_cache_key(producer.slug))
            p_worker = RoundupProducer(
                slug=producer.slug,
                name=producer.name,
                kind=producer.kind,
                category=producer.category,
                section_title=producer.section_title,
                footer=producer.footer,
                produce=lambda _db: _make_standing_members(
                    "worker-fresh", live_event=True
                ),
            )
            await evaluate_roundup_producer(
                p_worker,
                fake_session,
                now=clock[0],
                force_refresh=True,
            )
            # Clear web-dyno local cache so recovery MUST re-read live Redis.
            from app.utils.roundup_containers import _roundup_local_cache

            _roundup_local_cache.pop((producer.slug, "live"), None)
            _ = saved

        async def _produce_with_bg_worker(_db: Any) -> Any:
            await _publish_worker_copy_redis_only()
            await asyncio.sleep(0.25)
            return None

        producer_hanging = RoundupProducer(
            slug=producer.slug,
            name=producer.name,
            kind=producer.kind,
            category=producer.category,
            section_title=producer.section_title,
            footer=producer.footer,
            produce=_produce_with_bg_worker,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {producer_hanging.slug: producer_hanging},
        )

        placed = await add_roundup_feed_items(
            fake_session, _ordinary_deck(), now=t_read
        )
        assert _roundup_slugs_in(placed) == [producer.slug]
        assert "worker-fresh" in (_roundup_title_for(placed, producer.slug) or "")
        stats = get_roundup_read_failure_stats_10m(now=t_read)
        assert stats["kept_last_good"] == 1
        assert stats["dropped_no_copy"] == 0

    @pytest.mark.asyncio
    async def test_timeout_refusal_is_local_only_and_superseded_by_newer_shared_copy(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.utils.roundup_containers import (
            _cache_roundup_timeout_refusal,
            _roundup_local_cache,
        )

        reset_roundup_cache_for_tests()
        monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
        )

        t0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        clock = [t0.timestamp()]
        fake_redis = _ExpiringFakeRedis(clock)
        _wire_fake_redis(monkeypatch, fake_redis)

        produce_calls = 0

        async def _produce(_db: Any) -> Any:
            nonlocal produce_calls
            produce_calls += 1
            await asyncio.sleep(0.25)
            return None

        producer = RoundupProducer(
            slug="roundup-closest-games-tonight",
            name="The closest games tonight",
            kind="roundup",
            category="sports",
            section_title="The 4 closest games",
            footer="4 games",
            produce=_produce,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {producer.slug: producer},
        )

        fake_session = MagicMock(spec=AsyncSession)
        fake_session.rollback = AsyncMock()

        # 1. Cold timeout with empty Redis drops once and sets local cooldown ONLY;
        #    shared Redis is untouched (never poisoned with a 6h None tombstone).
        placed_0 = await add_roundup_feed_items(fake_session, _ordinary_deck(), now=t0)
        assert _roundup_slugs_in(placed_0) == []
        assert produce_calls == 1
        assert _roundup_local_cache[(producer.slug, "live")] == (
            t0.timestamp(),
            None,
            None,
        )
        assert _redis_cache_key(producer.slug) not in fake_redis._store
        assert get_roundup_read_failure_stats_10m(now=t0)["dropped_no_copy"] == 1

        # Calling _cache_roundup_timeout_refusal directly never overwrites a valid
        # local copy either.
        _roundup_local_cache[(producer.slug, "live")] = (
            t0.timestamp(),
            {"type": "bundle"},
            {"slug": producer.slug},
        )
        await _cache_roundup_timeout_refusal(producer, fake_session, ts=clock[0])
        assert _roundup_local_cache[(producer.slug, "live")][1] is not None
        _roundup_local_cache[(producer.slug, "live")] = (
            t0.timestamp(),
            None,
            None,
        )

        # 2. Within 60s local cooldown while shared Redis is still empty, Postgres
        #    is NOT hammered again.
        t_10s = t0 + timedelta(seconds=10)
        clock[0] = t_10s.timestamp()
        placed_10 = await add_roundup_feed_items(
            fake_session, _ordinary_deck(), now=t_10s
        )
        assert _roundup_slugs_in(placed_10) == []
        assert produce_calls == 1

        # 3. Still inside the 60s local cooldown, another dyno / pre-warmer writes
        #    a valid copy to shared Redis at t0 + 15s.
        t_15s = t0 + timedelta(seconds=15)
        clock[0] = t_15s.timestamp()
        saved_local = _roundup_local_cache.pop((producer.slug, "live"), None)
        p_worker = RoundupProducer(
            slug=producer.slug,
            name=producer.name,
            kind=producer.kind,
            category=producer.category,
            section_title=producer.section_title,
            footer=producer.footer,
            produce=lambda _db: _make_standing_members("worker-v2", live_event=True),
        )
        await evaluate_roundup_producer(
            p_worker, fake_session, now=t_15s, force_refresh=True
        )
        # Restore the web dyno's stale local (None, None) cooldown.
        assert saved_local is not None
        _roundup_local_cache[(producer.slug, "live")] = saved_local

        # 4. Next read at t0 + 20s immediately sees the newer shared Redis copy!
        t_20s = t0 + timedelta(seconds=20)
        clock[0] = t_20s.timestamp()
        placed_20 = await add_roundup_feed_items(
            fake_session, _ordinary_deck(), now=t_20s
        )
        assert _roundup_slugs_in(placed_20) == [producer.slug]
        assert "worker-v2" in (_roundup_title_for(placed_20, producer.slug) or "")
        assert produce_calls == 1
