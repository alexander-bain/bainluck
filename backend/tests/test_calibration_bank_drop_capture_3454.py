"""CAL-P1030 (#3454) — the bank wipe and the stop reason stop being invisible.

PILLAR: TRUTH. Rides the queued ship "the accuracy page's numbers start
refreshing again" (#1597, #3437).

What was wrong
--------------
The rebuild's most destructive event was the one event its telemetry could not
show. ``retain_planned_units``' CAL-P034 FAIL-CLOSED arm discards **every**
banked unit — building bank and serving bank both, *"Everything goes, and the
walk restarts"* — when any one banked unit is not in the current plan. Its only
signal is ``staged:units_dropped``, and ``calibration_beat_gauge_sampler``
captured neither that key nor any of the seven ``staged:*_stop:*`` reasons the
producer writes when a beat gives up early.

Measured 2026-09-06 over all 168 banked observations from
``GET /api/admin/calibration-beat-gauges?limit=16&full=true``: the substring
``drop`` does not occur once, and no ``*_stop:*`` key occurs once. Live
generation ``c1d6afbc16`` went 6 banked units → 0 between 03:16Z and 04:16Z with
every ``staged:cursor_reason:*`` at ``0`` — no recorded cause — and the one path
that produces exactly that shape was unobservable by construction.

The three classes of test here
------------------------------
1. **Capture.** A ledger carrying a drop and a stop reason surfaces both.
2. **Gotcha #53.** A drop of zero is distinguishable from a drop never written.
   The producer writes the key only inside ``if dropped:``, so absence is
   ambiguous on its own; the disambiguator is the cursor action, written
   unconditionally three lines above the call that can drop.
3. **Drift against the frozen writer.** ``precompute_calibration.py`` is
   D45/ruling-009 frozen, so the stop-key shape cannot be imported. These read
   its SOURCE and fail if the emitted literals move — CAL-P993's rule paid for
   differently, the same way ``test_calibration_cursor_decision_capture_1002.py``
   pays for ``CURSOR_PREFIX``.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    OPERATIONAL_GAUGES,
    STAGED_PREFIX,
    STOP_REASON_INFIX,
    bank_drop,
    build_observation,
    is_stop_key,
    select_gauges,
    stop_reasons,
)

# Every stop stage the producer writes today, read once here and pinned against
# the source below so this list cannot quietly go stale.
_WINDOW_STOPS = (
    "staged:window_stop:deadline",
    "staged:window_stop:unit_too_large",
    "staged:window_stop:units_cancelling",
)
_REBUILD_STOPS = (
    "staged:rebuild_stop:interrupted",
    "staged:rebuild_stop:no_window_after_publish",
    "staged:rebuild_stop:overlap_lock",
    "staged:rebuild_stop:error",
)


# ---------------------------------------------------------------------------
# 1. capture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", _WINDOW_STOPS + _REBUILD_STOPS)
def test_every_stop_reason_the_producer_writes_is_captured(key):
    """The regression in one line: none of these survived ``select_gauges``."""
    captured, _ = select_gauges({key: 0, "read:futures_generation": 226604})
    assert key in captured, f"{key} was dropped by the sampler"
    assert "read:futures_generation" not in captured


def test_the_two_stop_stems_are_both_reached_by_one_rule():
    """``window_stop`` and ``rebuild_stop`` share no prefix but ``staged:``.

    A prefix tuple would need one entry per stem and would silently miss the
    third — which is the omission this file has now recorded four times. The
    infix is what the producer's naming convention actually guarantees.
    """
    stages = {"staged:window_stop:deadline": 0, "staged:rebuild_stop:interrupted": 0}
    captured, _ = select_gauges(stages)
    assert set(captured) == set(stages)
    assert stop_reasons(captured) == ["rebuild_stop:interrupted", "window_stop:deadline"]


def test_a_stem_this_repo_has_never_written_is_still_captured():
    """The rule has to survive the NEXT stem, not just today's two."""
    captured, _ = select_gauges({"staged:publish_stop:something_new": 0})
    assert "staged:publish_stop:something_new" in captured
    assert stop_reasons(captured) == ["publish_stop:something_new"]


def test_units_dropped_is_captured():
    captured, _ = select_gauges({"staged:units_dropped": 6})
    assert captured["staged:units_dropped"] == 6
    assert "staged:units_dropped" in OPERATIONAL_GAUGES


def test_the_infix_is_namespaced_so_it_cannot_sweep_a_foreign_key():
    """``_stop:`` alone would match anything. Only ``staged:`` keys qualify."""
    captured, _ = select_gauges({"diagnostics:worker_stop:sigterm": 0})
    assert captured == {}
    assert is_stop_key("diagnostics:worker_stop:sigterm") is False
    assert is_stop_key("staged:window_stop:deadline") is True
    # The infix must be BEYOND the namespace, not inside it.
    assert is_stop_key("staged:units_done") is False
    assert is_stop_key(None) is False


def test_the_live_wipe_beat_becomes_attributable():
    """The 2026-09-06 03:16Z→04:16Z shape, replayed.

    6 banked units → 0 with every cursor reason at zero. Before this change the
    banked row carried no ``drop`` substring anywhere, so the wipe was
    indistinguishable from a beat that simply banked nothing.
    """
    stages = {
        "staged:cursor_resume": 0,
        "staged:cursor_reason:generation_unchanged": 0,
        "staged:units_dropped": 6,
        "staged:units_done": 0,
        "staged:window_stop:deadline": 0,
        "staged:window_left_ms": 1150000,
    }
    observation = build_observation(
        generation=1757131234567,
        generated_at="2026-09-06T04:16:00+00:00",
        complete=True,
        payload={"stages": stages, "terminal": "partial"},
    )
    assert observation["units_dropped"] == 6
    assert observation["units_dropped_measured"] is True
    assert observation["stop_reasons"] == ["window_stop:deadline"]
    # And the raw key is still on the row, so the derivation stays replayable
    # against a future version of this reader rather than replacing it.
    assert observation["gauges"]["staged:units_dropped"] == 6


