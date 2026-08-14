"""#1807 — the census must answer, or say why it cannot. It must never 503.

The failure this file exists to prevent, stated exactly, because the shape is
easy to reintroduce and was not visible in any test:

``redis_census`` bounded its expensive per-key work with a PER-CLASS quota
(``sample_per_class``). That is only a bound if the number of classes is
bounded, and ``_redis_key_class`` folded a key to its first two colon segments.
So ``interestingness:{market_id}`` — 41,152 keys written by
``precompute_interestingness`` — produced 41,152 distinct classes, every one of
them under its own untouched quota, and the census issued a ``MEMORY USAGE``
**and** a ``TTL`` round trip for every single key. It ran past Heroku's 30 s
router timeout and returned **503**, on the default call, against the very
keyspace #1716's acceptance criteria named it to measure.

Two things are therefore tested here, and the second matters more than the
first:

1. The fold is structural — an ``<family>:{id}`` keyspace collapses to one
   class — so the cost tracks the number of families, not the number of keys.
2. Whatever the bound, hitting it produces a **partial 200 with a verdict**,
   never a timeout and never a silently-empty body. An empty keyspace, a
   truncated scan and an unreachable Redis must read differently (gotcha #53).

Nothing here measures elapsed time. The deadline is driven off an injected
counter, because a test that branches on the real clock is the bug in gotcha
#44, not a test of one.

**Amended 2026-08-13 (LAT-P048), after a Codex post-merge audit found two
honesty bugs in the very rail this file was written to keep honest — and found
them THROUGH this file's own double.** Both are recorded at the bottom under
"the terminal page and the budget". The lesson generalises past the census:

*A test double that cannot express the cost of the thing under test will
certify the bound that fails to charge it.* ``_PagingFakeRedis.memory_usage``
and ``.ttl`` returned instantly, so no test in this file could describe a page
that is slow rather than merely long. All 20 tests passed against an endpoint
that could burn 50 simulated seconds against a 12-second deadline and then
report ``verdict="complete"``. The fix is ``_ClockedFakeRedis``, whose sampling
costs time, and the rule is that a bound expressed in SECONDS needs a double
that can spend them.
"""

import pytest

import app.routes.admin_celery as mod
import app.tasks.redis_state as redis_state


class _PagingFakeRedis:
    """A Redis that paginates, and counts what the census asks of it.

    The pre-existing census fake returns the whole keyspace in a single page
    with ``cursor == 0``, which cannot exercise a per-page bound at all — the
    loop breaks before the first check. Pagination is the point of this one.
    """

    def __init__(self, keys, ttls=None, page=500, dbsize=None):
        self._keys = list(keys)
        self._ttls = ttls or {}
        self._page = page
        self._dbsize = len(self._keys) if dbsize is None else dbsize
        self.memory_usage_calls = 0
        self.ttl_calls = 0
        self.scan_calls = 0

    def info(self, section):
        return {
            "memory": {
                "used_memory": 40 * 1024 * 1024,
                "used_memory_human": "40.00M",
                "used_memory_peak_human": "55.22M",
                "maxmemory": 100 * 1024 * 1024,
                "maxmemory_human": "100.00M",
                "maxmemory_policy": "allkeys-lru",
                "mem_fragmentation_ratio": 1.1,
            },
            "stats": {
                "evicted_keys": 0,
                "expired_keys": 11,
                "keyspace_hits": 5,
                "keyspace_misses": 1,
                "rejected_connections": 0,
            },
            "clients": {"connected_clients": 26, "blocked_clients": 0},
        }[section]

    def dbsize(self):
        return self._dbsize

    def scan(self, cursor=0, count=500):
        self.scan_calls += 1
        start = int(cursor)
        batch = self._keys[start : start + self._page]
        nxt = start + self._page
        if nxt >= len(self._keys):
            nxt = 0
        return nxt, [k.encode() for k in batch]

    def memory_usage(self, key, samples=0):
        self.memory_usage_calls += 1
        return 700

    def ttl(self, key):
        self.ttl_calls += 1
        return self._ttls.get(key, -1)


