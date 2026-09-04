"""CAL-P1002 (#2007) — a discarded rebuild says why.

WHAT WAS WRONG. ``_run_staged_futures`` records what it did with the checkpoint
as ``staged:cursor_<action>`` (``fresh`` / ``resume`` / ``invalidate``) plus
``staged:cursor_reason:<reason>`` beside it. The beat-gauge sampler captured
exactly ONE of those keys — ``staged:cursor_resume``, a fixed name in
``OPERATIONAL_GAUGES``. So the ring recorded the healthy case by name and the
destructive case not at all.

WHY THAT COST SOMETHING REAL. Measured over the live 168-beat ring on
2026-09-04: three beats reset the bank to 5 from 36, 119 and 76, two of them
also dropping a complete 128-unit served set. All three are among the ten rows
that carry no cursor key. Two are attributable only because
``input_fingerprint`` is banked separately and moved across the beat (ruling
075's deploy cause); the third — 2026-09-03 12:35 PT — has an unchanged
fingerprint, and there is nothing on its row that names what invalidated it.
The writer's own CAL-P024 comment says why the action alone would not have been
enough either: *"Five distinct causes produce INVALIDATE."*

WHAT THESE GUARD. The prefix stays in the capture tuple; the reader never
invents a decision that was not recorded; and the literal this module must use
instead of an import — because the emitter is inside ruling 009's freeze — still
matches the string the frozen writer emits.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    CAPTURED_PREFIXES,
    CURSOR_ACTIONS,
    CURSOR_PREFIX,
    cursor_decision,
    select_gauges,
)


# ---------------------------------------------------------------------------
# the capture
# ---------------------------------------------------------------------------

def test_the_cursor_prefix_is_in_the_capture_tuple():
    """The one line CAL-P1002 is. If this fails, everything below is theatre."""
    assert CURSOR_PREFIX in CAPTURED_PREFIXES


@pytest.mark.parametrize("action", CURSOR_ACTIONS)
def test_every_cursor_action_survives_the_sampler(action):
    """Not just ``resume``. ``resume`` was already captured by fixed name, so a
    test that only exercised it would have passed BEFORE this change and is the
    vacuous version of this one."""
    captured, _missing = select_gauges({f"staged:cursor_{action}": 0})
    assert captured == {f"staged:cursor_{action}": 0}


def test_the_reason_survives_the_sampler_and_it_is_the_whole_point():
    captured, _missing = select_gauges(
        {"staged:cursor_invalidate": 0, "staged:cursor_reason:fingerprint_moved": 0}
    )
    assert captured["staged:cursor_reason:fingerprint_moved"] == 0
    assert captured["staged:cursor_invalidate"] == 0


def test_the_destructive_case_was_dropped_before_this_change():
    """The regression this exists to stop coming back, stated as the old
    behaviour rather than asserted about the new one.

    Rebuild the pre-CAL-P1002 selection — fixed names only, the two original
    prefixes — and show it keeps ``resume`` and loses ``invalidate`` and the
    reason. A future edit that drops ``CURSOR_PREFIX`` back out of the tuple
    makes the live selector agree with this reconstruction, and
    :func:`test_every_cursor_action_survives_the_sampler` goes red.
    """
    from app.tasks.calibration_beat_gauge_sampler import (
        CANCEL_CAUSE_PREFIX,
        CONVERGENCE_REASON_PREFIX,
        OPERATIONAL_GAUGES,
        REQUIRED_DISCLOSURE_GAUGES,
    )

    stages = {
        "staged:cursor_invalidate": 0,
        "staged:cursor_reason:fingerprint_moved": 0,
        "staged:cursor_resume": 0,
    }
    old = {n: stages[n] for n in REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES
           if n in stages}
    old.update({k: v for k, v in stages.items()
                if k.startswith((CONVERGENCE_REASON_PREFIX, CANCEL_CAUSE_PREFIX))})

    assert old == {"staged:cursor_resume": 0}, (
        "the pre-change selector should keep only the healthy case"
    )
    new, _ = select_gauges(stages)
    assert set(new) == set(stages), "the change must keep all three"


def test_the_other_two_prefixes_still_work():
    """CAL-P083's and CAL-P993's captures are not collateral damage."""
    captured, _ = select_gauges(
        {
            "staged:convergence_reason:unreadable": 0,
            "beat:cancel_cause:interrupted": 0,
        }
    )
    assert set(captured) == {
        "staged:convergence_reason:unreadable",
        "beat:cancel_cause:interrupted",
    }


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

def test_a_row_with_no_cursor_key_reads_as_absence_not_as_a_decision():
    """The CAL-P028 collapse, arriving one layer further out.

    A beat that REFUSED returns before the ledger write, so its row carries no
    cursor key. Reporting that as ``resume``, or as ``""``, would make "we did
    not record a decision" indistinguishable from "we decided to resume" — which
    is the exact confusion the ring exists to end.
    """
    assert cursor_decision({}) == {"action": None, "reason": None}
    assert cursor_decision({"staged:units_banked": 5}) == {"action": None, "reason": None}
    assert cursor_decision(None) == {"action": None, "reason": None}
    assert cursor_decision("not a dict") == {"action": None, "reason": None}


def test_a_historical_row_reads_as_resume_and_no_reason():
    """Rows banked before CAL-P1002 carry at most ``staged:cursor_resume``. They
    must keep reading correctly, with ``reason`` honestly absent rather than
    back-filled."""
    assert cursor_decision({"staged:cursor_resume": 0}) == {
        "action": "resume",
        "reason": None,
    }


def test_refuse_is_not_a_reportable_action():
    """``refuse`` is a real cursor outcome and is deliberately NOT in
    ``CURSOR_ACTIONS``: that arm returns before the ledger write, so no row can
    legitimately carry ``staged:cursor_refuse``. If the writer ever starts
    emitting one, this fails and the omission gets re-decided on purpose."""
    assert "refuse" not in CURSOR_ACTIONS
    assert cursor_decision({"staged:cursor_refuse": 0})["action"] is None


def test_an_empty_reason_suffix_is_absence_not_an_empty_string():
    assert cursor_decision({"staged:cursor_reason:": 0})["reason"] is None


def test_action_and_reason_are_read_independently():
    got = cursor_decision(
        {"staged:cursor_invalidate": 0, "staged:cursor_reason:population_version_changed": 0}
    )
    assert got == {"action": "invalidate", "reason": "population_version_changed"}


# ---------------------------------------------------------------------------
# the drift guard that stands in for the import CAL-P993's rule would prefer
# ---------------------------------------------------------------------------

def test_the_cursor_prefix_still_matches_the_frozen_writer():
    """CAL-P993's rule is "read the constant off the module that emits it". The
    emitter here is ``precompute_calibration.py``, which ruling 009 freezes, so
    there is no constant to import and adding one would spend a bank wipe on a
    string. This reads the writer's SOURCE instead and fails if the literal
    moves — the same protection, paid for differently.

    When the freeze lifts: promote ``CURSOR_PREFIX`` to an import and delete
    this test.
    """
    from app.tasks import precompute_calibration

    src = Path(inspect.getsourcefile(precompute_calibration)).read_text()
    emitted = set(re.findall(r'record_stage\(\s*f?"(staged:cursor_[^"{]*)', src))
    assert emitted, "the writer no longer records any staged:cursor_* stage"
    assert all(name.startswith(CURSOR_PREFIX) for name in emitted), (
        f"writer emits {sorted(emitted)}, which {CURSOR_PREFIX!r} does not cover"
    )


def test_the_writer_still_records_a_reason_beside_the_action():
    """The reason key is the half that makes the action diagnostic (CAL-P024:
    "Five distinct causes produce INVALIDATE"). If the writer stops emitting it,
    capturing the prefix is no longer sufficient and this says so."""
    from app.tasks import precompute_calibration

    src = Path(inspect.getsourcefile(precompute_calibration)).read_text()
    assert 'record_stage(f"staged:cursor_reason:{reason}"' in src
