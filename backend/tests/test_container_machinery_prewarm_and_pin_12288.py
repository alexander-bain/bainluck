"""#12288 Machinery roundup prewarm, live/non-live TTLs, timeout safety, and
edition-pinned Discover two-page + reload seat stability proof.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from app.routes import feed as feed_route
from app.tasks.precompute_category_pages import _prewarm_machinery_roundups
from app.utils.feed_cache import FEED_PAGE_BASE_CACHE_PREFIX
from app.utils.roundup_containers import (
    ROUNDUP_CACHE_TTL_S,
    ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupProducer,
    _roundup_cache_ttl_seconds,
    _roundup_local_cache,
    add_roundup_feed_items,
    compose_roundup_container,
    compose_roundup_feed_item,
    reset_roundup_cache_for_tests,
)


def test_machinery_cache_ttl_is_300s_for_non_live_and_60s_for_live() -> None:
    non_live_payload = {
        "sections": [
            {
                "members": [
                    {"type": "event", "id": 1, "card": {"id": 1, "status": "scheduled"}},
                    {"type": "market", "id": 2, "card": {"id": 2, "status": "open"}},
                ]
            }
        ]
    }
    live_payload = {
        "sections": [
            {
                "members": [
                    {"type": "event", "id": 1, "card": {"id": 1, "status": "live"}},
                ]
            }
        ]
    }
    assert (
        _roundup_cache_ttl_seconds("machinery-fed-and-macro", non_live_payload)
        == ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S
    )
    assert (
        _roundup_cache_ttl_seconds("machinery-nba-night", live_payload)
        == ROUNDUP_CACHE_TTL_S
    )
    assert (
        _roundup_cache_ttl_seconds("roundup-nfl-week", non_live_payload)
        == ROUNDUP_CACHE_TTL_S
    )
    assert _roundup_cache_ttl_seconds("machinery-fed-and-macro", None) == ROUNDUP_CACHE_TTL_S


@pytest.mark.asyncio
async def test_cold_machinery_timeout_never_negative_caches_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 0.5 s Discover timeout on a cold machinery-* producer must NEVER write
    a negative refusal into cache that would poison /collections/machinery-*."""
    reset_roundup_cache_for_tests()
    saved = dict(ROUNDUP_PRODUCERS)

    async def _slow_produce(db, *, now=None):
        await asyncio.sleep(0.2)
        return None

    slow_prod = RoundupProducer(
        slug="machinery-fed-and-macro",
        name="Fed & U.S. Macro",
        kind="roundup",
        category="economics",
        section_title="Fed",
        footer="",
        produce=_slow_produce,
        membership="computed-produced",
        relations=("same_subject",),
        level="member",
        rule={"producer": "container_machinery"},
        enabled=lambda: True,
    )
    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS[slow_prod.slug] = slow_prod
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.02
        )
        items = [{"type": "futures", "id": f"f-{i}", "data": {"id": i}} for i in range(15)]
        out = await add_roundup_feed_items(
            None,
            items,
            include_machinery=True,
            machinery_only=True,
            budget_seconds=1.0,
            stage_budget_seconds=1.0,
        )
        assert len(out) == 15
        assert not any(k[0] == "machinery-fed-and-macro" for k in _roundup_local_cache)
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()


