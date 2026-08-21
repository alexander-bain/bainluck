"""CAL-P084 (#2007) — the beat gauge sampler, and the blind-spot class it closes.

The instrument under test exists because the bound's first descent
(2026-08-21 12:30:24Z, generation 1787315424367) was captured by a background
process a PREVIOUS window had left running. ``durable_state_snapshots`` keeps one
row per identity, so the phase ledger is overwritten every beat and that beat is
now unrecoverable from production. Descent-survived-on-luck.

The suite is weighted towards ONE property, because it is the one that has
already failed twice in this program and both times was found by accident:

    **the captured gauge set must be SUFFICIENT to reproduce the disclosure.**

``test_captured_gauges_reproduce_the_full_disclosure`` is that property stated
directly — it builds a disclosure from a complete ledger and again from only the
keys the sampler kept, and demands they be identical. Both CAL-P083 blind spots
(``staged:served_drift_uncheckable``, the term that can only push the bound UP;
and ``staged:units_done``, an operand of the carry guard's own predicate) would
have failed it on the row they were omitted from. So would the third one, the
``staged:convergence_reason:`` PREFIX, which was still open when this file was
written and which no fixed tuple can ever hold.
"""

from __future__ import annotations

import datetime

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    CONVERGENCE_REASON_PREFIX,
    HISTORY_LIMIT,
    OPERATIONAL_GAUGES,
    REQUIRED_DISCLOSURE_GAUGES,
    build_observation,
    decide_terminal,
    merge_history,
    select_gauges,
    summarise,
)
from app.utils.calibration_published_twin import tolerance_pp
from app.utils.calibration_staged_disclosure import build_disclosure

UTC = datetime.timezone.utc

# The real 2026-08-21 promotion, kept as the fixture spine so this suite fails if
# the production pair ever stops reproducing a beat already quoted in a report.
_PROMOTION_EPOCH = 1_787_315_330
_PRIOR_EPOCH = 1_787_250_149
_PROMOTION_GEN = 1_787_315_424_367
_PROMOTION_AT = "2026-08-21T12:30:24+00:00"


def _stages(*, served_at, served_drifted, served_units=128, uncheckable=0,
            rebuild_banked=0, this_beat=6, extra=None):
    """A ledger ``stages`` map with MORE keys than the sampler keeps.

    Deliberately noisy: the sampler's job includes not hoarding the whole ledger,
    so the fixture carries phase timings and counters it must drop.
    """
    stages = {
        "staged:served_units": served_units,
        "staged:served_drifted": served_drifted,
        "staged:served_drift_uncheckable": uncheckable,
        "staged:served_at": served_at,
        "staged:units_banked": rebuild_banked,
        "staged:units_this_beat": this_beat,
        "staged:units_drifted": 0,
        "staged:units_drift_checkable": rebuild_banked,
        "staged:units_drift_uncheckable": 0,
        "staged:units_planned": 128,
        "staged:units_done": rebuild_banked,
        "staged:units_completed_this_beat": this_beat,
        "staged:beats_to_publish": 17,
        "staged:unit_ms_mean": 4210,
        "staged:unit_ms_worst": 9980,
        "staged:window_left_ms": 120_000,
        "staged:cursor_resume": 1,
        "staged:units_cancelled": 0,
        # noise the sampler must NOT keep
        "read:futures_generation": 18_784,
        "write:sports": 4_100,
        "diagnostics:rows": 991_213,
    }
    if extra:
        stages.update(extra)
    return stages


def _ledger(stages, *, terminal="complete", banked=None, carried=None):
    return {
        "terminal": terminal,
        "carried": carried if carried is not None else [],
        "banked": banked if banked is not None else {},
        "outcome": "published",
        "elapsed_ms": 1_208_532,
        "input_fingerprint": "abc123",
        "stages": stages,
        "phases": [{"name": "futures", "checkpoint_write": "not_attempted"}],
    }


# ---------------------------------------------------------------------------
# The gauge list is DERIVED, not typed
# ---------------------------------------------------------------------------

