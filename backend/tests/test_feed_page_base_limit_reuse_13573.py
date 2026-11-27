"""#13573: Cross-limit anonymous feed page-base reuse + deterministic deck-invariance pin.

Why this exists:
- Before this change, `FEED_PREWARM_SHAPES` kept `limit=50` and `limit=20`
  (plus `limit=200` for `include_futures=False`) warm in `feed_cache:pagebase:*`,
  while `apply_discover_display_chain` already builds the exact same ordered
  deck regardless of `limit` (`DISCOVER_COMPOSITION_WINDOW = 20`, #5101).
- Because `feed_page_base_cache_key` hashes `limit` into the key, any caller
  passing a non-prewarmed `limit` (e.g. `GET /api/feed?limit=5`, which spiked
  to `16.82 s` after #13825 while `limit=20` stayed `0.67 s`) missed every
  warm page base and rebuilt Discover from Postgres.
- Now `get_feed` falls back to prewarmed anonymous page bases from
  `feed_page_base_fallback_limits()` when its own `limit` key misses, slicing
  to the caller's exact `(limit, offset)` and honoring every freshness/prewarm/
  personalization guard unchanged.
- `test_display_chain_deck_invariance_matches_reuse_version` runs the real
  `apply_discover_display_chain` over a frozen deterministic candidate pool at
  `limit=5`, `limit=20`, and `limit=50` (Discover + Sports) and fails with
  `"bump the version"` if `limit` starts changing the built deck or the output
  drifts without bumping `FEED_PAGE_BASE_REUSE_VERSION`.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.encoders import jsonable_encoder
from httpx import ASGITransport

from app.main import app
from app.routes import feed as feed_route
from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.services.database import get_db
from app.utils import feed_collections as feed_collections_mod
from app.utils import request_cache as _rc
from app.utils import roundup_containers as roundup_mod
from app.utils import theme_collection_ref as theme_ref_mod
from app.utils.feed_cache import (
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_PAGE_BASE_REUSE_VERSION,
    FEED_PREWARM_SCOPE_KEY,
    FEED_RESPONSE_TTL_LIVE_SECONDS,
    feed_machinery_page_base_key,
    feed_page_base_cache_key,
    feed_page_base_fallback_limits,
)

FIXED_NOW = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)

# Pinned SHA-256 fingerprint per `FEED_PAGE_BASE_REUSE_VERSION` for the frozen
# deterministic candidate pool below across limit in (5, 20, 50).
PINNED_DECK_INVARIANCE_FINGERPRINTS: dict[int, str] = {
    1: "0eeee5acceebc78897540ff3b5a1809c0a2f148b163d431a67811fbcf1fe78e4",
}


def _candidate_futures(
    idx: int,
    *,
    score: float,
    category: str,
    name: str,
    days_out: int = 30,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": FIXED_NOW.timestamp() - idx,
        "headline": name,
        "reason": f"Market {idx}",
        "data": {
            "id": 1000 + idx,
            "name": name,
            "category": category.lower(),
            "llm_sport_category": category,
            "status": "open",
            "market_tier": 1,
            "volume": 50000 - idx * 500,
            "volume_24h": 12000 - idx * 100,
            "resolution_date": (FIXED_NOW + timedelta(days=days_out)).isoformat(),
            "outcomes": [
                {"id": 5000 + idx, "name": f"Outcome A {idx}", "probability": 0.42},
                {"id": 6000 + idx, "name": f"Outcome B {idx}", "probability": 0.31},
            ],
        },
    }


def _candidate_event(
    idx: int,
    *,
    score: float,
    status: str = "live",
    sport_key: str = "basketball_nba",
    hours_offset: float = -1.0,
) -> dict:
    commence = FIXED_NOW + timedelta(hours=hours_offset)
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": commence.timestamp(),
        "headline": f"Away {idx} at Home {idx}",
        "reason": "Close matchup",
        "data": {
            "id": 2000 + idx,
            "sport_key": sport_key,
            "status": status,
            "commence_time": commence.isoformat(),
            "home_team": f"Home {idx}",
            "away_team": f"Away {idx}",
            "home_team_id": 100 + idx,
            "away_team_id": 200 + idx,
            "home_probability": 0.52,
            "away_probability": 0.48,
            "excite_index": 78.0,
            "home_team_data": {"logo": "h.png"},
            "away_team_data": {"logo": "a.png"},
        },
    }


def _frozen_candidate_pool() -> list[dict]:
    items = [
        _candidate_event(1, score=92.0, status="live", sport_key="basketball_nba", hours_offset=-1.0),
        _candidate_event(2, score=84.0, status="scheduled", sport_key="americanfootball_nfl", hours_offset=2.0),
        _candidate_event(3, score=76.0, status="completed", sport_key="basketball_nba", hours_offset=-4.0),
    ]
    categories = ("politics", "sports", "entertainment", "economics", "weather", "tech")
    for i in range(1, 25):
        items.append(
            _candidate_futures(
                i,
                score=96.0 - i,
                category=categories[i % len(categories)],
                name=f"Championship Question {i}",
                days_out=10 + i,
            )
        )
    return items


def _fingerprint(obj: object) -> str:
    canonical = json.dumps(
        jsonable_encoder(obj),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_decks_by_limit(monkeypatch) -> dict[str, dict[int, list[dict]]]:
    monkeypatch.setenv("DISCOVER_GAME_NEEDS_REASON", "false")
    out: dict[str, dict[int, list[dict]]] = {"discover": {}, "sports": {}}
    for lim in (5, 20, 50):
        disc_deck, _ = apply_discover_display_chain(
            [dict(it) for it in _frozen_candidate_pool()],
            limit=lim,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            include_events=True,
            my_teams_only=False,
            sports_mode=False,
            now=FIXED_NOW,
        )
        sports_deck, _ = apply_discover_display_chain(
            [dict(it) for it in _frozen_candidate_pool()],
            limit=lim,
            ctx=PersonalizationContext(),
            event_pct=None,
            include_events=True,
            my_teams_only=False,
            sports_mode=True,
            now=FIXED_NOW,
        )
        out["discover"][lim] = disc_deck
        out["sports"][lim] = sports_deck
    return out


def _assert_version_matches_fingerprint(
    version: int,
    decks_by_mode: dict[str, dict[int, list[dict]]],
    pinned: dict[int, str] | None = None,
) -> None:
    disc_fps = {lim: _fingerprint(deck) for lim, deck in decks_by_mode["discover"].items()}
    sports_fps = {lim: _fingerprint(deck) for lim, deck in decks_by_mode["sports"].items()}
    assert len(set(disc_fps.values())) == 1, (
        f"Discover deck order/membership depends on `limit` ({disc_fps}) "
        f"while FEED_PAGE_BASE_REUSE_VERSION={version} — bump the version."
    )
    assert len(set(sports_fps.values())) == 1, (
        f"Sports deck order/membership depends on `limit` ({sports_fps}) "
        f"while FEED_PAGE_BASE_REUSE_VERSION={version} — bump the version."
    )
    table = PINNED_DECK_INVARIANCE_FINGERPRINTS if pinned is None else pinned
    expected = table.get(version)
    actual = _fingerprint({"discover": decks_by_mode["discover"][50], "sports": decks_by_mode["sports"][50]})
    assert expected is not None, (
        f"Missing pinned fingerprint for FEED_PAGE_BASE_REUSE_VERSION={version} (got {actual})"
    )
    assert actual == expected, (
        "Discover/Sports built deck drifted while FEED_PAGE_BASE_REUSE_VERSION stayed at "
        f"{version} (expected {expected}, got {actual}) — bump the version."
    )


def test_fallback_limits_helper():
    assert feed_page_base_fallback_limits(limit=5) == (50, 20)
    assert feed_page_base_fallback_limits(limit=10) == (50, 20)
    assert feed_page_base_fallback_limits(limit=20) == (50,)
    assert feed_page_base_fallback_limits(limit=50) == (20,)
    assert feed_page_base_fallback_limits(limit=40, include_futures=False, include_events=True) == (200,)
    assert feed_page_base_fallback_limits(limit=200, include_futures=False, include_events=True) == ()
    assert feed_page_base_fallback_limits(limit=5, include_futures=False, include_events=False) == ()


def test_display_chain_deck_invariance_matches_reuse_version(monkeypatch):
    decks = _build_decks_by_limit(monkeypatch)
    assert len(decks["discover"][50]) >= 10
    _assert_version_matches_fingerprint(FEED_PAGE_BASE_REUSE_VERSION, decks)


def test_fingerprint_guard_fails_with_bump_message_when_limit_diverges_without_bump(
    monkeypatch,
):
    decks = _build_decks_by_limit(monkeypatch)
    real_fp = _fingerprint({"discover": decks["discover"][50], "sports": decks["sports"][50]})
    pinned = {FEED_PAGE_BASE_REUSE_VERSION: real_fp}

    drifted = {
        "discover": {
            **decks["discover"],
            5: list(reversed(decks["discover"][5])),
        },
        "sports": decks["sports"],
    }
    with pytest.raises(AssertionError, match="bump the version"):
        _assert_version_matches_fingerprint(FEED_PAGE_BASE_REUSE_VERSION, drifted, pinned)


def _sample_base(*, n: int = 25, live: bool = False, built_at: float | None = None) -> dict:
    items = []
    for i in range(n):
        if i == 0 and live:
            items.append(
                {
                    "type": "event",
                    "headline": "Live Game",
                    "data": {"id": 900 + i, "status": "live", "home_team": "A", "away_team": "B"},
                }
            )
        else:
            items.append(
                {
                    "type": "futures",
                    "headline": f"Futures Card {i}",
                    "data": {"id": 7000 + i, "name": f"Futures Card {i}", "status": "open"},
                }
            )
    ts = time.time() if built_at is None else built_at
    return {
        "items": items,
        "total": len(items),
        FEED_PAGE_BASE_BUILT_AT_FIELD: ts,
    }


class _MemoryAsyncRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.reads: list[str] = []

    async def get(self, key: str):
        self.reads.append(key)
        return self.store.get(key)

    async def mget(self, keys):
        return [await self.get(k) for k in keys]

    async def setex(self, key: str, ttl: int, val: str):
        self.store[key] = val
        return True

    async def set(self, key: str, val: str, ex=None, nx: bool = False):
        if nx and key in self.store:
            return None
        self.store[key] = val
        return True


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


def _install_common_route_fakes(
    monkeypatch,
    redis_client: _MemoryAsyncRedis,
    *,
    opening_seating: bool = False,
):
    db_exec_calls: list[object] = []

    async def _fail_if_executed(*_a, **_kw):
        db_exec_calls.append(True)
        raise AssertionError("DB query should not run on fallback page-base hit")

    async def _dummy_db():
        yield SimpleNamespace(
            execute=_fail_if_executed,
            scalars=_fail_if_executed,
            scalar=_fail_if_executed,
            commit=AsyncMock(),
        )

    monkeypatch.setattr(feed_route, "_DISCOVER_OPENING_SEATING_SERVED", opening_seating)
    monkeypatch.setattr(feed_collections_mod, "feed_collections_enabled", lambda **_kw: False)
    monkeypatch.setattr(theme_ref_mod, "theme_collection_refs_enabled", lambda **_kw: False)
    monkeypatch.setattr(roundup_mod, "roundup_feed_enabled", lambda **_kw: False)
    monkeypatch.setattr("app.utils.discover_fun_tags.is_discover_fun_admission_enabled", lambda: False)
    monkeypatch.setattr(_rc, "get_shared_async_redis", AsyncMock(return_value=redis_client))
    monkeypatch.setattr(
        _rc,
        "schedule_background",
        lambda coro: coro.close() if hasattr(coro, "close") else None,
    )
    return _dummy_db, db_exec_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("opening_seating", [False, True])
async def test_get_feed_limit_5_reuses_warm_limit_50_page_base_without_db_build(
    monkeypatch, opening_seating
):
    _reset_rc()
    rc = _MemoryAsyncRedis()
    built_at = time.time() - 12.0
    base_50_key = feed_page_base_cache_key(
        limit=50,
        event_pct=0.15,
        opening_seating=opening_seating,
    )
    rc.store[base_50_key] = json.dumps(_sample_base(n=25, built_at=built_at))

    dummy_db, db_calls = _install_common_route_fakes(
        monkeypatch, rc, opening_seating=opening_seating
    )
    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dummy_db
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for req_limit in (5, 10, 25):
                resp = await client.get(f"/api/feed?limit={req_limit}")
                assert resp.status_code == 200, resp.text
                assert resp.headers["x-feed-cache"] == "page_base_hit"
                body = resp.json()
                assert body["limit"] == req_limit
                assert body["offset"] == 0
                assert len(body["items"]) == req_limit
                assert body["total"] == 25
                assert body["has_more"] is (req_limit < 25)
                assert abs(body["cache"]["built_at"] - built_at) < 0.01
    finally:
        app.dependency_overrides = prior_overrides
        _reset_rc()

    assert db_calls == []


@pytest.mark.asyncio
async def test_get_feed_limit_5_machinery_reuses_limit_50_machinery_page_base(monkeypatch):
    _reset_rc()
    rc = _MemoryAsyncRedis()
    base_50_key = feed_page_base_cache_key(limit=50, event_pct=0.15, opening_seating=False)
    mach_50_key = feed_machinery_page_base_key(base_50_key)
    rc.store[mach_50_key] = json.dumps(_sample_base(n=22, built_at=time.time() - 8.0))

    dummy_db, db_calls = _install_common_route_fakes(monkeypatch, rc, opening_seating=False)
    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dummy_db
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/feed?limit=5&machinery=1")
            assert resp.status_code == 200, resp.text
            assert resp.headers["x-feed-cache"] == "page_base_hit"
            body = resp.json()
            assert body["limit"] == 5
            assert body["total"] == 22
            assert len(body["items"]) == 5
            assert body["has_more"] is True
    finally:
        app.dependency_overrides = prior_overrides
        _reset_rc()

    assert db_calls == []


@pytest.mark.asyncio
async def test_get_feed_events_only_reuses_limit_200_page_base(monkeypatch):
    _reset_rc()
    rc = _MemoryAsyncRedis()
    stale_200_key = f"{feed_page_base_cache_key(limit=200, include_events=True, include_futures=False)}:stale"
    rc.store[stale_200_key] = json.dumps(_sample_base(n=60, built_at=time.time() - 10.0))

    dummy_db, db_calls = _install_common_route_fakes(monkeypatch, rc, opening_seating=False)
    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dummy_db
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/feed?limit=40&include_futures=false")
            assert resp.status_code == 200, resp.text
            assert resp.headers["x-feed-cache"] == "page_base_stale_hit"
            body = resp.json()
            assert body["limit"] == 40
            assert body["total"] == 60
            assert len(body["items"]) == 40
            assert body["has_more"] is True
    finally:
        app.dependency_overrides = prior_overrides
        _reset_rc()

    assert db_calls == []


@pytest.mark.asyncio
async def test_live_ceiling_still_refuses_aged_out_fallback_page_base(monkeypatch):
    _reset_rc()
    rc = _MemoryAsyncRedis()
    # Live payload older than live ceiling (FEED_RESPONSE_STALE_TTL_LIVE_SECONDS = 60s)
    expired_age = max(120, FEED_RESPONSE_TTL_LIVE_SECONDS + 90)
    stale_50_key = f"{feed_page_base_cache_key(limit=50, event_pct=0.15)}:stale"
    rc.store[stale_50_key] = json.dumps(_sample_base(n=20, live=True, built_at=time.time() - expired_age))

    build_reached: list[bool] = []
    empty_res = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []), all=lambda: [], scalar=lambda: 0)

    async def _db_reached(*_a, **_kw):
        build_reached.append(True)
        return empty_res

    async def _dummy_db():
        yield SimpleNamespace(execute=_db_reached, scalars=_db_reached, scalar=_db_reached)

    _install_common_route_fakes(monkeypatch, rc, opening_seating=False)
    monkeypatch.setattr(feed_route, "_score_events", AsyncMock(side_effect=lambda *_a, **_kw: build_reached.append(True) or []))
    monkeypatch.setattr(feed_route, "_score_futures", AsyncMock(return_value=[]))
    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _dummy_db
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/feed?limit=5")
            assert resp.status_code == 200
            assert resp.headers["x-feed-cache"] == "miss"
    finally:
        app.dependency_overrides = prior_overrides
        _reset_rc()

    assert stale_50_key in rc.reads
    assert build_reached, "aged-out live fallback page base must be refused and trigger cold build"


@pytest.mark.asyncio
async def test_guards_keep_prewarm_my_teams_personalized_and_disabled_off_fallback_base(monkeypatch):
    _reset_rc()
    rc = _MemoryAsyncRedis()
    stale_50_key = f"{feed_page_base_cache_key(limit=50, event_pct=0.15)}:stale"
    rc.store[stale_50_key] = json.dumps(_sample_base(n=20, built_at=time.time() - 5.0))
    base_50_key = feed_page_base_cache_key(limit=50, event_pct=0.15)
    rc.store[base_50_key] = json.dumps(_sample_base(n=20, built_at=time.time() - 5.0))

    async def _empty_db():
        res = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []), all=lambda: [], scalar=lambda: 0)
        yield SimpleNamespace(execute=AsyncMock(return_value=res), scalars=AsyncMock(return_value=res))

    _install_common_route_fakes(monkeypatch, rc, opening_seating=False)
    monkeypatch.setattr(feed_route, "_score_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(feed_route, "_score_futures", AsyncMock(return_value=[]))

    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _empty_db
    try:
        # 1. FEED_PAGE_BASE=0 disables fallback completely.
        monkeypatch.setenv("FEED_PAGE_BASE", "0")
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            prior_reads = len(rc.reads)
            resp_off = await client.get("/api/feed?limit=5")
            assert resp_off.status_code == 200
            assert resp_off.headers["x-feed-cache"] == "miss"
            assert base_50_key not in rc.reads[prior_reads:]

            # 2. my_teams_only never reads anonymous fallback base.
            monkeypatch.delenv("FEED_PAGE_BASE", raising=False)
            prior_reads = len(rc.reads)
            resp_teams = await client.get("/api/feed?limit=5&my_teams_only=true")
            assert resp_teams.status_code == 200
            assert base_50_key not in rc.reads[prior_reads:]
            assert stale_50_key not in rc.reads[prior_reads:]

            # 3. Personalized reader (ctx != PersonalizationContext()) never reads fallback base.
            monkeypatch.setattr(
                feed_route,
                "_load_personalization_context",
                AsyncMock(return_value=PersonalizationContext(team_relations={101: {"follow"}})),
            )
            prior_reads = len(rc.reads)
            resp_pers = await client.get("/api/feed?limit=5", headers={"X-Session-Id": "sess-1"})
            assert resp_pers.status_code == 200
            assert resp_pers.headers["x-feed-cache"] == "miss"
            assert base_50_key not in rc.reads[prior_reads:]
            assert stale_50_key not in rc.reads[prior_reads:]

        # 4. _prewarm_rebuild=True never reads fallback base (inject scope marker via ASGI wrapper).
        monkeypatch.setattr(
            feed_route,
            "_load_personalization_context",
            AsyncMock(return_value=PersonalizationContext()),
        )

        async def _prewarm_asgi(scope, receive, send):
            if scope["type"] == "http":
                scope[FEED_PREWARM_SCOPE_KEY] = True
            await app(scope, receive, send)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=_prewarm_asgi), base_url="http://testserver"
        ) as prewarm_client:
            prior_reads = len(rc.reads)
            resp_pw = await prewarm_client.get("/api/feed?limit=5")
            assert resp_pw.status_code == 200
            assert resp_pw.headers["x-feed-cache"] == "miss"
            assert base_50_key not in rc.reads[prior_reads:]
            assert stale_50_key not in rc.reads[prior_reads:]
    finally:
        app.dependency_overrides = prior_overrides
        _reset_rc()
