"""#1500 — the latency rail must not report green through its own blind spot.

`/api/admin/latency-stats` is the only percentile rail in production and it
could not measure the thing it exists for. Three defects, all pinned here:

1. **The estimator floored to a low-order sample.** ``int(pct/100 * (n-1))``
   returns index 0 at n=2 — the MINIMUM. Live proof (Ops r324):
   ``/api/events/typeahead n=2 p50=1.2 p95=1.2 p99=1.2 max=12869.3`` — a p99 of
   1.2 ms on an endpoint whose slowest sample was 12.9 SECONDS.
2. **One global sample counter for every endpoint.** 1-in-10 against a shared
   counter left ``/api/feed`` with n=3 in an hour that contained four measured
   cold misses of 3.9–8.8 s. It retained none of them.
3. **No cache dimension.** Warm hits dominate ``/api/feed``, so a blended p95
   cannot express the cold tail — the single number that makes #1459 closable.

Those three shipped in Queue 292. The ops lane then filed six residuals across
r329 / r330 / r334 — every one closing ``NEEDS-CODE-LANE``, none taken until
LAT-P003. They are pinned at the bottom of this file:

4. **Unbounded Redis key minting (r329 B2).** The middleware runs BEFORE routing
   and filters only on the ``/api`` prefix, so a 404 on any arbitrary
   ``/api/<junk>`` became its own key and ``latency:_endpoints`` has no cap. On
   Premium-0 / 50 MB / allkeys-lru that evicts COLD keys — the samples this rail
   exists to keep.
5. **The payload could not be dated from its own contents (r329 B3).** r330
   watched ``max_ms`` go 19696.7 -> 12761.0 across 25 minutes at the same n=13:
   the worst sample ever recorded aged out silently.
6. **``by_cache_status`` did not sum to ``n`` (r330).** n=13 against a lone
   ``miss`` bucket of n=12 — the fast half, which is exactly what separates cold
   tail from warm serve, was invisible.
7. **``completeness: "complete"`` over a 2-of-5 payload (r334).** The false-green
   shape Queue 294 removed from the VALUES, still living in the VERDICT.
8. **An always-sampled endpoint could simply vanish (r334).** ``/api/feed`` was
   absent from a payload that declared it always-sampled.
9. **No non-finite guard (r329 B1).** Defensive; unreachable from today's
   writer, but one inf 500s the whole rail rather than one row.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.utils.latency_stats import (
    min_samples_for,
    parse_sample_member,
    percentile_nearest_rank,
    percentile_or_none,
    summarize,
)


# ---------------------------------------------------------------------------
# The estimator
# ---------------------------------------------------------------------------
class TestNearestRank:
    def test_the_r324_case_never_returns_the_minimum(self):
        """The headline defect. n=2, [1.2, 12869.3]: the old estimator returned
        1.2 for p95 AND p99."""
        data = [1.2, 12869.3]
        assert percentile_nearest_rank(data, 95) == 12869.3
        assert percentile_nearest_rank(data, 99) == 12869.3
        assert percentile_nearest_rank(data, 50) == 1.2

    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 10, 21, 100])
    def test_percentile_never_resolves_below_its_own_rank(self, n):
        """The general invariant: at least ``ceil(pct/100*n)`` samples must be
        <= the reported value. The old estimator violated this for every n<21
        at p95."""
        data = [float(i) for i in range(n)]
        for pct in (50, 90, 95, 99):
            value = percentile_nearest_rank(data, pct)
            at_or_below = sum(1 for d in data if d <= value)
            import math
            assert at_or_below >= math.ceil(pct / 100 * n)

    def test_empty_returns_none(self):
        assert percentile_nearest_rank([], 95) is None

    def test_single_sample(self):
        assert percentile_nearest_rank([7.0], 99) == 7.0

    def test_p100_is_the_max(self):
        assert percentile_nearest_rank([1.0, 2.0, 3.0], 100) == 3.0


class TestMinSamples:
    @pytest.mark.parametrize("pct,expected", [(50, 2), (90, 10), (95, 20), (99, 100)])
    def test_derived_thresholds(self, pct, expected):
        assert min_samples_for(pct) == expected

    @pytest.mark.parametrize("n", [0, 1, 2, 3, 19])
    def test_p95_is_null_below_minimum(self, n):
        data = [float(i) for i in range(n)]
        assert percentile_or_none(data, 95) is None

    def test_p95_available_at_minimum(self):
        """n=20 is the first n where p95 is answerable. ceil(.95*20)-1 = 18, and
        19 of the 20 samples (95%) are <= data[18]."""
        data = [float(i) for i in range(20)]
        assert percentile_or_none(data, 95) == 18.0
        assert sum(1 for d in data if d <= 18.0) == 19

    def test_the_r324_case_is_null_not_a_number(self):
        """Under the min-n rule the honest answer to 'p95 of 2 samples' is
        'unavailable' — never 1.2, and never a bare 12869.3 dressed as a p95."""
        assert percentile_or_none([1.2, 12869.3], 95) is None
        assert percentile_or_none([1.2, 12869.3], 99) is None
        # p50 IS answerable at n=2.
        assert percentile_or_none([1.2, 12869.3], 50) == 1.2


class TestSummarize:
    @pytest.mark.parametrize("n", [0, 1, 2, 3, 19, 20, 100])
    def test_n_is_always_reported(self, n):
        s = summarize([float(i) for i in range(n)])
        assert s["n"] == n
        assert s["min_samples"]["p95"] == 20

    def test_below_min_reports_null_percentiles_but_a_real_max(self):
        s = summarize([1.2, 12869.3])
        assert s["p95_ms"] is None
        assert s["p99_ms"] is None
        assert s["max_ms"] == 12869.3   # the tail is still visible
        assert s["min_ms"] == 1.2

    def test_empty_population(self):
        s = summarize([])
        assert s == {
            "n": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None,
            "max_ms": None, "min_ms": None,
            "min_samples": {"p50": 2, "p95": 20, "p99": 100},
        }

    def test_unsorted_input_is_sorted(self):
        s = summarize([9.0, 1.0, 5.0])
        assert s["min_ms"] == 1.0 and s["max_ms"] == 9.0


# ---------------------------------------------------------------------------
# Sample member encoding
# ---------------------------------------------------------------------------
class TestParseSampleMember:
    def test_new_three_field_form(self):
        assert parse_sample_member("1750000000.5:8798.2:miss") == (8798.2, "miss")

    def test_legacy_two_field_form_still_parses(self):
        """Members written before this change stay in the rolling window for up
        to an hour; dropping them would shrink n exactly when the new
        percentiles are being validated."""
        assert parse_sample_member("1750000000.5:23.3") == (23.3, "none")

    @pytest.mark.parametrize("bad", ["", "nope", "1750000000.5", "ts:not-a-number"])
    def test_unparseable_returns_none(self, bad):
        assert parse_sample_member(bad) is None

    def test_empty_bucket_field_falls_back_to_none(self):
        assert parse_sample_member("1.0:5.0:") == (5.0, "none")


# ---------------------------------------------------------------------------
# Middleware sampling + cache buckets
# ---------------------------------------------------------------------------
class TestSampling:
    def setup_method(self):
        from app.middleware import latency
        latency._request_counters.clear()

    def test_feed_is_always_sampled(self):
        """The fix for 'n=3 in an hour, all of them warm hits'."""
        from app.middleware.latency import _should_sample

        assert all(_should_sample("/api/feed") for _ in range(25))

    def test_other_endpoints_keep_the_global_rate(self):
        from app.middleware import latency

        hits = sum(1 for _ in range(100) if latency._should_sample("/api/events/{id}"))
        assert hits == 100 // latency.SAMPLE_RATE

    def test_counters_are_per_endpoint_not_global(self):
        """A rare endpoint's sampling must not depend on unrelated traffic."""
        from app.middleware import latency

        for _ in range(latency.SAMPLE_RATE - 1):
            latency._should_sample("/api/busy")
        # /api/rare has been seen once; it must not ride /api/busy's counter.
        assert latency._should_sample("/api/rare") is (latency.SAMPLE_RATE == 1)
        assert latency._request_counters["/api/rare"] == 1


