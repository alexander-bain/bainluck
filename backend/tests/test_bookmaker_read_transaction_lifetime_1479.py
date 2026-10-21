"""#1479 — the bookmaker sweep ends each successful read transaction before the next.

``_precompute_bookmaker_calibration`` opens one ``get_task_session`` for the grid
and every chunk. Before this change nothing on its success path ended a
transaction: the grid SELECT opened one, every landed chunk read inside it, the
cell bank was written and the curve published while it was still open, and only
``get_task_session``'s exit committed it. Only a timed-out chunk rolled back. So
a healthy walk held one snapshot for as long as the walk ran.

These tests drive the REAL writer against a REAL SQLAlchemy ``Session`` (sync,
on ``sqlite://`` — no aiosqlite in this sandbox, so a thin async shim fronts it,
the repo's established shape). Every statement the writer issues is answered
from a small event model, but each one is ALSO executed on the real session, so
autobegin, commit, rollback and close are SQLAlchemy's own and are observed
through its engine events — the layer that issues BEGIN/COMMIT on asyncpg. A
hand-written fake that merely counted ``commit()`` calls could not tell a
transaction that ended from one that did not.

The event model answers a chunk ``[lo, hi)`` with the aggregate of its events,
so a split chunk's halves sum exactly to the whole and the expected curve can be
folded from the events directly, independent of how the walk was chunked. Every
probability is a multiple of 1/4, so the float sums are exact in any order.
"""
from __future__ import annotations

import asyncio
import json
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

import app.tasks.backfill_winners as bw
from app.utils.db_session_identity import APPLICATION_NAME_MAX, parse_session_tag
from app.utils.soccer_three_way import (
    SOCCER_THREE_WAY_CONTRACT,
    SOCCER_THREE_WAY_CONTRACT_KEY,
)

UTC = timezone.utc
SETTLED = [datetime(2025, m, 1, tzinfo=UTC) for m in (1, 2, 3)]


def _open_month() -> datetime:
    # Offset-free: the current month has not ended, so it is open whatever the
    # clock reads (gotcha #44).
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


OPEN = _open_month()
TWO_WAY_CELLS = [(c, lo) for c in ("basketball_nba", "soccer_epl")
                 for lo in SETTLED + [OPEN]]
THREE_WAY_CELLS = [("soccer_epl", lo) for lo in SETTLED[1:] + [OPEN]]
#: Pre-banked 30 h ago: carried, then re-read by the spare-wall refresh.
CARRIED = ("basketball_nba", SETTLED[0])

_PROBS = (0.25, 0.5, 0.75, 0.5)
_WINS = (0, 1, 1, 0)


def _events(kind, category, lo):
    """Four games per cell, on days 3/10/17/24 — two each side of a split."""
    out = []
    for i, day in enumerate((3, 10, 17, 24)):
        p = _PROBS[(i + len(category) + (kind == "three")) % 4]
        w = _WINS[(i + lo.month) % 4]
        out.append((lo.replace(day=day, hour=12), int(p * 10), w, p))
    return out


def _rows(kind, category, lo, hi):
    """What the chunk statement returns for ``[lo, hi)``: one row per bucket."""
    month = lo.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    agg: dict[int, list] = {}
    for at, bucket, w, p in _events(kind, category, month):
        if lo <= at < hi:
            slot = agg.setdefault(bucket, [0, 0, 0.0, 0.0])
            slot[0] += 1
            slot[1] += w
            slot[2] += p
            slot[3] += (p - w) ** 2
    return [SimpleNamespace(bucket_idx=b, category=category, n=v[0],
                            winners=v[1], sum_prob=v[2], sum_sq_err=v[3])
            for b, v in sorted(agg.items())]


def _cell_rows(kind, category, lo):
    return [list(bw._bookmaker_row_tuple(r))
            for r in _rows(kind, category, lo, bw._add_month(lo))]


def _model_curve():
    """The curve folded straight from the events, no chunks involved."""
    out = {}
    for kind, cells in (("two", TWO_WAY_CELLS), ("three", THREE_WAY_CELLS)):
        for category, lo in cells:
            for b, cat, n, w, sp, se in _cell_rows(kind, category, lo):
                key = (b, cat, kind)
                slot = out.setdefault(key, [0, 0, 0.0, 0.0])
                slot[0] += n
                slot[1] += w
                slot[2] += sp
                slot[3] += se
    return {k: tuple(v) for k, v in out.items()}


class QueryCanceledError(Exception):
    """Named like asyncpg's, which is what ``_is_statement_timeout`` keys on."""


