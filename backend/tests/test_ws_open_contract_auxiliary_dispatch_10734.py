"""#10734 — an open-contract connection keeps reading quotes while one leg grades.

THE SHIP. An open-contract (auxiliary) Kalshi connection awaited the per-leg
grader (#10022) inline, so every quote behind a settlement frame on that
connection — for any contract at all — waited for the grade's database round
trip before it could enter the price buffer. The linked game socket already
defers its settlement through the #10667 dispatcher; this opts the auxiliary
connections into the same dispatcher, and only where that is safe.

WHAT KEEPS IT SAFE. The dispatcher serializes by the ticker prefix before the
last dash, per connection. The per-leg grader decides whether a board resolves
with a ``NOT EXISTS`` over sibling legs, so two legs of one market must never
grade concurrently. ``prepared_shard_indexes`` admits a connection only when
every ticker on it maps to a market whose admitted tickers share ONE prefix and
that prefix lives on ONE connection; anything else keeps the inline callback.

THE CASES (the real consumer through the #9484 recording socket):

    unrelated_quote_lands ........ THE SHIP. While SD20's grade is held, an
                                   unrelated contract's quote is accepted; the
                                   same board's later quote and settlement wait.
    inline_control ............... The same frames with admission refused: the
                                   unrelated quote waits for the grade (the old
                                   behaviour; proves the case above can fail).
    split / ambiguous cohorts .... A prefix split over two connections, or a
                                   market spanning two prefixes, stays inline.
    failed grade / recycle ....... A grader error is counted and the tail goes
                                   on; a recycle cancels a held grade and leaves
                                   no task behind.
    undo switch / linked frame ... ``WS_OPEN_CONTRACT_SETTLEMENT=0`` grades
                                   nothing; a linked-slate frame on a prepared
                                   connection is still not the shard's.

Final database state (terminal 0/1, last-leg-only resolution, the #5411
refusal of a late quote, commit before publication) is asserted on real
Postgres in ``tests/integration/test_open_contract_deferred_grade_pg_10734.py``.
"""

import asyncio

import pytest

import app.services.kalshi_ws as service
import app.tasks.live_blend_refresh as blend_mod
from app.tasks import ws_open_contracts as oc
from tests.test_ws_open_contract_prices_9484 import (
    LINKED_TICKER,
    OPEN_TICKER,
    _run,
    _settle,
    _tick,
)
from tests.test_ws_open_contract_settlement_10022 import (
    SD20,
    SD21,
    _recording_changes,
    _recording_grader,
)

BOARD = 62713436
SD20_ID, SD21_ID = 236765872, 236765873
OPEN_ID = 501

BOARD_ROWS = [(SD20, BOARD, SD20_ID), (SD21, BOARD, SD21_ID), (OPEN_TICKER, 50, OPEN_ID)]


def _record_wiring(monkeypatch):
    """(tickers, prepared?) for every connection the consumer opened."""
    wiring = []
    original = service.KalshiWebSocket.run

    async def run(self, *a, **kw):
        wiring.append((kw.get("market_tickers"), self.on_lifecycle_prepare is not None))
        return await original(self, *a, **kw)

    monkeypatch.setattr(service.KalshiWebSocket, "run", run)
    return wiring


def _record_accepted(monkeypatch, watch=OPEN_ID):
    """Every price the consumer accepted into its buffer, in order."""
    accepted, seen = [], asyncio.Event()
    original = blend_mod.TailReceipts.note_input

    def note_input(self, event, outcome, probability, origin):
        accepted.append((outcome, probability))
        if outcome == watch:
            seen.set()
        return original(self, event, outcome, probability, origin)

    monkeypatch.setattr(blend_mod.TailReceipts, "note_input", note_input)
    return accepted, seen


def _hold(monkeypatch, outcome_id):
    """Hold ``outcome_id``'s grade until released; other legs grade at once."""
    graded = oc.grade_open_contract_leg
    entered, release = asyncio.Event(), asyncio.Event()

    async def grade(session, **kw):
        if kw["outcome_id"] == outcome_id:
            entered.set()
            await release.wait()
        return await graded(session, **kw)

    monkeypatch.setattr(oc, "grade_open_contract_leg", grade)
    return entered, release


SHIP_FRAMES = [
    _tick(SD21, bid="0.40", ask="0.42", price="0.41"),
    _settle(SD20),
    _tick(SD21, bid="0.60", ask="0.62", price="0.61"),
    _tick(OPEN_TICKER),
    _settle(SD21),
    _tick(SD20, bid="0", ask="0", price="0"),
]


