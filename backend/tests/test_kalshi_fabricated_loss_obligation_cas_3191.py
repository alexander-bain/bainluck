"""CAL-P1011 / #3191 — two repair calls cannot lose each other's invalidation debt.

CERT-1877's non-blocking FOLLOW-UP. The fabricated-loss rail carries the
calibration invalidation debt in ONE durable slot, and both writers (the apply
and the restore) build their record as a FOLD: this call's ids UNIONED with
whatever the slot already held. Until this change the fold was staged with a
read-THEN-write — read the prior record, union, write — with nothing between the
read and the write to notice that the slot had moved.

That is a lost update with a name. Two attended calls overlapping in time each
read the same prior record, each build their own union, and the second commit
takes the slot. The first call's ids survive only if the second happened to
include them, which two calls carrying different pages do not. What is lost is
not bookkeeping: those ids are the markets whose banked calibration cells are
now wrong, and the record is the ONLY durable thing naming what would pay them.
Lose it and the published curve stays stale with no retry handle — the exact
failure CERT-1872 closed one layer down.

Both writes are now compare-and-set against the generation the caller ACTUALLY
READ. The loser writes nothing, rolls its rows back, and is told
``OBLIGATION_SLOT_MOVED``.

The catching tests below drive the REAL ``repair`` and ``restore`` entry points
through the p1008 harness (whose durable fake holds an in-transaction write on
the session until it commits, and now models the CAS predicate too). The
concurrent writer is injected at the one seam that matters: the instant AFTER
this call has read the slot and BEFORE it writes it. Every one of them passes
against a read-then-write only by accident, and none of them do.
"""

from __future__ import annotations

import datetime as _datetime

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.calibration_invalidation import (
    INVALIDATION_OBLIGATION_SCHEMA,
    RESTORE_DISCHARGES,
    new_obligation,
    obligation_market_ids,
)
from app.utils.durable_state import DurableEnvelope, generation_for

from tests.test_kalshi_fabricated_loss_p1008 import (
    _UndoSession,
    _plan,
    _row,
    _txn_store,
)

#: The ids the INTERLOPER owes. Deliberately disjoint from anything the call
#: under test writes, so "the interloper's debt survived" cannot be satisfied by
#: the winner's own union happening to contain it.
_INTERLOPER_MARKETS = [900, 901]
_INTERLOPER_LEGS = [90, 91]


def _interloper_record(*, owner=None, plan_hash="interloper-hash"):
    return new_obligation(
        plan_hash=plan_hash,
        market_ids=_INTERLOPER_MARKETS,
        leg_ids=_INTERLOPER_LEGS,
        owner=owner or rail.OBLIGATION_OWNER_APPLY,
    )


def _seat_the_interloper(store, record, *, after_generation):
    """Land a second call's committed record in the one slot.

    Written straight into the store rather than through a publisher: this is
    modelling a write that ALREADY COMMITTED in another process, which is the
    only thing the caller under test can observe. Its generation is strictly
    past the one the caller read, exactly as a real second writer's would be.
    """
    envelope = DurableEnvelope.build(
        identity=rail.OBLIGATION_IDENTITY,
        schema_version=INVALIDATION_OBLIGATION_SCHEMA,
        payload=record,
        complete=True,
        source="repair:kalshi-fabricated-loss",
        generation=(after_generation or 0) + 1_000,
    )
    store.rows[rail.OBLIGATION_IDENTITY] = envelope
    return envelope


def _interleave_after_the_read(monkeypatch, store, record):
    """Make a second call commit in the window between THIS call's read of the
    ledger and its write of the ledger.

    The seam is the reader itself: the real ``_load_obligation`` runs, answers
    honestly, and only then does the other writer land. Nothing about the
    function under test is faked — ``_stage_obligation`` and ``_save_obligation``
    are the shipped ones, against a store that really did move.
    """
    real = rail._load_obligation
    seen: dict[str, object] = {}

    async def _load_then_collide():
        prior, note, generation = await real()
        if not seen:
            seen["generation"] = generation
            seen["envelope"] = _seat_the_interloper(
                store, record, after_generation=generation
            )
        return prior, note, generation

    monkeypatch.setattr(rail, "_load_obligation", _load_then_collide)
    return seen


