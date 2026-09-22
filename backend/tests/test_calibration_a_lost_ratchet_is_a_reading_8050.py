"""CAL-P1337 (#6868, #8050) — a refinement ratchet that vanishes leaves a reading.

**The defect, measured on production before a line was written.** At 12:36:50Z on
2026-09-22 the rebuild beat invalidated its cursor on
``population_version_malformed`` and the beat ring went::

    11:29:47Z  action=resume      reason=resumable                    planned=203  banked=109
    12:36:50Z  action=invalidate  reason=population_version_malformed  planned=128  banked=0

``rebuild_units_planned`` is ``len(chunks)`` (the call site passes
``planned=len(chunks)``), and ``plan_units`` with an empty refinement map
produces exactly the ``STAGED_FUTURES_BUCKETS``-way partition. So 203 -> 128 is
not merely 109 banked units lost: it is the **~75 refinement children the build
had earned over days**, gone with them. The live cursor row agreed — ``unit_splits``
**0**, ``unit_cancels`` 6, ``committed`` 0.

That is the expensive half. A bank is re-earned in beats; a ratchet is re-earned
in DAYS, because a slot is cut only when it cancels and ``attempt_order`` spreads
cancellations one per slot across the whole partition. And post-wipe the build
banked nothing at all for five consecutive beats: at 128 slots a unit no longer
fits inside ``statement_timeout_ms``, so every unit died, and the mechanism that
would cut them finer is the mechanism the wipe had just reset.

**Nothing published the ratchet's size, in either direction.**

1. The WRITER recorded it only when it was non-empty::

       if cursor.unit_splits:
           runner.ledger.record_gauge("staged:units_refined_slots", len(...))

   so the one value that says *the ratchet is gone* — zero — was the one value
   never written. Gotcha #53: an absent key reads as "fine".
2. The SAMPLER never retained it. ``select_gauges`` keeps only the names in
   ``REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES`` (plus the prefix half),
   and this name was in neither, so even a written value died at capture.

Both halves had to be wrong for the loss to be invisible, and both were. Recovering
the figure after the fact took inferring the base partition from ``len(chunks)``
off the ring — archaeology, not a reading — and it is only recoverable at all
because the wipe happened to be large. Each beat overwrites the cursor, so the
payload that caused it is gone for good.

``carry_refinement`` exists precisely to carry the ratchet across an invalidation
and runs ABOVE the population-version check, so one of two things is true and this
file does not claim to know which: the payload's ``unit_splits`` were unreadable to
``refinement_from_raw``, or the carry is inert in production for a reason a
synthetic payload does not reproduce. **That is the point.** The next occurrence is
diagnosable only if the level is on the row, so the level goes on the row.

**What is deliberately NOT here.** The name is not added to
``REBUILD_PROGRESS_GAUGES``. That publishes a ring COLUMN, and a name first
captured today would answer ``capture_did_not_retain`` on every row already
banked — the trap CAL-P1334 documented for ``staged:units_planned_total`` (0 of
168 rows). That rung needs its own capture floor and a week of rows first;
``test_the_ring_column_is_deferred_on_purpose`` pins the deferral so a later
editor adds the floor rather than the field.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    GAUGE_CAPTURE_VERSION,
    OPERATIONAL_GAUGES,
    RATCHET_LEVEL_CAPTURE_VERSION,
    REBUILD_PROGRESS_GAUGES,
    capture_version,
    select_gauges,
)

# The real harness that drives the real ``_run_staged_futures``: a fake db and
# durable row, but the build's own planning, cursor and ledger code.
#
# BORROWED, NOT COPIED, and this file is the first in the suite to borrow from a
# sibling test module — so the coupling is stated rather than discovered. The
# alternative is a second set of ~100 lines of ``_Db``/``_Runner`` fakes, which
# this module's own C14 rule refuses for the reason it always does: two copies
# drift, and a drifted fake proves something about the fake. If the sibling is
# renamed, this import is the thing that says so, loudly, at collection.
from tests.test_calibration_incremental_equals_fresh_6599 import (
    BUCKETS,
    WHOLE_WINDOW_MS,
    _Db,
    _Durable,
    _population,
    _Runner,
    _State,
)

#: The level this file is about.
RATCHET_GAUGE = "staged:units_refined_slots"

#: Its event-shaped sibling. The two are not redundant and the suite says why:
#: a wipe earns no split, so ``units_split`` is silent on exactly the event that
#: matters most.
SPLIT_EVENT_GAUGE = "staged:units_split"

#: The 2026-09-22 11:29:47Z beat's shape, and the 12:36:50Z beat's. Only the two
#: numbers this file reasons about; the full rows are in the docstring.
PLANNED_BEFORE, BANKED_BEFORE = 203, 109
PLANNED_AFTER, BANKED_AFTER = 128, 0

#: The base partition the production plan is measured against — the ``after`` plan
#: IS the bare partition, which is the incident. Named rather than inlined because
#: ``203 - 128 = 75`` is the whole arithmetic of it.
BUCKETS_BASE = PLANNED_AFTER


async def _one_beat(monkeypatch):
    """One real beat over a fresh durable row. Returns its ledger's stage map.

    Modelled on the sibling suite's ``_fresh`` control, with one difference that
    is the whole reason it is copied rather than imported: that helper discards
    the runner and returns the census, and the runner is what holds the ledger.
    """
    from app.services import durable_snapshots as ds
    from app.tasks import calibration_main_build as cmb
    from app.tasks import precompute_calibration as pc
    import types

    durable = _Durable()
    monkeypatch.setattr(ds, "read_snapshot_standalone", durable.read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", durable.publish)
    monkeypatch.setattr(cmb, "STAGED_FUTURES_BUCKETS", BUCKETS)
    monkeypatch.setattr(cmb, "staged_lease", lambda: 0.0)
    monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
    monkeypatch.setattr(pc, "staged_unit_fingerprint", lambda: "ratchet-fp")

    state = _State(_population())
    runner = _Runner(
        generation=1, window_ms=WHOLE_WINDOW_MS, population_version="q268"
    )
    db = _Db(runner, state)
    monkeypatch.setattr(
        pc,
        "time",
        types.SimpleNamespace(monotonic=lambda r=runner: r.elapsed_ms() / 1000.0),
    )
    rows = await pc._run_staged_futures(db, runner, lambda frozen=False: "SELECT 1")
    assert rows is not None, "the control must publish in one beat"
    payload = runner.ledger.as_payload()
    stages = payload.get("stages")
    assert isinstance(stages, dict), "the ledger must expose a stage map to capture"
    return stages


# =============================================================================
# 1. THE WRITER — the zero is the reading, so the zero gets written
# =============================================================================


class TestTheLevelIsRecordedEvenWhenThereIsNothingToReport:
    @pytest.mark.asyncio
    async def test_a_beat_with_no_refinements_still_records_the_level(
        self, monkeypatch
    ):
        """The mutation this file exists to kill.

        Restore ``if cursor.unit_splits:`` around the write and this fails on the
        key's ABSENCE — which is exactly how production failed: a build whose
        partition had just been reset to the base 128 was indistinguishable, on
        the row, from a build nobody had ever asked.
        """
        stages = await _one_beat(monkeypatch)
        assert RATCHET_GAUGE in stages, (
            "a beat that carries no refinements must still say so: absence is "
            "the reading a reset produces, and an absent key reads as 'fine'"
        )
        assert stages[RATCHET_GAUGE] == 0

    @pytest.mark.asyncio
    async def test_zero_is_a_value_and_not_a_falsy_hole(self, monkeypatch):
        """``0`` has to survive every hop, not just be written.

        A level that is written and then dropped by a truthiness test downstream
        is the same defect one layer along, and it is the likelier regression:
        ``if value:`` reads as a null-guard and silently means ``if value != 0``.
        """
        stages = await _one_beat(monkeypatch)
        captured, _missing = select_gauges(stages)
        assert RATCHET_GAUGE in captured
        assert captured[RATCHET_GAUGE] == 0
        assert captured[RATCHET_GAUGE] is not None


# =============================================================================
# 2. THE SAMPLER — a written level that capture throws away is still invisible
# =============================================================================


class TestTheCaptureActuallyRetainsIt:
    def test_the_name_is_licensed_for_capture(self):
        """Asserted through the real selector, never by reading the tuple alone.

        The failure mode a membership assertion cannot see is a name in the tuple
        that ``select_gauges`` still does not keep — which is what the tuple's own
        🪤 records for ``staged:units_planned_total``: real gauge, never captured,
        0 of 168 rows.
        """
        assert RATCHET_GAUGE in OPERATIONAL_GAUGES
        captured, _missing = select_gauges({RATCHET_GAUGE: 75})
        assert captured[RATCHET_GAUGE] == 75

    def test_the_wipe_is_readable_from_two_captured_rows(self):
        """The production event, replayed as the two rows a reader would meet.

        Before: a ratchet of 75 against a 203-unit plan. After: 0 against 128.
        The point is that the SECOND row carries the number at all — under the old
        writer it carried nothing, and a reader comparing the rows saw only the
        bank fall and had no way to learn the partition had been reset under it.
        """
        before, _ = select_gauges(
            {RATCHET_GAUGE: PLANNED_BEFORE - BUCKETS_BASE, "staged:units_planned": PLANNED_BEFORE}
        )
        after, _ = select_gauges(
            {RATCHET_GAUGE: 0, "staged:units_planned": PLANNED_AFTER}
        )
        assert before[RATCHET_GAUGE] == 75
        assert after[RATCHET_GAUGE] == 0
        # The reading the old row could not produce: the ratchet collapsed, and
        # the plan collapsed WITH it rather than the bank merely falling.
        assert before[RATCHET_GAUGE] - after[RATCHET_GAUGE] == 75
        assert before["staged:units_planned"] - after["staged:units_planned"] == 75

    def test_it_is_not_the_same_fact_as_a_split_event(self):
        """Why both names are licensed, and why one could not cover the other.

        ``staged:units_split`` is recorded inside the ``SPLIT_APPLIED`` arm, so it
        counts refinements EARNED on this beat. A wipe earns none — it is silent
        on the beat that destroys seventy-five of them. Only a LEVEL can fall.
        """
        assert SPLIT_EVENT_GAUGE in OPERATIONAL_GAUGES
        wipe_beat, _ = select_gauges({RATCHET_GAUGE: 0, "staged:units_planned": 128})
        assert SPLIT_EVENT_GAUGE not in wipe_beat
        assert wipe_beat[RATCHET_GAUGE] == 0


# =============================================================================
# 3. THE RUNG THAT IS DELIBERATELY NOT TAKEN
# =============================================================================


class TestTheFloorSeparatesTheTwoPopulations:
    """A capture rule changes what ABSENCE means on every row banked before it.

    The ring holds 168 rows, so for a week after this ships every row below the
    floor carries a gauge map this key was discarded from AT CAPTURE TIME. On such
    a row "no ``staged:units_refined_slots``" is UNKNOWN — not "the build holds no
    refinements", which is the same bytes and the opposite diagnosis.
    """

    def test_a_row_banked_before_this_deploy_is_below_the_floor(self):
        assert capture_version({"gauge_capture_version": 4}) < (
            RATCHET_LEVEL_CAPTURE_VERSION
        )
        assert capture_version(
            {"gauge_capture_version": GAUGE_CAPTURE_VERSION}
        ) >= RATCHET_LEVEL_CAPTURE_VERSION

    def test_the_stamp_actually_moved_for_this_rule(self):
        """A floor that is not also a stamp bump marks nothing: both rows say 4.

        This is the duty ``test_adding_a_capture_rule_fails_this_until_the_stamp
        _moves`` names, asserted from the side of the rule that incurred it.
        """
        assert GAUGE_CAPTURE_VERSION >= RATCHET_LEVEL_CAPTURE_VERSION
        assert capture_version({}) < RATCHET_LEVEL_CAPTURE_VERSION


class TestTheRingColumnIsDeferredOnPurpose:
    def test_the_ring_column_is_deferred_on_purpose(self):
        """Pinned so the deferral is a decision a later editor has to re-make.

        Mapping the name here publishes a ring FIELD, and every row already banked
        was captured by a sampler that did not keep this key — so the field would
        answer ``capture_did_not_retain`` on all of them. CAL-P1334 paid this
        exact price for ``staged:units_planned_total`` and documented it. When the
        rows exist, the mapping arrives WITH a capture floor; until then this
        assertion is the reason it has not.
        """
        assert RATCHET_GAUGE not in REBUILD_PROGRESS_GAUGES.values(), (
            "publishing this as a ring column needs its own capture floor beside "
            "DROP_AND_STOP_CAPTURE_VERSION — see the module note on "
            "staged:units_planned_total"
        )
