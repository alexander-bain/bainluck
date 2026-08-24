"""The per-consumer CEILING — #2116's un-taken second half, approved as
instrument work by Fable's LAT-P084 directive (2026-08-24, pasted and reviewed
by Alex).

WHAT THE FLOOR LEFT BEHIND, in the floor's own words:

    RESIDUAL, STATED: the floor is a MINIMUM, so the ratio still governs slow
    beats and the sensitivity spread narrows from 67x to ~5x — it does not
    INVERT. Making the user-facing beat the most sensitive needs a per-consumer
    CEILING as well.

That residual is the whole gap between the instrument and the decision it is
supposed to serve. The named decision is **"when does a user-facing regression
revert?"** and the floored instrument still answered it worst:

    precompute_calibration_main   user_page       pinned 1187.8s -> +297.0s to REVERT
    precompute_source_intelligence operator_panel pinned   17.5s -> + 60.0s to REVERT

The one beat a visitor waits on needed a **five-minute** median regression before
the instrument would say so, while an admin precompute needed one minute. The
floor fixed the sign of the absurdity (a 4.4 s move no longer reverts a grant)
without fixing its direction.

WHAT THE CEILING IS. A per-consumer ABSOLUTE cap, in seconds, keyed on the SAME
measured `BeatBaseline.consumer` classification the floor uses. A beat degrades
when EITHER

    (a) the ratio trips AND the delta clears the consumer's FLOOR   (the #2116 rule), OR
    (b) the delta clears the consumer's CEILING, whatever the ratio did.

So the trip point is bounded from both sides — Fable's "capped both directions":

    effective_trip_delta = min( max(ratio_trip, floor), ceiling )

and each consumer class therefore trips inside a CLOSED INTERVAL `[floor, ceiling]`
instead of on an open-ended ratio. Choosing non-overlapping intervals is what
finally orders the classes by how close the beat sits to a visitor.

🔴 WHAT THE CEILING IS NOT. A ceiling TIGHTENS a gate, which is the opposite
failure mode from the floor's, and it deserves the mirror-image of the floor's
three structural guards:

  1. a ceiling trip is NAMED (`ceiling_exceeded`, `absolute_ceiling_s`) and its
     reason says the ratio did not trip. "Degraded" that cannot be traced to a
     gate is how a tightened instrument gets quietly distrusted.
  2. the ceiling is CAPPED BY THE CENSOR, exactly as the floor is. A ceiling
     above a beat's remaining headroom is unreachable — the beat saturates
     first — which is a dead gate wearing a strict gate's clothes.
  3. the ceiling must sit STRICTLY ABOVE its own floor, or the `immaterial`
     band is empty and the ceiling has silently deleted #2116.

`test_the_residual_asymmetry_is_bounded_and_named` in the floor's own module
pins the 5x residual this change is allowed to move; it is re-derived there, not
here, so the two files cannot disagree about which number is current.
"""

from __future__ import annotations

import pytest

from app.utils.heavy_routing_falsifier import (
    BASELINE_BY_TASK,
    CONSUMER_CEILING_S,
    CONSUMER_FLOOR_S,
    DEGRADE_P50_RATIO,
    PRE_MOVE_BASELINE,
    ROUTING_CHANGE_AT_EPOCH,
    RUN_COUNTER_WINDOW_S,
    beat_payload,
    grade_beat,
)

AT_HORIZON = ROUTING_CHANGE_AT_EPOCH + RUN_COUNTER_WINDOW_S + 3600

CAL_MAIN = "app.tasks.precompute_calibration_main"
SI = "app.tasks.precompute_source_intelligence"


def _obs(p50_s: float, *, runs: int = 20, n: int = 20):
    return {
        "recent_durations_ms": [p50_s * 1000] * n,
        "successes_24h": runs,
        "failures_24h": 0,
    }


# ---------------------------------------------------------------------------
# 1. THE TABLE — same classification, both directions
# ---------------------------------------------------------------------------


def test_every_consumer_class_declares_a_ceiling_and_a_floor():
    """One classification, capped both directions (Fable's wording).

    A ceiling keyed on a DIFFERENT partition than the floor would be a second
    taste dial, which is the thing #2116 refused.
    """
    assert set(CONSUMER_CEILING_S) == set(CONSUMER_FLOOR_S)


