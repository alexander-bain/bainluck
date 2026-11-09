"""#12340: the roster read reports where its time goes.

Measured Nov 8: ``read:futures_generation`` took 474 s of the futures phase's
600 s budget, so the rolling rebuild got 32 s and banked no unit, and the served
bank (Oct 27) kept the page ``stale``. pg_stat_statements put the statement at
154 s mean (29 s of disk reads), which leaves most of the stage unexplained. The
read streams 20,000-row batches into the worker, so the time is split three
ways: the wait for the first rows, every wait on the database, and the worker's
own copying.

🔴 THE LOAD-BEARING CHECKS:

* ``test_streamed_read_splits_database_wait_from_conversion`` — the waits land
  in ``first_batch_ms``/``fetch_ms`` and NOT in ``convert_ms``.
* ``test_a_read_cut_short_keeps_its_timings`` — the read that hits the statement
  timeout is the one worth splitting, so a raise must not lose the figures.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from app.tasks import precompute_calibration as pc


def _ns(i):
    return SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i}", is_grouped=False)


class _SlowResult:
    """Batches that each take ``delay_s`` to arrive, optionally failing at one."""

    def __init__(self, batches, *, delay_s, fail_at=None):
        self._batches = batches
        self._delay_s = delay_s
        self._fail_at = fail_at
        self.closed = False

    async def partitions(self, size):
        for i, batch in enumerate(self._batches):
            await asyncio.sleep(self._delay_s)
            if self._fail_at is not None and i == self._fail_at:
                raise RuntimeError("canceling statement due to statement timeout")
            yield batch

    async def close(self):
        self.closed = True


class _Db:
    def __init__(self, result):
        self.result = result

    async def stream(self, statement):
        return self.result


async def test_streamed_read_splits_database_wait_from_conversion():
    db = _Db(_SlowResult([[_ns(1), _ns(2)], [_ns(3)]], delay_s=0.06))
    timings: dict = {}
    roster = await pc._read_futures_roster(db, timings)

    assert [r.market_id for r in roster] == [1, 2, 3]
    assert timings["batches"] == 2
    assert timings["first_batch_ms"] >= 50
    # Both arrivals are database waits: ~120 ms, the first included.
    assert timings["fetch_ms"] >= 100
    assert timings["fetch_ms"] >= timings["first_batch_ms"]
    # Copying three rows is not where the time went.
    assert timings["convert_ms"] < 50


async def test_a_read_cut_short_keeps_its_timings():
    db = _Db(_SlowResult([[_ns(1)], [_ns(2)]], delay_s=0.06, fail_at=1))
    timings: dict = {}
    with pytest.raises(RuntimeError, match="statement timeout"):
        await pc._read_futures_roster(db, timings)
    assert db.result.closed is True
    assert timings["batches"] == 1
    # The interrupted second wait is counted, not dropped.
    assert timings["fetch_ms"] >= 100
    assert timings["first_batch_ms"] is not None


async def test_execute_session_fills_the_same_keys():
    rows = [_ns(4)]

    class _Result:
        def all(self):
            return rows

    class _ExecDb:
        async def execute(self, statement, params=None):
            return _Result()

    timings: dict = {}
    await pc._read_futures_roster(_ExecDb(), timings)
    assert set(timings) == {"first_batch_ms", "fetch_ms", "convert_ms", "batches"}
    assert timings["batches"] == 1


async def test_timings_are_optional():
    db = _Db(_SlowResult([[_ns(1)]], delay_s=0))
    assert [r.market_id for r in await pc._read_futures_roster(db)] == [1]


class _Ledger:
    def __init__(self):
        self.gauges: dict[str, int] = {}

    def record_gauge(self, name, value):
        self.gauges[name] = value


def test_timings_reach_the_ledger_as_gauges():
    runner = SimpleNamespace(ledger=_Ledger())
    pc._record_roster_timings(
        runner, {"first_batch_ms": 400_000, "fetch_ms": 470_000, "convert_ms": 3_000, "batches": 54}
    )
    assert runner.ledger.gauges == {
        "roster:first_batch_ms": 400_000,
        "roster:fetch_ms": 470_000,
        "roster:convert_ms": 3_000,
        "roster:batches": 54,
    }


def test_an_unreached_first_batch_is_not_recorded_as_zero():
    runner = SimpleNamespace(ledger=_Ledger())
    pc._record_roster_timings(
        runner, {"first_batch_ms": None, "fetch_ms": 570_000, "convert_ms": 0, "batches": 0}
    )
    assert "roster:first_batch_ms" not in runner.ledger.gauges
    assert runner.ledger.gauges["roster:fetch_ms"] == 570_000


def test_recording_never_raises():
    class _Broken:
        def record_gauge(self, name, value):
            raise RuntimeError("ledger gone")

    pc._record_roster_timings(SimpleNamespace(ledger=_Broken()), {"fetch_ms": 1})
    pc._record_roster_timings(SimpleNamespace(), {"fetch_ms": 1})


def test_the_beat_records_the_split_even_when_the_read_raises():
    source = inspect.getsource(pc._run_staged_futures)
    assert "await _read_futures_roster(db, roster_timings)" in source
    # #12340 roster reuse moved the read into an ``else:``, one level deeper.
    assert "finally:\n            _record_roster_timings(runner, roster_timings)" in source


def test_the_split_does_not_move_the_input_fingerprint():
    """The bank survives this deploy: the reader is not a hashed root."""
    for root in ("_main_input_fingerprint", "population_predicate_fingerprint"):
        src = inspect.getsource(getattr(pc, root))
        assert "_read_futures_roster" not in src
        assert "_run_staged_futures" not in src
