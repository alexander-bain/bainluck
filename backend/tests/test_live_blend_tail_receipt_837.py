"""#837 — a held price's receipt: received, stored, held, stamped, and QUIET only
if nothing else arrived for that event in between.

WHY THIS FILE EXISTS. The deferred-tail stamp (`_throttle_deferred`,
`_lock_retry`) is tested; what production could not show was, for ONE event,
which price the throttle held, when the socket received it, and whether the
stamp that finally carried it was the quiet flush or another tick. Codex's
review of the first receipt draft (2026-09-25 16:20Z,
`artifacts/chart-sprint-coordinator/morning-finish-20260925/
837-draft-receipt-counterexample.json`) reproduced the trap this file pins:

    refresh(event 1) @1000 · committed + held @1001 · another input @1003
    · refresh_pending @1006  ⇒  draft receipt: waited 6.0, quiet=True

The input at 1003 intervened, and the price was held 5s, not 6. The draft read
"quiet" off the FINAL flush's batch and "waited" off the previous refresh.

`TestTheCounterexample` is that sequence; `TestQuietControl` is its
non-vacuity partner (same shape, no second input ⇒ quiet=True), so a receipt
that printed quiet=False for everything could not pass both. The rest pin
the chain-ending cases Codex named: a same-price input that never reaches the
stored price, commit rollback, lock retries, recycle reset, bounded volume,
and the real consumer carrying receive marks into the refresh.
"""

import asyncio
import logging

import pytest
import websockets

import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task
from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts
from tests.test_live_blend_refresh import (
    _event_and_market,
    _LockedRowSession,
    _one_event_refresher,
)
from tests.test_ws_flush_retry_q491 import (
    EVENT_ID,
    NO_OUTCOME_ID,
    NO_TOKEN,
    POLY_SLATE,
    YES_OUTCOME_ID,
    YES_TOKEN,
    _install_slate,
    _poly_frame,
)

LOGGER = "app.tasks.live_blend_refresh"


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(blend_mod, "_mono", c)
    # Wall = monotonic + a fixed epoch offset: one clock, two domains.
    monkeypatch.setattr(blend_mod, "_wall", lambda: 1_758_816_000.0 + c.t)
    return c


def _receipts(caplog):
    """Every tail-receipt line as a dict of its key=value fields."""
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if "tail-receipt run=" not in msg:
            continue
        out.append(dict(
            kv.split("=", 1) for kv in msg.split("tail-receipt ", 1)[1].split()
        ))
    return out


def _summaries(caplog):
    return [r.getMessage() for r in caplog.records
            if "tail-receipt summary" in r.getMessage()]


def _refresher(outcomes=None):
    """A real refresher whose batch stamps without a database.

    `outcomes` maps a batch call number (1-based) to what it does: "stamp"
    (default), "unchanged", "lock", "commit_fail" (stamps, then the commit
    raises), "batch_fail" (raises before stamping).
    """
    r = LiveBlendRefresher("polymarket")
    r.receipts = TailReceipts("polymarket")
    outcomes = outcomes or {}
    calls = []

    async def _batch(event_ids, now):
        calls.append(sorted(event_ids))
        what = outcomes.get(len(calls), "stamp")
        for eid in event_ids:
            r._last_refresh_at[eid] = now
        if what == "batch_fail":
            raise RuntimeError("connection reset")
        for eid in event_ids:
            if what == "lock":
                r._dispositions[eid] = ("lock",)
                r._lock_retry.add(eid)
                r._last_refresh_at.pop(eid, None)
            elif what == "unchanged":
                r._dispositions[eid] = ("unchanged", 0.61)
            else:
                prev = r._last_written_value.get(eid)
                r._dispositions[eid] = (
                    "stamped", 0.61, f"stamp@{now}", prev,
                )
        if what == "commit_fail":
            raise RuntimeError("could not serialize access")
        for eid in event_ids:
            if r._dispositions.get(eid, ("",))[0] == "stamped":
                r._last_written_value[eid] = 0.61
                r._last_write_at[eid] = now

    r._refresh_batch = _batch
    return r, calls


async def _commit(r, clock, t, event_id=1, outcome_id=11, p=0.61):
    """One venue input at `t`, flushed and committed at `t`: what the socket
    does — note the input under the buffer lock, stage the committed revision,
    refresh."""
    clock.t = t
    mark = r.receipts.note_input(event_id, outcome_id, p, "price", "1758816000123")
    r.receipts.stage([mark])
    await r.refresh([event_id])
    return mark