class TestGaugeListIsDerived:
    def test_required_set_matches_every_gauge_constant_in_the_disclosure_module(self):
        """Both directions. A rename or an addition over there must land here.

        This is the structural half of the fix. The two CAL-P083 blind spots were
        transcription omissions from a hand-maintained tuple; a derivation cannot
        omit, but a later editor CAN replace the derivation with a literal and
        reintroduce the defect. This test is what stops that being silent.
        """
        from app.utils import calibration_staged_disclosure as mod

        declared = {
            value
            for attr, value in vars(mod).items()
            if attr.startswith("GAUGE_") and isinstance(value, str)
        }
        assert declared, "the disclosure module declares no GAUGE_* constants"
        assert set(REQUIRED_DISCLOSURE_GAUGES) == declared

    def test_the_two_cal_p083_blind_spots_are_in_the_required_set(self):
        """Named explicitly, because these two cost a queue each to discover."""
        assert "staged:served_drift_uncheckable" in REQUIRED_DISCLOSURE_GAUGES
        # `units_done` is not read by `build_disclosure`, so it lives in the
        # operational half — but it MUST be captured, because it is a literal
        # operand of the carry-withhold's predicate.
        assert "staged:units_done" in OPERATIONAL_GAUGES

    def test_required_gauges_are_sorted_and_deduped(self):
        """Stable across interpreter runs, so the tuple is quotable in a report."""
        assert list(REQUIRED_DISCLOSURE_GAUGES) == sorted(set(REQUIRED_DISCLOSURE_GAUGES))


# ---------------------------------------------------------------------------
# The property the whole instrument rests on
# ---------------------------------------------------------------------------

class TestCapturedGaugesAreSufficient:
    @pytest.mark.parametrize(
        "extra",
        [
            None,
            {"staged:convergence_reason:cursor_unreadable": 1},
            {"staged:convergence_reason:digest_absent": 3},
        ],
    )
    def test_captured_gauges_reproduce_the_full_disclosure(self, extra):
        """Disclosure over the FULL ledger == disclosure over what we kept.

        The parametrisation is the third blind spot. ``build_disclosure`` scans
        for any key starting with ``staged:convergence_reason:`` and returns that
        key as the unmeasured reason; a capture that dropped it would replay as
        the generic ``units_banked_absent``, so the one row that could explain a
        disclosure outage would explain it wrongly, with the instrument's
        authority.
        """
        stamp = datetime.datetime(2026, 8, 21, 12, 30, 24, tzinfo=UTC)
        full = _stages(served_at=_PROMOTION_EPOCH, served_drifted=0, extra=extra)
        if extra:
            # A convergence reason only reaches its branch when `units_banked`
            # is unreadable, so remove both banked gauges for that case.
            full.pop("staged:units_banked")
            full.pop("staged:served_units")

        captured, missing = select_gauges(full)

        from_full = build_disclosure(
            ledger_stages=full, staged_generated_at=stamp, now=stamp
        )
        from_captured = build_disclosure(
            ledger_stages=captured, staged_generated_at=stamp, now=stamp
        )
        assert from_captured == from_full
        assert tolerance_pp(from_captured) == tolerance_pp(from_full)
        if extra:
            assert from_captured["measured"] is False
            assert from_captured["reason"].startswith(CONVERGENCE_REASON_PREFIX)
        else:
            assert missing == []

    def test_noise_is_dropped(self):
        captured, _ = select_gauges(_stages(served_at=_PRIOR_EPOCH, served_drifted=128))
        assert "read:futures_generation" not in captured
        assert "diagnostics:rows" not in captured

    def test_a_missing_required_gauge_is_named_on_the_row_not_swallowed(self):
        stages = _stages(served_at=_PRIOR_EPOCH, served_drifted=128)
        stages.pop("staged:served_drift_uncheckable")
        captured, missing = select_gauges(stages)
        assert missing == ["staged:served_drift_uncheckable"]
        assert "staged:served_drift_uncheckable" not in captured

    def test_non_mapping_stages_report_everything_missing_rather_than_empty(self):
        captured, missing = select_gauges(None)
        assert captured == {}
        assert set(missing) == set(REQUIRED_DISCLOSURE_GAUGES)


