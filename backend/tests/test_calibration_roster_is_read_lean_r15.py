"""The Stage A roster is streamed into slim tuples, and nothing it feeds moves.

2026-10-07: ``worker-heavy`` (1 GB quota) was R15-killed at 10:20Z and 11:18Z
(Heroku dyno metrics: total memory 2.20 GB and 2.23 GB against the 2.0 GiB kill
line). Each kill landed before that beat's publish, so ``/api/calibration`` served
the 09:37Z curve until 12:17Z, with the page saying "not being refreshed right now".
Each roster read added ~700 MB to the dyno, and the beat reads it twice.

These tests pin both halves of the change:

* **Identity.** The slim roster yields the SAME generation digest, the SAME plan
  and the SAME frozen assignment as the ``Row`` objects it replaces. A digest that
  moved would throw away the staged bank (days of rebuild), so this is the
  load-bearing assertion.
* **Shape.** The production session is streamed in batches and the result is
  closed even when a batch fails; a session with no ``stream`` (every test double
  in this suite) still reads through ``execute``.
* **Size.** The slim roster holds measurably less heap than the ``Row`` list.
"""

from __future__ import annotations

import gc
import inspect
import tracemalloc
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.tasks import precompute_calibration as pc
from app.utils.calibration_staged_futures import (
    RosterRow,
    generation_fingerprint,
    plan_units,
    slim_roster,
)


def _sqlite_rows(n: int):
    """Real SQLAlchemy ``Row`` objects shaped like the roster, with edge values."""
    engine = create_engine("sqlite://")
    sources = ["kalshi", "polymarket", "odds_api", "datagolf"]
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE vm (market_id INTEGER, source TEXT, vm_id TEXT, is_grouped INTEGER)"
            )
        )
        rows = []
        for i in range(n):
            market_id = 5_000_000 + i
            grouped = i % 5 != 0
            rows.append(
                {
                    "m": market_id,
                    # a NULL source and a NULL flag must survive verbatim
                    "s": None if i % 97 == 0 else sources[i % 4],
                    "v": f"e:{9_000_000 + i // 6}" if grouped else f"m:{market_id}",
                    "g": None if i % 89 == 0 else int(grouped),
                }
            )
        conn.execute(text("INSERT INTO vm VALUES (:m, :s, :v, :g)"), rows)
    conn = engine.connect()
    result = conn.execute(
        text("SELECT market_id, source, vm_id, is_grouped FROM vm ORDER BY market_id")
    )
    return conn, result


def _assignment(roster):
    # The exact expression _run_staged_futures builds from the roster.
    return {int(r.market_id): (str(r.vm_id), bool(r.is_grouped)) for r in roster}


def _plan_view(chunks):
    return [
        (c.index, c.key, c.vm_ids, c.market_ids, c.stored_member_digest) for c in chunks
    ]


def test_slim_roster_keeps_digest_plan_and_assignment_identical():
    conn, result = _sqlite_rows(6_000)
    try:
        rows = result.all()
    finally:
        conn.close()
    slim = slim_roster(rows)

    assert len(slim) == len(rows)
    assert all(type(r) is RosterRow for r in slim)
    assert generation_fingerprint(slim) == generation_fingerprint(rows)
    assert _assignment(slim) == _assignment(rows)
    for refinements in ({}, {"128:3": 4}):
        assert _plan_view(
            plan_units(slim, buckets=128, refinements=refinements)
        ) == _plan_view(plan_units(rows, buckets=128, refinements=refinements))


def test_slim_roster_carries_values_verbatim():
    rows = [
        SimpleNamespace(market_id=7, source=None, vm_id="m:7", is_grouped=None),
        SimpleNamespace(market_id="8", source="kalshi", vm_id="e:1", is_grouped=0),
    ]
    assert slim_roster(rows) == [
        RosterRow(7, None, "m:7", None),
        RosterRow("8", "kalshi", "e:1", 0),
    ]


