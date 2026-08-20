"""CAL-P081 — consuming `C-APPLY-PRE-1912-R3`'s BLOCK: durability that is
ACKNOWLEDGED is not durability that is PROVED.

Codex's verdict, verbatim: *"BLOCK — THE HALT AND INTENT RECORDS ARE BOTH
ACKNOWLEDGED WITHOUT BEING PROVED; THE WAVE CAN CONTINUE AFTER A LOST HALT AND
CAN COMMIT ROWS AFTER ITS DEBT RECORD FAILED TO PERSIST."* Three findings, three
classes of test here, each driving the adversarial specimen codex built rather
than a restatement of it.

The pattern under all three is one mistake wearing three coats: a durable write
is claimed on the PUBLISHER'S opinion of itself. ``result["status"] == "ok"`` is
a value returned by the thing being audited. It answers "did I think that
worked", never "is it there".

What makes this file bite is that the discipline was already in the repository
when R3 ran. ``_save_progress`` had carried an after-read since CAL-P076 —
written for this exact class, with a comment explaining it. It was applied to the
counters and not to the STOP, and its equivalence test was weak enough that
somebody else's record could satisfy it. The rule was known; the reach was not.

* ``TestTheHaltMustBeProved`` — [P1] #1. A no-op publisher "persisted" the halt,
  ``_raise_wave_halt`` returned ``(True, "ok")``, a fresh-process read returned
  ``missing``, and the next dry-run dispatched normally. The record whose entire
  purpose is to stop page N+1.
* ``TestNoWriteWithoutADurableIntent`` — [P1] #2. ``intent_ok`` was computed
  before the loop and consulted after it. A forced ``(False, ...)`` still
  committed 2/2 legs. Codex's fix-sketch asked for a specimen asserting **zero
  UPDATEs and zero commits**; that is
  ``test_a_failed_intent_write_writes_no_rows_at_all``.
* ``TestSupersessionIsBoundToTheWave`` — [P2]. Equivalence was schema plus a
  monotone ``calls``, so a record for ``owner=different-rail``,
  ``cohort=different-population``, ``issue=9999``, ``calls=999`` was accepted as
  proof that OUR fold was durable.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import repair_pm_never_graded as rail
from app.tasks.repair_pm_never_graded import (
    WAVE_HALT_CLEARED,
    WAVE_HALT_RAISED,
    WAVE_IDENTITY_FIELDS,
    WAVE_PROGRESS_SCHEMA,
    WAVE_SUBSUMING_TOTALS,
    _apply_reviewed_plan,
    _raise_wave_halt,
    _save_progress,
    fold_progress,
)
from app.utils.repair_apply_plan import PlannedLeg, build_plan


def _plan(n=4):
    legs = [
        PlannedLeg(
            leg_id=910_000 + i,
            market_id=58_800_000 + (i // 2),
            verdict="winner" if i % 2 == 0 else "loser",
            expected_is_winner=False,
            expected_source=None,
        )
        for i in range(n)
    ]
    return build_plan(legs, context={"owner": "test"})


class _Res:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Db:
    """Enough session to reach the write loop; the counters are the assertion."""

    def __init__(self):
        self.state: dict[int, tuple] = {}
        self.updates = 0
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = dict(params or {})
        if "statement_timeout" in sql:
            return _Res()
        if sql.upper().startswith("SELECT RESOLUTION_SOURCE"):
            row = self.state.get(int(params["leg_id"]))
            return _Res([row] if row else [])
        if "GROUP BY" in sql.upper() and "llm_sport_category" in sql:
            return _Res([])          # a clean canary panel
        if sql.upper().startswith("UPDATE"):
            self.updates += 1
            self.state[int(params["leg_id"])] = (params.get("src"), params.get("wins"))
            return _Res(rowcount=1)
        return _Res()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


# =============================================================================
# [P1] #1 — the halt
# =============================================================================


class TestTheHaltMustBeProved:
    """``_raise_wave_halt`` after-reads through the reader that gates the wave."""

    @pytest.mark.asyncio
    async def test_the_no_op_publisher_specimen_no_longer_reports_success(
        self, monkeypatch
    ):
        """Codex's specimen exactly: stores nothing, answers ``superseded``."""

        async def _publish_nothing(_envelope):
            return {"status": "superseded"}

        async def _reader_sees_nothing():
            return None, "no halt recorded"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone",
            _publish_nothing,
        )
        monkeypatch.setattr(rail, "_wave_halt_state", _reader_sees_nothing)

        ok, note = await _raise_wave_halt("canary_tripped_preflight", {"rodeo": 12})
        assert ok is False
        assert "UNPROVED" in note
        assert "no halt recorded" in note

    @pytest.mark.asyncio
    async def test_a_halt_that_really_landed_still_reports_success(self, monkeypatch):
        """The other direction of the guard. A check that can only say no is not
        a check, it is an outage."""

        async def _publish(_envelope):
            return {"status": "ok"}

        async def _reader():
            return (
                {
                    "state": WAVE_HALT_RAISED,
                    "owner": rail._OWNER,
                    "reason": "canary_tripped_preflight",
                },
                "halted: canary_tripped_preflight",
            )

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_wave_halt_state", _reader)

        ok, note = await _raise_wave_halt("canary_tripped_preflight", {"rodeo": 12})
        assert ok is True
        assert "after-read proved" in note

    @pytest.mark.asyncio
    async def test_a_cleared_record_read_back_is_not_proof_of_a_raised_one(
        self, monkeypatch
    ):
        """``cleared`` and ``missing`` differ as records and agree on the only
        fact that matters here: nothing is stopping the wave."""

        async def _publish(_envelope):
            return {"status": "ok"}

        async def _reader():
            return None, "halt explicitly cleared"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_wave_halt_state", _reader)

        ok, note = await _raise_wave_halt("canary_tripped_preflight", {})
        assert ok is False
        assert "halt explicitly cleared" in note

    @pytest.mark.asyncio
    async def test_somebody_elses_halt_is_a_stop_but_not_proof_of_ours(
        self, monkeypatch
    ):
        """A raised halt from another trip would stop the wave today and be
        cleared tomorrow — silently un-stopping this one, whose record was never
        written. The two must not read alike."""

        async def _publish(_envelope):
            return {"status": "ok"}

        async def _reader():
            return (
                {
                    "state": WAVE_HALT_RAISED,
                    "owner": "some-other-rail",
                    "reason": "unrelated_trip",
                },
                "halted: unrelated_trip",
            )

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_wave_halt_state", _reader)

        ok, note = await _raise_wave_halt("canary_tripped_preflight", {})
        assert ok is False
        assert "different record" in note

    @pytest.mark.asyncio
    async def test_a_rejected_publish_never_reaches_the_after_read(self, monkeypatch):
        """Ordering, pinned: a publisher that says no is refused on its own word,
        so the after-read is a second gate and never a way past the first."""
        reads = {"n": 0}

        async def _publish(_envelope):
            return {"status": "rejected"}

        async def _reader():
            reads["n"] += 1
            return {"state": WAVE_HALT_RAISED, "owner": rail._OWNER, "reason": "x"}, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_wave_halt_state", _reader)

        ok, note = await _raise_wave_halt("x", {})
        assert ok is False
        assert "rejected" in note
        assert reads["n"] == 0

    def test_the_cleared_and_raised_states_are_still_distinct_constants(self):
        assert WAVE_HALT_RAISED != WAVE_HALT_CLEARED