class TestTheStagedFoldCannotClobberASecondCall:
    """The apply and the restore, each racing a call that got there first."""

    @pytest.mark.asyncio
    async def test_the_apply_refuses_and_writes_no_row_when_the_slot_moved(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"), (2, 200, "retract_fabricated"))
        session = _UndoSession([_row(1), _row(2, is_winner=True)])
        before = {i: dict(r) for i, r in session.rows.items()}

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        _interleave_after_the_read(monkeypatch, store, _interloper_record())

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["success"] is False
        assert out["refused"] == [
            "INVALIDATION_DEBT_NOT_STAGED",
            rail.OBLIGATION_SLOT_MOVED,
        ]
        assert out["rolled_back"] is True
        assert out["legs_written"] == 0
        assert out["obligation_note"].startswith(rail.OBLIGATION_SLOT_MOVED)
        # The operator is told the thing that is actually true and actionable.
        assert "Another repair call wrote this ledger" in out["reason"]

        # No row moved...
        assert {i: dict(r) for i, r in session.rows.items()} == before
        # ...and the other call's debt is untouched, ids and all.
        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert banked["state"] == "open"
        assert obligation_market_ids(banked) == _INTERLOPER_MARKETS
        assert banked["plan_hash"] == "interloper-hash"

    @pytest.mark.asyncio
    async def test_the_restore_refuses_and_reverses_nothing_when_the_slot_moved(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)
        applied = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)
        assert applied["legs_written"] == 1

        # A restore's own debt is owned by the RESTORE, so the interloper here is
        # one too — an apply-owned record would be refused for a different reason
        # upstream and the CAS would never be reached.
        _interleave_after_the_read(
            monkeypatch,
            store,
            _interloper_record(owner=rail.OBLIGATION_OWNER_RESTORE),
        )
        undo = _UndoSession(list(session.rows.values()))
        before = {i: dict(r) for i, r in undo.rows.items()}

        out = await rail.restore(undo, apply=True, plan_hash=plan.plan_hash)

        assert out["success"] is False
        assert out["refused"] == [
            "INVALIDATION_DEBT_NOT_STAGED",
            rail.OBLIGATION_SLOT_MOVED,
        ]
        assert out["rolled_back"] is True
        assert out["legs_reversed"] == 0
        assert {i: dict(r) for i, r in undo.rows.items()} == before

        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert banked["state"] == "open"
        assert obligation_market_ids(banked) == _INTERLOPER_MARKETS


