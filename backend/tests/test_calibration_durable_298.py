"""Queue 298 Item 2 — /api/calibration survives losing Redis entirely (#1512).

Queue 297 made the route fail HONESTLY. It could not make it stay UP, because
every tier it could fall back to lived in the same 50MB allkeys-lru Redis:
``main`` (2h), ``last_good`` (7d, but LRU does not care about TTL), and a
process-local copy that a freshly-booted dyno does not have. Lose Redis and all
three vanish at once, leaving a ~9s cold compute as the only option — the path
that produced "Failed to load calibration data" on Alex's anonymous load.

The durable row is the tier that does not vanish. These tests drive the real
``public_calibration`` handler, so they prove the branch structure rather than a
mock of it: a FRESH process (no in-process cache) with Redis unavailable must
still answer, dated and marked, without paying the cold compute.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.utils import durable_state as ds
from app.utils import request_cache as rc

pytestmark = pytest.mark.asyncio


def _at(*, days_ago: float = 0.0) -> str:
    """A stable stamp N days back that is ALWAYS in the past.

    Deliberately not the ``.replace(hour=12)`` idiom used elsewhere: anchoring to
    a fixed hour of *today* produces a FUTURE timestamp whenever the suite runs
    before that hour, and this boundary rejects future stamps outright (clock
    skew must surface, not be clamped). CI runs at ~00:0x UTC and caught it.
    Truncating to the hour keeps it deterministic within a run.
    """
    base = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return (base - timedelta(days=days_ago)).isoformat()


def _payload(*, outcomes: int = 1_000_000, version: str | None = None, generated_at=None):
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

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
        "generated_at": generated_at or _at(days_ago=0.05),
    }


class _DeadRedis:
    """Every command fails — a TLS drop or a dead instance."""

    async def get(self, key):
        raise ConnectionError("Error 111 connecting to rediss://u:pw@host:10819")


class _EmptyRedis:
    """Healthy store, but the keys are gone (the LRU eviction case)."""

    async def get(self, key):
        return None


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _durable_db(payload, *, generated_at=None, schema_version=None, complete=True):
    """A DB session whose durable row holds ``payload``."""
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = generated_at or datetime.now(timezone.utc) - timedelta(hours=5)
    row = {
        "identity": "calibration:main",
        "schema_version": schema_version or CALIBRATION_POPULATION_VERSION,
        "generation": ds.generation_for(stamp),
        "generated_at": stamp,
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": complete,
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
    """Simulate a freshly-booted web dyno: no in-process cache, no last-good."""
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


def _compute_fails(monkeypatch):
    """No usable snapshot anywhere: the cold compute cannot rescue the request.

    Without this the route would fall through to the REAL compute against a mock
    session and return a nonsense payload, hiding the branch under test.
    """
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise RuntimeError("compute unavailable in this test")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


def _no_compute(monkeypatch):
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise AssertionError(
            "the cold compute ran even though a durable snapshot was available"
        )

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


# ---------------------------------------------------------------------------
# The headline case
# ---------------------------------------------------------------------------


async def test_fresh_process_with_redis_dead_serves_the_durable_snapshot(monkeypatch):
    """THE #1512 CASE. No Redis, no process cache — and the page still renders."""
    from app.routes import calibration

    stamp = datetime.now(timezone.utc) - timedelta(hours=5)
    payload = _payload(generated_at=stamp.isoformat())
    _use(monkeypatch, _DeadRedis())
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=_durable_db(payload, generated_at=stamp))

    assert out["total_outcomes"] == 1_000_000
    # Dated and marked — served, but never dressed up as current.
    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "redis_unavailable_durable"
    assert out["provenance"]["source"] == "durable"
    assert out["provenance"]["dated"] is True
    assert out["provenance"]["age_s"] == pytest.approx(5 * 3600, abs=120)


async def test_evicted_keys_serve_the_durable_snapshot(monkeypatch):
    """Redis is alive but LRU threw both keys out — still no cold compute."""
    from app.routes import calibration

    payload = _payload()
    _use(monkeypatch, _EmptyRedis())
    _no_compute(monkeypatch)

    out = await calibration.public_calibration(db=_durable_db(payload))

    assert out["cache"]["reason"] == "main_key_absent_durable"
    assert out["provenance"]["source"] == "durable"


async def test_durable_tier_is_consulted_and_nothing_computes(monkeypatch):
    """Queue 300B: the durable tier is the last resort — there is no compute below it."""
    from app.routes import calibration

    _use(monkeypatch, _EmptyRedis())
    _no_compute(monkeypatch)  # raises if reached

    out = await calibration.public_calibration(db=_durable_db(_payload()))
    assert out["total_outcomes"] == 1_000_000


# ---------------------------------------------------------------------------
# Only a TRUSTWORTHY durable copy may serve
# ---------------------------------------------------------------------------


