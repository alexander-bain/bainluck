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
    inside the router timeout."""
    keys = [f"weird{i}:thing{i}" for i in range(20_000)]
    fake = _PagingFakeRedis(keys)

    out = await _census(monkeypatch, fake, sample_budget=500)

    assert out["verdict"] == "complete"
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
    """
    ticks = iter([0.0, 0.5, 99.0] + [199.0] * 50)
    monkeypatch.setattr(mod, "_census_clock", lambda: next(ticks))

    keys = [f"a:{i}" for i in range(10_000)]
    out = await _census(monkeypatch, _PagingFakeRedis(keys), deadline_s=12.0)

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
