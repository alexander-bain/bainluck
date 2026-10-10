"""#10090: queued fresh work must not replay preparation after another stamp waits."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_module
from app.tasks.live_blend_refresh import (
    FRESH_STAMP_WORKERS,
    LiveBlendRefresher,
    PREPARED_EVENT_FIELDS,
    PREPARED_MARKET_FIELDS,
    PREPARED_OUTCOME_FIELDS,
    TailReceipts,
)
from app.utils.kalshi_exact_trace import ExactKalshiTrace


OLD = datetime(2026, 10, 8, tzinfo=timezone.utc)
NEW = OLD + timedelta(seconds=1)
TICKER = "KXNBAGAME-26OCT08BOSGSW-BOS"
#: 43ed0b2629: the first FRESH_STAMP_WORKERS events take the initial worker
#: slots from the shared read; the queued tail behind them rereads current
#: quotes. The tail is what this file is about, so it starts after the slots.
HEAD = tuple(range(1, FRESH_STAMP_WORKERS + 1))
TAIL = (FRESH_STAMP_WORKERS + 1, FRESH_STAMP_WORKERS + 2)
PENDING = {TAIL[-1] + 1, TAIL[-1] + 2}
SINGLE = TAIL[-1] + 3


class Result:
    def __init__(self, *, rows=(), stamp=None):
        self.rows, self.stamp = rows, stamp

    def all(self):
        return self.rows

    def first(self):
        return self.stamp


class Board:
    """Emulate SELECT snapshots and UPDATE RETURNING; run the real read/resolver/stamp."""

    def __init__(self, source, schedule):
        self.source, self.schedule = source, schedule
        self.reads, self.writes, self.commits = [], {}, []
        self.release = asyncio.Event()
        self.events, self.markets, self.quotes = {}, {}, {}
        for eid in range(1, SINGLE + 1):
            self.events[eid] = SimpleNamespace(
                id=eid, home_team_name="Boston Celtics",
                away_team_name="Golden State Warriors", status="live",
                completed_at=None, commence_time=None, win_probability_sources={},
                espn_win_prob_home=None, opening_home_probability=None,
            )
            self.markets[eid] = SimpleNamespace(
                id=eid, event_id=eid, source=source, external_id=TICKER,
                name="Celtics vs Warriors", status="open",
            )
            self.quotes[eid] = [SimpleNamespace(
                id=eid * 10, market_id=eid, name="Boston Celtics", rank=1,
                current_probability=0.6, last_updated=OLD,
            )]

    def advance_tail(self):
        for eid in TAIL:
            self.quotes[eid][0].current_probability = 0.8
            self.quotes[eid][0].last_updated = NEW

    @asynccontextmanager
    async def session(self):
        session = Session(self)
        yield session
        if self.schedule == "failed_head" and session.event_id == 2:
            raise RuntimeError("contained head commit failure")
        if session.event_id is not None:
            self.commits.append(session.event_id)


class Session:
    def __init__(self, board):
        self.board, self.event_id = board, None

    async def execute(self, statement, *args):
        board = self.board
        params = statement.compile().params
        if isinstance(statement, Update):
            eid = params["id_1"]
            self.event_id = eid
            if eid == 1:
                if board.schedule == "synchronous_head":
                    board.advance_tail()
                else:
                    await board.release.wait()
            elif eid == 2:
                board.advance_tail()
                board.release.set()
            entry = next(
                json.loads(value) for value in params.values()
                if isinstance(value, str) and value.startswith('{"value":')
            )
            board.writes[eid] = entry
            entry = dict(entry, updated_at=NEW.isoformat())
            return Result(stamp=({board.source: entry}, eid))
        # Every source read uses the actual projected SQL's event admission.
        ids = params["event_id_1"]
        board.reads.append(tuple(sorted(ids)))
        rows = []
        for eid in ids:
            for quote in board.quotes[eid]:
                rows.append(tuple(
                    getattr(obj, key, None)
                    if key != "win_probability_sources" else None
                    for obj, fields in (
                        (board.markets[eid], PREPARED_MARKET_FIELDS),
                        (board.events[eid], PREPARED_EVENT_FIELDS),
                        (quote, PREPARED_OUTCOME_FIELDS),
                    ) for key in fields
                ))
        return Result(rows=rows)

    async def rollback(self):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize("schedule", ["stalled_head", "failed_head", "synchronous_head"])
async def test_queued_fresh_tail_reads_actual_quote_clock_without_claiming_old_mark(
    monkeypatch, caplog, source, schedule,
):
    caplog.set_level(logging.INFO, logger="app.tasks.live_blend_refresh")
    monkeypatch.setattr(blend_module, "_mono", lambda: 100.0)
    monkeypatch.setattr(blend_module, "_wall", lambda: OLD.timestamp())
    board = Board(source, schedule)
    r = LiveBlendRefresher(source, session_factory=board.session, stamp_lock_timeout_ms=0)
    r.receipts = TailReceipts(source)
    r.receipts._live_events.update(range(1, SINGLE + 1))
    held = TAIL[0]
    # Existing hold for the first tail event, so both delivery and tail
    # closure are exercised.
    mark = r.receipts.note_input(held, held * 10, 0.6, "price")
    r.receipts.observe({held: mark}, OLD.timestamp(), set(), 100.0)
    r.receipts.stage([mark])
    trace_lines = []
    trace = ExactKalshiTrace(
        {TICKER}, OLD.timestamp() + 60, 128, "control",
        lambda: OLD.timestamp(), lambda: 100.0, trace_lines.append,
    )
    message = {"market_ticker": TICKER, "price": 60}
    trace.received(1, message)
    trace.decided(message, reason="accepted", event=held, outcome=held * 10,
                  probability=0.6, mark=mark)
    trace.committed(mark, OLD)
    r.receipts.exact_trace = trace
    # Keep the chart outside this source control; known named orientation is real.
    r._last_snapshot_at.update({eid: float("inf") for eid in range(1, SINGLE + 1)})
    frames = []

    async def publish(batch):
        frames.extend(batch)

    monkeypatch.setattr(r, "_publish", publish)
    await asyncio.wait_for(r.refresh([*reversed(HEAD + TAIL)]), timeout=2)

    assert board.reads[0] == HEAD + TAIL
    assert all(board.writes[eid]["value"] == 0.6 for eid in HEAD)
    for eid in TAIL:
        assert board.writes[eid]["value"] == 0.8
        assert board.writes[eid]["observed_basis"] == {str(eid * 10): NEW.timestamp()}
        assert board.writes[eid]["observed_value"] == 0.8
        assert eid in board.commits
        assert next(frame for frame in frames if frame["event_id"] == eid)["p"] == 0.8
    assert sorted(board.reads[1:]) == [(eid,) for eid in TAIL]
    assert r.stats["errors"] == (1 if schedule == "failed_head" else 0)
    assert not any(line["stage"] == "EVENT_COMMITTED" for line in trace_lines)
    assert trace.stamps == {}  # Old staged mark did not join the new observation.
    delivery = r.receipts._window[held]["stamps"]
    assert len(delivery) == 1 and delivery[0].endswith("@-@-@0")
    tail = [record.getMessage() for record in caplog.records
            if "tail-receipt run=" in record.getMessage()
            and f"event={held} " in record.getMessage()]
    assert len(tail) == 1 and "stamp_rev_seq=- " in tail[0]

    # Pending-only work still shares preparation; singleton still reads directly.
    r._throttle_deferred.update(PENDING)
    before = len(board.reads)
    await r.refresh([])
    assert board.reads[before:] == [tuple(sorted(PENDING))]
    before = len(board.reads)
    await r.refresh([SINGLE])
    assert board.reads[before:] == [(SINGLE,)]
