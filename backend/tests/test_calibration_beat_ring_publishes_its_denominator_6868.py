"""CAL-P1334 (#6868) — the beat ring publishes the denominator it was counting against.

**The defect, measured on production before a line was written.** At 10:08Z on
2026-09-22 — the eighth day the accuracy page had served the snapshot built
2026-09-15T11:16:10Z — ``GET /api/admin/calibration-beat-gauges`` answered, for
the newest beat::

    {"generated_at": "2026-09-22T09:36:49.897313+00:00",
     "rebuild_units_banked": 107,
     "rebuild_units_this_beat": 0,
     "terminal": "cancelled"}

Read plainly that is *107 units banked and climbing*. It says nothing at all
about whether the build is getting closer, because the plan is not a constant:
CAL-P1301 (#6599) cuts a slot that cancelled into children, so the number of
units the generation needs GROWS while it is being built. The same row carried
``staged:units_planned: 202`` in its raw gauge map, and the row 41 hours before
it carried ``147`` beside ``31`` banked.

===========================  ================  ================
\\                            09-20 16:37Z      09-22 09:36Z
===========================  ================  ================
units banked                  31                107
units planned                 147               202
**units REMAINING**           **116**           **95**
===========================  ================  ================

So the numerator advanced 76 and the distance closed 21. A reader of the
published block saw the 76.

**What it cost.** Every ETA posted on #6868 was hand-sourced by someone who knew
to pull ``?full=true`` — ~200 KB of raw gauge maps — and knew which of the 26
keys was the denominator; one of those ETAs had to be retracted. The figure was
on the row the whole time, retained by the sampler on all 168 rows the ring then
held. Nothing published it.

**Why ``staged:units_planned`` and not ``staged:units_planned_total``.** The
write site's own comment advertises the latter, and it is real — it is what
``_planned_unit_total`` reads, and it is written unconditionally. But
``select_gauges`` has never captured it: **0 of the ring's 168 rows** carried it
on 2026-09-22, so a field wired to that name would answer
``capture_did_not_retain`` on every row in the ring and publish nothing until a
new sampler had run for a week. Reading the ring's HISTORY is the point, so the
field is wired to the name that is already on the rows. ``test_the_denominator
_is_read_from_the_gauge_production_rows_actually_carry`` is the pin.

**Why this one may be mapped where ``staged:units_cancelled`` may not** (the 🔴
on ``REBUILD_PROGRESS_GAUGES``): that refusal is about a key whose absence is the
COMMON case — a clean beat never writes it — and ``rebuild_progress_measured``
is one flag over every field, so mapping it would null the block on the healthy
majority. ``staged:units_planned`` is written by
``_record_convergence_projection`` above its ``ran_this_beat`` return, on the
pass that always runs, so a beat that banked nothing, ran nothing or deferred its
rebuild still writes it: 168 of 168 rows, every terminal in the ring, and zero
rows carrying ``staged:units_banked`` without it.

The suite is weighted towards four properties:

1. the two production rows above publish their denominator, measured, and the
   remaining distance is computable from the published block alone;
2. the field is read from the captured gauge, never from
   ``staged:units_planned_total`` (nothing captures it) and never from
   ``staged:units_done`` (which EQUALS the banked count on both rows, so a
   mis-wire there reads as a plausible number rather than as a failure);
3. an absent denominator stays two facts (gotcha #53) and is never ``0``;
4. adding a seventh field does not null the other six: a row that lost only the
   denominator still publishes every figure it has, and names the one it lacks.
"""

from __future__ import annotations

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    ALWAYS_CAPTURED_PROGRESS_GAUGES,
    OPERATIONAL_GAUGES,
    PROGRESS_ABSENT_BEAT,
    PROGRESS_ABSENT_CAPTURE,
    REBUILD_PROGRESS_FIELDS,
    REBUILD_PROGRESS_GAUGES,
    row_rebuild_progress,
    select_gauges,
)

#: The gauge the field is wired to, and the one it is deliberately NOT wired to.
PLANNED_GAUGE = "staged:units_planned"
UNCAPTURED_TWIN = "staged:units_planned_total"
PLANNED_FIELD = "rebuild_units_planned"