# ---------------------------------------------------------------------------
# One observation
# ---------------------------------------------------------------------------

class TestBuildObservation:
    def test_the_promotion_beat_reproduces_its_quoted_bound(self):
        obs = build_observation(
            generation=_PROMOTION_GEN,
            generated_at=_PROMOTION_AT,
            complete=True,
            payload=_ledger(_stages(served_at=_PROMOTION_EPOCH, served_drifted=0)),
        )
        assert obs["generation"] == _PROMOTION_GEN
        assert obs["tolerance_pp"] == pytest.approx(0.5)
        assert obs["measured"] is True
        assert obs["gauges_missing_required"] == []

    def test_the_saturated_beat_reproduces_100pp(self):
        obs = build_observation(
            generation=_PROMOTION_GEN + 3_600_000,
            generated_at="2026-08-21T13:30:24+00:00",
            complete=True,
            payload=_ledger(_stages(served_at=_PRIOR_EPOCH, served_drifted=128)),
        )
        assert obs["tolerance_pp"] == pytest.approx(100.0)

    def test_the_row_does_not_move_when_the_wall_clock_does(self):
        """Gotcha #44. ``now`` is pinned to the beat's own stamp.

        A stored observation whose ``staged_age_s`` depended on when the sampler
        happened to run would be a different number every re-derivation, and a
        grader whose output changes overnight cannot be quoted in a report.
        """
        payload = _ledger(_stages(served_at=_PROMOTION_EPOCH, served_drifted=0))
        first = build_observation(
            generation=_PROMOTION_GEN, generated_at=_PROMOTION_AT,
            complete=True, payload=payload,
        )
        second = build_observation(
            generation=_PROMOTION_GEN, generated_at=_PROMOTION_AT,
            complete=True, payload=payload,
        )
        assert first == second
        assert first["disclosure"]["staged_age_s"] == 94

    def test_the_carry_withhold_token_is_kept_from_banked_not_from_phases(self):
        """CAL-P083's own correction, pinned.

        ``phases[].checkpoint_write`` collapses to two values and can NEVER carry
        a refusal reason; the guard announces itself in the top-level ``banked``
        map. An instrument reading the wrong one can agree with the guard but
        never derive it.
        """
        obs = build_observation(
            generation=1_787_297_985_432,
            generated_at="2026-08-21T07:39:45+00:00",
            complete=False,
            payload=_ledger(
                _stages(served_at=_PRIOR_EPOCH, served_drifted=128, rebuild_banked=95),
                terminal="failed",
                banked={"futures": "rebuild_in_flight"},
                carried=["sports"],
            ),
        )
        assert obs["banked"] == {"futures": "rebuild_in_flight"}
        assert obs["terminal"] == "failed"
        assert obs["envelope_complete"] is False
        # And the predicate's operands travelled with the verdict.
        assert obs["gauges"]["staged:units_done"] == 95
        assert obs["gauges"]["staged:units_planned"] == 128

    def test_an_unparseable_beat_stamp_keeps_the_bound_and_withholds_the_age(self):
        """The wall-clock hole this suite actually found, pinned shut.

        ``build_disclosure`` derives a SERVING bank's ``staged_at`` from
        ``staged:served_at`` and ignores ``staged_generated_at`` entirely, so an
        unparseable beat stamp still yields a MEASURED disclosure — and the
        first version of ``build_observation`` then passed ``now=None``, which
        dates that row against whenever the sampler happened to run. The row
        became a different row on every re-derivation: gotcha #44 through the
        one input that looked safe because it is usually not None.

        The bound does not depend on an age, so it is kept; the age does, so it
        is withheld and the withholding is named.
        """
        obs = build_observation(
            generation=1, generated_at="not-a-date", complete=True,
            payload=_ledger(_stages(served_at=_PRIOR_EPOCH, served_drifted=128)),
        )
        assert obs["generated_at"] is None
        assert obs["beat_stamp_unparseable"] is True
        assert obs["measured"] is True
        assert obs["tolerance_pp"] == pytest.approx(100.0)
        assert obs["disclosure"]["staged_age_s"] is None

    def test_an_unparseable_stamp_row_is_still_clock_independent(self):
        payload = _ledger(_stages(served_at=_PRIOR_EPOCH, served_drifted=128))
        first = build_observation(
            generation=1, generated_at="not-a-date", complete=True, payload=payload
        )
        second = build_observation(
            generation=1, generated_at="not-a-date", complete=True, payload=payload
        )
        assert first == second

    def test_neither_stamp_nor_served_epoch_is_unmeasured_not_defaulted(self):
        stages = _stages(served_at=_PRIOR_EPOCH, served_drifted=128)
        stages.pop("staged:served_at")
        obs = build_observation(
            generation=1, generated_at="not-a-date", complete=True,
            payload=_ledger(stages),
        )
        assert obs["measured"] is False
        assert obs["tolerance_pp"] is None


