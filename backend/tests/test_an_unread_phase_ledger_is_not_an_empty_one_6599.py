"""#6599, THIRD SITE: ``save_phase_ledger``'s fold ran on a prior it could not read.

THE CLASS, for the third time in this file's neighbourhood: an answer that did
not come back is not an answer of "empty" (gotcha #53). The first two sites were
``load_staged_cursor`` and ``load_main_checkpoint``, and both were repaired by
REFUSING to act on UNKNOWN. This one is the same cause with a different shape,
and the difference is why it needs its own test file rather than a widening of
the other two.

THE SHAPE. ``save_phase_ledger``'s payload is a FOLD::

    payload["history"]   = merge_history(prior_history, this_beat.observations())
    payload["floors"]    = merge_history(prior_floors,  this_beat.floors())
    payload["unit_costs"] = this_beat_level or carried(prior_level)
    payload[WORST]       = merge_history(prior_worst, this_beat_worst)

and ``publish_snapshot`` is an unconditional whole-payload replace — there is no
merge mode, the SQL is one UPSERT of ``canonical_json(payload)``. So when
``load_phase_carryover`` answered a read that did not come back with four empty
dicts, every one of those folds degenerated to "this beat only" and the publish
wrote THAT over the bank. Measured on the real chain before the repair, with
nothing hand-built — three real ``save_phase_ledger`` calls banking a history,
then one read classified ``unavailable``::

    BANKED after 3 beats   history {'futures': [1000, 1100, 1200]}
                           ring    {'futures': [1000, 1100, 1200]}
    4th beat, read 'unavailable'
      save_phase_ledger returned : ok          <- and it said OK
      durable writes issued      : 1
      history NOW                : {'futures': [9999]}
      ring NOW                   : {'futures': [9999]}

Two things are worse here than at the other two sites. The first is that the
caller was told ``ok``, so ``health_for`` could return GREEN for a beat that had
just destroyed the bank. The second is that ``STATE_MAX_AGE_S`` is fourteen days:
this row is the ONLY record of how long the phases take, it is what
``derive_plan`` reasons from, and nothing re-derives it — a beat re-measures one
observation, not ten.

THE REPAIR IS A DIFFERENT SHAPE FROM THE OTHER TWO, deliberately. You cannot
"preserve" a prior you could not read: there is nothing to fold onto, so there is
no version of this beat's row that is safe to write. The question is whether the
row may be written WHOLE at all, and with the prior UNKNOWN the answer is no.
``save_phase_ledger`` stands down: no write, a loud log naming the read status,
and its own return value.

WHAT IT COSTS, named so no one has to discover it. This beat's telemetry is not
persisted — one beat's observations, which the next beat re-measures, against a
multi-beat bank that nothing re-derives. It does not reach publication or resume:
by the time ``save_phase_ledger`` runs, the artifact has already published and
``save_main_checkpoint`` has already banked the resumable phases onto a DIFFERENT
durable row. The one contract it does reach is ``health_for``, and that is
preserved by construction rather than by care: the return value is not ``ok``, so
health is UNKNOWN. That is strictly more honest than what it replaces.

THE FOUR STATES, and which of them may write (``TestTheFourStates`` below):

    missing                 -> WRITE. No row. A cold start is not a failure and
                               initialising is the correct behaviour.
    ok, nothing banked      -> WRITE. A real row that really says nothing.
    unavailable / raised    -> DECLINE. The read did not answer.
    malformed / wrong_type  -> WRITE. A row we HAVE and can prove we may not
    wrong_version / stale      USE. Same six that stay INVALIDATE in
    ok, payload not a dict     ``load_main_checkpoint``, and for the same
                               reason: refusing them forever would wedge the
                               build permanently, with no way to re-initialise
                               after one torn write or a fourteen-day gap.

Revert the ``carry.unknown`` branch in ``save_phase_ledger`` and
``TestTheBankSurvives`` reproduces the table above exactly. Widen it to every
non-``ok`` status and ``TestTheFourStates`` goes red on the two arms that must
still write.
"""

from __future__ import annotations

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_phase_ledger import (
    LEDGER_WRITE_DECLINED,
    LEDGER_WRITE_OK,
    PHASE_FUTURES,
    PhaseBudget,
    PhasePlan,
    TERMINAL_COMPLETE,
    UNKNOWN,
    health_for,
)
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