def test_each_ceiling_sits_strictly_above_its_own_floor():
    """Otherwise `immaterial` is unreachable and the ceiling deletes #2116."""
    for consumer, ceiling in CONSUMER_CEILING_S.items():
        assert ceiling > CONSUMER_FLOOR_S[consumer], (
            f"{consumer}: ceiling {ceiling}s <= floor {CONSUMER_FLOOR_S[consumer]}s "
            "— the materiality band is empty, so the floor can never fire"
        )


def test_ceilings_are_ordered_by_how_close_the_consumer_sits_to_a_visitor():
    """user_page < operator_panel < no_reader, the SAME order as the floors."""
    assert (
        CONSUMER_CEILING_S["user_page"]
        < CONSUMER_CEILING_S["operator_panel"]
        < CONSUMER_CEILING_S["no_reader"]
    ), CONSUMER_CEILING_S


def test_the_class_trip_intervals_do_not_overlap():
    """The property that makes the ordering a fact about the SCHEME.

    Every `user_page` beat trips somewhere in [30, 60]; every `operator_panel`
    beat in [60, 120]; every `no_reader` beat in [120, 240]. Each class's
    ceiling IS the next looser class's floor, so the bands tile the axis
    contiguously: they touch at their endpoints, never cross, and leave no delta
    in nobody's band. That is what makes the ordering a property of the SCHEME
    rather than of today's seven pins — no future baseline can make an admin
    beat strictly more sensitive than a visitor-facing one.
    """
    order = ("user_page", "operator_panel", "no_reader")
    for tighter, looser in zip(order, order[1:]):
        assert CONSUMER_CEILING_S[tighter] <= CONSUMER_FLOOR_S[looser], (
            f"{tighter}'s ceiling ({CONSUMER_CEILING_S[tighter]}s) reaches past "
            f"{looser}'s floor ({CONSUMER_FLOOR_S[looser]}s) — the classes "
            "overlap, so their ordering depends on today's baselines"
        )


# ---------------------------------------------------------------------------
# 2. THE INVERSION — the reason this exists
# ---------------------------------------------------------------------------


def test_the_ceiling_degrades_a_user_page_beat_whose_ratio_never_tripped():
    """THE named decision, made answerable.

    `precompute_calibration_main` is pinned at 1187.8 s and feeds `/calibration`.
    A +90 s median regression is 1.08x — nowhere near the 1.25x ratio — and under
    the floored instrument it graded `hold`. A minute and a half of extra delay
    on the beat a public page waits on is exactly the thing the program exists to
    catch, and the ratio could not see it.
    """
    baseline = BASELINE_BY_TASK[CAL_MAIN]
    assert baseline.consumer == "user_page"

    observed = baseline.p50_s + 90.0
    ratio = observed / baseline.p50_s
    assert ratio < DEGRADE_P50_RATIO, "premise: the ratio must NOT trip here"

    verdict = grade_beat(baseline, _obs(observed), age_since_move_s=RUN_COUNTER_WINDOW_S + 3600)

    assert verdict.verdict == "degraded"
    assert verdict.ratio_exceeded is False
    assert verdict.ceiling_exceeded is True


def test_the_ceiling_trip_names_itself_in_the_reason():
    """A tightened gate must say WHICH gate fired, or it will be distrusted."""
    baseline = BASELINE_BY_TASK[CAL_MAIN]
    verdict = grade_beat(
        baseline,
        _obs(baseline.p50_s + 90.0),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )

    assert "ceiling" in verdict.reason.lower()
    assert "user_page" in verdict.reason
    # It must be explicit that the RATIO is not what fired, otherwise a reader
    # re-derives 1.08x, sees it under 1.25x, and concludes the panel is broken.
    assert "ratio" in verdict.reason.lower()
    assert verdict.absolute_ceiling_s == pytest.approx(CONSUMER_CEILING_S["user_page"])


def test_the_user_page_class_is_now_the_most_sensitive_on_the_real_pins():
    """The inversion, measured over the SEVEN PRODUCTION BASELINES.

    This is the assertion the floor's residual said it could not make. It reads
    the real pinned table, so it fails if a future baseline change re-inverts the
    instrument by the back door.
    """
    trips = {
        b.task: (b.consumer, b.degrade_trips_at_s - b.p50_s)
        for b in PRE_MOVE_BASELINE
        if not b.censored
    }
    user_page = [d for _, (c, d) in trips.items() if c == "user_page"]
    others = [d for _, (c, d) in trips.items() if c != "user_page"]

    assert user_page, "premise: at least one user_page beat is gradeable"
    assert max(user_page) <= min(others), (
        "a user-facing beat still needs a LARGER absolute regression than some "
        f"admin beat before the instrument reverts: {trips}"
    )