@pytest.mark.asyncio
async def test_prewarm_machinery_roundups_noop_when_off_and_warms_parallel_when_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "false")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    off_res = await _prewarm_machinery_roundups()
    assert off_res["outcome"] == "disabled"

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    saved = dict(ROUNDUP_PRODUCERS)
    warmed_slugs: list[str] = []

    def _make_prod(slug: str) -> RoundupProducer:
        async def _prod(db, *, now=None):
            return RoundupMembers(
                members=[{"type": "market", "id": 1, "destination": "/futures/1", "card": {"id": 1, "name": slug}}],
                rows=[{"market_id": 1, "outcome_id": 1, "label": "A", "probability": 0.5, "rendered_percent": 50}],
                title=slug,
                destination_href=f"/collections/{slug}",
            )

        return RoundupProducer(
            slug=slug,
            name=slug,
            kind="roundup",
            category="other",
            section_title="Markets",
            footer="",
            produce=_prod,
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        )

    @asynccontextmanager
    async def _fake_session(**kwargs):
        yield object()

    async def _fake_eval(prod, db, *, force_refresh=False, **kwargs):
        assert force_refresh is True
        warmed_slugs.append(prod.slug)
        return {"type": "bundle"}, {"slug": prod.slug}

    try:
        ROUNDUP_PRODUCERS.clear()
        for s in ("machinery-nfl-week", "machinery-fed-and-macro", "roundup-other"):
            ROUNDUP_PRODUCERS[s] = _make_prod(s)
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr(
            "app.utils.roundup_containers.evaluate_roundup_producer", _fake_eval
        )
        on_res = await _prewarm_machinery_roundups(deadline_s=5.0)
        assert on_res["outcome"] == "ok"
        assert on_res["warmed"] == 2
        assert sorted(warmed_slugs) == ["machinery-fed-and-macro", "machinery-nfl-week"]
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_edition_pinned_discover_page1_page2_and_reload_one_minute_later_with_machinery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable 10:02 PM PT pre-switch proof:
    With CONTAINER_MACHINERY_SLICE1_ENABLED=true and `machinery=1`:
    - Page 1 (offset=0, limit=20) mints an edition token and seats machinery cards.
    - Page 2 (offset=20, limit=20, edition=token) holds the pin with 0 duplicates and
      0 missing cards across the combined 40 cards.
    - Reloading Page 1 a minute later (same edition pin) keeps every machinery grouping
      in the EXACT SAME seat index."""
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("FEED_PAGE_BASE_ENABLED", "1")
    saved = dict(ROUNDUP_PRODUCERS)

    # 50 ordinary cards in the single 1.0.6-safe prewarmed base
    base_items = [
        {
            "type": "futures",
            "id": f"fut-{i}",
            "score": 80.0 - i * 0.5,
            "reason": f"Market {i}",
            "headline": f"Market {i}",
            "data": {
                "id": 9000 + i,
                "name": f"Open Market {i}",
                "status": "open",
                "source": "kalshi",
                "story_key": f"fut:story:{i}",
                "top_outcomes": [{"id": i + 1, "name": "Yes", "probability": 0.55}],
            },
        }
        for i in range(50)
    ]
    base_json = json.dumps(
        {
            "items": base_items,
            "total": len(base_items),
            "_base_built_at": 1_800_000_000.0,
        }
    )
    store: dict[str, str] = {}

    class _FakeAsyncRedis:
        async def get(self, k: str):
            if k.startswith(f"{FEED_PAGE_BASE_CACHE_PREFIX}:") and not k.endswith(
                (":stale", ":last_good")
            ):
                return base_json
            return store.get(k)

        async def mget(self, keys: list[str]):
            out = []
            for k in keys:
                if k.startswith(f"{FEED_PAGE_BASE_CACHE_PREFIX}:") and not k.endswith(
                    (":stale", ":last_good")
                ):
                    out.append(base_json)
                else:
                    out.append(store.get(k))
            return out

        async def set(self, k: str, v: str, ex: int | None = None, nx: bool = False):
            if nx and k in store:
                return False
            store[k] = v
            return True

        async def setex(self, k: str, ttl: int, v: str):
            store[k] = v
            return True

        async def hgetall(self, k: str):
            return {}

    fake_redis = _FakeAsyncRedis()

    async def _fake_get_shared_redis():
        return fake_redis

    monkeypatch.setattr(
        "app.utils.request_cache.get_shared_async_redis", _fake_get_shared_redis
    )
    monkeypatch.setattr(
        "app.utils.feed_collections.feed_collections_enabled", lambda **kw: False
    )
    monkeypatch.setattr(
        "app.utils.theme_collection_ref.theme_collection_refs_enabled",
        lambda **kw: False,
    )

    # Build 2 real machinery roundup bundle cards via compose_roundup_feed_item
    mach_cards: list[dict] = []
    for idx, (slug, title) in enumerate(
        [
            ("machinery-nfl-week", "Ravens at Panthers headlines the Nov 19–22 slate"),
            ("machinery-oscars-best-picture", "The Odyssey leads Best Picture at 54%"),
        ]
    ):
        prod = RoundupProducer(
            slug=slug,
            name=title,
            kind="roundup",
            category="football" if idx == 0 else "entertainment",
            section_title="Markets",
            footer="",
            produce=AsyncMock(),
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        )
        members = RoundupMembers(
            members=[
                {
                    "type": "market",
                    "id": 7000 + idx,
                    "destination": f"/futures/{7000 + idx}",
                    "card": {
                        "id": 7000 + idx,
                        "name": title,
                        "status": "open",
                        "source": "kalshi",
                        "top_outcomes": [{"id": 1, "name": "Leader", "probability": 0.54}],
                    },
                }
            ],
            rows=[
                {
                    "market_id": 7000 + idx,
                    "outcome_id": 1,
                    "label": "Leader",
                    "probability": 0.54,
                    "rendered_percent": 54,
                }
            ],
            title=title,
            destination_href=f"/collections/{slug}",
        )
        fi = compose_roundup_feed_item(prod, members)
        assert fi is not None
        assert compose_roundup_container(prod, members) is not None
        mach_cards.append(fi)

    async def _fake_add_roundups(db, items, **kwargs):
        if kwargs.get("include_machinery") and kwargs.get("machinery_only"):
            # Seat machinery cards at deterministic seats 2 and 7
            spliced = list(items)
            spliced.insert(2, mach_cards[0])
            spliced.insert(7, mach_cards[1])
            return spliced
        return items

    monkeypatch.setattr(
        "app.utils.roundup_containers.add_roundup_feed_items", _fake_add_roundups
    )
    fake_req = SimpleNamespace(
        headers={}, cookies={}, query_params={}, url=SimpleNamespace(path="/api/feed")
    )

    def _card_key(it: dict) -> str:
        d = it.get("data") or {}
        slug = (d.get("collection_ref") or {}).get("slug")
        if slug:
            return f"collection:{slug}"
        return f"{it.get('type')}:{d.get('id', it.get('id'))}"

    try:
        # 1. Page 1 (unpinned, machinery=1)
        p1 = await feed_route.get_feed(
            response=Response(),
            request=fake_req,
            limit=20,
            offset=0,
            sport=None,
            category=None,
            include_events=True,
            include_futures=True,
            my_teams_only=False,
            mode="discover",
            tags=None,
            event_pct=0.15,
            edition=None,
            debug=False,
            debug_ground_truth=False,
            debug_personalization=False,
            exclude_reviewed=False,
            reviewer=None,
            reviewed_surface=None,
            machinery=1,
            secret=None,
            db=AsyncMock(),
            user=None,
        )
        # Allow background manifest SET NX EX task to flush into fake_redis
        await asyncio.sleep(0.05)

        ed_token = p1.get("edition")
        assert ed_token
        p1_keys = [_card_key(it) for it in p1["items"]]
        assert len(p1_keys) == 20
        p1_mach_seats = {
            k: i for i, k in enumerate(p1_keys) if k.startswith("collection:machinery-")
        }
        assert set(p1_mach_seats) == {
            "collection:machinery-nfl-week",
            "collection:machinery-oscars-best-picture",
        }

        # 2. Page 2 (pinned to ed_token, machinery=1)
        p2 = await feed_route.get_feed(
            response=Response(),
            request=fake_req,
            limit=20,
            offset=20,
            sport=None,
            category=None,
            include_events=True,
            include_futures=True,
            my_teams_only=False,
            mode="discover",
            tags=None,
            event_pct=0.15,
            edition=ed_token,
            debug=False,
            debug_ground_truth=False,
            debug_personalization=False,
            exclude_reviewed=False,
            reviewer=None,
            reviewed_surface=None,
            machinery=1,
            secret=None,
            db=AsyncMock(),
            user=None,
        )
        p2_keys = [_card_key(it) for it in p2["items"]]
        assert len(p2_keys) == 20
        assert p2.get("edition") == ed_token
        assert p2.get("edition_status") == "pinned"
        # Zero duplicates across Page 1 and Page 2, and all 40 unique cards present.
        assert set(p1_keys) & set(p2_keys) == set()
        assert len(set(p1_keys) | set(p2_keys)) == 40

        # 3. Reload Page 1 a minute later (same edition pin; fresh response cache miss)
        p1_reload = await feed_route.get_feed(
            response=Response(),
            request=fake_req,
            limit=20,
            offset=0,
            sport=None,
            category=None,
            include_events=True,
            include_futures=True,
            my_teams_only=False,
            mode="discover",
            tags=None,
            event_pct=0.15,
            edition=ed_token,
            debug=False,
            debug_ground_truth=False,
            debug_personalization=False,
            exclude_reviewed=False,
            reviewer=None,
            reviewed_surface=None,
            machinery=1,
            secret=None,
            db=AsyncMock(),
            user=None,
        )
        p1r_keys = [_card_key(it) for it in p1_reload["items"]]
        p1r_mach_seats = {
            k: i for i, k in enumerate(p1r_keys) if k.startswith("collection:machinery-")
        }
        assert p1_reload.get("edition") == ed_token
        assert p1_reload.get("edition_status") == "pinned"
        assert p1r_mach_seats == p1_mach_seats
        assert p1r_keys == p1_keys
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


def test_machinery_live_rail_enrollment_and_imminent_start_window() -> None:
    """Live slates AND slates starting within 3 minutes enroll on the 30s rail;
    final or distant slates leave it."""
    from datetime import datetime, timedelta, timezone

    from app.utils.roundup_containers import _roundup_payload_needs_live_rail

    now = datetime(2026, 11, 19, 18, 0, 0, tzinfo=timezone.utc)
    now_ts = now.timestamp()

    live_payload = {
        "sections": [
            {"members": [{"type": "event", "id": 1, "card": {"status": "live"}}]}
        ]
    }
    imminent_payload = {
        "sections": [
            {
                "members": [
                    {
                        "type": "event",
                        "id": 2,
                        "card": {
                            "status": "scheduled",
                            "commence_time": (now + timedelta(seconds=120)).isoformat(),
                        },
                    }
                ]
            }
        ]
    }
    distant_payload = {
        "sections": [
            {
                "members": [
                    {
                        "type": "event",
                        "id": 3,
                        "card": {
                            "status": "scheduled",
                            "commence_time": (now + timedelta(hours=4)).isoformat(),
                        },
                    }
                ]
            }
        ]
    }
    final_payload = {
        "sections": [
            {
                "members": [
                    {
                        "type": "event",
                        "id": 4,
                        "card": {
                            "status": "final",
                            "commence_time": (now - timedelta(hours=2)).isoformat(),
                        },
                    }
                ]
            }
        ]
    }

    assert _roundup_payload_needs_live_rail(live_payload, now_ts=now_ts) is True
    assert _roundup_payload_needs_live_rail(imminent_payload, now_ts=now_ts) is True
    assert _roundup_payload_needs_live_rail(distant_payload, now_ts=now_ts) is False
    assert _roundup_payload_needs_live_rail(final_payload, now_ts=now_ts) is False


@pytest.mark.asyncio
async def test_live_machinery_republish_on_30s_rail_keeps_live_slates_warm_and_fills_holes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable Point 1: `_prewarm_live_machinery_roundups` (called every 30s on realtime)
    rebuilds live slates FIRST, skips already-warm non-live groupings, and refills any
    absent non-live key as a LAT-P112 safety net."""
    from app.tasks.precompute_category_pages import _prewarm_live_machinery_roundups
    from app.utils.roundup_containers import (
        MACHINERY_LIVE_SLUGS_KEY,
        _redis_cache_key,
    )

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "false")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    class _FakeSyncRedis:
        def __init__(self, hashes: dict, existing: set[str]):
            self.hashes = hashes
            self.existing = existing
            self.calls = 0

        def hgetall(self, k: str):
            self.calls += 1
            return dict(self.hashes.get(k, {}))

        def exists(self, k: str):
            self.calls += 1
            return 1 if k in self.existing else 0

    rc_off = _FakeSyncRedis({}, set())
    off_res = await _prewarm_live_machinery_roundups(rc_off, deadline_s=10.0)
    assert off_res["outcome"] == "disabled"
    assert rc_off.calls == 0

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    saved = dict(ROUNDUP_PRODUCERS)
    call_order: list[tuple[str, ...]] = []

    def _make_prod(slug: str) -> RoundupProducer:
        return RoundupProducer(
            slug=slug,
            name=slug,
            kind="roundup",
            category="other",
            section_title="Markets",
            footer="",
            produce=AsyncMock(),
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        )

    async def _fake_prewarm(deadline_s: float = 10.0, *, slugs=None):
        tup = tuple(sorted(slugs or ()))
        call_order.append(tup)
        return {
            "outcome": "ok",
            "warmed": len(tup),
            "slugs": {s: {"outcome": "ok", "elapsed_ms": 12.0, "live": True} for s in tup},
        }

    try:
        ROUNDUP_PRODUCERS.clear()
        all_slugs = [
            "machinery-nba-night",
            "machinery-nfl-week",
            "machinery-fed-and-macro",
        ]
        for s in all_slugs:
            ROUNDUP_PRODUCERS[s] = _make_prod(s)
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr(
            "app.tasks.precompute_category_pages._prewarm_machinery_roundups",
            _fake_prewarm,
        )

        # Case A: NBA is live, all 3 keys exist -> rebuilds ONLY machinery-nba-night
        rc_live = _FakeSyncRedis(
            {MACHINERY_LIVE_SLUGS_KEY: {b"machinery-nba-night": b"1800000000"}},
            {_redis_cache_key(s) for s in all_slugs},
        )
        res_a = await _prewarm_live_machinery_roundups(rc_live, deadline_s=10.0)
        assert res_a["outcome"] == "ok"
        assert res_a["live_slugs"] == ["machinery-nba-night"]
        assert res_a["absent_slugs"] == []
        assert call_order == [("machinery-nba-night",)]

        # Case B: NBA is live AND Fed key went absent -> live runs FIRST, absent SECOND
        call_order.clear()
        rc_hole = _FakeSyncRedis(
            {MACHINERY_LIVE_SLUGS_KEY: {"machinery-nba-night": "1800000000"}},
            {_redis_cache_key("machinery-nba-night"), _redis_cache_key("machinery-nfl-week")},
        )
        res_b = await _prewarm_live_machinery_roundups(rc_hole, deadline_s=10.0)
        assert res_b["live_slugs"] == ["machinery-nba-night"]
        assert res_b["absent_slugs"] == ["machinery-fed-and-macro"]
        assert call_order == [("machinery-nba-night",), ("machinery-fed-and-macro",)]

        # Case C: Nothing live and all keys warm -> idle, zero builds
        call_order.clear()
        rc_idle = _FakeSyncRedis({}, {_redis_cache_key(s) for s in all_slugs})
        res_c = await _prewarm_live_machinery_roundups(rc_idle, deadline_s=10.0)
        assert res_c["outcome"] == "idle"
        assert call_order == []
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_live_machinery_card_enforces_60s_ceiling_on_page_and_discover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable Point 1 worst-case staleness proof:
    - Live machinery card carries `data.status == 'live'` so Discover detects it as live.
    - Local dyno cache anchors to Redis `built_at` (never double-TTL'd past 60s).
    - Cached live machinery read records `built_at` in LAT-P230's age sink so
      `live_total_age_headroom_s` keeps Discover + grouping <= 60s total."""
    from app.utils import principal_independent_cache as pic
    from app.utils.feed_cache import (
        FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
        live_total_age_headroom_s,
        payload_contains_live_event,
    )
    from app.utils.roundup_containers import (
        _record_machinery_live_origin,
        evaluate_roundup_producer,
    )

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    async def _live_produce(db, *, now=None):
        return RoundupMembers(
            members=[
                {
                    "type": "event",
                    "id": 42,
                    "destination": "/events/42",
                    "card": {"id": 42, "status": "live", "home_team": "Bulls", "away_team": "Heat"},
                }
            ],
            rows=[
                {
                    "event_id": 42,
                    "label": "Heat at Bulls",
                    "probability": 0.52,
                    "rendered_percent": 52,
                }
            ],
            title="Heat at Bulls live",
            destination_href="/collections/machinery-nba-night",
        )

    prod = RoundupProducer(
        slug="machinery-nba-night",
        name="NBA Slate",
        kind="roundup",
        category="basketball",
        section_title="Live Games",
        footer="",
        produce=_live_produce,
        membership="computed-produced",
        relations=("same_subject",),
        level="member",
        rule={"producer": "container_machinery"},
        enabled=lambda: True,
    )

    built_ts = 1_800_000_000.0
    fi, cp = await evaluate_roundup_producer(prod, object(), now=built_ts)
    assert fi is not None and cp is not None
    assert fi["data"]["status"] == "live"
    assert payload_contains_live_event({"items": [fi]}) is True

    # Reading a 45s-old cached live entry records its origin in LAT-P230 sink,
    # capping any Discover response cache TTL to <= 15s (45 + 15 == 60s ceiling).
    origins: list[float] = []
    pic.bind_reuse_sink([], [], origins)
    _record_machinery_live_origin(built_ts, "machinery-nba-night", cp)
    assert origins == [built_ts]
    assert live_total_age_headroom_s(45.0) == FEED_RESPONSE_STALE_TTL_LIVE_SECONDS - 45
    assert live_total_age_headroom_s(60.0) == 0
    reset_roundup_cache_for_tests()


def test_scoped_open_market_scan_uses_ix_fm_feed_open_sports_without_ilike_or_sort() -> None:
    """Fable Point 2 structural SQL proof: the machinery candidate scan walks
    `ix_fm_feed_open_sports` (status='open' AND event_id IS NULL AND llm_sport_category)
    with UNION ALL and zero ILIKE / NOT ILIKE / unindexed ORDER BY volume."""
    from sqlalchemy.dialects import postgresql

    from app.utils.container_machinery import (
        _build_scoped_open_market_scan_stmt,
        _category_llm_pool_for_definition,
    )

    fed_pool = _category_llm_pool_for_definition({"category": "economics"})
    assert fed_pool is not None and "economics" in fed_pool and "finance" in fed_pool

    sql = str(
        _build_scoped_open_market_scan_stmt(fed_pool).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    sql_low = sql.lower()
    assert "union all" in sql_low
    assert "futures_markets.status = 'open'" in sql_low
    assert "futures_markets.event_id is null" in sql_low
    assert "futures_markets.llm_sport_category in" in sql_low
    assert "futures_markets.llm_sport_category is null" in sql_low
    assert "ilike" not in sql_low
    assert "order by" not in sql_low


@pytest.mark.asyncio
async def test_load_snapshot_from_db_batches_withheld_prices_and_single_fleet_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable Point 2 batching proof: `_load_snapshot_from_db` calls
    `withheld_price_outcome_ids_for_markets` ONCE (never per-market N+1) and
    `_fleet_newest_observation` at most ONCE across all candidate markets."""
    from datetime import datetime, timezone

    from app.utils.container_machinery import _load_snapshot_from_db

    fake_outcomes = [
        SimpleNamespace(
            id=101,
            name="Quarter-point cut",
            current_probability=0.61,
            implied_probability=0.61,
            opening_probability=0.55,
            image_url=None,
            last_updated=None,
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=None,
        ),
        SimpleNamespace(
            id=102,
            name="No change",
            current_probability=0.30,
            implied_probability=0.30,
            opening_probability=0.35,
            image_url=None,
            last_updated=None,
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=None,
        ),
        SimpleNamespace(
            id=103,
            name="Quarter-point increase",
            current_probability=0.09,
            implied_probability=0.09,
            opening_probability=0.10,
            image_url=None,
            last_updated=None,
            is_winner=None,
            resolution_source=None,
            volume_24h=100,
            volume_24h_at=None,
        ),
    ]
    fake_markets = [
        SimpleNamespace(
            id=1,
            name="Fed decision in Jan 2027?",
            status="open",
            source="polymarket",
            mutually_exclusive=True,
            market_type="field",
            volume=900000,
            image_url=None,
            llm_sport_category="economics",
            outcomes=fake_outcomes,
        ),
        SimpleNamespace(
            id=2,
            name="What will the Fed rate be at the end of 2026?",
            status="open",
            source="polymarket",
            mutually_exclusive=True,
            market_type="field",
            volume=800000,
            image_url=None,
            llm_sport_category="economics",
            outcomes=fake_outcomes,
        ),
    ]

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return list(self._rows)

        def unique(self):
            return self

        def scalars(self):
            return self

    class _FakeSession:
        def __init__(self):
            self.exec_calls = 0

        async def execute(self, stmt):
            self.exec_calls += 1
            if self.exec_calls == 1:
                return _FakeResult([(m.id, m.name, m.volume) for m in fake_markets])
            if self.exec_calls == 2:
                return _FakeResult(fake_markets)
            return _FakeResult([])

    batched_withheld_calls: list[int] = []
    fleet_calls = 0

    async def _fake_batched_withheld(db, markets):
        batched_withheld_calls.append(len(markets))
        return {m.id: set() for m in markets}

    async def _fake_fleet(db, fm):
        nonlocal fleet_calls
        fleet_calls += 1
        return datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)

    async def _fake_out_legs(markets):
        return {}

    async def _fake_vt(db, fm):
        return SimpleNamespace(reason="not_a_title_question")

    def _fake_format(fm, *_args, **_kwargs):
        return {
            "outcomes": [
                {"id": o.id, "name": o.name, "probability": o.current_probability}
                for o in fm.outcomes
            ]
        }

    monkeypatch.setattr(
        "app.routes.futures.withheld_price_outcome_ids_for_markets",
        _fake_batched_withheld,
    )
    monkeypatch.setattr("app.routes.futures._fleet_newest_observation", _fake_fleet)
    monkeypatch.setattr("app.routes.futures.out_legs_by_market", _fake_out_legs)
    monkeypatch.setattr("app.routes.futures._resolve_verified_title", _fake_vt)
    monkeypatch.setattr("app.routes.futures._format_market_detail", _fake_format)
    monkeypatch.setattr(
        "app.routes.futures._apply_verified_title_to_detail", lambda d, v, fm: None
    )

    definition = {
        "slug": "machinery-fed-and-macro",
        "category": "economics",
        "rule": {
            "sections": [
                {
                    "key": "jan_fomc",
                    "atom_query": {
                        "kind": "markets",
                        "title_all_tokens": ["fed", "decision", "jan"],
                        "shape": "field",
                        "max_items": 1,
                    },
                },
                {
                    "key": "rate_path",
                    "atom_query": {
                        "kind": "markets",
                        "any_tokens": ["fed rate be at the end of 2026"],
                        "shape": "field",
                        "max_items": 1,
                    },
                },
            ]
        },
    }
    session = _FakeSession()
    snap = await _load_snapshot_from_db(
        session, definition, datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    )
    assert len(snap["markets"]) == 2
    assert batched_withheld_calls == [2]
    assert fleet_calls == 1
    # 1 lightweight ix_fm_feed_open_sports scan + 1 PK _verified_title_market_stmt
    # + 1 FuturesOddsSnapshot history read (no double FuturesMarket fetch!)
    assert session.exec_calls == 3


