"""Queue 275 (#1475): truthful feed diagnostics helpers.

Queue 273 emitted the X-Feed-Stages / X-Feed-Counts / X-Feed-Singleflight
observability headers ONLY on the leader-built response. C67 confirmed the fast
paths a field debugger most needs — fresh hit, stale hit, Redis-error last-good,
coalesced waiter, waiter last-good, and the auth-required team feed — returned
without them. Route-level branch coverage lives in
``tests/integration/test_route_feed_finalizer.py``; this file freezes the two
pure helpers the centralized finalizer is built on.
"""

from app.routes.feed import _feed_obs_counts, _finalize_feed_response


class _Resp:
    def __init__(self):
        self.headers = {}


def test_feed_obs_counts_breaks_down_by_type():
    counts = _feed_obs_counts(
        [{"type": "event"}, {"type": "futures"}, {"type": "event"}],
        total=3,
        returned=3,
    )
    assert counts["type_event"] == 2
    assert counts["type_futures"] == 1
    assert counts["total"] == 3
    assert counts["returned"] == 3


def test_feed_obs_counts_safe_on_empty_and_missing_type():
    counts = _feed_obs_counts(None, total=0, returned=0)
    assert counts == {"total": 0, "returned": 0}
    counts2 = _feed_obs_counts([{"no_type": 1}], total=1, returned=1)
    assert counts2["type_unknown"] == 1


def test_finalizer_stamps_three_headers_and_cache():
    resp = _Resp()
    _finalize_feed_response(
        resp,
        cache_status="hit",
        singleflight="none",
        timings=[{"stage": "cache_hit", "ms": 0.4}],
        started_at=__import__("time").perf_counter(),
        counts=_feed_obs_counts([{"type": "futures"}], total=1, returned=1),
    )
    assert resp.headers["X-Feed-Cache"] == "hit"
    assert resp.headers["X-Feed-Singleflight"] == "none"
    assert "X-Feed-Stages" in resp.headers
    assert "type_futures=1" in resp.headers["X-Feed-Counts"]
    assert "X-Feed-Elapsed-Ms" in resp.headers


def test_finalizer_none_cache_status_leaves_x_feed_cache_unset():
    """The requires-auth early return never set X-Feed-Cache; passing None keeps
    it byte-for-byte absent while still emitting the diagnostics."""
    resp = _Resp()
    _finalize_feed_response(
        resp,
        cache_status=None,
        singleflight="none",
        timings=[],
        started_at=__import__("time").perf_counter(),
        counts=_feed_obs_counts([], total=0, returned=0),
    )
    assert "X-Feed-Cache" not in resp.headers
    assert resp.headers["X-Feed-Singleflight"] == "none"
    assert "X-Feed-Counts" in resp.headers


# --- Queue 277 (#1475): inert, comparable diagnostics ------------------------
import pytest


@pytest.mark.parametrize(
    "items,total,returned",
    [
        ([None], 1, 1),  # element is None → it.get would AttributeError
        ([{"type": "event"}, 5, "x"], 3, 3),  # mixed non-dict elements
        ({"not": "a list"}, 2, 2),  # items is a dict, not a list
        (5, 1, 1),  # items is an int
        ([{"type": "event"}], None, None),  # total/returned null
        ([{"type": "event"}], "3", "1"),  # numeric strings
    ],
)
def test_feed_obs_counts_never_throws_on_malformed_payload(items, total, returned):
    """Count extraction must be independently non-throwing: a malformed or old
    cached payload can never raise out of the diagnostics path and divert the
    response into a cold build (the C69 observer effect)."""
    counts = _feed_obs_counts(items, total=total, returned=returned)
    assert isinstance(counts, dict)
    # total/returned are always coerced to ints, never left as None/str.
    assert isinstance(counts["total"], int)
    assert isinstance(counts["returned"], int)
    # every emitted value is a plain int so the header formatter cannot throw.
    assert all(isinstance(v, int) for v in counts.values())


def test_feed_obs_counts_scope_is_comparable_leader_vs_hit():
    """Leader and immediate-hit counts must be comparable by contract: type_*
    breakdown is page-scoped on every path, so sum(type_*) == returned even when
    total > returned (a paginated feed)."""
    page = [{"type": "event"}, {"type": "futures"}, {"type": "event"}]
    # Leader: full feed has 100 items, page returned 3.
    leader = _feed_obs_counts(page, total=100, returned=3)
    # Immediate hit reading the same cached page.
    hit = _feed_obs_counts(page, total=100, returned=3)
    assert leader == hit
    type_sum = sum(v for k, v in leader.items() if k.startswith("type_"))
    assert type_sum == leader["returned"] == 3
    assert leader["total"] == 100  # total > returned preserved


def test_finalizer_emits_fixed_count_scope_header():
    resp = _Resp()
    _finalize_feed_response(
        resp,
        cache_status="leader",
        singleflight="leader",
        timings=[],
        started_at=__import__("time").perf_counter(),
        counts=_feed_obs_counts([{"type": "event"}], total=10, returned=1),
    )
    # One explicit, machine-readable scope indicator on every path.
    assert resp.headers["X-Feed-Count-Scope"] == "page"
