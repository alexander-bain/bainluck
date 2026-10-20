"""#11317 P2 — a bundled pair the current-book proof refused is not re-read on
every flush; it is read again when an input the proof reads changes.

v5810 (#11317 live): a refusal re-queued the event as throttle-deferred, so
every quiet flush counted as work, started a refresh, re-read the same board
and was refused again on the same book (blend no_reading ≈ 5.7× stamped for
6 minutes at 07:56–08:02Z). These tests drive the production flush
(`flush_prices`, exec'd from kalshi_ws.py by the #10655 rig) and the
production proof readers (`steady_*`, exec'd by the #10090 rig) over a real
`KalshiWebSocket` book, with a real `LiveBlendRefresher`. They prove work
counts and stamp outcomes in-process, not production latency or a page.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.kalshi_ws as K
import app.tasks.live_blend_refresh as LBR
from app.tasks.kalshi import _kalshi_yes_probability
from app.tasks.live_blend_refresh import (
    BOOK_REFUSED_SWEEP_S,
    LiveBlendRefresher,
    adopt_handed_off,
    hand_off_pending,
)
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from app.utils.live_blend import MarketOutcomes
from tests import test_bundled_pair_book_proof_10090 as old
from tests import test_kalshi_game_isolation_10655 as flush_rig

H, A, P = old.H, old.A, old.P


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def board(home=".825", away=".185", *, home_id=11, away_id=12, ticker=P,
          home_ticker=H, away_ticker=A, home_at=None):
    m = NS(id=1, source="kalshi", external_id=ticker, name="Brooksby vs Krueger",
           status="open", market_metadata={})
    h = NS(id=home_id, name="Jenson Brooksby", external_id=home_ticker,
           current_probability=Decimal(home), rank=1,
           last_updated=home_at or old.NOW, is_winner=None, resolution_source=None)
    a = NS(id=away_id, name="Mitchell Krueger", external_id=away_ticker,
           current_probability=Decimal(away), rank=2, last_updated=old.OLD,
           is_winner=None, resolution_source=None)
    return [MarketOutcomes(m, [h, a], event_commence_time=old.NOW - timedelta(hours=1),
                           event_has_result=False)]


def build(monkeypatch, *, signature=True, proof=True, rows=None):
    """A real refresher wired with the consumer's real readers over a real book.

    `rows()` returns the board each read sees (a new object per read, as a
    session would). Reads and UPDATEs are recorded.
    """
    clock = Clock()
    monkeypatch.setattr(LBR, "_mono", clock)
    s = old.socket()  # H .82/.83 (mid .825) and A .18/.19 (mid .185)
    custody = PrimaryQuoteCustody()
    r = LiveBlendRefresher("kalshi", min_refresh_interval_s=.25)
    r._normal_closed = True
    clients = [NS(sock=s, tickers={H, A}, task=NS(done=lambda: False))]
    ns = dict(vars(K))
    ns.update(game_clients=clients, ticker_to_ids={H: (1, 11), A: (1, 12)},
              prices=NS(settled_market_ids=set()), primary_quote_custody=custody,
              blend_refresher=r, _kalshi_yes_probability=_kalshi_yes_probability)
    readers = {name: old.nested(name, ns) for name in (
        "steady_book_midpoint", "steady_book_primary_price",
        "steady_primary_input", "steady_book_signature")}
    if proof:
        r.require_current_book_proof = True
        r.current_book_midpoint = readers["steady_book_midpoint"]
        r.current_book_primary_price = readers["steady_book_primary_price"]
        r.current_primary_input = readers["steady_primary_input"]
        if signature:
            r.current_book_signature = readers["steady_book_signature"]
    event = NS(id=1, home_team_name="Brooksby", away_team_name="Krueger",
               status="live", completed_at=None, espn_win_prob_home=None,
               opening_home_probability=None, win_probability_sources={})
    rec = NS(seq=2, reads=[], updates=[], clock=clock, sock=s, custody=custody,
             ns=ns, event=event, readers=readers)
    rows = rows or board

    class Session:
        async def execute(self, stmt, *args, **kwargs):
            if isinstance(stmt, Update):
                rec.updates.append(stmt)
                return NS(first=lambda: (
                    {"kalshi": {"value": .8, "updated_at": old.NOW.isoformat()}}, 1))
            return NS(scalar_one_or_none=lambda: None)

        def add(self, *args):
            pass

        async def flush(self):
            pass

        @asynccontextmanager
        async def begin_nested(self):
            yield

    @asynccontextmanager
    async def sessions():
        yield Session()

    async def groups(_session, ids):
        rec.reads.append(tuple(sorted(ids)))
        return {eid: (event, rows()) for eid in ids if eid == 1}

    async def snapshot(*args, **kwargs):
        return None, False

    async def publish(frames):
        return r._normal_revisions(frames)

    r._session_factory = sessions
    monkeypatch.setattr(r, "_read_groups", groups)
    monkeypatch.setattr("app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot)
    monkeypatch.setattr(r, "_publish", publish)
    return r, rec


def book(rec, ticker, bid, ask):
    """One more snapshot on the socket's sid, in sequence (a gap drops the book)."""
    rec.seq += 1
    frame = old.snapshot(ticker, bid, ask, rec.seq)
    if bid == "0":
        frame["msg"]["yes_dollars_fp"] = []
    rec.sock._book.apply(frame)


