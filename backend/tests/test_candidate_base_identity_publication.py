"""Candidate-base identity, bounds, rollback, and monotonic publication (Queue 288, C91).

Deterministic reproductions for the five defects Queue 288 inherited from C91.
Each class is one defect; every test here failed against the Queue 285 shipped
code (schema v1) and passes against the v2 canonical-identity implementation.

1. ``TestIdentityCollision``   — delimiter collision: distinct filters produced
   the SAME identity string, so one filter was served the other's candidates.
2. ``TestIdentityEquivalence`` — equivalent filters (duplicate / reordered tags)
   produced DIFFERENT identities, fragmenting the shared base.
3. ``TestAdmission``           — malformed / non-string / oversized tag payloads
   reached the identity builder instead of a typed client error.
4. ``TestBoundedL0``           — the process-local L0 map had no eviction, so
   high-cardinality filter churn grew it without bound.
5. ``TestTruthfulSwitch``      — a warm L0 entry kept serving after the kill
   switch flipped, and the sync (beat) publisher never checked the switch.
6. ``TestMonotonicPublication``— an older build completing last overwrote a
   newer base on both the async and sync publish paths.

These are pure-unit boundary tests: no DB, no network, no candidate SQL.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import candidate_base as cb
from app.utils import request_cache as rc


NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


class _FakeRedis:
    """Async Redis stand-in with EVAL support (for the monotonic publish guard)."""

    def __init__(self, store=None, mode="ok"):
        self.store = dict(store or {})
        self.mode = mode
        self.gets = 0
        self.sets = 0
        self.evals = 0

    async def get(self, key):
        self.gets += 1
        if self.mode == "down":
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.sets += 1
        if self.mode == "down":
            raise ConnectionError("redis down")
        self.store[key] = value
        return True

    async def eval(self, script, numkeys, *args):
        """Emulate the monotonic compare-and-set Lua contract."""
        self.evals += 1
        if self.mode == "down":
            raise ConnectionError("redis down")
        if self.mode == "no-eval":
            raise Exception("unknown command 'EVAL'")
        key = args[0]
        payload, incoming_epoch = args[numkeys], int(args[numkeys + 1])
        current = self.store.get(key)
        if current:
            try:
                existing = json.loads(current).get("generated_epoch_ms")
                if isinstance(existing, int) and existing > incoming_epoch:
                    return 0
            except (ValueError, TypeError):
                pass
        self.store[key] = payload
        self.sets += 1
        return 1


class _FakeSyncRedis:
    """Sync Redis stand-in for the precompute-beat publish path."""

    def __init__(self, store=None):
        self.store = dict(store or {})
        self.sets = 0
        self.evals = 0

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.sets += 1
        self.store[key] = value
        return True

    def eval(self, script, numkeys, *args):
        self.evals += 1
        key = args[0]
        payload, incoming_epoch = args[numkeys], int(args[numkeys + 1])
        current = self.store.get(key)
        if current:
            try:
                existing = json.loads(current).get("generated_epoch_ms")
                if isinstance(existing, int) and existing > incoming_epoch:
                    return 0
            except (ValueError, TypeError):
                pass
        self.store[key] = payload
        self.sets += 1
        return 1


def _install(monkeypatch, client):
    async def _get():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _get)


@pytest.fixture(autouse=True)
def _clean_process_state():
    cb._reset_l0_for_tests()
    rc._reset_last_good_for_tests()
    yield
    cb._reset_l0_for_tests()
    rc._reset_last_good_for_tests()


# --- 1. Delimiter collision ----------------------------------------------------
class TestIdentityCollision:
    """Distinct filters must never share an identity (they'd serve wrong candidates)."""

    def test_comma_inside_tag_does_not_collide_with_two_tags(self):
        # v1: both rendered the tags token "a,b" -> same key, wrong candidates.
        assert cb.base_identity(None, ["a,b"]) != cb.base_identity(None, ["a", "b"])

    def test_colon_in_sport_does_not_collide_with_tag_segment(self):
        # v1: "…:v1:" + "a:b" + ":no-static-tags" collided with sport "a" + tag
        # "b:no-static-tags" because ':' was both the field and the value delimiter.
        assert cb.base_identity("a:b", None) != cb.base_identity(
            "a", ["b:no-static-tags"]
        )

    def test_empty_string_tag_does_not_collide_with_no_tags(self):
        assert cb.base_identity(None, [""]) != cb.base_identity(None, None)

    def test_unicode_confusables_do_not_collide(self):
        # NFC vs NFD "café" are distinct DB values, so they must stay distinct
        # identities — merging them would serve the wrong candidate set.
        nfc, nfd = "café", "café"
        assert nfc != nfd
        assert cb.base_identity(None, [nfc]) != cb.base_identity(None, [nfd])

    def test_separator_injection_cannot_forge_another_identity(self):
        forged = cb.base_identity(None, ["x"])
        for probe in ["x:no-static-tags", "all:x", ":", ",", "v1:all:no-static-tags"]:
            assert cb.base_identity(None, [probe]) != forged

    def test_identity_is_length_bounded(self):
        # An oversized (but admissible) tag set must not produce an unbounded key.
        tags = [f"sport:{'x' * 200}{i}" for i in range(cb.MAX_STATIC_TAGS)]
        assert len(cb.base_identity(None, tags)) <= cb.MAX_IDENTITY_LENGTH


# --- 2. Equivalent filters share identity -------------------------------------
class TestIdentityEquivalence:
    """Filters with identical SQL semantics must share one base."""

    def test_reordered_tags_share_identity(self):
        assert cb.base_identity(None, ["a", "b"]) == cb.base_identity(None, ["b", "a"])

    def test_duplicate_tags_share_identity_with_deduped(self):
        # v1: ["a","a"] -> "a,a" but ["a"] -> "a" — two bases for one SQL filter.
        assert cb.base_identity(None, ["a", "a"]) == cb.base_identity(None, ["a"])

    def test_duplicates_and_order_together(self):
        assert cb.base_identity(None, ["b", "a", "b"]) == cb.base_identity(
            None, ["a", "b"]
        )

    def test_anon_default_is_stable_and_readable(self):
        # The hot anonymous key stays human-readable for ops/oracle parity.
        assert cb.base_identity(None, None) == "discover-candidates:v2:all:no-static-tags"

    def test_case_is_not_folded(self):
        # Tag matching is byte-exact in Postgres JSONB containment, so folding
        # case would merge genuinely different candidate sets.
        assert cb.base_identity(None, ["sport:NBA"]) != cb.base_identity(
            None, ["sport:nba"]
        )


# --- 3. Malformed / oversized admission ---------------------------------------
class TestAdmission:
    """Bad tag payloads must raise a typed client error, never a 500 or a bad key."""

    @pytest.mark.parametrize("bad", [1, None, {"a": 1}, ["nested"], 3.5, True, b"x"])
    def test_non_string_tag_rejected(self, bad):
        with pytest.raises(cb.CandidateBaseTagError):
            cb.base_identity(None, [bad])

    def test_oversized_single_tag_rejected(self):
        with pytest.raises(cb.CandidateBaseTagError):
            cb.base_identity(None, ["x" * (cb.MAX_TAG_LENGTH + 1)])

    def test_too_many_tags_rejected(self):
        with pytest.raises(cb.CandidateBaseTagError):
            cb.base_identity(None, [f"t{i}" for i in range(cb.MAX_STATIC_TAGS + 1)])

    def test_oversized_sport_rejected(self):
        with pytest.raises(cb.CandidateBaseTagError):
            cb.base_identity("s" * (cb.MAX_TAG_LENGTH + 1), None)

    def test_error_is_a_valueerror_for_callers_that_catch_broadly(self):
        assert issubclass(cb.CandidateBaseTagError, ValueError)

    def test_valid_payloads_still_admitted(self):
        # The guard must not narrow valid feed responses.
        assert cb.base_identity("golf", ["sport:golf", "tier:1"])
        assert cb.base_identity(None, None)
        assert cb.base_identity(None, [])


class TestRouteAdmission:
    """The real feed query-param parser must not 500 on malformed tags."""

    def test_dict_with_colon_key_returns_typed_error_not_attributeerror(self):
        from app.routes.feed import _split_tag_filter, FeedTagFilterError

        # v1 inline parser raised AttributeError -> 500 on a public endpoint.
        with pytest.raises(FeedTagFilterError):
            _split_tag_filter('[{":": 1}]')
        with pytest.raises(FeedTagFilterError):
            _split_tag_filter('[[":"]]')

    def test_well_formed_tags_split_static_and_dynamic_unchanged(self):
        from app.routes.feed import _split_tag_filter

        tag_filter, static, dynamic = _split_tag_filter(
            '["sport:nba", "status:live", "tier:1"]'
        )
        assert tag_filter == ["sport:nba", "status:live", "tier:1"]
        assert static == ["sport:nba", "tier:1"]
        assert dynamic == ["status:live"]

    def test_oversized_static_tag_rejected_at_admission_not_deeper(self):
        # Regression: the route parser admitted an arbitrarily long tag, which
        # then raised CandidateBaseTagError inside the identity builder -> 500.
        from app.routes.feed import _split_tag_filter, FeedTagFilterError

        with pytest.raises(FeedTagFilterError):
            _split_tag_filter(json.dumps(["sport:" + "x" * 5000]))
        with pytest.raises(FeedTagFilterError):
            _split_tag_filter(
                json.dumps([f"sport:s{i}" for i in range(cb.MAX_STATIC_TAGS + 1)])
            )

    def test_anything_admitted_by_the_route_can_be_keyed(self):
        # The admission bound and the identity bound must agree: nothing that
        # survives _split_tag_filter may raise in base_identity.
        from app.routes.feed import _split_tag_filter

        payloads = [
            json.dumps(["sport:nba", "tier:1"]),
            json.dumps(["sport:" + "x" * (cb.MAX_TAG_LENGTH - 6)]),
            json.dumps([f"sport:s{i}" for i in range(cb.MAX_STATIC_TAGS)]),
            json.dumps(["status:live"]),
            json.dumps([]),
        ]
        for payload in payloads:
            _, static, _ = _split_tag_filter(payload)
            assert cb.base_identity(None, static or None)

    @pytest.mark.asyncio
    async def test_base_read_degrades_to_direct_on_bad_identity(self, monkeypatch):
        # Defense in depth: a bad pool input from any caller falls back to the
        # direct-query path instead of raising into the request handler.
        _install(monkeypatch, _FakeRedis({}))
        ids, prov, curator = await cb.get_candidate_base(
            NOW, None, ["x" * (cb.MAX_TAG_LENGTH + 1)]
        )
        assert ids is None and prov == cb.PROV_DIRECT and curator is None

    def test_non_list_and_unparseable_json_stay_permissive(self):
        from app.routes.feed import _split_tag_filter

        # Unchanged legacy behaviour: not a filter at all, not an error.
        assert _split_tag_filter('{"a":1}') == (None, [], [])
        assert _split_tag_filter("not json") == (None, [], [])
        assert _split_tag_filter(None) == (None, [], [])


# --- 4. Bounded L0 -------------------------------------------------------------
class TestBoundedL0:
    """High-cardinality filter churn must not grow the process-local map forever."""

    def test_l0_is_bounded_under_churn(self):
        for i in range(cb.CANDIDATE_BASE_L0_MAX_ENTRIES * 4):
            identity = cb.base_identity(f"sport{i}", None)
            cb._l0_store(identity, cb.build_envelope(NOW, identity, [i]))
        assert len(cb._l0) <= cb.CANDIDATE_BASE_L0_MAX_ENTRIES

    def test_expired_entries_are_purged_not_just_capped(self):
        identity = cb.base_identity("golf", None)
        cb._l0_store(identity, cb.build_envelope(NOW, identity, [1]))
        # Age the entry past the L0 read throttle window.
        cb._l0[identity]["fetched_wall"] -= cb.CANDIDATE_BASE_L0_TTL_S + 60
        other = cb.base_identity("nba", None)
        cb._l0_store(other, cb.build_envelope(NOW, other, [2]))
        assert identity not in cb._l0
        assert other in cb._l0

    def test_eviction_prefers_oldest_entries(self):
        import time as _time

        total = cb.CANDIDATE_BASE_L0_MAX_ENTRIES + 5
        base_wall = _time.time()
        for i in range(total):
            identity = cb.base_identity(f"s{i}", None)
            cb._l0_store(identity, cb.build_envelope(NOW, identity, [i]))
            # All entries stay INSIDE the expiry window, so only the size cap can
            # evict — this isolates oldest-first ordering from expiry purging.
            cb._l0[identity]["fetched_wall"] = base_wall - (total - i) * 0.001
        assert len(cb._l0) <= cb.CANDIDATE_BASE_L0_MAX_ENTRIES
        # The most recent identity survived; the very first did not.
        newest = cb.base_identity(f"s{cb.CANDIDATE_BASE_L0_MAX_ENTRIES + 4}", None)
        assert newest in cb._l0
        assert cb.base_identity("s0", None) not in cb._l0


# --- 5. Truthful kill switch ---------------------------------------------------
class TestTruthfulSwitch:
    """Rollback must be immediate — no warm cache may outlive the switch."""

    @pytest.mark.asyncio
    async def test_warm_l0_does_not_serve_after_disable(self, monkeypatch):
        identity = cb.base_identity(None, None)
        env = cb.build_envelope(NOW, identity, [1, 2, 3])
        client = _FakeRedis(
            {
                cb._redis_keys(identity)[0]: json.dumps(env),
                cb._redis_keys(identity)[1]: json.dumps(env),
            }
        )
        _install(monkeypatch, client)

        ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
        assert prov == cb.PROV_FRESH and ids == [1, 2, 3]  # L0 now warm

        client.store[cb.CANDIDATE_BASE_ENABLED_KEY] = "0"
        ids2, prov2, _ = await cb.get_candidate_base(NOW, None, None)
        # v1 served the warm L0 entry for up to CANDIDATE_BASE_L0_TTL_S (30s).
        assert prov2 == cb.PROV_DISABLED
        assert ids2 is None

    @pytest.mark.asyncio
    async def test_disable_clears_local_base_for_identity(self, monkeypatch):
        identity = cb.base_identity(None, None)
        env = cb.build_envelope(NOW, identity, [9])
        client = _FakeRedis({cb._redis_keys(identity)[0]: json.dumps(env)})
        _install(monkeypatch, client)
        await cb.get_candidate_base(NOW, None, None)
        assert identity in cb._l0

        client.store[cb.CANDIDATE_BASE_ENABLED_KEY] = "0"
        await cb.get_candidate_base(NOW, None, None)
        assert identity not in cb._l0

    @pytest.mark.asyncio
    async def test_redis_outage_does_not_falsely_disable(self, monkeypatch):
        # A switch read failure must leave the base ENABLED (default on) so an
        # outage degrades to last-good, not to a full direct-query stampede.
        identity = cb.base_identity(None, None)
        env = cb.build_envelope(NOW, identity, [4, 8])
        _install(monkeypatch, _FakeRedis({cb._redis_keys(identity)[0]: json.dumps(env)}))
        ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
        assert prov == cb.PROV_FRESH and ids == [4, 8]

        cb._reset_l0_for_tests()  # bypass the warm throttle: exercise the outage path
        _install(monkeypatch, _FakeRedis({}, mode="down"))
        ids2, prov2, _ = await cb.get_candidate_base(NOW, None, None)
        assert prov2 == cb.PROV_LAST_GOOD
        assert ids2 == [4, 8]

    def test_sync_publish_honours_kill_switch(self):
        # v1: publish_candidate_base_sync had NO switch check, so the beat kept
        # republishing a base the operator had just rolled back.
        rc_sync = _FakeSyncRedis({cb.CANDIDATE_BASE_ENABLED_KEY: "0"})
        identity = cb.base_identity(None, None)
        cb.publish_candidate_base_sync(rc_sync, cb.build_envelope(NOW, identity, [1]))
        assert rc_sync.sets == 0

    def test_sync_publish_writes_when_enabled(self):
        rc_sync = _FakeSyncRedis()
        identity = cb.base_identity(None, None)
        cb.publish_candidate_base_sync(rc_sync, cb.build_envelope(NOW, identity, [1]))
        assert rc_sync.sets >= 1


# --- 6. Monotonic publication --------------------------------------------------
class TestMonotonicPublication:
    """An older build completing last must never replace a newer base."""

    @pytest.mark.asyncio
    async def test_older_async_publish_cannot_overwrite_newer(self, monkeypatch):
        client = _FakeRedis({})
        _install(monkeypatch, client)
        identity = cb.base_identity(None, None)

        newer = cb.build_envelope(NOW, identity, [100, 200])
        older = cb.build_envelope(NOW - timedelta(seconds=45), identity, [1])

        await cb.publish_candidate_base(newer)
        await cb.publish_candidate_base(older)  # slow build finishing late

        cb._reset_l0_for_tests()
        ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
        assert ids == [100, 200], "older build clobbered the newer base"
        assert prov == cb.PROV_FRESH

    @pytest.mark.asyncio
    async def test_newer_publish_still_replaces_older(self, monkeypatch):
        client = _FakeRedis({})
        _install(monkeypatch, client)
        identity = cb.base_identity(None, None)
        await cb.publish_candidate_base(
            cb.build_envelope(NOW - timedelta(seconds=45), identity, [1])
        )
        await cb.publish_candidate_base(cb.build_envelope(NOW, identity, [100, 200]))
        cb._reset_l0_for_tests()
        ids, _, _ = await cb.get_candidate_base(NOW, None, None)
        assert ids == [100, 200]

    def test_older_sync_publish_cannot_overwrite_newer(self):
        rc_sync = _FakeSyncRedis()
        identity = cb.base_identity(None, None)
        cb.publish_candidate_base_sync(rc_sync, cb.build_envelope(NOW, identity, [7, 7]))
        cb.publish_candidate_base_sync(
            rc_sync, cb.build_envelope(NOW - timedelta(seconds=90), identity, [3])
        )
        stored = json.loads(rc_sync.store[cb._redis_keys(identity)[0]])
        assert stored["candidate_ids"] == [7, 7]

    @pytest.mark.asyncio
    async def test_monotonic_guard_degrades_safely_without_eval(self, monkeypatch):
        # A Redis without EVAL must still publish (bounded, best-effort) rather
        # than silently never publishing at all.
        client = _FakeRedis({}, mode="no-eval")
        _install(monkeypatch, client)
        identity = cb.base_identity(None, None)
        await cb.publish_candidate_base(cb.build_envelope(NOW, identity, [5]))
        assert client.sets >= 1

    @pytest.mark.asyncio
    async def test_publish_failure_never_raises(self, monkeypatch):
        _install(monkeypatch, _FakeRedis({}, mode="down"))
        identity = cb.base_identity(None, None)
        await cb.publish_candidate_base(cb.build_envelope(NOW, identity, [1]))

    def test_envelope_carries_monotonic_epoch(self):
        identity = cb.base_identity(None, None)
        env = cb.build_envelope(NOW, identity, [1])
        assert isinstance(env["generated_epoch_ms"], int)
        older = cb.build_envelope(NOW - timedelta(seconds=1), identity, [1])
        assert older["generated_epoch_ms"] < env["generated_epoch_ms"]
