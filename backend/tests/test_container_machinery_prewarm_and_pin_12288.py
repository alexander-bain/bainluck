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
