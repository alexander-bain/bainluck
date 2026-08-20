"""Pre-cert for the `warm-typeahead` publish-side gate — LAT-P073 (#1609, #1866).

The gate is not wired (see `app/utils/typeahead_publish_gate.py`). This suite is
the certification Fable's LAT-P073 item 2 requires *before* it may be: the gate
runs inside the beat process's scheduling loop, so a policy bug there stops every
beat in the system, and the policy is the half that can be proved on a bench.

Three properties carry the whole design, and each has an explicit test that is
meant to be mutated:

1. **FAIL OPEN** — an unknowable age must PUBLISH. A gate that failed closed would
   stop the warmer silently and read as a quiet period on every instrument.
2. **THE FUSE** — a stuck-fresh age must not suppress forever. Fail-open covers
   Redis erroring; only the fuse covers Redis lying consistently.
3. **PERIOD NEUTRALITY** — the gate must never remove a fire that could have
   started a pass. This is the property that distinguishes it from the 60 s beat
   LAT-P072 refused, and it is tested as a simulation over the whole measured wall
   range rather than as an assertion about one case.
"""

from __future__ import annotations

import math

import pytest

from app.utils.typeahead_publish_gate import (
    BEAT_INTERVAL_S,
    FUSE_MAX_CONSECUTIVE_SUPPRESSIONS,
    MIN_PASS_PERIOD_S,
    GateReason,
    predicted_publish_cut,
    should_publish,
    suppressed_fires_per_period,
)

# ---------------------------------------------------------------------------
# Mirror pins. A drifted mirror must be a red test, never a silently wrong gate.
# ---------------------------------------------------------------------------


def test_min_pass_period_mirror_matches_the_warmer():
    """The gate suppresses on the warmer's floor, so it must BE the warmer's floor.

    If these drift apart the gate starts suppressing fires the task would have
    accepted, which is the one thing the correctness argument forbids.
    """
    from app.tasks.typeahead_warmer import MIN_PASS_PERIOD_SECONDS

    assert MIN_PASS_PERIOD_S == MIN_PASS_PERIOD_SECONDS, (
        f"typeahead_warmer floor is {MIN_PASS_PERIOD_SECONDS}s but the publish "
        f"gate mirrors {MIN_PASS_PERIOD_S}s. The gate's whole safety argument is "
        "that a suppressed fire could not have started a pass; a drifted floor "
        "breaks exactly that."
    )


def test_beat_interval_mirror_matches_the_live_schedule():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-typeahead"]
    assert float(entry["schedule"]) == BEAT_INTERVAL_S, (
        f"live warm-typeahead beat is {entry['schedule']}s, gate mirrors "
        f"{BEAT_INTERVAL_S}s — the fuse limit is derived from this."
    )


