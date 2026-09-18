"""GATE for LAT-P225 (#2143 residual) — a cross-worker failure must NAME its
cause, and an eleventh cause must not be able to arrive unnamed.

## The ship

A reader opens Discover on a web worker whose cross-worker read just failed, and
waits for `market_load` to be rebuilt — 692-775 ms of a cold build — instead of
being handed the copy another worker already published. `cross_worker_failures`
has counted exactly that event since LAT-P103 and could never say why it
happened, so nobody could fix it.

## Why this is a gate and not a nice-to-have

Measured on production through `/api/admin/shared-build-stats`, 2026-09-18
02:50-03:01Z, 54 samples across two web workers:

    pid 11 (busy)   cross_worker_hits 25->31  misses 16->20  FAILURES 0 -> 0
    pid 10 (quiet)  cross_worker_hits 12->14  misses  8->10  FAILURES 4 -> 5

Still accruing, and worker-asymmetric: ~1 in 6 of the quiet worker's reads
failed while 51 reads on the busy worker failed none. The ten events behind that
one number have opposite remedies — a stall says widen the deadline or shrink
the artifact, a connection error on an idle worker says retry once, a malformed
envelope says a writer and a reader disagree about the wire. Choosing between
them from `cross_worker_failures` alone is not possible, and that is the defect.

The information was never missing, only discarded: `RedisResult` already carries
`TIMEOUT` and `ERROR` as separate states, and the envelope branches are four
distinct `if`s.

## What these tests deliberately do NOT assert

Not a duration, and not a failure RATE. The first is a flake generator (LAT-P084)
and the second is a property of production, not of this module. These assert
attribution, arithmetic agreement with the counter they refine, and — the one
that matters in a year — that a new failure branch cannot be counted without
naming itself.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.utils import principal_independent_cache as pic
from app.utils import request_cache as _rc


class _FakeRedis:
    """Stage tier only, with per-call failure injection.

    `fail_get` / `fail_set` raise or stall on demand so each failure BRANCH can
    be reached the way production reaches it — through `bounded_redis_call` —
    rather than by calling the counter directly, which would assert nothing
    about the call sites.
    """

    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.get_error: BaseException | None = None
        self.set_error: BaseException | None = None

    def _stage_key(self, key: str) -> bool:
        return str(key).startswith(pic.REDIS_KEY_PREFIX)

    async def get(self, key):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        if self.get_error is not None:
            raise self.get_error
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        if self.set_error is not None:
            raise self.set_error
        self.store[key] = value
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    return fake


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


async def _build_small():
    return {"ok": 1}


def _reasons(namespace: str) -> dict[str, int]:
    return pic.shared_build_stats()["failure_reasons"].get(namespace, {})


# --------------------------------------------------------------------------
# THE HEADLINE GATE — a cause cannot arrive unnamed
# --------------------------------------------------------------------------


def test_no_failure_can_be_counted_without_naming_its_cause():
    """THE gate, and the only one that still holds in a year.

    Every other test here checks a branch that exists TODAY. This one checks the
    branch somebody adds next: `cross_worker_failures` may be incremented in
    exactly one place — inside `_bump_failure`, which refuses an unknown reason —
    so a new failure path cannot reach the fused counter while skipping the named
    one. Read off this module's own source, because the property is structural
    and no runtime scenario can demonstrate the absence of a future call site.
    """
    source = inspect.getsource(pic)
    tree = ast.parse(source)

    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "_bump"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == "cross_worker_failures":
                offenders.append(node.lineno)

    # One legitimate site: the call inside `_bump_failure` itself.
    bump_failure_lines = {
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_bump_failure"
    }
    assert bump_failure_lines, "_bump_failure has gone — this gate is now vacuous"
    start = min(bump_failure_lines)
    outside = [line for line in offenders if line < start]

    assert offenders, (
        "no `_bump(..., 'cross_worker_failures')` call exists at all — either the "
        "counter was renamed or this gate stopped reading the real source"
    )
    assert not outside, (
        "a cross-worker failure is counted outside `_bump_failure` at line(s) "
        f"{outside} — that event will be invisible in `failure_reasons` and the "
        "operator is back to one number meaning ten things"
    )


# --------------------------------------------------------------------------
# The branches that exist today, each reached the way production reaches it
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_read_that_raises_is_named_an_error_not_a_stall(fake_redis):
    """A connection error and a timeout are the two states `is_failure` folds,
    and they are the two remedies. Injected as a real exception through
    `bounded_redis_call`, not by calling the counter."""
    fake_redis.get_error = ConnectionError("connection reset by peer")

    await pic.get_or_build("market_load", ("k", (), 1), _build_small)

    assert _reasons("market_load").get(pic.FAIL_READ_ERROR) == 1
    assert pic.FAIL_READ_TIMEOUT not in _reasons("market_load"), (
        "a connection error was filed as a stall — the two have opposite fixes"
    )


@pytest.mark.asyncio
async def test_a_read_that_stalls_is_named_a_stall(fake_redis, monkeypatch):
    """The deadline is what turns a slow Redis into a rebuilt artifact, so the
    stall has to be distinguishable from an error by name."""
    import asyncio

    async def _stall():
        await asyncio.sleep(10)

    monkeypatch.setattr(pic, "REDIS_READ_DEADLINE_MS", 5)

    async def _slow_get(key):
        await _stall()

    fake_redis.get = _slow_get  # type: ignore[method-assign]

    await pic.get_or_build("concepts", ("k", (), 1), _build_small)

    assert _reasons("concepts").get(pic.FAIL_READ_TIMEOUT) == 1
    assert pic.FAIL_READ_ERROR not in _reasons("concepts")


@pytest.mark.asyncio
async def test_a_foreign_entry_is_named_as_a_wire_failure_not_a_stall(fake_redis):
    """A predecessor's uncompressed JSON, another lane's typo, a truncated
    write: `wire_decode` returns None for all of them and the reader rebuilds.
    That is a writer/reader disagreement, not a network event."""
    key = ("k", (), 1)
    fake_redis.store[pic.redis_key_for("concepts", key)] = b"not-our-wire-form"

    await pic.get_or_build("concepts", key, _build_small)

    assert _reasons("concepts").get(pic.FAIL_UNDECODABLE_WIRE) == 1


@pytest.mark.asyncio
async def test_a_publish_failure_is_named_apart_from_a_read_failure(fake_redis):
    """A worker that reads fine and cannot PUBLISH starves every OTHER worker
    while looking healthy from its own side. Today both are one number."""
    fake_redis.set_error = ConnectionError("connection reset by peer")

    await pic.get_or_build("canonical_counts", ("k", (), 1), _build_small)

    reasons = _reasons("canonical_counts")
    assert reasons.get(pic.FAIL_PUBLISH_ERROR) == 1
    assert pic.FAIL_READ_ERROR not in reasons, (
        "a publish failure was filed as a read failure — the read side was fine"
    )


# --------------------------------------------------------------------------
# The two views must agree, and the finer one must not leak
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_named_causes_sum_to_the_counter_they_refine(fake_redis):
    """`failure_reasons` is a finer reading of the SAME events, never a second
    tally that can drift. Per namespace and in aggregate."""
    fake_redis.get_error = ConnectionError("boom")
    await pic.get_or_build("market_load", ("a", (), 1), _build_small)
    await pic.get_or_build("concepts", ("b", (), 1), _build_small)

    stats = pic.shared_build_stats()
    by_ns = stats["by_namespace"]
    by_reason = stats["failure_reasons"]

    assert stats["cross_worker_failures"] >= 2, "the scenario produced no failures"
    for ns, counters in by_ns.items():
        assert sum(by_reason.get(ns, {}).values()) == counters.get(
            "cross_worker_failures", 0
        ), f"{ns}: named causes and the fused counter disagree"

    assert sum(
        sum(r.values()) for r in by_reason.values()
    ) == stats["cross_worker_failures"]


@pytest.mark.asyncio
async def test_a_worker_boundary_resets_the_named_causes_too(fake_redis):
    """A cold worker starts with cold counters on every view, or the views
    disagree about the same worker boundary."""
    fake_redis.get_error = ConnectionError("boom")
    await pic.get_or_build("concepts", ("a", (), 1), _build_small)
    assert pic.shared_build_stats()["failure_reasons"], "nothing was recorded to reset"

    pic.clear_shared_builds()

    assert pic.shared_build_stats()["failure_reasons"] == {}


@pytest.mark.asyncio
async def test_the_reason_view_is_bounded_by_the_same_namespace_cap(
    fake_redis, monkeypatch
):
    """A per-namespace dict in a process that lives for days is a leak unless it
    is bounded — and it must fold into the SAME overflow bucket as
    `by_namespace`, or one event is filed under two different artifact names."""
    monkeypatch.setattr(pic, "MAX_TRACKED_NAMESPACES", 4)
    fake_redis.get_error = ConnectionError("boom")

    for i in range(20):
        await pic.get_or_build(f"ns{i}", ("k", (), 1), _build_small)

    stats = pic.shared_build_stats()
    by_reason = stats["failure_reasons"]

    assert len(by_reason) <= 5, f"unbounded reason tracking: {len(by_reason)} buckets"
    assert pic._NS_OVERFLOW_BUCKET in by_reason, "overflow causes were dropped"
    assert set(by_reason) <= set(stats["by_namespace"]), (
        "a cause is filed under a namespace the counter view never heard of — "
        "the two views fold over-cap namespaces differently"
    )
    assert (
        sum(sum(r.values()) for r in by_reason.values())
        == stats["cross_worker_failures"]
        == 20
    )


@pytest.mark.asyncio
async def test_production_can_read_the_named_cause(fake_redis, monkeypatch):
    """A counter with no reader is not an instrument (LAT-P223's lesson, one
    level down). The cause has to arrive at the same endpoint the fused counter
    does, already summed — an operator reading a nested dict by eye is how
    LAT-P221's refusal stayed invisible beside a healthy-looking aggregate."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.routes import admin as admin_routes

    monkeypatch.setattr(admin_routes, "_check_admin_secret", lambda *a, **k: None)
    fake_redis.get_error = ConnectionError("connection reset by peer")

    await pic.get_or_build("market_load", ("k", (), 1), _build_small)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/shared-build-stats")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["failure_reasons_total"] == {pic.FAIL_READ_ERROR: 1}
    assert body["stats"]["failure_reasons"]["market_load"] == {pic.FAIL_READ_ERROR: 1}
    # The vocabulary travels with the reading, so an operator can tell "this
    # cause never fired" from "this cause does not exist".
    assert pic.FAIL_PUBLISH_TIMEOUT in body["known_failure_reasons"]


def test_an_unknown_reason_is_refused_rather_than_silently_counted():
    """The allowlist has a real default only if a miss RAISES. A miss that
    stored the string would let a typo mint a reason nobody reads."""
    with pytest.raises(ValueError):
        pic._bump_failure("concepts", "a-reason-nobody-declared")

    assert pic.shared_build_stats()["cross_worker_failures"] == 0, (
        "the refused reason still incremented the fused counter"
    )
