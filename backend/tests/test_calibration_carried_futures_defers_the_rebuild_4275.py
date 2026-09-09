"""A beat that CARRIES the futures phase must still get its rebuild — #4275.

CAL-P1064. The defect this file guards, measured on production 2026-09-09:

    beat                  terminal              elapsed  carried                units
    2026-09-09T06:15:48Z  complete, published      47 s  ['futures','sports']       0
    2026-09-09T07:50:03Z  complete, published      23 s  ['futures']                0

2 of 2. A resumed beat reuses the futures phase's banked rows, so
``_run_staged_futures`` — the only caller of ``PhaseRunner.defer_rebuild`` — never
runs, ``rebuild_deferred`` stays False, and the post-publish rebuild pass takes its
``not_deferred`` early return. The beat hands back twenty-two minutes of window with
the 128-unit census incomplete. Between 04:28Z and 08:23Z the census sat at 91/128:
four hours, nothing, while ``/calibration`` told readers its market data was 28 hours
old.

**Why there are controls here and not just assertions.** A repair that called
``defer_rebuild()`` unconditionally satisfies every assertion about the carried case
while quietly making every non-producer build open a second session and re-read the
roster. So the file asserts both directions: carried ⇒ deferred, and *not* carried
⇒ not deferred, including a beat that carries a DIFFERENT phase. Without the second
half the first proves nothing about the predicate.
"""

from __future__ import annotations

import pytest

from app.tasks import calibration_main_build as cmb
from app.utils.calibration_phase_ledger import (
    MainBuildCheckpoint,
    PHASE_DIAGNOSTICS,
    PHASE_FUTURES,
    PHASE_SPORTS,
    RESUME,
    FRESH,
)

pytestmark = pytest.mark.asyncio

VERSION = "test-population-v1"
FINGERPRINT = "fingerprint-4275"


def _checkpoint(*completed: str) -> MainBuildCheckpoint:
    """A checkpoint carrying exactly ``completed``, with whole outputs for each.

    ``PhaseRunner.carry`` is driven by ``completed_phases``; the outputs matter
    only so nothing downstream reads a carried phase as empty.
    """
    return MainBuildCheckpoint(
        version=VERSION,
        generation=1,
        owner="prior-beat",
        input_fingerprint=FINGERPRINT,
        completed_phases=tuple(completed),
        phase_outputs={name: {"stored": True, "values": {}} for name in completed},
    )


@pytest.fixture
def wiring(monkeypatch):
    """``build_runner`` with its two durable reads stubbed and nothing else.

    ``derive_plan`` runs for real on an empty history — the plan is not what is
    under test, and a fake one could not tell us whether the real one is
    compatible with the branch being added.
    """

    async def _no_measurements():
        return {}, {}, {}

    monkeypatch.setattr(cmb, "load_phase_measurements", _no_measurements)

    def _serve(checkpoint: MainBuildCheckpoint, action: str = RESUME):
        async def _load(**kwargs):
            return checkpoint, action

        monkeypatch.setattr(cmb, "load_main_checkpoint", _load)

    return _serve


async def _runner(wiring, checkpoint, action=RESUME):
    wiring(checkpoint, action)
    runner, returned_action = await cmb.build_runner(
        population_version=VERSION, fingerprint=FINGERPRINT
    )
    return runner, returned_action


class TestTheShip:
    async def test_a_carried_futures_phase_defers_the_rebuild(self, wiring):
        """The 07:50:03Z beat: ``carried: ['futures']``, and it must now rebuild."""
        runner, _ = await _runner(wiring, _checkpoint(PHASE_FUTURES))

        assert runner.is_carried(PHASE_FUTURES) is True
        assert runner.rebuild_deferred is True, (
            "a beat that carries the futures phase never reaches the futures "
            "phase's own defer_rebuild() call, so the rebuild pass would take its "
            "not_deferred early return and the whole window would go unspent"
        )

    async def test_the_06_15Z_shape_defers_too(self, wiring):
        """``carried: ['futures','sports']`` — the other production specimen."""
        runner, _ = await _runner(wiring, _checkpoint(PHASE_FUTURES, PHASE_SPORTS))

        assert runner.rebuild_deferred is True

    async def test_the_reason_is_recorded_under_its_own_name(self, wiring):
        """Ruling 075 clause 2: the two deferral reasons must not share an entry.

        "Deferred because the served bank covered the plan" and "deferred because
        the phase was carried" are different facts about a beat. Folding them into
        one stage makes the second invisible in the very ledger built to find it.
        """
        runner, _ = await _runner(wiring, _checkpoint(PHASE_FUTURES))

        assert "staged:rebuild_deferred:carried" in runner.ledger.stages
        # And NOT under the publish-first reorder's name, which describes a
        # different beat and is written by the futures phase itself.
        assert "staged:rebuild_deferred" not in runner.ledger.stages


class TestTheControls:
    """Each of these fails against a repair that defers unconditionally."""

    async def test_a_beat_carrying_nothing_does_not_defer(self, wiring):
        """A cold beat runs the futures phase inline; deferring is that phase's call."""
        runner, _ = await _runner(wiring, _checkpoint(), action=FRESH)

        assert runner.is_carried(PHASE_FUTURES) is False
        assert runner.rebuild_deferred is False
        assert "staged:rebuild_deferred:carried" not in runner.ledger.stages

    async def test_a_beat_carrying_a_DIFFERENT_phase_does_not_defer(self, wiring):
        """The predicate is the futures phase, not "resumed from something".

        Without this the branch could read ``if checkpoint.completed_phases:`` and
        every assertion above would still pass, while a beat that resumed only its
        diagnostics phase — whose futures phase runs inline and defers on its own
        terms — would be deferred twice.
        """
        runner, _ = await _runner(wiring, _checkpoint(PHASE_SPORTS, PHASE_DIAGNOSTICS))

        assert runner.is_carried(PHASE_SPORTS) is True
        assert runner.is_carried(PHASE_FUTURES) is False
        assert runner.rebuild_deferred is False


class TestTheContractTheRepairRidesOn:
    async def test_defer_rebuild_is_idempotent(self, wiring):
        """Both setters may fire on one runner without the flag meaning less.

        They are mutually exclusive today — a carried phase does not run, so the
        futures phase's own call cannot follow ``build_runner``'s — but the flag
        is documented one-way and the consumer reads it once, so the property is
        worth pinning rather than reasoning about.
        """
        runner, _ = await _runner(wiring, _checkpoint(PHASE_FUTURES))
        assert runner.rebuild_deferred is True

        runner.defer_rebuild()

        assert runner.rebuild_deferred is True

    async def test_the_flag_defaults_off_on_a_fresh_runner(self, wiring):
        """A build that never took either path behaves exactly as it did before."""
        runner, action = await _runner(wiring, _checkpoint(), action=FRESH)

        assert action == FRESH
        assert runner.rebuild_deferred is False

    async def test_the_action_the_caller_branches_on_is_unchanged(self, wiring):
        """``build_runner`` returns ``(runner, action)``; the repair touches neither.

        The orchestrator's REFUSE branch keys on this value, so a repair that
        altered it would change which beats run at all.
        """
        _, action = await _runner(wiring, _checkpoint(PHASE_FUTURES), action=RESUME)

        assert action == RESUME
