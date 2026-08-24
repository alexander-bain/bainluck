"""CAL-P089 (#2076) — the twin's published-read rail, all three legs.

CAL-P088 item 3 diagnosed the SECOND blocker on #2076's ceiling run
(``fold_duration_s 1351.95``, ``db_rows 0``,
``payload_error: "published_read_failed: redis call did not complete"``) and was
ordered to propose nothing. The Fable directive of 2026-08-23 ratified that
report in full and ordered the fix. This file is the fix's red-first suite: every
test below was written and run against the UNCHANGED
:mod:`app.tasks.calibration_published_twin_worker` first, and the ones that
describe the defect went red there.

The three legs, each of which is a separate way the rail lies or gives up:

**Leg A — a clean MISS is reported as a transport failure.**
``bounded_redis_call`` returns ``RedisResult(MISS)`` for a nil reply and ``is_ok``
is ``status == OK``, so ``if not res.is_ok`` swallowed the miss and answered
*"redis call did not complete"* — untrue; the call completed and returned nil.
The ``published_absent`` branch two lines below was therefore **unreachable dead
code**, inside a function whose own docstring promises *"a miss and a Redis
failure are DIFFERENT facts and are named differently"*. Gotcha #53 aimed at the
instrument built to catch gotcha #53.

**Leg B — the twin was the only ``main`` consumer with no ``last_good``
fallback.** ``bainluck:calibration:main`` carries a 2 h TTL on a 50 MB
``allkeys-lru`` instance, and ``precompute_calibration.py`` documents the
consequence itself: main *"is evicted long before ``last_good`` (7d)"*. The route
falls back (``routes/calibration.py`` tier 2b), the publish gate falls back
(``_read_published_baseline``); the twin did not. So the COMMON case — the beat
landing more than 2 h after a publish — cost Gate 0 its whole verdict, over a
durable copy sitting right there and being served to real readers.

**Leg C — a request-path deadline over a background client's cold start.**
``REDIS_OP_DEADLINE_MS`` is 600 ms and sized for the request path under the 30 s
H12 cutoff; the shared client is provisioned for a 5 s connect with a 3-attempt
retry, i.e. **up to ~18 s of legitimate recovery inside a 0.6 s wrapper**. And the
fold guarantees the recovery is needed: both ``read_served_disclosure`` calls go
to Postgres, so the post-fold read is the run's FIRST Redis touch, after 1,351 s
— **54× the 25 s ``health_check_interval``**. Not probabilistic. Deterministic.

What is deliberately NOT here: nothing in this file touches the frozen builder.
**Ruling 009's exception stays UNSPENT.**
"""

from __future__ import annotations

import json

from app.tasks import calibration_published_twin_worker as worker
from app.utils import request_cache as _rc


# --- fakes --------------------------------------------------------------------
class _FakeRedis:
    """An async client that records the ORDER of what it was asked to do.

    Order is the subject of leg C — "was the connection touched before the read"
    is not answerable from a call count.
    """

    def __init__(self, *, values=None, ping=True, effects=None):
        self.values = dict(values or {})
        self.calls: list[tuple[str, object]] = []
        self._ping = ping
        # key -> list of per-attempt effects (value or exception), consumed in order
        self._effects = {k: list(v) for k, v in (effects or {}).items()}

    async def ping(self):
        self.calls.append(("ping", None))
        if isinstance(self._ping, BaseException):
            raise self._ping
        return self._ping

    async def get(self, key):
        self.calls.append(("get", key))
        queued = self._effects.get(key)
        if queued:
            effect = queued.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return self.values.get(key)

    def gets(self, key) -> int:
        return sum(1 for kind, arg in self.calls if kind == "get" and arg == key)


def _install(monkeypatch, client) -> None:
    async def _getter():
        return client

    monkeypatch.setattr(_rc, "get_shared_async_redis", _getter)