# =============================================================================
# [P1] #2 — the intent record
# =============================================================================


def _wire(monkeypatch, *, plan, save_obligation_result=(True, "ok")):
    async def _load_plan():
        return plan, "ok"

    async def _load_ob():
        return None, "missing"

    async def _save_ob(_rec):
        return save_obligation_result

    async def _inval(_session, _ids):
        return {"status": "invalidated"}

    async def _load_progress():
        return None, "missing"

    async def _save_progress_ok(_rec):
        return True, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load_plan)
    monkeypatch.setattr(rail, "_load_obligation", _load_ob)
    monkeypatch.setattr(rail, "_save_obligation", _save_ob)
    monkeypatch.setattr(rail, "_load_progress", _load_progress)
    monkeypatch.setattr(rail, "_save_progress", _save_progress_ok)
    monkeypatch.setattr(
        "app.tasks.repair_kalshi_fabricated_loss.invalidate_calibration_generation",
        _inval,
    )


class TestNoWriteWithoutADurableIntent:
    @pytest.mark.asyncio
    async def test_a_failed_intent_write_writes_no_rows_at_all(self, monkeypatch):
        """Codex's fix-sketch, as an assertion: zero UPDATEs and zero commits.

        The specimen it replaces committed 2/2 legs and then reported
        ``success: false`` — which is not the same thing at all. A process death
        between those two moments leaves rows on disk with no record of the debt.
        """
        plan = _plan(4)
        _wire(monkeypatch, plan=plan,
              save_obligation_result=(False, "publisher unavailable"))
        db = _Db()

        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert db.updates == 0
        assert db.commits == 0
        assert out["wrote"] is False
        assert out["success"] is False
        assert out["refused"] == ["INTENT_NOT_DURABLE"]
        assert out["legs_written"] == 0
        assert out["obligation_persisted"] is False
        assert "publisher unavailable" in out["obligation_note"]

    @pytest.mark.asyncio
    async def test_the_refusal_says_nothing_needs_reverting(self, monkeypatch):
        """The operator-facing half. A refusal and a half-applied wave demand
        opposite next actions, so the receipt must not leave that ambiguous."""
        plan = _plan(2)
        _wire(monkeypatch, plan=plan, save_obligation_result=(False, "boom"))
        out = await _apply_reviewed_plan(_Db(), plan.plan_hash, time.monotonic())
        assert "NOTHING WAS WRITTEN" in out["note"]
        assert "no revert is owed" in out["note"]
        assert "re-present this same plan_hash" in out["note"]

    @pytest.mark.asyncio
    async def test_a_durable_intent_still_lets_the_wave_write(self, monkeypatch):
        """The control. A gate that refuses everything proves nothing."""
        plan = _plan(4)
        _wire(monkeypatch, plan=plan, save_obligation_result=(True, "ok"))
        db = _Db()

        out = await _apply_reviewed_plan(db, plan.plan_hash, time.monotonic())

        assert db.updates == 4
        assert out.get("refused") != ["INTENT_NOT_DURABLE"]
        assert out["legs_written"] == 4


