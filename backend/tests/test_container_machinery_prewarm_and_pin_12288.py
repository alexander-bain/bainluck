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


def test_machinery_replaces_same_race_at_old_seat_and_leaves_non_replacers_in_registry_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#12288 (Fable 9:57 AM PT direction):
      1. General `replaces` line: `machinery-oscars-best-picture` replaces
         `roundup-oscars-best-picture` and inherits its registry turn & seat
         (no artificial lift above older roundups for non-replacers).
      2. Fed & Rates (`theme:story:macro_rates`) dissolves naturally when
         `machinery-fed-and-macro` covers `57574250` ("Fed Decision in December?"),
         leaving `< 2` children on the old 2-market theme card.
      3. Broad `Oscars 2027` (`theme:story:oscars`) stays by default (`replaces_themes: []`)
         and toggles off with one line of JSON data (`replaces_themes: ["story:oscars"]`).
      4. Fail-safe: when `machinery-oscars-best-picture` is NOT served,
         `roundup-oscars-best-picture` remains untouched at its original seat.
      5. `1.0.6` (no machinery cards) is byte-for-byte identical before and after.
    """
    from app.utils.container_machinery import register_machinery_slice1_candidates
    from app.utils.roundup_containers import (
        ROUNDUP_PRODUCERS,
        RoundupProducer,
        insert_roundup_feed_items,
    )

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    saved_producers = dict(ROUNDUP_PRODUCERS)
    try:
        register_machinery_slice1_candidates()
        _run_machinery_replace_assertions(
            ROUNDUP_PRODUCERS, RoundupProducer, insert_roundup_feed_items
        )
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved_producers)


def _run_machinery_replace_assertions(
    ROUNDUP_PRODUCERS, RoundupProducer, insert_roundup_feed_items
) -> None:
    mach_slugs = [
        "machinery-nfl-week",
        "machinery-nba-night",
        "machinery-oscars-best-picture",
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
    ]
    for s in mach_slugs:
        assert s in ROUNDUP_PRODUCERS, f"Missing registered machinery producer {s}"

    def _theme_card(theme_id: str, name: str, mids: list[int], slug: str | None = None) -> dict:
        data: dict = {
            "id": theme_id,
            "kind": "theme",
            "name": name,
            "items": [
                {"type": "futures", "data": {"id": mid, "name": f"M{mid}", "status": "open"}}
                for mid in mids
            ],
        }
        if slug:
            data["collection_ref"] = {"slug": slug, "href": f"/collections/{slug}", "name": name}
        return {"type": "bundle", "score": 90.0, "data": data}

    def _legacy_roundup_card(slug: str, name: str, *, sibling: bool = False) -> dict:
        return {
            "type": "bundle",
            "score": 60.0,
            "data": {
                "id": f"roundup:{slug.removeprefix('roundup-')}",
                "kind": "roundup",
                "name": name,
                "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": name},
                "roundup": {
                    "kicker": "ROUND-UP",
                    "relations": ["sibling"] if sibling else ["same_subject"],
                    "rows": [],
                },
                "items": [],
            },
        }

    def _single_card(idx: int) -> dict:
        return {
            "type": "futures",
            "score": 80.0 - idx * 0.5,
            "data": {"id": 90000 + idx, "name": f"Standalone {idx}", "status": "open"},
        }

    def _mach_card(
        slug: str,
        mids: list[int] | None = None,
        covered: list[int] | None = None,
    ) -> dict:
        prod = ROUNDUP_PRODUCERS[slug]
        mids = list(mids or [])
        all_mids = list(dict.fromkeys([*mids, *(covered or [])]))
        return {
            "type": "bundle",
            "score": 75.0,
            "data": {
                "id": f"roundup:{slug}",
                "kind": "roundup",
                "name": prod.name,
                "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": prod.name},
                "roundup": {
                    "kicker": prod.kicker,
                    "relations": list(prod.relations),
                    "rows": [],
                },
                "items": [{"type": "futures", "data": {"id": mid, "status": "open"}} for mid in mids],
                "member_ids": all_mids,
            },
        }

    base: list[dict] = [
        _theme_card("theme:story:oscars:6173044-58492234-58492236", "Oscars 2027", [6173044, 58492234, 58492236], slug="oscars-2027"),
        _theme_card("theme:story:grammys:70208645-58492243", "Grammys", [70208645, 58492243]),
        _theme_card("theme:story:middle_east_conflict:69603905-113232", "Middle East", [69603905, 113232]),
        _single_card(4),
        _theme_card("theme:story:macro_rates:57574250-56995847", "Fed & Rates", [57574250, 56995847]),
        _single_card(6),
        _single_card(7),
        _theme_card("theme:story:russia_ukraine:20569379-112896", "Russia-Ukraine", [20569379, 112896]),
        _single_card(9),
        _single_card(10),
        _single_card(11),
        _single_card(12),
    ]
    legacy_slugs = [
        "roundup-cfp-picture",
        "by-november-30",
        "liga-profesional-relegation-2026",
        "by-december-31",
        "nhl-playoffs-2026-27",
        "golf-this-week",
        "gta-vi-album-features",
        "for-scale-snow-in-dc",
        "celtics-next-3-games",
        "lakers-next-3-games",
        "roundup-oscars-best-picture",
        "roundup-nfl-division-front-runners",
    ]
    sib_legacy = {
        "liga-profesional-relegation-2026",
        "nhl-playoffs-2026-27",
        "gta-vi-album-features",
    }
    for i, lslug in enumerate(legacy_slugs):
        base.append(_legacy_roundup_card(lslug, f"Legacy {lslug}", sibling=(lslug in sib_legacy)))
        base.append(_single_card(100 + i))
    # Standalone unlinked Kalshi 2028 market (`108326`) sitting beside the 2028 grouping
    base.insert(
        28,
        {
            "type": "futures",
            "score": 61.0,
            "data": {
                "id": 108326,
                "name": "2028 U.S. Presidential Election winner?",
                "status": "open",
            },
        },
    )
    for extra in range(20):
        base.append(_single_card(200 + extra))

    def _slug_of(it: dict) -> str:
        d = it.get("data") or {}
        return str((d.get("collection_ref") or {}).get("slug") or d.get("id") or "")

    # 1.0.6 (no machinery cards): top 40 untouched
    assert insert_roundup_feed_items(base, [], page_window=20)[:40] == base[:40]

    # Verify `_dedupe_twin_markets` records unlinked cross-venue twin `108326` on `112897`
    # and `build_roundup_feed_item` propagates it into `data["member_ids"]`.
    from datetime import datetime, timezone

    from app.utils.container_machinery import _clean_section_market_label, _dedupe_twin_markets
    from app.utils.discover_opening_seating import seat_opening
    from app.utils.roundup_containers import RoundupMembers, compose_roundup_feed_item

    deduped_2028 = _dedupe_twin_markets(
        [
            {"market_id": 112897, "title": _clean_section_market_label("Presidential Election Winner 2028")},
            {"market_id": 108326, "title": _clean_section_market_label("2028 U.S. Presidential Election winner?")},
        ]
    )
    assert len(deduped_2028) == 1
    assert deduped_2028[0]["market_id"] == 112897
    assert deduped_2028[0]["_twin_market_ids"] == [108326]
    built_2028 = compose_roundup_feed_item(
        ROUNDUP_PRODUCERS["machinery-2028-presidential"],
        RoundupMembers(
            [{"type": "market", "id": 112897, "card": {"id": 112897, "status": "open"}}],
            covered_market_ids=deduped_2028[0]["_twin_market_ids"],
        ),
    )
    assert built_2028 is not None
    assert built_2028["data"]["item_count"] == 1
    assert built_2028["data"]["member_ids"] == [112897, 108326]

    fed_orig_idx = next(
        i for i, it in enumerate(base)
        if str((it.get("data") or {}).get("id") or "").startswith("theme:story:macro_rates:")
    )

    cards = [
        _mach_card("machinery-nfl-week"),
        _mach_card("machinery-nba-night"),
        _mach_card("machinery-oscars-best-picture", [6173044, 5165726]),
        _mach_card("machinery-2028-presidential", [112897], covered=[108326]),
        _mach_card("machinery-fed-and-macro", [57574217, 57574250]),
    ]
    now_dt = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
    spliced = insert_roundup_feed_items(base, cards, page_window=20, now=now_dt)
    all_ids = [str((it.get("data") or {}).get("id") or "") for it in spliced]
    all_slugs = [_slug_of(it) for it in spliced]

    # All five present once
    for s in mach_slugs:
        assert all_slugs.count(s) == 1

    # Fed & U.S. Macro absorbed `Fed & Rates` (dissolving it to < 2 children)
    # and inherited its exact opening seat — surviving `seat_opening` in place.
    assert not any(i.startswith("theme:story:macro_rates:") for i in all_ids)
    assert all_slugs[fed_orig_idx] == "machinery-fed-and-macro"
    assert spliced[fed_orig_idx]["data"].get("inherited_opening_seat") is True
    opening_outcome = seat_opening(spliced, now=now_dt)
    assert opening_outcome.status == "compliant"
    assert _slug_of(opening_outcome.items[fed_orig_idx]) == "machinery-fed-and-macro"

    # Unlinked Kalshi 2028 twin (`108326`) is pruned so only ONE 2028 card appears
    assert "108326" not in all_ids
    assert all_slugs.count("machinery-2028-presidential") == 1

    # Same race (`roundup-oscars-best-picture`) replaced in-place between lakers and nfl-division
    assert "roundup-oscars-best-picture" not in all_slugs
    assert all_slugs.index("lakers-next-3-games") < all_slugs.index("machinery-oscars-best-picture")
    assert all_slugs.index("machinery-oscars-best-picture") < all_slugs.index("roundup-nfl-division-front-runners")

    # Non-replacers are NOT artificially lifted above older roundups in their
    # respective sibling / non-sibling queues (existing 1:1 interleaver order).
    assert all_slugs.index("gta-vi-album-features") < all_slugs.index("machinery-2028-presidential")
    assert all_slugs.index("roundup-nfl-division-front-runners") < all_slugs.index("machinery-nba-night")
    assert all_slugs.index("machinery-nba-night") < all_slugs.index("machinery-nfl-week")

    # Broad Oscars 2027 at Seat 1 STAYS by default (Ruling 270: A, `replaces_themes: []`)
    assert all_ids[0].startswith("theme:story:oscars:")

    # One-line data toggle (`replaces_themes: ["story:oscars"]`) removes Seat 1 Oscars 2027 cleanly
    orig_osc = ROUNDUP_PRODUCERS["machinery-oscars-best-picture"]
    ROUNDUP_PRODUCERS["machinery-oscars-best-picture"] = RoundupProducer(
        slug=orig_osc.slug,
        name=orig_osc.name,
        kind=orig_osc.kind,
        category=orig_osc.category,
        section_title=orig_osc.section_title,
        footer=orig_osc.footer,
        produce=orig_osc.produce,
        membership=orig_osc.membership,
        relations=orig_osc.relations,
        level=orig_osc.level,
        rule={**(orig_osc.rule or {}), "replaces_themes": ["story:oscars"]},
        tag=orig_osc.tag,
        kicker=orig_osc.kicker,
        enabled=orig_osc.enabled,
    )
    toggled = insert_roundup_feed_items(base, cards, page_window=20)
    toggled_ids = [str((it.get("data") or {}).get("id") or "") for it in toggled]
    assert not any(i.startswith("theme:story:oscars:") for i in toggled_ids)
    ROUNDUP_PRODUCERS["machinery-oscars-best-picture"] = orig_osc

    # Fail-safe: when Oscars machinery is NOT served, legacy roundup stays
    partial = insert_roundup_feed_items(base, [_mach_card("machinery-nba-night")], page_window=20)
    partial_slugs = [_slug_of(it) for it in partial]
    assert "roundup-oscars-best-picture" in partial_slugs


def test_standing_roundup_seats_unchanged_and_machinery_never_moves_later_on_deep_takeover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable 12:16 PM PT probe on #13077:
      1. A standing round-up absorbing a 2-market theme card at seats 4, 15, or 41
         seats identically to master (11, 15, 11) and is never marked `inherited_opening_seat`.
      2. A machinery grouping absorbing a 2-market theme card at seat 4 takes seat 4,
         at seat 15 takes seat 15, and at seat 41 (later than its own seat 11) stays at 11.
    """
    from app.utils.container_machinery import register_machinery_slice1_candidates
    from app.utils.roundup_containers import ROUNDUP_PRODUCERS, insert_roundup_feed_items

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    saved_producers = dict(ROUNDUP_PRODUCERS)
    try:
        register_machinery_slice1_candidates()

        def _single(i: int) -> dict:
            return {
                "type": "futures",
                "score": 80.0 - i * 0.5,
                "data": {"id": 90000 + i, "name": f"S{i}", "status": "open"},
            }

        def _theme(tid: str, mids: list[int]) -> dict:
            return {
                "type": "bundle",
                "score": 90.0,
                "data": {
                    "id": tid,
                    "kind": "theme",
                    "name": "Two-market theme",
                    "items": [
                        {"type": "futures", "data": {"id": m, "name": f"M{m}", "status": "open"}}
                        for m in mids
                    ],
                },
            }

        def _roundup(slug: str, mids: list[int]) -> dict:
            prod = ROUNDUP_PRODUCERS.get(slug)
            return {
                "type": "bundle",
                "score": 60.0,
                "data": {
                    "id": f"roundup:{slug.removeprefix('roundup-')}",
                    "kind": "roundup",
                    "name": getattr(prod, "name", slug),
                    "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": slug},
                    "roundup": {"kicker": "ROUND-UP", "relations": ["same_subject"], "rows": []},
                    "items": [{"type": "futures", "data": {"id": m, "status": "open"}} for m in mids],
                    "member_ids": list(mids),
                },
            }

        standing_slug = next(s for s in ROUNDUP_PRODUCERS if not s.startswith("machinery-"))
        for theme_idx, expected_seat in ((3, 11), (14, 15), (40, 11)):
            feed = [_single(i) for i in range(60)]
            feed[theme_idx] = _theme("theme:story:x:1-2", [777001, 777002])
            card = _roundup(standing_slug, [777001, 555001, 555002])
            out = insert_roundup_feed_items(feed, [card], page_window=20)
            ids = [str((it.get("data") or {}).get("id") or "") for it in out]
            rid = card["data"]["id"]
            assert ids.index(rid) + 1 == expected_seat
            assert not any(i.startswith("theme:story:x") for i in ids)
            assert out[ids.index(rid)]["data"].get("inherited_opening_seat") is None

        for theme_idx, expected_seat, expected_flag in ((3, 4, True), (14, 15, None), (40, 11, None)):
            feed = [_single(i) for i in range(60)]
            feed[theme_idx] = _theme("theme:story:y:1-2", [888001, 888002])
            card = _roundup("machinery-2028-presidential", [888001, 555001, 555002])
            out = insert_roundup_feed_items(feed, [card], page_window=20)
            ids = [str((it.get("data") or {}).get("id") or "") for it in out]
            rid = card["data"]["id"]
            assert ids.index(rid) + 1 == expected_seat
            assert not any(i.startswith("theme:story:y") for i in ids)
            assert out[ids.index(rid)]["data"].get("inherited_opening_seat") is expected_flag
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved_producers)