class _Rail:
    """A real SQLAlchemy Session plus the record of what it did."""

    def __init__(self, *, chunk_fault=None, commit_fault=None):
        self.engine = create_engine("sqlite://")
        self.txn = 0
        self.log: list[tuple[str, int]] = []
        self.statements: list[dict] = []
        self.chunk_fault = chunk_fault
        self.commit_fault = commit_fault
        self.commits = 0
        self.sync: Session | None = None
        # (what, in_transaction) at every side effect outside the database.
        self.side_effects: list[tuple[str, bool]] = []
        for name in ("begin", "commit", "rollback"):
            event.listen(self.engine, name, self._listener(name))

    def _listener(self, name):
        def _on(_conn):
            if name == "begin":
                self.txn += 1
            self.log.append((name, self.txn))
        return _on

    def in_txn(self) -> bool:
        return self.sync is not None and self.sync.in_transaction()

    def reads(self):
        return [s for s in self.statements
                if s["kind"] in ("grid", "soccer_grid", "two", "three")]

    def chunks(self):
        return [s for s in self.statements if s["kind"] in ("two", "three")]


class _Shim:
    """Async surface over the rail's real sync session."""

    def __init__(self, rail: _Rail):
        self.rail = rail
        self._s = Session(rail.engine, expire_on_commit=False)
        rail.sync = self._s

    async def execute(self, statement, params=None, *a, **k):
        sql = str(statement)
        params = dict(params or {})
        if "set_config('application_name'" in sql:
            kind = "tag"
        elif "SET LOCAL statement_timeout" in sql:
            kind = "set_local"
        elif "date_trunc('month'" in sql:
            kind = "soccer_grid" if "soccer_three_way_since" in sql else "grid"
        elif "soccer_draw_residual_min" in sql:
            kind = "three"
        else:
            kind = "two"
        # The real statement: this is what makes the transaction real.
        self._s.execute(text("SELECT 1"))
        rec = {"kind": kind, "txn": self.rail.txn, "params": params}
        self.rail.statements.append(rec)

        if kind == "tag":
            return _Result([SimpleNamespace(name=params["tag"], pid=4242)])
        if kind == "set_local":
            return _Result([])
        if kind == "grid":
            return _Result([SimpleNamespace(category=c, bucket_start=lo)
                            for c, lo in TWO_WAY_CELLS])
        if kind == "soccer_grid":
            return _Result([SimpleNamespace(category=c, bucket_start=lo)
                            for c, lo in THREE_WAY_CELLS])
        if self.rail.chunk_fault is not None:
            exc = self.rail.chunk_fault(rec, len(self.rail.chunks()))
            if exc is not None:
                raise exc
        return _Result(_rows(kind, params["category"], params["lo"],
                             params["hi"]))

    async def commit(self):
        self.rail.commits += 1
        if self.rail.commit_fault is not None:
            exc = self.rail.commit_fault(self.rail.commits)
            if exc is not None:
                raise exc
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def close(self):
        self._s.close()


class _Result:
    def __init__(self, payload):
        self._payload = payload

    def all(self):
        return list(self._payload)

    def first(self):
        return self._payload[0] if self._payload else None


class _Redis:
    def __init__(self, rail: _Rail):
        self.rail = rail
        self.curve = None
        self.hashes: dict[str, dict[str, str]] = {}

    def setex(self, key, ttl, value):
        self.rail.side_effects.append(("setex", self.rail.in_txn()))
        self.curve = (key, ttl, value)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, field, value):
        self.rail.side_effects.append(("bank", self.rail.in_txn()))
        self.hashes.setdefault(key, {})[field] = value

    def expire(self, key, ttl):
        return None


def _run(monkeypatch, rail: _Rail):
    """One real writer run. Returns (summary, redis, durable payloads)."""
    redis = _Redis(rail)
    key = bw._bookmaker_cell_key(*CARRIED)
    redis.hashes[bw._BOOKMAKER_BANK_KEY] = {key: json.dumps({
        "banked_at": _time.time() - 30 * 3600,
        "rows": _cell_rows("two", *CARRIED)})}
    durable: list = []

    @asynccontextmanager
    async def _task_session():
        # `get_task_session`'s own contract, on the rail: commit on success,
        # roll back on Exception, close (which rolls back anything still open)
        # on every exit — including a BaseException such as cancellation.
        shim = _Shim(rail)
        try:
            yield shim
            await shim.commit()
        except Exception:
            await shim.rollback()
            raise
        finally:
            await shim.close()

    async def _publish(envelope):
        rail.side_effects.append(("durable", rail.in_txn()))
        durable.append(envelope.payload)
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    monkeypatch.setattr(bw, "get_task_session", _task_session)
    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", _publish)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                        lambda *a, **k: redis)
    summary = asyncio.run(bw._precompute_bookmaker_calibration())
    return summary, redis, durable


def _published(redis):
    out = {}
    for b in json.loads(redis.curve[2]):
        kind = "three" if b.get(SOCCER_THREE_WAY_CONTRACT_KEY) == \
            SOCCER_THREE_WAY_CONTRACT else "two"
        out[(b["bucket_idx"], b["category"], kind)] = (
            b["n"], b["winners"], b["sum_prob"], b["sum_sq_err"])
    return out


