"""CAL-P1047 (#3803) — the beat ring stops reporting six banked when five were.

**The defect, measured on production before a line was written.** At 05:46Z on
2026-09-07, ``GET /api/admin/calibration-beat-gauges`` served this for the 04:15Z
beat::

    {"generated_at": "2026-09-07T04:37:32.799288+00:00",
     "rebuild_units_banked": 18,
     "rebuild_units_this_beat": 6,
     "terminal": "cancelled",
     "stop_reasons": ["window_stop:unit_too_large"]}

Read plainly that is *six pieces banked this hour*. **Five were** — the prior row
reads ``rebuild_units_banked: 13``, so the running total advanced 13 → 18, and the
beat's own ledger carried ``staged:units_completed_this_beat: 5`` beside
``staged:units_this_beat: 6``.

**Why.** ``REBUILD_PROGRESS_GAUGES`` mapped ``rebuild_units_this_beat`` to
``staged:units_this_beat``, the count of units that RAN
(``calibration_main_build.py``: ``ran = runner.ledger.stage_counts.get(...)``),
and a unit cancelled at its statement bound is one of them. CAL-P067 deliberately
kept that gauge mixed for compatibility — *"the operator-facing gauges above keep
the values CAL-P066 published, so nothing that reads them moves"* — which was the
right call for the GAUGE and left the RING, the thing an operator actually reads,
carrying only the mixed one.

**Why it is not a rounding of the truth.** The two beats measured that night both
ended the same way: one unit was handed the remainder of the window as its bound,
ran to it, and was cancelled having banked nothing.

===========================  ================  ================
\\                            04:15Z beat       05:15Z beat
===========================  ================  ================
units RAN                     6                 6
units BANKED                  5                 5
the cancelled unit            15m50.3s          16m19.2s
its share of the beat         **70.3%**         **72.5%**
completed-unit mean           1m12.4s           1m05.9s
===========================  ================  ================

So the field reported the beat's single most expensive **failure** as its largest
**success**, and did it in the instrument an operator reads to decide whether the
rebuild is moving at all. On the 12 rows then in the ring the published figure
disagreed with the ``rebuild_units_banked`` delta twice.

**The repair keeps three facts on three names**, rather than picking a winner
between two: ``rebuild_units_this_beat`` (banked — the progress reading, and the
one the name is read as), ``rebuild_units_ran_this_beat`` (the old mixed number,
nothing lost), and ``rebuild_units_ran_not_banked_this_beat`` (the difference,
stated on the row instead of left to a reader to subtract).

**The gap is DERIVED from those two, and that is the second finding here.** The
obvious repair publishes ``staged:units_cancelled``, and it is wrong: that gauge
is a ``record_stage`` counter written only in the cancel arm, so a beat that
cancelled nothing never writes the key — while ``rebuild_progress_measured`` is
``not absent``, one flag over every field. Mapping it would have nulled the whole
progress block on every CLEAN beat, which is CAL-P1039's own defect ("eight of
the nine required gauges present; the ninth nulled all eight") rebuilt one layer
up by the repair for its sibling. Both operands of the subtraction are written
unconditionally, so the derived gap is measured on every beat, and on a clean one
it is a real ``0``.

The suite is weighted towards four properties:

1. the production beat above publishes **5**, not 6, and the running-total delta
   agrees with it;
2. the ran count survives under its own name — a repair that deleted it would
   have destroyed the only evidence that the cancellation happened;
3. an absent completed-count is attributed to the **beat**, never to the capture
   (gotcha #53) — the new gauge is outside ``REQUIRED_DISCLOSURE_GAUGES``, so the
   pre-existing ``looked_for`` test would have got this backwards;
4. the ring and ``build_disclosure`` now answer different questions under the
   same field name, on purpose, and the beat where they diverge is pinned here.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    ALWAYS_CAPTURED_PROGRESS_GAUGES,
    GAP_FIELD,
    PROGRESS_ABSENT_BEAT,
    PROGRESS_ABSENT_CAPTURE,
    REBUILD_PROGRESS_FIELDS,
    row_rebuild_progress,
)

#: The 2026-09-07 04:15Z beat (generation stamped 04:37:32.799288Z), from
#: ``calibration:main:phase_ledger`` as read live at 04:40Z and cross-read off the
#: ring at 05:46Z. Six units ran, five banked, one cancelled at 15m50.3s against a
#: 15m49.7s bound. This map is the fixture spine: it is the beat the defect was
#: found on, not a constructed one.
BEAT_0415Z_GAUGES: dict = {
    "staged:units_banked": 18,
    "staged:units_this_beat": 6,
    "staged:units_completed_this_beat": 5,
    "staged:units_cancelled": 1,
    "staged:unit_cancelled_after_ms": 950_329,
    "staged:unit_bound_ms:futures": 949_749,
    "staged:unit_ms_mean_completed": 72_400,
    "staged:units_drifted": 8,
    "staged:units_drift_checkable": 13,
    "staged:units_drift_uncheckable": 5,
    "staged:units_dropped": 0,
    "staged:window_stop:unit_too_large": 1,
}

#: The 05:15Z beat that followed it. Same shape to within a second on elapsed and
#: exactly on the unit counts, with a DIFFERENT cancelled-unit digest — which is
#: why the over-count is a standing property of the rebuild's operating mode and
#: not a one-off worth a note in a report.
BEAT_0515Z_GAUGES: dict = {
    "staged:units_banked": 23,
    "staged:units_this_beat": 6,
    "staged:units_completed_this_beat": 5,
    "staged:units_cancelled": 1,
    "staged:unit_cancelled_after_ms": 979_202,
    "staged:unit_bound_ms:futures": 978_902,
    "staged:unit_ms_mean_completed": 65_891,
    "staged:units_drifted": 13,
    "staged:units_drift_checkable": 18,
    "staged:units_drift_uncheckable": 5,
    "staged:units_dropped": 0,
    "staged:window_stop:unit_too_large": 1,
}


def _row(gauges: dict, **over) -> dict:
    """One banked ring observation around ``gauges``.

    ``gauges_missing_required`` empty and ``gauge_capture_version`` 2 unless a
    test says otherwise: the rows this defect was served on were both.
    """
    row = {
        "generation": 1_788_755_852_799,
        "generated_at": "2026-09-07T04:37:32.799288+00:00",
        "terminal": "cancelled",
        "gauge_capture_version": 2,
        "gauges_missing_required": [],
        "gauges": gauges,
    }
    row.update(over)
    return row


class TestTheNumberAnOperatorReads:
    """Property 1 — the beat publishes what it BANKED."""

    @pytest.mark.parametrize(
        "gauges,banked_now,banked_before",
        [(BEAT_0415Z_GAUGES, 18, 13), (BEAT_0515Z_GAUGES, 23, 18)],
    )
    def test_the_beat_publishes_five_not_six(self, gauges, banked_now, banked_before):
        """The defect, stated as the arithmetic that exposed it.

        ``rebuild_units_this_beat`` must equal the advance in the running total.
        Both beats banked five of six; the ring served six for the first.
        """
        progress = row_rebuild_progress(_row(gauges))

        assert progress["rebuild_units_this_beat"] == 5
        assert progress["rebuild_units_this_beat_measured"] is True
        assert progress["rebuild_units_banked"] == banked_now
        assert progress["rebuild_units_this_beat"] == banked_now - banked_before

    def test_the_ran_count_is_not_destroyed_it_is_named(self):
        """Property 2. The cancellation is the beat's most important fact.

        A repair that simply repointed the field and stopped would have left the
        ring unable to say that anything was attempted and abandoned — 16 minutes
        of the hour would have become invisible rather than mis-labelled, which
        is the worse of the two.
        """
        progress = row_rebuild_progress(_row(BEAT_0415Z_GAUGES))

        assert progress["rebuild_units_ran_this_beat"] == 6
        assert progress["rebuild_units_ran_this_beat_measured"] is True
        assert progress[GAP_FIELD] == 1
        assert progress[f"{GAP_FIELD}_measured"] is True

    def test_the_three_numbers_reconcile_on_the_row(self):
        """ran = banked + gap, on the row, without a reader subtracting.

        Asserted on both beats because the property is what makes the trio worth
        publishing: a reader who sees the three disagree has found a new defect
        rather than a rounding.
        """
        for gauges in (BEAT_0415Z_GAUGES, BEAT_0515Z_GAUGES):
            p = row_rebuild_progress(_row(gauges))
            assert (
                p["rebuild_units_ran_this_beat"]
                == p["rebuild_units_this_beat"] + p[GAP_FIELD]
            ), gauges["staged:units_banked"]

    def test_a_clean_beat_is_unaffected(self):
        """The common case must not move.

        A beat that cancelled nothing published the same number before and after
        this change, and the 168-row ring is mostly those. Stated so the repair
        cannot be read as a re-baselining of the whole instrument.
        """
        clean = dict(BEAT_0415Z_GAUGES)
        clean["staged:units_this_beat"] = 5
        clean["staged:units_completed_this_beat"] = 5
        clean["staged:units_cancelled"] = 0

        p = row_rebuild_progress(_row(clean))
        assert p["rebuild_units_this_beat"] == 5
        assert p["rebuild_units_ran_this_beat"] == 5
        assert p[GAP_FIELD] == 0
        assert p[f"{GAP_FIELD}_measured"] is True
        assert p["rebuild_progress_measured"] is True


class TestAbsenceStaysTwoFacts:
    """Property 3 — gotcha #53, on the two gauges the old test could not cover."""

    def test_a_beat_that_wrote_no_completed_count_blames_the_beat(self):
        """The mis-attribution this repair had to fix on its way in.

        ``looked_for`` reads ``gauges_missing_required``, which lists only
        REQUIRED gauges. ``staged:units_completed_this_beat`` is operational, so
        the pre-existing rule would have answered ``capture_did_not_retain`` — "we
        may never have looked" — for a row where the sampler has looked since the
        module's first commit and the BEAT wrote nothing. That is the collapse of
        the two facts, arriving through the fix for a different symptom.
        """
        gauges = {
            k: v
            for k, v in BEAT_0415Z_GAUGES.items()
            if k not in ALWAYS_CAPTURED_PROGRESS_GAUGES
        }
        progress = row_rebuild_progress(_row(gauges))

        for field in ("rebuild_units_this_beat", GAP_FIELD):
            assert progress[field] is None, field
            assert progress[f"{field}_measured"] is False, field
            assert progress["rebuild_progress_absent"][field] == PROGRESS_ABSENT_BEAT

    def test_an_unversioned_row_gets_the_same_answer(self):
        """No version floor, and the reason is that there is no old sampler.

        Both gauges have been in ``select_gauges`` since ``64c7b761`` created the
        module, so even a row banked before the version stamp existed was one the
        sampler looked at. If a future capture rule adds a gauge here that is NOT
        true of, this test is the one that has to change, and it should be hard.
        """
        gauges = {
            k: v
            for k, v in BEAT_0415Z_GAUGES.items()
            if k not in ALWAYS_CAPTURED_PROGRESS_GAUGES
        }
        row = _row(gauges)
        row.pop("gauge_capture_version")

        progress = row_rebuild_progress(row)
        assert (
            progress["rebuild_progress_absent"]["rebuild_units_this_beat"]
            == PROGRESS_ABSENT_BEAT
        )

    def test_a_required_gauge_the_capture_dropped_still_blames_the_capture(self):
        """The other arm, unchanged. The split is only worth having if both hold.

        ``staged:units_drift_uncheckable`` is required and is absent from neither
        the row's ``gauges_missing_required`` nor the always-captured set, so it
        reads as the sampler's silence — which is exactly what it is.
        """
        gauges = {
            k: v
            for k, v in BEAT_0415Z_GAUGES.items()
            if k != "staged:units_drift_uncheckable"
        }
        progress = row_rebuild_progress(_row(gauges))

        assert progress["rebuild_units_drift_uncheckable"] is None
        assert (
            progress["rebuild_progress_absent"]["rebuild_units_drift_uncheckable"]
            == PROGRESS_ABSENT_CAPTURE
        )

    def test_no_absent_field_is_ever_rendered_as_zero(self):
        """The invariant the whole module exists for, over every field at once."""
        progress = row_rebuild_progress(_row({}))

        assert progress["rebuild_progress_measured"] is False
        assert set(progress["rebuild_progress_absent"]) == set(REBUILD_PROGRESS_FIELDS)
        for field in REBUILD_PROGRESS_FIELDS:
            assert progress[field] is None, field
            assert progress[f"{field}_measured"] is False, field