def mismatch(rec):
    """The home book moves away from the stored .825: the proof refuses."""
    book(rec, H, ".80", ".81")


def consumer_flush(r):
    """The production `flush_prices`, with this real refresher as its owner."""
    rig = flush_rig.rig()
    rig.batch.clear()
    rig.ns["blend_refresher"] = r
    return rig


async def quiet_flushes(rig, r, rec, n, step=1.0):
    """`n` production flushes with no new price, `step` seconds apart."""
    prices = rig.ns["prices"]
    work = []
    for _ in range(n):
        rec.clock.t += step
        before = prices.flush_work
        assert await rig.flush(rec.clock.t) is True
        await prices.join_stamp(r)
        work.append(prices.flush_work - before)
    return work


# ── (a) a refused pair with no changed input is read once ───────────────────

@pytest.mark.asyncio
async def test_a_refused_pair_spends_no_quiet_flush_until_an_input_changes(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    assert rec.reads == [(1,)] and rec.updates == []
    assert r.stats["no_reading"] == 1 and r.stats["bundled_refused"] == 1
    # Owed, not lost: parked with the inputs it was refused on.
    assert set(r._book_refused) == {1}
    rig = consumer_flush(r)
    work = await quiet_flushes(rig, r, rec, 8)  # 8 s < the 10 s sweep
    assert rec.reads == [(1,)], "no flush re-read the refused board"
    assert work == [0] * 8, "no quiet flush counted as work"
    assert r.stats["bundled_refused"] == 1 and set(r._book_refused) == {1}


@pytest.mark.asyncio
async def test_without_the_signature_reader_every_due_flush_still_rereads(monkeypatch):
    # The pre-#11317-P2 shape, kept for a refresher whose owner installs no
    # signature: the refusal re-queues and every due flush pays for it.
    r, rec = build(monkeypatch, signature=False)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    assert 1 in r.pending_event_ids() and not r._book_refused
    rig = consumer_flush(r)
    work = await quiet_flushes(rig, r, rec, 4)
    assert len(rec.reads) == 5 and work == [1, 1, 1, 1]
    assert r.stats["bundled_refused"] == 5 and rec.updates == []


# ── (b) a changed input re-admits it, with no price change ──────────────────

@pytest.mark.asyncio
async def test_book_recovery_without_a_price_change_wakes_and_stamps_the_pair(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    rig = consumer_flush(r)
    assert await quiet_flushes(rig, r, rec, 3) == [0, 0, 0]
    # The book returns to the stored price. No row changed; no batch names it.
    book(rec, H, ".82", ".83")
    assert 1 in r.pending_event_ids()
    work = await quiet_flushes(rig, r, rec, 1)
    assert work == [1] and rec.reads == [(1,), (1,)]
    assert len(rec.updates) == 1 and not r._book_refused
    assert 1 not in r.pending_event_ids()


@pytest.mark.asyncio
async def test_a_gap_then_resnapshot_wakes_the_pair_it_refused(monkeypatch):
    r, rec = build(monkeypatch)
    # A sequence gap removes the book: the proof refuses.
    rec.sock._book.apply({"type": "orderbook_delta", "sid": 3, "seq": 9, "msg": {
        "market_ticker": H, "side": "yes", "price_dollars": ".80", "delta_fp": "1"}})
    await r.refresh([1], flush_started=rec.clock.t)
    assert rec.updates == [] and set(r._book_refused) == {1}
    rig = consumer_flush(r)
    assert await quiet_flushes(rig, r, rec, 2) == [0, 0]
    rec.seq = 9
    book(rec, H, ".82", ".83")  # the resnapshot, both legs
    book(rec, A, ".18", ".19")
    assert await quiet_flushes(rig, r, rec, 1) == [1]
    assert len(rec.updates) == 1 and not r._book_refused


@pytest.mark.asyncio
async def test_a_landed_primary_input_wakes_the_pair_without_a_price_change(monkeypatch):
    # Off-ask original trade: the home row's .08 is provable only once that
    # accepted input has itself landed (custody), never by book or equality.
    at = old.NOW
    r, rec = build(monkeypatch, rows=lambda: board(".08", ".93", home_at=at))
    book(rec, H, "0", ".12")
    book(rec, A, ".92", ".94")
    q = rec.sock._overlay_ticker({"market_ticker": H, "price_dollars": ".08"})
    rec.custody.receive(11, q)
    await r.refresh([1], flush_started=rec.clock.t)
    assert rec.updates == [] and set(r._book_refused) == {1}
    rig = consumer_flush(r)
    assert await quiet_flushes(rig, r, rec, 2) == [0, 0]
    # The same input lands at the stored row's own observation. The book,
    # the stored price and the batch are all unchanged.
    rec.custody.committed(rec.custody.snapshot([11]), {11: at})
    assert await quiet_flushes(rig, r, rec, 1) == [1]
    assert len(rec.updates) == 1 and len(rec.reads) == 2
    # The home-only reading stamps. An original-input proof never licenses the
    # two-leg average, so the pair stays parked for the next changed input
    # rather than costing every flush again.
    assert set(r._book_refused) == {1}
    assert await quiet_flushes(rig, r, rec, 2) == [0, 0]


@pytest.mark.asyncio
async def test_a_refused_sibling_leg_wakes_the_devig_when_its_book_proves(monkeypatch):
    # Home proven, away refused: the home-only reading stamps and the pair
    # is parked; the away book proving later is owed the two-leg reading.
    r, rec = build(monkeypatch)
    book(rec, A, ".16", ".17")
    await r.refresh([1], flush_started=rec.clock.t)
    assert len(rec.updates) == 1 and set(r._book_refused) == {1}
    assert r.stats["bundled_refused"] == 0, "a stamped reading is not a no-reading"
    rig = consumer_flush(r)
    assert await quiet_flushes(rig, r, rec, 2) == [0, 0]
    book(rec, A, ".18", ".19")
    assert await quiet_flushes(rig, r, rec, 1) == [1]
    assert len(rec.reads) == 2 and not r._book_refused


@pytest.mark.asyncio
async def test_a_midpoint_appearing_at_the_old_ask_only_price_wakes_the_devig(monkeypatch):
    # lane1b's review: the away leg's ask-only primary price (.18) already
    # equals the midpoint that later appears, so a primary-price-only
    # signature would wait for the sweep. The devig proves on the midpoint.
    r, rec = build(monkeypatch, rows=lambda: board(".825", ".18"))
    book(rec, A, "0.00", ".18")
    assert rec.readers["steady_book_midpoint"](A) is None
    await r.refresh([1], flush_started=rec.clock.t)
    assert len(rec.updates) == 1 and set(r._book_refused) == {1}
    rig = consumer_flush(r)
    assert await quiet_flushes(rig, r, rec, 2) == [0, 0]
    book(rec, A, ".17", ".19")
    assert rec.readers["steady_book_primary_price"](A) == Decimal(".18")
    assert await quiet_flushes(rig, r, rec, 1) == [1]
    assert len(rec.updates) == 2 and not r._book_refused


@pytest.mark.asyncio
async def test_a_fresh_price_for_a_parked_pair_is_read_at_once(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    rec.clock.t += 1
    await r.refresh([1], flush_started=rec.clock.t)  # a committed new price
    assert rec.reads == [(1,), (1,)]
    assert set(r._book_refused) == {1}, "refused again, parked again"


@pytest.mark.asyncio
async def test_a_parked_pair_proven_by_its_fresh_price_leaves_the_parked_set(monkeypatch):
    # The stored price catches up with the book (a committed new price); the
    # book itself did not change, so only the fresh read can unpark it.
    stored = {"home": ".825"}
    r, rec = build(monkeypatch, rows=lambda: board(stored["home"]))
    mismatch(rec)  # book .80/.81, mid .805
    await r.refresh([1], flush_started=rec.clock.t)
    assert set(r._book_refused) == {1}
    stored["home"] = ".805"
    rec.clock.t += 1
    await r.refresh([1], flush_started=rec.clock.t)
    assert len(rec.updates) == 1 and not r._book_refused
    rig = consumer_flush(r)
    assert sum(await quiet_flushes(rig, r, rec, 25)) == 0
    assert len(rec.reads) == 2


@pytest.mark.asyncio
async def test_the_shared_sweep_reads_an_unchanged_parked_pair_once_per_period(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    rig = consumer_flush(r)
    work = await quiet_flushes(rig, r, rec, 25)  # 25 s, sweep 10 s
    assert sum(work) == 2 and len(rec.reads) == 3
    assert work.index(1) == int(BOOK_REFUSED_SWEEP_S) - 1
    assert set(r._book_refused) == {1}


# ── durable custody: recycle, failure, cancellation ─────────────────────────

@pytest.mark.asyncio
async def test_a_parked_pair_is_handed_off_and_read_once_by_the_next_run(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    assert 1 not in r.pending_event_ids()
    assert hand_off_pending(r) == 1
    nxt, rec2 = build(monkeypatch)
    rec2.clock.t = rec.clock.t
    assert adopt_handed_off(nxt) == 1 and 1 in nxt.pending_event_ids()
    rec2.clock.t += 1
    await nxt.refresh_pending(flush_started=rec2.clock.t)
    assert rec2.reads == [(1,)] and len(rec2.updates) == 1


@pytest.mark.asyncio
async def test_a_failed_batch_after_the_refusal_keeps_the_pair_owed(monkeypatch):
    r, rec = build(monkeypatch)
    mismatch(rec)
    real = LBR.LiveBlendRefresher._refresh_batch

    async def failing(self, ids, now, **kw):
        await real(self, ids, now, **kw)  # the refusal parks the pair
        raise RuntimeError("controlled transaction failure after the refusal")

    monkeypatch.setattr(LBR.LiveBlendRefresher, "_refresh_batch", failing)
    await r.refresh([1], flush_started=rec.clock.t)
    assert r.stats["bundled_refused"] == 1
    # The failed batch re-queues its events as before; parking adds nothing
    # that could drop it, and the ordinary failed-retry hold still applies.
    assert 1 in r.pending_event_ids()


def two_events(monkeypatch, stored):
    """Event 1 (Brooksby–Krueger, the refused pair) and event 2 (Smith–Jones,
    a proven pair) on one socket; event 2's UPDATE waits on `gate` while
    `hold` is set, so a call can be held running."""
    other = "KXATPCHALLENGERMATCH-26OCT19SMIJON"
    smi, jon = other + "-SMI", other + "-JON"
    r, rec = build(monkeypatch)
    rec.gate, rec.entered, rec.hold = asyncio.Event(), asyncio.Event(), True
    s = rec.sock
    s._book_requested = s.book_tickers = frozenset([H, A, smi, jon])
    book(rec, smi, ".60", ".62")
    book(rec, jon, ".38", ".40")
    rec.ns["game_clients"][0].tickers |= {smi, jon}
    rec.ns["ticker_to_ids"].update({smi: (2, 21), jon: (2, 22)})
    event2 = NS(**{**vars(rec.event), "id": 2, "home_team_name": "Smith",
                   "away_team_name": "Jones"})

    def board2():
        return board(".61", ".39", home_id=21, away_id=22, ticker=other,
                     home_ticker=smi, away_ticker=jon)

    names = {"Jenson Brooksby": "Smith", "Mitchell Krueger": "Jones"}

    async def groups(_session, ids):
        rec.reads.append(tuple(sorted(ids)))
        out = {}
        if 1 in ids:
            out[1] = (rec.event, board(stored["home"]))
        if 2 in ids:
            g = board2()
            for row in g[0].outcomes:
                row.name = names[row.name]
            g[0].market.id = 2
            g[0].market.name = "Smith vs Jones"
            out[2] = (event2, g)
        return out

    class Session:
        async def execute(self, stmt, *args, **kwargs):
            if isinstance(stmt, Update):
                if rec.hold:
                    rec.hold = False
                    rec.entered.set()
                    await rec.gate.wait()
                rec.updates.append(stmt)
                return NS(first=lambda: (
                    {"kalshi": {"value": .6, "updated_at": old.NOW.isoformat()}}, 1))
            return NS(scalar_one_or_none=lambda: None)

        def add(self, *args):
            pass

        async def flush(self):
            pass

        async def rollback(self):
            pass

        @asynccontextmanager
        async def begin_nested(self):
            yield

    @asynccontextmanager
    async def sessions():
        yield Session()

    monkeypatch.setattr(r, "_read_groups", groups)
    r._session_factory = sessions
    return r, rec


@pytest.mark.asyncio
async def test_cancelling_a_batch_after_the_refusal_keeps_both_events_owed(monkeypatch):
    # Event 1 is refused and parked; event 2's stamp is cancelled mid-UPDATE.
    r, rec = two_events(monkeypatch, {"home": ".825"})
    mismatch(rec)
    task = asyncio.create_task(r.refresh([1, 2], flush_started=rec.clock.t))
    await asyncio.wait_for(rec.entered.wait(), 2)
    assert set(r._book_refused) == {1}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert 2 in r.pending_event_ids()
    assert 1 in set(r.pending_event_ids()) | set(r._book_refused)


@pytest.mark.asyncio
async def test_a_running_call_admitting_a_parked_pair_unparks_it(monkeypatch):
    stored = {"home": ".825"}
    r, rec = two_events(monkeypatch, stored)
    mismatch(rec)  # mid .805
    rec.hold = False
    await r.refresh([1], flush_started=rec.clock.t)
    assert set(r._book_refused) == {1}
    rec.hold = True
    stored["home"] = ".805"  # the committed new price the next flush admits
    rec.clock.t += 1
    task = asyncio.create_task(r.refresh([2], flush_started=rec.clock.t))
    await asyncio.wait_for(rec.entered.wait(), 2)
    assert r.admit_fresh([1], flush_started=rec.clock.t) == {1}
    rec.gate.set()
    await asyncio.wait_for(task, 2)
    assert len(rec.updates) == 2 and not r._book_refused


@pytest.mark.asyncio
async def test_a_running_call_takes_a_pair_woken_while_it_runs(monkeypatch):
    r, rec = two_events(monkeypatch, {"home": ".825"})
    mismatch(rec)
    rec.hold = False
    await r.refresh([1], flush_started=rec.clock.t)
    assert set(r._book_refused) == {1}
    rec.hold = True
    rec.clock.t += 1
    task = asyncio.create_task(r.refresh([2], flush_started=rec.clock.t))
    await asyncio.wait_for(rec.entered.wait(), 2)
    book(rec, H, ".82", ".83")  # the book proves the stored .825 again
    # The next flush's fresh cohort joins the running call; the woken pair
    # rides it as owed debt instead of waiting for the call to return.
    rec.clock.t += 1
    assert r.admit_fresh([3], flush_started=rec.clock.t) == {3}
    assert r._admission.debt == 1 and 1 in r.holding_event_ids()
    rec.gate.set()
    await asyncio.wait_for(task, 2)
    assert (1,) in rec.reads[1:] and len(rec.updates) == 2
    assert not r._book_refused and 1 not in r.pending_event_ids()


# ── (c) proof-off and non-bundled paths are unchanged ───────────────────────

@pytest.mark.asyncio
async def test_proof_off_reads_without_refusal_or_parking(monkeypatch):
    r, rec = build(monkeypatch, proof=False)
    mismatch(rec)
    await r.refresh([1], flush_started=rec.clock.t)
    assert len(rec.updates) == 1 and not r._book_refused
    assert r.stats["bundled_refused"] == 0 and r.stats["no_reading"] == 0


@pytest.mark.asyncio
async def test_a_non_bundled_no_reading_is_not_parked_or_counted_as_refused(monkeypatch):
    # A Kalshi game market that is not the bundled Challenger pair: no proof
    # applies, its no-reading is an ordinary no-reading, nothing is parked.
    def nba():
        m = NS(id=1, source="kalshi", external_id="KXNBAGAME-26OCT19BOSNYK",
               name="Celtics vs Knicks", status="open", market_metadata={})
        return [MarketOutcomes(m, [], event_commence_time=old.NOW, event_has_result=False)]

    r, rec = build(monkeypatch, rows=nba)
    await r.refresh([1], flush_started=rec.clock.t)
    assert r.stats["no_reading"] == 1 and r.stats["bundled_refused"] == 0
    assert not r._book_refused and 1 not in r.pending_event_ids()


def test_the_minute_line_reports_refusals_and_parked_pairs():
    import inspect
    source = inspect.getsource(K)
    assert "bundled_refused=%d parked=%d" in source
    assert 'blend.get("bundled_refused", 0)' in source
