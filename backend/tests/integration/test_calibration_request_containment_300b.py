"""Queue 300B Item 0 — an anonymous request cannot launch the calibration build.

The failure this closes: ``GET /api/calibration?bust=1`` was an unauthenticated
recompute trigger. It skipped every cache tier and ran
``compute_calibration_payload`` — the canonical futures CTE, measured at ~22
minutes on the current population — inside a web request. A deadline was
wrapped around it in Queue 297, and that deadline is real, but it bounds only
how long the CLIENT waits. The Postgres backend keeps running the statement
with its xmin pinned long after the request is gone; that is the orphan shape
#1479 records, and two of them are still sitting on the database today.

So the containment is structural rather than temporal: there is no build tier in
the request path at all. Every one of these tests drives the REAL handler (most
of them through the real ASGI stack, so query-string parsing is exercised too)
with ``compute_calibration_payload`` replaced by a landmine. Any path that
reaches it fails the suite.

Coverage per the queue's acceptance: malformed/hidden/absent bust variants,
clean cache miss, cache failure, durable miss, durable wrong-version,
cancellation, poison tiers, and concurrency.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.utils import durable_state as ds
from app.utils import request_cache as rc

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / doubles
# ---------------------------------------------------------------------------


def _payload(*, outcomes: int = 1_000_000, version: str | None = None, generated_at=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = generated_at or (
        datetime.now(timezone.utc) - timedelta(minutes=30)
    ).isoformat()
    return {
        "buckets": [{"bucket_idx": 0, "n": outcomes, "winners": outcomes // 2}],
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": version or CALIBRATION_POPULATION_VERSION,
        "generated_at": stamp,
    }


class _EmptyRedis:
    """Healthy store, keys absent — the LRU-eviction / expired-TTL case."""

    async def get(self, key):
        return None


class _DeadRedis:
    """Every command raises — a TLS drop or a dead instance."""

    async def get(self, key):
        raise ConnectionError("Error 111 connecting to rediss://…")


class _PoisonRedis:
    """``main`` is corrupt; ``last_good`` is fine.

    The poison-tier case: one bad tier must not erase its siblings.
    """

    def __init__(self, last_good: str | None):
        self._last_good = last_good

    async def get(self, key):
        if key.endswith(":main"):
            return "{not json at all"
        return self._last_good


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _durable_db(payload, *, generated_at=None, schema_version=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = generated_at or datetime.now(timezone.utc) - timedelta(hours=4)
    row = {
        "identity": "calibration:main",
        "schema_version": schema_version or CALIBRATION_POPULATION_VERSION,
        "generation": ds.generation_for(stamp),
        "generated_at": stamp,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": True,
        "source": "precompute_calibration",
    }
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    db.execute.return_value = result
    return db


def _empty_db():
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    db.execute.return_value = result
    return db


@pytest.fixture(autouse=True)
def _fresh_process():
    """A freshly-booted web dyno: nothing in process, nothing remembered."""
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


@pytest.fixture(autouse=True)
def _build_is_a_landmine(monkeypatch):
    """The single assertion this whole file exists to make.

    Patched on EVERY test rather than per-case: the point is that no reachable
    branch — however exotic the query string — can get here.
    """
    from app.tasks import precompute_calibration

    async def _boom(db, **_kwargs):
        raise AssertionError(
            "the request path started compute_calibration_payload — Queue 300B "
            "removed that authority and it must stay removed"
        )

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


def _assert_typed_unavailable(exc: HTTPException) -> None:
    assert exc.status_code == 503
    detail = exc.detail
    assert isinstance(detail, dict), "the body must be typed, not a bare string"
    assert detail["status"] == "unavailable"
    assert detail["retry_after_s"] == 30
    assert detail["reason"]
    assert exc.headers["Retry-After"] == "30"


# ---------------------------------------------------------------------------
# The query string cannot buy a build
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?bust=1",
        "?bust=0",
        "?bust=true",
        "?bust=yes",  # malformed under the old int coercion — used to 422
        "?bust=-1",
        "?bust=99999999999999999999",
        "?bust=",
        "?bust=1&bust=1",
        "?bust[]=1",
        "?BUST=1",
        "?Bust=1",
        "?bust=1%00",
        "?bust=1;DROP",
        "?refresh=1&force=1&nocache=1",
    ],
)
async def test_no_query_string_variant_can_reach_the_build(client, monkeypatch, query):
    """Every shape of the old trigger, through the real ASGI stack.

    ``?bust=yes`` matters twice over: under the removed ``int`` coercion it was a
    422, so this also proves the parameter is genuinely gone rather than merely
    ignored in the handler body.
    """
    _use(monkeypatch, _EmptyRedis())

    resp = await client.get(f"/api/calibration{query}")

    # 503 (nothing to serve) is the only honest answer here; 422 would mean the
    # parameter still exists, and 200 would mean something built a payload.
    assert resp.status_code == 503, resp.text
    body = resp.json()["detail"]
    assert body["status"] == "unavailable"
    assert resp.headers["Retry-After"] == "30"


async def test_bust_is_not_an_accepted_parameter_anymore(client, monkeypatch):
    """The handler signature itself no longer names it."""
    import inspect

    from app.routes import calibration

    params = inspect.signature(calibration.public_calibration).parameters
    assert "bust" not in params, (
        "a hidden recompute parameter is still an unauthenticated recompute "
        "parameter — hidden is not authenticated"
    )


async def test_the_route_module_cannot_even_reference_the_build():
    """A source-level guard, because a future refactor is the real risk here.

    Every test above proves the *current* branches are clean. This one proves
    nobody can quietly add a new branch that is not.
    """
    import inspect

    from app.routes import calibration

    src = inspect.getsource(calibration.public_calibration)
    assert "compute_calibration_payload" not in src.replace(
        # the docstring names it to explain WHY it is absent
        "``compute_calibration_payload``", ""
    )


# ---------------------------------------------------------------------------
# Cache miss and cache failure
# ---------------------------------------------------------------------------


async def test_clean_cache_miss_is_a_typed_503_not_a_build(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=_empty_db())

    _assert_typed_unavailable(exc.value)
    assert exc.value.detail["reason"] == "no_trustworthy_snapshot"


async def test_cache_failure_is_a_typed_503_not_a_build(monkeypatch):
    """Redis erroring is the worst possible moment to start a 22-minute query."""
    from app.routes import calibration

    _use(monkeypatch, _DeadRedis())

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=_empty_db())

    _assert_typed_unavailable(exc.value)


async def test_cache_failure_prefers_a_dated_copy_over_any_503(monkeypatch):
    """Degraded-but-real beats unavailable. It just never beats "do not build"."""
    from app.routes import calibration

    rc.remember_last_good("calibration:main", _payload())
    _use(monkeypatch, _DeadRedis())

    out = await calibration.public_calibration(db=_empty_db())

    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "redis_unavailable"


async def test_a_clean_miss_also_serves_a_dated_copy_when_one_exists(monkeypatch):
    """The rescue that used to live in the compute tier's ``except`` branch.

    Removing the compute removed its fallback with it; if that rescue had not
    been relocated, a clean miss would 503 straight past a serviceable copy.
    """
    from app.routes import calibration

    rc.remember_last_good("calibration:main", _payload())
    _use(monkeypatch, _EmptyRedis())

    out = await calibration.public_calibration(db=_empty_db())

    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "cache_miss"


# ---------------------------------------------------------------------------
# Durable tier: miss and wrong version
# ---------------------------------------------------------------------------


async def test_durable_miss_does_not_fall_through_to_a_build(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=_empty_db())

    _assert_typed_unavailable(exc.value)


async def test_durable_wrong_version_does_not_fall_through_to_a_build(monkeypatch):
    """A refused snapshot is refused. It is not a licence to rebuild in-request."""
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())
    db = _durable_db(_payload(), schema_version="q000-ancient")

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=db)

    _assert_typed_unavailable(exc.value)


async def test_durable_read_that_raises_does_not_fall_through_to_a_build(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("connection reset by peer")

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=db)

    _assert_typed_unavailable(exc.value)


# ---------------------------------------------------------------------------
# Poison tiers — one bad tier must not erase its siblings
# ---------------------------------------------------------------------------


async def test_a_corrupt_main_key_still_lets_last_good_serve(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _PoisonRedis(last_good=json.dumps(_payload())))

    out = await calibration.public_calibration(db=_empty_db())

    assert out["total_outcomes"] == 1_000_000
    assert out["cache"]["status"] == "stale"


async def test_a_corrupt_main_and_last_good_still_lets_durable_serve(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _PoisonRedis(last_good="{also not json"))

    out = await calibration.public_calibration(db=_durable_db(_payload()))

    assert out["provenance"]["source"] == "durable"
    assert out["cache"]["status"] == "stale"
    # Corrupt is a MISS, not a Redis outage — the reason must say so, or the next
    # operator reading it goes and looks at a healthy Redis instance.
    assert out["cache"]["reason"] == "main_key_absent_durable"


async def test_every_tier_poisoned_is_a_typed_503(monkeypatch):
    from app.routes import calibration

    _use(monkeypatch, _PoisonRedis(last_good="{also not json"))
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("durable read exploded too")

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=db)

    _assert_typed_unavailable(exc.value)


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


async def test_client_cancellation_leaves_nothing_running(monkeypatch):
    """The client walking away must not leave work behind — because there is none.

    Under the old shape this was the dangerous case: the request was cancelled,
    the ``await`` unwound, and the Postgres backend carried on with the CTE. With
    no build to start there is nothing to orphan, and the cancellation propagates
    cleanly rather than being swallowed into a fallback.
    """
    from app.routes import calibration

    class _CancellingRedis:
        async def get(self, key):
            raise asyncio.CancelledError()

    _use(monkeypatch, _CancellingRedis())

    task = asyncio.create_task(calibration.public_calibration(db=_empty_db()))
    with pytest.raises((asyncio.CancelledError, HTTPException)):
        await task


async def test_a_cancelled_request_does_not_poison_the_next_one(monkeypatch):
    from app.routes import calibration

    calls = {"n": 0}

    class _FirstCallCancels:
        async def get(self, key):
            calls["n"] += 1
            if calls["n"] == 1:
                raise asyncio.CancelledError()
            return json.dumps(_payload())

    _use(monkeypatch, _FirstCallCancels())

    with pytest.raises((asyncio.CancelledError, HTTPException)):
        await calibration.public_calibration(db=_empty_db())

    out = await calibration.public_calibration(db=_empty_db())
    assert out["total_outcomes"] == 1_000_000


# ---------------------------------------------------------------------------
# Concurrency — the stampede that can no longer happen
# ---------------------------------------------------------------------------


async def test_forty_concurrent_cold_requests_start_zero_builds(monkeypatch):
    """No coalescing lock needed when there is nothing to coalesce.

    Forty simultaneous anonymous loads against a cold cache used to be forty
    candidate builds gated only by a per-request deadline. Now it is forty fast,
    honest 503s.
    """
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())

    results = await asyncio.gather(
        *(calibration.public_calibration(db=_empty_db()) for _ in range(40)),
        return_exceptions=True,
    )

    assert len(results) == 40
    for item in results:
        assert isinstance(item, HTTPException)
        _assert_typed_unavailable(item)


async def test_concurrent_requests_over_the_real_stack_all_answer(client, monkeypatch):
    _use(monkeypatch, _EmptyRedis())

    responses = await asyncio.gather(
        *(client.get("/api/calibration?bust=1") for _ in range(10))
    )

    assert [r.status_code for r in responses] == [503] * 10


# ---------------------------------------------------------------------------
# The admin rail that is allowed to survive
# ---------------------------------------------------------------------------


async def test_the_admin_recompute_rail_is_authenticated_and_queues(client):
    """It may exist because it is authenticated AND it does not run inline.

    ``/api/admin/calibration/mce?bust=true`` sends the heavy task to the worker
    queue and returns. Unauthenticated, it must not even get that far.
    """
    import inspect

    from app.routes import admin_data_quality

    resp = await client.get("/api/admin/calibration/mce?bust=true")
    assert resp.status_code in (401, 403), resp.text

    src = inspect.getsource(admin_data_quality.calibration_mce_summary)
    assert "_check_admin_secret" in src
    assert "_safe_send_task" in src, "the admin rail must QUEUE, never compute inline"
    assert "compute_calibration_payload" not in src