def test_slim_roster_appends_batches_into_one_list():
    first = [SimpleNamespace(market_id=1, source="kalshi", vm_id="m:1", is_grouped=False)]
    second = [SimpleNamespace(market_id=2, source="kalshi", vm_id="m:2", is_grouped=False)]
    out: list = []
    slim_roster(first, into=out)
    slim_roster(second, into=out)
    assert [r.market_id for r in out] == [1, 2]


class _StreamResult:
    def __init__(self, batches, *, fail_after=None):
        self._batches = batches
        self._fail_after = fail_after
        self.partition_sizes = []
        self.closed = False

    async def partitions(self, size):
        self.partition_sizes.append(size)
        for i, batch in enumerate(self._batches):
            if self._fail_after is not None and i == self._fail_after:
                raise RuntimeError("connection lost mid-roster")
            yield batch

    async def close(self):
        self.closed = True


class _StreamingDb:
    def __init__(self, result):
        self.result = result
        self.statements = []
        self.executed = False

    async def stream(self, statement):
        self.statements.append(statement)
        return self.result

    async def execute(self, *_a, **_k):  # pragma: no cover - must not be called
        self.executed = True
        raise AssertionError("a streaming session must not buffer the roster")


def _ns(i):
    return SimpleNamespace(market_id=i, source="polymarket", vm_id=f"m:{i}", is_grouped=False)


async def test_production_session_streams_the_roster_in_batches():
    batches = [[_ns(1), _ns(2)], [_ns(3)]]
    db = _StreamingDb(_StreamResult(batches))

    roster = await pc._read_futures_roster(db)

    assert [r.market_id for r in roster] == [1, 2, 3]
    assert all(type(r) is RosterRow for r in roster)
    assert db.executed is False
    assert db.result.partition_sizes == [pc.ROSTER_STREAM_BATCH]
    assert db.result.closed is True
    (statement,) = db.statements
    assert statement.get_execution_options().get("yield_per") == pc.ROSTER_STREAM_BATCH
    assert statement.text == pc._futures_generation_sql()


async def test_stream_is_closed_when_a_batch_fails():
    db = _StreamingDb(_StreamResult([[_ns(1)], [_ns(2)]], fail_after=1))
    with pytest.raises(RuntimeError, match="mid-roster"):
        await pc._read_futures_roster(db)
    assert db.result.closed is True


async def test_session_without_stream_reads_through_execute():
    rows = [_ns(4), _ns(5)]

    class _Result:
        def all(self):
            return rows

    class _Db:
        async def execute(self, statement, params=None):
            self.statement = statement
            return _Result()

    db = _Db()
    roster = await pc._read_futures_roster(db)
    assert roster == [RosterRow(4, "polymarket", "m:4", False), RosterRow(5, "polymarket", "m:5", False)]
    assert db.statement.text == pc._futures_generation_sql()


def test_the_beat_reads_its_roster_through_the_lean_reader():
    source = inspect.getsource(pc._run_staged_futures)
    assert "await _read_futures_roster(db)" in source
    assert "_futures_generation_sql()))).all()" not in source


def _held_after_read(convert):
    """Heap still held once the roster is read and (optionally) converted.

    Both arms fetch the same rows from an identical table INSIDE the trace, so
    the strings the driver allocates are counted on both sides; the slim arm then
    drops the ``Row`` list, as the batched reader does after each batch.
    """
    conn, result = _sqlite_rows(60_000)
    try:
        gc.collect()
        tracemalloc.start()
        try:
            kept = result.all()
            if convert:
                kept = slim_roster(kept)
            gc.collect()
            held = tracemalloc.get_traced_memory()[0]
        finally:
            tracemalloc.stop()
    finally:
        conn.close()
    del kept
    return held


def test_slim_roster_holds_less_heap_than_row_objects():
    # Measured locally at 1.2M rows: 317 MB of Row objects vs 197 MB slim (0.62).
    row_bytes = _held_after_read(convert=False)
    slim_bytes = _held_after_read(convert=True)
    assert slim_bytes < 0.85 * row_bytes, (slim_bytes, row_bytes)
