"""#6599, second site: a CHECKPOINT we could not READ is not one we may write over.

PILLAR: TRUTH. SHIP: a temporary database-read failure stops erasing progress
toward a complete accuracy-page rebuild.

## What this is about

This is ``load_staged_cursor``'s defect one layer up, found while fixing it
(``test_calibration_unreadable_cursor_is_not_an_empty_one_6599.py``, merged as
``2d84dc1b6``). The two functions read two different durable rows for two
different purposes, and both classified the same UNKNOWN the same wrong way.

``load_main_checkpoint`` reads the build's phase checkpoint — which of the three
resumable phases a prior beat completed, and their stored output. Six read
statuses mean *we have a row and can prove we may not resume it* (``malformed``,
``wrong_type``, ``wrong_version``, ``stale``, plus the decoder's own version and
fingerprint mismatches). One does not: ``unavailable`` is
``app.utils.durable_state``'s named UNKNOWN — **the database did not answer** —
and it was being folded in with the six, returning ``INVALIDATE`` and a blank
checkpoint. The ``except`` arm in ``build_runner`` said the quiet part in a
comment: *"an unreadable checkpoint is a fresh one"*.

## Why that is destructive rather than merely wasteful

The beat then runs on the blank, and at its tail
(``_precompute_calibration_main``) ``runner.build_checkpoint()`` folds in the
phases **this beat** completed — carried phases are re-banked from the ledger,
and with nothing carried there are none — and ``save_main_checkpoint`` writes
that over the durable row the read could not see.

So the loss is precise, and it is worth stating precisely rather than as "the
checkpoint is wiped": the row is replaced by a SUBSET of itself. A beat that had
two phases banked and completes one writes one back. On a build that does not
fit in a single beat, that is the difference between three beats converging and
three beats each redoing the first phase. ``TestTheDurableRowIsNotOverwritten``
drives exactly that through the real tail and measures it.

``REFUSE`` is the action the build already has for "doing nothing is correct",
its caller already returns on it without running a phase, and the durable row is
therefore untouched.

## What is NOT changed, deliberately — and each has a control below

* ``missing`` is still ``FRESH``. A cold start is not a failure, and a build
  that refused to start because nothing had ever been published would be a
  strictly worse bug than the one being fixed.
* Every genuine invalidator still discards whole: ``malformed``,
  ``wrong_type``, ``wrong_version``, ``stale``, and the decoder's population and
  fingerprint mismatches. Those are evidence ABOUT THE ROW.
* The lease refusal keeps its own reason and its own caller behaviour. Two
  workers each advancing half a checkpoint is the corruption that branch exists
  to prevent, and it is a HEALTHY outcome — the hourly one-off exits 0 on it.

## The reason, and why it is not cosmetic

``REFUSE`` now has two unrelated causes, so the action alone stopped being
diagnostic — CAL-P024's lesson, which the staged cursor already learned. The
reason travels beside the action (``load_main_checkpoint`` returns a triple,
``PhaseRunner`` carries it) for one behavioural purpose beyond the ledger:
``scripts/run_calibration_hourly.is_checkpoint_declined`` matches on BOTH
``status`` and ``reason``, because "a skip for any other reason is a build that
did not happen for a reason nobody has vetted, and those must keep exiting 1".
A read failure reported as ``checkpoint_leased`` would exit 0 — a green tick
over a build that did not run. ``TestTheHourlyJobStillFailsLoudly`` pins that.

## What this ship does NOT claim

It does not claim to be the cause of any particular reset on the ring; a beat
that stood down recorded nothing until this change, which is why both
``record_stage`` calls are now unconditional. It does not make the accuracy page
complete or trustworthy — the rebuild has never once reached 128 of 128, and
this removes one cause of going backwards, not all of them.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import durable_snapshots as ds
from app.tasks import calibration_main_build as cmb
from app.tasks import precompute_calibration as pc
from app.utils.calibration_phase_ledger import (
    CHECKPOINT_REASON_ABSENT,
    CHECKPOINT_REASON_LEASE_HELD,
    CHECKPOINT_REASON_READ_FAILED,
    FRESH,
    INVALIDATE,
    MAIN_CHECKPOINT_SCHEMA,
    PHASE_DIAGNOSTICS,
    PHASE_OUTPUT_KEYS,
    PHASE_SPORTS,
    REFUSE,
    RESUME,
)
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

VERSION = "q268"
FINGERPRINT = "fp-main"
OWNER = "worker:test"
GENERATION = 7

#: The two phases the "prior beat" banked. ``futures`` is deliberately NOT one
#: of them: ``build_checkpoint`` declines to bank it while a rebuild is in
#: flight (CAL-P081), so using it would measure that rule instead of this one.
BANKED_PHASES = (PHASE_SPORTS, PHASE_DIAGNOSTICS)


class _Durable:
    """The durable store, per identity, with a switch for the next READ.

    Patched at ``app.services.durable_snapshots`` rather than at
    ``calibration_main_build``, so the REAL ``load_main_checkpoint``,
    ``save_main_checkpoint`` and ``build_runner`` are what these tests drive. A
    stand-in for the subject would test the stand-in.
    """

    def __init__(self):
        self.payloads: dict[str, dict] = {}
        #: identity -> status to fail the NEXT read with, or ``"raise"``.
        self.next_read: dict[str, str] = {}
        self.writes: dict[str, int] = {}

    async def read(self, identity, *, expected_version=None, max_age_s=None):
        failure = self.next_read.pop(identity, None)
        if failure == "raise":
            raise RuntimeError("canceling statement due to statement timeout")
        if failure is not None:
            return EnvelopeRead(
                status=failure,
                tier=ds.TIER_DURABLE,
                error_class="OperationalError",
                error="the database did not answer",
            )
        payload = self.payloads.get(identity)
        if payload is None:
            return EnvelopeRead(status="missing", tier=ds.TIER_DURABLE)
        return EnvelopeRead(
            status="ok",
            tier=ds.TIER_DURABLE,
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=MAIN_CHECKPOINT_SCHEMA,
                payload=payload,
                generated_at=datetime.now(timezone.utc),
                source=cmb.MAIN_BUILD_TASK,
            ),
        )

    async def publish(self, envelope):
        self.writes[envelope.identity] = self.writes.get(envelope.identity, 0) + 1
        self.payloads[envelope.identity] = envelope.payload
        return {"status": "ok"}

    # --- readings of the checkpoint row, for assertions ----------------------

    @property
    def checkpoint_payload(self) -> dict:
        return self.payloads.get(cmb.CHECKPOINT_IDENTITY) or {}

    @property
    def banked_phases(self) -> tuple[str, ...]:
        return tuple(self.checkpoint_payload.get("completed_phases") or ())

    @property
    def checkpoint_writes(self) -> int:
        return self.writes.get(cmb.CHECKPOINT_IDENTITY, 0)


@pytest.fixture
def durable(monkeypatch):
    store = _Durable()
    monkeypatch.setattr(ds, "read_snapshot_standalone", store.read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", store.publish)
    return store


async def _bank_prior(durable, beat) -> None:
    """Put a prior checkpoint on disk by RUNNING A BEAT that banks two phases.

    Hand-building the payload was the first attempt and was the wrong rig: it
    measures the fixture's idea of a stored phase output, not the one
    ``build_checkpoint`` actually writes. Every row these tests then defend is a
    row the real fold and the real save produced.
    """
    summary = await beat(completes=BANKED_PHASES)
    assert summary["status"] != "skipped"
    assert tuple(durable.banked_phases) == BANKED_PHASES
    # The banking beat stamped its own lease, which by design outlives the
    # Celery hard limit. An hour passes before the next beat, so by then it has
    # expired; a LIVE lease is a different subject and has its own class below.
    durable.payloads[cmb.CHECKPOINT_IDENTITY]["lease_expires_at"] = 0.0
    durable.writes.clear()


def _hand_the_lease_to(durable, owner: str, *, seconds: float = 600.0) -> None:
    """Surgery on the REAL stored row: another worker now holds its lease."""
    import time as _time

    payload = durable.payloads[cmb.CHECKPOINT_IDENTITY]
    payload["owner"] = owner
    payload["lease_expires_at"] = _time.time() + seconds


async def _load(**over):
    kw = dict(
        population_version=VERSION,
        fingerprint=FINGERPRINT,
        owner=OWNER,
        generation=GENERATION,
    )
    kw.update(over)
    return await cmb.load_main_checkpoint(**kw)


# =============================================================================
# 1. THE SUBJECT — UNKNOWN stands the beat down; it does not invalidate
# =============================================================================


class TestAnUnreadableCheckpointIsRefusedNotInvalidated:
    """The two ways a read can fail to answer, and one verdict for both."""

    @pytest.mark.asyncio
    async def test_an_unavailable_read_refuses(self, durable, beat):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        checkpoint, action, reason = await _load()

        assert action == REFUSE
        assert reason == CHECKPOINT_REASON_READ_FAILED
        # And it hands back a blank rather than a half-read row: nothing may be
        # resumed off a read that did not answer either.
        assert checkpoint.completed_phases == ()

    @pytest.mark.asyncio
    async def test_a_raising_read_refuses_through_build_runner(self, durable, beat):
        """``read_snapshot_standalone`` catches its own exceptions, so this arm
        fires on the layer above — an import, a session factory, a codec. It
        carried the same "an unreadable checkpoint is a fresh one" comment."""
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "raise"

        runner, action = await cmb.build_runner(
            population_version=VERSION, fingerprint=FINGERPRINT
        )

        assert action == REFUSE
        assert runner.checkpoint_reason == CHECKPOINT_REASON_READ_FAILED

    @pytest.mark.asyncio
    async def test_the_refusal_carries_nothing_forward(self, durable, beat):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        runner, action = await cmb.build_runner(
            population_version=VERSION, fingerprint=FINGERPRINT
        )

        assert action == REFUSE
        assert runner.carried_phases == []
        assert runner.rebuild_deferred is False


# =============================================================================
# 2. THE SHIP — the durable row survives a read that did not answer
# =============================================================================


class TestTheDurableRowIsNotOverwritten:
    """Measured through the real tail of ``_precompute_calibration_main``.

    The beat body is stood in for, because what is under test is what the tail
    WRITES given what the head classified — but the head (``build_runner``,
    ``load_main_checkpoint``), the fold (``runner.build_checkpoint``) and the
    write (``save_main_checkpoint``) are all the real ones.
    """

    @pytest.mark.asyncio
    async def test_a_beat_that_could_not_read_writes_nothing(self, durable, beat):
        """The ship. Asserted on the ROW ALONE, deliberately.

        The reason string has its own test below, because a test that checks
        the status first would report the damage as a wording mismatch: with the
        old classification this assertion is what fails, and it fails at
        ``('sports',) != ('sports', 'diagnostics')`` — a beat that completed one
        phase writing its one phase over the two the read could not see.
        """
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        await beat(completes=(PHASE_SPORTS,))

        assert durable.banked_phases == BANKED_PHASES
        assert durable.checkpoint_writes == 0

    @pytest.mark.asyncio
    async def test_the_stand_down_is_reported_as_its_own_reason(self, durable, beat):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        summary = await beat(completes=(PHASE_SPORTS,))

        assert summary["status"] == "skipped"
        assert summary["reason"] == "checkpoint_unreadable"

    @pytest.mark.asyncio
    async def test_a_readable_row_still_resumes_and_advances(self, durable, beat):
        """The control that keeps the fix from being "refuse everything": a
        healthy read carries both phases and the beat banks a third."""
        await _bank_prior(durable, beat)

        summary = await beat(completes=(PHASE_SPORTS, PHASE_DIAGNOSTICS))

        assert summary["status"] != "skipped"
        assert set(durable.banked_phases) == set(BANKED_PHASES)
        assert durable.checkpoint_writes == 1

    @pytest.mark.asyncio
    async def test_an_invalidating_row_still_discards_whole(self, durable, beat):
        """A row we HAVE and may not resume is still replaced by this beat's
        subset. That is not the defect — it is the correct answer to evidence of
        incompatibility, and narrowing it is explicitly not this ship."""
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "wrong_version"

        summary = await beat(completes=(PHASE_SPORTS,))

        assert summary["status"] != "skipped"
        assert durable.banked_phases == (PHASE_SPORTS,)
        assert durable.checkpoint_writes == 1


# =============================================================================
# 3. CONTROLS — everything that is NOT the named UNKNOWN keeps its behaviour
# =============================================================================


class TestEveryOtherStatusIsUnchanged:
    @pytest.mark.asyncio
    async def test_a_missing_row_is_a_cold_start_not_a_refusal(self, durable):
        checkpoint, action, reason = await _load()

        assert action == FRESH
        assert reason == CHECKPOINT_REASON_ABSENT
        assert checkpoint.completed_phases == ()

    @pytest.mark.parametrize("status", ["malformed", "wrong_type", "wrong_version", "stale"])
    @pytest.mark.asyncio
    async def test_a_row_we_may_not_vouch_for_still_invalidates(self, durable, beat, status):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = status

        _, action, reason = await _load()

        assert action == INVALIDATE
        assert reason == f"envelope_{status}"

    @pytest.mark.asyncio
    async def test_a_moved_population_version_still_invalidates(self, durable, beat):
        """Through the DECODER rather than the read — the contract that fix
        leaves alone. The row is readable and says it is for another build."""
        await _bank_prior(durable, beat)

        _, action, _ = await _load(population_version="q999")

        assert action == INVALIDATE

    @pytest.mark.asyncio
    async def test_a_moved_fingerprint_still_invalidates(self, durable, beat):
        await _bank_prior(durable, beat)

        _, action, _ = await _load(fingerprint="fp-moved")

        assert action == INVALIDATE

    @pytest.mark.asyncio
    async def test_a_resumable_row_still_resumes(self, durable, beat):
        await _bank_prior(durable, beat)

        checkpoint, action, _ = await _load()

        assert action == RESUME
        assert checkpoint.completed_phases == BANKED_PHASES


class TestTheLeaseRefusalKeepsItsOwnIdentity:
    """The stand-down that existed before this fix, and still means what it did."""

    @pytest.mark.asyncio
    async def test_a_held_lease_refuses_with_its_own_reason(self, durable, beat):
        await _bank_prior(durable, beat)
        _hand_the_lease_to(durable, "worker:other")

        checkpoint, action, reason = await _load()

        assert action == REFUSE
        assert reason == CHECKPOINT_REASON_LEASE_HELD
        assert checkpoint.owner == "worker:other"

    @pytest.mark.asyncio
    async def test_the_two_refusals_are_told_apart_at_the_caller(self, durable, beat):
        await _bank_prior(durable, beat)
        _hand_the_lease_to(durable, "worker:other")

        summary = await beat(completes=())

        assert summary["status"] == "skipped"
        assert summary["reason"] == "checkpoint_leased"
        assert summary["owner"] == "worker:other"
        assert durable.checkpoint_writes == 0


class TestTheHourlyJobStillFailsLoudly:
    """The behavioural consequence of the reason, and the reason it is not cosmetic."""

    def test_a_lease_decline_is_the_vetted_one(self):
        from scripts.run_calibration_hourly import is_checkpoint_declined

        assert is_checkpoint_declined({"status": "skipped", "reason": "checkpoint_leased"})

    def test_an_unreadable_decline_is_not(self):
        from scripts.run_calibration_hourly import is_checkpoint_declined

        # Exit 1, not 0. A build that did not run because the database did not
        # answer must not be indistinguishable from a healthy overlap.
        assert not is_checkpoint_declined(
            {"status": "skipped", "reason": "checkpoint_unreadable"}
        )


# =============================================================================
# 4. COUNTABILITY — a stood-down beat is not invisible
# =============================================================================


class TestTheStandDownIsRecorded:
    """#6723's second half, applied here: a refusal that records nothing reads
    exactly like a beat that never ran, and "how often is this happening" has to
    be answerable from the ring."""

    @pytest.mark.asyncio
    async def test_the_refusal_records_its_action_and_its_reason(self, durable, beat):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        runner, _ = await cmb.build_runner(
            population_version=VERSION, fingerprint=FINGERPRINT
        )

        assert f"checkpoint:{REFUSE}" in runner.ledger.stage_counts
        assert (
            f"checkpoint:reason:{CHECKPOINT_REASON_READ_FAILED}"
            in runner.ledger.stage_counts
        )

    @pytest.mark.asyncio
    async def test_the_denominator_is_recorded_too(self, durable, beat):
        """A count of refusals with no count of beats is not a rate. Every
        action records, not only the ones that stand down."""
        await _bank_prior(durable, beat)

        runner, action = await cmb.build_runner(
            population_version=VERSION, fingerprint=FINGERPRINT
        )

        assert action == RESUME
        assert f"checkpoint:{RESUME}" in runner.ledger.stage_counts
        assert f"checkpoint:reason:{RESUME}" in runner.ledger.stage_counts

    @pytest.mark.asyncio
    async def test_the_reason_reaches_the_ledger_row(self, durable, beat):
        await _bank_prior(durable, beat)
        durable.next_read[cmb.CHECKPOINT_IDENTITY] = "unavailable"

        await beat(completes=())

        ledger = durable.payloads.get(cmb.LEDGER_IDENTITY) or {}
        assert ledger.get("checkpoint_reason") == CHECKPOINT_REASON_READ_FAILED
        assert ledger.get("checkpoint_action") == REFUSE


# =============================================================================
# The rig for the caller-level tests
# =============================================================================


@pytest.fixture
def plan_wiring(monkeypatch):
    """``build_runner`` with only its history read stubbed.

    ``derive_plan`` runs for real on an empty history: the plan is not what is
    under test, and a fake one could not tell us whether the real one is
    compatible with the branch being added.
    """

    async def _no_measurements():
        return {}, {}, {}

    monkeypatch.setattr(cmb, "load_phase_measurements", _no_measurements)


@pytest.fixture
def beat(monkeypatch, plan_wiring):
    """One run of ``_precompute_calibration_main`` with the BODY stood in for.

    Everything this file is about is outside the body: the checkpoint read that
    classifies, the early return that stands down, and the tail that folds and
    writes. ``completes`` names the phases the stand-in body finishes, which is
    what the real tail then banks.
    """
    monkeypatch.setattr(pc, "_main_input_fingerprint", lambda: FINGERPRINT)
    monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", VERSION)

    async def _run(completes):
        async def _body(runner):
            # The real phase protocol, which is what makes the tail's fold real:
            # begin, capture every key the phase owes, complete.
            for phase in completes:
                runner.begin(phase)
                for key in sorted(PHASE_OUTPUT_KEYS[phase]):
                    runner.record(phase, key, [])
                runner.complete(phase)
            return {"status": "ok"}

        monkeypatch.setattr(pc, "_run_calibration_main_build", _body)
        return await pc._precompute_calibration_main()

    return _run
