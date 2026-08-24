"""#2116 — `DEGRADE_P50_RATIO` gets a MATERIALITY FLOOR, in absolute seconds,
scaled by what CONSUMES the beat. Fable directive 2026-08-23 (LAT-P083 item 1),
pasted and reviewed by Alex, executing option **B** of the three costed in #2116.

WHAT WAS WRONG. `DEGRADE_P50_RATIO = 1.25` is a pure ratio with no absolute
term, so the falsifier's sensitivity was **inversely proportional to how much a
beat matters**:

    precompute_source_intelligence   pinned  17.5s   ->  +4.4s fires REVERT
    compute_fair_fight_comparison    pinned 147.8s   ->  +37s  fires REVERT
    precompute_calibration_main      pinned 1187.8s  ->  +297s fires REVERT
                                                          ^ the one beat a
                                                            user-facing page
                                                            waits on

**67x more sensitive to the beat that matters least.** On 2026-08-23 that
converted +9.3 s of median on a 4x/day admin precompute into a mechanical
REVERT of ruling 110's grant, with a *falling* p95 and n = 8.

WHAT THE FIX IS. A beat degrades only when BOTH gates trip: the ratio AND an
absolute delta in seconds. The floor is per-beat and comes from a MEASURED
consumer classification (`BeatBaseline.consumer`), not from taste — see
`CONSUMER_FLOOR_S` for the classification evidence.

🔴 **WHAT THE FIX IS NOT, and this is the test that says so.** A floor is a way
to make a gate quieter, and a gate that cannot go red is the failure this
program has already minted twice (LAT-P079's `samples == 0 => INCONCLUSIVE`
would have been never-false). So:

  * `test_the_floor_can_still_fire_a_revert` is the control. It must be green
    BEFORE this change and AFTER it — the floor raises the bar, it does not
    remove it.
  * a ratio trip under the floor grades **`immaterial`**, a named state that is
    printed, counted and carried into `grade_move`'s top-level reason. It is
    never folded into `hold`. A suppressed finding that leaves no trace is the
    same defect wearing the fix's clothes.
  * the floor is CAPPED so it can never push a beat's trip point past the point
    at which the observation-side censor (#2071) takes over. Otherwise a beat
    could be made ungradeable by the floor alone.

RESIDUAL, STATED RATHER THAN CLAIMED FIXED: the floor is a MINIMUM, so the ratio
still governs slow beats, and the sensitivity spread narrows from **67x to
~5x** — it does not invert. Making the user-facing beat the *most* sensitive
needs a per-consumer CEILING as well, which tightens REVERT and is therefore a
decision about ruling 110's grant that this lane does not get to make.
`test_the_residual_asymmetry_is_bounded_and_named` pins the number so the claim
is executable rather than prose.
"""

from __future__ import annotations

import pytest

from app.utils.heavy_routing_falsifier import (
    CENSOR_FRACTION_OF_SOFT_LIMIT,
    CONSUMER_FLOOR_S,
    DEGRADE_P50_RATIO,
    PRE_MOVE_BASELINE,
    BASELINE_BY_TASK,
    ROUTING_CHANGE_AT_EPOCH,
    RUN_COUNTER_WINDOW_S,
    grade_beat,
    grade_move,
)

AT_HORIZON = ROUTING_CHANGE_AT_EPOCH + RUN_COUNTER_WINDOW_S + 3600

SI = "app.tasks.precompute_source_intelligence"

#: The eight post-move samples #2116 was escalated on, in seconds, exactly as
#: read from production on 2026-08-23. Their median is 26.8 s against a pinned
#: 17.5 s => ratio 1.53x, and their p95 (31.0 s) is BELOW the pinned p95
#: (32.6 s at the time of escalation) — a degradation that improves the tail.
REAL_2116_SAMPLES_S = (12.6, 19.9, 22.9, 23.6, 26.8, 27.4, 29.9, 31.0)


def _obs(p50_s: float, *, runs: int = 20, n: int = 20):
    return {
        "recent_durations_ms": [p50_s * 1000] * n,
        "successes_24h": runs,
        "failures_24h": 0,
    }


def _obs_from(samples_s, *, runs: int = 20):
    return {
        "recent_durations_ms": [s * 1000 for s in samples_s],
        "successes_24h": runs,
        "failures_24h": 0,
    }


def _all_holding():
    return {b.metrics_name: _obs(b.p50_s) for b in PRE_MOVE_BASELINE}


# ---------------------------------------------------------------------------
# 1. THE RE-GRADE — the reading #2116 was escalated on
# ---------------------------------------------------------------------------