class TestCacheBucket:
    @pytest.mark.parametrize("header,expected", [
        ("miss", "miss"), ("hit", "hit"), ("stale_hit", "stale_hit"),
        ("error", "error"), ("MISS", "miss"), ("  hit ", "hit"),
        # #2143: the six the rail used to pool into one opaque `other`.
        ("coalesced", "coalesced"), ("last_good", "last_good"),
        ("unavailable", "unavailable"), ("disabled", "disabled"),
        ("disabled_debug", "disabled_debug"),
        ("disabled_reviewed_filter", "disabled_reviewed_filter"),
    ])
    def test_allowlisted_buckets(self, header, expected):
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={"x-feed-cache": header})) == expected

    def test_bucket_allowlist_covers_everything_its_writer_emits(self):
        """The allowlist is DERIVED from the writer, never restated beside it.

        #2143. `_CACHE_BUCKETS` was four hand-picked values while
        `routes/feed.py` wrote ten, so `coalesced`, `last_good`, `unavailable`
        and the three `disabled*` values all landed in `other` — 37% of
        production `/api/feed` samples (35 of 95 bucketed, 2026-09-21 21:42Z)
        pooled into one bucket whose members have different serve shapes and
        therefore incomparable latencies.

        Restating the values here would reproduce the original defect one layer
        down, so this derives them from the producer's own call sites — the same
        authority as `test_cache_status_domain_matches_its_producer` in
        `test_client_timing_contract.py`, which has guarded the COPY of this set
        since CERT-1873 while the original went unguarded.

        #2143 SECOND PASS — THE DERIVATION USED TO BE THE DEFECT. Both guards
        parsed the producer with a regex over STRING LITERALS, and the allowlist
        was built from that same regex, so `produced - _CACHE_BUCKETS` was empty
        BY CONSTRUCTION: the test compared a set against itself. Four values are
        written through a variable (`_read_shared_feed_cache` returns
        `shared_hit`/`shared_stale_hit`; `_pb_status` is
        `page_base_hit`/`page_base_stale_hit`), the regex never saw them, and on
        a release-pure window (2026-09-22 00:12Z) `other` was 43.2% of bucketed
        `/api/feed` samples — up from 35.4%, with this test green over it.

        The floor pin added in the first pass did not rescue it, and that is the
        lesson worth keeping: a floor detects values DISAPPEARING from a parse,
        never values the parse NEVER REACHED. So the parse is gone. The producer
        is now read by AST, and anything the resolver cannot resolve is a
        FAILURE rather than a silent omission — a derivation that cannot go
        quietly incomplete cannot go quietly vacuous.
        """
        from tests.cache_status_producer import resolve_cache_status_domain

        from app.middleware.latency import _CACHE_BUCKETS

        produced, unresolved, sites = resolve_cache_status_domain()

        assert not unresolved, (
            f"the producer AST resolver could not resolve {len(unresolved)} "
            f"cache_status argument(s): {unresolved} — resolve them (extend the "
            f"resolver) rather than letting them pass unseen, which is exactly "
            f"how #2143's four missing values stayed invisible behind a green test"
        )
        assert sites >= 13, (
            f"only {sites} cache_status call sites found (expected >=13) — the "
            f"resolver has stopped seeing the producer; treat as rot, not as a "
            f"shrinking domain, until you have read feed.py and confirmed"
        )
        assert produced, "resolved no cache_status producer at all — the AST walk rotted"

        missing = produced - set(_CACHE_BUCKETS)
        assert not missing, (
            f"feed.py writes X-Feed-Cache values the latency rail cannot name: "
            f"{sorted(missing)} — they pool into `other`, and a pooled bucket "
            f"cannot grade a per-bucket latency claim (#2143)"
        )

    def test_the_producer_resolver_refuses_an_argument_it_cannot_resolve(self):
        """The anti-vacuity property itself, asserted.

        The guard above is only worth having if an UNRESOLVABLE `cache_status=`
        argument is loud. Its predecessor's failure mode was silence: a value it
        could not parse simply did not appear in `produced`, and the comparison
        that followed was then trivially satisfied. Feed the resolver's
        internals a call site whose argument comes from outside the module and
        assert it is REPORTED, not dropped.
        """
        import ast

        from tests.cache_status_producer import _Resolver

        tree = ast.parse(
            "import x\n"
            "def _finalize_feed_response(**kw):\n"
            "    pass\n"
            "_v = x.something_opaque()\n"
            "_finalize_feed_response(cache_status=_v)\n"
        )
        resolver = _Resolver(tree)
        call = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and any(k.arg == "cache_status" for k in n.keywords)
        ][0]
        arg = [k for k in call.keywords if k.arg == "cache_status"][0].value

        values, unresolved = resolver.resolve(arg)

        assert values == set(), "invented a value it could not actually resolve"
        assert unresolved, (
            "an unresolvable cache_status argument produced NO complaint — the "
            "resolver is back to failing silently, which is the #2143 defect"
        )

    def test_unknown_value_collapses_to_other(self):
        """Bounded dimension — an unexpected header value can never mint a new
        bucket (Redis is Premium-0/50MB with allkeys-lru).

        Widening the allowlist to the writer's real domain (#2143) does not
        relax this: the dimension is still closed, so no caller-controlled
        header value can mint a bucket of its own.
        """
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={"x-feed-cache": "weird"})) == "other"

    def test_absent_header_is_none_bucket(self):
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={})) == "none"


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def _redis_with(samples: dict[str, list[str]], now: float = 0.0):
    """Fake Redis whose ZRANGEBYSCORE honours `withscores` like the real client.

    The score is the sample timestamp. Members already carry it as their first
    field, so it is parsed back out — a fixture cannot then drift from the
    member/score agreement the real writer maintains.
    """
    r = MagicMock()
    r.smembers.return_value = set(samples.keys())

    def _zrangebyscore(key, lo, hi, withscores=False):
        members = samples[key.split("latency:", 1)[1]]
        if not withscores:
            return members
        out = []
        for m in members:
            try:
                score = float(m.split(":")[0])
            except (TypeError, ValueError):
                score = 0.0
            out.append((m, score))
        return out

    r.zrangebyscore.side_effect = _zrangebyscore
    return r