# The three beats that bank the history. Ordinary numbers; the point of the
# file is the fold, not the magnitudes.
BANKING_BEATS = (1_000, 1_100, 1_200)
#: The beat that runs while the database is not answering.
BLIND_BEAT = 9_999


def _plan() -> PhasePlan:
    return PhasePlan(
        budgets=(
            PhaseBudget(
                name=PHASE_FUTURES,
                required=True,
                budget_ms=1_267_625,
                statement_timeout_ms=1_237_625,
                measured_input=True,
                observations=10,
                units_total=128,
                units_done=0,
            ),
        ),
        soft_limit_ms=1_500_000,
        cleanup_margin_ms=120_000,
    )


def _runner(observed_ms: int) -> cmb.PhaseRunner:
    """A runner in the state one COMPLETED beat leaves behind.

    The phase is driven through the real ``begin``/``complete`` lifecycle rather
    than by writing a record, because ``observations()`` reads the record STATUS
    and a hand-set duration would be an observation the ledger never agreed to.
    """
    runner = cmb.PhaseRunner(
        plan=_plan(),
        checkpoint=cmb.new_main_checkpoint(
            version="q269", fingerprint="fp", owner="test:1", generation=1
        ),
        checkpoint_action="fresh",
        owner="test:1",
        generation=1,
        fingerprint="fp",
        population_version="q269",
    )
    runner.ledger.record_stage_outcome(cmb.STAGED_UNIT_STAGE, observed_ms, completed=True)
    runner.ledger.begin(PHASE_FUTURES, now_ms=0)
    runner.ledger.complete(PHASE_FUTURES, now_ms=observed_ms)
    return runner


class Rig:
    """ONE durable row, served back by the read the way the database would.

    The prior state is never hand-built: it is whatever ``save_phase_ledger``
    last published. A fixture-authored payload would be this file's idea of a
    banked ledger rather than the one the producer writes, and the fold under
    test is exactly the join between the two.

    ``read_status`` is the only thing a test varies. The staged-futures identity
    is answered separately and always ``missing`` — it is a different row, and a
    fake that served one payload to both identities would make them agree by
    construction.
    """

    def __init__(self, monkeypatch):
        from app.services import durable_snapshots

        self.row: dict | None = None
        self.read_status: str = "ok"
        self.read_raises: bool = False
        self.payload_not_a_dict: bool = False
        self.writes: list[dict] = []

        async def fake_publish(envelope):
            self.writes.append({"identity": envelope.identity, "payload": envelope.payload})
            self.row = envelope.payload
            return {"status": "ok"}

        async def fake_read(identity, *, expected_version=None, max_age_s=None):
            if identity == cmb.STAGED_FUTURES_IDENTITY:
                return EnvelopeRead(status="missing", tier="durable")
            if self.read_raises:
                raise RuntimeError("canceling statement due to statement timeout")
            if self.read_status != "ok":
                # A classified non-ok read carries no envelope, which is what
                # `read_snapshot` does for every one of these statuses.
                return EnvelopeRead(status=self.read_status, tier="durable")
            if self.row is None:
                return EnvelopeRead(status="missing", tier="durable")
            return EnvelopeRead(
                status="ok",
                tier="durable",
                envelope=DurableEnvelope.build(
                    identity=identity,
                    schema_version=expected_version or "v1",
                    payload=["not", "a", "dict"] if self.payload_not_a_dict else self.row,
                    complete=True,
                    source=cmb.MAIN_BUILD_TASK,
                ),
            )

        monkeypatch.setattr(durable_snapshots, "publish_snapshot_standalone", fake_publish)
        monkeypatch.setattr(durable_snapshots, "read_snapshot_standalone", fake_read)

    async def bank_three_beats(self) -> dict:
        """Produce the prior the way production produces it: by running beats."""
        for ms in BANKING_BEATS:
            assert await cmb.save_phase_ledger(_runner(ms)) == LEDGER_WRITE_OK
        assert self.row is not None
        return dict(self.row)

    @property
    def ledger_writes(self) -> list[dict]:
        return [w for w in self.writes if w["identity"] == cmb.LEDGER_IDENTITY]


@pytest.fixture
def rig(monkeypatch) -> Rig:
    return Rig(monkeypatch)