@pytest.fixture(autouse=True)
def _info(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)


class TestTheCounterexample:
    @pytest.mark.asyncio
    async def test_an_input_inside_the_hold_is_not_quiet(self, clock, caplog):
        r, calls = _refresher()
        await _commit(r, clock, 1000.0)            # stamped at once
        first = await _commit(r, clock, 1001.0)    # held by the throttle
        second = await _commit(r, clock, 1003.0)   # intervenes, still held
        clock.t = 1006.0
        await r.refresh_pending()                  # the "quiet" flush

        assert calls == [[1], [1]]
        (rc,) = _receipts(caplog)
        assert rc["result"] == "stamped"
        assert rc["quiet"] == "False", rc
        assert rc["later_committed"] == "1"
        assert rc["later_inputs"] == "1"
        assert rc["rev_seq"] == str(first.seq)
        assert rc["stamp_rev_seq"] == str(second.seq), (
            "the stamp carried the later revision, and must say so"
        )
        assert rc["held_s"] == "5.000", (
            "held from the hold at 1001, not from the previous refresh at 1000"
        )
        assert rc["recv_to_close_s"] == "5.000"


class TestQuietControl:
    @pytest.mark.asyncio
    async def test_nothing_after_the_held_price_is_quiet(self, clock, caplog):
        r, _ = _refresher()
        await _commit(r, clock, 1000.0)
        held = await _commit(r, clock, 1001.0)
        clock.t = 1006.0
        await r.refresh_pending()

        (rc,) = _receipts(caplog)
        assert rc["result"] == "stamped" and rc["quiet"] == "True", rc
        assert rc["later_inputs"] == "0" and rc["later_committed"] == "0"
        assert rc["rev_seq"] == rc["stamp_rev_seq"] == str(held.seq)
        assert rc["rev_outcome"] == "11" and rc["rev_kind"] == "price"
        assert rc["rev_venue_ts_ms"] == "1758816000123"
        assert rc["origin"] == "throttle"
        assert rc["held_s"] == "5.000"
        # Dyno wall, ms precision, UTC; `stamped_at` is the batch's own value.
        assert rc["rev_recv_wall"].endswith("+00:00")
        assert rc["stamped_at"] == "stamp@1006.0"
        assert rc["moved"] == "False", "0.61 → 0.61 is a restamp, not a move"

    @pytest.mark.asyncio
    async def test_an_unheld_price_writes_no_receipt(self, clock, caplog):
        """Due at once ⇒ nothing was held ⇒ no chain. Receipts are for tails."""
        r, _ = _refresher()
        await _commit(r, clock, 1000.0)
        await _commit(r, clock, 1010.0)
        assert _receipts(caplog) == []


class TestASamePriceInputThatNeverReachesTheStore:
    @pytest.mark.asyncio
    async def test_it_still_breaks_quiet(self, clock, caplog):
        """A repeat of the held price, received but never committed (the
        buffer entry is removed as already written). `price_changed_at` cannot
        see it; the receipt must."""
        r, _ = _refresher()
        await _commit(r, clock, 1000.0)
        await _commit(r, clock, 1001.0)
        clock.t = 1003.0
        r.receipts.note_input(1, 11, 0.61, "trade", None)  # never staged
        clock.t = 1006.0
        await r.refresh_pending()

        (rc,) = _receipts(caplog)
        assert rc["quiet"] == "False", rc
        assert rc["later_inputs"] == "1" and rc["later_committed"] == "0"

    @pytest.mark.asyncio
    async def test_another_events_input_does_not(self, clock, caplog):
        r, _ = _refresher()
        await _commit(r, clock, 1000.0)
        await _commit(r, clock, 1001.0)
        clock.t = 1003.0
        r.receipts.note_input(2, 21, 0.4, "price", None)
        clock.t = 1006.0
        await r.refresh_pending()
        (rc,) = _receipts(caplog)
        assert rc["event"] == "1" and rc["quiet"] == "True", rc


