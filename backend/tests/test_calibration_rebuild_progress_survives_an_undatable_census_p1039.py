"""CAL-P1039 (#3536) — the beat ring stops losing the rebuild's progress.

**The defect, measured on production before a line was written.** On 2026-09-06
at 21:10Z, ``GET /api/admin/calibration-beat-gauges?limit=200`` returned 168
banked observations of which **124 answered ``measured: false``** — every row
since **2026-09-05T07:19:23Z**, thirty-six hours — and all 124 for exactly one
reason::

    "gauges_missing_required": ["staged:served_at"]

On those rows ``units_banked``, ``units_drifted``, ``units_drift_unknown``,
``rebuild_units_banked`` and ``rebuild_units_this_beat`` were all ``null``.
The raw gauge map of the very same rows — ``?full=true``, 20:15Z beat — carried::

    staged:units_banked          = 5
    staged:units_this_beat       = 1
    staged:units_drifted         = 2
    staged:units_drift_checkable = 4
    staged:units_drift_uncheckable = 1

Eight of the nine required gauges present. The ninth, belonging to a phase those
beats never reach, nulled all eight.

**Why it happened, and the general shape.** The ring published progress out of
``build_disclosure``, which is a SERVING-bank instrument: it answers
``unmeasured("served_at_absent")`` — a two-key dict and nothing else — for a bank
that is serving but has never been stamped. That is correct behaviour *there*;
refusing to date a census it cannot date is the whole job, and it is on the
serving path for ``/api/calibration``. It is wrong *here*, because this ring is
not publishing a curve, it is recording what a beat did. **A helper written to
REFUSE is the wrong reader for a question that is not asking it to certify
anything** — the same trap as reusing a permissive matcher for a display rule,
arriving from the opposite direction.

**What it cost.** ``calibration:main:phase_ledger`` holds one row and every beat
overwrites it; the ring exists precisely so the descent is not observable only by
"something that happened to be watching at the time" (its own docstring). While
it recorded nulls, that is exactly what the descent depended on: all five entries
in ``MEASURED_COMPLETIONS`` were caught live by a session sitting on the clock,
and no hour that nobody watched can be recovered.

The suite is weighted towards two properties:

1. the production row above — an undatable census — must yield the rebuild's five
   figures, measured;
2. an absent figure must stay **two facts**, never one (gotcha #53): a gauge the
   sampler looked for and the beat did not write, versus a gauge this row's
   capture may never have retained. Neither is ever ``0``.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    PROGRESS_ABSENT_BEAT,
    PROGRESS_ABSENT_CAPTURE,
    REBUILD_PROGRESS_GAUGES,
    REQUIRED_DISCLOSURE_GAUGES,
    row_rebuild_progress,
)
from app.utils.calibration_staged_disclosure import build_disclosure

#: The 2026-09-06 20:15Z beat, verbatim from ``?full=true``. Unit 5 of 128 banked
#: at 901,551 ms; the beat then stopped on ``window_stop:unit_too_large`` with
#: 250,737 ms left. This map is the fixture spine: if the shape it describes stops
#: reproducing, this suite is describing a production that no longer exists.
PRODUCTION_2015Z_GAUGES: dict = {
    "staged:served_units": 0,
    "staged:served_drifted": 0,
    "staged:served_drift_uncheckable": 0,
    # staged:served_at — ABSENT. The whole defect.
    "staged:units_banked": 5,
    "staged:units_this_beat": 1,
    "staged:units_completed_this_beat": 1,
    "staged:units_done": 5,
    "staged:units_planned": 128,
    "staged:units_drifted": 2,
    "staged:units_drift_checkable": 4,
    "staged:units_drift_uncheckable": 1,
    "staged:unit_ms_mean": 901_551,
    "staged:unit_ms_worst": 902_392,
    "staged:window_left_ms": 250_737,
    "staged:window_stop:unit_too_large": 0,
    "staged:cursor_resume": 0,
    "staged:cursor_reason:resumable": 0,
}

PRODUCTION_2015Z_ROW: dict = {
    "generation": 1_788_726_830_627,
    "generated_at": "2026-09-06T20:33:50.627417+00:00",
    "terminal": "cancelled",
    "gauges": PRODUCTION_2015Z_GAUGES,
    "gauges_missing_required": ["staged:served_at"],
    "gauge_capture_version": 2,
    # What the ring actually banked for this beat, and the reason it published
    # five nulls. Kept on the fixture rather than described in prose so the test
    # below can assert against the real refusal instead of a re-enactment.
    "disclosure": {"reason": "served_at_absent", "measured": False},
    "measured": False,
}


class TestTheProductionRowThatWasLost:
    """The regression itself, on the row that exhibited it."""

    def test_the_disclosure_really_does_refuse_this_row(self):
        """The premise, asserted rather than assumed.

        If ``build_disclosure`` ever starts answering this ledger, the repair
        below is no longer load-bearing and someone should find out from a test
        rather than from a stale comment.
        """
        block = build_disclosure(
            ledger_stages=PRODUCTION_2015Z_GAUGES,
            staged_generated_at=None,
            now=None,
        )
        assert block["measured"] is False
        assert block["reason"] == "served_at_absent"
        # And it carries NOTHING else — this is why five fields went null.
        assert set(block) == {"measured", "reason"}

    def test_the_rebuilds_progress_survives_the_refusal(self):
        """Five figures, measured, off a row the disclosure could not read."""
        progress = row_rebuild_progress(PRODUCTION_2015Z_ROW)

        assert progress["rebuild_units_banked"] == 5
        assert progress["rebuild_units_this_beat"] == 1
        assert progress["rebuild_units_drifted"] == 2
        assert progress["rebuild_units_drift_checkable"] == 4
        assert progress["rebuild_units_drift_uncheckable"] == 1

        assert progress["rebuild_progress_measured"] is True
        assert progress["rebuild_progress_absent"] == {}
        for field in REBUILD_PROGRESS_GAUGES:
            assert progress[f"{field}_measured"] is True, field

    def test_it_reads_the_gauges_and_never_the_disclosure(self):
        """A fallback to ``disclosure`` would re-open the hole. Prove it is absent.

        The row here carries a MEASURED disclosure whose figures disagree with its
        gauges. Any reader that consults the disclosure first — or at all — picks
        up 99; the gauge map is the beat's own record and is the only source.
        """
        row = dict(PRODUCTION_2015Z_ROW)
        row["measured"] = True
        row["disclosure"] = {
            "measured": True,
            "units_banked": 99,
            "rebuild_units_banked": 99,
            "rebuild_units_this_beat": 99,
            "units_drifted": 99,
        }

        progress = row_rebuild_progress(row)
        assert progress["rebuild_units_banked"] == 5
        assert progress["rebuild_units_this_beat"] == 1
        assert progress["rebuild_units_drifted"] == 2


class TestAbsenceStaysTwoFacts:
    """Gotcha #53, and :func:`bank_drop`'s shape applied to a second field set."""

    def test_a_gauge_the_beat_did_not_write_is_named_as_the_beats_silence(self):
        gauges = dict(PRODUCTION_2015Z_GAUGES)
        del gauges["staged:units_drifted"]
        row = dict(
            PRODUCTION_2015Z_ROW,
            gauges=gauges,
            gauges_missing_required=["staged:served_at", "staged:units_drifted"],
        )

        progress = row_rebuild_progress(row)
        assert progress["rebuild_units_drifted"] is None
        assert progress["rebuild_units_drifted_measured"] is False
        assert progress["rebuild_progress_absent"] == {
            "rebuild_units_drifted": PROGRESS_ABSENT_BEAT
        }
        assert progress["rebuild_progress_measured"] is False
        # The neighbours are untouched: one silent gauge must not null the row.
        assert progress["rebuild_units_banked"] == 5

    def test_a_gauge_the_capture_may_never_have_kept_is_named_differently(self):
        """Absent from the map AND absent from ``gauges_missing_required``.

        The sampler records what it looked for and did not find. A gauge in
        neither place was never looked for by this row's capture, which is a fact
        about the SAMPLER, and reporting it as the beat's silence would be
        CERT-2051's confident wrong zero wearing a new field name.
        """
        gauges = dict(PRODUCTION_2015Z_GAUGES)
        del gauges["staged:units_drift_checkable"]
        row = dict(PRODUCTION_2015Z_ROW, gauges=gauges)

        progress = row_rebuild_progress(row)
        assert progress["rebuild_units_drift_checkable"] is None
        assert progress["rebuild_units_drift_checkable_measured"] is False
        assert progress["rebuild_progress_absent"] == {
            "rebuild_units_drift_checkable": PROGRESS_ABSENT_CAPTURE
        }

    @pytest.mark.parametrize(
        "junk", [None, True, False, "5", 5.0, [], {}], ids=repr
    )
    def test_a_non_integer_gauge_is_unknown_and_never_coerced(self, junk):
        """``True`` is the one that matters: ``isinstance(True, int)`` is ``True``.

        A bool waved through here publishes ``rebuild_units_banked: true``, and
        the endpoint's reader would render it as 1 banked unit.
        """
        gauges = dict(PRODUCTION_2015Z_GAUGES, **{"staged:units_banked": junk})
        progress = row_rebuild_progress(dict(PRODUCTION_2015Z_ROW, gauges=gauges))

        assert progress["rebuild_units_banked"] is None
        assert progress["rebuild_units_banked_measured"] is False

    @pytest.mark.parametrize("row", [None, [], "row", 7, {}], ids=repr)
    def test_a_row_that_is_not_a_row_answers_unknown_on_every_field(self, row):
        progress = row_rebuild_progress(row)
        assert progress["rebuild_progress_measured"] is False
        for field in REBUILD_PROGRESS_GAUGES:
            assert progress[field] is None, field
            assert progress[f"{field}_measured"] is False, field
        # Unknown for the CAPTURE reason: a row with no ``gauges_missing_required``
        # never told us it looked.
        assert set(progress["rebuild_progress_absent"].values()) == {
            PROGRESS_ABSENT_CAPTURE
        }