class _Clock:
    """An injected monotonic clock that only moves when something spends it."""

    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class _ClockedFakeRedis(_PagingFakeRedis):
    """A Redis whose SAMPLING COSTS TIME — the double this file was missing.

    ``_PagingFakeRedis`` answers ``MEMORY USAGE`` and ``TTL`` for free, so the
    only way it could ever trip the deadline was by being handed a tick
    iterator that jumped. That made every deadline test implicitly a test of
    *many cheap pages*, and left *one expensive page* — the actual production
    shape, 500 keys x 2 synchronous round trips — inexpressible.

    Here each sample call advances the injected clock, so elapsed time is a
    function of the work requested rather than of a scripted sequence. Nothing
    reads the wall clock (gotcha #44).
    """

    def __init__(self, keys, *, clock, cost_s=0.0, **kwargs):
        super().__init__(keys, **kwargs)
        self._clock = clock
        self._cost_s = cost_s

    def memory_usage(self, key, samples=0):
        self._clock.advance(self._cost_s)
        return super().memory_usage(key, samples=samples)

    def ttl(self, key):
        self._clock.advance(self._cost_s)
        return super().ttl(key)


class _DeadRedis:
    def info(self, section):
        raise ConnectionError("Error 111 connecting to redis: Connection refused")


async def _census(monkeypatch, fake, **kwargs):
    monkeypatch.setattr(mod, "_check_admin_secret", lambda *a, **k: None)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: fake)
    params = {"scan_limit": 200000, "sample_per_class": 12, "deadline_s": 12.0,
              "sample_budget": 4000}
    params.update(kwargs)
    return await mod.redis_census(request=None, secret="x", **params)


# ---------------------------------------------------------------------------
# The fold — cost has to track families, not keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,expected",
    [
        # The #1807 keyspace itself.
        ("interestingness:41152", "interestingness:*"),
        ("interestingness:7", "interestingness:*"),
        # Opaque ids in general, not just the one family somebody listed.
        ("lock:9f8b1c2d3e4a5b6c7d8e9f0a1b2c3d4e", "lock:*"),
        ("session:0e1d2c3b-4a59-6879-8a9b-0c1d2e3f4a5b", "session:*"),
        # Families keep their names.
        ("bainluck:calibration:payload", "bainluck:calibration"),
        ("bainluck:category:politics", "bainluck:category"),
        ("interestingness:blend_weight", "interestingness:blend_weight"),
        # The prefix table still wins where it applies.
        ("celery-task-meta-abc123", "celery-task-meta-*"),
        ("_kombu.binding.celery", "_kombu.binding.*"),
        # Degenerate input must not raise.
        ("", "(root)"),
        ("plainkey", "plainkey"),
    ],
)
def test_key_class_folds_opaque_ids_but_keeps_family_names(key, expected):
    assert mod._redis_key_class(key) == expected


def test_short_hex_is_a_name_not_an_id():
    """`bainluck:feed` is hex-ish only if you squint. Don't fold real names."""
    assert mod._looks_like_opaque_id("feed") is False
    assert mod._looks_like_opaque_id("abc") is False
    assert mod._looks_like_opaque_id("") is False
    assert mod._looks_like_opaque_id("0123456789abcdef") is True


@pytest.mark.asyncio
async def test_the_1807_keyspace_costs_one_class_not_forty_thousand(monkeypatch):
    """THE GUARD (#1807 acceptance 3).

    58,000 keys of the exact shape that took the endpoint down. On the code
    that shipped the bug this issues ~58,000 MEMORY USAGE calls and ~58,000
    TTLs; the assertion below is what fails, deterministically, with no clock
    involved.
    """
    keys = [f"interestingness:{i}" for i in range(58_000)]
    fake = _PagingFakeRedis(keys)

    out = await _census(monkeypatch, fake)

    assert out["verdict"] == "complete"
    assert out["scanned"] == 58_000
    assert out["cost"]["classes_seen"] == 1
    row = next(c for c in out["classes"] if c["class"] == "interestingness:*")
    assert row["keys"] == 58_000
    # The bound that was missing: expensive work is capped by the class count.
    assert out["cost"]["sample_ops"] <= 12
    assert fake.memory_usage_calls <= 12
    assert fake.ttl_calls <= 12