# =============================================================================
# 1. THE PREMISE — the bank exists, and it is the only copy
# =============================================================================


class TestThePremise:
    async def test_three_beats_bank_a_rolling_history_on_one_row(self, rig):
        """Not a claim about the repair. A claim about what is at stake: ten
        beats of observations accumulate on ONE durable row, and this is the
        only place they exist."""
        banked = await rig.bank_three_beats()
        assert banked["history"] == {PHASE_FUTURES: list(BANKING_BEATS)}
        assert banked[cmb.UNIT_WORST_HISTORY_KEY] == {PHASE_FUTURES: list(BANKING_BEATS)}
        assert len(rig.ledger_writes) == len(BANKING_BEATS)

    async def test_the_payload_is_a_fold_not_an_independent_rebuild(self, rig):
        """WHY an unread prior is destructive here and not merely unhelpful. The
        beat contributes ONE observation; the other two can only be in the
        payload because they were read off the prior row."""
        await rig.bank_three_beats()
        written = rig.ledger_writes[-1]["payload"]
        assert written["history"][PHASE_FUTURES] == list(BANKING_BEATS)
        assert BANKING_BEATS[-1] == written["history"][PHASE_FUTURES][-1]
        # The beat itself observed exactly one duration.
        assert _runner(BANKING_BEATS[-1]).ledger.observations() == {
            PHASE_FUTURES: BANKING_BEATS[-1]
        }


# =============================================================================
# 2. THE BANK SURVIVES A READ THAT DID NOT ANSWER — the repair
# =============================================================================


class TestTheBankSurvives:
    async def test_a_beat_whose_read_is_unavailable_issues_no_write_at_all(self, rig):
        """The whole repair in one assertion. There is no safe partial payload
        to write — ``publish_snapshot`` replaces the row — so the only thing
        that preserves the bank is not writing."""
        await rig.bank_three_beats()
        before = len(rig.ledger_writes)
        rig.read_status = "unavailable"
        await cmb.save_phase_ledger(_runner(BLIND_BEAT))
        assert len(rig.ledger_writes) == before

    async def test_and_the_banked_history_ring_and_floors_are_untouched(self, rig):
        """The consequence, read off the row rather than off the call count."""
        banked = await rig.bank_three_beats()
        rig.read_status = "unavailable"
        await cmb.save_phase_ledger(_runner(BLIND_BEAT))
        assert rig.row == banked
        assert rig.row["history"] == {PHASE_FUTURES: list(BANKING_BEATS)}
        assert BLIND_BEAT not in rig.row["history"][PHASE_FUTURES]

    async def test_a_read_that_RAISED_is_the_same_unknown(self, rig):
        """The second door into the same room. This arm used to be commented
        'a lost history is not a lost ledger' and fell through to four empty
        dicts — which is the identical destructive fold, reached by an exception
        instead of by a classification."""
        banked = await rig.bank_three_beats()
        rig.read_raises = True
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_DECLINED
        assert rig.row == banked

    async def test_the_decline_is_reported_and_is_not_ok(self, rig):
        """Explicit failure reporting is retained: the stand-down has its own
        word on both the return value and the runner, so it is never confused
        with a write that was tried and lost (``error``) or with one that
        succeeded."""
        await rig.bank_three_beats()
        rig.read_status = "unavailable"
        runner = _runner(BLIND_BEAT)
        status = await cmb.save_phase_ledger(runner)
        assert status == LEDGER_WRITE_DECLINED
        assert status != LEDGER_WRITE_OK
        assert runner.ledger.ledger_write == LEDGER_WRITE_DECLINED

    async def test_it_says_which_read_status_declined_it(self, rig, caplog):
        """A stand-down with no cause in the log is a silent one. The read's own
        status travels into the message so an operator is not left deciding
        between 'the database did not answer' and 'the code refused'."""
        import logging

        await rig.bank_three_beats()
        rig.read_status = "unavailable"
        with caplog.at_level(logging.ERROR):
            await cmb.save_phase_ledger(_runner(BLIND_BEAT))
        messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("UNREADABLE" in m and "unavailable" in m for m in messages), messages

    async def test_the_defect_returns_the_instant_the_guard_is_loosened(self, rig, monkeypatch):
        """THE CONTROL. Without this the file only proves that a function which
        returns early writes nothing. Here the classified reader is loosened to
        the pre-repair answer — four empty dicts, ``unknown`` False, which is
        exactly what ``load_phase_carryover`` returned for every read problem —
        and the bank dies. That is the behaviour on master before this change."""
        banked = await rig.bank_three_beats()

        async def pre_repair_reader():
            return cmb.PhaseCarryover({}, {}, {}, {}, status="unavailable", unknown=False)

        monkeypatch.setattr(cmb, "read_phase_carryover", pre_repair_reader)
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_OK
        assert rig.row["history"] == {PHASE_FUTURES: [BLIND_BEAT]}
        assert rig.row != banked


