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
    ])
    def test_allowlisted_buckets(self, header, expected):
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={"x-feed-cache": header})) == expected

    def test_unknown_value_collapses_to_other(self):
        """Bounded dimension — an unexpected header value can never mint a new
        bucket (Redis is Premium-0/50MB with allkeys-lru)."""
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={"x-feed-cache": "weird"})) == "other"

    def test_absent_header_is_none_bucket(self):
        from app.middleware.latency import _cache_bucket

        assert _cache_bucket(MagicMock(headers={})) == "none"


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def _redis_with(samples: dict[str, list[str]]):
    r = MagicMock()
    r.smembers.return_value = set(samples.keys())
    r.zrangebyscore.side_effect = lambda key, lo, hi: samples[key.split("latency:", 1)[1]]
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
        out = await get_latency_stats(MagicMock(), "s", 20)

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
        out = await get_latency_stats(MagicMock(), "s", 20)

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
        out = await get_latency_stats(MagicMock(), "s", 20)

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
        out = await get_latency_stats(MagicMock(), "s", 20)

    assert out["endpoints"][0]["endpoint"] == "/api/slow_unknown"


@pytest.mark.asyncio
async def test_endpoint_requires_admin_auth():
    from fastapi import HTTPException

    from app.routes.admin import get_latency_stats

    with patch("app.routes.admin._check_admin_secret",
               side_effect=HTTPException(status_code=403, detail="no")):
        with pytest.raises(HTTPException) as exc:
            await get_latency_stats(MagicMock(), None, 20)
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