class TestTheRingAndTheDisclosureNowDiffer:
    """Property 4 — same field name, two questions, and the beat that proves it."""

    def test_on_a_cancelled_beat_the_two_readers_disagree_by_the_cancelled_unit(self):
        """Pinned deliberately, as the cost of the repair rather than a surprise.

        ``build_disclosure`` is the SERVING path and still reads the ran count;
        the ring reads the banked count. On a beat with one cancelled unit they
        differ by exactly one, and a future editor who "fixes" the disagreement in
        the wrong direction breaks the ring again.

        The serving twin is #3803's named follow-up and is NOT changed here: its
        ``GAUGE_*`` constants are what ``REQUIRED_DISCLOSURE_GAUGES`` is derived
        from, so adding one there re-dates every row's required-gauge list, and
        that is a separate change with a separate blast radius.
        """
        from app.utils.calibration_staged_disclosure import build_disclosure

        serving = dict(BEAT_0415Z_GAUGES)
        serving["staged:served_at"] = 1_788_724_500
        serving["staged:served_units"] = 128

        block = build_disclosure(
            ledger_stages=serving, staged_generated_at=None, now=None
        )
        assert block["measured"] is True, "fixture must reach the serving branch"

        progress = row_rebuild_progress(_row(serving))

        assert block["rebuild_units_this_beat"] == 6
        assert progress["rebuild_units_this_beat"] == 5
        assert progress["rebuild_units_ran_this_beat"] == block["rebuild_units_this_beat"]
        assert progress["rebuild_units_banked"] == block["rebuild_units_banked"]