class TestTheBuilderIsNeverConfusedWithTheServedCensus:
    """The naming rule, enforced — this is the conflation that caused the bug."""

    def test_every_published_field_carries_the_rebuild_prefix(self):
        """No bare ``units_*`` may leave this reader.

        In ``build_disclosure`` the name ``units_banked`` means the SERVED census
        when one exists and the builder's count when it does not. That double
        meaning is correct there and unusable here, so nothing this function
        returns may borrow the ambiguous name.
        """
        progress = row_rebuild_progress(PRODUCTION_2015Z_ROW)
        summary = {"rebuild_progress_measured", "rebuild_progress_absent"}
        for key in progress:
            if key in summary:
                continue
            assert key.startswith("rebuild_units_"), key

    def test_it_never_reads_a_served_gauge(self):
        """Blanking every ``served_*`` gauge must not move a single figure.

        The served census and the bank being built are different populations, and
        a reader that quietly fell back to ``staged:served_units`` would report
        the rebuild's progress as 0 on exactly the rows this repair is for.
        """
        gauges = {
            k: v for k, v in PRODUCTION_2015Z_GAUGES.items()
            if not k.startswith("staged:served_")
        }
        before = row_rebuild_progress(PRODUCTION_2015Z_ROW)
        after = row_rebuild_progress(dict(PRODUCTION_2015Z_ROW, gauges=gauges))
        assert before == after

    def test_the_two_names_the_disclosure_already_used_keep_their_meaning(self):
        """``rebuild_units_banked`` / ``rebuild_units_this_beat`` are not redefined.

        The endpoint used to serve both out of ``build_disclosure``'s serving
        branch. This proves the substitution is meaning-preserving where the old
        reader answered at all: same gauges, same numbers. A repair that fixed the
        null by changing what the field MEANS would be a different bug.
        """
        serving = dict(PRODUCTION_2015Z_GAUGES)
        serving["staged:served_at"] = 1_788_724_500
        serving["staged:served_units"] = 128

        block = build_disclosure(
            ledger_stages=serving, staged_generated_at=None, now=None
        )
        assert block["measured"] is True, "fixture must reach the serving branch"

        progress = row_rebuild_progress(
            dict(PRODUCTION_2015Z_ROW, gauges=serving, gauges_missing_required=[])
        )
        assert progress["rebuild_units_banked"] == block["rebuild_units_banked"]
        assert progress["rebuild_units_this_beat"] == block["rebuild_units_this_beat"]