# ---------------------------------------------------------------------------
# The ring
# ---------------------------------------------------------------------------

def _obs(gen, *, measured=True, bound=100.0):
    return {"generation": gen, "generated_at": f"gen-{gen}",
            "measured": measured, "tolerance_pp": bound}


class TestMergeHistory:
    def test_a_new_generation_appends(self):
        out = merge_history({"observations": [_obs(1)]}, _obs(2))
        assert out["appended"] is True
        assert [r["generation"] for r in out["observations"]] == [1, 2]

    def test_a_generation_seen_twice_is_one_beat_read_twice(self):
        """CAL-P081's ``[13, 13]`` was exactly this shape in the adjacent tool."""
        out = merge_history({"observations": [_obs(1), _obs(2)]}, _obs(2))
        assert out["appended"] is False
        assert [r["generation"] for r in out["observations"]] == [1, 2]

    def test_a_measured_re_read_upgrades_an_unmeasured_row(self):
        out = merge_history(
            {"observations": [_obs(2, measured=False, bound=None)]},
            _obs(2, measured=True, bound=0.5),
        )
        assert out["replaced"] is True
        assert out["observations"][0]["tolerance_pp"] == 0.5

    def test_an_unmeasured_re_read_never_degrades_a_measured_row(self):
        out = merge_history(
            {"observations": [_obs(2, measured=True, bound=0.5)]},
            _obs(2, measured=False, bound=None),
        )
        assert out["replaced"] is False
        assert out["observations"][0]["tolerance_pp"] == 0.5

    def test_the_ring_trims_to_the_limit_keeping_the_newest(self):
        existing = {"observations": [_obs(g) for g in range(HISTORY_LIMIT)]}
        out = merge_history(existing, _obs(HISTORY_LIMIT))
        assert len(out["observations"]) == HISTORY_LIMIT
        assert out["observations"][-1]["generation"] == HISTORY_LIMIT
        assert out["observations"][0]["generation"] == 1

    def test_rows_are_ordered_by_generation_even_if_banked_out_of_order(self):
        out = merge_history({"observations": [_obs(9), _obs(3)]}, _obs(5))
        assert [r["generation"] for r in out["observations"]] == [3, 5, 9]

    def test_a_generationless_observation_is_refused_rather_than_appended(self):
        existing = {"observations": [_obs(1)]}
        out = merge_history(existing, {"generation": None})
        assert out["appended"] is False
        assert [r["generation"] for r in out["observations"]] == [1]

    def test_an_unreadable_existing_ring_does_not_wipe_the_history_shape(self):
        out = merge_history("not-a-dict", _obs(1))
        assert out["appended"] is True
        assert len(out["observations"]) == 1