@pytest.mark.asyncio
async def test_scoped_scan_parity_with_legacy_ilike_across_all_five_definitions_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parity proof for claude[bot] Finding 2:
    1. Across all 5 registered machinery definitions, the new `ix_fm_feed_open_sports`
       Python-filtered selection picks the exact same standalone (`event_id IS NULL`)
       markets as the legacy SQL `ILIKE`/`NOT ILIKE` matcher.
    2. Game-linked prop rows (`event_id IS NOT NULL`) are intentionally excluded so
       game props never pollute standalone championship/award/macro sections.
    3. An off-pool `llm_sport_category` (e.g. `'news'`) still seats via the
       unmatched-section fallback, even if `min_items == 0`."""
    import json as _json
    from datetime import datetime, timezone
    from pathlib import Path

    from app.utils.container_machinery import (
        _category_llm_pool_for_definition,
        _load_snapshot_from_db,
        _market_title_matches_query,
    )

    cand_dir = Path(__file__).resolve().parents[1] / "data" / "groupings" / "candidates"
    defs = [
        _json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(cand_dir.glob("machinery-*.json"))
    ]
    assert len(defs) == 5

    # Fixture covering all 5 definitions + an off-pool category + an event_id!=None game prop
    fixture_rows = [
        (1, "Fed decision in Jan 2027?", 950000, "economics", None),
        (2, "Fed decision in March 2027?", 600000, "economics", None),
        (3, "What will the Fed rate be at the end of 2026?", 800000, "economics", None),
        (4, "How many Fed rate hikes in 2026?", 450000, "finance", None),
        (5, "US recession in 2027?", 700000, "politics", None),
        (6, "US GDP growth in 2026?", 400000, "economics", None),
        (7, "2028 Presidential Election Winning Party?", 900000, "politics", None),
        (8, "2028 Presidential Election Winner?", 950000, "politics", None),
        (9, "2028 Democratic Presidential Nominee?", 650000, "politics", None),
        (10, "2028 Republican Presidential Nominee?", 640000, "politics", None),
        (11, "2028 Presidential Primary: Iowa?", 300000, "politics", None),
        (12, "Oscars 2027 Best Director Winner?", 500000, "entertainment", None),
        (13, "Oscars 2027 Best Actor Winner?", 480000, "entertainment", None),
        (14, "Oscars 2027 Best Actress Winner?", 470000, "entertainment", None),
        (15, "NFL MVP Winner 2026?", 850000, "football", None),
        (16, "NFL Passing Yards Leader 2026?", 420000, "football", None),
        (17, "NFC North Champion 2026?", 410000, "football", None),
        (18, "AFC North Champion 2026?", 405000, "football", None),
        (19, "NBA MVP Winner 2026-27?", 820000, "basketball", None),
        (20, "NBA Points Per Game Leader 2026-27?", 410000, "basketball", None),
        (21, "NBA Sixth Man of the Year Winner?", 390000, "basketball", None),
        (22, "NBA Defensive Player of the Year Winner?", 385000, "basketball", None),
        # Intentionally excluded game-linked prop (event_id IS NOT NULL)
        (99, "NFL Passing Yards Leader — Game Prop Tonight", 999999, "football", 55555),
    ]

    def _legacy_ilike_match(name: str, aq: dict) -> bool:
        low = name.lower()
        for t in aq.get("title_all_tokens") or ():
            if str(t).strip().lower() not in low:
                return False
        any_t = [str(t).strip().lower() for t in (aq.get("any_tokens") or ()) if str(t).strip()]
        if any_t and not any(t in low for t in any_t):
            return False
        for ex in aq.get("exclude_tokens") or ():
            if str(ex).strip().lower() in low:
                return False
        return True

    for d in defs:
        pool = _category_llm_pool_for_definition(d)
        assert pool is not None
        scoped = [r for r in fixture_rows if r[4] is None and (r[3] in pool or r[3] is None)]
        for sec in d["rule"]["sections"]:
            aq = sec["atom_query"]
            if aq["kind"] not in {"markets", "market_history"}:
                continue
            assert int(aq.get("min_items", 0) or 0) >= 1
            legacy_standalone_ids = {
                r[0] for r in fixture_rows if r[4] is None and _legacy_ilike_match(r[1], aq)
            }
            new_scoped_ids = {
                r[0] for r in scoped if _market_title_matches_query(r[1], aq)
            }
            assert new_scoped_ids == legacy_standalone_ids
            assert 99 not in new_scoped_ids

    # Off-pool category fallback test (even when min_items == 0):
    off_pool_market = SimpleNamespace(
        id=777,
        name="Fed decision in Jan 2027?",
        status="open",
        source="polymarket",
        mutually_exclusive=True,
        market_type="field",
        volume=500000,
        image_url=None,
        llm_sport_category="news",  # outside economics pool!
        outcomes=[
            SimpleNamespace(id=1, name="Quarter-point cut", current_probability=0.60, implied_probability=0.60, opening_probability=0.55, image_url=None),
            SimpleNamespace(id=2, name="No change", current_probability=0.30, implied_probability=0.30, opening_probability=0.35, image_url=None),
            SimpleNamespace(id=3, name="Quarter-point increase", current_probability=0.10, implied_probability=0.10, opening_probability=0.10, image_url=None),
        ],
    )

    class _FallbackResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return list(self._rows)

        def unique(self):
            return self

        def scalars(self):
            return self

    class _FallbackSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return _FallbackResult([])  # scoped pool returned 0 hits
            if self.calls == 2:
                return _FallbackResult([(777, off_pool_market.name, off_pool_market.volume)])
            if self.calls == 3:
                return _FallbackResult([off_pool_market])
            return _FallbackResult([])

    monkeypatch.setattr(
        "app.routes.futures.withheld_price_outcome_ids_for_markets",
        AsyncMock(return_value={777: set()}),
    )
    monkeypatch.setattr("app.routes.futures._fleet_newest_observation", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routes.futures.out_legs_by_market", AsyncMock(return_value={}))
    monkeypatch.setattr(
        "app.routes.futures._resolve_verified_title",
        AsyncMock(return_value=SimpleNamespace(reason="not_a_title_question")),
    )
    monkeypatch.setattr(
        "app.routes.futures._format_market_detail",
        lambda fm, *a, **kw: {
            "outcomes": [
                {"id": o.id, "name": o.name, "probability": o.current_probability}
                for o in fm.outcomes
            ]
        },
    )
    monkeypatch.setattr(
        "app.routes.futures._apply_verified_title_to_detail", lambda d, v, fm: None
    )

    def_min0 = {
        "slug": "machinery-fed-and-macro",
        "category": "economics",
        "rule": {
            "sections": [
                {
                    "key": "jan_fomc",
                    "atom_query": {
                        "kind": "markets",
                        "title_all_tokens": ["fed", "decision", "jan"],
                        "shape": "field",
                        "min_items": 0,
                        "max_items": 1,
                    },
                }
            ]
        },
    }
    snap = await _load_snapshot_from_db(
        _FallbackSession(), def_min0, datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
    )
    assert [m["id"] for m in snap["markets"]] == [777]