#: The 2026-09-20 16:37Z beat, verbatim from ``?full=true`` read at 10:08Z on
#: 2026-09-22. 31 of 147 units banked; one unit ran 20m57s and was cancelled.
BEAT_1637Z_GAUGES: dict = {
    "beat:cancel_cause:incomplete": 1,
    "staged:beats_to_publish": 112,
    "staged:cursor_reason:resumable": 0,
    "staged:cursor_resume": 0,
    "staged:served_drift_uncheckable": 0,
    "staged:served_drifted": 0,
    "staged:served_units": 0,
    "staged:unit_cancel_conclusive:128:8": 1_257_289,
    "staged:unit_cancelled:a5a9d5babda1d23d": 1_257_289,
    "staged:unit_cancelled_after_ms": 1_257_289,
    "staged:unit_cancels:128:8": 2,
    "staged:unit_cost_reason:no_unit_completed": 1,
    "staged:unit_cost_reason:withdrawn_refuted_by_cancellation": 1,
    "staged:unit_ms_mean": 1_254_779,
    "staged:unit_split:applied:128:8": 2,
    "staged:units_banked": 31,
    "staged:units_cancelled": 1,
    "staged:units_completed_this_beat": 0,
    "staged:units_done": 31,
    "staged:units_drift_checkable": 31,
    "staged:units_drift_uncheckable": 0,
    "staged:units_drifted": 4,
    "staged:units_planned": 147,
    "staged:units_split": 1,
    "staged:units_this_beat": 1,
    "staged:window_left_ms": 53_628,
    "staged:window_stop:unit_too_large": 0,
}

#: The 2026-09-22 09:36Z beat — the newest row in the ring when this was written,
#: and the one #6868 was being graded on. 107 of 202, same shape 41 hours later.
BEAT_0936Z_GAUGES: dict = {
    "beat:cancel_cause:incomplete": 1,
    "staged:beats_to_publish": 90,
    "staged:cursor_reason:resumable": 0,
    "staged:cursor_resume": 0,
    "staged:served_drift_uncheckable": 0,
    "staged:served_drifted": 0,
    "staged:served_units": 0,
    "staged:unit_cancelled:248c4616a352cdab": 1_253_807,
    "staged:unit_cancelled_after_ms": 1_253_807,
    "staged:unit_cancels:128:30": 2,
    "staged:unit_cost_reason:no_unit_completed": 1,
    "staged:unit_cost_reason:withdrawn_refuted_by_cancellation": 1,
    "staged:unit_ms_mean": 1_253_762,
    "staged:unit_split:applied:128:30": 2,
    "staged:units_banked": 107,
    "staged:units_cancelled": 1,
    "staged:units_completed_this_beat": 0,
    "staged:units_done": 107,
    "staged:units_drift_checkable": 107,
    "staged:units_drift_uncheckable": 0,
    "staged:units_drifted": 50,
    "staged:units_planned": 202,
    "staged:units_split": 1,
    "staged:units_this_beat": 1,
    "staged:window_left_ms": 71_068,
    "staged:window_stop:unit_too_large": 0,
}


def _row(gauges: dict, **over) -> dict:
    """One banked ring observation around ``gauges``, in the production shape.

    ``gauges_missing_required: ["staged:served_at"]`` and ``measured: false``
    because that is what BOTH real rows carry: the served bank is empty, so the
    disclosure refuses to date it — which is CAL-P1039's row, still the normal
    state of this ring, and the reason the rebuild's progress is read off the
    gauges rather than out of the disclosure.
    """
    row = {
        "generation": 1_790_069_809_897,
        "generated_at": "2026-09-22T09:36:49.897313+00:00",
        "terminal": "cancelled",
        "gauge_capture_version": 4,
        "gauges_missing_required": ["staged:served_at"],
        "disclosure": {"reason": "served_bank_empty", "measured": False},
        "measured": False,
        "gauges": gauges,
    }
    row.update(over)
    return row


