"""CAL-P1105 (#997): the beat ring captures WHAT FENCE a unit ran under.

🔴 THE DEFECT, MEASURED BEFORE THE FIX. ``GET /api/admin/calibration-beat-gauges
?full=true`` at 2026-09-11T04:11Z returned 168 banked observations carrying 32
distinct gauge keys between them. ``staged:unit_ms_worst`` (what a unit COST) was
one of them, and so was ``staged:window_stop:unit_too_large`` (a beat giving up
because a unit did not fit its fence). ``staged:unit_bound_ms:*``,
``staged:unit_bound_headroom_ms:*``, ``staged:unit_worst_carried_ms:*`` and
``staged:unit_worst_reason:*`` occurred on **zero** rows.

So the ring could report that a beat stopped because a unit was too large for a
bound it never recorded. CAL-P163 (#1978) added that pair for exactly this — its
comment reads "a cancelled unit records only that it was cancelled, the same
ledger entry whether the fence was 100 ms too tight or 600 s too tight" — and
``select_gauges`` never grew a rule that could reach it, because the phase half
of the key is interpolated and every rule but the prefix scan matches fixed
names. Fifth occurrence of that class in this module.

What it cost: D119's throughput half measured that every beat completes exactly
5 units, 19 of 19, across a 1.46× swing in mean unit cost and ending with 29–191
seconds unspent — and could not attribute it, because whether the fence was
mis-sized is unanswerable from a ring that does not record the fence.
"""

import inspect
import re
from pathlib import Path

from app.tasks.calibration_beat_gauge_sampler import (
    CAPTURED_PREFIXES,
    GAUGE_CAPTURE_VERSION,
    UNIT_BOUND_PREFIX,
    UNIT_FENCE_ABSENT_CAPTURE,
    UNIT_FENCE_CAPTURE_VERSION,
    UNIT_FENCE_STEMS,
    UNIT_WORST_PREFIX,
    row_unit_fence,
    select_gauges,
    unit_fence,
)

#: One beat's ledger, shaped like the live rows: the fence pair the producer
#: writes per unit, beside the cost gauges the ring already kept.
LEDGER = {
    "staged:units_done": 15,
    "staged:unit_ms_worst": 220_373,
    "staged:window_stop:unit_too_large": 0,
    "staged:unit_bound_ms:futures": 949_749,
    "staged:unit_bound_headroom_ms:futures": 191_000,
    "staged:unit_worst_carried_ms:futures": 220_373,
    "staged:unit_bound_ms:events": 540_000,
    "staged:unit_bound_headroom_ms:events": 0,
    "staged:unit_worst_reason:unmeasured:events": 1,
}


def test_the_fence_keys_survive_capture():
    """The regression itself: every fence key the producer writes is retained."""
    captured, _missing = select_gauges(LEDGER)

    for key in LEDGER:
        if key.startswith(("staged:unit_bound", "staged:unit_worst")):
            assert key in captured, f"{key} was dropped at capture — the CAL-P1105 defect"


def test_the_prefixes_are_read_off_the_module_that_emits_them():
    """CAL-P993's rule. The emitter is ``calibration_main_build``, which is not
    the ruling-009 frozen module, so these are imports and not retyped literals
    guarded by a source scan."""
    from app.tasks import calibration_main_build

    assert UNIT_BOUND_PREFIX is calibration_main_build.UNIT_BOUND_PREFIX
    assert UNIT_WORST_PREFIX is calibration_main_build.UNIT_WORST_PREFIX
    assert UNIT_BOUND_PREFIX in CAPTURED_PREFIXES
    assert UNIT_WORST_PREFIX in CAPTURED_PREFIXES


def test_the_prefixes_still_cover_every_fence_key_the_producer_emits():
    """A seventh fence key added to the write site with a stem these prefixes do
    not cover would be dropped in silence, which is the defect this file records.
    Scanning the producer's source is what makes a new stem fail loudly."""
    from app.tasks import calibration_main_build

    src = Path(inspect.getsourcefile(calibration_main_build)).read_text()
    # Only the interpolated-prefix form is legal now; a bare literal is what
    # regressed last time, so both forms are collected and both must be covered.
    emitted = set(re.findall(r'record_gauge\(\s*f?"(staged:unit_(?:bound|worst)[^"{]*)', src))
    interpolated = set(
        re.findall(r'record_gauge\(\s*f?"\{(UNIT_(?:BOUND|WORST)_PREFIX)\}([^"{]*)', src)
    )
    resolved = {
        getattr(calibration_main_build, name) + rest for name, rest in interpolated
    }
    all_emitted = emitted | resolved

    assert all_emitted, "the writer no longer records any unit fence gauge"
    for name in sorted(all_emitted):
        assert name.startswith((UNIT_BOUND_PREFIX, UNIT_WORST_PREFIX)), (
            f"writer emits {name!r}, which the captured prefixes do not cover"
        )