def _record_deadlines(monkeypatch) -> list[int]:
    """Capture every ``deadline_ms`` the twin grades a Redis op at."""
    seen: list[int] = []
    real = _rc.bounded_redis_call

    async def _spy(factory, *, deadline_ms=_rc.REDIS_OP_DEADLINE_MS, **kw):
        seen.append(deadline_ms)
        return await real(factory, deadline_ms=deadline_ms, **kw)

    monkeypatch.setattr(_rc, "bounded_redis_call", _spy)
    return seen


MAIN = worker.PUBLISHED_MAIN_KEY
LAST_GOOD = "bainluck:calibration:main:last_good"


async def _run_twin(monkeypatch, *, timeout_ms: int = 1_000) -> dict:
    """``run_published_twin`` with everything that is not the read stubbed out.

    The fold, the disclosure and the durable write are all somebody else's
    subject; what is under test is the payload read and what the artifact then
    says about it.
    """

    async def _no_disclosure():
        return None, None, "staged_cursor_unreadable: missing"

    async def _no_fold(*, timeout_ms):  # noqa: ARG001 — signature must match
        return [], 0.1, None

    async def _no_bank(envelope):  # noqa: ARG001
        return {"status": "skipped"}

    monkeypatch.setattr(worker, "read_served_disclosure", _no_disclosure)
    monkeypatch.setattr(worker, "_fold", _no_fold)
    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", _no_bank
    )
    return await worker.run_published_twin(timeout_ms=timeout_ms)


class _Row:
    """A driver-shaped row, so the fold reducer is exercised as it is in prod."""

    def __init__(self, source, category, bucket_idx, n, winners, sum_prob):
        self._mapping = {
            "source": source, "category": category, "bucket_idx": bucket_idx,
            "n": n, "winners": winners, "sum_prob": sum_prob,
        }


def _rows():
    """A fold that SUCCEEDED — bucket 7, db rate 0.70, matching ``_payload``."""
    return [_Row("kalshi", "quantity", 7, 100, 70, 72.5)]


def _staged(*, banked=128, drifted=0, unknown=0):
    """A disclosure of the shape ``build_disclosure`` returns, so a bound exists."""
    return {
        "measured": True,
        "staged_at": "2026-08-23T12:28:50+00:00",
        "units_banked": banked,
        "units_drifted": drifted,
        "units_drift_unknown": unknown,
    }


def _payload(*, generated_at="2026-08-23T20:00:00+00:00", rate=0.70) -> str:
    return json.dumps(
        {
            "generated_at": generated_at,
            "buckets": [
                {
                    "source": "kalshi",
                    "category": "quantity",
                    "bucket_idx": 7,
                    "actual_rate": rate,
                }
            ],
        }
    )