async def _serve(monkeypatch, rows):
    """The real endpoint over a ring of ``rows``, with only the read stubbed.

    The pure reader is not the surface. CAL-P1039's finding was that the ENDPOINT
    applied a refusing helper to rows it does not describe, and a suite that only
    exercised the pure function would have passed straight through it; the same
    is true of a field that is derived but never published.
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
        generated_at=datetime(2026, 9, 22, 10, 8, tzinfo=timezone.utc),
    )

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        return EnvelopeRead(status="fresh", tier="durable", envelope=envelope)

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)
    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    return await admin_cohort.calibration_beat_gauges(request=None, limit=24)


class TestTheNumberTheRingCouldNotShow:
    """Property 1 — the denominator reaches the surface, on the rows it was missing from."""

    @pytest.mark.asyncio
    async def test_the_0936Z_row_publishes_202_beside_its_107(self, monkeypatch):
        out = await _serve(monkeypatch, [_row(BEAT_0936Z_GAUGES)])
        row = out["observations"][0]

        assert row["rebuild_units_banked"] == 107
        assert row[PLANNED_FIELD] == 202
        assert row[f"{PLANNED_FIELD}_measured"] is True
        assert row["rebuild_progress_measured"] is True

    @pytest.mark.asyncio
    async def test_the_distance_is_computable_from_the_published_block_alone(
        self, monkeypatch
    ):
        """The whole ship, stated as the arithmetic a reader could not do.

        Both rows, in one served ring, because the finding is a RELATION between
        beats and not a level on either: banked +76 while remaining closed by 21.
        A reader with only ``rebuild_units_banked`` sees the 76 and concludes the
        build is four-fifths done; it is 53% done and the denominator is moving.
        """
        out = await _serve(
            monkeypatch,
            [
                _row(
                    BEAT_1637Z_GAUGES, generated_at="2026-09-20T16:37:07.979145+00:00"
                ),
                _row(BEAT_0936Z_GAUGES),
            ],
        )
        first, last = out["observations"]

        assert last["rebuild_units_banked"] - first["rebuild_units_banked"] == 76
        remaining = [
            r[PLANNED_FIELD] - r["rebuild_units_banked"] for r in (first, last)
        ]
        assert remaining == [116, 95]
        # The relation the numerator alone denies: the distance closed by less
        # than a third of what was banked, because the plan grew underneath it.
        assert remaining[0] - remaining[1] == 21
        assert last[PLANNED_FIELD] - first[PLANNED_FIELD] == 55


class TestItIsWiredToTheGaugeTheRowsCarry:
    """Property 2 — the two mis-wires that would look like a working field."""

    def test_the_denominator_is_read_from_the_gauge_production_rows_actually_carry(
        self,
    ):
        """``staged:units_planned_total`` is the trap, and it is silent.

        It is the name the write site advertises and the one
        ``_planned_unit_total`` reads, so it is what a reader of that code reaches
        for. ``select_gauges`` has never captured it — 0 of 168 rows on
        2026-09-22 — so the field would answer unknown on every real row while
        every unit test that hand-builds a gauge map passed. Asserted against the
        production maps: they carry one name and not the other.
        """
        assert REBUILD_PROGRESS_GAUGES[PLANNED_FIELD] == PLANNED_GAUGE
        for gauges in (BEAT_1637Z_GAUGES, BEAT_0936Z_GAUGES):
            assert PLANNED_GAUGE in gauges
            assert UNCAPTURED_TWIN not in gauges
        assert UNCAPTURED_TWIN not in OPERATIONAL_GAUGES

    def test_it_is_not_read_from_units_done_which_equals_the_banked_count(self):
        """The mis-wire that publishes a plausible number instead of a wrong one.

        ``staged:units_done`` is 31 on the first row and 107 on the second —
        exactly ``staged:units_banked`` both times, because the loop's ``done``
        counts what the cursor already holds. A field wired there would publish
        ``107 of 107``: a complete-looking build, on the beat where 95 units were
        outstanding. So the pin is not "the value is right" but "removing the
        denominator does not fall back onto a number that happens to be there".
        """
        for gauges in (BEAT_1637Z_GAUGES, BEAT_0936Z_GAUGES):
            assert gauges["staged:units_done"] == gauges["staged:units_banked"]

        without = {k: v for k, v in BEAT_0936Z_GAUGES.items() if k != PLANNED_GAUGE}
        progress = row_rebuild_progress(_row(without))
        assert progress[PLANNED_FIELD] is None
        assert progress[f"{PLANNED_FIELD}_measured"] is False

    def test_blanking_every_served_gauge_moves_nothing(self):
        """The served census and the bank being built are different populations."""
        gauges = {
            k: v
            for k, v in BEAT_0936Z_GAUGES.items()
            if not k.startswith("staged:served_")
        }
        assert row_rebuild_progress(_row(BEAT_0936Z_GAUGES)) == row_rebuild_progress(
            _row(gauges)
        )

    def test_the_sampler_really_does_capture_it(self):
        """Route 2's licence, asserted through ``select_gauges`` and not the set.

        :data:`ALWAYS_CAPTURED_PROGRESS_GAUGES` is hand-written, so the failure
        mode is a name licensed as always-captured that the capture never keeps —
        which would make every absence read ``beat_did_not_record`` when the truth
        is that nothing looked. Run the real selector over a real ledger map.
        """
        assert PLANNED_GAUGE in ALWAYS_CAPTURED_PROGRESS_GAUGES
        captured, _missing = select_gauges(dict(BEAT_0936Z_GAUGES))
        assert captured[PLANNED_GAUGE] == 202


class TestAnAbsentDenominatorStaysTwoFacts:
    """Property 3 — gotcha #53 on the new field, both directions."""

    def test_a_beat_that_wrote_no_plan_blames_the_beat(self):
        """Route 2: the sampler has looked for this name since before the oldest
        row the ring can hold, so its absence is the BEAT's silence."""
        without = {k: v for k, v in BEAT_0936Z_GAUGES.items() if k != PLANNED_GAUGE}
        progress = row_rebuild_progress(_row(without))

        assert progress[PLANNED_FIELD] is None
        assert progress[f"{PLANNED_FIELD}_measured"] is False
        assert (
            progress["rebuild_progress_absent"][PLANNED_FIELD] == PROGRESS_ABSENT_BEAT
        )

    def test_a_row_with_no_capture_at_all_blames_the_capture(self):
        """The licence is a claim about what THIS row's capture retained, so it
        may not be applied to a row that captured nothing."""
        progress = row_rebuild_progress(_row({}))

        assert progress[PLANNED_FIELD] is None
        assert (
            progress["rebuild_progress_absent"][PLANNED_FIELD]
            == PROGRESS_ABSENT_CAPTURE
        )

    @pytest.mark.parametrize("junk", ["202", 202.0, True, None, {"n": 202}])
    def test_a_non_integer_plan_is_unknown_and_never_coerced(self, junk):
        progress = row_rebuild_progress(
            _row(dict(BEAT_0936Z_GAUGES, **{PLANNED_GAUGE: junk}))
        )
        assert progress[PLANNED_FIELD] is None
        assert progress[f"{PLANNED_FIELD}_measured"] is False


