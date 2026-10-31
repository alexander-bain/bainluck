"""#10090 `price_commit_ack_wall` — when the price transaction carrying a tail
receipt's held input returned, so receive -> staging splits into receive ->
COMMIT acknowledgement and acknowledgement -> offer.

PILLARS: TRUTH. SHIP: a reader holding a live game sees each new Polymarket
price confirmed within about a second; this field says where the slow ones
(p50 1.05 s, p90 6.2 s vs Kalshi's 0.28 / 0.49) wait, so the fix is aimed.

Argon's rules (RETURN-argon-20261031T055920Z, Part B), one test class each:
the clock binds to the exact original input; it survives a later superseding
write and a newer quote never fills it; an overlay offer that precedes the
acknowledgement keeps that order; it is None for overlay-only, skipped,
non-returning, unmatched or unacknowledged inputs; ``PRICE_COMMIT_ACK_LOG=0``
prints today's line. The writer seams run the SHIPPED write_chunk, bridged
writer and Kalshi flush with fake sessions: control flow, not latency.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks.live_blend_refresh import (
    PRICE_COMMIT_ACK_EVENTS,
    PRICE_COMMIT_ACK_PER_EVENT,
    TailReceipts,
    _iso,
    note_price_commit_ack,
)

LOGGER = "app.tasks.live_blend_refresh"
EPOCH = 1_761_879_600.0  # 2026-10-31 03:00:00Z
NOW = datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(blend_mod, "_mono", c)
    monkeypatch.setattr(blend_mod, "_wall", lambda: EPOCH + c.t)
    monkeypatch.delenv("PRICE_COMMIT_ACK_LOG", raising=False)
    return c


def _lines(caplog):
    return [r.getMessage() for r in caplog.records
            if "tail-receipt run=" in r.getMessage()]


def _fields(line):
    return dict(kv.split("=", 1) for kv in line.split("tail-receipt ", 1)[1].split())


def _stamped(event_id):
    return {event_id: ("stamped", 0.61, "2026-10-31T03:00:09.000+00:00", 0.55)}


def _held_then_stamped(receipts, clock, mark, *, later=(), ack_after_open=None):
    """Offer ``mark`` while the throttle holds its event (a chain opens), let
    ``later`` marks commit inside the hold, then a due stamp closes it."""
    event_id = mark.event_id
    receipts.observe({event_id: mark}, EPOCH + clock.t, set(), clock.t)
    if ack_after_open is not None:
        clock.t += 0.5
        receipts.note_commit_ack([mark], ack_after_open)
    for newer in later:
        clock.t += 0.5
        receipts.observe({event_id: newer}, EPOCH + clock.t, set(), clock.t)
    clock.t += 1.0
    receipts.resolve({event_id}, _stamped(event_id), {}, EPOCH + clock.t, clock.t)


class TestExactBinding:
    def test_the_held_inputs_own_acknowledgement_is_printed(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        other_game = receipts.note_input(2, 21, 0.40, "price")
        clock.t += 0.2
        receipts.note_commit_ack([other_game], EPOCH + 100.1)
        receipts.note_commit_ack([held], EPOCH + 100.2)
        clock.t += 3.0
        _held_then_stamped(receipts, clock, held)
        [line] = _lines(caplog)
        fields = _fields(line)
        assert fields["rev_seq"] == str(held.seq) and fields["event"] == "1"
        assert fields["price_commit_ack_wall"] == _iso(EPOCH + 100.2)
        # The ack precedes the offer: persistence and offering are now apart.
        assert fields["price_commit_ack_wall"] < fields["stored_wall"]

    def test_an_acknowledgement_of_another_input_of_the_game_is_not_its_own(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        older = receipts.note_input(1, 11, 0.60, "price")
        held = receipts.note_input(1, 12, 0.39, "price")
        receipts.note_commit_ack([older], EPOCH + 100.1)
        _held_then_stamped(receipts, clock, held)
        [line] = _lines(caplog)
        assert _fields(line)["price_commit_ack_wall"] == "None"

    def test_a_second_acknowledgement_of_the_same_input_keeps_the_first(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        receipts.note_commit_ack([held], EPOCH + 100.1)
        receipts.note_commit_ack([held], EPOCH + 100.9)
        _held_then_stamped(receipts, clock, held)
        [line] = _lines(caplog)
        assert _fields(line)["price_commit_ack_wall"] == _iso(EPOCH + 100.1)


class TestSupersession:
    def test_a_later_write_inside_the_hold_keeps_the_originals_clock(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        receipts.note_commit_ack([held], EPOCH + 100.1)
        newer = receipts.note_input(1, 11, 0.63, "price")
        receipts.note_commit_ack([newer], EPOCH + 100.4)
        _held_then_stamped(receipts, clock, held, later=[newer])
        [line] = _lines(caplog)
        fields = _fields(line)
        assert fields["stamp_rev_seq"] == str(newer.seq)
        assert fields["later_committed"] == "1"
        assert fields["price_commit_ack_wall"] == _iso(EPOCH + 100.1)

    def test_a_newer_quote_never_fills_an_unacknowledged_original(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")  # overlay-only: never acked
        newer = receipts.note_input(1, 11, 0.63, "price")
        receipts.note_commit_ack([newer], EPOCH + 100.4)
        _held_then_stamped(receipts, clock, held, later=[newer])
        [line] = _lines(caplog)
        assert _fields(line)["stamp_rev_seq"] == str(newer.seq)
        assert _fields(line)["price_commit_ack_wall"] == "None"

    def test_a_newer_acknowledgement_arriving_after_the_offer_is_not_the_originals(
        self, clock, caplog,
    ):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        newer = receipts.note_input(1, 11, 0.63, "price")
        receipts.observe({1: held}, EPOCH + clock.t, set(), clock.t)
        receipts.note_commit_ack([newer], EPOCH + 100.4)
        clock.t += 1.0
        receipts.resolve({1}, _stamped(1), {}, EPOCH + clock.t, clock.t)
        [line] = _lines(caplog)
        assert _fields(line)["price_commit_ack_wall"] == "None"


    def test_the_superseding_writes_own_late_acknowledgement_is_not_the_originals(
        self, clock, caplog,
    ):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        newer = receipts.note_input(1, 11, 0.63, "price")
        receipts.observe({1: held}, EPOCH + clock.t, set(), clock.t)
        clock.t += 0.5
        receipts.observe({1: newer}, EPOCH + clock.t, set(), clock.t)  # stamp_rev
        receipts.note_commit_ack([newer], EPOCH + clock.t + 0.1)
        clock.t += 1.0
        receipts.resolve({1}, _stamped(1), {}, EPOCH + clock.t, clock.t)
        [line] = _lines(caplog)
        assert _fields(line)["stamp_rev_seq"] == str(newer.seq)
        assert _fields(line)["price_commit_ack_wall"] == "None"


class TestOverlayFirstOrder:
    def test_an_offer_before_the_commit_keeps_that_real_order(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        clock.t += 0.1
        _held_then_stamped(receipts, clock, held, ack_after_open=EPOCH + 100.6)
        [line] = _lines(caplog)
        fields = _fields(line)
        assert fields["price_commit_ack_wall"] == _iso(EPOCH + 100.6)
        # Offered (stored_wall) first, acknowledged after: not rewritten.
        assert fields["stored_wall"] < fields["price_commit_ack_wall"]

    def test_an_acknowledgement_after_the_chain_closed_never_reaches_the_next_chain(
        self, clock, caplog,
    ):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        first = receipts.note_input(1, 11, 0.61, "price")
        _held_then_stamped(receipts, clock, first)
        receipts.note_commit_ack([first], EPOCH + clock.t)  # late
        second = receipts.note_input(1, 11, 0.64, "price")
        clock.t += 1.0
        _held_then_stamped(receipts, clock, second)
        assert [_fields(line)["price_commit_ack_wall"] for line in _lines(caplog)] == [
            "None", "None",
        ]

    def test_a_lock_chain_opened_after_a_due_stamp_takes_its_inputs_ack(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        mark = receipts.note_input(1, 11, 0.61, "price")
        receipts.note_commit_ack([mark], EPOCH + 100.1)
        # Due at once: no throttle chain; the read skips a locked row.
        receipts.observe({1: mark}, EPOCH + 100.2, {1}, clock.t)
        receipts.resolve({1}, {1: ("lock",)}, {1: mark}, EPOCH + 100.2, clock.t)
        clock.t += 1.0
        receipts.resolve({1}, _stamped(1), {1: mark}, EPOCH + clock.t, clock.t)
        [line] = _lines(caplog)
        assert _fields(line)["origin"] == "lock"
        assert _fields(line)["price_commit_ack_wall"] == _iso(EPOCH + 100.1)


class TestNullCases:
    def test_unacknowledged_is_none(self, clock, caplog):
        caplog.set_level(logging.INFO, logger=LOGGER)
        receipts = TailReceipts("polymarket")
        held = receipts.note_input(1, 11, 0.61, "price")
        _held_then_stamped(receipts, clock, held)
        assert _fields(_lines(caplog)[0])["price_commit_ack_wall"] == "None"

    def test_unmatched_inputs_and_no_clock_record_nothing(self, clock):
        receipts = TailReceipts("polymarket")
        assert receipts.note_input(None, 11, 0.61, "price") is None
        receipts.note_commit_ack([None], EPOCH)
        held = receipts.note_input(1, 11, 0.61, "price")
        note_price_commit_ack(receipts, [held], None)  # switch off / no ack
        note_price_commit_ack(None, [held], EPOCH)  # no receipts wired
        assert receipts._commit_acks == {}

    def test_a_failing_receipt_never_raises_into_the_writer(self, clock, caplog):
        caplog.set_level(logging.WARNING, logger=LOGGER)
        note_price_commit_ack(Row(), [object()], EPOCH)
        assert "price commit ack failed" in caplog.text


class TestBounded:
    def test_waiting_acknowledgements_are_capped_per_event_and_in_all(self, clock):
        receipts = TailReceipts("polymarket")
        marks = [receipts.note_input(1, 11, 0.5, "price")
                 for _ in range(PRICE_COMMIT_ACK_PER_EVENT + 5)]
        receipts.note_commit_ack(marks, EPOCH)
        assert sorted(receipts._commit_acks[1]) == [
            m.seq for m in marks[-PRICE_COMMIT_ACK_PER_EVENT:]
        ]
        for event_id in range(2, PRICE_COMMIT_ACK_EVENTS + 10):
            receipts.note_commit_ack([receipts.note_input(event_id, 1, 0.5, "price")], EPOCH)
        assert len(receipts._commit_acks) == PRICE_COMMIT_ACK_EVENTS
        assert 1 not in receipts._commit_acks  # the oldest event went first

    def test_staging_a_newer_input_drops_the_superseded_ones(self, clock):
        receipts = TailReceipts("polymarket")
        old = receipts.note_input(1, 11, 0.5, "price")
        new = receipts.note_input(1, 11, 0.6, "price")
        receipts.note_commit_ack([old, new], EPOCH)
        receipts.observe({1: new}, EPOCH, {1}, clock.t)  # due: no chain opens
        assert receipts._commit_acks == {1: {new.seq: EPOCH}}

    def test_close_all_forgets_them(self, clock):
        receipts = TailReceipts("polymarket")
        receipts.note_commit_ack([receipts.note_input(1, 11, 0.5, "price")], EPOCH)
        receipts.close_all("shutdown")
        assert receipts._commit_acks == {}


class TestSwitchOff:
    def _scenario(self, clock, caplog):
        caplog.clear()
        clock.t = 100.0
        receipts = TailReceipts("polymarket")
        receipts.run = "fixedrun"
        held = receipts.note_input(1, 11, 0.61, "price")
        receipts.note_commit_ack([held], EPOCH + 100.1)
        _held_then_stamped(receipts, clock, held)
        [line] = _lines(caplog)
        return line

    def test_off_prints_todays_line_byte_for_byte(self, clock, caplog, monkeypatch):
        caplog.set_level(logging.INFO, logger=LOGGER)
        on = self._scenario(clock, caplog)
        monkeypatch.setenv("PRICE_COMMIT_ACK_LOG", "0")
        off = self._scenario(clock, caplog)
        assert "price_commit_ack_wall" not in off
        assert on.replace(f" price_commit_ack_wall={_iso(EPOCH + 100.1)}", "") == off
        assert "error=None" in off and off.endswith("error=None")


# ------------------------------------------------------------ the PM writers


def _pm_game_flush(*, skipped=(), during_write=None):
    """The SHIPPED `write_chunk` in the PM game flush rig
    (`test_preview_from_commit_10090._pm_writer`), its UPDATE returning rows."""
    from app.tasks.polymarket_ws import _PMPriceWriteResult
    from tests.test_polymarket_withdrawal_speed_10651 import ROOT, compile_functions
    from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig

    r = pm_rig(batch={1: 0.6, 2: 0.4}, books={})
    acks = []

    class Session:
        def __init__(self):
            self.info = {}

        async def execute(self, statement, params=None):
            if isinstance(statement, tuple) and statement[0] == "prices":
                if during_write is not None:
                    during_write(r)
                return Row(all=lambda: [
                    Row(id=oid, ord=i, market_id=10, quote_moved=True, last_updated=NOW,
                        current_probability=Decimal(str(value)), is_winner=False,
                        resolution_source=None, database_clock=NOW,
                        skipped=oid in skipped)
                    for i, (oid, value) in enumerate(statement[1].items())
                ])
            return Row(rowcount=1)

    @asynccontextmanager
    async def session():
        yield Session()
        r.trace.append(("commit", None))

    class Refresher:
        async def publish_market_changes(self, session):
            r.trace.append(("market", None))

        def pending_event_ids(self):
            return frozenset()

        async def refresh(self, ids, **kwargs):
            r.trace.append(("refresh", sorted(ids)))

        async def refresh_pending(self, **kwargs):
            pass

        def note_committed_rows(self, rows):
            r.trace.append(("noted", None))

    def note_commit_ack(marks, wall):
        acks.append((list(marks), wall))

    r.ns["tail_receipts"].note_commit_ack = note_commit_ack
    r.ns.update(
        get_task_session=session, blend_refresher=Refresher(),
        _PMPriceWriteResult=_PMPriceWriteResult,
        chunk_price_update_execution=lambda chunk, **kw: (("prices", chunk), {}),
        pm_rerank_market_fields_execution=lambda ids: (
            r.ns["rerank_market_fields_stmt"](ids), {}
        ),
    )
    compile_functions(ROOT / "app/tasks/polymarket_ws.py", ["write_chunk"], r.ns)
    return r, acks


@pytest.fixture
def seam_clock(monkeypatch):
    """`_wall` as write_chunk imports it: each sample is traced."""
    holder = {"trace": None, "n": 0}

    def wall():
        holder["n"] += 1
        if holder["trace"] is not None:
            holder["trace"].append(("ack-clock", holder["n"]))
        return EPOCH + holder["n"]

    monkeypatch.setattr(blend_mod, "_wall", wall)
    monkeypatch.delenv("PRICE_COMMIT_ACK_LOG", raising=False)
    return holder


class TestPolymarketGameFlush:
    async def test_sampled_after_commit_before_publication_for_the_written_rows(
        self, seam_clock,
    ):
        r, acks = _pm_game_flush()
        seam_clock["trace"] = r.trace
        await r.ns["flush_prices"]()
        [(marks, wall)] = acks
        assert marks == [1, 2]  # the rig's marks are the outcome ids
        [clock_at] = [i for i, entry in enumerate(r.trace) if entry[0] == "ack-clock"]
        assert wall == EPOCH + r.trace[clock_at][1]
        # Before the preview hand-over, so before any publication can yield.
        assert r.trace.index(("commit", None)) < clock_at < r.trace.index(("noted", None))

    async def test_a_row_held_back_by_a_lock_is_not_acknowledged(self, seam_clock):
        r, acks = _pm_game_flush(skipped={2})
        await r.ns["flush_prices"]()
        assert [marks for marks, _ in acks] == [[1]]

    async def test_a_newer_quote_buffered_during_the_write_never_takes_the_clock(
        self, seam_clock,
    ):
        def newer(r):
            r.ns["input_marks"][1] = "newer-quote"

        r, acks = _pm_game_flush(during_write=newer)
        await r.ns["flush_prices"]()
        assert [marks for marks, _ in acks] == [[1, 2]]

    async def test_off_samples_nothing_and_records_nothing(self, seam_clock, monkeypatch):
        monkeypatch.setenv("PRICE_COMMIT_ACK_LOG", "0")
        r, acks = _pm_game_flush()
        seam_clock["trace"] = r.trace
        await r.ns["flush_prices"]()
        assert acks == []
        assert not [entry for entry in r.trace if entry[0] == "ack-clock"]


class TestPolymarketBridgedWriter:
    async def _run(self, *, written, wall, newer_during_write=False):
        from app.tasks import polymarket_ws as pm

        boundary = pm._PMCatalogFlushBoundary()
        acks = []
        boundary.bridges.receipts = Row(
            note_commit_ack=lambda marks, at: acks.append((list(marks), at)),
        )
        buffer = {700: 0.4, 701: 0.6}
        input_marks = {700: "mark-700", 701: "mark-701"}

        async def write(chunk, *, start_market_publish=None):
            if newer_during_write:
                input_marks[700] = "newer-700"
            if start_market_publish is not None:
                start_market_publish(object())
            return pm._PMPriceWriteResult(written, commit_ack_wall=wall)

        async def publish(session):
            return 0

        boundary.bridges.offer(
            list(buffer), {7}, write=write, publish=publish,
            side_writer=boundary.side_writer, buffer_lock=asyncio.Lock(),
            price_buffer=buffer, input_marks=input_marks,
        )
        await asyncio.wait_for(boundary.bridges.join(), 1)
        return acks

    async def test_binds_the_cohorts_frozen_marks_for_its_written_rows(self):
        acks = await self._run(written=[701], wall=EPOCH + 3, newer_during_write=True)
        assert acks == [(["mark-701"], EPOCH + 3)]

    async def test_a_newer_quote_during_the_write_is_not_the_cohorts(self):
        acks = await self._run(written=[700, 701], wall=EPOCH + 3, newer_during_write=True)
        assert acks == [(["mark-700", "mark-701"], EPOCH + 3)]

    async def test_no_clock_records_nothing(self):
        assert await self._run(written=[700, 701], wall=None) == []


# ---------------------------------------------------------- the Kalshi writer


class TestKalshiParity:
    async def _flush(self, monkeypatch, *, off=False, declined=9):
        from tests.test_kalshi_game_isolation_10655 import rig as kalshi_rig

        if off:
            monkeypatch.setenv("PRICE_COMMIT_ACK_LOG", "0")
        else:
            monkeypatch.delenv("PRICE_COMMIT_ACK_LOG", raising=False)
        r = kalshi_rig(declined=declined)
        r.release.set()
        acks = []

        def note_commit_ack(marks, wall):
            acks.append((list(marks), wall))
            r.trace.append(("ack", tuple(marks)))

        r.ns["tail_receipts"].note_commit_ack = note_commit_ack
        real_execute_factory = r.ns["get_task_session"]

        @asynccontextmanager
        async def session():
            async with real_execute_factory() as s:
                real = s.execute

                async def execute(stmt, bind=None):
                    result = await real(stmt, bind)
                    # A newer input lands while game 200's write is in flight.
                    if r.trace and r.trace[-1] == ("write", 3):
                        async with r.ns["buffer_lock"]:
                            r.batch[3] = (.85, .84, .86)
                            r.ns["input_marks"][3] = "newer-than-the-write"
                    return result

                s.execute = execute
                yield s

        r.ns["get_task_session"] = session
        try:
            assert await asyncio.wait_for(r.flush(), 2) is True
        finally:
            r.ns["prices"].close()
        return r, acks

    async def test_each_committed_phase_acknowledges_its_returned_rows_after_commit(
        self, monkeypatch,
    ):
        r, acks = await self._flush(monkeypatch)
        assert r.ns["input_marks"][3] == "newer-than-the-write"  # the race ran
        assert [marks for marks, _ in acks] == [[1, 2], [3]]
        # After that phase's COMMIT, before its publication.
        assert r.trace.index(("commit", (1, 2))) < r.trace.index(("ack", (1, 2)))
        assert r.trace.index(("ack", (1, 2))) < r.trace.index(("publish", (1, 2)))
        # Declined (9) returned no row: not acknowledged; the newer input
        # buffered during game 200's write never takes its clock.
        assert all(9 not in marks and "newer-than-the-write" not in marks
                   for marks, _ in acks)

    async def test_a_row_the_phase_did_not_return_is_not_acknowledged(self, monkeypatch):
        _r, acks = await self._flush(monkeypatch, declined=2)
        assert [marks for marks, _ in acks][0] == [1]

    async def test_off_records_nothing(self, monkeypatch):
        _r, acks = await self._flush(monkeypatch, off=True)
        assert acks == []
