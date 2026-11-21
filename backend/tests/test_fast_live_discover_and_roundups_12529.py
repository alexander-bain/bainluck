"""#12529 — Fast live Discover (<1s median) and zero dropped round-up cards."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Response
from starlette.requests import Request

from app.utils import feed_cache as fc
from app.utils import roundup_containers as rc_mod

pcp = import_module("app.tasks.precompute_category_pages")


def test_discover_and_discover_native_run_in_wave_1_before_sports() -> None:
    """Both Discover shapes must occupy Wave 1 ahead of Sports so 3 Sports shapes never starve Discover."""
    labels = [s["label"] for s in pcp.FEED_PREWARM_SHAPES]
    assert labels[:2] == ["discover", "discover_native"]
    assert "sports_native" in labels[fc.FEED_LIVE_REPUBLISH_CONCURRENCY :]
    assert "sports_native_events" in labels[fc.FEED_LIVE_REPUBLISH_CONCURRENCY :]


@pytest.mark.asyncio
async def test_limit20_discover_enrolls_as_live_when_page_base_or_machinery_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When live games sit at seat >= 20, `discover` page-base and `:machinery` still expire at <=60s.

    The 20-card top slice reads `live=False`, so `_prewarm_feed_shape` must enroll
    `"discover"` on the 30s rail whenever `_mach_base_ctx["page_base_body"]` OR the
    spliced `:machinery` bundle contains a live event, and record page-base +
    machinery hashes so `_absent_prewarm_labels` checks the keys the web actually reads.
    """
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

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

    fake_rc = MagicMock()
    fake_rc.pipeline.side_effect = lambda transaction=True: _FakePipe()
    fake_rc.hset.side_effect = lambda k, f, v: hashes.setdefault(k, {}).__setitem__(f, v)
    fake_rc.hgetall.side_effect = lambda k: dict(hashes.get(k, {}))
    fake_rc.setex.side_effect = lambda k, ttl, v: written_keys.__setitem__(k, (ttl, v))
    fake_rc.exists.side_effect = lambda k: 1 if k in written_keys else 0

    full_deck = [
        {"type": "futures", "id": "f-1", "data": {"id": 1, "status": "open"}},
        {"type": "event", "id": "ev-live", "data": {"id": 999, "status": "live"}},
    ]

    async def _fake_get_feed(**kwargs):
        req: Request = kwargs["request"]
        req.scope[fc.FEED_PREWARM_KEY_SCOPE_KEY] = "feed_cache:disc20"
        req.scope[fc.FEED_PREWARM_MACHINERY_BASE_SCOPE_KEY] = {
            "page_base_key": "feed:pagebase:disc20",
            "page_base_body": {"items": full_deck, "total": len(full_deck)},
            "page_base_fresh_ttl": 30,
            "page_base_stale_ttl": 60,
            "page_base_last_good_ttl": 60,
            "cache_shape": {"limit": 20, "offset": 0, "event_pct": 0.15, "mode": "discover"},
            "limit": 20,
            "offset": 0,
            "opening_seating": True,
            "edition_policy": "default",
            "age_origin": 1_800_000_000.0,
        }
        return {
            "items": [full_deck[0]],
            "total": len(full_deck),
            "cache": {"status": "miss", "built_at": 1_800_000_000.0},
        }

    def _fake_splice(rc, *, mach_base, label):
        written_keys["feed:machinery_pagebase:disc20"] = (30, "{}")
        written_keys["feed:machinery_pagebase:disc20:stale"] = (60, "{}")
        return {
            "outcome": "ok",
            "live": True,
            "page_base_key": "feed:machinery_pagebase:disc20",
        }

    @asynccontextmanager
    async def _fake_session():
        yield MagicMock()

    discover_shape = next(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover")
    with (
        patch("app.routes.feed.get_feed", _fake_get_feed),
        patch("app.tasks.base.get_task_session", _fake_session),
        patch.object(pcp, "_publish_machinery_feed_from_prewarm_base", _fake_splice),
        patch("app.utils.feed_served_markets.record_served_market_ids"),
    ):
        res = await pcp._prewarm_feed_shape(dict(discover_shape), fake_rc)

    assert res["outcome"] == "ok"
    assert hashes[pcp.FEED_PREWARM_LIVE_SHAPES_KEY].get("discover") == "1"
    assert hashes[pcp.FEED_PREWARM_PAGE_BASE_KEYS_KEY]["discover"] == "feed:pagebase:disc20"
    assert (
        hashes[pcp.FEED_PREWARM_MACHINERY_KEYS_KEY]["discover"]
        == "feed:machinery_pagebase:disc20"
    )

    # All three stale keys exist (simulate feed_cache:stale surviving at 300s while
    # :machinery:stale expires at 60s): removing `:machinery:stale` MUST trigger absent.
    written_keys["feed_cache:disc20:stale"] = (300, "{}")
    assert pcp._absent_prewarm_labels(fake_rc) == set()
    written_keys.pop("feed:machinery_pagebase:disc20:stale")
    assert pcp._absent_prewarm_labels(fake_rc) == {"discover"}
    for call in fake_rc.exists.call_args_list:
        assert str(call.args[0]).endswith(":stale")


def test_render_machinery_bundle_subtracts_input_age_and_refuses_over_60s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spliced live `:machinery` bundles must never serve older than 60s total."""
    monkeypatch.setenv("FEED_EDITION_POLICY_DISABLED", "0")
    base_items = [
        {
            "type": "event",
            "score": 90.0,
            "data": {"id": 500, "status": "live", "commence_time": "2026-11-21T18:00:00Z"},
        }
    ]
    now_ts = 1_800_000_050.0
    bundle = rc_mod.render_machinery_prewarm_bundle(
        mach_base={
            "page_base_body": {"items": base_items, "total": len(base_items)},
            "page_base_key": "feed:pagebase:test",
            "age_origin": now_ts - 15.0,
            "opening_seating": False,
            "limit": 20,
            "offset": 0,
            "cache_shape": {"limit": 20, "offset": 0, "event_pct": 0.15, "mode": "discover"},
        },
        produced=[],
        oldest_live_built_at=None,
        now_ts=now_ts,
    )
    assert bundle is not None
    assert bundle["live"] is True
    assert bundle["stale_ttl"] == 45

    # When inputs are already >= 60s old, refuse to publish rather than violate #2216.
    expired_bundle = rc_mod.render_machinery_prewarm_bundle(
        mach_base={
            "page_base_body": {"items": base_items, "total": len(base_items)},
            "page_base_key": "feed:pagebase:test",
            "age_origin": now_ts - 60.0,
            "opening_seating": False,
            "limit": 20,
            "offset": 0,
            "cache_shape": {"limit": 20, "offset": 0, "event_pct": 0.15, "mode": "discover"},
        },
        produced=[],
        oldest_live_built_at=None,
        now_ts=now_ts,
    )
    assert expired_bundle is None


def _make_standing_producer(
    slug: str,
    *,
    enabled: bool = True,
    rule: dict | None = None,
    produce_fn=None,
) -> rc_mod.RoundupProducer:
    async def _default_prod(_db, *, now=None):
        return None

    return rc_mod.RoundupProducer(
        slug=slug,
        name=slug,
        kind="roundup",
        category="other",
        section_title="Markets",
        footer="",
        produce=produce_fn or _default_prod,
        membership="computed-produced",
        relations=("same_subject",),
        level="member",
        rule=rule if rule is not None else {},
        enabled=lambda: enabled,
    )


@pytest.mark.asyncio
async def test_add_roundup_feed_items_skips_disabled_and_runs_yardstick_before_budget_exhausts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled producers must not increment `dropped_no_copy`, and uncacheable yardstick
    pairs run before slow cached producers while preserving output card order."""
    rc_mod.reset_roundup_cache_for_tests()
    now = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)

    async def _slow_cached(_db, *, now=None):
        await asyncio.sleep(0.08)
        return rc_mod.RoundupMembers(
            members=[
                {"type": "market", "id": 1, "destination": "/futures/1", "card": {"id": 1, "name": "Cached A"}},
                {"type": "market", "id": 11, "destination": "/futures/11", "card": {"id": 11, "name": "Cached B"}},
            ],
            rows=[
                {"market_id": 1, "outcome_id": 1, "label": "Cached A", "probability": 0.5, "rendered_percent": 50},
                {"market_id": 11, "outcome_id": 11, "label": "Cached B", "probability": 0.4, "rendered_percent": 40},
            ],
            title="Cached Card",
        )

    async def _fast_yardstick(_db, *, now=None):
        return rc_mod.RoundupMembers(
            members=[
                {"type": "market", "id": 2, "destination": "/futures/2", "card": {"id": 2, "name": "Scale A"}},
                {"type": "market", "id": 3, "destination": "/futures/3", "card": {"id": 3, "name": "Scale B"}},
            ],
            rows=[
                {"market_id": 2, "outcome_id": 2, "label": "Scale A", "probability": 0.4, "rendered_percent": 40},
                {"market_id": 3, "outcome_id": 3, "label": "Scale B", "probability": 0.39, "rendered_percent": 39},
            ],
            title="For scale Card",
        )

    producers = {
        "disabled-seasonal": _make_standing_producer("disabled-seasonal", enabled=False),
        "slow-first": _make_standing_producer("slow-first", produce_fn=_slow_cached),
        "for-scale-test": _make_standing_producer(
            "for-scale-test",
            rule={"cache": "none"},
            produce_fn=_fast_yardstick,
        ),
    }
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)

    async def _no_screen(db, produced, now_arg, cov):
        return produced

    monkeypatch.setattr("app.utils.not_trading.drop_not_trading_roundup_members", _no_screen)

    base_items = [
        {"type": "futures", "score": 80 - i, "data": {"id": 7000 + i, "name": f"M{i}", "status": "open"}}
        for i in range(25)
    ]
    before = rc_mod.get_roundup_read_failure_stats_10m(now=now.timestamp())
    out = await rc_mod.add_roundup_feed_items(
        object(),
        base_items,
        stage_budget_seconds=0.05,
        budget_seconds=1.0,
        now=now,
    )
    after = rc_mod.get_roundup_read_failure_stats_10m(now=now.timestamp())

    slugs = [
        (it.get("data") or {}).get("collection_ref", {}).get("slug")
        for it in out
        if it.get("type") == "bundle" and (it.get("data") or {}).get("kind") == "roundup"
    ]
    assert "for-scale-test" in slugs
    assert "disabled-seasonal" not in slugs
    # Disabled producer was skipped before loop; slow-first exceeded 0.05s stage budget,
    # so only the un-cached slow-first failure incremented (never disabled-seasonal).
    assert after["dropped_no_copy"] - before["dropped_no_copy"] == 1