async def _serve(monkeypatch, rows):
    """The real endpoint over a ring of ``rows``, with only the read stubbed.

    Borrowed wholesale from ``test_calibration_bank_drop_capture_3454``: the
    finding there was never that the pure readers are wrong, it was that the
    ENDPOINT applied one to rows it does not describe, and that is exactly the
    finding here too. A suite that only exercised the pure function would have
    passed all the way through this bug.
    """
    from datetime import datetime, timezone

    from app.routes import admin_cohort
    from app.tasks.calibration_beat_gauge_sampler import (
        HISTORY_IDENTITY,
        HISTORY_SCHEMA,
    )
    from app.utils.durable_state import DurableEnvelope, EnvelopeRead

    envelope = DurableEnvelope.build(
        identity=HISTORY_IDENTITY,
        schema_version=HISTORY_SCHEMA,
        payload={
            "schema": HISTORY_SCHEMA,
            "limit": 168,
            "observations": rows,
            "summary": {"observations": len(rows)},
        },
        complete=True,
        source="calibration_beat_gauge_sampler",
        generated_at=datetime(2026, 9, 6, 21, 0, tzinfo=timezone.utc),
    )

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        return EnvelopeRead(status="fresh", tier="durable", envelope=envelope)

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)
    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    return await admin_cohort.calibration_beat_gauges(request=None, limit=24)