# =============================================================================
# 3. THE FOUR STATES — and the three that must still write
# =============================================================================


class TestTheFourStates:
    async def test_a_genuinely_missing_row_initialises(self, rig):
        """A cold start is not a failure. Nothing is banked, nothing can be
        destroyed, and refusing here would mean the row could never be created.

        This is the first arm a too-wide guard breaks."""
        assert await cmb.save_phase_ledger(_runner(BANKING_BEATS[0])) == LEDGER_WRITE_OK
        assert rig.row["history"] == {PHASE_FUTURES: [BANKING_BEATS[0]]}

    async def test_a_valid_empty_row_is_a_real_answer_and_is_written_over(self, rig):
        """``ok`` with nothing banked. The read ANSWERED; that the answer is
        empty is knowledge, not blindness."""
        rig.row = {"history": {}, "floors": {}}
        assert await cmb.save_phase_ledger(_runner(BANKING_BEATS[0])) == LEDGER_WRITE_OK
        assert rig.row["history"] == {PHASE_FUTURES: [BANKING_BEATS[0]]}

    async def test_a_successful_read_still_folds_and_advances(self, rig):
        """The positive control for the whole change: the ordinary path is
        untouched. A fix that stopped the beat writing would pass every test in
        section 2 and be worthless."""
        await rig.bank_three_beats()
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_OK
        assert rig.row["history"] == {PHASE_FUTURES: [*BANKING_BEATS, BLIND_BEAT]}

    async def test_an_unavailable_read_declines(self, rig):
        """The one arm that stands down, stated beside its three siblings so the
        table is readable in one place."""
        await rig.bank_three_beats()
        rig.read_status = "unavailable"
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_DECLINED

    @pytest.mark.parametrize("status", ["malformed", "wrong_type", "wrong_version", "stale"])
    async def test_a_row_we_have_and_may_not_use_is_still_write_authorised(self, rig, status):
        """Corrupt / incompatible / expired. These are NOT the unknown: the
        database answered, and what it returned is a row we can prove we may not
        resume from — the same six statuses that stay ``INVALIDATE`` in
        ``load_main_checkpoint``.

        Refusing them would be a strictly worse bug than the one this file
        fixes: one torn write, or fourteen days of ``STATE_MAX_AGE_S`` passing,
        would wedge the ledger permanently with no path back to a good row.
        Preserving a row nobody may read preserves nothing."""
        await rig.bank_three_beats()
        rig.read_status = status
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_OK
        assert rig.row["history"] == {PHASE_FUTURES: [BLIND_BEAT]}

    async def test_an_ok_read_whose_payload_is_not_a_dict_is_also_write_authorised(self, rig):
        """The seventh arm of the same branch, and the one a reader misses: the
        status is ``ok``, so ``unknown`` is False, and the row is replaced."""
        await rig.bank_three_beats()
        rig.payload_not_a_dict = True
        assert await cmb.save_phase_ledger(_runner(BLIND_BEAT)) == LEDGER_WRITE_OK


# =============================================================================
# 4. THE READER — what it classifies, and what it does NOT change
# =============================================================================