async def _ship_run(monkeypatch, *, prepared):
    if not prepared:
        monkeypatch.setattr(oc, "prepared_shard_indexes", lambda _ids, _shards: set())
    calls = _recording_grader(monkeypatch)
    changes = _recording_changes(monkeypatch)
    wiring = _record_wiring(monkeypatch)
    accepted, open_seen = _record_accepted(monkeypatch)
    entered, release = _hold(monkeypatch, SD20_ID)
    job = asyncio.create_task(_run(
        monkeypatch, frames_for={SD20: list(SHIP_FRAMES)}, open_rows=BOARD_ROWS,
        refresh=1.0,
    ))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if prepared:
            await asyncio.wait_for(open_seen.wait(), 2)
        else:
            await asyncio.sleep(0.2)
        before_release = list(accepted)
        grades_before_release = list(calls)
    finally:
        release.set()
    stats, _record, state = await job
    return dict(
        before=before_release, grades_before=grades_before_release, calls=calls,
        accepted=accepted, changes=changes, wiring=wiring, stats=stats, state=state,
    )


class TestAnUnrelatedQuoteLandsWhileALegGrades:
    async def test_unrelated_quote_lands(self, monkeypatch):
        run = await _ship_run(monkeypatch, prepared=True)

        assert (OPEN_ID, pytest.approx(0.41)) in run["before"], "the ship"
        # The same board waits behind its own settlement: its later quote and
        # its sibling's settlement are not taken while SD20 is grading.
        assert (SD21_ID, pytest.approx(0.61)) not in run["before"]
        assert run["grades_before"] == []
        assert [p for t, p in run["wiring"] if t and OPEN_TICKER in t] == [True]

        # After release: frame order per board is unchanged.
        assert run["calls"] == [(BOARD, SD20_ID, False), (BOARD, SD21_ID, False)]
        assert (SD21_ID, pytest.approx(0.61)) in run["accepted"]
        assert all(oid != SD20_ID for oid, _ in run["accepted"]), "terminal tick refused"
        assert run["stats"]["open_contract_settlements"] == 2
        assert run["stats"]["open_contract_markets_resolved"] == 0
        assert all(not c.get("terminal", False) for c in run["changes"])

    async def test_inline_control(self, monkeypatch):
        """Admission refused: the pre-#10734 shape. The unrelated quote waits."""
        run = await _ship_run(monkeypatch, prepared=False)

        assert all(oid != OPEN_ID for oid, _ in run["before"])
        assert [p for t, p in run["wiring"] if t and OPEN_TICKER in t] == [False]
        assert run["calls"] == [(BOARD, SD20_ID, False), (BOARD, SD21_ID, False)]
        assert (OPEN_ID, pytest.approx(0.41)) in run["accepted"]
        assert run["stats"]["open_contract_settlements"] == 2

    async def test_both_arms_end_in_the_same_place(self, monkeypatch):
        deferred = await _ship_run(monkeypatch, prepared=True)
        monkeypatch.undo()
        inline = await _ship_run(monkeypatch, prepared=False)

        assert sorted(deferred["accepted"]) == sorted(inline["accepted"])
        assert deferred["calls"] == inline["calls"]
        assert deferred["changes"] == inline["changes"]
        keys = ("errors", "settlements", "open_contract_settlements",
                "open_contract_markets_resolved", "open_contract_lifecycle_unverdicted")
        assert {k: deferred["stats"][k] for k in keys} == {k: inline["stats"][k] for k in keys}
        assert deferred["state"]["market_writes"] == inline["state"]["market_writes"] == []