# --- LEG A — a miss is a miss --------------------------------------------------
class TestLegAMissIsNotAFailure:
    """``published_absent`` must be REACHABLE, and the miss must not lie."""

    async def test_an_absent_key_reports_absent_not_read_failed(self, monkeypatch):
        _install(monkeypatch, _FakeRedis(values={}))
        _payload_out, error, _meta = await worker._read_published_payload()
        assert error is not None
        assert error.startswith("published_absent"), error
        assert "redis call did not complete" not in error

    async def test_the_absent_error_names_both_keys_it_looked_at(self, monkeypatch):
        """An absence is only a finding about the producer if the search was whole."""
        _install(monkeypatch, _FakeRedis(values={}))
        _payload_out, error, _meta = await worker._read_published_payload()
        assert MAIN in error and LAST_GOOD in error, error

    async def test_a_stalled_call_still_reports_read_failed(self, monkeypatch):
        """The other direction: a real transport failure must NOT read as absent."""
        boom = ConnectionError("connection reset by peer")
        _install(
            monkeypatch,
            _FakeRedis(effects={MAIN: [boom, boom], LAST_GOOD: [boom]}),
        )
        _payload_out, error, _meta = await worker._read_published_payload()
        assert error is not None
        assert error.startswith("published_read_failed"), error

    async def test_an_absent_key_reports_absent_END_TO_END(self, monkeypatch):
        """The same claim through the public entry point, so the red is BEHAVIOUR.

        Every other leg-A test above binds a signature this fix introduces, which
        makes their red structural. This one asks the question the artifact asks —
        *what did the run say happened?* — of a function whose shape is unchanged.
        """
        _install(monkeypatch, _FakeRedis(values={}))
        art = await _run_twin(monkeypatch)
        assert art["payload_error"].startswith("published_absent"), art["payload_error"]

    async def test_miss_and_failure_are_distinguishable_on_the_record(
        self, monkeypatch
    ):
        """The CAL-P088 finding, stated as an assertion: same string, two facts.

        Not just the message — the artifact must carry the typed status, because
        the message is prose and prose is what conflated them in the first place.
        """
        _install(monkeypatch, _FakeRedis(values={}))
        _p, _e, miss_meta = await worker._read_published_payload()

        boom = ConnectionError("connection reset by peer")
        _install(
            monkeypatch,
            _FakeRedis(effects={MAIN: [boom, boom], LAST_GOOD: [boom]}),
        )
        _p2, _e2, fail_meta = await worker._read_published_payload()

        assert miss_meta["main_status"] == "miss"
        assert fail_meta["main_status"] == "error"
        assert miss_meta["main_status"] != fail_meta["main_status"]


# --- LEG B — fall back like every other consumer -------------------------------
class TestLegBLastGoodFallback:
    """Eviction of a 2 h key on an ``allkeys-lru`` box is the COMMON case."""

    def test_both_keys_are_pinned_to_the_PRODUCERS_constants(self):
        """A drift guard, and it is the difference between a fix and a fix-shaped
        comment.

        Both key names are string literals here, matching how ``routes/
        calibration.py`` writes them — but a literal that drifts from the
        producer does not raise, it just never finds anything. Renaming
        ``_MAIN_LAST_GOOD_KEY`` would silently return this worker to the exact
        state CAL-P089 exists to end: no fallback, ``unmeasurable`` over a
        perfect fold, and nothing anywhere saying why.
        """
        from app.tasks.precompute_calibration import (
            _MAIN_KEY,
            _MAIN_LAST_GOOD_KEY,
        )

        assert worker.PUBLISHED_MAIN_KEY == _MAIN_KEY
        assert worker.PUBLISHED_LAST_GOOD_KEY == _MAIN_LAST_GOOD_KEY

    async def test_main_absent_falls_back_to_last_good(self, monkeypatch):
        client = _FakeRedis(values={LAST_GOOD: _payload()})
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert payload["buckets"][0]["bucket_idx"] == 7
        assert meta["payload_source"] == LAST_GOOD
        assert meta["fallback_used"] is True

    async def test_a_healthy_main_never_reads_last_good(self, monkeypatch):
        client = _FakeRedis(values={MAIN: _payload(), LAST_GOOD: _payload(rate=0.1)})
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert payload["buckets"][0]["actual_rate"] == 0.70
        assert meta["payload_source"] == MAIN
        assert meta["fallback_used"] is False
        assert meta["last_good_status"] is None
        assert client.gets(LAST_GOOD) == 0

    async def test_a_poisoned_main_does_not_take_last_good_down_with_it(
        self, monkeypatch
    ):
        """Queue 300B's lesson, one consumer over: malformed is a miss, not a fault.

        A truncated ``main`` (an eviction mid-write, a partial read) must not
        deprive the twin of a perfectly healthy durable sibling.
        """
        client = _FakeRedis(values={MAIN: '{"buckets": [', LAST_GOOD: _payload()})
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert meta["main_status"] == "undecodable"
        assert meta["payload_source"] == LAST_GOOD
        assert payload["buckets"][0]["bucket_idx"] == 7

    async def test_a_wrong_shaped_main_also_falls_back(self, monkeypatch):
        client = _FakeRedis(values={MAIN: "[1, 2, 3]", LAST_GOOD: _payload()})
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert meta["main_status"] == "wrong_shape"
        assert payload["buckets"][0]["bucket_idx"] == 7

    async def test_a_failed_main_read_still_tries_the_durable_sibling(
        self, monkeypatch
    ):
        """A dead pooled connection is per-connection; the next checkout may live."""
        boom = ConnectionError("connection reset by peer")
        client = _FakeRedis(
            values={LAST_GOOD: _payload()}, effects={MAIN: [boom, boom]}
        )
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert meta["main_status"] == "error"
        assert meta["payload_source"] == LAST_GOOD
        assert payload["buckets"][0]["bucket_idx"] == 7

    async def test_the_fallback_is_declared_on_the_artifact_never_silent(self):
        """Grading a durable copy is legitimate; grading it SILENTLY is not.

        The route serves ``last_good`` to real readers when ``main`` is absent, so
        the twin's subject is still "the artifact readers get" — but which copy it
        was, and how old, has to survive onto the record.
        """
        art = worker.build_artifact(
            rows=[],
            fold_duration_s=1.0,
            fold_error=None,
            payload=json.loads(_payload()),
            payload_error=None,
            timeout_ms=240_000,
            payload_meta={
                "payload_source": LAST_GOOD,
                "fallback_used": True,
                "main_status": "miss",
                "last_good_status": "ok",
                "pretouch_status": "ok",
                "read_attempts": 1,
            },
        )
        assert art["payload_source"] == LAST_GOOD
        assert art["payload_fallback_used"] is True
        assert art["payload_main_status"] == "miss"
        assert art["payload_last_good_status"] == "ok"

    def test_an_artifact_with_no_meta_still_names_the_main_key(self):
        """Back-compat: every pre-CAL-P089 caller/fixture keeps its meaning."""
        art = worker.build_artifact(
            rows=[],
            fold_duration_s=1.0,
            fold_error=None,
            payload={},
            payload_error=None,
            timeout_ms=240_000,
        )
        assert art["payload_source"] == MAIN
        assert art["payload_fallback_used"] is False


