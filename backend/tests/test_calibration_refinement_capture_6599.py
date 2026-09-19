"""CAL-P1306 (#6599) — the ring says a unit cancelled, and what was done about it.

WHAT WAS WRONG. CAL-P1301/1303 are the policy that is supposed to END the
livelock #6599 names: a slot that cancels is remembered durably
(``staged:unit_cancels:<ref>``), is attempted LAST next beat so the head moves,
and is CUT FINER — on its second cancellation, or on its first when
``cancellation_is_conclusive`` holds. Every key that reports any of that
(``staged:unit_cancels:*``, ``staged:unit_cancel_conclusive:*``,
``staged:unit_split:*``, ``staged:units_split``, and the
``staged:unit_cancel_not_persisted`` that fires when the durable memory the
whole policy rests on is LOST) matched no prefix in ``CAPTURED_PREFIXES`` and
appeared in no fixed-name tuple. The sampler wrote them and dropped them.

WHY THAT COST SOMETHING REAL. Measured on the live ring 2026-09-19: twenty-four
consecutive beats (2026-09-18T12:37Z → 2026-09-19T12:37Z) are indistinguishable
— 128 planned, 2 attempted, 2 cancelled, 0 completed, ``units_banked`` frozen at
1, each stopping on ``window_stop:units_cancelling``, all under one unchanged
``input_fingerprint`` — while ``/api/calibration`` served a snapshot 98 hours
old. On rows of that shape "the refinement never fired" and "the refinement
fires every beat and does not help" are the SAME ROW, and they call for
opposite repairs. That is the instrument gap, and it is why no lever could be
chosen off this ring.

WHAT THESE GUARD. The two prefixes and the one fixed name stay in the capture
tuples, and the literals keep matching the frozen writer. They do NOT assert
that the policy works — only that the ring can finally show whether it does.
"""

import inspect
import re
from pathlib import Path

from app.tasks.calibration_beat_gauge_sampler import (
    CAPTURED_PREFIXES,
    DROP_AND_STOP_CAPTURE_VERSION,
    GAUGE_CAPTURE_VERSION,
    OPERATIONAL_GAUGES,
    REFINEMENT_CAPTURE_VERSION,
    UNIT_CANCEL_PREFIX,
    UNIT_COST_CAPTURE_VERSION,
    UNIT_SPLIT_PREFIX,
    capture_version,
    select_gauges,
)


def _writer_source() -> str:
    from app.tasks import precompute_calibration

    return Path(inspect.getsourcefile(precompute_calibration)).read_text()


def test_the_refinement_prefixes_still_match_the_frozen_writer():
    """CAL-P993's rule is "read the constant off the module that emits it". The
    emitter is ``precompute_calibration.py``, which ruling 009 freezes, so there
    is no constant to import and adding one would spend a bank wipe on a string
    — the same trade :data:`CURSOR_PREFIX` makes. This reads the writer's SOURCE
    and fails if either literal moves.

    When the freeze lifts: promote both to imports and delete this test.
    """
    src = _writer_source()
    emitted = set(
        re.findall(r'record_(?:gauge|stage)\(\s*f?"(staged:unit_(?:cancel|split)[^"{]*)', src)
    )
    assert emitted, "the writer no longer records any staged:unit_cancel*/unit_split* key"
    uncovered = sorted(
        name
        for name in emitted
        if not name.startswith((UNIT_CANCEL_PREFIX, UNIT_SPLIT_PREFIX))
    )
    assert not uncovered, (
        f"writer emits {uncovered}, which "
        f"{(UNIT_CANCEL_PREFIX, UNIT_SPLIT_PREFIX)!r} does not cover"
    )


def test_both_refinement_prefixes_are_in_the_capture_tuple():
    """A prefix constant that is never scanned is a comment."""
    assert UNIT_CANCEL_PREFIX in CAPTURED_PREFIXES
    assert UNIT_SPLIT_PREFIX in CAPTURED_PREFIXES


def test_units_split_is_carried_as_a_fixed_name():
    """``staged:units_split`` (plural) is the only key recorded exclusively
    inside the ``SPLIT_APPLIED`` arm, and no prefix reaches it."""
    assert "staged:units_split" in OPERATIONAL_GAUGES
    assert not "staged:units_split".startswith(UNIT_SPLIT_PREFIX), (
        "if the plural ever fell under the prefix this fixed name would be "
        "redundant — it does not, which is why it is listed separately"
    )


def test_the_writer_still_records_the_durable_cancel_count():
    """The count is the half that makes the policy legible: the tail-move and
    the cut-finer threshold are both keyed on it. Capturing the prefix is not
    sufficient if the writer stops emitting it."""
    assert 'record_gauge(f"staged:unit_cancels:{ref}"' in _writer_source()


def _livelocked_beat() -> dict:
    """The shape the live ring banked twenty-four times on 2026-09-19, plus the
    refinement keys that were written on those beats and thrown away."""
    return {
        "staged:units_planned": 128,
        "staged:units_this_beat": 2,
        "staged:units_cancelled": 2,
        "staged:units_completed_this_beat": 0,
        "staged:unit_cost_reason:no_unit_completed": 1,
        "staged:window_stop:units_cancelling": 0,
        # The dropped half.
        "staged:unit_cancelled_after_ms": 661497,
        "staged:unit_cancelled:futures/0007": 661497,
        "staged:unit_cancels:futures/0007": 1,
        "staged:unit_cancel_conclusive:futures/0007": 661497,
        "staged:unit_split:applied:futures/0007": 1,
        "staged:unit_cancel_not_persisted": 1,
        "staged:units_split": 1,
    }