@pytest.mark.asyncio
async def test_endpoint_reports_null_not_a_false_p99():
    """The end-to-end r324 reproduction."""
    from app.routes.admin import get_latency_stats

    r = _redis_with({
        "/api/events/typeahead": ["1.0:1.2:none", "2.0:12869.3:none"],
    })
    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    ep = out["endpoints"][0]
    assert ep["samples"] == 2
    assert ep["n"] == 2
    assert ep["p95_ms"] is None
    assert ep["p99_ms"] is None
    assert ep["max_ms"] == 12869.3


@pytest.mark.asyncio
async def test_endpoint_splits_feed_by_cache_status():
    """Cold p95 is unmeasurable while warm hits dominate the population."""
    from app.routes.admin import get_latency_stats

    warm = [f"{i}.0:20.0:hit" for i in range(30)]
    cold = [f"9{i}.0:{3000 + i * 100}.0:miss" for i in range(25)]
    r = _redis_with({"/api/feed": warm + cold})

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    ep = out["endpoints"][0]
    buckets = ep["by_cache_status"]
    assert buckets["miss"]["n"] == 25
    assert buckets["hit"]["n"] == 30
    # The cold tail is legible on its own; the blended number hides it.
    assert buckets["miss"]["p95_ms"] >= 5000
    assert buckets["hit"]["p95_ms"] == 20.0
    assert ep["always_sampled"] is True