# --- LEG C — cold start is not a request-path event ----------------------------
class TestLegCColdStartBudget:
    """The fold makes the post-fold read the run's first Redis touch."""

    def test_the_twin_deadline_covers_the_clients_own_reconnect_budget(self):
        """3 x (5 s connect + <=1 s backoff) ~ 18 s. A smaller number is a lie."""
        assert worker.TWIN_REDIS_DEADLINE_MS >= 18_000
        assert worker.TWIN_REDIS_DEADLINE_MS > _rc.REDIS_OP_DEADLINE_MS

    async def test_the_connection_is_pretouched_before_the_read(self, monkeypatch):
        client = _FakeRedis(values={MAIN: _payload()})
        _install(monkeypatch, client)
        await worker._read_published_payload()
        kinds = [kind for kind, _ in client.calls]
        assert kinds[0] == "ping", client.calls
        assert "get" in kinds

    async def test_no_twin_redis_op_is_graded_at_the_request_path_budget(
        self, monkeypatch
    ):
        """Every op — pre-touch, main, fallback — gets the background budget."""
        seen = _record_deadlines(monkeypatch)
        _install(monkeypatch, _FakeRedis(values={}))
        await worker._read_published_payload()
        assert seen, "no bounded op ran"
        assert all(d >= worker.TWIN_REDIS_DEADLINE_MS for d in seen), seen
        assert all(d > _rc.REDIS_OP_DEADLINE_MS for d in seen), seen

    async def test_a_failed_read_is_retried_once_and_can_succeed(self, monkeypatch):
        """The pool can hand the GET a DIFFERENT idle-dead connection than the PING
        healed, so warming one connection is not the same as warming the pool."""
        client = _FakeRedis(
            effects={MAIN: [ConnectionError("reset"), _payload()]}
        )
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert meta["payload_source"] == MAIN
        assert meta["read_attempts"] == 2
        assert client.gets(MAIN) == 2
        assert payload["buckets"][0]["bucket_idx"] == 7

    async def test_the_retry_is_exactly_once_not_a_loop(self, monkeypatch):
        boom = ConnectionError("reset")
        client = _FakeRedis(effects={MAIN: [boom, boom, boom, boom], LAST_GOOD: [boom]})
        _install(monkeypatch, client)
        _p, error, meta = await worker._read_published_payload()
        assert client.gets(MAIN) == 2
        assert meta["read_attempts"] == 2
        assert error is not None and error.startswith("published_read_failed")

    async def test_a_clean_miss_is_not_retried(self, monkeypatch):
        """A retry is for a broken connection. Retrying a nil reply is just slower."""
        client = _FakeRedis(values={})
        _install(monkeypatch, client)
        await worker._read_published_payload()
        assert client.gets(MAIN) == 1

    async def test_a_failing_pretouch_never_costs_the_read(self, monkeypatch):
        """The pre-touch is an optimisation. It must not become a new gate."""
        client = _FakeRedis(values={MAIN: _payload()}, ping=ConnectionError("reset"))
        _install(monkeypatch, client)
        payload, error, meta = await worker._read_published_payload()
        assert error is None
        assert meta["pretouch_status"] == "error"
        assert payload["buckets"][0]["bucket_idx"] == 7