@pytest.mark.asyncio
async def test_a_pathological_class_explosion_still_stops_at_the_budget(monkeypatch):
    """Belt and braces: if some future keyspace defeats the fold anyway, the
    global sample budget — not the class count — is what keeps the endpoint
    inside the router timeout.

    **Contract amended 2026-08-13 (LAT-P048).** This test previously asserted
    ``verdict == "complete"`` on the same line as ``sample_budget_exhausted is
    True``, which contract-LOCKED the false green Codex later found: it made
    "the census stopped ranking after 500 of 20,000 classes" and "the census
    finished" the same answer, and any fix would have had to break this test to
    land. The budget still bounds the work — that is what this test is for —
    but the verdict now says the sampling was cut short.
    """
    keys = [f"weird{i}:thing{i}" for i in range(20_000)]
    fake = _PagingFakeRedis(keys)

    out = await _census(monkeypatch, fake, sample_budget=500)

    assert out["verdict"] == "partial"
    assert out["partial_reason"] == "sample_budget"
    assert out["scanned"] == 20_000
    assert out["cost"]["sample_ops"] == 500
    assert out["cost"]["sample_budget_exhausted"] is True
    assert fake.memory_usage_calls == 500


@pytest.mark.asyncio
async def test_unsampled_classes_say_so_instead_of_estimating_zero(monkeypatch):
    keys = [f"fam{i}:x" for i in range(50)]
    out = await _census(monkeypatch, _PagingFakeRedis(keys), sample_budget=0)

    assert out["cost"]["sample_ops"] == 0
    assert all(c["est_basis"] == "unsampled" for c in out["classes"])
    assert all(c["est_total_bytes"] == 0 for c in out["classes"])
    # Zero bytes must not be readable as "measured and found empty".
    assert all(c["sampled"] == 0 for c in out["classes"])


# ---------------------------------------------------------------------------
# The verdict — a bound that is hit must be reported, never timed out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_census_says_complete(monkeypatch):
    out = await _census(monkeypatch, _PagingFakeRedis([f"a:{i}" for i in range(1200)]))

    assert out["verdict"] == "complete"
    assert out["truncated"] is False
    assert out["truncated_reason"] is None
    assert out["coverage_pct"] == 100.0


@pytest.mark.asyncio
async def test_scan_limit_truncation_is_named(monkeypatch):
    keys = [f"a:{i}" for i in range(10_000)]
    out = await _census(monkeypatch, _PagingFakeRedis(keys), scan_limit=1000)

    assert out["verdict"] == "truncated"
    assert out["truncated"] is True
    assert out["truncated_reason"] == "scan_limit"
    assert out["scanned"] < 10_000
    assert out["coverage_pct"] < 100.0


@pytest.mark.asyncio
async def test_deadline_truncation_is_named_and_does_not_503(monkeypatch):
    """The deadline runs off an injected counter, never the wall clock.

    gotcha #44: a test that reads the real clock to prove a timeout fires is a
    test that will one day fire on its own.

    **Rewritten 2026-08-13 (LAT-P048) onto ``_ClockedFakeRedis``.** It used to
    drive a hand-written ``ticks`` iterator, which was fragile in a way that
    mattered: the script assumed the clock is read once per PAGE, so it encoded
    the very page-boundary behaviour that turned out to be the bug. Moving the
    checks per-key exhausted the iterator. Time is now spent by the sampling
    that actually costs it, so this test no longer has an opinion about WHERE
    the endpoint chooses to look at the clock — only that it stops when the
    budget of seconds is gone.
    """
    clock = _Clock()
    monkeypatch.setattr(mod, "_census_clock", clock)

    # One class, so per-class sampling stops after 12 keys and the remaining
    # time is spent scanning — a MANY CHEAP PAGES shape, deliberately the
    # opposite of the slow-terminal-page specimen below.
    keys = [f"a:{i}" for i in range(10_000)]
    fake = _ClockedFakeRedis(keys, clock=clock, cost_s=0.6)
    out = await _census(monkeypatch, fake, deadline_s=12.0)

    assert out["verdict"] == "truncated"
    assert out["truncated_reason"] == "deadline"
    # It answered with what it had rather than burning the router timeout.
    assert out["scanned"] > 0
    assert out["scanned"] < 10_000
    assert 0 < out["coverage_pct"] < 100.0
    assert out["classes"]