def test_the_2116_reading_grades_immaterial_not_degraded():
    """+9.3 s on a beat whose only reader is `/admin/source-intelligence`.

    The ratio still trips (1.53x > 1.25x) and the verdict still SAYS so. What
    changes is that a ratio trip is no longer sufficient on its own.
    """
    baseline = BASELINE_BY_TASK[SI]
    verdict = grade_beat(
        baseline,
        _obs_from(REAL_2116_SAMPLES_S),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )

    assert verdict.verdict == "immaterial", verdict.reason
    assert verdict.ratio is not None and verdict.ratio > DEGRADE_P50_RATIO
    assert verdict.ratio_exceeded is True
    # +9.3s against a 60s floor for an operator-panel beat.
    assert verdict.absolute_delta_s == pytest.approx(9.3, abs=0.05)
    assert verdict.materiality_floor_s == pytest.approx(60.0)
    # The reason must carry BOTH numbers. A reader who is told only "immaterial"
    # cannot check the arithmetic that suppressed a REVERT.
    assert "1.53" in verdict.reason
    assert "9.3" in verdict.reason
    assert "60" in verdict.reason


def test_the_2116_reading_does_not_revert_the_routing():
    """End to end: the whole panel holds, and it NAMES what it declined to fire."""
    observations = _all_holding()
    observations[BASELINE_BY_TASK[SI].metrics_name] = _obs_from(REAL_2116_SAMPLES_S)

    result = grade_move(observations, now_epoch=AT_HORIZON)

    assert result.verdict == "HOLD", result.reason
    assert not result.must_revert
    assert "precompute_source_intelligence" in result.reason
    assert "immaterial" in result.reason.lower()


# ---------------------------------------------------------------------------
# 2. THE CONTROL — the gate must still be able to go red
# ---------------------------------------------------------------------------


def test_the_floor_can_still_fire_a_revert():
    """GREEN BEFORE AND AFTER. A floor raises the bar; it must not remove it.

    Same beat, same threshold, a delta that clears the floor: +72.5 s.
    """
    baseline = BASELINE_BY_TASK[SI]
    material = baseline.p50_s + baseline.materiality_floor_s + 10.0

    verdict = grade_beat(
        baseline, _obs(material), age_since_move_s=RUN_COUNTER_WINDOW_S + 3600
    )
    assert verdict.verdict == "degraded", verdict.reason

    observations = _all_holding()
    observations[baseline.metrics_name] = _obs(material)
    result = grade_move(observations, now_epoch=AT_HORIZON)
    assert result.verdict == "REVERT", result.reason
    assert result.must_revert


def test_a_delta_one_second_under_the_floor_holds_and_one_over_reverts():
    """The floor is a real edge, tested from both sides on one beat."""
    baseline = BASELINE_BY_TASK[SI]
    trip = baseline.p50_s + baseline.materiality_floor_s

    under = grade_beat(
        baseline, _obs(trip - 1.0), age_since_move_s=RUN_COUNTER_WINDOW_S + 3600
    )
    over = grade_beat(
        baseline, _obs(trip + 1.0), age_since_move_s=RUN_COUNTER_WINDOW_S + 3600
    )
    assert under.verdict == "immaterial", under.reason
    assert over.verdict == "degraded", over.reason