@pytest.mark.asyncio
async def test_prewarm_standing_roundups_caches_300s_nonlive_60s_live_and_never_caches_yardstick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standing prewarm stores 300s fresh for non-live, 60s + live rail for live,
    nothing_to_show for empty, and never writes `yardstick_pair`."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    kv: dict[str, tuple[str, int]] = {}
    hashes: dict[str, dict[str, str]] = {}

    fake_rc = MagicMock()
    fake_rc.set.side_effect = lambda k, v, ex=0: kv.__setitem__(k, (v, ex))
    fake_rc.get.side_effect = lambda k: kv[k][0] if k in kv else None
    fake_rc.ttl.side_effect = lambda k: kv[k][1] if k in kv else -2
    fake_rc.hset.side_effect = lambda k, f, v: hashes.setdefault(k, {}).__setitem__(f, v)
    fake_rc.hdel.side_effect = lambda k, f: hashes.setdefault(k, {}).pop(f, None)
    fake_rc.hgetall.side_effect = lambda k: dict(hashes.get(k, {}))
    fake_rc.exists.side_effect = lambda k: 1 if k in kv else 0

    producers = {
        "roundup-nonlive": _make_standing_producer("roundup-nonlive"),
        "roundup-live": _make_standing_producer("roundup-live"),
        "roundup-empty": _make_standing_producer("roundup-empty"),
        "for-scale-never": _make_standing_producer(
            "for-scale-never", rule={"producer": "yardstick_pair", "cache": "none"}
        ),
    }
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", producers)

    @asynccontextmanager
    async def _fake_session(**kwargs):
        yield MagicMock()

    async def _fake_eval(prod, db, *, force_refresh=False, outcome_meta=None):
        assert prod.slug != "for-scale-never"
        if prod.slug == "roundup-nonlive":
            return {"type": "bundle"}, {
                "slug": prod.slug,
                "sections": [{"members": [{"type": "market", "card": {"status": "open"}}]}],
            }
        if prod.slug == "roundup-live":
            return {"type": "bundle"}, {
                "slug": prod.slug,
                "sections": [{"members": [{"type": "event", "card": {"status": "live"}}]}],
            }
        if outcome_meta is not None:
            outcome_meta["clean_empty"] = True
            outcome_meta["reason"] = "quiet_tonight"
        return None, None

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(rc_mod, "evaluate_roundup_producer", _fake_eval)

    res = await pcp._prewarm_standing_roundups(deadline_s=5.0, rc=fake_rc)
    assert res["outcome"] == "ok"
    assert res["warmed"] == 2

    nonlive_entry = json.loads(kv[rc_mod._redis_cache_key("roundup-nonlive")][0])
    live_entry = json.loads(kv[rc_mod._redis_cache_key("roundup-live")][0])
    empty_entry = json.loads(kv[rc_mod._redis_cache_key("roundup-empty")][0])
    assert nonlive_entry["ttl_s"] == rc_mod.ROUNDUP_STANDING_PREWARM_FRESH_TTL_S == 300.0
    assert live_entry["ttl_s"] == rc_mod.ROUNDUP_CACHE_TTL_S == 60.0
    assert empty_entry["nothing_to_show"] is True
    assert rc_mod._redis_cache_key("for-scale-never") not in kv
    assert set(hashes[rc_mod.STANDING_LIVE_SLUGS_KEY]) == {"roundup-live"}

    # Live standing pass refreshes only `roundup-live` (and absent warmed keys),
    # and fails closed (`idle`) on an empty mock Redis.
    seen_slugs: list[tuple[str, ...]] = []

    async def _fake_warm_stand(*, deadline_s=15.0, slugs=None, rc=None):
        seen_slugs.append(tuple(sorted(slugs or ())))
        return {"outcome": "ok", "warmed": len(seen_slugs[-1]), "slugs": {}}

    with patch.object(pcp, "_prewarm_standing_roundups", _fake_warm_stand):
        live_res = await pcp._prewarm_live_standing_roundups(fake_rc, deadline_s=10.0)
        idle_res = await pcp._prewarm_live_standing_roundups(MagicMock(hgetall=lambda _k: {}))

    assert live_res["outcome"] == "ok"
    assert seen_slugs == [("roundup-live",)]
    assert idle_res == {"outcome": "idle", "warmed": 0}