@pytest.mark.asyncio
async def test_an_unreachable_redis_does_not_read_as_an_empty_keyspace(monkeypatch):
    """gotcha #53 in its purest form: two different facts, two different bodies."""
    dead = await _census(monkeypatch, _DeadRedis())
    empty = await _census(monkeypatch, _PagingFakeRedis([]))

    assert dead["verdict"] == "error"
    assert "error" in dead
    assert empty["verdict"] == "complete"
    assert "error" not in empty
    assert empty["classes"] == []
    # The distinguishing field must be the verdict, not the absence of rows —
    # both bodies have zero classes.
    assert dead.get("classes", []) == []
    assert dead["verdict"] != empty["verdict"]


@pytest.mark.asyncio
async def test_default_call_covers_the_current_production_keyspace(monkeypatch):
    """#1807 acceptance 1: no query-string tuning required.

    The default `scan_limit` was 20,000 against a 57,871-key keyspace, so the
    default call could not have covered it even after the cost fix.
    """
    import inspect

    sig = inspect.signature(mod.redis_census)
    assert sig.parameters["scan_limit"].default.default >= 200_000
    assert sig.parameters["deadline_s"].default.default <= 25.0

    keys = [f"interestingness:{i}" for i in range(57_871)]
    keys += [f"celery-task-meta-{i:032x}" for i in range(2_000)]
    out = await _census(monkeypatch, _PagingFakeRedis(keys))

    assert out["verdict"] == "complete"
    assert out["scanned"] == 59_871
    assert out["coverage_pct"] == 100.0


# ---------------------------------------------------------------------------
# The terminal page and the budget — two ways a bounded rail said "complete"
# about work it had not done. Both found by a Codex post-merge audit of #1807,
# 2026-08-13, and both invisible to the 20 tests above.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_slow_terminal_page_cannot_report_complete_after_the_deadline(monkeypatch):
    """THE GUARD. One page, 500 classes, every key sampled, 50 ms per call.

    The bug: the loop checked ``cursor == 0`` and broke BEFORE it consulted
    either the scan limit or the deadline, so the LAST page — which for any
    keyspace under 500 keys is the only page — was exempt from both bounds.
    Every sample in it had already been paid for by the time the break ran.

    Measured on the unfixed endpoint: **50.0 simulated seconds** against
    ``deadline_s=12``, 500 MEMORY + 500 TTL round trips, and a returned
    ``verdict="complete"`` with ``truncated_reason=None``. That is the exact
    failure the verdict field exists to make impossible — a rail built so a
    census "must never 503" burning past Heroku's 30 s router deadline and
    then calling the result complete.
    """
    clock = _Clock()
    monkeypatch.setattr(mod, "_census_clock", clock)
    # 500 distinct classes so the per-class quota never throttles sampling.
    keys = [f"fam{i}:key{i}" for i in range(500)]
    fake = _ClockedFakeRedis(keys, clock=clock, cost_s=0.05)

    out = await _census(monkeypatch, fake, deadline_s=12.0)

    assert out["verdict"] == "truncated"
    assert out["truncated"] is True
    assert out["truncated_reason"] == "deadline"
    # It stopped ON the deadline, not after four times it.
    assert clock.t < 13.0, f"spent {clock.t}s against a 12s deadline"
    # Overshoot is bounded to ONE key's work, not one page's.
    assert clock.t <= 12.0 + 2 * 0.05
    # It answered with what it had, and said so honestly.
    assert 0 < out["scanned"] < 500
    assert 0 < out["coverage_pct"] < 100.0
    assert out["classes"]


