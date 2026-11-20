"""Tests for #13183: one cleanly empty grouping must not disable warm Discover publishing.

Covers Fable's five nearest neighbours:
1. All five present -> publishes with 5, standard log wording.
2. One cleanly empty -> publishes with 4, distinct log wording naming cleanly empty.
3. One failed and absent -> refuses to publish, warning names absent/failed.
4. One cleanly empty and one failed -> refuses to publish.
5. Clean-empty marker older than its lifetime -> treated as absent, refuses to publish.
Plus: worker `_prewarm_machinery_roundups` writes a clean-empty marker on a clean
empty producer result and never writes one on timeout, exception, or transient refusal.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.tasks.precompute_category_pages import (
    _prewarm_machinery_roundups,
    _publish_machinery_feed_from_prewarm_base,
)
from app.utils.roundup_containers import (
    ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S,
    RoundupProducer,
    RoundupRefusal,
    _redis_cache_key,
    reset_roundup_cache_for_tests,
    store_roundup_cache_sync,
    store_roundup_clean_empty_sync,
)

FIVE_SLUGS = [
    "machinery-oscars-best-picture",
    "machinery-2028-presidential",
    "machinery-fed-and-macro",
    "machinery-nba-night",
    "machinery-nfl-week",
]


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


def _fake_mach_base(now_ts: float) -> dict[str, Any]:
    items = [
        {
            "type": "futures",
            "score": 90 - i,
            "reason": "test",
            "headline": f"Card {i}",
            "data": {"id": 9000 + i, "name": f"Market {i}", "status": "open"},
        }
        for i in range(45)
    ]
    return {
        "page_base_body": {"items": items, "total": len(items), "has_more": True},
        "age_origin": now_ts,
        "opening_seating": False,
        "edition_policy": "default",
        "limit": 20,
        "offset": 0,
        "params": {"limit": 20, "offset": 0, "event_pct": 0.15},
    }


def _fake_card(slug: str, idx: int) -> tuple[dict[str, Any], dict[str, Any]]:
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
            "member_ids": [1000 + idx],
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
            {"members": [{"type": "market", "id": 1000 + idx, "card": {"id": 1000 + idx, "status": "open"}}]}
        ],
    }
    return fi, cp


def _register_five_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    producers = {
        slug: RoundupProducer(
            slug=slug,
            name=slug,
            kind="roundup",
            category="sports",
            section_title="Section",
            footer="",
            produce=lambda _db: None,
        )
        for slug in FIVE_SLUGS
    }
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", producers)
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


def _patch_bundle_renderer(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    counts: list[int] = []

    def _fake_render(*, mach_base: dict[str, Any], produced: list[dict[str, Any]], **_kw: Any) -> dict[str, Any]:
        counts.append(len(produced))
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
    return counts


def test_five_nearest_neighbours_for_clean_empty_vs_absent_groupings(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_roundup_cache_for_tests()
    _register_five_producers(monkeypatch)
    now_ts = time.time()
    mach_base = _fake_mach_base(now_ts)

    # 1. All five present -> publishes with 5, standard log wording.
    rc1 = _FakeSyncRedis()
    counts1 = _patch_bundle_renderer(monkeypatch)
    for i, slug in enumerate(FIVE_SLUGS):
        fi, cp = _fake_card(slug, i)
        assert store_roundup_cache_sync(rc1, slug, now_ts, fi, cp)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        res1 = _publish_machinery_feed_from_prewarm_base(rc1, mach_base=mach_base, label="discover")
    assert res1["outcome"] == "ok"
    assert res1["groupings"] == 5
    assert res1["clean_empty"] == []
    assert counts1 == [5]
    assert "Pre-warmed machinery Discover discover (5/5 groupings," in caplog.text
    assert "cleanly empty" not in caplog.text

    # 2. One cleanly empty -> publishes with 4, distinct log wording naming cleanly empty.
    rc2 = _FakeSyncRedis()
    counts2 = _patch_bundle_renderer(monkeypatch)
    for i, slug in enumerate(FIVE_SLUGS[:-1]):
        fi, cp = _fake_card(slug, i)
        assert store_roundup_cache_sync(rc2, slug, now_ts, fi, cp)
    assert store_roundup_clean_empty_sync(rc2, FIVE_SLUGS[-1], now_ts)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        res2 = _publish_machinery_feed_from_prewarm_base(rc2, mach_base=mach_base, label="discover")
    assert res2["outcome"] == "ok"
    assert res2["groupings"] == 4
    assert res2["clean_empty"] == [FIVE_SLUGS[-1]]
    assert counts2 == [4]
    assert "4/5 groupings active, 1 cleanly empty: machinery-nfl-week" in caplog.text

    # 3. One failed and absent -> refuses to publish, warning names absent/failed.
    rc3 = _FakeSyncRedis()
    counts3 = _patch_bundle_renderer(monkeypatch)
    for i, slug in enumerate(FIVE_SLUGS[:-1]):
        fi, cp = _fake_card(slug, i)
        assert store_roundup_cache_sync(rc3, slug, now_ts, fi, cp)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        res3 = _publish_machinery_feed_from_prewarm_base(rc3, mach_base=mach_base, label="discover")
    assert res3["outcome"] == "incomplete"
    assert res3["absent"] == [FIVE_SLUGS[-1]]
    assert counts3 == []
    assert "absent/failed (machinery-nfl-week)" in caplog.text

    # 4. One cleanly empty and one failed -> refuses to publish.
    rc4 = _FakeSyncRedis()
    counts4 = _patch_bundle_renderer(monkeypatch)
    for i, slug in enumerate(FIVE_SLUGS[:3]):
        fi, cp = _fake_card(slug, i)
        assert store_roundup_cache_sync(rc4, slug, now_ts, fi, cp)
    assert store_roundup_clean_empty_sync(rc4, FIVE_SLUGS[3], now_ts)
    # FIVE_SLUGS[4] is absent (failed)
    res4 = _publish_machinery_feed_from_prewarm_base(rc4, mach_base=mach_base, label="discover")
    assert res4["outcome"] == "incomplete"
    assert res4["clean_empty"] == 1
    assert res4["absent"] == [FIVE_SLUGS[4]]
    assert counts4 == []

    # 5. Clean-empty marker older than its lifetime -> treated as absent, refuses to publish.
    rc5 = _FakeSyncRedis()
    counts5 = _patch_bundle_renderer(monkeypatch)
    for i, slug in enumerate(FIVE_SLUGS[:-1]):
        fi, cp = _fake_card(slug, i)
        assert store_roundup_cache_sync(rc5, slug, now_ts, fi, cp)
    expired_ts = now_ts - ROUNDUP_MACHINERY_NON_LIVE_STALE_TTL_S - 60.0
    assert store_roundup_clean_empty_sync(rc5, FIVE_SLUGS[-1], expired_ts)
    res5 = _publish_machinery_feed_from_prewarm_base(rc5, mach_base=mach_base, label="discover")
    assert res5["outcome"] == "incomplete"
    assert res5["absent"] == [FIVE_SLUGS[-1]]
    assert counts5 == []


@pytest.mark.asyncio
async def test_prewarm_worker_writes_clean_empty_marker_only_for_clean_empty_not_transient_or_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")

    class _DummySessionCtx:
        async def __aenter__(self) -> Any:
            return MagicMock()

        async def __aexit__(self, *args: Any) -> bool:
            return False

    monkeypatch.setattr(
        "app.tasks.base.get_task_session",
        lambda **_kw: _DummySessionCtx(),
    )

    p_clean = RoundupProducer(
        slug="machinery-nfl-week",
        name="NFL Week",
        kind="roundup",
        category="nfl",
        section_title="Slate",
        footer="",
        produce=lambda _db: RoundupRefusal(reasons=[("sport", "empty_pool")]),
    )
    p_transient = RoundupProducer(
        slug="machinery-nba-night",
        name="NBA Night",
        kind="roundup",
        category="nba",
        section_title="Slate",
        footer="",
        produce=lambda _db: RoundupRefusal(reasons=[("sport", "source_unavailable")]),
    )
    p_boom = RoundupProducer(
        slug="machinery-fed-and-macro",
        name="Fed & Macro",
        kind="roundup",
        category="economics",
        section_title="Fed",
        footer="",
        produce=lambda _db: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
        {p_clean.slug: p_clean, p_transient.slug: p_transient, p_boom.slug: p_boom},
    )
    monkeypatch.setattr(
        "app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None
    )

    rc = _FakeSyncRedis()
    res = await _prewarm_machinery_roundups(deadline_s=5.0, rc=rc)
    assert res["slugs"]["machinery-nfl-week"]["outcome"] == "clean_empty"
    assert res["slugs"]["machinery-nfl-week"]["redis_written"] is True
    assert res["slugs"]["machinery-nfl-week"]["redis_read_back"] is True
    stored_clean = json.loads(rc.store[_redis_cache_key("machinery-nfl-week")])
    assert stored_clean["clean_empty"] is True
    assert stored_clean["feed_item"] is None

    # Transient refusal & exception MUST NOT write a clean_empty marker!
    assert res["slugs"]["machinery-nba-night"]["outcome"] == "refused"
    assert res["slugs"]["machinery-nba-night"]["redis_written"] is False
    assert _redis_cache_key("machinery-nba-night") not in rc.store

    assert res["slugs"]["machinery-fed-and-macro"]["outcome"] == "error"
    assert res["slugs"]["machinery-fed-and-macro"]["redis_written"] is False
    assert _redis_cache_key("machinery-fed-and-macro") not in rc.store
