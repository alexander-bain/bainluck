"""Tests for #13445: prewarm_live_feed_shapes O(M) spacing, batched Redis I/O, and live machinery trickle."""

from __future__ import annotations

import asyncio
import json
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest

from app.utils import roundup_containers as rc_mod

pcp = import_module("app.tasks.precompute_category_pages")


def _ref_space_by_sport(items):
    if len(items) <= 2:
        return list(items)
    non_sports_count = sum(
        1 for it in items if rc_mod._client_sport_category(it) not in rc_mod._CLIENT_SPORT_CATEGORIES
    )
    max_sports_run = 2 if non_sports_count >= 4 else 3
    remaining = list(items)
    result = []
    last_sport = ""
    sports_since_non_sport = 0
    while remaining:
        pick = -1
        for idx, it in enumerate(remaining):
            cat = rc_mod._client_sport_category(it)
            if cat not in rc_mod._CLIENT_SPORT_CATEGORIES or (
                sports_since_non_sport < max_sports_run and cat != last_sport
            ):
                pick = idx
                break
        if pick == -1:
            for idx, it in enumerate(remaining):
                if rc_mod._client_sport_category(it) != last_sport:
                    pick = idx
                    break
        if pick == -1:
            pick = 0
        chosen = remaining.pop(pick)
        cat = rc_mod._client_sport_category(chosen)
        result.append(chosen)
        if cat in rc_mod._CLIENT_SPORT_CATEGORIES:
            last_sport = cat
            sports_since_non_sport += 1
        else:
            last_sport = ""
            sports_since_non_sport = 0
    return result


def _ref_has_adjacent_roundup(items) -> bool:
    spaced = _ref_space_by_sport(_ref_space_by_sport(items))
    for i in range(len(spaced) - 1):
        a, b = spaced[i], spaced[i + 1]
        if (
            rc_mod._is_grouped_feed_card(a)
            and rc_mod._is_grouped_feed_card(b)
            and (rc_mod._is_roundup_bundle_card(a) or rc_mod._is_roundup_bundle_card(b))
        ):
            return True
    return False


def _ref_find_non_adjacent_seat(items, start_idx, *, floor_idx, candidate_item=None, page_window=20):
    start_pos = max(int(floor_idx), int(start_idx))
    n = len(items)
    first_raw = None
    pos = start_pos
    while pos <= n:
        prev_g = pos > 0 and rc_mod._is_grouped_feed_card(items[pos - 1])
        next_g = pos < n and rc_mod._is_grouped_feed_card(items[pos])
        if not prev_g and not next_g:
            if first_raw is None:
                first_raw = pos
            if candidate_item is None:
                return pos
            trial = [*items[:pos], candidate_item, *items[pos:]]
            ws = trial[: max(int(page_window), pos + 2)]
            if not _ref_has_adjacent_roundup(ws):
                return pos
        pos += 1
    return first_raw


