"""CAL-P993 (calibration-028) — a killed beat and a partial beat stop sharing one word.

``PhaseRunner.classify_failure`` maps both ``StagedFuturesIncomplete`` and
``asyncio.CancelledError`` to the terminal ``cancelled``, and both mappings are
right: neither is a failure, neither should page anybody. But they are opposite
facts about the producer —

* ``incomplete``  = the staged build ran out of window with units banked. The
  number "is it converging?" is asking for.
* ``interrupted`` = the runtime took the worker away mid-phase. Measured on the
  168-beat ring 2026-09-03: **21 of 23** such beats had a Heroku release inside
  their own window, and the last four terminated 16-28 s after one. A finding
  about the deploy cadence, not about calibration.

— and ruling 009's freeze score, the number that decides whether
``precompute_calibration.py`` may be touched at all, is computed off a ring in
which the difference could not be written down.

THE DEFECT ARM, and why it is written the way it is
---------------------------------------------------
``test_a_bare_cancellation_used_to_vanish_from_the_ledger`` reproduces the
pre-993 shape directly rather than importing it: ``asyncio.CancelledError()``
renders as the EMPTY STRING, ``PhaseLedger.fail`` stores ``detail or None``, so
the old ``detail=str(exc)[:200]`` wrote nothing at all and the phase record read
as though nothing had been recorded. Production says so: every ``cancelled``
phase in ``calibration:main:phase_ledger`` carries no ``detail`` key.

Every test here EXECUTES the real classifier, the real ledger and the real
sampler against a real payload. None of them asserts on the text of anything.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    CANCEL_CAUSE_PREFIX as SAMPLER_PREFIX,
    CAPTURED_PREFIXES,
    build_observation,
    select_gauges,
)
from app.tasks.calibration_main_build import (
    CANCEL_CAUSE_INCOMPLETE,
    CANCEL_CAUSE_INTERRUPTED,
    CANCEL_CAUSE_PREFIX,
    StagedFuturesIncomplete,
    cancel_cause,
    describe_failure,
)
from app.utils.calibration_phase_ledger import CANCELLED, PHASE_FUTURES


# ---------------------------------------------------------------------------
# the real runner, on the real ledger
# ---------------------------------------------------------------------------

def _runner():
    """A ``PhaseRunner`` with an open futures phase, built the production way."""
    from app.tasks.calibration_main_build import PhaseRunner, new_main_checkpoint
    from app.utils.calibration_phase_ledger import INVALIDATE, PhaseLedger, derive_plan

    plan = derive_plan(history={}, floors={}, unit_costs={})
    checkpoint = new_main_checkpoint(
        version="q999", fingerprint="f" * 32, owner="test", generation=1,
    )
    runner = PhaseRunner(
        plan=plan,
        checkpoint=checkpoint,
        checkpoint_action=INVALIDATE,
        population_version="q999",
        owner="test",
        generation=1,
        fingerprint="f" * 32,
    )
    assert isinstance(runner.ledger, PhaseLedger)
    runner.begin(PHASE_FUTURES)
    return runner


@pytest.mark.parametrize(
    "exc, expected",
    [
        (asyncio.CancelledError(), CANCEL_CAUSE_INTERRUPTED),
        (StagedFuturesIncomplete("units banked, nothing published"), CANCEL_CAUSE_INCOMPLETE),
    ],
)
def test_abort_records_the_cause_beside_the_terminal(exc, expected):
    """Both arms. A test that only checked the killed one could not see a swap."""
    runner = _runner()
    assert runner.abort(exc) == CANCELLED, "both must still classify as cancelled"
    key = f"{CANCEL_CAUSE_PREFIX}{expected}"
    assert runner.ledger.stages.get(key) == 1, runner.ledger.stages
    other = {
        CANCEL_CAUSE_INTERRUPTED: CANCEL_CAUSE_INCOMPLETE,
        CANCEL_CAUSE_INCOMPLETE: CANCEL_CAUSE_INTERRUPTED,
    }[expected]
    assert f"{CANCEL_CAUSE_PREFIX}{other}" not in runner.ledger.stages


def test_a_beat_that_did_not_cancel_records_no_cause_at_all():
    """The control. A timeout or a genuine error must not acquire a cancel cause.

    Without this the gauge could be written unconditionally and every test above
    would still pass, while the ring gained a field that says "cancelled" on
    beats that were not.
    """
    runner = _runner()
    assert runner.abort(ValueError("a real bug")) != CANCELLED
    assert cancel_cause(ValueError("a real bug")) is None
    assert not [k for k in runner.ledger.stages if k.startswith(CANCEL_CAUSE_PREFIX)]


def test_a_bare_cancellation_used_to_vanish_from_the_ledger():
    """DEFECT ARM: the pre-993 ``detail=str(exc)[:200]`` stored nothing.

    Asserted against the LEDGER's own storage rule (``detail or None``), not
    against a remembered string, so the arm still means something if the ledger
    changes how it stores a detail.
    """
    bare = asyncio.CancelledError()
    assert str(bare) == "", "the premise: a bare cancellation has no message"

    runner = _runner()
    runner.ledger.fail(PHASE_FUTURES, now_ms=1, status=CANCELLED, detail=str(bare)[:200])
    old = [p for p in runner.ledger.as_payload()["phases"] if p["name"] == PHASE_FUTURES][0]
    assert "detail" not in old, "the defect: the killed beat left no detail"

    runner = _runner()
    runner.abort(bare)
    new = [p for p in runner.ledger.as_payload()["phases"] if p["name"] == PHASE_FUTURES][0]
    assert new["detail"] == "CancelledError"


def test_describe_failure_prefers_the_message_when_there_is_one():
    """The class name is a FALLBACK. A message-carrying exception keeps its message."""
    assert describe_failure(StagedFuturesIncomplete("units banked")) == "units banked"
    assert describe_failure(asyncio.CancelledError()) == "CancelledError"
    assert len(describe_failure(RuntimeError("x" * 500))) == 200


# ---------------------------------------------------------------------------
# the sampler — the cause has to reach the ring, or the freeze score cannot read it
# ---------------------------------------------------------------------------

def test_the_sampler_carries_the_cause_onto_the_observation():
    """End to end, through the real ``build_observation``.

    ``select_gauges`` is a fixed tuple plus a prefix scan; the cause key is
    dynamic, so a fixed tuple can never hold it. This asserts on the OBSERVATION
    rather than on the tuple, because the tuple is not what the ring stores.
    """
    stages = {
        f"{CANCEL_CAUSE_PREFIX}{CANCEL_CAUSE_INTERRUPTED}": 1,
        "staged:units_banked": 33,
    }
    captured, _missing = select_gauges(stages)
    assert captured[f"{CANCEL_CAUSE_PREFIX}{CANCEL_CAUSE_INTERRUPTED}"] == 1

    observation = build_observation(
        generation=1788420758781,
        generated_at="2026-09-03T07:32:38.781799+00:00",
        complete=True,
        payload={"terminal": CANCELLED, "stages": stages, "outcome": {"gate": "not_evaluated"}},
    )
    assert (
        observation["gauges"][f"{CANCEL_CAUSE_PREFIX}{CANCEL_CAUSE_INTERRUPTED}"] == 1
    ), observation["gauges"]


def test_the_sampler_did_not_lose_the_prefix_it_already_carried():
    """Control for the widening: adding a second prefix must not drop the first.

    AMENDED by CAL-P1002, and the amendment is the point of the test rather than
    a concession to it. The original line was
    ``len(CAPTURED_PREFIXES) == 2 and len(set(CAPTURED_PREFIXES)) == 2`` — a
    COUNT pinned to a tuple whose own comment invites growth ("One tuple so a
    third prefix is one line here and nowhere else"). So it went red on exactly
    the change it exists to permit, while a prefix silently *swapped* for another
    would have kept the count at 2 and passed.

    The claim it was making is kept and made strictly harder: the earlier prefix
    is still present BY NAME (not by arithmetic), the tuple still holds no
    duplicates, and it has still only ever grown.
    """
    stages = {"staged:convergence_reason:read_raised": 1}
    captured, _ = select_gauges(stages)
    assert captured == stages

    from app.tasks.calibration_beat_gauge_sampler import CONVERGENCE_REASON_PREFIX

    assert CONVERGENCE_REASON_PREFIX in CAPTURED_PREFIXES
    assert SAMPLER_PREFIX in CAPTURED_PREFIXES
    assert len(set(CAPTURED_PREFIXES)) == len(CAPTURED_PREFIXES)
    assert len(CAPTURED_PREFIXES) >= 2


def test_the_sampler_reads_the_producers_own_prefix_constant():
    """No transcription. CAL-P083's two blind spots were both copied strings."""
    assert SAMPLER_PREFIX == CANCEL_CAUSE_PREFIX


# ---------------------------------------------------------------------------
# the freeze score — the consumer, loaded from disk because it is a script
# ---------------------------------------------------------------------------

def _freeze_score_module():
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "scripts"
        / "calibration_freeze_score.py"
    )
    spec = importlib.util.spec_from_file_location("_cal_freeze_score_993", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_freeze_score_speaks_the_same_prefix_as_the_producer():
    """The script imports nothing from ``app`` on purpose; the equality lives here.

    Without this the two could drift and the score would report every miss as
    ``unattributed`` forever, which looks exactly like "the producer never
    cancels" to a reader who does not know the join is broken.
    """
    module = _freeze_score_module()
    assert module.CANCEL_CAUSE_PREFIX == CANCEL_CAUSE_PREFIX
    assert set(module.CANCEL_CAUSES) == {CANCEL_CAUSE_INCOMPLETE, CANCEL_CAUSE_INTERRUPTED}
    for cause in module.CANCEL_CAUSES:
        assert f"'{module.CANCEL_CAUSE_PREFIX}{cause}'" in module.SQL


def test_the_score_attributes_misses_without_changing_the_score():
    """The whole point: 009 excuses no beat. Only the READING gains a column."""
    module = _freeze_score_module()
    rows = []
    for i in range(24):
        row = {"generation": i, "generated_at": f"2026-09-03T{i:02d}:15:00+00:00"}
        if i < 5:
            row.update(terminal="complete", gate="pass", published="true")
        elif i < 15:
            row.update(
                terminal="cancelled", gate="not_evaluated", published="false",
                cause_interrupted="1",
            )
        elif i < 22:
            row.update(
                terminal="cancelled", gate="not_evaluated", published="false",
                cause_incomplete="1",
            )
        else:
            # Pre-993 beats, and a `failed` one. Neither has a cause gauge.
            row.update(terminal="failed", gate="not_evaluated", published="false")
        rows.append(row)

    result = module.score(rows)
    assert result["clean"] == 5 and result["misses"] == 19
    assert result["miss_causes"] == {
        "incomplete": 7,
        "interrupted": 10,
        "unattributed": 2,
    }
    rendered = module.render(result)
    assert "10 interrupted" in rendered
    # 10 of 19 is a majority, so the deploy-cadence note must fire.
    assert "deploy-cadence finding" in rendered


def test_a_clean_beat_is_never_given_a_cause():
    module = _freeze_score_module()
    rows = [
        {
            "generation": i,
            "generated_at": f"2026-09-03T{i:02d}:15:00+00:00",
            "terminal": "complete",
            "gate": "pass",
            "published": "true",
            # A stray gauge on a clean beat must not become a rendered cause.
            "cause_interrupted": "1",
        }
        for i in range(24)
    ]
    result = module.score(rows)
    assert result["clean"] == 24
    assert result["miss_causes"] == {"incomplete": 0, "interrupted": 0, "unattributed": 0}
    assert all(b["miss_cause"] is None for b in result["beats"])


def test_two_causes_on_one_beat_is_unattributed_not_a_coin_flip():
    module = _freeze_score_module()
    row = {
        "generation": 1,
        "generated_at": "2026-09-03T01:15:00+00:00",
        "terminal": "cancelled",
        "gate": "not_evaluated",
        "published": "false",
        "cause_interrupted": "1",
        "cause_incomplete": "1",
    }
    assert module.miss_cause(row) == module.CANCEL_CAUSE_UNATTRIBUTED