@pytest.mark.asyncio
async def test_live_feed_shapes_resplices_live_machinery_after_gather_when_warmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `gather` warms live machinery after Discover finishes, post-gather re-splices `:machinery`."""
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    async def _run_case(*, warmed_count: int) -> tuple[int, dict[str, tuple[int, str]], dict[str, dict[str, str]]]:
        hashes: dict[str, dict[str, str]] = {
            pcp.FEED_PREWARM_LIVE_SHAPES_KEY: {"discover": "1"},
        }
        written_keys: dict[str, tuple[int, str]] = {}
        splice_calls = 0
        machinery_refreshed = False

        class _Pipe:
            def __init__(self) -> None:
                self.ops: list[tuple] = []

            def hset(self, key: str, field: str, value: str):
                self.ops.append(("hset", key, field, value))
                return self

            def hdel(self, key: str, field: str):
                self.ops.append(("hdel", key, field))
                return self

            def expire(self, key: str, ttl: int):
                return self

            def execute(self) -> None:
                for op, k, f, *rest in self.ops:
                    if op == "hset":
                        hashes.setdefault(k, {})[f] = rest[0]
                    elif op == "hdel":
                        hashes.setdefault(k, {}).pop(f, None)

        fake_rc = MagicMock()
        fake_rc.pipeline.side_effect = lambda transaction=True: _Pipe()
        fake_rc.get.return_value = None
        fake_rc.hset.side_effect = lambda k, f, v: hashes.setdefault(k, {}).__setitem__(f, v)
        fake_rc.hgetall.side_effect = lambda k: dict(hashes.get(k, {}))
        fake_rc.setex.side_effect = lambda k, ttl, v: written_keys.__setitem__(k, (ttl, v))
        fake_rc.exists.side_effect = lambda k: 1 if k in written_keys else 0

        full_deck = [
            {"type": "futures", "id": "f-1", "data": {"id": 1, "status": "open"}},
            {"type": "event", "id": "ev-live", "data": {"id": 999, "status": "live"}},
        ]

        async def _fake_get_feed(**kwargs):
            req: Request = kwargs["request"]
            req.scope[fc.FEED_PREWARM_KEY_SCOPE_KEY] = "feed_cache:disc20"
            req.scope[fc.FEED_PREWARM_MACHINERY_BASE_SCOPE_KEY] = {
                "page_base_key": "feed:pagebase:disc20",
                "page_base_body": {"items": full_deck, "total": len(full_deck)},
                "page_base_fresh_ttl": 30,
                "page_base_stale_ttl": 60,
                "page_base_last_good_ttl": 60,
                "cache_shape": {"limit": 20, "offset": 0, "event_pct": 0.15, "mode": "discover"},
                "limit": 20,
                "offset": 0,
                "opening_seating": True,
                "edition_policy": "default",
                "age_origin": 1_800_000_000.0,
            }
            return {
                "items": [full_deck[0]],
                "total": len(full_deck),
                "cache": {"status": "miss", "built_at": 1_800_000_000.0},
            }

        def _fake_splice(rc, *, mach_base, label):
            nonlocal splice_calls
            splice_calls += 1
            ttl = 60 if machinery_refreshed else 25
            pb_key = f"feed:machinery_pagebase:disc20:{'fresh' if machinery_refreshed else 'stale'}"
            written_keys["feed:machinery_pagebase:disc20:stale"] = (ttl, "{}")
            return {"outcome": "ok", "live": True, "page_base_key": pb_key}

        async def _fake_mach_live(rc, *, deadline_s=20.0):
            nonlocal machinery_refreshed
            await asyncio.sleep(0)
            if warmed_count > 0:
                machinery_refreshed = True
            return {"outcome": "ok" if warmed_count else "idle", "warmed": warmed_count}

        async def _fake_stand_live(rc, *, deadline_s=15.0):
            return {"outcome": "idle", "warmed": 0}

        @asynccontextmanager
        async def _fake_session():
            yield MagicMock()

        discover_only = tuple(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover")
        with (
            patch("app.tasks.redis_state.get_redis_client", lambda: fake_rc),
            patch("app.routes.feed.get_feed", _fake_get_feed),
            patch("app.tasks.base.get_task_session", _fake_session),
            patch.object(pcp, "FEED_PREWARM_SHAPES", discover_only),
            patch.object(pcp, "_publish_machinery_feed_from_prewarm_base", _fake_splice),
            patch.object(pcp, "_prewarm_live_machinery_roundups", _fake_mach_live),
            patch.object(pcp, "_prewarm_live_standing_roundups", _fake_stand_live),
            patch("app.utils.feed_served_markets.record_served_market_ids"),
        ):
            await pcp._prewarm_live_feed_shapes()

        return splice_calls, written_keys, hashes

    calls_warmed, written_warmed, hashes_warmed = await _run_case(warmed_count=1)
    assert calls_warmed == 2
    assert written_warmed["feed:machinery_pagebase:disc20:stale"][0] == 60
    assert (
        hashes_warmed[pcp.FEED_PREWARM_MACHINERY_KEYS_KEY]["discover"]
        == "feed:machinery_pagebase:disc20:fresh"
    )

    calls_idle, written_idle, hashes_idle = await _run_case(warmed_count=0)
    assert calls_idle == 1
    assert written_idle["feed:machinery_pagebase:disc20:stale"][0] == 25
    assert (
        hashes_idle[pcp.FEED_PREWARM_MACHINERY_KEYS_KEY]["discover"]
        == "feed:machinery_pagebase:disc20:stale"
    )