class TestTheClassifiedReader:
    @pytest.mark.parametrize(
        "status,unknown",
        [
            ("missing", False),
            ("malformed", False),
            ("wrong_type", False),
            ("wrong_version", False),
            ("stale", False),
            ("unavailable", True),
        ],
    )
    async def test_only_unavailable_is_unknown(self, rig, status, unknown):
        """``unknown`` is not 'the dicts came back empty' — five of these six
        also come back empty. It is 'the read did not answer'."""
        rig.read_status = status
        carry = await cmb.read_phase_carryover()
        assert carry.unknown is unknown
        assert carry.status == status
        assert (carry.history, carry.floors, carry.unit_costs, carry.worst_history) == (
            {}, {}, {}, {},
        )

    async def test_the_plan_facing_reader_is_unchanged_in_shape_and_in_answer(self, rig):
        """``load_phase_carryover`` keeps its four-tuple and keeps collapsing
        every read problem into it. That conflation is harmless for the PLAN —
        an empty history produces ``no_data`` and a provisional plan, which is
        the right answer to being blind — and three callers plus their test
        doubles depend on the signature. Only the SAVE needed the fifth value."""
        await rig.bank_three_beats()
        rig.read_status = "unavailable"
        assert await cmb.load_phase_carryover() == ({}, {}, {}, {})
        assert await cmb.load_phase_history() == ({}, {})
        assert await cmb.load_phase_measurements() == ({}, {}, {})

    async def test_and_it_still_returns_the_bank_on_a_good_read(self, rig):
        """The control for the test above."""
        await rig.bank_three_beats()
        history, _floors, _costs, ring = await cmb.load_phase_carryover()
        assert history == {PHASE_FUTURES: list(BANKING_BEATS)}
        assert ring == {PHASE_FUTURES: list(BANKING_BEATS)}


# =============================================================================
# 5. THE SAFETY CONTRACT — what a declined write does and does not reach
# =============================================================================


class TestTheSafetyContract:
    def test_a_declined_write_is_unknown_never_green(self):
        """The named dependency. ``health_for`` asks ``ledger_write != "ok"``,
        so the new word needs no change there — but the contract has to be
        asserted, not assumed, because it is the only thing standing between a
        stand-down and a run reporting success it cannot vouch for."""
        assert (
            health_for(
                terminal=TERMINAL_COMPLETE,
                ledger_write=LEDGER_WRITE_DECLINED,
                artifact_fresh=True,
                artifact_generation=7,
            )
            == UNKNOWN
        )

    def test_the_verdict_that_reads_that_health_is_not_complete(self):
        """One layer up: the hourly one-off's exit code comes from
        ``verdict_for``, which consumes ``health`` rather than re-deriving it.
        A declined ledger write therefore exits 1, which is correct — no
        telemetry persisted is not a clean run."""
        from app.utils.task_verdict import COMPLETE, _phase_ledger_verdict

        verdict = _phase_ledger_verdict(
            {"terminal": TERMINAL_COMPLETE, "health": UNKNOWN}
        )
        assert verdict.verdict != COMPLETE

    def test_the_old_path_could_report_green_on_the_beat_that_destroyed_the_bank(self):
        """Why the return value had to change and not only the write. Before the
        repair this path returned ``ok``, and ``ok`` is the single input
        ``health_for`` needs to be free to say GREEN."""
        assert (
            health_for(
                terminal=TERMINAL_COMPLETE,
                ledger_write=LEDGER_WRITE_OK,
                artifact_fresh=True,
                artifact_generation=7,
            )
            != UNKNOWN
        )

    async def test_the_decline_writes_to_no_other_durable_identity_either(self, rig):
        """Publication and resume are not reached by this stand-down, and the
        reason is structural: ``save_phase_ledger`` runs AFTER the artifact has
        published and AFTER ``save_main_checkpoint`` has banked the resumable
        phases onto ``CHECKPOINT_IDENTITY``, a different row. The assertion
        below is the narrow, checkable half — declining issues no durable write
        of any identity, so it cannot disturb either."""
        await rig.bank_three_beats()
        before = len(rig.writes)
        rig.read_status = "unavailable"
        await cmb.save_phase_ledger(_runner(BLIND_BEAT))
        assert len(rig.writes) == before

    async def test_the_declined_beat_leaves_the_runners_own_state_alone(self, rig):
        """It is a write stand-down, not a run stand-down: nothing about what the
        beat did is rewritten, only the record of it is withheld."""
        await rig.bank_three_beats()
        rig.read_status = "unavailable"
        runner = _runner(BLIND_BEAT)
        await cmb.save_phase_ledger(runner)
        assert runner.ledger.observations() == {PHASE_FUTURES: BLIND_BEAT}