def test_the_two_bound_stems_cannot_shadow_each_other():
    """``_headroom_ms:`` and ``_ms:`` both follow ``staged:unit_bound``. If one
    were a prefix of the other, scan order would decide which phase map a key
    landed in — so pin that neither is, rather than trusting the reading."""
    a, b = UNIT_FENCE_STEMS["unit_bound_ms"], UNIT_FENCE_STEMS["unit_bound_headroom_ms"]
    assert not a.startswith(b) and not b.startswith(a)


def test_the_fence_reads_back_per_phase():
    fence = unit_fence(LEDGER)

    assert fence["unit_bound_ms"] == {"futures": 949_749, "events": 540_000}
    assert fence["unit_bound_headroom_ms"] == {"futures": 191_000, "events": 0}


def test_a_headroom_of_zero_is_a_measurement_not_an_absence():
    """The whole reason this pair is version-gated. ``events`` above ran a bound
    that consumed its entire remaining window — a real, reportable state — and it
    must be distinguishable from a key nobody retained."""
    row = {"gauge_capture_version": UNIT_FENCE_CAPTURE_VERSION, "gauges": LEDGER}

    out = row_unit_fence(row)

    assert out["unit_bound_headroom_ms"]["events"] == 0
    assert out["unit_fence_measured"] is True
    assert out["unit_fence_absent"] is None


def test_a_row_below_the_floor_answers_unknown_never_zero():
    """CERT-2051. A row banked by the previous sampler has these keys discarded
    AT CAPTURE TIME, so re-deriving from its gauge map would report a bound that
    left no headroom — plausible, specific and false."""
    row = {"gauge_capture_version": UNIT_FENCE_CAPTURE_VERSION - 1, "gauges": LEDGER}

    out = row_unit_fence(row)

    assert out["unit_bound_ms"] is None
    assert out["unit_bound_headroom_ms"] is None
    assert out["unit_fence_measured"] is False
    assert out["unit_fence_absent"] == UNIT_FENCE_ABSENT_CAPTURE


def test_a_beat_that_applied_no_bound_is_not_the_same_value_as_a_row_that_cannot_say():
    """``{}`` and ``None`` never share a value domain. A beat that refused its
    lease or died before its first unit wrote no fence key and says so; a row
    below the floor cannot speak to the question at all."""
    versioned_empty = row_unit_fence(
        {"gauge_capture_version": UNIT_FENCE_CAPTURE_VERSION, "gauges": {"staged:units_done": 0}}
    )
    below_floor = row_unit_fence({"gauge_capture_version": 3, "gauges": {}})

    assert versioned_empty["unit_bound_ms"] == {}
    assert versioned_empty["unit_fence_measured"] is True
    assert below_floor["unit_bound_ms"] is None
    assert below_floor["unit_fence_measured"] is False


def test_a_legacy_or_hostile_row_falls_to_unknown():
    """An unversioned row, a non-dict and a bool version all land below the floor
    — absence fails to unknown, never to a number."""
    for row in ({"gauges": LEDGER}, None, "row", {"gauge_capture_version": True}):
        out = row_unit_fence(row)
        assert out["unit_fence_measured"] is False, row
        assert out["unit_bound_ms"] is None, row


def test_non_integer_and_malformed_fence_values_are_refused():
    """A gauge that is not a plain int is not a duration. Dropping it keeps the
    map's value domain honest rather than serving a string as a millisecond
    count; ``True`` is refused for the reason ``capture_version`` refuses it."""
    fence = unit_fence(
        {
            "staged:unit_bound_ms:futures": "949749",
            "staged:unit_bound_headroom_ms:futures": True,
            "staged:unit_bound_ms:events": 1,
        }
    )

    assert fence["unit_bound_ms"] == {"events": 1}
    assert fence["unit_bound_headroom_ms"] == {}


def test_the_capture_stamp_moved_with_the_rule():
    """A capture rule changes what ABSENCE means and the ring outlives the
    change, so the stamp a row carries has to be able to tell the two apart."""
    assert GAUGE_CAPTURE_VERSION >= UNIT_FENCE_CAPTURE_VERSION
    assert UNIT_FENCE_CAPTURE_VERSION == 4


def test_the_endpoint_projects_the_fence_into_the_default_view():
    """CAL-P1002's precedent: the question a reader of a stalled rebuild arrives
    with must not cost a ~200 KB ``full=true`` pull to reach."""
    from app.routes import admin_cohort

    src = Path(inspect.getsourcefile(admin_cohort)).read_text()
    assert "row_unit_fence" in src
    assert "fences = [row_unit_fence(r) for r in bounded]" in src