def test_the_ratio_still_governs_when_it_is_the_stricter_gate():
    """A slow beat is NOT loosened by the floor. Both gates, always AND.

    `precompute_backfill_winners_status` trips the ratio at +129.6 s and the
    floor at +60 s, so the ratio is the binding constraint and the floor changes
    nothing about it. A floor that quietly loosened a slow beat would be the
    "loosening `DEGRADE_P50_RATIO`" #2102 fenced off.

    NOTE 2026-08-24: since the ceiling shipped, the binding gate on THIS beat is
    the ceiling (+69.6 s, censor-capped from 120 s), not the ratio (+129.6 s).
    The assertion below is unchanged and still true — the floor is still the
    loosest of the three — and the +61 s reading still `hold`s because it is
    under the ceiling too. What the ceiling proves here is the direction the
    floor could not: the slow beat got STRICTER, not looser.
    """
    baseline = BASELINE_BY_TASK["app.tasks.precompute_backfill_winners_status"]
    assert baseline.materiality_floor_s < baseline.p50_s * (DEGRADE_P50_RATIO - 1.0)

    # Over the floor, under the ratio -> still holds, and NOT as `immaterial`
    # (the ratio never tripped, so there is nothing to declare immaterial).
    over_floor_only = baseline.p50_s + baseline.materiality_floor_s + 1.0
    verdict = grade_beat(
        baseline,
        _obs(over_floor_only),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    assert verdict.verdict == "hold", verdict.reason
    assert verdict.ratio_exceeded is False


# ---------------------------------------------------------------------------
# 3. THE CLASSIFICATION IS DECLARED, MEASURED, AND COMPLETE
# ---------------------------------------------------------------------------


def test_every_baseline_declares_a_consumer_from_the_table():
    """Ruling 123's shape, reused: a field the endpoint prints and a test enforces.

    A beat with no declared consumer has no defensible floor, so it must not be
    possible to add one silently.
    """
    for baseline in PRE_MOVE_BASELINE:
        assert baseline.consumer in CONSUMER_FLOOR_S, (
            f"{baseline.task} declares consumer={baseline.consumer!r}, which is "
            f"not one of {sorted(CONSUMER_FLOOR_S)}"
        )
        assert baseline.consumer_note.strip(), (
            f"{baseline.task} declares a consumer with no evidence — the note "
            "must say WHERE the consumer was found, because the floor is "
            "argued from it"
        )


def test_exactly_one_beat_is_classified_user_page():
    """Measured 2026-08-23, and it is the fact the whole floor turns on.

    `/api/calibration` is called by `frontend/lib/api.ts:2118` from the public
    `/calibration` page. Every other watched beat's only rendered consumer is
    under `/admin`, or has no rendered consumer at all.
    """
    user_page = [b.task for b in PRE_MOVE_BASELINE if b.consumer == "user_page"]
    assert user_page == ["app.tasks.precompute_calibration_main"]


# ---------------------------------------------------------------------------
# 4. THE FLOOR CANNOT DISARM THE INSTRUMENT
# ---------------------------------------------------------------------------


def test_the_floor_never_pushes_a_beat_past_its_own_censor():
    """The cap. Beyond the censor point the beat saturates and #2071 owns it.

    Without this, a declared floor larger than a beat's remaining headroom would
    make the ratio unreachable — a gate that cannot go red, minted by its own
    fix, for the third time in this program.
    """
    for baseline in PRE_MOVE_BASELINE:
        censor_at = CENSOR_FRACTION_OF_SOFT_LIMIT * baseline.effective_clamp_s
        if baseline.censored:
            # A beat whose BASELINE is already at the clamp never reaches the
            # ratio, so its floor is meaningless and clamps to zero rather than
            # going negative. `compute_calibration_prices` is the case — found
            # by this test on its first run, which is the reason the cap is
            # written as `max(0.0, min(...))` and not as a bare subtraction.
            assert baseline.materiality_floor_s == 0.0, baseline.task
            continue
        assert baseline.p50_s + baseline.materiality_floor_s <= censor_at + 1e-9, (
            f"{baseline.task}: floor trip "
            f"{baseline.p50_s + baseline.materiality_floor_s:.1f}s is past its "
            f"censor point {censor_at:.1f}s"
        )


def test_snapshot_coverage_metrics_floor_is_capped_and_says_so():
    """The one beat where the cap actually binds — 120s declared, 107.9s applied."""
    baseline = BASELINE_BY_TASK["app.tasks.snapshot_coverage_metrics"]
    assert baseline.consumer == "no_reader"
    assert CONSUMER_FLOOR_S["no_reader"] == pytest.approx(120.0)
    assert baseline.floor_capped_by_censor is True
    assert baseline.materiality_floor_s == pytest.approx(107.9, abs=0.05)
    assert baseline.materiality_floor_s < baseline.declared_materiality_floor_s


def test_the_censor_still_fires_regardless_of_the_floor():
    """A newly-saturated beat is censored, not immaterial. #2071 is untouched.

    The floor gates the RATIO. It must not be able to talk the instrument out of
    the loudest fact it can hold.
    """
    baseline = BASELINE_BY_TASK[SI]
    saturated = baseline.effective_clamp_s  # 600s, way over the clamp fraction
    verdict = grade_beat(
        baseline, _obs(saturated), age_since_move_s=RUN_COUNTER_WINDOW_S + 3600
    )
    assert verdict.verdict == "censored", verdict.reason
    assert verdict.censored_side == "observation"


# ---------------------------------------------------------------------------
# 5. THE RESIDUAL — pinned as a number, not described in prose
# ---------------------------------------------------------------------------


def test_the_residual_asymmetry_is_bounded_and_named():
    """67.9x -> 4.95x -> 2.0x, and at the third number it INVERTS.

    RE-DERIVED 2026-08-24 (LAT-P084). This test used to pin `3.0 < spread < 6.0`
    and its own failure message anticipated exactly this edit: *"or the floor
    became a ceiling; re-derive before loosening this bound"*. A per-consumer
    ceiling shipped (`CONSUMER_CEILING_S`), the bound is re-derived from
    measurement rather than loosened, and the residual it named is CLOSED:

        ratio only     1187.8 / 17.5                       = 67.9x
        + floor        296.95 / 60.0   user_page WORST     =  4.95x
        + ceiling      120.0  / 60.0   user_page JOINT-BEST=  2.00x

    Two changes, and the second one is the point. It reads
    `degrade_trips_at_s` — the trip the instrument ACTUALLY applies — rather
    than re-deriving `max(ratio, floor)` inline. The old inline form would have
    kept printing 4.95x after the ceiling shipped, i.e. it would have gone on
    passing while measuring an instrument that no longer exists.

    The residual 2.0x is deliberate and is NOT the same defect shrunk: it is
    `no_reader` (120s) over `user_page` (60s), which is the ordering we want. A
    spread of exactly 1.0 would mean the consumer classification stopped
    mattering at all.
    """
    trips = {
        b.task: (b.consumer, b.degrade_trips_at_s - b.p50_s)
        for b in PRE_MOVE_BASELINE
        if not b.censored
    }
    deltas = [d for _, d in trips.values()]
    spread = max(deltas) / min(deltas)

    assert spread < 2.5, trips
    assert spread > 1.5, (
        "the classes have collapsed onto one another — a spread near 1.0 means "
        "the measured consumer classification no longer changes the answer, "
        "which is #2116 and its second half both undone"
    )

    # THE INVERSION, asserted rather than described. Before the ceiling, the
    # user-facing beat needed the LARGEST absolute regression in the set.
    user_page = [d for c, d in trips.values() if c == "user_page"]
    assert user_page and max(user_page) <= min(deltas), trips


def test_the_route_and_the_offline_mirror_share_one_beat_payload_producer():
    """The drift this prevents ALREADY HAPPENED, in this cycle, on this change.

    `admin_celery.heavy_move_falsifier` and `scripts/falsifier_offline_mirror.py`
    each hand-built the per-beat dict, and the mirror's own docstring promised
    it mirrored the route "field for field". #2116 added six fields to the route
    and the mirror emitted `null` for every one of them on its first real run —
    while being read as the authoritative re-grade, because the verdict was
    right and a missing field renders exactly like an absent value (gotcha #53).
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    route = (root / "app" / "routes" / "admin_celery.py").read_text()
    mirror = (root / "scripts" / "falsifier_offline_mirror.py").read_text()

    for name, src in (("route", route), ("mirror", mirror)):
        assert '"beats": [beat_payload(b) for b in result.beats],' in src, (
            f"the {name} stopped using the shared producer — a second hand-built "
            "copy of this block is the defect this test exists for"
        )
        assert '"task": b.task,' not in src, (
            f"the {name} is hand-building a beat dict again"
        )


def test_beat_payload_carries_every_two_gate_field():
    """A reader must be able to audit a suppressed REVERT from the payload alone."""
    from app.utils.heavy_routing_falsifier import beat_payload

    baseline = BASELINE_BY_TASK[SI]
    verdict = grade_beat(
        baseline,
        _obs_from(REAL_2116_SAMPLES_S),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    payload = beat_payload(verdict)

    assert payload["verdict"] == "immaterial"
    assert payload["ratio_exceeded"] is True
    assert payload["consumer"] == "operator_panel"
    assert payload["materiality_floor_s"] == pytest.approx(60.0)
    assert payload["absolute_delta_s"] == pytest.approx(9.3, abs=0.05)
    assert payload["degrade_trips_at_s"] == pytest.approx(77.5)
    assert payload["floor_capped_by_censor"] is False
    assert payload["consumer_note"]


def test_the_user_facing_beat_is_watched_by_the_censor_not_the_ratio():
    """Why the residual asymmetry is survivable, made executable.

    `precompute_calibration_main`'s ratio trip (1.25 x 1187.8 = 1484.8 s) is
    ABOVE its own censor point (0.98 x 1500 = 1470 s), so a real degradation on
    the beat a page waits on shows up as saturation before it could ever show up
    as a ratio. That was true before this change and the floor must not alter
    it — the floor is 30 s there, far inside the gap.

    NOTE 2026-08-24: this test's TITLE is now historical. The censor is no
    longer what watches that beat — the 60 s `user_page` ceiling is, and it
    fires 222 s before saturation would. The three assertions below are facts
    about the ratio, the floor and the censor, all still true and all still
    worth pinning; what has changed is that "the residual is survivable because
    the censor eventually catches it" is no longer the argument being made. It
    was a consolation for the gap, and the gap is closed.
    """
    baseline = BASELINE_BY_TASK["app.tasks.precompute_calibration_main"]
    censor_at = CENSOR_FRACTION_OF_SOFT_LIMIT * baseline.effective_clamp_s
    assert baseline.p50_s * DEGRADE_P50_RATIO > censor_at
    assert baseline.p50_s + baseline.materiality_floor_s < censor_at
    assert baseline.consumer == "user_page"