class TestTheSeventhFieldDoesNotNullTheOtherSix:
    """Property 4 — the hazard the 🔴 on ``staged:units_cancelled`` names.

    Mapping a gauge whose absence is COMMON would flip ``rebuild_progress_
    measured`` — one flag over every field — on the healthy majority of rows.
    This gauge is not that, and the test states what happens when it IS missing:
    every other figure keeps its value and its own ``_measured`` flag, and the
    aggregate names exactly the one field that is unknown. Nothing is nulled.
    """

    def test_the_other_figures_survive_a_missing_denominator(self):
        without = {k: v for k, v in BEAT_0936Z_GAUGES.items() if k != PLANNED_GAUGE}
        progress = row_rebuild_progress(_row(without))

        assert progress["rebuild_units_banked"] == 107
        assert progress["rebuild_units_banked_measured"] is True
        assert progress["rebuild_units_this_beat"] == 0
        assert progress["rebuild_units_ran_this_beat"] == 1
        assert progress["rebuild_units_ran_not_banked_this_beat"] == 1
        assert progress["rebuild_progress_measured"] is False
        assert set(progress["rebuild_progress_absent"]) == {PLANNED_FIELD}

    def test_a_complete_row_measures_every_published_field(self):
        """And the complete case is the one the ring is mostly made of."""
        progress = row_rebuild_progress(_row(BEAT_0936Z_GAUGES))

        for field in REBUILD_PROGRESS_FIELDS:
            assert progress[f"{field}_measured"] is True, field
            assert isinstance(progress[field], int), field
        assert progress["rebuild_progress_measured"] is True
        assert progress["rebuild_progress_absent"] == {}

    def test_the_new_field_is_published_under_the_rebuild_prefix(self):
        """It describes the bank being BUILT, never the census being served."""
        assert PLANNED_FIELD in REBUILD_PROGRESS_FIELDS
        assert PLANNED_FIELD.startswith("rebuild_units_")
