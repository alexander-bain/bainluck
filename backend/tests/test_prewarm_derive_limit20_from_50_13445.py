"""Tests for #13445 Option 2: deriving limit=20 prewarm siblings from limit=50 parents."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils import request_cache as _rc
from app.utils.feed_cache import (
    FEED_PREWARM_KEY_SCOPE_KEY,
    FEED_PREWARM_MACHINERY_BASE_SCOPE_KEY,
    feed_machinery_page_base_key,
    feed_page_base_cache_key,
    feed_page_base_last_good_key,
    feed_response_cache_key,
    render_feed_page_from_base,
)

pcp = import_module("app.tasks.precompute_category_pages")

_CATEGORIES = ("politics", "economics", "entertainment", "tech", "weather", "culture")


def _scored_event_item(oid: int) -> dict:
    commence = (datetime.now(timezone.utc) + timedelta(hours=(oid % 10) + 2)).isoformat()
    return {
        "type": "event",
        "id": f"ev-{oid}",
        "headline": f"Away {oid} at Home {oid}",
        "score": 82.0 - oid * 0.3,
        "reason": "Close matchup",
        "data": {
            "id": oid,
            "home_team": f"Home {oid}",
            "away_team": f"Away {oid}",
            "home_team_name": f"Home {oid}",
            "away_team_name": f"Away {oid}",
            "status": "scheduled",
            "sport_key": "basketball_nba" if oid % 2 == 0 else "americanfootball_nfl",
            "sport": "Basketball" if oid % 2 == 0 else "Football",
            "commence_time": commence,
            "home_probability": round(0.45 + (oid % 7) * 0.05, 4),
            "away_probability": round(0.55 - (oid % 7) * 0.05, 4),
            "excite_index": 75.0 - oid * 0.3,
        },
    }


def _scored_futures_item(idx: int) -> dict:
    mid = 5000 + idx
    cat = _CATEGORIES[idx % len(_CATEGORIES)]
    return {
        "type": "futures",
        "id": f"fut-{mid}",
        "headline": f"Unique Market Subject {idx} Outcome",
        "score": 88.0 - idx * 0.4,
        "reason": f"Leading contender {idx}",
        "data": {
            "id": mid,
            "name": f"Unique Market Subject {idx} Outcome",
            "status": "open",
            "category": cat,
            "llm_sport_category": cat,
            "top_outcomes": [
                {"id": mid * 10, "name": "Yes", "probability": round(0.42 + (idx % 9) * 0.04, 4)}
            ],
        },
    }


def _empty_session() -> AsyncMock:
    session = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    res.scalars.return_value.first.return_value = None
    res.scalar_one_or_none.return_value = None
    res.scalar.return_value = 0
    res.fetchall.return_value = []
    res.all.return_value = []
    res.first.return_value = None
    session.execute = AsyncMock(return_value=res)
    session.rollback = AsyncMock()
    return session


class _AsyncRedisStandIn:
    def __init__(self) -> None:
        self.contents: dict[str, str] = {}

    async def mget(self, keys):
        return [self.contents.get(k) for k in keys]

    async def get(self, key):
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        if ttl <= 0:
            raise ValueError(f"invalid expire time {ttl}")
        self.contents[key] = value
        return True


def _fake_sync_rc():
    hashes: dict[str, dict[str, str]] = {}
    written_keys: dict[str, tuple[int, str]] = {}

    class _FakePipe:
        def __init__(self) -> None:
            self.ops: list[tuple] = []

        def hset(self, key: str, field: str, value: str):
            self.ops.append(("hset", key, field, value))
            return self

        def hdel(self, key: str, field: str):
            self.ops.append(("hdel", key, field))
            return self

        def expire(self, key: str, ttl: int):
            self.ops.append(("expire", key, ttl))
            return self

        def execute(self) -> None:
            for op, *rest in self.ops:
                if op == "hset":
                    k, f, v = rest
                    hashes.setdefault(k, {})[f] = v
                elif op == "hdel":
                    k, f = rest
                    hashes.setdefault(k, {}).pop(f, None)

    rc = MagicMock()
    rc.pipeline.side_effect = lambda transaction=True: _FakePipe()
    rc.hset.side_effect = lambda k, f, v: hashes.setdefault(k, {}).__setitem__(f, v)
    rc.hget.side_effect = lambda k, f: hashes.get(k, {}).get(f)
    rc.hgetall.side_effect = lambda k: dict(hashes.get(k, {}))
    rc.setex.side_effect = lambda k, ttl, v: written_keys.__setitem__(k, (ttl, v))
    rc.exists.side_effect = lambda k: 1 if k in written_keys else 0
    return rc, hashes, written_keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query_extra", "mode", "event_pct", "opening_seating"),
    [
        ("", None, 0.15, False),
        ("", None, 0.15, True),
        ("&machinery=1", None, 0.15, True),
        ("&mode=sports", "sports", None, False),
    ],
)
async def test_route_parity_get_feed_limit20_vs_slice_of_base50(
    monkeypatch: pytest.MonkeyPatch,
    query_extra: str,
    mode: str | None,
    event_pct: float | None,
    opening_seating: bool,
) -> None:
    """Real `GET /api/feed` with limit=20 equals `render_feed_page_from_base(base_50, limit=20)`."""
    from app.main import app

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    monkeypatch.setenv("FEED_OPENING_MIX_ENABLED", "true" if opening_seating else "false")
    monkeypatch.setenv(
        "CONTAINER_MACHINERY_SLICE1_ENABLED",
        "true" if "machinery=1" in query_extra else "false",
    )

    events_deck = [_scored_event_item(i) for i in range(1, 35)]
    futures_deck = [_scored_futures_item(i) for i in range(1, 45)]

    async def _mock_get_db():
        yield _empty_session()

    @asynccontextmanager
    async def _fake_session_cm():
        yield _empty_session()

    async def _mock_user():
        return None

    scheduled: list[asyncio.Task] = []

    def _spy_schedule(coro):
        task = asyncio.ensure_future(coro)
        scheduled.append(task)
        return task

    async def _no_roundups(*_a, **_kw):
        return []

    async def _fake_events(*_a, **_kw):
        return [dict(it) for it in events_deck]

    async def _fake_futures(*_a, **_kw):
        return [dict(it) for it in futures_deck]

    redis_50 = _AsyncRedisStandIn()
    redis_20 = _AsyncRedisStandIn()

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user
    try:
        monkeypatch.setattr(_rc, "schedule_background", _spy_schedule)
        monkeypatch.setattr("app.services.database.async_session_maker", _fake_session_cm)
        monkeypatch.setattr("app.utils.roundup_containers.add_roundup_feed_items", _no_roundups)

        # 1. Drive real GET /api/feed with limit=50 -> inspect stored base_50
        monkeypatch.setattr(_rc, "get_shared_async_redis", AsyncMock(return_value=redis_50))
        q50 = (
            f"/api/feed?limit=50&offset=0"
            f"{f'&event_pct={event_pct}' if event_pct is not None else ''}{query_extra}"
        )
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.routes.feed._score_events", new=AsyncMock(side_effect=_fake_events)),
            patch("app.routes.feed._score_futures", new=AsyncMock(side_effect=_fake_futures)),
            patch(
                "app.routes.feed._score_sports_mode_futures",
                new=AsyncMock(side_effect=_fake_futures),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp50 = await ac.get(q50)
        if scheduled:
            await asyncio.gather(*scheduled, return_exceptions=True)
            scheduled.clear()
        assert resp50.status_code == 200
        body50 = resp50.json()
        assert len(body50["items"]) >= 25

        base50_raw = next(
            (v for k, v in redis_50.contents.items() if ":pagebase:" in k and ":last_good" not in k),
            None,
        )
        assert base50_raw is not None, f"expected page_base written in {list(redis_50.contents)}"
        derived20 = render_feed_page_from_base(json.loads(base50_raw), limit=20, offset=0)
        assert derived20 is not None

        # 2. Drive real GET /api/feed with limit=20 -> exact item/order/total/has_more parity
        monkeypatch.setattr(_rc, "get_shared_async_redis", AsyncMock(return_value=redis_20))
        q20 = (
            f"/api/feed?limit=20&offset=0"
            f"{f'&event_pct={event_pct}' if event_pct is not None else ''}{query_extra}"
        )
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.routes.feed._score_events", new=AsyncMock(side_effect=_fake_events)),
            patch("app.routes.feed._score_futures", new=AsyncMock(side_effect=_fake_futures)),
            patch(
                "app.routes.feed._score_sports_mode_futures",
                new=AsyncMock(side_effect=_fake_futures),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp20 = await ac.get(q20)
        if scheduled:
            await asyncio.gather(*scheduled, return_exceptions=True)
            scheduled.clear()
        assert resp20.status_code == 200
        direct20 = resp20.json()

        assert [(it.get("type"), it.get("id")) for it in derived20["items"]] == [
            (it.get("type"), it.get("id")) for it in direct20["items"]
        ]
        assert len(direct20["items"]) == 20
        assert derived20["total"] == direct20["total"]
        assert derived20["has_more"] == direct20["has_more"]
        assert derived20.get("opening") == direct20.get("opening")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_prewarm_live_feed_shapes_opens_3_sessions_in_1_wave_and_publishes_all_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Option 2, 5 target shapes open only 3 DB sessions (1 wave) and populate all 5 keys."""
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    rc, hashes, written_keys = _fake_sync_rc()
    opened = 0
    active = 0
    peak = 0
    built_labels: list[str] = []

    full_deck = [
        {"type": "futures", "id": f"f-{i}", "data": {"id": 100 + i, "status": "open"}}
        for i in range(60)
    ]
    # Live item at seat 25 (inside base_50, outside top-20 child_payload) checks page_base liveness enrollment!
    full_deck[25] = {"type": "event", "id": "ev-live-25", "data": {"id": 925, "status": "live"}}

    @asynccontextmanager
    async def _fake_session():
        nonlocal opened, active, peak
        opened += 1
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        try:
            yield MagicMock()
        finally:
            active -= 1

    def _shape_for_req(limit: int, mode: str | None) -> str:
        return {
            (50, "discover"): "discover_native",
            (20, "discover"): "discover",
            (50, "sports"): "sports_native",
            (20, "sports"): "sports",
            (200, "discover"): "sports_native_events",
        }[(limit, mode or "discover")]

    async def _fake_get_feed(**kwargs):
        req: Request = kwargs["request"]
        limit = int(kwargs["limit"])
        mode = kwargs.get("mode")
        event_pct = kwargs.get("event_pct")
        include_events = bool(kwargs.get("include_events", True))
        include_futures = bool(kwargs.get("include_futures", True))
        lbl = _shape_for_req(limit, mode)
        built_labels.append(lbl)

        cache_shape = {
            "sport": None,
            "limit": limit,
            "offset": 0,
            "include_events": include_events,
            "include_futures": include_futures,
            "tags": None,
            "event_pct": event_pct,
            "my_teams_only": False,
            "mode": mode or ("discover" if include_futures else None),
            "category": None,
            "edition": None,
            "collections": None,
            "opening_seating": False,
            "machinery": False,
            "fun_admission": False,
        }
        ckey = feed_response_cache_key(**cache_shape)
        pb_key = feed_page_base_cache_key(
            **{k: v for k, v in cache_shape.items() if k not in ("offset", "edition", "machinery")}
        )
        pb_body = {"items": full_deck, "total": len(full_deck), "limit": limit}
        req.scope[FEED_PREWARM_KEY_SCOPE_KEY] = ckey
        req.scope[FEED_PREWARM_MACHINERY_BASE_SCOPE_KEY] = {
            "cache_shape": cache_shape,
            "page_base_key": pb_key,
            "page_base_body": pb_body,
            "page_base_last_good_body": pb_body,
            "page_base_fresh_ttl": 30,
            "page_base_stale_ttl": 60,
            "page_base_last_good_ttl": 300,
            "opening_seating": False,
            "edition_policy": None,
            "age_origin": 1_800_000_000.0,
        }
        page_items = full_deck[:limit]
        return {
            "items": page_items,
            "total": len(full_deck),
            "limit": limit,
            "offset": 0,
            "has_more": len(full_deck) > limit,
            "cache": {"status": "miss", "built_at": 1_800_000_000.0},
        }

    # Enroll all 5 shapes as live.
    all_labels = [s["label"] for s in pcp.FEED_PREWARM_SHAPES]
    hashes[pcp.FEED_PREWARM_LIVE_SHAPES_KEY] = {lbl: "1" for lbl in all_labels}

    async def _fake_mach_live(*_a, **_kw):
        return {"outcome": "ok", "live_slugs": []}

    mach_spliced: dict[str, int] = {}

    def _spy_mach_publish(_rc, *, mach_base, label):
        mach_spliced[label] = int(mach_base["cache_shape"]["limit"])
        pb = mach_base["page_base_key"]
        written_keys[feed_machinery_page_base_key(pb)] = (60, "{}")
        return {"outcome": "ok", "live": payload_live}

    payload_live = False

    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.feed.get_feed", _fake_get_feed),
        patch("app.tasks.base.get_task_session", _fake_session),
        patch.object(pcp, "_prewarm_live_machinery_roundups", _fake_mach_live),
        patch.object(pcp, "_publish_machinery_feed_from_prewarm_base", _spy_mach_publish),
        patch("app.utils.feed_served_markets.record_served_market_ids"),
    ):
        published = await pcp._prewarm_live_feed_shapes()

    assert mach_spliced.get("discover") == 20
    assert mach_spliced.get("discover_native") == 50

    assert published == 5
    assert opened == 3
    assert peak == 3
    assert set(built_labels) == {"discover_native", "sports_native", "sports_native_events"}

    report = json.loads(written_keys[pcp.FEED_LIVE_PREWARM_STATUS_KEY][1])
    assert set(report["shapes"].keys()) == set(all_labels)
    assert all(report["shapes"][lbl]["outcome"] == "ok" for lbl in all_labels)
    assert report["shapes"]["discover"]["derived_from"] == "discover_native"
    assert report["shapes"]["sports"]["derived_from"] == "sports_native"

    # Both derived shapes wrote response, page_base, last_good, and machinery_pagebase keys + hash entries!
    for derived_lbl, shape in (
        ("discover", {"limit": 20, "event_pct": 0.15, "mode": "discover", "include_events": True, "include_futures": True}),
        ("sports", {"limit": 20, "event_pct": None, "mode": "sports", "include_events": True, "include_futures": True}),
    ):
        exp_key = feed_response_cache_key(offset=0, **shape)
        exp_pb = feed_page_base_cache_key(**shape)
        assert exp_key in written_keys
        assert exp_pb in written_keys
        assert feed_page_base_last_good_key(exp_pb) in written_keys
        if derived_lbl == "discover":
            assert feed_machinery_page_base_key(exp_pb) in written_keys
        assert hashes[pcp.FEED_PREWARM_SHAPE_KEYS_KEY][derived_lbl] == exp_key
        assert hashes[pcp.FEED_PREWARM_PAGE_BASE_KEYS_KEY][derived_lbl] == exp_pb
        # Even though seat 25 is outside limit=20's page 1, Discover base has live game -> still enrolled as live!
        assert hashes[pcp.FEED_PREWARM_LIVE_SHAPES_KEY].get(derived_lbl) == "1"