def test_the_gate_is_not_wired_anywhere():
    """This module must stay import-isolated until it is deliberately shipped.

    LAT-P073 delivered the PLAN, not the wiring. If a later change imports this
    into `tasks/` or `routes/` it is shipping the gate, and shipping it requires
    the beat-schedule declaration and the kill switch from the plan doc — so this
    test is the tripwire that makes that a conscious act rather than a drift.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if "typeahead_publish_gate" in path.name:
            continue
        if "typeahead_publish_gate" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(root)))
    assert not offenders, (
        "typeahead_publish_gate is imported by "
        f"{offenders} — it is the UNWIRED pre-cert artifact. Wiring it is a "
        "beat_schedule_change and needs the kill switch + halt from "
        "docs/audits/latency/lat-p073-publish-gate-plan.md."
    )


# ---------------------------------------------------------------------------
# Property 1 — FAIL OPEN. Both directions, explicitly.
# ---------------------------------------------------------------------------


def test_unknown_age_publishes_this_is_the_fail_open_direction():
    """`None` means "could not establish the age". It must PUBLISH.

    Every upstream failure — Redis unreachable, key missing, value unparseable,
    negative delta from clock skew — is required to arrive here as `None`. The
    asymmetry that justifies it: suppressing wrongly empties the typeahead head
    (a MISS is 1.16-2.29 s p50 against a <150 ms budget, #1866) and is invisible;
    publishing wrongly costs one 10 ms no-op.
    """
    d = should_publish(age_since_last_pass_s=None)
    assert d.publish is True
    assert d.reason == GateReason.AGE_UNKNOWN


def test_unknown_age_publishes_even_deep_into_a_suppression_run():
    """Fail-open must outrank the suppression history, not be reset by it.

    A Redis that dies mid-run arrives here as `None` with a non-zero suppression
    count. If the count were consulted first, the gate would keep suppressing at
    exactly the moment it lost the ability to know better.
    """
    d = should_publish(age_since_last_pass_s=None, consecutive_suppressions=2)
    assert d.publish is True
    assert d.reason == GateReason.AGE_UNKNOWN


def test_a_fresh_age_does_suppress_so_fail_open_is_not_vacuous():
    """The counter-test. Without it, `return True` passes every fail-open test.

    A guard that only ever asserts "it published" cannot distinguish a working
    gate from a gate that is permanently off, and an always-open gate would be
    reported as certified while delivering none of the cut it was built for.
    """
    d = should_publish(age_since_last_pass_s=1.0)
    assert d.publish is False
    assert d.reason == GateReason.FLOOR_NOT_CLEAR


# ---------------------------------------------------------------------------
# Property 2 — the kill switch and the fuse.
# ---------------------------------------------------------------------------


def test_kill_switch_publishes_regardless_of_age():
    d = should_publish(age_since_last_pass_s=0.0, enabled=False)
    assert d.publish is True
    assert d.reason == GateReason.DISABLED


def test_kill_switch_outranks_a_garbage_age():
    """The switch must work when the input is worst, or it is not a kill switch.

    If the age were evaluated first, an input pathological enough to need the
    switch could be the very thing that stops it being reached.
    """
    for age in (0.0, -1.0, 1e9):
        d = should_publish(age_since_last_pass_s=age, enabled=False)
        assert d.publish is True, age
        assert d.reason == GateReason.DISABLED


def test_kill_switch_reports_disabled_even_when_the_age_is_unknown():
    """With the switch off, every decision must say so — including this one.

    Added because a mutation survived the first pass of this suite: demoting the
    kill-switch check below the fail-open check still publishes (both branches
    do), so nothing failed, and the only casualty was the reason label. That is
    not cosmetic. `age_unknown` means "Redis would not answer"; an operator who
    has just killed the gate and sees that in the logs will read a working switch
    as a broken Redis, and go looking for the wrong fault. The switch must be the
    outermost branch, and this is what holds it there.
    """
    d = should_publish(age_since_last_pass_s=None, enabled=False)
    assert d.publish is True
    assert d.reason == GateReason.DISABLED, (
        "with the kill switch off the gate reported "
        f"{d.reason!r}; the switch must outrank the fail-open branch so its "
        "own state is what gets logged."
    )


def test_fuse_limit_is_derived_from_the_floor_and_the_beat():
    assert FUSE_MAX_CONSECUTIVE_SUPPRESSIONS == math.ceil(
        MIN_PASS_PERIOD_S / BEAT_INTERVAL_S
    )
    assert FUSE_MAX_CONSECUTIVE_SUPPRESSIONS == 3


def test_a_permanently_fresh_age_cannot_suppress_forever():
    """The failure fail-open does NOT cover: Redis answering, and lying.

    A future-dated stamp from a clock-skewed dyno keeps the age below the floor
    indefinitely. Every individual decision is locally correct and the warmer
    stops for good — which on the adherence surface is indistinguishable from a
    healthy quiet period. Only a guard on the SEQUENCE catches it.
    """
    consecutive = 0
    published = 0
    for _ in range(40):
        d = should_publish(
            age_since_last_pass_s=0.0, consecutive_suppressions=consecutive
        )
        consecutive = d.consecutive_suppressions
        published += int(d.publish)
    assert published > 0, "a stuck-fresh age suppressed 40 consecutive fires"
    # One publish every (fuse + 1) fires: three suppressions, then a fire.
    assert published == 40 // (FUSE_MAX_CONSECUTIVE_SUPPRESSIONS + 1)


def test_fuse_never_fires_during_a_healthy_run():
    """A healthy suppression run is exactly the floor long, so it must not trip.

    If the fuse blew inside a normal cycle it would publish a message the floor
    guarantees is a no-op — harmless, but it would also mean the fuse could never
    be read as a fault signal.
    """
    consecutive = 0
    reasons = []
    for k in range(1, 6):  # ages 10, 20, 30, 40, 50 at a 10s beat
        d = should_publish(
            age_since_last_pass_s=k * BEAT_INTERVAL_S,
            consecutive_suppressions=consecutive,
        )
        consecutive = d.consecutive_suppressions
        reasons.append(d.reason)
    assert GateReason.FUSE not in reasons, reasons
    assert reasons == [
        GateReason.FLOOR_NOT_CLEAR,   # age 10
        GateReason.FLOOR_NOT_CLEAR,   # age 20
        GateReason.FLOOR_CLEAR,       # age 30 — the floor is >=, not >
        GateReason.FLOOR_CLEAR,
        GateReason.FLOOR_CLEAR,
    ]


def test_a_publish_resets_the_suppression_count():
    d = should_publish(age_since_last_pass_s=99.0, consecutive_suppressions=2)
    assert d.publish is True
    assert d.consecutive_suppressions == 0


# ---------------------------------------------------------------------------
# Property 3 — the floor boundary and period neutrality.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age,expect_publish",
    [
        (0.0, False),
        (29.999, False),
        (30.0, True),    # the warmer's own test is `< floor`, so 30 is admitted
        (30.001, True),
        (1e6, True),
    ],
)
def test_floor_boundary_matches_the_warmers_own_comparison(age, expect_publish):
    """The warmer suppresses on `since_last < MIN_PASS_PERIOD_SECONDS`.

    The gate must use the identical comparison. A gate that suppressed at exactly
    the floor would remove the first fire that could legitimately start a pass —
    one lost opportunity is +1 beat on the period, and at today's 50 s period that
    is 60 s, over the 45 s cliff.
    """
    assert should_publish(age_since_last_pass_s=age).publish is expect_publish


def test_the_gate_never_removes_a_fire_that_could_have_started_a_pass():
    """Period neutrality, simulated over the whole measured wall range.

    This is the property that separates this gate from the beat cut LAT-P072
    refused. Simulate a pass of wall W starting at t=0: the task's own gates admit
    a new pass only once BOTH the lock is free (t >= W) and the floor has cleared
    (t >= 30). The gate suppresses only while the age is under the floor, so the
    first fire it lets through must be no later than the first fire the task would
    have accepted — for every wall in 29.4-44.6 s (the measured range, its upper
    bound now the 44.6 s p95 read on 2026-08-19T23:30Z).
    """
    beat = BEAT_INTERVAL_S
    for tenths in range(294, 447):
        wall = tenths / 10.0
        fires = [k * beat for k in range(1, 200)]
        first_task_accept = next(
            t for t in fires if t >= wall and t >= MIN_PASS_PERIOD_S
        )
        consecutive = 0
        first_gate_publish_that_would_start = None
        for t in fires:
            d = should_publish(
                age_since_last_pass_s=t, consecutive_suppressions=consecutive
            )
            consecutive = d.consecutive_suppressions
            if d.publish and t >= wall and t >= MIN_PASS_PERIOD_S:
                first_gate_publish_that_would_start = t
                break
        assert first_gate_publish_that_would_start == first_task_accept, (
            f"wall={wall}s: the task would have started a pass at "
            f"t={first_task_accept}s but the gate's first usable publish is "
            f"t={first_gate_publish_that_would_start}s. The gate moved the pass "
            "period, which is the one thing it may not do."
        )


def test_next_check_is_never_longer_than_one_beat():
    """Hazard 3: a long `next_check` starves the firing opportunity.

    The gate would still be "correct" on every individual decision while quietly
    lengthening the period — the same failure mode as the 60 s beat, arrived at
    through the scheduler instead of the config.
    """
    for age in (0.0, 5.0, 15.0, 29.9, 30.0, 100.0):
        d = should_publish(age_since_last_pass_s=age)
        assert 0 < d.next_check_s <= BEAT_INTERVAL_S, (age, d)
    assert should_publish(age_since_last_pass_s=None).next_check_s <= BEAT_INTERVAL_S


# ---------------------------------------------------------------------------
# The payoff arithmetic — reported against publishes, never executions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period,expected_suppressed,expected_fires",
    [
        (40.0, 2, 4),
        (42.5, 2, 4),
        (50.0, 2, 5),
        (51.7, 2, 5),
        (30.0, 2, 3),
    ],
)
def test_suppressed_fires_per_period(period, expected_suppressed, expected_fires):
    assert suppressed_fires_per_period(period) == expected_suppressed
    assert int(period // BEAT_INTERVAL_S) == expected_fires


def test_predicted_cut_over_the_measured_period_range():
    """The registered prediction: 39-47 % of PUBLISHES over the measured period.

    Production measured the live pass period at 42.5-51.7 s (LAT-P062, two reads).
    Stated as a fraction of publishes because `deliveries` counts executions and
    the two differ by the `expires` discard — conflating them is how "~82 % of
    fires are no-ops" came to be staged as this gate's payoff.
    """
    lo = predicted_publish_cut(51.7)
    hi = predicted_publish_cut(42.5)
    assert 0.38 <= lo <= 0.40, lo
    assert 0.49 <= hi <= 0.51, hi
    assert lo < hi, "a longer period dilutes a fixed suppression count"


def test_predicted_cut_refuses_a_nonsense_period():
    with pytest.raises(ValueError):
        suppressed_fires_per_period(0.0)
    with pytest.raises(ValueError):
        suppressed_fires_per_period(50.0, beat_s=0.0)


def test_cut_is_never_reported_as_an_execution_cut():
    """Guard against the stale premise creeping back in.

    The queue staged this gate against "~82 % no-ops". Production says executions
    are ~40 % of publishes because `expires` discards the rest, so no publish-side
    cut can be worth 82 % of anything. If someone later "improves" the predicted
    cut past what suppression can arithmetically deliver, this fails.
    """
    for period in (30.0, 40.0, 42.5, 50.0, 51.7, 60.0):
        assert predicted_publish_cut(period) <= 2.0 / 3.0, period