def _txn_closures(rail):
    """{txn: how it ended}, from SQLAlchemy's own events."""
    return {t: name for name, t in rail.log if name != "begin"}


# ---------------------------------------------------------------------------
# The lifetime itself
# ---------------------------------------------------------------------------


def test_no_two_successful_reads_share_a_transaction(monkeypatch):
    """THE DEFECT: grid, two-way chunks, soccer grid, three-way chunks and the
    refresh re-read all sat in ONE transaction. Each now has its own."""
    rail = _Rail()
    summary, _, _ = _run(monkeypatch, rail)
    assert summary["terminal"] == "complete", summary

    reads = rail.reads()
    kinds = {r["kind"] for r in reads}
    assert kinds == {"grid", "soccer_grid", "two", "three"}, kinds
    assert bw._bookmaker_cell_key(*CARRIED) in {
        bw._bookmaker_cell_key(r["params"]["category"], r["params"]["lo"])
        for r in rail.chunks()}, "the refresh path was not exercised"
    txns = [r["txn"] for r in reads]
    assert len(set(txns)) == len(txns), (
        f"{len(txns)} successful reads ran in only {len(set(txns))} "
        f"transaction(s): a landed read's snapshot was kept open for the next")


def test_each_read_is_committed_before_the_next_transaction_begins(monkeypatch):
    rail = _Rail()
    _run(monkeypatch, rail)

    # Strict alternation: begin N, commit N, begin N+1, ... — nothing nests,
    # nothing is left for get_task_session's exit to sweep up.
    begins = [t for name, t in rail.log if name == "begin"]
    # One transaction per read, and none besides: alternation over a single
    # walk-long transaction would hold trivially.
    assert len(begins) == len(rail.reads()), (len(begins), len(rail.reads()))
    assert rail.log == [entry for t in begins
                        for entry in (("begin", t), ("commit", t))], rail.log
    for r in rail.reads():
        assert _txn_closures(rail)[r["txn"]] == "commit"


def test_no_transaction_is_open_while_banking_or_publishing(monkeypatch):
    """Banking a cell and publishing the curve are Redis/durable work; before
    #1479 every one of them ran inside the walk's still-open read."""
    rail = _Rail()
    summary, redis, durable = _run(monkeypatch, rail)

    assert summary["published"] is True
    seen = {what for what, _ in rail.side_effects}
    assert seen == {"bank", "durable", "setex"}, seen
    held = [what for what, open_ in rail.side_effects if open_]
    assert held == [], f"a read transaction was open during {held}"


def test_every_transaction_opens_with_one_bounded_task_identity(monkeypatch):
    """`set_config(..., is_local)` dies with its transaction, so the tag is the
    first statement of EVERY transaction, and it is the same tag each time."""
    rail = _Rail()
    _run(monkeypatch, rail)

    first_by_txn: dict[int, dict] = {}
    for s in rail.statements:
        first_by_txn.setdefault(s["txn"], s)
    reads_txns = {r["txn"] for r in rail.reads()}
    assert reads_txns <= set(first_by_txn)
    assert {first_by_txn[t]["kind"] for t in reads_txns} == {"tag"}

    tags = {s["params"]["tag"] for s in rail.statements if s["kind"] == "tag"}
    assert len(tags) == 1, tags
    (tag,) = tags
    assert len(tag.encode()) <= APPLICATION_NAME_MAX
    parsed = parse_session_tag(tag)
    assert parsed is not None and parsed.task == "bookmaker_calibration", tag


# ---------------------------------------------------------------------------
# Unchanged outputs
# ---------------------------------------------------------------------------


def test_curve_and_bank_are_exactly_the_event_fold(monkeypatch):
    rail = _Rail()
    summary, redis, durable = _run(monkeypatch, rail)

    assert summary["terminal"] == "complete"
    assert _published(redis) == _model_curve()
    assert durable == [json.loads(redis.curve[2])]
    for kind, bank_key, cells in (
            ("two", bw._BOOKMAKER_BANK_KEY, TWO_WAY_CELLS),
            ("three", bw._BOOKMAKER_SOCCER_BANK_KEY, THREE_WAY_CELLS)):
        bank = redis.hashes[bank_key]
        for category, lo in cells:
            key = bw._bookmaker_cell_key(category, lo)
            if lo == OPEN:
                # Open months are read fresh and never carried, as before.
                continue
            assert json.loads(bank[key])["rows"] == \
                _cell_rows(kind, category, lo), key


# ---------------------------------------------------------------------------
# Rollback / split
# ---------------------------------------------------------------------------