class TestOnlyASafeConnectionIsPrepared:
    def test_admission_helper(self):
        ids = {"GAME-A": (10, 1), "GAME-B": (10, 2), "OTHER-C": (20, 3)}
        assert oc.prepared_shard_indexes(ids, [["GAME-A", "GAME-B", "OTHER-C"]]) == {0}
        # GAME's prefix is split over two connections: both stay inline.
        assert oc.prepared_shard_indexes(ids, [["GAME-A"], ["GAME-B"], ["OTHER-C"]]) == {2}
        # One market under two prefixes: neither connection is prepared.
        two_prefixes = {"GAME-A": (10, 1), "DIFFERENT-B": (10, 2), "OTHER-C": (20, 3)}
        assert oc.prepared_shard_indexes(
            two_prefixes, [["GAME-A"], ["DIFFERENT-B"], ["OTHER-C"]],
        ) == {2}
        assert oc.prepared_shard_indexes(
            two_prefixes, [["GAME-A", "DIFFERENT-B", "OTHER-C"]],
        ) == set()
        # No prefix at all is an unknown identity: the dispatcher's global barrier.
        no_prefix = {"NOIDENTITY": (10, 1), "OTHER-C": (20, 3)}
        assert oc.prepared_shard_indexes(no_prefix, [["NOIDENTITY"], ["OTHER-C"]]) == {1}
        # A ticker the map does not carry, and an empty shard, are never prepared.
        assert oc.prepared_shard_indexes(ids, [["UNKNOWN-X"], ["GAME-A", "GAME-B"]]) == {1}
        assert oc.prepared_shard_indexes(ids, [[], ["OTHER-C"]]) == {1}
        assert oc.prepared_shard_indexes({}, []) == set()

    async def test_a_split_prefix_keeps_the_inline_callback(self, monkeypatch):
        sharded = oc.shard_tickers
        monkeypatch.setattr(oc, "shard_tickers", lambda ids: sharded(ids, per_connection=1))
        wiring = _record_wiring(monkeypatch)

        await _run(monkeypatch, frames_for={}, open_rows=BOARD_ROWS)

        assert ([SD20], False) in wiring and ([SD21], False) in wiring
        assert ([OPEN_TICKER], True) in wiring
        # The game socket keeps its own #10667 preparation, untouched.
        assert ([LINKED_TICKER], True) in wiring

    async def test_a_market_under_two_prefixes_keeps_the_inline_callback(self, monkeypatch):
        other_prefix = "KXMLBSERIESGAMES-26CHCSDWC-O25"
        wiring = _record_wiring(monkeypatch)

        await _run(monkeypatch, frames_for={}, open_rows=[
            (SD20, BOARD, SD20_ID), (other_prefix, BOARD, 9), (OPEN_TICKER, 50, OPEN_ID),
        ])

        shard = [(t, p) for t, p in wiring if t and SD20 in t]
        assert shard == [(sorted([OPEN_TICKER, SD20, other_prefix]), False)]


class TestTheDeferredGradeKeepsItsGuarantees:
    async def test_a_failed_grade_is_an_error_and_the_board_tail_goes_on(self, monkeypatch):
        calls = _recording_grader(monkeypatch)
        _recording_changes(monkeypatch)
        recorded = oc.grade_open_contract_leg
        accepted, _seen = _record_accepted(monkeypatch)

        async def grade(session, **kw):
            if kw["outcome_id"] == SD20_ID:
                raise RuntimeError("deadlock detected")
            return await recorded(session, **kw)

        monkeypatch.setattr(oc, "grade_open_contract_leg", grade)
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={SD20: [_settle(SD20), _settle(SD21), _tick(OPEN_TICKER)]},
            open_rows=BOARD_ROWS,
        )

        assert stats["errors"] >= 1
        assert calls == [(BOARD, SD21_ID, False)]
        assert stats["open_contract_settlements"] == 1
        assert (OPEN_ID, pytest.approx(0.41)) in accepted

    async def test_a_recycle_cancels_a_held_grade_and_leaves_no_task(self, monkeypatch):
        calls = _recording_grader(monkeypatch)
        entered, _release = _hold(monkeypatch, SD20_ID)  # never released
        accepted, _seen = _record_accepted(monkeypatch)

        stats, _record, state = await _run(
            monkeypatch,
            frames_for={SD20: [_settle(SD20), _settle(SD21), _tick(OPEN_TICKER)]},
            open_rows=BOARD_ROWS, refresh=0.4,
        )

        assert entered.is_set()
        assert calls == [], "the held leg and the sibling queued behind it never graded"
        assert stats["open_contract_settlements"] == 0
        assert (OPEN_ID, pytest.approx(0.41)) in accepted
        # The final drain still wrote the unrelated quote that was accepted.
        assert (OPEN_ID, pytest.approx(0.41)) in state["price_writes"]
        lingering = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
            and "ordered" in repr(t.get_coro())
        ]
        assert lingering == []

    async def test_the_settlement_undo_switch_grades_nothing(self, monkeypatch):
        monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        calls = _recording_grader(monkeypatch)
        wiring = _record_wiring(monkeypatch)

        stats, _record, _state = await _run(
            monkeypatch, frames_for={SD20: [_settle(SD20)]}, open_rows=BOARD_ROWS,
        )

        assert any(t and SD20 in t and p for t, p in wiring)
        assert calls == []
        assert stats["open_contract_settlements"] == 0

    async def test_a_linked_frame_on_a_prepared_connection_does_nothing(self, monkeypatch):
        calls = _recording_grader(monkeypatch)
        wiring = _record_wiring(monkeypatch)

        stats, _record, state = await _run(
            monkeypatch,
            frames_for={OPEN_TICKER: [_settle(LINKED_TICKER, result="yes")]},
            open_rows=[(OPEN_TICKER, 50, OPEN_ID)],
        )

        assert ([OPEN_TICKER], True) in wiring
        assert calls == []
        assert state["market_writes"] == []
        assert stats["settlements"] == 0