# ---------------------------------------------------------------------------
# 2. gotcha #53 — a zero drop is not an unwritten drop
# ---------------------------------------------------------------------------

def test_a_drop_of_zero_is_distinguishable_from_a_drop_never_written():
    """The producer writes the key only inside ``if dropped:``.

    So absence carries two facts, and the cursor action — written
    unconditionally three lines above the call that can drop — separates them.
    """
    reached = bank_drop({"staged:cursor_resume": 0})
    assert reached == {"units_dropped": 0, "measured": True}

    never_reached = bank_drop({"staged:units_done": 4})
    assert never_reached == {"units_dropped": None, "measured": False}

    # And the two must not collapse into the same rendered value.
    assert reached["units_dropped"] != never_reached["units_dropped"]


def test_a_refused_beat_reports_unknown_rather_than_zero():
    """``REFUSE`` returns BEFORE the ledger write, so the row has no cursor key.

    Reporting that as "dropped 0" would be the CAL-P028 collapse ("nothing
    dropped" vs "we never looked") arriving through the field added to end it.
    """
    assert bank_drop({})["measured"] is False
    assert bank_drop({})["units_dropped"] is None
    assert bank_drop(None)["units_dropped"] is None


@pytest.mark.parametrize("action", ["fresh", "resume", "invalidate"])
def test_every_cursor_action_counts_as_having_reached_the_drop_path(action):
    """``record_stage(f"staged:cursor_{action}")`` is unconditional for all three."""
    assert bank_drop({f"staged:cursor_{action}": 0}) == {
        "units_dropped": 0,
        "measured": True,
    }


def test_an_explicit_zero_is_reported_as_measured():
    """If the writer's ``if dropped:`` guard is ever removed, a literal 0 must
    read as measured rather than falling through to the cursor inference."""
    assert bank_drop({"staged:units_dropped": 0}) == {
        "units_dropped": 0,
        "measured": True,
    }


def test_a_beat_that_recorded_no_stop_reason_answers_empty_not_unknown():
    assert stop_reasons({"staged:units_done": 128}) == []
    assert stop_reasons(None) == []


# ---------------------------------------------------------------------------
# 3. drift against the frozen writer
# ---------------------------------------------------------------------------

def _producer_source() -> str:
    from app.tasks import precompute_calibration

    return Path(inspect.getsourcefile(precompute_calibration)).read_text()


def test_every_stop_stage_in_the_frozen_writer_matches_the_infix_rule():
    """``precompute_calibration.py`` is frozen, so there is no constant to
    import. This reads its source and fails if a stop stage is ever emitted
    under a name the sampler's rule cannot reach.

    When the freeze lifts: promote these literals to imports and delete this.
    """
    src = _producer_source()
    emitted = set(re.findall(r'record_stage\(\s*f?"([^"{]*_stop:[^"{]*)', src))
    assert emitted, "the writer no longer records any *_stop:* stage"
    unreachable = sorted(name for name in emitted if not is_stop_key(name))
    assert not unreachable, (
        f"writer emits {unreachable}, which "
        f"{STAGED_PREFIX!r} + {STOP_REASON_INFIX!r} does not cover"
    )


def test_the_stop_stages_this_suite_names_are_the_ones_the_writer_writes():
    """The parametrised list above is a transcription, and a transcription that
    is never checked is how ``staged:units_done`` went missing in CAL-P083."""
    src = _producer_source()
    emitted = set(re.findall(r'record_stage\(\s*"(staged:[a-z_]+_stop:[a-z_]+)"', src))
    named = set(_WINDOW_STOPS + _REBUILD_STOPS)
    # ``staged:window_stop:{stop_reason}`` is interpolated, so ``deadline`` and
    # ``unit_too_large`` are not literals in the source and are excluded here.
    interpolated = {"staged:window_stop:deadline", "staged:window_stop:unit_too_large"}
    assert emitted <= named, f"writer emits stop stages this suite does not name: {emitted - named}"
    assert (named - interpolated) <= emitted, (
        f"this suite names stop stages the writer no longer writes: {named - interpolated - emitted}"
    )


def test_the_writer_still_records_units_dropped_under_that_name():
    """If the drop stage is renamed, capturing the old name is a silent no-op —
    exactly the shape of the defect this file closes."""
    assert 'record_stage("staged:units_dropped"' in _producer_source()


def test_the_writer_still_writes_the_cursor_action_before_it_can_drop():
    """``bank_drop``'s zero-vs-unknown split rests entirely on this ordering.

    If ``retain_planned_units`` ever moves above the cursor stage write, a beat
    that dropped nothing would report ``measured: false`` — degraded, not wrong,
    but this says so rather than letting the inference rot quietly.
    """
    src = _producer_source()
    cursor_at = src.index('record_stage(f"staged:cursor_{action}"')
    drop_at = src.index("cursor, dropped = retain_planned_units(")
    assert cursor_at < drop_at, (
        "the cursor action is no longer written before the drop path — "
        "bank_drop's zero-vs-unknown inference no longer holds"
    )
