"""Tests for set-page SWR (<30 min), singleflight, failure preservation, and Discover parity (#13475)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import roundup_containers as rc
from app.utils.roundup_containers import (
    ROUNDUP_PAGE_SWR_MAX_AGE_S,
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    _roundup_bg_refresh_tasks,
    _roundup_local_cache,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
    serve_roundup,
)

T0 = datetime(2026, 11, 23, 6, 0, 0, tzinfo=timezone.utc)


class _FakeAsyncSession(AsyncSession):
    """Minimal AsyncSession subclass for unit tests without a DB engine."""

    def __init__(self) -> None:  # noqa: D107 — skip AsyncSession engine setup
        pass


class _FakeAsyncCM:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _install_fake_redis(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    redis_store: dict[str, str] = {}

    class _FakeRedis:
        async def get(self, key: str) -> str | None:
            return redis_store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            redis_store[key] = value
            return True

        async def hset(self, *_args: Any, **_kwargs: Any) -> int:
            return 1

        async def hdel(self, *_args: Any, **_kwargs: Any) -> int:
            return 0

        async def expire(self, *_args: Any, **_kwargs: Any) -> bool:
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

    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setattr("app.utils.request_cache.get_shared_async_redis", _get_redis)
    monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _bounded)
    return redis_store


def _make_non_live_members(label: str, probability: float = 0.62) -> RoundupMembers:
    return RoundupMembers(
        members=[
            {
                "id": 91001,
                "name": f"Fed Cut Path ({label})",
                "top_outcome": "25 bps",
                "probability": probability,
                "status": "open",
            },
            {
                "id": 91002,
                "name": f"US Recession 2027 ({label})",
                "top_outcome": "No",
                "probability": round(1.0 - probability, 4),
                "status": "open",
            },
        ],
        title=f"Fed & U.S. Macro ({label})",
        footer="Macro markets",
    )


def _make_live_members(label: str) -> RoundupMembers:
    return RoundupMembers(
        members=[
            {
                "type": "event",
                "id": 77101,
                "destination": "/events/77101",
                "event_id": 77101,
                "card": {
                    "id": 77101,
                    "name": f"Live Bowl ({label})",
                    "status": "live",
                    "home_team": "Home",
                    "away_team": "Away",
                    "home_prob": 0.61,
                },
            }
        ],
        title=f"Live Slate ({label})",
        footer="Live game",
    )


def _make_imminent_members(label: str, commence_at: datetime) -> RoundupMembers:
    return RoundupMembers(
        members=[
            {
                "type": "event",
                "id": 77102,
                "destination": "/events/77102",
                "event_id": 77102,
                "card": {
                    "id": 77102,
                    "name": f"Imminent Game ({label})",
                    "status": "scheduled",
                    "commence_time": commence_at.isoformat(),
                    "home_team": "Home",
                    "away_team": "Away",
                    "home_prob": 0.55,
                },
            }
        ],
        title=f"Imminent Slate ({label})",
        footer="Starts soon",
    )


def _member_prob(payload: dict[str, Any]) -> float:
    return float(payload["sections"][0]["members"][0]["card"]["probability"])


def _feed_card_title(feed_item: dict[str, Any]) -> str:
    return str(feed_item.get("headline") or feed_item["data"]["title"])


async def _drain_bg_tasks() -> None:
    pending = [t for t in _roundup_bg_refresh_tasks.values() if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_reader_never_waits_when_copy_under_30_minutes_exists_l0_and_cold_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        lambda _db, cards, *_a, **_kw: asyncio.sleep(0, result=cards),
    )

    version = {"val": "v1", "prob": 0.61}
    calls = 0
    bg_started = asyncio.Event()
    allow_bg_finish = asyncio.Event()
    block_builds = {"active": False}

    async def _produce(_db: Any) -> RoundupMembers:
        nonlocal calls
        calls += 1
        if block_builds["active"]:
            bg_started.set()
            await allow_bg_finish.wait()
        return _make_non_live_members(version["val"], version["prob"])

    producer = RoundupProducer(
        slug="machinery-fed-and-macro",
        name="Fed & U.S. Macro",
        kind="roundup",
        category="economics",
        section_title="Macro",
        footer="Macro",
        produce=_produce,
    )
    monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    db = _FakeAsyncSession()
    monkeypatch.setattr(rc, "_open_roundup_bg_session", lambda: _FakeAsyncCM(_FakeAsyncSession()))

    # 1. Seed fresh v1 at T0 (both L0 and Redis).
    await serve_roundup(producer.slug, db, include_children=False, now=T0)
    assert calls == 1

    # 2. Reader arrives at T0 + 600s (> 300s fresh TTL, < 1800s SWR bound) on L0.
    version.update({"val": "v2", "prob": 0.74})
    block_builds["active"] = True
    t_stale = T0 + timedelta(seconds=600)
    served_l0 = await asyncio.wait_for(
        serve_roundup(producer.slug, db, include_children=False, now=t_stale),
        timeout=0.3,
    )
    assert "v1" in served_l0["container"]["name"]
    assert _member_prob(served_l0) == pytest.approx(0.61)

    await asyncio.wait_for(bg_started.wait(), timeout=0.5)
    allow_bg_finish.set()
    await _drain_bg_tasks()
    assert calls == 2

    # Next read sees refreshed v2 from cache with no additional build.
    served_after_l0 = await serve_roundup(producer.slug, db, include_children=False, now=t_stale)
    assert "v2" in served_after_l0["container"]["name"]
    assert _member_prob(served_after_l0) == pytest.approx(0.74)
    assert calls == 2

    # 3. Cold-process test: drop L0, advance clock to T0 + 1200s (age 600s > 300s, < 1800s) -> Redis SWR hit.
    _roundup_local_cache.clear()
    bg_started.clear()
    allow_bg_finish.clear()
    version.update({"val": "v3", "prob": 0.83})
    t_cold = T0 + timedelta(seconds=1200)
    served_redis = await asyncio.wait_for(
        serve_roundup(producer.slug, db, include_children=False, now=t_cold),
        timeout=0.3,
    )
    assert "v2" in served_redis["container"]["name"]
    assert _member_prob(served_redis) == pytest.approx(0.74)

    await asyncio.wait_for(bg_started.wait(), timeout=0.5)
    allow_bg_finish.set()
    await _drain_bg_tasks()
    assert calls == 3

    _roundup_local_cache.clear()
    served_after_redis = await serve_roundup(producer.slug, db, include_children=False, now=t_cold)
    assert "v3" in served_after_redis["container"]["name"]
    assert _member_prob(served_after_redis) == pytest.approx(0.83)
    assert calls == 3


@pytest.mark.asyncio
async def test_simultaneous_readers_share_one_rebuild_swr_and_cold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        lambda _db, cards, *_a, **_kw: asyncio.sleep(0, result=cards),
    )

    calls = 0
    ver = {"val": "cold-v1", "prob": 0.55}
    gate = asyncio.Event()
    gate_enabled = {"on": True}

    async def _produce(_db: Any) -> RoundupMembers:
        nonlocal calls
        calls += 1
        if gate_enabled["on"]:
            await asyncio.sleep(0.03)
            await gate.wait()
        return _make_non_live_members(ver["val"], ver["prob"])

    producer = RoundupProducer(
        slug="machinery-concurrent-set",
        name="Concurrent Set",
        kind="roundup",
        category="economics",
        section_title="Macro",
        footer="Macro",
        produce=_produce,
    )
    monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    monkeypatch.setattr(rc, "_open_roundup_bg_session", lambda: _FakeAsyncCM(_FakeAsyncSession()))

    # A. Simultaneous genuine cold misses -> singleflight shares 1 DB build.
    gate.set()
    cold_results = await asyncio.gather(
        *(
            serve_roundup(producer.slug, _FakeAsyncSession(), include_children=False, now=T0)
            for _ in range(5)
        )
    )
    assert calls == 1
    assert all("cold-v1" in r["container"]["name"] for r in cold_results)

    # B. 10 simultaneous readers under 30 min (T0 + 600s) -> return kept copy immediately & spawn 1 bg rebuild.
    ver.update({"val": "swr-v2", "prob": 0.71})
    gate.clear()
    swr_results = await asyncio.wait_for(
        asyncio.gather(
            *(
                serve_roundup(
                    producer.slug,
                    _FakeAsyncSession(),
                    include_children=False,
                    now=T0 + timedelta(seconds=600),
                )
                for _ in range(10)
            )
        ),
        timeout=0.3,
    )
    assert len(swr_results) == 10
    assert all("cold-v1" in r["container"]["name"] for r in swr_results)
    assert len(_roundup_bg_refresh_tasks) == 1
    gate.set()
    await _drain_bg_tasks()
    assert calls == 2

    # C. Simultaneous readers past 30 min (age 1805s) -> singleflight shares 1 inline rebuild.
    ver.update({"val": "expired-v3", "prob": 0.88})
    t_over = T0 + timedelta(seconds=600 + 1805)
    over_results = await asyncio.gather(
        *(
            serve_roundup(producer.slug, _FakeAsyncSession(), include_children=False, now=t_over)
            for _ in range(5)
        )
    )
    assert calls == 3
    assert all("expired-v3" in r["container"]["name"] for r in over_results)


@pytest.mark.asyncio
async def test_failed_rebuild_keeps_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_roundup_cache_for_tests()
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        lambda _db, cards, *_a, **_kw: asyncio.sleep(0, result=cards),
    )

    mode = {"val": "ok"}

    async def _produce(_db: Any) -> Any:
        if mode["val"] == "raise":
            raise RuntimeError("db query timed out")
        if mode["val"] == "transient":
            return RoundupRefusal(("source_unavailable:timeout",))
        return _make_non_live_members("kept-v1", 0.64)

    producer = RoundupProducer(
        slug="machinery-fail-keep",
        name="Fail Keep Set",
        kind="roundup",
        category="economics",
        section_title="Macro",
        footer="Macro",
        produce=_produce,
    )
    monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    db = _FakeAsyncSession()
    monkeypatch.setattr(rc, "_open_roundup_bg_session", lambda: _FakeAsyncCM(_FakeAsyncSession()))

    await serve_roundup(producer.slug, db, include_children=False, now=T0)

    # 1. Background rebuild raises -> copy survives in L0 & Redis.
    mode["val"] = "raise"
    t1 = T0 + timedelta(seconds=600)
    res1 = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    assert "kept-v1" in res1["container"]["name"]
    await _drain_bg_tasks()

    _roundup_local_cache.clear()
    res1_cold = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    assert "kept-v1" in res1_cold["container"]["name"]
    await _drain_bg_tasks()

    # 2. Background rebuild returns transient refusal -> copy survives too.
    mode["val"] = "transient"
    res2 = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    assert "kept-v1" in res2["container"]["name"]
    await _drain_bg_tasks()

    _roundup_local_cache.clear()
    res2_cold = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    assert "kept-v1" in res2_cold["container"]["name"]
    await _drain_bg_tasks()


@pytest.mark.asyncio
async def test_page_and_discover_card_agree_when_from_same_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        lambda _db, cards, *_a, **_kw: asyncio.sleep(0, result=cards),
    )

    state = {"label": "v1", "prob": 0.58}
    allow_refresh = asyncio.Event()
    gate = {"block": False}

    async def _produce(_db: Any) -> RoundupMembers:
        if gate["block"]:
            await allow_refresh.wait()
        return _make_non_live_members(state["label"], state["prob"])

    producer = RoundupProducer(
        slug="machinery-parity-set",
        name="Parity Set",
        kind="roundup",
        category="economics",
        section_title="Macro",
        footer="Macro",
        produce=_produce,
    )
    monkeypatch.setattr(rc, "ROUNDUP_PRODUCERS", {producer.slug: producer})
    db = _FakeAsyncSession()
    monkeypatch.setattr(rc, "_open_roundup_bg_session", lambda: _FakeAsyncCM(_FakeAsyncSession()))

    # Seed v1 into Redis at T0, then simulate fresh cold web process at T0 + 600s.
    await evaluate_roundup_producer(producer, db, now=T0)
    _roundup_local_cache.clear()

    state.update({"label": "v2", "prob": 0.79})
    gate["block"] = True
    t1 = T0 + timedelta(seconds=600)

    page = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    fi_disc, cp_disc = await evaluate_roundup_producer(
        producer, db, now=t1, allow_stale=True
    )
    assert fi_disc is not None and cp_disc is not None
    assert page["container"]["name"] == cp_disc["container"]["name"]
    assert "v1" in _feed_card_title(fi_disc)
    assert _member_prob(page) == pytest.approx(_member_prob(cp_disc)) == pytest.approx(0.58)

    # Release the single background rebuild -> both page and Discover card reflect v2.
    allow_refresh.set()
    await _drain_bg_tasks()
    _roundup_local_cache.clear()
    page2 = await serve_roundup(producer.slug, db, include_children=False, now=t1)
    fi_disc2, cp_disc2 = await evaluate_roundup_producer(
        producer, db, now=t1, allow_stale=True
    )
    assert fi_disc2 is not None and cp_disc2 is not None
    assert page2["container"]["name"] == cp_disc2["container"]["name"]
    assert "v2" in _feed_card_title(fi_disc2)
    assert _member_prob(page2) == pytest.approx(_member_prob(cp_disc2)) == pytest.approx(0.79)


@pytest.mark.asyncio
async def test_boundary_over_30_minutes_live_imminent_and_withdrawal_tombstone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    _install_fake_redis(monkeypatch)
    monkeypatch.setattr(
        "app.utils.not_trading.drop_not_trading_roundup_members",
        lambda _db, cards, *_a, **_kw: asyncio.sleep(0, result=cards),
    )

    calls = 0
    mode = {"kind": "non_live", "label": "v1", "withdraw": False}

    async def _produce(_db: Any) -> Any:
        nonlocal calls
        calls += 1
        if mode["withdraw"]:
            return RoundupRefusal(("too_few_markets",))
        if mode["kind"] == "live":
            return _make_live_members(mode["label"])
        if mode["kind"] == "imminent":
            return _make_imminent_members(mode["label"], T0 + timedelta(seconds=120))
        return _make_non_live_members(mode["label"], 0.65)

    p_non_live = RoundupProducer(
        slug="machinery-boundary-30m",
        name="Boundary Set",
        kind="roundup",
        category="economics",
        section_title="Macro",
        footer="Macro",
        produce=_produce,
    )
    p_live = RoundupProducer(
        slug="machinery-live-set",
        name="Live Set",
        kind="roundup",
        category="sports",
        section_title="Games",
        footer="Games",
        produce=_produce,
    )
    p_imminent = RoundupProducer(
        slug="machinery-imminent-set",
        name="Imminent Set",
        kind="roundup",
        category="sports",
        section_title="Games",
        footer="Games",
        produce=_produce,
    )
    monkeypatch.setattr(
        rc,
        "ROUNDUP_PRODUCERS",
        {
            p_non_live.slug: p_non_live,
            p_live.slug: p_live,
            p_imminent.slug: p_imminent,
        },
    )
    db = _FakeAsyncSession()

    # 1. Exact 1800s boundary (>= 30 min) rebuilds synchronously inline, NOT SWR.
    await serve_roundup(p_non_live.slug, db, include_children=False, now=T0)
    mode["label"] = "v2-at-30m"
    res_30m = await serve_roundup(
        p_non_live.slug,
        db,
        include_children=False,
        now=T0 + timedelta(seconds=ROUNDUP_PAGE_SWR_MAX_AGE_S),
    )
    assert "v2-at-30m" in res_30m["container"]["name"]
    assert len(_roundup_bg_refresh_tasks) == 0

    # 2. Live set aged 90s (> 60s live TTL) rebuilds inline, NOT SWR.
    mode.update({"kind": "live", "label": "live-v1"})
    await serve_roundup(p_live.slug, db, include_children=False, now=T0)
    mode["label"] = "live-v2"
    res_live = await serve_roundup(
        p_live.slug,
        db,
        include_children=False,
        now=T0 + timedelta(seconds=90),
    )
    assert "live-v2" in res_live["container"]["name"]
    assert len(_roundup_bg_refresh_tasks) == 0

    # 3. Imminent set built 400s ago (>300s fresh TTL) whose tipoff is now 120s away rebuilds inline, NOT SWR.
    t_imm_seed = T0 - timedelta(seconds=400)
    mode.update({"kind": "imminent", "label": "imm-v1"})
    await serve_roundup(p_imminent.slug, db, include_children=False, now=t_imm_seed)
    mode["label"] = "imm-v2"
    res_imm = await serve_roundup(
        p_imminent.slug,
        db,
        include_children=False,
        now=T0,
    )
    assert "imm-v2" in res_imm["container"]["name"]
    assert len(_roundup_bg_refresh_tasks) == 0

    # 4. Newer withdrawal tombstone in Redis prevents resurrecting older local copy.
    t_w0 = T0 + timedelta(seconds=3000)
    t_w_tomb = T0 + timedelta(seconds=3400)
    t_w_read = T0 + timedelta(seconds=3600)
    mode.update({"kind": "non_live", "label": "alive-v1", "withdraw": False})
    await serve_roundup(p_non_live.slug, db, include_children=False, now=t_w0)
    saved_l0 = dict(_roundup_local_cache)
    mode["withdraw"] = True
    await evaluate_roundup_producer(
        p_non_live,
        db,
        now=t_w_tomb,
        force_refresh=True,
    )
    # Restore stale L0 entry from t_w0 (worker process that missed the withdrawal); Redis holds t_w_tomb tombstone.
    _roundup_local_cache.update(saved_l0)
    with pytest.raises(HTTPException) as exc_info:
        await serve_roundup(
            p_non_live.slug,
            db,
            include_children=False,
            now=t_w_read,
        )
    assert exc_info.value.status_code == 404