# --- the rail as a whole -------------------------------------------------------
class TestTheRailEndToEnd:
    async def test_the_run_carries_the_read_diagnostics_onto_the_artifact(
        self, monkeypatch
    ):
        """The CAL-P088 finding was that the RECORD could not attribute the failure.
        A fix that healed the read and kept the record mute would not close it."""
        _install(monkeypatch, _FakeRedis(values={LAST_GOOD: _payload()}))
        art = await _run_twin(monkeypatch)
        assert art["payload_error"] is None
        assert art["payload_source"] == LAST_GOOD
        assert art["payload_fallback_used"] is True
        assert art["payload_main_status"] == "miss"
        assert art["payload_pretouch_status"] == "ok"

    def test_a_healthy_read_over_this_fold_DOES_produce_a_verdict(self):
        """The positive control for the test below it, and it is not optional.

        Asserting ``unmeasurable`` proves nothing unless the same fixture can
        reach a verdict when the read succeeds — otherwise the assertion is
        satisfied by whatever else was already broken, which is exactly how the
        first version of the next test let a mutation through (``rows=[]`` meant
        the zero-row clause fired and the payload clause was never exercised).
        """
        art = worker.build_artifact(
            rows=_rows(),
            fold_duration_s=1.0,
            fold_error=None,
            payload=json.loads(_payload()),
            payload_error=None,
            timeout_ms=240_000,
            staged=_staged(),
        )
        assert art["db_rows"] == 100
        assert art["verdict"] in ("agrees", "disagrees")
        assert art["measured"] is True

    async def test_an_unreadable_payload_still_forces_unmeasurable(self, monkeypatch):
        """The fallback must not soften guard 1. A rail with nothing on either key
        is still a run that compared nothing, and it must never read as agreement —
        **even when the fold went perfectly**, which is the case that matters and
        the only one that can tell this clause from the zero-row clause below it.
        """
        boom = ConnectionError("reset")
        _install(
            monkeypatch,
            _FakeRedis(effects={MAIN: [boom, boom], LAST_GOOD: [boom]}),
        )
        _p, error, meta = await worker._read_published_payload()
        art = worker.build_artifact(
            rows=_rows(),
            fold_duration_s=1.0,
            fold_error=None,
            payload={},
            payload_error=error,
            timeout_ms=240_000,
            payload_meta=meta,
            staged=_staged(),
        )
        assert art["db_rows"] == 100, "the fold succeeded; only the READ failed"
        assert art["verdict"] == "unmeasurable"
        assert art["unmeasurable_reason"] == error
        assert art["terminal"] == "failed"
        assert art["measured"] is False