@pytest.mark.asyncio
async def test_derived_child_falls_back_when_parent_fails_or_lacks_base_scope() -> None:
    """If parent times out, errors, or lacks MACHINERY_BASE_SCOPE, child builds via `_prewarm_feed_shape`."""
    rc, hashes, written_keys = _fake_sync_rc()
    hashes[pcp.FEED_PREWARM_LIVE_SHAPES_KEY] = {s["label"]: "1" for s in pcp.FEED_PREWARM_SHAPES}
    called: list[str] = []

    async def _stub_shape(shape: dict, _rc, *, deadline_s: float = 10.0) -> dict:
        called.append(shape["label"])
        if shape["label"] == "discover_native":
            return {"outcome": "timeout"}
        return {"outcome": "ok"}

    async def _fake_mach_live(*_a, **_kw):
        return {"outcome": "skipped", "live_slugs": []}

    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch.object(pcp, "_prewarm_feed_shape", _stub_shape),
        patch.object(pcp, "_prewarm_live_machinery_roundups", _fake_mach_live),
    ):
        published = await pcp._prewarm_live_feed_shapes()

    assert published == 4
    assert "discover" in called
    report = json.loads(written_keys[pcp.FEED_LIVE_PREWARM_STATUS_KEY][1])
    assert report["shapes"]["discover_native"]["outcome"] == "timeout"
    assert report["shapes"]["discover"]["outcome"] == "ok"


@pytest.mark.asyncio
async def test_priority_tier_never_groups_live_child_under_absent_parent() -> None:
    """A live `discover` child is never delayed behind an absent `discover_native` parent."""
    targets = [(s["label"], s) for s in pcp.FEED_PREWARM_SHAPES if s["label"] in {"discover", "discover_native"}]

    grouped, children_map = pcp._group_live_prewarm_targets(
        targets, live_labels={"discover"}, absent_labels={"discover_native"}
    )
    assert [lbl for lbl, _ in grouped] == ["discover", "discover_native"]
    assert children_map == {}

    # When both sit in the same tier, grouping attaches discover under discover_native.
    same_tier_grouped, same_tier_children = pcp._group_live_prewarm_targets(
        targets, live_labels={"discover", "discover_native"}, absent_labels=set()
    )
    assert [lbl for lbl, _ in same_tier_grouped] == ["discover_native"]
    assert [c["label"] for c in same_tier_children["discover_native"]] == ["discover"]
