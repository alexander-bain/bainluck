"""Queue 272 (#1459): durable + truthful calibration precompute publication.

The hourly ``precompute_calibration_main`` beat blanked ``/api/calibration``:
the canonical compute grew to ~600s and kept dying with SoftTimeLimitExceeded
BEFORE it could publish, so once the 2h TTL expired the route 503'd (the
in-process last-good does not survive a dyno restart). These tests pin the fix:

  * a partial/empty compute is NEVER published (can't replace a valid entry);
  * a successful compute publishes BOTH the fresh ``main`` key and the durable
    ``last_good`` key (SET-only, never DEL);
  * a publish failure RAISES (recorded as a task failure) yet leaves any prior
    last-good intact — it can never masquerade as success;
  * the terminal summary distinguishes the compute / serialize / publish stages
    with generated_at + payload size;
  * the route serves the durable last-good (as ``stale``) on a clean main-key
    miss instead of paying a cold compute or 503-ing.

Scenarios (Item 2 acceptance): cache absent, publish success, publish failure,
Redis stall, compute timeout, cancellation, repeated beat, sibling progress.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tasks.precompute_calibration as pc
from app.tasks.precompute_calibration import (
    _MAIN_KEY,
    _MAIN_LAST_GOOD_KEY,
    _main_payload_is_publishable,
    _precompute_calibration_main,
    _publish_calibration_main,
)


def _payload(*, buckets=1, outcomes=635464):
    """A publishable payload.

    Queue 297 added an atomic publish gate that refuses a structurally
    INCOMPLETE candidate, so this fixture now carries the required sections
    (see ``calibration_publish_gate.REQUIRED_SECTIONS``). These tests are about
    publication mechanics, not payload shape — the minimal three-key dict was a
    fixture convenience, and a build actually missing these sections is exactly
    what the gate is supposed to stop.
    """
    return {
        "buckets": [{"bucket": i} for i in range(buckets)],
        "total_outcomes": outcomes,
        "total_markets": outcomes // 4,
        "total_winners": outcomes // 2,
        "by_category": [{"category": "politics", "outcomes": outcomes}],
        "by_source": [{"source": "kalshi", "outcomes": outcomes}],
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "generated_at": _RECENT_GENERATED_AT,
    }


# Queue 297 age-bounds a servable last-good at 7 days, so a hardcoded date would
# silently age out of the fixture's own contract and red the suite one week after
# it was written. Anchored 2 days back at a FIXED hour (gotcha #44: never seed
# relative to `now` across a date boundary).
_RECENT_GENERATED_AT = (
    (datetime.now(timezone.utc) - timedelta(days=2))
    .replace(hour=12, minute=0, second=0, microsecond=0)
    .isoformat()
)


class _FakeCM:
    def __init__(self, response):
        self._response = response
        # Queue 274: the beat now arms a DB-level statement_timeout on this
        # session before computing, so the session must support `await execute`.
        self.db = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *a):
        return False


def _patch_compute(response=None, *, raises=None):
    async def _compute(db, **_kwargs):
        if raises is not None:
            raise raises
        return response

    return _compute


# ---------------------------------------------------------------------------
# _main_payload_is_publishable — the partial/empty guard
# ---------------------------------------------------------------------------
def test_publishable_accepts_real_payload():
    assert _main_payload_is_publishable(_payload()) is True


@pytest.mark.parametrize(
    "bad",
    [
        {"buckets": [], "total_outcomes": 0},  # empty (degraded compute)
        {"buckets": [], "total_outcomes": 100},  # no buckets
        {"buckets": [{"b": 1}], "total_outcomes": 0},  # zero outcomes
        {},  # nothing
        None,  # cancelled/None
        "not a dict",
    ],
)
def test_publishable_rejects_partial_or_empty(bad):
    assert _main_payload_is_publishable(bad) is False


# ---------------------------------------------------------------------------
# _publish_calibration_main — dual-key, SET-only, bounded, fault-tolerant
# ---------------------------------------------------------------------------
def test_publish_writes_both_keys_set_only():
    rc = MagicMock()
    stages = _publish_calibration_main(rc, json.dumps(_payload()))

    assert stages == {"last_good": "ok", "main": "ok"}
    written = {c.args[0] for c in rc.set.call_args_list}
    assert written == {_MAIN_KEY, _MAIN_LAST_GOOD_KEY}
    # SET-only: a publish must never DEL a prior payload.
    rc.delete.assert_not_called()


def test_publish_main_failure_preserves_last_good_write():
    """A stalled/erroring ``main`` SET is captured; the durable write already ran."""
    rc = MagicMock()

    def _set(key, *a, **k):
        if key == _MAIN_KEY:
            raise ConnectionError("SSL: UNEXPECTED_EOF")
        return True

    rc.set.side_effect = _set
    stages = _publish_calibration_main(rc, json.dumps(_payload()))

    assert stages["last_good"] == "ok"  # durable survivor written first
    assert stages["main"] == "error"
    assert "UNEXPECTED_EOF" in stages["main_error"]
    rc.delete.assert_not_called()


# ---------------------------------------------------------------------------
# _precompute_calibration_main — terminal state truthfulness
# ---------------------------------------------------------------------------
async def test_precompute_success_publishes_and_reports_stages():
    rc = MagicMock()
    payload = _payload(buckets=1572)

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(payload)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(payload)):
        summary = await _precompute_calibration_main()

    assert summary["status"] == "ok"
    assert summary["buckets"] == 1572
    assert summary["outcomes"] == 635464
    assert summary["generated_at"] == payload["generated_at"]
    assert summary["payload_bytes"] > 0
    # stage timings present (truthful terminal — Item 1)
    for k in ("compute_ms", "serialize_ms", "publish_ms"):
        assert k in summary
    # Queue 298: the durable row is published alongside the two Redis keys, and
    # its stage is reported with them.
    assert summary["publish"]["last_good"] == "ok"
    assert summary["publish"]["main"] == "ok"
    assert summary["publish"]["durable"] == "ok"
    assert summary["publication"]["success"] is True
    written = {c.args[0] for c in rc.set.call_args_list}
    assert written == {_MAIN_KEY, _MAIN_LAST_GOOD_KEY}


async def test_precompute_empty_payload_never_published():
    """A degraded (empty) compute must not overwrite a valid cache entry."""
    rc = MagicMock()
    empty = {"buckets": [], "total_outcomes": 0}

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(empty)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(empty)):
        with pytest.raises(RuntimeError, match="unpublishable"):
            await _precompute_calibration_main()

    rc.set.assert_not_called()  # neither key touched
    rc.delete.assert_not_called()


async def test_precompute_main_publish_failure_is_degraded_not_failed():
    """Queue 298 moved the success criterion from Redis to the durable row.

    Before, a failed ``main`` SET raised — correct when Redis WAS the survivor.
    It is not any more: the durable row is, and once it has landed the run has
    genuinely done its job. The route serves the durable copy (dated) until
    Redis recovers, so failing the task here would only add a false alarm. The
    failure is still recorded in the stages and logged loudly.
    """
    rc = MagicMock()
    payload = _payload()

    def _set(key, *a, **k):
        if key == _MAIN_KEY:
            raise ConnectionError("redis stall")
        return True

    rc.set.side_effect = _set

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(payload)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(payload)):
        summary = await _precompute_calibration_main()

    assert summary["status"] == "ok"
    assert summary["publish"]["main"] == "error"
    assert summary["publish"]["durable"] == "ok"
    assert summary["publication"]["success"] is True
    # last-good SET was still attempted; nothing was DEL'd.
    written = {c.args[0] for c in rc.set.call_args_list}
    assert _MAIN_LAST_GOOD_KEY in written
    rc.delete.assert_not_called()


async def test_precompute_durable_failure_fails_the_run_and_skips_redis():
    """The inverse, and the one that now matters: no durable row, no success.

    A run that persisted nothing must not report success — otherwise the task
    metric and any Review/Verify evidence citing it claim a completed run whose
    output does not exist. Redis is left untouched so the accelerator can never
    lead the durable store.
    """
    rc = MagicMock()
    payload = _payload()

    async def _durable_fails(envelope):
        return {"status": "error", "identity": envelope.identity,
                "generation": envelope.generation, "error": "db down"}

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(payload)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(payload)), patch(
        "app.services.durable_snapshots.publish_snapshot_standalone", _durable_fails
    ):
        with pytest.raises(RuntimeError, match="durable publication did not succeed"):
            await _precompute_calibration_main()

    rc.set.assert_not_called()
    rc.delete.assert_not_called()


async def test_precompute_compute_timeout_propagates_unpublished():
    """SoftTimeLimitExceeded-class compute failure never publishes anything."""
    rc = MagicMock()

    class _SoftTimeLimitExceeded(Exception):
        pass

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(None)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(
        pc,
        "compute_calibration_payload",
        _patch_compute(raises=_SoftTimeLimitExceeded()),
    ):
        with pytest.raises(_SoftTimeLimitExceeded):
            await _precompute_calibration_main()

    rc.set.assert_not_called()


async def test_precompute_cancellation_propagates_unpublished():
    """A cancelled build retains the last-good payload (nothing written/DEL'd)."""
    rc = MagicMock()

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(None)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(
        pc,
        "compute_calibration_payload",
        _patch_compute(raises=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _precompute_calibration_main()

    rc.set.assert_not_called()
    rc.delete.assert_not_called()


async def test_precompute_repeated_beat_is_idempotent():
    """Two successive runs both publish the same keys (no drift, no starvation)."""
    rc = MagicMock()
    payload = _payload()

    with patch("app.tasks.base.get_task_session", return_value=_FakeCM(payload)), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(payload)):
        s1 = await _precompute_calibration_main()
        s2 = await _precompute_calibration_main()

    assert s1["status"] == s2["status"] == "ok"
    # 2 runs x 2 keys = 4 SETs, all idempotent overwrites of the same 2 keys.
    written = [c.args[0] for c in rc.set.call_args_list]
    assert written.count(_MAIN_KEY) == 2
    assert written.count(_MAIN_LAST_GOOD_KEY) == 2


# ---------------------------------------------------------------------------
# Queue 274 (#1479): DB-level statement_timeout backstop against orphaned scans
# ---------------------------------------------------------------------------
def test_statement_timeout_fires_before_celery_hard_limit():
    """The DB must cancel a wedged statement (releasing its xmin) BEFORE Celery's
    hard time_limit SIGKILLs the worker — a SIGKILL orphans the backend, which is
    what pinned autovacuum and drove the bloat spiral (#1479)."""
    # precompute_calibration_main is registered soft=1500 / hard=1560 (seconds).
    assert pc._MAIN_COMPUTE_STMT_TIMEOUT_MS < 1560 * 1000
    # ...but not so low it kills a healthy compute (last success measured ~905s).
    assert pc._MAIN_COMPUTE_STMT_TIMEOUT_MS >= 1000 * 1000


async def test_precompute_arms_statement_timeout_before_compute():
    """The beat issues a SET LOCAL statement_timeout on its session before the
    canonical compute runs — the DB-level backstop for gotchas #38/#39."""
    rc = MagicMock()
    payload = _payload()
    cm = _FakeCM(payload)

    with patch("app.tasks.base.get_task_session", return_value=cm), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(pc, "compute_calibration_payload", _patch_compute(payload)):
        summary = await _precompute_calibration_main()

    assert summary["status"] == "ok"  # healthy compute still publishes normally
    executed = [str(c.args[0]).lower() for c in cm.db.execute.call_args_list]
    assert any("set local statement_timeout" in s for s in executed), executed
    assert any(str(pc._MAIN_COMPUTE_STMT_TIMEOUT_MS) in s for s in executed), executed


# ---------------------------------------------------------------------------
# Route — durable last-good serves during a clean main-key miss (sibling progress)
# ---------------------------------------------------------------------------
class _RouteRedis:
    """Async Redis stand-in: main key absent, durable last-good present."""

    def __init__(self, *, main=None, last_good=None):
        self._store = {}
        if main is not None:
            self._store["bainluck:calibration:main"] = main
        if last_good is not None:
            self._store["bainluck:calibration:main:last_good"] = last_good
        self.gets = []

    async def get(self, key):
        self.gets.append(key)
        return self._store.get(key)


def _fake_getter(client):
    async def _get():
        return client

    return _get


async def test_route_serves_durable_last_good_on_main_miss(monkeypatch):
    """Main key expired (clean miss) but the durable last-good bridges the gap —
    the route serves it as ``stale`` and never pays the cold compute."""
    from app.routes import calibration
    from app.utils import request_cache as rc

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()

    payload = _payload(buckets=1572)
    client = _RouteRedis(main=None, last_good=json.dumps(payload))
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    async def _boom(db):
        raise AssertionError("cold compute ran despite a durable last-good")

    monkeypatch.setattr(
        "app.tasks.precompute_calibration.compute_calibration_payload", _boom
    )

    out = await calibration.public_calibration(db=object(), bust=0)

    assert out["total_outcomes"] == 635464
    assert out["generated_at"] == payload["generated_at"]
    assert out["cache"]["status"] == "stale"
    assert out["cache"]["reason"] == "main_key_absent"
    # Queue 297 Item 1: a degraded copy must be DATED, so the banner can say how
    # old it is instead of implying the numbers are current.
    assert out["cache"]["generated_at"] == payload["generated_at"]
    assert out["cache"]["age_s"] >= 0
    assert "bainluck:calibration:main:last_good" in client.gets

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


async def test_route_bust_skips_durable_last_good(monkeypatch):
    """bust=1 must force a fresh recompute, not serve the durable last-good."""
    from app.routes import calibration
    from app.utils import request_cache as rc

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()

    fresh = _payload(buckets=3)
    client = _RouteRedis(main=None, last_good=json.dumps(_payload(buckets=1572)))
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    async def _compute(db, **_kwargs):
        return fresh

    monkeypatch.setattr(
        "app.tasks.precompute_calibration.compute_calibration_payload", _compute
    )

    out = await calibration.public_calibration(db=object(), bust=1)

    # served the fresh recompute, not the durable last-good
    assert out["buckets"] == fresh["buckets"]
    assert "cache" not in out or out.get("cache", {}).get("status") != "stale"

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


# ---------------------------------------------------------------------------
# Queue #284 Item 3 — the memoized stale copy stays honestly marked
# ---------------------------------------------------------------------------
async def test_stale_last_good_memoized_copy_stays_marked_across_requests(monkeypatch):
    """First AND second same-dyno responses on a persistent main-key miss must
    both be ``cache.status=stale``: the copy stored in the in-process cache is
    marked BEFORE it is memoized, so a later Tier-1 hit can't serve it as fresh."""
    from app.routes import calibration
    from app.utils import request_cache as rc

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()

    payload = _payload(buckets=1572)
    client = _RouteRedis(main=None, last_good=json.dumps(payload))
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    async def _boom(db):
        raise AssertionError("cold compute ran despite a durable last-good")

    monkeypatch.setattr(
        "app.tasks.precompute_calibration.compute_calibration_payload", _boom
    )

    first = await calibration.public_calibration(db=object(), bust=0)
    assert first["cache"]["status"] == "stale"
    assert first["cache"]["reason"] == "main_key_absent"
    # THE contract: the memoized copy itself carries the stale marker.
    assert calibration._cache["data"].get("cache", {}).get("status") == "stale"

    # A second same-dyno request (main still absent) is ALSO stale — never a
    # falsely-fresh memoized copy.
    second = await calibration.public_calibration(db=object(), bust=0)
    assert second["cache"]["status"] == "stale"
    assert second["cache"]["reason"] == "main_key_absent"

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


async def test_recovered_fresh_main_replaces_stale_memoized_copy(monkeypatch):
    """Once the fresh ``main`` key returns, the same-dyno route replaces the
    stale-marked memoized copy with fresh metadata (no TTL/compute change)."""
    from app.routes import calibration
    from app.utils import request_cache as rc

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()

    stale_payload = _payload(buckets=1572)
    client = _RouteRedis(main=None, last_good=json.dumps(stale_payload))
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    async def _boom(db):
        raise AssertionError("cold compute ran unexpectedly")

    monkeypatch.setattr(
        "app.tasks.precompute_calibration.compute_calibration_payload", _boom
    )

    stale = await calibration.public_calibration(db=object(), bust=0)
    assert stale["cache"]["status"] == "stale"

    # Main recovers: the fresh key is now present.
    fresh_payload = _payload(buckets=3)
    client._store["bainluck:calibration:main"] = json.dumps(fresh_payload)

    out = await calibration.public_calibration(db=object(), bust=0)
    assert out["buckets"] == fresh_payload["buckets"]
    assert "cache" not in out
    assert calibration._cache["data"].get("cache") is None

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