@pytest.mark.asyncio
async def test_endpoint_tolerates_legacy_members():
    from app.routes.admin import get_latency_stats

    r = _redis_with({"/api/events": [f"{i}.0:{10 + i}.0" for i in range(25)]})
    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    ep = out["endpoints"][0]
    assert ep["n"] == 25
    assert "by_cache_status" not in ep   # no real buckets → no noise heading


@pytest.mark.asyncio
async def test_null_p95_does_not_sort_as_fast():
    """An unmeasurable endpoint must not be buried below fast ones — its max is
    a lower bound on its true p95."""
    from app.routes.admin import get_latency_stats

    r = _redis_with({
        "/api/slow_unknown": ["1.0:9000.0:none", "2.0:1.0:none"],   # n=2 → null p95
        "/api/fast": [f"{i}.0:5.0:none" for i in range(30)],         # real p95 = 5
    })
    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    assert out["endpoints"][0]["endpoint"] == "/api/slow_unknown"


@pytest.mark.asyncio
async def test_endpoint_requires_admin_auth():
    from fastapi import HTTPException

    from app.routes.admin import get_latency_stats

    with patch("app.routes.admin._check_admin_secret",
               side_effect=HTTPException(status_code=403, detail="no")):
        with pytest.raises(HTTPException) as exc:
            await get_latency_stats(MagicMock(), None, 20, 60)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Redis footprint bound