def test_the_livelocked_beat_now_banks_every_refinement_key():
    captured, _missing = select_gauges(_livelocked_beat())
    for key in (
        "staged:unit_cancelled_after_ms",
        "staged:unit_cancelled:futures/0007",
        "staged:unit_cancels:futures/0007",
        "staged:unit_cancel_conclusive:futures/0007",
        "staged:unit_split:applied:futures/0007",
        "staged:unit_cancel_not_persisted",
        "staged:units_split",
    ):
        assert key in captured, f"{key} is still dropped by select_gauges"


def test_a_beat_that_cancelled_without_refining_is_now_distinguishable():
    """The whole point. Two beats with identical cancel counts, one of which
    refined and one of which did not, must not produce the same banked row —
    that ambiguity is what made the live ring unreadable."""
    refined = _livelocked_beat()
    declined = {
        k: v
        for k, v in _livelocked_beat().items()
        if not k.startswith(("staged:unit_split:", "staged:unit_cancel_conclusive:"))
        and k != "staged:units_split"
    }
    assert select_gauges(refined)[0] != select_gauges(declined)[0]
    assert not any(
        k.startswith("staged:unit_split:") for k in select_gauges(declined)[0]
    )


def test_the_filter_is_real_so_the_capture_above_is_not_vacuous():
    """Strawman guard: ``select_gauges`` must still DROP an unrelated staged
    key, or the assertions above would pass against a sampler that captured
    everything and would say nothing about these prefixes."""
    captured, _ = select_gauges(
        {**_livelocked_beat(), "staged:something_nobody_captures": 1}
    )
    assert "staged:something_nobody_captures" not in captured


def test_the_cancel_prefix_cannot_swallow_the_cost_reason_family():
    """``staged:unit_cancel`` is deliberately unsuffixed. Check it did not grow
    a reach over a neighbouring family that is captured for other reasons."""
    assert not "staged:unit_cost_reason:no_unit_completed".startswith(UNIT_CANCEL_PREFIX)
    assert not "staged:unit_ms_mean".startswith(UNIT_CANCEL_PREFIX)


# ---------------------------------------------------------------------------
# the version floor — the half ``ec030df12`` shipped without
# ---------------------------------------------------------------------------

def test_the_stamp_moved_for_this_capture_rule():
    """The capture rule above changed what ABSENCE means, so the stamp must move.

    Without this, every row banked before the deploy carries a gauge map the
    refinement keys were discarded from at capture time and is stamped ``3`` —
    the same value as the rows banked after it. A reader asking #6599's own
    question ("did the refinement fire?") reads absence on both and cannot tell
    "the sampler could not see it" from "the policy declined", which are the two
    readings this whole ship exists to separate.
    """
    assert GAUGE_CAPTURE_VERSION == REFINEMENT_CAPTURE_VERSION


def test_the_older_floors_did_not_move():
    """Re-dating an earlier floor would make a week of rows stop licensing a
    reading they legitimately license — the reason the floors are separate
    constants and not one number (``DROP_AND_STOP_CAPTURE_VERSION``'s comment
    says exactly this)."""
    assert DROP_AND_STOP_CAPTURE_VERSION == 2
    assert UNIT_COST_CAPTURE_VERSION == 3
    assert UNIT_COST_CAPTURE_VERSION < REFINEMENT_CAPTURE_VERSION


def test_a_row_banked_before_this_deploy_is_below_the_floor():
    """The floor has to actually separate the two populations, or it is a
    decoration. A row stamped with the PREVIOUS stamp must fall below it, and a
    row stamped with the current one must not."""
    assert capture_version({"gauge_capture_version": 3}) < REFINEMENT_CAPTURE_VERSION
    assert capture_version(
        {"gauge_capture_version": GAUGE_CAPTURE_VERSION}
    ) >= REFINEMENT_CAPTURE_VERSION


#: Every capture rule ``select_gauges`` applies, pinned. NOT a restatement of the
#: module for its own sake — see the test below for why this exact shape.
EXPECTED_CAPTURE_PREFIXES = 6
EXPECTED_OPERATIONAL_GAUGES = 13


def test_adding_a_capture_rule_fails_this_until_the_stamp_moves():
    """🔴 THE GUARD THAT WAS MISSING, AND THE REASON #6599 NEEDED A SECOND SHIP.

    #4314 had a test called ``test_the_stamp_moved_for_this_capture_rule`` that
    asserted ``GAUGE_CAPTURE_VERSION == UNIT_COST_CAPTURE_VERSION``. That fires
    when a later ship bumps the stamp — the CORRECT action — and is silent when a
    ship adds a capture rule and forgets to, which is the defect. CAL-P1306 walked
    straight through it: two prefixes and a fixed gauge added, stamp untouched,
    suite green.

    An equality against a floor cannot express the duty, because the duty is about
    a rule that does not exist yet. A pinned CENSUS can: adding a prefix or a fixed
    operational gauge moves one of these counts, this test fails, and its message
    names the two things the author now owes. Crude on purpose — a count is the
    only property of "the set of capture rules" that a future rule cannot satisfy
    by accident.
    """
    assert len(CAPTURED_PREFIXES) == EXPECTED_CAPTURE_PREFIXES, (
        "A capture prefix was added or removed. A capture rule changes what "
        "ABSENCE means on every row banked before it, so you now owe BOTH: bump "
        "GAUGE_CAPTURE_VERSION, and add a <NAME>_CAPTURE_VERSION floor equal to "
        "the new stamp so absence below it reads UNKNOWN. Then update this count."
    )
    assert len(OPERATIONAL_GAUGES) == EXPECTED_OPERATIONAL_GAUGES, (
        "A fixed operational gauge was added or removed — same duty as above: "
        "bump the stamp, add the floor, then update this count."
    )