@pytest.mark.asyncio
async def test_machinery_stale_while_revalidate_prevents_feed_drop_and_proactive_prewarm_refreshes_before_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#12288 attended-flip catch:
    1. Non-live machinery keeps a 1800s hard stale window (live: 120s) while soft TTL stays 300s/60s.
    2. When a non-live machinery cache entry passes its 300s soft TTL (e.g. age=450s < 1800s),
       Discover feed splicing (`allow_stale=True`) serves the last-known-good card immediately
       instead of hitting the 0.5s producer timeout and dropping the grouping from Discover.
    3. Direct page opens (`allow_stale=False`) still rebuild live when past soft TTL, and entries
       past the 1800s hard window are never served stale.
    4. `_absent_machinery_slugs` proactively queues a refresh at >= 70% of soft TTL (210s/300s)
       so background prewarm refreshes before soft expiry instead of waiting for key deletion.
    """
    import time as _time

    from app.tasks.precompute_category_pages import _absent_machinery_slugs
    from app.utils.roundup_containers import (
        ROUNDUP_MACHINERY_LIVE_STALE_TTL_S,
        ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
        _redis_cache_key,
        _roundup_cache_stale_ttl_seconds,
        evaluate_roundup_producer,
    )

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    non_live_cp = {
        "sections": [{"members": [{"type": "market", "id": 1, "card": {"id": 1, "status": "open"}}]}]
    }
    live_cp = {
        "sections": [{"members": [{"type": "event", "id": 2, "card": {"id": 2, "status": "live"}}]}]
    }
    assert (
        _roundup_cache_stale_ttl_seconds("machinery-fed-and-macro", non_live_cp)
        == ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
    )
    assert (
        _roundup_cache_stale_ttl_seconds("machinery-nba-night", live_cp)
        == ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
    )
    assert _roundup_cache_stale_ttl_seconds("roundup-cfp-picture", non_live_cp) == ROUNDUP_CACHE_TTL_S
    assert _roundup_cache_stale_ttl_seconds("machinery-fed-and-macro", None) == ROUNDUP_CACHE_TTL_S

    calls = 0

    async def _slow_on_second_call(db, *, now=None):
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.sleep(0.2)
        return RoundupMembers(
            members=[
                {
                    "type": "market",
                    "id": 57574217,
                    "destination": "/futures/57574217",
                    "card": {"id": 57574217, "name": "Fed Decision in January?", "status": "open"},
                }
            ],
            rows=[
                {
                    "market_id": 57574217,
                    "outcome_id": 1,
                    "label": "25 bps increase",
                    "probability": 0.61,
                    "rendered_percent": 61,
                }
            ],
            title="Fed & U.S. Macro",
            destination_href="/collections/machinery-fed-and-macro",
        )

    prod = RoundupProducer(
        slug="machinery-fed-and-macro",
        name="Fed & U.S. Macro",
        kind="roundup",
        category="economics",
        section_title="Fed",
        footer="",
        produce=_slow_on_second_call,
        membership="computed-produced",
        relations=("same_subject",),
        level="member",
        rule={"producer": "container_machinery"},
        enabled=lambda: True,
    )

    saved = dict(ROUNDUP_PRODUCERS)
    fake_db = object()
    t0 = 1_800_000_000.0
    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS[prod.slug] = prod
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCER_TIMEOUT_SECONDS", 0.05
        )

        # Warm the cache at t0
        fi0, cp0 = await evaluate_roundup_producer(prod, fake_db, now=t0)
        assert fi0 is not None and cp0 is not None and calls == 1

        # At t0 + 450s (past 300s soft TTL, inside 1800s stale window):
        # Discover splice (`allow_stale=True`) serves last-known-good with ZERO DB timeout.
        base_items = [
            {"type": "futures", "id": f"f-{i}", "score": 80.0 - i, "data": {"id": 1000 + i, "status": "open"}}
            for i in range(15)
        ]
        spliced = await add_roundup_feed_items(
            fake_db,
            base_items,
            include_machinery=True,
            machinery_only=True,
            now=t0 + 450.0,
            budget_seconds=1.0,
            stage_budget_seconds=1.0,
        )
        assert calls == 1
        assert any(
            (it.get("data") or {}).get("collection_ref", {}).get("slug") == "machinery-fed-and-macro"
            for it in spliced
        )

        # Past the 1800s hard stale window (t0 + 1900s), stale entry is NOT served
        fi_expired, cp_expired = await evaluate_roundup_producer(
            prod, fake_db, now=t0 + 1900.0, allow_stale=True
        )
        assert fi_expired is not None and cp_expired is not None and calls == 2

        # Direct page open (`allow_stale=False`) past soft TTL (t0 + 1900 + 450) still rebuilds live
        fi_fresh, cp_fresh = await evaluate_roundup_producer(
            prod, fake_db, now=t0 + 2350.0, allow_stale=False
        )
        assert fi_fresh is not None and cp_fresh is not None and calls == 3

        # Proactive prewarm check: >= 70% of 300s soft TTL (220s) is due; fresh (100s) is idle
        now_wall = _time.time()
        payloads = {
            _redis_cache_key("machinery-fed-and-macro"): json.dumps(
                {"built_at": now_wall - 220.0, "ttl_s": 300.0}
            ),
            _redis_cache_key("machinery-2028-presidential"): json.dumps(
                {"built_at": now_wall - 100.0, "ttl_s": 300.0}
            ),
        }

        class _FakeAgeRedis:
            def exists(self, k: str) -> int:
                return 1 if k in payloads else 0

            def get(self, k: str):
                return payloads.get(k)

        due = _absent_machinery_slugs(
            _FakeAgeRedis(),
            registered_slugs=[
                "machinery-fed-and-macro",
                "machinery-2028-presidential",
                "machinery-oscars-best-picture",
            ],
            exclude=set(),
        )
        assert due == ["machinery-fed-and-macro", "machinery-oscars-best-picture"]
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()


@pytest.mark.asyncio
async def test_celery_prewarm_publishes_machinery_via_sync_redis_and_web_path_never_calls_sync_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#12288 12-minute hold catch + Fable 7:46 PM review (#969 NEVER-AGAIN):
    In Celery ForkPoolWorker, `asyncio.run()` closes the event loop between tasks so
    process-global `get_shared_async_redis()` returns `RedisResult(ERROR)` and silently
    drops Redis writes. Verify:
    1. On the web path (`_store_roundup_cache_entry`), when `bounded_redis_call`
       returns `ERROR` or `TIMEOUT`, ZERO sync Redis (`get_redis_client`) calls are
       made so a slow Redis never freezes the web dyno event loop.
    2. `_prewarm_machinery_roundups(..., rc=...)` explicitly publishes both live and
       non-live groupings through sync Redis and reports `redis_written == warmed`.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.request_cache import ERROR, TIMEOUT, RedisResult
    from app.utils.roundup_containers import (
        MACHINERY_LIVE_SLUGS_KEY,
        ROUNDUP_MACHINERY_LIVE_STALE_TTL_S,
        ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
        _redis_cache_key,
        _store_roundup_cache_entry,
    )

    class _FakeSyncRedis:
        def __init__(self) -> None:
            self.kv: dict[str, tuple[str, int | None]] = {}
            self.hashes: dict[str, dict[str, str]] = {}
            self.expires: dict[str, int] = {}

        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            self.kv[key] = (value, ex)
            return True

        def get(self, key: str) -> str | None:
            entry = self.kv.get(key)
            return entry[0] if entry is not None else None

        def ttl(self, key: str) -> int:
            entry = self.kv.get(key)
            if entry is None:
                return -2
            return int(entry[1]) if entry[1] is not None else -1

        def hset(self, name: str, key: str, value: str) -> int:
            self.hashes.setdefault(name, {})[key] = value
            return 1

        def hdel(self, name: str, key: str) -> int:
            self.hashes.setdefault(name, {}).pop(key, None)
            return 1

        def expire(self, name: str, ttl: int) -> bool:
            self.expires[name] = ttl
            return True

    live_cp = {
        "sections": [
            {"members": [{"type": "event", "id": 10, "card": {"id": 10, "status": "live"}}]}
        ]
    }
    non_live_cp = {
        "sections": [
            {"members": [{"type": "market", "id": 20, "card": {"id": 20, "status": "open"}}]}
        ]
    }

    sync_client_calls = 0

    def _forbidden_sync_client():
        nonlocal sync_client_calls
        sync_client_calls += 1
        raise AssertionError("web path must never call sync get_redis_client()")

    async def _fake_async_client():
        return object()

    monkeypatch.setattr("app.utils.request_cache.get_shared_async_redis", _fake_async_client)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _forbidden_sync_client)

    # 1. On the web path, async ERROR and TIMEOUT must NEVER invoke sync Redis
    fake_session = AsyncSession.__new__(AsyncSession)
    for fail_status in (ERROR, TIMEOUT):
        async def _broken_async_call(*args, _st=fail_status, **kwargs):
            return RedisResult(_st)

        monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _broken_async_call)
        await _store_roundup_cache_entry(
            ("machinery-nba-night", "live"),
            "machinery-nba-night",
            1_800_000_000.0,
            {"type": "bundle", "data": {"status": "live"}},
            live_cp,
            fake_session,
        )
    assert sync_client_calls == 0

    # 2. `_prewarm_machinery_roundups` publishes live + non-live directly via sync `rc`
    fake_rc2 = _FakeSyncRedis()
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    saved = dict(ROUNDUP_PRODUCERS)

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

    @asynccontextmanager
    async def _fake_session(**kwargs):
        yield object()

    async def _fake_eval(prod, db, *, force_refresh=False, **kwargs):
        cp = live_cp if prod.slug == "machinery-nfl-week" else non_live_cp
        return {"type": "bundle", "slug": prod.slug}, cp

    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS["machinery-nfl-week"] = _make_prod("machinery-nfl-week")
        ROUNDUP_PRODUCERS["machinery-fed-and-macro"] = _make_prod("machinery-fed-and-macro")
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr(
            "app.utils.roundup_containers.evaluate_roundup_producer", _fake_eval
        )
        res = await _prewarm_machinery_roundups(deadline_s=5.0, rc=fake_rc2)
        assert res["outcome"] == "ok"
        assert res["warmed"] == 2
        assert res["redis_written"] == 2
        assert res["redis_read_back"] == 2
        assert res["slugs"]["machinery-nfl-week"]["redis_read_back"] is True
        assert res["slugs"]["machinery-nfl-week"]["redis_ttl_s"] == int(
            ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
        )
        assert res["slugs"]["machinery-fed-and-macro"]["redis_read_back"] is True
        assert res["slugs"]["machinery-fed-and-macro"]["redis_ttl_s"] == int(
            ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
        )
        assert fake_rc2.kv[_redis_cache_key("machinery-nfl-week")][1] == int(
            ROUNDUP_MACHINERY_LIVE_STALE_TTL_S
        )
        assert fake_rc2.kv[_redis_cache_key("machinery-fed-and-macro")][1] == int(
            ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S
        )
        assert "machinery-nfl-week" in fake_rc2.hashes.get(MACHINERY_LIVE_SLUGS_KEY, {})
        assert "machinery-fed-and-macro" not in fake_rc2.hashes.get(
            MACHINERY_LIVE_SLUGS_KEY, {}
        )
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_roundup_cache_serializes_datetime_date_decimal_uuid_in_sync_and_async_writers(
    monkeypatch, caplog
):
    """Regression (#12288 Flip 4): ORM `datetime` fields (e.g. `resolution_date` / `event_date`)
    must serialize cleanly in BOTH `store_roundup_cache_sync` (Celery) and
    `_store_roundup_cache_entry` (web async), and truly unserializable objects must log WARNING
    instead of silently disappearing at DEBUG or raising out of `store_roundup_cache_sync`.
    """
    from datetime import date, datetime, timezone
    from decimal import Decimal
    import json
    import logging
    from unittest.mock import AsyncMock
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.request_cache import OK, RedisResult
    from app.utils.roundup_containers import (
        _redis_cache_key,
        _store_roundup_cache_entry,
        reset_roundup_cache_for_tests,
        store_roundup_cache_sync,
    )

    reset_roundup_cache_for_tests()
    sample_dt = datetime(2026, 12, 18, 19, 0, tzinfo=timezone.utc)
    sample_date = date(2026, 12, 18)
    sample_dec = Decimal("0.875")
    sample_uuid = UUID("12345678-1234-5678-1234-567812345678")

    feed_item = {
        "type": "bundle",
        "data": {
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 114367,
                        "resolution_date": sample_dt,
                        "event_date": sample_date,
                        "price": sample_dec,
                        "trace_id": sample_uuid,
                    },
                }
            ]
        },
    }
    container_payload = {
        "slug": "machinery-fed-and-macro",
        "sections": [
            {
                "members": [
                    {
                        "type": "market",
                        "id": 114367,
                        "card": {
                            "resolution_date": sample_dt,
                            "event_date": sample_date,
                        },
                    }
                ]
            }
        ],
    }

    class _SyncFake:
        def __init__(self):
            self.kv = {}

        def set(self, k, v, ex=None):
            self.kv[k] = (v, ex)
            return True

        def hdel(self, *args):
            return 0

    sync_rc = _SyncFake()
    ok = store_roundup_cache_sync(
        sync_rc,
        "machinery-fed-and-macro",
        1700000000.0,
        feed_item,
        container_payload,
    )
    assert ok is True
    raw_sync, _ex = sync_rc.kv[_redis_cache_key("machinery-fed-and-macro")]
    parsed_sync = json.loads(raw_sync)
    card_sync = parsed_sync["feed_item"]["data"]["items"][0]["data"]
    assert card_sync["resolution_date"] == sample_dt.isoformat()
    assert card_sync["event_date"] == sample_date.isoformat()
    assert card_sync["price"] == pytest.approx(0.875)
    assert card_sync["trace_id"] == str(sample_uuid)

    # Async web writer must also serialize datetime payloads cleanly without calling sync Redis.
    async_kv = {}

    class _AsyncFake:
        async def set(self, k, v, ex=None):
            async_kv[k] = (v, ex)
            return True

        async def hdel(self, *args):
            return 0

    async def _fake_bounded(fn, *, treat_none_as_miss=True):
        val = await fn()
        return RedisResult(status=OK, value=val)

    monkeypatch.setattr(
        "app.utils.request_cache.get_shared_async_redis",
        AsyncMock(return_value=_AsyncFake()),
    )
    monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _fake_bounded)

    fake_db = AsyncSession.__new__(AsyncSession)
    await _store_roundup_cache_entry(
        ("machinery-fed-and-macro", "live"),
        "machinery-fed-and-macro",
        1700000000.0,
        feed_item,
        container_payload,
        fake_db,
    )
    assert _redis_cache_key("machinery-fed-and-macro") in async_kv
    parsed_async = json.loads(async_kv[_redis_cache_key("machinery-fed-and-macro")][0])
    assert (
        parsed_async["container_payload"]["sections"][0]["members"][0]["card"][
            "resolution_date"
        ]
        == sample_dt.isoformat()
    )

    # Truly unserializable objects must return False (sync) and log WARNING (both sync and async).
    bad_payload = {"bad": object()}
    with caplog.at_level(logging.WARNING, logger="app.utils.roundup_containers"):
        assert (
            store_roundup_cache_sync(
                sync_rc,
                "machinery-fed-and-macro",
                1700000000.0,
                bad_payload,
                None,
            )
            is False
        )
        await _store_roundup_cache_entry(
            ("machinery-fed-and-macro", "live"),
            "machinery-fed-and-macro",
            1700000000.0,
            bad_payload,
            None,
            fake_db,
        )
    warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("sync Redis cache write failed" in m for m in warnings)
    assert any("shared cache encode failed" in m for m in warnings)


@pytest.mark.asyncio
async def test_real_nba_grouping_payload_round_trips_from_sync_prewarm_to_cold_web_reader(
    monkeypatch, caplog
):
    """Fable 9:42 PM (#12288 Flip 5 prereq): build a real `machinery-nba-night` grouping
    carrying raw `datetime` fields on its market cards, publish via `store_roundup_cache_sync`,
    confirm `verify_roundup_cache_sync` (exists + positive TTL + decode) and
    `redis_read_back=1/1` log line, then clear local cache and read back through the
    reader's own `evaluate_roundup_producer` path with zero DB calls.
    """
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone
    import logging
    from unittest.mock import AsyncMock
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.tasks.precompute_category_pages import _prewarm_machinery_roundups
    from app.utils.container_machinery import (
        _CANDIDATES_DIR,
        load_machinery_definition,
        produce_container_machinery,
    )
    from app.utils.request_cache import OK, RedisResult
    from app.utils.roundup_containers import (
        ROUNDUP_PRODUCERS,
        RoundupMembers,
        RoundupProducer,
        compose_roundup_container,
        compose_roundup_feed_item,
        evaluate_roundup_producer,
        reset_roundup_cache_for_tests,
        verify_roundup_cache_sync,
    )

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-nba-night.json")
    now_dt = datetime(2026, 11, 20, 2, 0, tzinfo=timezone.utc)
    raw_events = [
        {
            "id": 990001,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Boston Celtics",
            "away_team": "Miami Heat",
            "commence_time": "2026-11-20T01:30:00+00:00",
            "status": "live",
            "home_score": 54,
            "away_score": 52,
            "hero_probability": 0.52,
            "hero_probability_away": 0.48,
            "current_odds": {
                "home_probability": 0.52,
                "away_probability": 0.48,
                "home_rendered_percent": 52,
                "away_rendered_percent": 48,
            },
        },
        {
            "id": 990002,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Los Angeles Lakers",
            "away_team": "Denver Nuggets",
            "commence_time": "2026-11-20T03:00:00+00:00",
            "status": "scheduled",
            "hero_probability": 0.54,
            "hero_probability_away": 0.46,
            "current_odds": {
                "home_probability": 0.54,
                "away_probability": 0.46,
                "home_rendered_percent": 54,
                "away_rendered_percent": 46,
            },
        },
        {
            "id": 990003,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "New York Knicks",
            "away_team": "Milwaukee Bucks",
            "commence_time": "2026-11-20T00:30:00+00:00",
            "status": "scheduled",
            "hero_probability": 0.61,
            "hero_probability_away": 0.39,
            "current_odds": {
                "home_probability": 0.61,
                "away_probability": 0.39,
                "home_rendered_percent": 61,
                "away_rendered_percent": 39,
            },
        },
        {
            "id": 990004,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Golden State Warriors",
            "away_team": "Phoenix Suns",
            "commence_time": "2026-11-20T03:30:00+00:00",
            "status": "scheduled",
            "hero_probability": 0.72,
            "hero_probability_away": 0.28,
            "current_odds": {
                "home_probability": 0.72,
                "away_probability": 0.28,
                "home_rendered_percent": 72,
                "away_rendered_percent": 28,
            },
        },
        {
            "id": 990005,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Cleveland Cavaliers",
            "away_team": "Chicago Bulls",
            "commence_time": "2026-11-20T04:00:00+00:00",
            "status": "scheduled",
            "hero_probability": 0.76,
            "hero_probability_away": 0.24,
            "current_odds": {
                "home_probability": 0.76,
                "away_probability": 0.24,
                "home_rendered_percent": 76,
                "away_rendered_percent": 24,
            },
        },
    ]
    raw_markets = [
        {
            "id": 880001,
            "name": "NBA Points Per Game Leader 2026-27",
            "status": "active",
            "source": "kalshi",
            "mutually_exclusive": True,
            "volume": 500000.0,
            "llm_sport_category": "basketball_nba",
            "resolution_date": datetime(2027, 6, 25, 0, 0, tzinfo=timezone.utc),
            "event_date": datetime(2027, 6, 20, 0, 0, tzinfo=timezone.utc),
            "newest_outcome_updated_at": now_dt.isoformat(),
            "top_outcomes": [
                {"id": 1, "name": "Shai Gilgeous-Alexander", "probability": 0.42, "rendered_percent": 42},
                {"id": 2, "name": "Luka Doncic", "probability": 0.31, "rendered_percent": 31},
                {"id": 3, "name": "Giannis Antetokounmpo", "probability": 0.14, "rendered_percent": 14},
            ],
        },
        {
            "id": 880002,
            "name": "NBA Rebounds Per Game Leader 2026-27",
            "status": "active",
            "source": "kalshi",
            "mutually_exclusive": True,
            "volume": 420000.0,
            "llm_sport_category": "basketball_nba",
            "resolution_date": datetime(2027, 5, 15, 0, 0, tzinfo=timezone.utc),
            "event_date": datetime(2027, 5, 10, 0, 0, tzinfo=timezone.utc),
            "newest_outcome_updated_at": now_dt.isoformat(),
            "top_outcomes": [
                {"id": 11, "name": "Domantas Sabonis", "probability": 0.36, "rendered_percent": 36},
                {"id": 12, "name": "Nikola Jokic", "probability": 0.31, "rendered_percent": 31},
                {"id": 13, "name": "Victor Wembanyama", "probability": 0.17, "rendered_percent": 17},
            ],
        },
        {
            "id": 880003,
            "name": "NBA MVP Winner 2026-27",
            "status": "active",
            "source": "polymarket",
            "mutually_exclusive": True,
            "volume": 310000.0,
            "llm_sport_category": "basketball_nba",
            "resolution_date": datetime(2027, 5, 1, 0, 0, tzinfo=timezone.utc),
            "event_date": datetime(2027, 4, 28, 0, 0, tzinfo=timezone.utc),
            "newest_outcome_updated_at": now_dt.isoformat(),
            "top_outcomes": [
                {"id": 21, "name": "Shai Gilgeous-Alexander", "probability": 0.58, "rendered_percent": 58},
                {"id": 22, "name": "Nikola Jokic", "probability": 0.24, "rendered_percent": 24},
                {"id": 23, "name": "Luka Doncic", "probability": 0.11, "rendered_percent": 11},
            ],
        },
        {
            "id": 880004,
            "name": "NBA Sixth Man of the Year Winner 2026-27",
            "status": "active",
            "source": "kalshi",
            "mutually_exclusive": True,
            "volume": 240000.0,
            "llm_sport_category": "basketball_nba",
            "resolution_date": datetime(2027, 5, 5, 0, 0, tzinfo=timezone.utc),
            "event_date": datetime(2027, 5, 2, 0, 0, tzinfo=timezone.utc),
            "newest_outcome_updated_at": now_dt.isoformat(),
            "top_outcomes": [
                {"id": 31, "name": "Payton Pritchard", "probability": 0.44, "rendered_percent": 44},
                {"id": 32, "name": "Naz Reid", "probability": 0.26, "rendered_percent": 26},
                {"id": 33, "name": "Malik Monk", "probability": 0.15, "rendered_percent": 15},
            ],
        },
        {
            "id": 880005,
            "name": "NBA Defensive Player of the Year Winner 2026-27",
            "status": "active",
            "source": "polymarket",
            "mutually_exclusive": True,
            "volume": 290000.0,
            "llm_sport_category": "basketball_nba",
            "resolution_date": datetime(2027, 5, 8, 0, 0, tzinfo=timezone.utc),
            "event_date": datetime(2027, 5, 4, 0, 0, tzinfo=timezone.utc),
            "newest_outcome_updated_at": now_dt.isoformat(),
            "top_outcomes": [
                {"id": 41, "name": "Victor Wembanyama", "probability": 0.56, "rendered_percent": 56},
                {"id": 42, "name": "Evan Mobley", "probability": 0.21, "rendered_percent": 21},
                {"id": 43, "name": "Chet Holmgren", "probability": 0.12, "rendered_percent": 12},
            ],
        },
    ]
    members = await produce_container_machinery(
        {"events": raw_events, "markets": raw_markets},
        defn,
        now=now_dt,
    )
    assert isinstance(members, RoundupMembers), f"Unexpected refusal: {members!r}"

    produce_spy = AsyncMock(return_value=members)
    prod = RoundupProducer(
        slug="machinery-nba-night",
        name=defn["name"],
        kind="roundup",
        category=defn["category"],
        section_title="",
        footer="",
        produce=produce_spy,
        membership="computed-produced",
        relations=("same_subject",),
        level="member",
        rule={"producer": "container_machinery"},
        enabled=lambda: True,
    )
    fi_built = compose_roundup_feed_item(prod, members)
    cp_built = compose_roundup_container(prod, members)
    assert fi_built is not None and cp_built is not None

    # Shared fake Redis store used by sync prewarm writer AND async web reader.
    store: dict[str, tuple[bytes, int]] = {}

    class _SharedSyncRedis:
        def set(self, k: str, v: str, ex: int | None = None) -> bool:
            store[k] = (v.encode("utf-8"), int(ex or 0))
            return True

        def get(self, k: str) -> bytes | None:
            ent = store.get(k)
            return ent[0] if ent is not None else None

        def ttl(self, k: str) -> int:
            ent = store.get(k)
            return ent[1] if ent is not None else -2

        def hset(self, *args) -> int:
            return 1

        def hdel(self, *args) -> int:
            return 0

        def expire(self, *args) -> bool:
            return True

    class _SharedAsyncRedis:
        async def get(self, k: str) -> bytes | None:
            ent = store.get(k)
            return ent[0] if ent is not None else None

    async def _fake_bounded(fn, *, treat_none_as_miss=True):
        val = await fn()
        return RedisResult(status=OK, value=val)

    @asynccontextmanager
    async def _fake_session(**kwargs):
        yield object()

    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS["machinery-nba-night"] = prod
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )
        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
        monkeypatch.setattr(
            "app.utils.request_cache.get_shared_async_redis",
            AsyncMock(return_value=_SharedAsyncRedis()),
        )
        monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _fake_bounded)

        sync_rc = _SharedSyncRedis()
        with caplog.at_level(logging.INFO, logger="app.tasks.precompute_category_pages"):
            res = await _prewarm_machinery_roundups(deadline_s=5.0, rc=sync_rc)

        assert res["warmed"] == 1
        assert res["redis_written"] == 1
        assert res["redis_read_back"] == 1
        assert any(
            "redis_written=1/1 redis_read_back=1/1" in r.message for r in caplog.records
        )

        rb_ok, rb_ttl = verify_roundup_cache_sync(sync_rc, "machinery-nba-night")
        assert rb_ok is True
        assert rb_ttl is not None and rb_ttl > 0

        # Simulate a cold web dyno: clear local cache and reset produce_spy, then
        # read back via evaluate_roundup_producer(prod, AsyncSession).
        reset_roundup_cache_for_tests()
        produce_spy.reset_mock()
        fake_async_db = AsyncSession.__new__(AsyncSession)
        read_fi, read_cp = await evaluate_roundup_producer(
            prod, fake_async_db, allow_stale=True
        )
        assert produce_spy.await_count == 0
        assert read_fi is not None and read_cp is not None
        assert read_cp["slug"] == "machinery-nba-night"
        assert read_fi["type"] == "bundle"
        assert read_fi["data"]["collection_ref"]["slug"] == "machinery-nba-night"
        assert len(read_cp["sections"]) >= 1
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_flip6_machinery_prewarm_publishes_response_and_page_base_and_skips_per_read_not_trading_db(
    monkeypatch,
):
    """#12288 Flip 6:
    1. `_publish_machinery_feed_from_prewarm_base` derives the `machinery=1` Discover
       response key (`feed:v1:...`), `feed:machinery_pagebase:...`, and edition manifest
       from the just-built plain Discover base in pure Python (0 DB queries), refuses
       to publish a partial set if any grouping is missing from Redis, and backdates
       `built_at` to the oldest live machinery grouping origin (`CERT-409`).
    2. `add_roundup_feed_items(..., machinery_only=True)` does NOT call
       `drop_not_trading_roundup_members` on the hot reader path (zero ~580 ms DB query),
       while `_prewarm_machinery_roundups` runs `drop_not_trading_roundup_members` once
       before writing to Redis.
    """
    import json
    import time
    from unittest.mock import AsyncMock

    from app.tasks.precompute_category_pages import (
        _publish_machinery_feed_from_prewarm_base,
    )
    from app.utils.feed_cache import (
        FEED_EDITION_FIELD,
        FEED_PAGE_BASE_BUILT_AT_FIELD,
        feed_machinery_page_base_key,
        feed_page_base_cache_key,
        feed_response_cache_key,
    )
    from app.utils.roundup_containers import (
        ROUNDUP_PRODUCERS,
        RoundupProducer,
        _redis_cache_key,
        add_roundup_feed_items,
        reset_roundup_cache_for_tests,
        store_roundup_cache_sync,
    )

    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    class _SyncRedis:
        def __init__(self) -> None:
            self.kv: dict[str, tuple[str, int | None]] = {}

        def set(self, k: str, v: str, ex: int | None = None) -> bool:
            self.kv[k] = (v, ex)
            return True

        def setex(self, k: str, ttl: int, v: str) -> bool:
            self.kv[k] = (v, ttl)
            return True

        def get(self, k: str) -> str | None:
            ent = self.kv.get(k)
            return ent[0] if ent is not None else None

        def hset(self, *args) -> int:
            return 1

        def hdel(self, *args) -> int:
            return 0

        def expire(self, *args) -> bool:
            return True

    def _make_item(idx: int) -> dict:
        return {
            "type": "futures",
            "score": 80.0 - idx * 0.2,
            "data": {"id": 50000 + idx, "name": f"Card {idx}", "category": "politics"},
        }

    plain_items = [_make_item(i) for i in range(40)]
    now_ts = time.time()
    base_built_at = now_ts - 2.0
    older_live_built_at = now_ts - 18.0

    cache_shape = dict(
        sport=None,
        limit=20,
        offset=0,
        include_events=True,
        include_futures=True,
        tags=None,
        event_pct=0.15,
        my_teams_only=False,
        mode=None,
        category=None,
        edition=None,
        collections=None,
        opening_seating=False,
        machinery=False,
        fun_admission=False,
    )
    plain_pb_key = feed_page_base_cache_key(
        **{k: v for k, v in cache_shape.items() if k not in ("offset", "edition", "machinery")}
    )
    mach_base_ctx = {
        "page_base_key": plain_pb_key,
        "page_base_body": {
            "items": plain_items,
            "total": len(plain_items),
            FEED_PAGE_BASE_BUILT_AT_FIELD: base_built_at,
        },
        "cache_shape": cache_shape,
        "limit": 20,
        "offset": 0,
        "opening_seating": False,
        "edition_policy": "default",
        "age_origin": base_built_at,
    }

    def _make_mach_prod(slug: str) -> RoundupProducer:
        return RoundupProducer(
            slug=slug,
            name=slug,
            kind="roundup",
            category="basketball",
            section_title="",
            footer="",
            produce=AsyncMock(),
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        )

    def _make_mach_fi(slug: str, *, live: bool = False) -> tuple[dict, dict]:
        fi = {
            "type": "bundle",
            "score": 70.0,
            "reason": slug,
            "headline": slug,
            "data": {
                "id": f"roundup:{slug}",
                "title": slug,
                "kind": "roundup",
                "story_key": f"roundup:{slug}",
                "item_count": 1,
                "member_ids": [999001 if live else 999002],
                "items": [],
                "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": slug},
                "roundup": {"kicker": "NBA", "rows": [], "machinery_card": {"slug": slug}},
                **({"status": "live"} if live else {}),
            },
        }
        cp = {
            "slug": slug,
            "sections": [
                {
                    "members": [
                        {
                            "type": "event" if live else "market",
                            "id": 999001 if live else 999002,
                            "card": {"id": 999001 if live else 999002, "status": "live" if live else "active"},
                        }
                    ]
                }
            ],
        }
        return fi, cp

    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS["machinery-nba-night"] = _make_mach_prod("machinery-nba-night")
        ROUNDUP_PRODUCERS["machinery-fed-and-macro"] = _make_mach_prod("machinery-fed-and-macro")
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )

        rc = _SyncRedis()
        nba_fi, nba_cp = _make_mach_fi("machinery-nba-night", live=True)
        fed_fi, fed_cp = _make_mach_fi("machinery-fed-and-macro", live=False)

        # 1. Incomplete Redis (1/2) must refuse to publish a half-populated page.
        store_roundup_cache_sync(rc, "machinery-nba-night", older_live_built_at, nba_fi, nba_cp)
        inc_res = _publish_machinery_feed_from_prewarm_base(
            rc, mach_base=mach_base_ctx, label="discover"
        )
        assert inc_res["outcome"] == "incomplete"
        mach_resp_key = feed_response_cache_key(
            user_id=None, session_id=None, **{**cache_shape, "machinery": True}
        )
        mach_pb_key = feed_machinery_page_base_key(plain_pb_key)
        assert mach_resp_key not in rc.kv
        assert mach_pb_key not in rc.kv

        # 2. All registered groupings present (2/2) -> publishes response + machinery page base + edition manifest.
        store_roundup_cache_sync(rc, "machinery-fed-and-macro", now_ts - 1.0, fed_fi, fed_cp)
        ok_res = _publish_machinery_feed_from_prewarm_base(
            rc, mach_base=mach_base_ctx, label="discover"
        )
        assert ok_res["outcome"] == "ok"
        assert ok_res["groupings"] == 2
        assert ok_res["live"] is True
        assert mach_resp_key in rc.kv
        assert f"{mach_resp_key}:stale" in rc.kv
        assert mach_pb_key in rc.kv
        assert f"{mach_pb_key}:stale" in rc.kv

        published_pb = json.loads(rc.kv[mach_pb_key][0])
        slugs_in_pb = [
            ((it.get("data") or {}).get("collection_ref") or {}).get("slug")
            for it in published_pb["items"]
        ]
        assert "machinery-nba-night" in slugs_in_pb
        assert "machinery-fed-and-macro" in slugs_in_pb
        # Honest live age origin (CERT-409): backdated to the older live machinery grouping.
        assert published_pb[FEED_PAGE_BASE_BUILT_AT_FIELD] == pytest.approx(
            older_live_built_at, abs=0.01
        )
        assert published_pb.get(FEED_EDITION_FIELD)

        # 3. `add_roundup_feed_items(..., machinery_only=True)` must NOT call drop_not_trading_roundup_members.
        not_trading_spy = AsyncMock(side_effect=AssertionError("must not hit DB on hot machinery splice"))
        monkeypatch.setattr(
            "app.utils.not_trading.drop_not_trading_roundup_members",
            not_trading_spy,
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.evaluate_roundup_producer",
            AsyncMock(side_effect=[(nba_fi, nba_cp), (fed_fi, fed_cp)]),
        )
        spliced = await add_roundup_feed_items(
            object(),
            list(plain_items),
            include_machinery=True,
            machinery_only=True,
        )
        assert not_trading_spy.await_count == 0
        spliced_slugs = [
            ((it.get("data") or {}).get("collection_ref") or {}).get("slug")
            for it in spliced
        ]
        assert "machinery-nba-night" in spliced_slugs
        assert "machinery-fed-and-macro" in spliced_slugs
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