# ---------------------------------------------------------------------------
class TestWriteBound:
    async def test_sample_write_caps_member_count(self):
        """Always-sampling /api/feed multiplies its sorted set ~SAMPLE_RATE-fold.
        Redis is Premium-0 / 50 MB / allkeys-lru, where an oversized working set
        evicts cold keys regardless of TTL (r320 lost the grid-sentinel verdict
        that way), so the member count is capped explicitly."""
        from app.middleware import latency

        latency._request_counters.clear()
        pipe = MagicMock()
        redis = MagicMock()
        redis.pipeline.return_value = pipe

        request = MagicMock()
        request.url.path = "/api/feed"
        response = MagicMock(headers={"x-feed-cache": "miss"})

        async def _call_next(_req):
            return response

        mw = latency.LatencyMiddleware(app=MagicMock())
        with patch.object(latency, "_get_redis", return_value=redis):
            await mw.dispatch(request, _call_next)

        # The rank trim is present and keeps the NEWEST MAX_SAMPLES_PER_ENDPOINT.
        pipe.zremrangebyrank.assert_called_once_with(
            "latency:/api/feed", 0, -(latency.MAX_SAMPLES_PER_ENDPOINT + 1)
        )
        # The time-window trim is still there too — both bounds apply.
        assert pipe.zremrangebyscore.called
        # The cache bucket rides the existing member; no new key family.
        member = list(pipe.zadd.call_args.args[1].keys())[0]
        assert member.endswith(":miss")
        assert redis.pipeline.call_count == 1

    def test_cap_is_comfortably_above_p99_requirement(self):
        from app.middleware.latency import MAX_SAMPLES_PER_ENDPOINT
        from app.utils.latency_stats import min_samples_for

        assert MAX_SAMPLES_PER_ENDPOINT >= min_samples_for(99) * 10


