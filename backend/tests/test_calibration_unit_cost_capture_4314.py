"""CAL-P1066 (#4314) — the ring keeps the cost number, not just the clock.

WHAT WAS WRONG. CAL-P1048 split cost from progress at the write site and said in
its own comment which number is which: ``staged:unit_ms_mean`` times every unit
the beat ran "INCLUDING the one cancelled at the deadline, so it is the right
number for attributing elapsed time and *the wrong one for costing a unit*",
while ``staged:unit_ms_mean_completed`` costs the units that finished. The
sampler's ``OPERATIONAL_GAUGES`` gained the timed mean and never gained the
other. Nor ``staged:units_completion_not_banked``, nor any
``staged:unit_cost_reason:<reason>``.

WHY THAT COST SOMETHING REAL. Measured over the live 168-beat ring
(2026-09-02T14:22Z -> 2026-09-09T11:37Z): ``staged:unit_ms_mean`` on 146 beats,
``staged:unit_ms_mean_completed`` on **0**, every ``staged:unit_cost_reason:*``
on **0**. Over the same window the rebuild RAN 695 units and BANKED 549 — 146
discarded, of which 90 are named by ``staged:units_cancelled`` and **56 have no
recorded cause at all**. Whether any of those 56 were cursor-write failures —
the "durable-state path is failing" diagnosis that CAL-P1048's comment calls the
opposite of a designed cancellation — could not be determined, because the gauge
that separates the two was discarded at capture time. This lane read that
absence as a measured zero before finding the gap.

A cancelled unit is the most expensive unit of its beat by construction: it is
the one that did not fit. Excluding it from the only cost figure a reader can
reach makes every cost claim taken off this ring a survivor of that exclusion.

WHAT THESE GUARD. The prefix and the two fixed names stay captured; the stamp
moved and the drop-and-stop floor did not; and the constant this module imports
still matches the one the producer emits.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    CAPTURED_PREFIXES,
    DROP_AND_STOP_CAPTURE_VERSION,
    GAUGE_CAPTURE_VERSION,
    OPERATIONAL_GAUGES,
    REQUIRED_DISCLOSURE_GAUGES,
    UNIT_COST_CAPTURE_VERSION,
    UNIT_COST_REASON_PREFIX,
    select_gauges,
)

#: The cost gauges the producer writes as fixed names.
COST_PAIR = ("staged:unit_ms_mean_completed", "staged:units_completion_not_banked")

#: Every reason ``calibration_main_build`` emits today. Read off the producer in
#: :func:`test_every_reason_the_producer_emits_is_reachable_by_the_prefix` rather
#: than trusted from here — this literal is the readable version, that test is
#: the one that fails when a fifth reason is added.
KNOWN_REASONS = (
    "no_unit_completed",
    "withdrawn_self_blocked",
    "units_done_unverified",
)


def _producer_source() -> str:
    """The producer's own source, read the way this suite already reads a
    writer's source (``test_calibration_cursor_decision_capture_1002``)."""
    from app.tasks import calibration_main_build

    return Path(inspect.getsourcefile(calibration_main_build)).read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# the capture
# ---------------------------------------------------------------------------

def test_the_unit_cost_reason_prefix_is_in_the_capture_tuple():
    """The one line CAL-P1066 is. If this fails, everything below is theatre."""
    assert UNIT_COST_REASON_PREFIX in CAPTURED_PREFIXES


@pytest.mark.parametrize("reason", KNOWN_REASONS)
def test_every_known_cost_reason_survives_the_sampler(reason):
    key = f"{UNIT_COST_REASON_PREFIX}{reason}"
    captured, _missing = select_gauges({key: 1})
    assert captured == {key: 1}


@pytest.mark.parametrize("gauge", COST_PAIR)
def test_the_cost_pair_survives_the_sampler(gauge):
    captured, _missing = select_gauges({gauge: 7})
    assert captured == {gauge: 7}


def test_the_cost_number_and_the_clock_are_both_kept_and_are_not_the_same_key():
    """The defect was not "no cost gauge" — it was the WRONG one, alone.

    A fix that swapped the timed mean out for the completed mean would satisfy a
    naive "the completed mean is captured" assertion while destroying the pair
    the write site says feasibility reads together.
    """
    stages = {"staged:unit_ms_mean": 900_000, "staged:unit_ms_mean_completed": 107_000}
    captured, _ = select_gauges(stages)
    assert captured == stages