@pytest.mark.asyncio
async def test_the_terminal_page_honours_the_scan_limit_too(monkeypatch):
    """The same exemption, reached by the other bound and with no clock at all.

    A 300-key single-page keyspace with ``scan_limit=100`` returned
    ``complete``, ``scanned=300``, ``coverage_pct=100.0`` — three times the
    ceiling it was given, reported as full coverage.
    """
    keys = [f"fam{i}:key{i}" for i in range(300)]

    out = await _census(monkeypatch, _PagingFakeRedis(keys), scan_limit=100)

    assert out["verdict"] == "truncated"
    assert out["truncated_reason"] == "scan_limit"
    assert out["scanned"] == 100
    assert out["coverage_pct"] < 100.0


@pytest.mark.asyncio
async def test_exhausting_the_sample_budget_is_not_a_complete_census(monkeypatch):
    """A census that ranked 10 classes out of 1,000 has not finished ranking.

    ``sample_budget_exhausted`` was recorded in ``cost`` but could not move the
    top-level verdict — only scan-limit and deadline truncation could. So the
    headline field read ``complete`` while 990 classes were never sampled and
    therefore estimate as **zero bytes**, on an endpoint whose entire purpose
    is ranking classes BY bytes. The live-proof acceptance for #1807 reads that
    headline.

    ``partial`` is deliberately a third value rather than ``truncated``:
    coverage genuinely IS complete — every key was scanned and counted — so
    calling it truncated would be its own false statement. What stopped early
    is the sampling, and the verdict now says which (gotcha #53: three
    different facts, three different bodies).
    """
    keys = [f"fam{i}:key{i}" for i in range(1_000)]

    out = await _census(monkeypatch, _PagingFakeRedis(keys), sample_budget=10)

    assert out["verdict"] == "partial"
    assert out["partial_reason"] == "sample_budget"
    assert out["cost"]["sample_budget_exhausted"] is True
    assert out["cost"]["sample_ops"] == 10
    # Coverage is real and must not be understated either.
    assert out["truncated"] is False
    assert out["scanned"] == 1_000
    assert out["coverage_pct"] == 100.0
    # 990 of the 1,000 classes were never sampled. The response caps the class
    # list at 60, so the debt is asserted where it is actually visible: the
    # class count, the omitted count, and every returned unsampled row saying
    # so rather than estimating zero bytes.
    assert out["cost"]["classes_seen"] == 1_000
    assert out["classes_omitted"] == 1_000 - len(out["classes"])
    unsampled = [c for c in out["classes"] if c["sampled"] == 0]
    assert len(unsampled) >= 50
    assert all(c["est_basis"] == "unsampled" for c in unsampled)
    assert all(c["est_total_bytes"] == 0 for c in unsampled)


@pytest.mark.asyncio
async def test_truncated_outranks_partial_when_both_bounds_are_hit(monkeypatch):
    """One verdict field, so the stronger statement has to win.

    Incomplete COVERAGE subsumes incomplete sampling: if the scan stopped
    early, saying "partial" would understate what was missed.
    """
    keys = [f"fam{i}:key{i}" for i in range(1_000)]

    out = await _census(monkeypatch, _PagingFakeRedis(keys),
                        scan_limit=100, sample_budget=5)

    assert out["verdict"] == "truncated"
    assert out["truncated_reason"] == "scan_limit"
    # The weaker fact is still reported, just not as the headline.
    assert out["cost"]["sample_budget_exhausted"] is True


@pytest.mark.asyncio
async def test_a_fast_terminal_page_inside_both_bounds_is_still_complete(monkeypatch):
    """The control. Charging for sampling must not make everything truncated.

    Without this, the two fixes above could be 'passing' because the endpoint
    now reports truncation unconditionally.
    """
    clock = _Clock()
    monkeypatch.setattr(mod, "_census_clock", clock)
    keys = [f"fam{i}:key{i}" for i in range(200)]
    fake = _ClockedFakeRedis(keys, clock=clock, cost_s=0.001)

    out = await _census(monkeypatch, fake, deadline_s=12.0)

    assert out["verdict"] == "complete"
    assert out["truncated"] is False
    assert out["truncated_reason"] is None
    assert out["scanned"] == 200
    assert out["coverage_pct"] == 100.0
    assert clock.t < 12.0