class TestRollback:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["commit_fail", "batch_fail"])
    @pytest.mark.parametrize("fresh", [False, True])
    async def test_failed_stamp_retries_without_another_input(
        self, clock, caplog, failure, fresh,
    ):
        r, calls = _refresher({1 if fresh else 2: failure})
        if fresh:
            await _commit(r, clock, 1001.0)
        else:
            await _commit(r, clock, 1000.0)
            await _commit(r, clock, 1001.0)
            clock.t = 1006.0
            await r.refresh_pending()

        failed_at = clock.t
        assert _receipts(caplog) == [], "the retry chain must stay open"
        assert r._throttle_deferred == {1} and r._lock_retry == set()
        calls_before = len(calls)
        clock.t = failed_at + 2.0
        await r.refresh_pending()
        assert len(calls) == calls_before, "failures must respect the throttle"
        clock.t = failed_at + 5.0
        await r.refresh_pending()

        (rc,) = _receipts(caplog)
        assert rc["result"] == "stamped" and rc["quiet"] == "True"
        assert rc["origin"] == ("batch" if fresh else "throttle")
        assert rc["commit_failures"] == ("1" if failure == "commit_fail" else "0")
        assert rc["batch_failures"] == ("1" if failure == "batch_fail" else "0")
        assert rc["later_inputs"] == "0"
        assert rc["recv_to_close_s"] == ("5.000" if fresh else "10.000")
        assert r._throttle_deferred == set() and r._lock_retry == set()


class TestLockChains:
    @pytest.mark.asyncio
    async def test_a_lock_skip_opens_a_chain_the_retry_closes(self, clock, caplog):
        r, _ = _refresher({1: "lock"})
        mark = await _commit(r, clock, 1000.0)
        assert _receipts(caplog) == [], "a lock skip is not the end of the chain"
        clock.t = 1002.0
        await r.refresh([])  # next flush, quiet: the retry is due at once

        (rc,) = _receipts(caplog)
        assert rc["origin"] == "lock" and rc["result"] == "stamped", rc
        assert rc["lock_retries"] == "1"
        assert rc["rev_seq"] == str(mark.seq)
        assert rc["held_s"] == "2.000"

    @pytest.mark.asyncio
    async def test_a_retry_whose_commit_fails_stays_open_and_counts(
        self, clock, caplog,
    ):
        r, _ = _refresher({1: "lock", 2: "commit_fail"})
        await _commit(r, clock, 1000.0)
        clock.t = 1002.0
        await r.refresh([])          # retry stamps, commit fails, re-queued
        assert _receipts(caplog) == []
        assert r._lock_retry == {1}
        clock.t = 1004.0
        await r.refresh([])          # lands
        (rc,) = _receipts(caplog)
        assert rc["result"] == "stamped" and rc["commit_failures"] == "1", rc
        assert rc["batch_failures"] == "0" and rc["lock_retries"] == "1"

    @pytest.mark.asyncio
    async def test_the_real_batch_reports_the_lock(self, monkeypatch, caplog):
        """The disposition comes from the REAL `_refresh_batch`, not a fake."""
        event, market = _event_and_market()
        session = _LockedRowSession([(market, event)], [], {"polymarket": {}})
        r, published = _one_event_refresher(monkeypatch, session)
        r.receipts = TailReceipts("polymarket")
        r.receipts.stage([r.receipts.note_input(1, 11, 0.9, "price", None)])
        await r.refresh([1])
        assert r._dispositions == {1: ("lock",)}
        assert r.receipts._open[1].origin == "lock"

        session.locked = False
        session._selects = 0
        await r.refresh([])
        assert r._dispositions[1][0] == "stamped"
        assert r._dispositions[1][2] == published[0]["updated_at"], (
            "the receipt's stamped_at must be the instant the frame and the "
            "JSONB carry, or it cannot be joined to what was served"
        )
        (rc,) = _receipts(caplog)
        assert rc["result"] == "stamped" and rc["moved"] == "True", rc


class TestRecycle:
    @pytest.mark.asyncio
    async def test_an_open_chain_is_reported_at_recycle(self, clock, caplog):
        r, _ = _refresher()
        await _commit(r, clock, 1000.0)
        await _commit(r, clock, 1001.0)   # held; the run ends before it is due
        clock.t = 1003.0
        r.receipts.close_all("recycle_reset")

        (rc,) = _receipts(caplog)
        assert rc["result"] == "recycle_reset" and rc["stamped_at"] == "None"
        (summary,) = _summaries(caplog)
        assert "reason=recycle_reset" in summary and "open_at_close=1" in summary
        assert f"run={r.receipts.run}" in summary

    def test_a_run_with_nothing_open_still_says_it_ran(self, caplog):
        TailReceipts("polymarket").close_all("recycle_reset")
        (summary,) = _summaries(caplog)
        assert "inputs=0" in summary and "open_at_close=0" in summary