# =============================================================================
# [P2] — supersession
# =============================================================================


def _fold(**over):
    rec = fold_progress(None, mode="dry_run", examined_markets=10,
                        planned_markets=3, cursor=99)
    rec.update(over)
    return rec


class TestSupersessionIsBoundToTheWave:
    @pytest.mark.asyncio
    async def test_a_different_wave_with_a_bigger_counter_is_not_proof(
        self, monkeypatch
    ):
        """Codex's stored record, field for field."""
        mine = _fold()
        theirs = dict(mine, owner="different-rail", cohort="different-population",
                      issue=9999, calls=999)

        async def _publish(_e):
            return {"status": "superseded"}

        async def _load():
            return theirs, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await _save_progress(mine)
        assert ok is False
        assert "different wave" in note

    @pytest.mark.parametrize("field", WAVE_IDENTITY_FIELDS)
    @pytest.mark.asyncio
    async def test_each_identity_field_is_load_bearing_on_its_own(
        self, monkeypatch, field
    ):
        """Parametrised so a future edit cannot quietly drop one from the tuple
        and leave the remaining checks passing."""
        mine = _fold()
        theirs = dict(mine, calls=mine["calls"] + 5)
        theirs[field] = "moved"

        async def _publish(_e):
            return {"status": "ok"}

        async def _load():
            return theirs, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await _save_progress(mine)
        assert ok is False
        assert field in note

    @pytest.mark.parametrize("field", WAVE_SUBSUMING_TOTALS)
    @pytest.mark.asyncio
    async def test_a_bigger_calls_count_cannot_hide_a_smaller_total(
        self, monkeypatch, field
    ):
        """``calls`` is monotone by construction, so it can rise while the totals
        it summarises fall — which is what a fold that lost this call's
        contribution to a writer starting from an older prior looks like."""
        mine = _fold()
        mine[field] = 7
        theirs = dict(mine, calls=mine["calls"] + 3)
        theirs[field] = 6

        async def _publish(_e):
            return {"status": "ok"}

        async def _load():
            return theirs, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await _save_progress(mine)
        assert ok is False
        assert "does not subsume" in note

    @pytest.mark.asyncio
    async def test_a_genuine_concurrent_writer_of_the_SAME_wave_still_passes(
        self, monkeypatch
    ):
        """The control, and the reason this is not just "require equality": a
        later call of our own wave legitimately wins the race, and refusing it
        would make every concurrent page report a phantom durability failure."""
        mine = _fold()
        theirs = dict(mine, calls=mine["calls"] + 1)
        for f in WAVE_SUBSUMING_TOTALS:
            if isinstance(theirs.get(f), int):
                theirs[f] = theirs[f] + 1

        async def _publish(_e):
            return {"status": "superseded"}

        async def _load():
            return theirs, "ok"

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(rail, "_load_progress", _load)

        ok, note = await _save_progress(mine)
        assert ok is True
        assert "after-read proved" in note

    def test_the_identity_fields_are_actually_on_the_record(self):
        """A tuple of field names that the record does not carry would compare
        ``None`` to ``None`` and pass forever — a guard that cannot fail."""
        rec = _fold()
        for field in WAVE_IDENTITY_FIELDS:
            assert rec.get(field) is not None, field
        assert rec["schema"] == WAVE_PROGRESS_SCHEMA