# ---------------------------------------------------------------------------
# 3. THE MIRROR-IMAGE GUARDS — a tightened gate can break too
# ---------------------------------------------------------------------------


def test_the_floor_still_governs_below_the_ceiling():
    """#2116 must survive its own second half.

    The +9.3 s reading #2116 was escalated on is still `immaterial`: it trips the
    ratio, misses the 60 s operator floor, and is nowhere near the 300 s operator
    ceiling. If the ceiling had swallowed the floor this would read `degraded`.
    """
    baseline = BASELINE_BY_TASK[SI]
    verdict = grade_beat(
        baseline,
        _obs(baseline.p50_s + 9.3),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    assert verdict.verdict == "immaterial"
    assert verdict.ceiling_exceeded is False


def test_an_improvement_never_trips_the_ceiling():
    """A beat that got FASTER is not a degradation, however large the move."""
    baseline = BASELINE_BY_TASK[CAL_MAIN]
    verdict = grade_beat(
        baseline,
        _obs(baseline.p50_s - 400.0),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    assert verdict.verdict == "hold"
    assert verdict.ceiling_exceeded is False


def test_the_ceiling_is_capped_by_the_censor_like_the_floor():
    """An unreachable ceiling is a dead gate wearing a strict gate's clothes.

    A beat whose remaining headroom to the censor is smaller than its declared
    ceiling would saturate before the ceiling could ever fire. Every baseline's
    APPLIED ceiling must therefore sit at or under its censor threshold.
    """
    for b in PRE_MOVE_BASELINE:
        if b.censored:
            # An already-saturated beat has NEGATIVE headroom and grades
            # `censored` before any delta is computed. Asserting a reachable
            # ceiling on it would be asserting a property of a beat that is not
            # graded on deltas at all.
            continue
        assert b.p50_s + b.absolute_ceiling_s <= b.censor_threshold_s + 1e-9, (
            f"{b.task}: ceiling trips at {b.p50_s + b.absolute_ceiling_s:.1f}s, "
            f"past its {b.censor_threshold_s:.1f}s censor threshold — unreachable"
        )


def test_a_capped_ceiling_says_so_rather_than_leaving_a_subtraction():
    """`ceiling_capped_by_censor` is the floor's `floor_capped_by_censor` twin."""
    for b in PRE_MOVE_BASELINE:
        assert b.ceiling_capped_by_censor == (
            b.absolute_ceiling_s < b.declared_absolute_ceiling_s
        )


def test_the_applied_ceiling_never_falls_below_the_applied_floor():
    """The censor caps BOTH; it must not cross them over.

    If a cap pushed the ceiling under the floor, `min(max(ratio, floor), ceiling)`
    would silently make the ceiling the only gate and delete the materiality band
    for that beat.
    """
    for b in PRE_MOVE_BASELINE:
        assert b.absolute_ceiling_s >= b.materiality_floor_s, (
            f"{b.task}: applied ceiling {b.absolute_ceiling_s:.1f}s is under its "
            f"applied floor {b.materiality_floor_s:.1f}s"
        )


# ---------------------------------------------------------------------------
# 4. THE PAYLOAD — auditable from the panel alone
# ---------------------------------------------------------------------------


def test_beat_payload_carries_the_ceiling_fields():
    """A reader must be able to audit a TIGHTENED revert from the payload alone,
    exactly as #2116 made a SUPPRESSED one auditable."""
    baseline = BASELINE_BY_TASK[CAL_MAIN]
    verdict = grade_beat(
        baseline,
        _obs(baseline.p50_s + 90.0),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    payload = beat_payload(verdict)

    assert payload["verdict"] == "degraded"
    assert payload["ceiling_exceeded"] is True
    assert payload["ratio_exceeded"] is False
    assert payload["absolute_ceiling_s"] == pytest.approx(60.0)
    assert payload["declared_absolute_ceiling_s"] == pytest.approx(60.0)
    assert payload["ceiling_capped_by_censor"] is False
    # The two-sided bound printed together: a reader should never have to hold
    # the floor in one hand and the ceiling in the other.
    assert payload["materiality_floor_s"] == pytest.approx(30.0)
    assert payload["degrade_trips_at_s"] == pytest.approx(baseline.p50_s + 60.0, abs=0.1)