class TestVolumeIsBoundedWithoutDroppingTheQualifyingChain:
    @pytest.mark.asyncio
    async def test_routine_chains_coalesce_per_event(self, clock, caplog):
        r, _ = _refresher({2: "unchanged", 4: "unchanged", 6: "unchanged"})
        t = 1000.0
        for _ in range(3):                      # three unchanged chains, 20s apart
            await _commit(r, clock, t)
            await _commit(r, clock, t + 1)
            clock.t = t + 6
            await r.refresh_pending()
            t += 20
        lines = _receipts(caplog)
        assert [x["result"] for x in lines] == ["unchanged"], lines
        assert r.receipts.stats["coalesced"] == 2

        clock.t = 1100.0                        # past the coalesce window
        await _commit(r, clock, 1100.0)
        await _commit(r, clock, 1101.0)
        clock.t = 1106.0
        await r.refresh_pending()
        last = _receipts(caplog)[-1]
        assert last["coalesced"] == "2", "the count of what was summarised"

    @pytest.mark.asyncio
    async def test_quiet_stamps_are_never_coalesced(self, clock, caplog):
        r, _ = _refresher()
        t = 1000.0
        for _ in range(4):                      # four quiet tails in 80s
            await _commit(r, clock, t)
            await _commit(r, clock, t + 1)
            clock.t = t + 6
            await r.refresh_pending()
            t += 20
        lines = _receipts(caplog)
        assert len(lines) == 4 and all(x["quiet"] == "True" for x in lines)
        assert r.receipts.stats["coalesced"] == 0


class TestTheReceiptIsNeverPartOfThePricePath:
    @pytest.mark.asyncio
    async def test_a_failing_receipt_costs_no_stamp(self, clock, caplog):
        r, calls = _refresher()

        def _boom(*_a):
            raise ValueError("receipt bug")

        r.receipts.observe = _boom
        r.receipts.resolve = _boom
        await _commit(r, clock, 1000.0)
        assert calls == [[1]] and r._last_written_value == {1: 0.61}

    @pytest.mark.asyncio
    async def test_no_receipts_attached_is_the_old_refresher(self, clock, caplog):
        """The Kalshi arm attaches none; it must log and behave as before."""
        r, calls = _refresher()
        r.receipts = None
        clock.t = 1000.0
        await r.refresh([1])
        clock.t = 1001.0
        await r.refresh([1])
        clock.t = 1006.0
        await r.refresh_pending()
        assert calls == [[1], [1]]
        assert _receipts(caplog) == [] and _summaries(caplog) == []


# ------------------------------------------------ the real consumer ----


class _TimedFrames:
    """Frames with delays, so a second input lands AFTER the first flush."""

    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            delay, frame = self._frames.pop(0)
            await asyncio.sleep(delay)
            return frame
        await asyncio.sleep(3600)
        raise StopAsyncIteration  # pragma: no cover


def _install_timed_socket(monkeypatch, frames):
    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self):
                return _TimedFrames(frames)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()

    monkeypatch.setattr(websockets, "connect", _connect)


async def _run_consumer(monkeypatch, frames, throttle=0.5, recycle=1.5):
    """The REAL consumer and the REAL refresher bookkeeping; only the socket,
    the slate/price session and the blend batch's database are faked."""
    seen: dict = {}

    class _Recording(LiveBlendRefresher):
        def __init__(self, source, **kw):
            super().__init__(source, min_refresh_interval_s=throttle, **kw)
            seen["refresher"] = self

        async def _refresh_batch(self, event_ids, now):
            for eid in event_ids:
                self._last_refresh_at[eid] = now
                self._dispositions[eid] = (
                    "stamped", 0.7, f"stamp@{now:.3f}",
                    self._last_written_value.get(eid),
                )
                self._last_written_value[eid] = 0.7
                self._last_write_at[eid] = now

    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Recording)
    _install_timed_socket(monkeypatch, frames)
    writes: list = []
    _install_slate(monkeypatch, POLY_SLATE, writes,
                   {"fail_writes": 0, "failed": 0})
    await poly_task._run_polymarket_ws_consumer()
    return seen["refresher"], writes