def test_fast_spacing_and_seat_search_match_reference_and_stay_fast():
    rng = random.Random(20261122)
    sports = ["basketball_nba", "football_nfl", "icehockey_nhl", "baseball_mlb", "tennis_atp"]
    cats = ["politics", "economics", "golf", "entertainment", "other"]

    for _ in range(60):
        length = rng.randint(0, 50)
        deck = []
        for i in range(length):
            kind = rng.choice(["event", "futures", "bundle_roundup", "bundle_theme", "collection"])
            if kind == "event":
                deck.append({"type": "event", "id": f"e-{i}", "data": {"id": i, "sport": rng.choice(sports)}})
            elif kind == "futures":
                deck.append(
                    {"type": "futures", "id": f"f-{i}", "data": {"id": i, "llm_sport_category": rng.choice(cats)}}
                )
            elif kind == "bundle_roundup":
                child = (
                    {"type": "event", "data": {"sport": rng.choice(sports)}}
                    if rng.random() < 0.7
                    else {"type": "futures", "data": {"llm_sport_category": rng.choice(cats)}}
                )
                deck.append(
                    {
                        "type": "bundle",
                        "id": f"r-{i}",
                        "data": {
                            "id": f"roundup:s-{i}",
                            "kind": "roundup",
                            "collection_ref": {"slug": f"s-{i}"},
                            "items": [child],
                        },
                    }
                )
            elif kind == "bundle_theme":
                deck.append(
                    {
                        "type": "bundle",
                        "id": f"t-{i}",
                        "data": {"id": f"theme-{i}", "items": [{"type": "futures", "data": {"llm_sport_category": rng.choice(cats)}}]},
                    }
                )
            else:
                deck.append({"type": "collection", "id": f"c-{i}", "data": {"id": f"col-{i}"}})

        got = rc_mod._client_space_by_sport(deck)
        exp = _ref_space_by_sport(deck)
        assert [x["id"] for x in got] == [x["id"] for x in exp]
        assert rc_mod._spaced_has_adjacent_roundup(deck) == _ref_has_adjacent_roundup(deck)

        cand = {
            "type": "bundle",
            "id": "cand",
            "data": {
                "id": "roundup:cand",
                "kind": "roundup",
                "collection_ref": {"slug": "cand"},
                "items": [{"type": "event", "data": {"sport": rng.choice(sports)}}],
            },
        }
        start_idx = rng.randint(0, length)
        floor_idx = rng.randint(0, 10)
        page_window = rng.choice([10, 20, 30])
        assert rc_mod._find_non_adjacent_roundup_seat(
            deck, start_idx, floor_idx=floor_idx, candidate_item=cand, page_window=page_window
        ) == _ref_find_non_adjacent_seat(
            deck, start_idx, floor_idx=floor_idx, candidate_item=cand, page_window=page_window
        )

    # Latency guard: 171-item deck + 25 machinery groupings must finish well under 1.0s
    large_deck = [
        {"type": "futures", "id": f"f-{i}", "score": 80.0 - i * 0.1, "data": {"id": 1000 + i, "llm_sport_category": cats[i % len(cats)], "status": "open"}}
        for i in range(171)
    ]
    large_roundups = [
        {
            "type": "bundle",
            "id": f"r-{j}",
            "score": 60.0,
            "data": {
                "id": f"roundup:machinery-test-{j}",
                "kind": "roundup",
                "collection_ref": {"slug": f"machinery-test-{j}"},
                "items": [{"type": "event", "data": {"sport": sports[j % len(sports)]}}],
            },
        }
        for j in range(25)
    ]
    t0 = time.monotonic()
    out = rc_mod.insert_roundup_feed_items(
        large_deck,
        large_roundups,
        page_window=20,
        now=datetime(2026, 11, 22, 16, 40, tzinfo=timezone.utc),
        preserve_existing_roundups=True,
    )
    elapsed_s = time.monotonic() - t0
    assert len(out) >= 171
    assert elapsed_s < 1.0