def test_the_cost_half_was_dropped_before_this_change():
    """The regression this exists to stop coming back, stated as the OLD
    behaviour rather than asserted about the new one.

    Rebuild the pre-CAL-P1066 selection — the fixed names minus the pair this
    change added, and the three original prefixes — and show it keeps the timed
    mean and loses the completed mean, the cursor-write-failure count and the
    reason. An edit that drops the prefix or the pair back out makes the live
    selector agree with this reconstruction, and the tests above go red.
    """
    from app.tasks.calibration_beat_gauge_sampler import (
        CANCEL_CAUSE_PREFIX,
        CONVERGENCE_REASON_PREFIX,
        CURSOR_PREFIX,
    )

    stages = {
        "staged:unit_ms_mean": 900_000,
        "staged:unit_ms_mean_completed": 107_000,
        "staged:units_completion_not_banked": 2,
        f"{UNIT_COST_REASON_PREFIX}no_unit_completed": 1,
    }
    old_names = [
        n
        for n in REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES
        if n not in COST_PAIR
    ]
    old = {n: stages[n] for n in old_names if n in stages}
    old.update(
        {
            k: v
            for k, v in stages.items()
            if k.startswith(
                (CONVERGENCE_REASON_PREFIX, CANCEL_CAUSE_PREFIX, CURSOR_PREFIX)
            )
        }
    )

    assert old == {"staged:unit_ms_mean": 900_000}, (
        "the pre-change selector should keep only the number the write site "
        "calls the wrong one for costing a unit"
    )
    new, _ = select_gauges(stages)
    assert set(new) == set(stages), "the change must keep all four"


def test_the_other_three_prefixes_still_work():
    """CAL-P083's, CAL-P993's and CAL-P1002's captures are not collateral."""
    captured, _ = select_gauges(
        {
            "staged:convergence_reason:unreadable": 0,
            "beat:cancel_cause:interrupted": 0,
            "staged:cursor_reason:fingerprint_moved": 0,
        }
    )
    assert len(captured) == 3


def test_the_restamp_gauge_is_not_swept_in_by_the_new_prefix():
    """``staged:unit_cost_units_done_restamped`` shares ``staged:unit_cost`` but
    is not a reason, and this ship did not claim it. A prefix shortened to
    ``staged:unit_cost`` would capture it silently and widen the change past
    what #4314 says it does."""
    captured, _ = select_gauges({"staged:unit_cost_units_done_restamped": 128})
    assert captured == {}


# ---------------------------------------------------------------------------
# the version floor
# ---------------------------------------------------------------------------

def test_the_stamp_moved_for_this_capture_rule():
    """A capture rule changes what absence MEANS, and the ring outlives it."""
    assert GAUGE_CAPTURE_VERSION == UNIT_COST_CAPTURE_VERSION


def test_the_drop_and_stop_floor_did_not_move():
    """The whole reason the two constants are separate (the comment on
    ``DROP_AND_STOP_CAPTURE_VERSION`` says so). Re-dating it would make a week of
    rows stop licensing a reading they legitimately license."""
    assert DROP_AND_STOP_CAPTURE_VERSION == 2
    assert DROP_AND_STOP_CAPTURE_VERSION < UNIT_COST_CAPTURE_VERSION


# ---------------------------------------------------------------------------
# drift: the constant is the producer's, not a retyped copy
# ---------------------------------------------------------------------------

def test_the_prefix_is_the_producers_own_constant():
    from app.tasks.calibration_main_build import UNIT_COST_REASON_PREFIX as emitted

    assert UNIT_COST_REASON_PREFIX == emitted


def test_the_import_fallback_matches_the_producer_too():
    """The ``except`` arm exists so a sampler never dies on an import, which
    means it can be taken in production — so it has to be right, not just
    present."""
    from app.tasks.calibration_beat_gauge_sampler import (
        _UNIT_COST_REASON_PREFIX_FALLBACK,
    )
    from app.tasks.calibration_main_build import UNIT_COST_REASON_PREFIX as emitted

    assert _UNIT_COST_REASON_PREFIX_FALLBACK == emitted


def test_every_reason_the_producer_emits_is_reachable_by_the_prefix():
    """A fifth reason added to the producer must not need a sampler edit.

    Pins the ARGUMENT of the record_gauge call, not a neighbouring token: an
    f-string built from the constant, or a bare literal if someone reintroduces
    one. Either way the resulting KEY has to start with the captured prefix.
    """
    source = _producer_source()
    emitted = set(
        re.findall(
            r'record_gauge\(\s*f?"(?:\{UNIT_COST_REASON_PREFIX\}|staged:unit_cost_reason:)'
            r'([a-z_]+)"',
            source,
        )
    )
    assert emitted, "found no unit_cost_reason emit site — the regex has rotted"
    assert set(KNOWN_REASONS) <= emitted, (
        f"a known reason stopped being emitted: {set(KNOWN_REASONS) - emitted}"
    )
    for reason in emitted:
        key = f"{UNIT_COST_REASON_PREFIX}{reason}"
        captured, _ = select_gauges({key: 1})
        assert captured == {key: 1}, f"{key} is emitted but not captured"


def test_no_emit_site_hardcodes_the_prefix():
    """CAL-P993's rule, enforced. A retyped literal is free to drift from the
    constant the sampler imports; the constant's own definition is the one
    permitted occurrence."""
    source = _producer_source()
    hardcoded = re.findall(r'"staged:unit_cost_reason:[a-z_]*"', source)
    assert hardcoded == [
        '"staged:unit_cost_reason:"'
    ], f"unexpected hard-coded unit_cost_reason literals: {hardcoded}"