class TestTheRealConsumerCarriesTheReceiveMark:
    @pytest.mark.asyncio
    async def test_a_quiet_held_price_is_receipted_end_to_end(
        self, monkeypatch, caplog,
    ):
        frames = [
            (0.0, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68",
                              best_ask="0.72", timestamp="1758816000001")),
            (0.1, _poly_frame("best_bid_ask", NO_TOKEN, best_bid="0.27",
                              best_ask="0.29", timestamp="1758816000102")),
        ]
        r, writes = await _run_consumer(monkeypatch, frames)

        assert {oid for oid, _ in writes} == {YES_OUTCOME_ID, NO_OUTCOME_ID}
        lines = [x for x in _receipts(caplog) if x["result"] == "stamped"]
        assert len(lines) == 1, _receipts(caplog)
        (rc,) = lines
        assert rc["event"] == str(EVENT_ID) and rc["quiet"] == "True", rc
        assert rc["rev_outcome"] == str(NO_OUTCOME_ID)
        assert rc["rev_seq"] == "2" and rc["rev_venue_ts_ms"] == "1758816000102"
        assert rc["run"] == r.receipts.run
        (summary,) = _summaries(caplog)
        assert "reason=recycle_reset" in summary and "inputs=2" in summary

    @pytest.mark.asyncio
    async def test_a_same_price_repeat_inside_the_hold_breaks_quiet(
        self, monkeypatch, caplog,
    ):
        frames = [
            (0.0, _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68",
                              best_ask="0.72")),
            (0.1, _poly_frame("best_bid_ask", NO_TOKEN, best_bid="0.27",
                              best_ask="0.29")),
            (0.1, _poly_frame("last_trade_price", NO_TOKEN, price="0.28")),
        ]
        await _run_consumer(monkeypatch, frames)
        lines = [x for x in _receipts(caplog) if x["result"] == "stamped"]
        assert len(lines) == 1, _receipts(caplog)
        (rc,) = lines
        assert rc["quiet"] == "False", rc
        assert rc["later_inputs"] == "1"
        assert rc["rev_seq"] == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["stamp", "commit_fail"])
async def test_receipt_elapsed_time_includes_awaited_batch(clock, caplog, finish):
    r, _ = _refresher({2: finish})
    await _commit(r, clock, 1000.0)
    await _commit(r, clock, 1001.0)
    original_batch = r._refresh_batch

    async def slow_batch(event_ids, now):
        try:
            await original_batch(event_ids, now)
        finally:
            # Work or commit failure completes twenty seconds after dispatch.
            clock.t += 20.0

    r._refresh_batch = slow_batch
    clock.t = 1006.0
    await r.refresh_pending()

    if finish == "commit_fail":
        assert _receipts(caplog) == []
        assert r.receipts._open[1].commit_failures == 1
        # Failed work is now retained. A shutdown records its elapsed hold.
        r.receipts.close_all("shutdown")
    (receipt,) = _receipts(caplog)
    assert receipt["result"] == ("stamped" if finish == "stamp" else "shutdown")
    assert receipt["held_s"] == "25.000"
    assert receipt["recv_to_close_s"] == "25.000"


@pytest.mark.asyncio
async def test_fresh_failed_attempt_opens_hold_at_completion(clock, caplog):
    r, _ = _refresher()
    successful_batch = r._refresh_batch

    async def slow_failure(event_ids, now):
        for event_id in event_ids:
            r._last_refresh_at[event_id] = now
        clock.t += 20.0
        raise RuntimeError("connection reset after awaited work")

    r._refresh_batch = slow_failure
    await _commit(r, clock, 1001.0)
    assert r.receipts._open[1].opened_mono == 1021.0
    r._refresh_batch = successful_batch
    clock.t = 1026.0
    await r.refresh_pending()
    (receipt,) = _receipts(caplog)
    assert receipt["origin"] == "batch"
    assert receipt["held_s"] == "5.000"
    assert receipt["recv_to_close_s"] == "25.000"


@pytest.mark.asyncio
async def test_new_lock_in_failed_batch_keeps_its_lock_origin(clock, caplog):
    r, _ = _refresher()
    successful_batch = r._refresh_batch

    async def lock_then_failed_commit(event_ids, now):
        r._dispositions[1] = ("lock",)
        r._lock_retry.add(1)
        raise RuntimeError("batch commit failed after another row was locked")

    r._refresh_batch = lock_then_failed_commit
    await _commit(r, clock, 1000.0)
    assert r._lock_retry == {1}
    r._refresh_batch = successful_batch
    clock.t = 1002.0
    await r.refresh_pending()
    (receipt,) = _receipts(caplog)
    assert receipt["origin"] == "lock"
    assert receipt["lock_retries"] == "1"
    assert receipt["batch_failures"] == "1"
    assert receipt["result"] == "stamped"
