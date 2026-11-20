"""Tests for Step 7 follow-ups from #13184 and #13186.

Covers all five follow-up requirements from Fable's reviews:
1. Out-of-time branch treats an unexpired quiet grouping (#13186 mark) as quiet,
   not incomplete — so the remaining groupings still publish instead of dropping all.
2. Out-of-time branch reads shared Redis kept copies TOGETHER in one batched MGET
   call instead of N sequential GET calls.
3. Clock rule (`_roundup_effective_keep_seconds`) applies to groupings' own kept
   copies (`evaluate_roundup_producer(allow_stale=True)` and
   `_publish_machinery_feed_from_prewarm_base`): copy built 2 min before tip-off is
   kept 2 min into the game and expires 8 min into the game.
4. Quiet mark carries `clean_empty_reason` (the actual refusal reason, e.g.
   `missing_paired_stage` vs `zero_members`) and `_publish_machinery_feed_from_prewarm_base`
   prints it in the "cleanly empty" log line.
5. Missing #13186 neighbour: a plain refusal note written by a web process
   (`feed_item=None, container_payload=None`, no `clean_empty` flag) is treated as
   missing/absent and refuses publication (`outcome == "incomplete"`).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.precompute_category_pages import (
    _prewarm_machinery_roundups,
    _publish_machinery_feed_from_prewarm_base,
)
from app.utils.roundup_containers import (
    ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S,
    ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
    RoundupProducer,
    RoundupRefusal,
    _encode_roundup_cache_entry,
    _redis_cache_key,
    _roundup_local_cache,
    add_roundup_feed_items,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
    store_roundup_cache_sync,
    store_roundup_clean_empty_sync,
)


class _FakeSyncRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.store[key] = value
        self.ttls[key] = int(ttl)
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    def hset(self, key: str, field: str, value: str) -> int:
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def hdel(self, key: str, field: str) -> int:
        return 1 if self.hashes.get(key, {}).pop(field, None) is not None else 0

    def expire(self, _key: str, _ttl: int) -> bool:
        return True


class _FakeAsyncRedisBatch:
    def __init__(self, store: dict[str, str]) -> None:
        self.store = dict(store)
        self.mget_calls: list[list[str]] = []
        self.get_calls: list[str] = []

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.mget_calls.append(list(keys))
        return [self.store.get(k) for k in keys]

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True


def _fake_card(slug: str, idx: int, *, commence_time_iso: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    card_inner: dict[str, Any] = {"id": 5000 + idx, "status": "scheduled"}
    if commence_time_iso is not None:
        card_inner["commence_time"] = commence_time_iso
    fi = {
        "type": "bundle",
        "score": 95.0 - idx,
        "reason": f"{slug} headline",
        "headline": f"{slug} headline",
        "data": {
            "id": f"roundup:{slug}",
            "title": f"{slug} headline",
            "kind": "roundup",
            "story_key": f"roundup:{slug}",
            "item_count": 3,
            "member_ids": [5000 + idx],
            "items": [],
            "collection_ref": {
                "slug": slug,
                "href": f"/collections/{slug}",
                "name": f"{slug} headline",
                "revision": 1,
                "collection_count": 3,
            },
            "roundup": {"kicker": "TEST", "footer": "", "rows": []},
        },
    }
    cp = {
        "slug": slug,
        "sections": [
            {"members": [{"type": "event", "id": 5000 + idx, "card": card_inner}]}
        ],
    }
    return fi, cp


def _patch_async_redis(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    async def _get_client():
        return client

    async def _bounded(fn, **_kw):
        val = await fn()
        return type("_Res", (), {"is_ok": True, "value": val})()

    monkeypatch.setattr("app.utils.request_cache.get_shared_async_redis", _get_client)
    monkeypatch.setattr("app.utils.request_cache.bounded_redis_call", _bounded)


@pytest.mark.asyncio
async def test_out_of_time_branch_reads_shared_copies_together_and_honors_quiet_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_READ_CACHE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    now_ts = 1_800_000_000.0

    slugs = ["machinery-alpha", "machinery-beta", "machinery-gamma"]
    fi_a, cp_a = _fake_card("machinery-alpha", 1)
    fi_b, cp_b = _fake_card("machinery-beta", 2)

    sync_rc = _FakeSyncRedis()
    store_roundup_cache_sync(sync_rc, "machinery-alpha", now_ts - 60, fi_a, cp_a)
    store_roundup_cache_sync(sync_rc, "machinery-beta", now_ts - 60, fi_b, cp_b)
    # Gamma is properly quiet with an explicit refusal reason
    store_roundup_clean_empty_sync(sync_rc, "machinery-gamma", now_ts - 60, reason="zero_members")

    async_rc = _FakeAsyncRedisBatch(sync_rc.store)
    _patch_async_redis(monkeypatch, async_rc)

    producers = {
        s: RoundupProducer(
            slug=s,
            name=s,
            kind="roundup",
            category="sports",
            section_title="Section",
            footer="",
            produce=lambda _db: None,
        )
        for s in slugs
    }
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )

    fake_db = MagicMock(spec=AsyncSession)
    # Stage budget 0.0 forces immediate out-of-time branch on all 3 producers
    base_items = [
        {"type": "futures", "score": 50.0, "data": {"id": 999 + i, "name": f"Base {i}"}}
        for i in range(6)
    ]
    out_items = await add_roundup_feed_items(
        fake_db,
        base_items,
        seat_floor=1,
        now=datetime.fromtimestamp(now_ts, tz=timezone.utc),
        budget_seconds=1.0,
        stage_budget_seconds=0.0,
        include_machinery=True,
    )

    # Batched: ONE mget covering all 3 keys, ZERO serial get calls
    assert len(async_rc.mget_calls) == 1
    assert set(async_rc.mget_calls[0]) == {_redis_cache_key(s) for s in slugs}
    assert async_rc.get_calls == []

    # Quiet gamma did NOT trigger machinery_incomplete -> alpha and beta both appear
    served_slugs = [
        it.get("data", {}).get("collection_ref", {}).get("slug")
        for it in out_items
        if it.get("type") == "bundle"
    ]
    assert set(served_slugs) == {"machinery-alpha", "machinery-beta"}


@pytest.mark.asyncio
async def test_out_of_time_branch_treats_plain_web_refusal_note_as_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_READ_CACHE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    now_ts = 1_800_000_000.0

    fi_a, cp_a = _fake_card("machinery-alpha", 1)
    sync_rc = _FakeSyncRedis()
    store_roundup_cache_sync(sync_rc, "machinery-alpha", now_ts - 60, fi_a, cp_a)
    # Plain web refusal note (no card, NO clean_empty flag) -> MUST count as incomplete
    sync_rc.set(
        _redis_cache_key("machinery-beta"),
        _encode_roundup_cache_entry(
            ts=now_ts - 30,
            ttl_s=60.0,
            stale_ttl_s=60.0,
            feed_item=None,
            container_payload=None,
            clean_empty=False,
        ),
        ex=60,
    )

    async_rc = _FakeAsyncRedisBatch(sync_rc.store)
    _patch_async_redis(monkeypatch, async_rc)

    producers = {
        s: RoundupProducer(
            slug=s,
            name=s,
            kind="roundup",
            category="sports",
            section_title="Section",
            footer="",
            produce=lambda _db: None,
        )
        for s in ("machinery-alpha", "machinery-beta")
    }
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )

    fake_db = MagicMock(spec=AsyncSession)
    base_items = [
        {"type": "futures", "score": 50.0, "data": {"id": 999 + i, "name": f"Base {i}"}}
        for i in range(6)
    ]
    out_items = await add_roundup_feed_items(
        fake_db,
        base_items,
        seat_floor=1,
        now=datetime.fromtimestamp(now_ts, tz=timezone.utc),
        budget_seconds=1.0,
        stage_budget_seconds=0.0,
        include_machinery=True,
    )

    # All-or-nothing drops machinery cards when beta is a plain refusal (not quiet)
    bundle_slugs = [
        it.get("data", {}).get("collection_ref", {}).get("slug")
        for it in out_items
        if it.get("type") == "bundle"
    ]
    assert bundle_slugs == []


@pytest.mark.asyncio
async def test_clock_rule_applies_to_groupings_own_kept_copies_after_tipoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_READ_CACHE_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")

    # Game tips off at T0; copy was built 2 min before tip-off (T0 - 120s).
    tipoff_ts = 1_800_010_000.0
    built_ts = tipoff_ts - 120.0
    tipoff_iso = datetime.fromtimestamp(tipoff_ts, tz=timezone.utc).isoformat()
    fi, cp = _fake_card("machinery-nba-night", 1, commence_time_iso=tipoff_iso)

    produce_calls = 0

    def _produce(_db):
        nonlocal produce_calls
        produce_calls += 1
        return None

    prod = RoundupProducer(
        slug="machinery-nba-night",
        name="NBA",
        kind="roundup",
        category="sports",
        section_title="NBA",
        footer="",
        produce=_produce,
    )
    fake_db = MagicMock(spec=AsyncSession)

    # Seed shared Redis with the pre-tipoff copy (stored stale_ttl_s=1800 because non-live at build)
    sync_rc = _FakeSyncRedis()
    sync_rc.set(
        _redis_cache_key(prod.slug),
        _encode_roundup_cache_entry(
            ts=built_ts,
            ttl_s=60.0,
            stale_ttl_s=ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
            feed_item=fi,
            container_payload=cp,
        ),
        ex=1800,
    )
    async_rc = _FakeAsyncRedisBatch(sync_rc.store)
    _patch_async_redis(monkeypatch, async_rc)

    # At 2 min into the game (age = 4 min < 5 min live cap): kept without recomputing!
    fi_2m, cp_2m = await evaluate_roundup_producer(
        prod, fake_db, now=tipoff_ts + 120.0, allow_stale=True
    )
    assert fi_2m is not None and cp_2m is not None
    assert produce_calls == 0

    # At 8 min into the game (age = 10 min >= 5 min live cap): clock rule expires it!
    _roundup_local_cache.clear()
    fi_8m, cp_8m = await evaluate_roundup_producer(
        prod, fake_db, now=tipoff_ts + 480.0, allow_stale=True
    )
    assert fi_8m is None and cp_8m is None
    assert produce_calls == 1


def test_publish_machinery_feed_enforces_clock_rule_and_logs_refusal_reason_and_rejects_plain_refusal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_roundup_cache_for_tests()
    slugs = ["machinery-alpha", "machinery-beta"]
    producers = {
        s: RoundupProducer(
            slug=s,
            name=s,
            kind="roundup",
            category="sports",
            section_title="Section",
            footer="",
            produce=lambda _db: None,
        )
        for s in slugs
    }
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    def _fake_render(*, mach_base: dict[str, Any], produced: list[dict[str, Any]], **_kw: Any) -> dict[str, Any]:
        return {
            "ttl": 60,
            "stale_ttl": 300,
            "live": False,
            "cache_key": "feed:resp:mach:discover",
            "page_json": json.dumps({"items": produced}),
            "page_base_key": "feed:machinery_pagebase:discover",
            "page_base_json": json.dumps({"items": produced}),
            "manifest_key": None,
            "manifest_json": None,
            "manifest_ttl": 0,
        }

    monkeypatch.setattr(
        "app.utils.roundup_containers.render_machinery_prewarm_bundle", _fake_render
    )

    now_ts = time.time()
    mach_base = {
        "page_base_body": {"items": [], "total": 0, "has_more": False},
        "age_origin": now_ts,
        "opening_seating": False,
        "edition_policy": "default",
        "limit": 20,
        "offset": 0,
        "params": {"limit": 20, "offset": 0, "event_pct": 0.15},
    }

    # A. Quiet mark with explicit refusal reason -> reason appears in mark & "cleanly empty" log line
    rc_reason = _FakeSyncRedis()
    fi_a, cp_a = _fake_card("machinery-alpha", 1)
    store_roundup_cache_sync(rc_reason, "machinery-alpha", now_ts, fi_a, cp_a)
    store_roundup_clean_empty_sync(
        rc_reason, "machinery-beta", now_ts, reason="missing_paired_stage"
    )
    decoded_mark = json.loads(rc_reason.get(_redis_cache_key("machinery-beta")) or "{}")
    assert decoded_mark["clean_empty"] is True
    assert decoded_mark["clean_empty_reason"] == "missing_paired_stage"

    caplog.clear()
    with caplog.at_level(logging.INFO):
        res_reason = _publish_machinery_feed_from_prewarm_base(
            rc_reason, mach_base=mach_base, label="discover"
        )
    assert res_reason["outcome"] == "ok"
    assert res_reason["clean_empty_reasons"] == {"machinery-beta": "missing_paired_stage"}
    assert "cleanly empty: machinery-beta(missing_paired_stage)" in caplog.text

    # B. Missing #13186 neighbour: plain refusal note written by web process (no card, no clean_empty)
    #    is treated as absent/missing -> refuses publication.
    rc_web_refusal = _FakeSyncRedis()
    store_roundup_cache_sync(rc_web_refusal, "machinery-alpha", now_ts, fi_a, cp_a)
    rc_web_refusal.set(
        _redis_cache_key("machinery-beta"),
        _encode_roundup_cache_entry(
            ts=now_ts - 10,
            ttl_s=60.0,
            stale_ttl_s=60.0,
            feed_item=None,
            container_payload=None,
            clean_empty=False,
        ),
        ex=60,
    )
    res_web = _publish_machinery_feed_from_prewarm_base(
        rc_web_refusal, mach_base=mach_base, label="discover"
    )
    assert res_web["outcome"] == "incomplete"
    assert res_web["absent"] == ["machinery-beta"]

    # C. Clock rule in prewarm publisher: copy built 2 min before tip-off expires 8 min into game
    rc_clock = _FakeSyncRedis()
    tipoff_iso = datetime.fromtimestamp(now_ts - 480.0, tz=timezone.utc).isoformat()
    fi_live, cp_live = _fake_card("machinery-alpha", 1, commence_time_iso=tipoff_iso)
    # Stored built_at = 10 min ago (2 min before tip-off), with non-live 1800s stale_ttl_s
    rc_clock.set(
        _redis_cache_key("machinery-alpha"),
        _encode_roundup_cache_entry(
            ts=now_ts - 600.0,
            ttl_s=ROUNDUP_MACHINERY_NON_LIVE_CACHE_TTL_S,
            stale_ttl_s=ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
            feed_item=fi_live,
            container_payload=cp_live,
        ),
        ex=1800,
    )
    store_roundup_clean_empty_sync(rc_clock, "machinery-beta", now_ts, reason="zero_members")
    res_clock = _publish_machinery_feed_from_prewarm_base(
        rc_clock, mach_base=mach_base, label="discover"
    )
    assert res_clock["outcome"] == "incomplete"
    assert res_clock["absent"] == ["machinery-alpha"]


@pytest.mark.asyncio
async def test_prewarm_worker_stores_actual_refusal_reason_in_quiet_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")

    prod = RoundupProducer(
        slug="machinery-oscars-test",
        name="Oscars",
        kind="roundup",
        category="entertainment",
        section_title="Oscars",
        footer="",
        produce=lambda _db: RoundupRefusal(["missing_paired_stage"]),
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS", {prod.slug: prod}
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )

    sync_rc = _FakeSyncRedis()

    class _DummySessionCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("app.tasks.base.get_task_session", lambda **_kw: _DummySessionCtx())

    out = await _prewarm_machinery_roundups(deadline_s=5.0, rc=sync_rc)
    assert out["slugs"][prod.slug]["outcome"] == "clean_empty"
    assert out["slugs"][prod.slug]["reason"] == "missing_paired_stage"
    stored = json.loads(sync_rc.get(_redis_cache_key(prod.slug)) or "{}")
    assert stored["clean_empty"] is True
    assert stored["clean_empty_reason"] == "missing_paired_stage"