class TestSummarise:
    def test_the_trough_is_reported_with_its_denominator(self):
        """CAL-P083's finding: quoting the trough alone is #2007 in party clothes."""
        rows = [_obs(g, bound=100.0) for g in range(15)] + [_obs(15, bound=0.5)]
        out = summarise({"observations": rows})
        assert out["bound_min_pp"] == 0.5
        assert out["bound_min_generation"] == 15
        assert out["bound_max_pp"] == 100.0
        assert out["observations"] == 16
        # one beat in sixteen — the operative fact
        assert out["beats_at_floor"] == 1

    def test_an_empty_ring_reports_none_not_zero(self):
        out = summarise({"observations": []})
        assert out["observations"] == 0
        assert out["bound_min_pp"] is None
        assert out["newest_generation"] is None


# ---------------------------------------------------------------------------
# Terminals — the half that decides whether a silent sampler reads GREEN
# ---------------------------------------------------------------------------

class TestDecideTerminal:
    def test_a_captured_current_beat_is_complete(self):
        terminal, reason = decide_terminal(
            read_status="ok", observation=_obs(1), write_status="stored", ledger_age_s=600
        )
        assert terminal == "complete"
        assert reason is None

    def test_an_already_present_beat_is_still_complete(self):
        """``unchanged`` is the job done, not a failure and not no-work."""
        terminal, _ = decide_terminal(
            read_status="ok", observation=_obs(1), write_status="unchanged", ledger_age_s=600
        )
        assert terminal == "complete"

    def test_an_unreadable_ledger_fails(self):
        terminal, reason = decide_terminal(
            read_status="unavailable", observation=None, write_status=None, ledger_age_s=None
        )
        assert terminal == "failed"
        assert "unavailable" in reason

    def test_a_failed_history_write_fails_because_the_record_IS_the_product(self):
        terminal, reason = decide_terminal(
            read_status="ok", observation=_obs(1), write_status="error", ledger_age_s=60
        )
        assert terminal == "failed"
        assert "history_write_failed" in reason

    def test_a_missing_required_gauge_fails(self):
        obs = dict(_obs(1), gauges_missing_required=["staged:served_drift_uncheckable"])
        terminal, reason = decide_terminal(
            read_status="ok", observation=obs, write_status="stored", ledger_age_s=60
        )
        assert terminal == "failed"
        assert "staged:served_drift_uncheckable" in reason

    def test_a_stale_ledger_is_partial_so_it_cannot_read_green(self):
        """The sampler worked; the producer stopped. Not the same as health."""
        terminal, reason = decide_terminal(
            read_status="ok", observation=_obs(1), write_status="unchanged",
            ledger_age_s=4 * 3600,
        )
        assert terminal == "partial"
        assert "ledger_stale" in reason

    def test_a_write_failure_dominates_a_stale_ledger(self):
        terminal, reason = decide_terminal(
            read_status="ok", observation=_obs(1), write_status="error",
            ledger_age_s=4 * 3600,
        )
        assert terminal == "failed"
        assert "history_write_failed" in reason


class TestEnrolment:
    def test_the_sampler_is_enrolled_with_a_terminal(self):
        """Enrolment without a terminal is a documented no-op."""
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "calibration_beat_gauge_sampler" in ENFORCED_TASKS
        green = verdict_for("calibration_beat_gauge_sampler", {"terminal": "complete"})
        red = verdict_for("calibration_beat_gauge_sampler", {"terminal": "failed"})
        stale = verdict_for("calibration_beat_gauge_sampler", {"terminal": "partial"})
        assert green.authoritative and green.verdict != red.verdict
        assert red.authoritative
        assert stale.verdict != green.verdict

    def test_the_beat_entries_avoid_the_producer_window(self):
        """:05 and :45 — never inside the producer's :15-:35."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["calibration-beat-gauge-sampler"]
        assert entry["task"] == "app.tasks.calibration_beat_gauge_sampler"
        minutes = {int(m) for m in entry["schedule"].minute}
        assert minutes == {5, 45}
        assert not any(15 <= m <= 35 for m in minutes)