def test_a_timed_out_chunk_splits_into_fresh_transactions_and_moves_nothing(
        monkeypatch):
    target = ("soccer_epl", SETTLED[1])
    hits = {"two": 0, "three": 0}

    def _fault(rec, _n):
        p = rec["params"]
        if (p["category"], p["lo"]) == target and \
                p["hi"] == bw._add_month(target[1]):
            hits[rec["kind"]] += 1
            return QueryCanceledError("canceling statement due to statement timeout")
        return None

    rail = _Rail(chunk_fault=_fault)
    summary, redis, _ = _run(monkeypatch, rail)

    assert hits == {"two": 1, "three": 1}, hits
    assert summary["terminal"] == "complete", summary
    assert _published(redis) == _model_curve()
    closures = _txn_closures(rail)
    assert sorted(closures.values()).count("rollback") == 2
    reads = rail.reads()
    landed = [r for r in reads if closures[r["txn"]] == "commit"]
    assert len({r["txn"] for r in landed}) == len(landed)
    assert [w for w, open_ in rail.side_effects if open_] == []


def test_an_irreducible_chunk_still_publishes_nothing(monkeypatch):
    target = ("basketball_nba", SETTLED[2])

    def _fault(rec, _n):
        if rec["params"]["category"] == target[0] and \
                target[1] <= rec["params"]["lo"] < bw._add_month(target[1]):
            return QueryCanceledError("statement timeout")
        return None

    monkeypatch.setattr(bw, "_CHUNK_MAX_DEPTH", 1)
    rail = _Rail(chunk_fault=_fault)
    summary, redis, durable = _run(monkeypatch, rail)

    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert redis.curve is None and durable == []
    assert set(_txn_closures(rail)) == {t for n, t in rail.log if n == "begin"}


# ---------------------------------------------------------------------------
# Commit failure
# ---------------------------------------------------------------------------


def test_a_failed_commit_after_a_landed_chunk_fails_closed(monkeypatch):
    # Commit 1 ends the grid read; commit 3 ends the SECOND chunk.
    rail = _Rail(commit_fault=lambda n: RuntimeError("connection lost at COMMIT")
                 if n == 3 else None)
    summary, redis, durable = _run(monkeypatch, rail)

    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert redis.curve is None and durable == []
    assert any("connection lost at COMMIT" in e for e in summary["errors"])
    chunks = rail.chunks()
    assert len(chunks) == 2, "the walk went on after a commit failed"
    bank = redis.hashes[bw._BOOKMAKER_BANK_KEY]
    first, second = (bw._bookmaker_cell_key(c["params"]["category"],
                                            c["params"]["lo"]) for c in chunks)
    assert first in bank
    assert second not in bank, "a cell whose read did not commit was banked"
    assert _txn_closures(rail)[chunks[1]["txn"]] == "rollback"


def test_a_commit_failure_shaped_like_a_timeout_is_not_split(monkeypatch):
    """The commit sits OUTSIDE the timeout handler: a failed COMMIT is not a
    slow statement, and splitting on it would re-read a cell already in hand."""
    rail = _Rail(commit_fault=lambda n: QueryCanceledError("statement timeout")
                 if n == 2 else None)
    summary, redis, _ = _run(monkeypatch, rail)

    assert summary["terminal"] == "failed"
    assert redis.curve is None
    assert len(rail.chunks()) == 1, [c["params"] for c in rail.chunks()]
    assert summary.get("chunks_failed") is None


def test_a_failed_grid_commit_reads_no_chunk(monkeypatch):
    rail = _Rail(commit_fault=lambda n: RuntimeError("grid commit lost")
                 if n == 1 else None)
    summary, redis, durable = _run(monkeypatch, rail)

    assert summary["terminal"] == "failed"
    assert rail.chunks() == []
    assert redis.curve is None and durable == []


# ---------------------------------------------------------------------------
# Hard interruption
# ---------------------------------------------------------------------------


def test_a_hard_interruption_mid_walk_publishes_nothing_and_ends_its_read(
        monkeypatch):
    """Cancellation is a BaseException: neither the writer's nor the session's
    `except Exception` sees it. Every read before it has already committed;
    the interrupted one is ended by the session's close, never left open."""
    rail = _Rail(chunk_fault=lambda rec, n: asyncio.CancelledError()
                 if n == 3 else None)
    with pytest.raises(asyncio.CancelledError):
        _run(monkeypatch, rail)

    chunks = rail.chunks()
    assert len(chunks) == 3
    closures = _txn_closures(rail)
    assert [closures[c["txn"]] for c in chunks] == ["commit", "commit",
                                                    "rollback"]
    assert closures[rail.reads()[0]["txn"]] == "commit"
    assert not rail.in_txn()
    assert [w for w, _ in rail.side_effects] == ["bank", "bank"]
    assert all(not open_ for _, open_ in rail.side_effects)