class TestADischargeCannotPayADebtItNeverSaw:
    """The more dangerous half: writing "paid" over somebody else's unpaid ids.

    A discharge is a fold too — the record it marks paid is the one this call
    read. If the slot has since collected another call's ids, a blind write
    retires a debt nobody settled, and the curve stays stale with nothing left
    naming it. The loser must leave the record OPEN and say so.
    """

    @pytest.mark.asyncio
    async def test_the_apply_leaves_the_record_open_when_the_slot_moved(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        plan = _plan((1, 100, "restore_winner"))
        session = _UndoSession([_row(1)])

        async def _load():
            return plan, "ok"

        monkeypatch.setattr(rail, "_load_plan", _load)

        # The seam for a DISCHARGE is after the rows and their debt have
        # committed and before the debt is marked paid: the invalidation itself.
        real_invalidate = rail.invalidate_calibration_generation
        landed: dict[str, object] = {}

        async def _invalidate_then_collide(db, market_ids):
            verdict = await real_invalidate(db, market_ids)
            if not landed:
                staged = store.rows.get(rail.OBLIGATION_IDENTITY)
                folded = new_obligation(
                    plan_hash=plan.plan_hash,
                    # A REAL second caller folds what it read forward, so its
                    # union carries this call's ids too — and it is that union,
                    # not this call's discharge, that is allowed to be paid.
                    market_ids=obligation_market_ids(staged.payload)
                    + _INTERLOPER_MARKETS,
                    leg_ids=_INTERLOPER_LEGS,
                    owner=rail.OBLIGATION_OWNER_APPLY,
                )
                landed["envelope"] = _seat_the_interloper(
                    store, folded, after_generation=staged.generation
                )
            return verdict

        monkeypatch.setattr(
            rail, "invalidate_calibration_generation", _invalidate_then_collide
        )

        out = await rail.repair(session, apply=True, plan_hash=plan.plan_hash)

        assert landed, "the collision never happened — the test proves nothing"
        assert out["legs_written"] == 1, "the rows themselves are fine"
        ledger = out["invalidation_obligation"]
        assert ledger["ledger_cleared"] is False
        assert ledger["state"] == "open"
        assert ledger["clear_note"].startswith(rail.OBLIGATION_SLOT_MOVED)

        # The slot still holds the OPEN union, and it still names both debts.
        banked = store.payload(rail.OBLIGATION_IDENTITY)
        assert banked["state"] == "open", "a debt nobody paid was marked paid"
        assert set(_INTERLOPER_MARKETS).issubset(set(obligation_market_ids(banked)))
        assert 100 in obligation_market_ids(banked)


class TestTheCompareIsAgainstWhatWasRead:
    """Unit-level, because the predicate has a plausible wrong form.

    Comparing against the generation the caller PROPOSES instead of the one it
    read still reads like a compare-and-set and never refuses anything.
    """

    @pytest.mark.asyncio
    async def test_a_stage_whose_expected_generation_is_stale_writes_nothing(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        record = new_obligation(
            plan_hash="h",
            market_ids=[100],
            leg_ids=[1],
            owner=rail.OBLIGATION_OWNER_APPLY,
        )
        seated = _seat_the_interloper(store, _interloper_record(), after_generation=0)
        session = _UndoSession([_row(1)])

        ok, note, generation = await rail._stage_obligation(
            session, record, expected_generation=seated.generation - 1
        )

        assert ok is False
        assert note.startswith(rail.OBLIGATION_SLOT_MOVED)
        assert generation is None
        assert session.pending_durable == [], "a losing CAS staged something"
        assert store.payload(rail.OBLIGATION_IDENTITY)["plan_hash"] == "interloper-hash"

    @pytest.mark.asyncio
    async def test_a_stage_on_the_generation_it_read_lands_and_reports_it(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        record = new_obligation(
            plan_hash="h",
            market_ids=[100],
            leg_ids=[1],
            owner=rail.OBLIGATION_OWNER_APPLY,
        )
        seated = _seat_the_interloper(store, _interloper_record(), after_generation=0)
        session = _UndoSession([_row(1)])

        ok, note, generation = await rail._stage_obligation(
            session, record, expected_generation=seated.generation
        )

        assert ok is True, note
        assert generation is not None and generation > seated.generation

    @pytest.mark.asyncio
    async def test_a_discharge_whose_slot_moved_is_reported_not_assumed(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        seated = _seat_the_interloper(store, _interloper_record(), after_generation=0)

        ok, note = await rail._save_obligation(
            _interloper_record(), expected_generation=seated.generation - 1
        )

        assert ok is False
        assert note.startswith(rail.OBLIGATION_SLOT_MOVED)
        assert store.rows[rail.OBLIGATION_IDENTITY] is seated, "the loser wrote"


class TestTheGenerationStrictlyAdvances:
    """The degenerate CAS: a predicate that cannot discriminate.

    Generations are epoch MILLISECONDS off the write clock, so two repair calls
    inside one millisecond would propose the same number. An envelope whose
    generation equals the one it is replacing leaves ``stored`` unmoved, and the
    next writer holding that same stale expectation would pass the predicate
    too. The counter has to take over where the clock stops separating them.
    """

    def test_a_same_millisecond_write_still_moves_the_slot(self, monkeypatch):
        frozen = _datetime.datetime(2026, 9, 5, 12, 0, 0, tzinfo=_datetime.timezone.utc)
        expected = generation_for(frozen)

        class _FrozenClock(_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen

        monkeypatch.setattr(
            "app.utils.durable_state.datetime", _FrozenClock, raising=False
        )
        envelope = rail._obligation_envelope(
            _interloper_record(), expected_generation=expected
        )

        assert envelope.generation == expected + 1

    def test_a_creator_takes_the_clocks_generation_unchanged(self):
        envelope = rail._obligation_envelope(
            _interloper_record(), expected_generation=None
        )

        assert envelope.generation == generation_for(envelope.generated_at)


class TestTheReadReportsWhatItRead:
    @pytest.mark.asyncio
    async def test_a_present_record_carries_its_generation(self, monkeypatch):
        store = _txn_store(monkeypatch)
        seated = _seat_the_interloper(store, _interloper_record(), after_generation=0)

        record, note, generation = await rail._load_obligation()

        assert note == "ok"
        assert record["plan_hash"] == "interloper-hash"
        assert generation == seated.generation

    @pytest.mark.asyncio
    async def test_an_absent_record_has_no_generation_to_compare(self, monkeypatch):
        _txn_store(monkeypatch)

        record, note, generation = await rail._load_obligation()

        assert (record, note, generation) == (None, "missing", None)

    @pytest.mark.asyncio
    async def test_an_unreadable_record_has_no_generation_either(self, monkeypatch):
        store = _txn_store(monkeypatch)
        store.unreadable[rail.OBLIGATION_IDENTITY] = "unavailable"

        record, note, generation = await rail._load_obligation()

        assert record is None
        assert note not in ("ok", "missing")
        assert generation is None, "an unreadable slot must not hand out a CAS token"


class TestTheRestoreOwnedRecordStillSaysHowItIsPaid:
    """The CAS must not have quietly changed what a surviving record MEANS."""

    @pytest.mark.asyncio
    async def test_the_interlopers_restore_record_still_names_the_restore(
        self, monkeypatch
    ):
        store = _txn_store(monkeypatch)
        _seat_the_interloper(
            store,
            new_obligation(
                plan_hash="interloper-hash",
                market_ids=_INTERLOPER_MARKETS,
                leg_ids=_INTERLOPER_LEGS,
                owner=rail.OBLIGATION_OWNER_RESTORE,
                retry_instruction=RESTORE_DISCHARGES,
            ),
            after_generation=0,
        )

        record, note, _ = await rail._load_obligation()

        assert note == "ok"
        assert record["retry_instruction"] == RESTORE_DISCHARGES