async def test_an_ancient_durable_copy_is_refused(monkeypatch):
    """Beyond the serve age bound it is not "the calibration curve" any more."""
    from app.routes import calibration
    from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S

    ancient = datetime.now(timezone.utc) - timedelta(seconds=SERVE_MAX_AGE_S + 86400)
    payload = _payload(generated_at=ancient.isoformat())
    _use(monkeypatch, _DeadRedis())
    _compute_fails(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(
            db=_durable_db(payload, generated_at=ancient))
    assert exc.value.status_code == 503


async def test_a_wrong_version_durable_copy_is_refused(monkeypatch):
    """A population the current UI labels cannot describe must not be served."""
    from app.routes import calibration

    payload = _payload(version="q000-ancient")
    _use(monkeypatch, _DeadRedis())
    _compute_fails(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(
            db=_durable_db(payload, schema_version="q000-ancient"))
    assert exc.value.status_code == 503


async def test_a_corrupted_durable_payload_is_refused(monkeypatch):
    """Checksum mismatch = torn write, even though the JSON parses."""
    from app.routes import calibration
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    stamp = datetime.now(timezone.utc) - timedelta(hours=2)
    good = _payload()
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "identity": "calibration:main",
        "schema_version": CALIBRATION_POPULATION_VERSION,
        "generation": ds.generation_for(stamp),
        "generated_at": stamp,
        "payload": good,
        "checksum": "0" * 64,  # does not match the body
        "complete": True,
        "source": "precompute_calibration",
    }
    db.execute.return_value = result
    _use(monkeypatch, _DeadRedis())
    _compute_fails(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=db)
    assert exc.value.status_code == 503


async def test_nothing_anywhere_is_still_a_typed_unavailable(monkeypatch):
    """Queue 297's honest failure survives — we did not trade it away."""
    from app.routes import calibration

    _use(monkeypatch, _DeadRedis())
    _compute_fails(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=_empty_db())
    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "unavailable"


async def test_a_broken_durable_tier_cannot_break_the_route(monkeypatch):
    """A database problem must degrade to the old behavior, not 500."""
    from app.routes import calibration

    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db exploded")
    _use(monkeypatch, _DeadRedis())
    _compute_fails(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=db)
    assert exc.value.status_code == 503


async def test_no_caller_can_skip_the_durable_tier_into_a_recompute(monkeypatch):
    """Queue 300B inverted this test's premise, deliberately.

    It used to assert that ``?bust=1`` skipped the durable tier and forced a
    fresh in-request build. That was the bug: an anonymous query string could
    launch the ~22-minute population CTE, and the request abandoning it did not
    stop the backend. The durable tier is now unskippable and the build tier is
    gone, so the durable copy is what a caller gets — served, dated, and marked.
    """
    from app.routes import calibration
    from app.tasks import precompute_calibration

    async def _boom(db, **_kwargs):
        raise AssertionError("a request started the canonical build")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)
    _use(monkeypatch, _EmptyRedis())

    out = await calibration.public_calibration(db=_durable_db(_payload()))
    assert out["provenance"]["source"] == "durable"
    assert out["cache"]["status"] == "stale"


# ---------------------------------------------------------------------------
# Producer side
# ---------------------------------------------------------------------------


async def test_publisher_writes_durable_before_redis(monkeypatch):
    """Ordering is the contract: volatile must never lead durable."""
    import app.services.durable_snapshots as dsnap
    from app.tasks import precompute_calibration as pc

    order: list[str] = []
    payload = _payload()

    async def _compute(db, **_kwargs):
        return payload

    class _Session:
        async def execute(self, *a, **k):
            return MagicMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    def _task_session():
        return _Session()

    async def _durable(envelope):
        order.append("durable")
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    rc_mock = MagicMock()
    rc_mock.set.side_effect = lambda *a, **k: order.append("volatile")

    monkeypatch.setattr(pc, "compute_calibration_payload", _compute)
    monkeypatch.setattr("app.tasks.base.get_task_session", _task_session)
    monkeypatch.setattr(dsnap, "publish_snapshot_standalone", _durable)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc_mock)
    monkeypatch.setattr(pc, "_read_published_baseline", lambda _rc: None)

    summary = await pc._precompute_calibration_main()

    assert order[0] == "durable", "the survivor must be written first"
    assert "volatile" in order
    assert summary["publication"]["success"] is True
    assert summary["publish"]["durable"] == "ok"


async def test_publisher_fails_the_run_when_the_durable_write_fails(monkeypatch):
    """A run that persisted nothing may not report success."""
    import app.services.durable_snapshots as dsnap
    from app.tasks import precompute_calibration as pc

    payload = _payload()

    async def _compute(db, **_kwargs):
        return payload

    class _Session:
        async def execute(self, *a, **k):
            return MagicMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _durable(envelope):
        return {"status": "error", "identity": envelope.identity,
                "generation": envelope.generation, "error": "db down"}

    rc_mock = MagicMock()
    monkeypatch.setattr(pc, "compute_calibration_payload", _compute)
    monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _Session())
    monkeypatch.setattr(dsnap, "publish_snapshot_standalone", _durable)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc_mock)
    monkeypatch.setattr(pc, "_read_published_baseline", lambda _rc: None)

    with pytest.raises(RuntimeError, match="durable publication did not succeed"):
        await pc._precompute_calibration_main()

    # And it never touched the accelerators, so nothing is torn.
    rc_mock.set.assert_not_called()