def test_publish_machinery_batches_mget_pipeline_and_shares_snapshot(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTAINER_MACHINERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("FEED_EDITION_POLICY_DISABLED", "0")

    class _Pipe:
        def __init__(self, store: dict[str, tuple[int, str]]) -> None:
            self.store = store
            self.ops: list[tuple[str, int, str]] = []

        def setex(self, key: str, ttl_s: int, value: str):
            self.ops.append((key, ttl_s, value))
            return self

        def execute(self):
            for k, ttl_s, v in self.ops:
                self.store[k] = (ttl_s, v)
            return [True] * len(self.ops)

    class _BatchedRedis:
        def __init__(self, initial: dict[str, str]) -> None:
            self.data = dict(initial)
            self.written: dict[str, tuple[int, str]] = {}
            self.mget_calls = 0
            self.get_calls = 0
            self.pipeline_calls = 0
            self.setex_calls = 0

        def mget(self, keys: list[str]):
            self.mget_calls += 1
            return [self.data.get(k) for k in keys]

        def get(self, key: str):
            self.get_calls += 1
            return self.data.get(key)

        def pipeline(self, transaction: bool = False):
            self.pipeline_calls += 1
            return _Pipe(self.written)

        def setex(self, key: str, ttl_s: int, value: str):
            self.setex_calls += 1
            self.written[key] = (ttl_s, value)

    now_ts = time.time()
    saved = dict(rc_mod.ROUNDUP_PRODUCERS)
    try:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        slugs = ["machinery-alpha", "machinery-beta"]
        initial_blobs: dict[str, str] = {}
        for idx, slug in enumerate(slugs):
            rc_mod.ROUNDUP_PRODUCERS[slug] = rc_mod.RoundupProducer(
                slug=slug,
                name=slug,
                kind="roundup",
                category="other",
                section_title="Markets",
                footer="",
                produce=MagicMock(),
                membership="computed-produced",
                relations=("same_subject",),
                level="member",
                rule={"producer": "container_machinery"},
                enabled=lambda: True,
            )
            initial_blobs[rc_mod._redis_cache_key(slug)] = json.dumps(
                {
                    "built_at": now_ts - 10.0,
                    "ttl_s": 300.0,
                    "stale_ttl_s": 21600.0,
                    "feed_item": {
                        "type": "bundle",
                        "id": f"bundle-{idx}",
                        "data": {
                            "id": f"roundup:{slug}",
                            "kind": "roundup",
                            "collection_ref": {"slug": slug},
                            "items": [
                                {"type": "futures", "data": {"id": 900 + idx, "llm_sport_category": "other"}}
                            ],
                        },
                    },
                    "container_payload": {
                        "sections": [
                            {"members": [{"type": "market", "id": 900 + idx, "card": {"id": 900 + idx, "status": "open"}}]}
                        ]
                    },
                }
            )

        rc = _BatchedRedis(initial_blobs)
        deck = [
            {"type": "futures", "id": f"f-{i}", "score": 90.0 - i, "data": {"id": i + 1, "llm_sport_category": "other", "status": "open"}}
            for i in range(25)
        ]

        def _mach_base(limit: int, pb_key: str) -> dict:
            return {
                "page_base_key": pb_key,
                "page_base_body": {"items": deck, "total": len(deck)},
                "page_base_fresh_ttl": 60,
                "page_base_stale_ttl": 300,
                "page_base_last_good_ttl": 21600,
                "cache_shape": {"limit": limit, "offset": 0, "event_pct": 0.15, "mode": None},
                "limit": limit,
                "offset": 0,
                "opening_seating": False,
                "edition_policy": "default",
                "age_origin": now_ts - 5.0,
            }

        snap_cache: dict = {}
        tok = pcp._PREWARM_MACHINERY_SNAPSHOT_CACHE_VAR.set(snap_cache)
        try:
            with patch("app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None):
                res1 = pcp._publish_machinery_feed_from_prewarm_base(
                    rc, mach_base=_mach_base(20, "feed_cache:pagebase:d20"), label="discover"
                )
                res2 = pcp._publish_machinery_feed_from_prewarm_base(
                    rc, mach_base=_mach_base(50, "feed_cache:pagebase:d50"), label="discover_native"
                )
                assert res1["outcome"] == "ok" and res2["outcome"] == "ok"
                assert rc.mget_calls == 1
                assert rc.get_calls == 0
                assert rc.pipeline_calls == 2
                assert rc.setex_calls == 0

                snap_cache.clear()
                res3 = pcp._publish_machinery_feed_from_prewarm_base(
                    rc, mach_base=_mach_base(20, "feed_cache:pagebase:d20"), label="discover"
                )
                assert res3["outcome"] == "ok"
                assert rc.mget_calls == 2
        finally:
            pcp._PREWARM_MACHINERY_SNAPSHOT_CACHE_VAR.reset(tok)
    finally:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        rc_mod.ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_live_machinery_prioritizes_missing_and_trickles_at_most_two_due(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTAINER_MACHINERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")

    now_ts = time.time()

    def _blob(age_s: float) -> str:
        return json.dumps(
            {
                "built_at": now_ts - age_s,
                "ttl_s": 300.0,
                "stale_ttl_s": 21600.0,
                "feed_item": {"type": "bundle", "data": {"id": "roundup:x", "kind": "roundup"}},
                "container_payload": {
                    "sections": [{"members": [{"type": "market", "id": 1, "card": {"id": 1, "status": "open"}}]}]
                },
            }
        )

    all_slugs = [
        "machinery-live-1",
        "machinery-missing-1",
        "machinery-due-a",
        "machinery-due-b",
        "machinery-due-c",
        "machinery-due-d",
        "machinery-due-e",
        "machinery-fresh-1",
    ]
    store = {
        rc_mod._redis_cache_key("machinery-live-1"): _blob(30.0),
        rc_mod._redis_cache_key("machinery-due-a"): _blob(215.0),
        rc_mod._redis_cache_key("machinery-due-b"): _blob(290.0),
        rc_mod._redis_cache_key("machinery-due-c"): _blob(230.0),
        rc_mod._redis_cache_key("machinery-due-d"): _blob(270.0),
        rc_mod._redis_cache_key("machinery-due-e"): _blob(250.0),
        rc_mod._redis_cache_key("machinery-fresh-1"): _blob(40.0),
    }

    class _FakeMgetRedis:
        def hgetall(self, k: str):
            if k == rc_mod.MACHINERY_LIVE_SLUGS_KEY:
                return {"machinery-live-1": "1"}
            return {}

        def exists(self, k: str):
            return 1 if k in store else 0

        def get(self, k: str):
            return store.get(k)

        def mget(self, keys: list[str]):
            return [store.get(k) for k in keys]

    recorded: list[tuple[tuple[str, ...], int | None]] = []

    async def _fake_warm(deadline_s: float = 25.0, *, slugs=None):
        recorded.append((tuple(slugs or ()), pcp._PREWARM_MACHINERY_CONCURRENCY_VAR.get()))
        return {
            "outcome": "ok",
            "warmed": len(slugs or ()),
            "slugs": {s: {"outcome": "ok", "elapsed_ms": 10.0, "live": False} for s in (slugs or ())},
        }

    saved = dict(rc_mod.ROUNDUP_PRODUCERS)
    try:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        for s in all_slugs:
            rc_mod.ROUNDUP_PRODUCERS[s] = rc_mod.RoundupProducer(
                slug=s,
                name=s,
                kind="roundup",
                category="other",
                section_title="Markets",
                footer="",
                produce=MagicMock(),
                membership="computed-produced",
                relations=("same_subject",),
                level="member",
                rule={"producer": "container_machinery"},
                enabled=lambda: True,
            )

        with (
            patch("app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None),
            patch.object(pcp, "_prewarm_machinery_roundups", _fake_warm),
        ):
            res = await pcp._prewarm_live_machinery_roundups(_FakeMgetRedis(), deadline_s=20.0)

        assert res["outcome"] == "ok"
        assert res["live_slugs"] == ["machinery-live-1"]
        assert res["absent_slugs"] == ["machinery-missing-1", "machinery-due-b", "machinery-due-d"]
        assert recorded == [
            (("machinery-live-1",), 2),
            (("machinery-missing-1",), 2),
            (("machinery-due-b", "machinery-due-d"), 1),
        ]
    finally:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        rc_mod.ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_prewarm_machinery_roundups_skips_when_wall_budget_exhausted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTAINER_MACHINERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")

    async def _slow_eval(prod, db, **kwargs):
        await asyncio.sleep(0.08)
        return None, None

    @asynccontextmanager
    async def _fake_session(*, statement_timeout_ms=None):
        yield MagicMock()

    class _DummyRc:
        pass

    saved = dict(rc_mod.ROUNDUP_PRODUCERS)
    try:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        slugs = ["machinery-s1", "machinery-s2", "machinery-s3"]
        for s in slugs:
            rc_mod.ROUNDUP_PRODUCERS[s] = rc_mod.RoundupProducer(
                slug=s,
                name=s,
                kind="roundup",
                category="other",
                section_title="Markets",
                footer="",
                produce=MagicMock(),
                membership="computed-produced",
                relations=("same_subject",),
                level="member",
                rule={"producer": "container_machinery"},
                enabled=lambda: True,
            )

        tok = pcp._PREWARM_MACHINERY_CONCURRENCY_VAR.set(1)
        try:
            with (
                patch("app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None),
                patch("app.utils.roundup_containers.evaluate_roundup_producer", _slow_eval),
                patch("app.tasks.base.get_task_session", _fake_session),
            ):
                res = await pcp._prewarm_machinery_roundups(deadline_s=0.55, slugs=slugs, rc=_DummyRc())
        finally:
            pcp._PREWARM_MACHINERY_CONCURRENCY_VAR.reset(tok)

        outcomes = [v["outcome"] for v in res["slugs"].values()]
        # With deadline=0.55s: s1 finishes in 0.08s, leaving <0.5s (0.47s < 0.5s guard),
        # so s2 and s3 cleanly skip without checking out DB sessions past budget.
        assert outcomes == ["refused", "skipped_no_time", "skipped_no_time"]
    finally:
        rc_mod.ROUNDUP_PRODUCERS.clear()
        rc_mod.ROUNDUP_PRODUCERS.update(saved)