# ---------------------------------------------------------------------------
# #1500 residuals — ops r329 (B1/B2/B3), r330, r334. Each closed NEEDS-CODE-LANE
# and none had been taken; these pin them so they cannot come back.
# ---------------------------------------------------------------------------
class TestEndpointBucketIsBounded:
    """r329 B2 — an unauthenticated caller could mint unbounded Redis keys.

    The middleware runs BEFORE routing and only filters on the /api prefix, so a
    404 on any arbitrary `/api/<junk>` used to become its own endpoint key, and
    `latency:_endpoints` has no cap. Redis is Premium-0 / 50 MB / allkeys-lru,
    where an oversized working set evicts COLD keys regardless of TTL — the r320
    grid-sentinel mechanism — so the flood would evict the very cold samples
    this rail exists to retain.
    """

    @staticmethod
    def _keys_written(paths):
        """Drive the REAL middleware over a real router; collect the Redis keys."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.middleware import latency

        app = FastAPI()
        app.add_middleware(latency.LatencyMiddleware)

        @app.get("/api/leagues/{sport_key}")
        def _league(sport_key: str):
            return {"ok": sport_key}

        @app.get("/api/events/{event_id}")
        def _event(event_id: int):
            return {"ok": event_id}

        pipe = MagicMock()
        redis = MagicMock()
        redis.pipeline.return_value = pipe

        latency._request_counters.clear()
        with patch.object(latency, "_get_redis", return_value=redis), \
             patch.object(latency, "SAMPLE_RATE", 1):
            client = TestClient(app, raise_server_exceptions=False)
            for p in paths:
                client.get(p)

        return [c.args[0] for c in pipe.zadd.call_args_list]

    def test_unmatched_paths_collapse_to_one_bucket(self):
        """20 distinct junk paths must not mint 20 Redis keys."""
        from app.middleware.latency import UNMATCHED_BUCKET

        keys = self._keys_written([f"/api/junk-{i}/{i}" for i in range(20)])

        assert len(keys) == 20                      # every request still sampled
        assert set(keys) == {f"latency:{UNMATCHED_BUCKET}"}   # ...into ONE key

    def test_string_path_params_bucket_by_route_template(self):
        """`_normalize_path` only collapses numbers and UUIDs, so every route
        with a STRING path param kept its raw value as its own bucket."""
        keys = self._keys_written([
            "/api/leagues/basketball_nba",
            "/api/leagues/americanfootball_nfl",
            "/api/leagues/icehockey_nhl",
        ])

        assert set(keys) == {"latency:/api/leagues/{sport_key}"}

    def test_numeric_ids_still_collapse(self):
        keys = self._keys_written(["/api/events/1", "/api/events/2", "/api/events/3"])
        assert set(keys) == {"latency:/api/events/{event_id}"}

    def test_counter_dict_is_bounded(self):
        """r329 also flagged `_request_counters` as unbounded per-dyno memory
        growth on the same attacker-controlled input."""
        from app.middleware import latency

        latency._request_counters.clear()
        with patch.object(latency, "SAMPLE_RATE", 10):
            for i in range(latency._MAX_COUNTER_KEYS + 500):
                latency._should_sample(f"/api/synthetic/{i}")

        assert len(latency._request_counters) <= latency._MAX_COUNTER_KEYS

    def test_skip_prefixes_dead_code_is_gone(self):
        """Defined, never referenced — and its "/" entry would have skipped
        every path if it had ever been wired up."""
        from app.middleware import latency

        assert not hasattr(latency, "_SKIP_PREFIXES")


class TestNonFiniteGuard:
    """r329 B1 — defensive. Unreachable from today's writer (perf_counter is
    always finite), but the blast radius is the WHOLE rail, not one row."""

    @pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "NaN", "Infinity"])
    def test_non_finite_samples_are_rejected(self, bad):
        assert parse_sample_member(f"1.0:{bad}:miss") is None

    def test_a_single_inf_cannot_500_the_whole_rail(self):
        """json.dumps(allow_nan=False) — Starlette's renderer — raises on inf.
        One poisoned sample must not take every other endpoint's numbers with
        it."""
        import json

        members = [f"{i}.0:{10 + i}.0:hit" for i in range(25)] + ["99.0:inf:miss"]
        good = [parse_sample_member(m) for m in members]
        kept = [g[0] for g in good if g is not None]

        assert len(kept) == 25
        json.dumps(summarize(kept), allow_nan=False)   # renders, does not raise


@pytest.mark.asyncio
async def test_payload_can_be_dated_from_its_own_contents():
    """r329 B3 / r330 — `max_ms` moved 19696.7 -> 12761.0 across 25 minutes at
    the SAME n=13: the worst sample the rail ever recorded aged out silently and
    no consumer could know it had existed."""
    import time as _t

    from app.routes.admin import get_latency_stats

    now = _t.time()
    # Oldest sample 30 min old, newest 10 s old.
    members = [f"{now - 1800}:5000.0:miss"] + [
        f"{now - 10 - i}:{20 + i}.0:hit" for i in range(24)
    ]
    r = _redis_with({"/api/feed": members})

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    assert "generated_at" in out and out["generated_at"]

    ep = out["endpoints"][0]
    # ~10s vs ~1800s — the two must be clearly distinguishable, which is the
    # whole point: "n=25 from the last minute" != "n=25 from 30 minutes ago".
    assert ep["newest_sample_age_s"] < 120
    assert ep["oldest_sample_age_s"] > 1500


@pytest.mark.asyncio
async def test_cache_buckets_account_for_every_sample():
    """r330 — endpoint n=13 with a lone `miss` bucket of n=12, and a row min_ms
    of 4.0ms against the miss bucket's 1710.0ms: a real fast sample existed and
    was invisible. The fast bucket is exactly the half that separates cold tail
    from warm serve."""
    from app.routes.admin import get_latency_stats

    members = (
        [f"{i}.0:1800.0:miss" for i in range(12)]
        + ["99.0:4.0"]           # legacy 2-field member -> "none" bucket
    )
    r = _redis_with({"/api/feed": members})

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    ep = out["endpoints"][0]
    assert ep["n"] == 13
    assert ep["min_ms"] == 4.0
    bucketed = sum(b["n"] for b in ep["by_cache_status"].values())
    assert bucketed + ep["unbucketed_samples"] == ep["n"]
    assert ep["unbucketed_samples"] == 1


@pytest.mark.asyncio
async def test_completeness_reconciles_against_its_own_denominator():
    """r334 — `completeness: "complete"` asserted over a 2-of-5 payload with an
    empty `unreadable_endpoints`. The false-green shape Queue 294 removed from
    the VALUES was still living in the VERDICT."""
    from app.routes.admin import get_latency_stats

    r = _redis_with({
        "/api/playoffs/{league_slug}": ["1.0:29.7:none"],
        "/api/teams/{identifier}": ["1.0:22.3:none"],
        "/api/quiet-a": [],      # tracked, readable, nothing in window
        "/api/quiet-b": [],
        "/api/quiet-c": [],
    })

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    rec = out["endpoint_reconciliation"]
    assert rec["tracked"] == 5
    assert rec["reported"] == 2
    assert rec["no_samples_in_window"] == 3       # the gap r334 could not see
    assert rec["unaccounted"] == 0
    assert rec["reconciles"] is True
    assert out["completeness"] == "complete"      # now EARNED, not asserted


@pytest.mark.asyncio
async def test_always_sampled_endpoint_never_just_vanishes():
    """r334 — `/api/feed` was declared always_sampled and was entirely absent.
    Absence with no timestamp is indistinguishable from a dead sampler."""
    from app.routes.admin import get_latency_stats

    r = _redis_with({"/api/playoffs/{league_slug}": ["1.0:29.7:none"]})

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 20, 60)

    feed = [e for e in out["endpoints"] if e["endpoint"] == "/api/feed"]
    assert len(feed) == 1
    assert feed[0]["no_samples_in_window"] is True
    assert feed[0]["n"] == 0
    assert feed[0]["p95_ms"] is None


@pytest.mark.asyncio
async def test_zero_row_survives_top_truncation():
    """A zero row has no p95 to sort on, so `top` would drop it exactly when the
    rail is busiest — the moment the signal matters most."""
    from app.routes.admin import get_latency_stats

    samples = {
        f"/api/busy-{i}": [f"{j}.0:{100 * (i + 1)}.0:none" for j in range(25)]
        for i in range(10)
    }
    r = _redis_with(samples)

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        out = await get_latency_stats(MagicMock(), "s", 3, 60)   # top=3

    names = [e["endpoint"] for e in out["endpoints"]]
    assert "/api/feed" in names
    assert out["endpoint_reconciliation"]["truncated_by_top"] == 7


# ---------------------------------------------------------------------------
# #2143 — the `minutes` window parameter
#
# The fixed 60-minute window made a deploy-free read unobtainable. A release
# inside the window restarts dynos, so the samples that follow are cold and an
# after-check reading them cannot separate "the fix did nothing" from "the
# window contained a deploy". Measured over 19 consecutive intervals during desk
# hours on 2026-09-21: 0 cleared 62 minutes, 4 cleared 32.
#
# ⚠️ `_redis_with` above IGNORES the `lo`/`hi` bounds it is handed — every test
# written against it passes whatever the cutoff is. A window test built on it
# would be VACUOUS. `_redis_honouring_scores` below is the same fake with the
# lower bound actually applied, which is the whole point of these tests.
# ---------------------------------------------------------------------------
def _redis_honouring_scores(samples: dict[str, list[str]]):
    """`_redis_with`, except ZRANGEBYSCORE applies the lower bound.

    The route's cutoff arithmetic is the subject here, so a fake that returns
    every member regardless of score cannot fail and must not be used.
    """
    r = MagicMock()
    r.smembers.return_value = set(samples.keys())

    def _zrangebyscore(key, lo, hi, withscores=False):
        out = []
        for m in samples[key.split("latency:", 1)[1]]:
            score = float(m.split(":")[0])
            if score < float(lo):
                continue
            out.append((m, score) if withscores else m)
        return out

    r.zrangebyscore.side_effect = _zrangebyscore
    return r


def _aged_feed_samples(now: float):
    """25 samples 50 min old (slow) + 25 samples 5 min old (fast).

    The two ages carry different latencies so a read can be attributed to a
    window by its VALUES, not only by its count.
    """
    old = [f"{now - 50 * 60 + i}:{5000 + i}.0:miss" for i in range(25)]
    recent = [f"{now - 5 * 60 + i}:{20 + i}.0:hit" for i in range(25)]
    return {"/api/feed": old + recent}


@pytest.mark.asyncio
async def test_narrowing_the_window_excludes_the_older_samples():
    """The decisive test: SAME fixture, two windows, different populations.

    Reading only `minutes=30` would not prove the cutoff moved — it would also
    pass against a fake that drops everything. The 60-minute read on the same
    fixture is the control.
    """
    import time as _t

    from app.routes.admin import get_latency_stats

    now = _t.time()
    r = _redis_honouring_scores(_aged_feed_samples(now))

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        hour = await get_latency_stats(MagicMock(), "s", 20, 60)
        half = await get_latency_stats(MagicMock(), "s", 20, 30)

    hour_feed = next(e for e in hour["endpoints"] if e["endpoint"] == "/api/feed")
    half_feed = next(e for e in half["endpoints"] if e["endpoint"] == "/api/feed")

    # Control: the hour sees both ages.
    assert hour_feed["n"] == 50
    assert set(hour_feed["by_cache_status"]) == {"hit", "miss"}

    # Subject: 30 minutes excludes the 50-minute-old population entirely.
    assert half_feed["n"] == 25
    assert set(half_feed["by_cache_status"]) == {"hit"}
    assert half_feed["max_ms"] < 100  # the 5000 ms miss tail is gone


@pytest.mark.asyncio
async def test_the_payload_states_the_window_it_actually_used():
    """`window` was the frozen literal "1 hour". A 30-minute read carrying an
    hourly title is the false-confidence shape this endpoint exists to refuse."""
    import time as _t

    from app.routes.admin import get_latency_stats

    r = _redis_honouring_scores(_aged_feed_samples(_t.time()))

    with patch("app.routes.admin._check_admin_secret", return_value=True), \
         patch("app.tasks.redis_state.get_redis_client", return_value=r):
        hour = await get_latency_stats(MagicMock(), "s", 20, 60)
        half = await get_latency_stats(MagicMock(), "s", 20, 30)

    assert hour["window"] == "1 hour"
    assert hour["window_minutes"] == 60
    assert half["window"] == "30 minutes"
    assert half["window_minutes"] == 30
    # A reader must be able to tell the two payloads apart on this field alone.
    assert hour["window"] != half["window"]


def _minutes_query():
    """The declared `minutes` parameter, with its constraints.

    A direct call cannot resolve a FastAPI default (that is why every test in
    this file passes `top` explicitly), so the DEFAULT and the BOUNDS have to be
    read off the declaration — which is the contract FastAPI actually enforces
    — rather than inferred from a call that never exercises it.
    """
    import inspect

    from app.routes.admin import get_latency_stats

    q = inspect.signature(get_latency_stats).parameters["minutes"].default
    bounds = {type(m).__name__.lower(): m for m in q.metadata}
    return q, bounds


def test_the_default_window_is_still_one_hour():
    """Every existing caller omits `minutes`, so the default is their window."""
    q, _ = _minutes_query()
    assert q.default == 60


def test_the_maximum_window_agrees_with_what_the_middleware_retains():
    """A drift guard across TWO independent sources, not one parse twice.

    The route's ceiling is declared on the Query; the retention is the
    middleware's `WINDOW_SECONDS`. If someone raises retention and not the
    ceiling, the endpoint silently refuses data that now exists; if they lower
    retention, it accepts a window it cannot fill and reports the shortfall as
    a quiet period. Neither is visible without this comparison.
    """
    from app.middleware.latency import WINDOW_SECONDS

    _, bounds = _minutes_query()
    assert bounds["le"].le == WINDOW_SECONDS // 60
    # Refused above the ceiling, never clamped: serving 60 minutes to a caller
    # who asked for 120 would label an hour of samples as two.
    assert bounds["ge"].ge == 1


def test_an_out_of_range_window_is_refused_by_the_real_stack():
    """End-to-end proof of "refused, never clamped".

    The bounds test above reads the DECLARATION; this one proves FastAPI
    enforces it. Validation runs before the handler, so a bad `minutes` is a 422
    regardless of the admin secret — and `minutes=30` reaching the auth check
    (403) is the control proving the 422s are about the bound and not about
    the parameter being rejected outright.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/admin/latency-stats?minutes=120&secret=wrong").status_code == 422
    assert c.get("/api/admin/latency-stats?minutes=0&secret=wrong").status_code == 422
    assert c.get("/api/admin/latency-stats?minutes=30&secret=wrong").status_code == 403