class TestTheEndpointStopsAnsweringUnknown:
    """The surface. This is the assertion the ring existed for and was failing."""

    @pytest.mark.asyncio
    async def test_the_2015Z_row_now_reports_its_five_banked_units(self, monkeypatch):
        out = await _serve(monkeypatch, [PRODUCTION_2015Z_ROW])
        row = out["observations"][0]

        assert row["rebuild_units_banked"] == 5
        assert row["rebuild_units_this_beat"] == 1
        assert row["rebuild_units_drifted"] == 2
        assert row["rebuild_units_drift_checkable"] == 4
        assert row["rebuild_units_drift_uncheckable"] == 1
        assert row["rebuild_progress_measured"] is True

    @pytest.mark.asyncio
    async def test_the_served_census_columns_still_say_unknown(self, monkeypatch):
        """The repair is additive and must NOT paper over the real absence.

        ``units_banked`` / ``units_drifted`` / ``units_drift_unknown`` describe the
        SERVED census, whose date this beat genuinely does not know. They stay
        ``null``. A repair that filled those in from the builder's gauges would be
        the CAL-P078 substitution — the publish clock wearing the census's name —
        arriving through the fix for its own symptom.
        """
        out = await _serve(monkeypatch, [PRODUCTION_2015Z_ROW])
        row = out["observations"][0]

        assert row["measured"] is False
        assert row["units_banked"] is None
        assert row["units_drifted"] is None
        assert row["units_drift_unknown"] is None
        assert row["gauges_missing_required"] == ["staged:served_at"]

    @pytest.mark.asyncio
    async def test_an_unmeasured_progress_field_is_never_rendered_as_a_number(
        self, monkeypatch
    ):
        """The one invariant a reader of this surface leans on, on the surface."""
        gauges = {
            k: v for k, v in PRODUCTION_2015Z_GAUGES.items()
            if not k.startswith("staged:units_")
        }
        out = await _serve(
            monkeypatch, [dict(PRODUCTION_2015Z_ROW, gauges=gauges)]
        )
        row = out["observations"][0]

        for field in REBUILD_PROGRESS_GAUGES:
            assert row[f"{field}_measured"] is False, field
            assert row[field] is None, field
        assert row["rebuild_progress_measured"] is False
        assert set(row["rebuild_progress_absent"]) == set(REBUILD_PROGRESS_GAUGES)

    @pytest.mark.asyncio
    async def test_full_true_is_untouched_and_still_serves_the_raw_rows(
        self, monkeypatch
    ):
        """``full=true`` returns banked rows verbatim; the projection is the
        default view's business only. Asserted because a reader replaying the ring
        against a future disclosure needs the row as banked, not as re-read."""
        from app.routes import admin_cohort
        from app.tasks.calibration_beat_gauge_sampler import (
            HISTORY_IDENTITY,
            HISTORY_SCHEMA,
        )
        from app.utils.durable_state import DurableEnvelope, EnvelopeRead
        from datetime import datetime, timezone

        envelope = DurableEnvelope.build(
            identity=HISTORY_IDENTITY,
            schema_version=HISTORY_SCHEMA,
            payload={"schema": HISTORY_SCHEMA, "observations": [PRODUCTION_2015Z_ROW]},
            complete=True,
            source="calibration_beat_gauge_sampler",
            generated_at=datetime(2026, 9, 6, 21, 0, tzinfo=timezone.utc),
        )

        async def _fake_read(identity, *, expected_version=None, max_age_s=None):
            return EnvelopeRead(status="fresh", tier="durable", envelope=envelope)

        import app.services.durable_snapshots as ds

        monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)
        monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
        out = await admin_cohort.calibration_beat_gauges(request=None, full=True)

        assert out["observations"] == [PRODUCTION_2015Z_ROW]
        assert "rebuild_progress_measured" not in out["observations"][0]


class TestTheNoVersionGateDecisionIsLicensed:
    """Why this reader needs no capture-version floor, asserted not asserted-in-prose."""

    def test_every_gauge_it_reads_is_a_required_disclosure_gauge(self):
        """The licence itself.

        ``row_stop_and_drop`` needs a version floor because its gauges were added
        by a later capture rule, so their absence on an old row is the sampler's
        silence and unrecoverable. Every gauge here is in
        :data:`REQUIRED_DISCLOSURE_GAUGES`, so a capture that failed to keep one
        records it in the row's own ``gauges_missing_required`` at the time — the
        row carries its own disambiguating signal and no constant is needed. If
        someone adds a gauge to the map that is NOT required, this fails, and the
        version gate has to be thought about again.
        """
        for field, gauge in REBUILD_PROGRESS_GAUGES.items():
            assert gauge in REQUIRED_DISCLOSURE_GAUGES, (field, gauge)

    def test_the_two_absence_reasons_are_distinct_strings(self):
        """They are compared by value downstream; equal ones would erase the split."""
        assert PROGRESS_ABSENT_BEAT != PROGRESS_ABSENT_CAPTURE
