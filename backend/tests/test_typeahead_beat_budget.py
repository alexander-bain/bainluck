"""Guards for the `warm-typeahead` beat interval against the 45 s response-cache cliff.

LAT-P072 (#1609, #1866).

**Why this file exists at all.** Before it, the 45-second cliff lived only in prose —
a comment block in `tasks/typeahead_warmer.py` and a graded audit note. Fable's
LAT-P072 directive proposed moving the beat 10 s -> 60 s on arithmetic that is correct
about arrivals and simply has no way to see the cliff, because nothing in the tree
made the cliff checkable. A constant whose only defence is a paragraph will eventually
be changed by someone who did not read the paragraph; that is the trap ruling 076 banks
and this file closes it for this constant.

The load-bearing test is `test_live_beat_interval_is_not_unsafe`. Everything else pins
the inputs that test depends on, because a guard whose inputs can drift silently is
doctrine clause 2's failure — it moves with the thing it is meant to police.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.utils.typeahead_beat_budget import (
    CURRENT_BEAT_INTERVAL_S,
    MEASURED_WALL_MAX_S,
    MEASURED_WALL_MEDIAN_S,
    MEASURED_WALL_MIN_S,
    MIN_PASS_PERIOD_S,
    PROPOSED_W_MOVE_BEAT_S,
    RESPONSE_CACHE_TTL_S,
    SAFETY_MARGIN_S,
    BeatVerdict,
    background_arrivals_per_min,
    grade_beat_interval,
    quantised_period_s,
)


def _strip_comments(src: str) -> str:
    """Drop whole-line `#` comments so a guard cannot match its own explanation.

    LAT-P067 hit this class three times in one day (a substring "gin" inside
    `sa.BigInteger()`; a word-boundary hit on the comment explaining an ABSENT
    GIN index). The patterns below are specific enough that a partial mask is
    proportionate — they require a real call shape, not a bare number.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


# ---------------------------------------------------------------------------
# Mirror pins. Each asserts a mirrored constant still equals its real definition.
# ---------------------------------------------------------------------------


def test_response_cache_ttl_mirror_matches_the_route():
    """`RESPONSE_CACHE_TTL_S` must equal the TTL `/typeahead` actually writes.

    This is the cliff. If the route's TTL moves and this mirror does not, every
    verdict in the module becomes confidently wrong in whichever direction the
    drift went — so it is pinned to the source of the write, not to a docstring.
    """
    from app.routes.events import typeahead_search

    src = _strip_comments(inspect.getsource(typeahead_search))
    matches = re.findall(r"setex\(\s*_cache_key\s*,\s*(\d+)\s*,", src)

    assert len(matches) == 1, (
        "expected exactly one response-cache write in typeahead_search; found "
        f"{len(matches)}. If the route now writes its cache in more than one place, "
        "this guard must be taught which one is the head's TTL rather than silently "
        "picking the first."
    )
    assert int(matches[0]) == RESPONSE_CACHE_TTL_S, (
        f"typeahead response cache TTL is {matches[0]}s but "
        f"typeahead_beat_budget.RESPONSE_CACHE_TTL_S mirrors {RESPONSE_CACHE_TTL_S}s. "
        "The cliff moved; re-derive the beat grades before updating this mirror."
    )


def test_min_pass_period_mirror_matches_the_warmer():
    from app.tasks.typeahead_warmer import MIN_PASS_PERIOD_SECONDS

    assert MIN_PASS_PERIOD_S == MIN_PASS_PERIOD_SECONDS, (
        "the pass-start floor drifted from its mirror; the quantiser's binding "
        "term is wrong and every period below is understated or overstated"
    )


def test_current_beat_interval_mirror_matches_the_beat_schedule():
    """Pinned against the live celery config, not against the source text.

    The beat schedule is real configuration at import time, so asserting on the
    object is strictly stronger than grepping for `"schedule": 10.0`.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-typeahead"]
    assert float(entry["schedule"]) == float(CURRENT_BEAT_INTERVAL_S), (
        f"warm-typeahead beat is {entry['schedule']}s but the module mirrors "
        f"{CURRENT_BEAT_INTERVAL_S}s"
    )


# ---------------------------------------------------------------------------
# The load-bearing guard.
# ---------------------------------------------------------------------------


def test_live_beat_interval_is_not_unsafe():
    """The shipped beat must never sit where the MEDIAN pass empties the head.

    This is the guard that would have caught the 60 s proposal. It deliberately
    permits `MARGINAL` — today's 10 s value IS marginal (see the test below) and
    failing on it would make the guard red on arrival and therefore disabled
    within a week. It fails on `UNSAFE`, which is the qualitatively different
    state: the typical pass, not the tail, crossing the cliff.
    """
    from app.tasks import celery_app

    beat_s = float(celery_app.conf.beat_schedule["warm-typeahead"]["schedule"])
    grade = grade_beat_interval(beat_s)

    assert grade.verdict != BeatVerdict.UNSAFE, (
        f"warm-typeahead beat is {beat_s}s: {grade.reason}. "
        f"LAT-P063 measured 20 passes for 20 that a period over the "
        f"{RESPONSE_CACHE_TTL_S}s TTL loses cached entries (up to 39 of 40). "
        "Raising this beat to cut queue arrivals also quantises the pass period "
        "over the cliff — see app/utils/typeahead_beat_budget.py for the "
        "publish-side alternative that cuts arrivals without moving the period."
    )
    assert grade.verdict != BeatVerdict.REFUSED, (
        f"the live beat interval could not be graded at all: {grade.reason}"
    )


def test_the_proposed_60s_w_move_is_still_refused_on_the_newest_measurement():
    """🔴 A HOLE THE TTL RAISE OPENED, closed here deliberately.

    ⚠️ **REWRITTEN, LAT-P075, and the rewrite is the point — read it before
    touching it.** This test used to be one line: `grade_beat_interval(60.0)`
    against the defaults, asserting UNSAFE. Raising the TTL 45 -> 65 made that
    assertion FALSE, and the reason is uncomfortable: at the swapped worst wall
    (53.920 s) a 60 s beat quantises to a 60 s period, which now fits under a
    65 s TTL with zero margin, so **the grader began calling Fable's refused
    LAT-P072 W-move SAFE.**

    That is the TTL purchasing a beat move nobody ruled, through a constant that
    was already known to be a lower bound.

    🔴 **AND IT IS WORSE THAN ONE STALE CONSTANT, WHICH IS WHY THIS TEST IS LONG.**
    On the ring measurement taken the same day the 60 s beat quantises to **120 s**
    at the worst wall — but its MEDIAN wall (45.687 s) quantises to 60 s, which is
    under 65. `grade_beat_interval` reserves UNSAFE for crossing on the MEDIAN, so
    the honest verdict on the newest data is **MARGINAL**, not UNSAFE.

    That matters because `test_live_beat_interval_is_not_unsafe` — described in
    this module's own docstring as "the load-bearing test", the one written so
    that "a constant whose only defence is a paragraph" could not be changed by
    someone who did not read the paragraph — **fails only on UNSAFE**. Raising the
    TTL therefore moved the 60 s W-move out of the range that guard can see, on
    every wall triple in the module. The guard did not break; it stopped covering
    the case it was built for.

    Per Fable's standing rule of 2026-08-19, a green gate is evidence only if you
    can say what it would have to see to go red. `test_live_beat_interval_is_not_unsafe`
    would now go red only on a beat >= 70 s. **It would NOT go red on the 60 s move
    it was written to catch.** This test is that coverage, restored explicitly: it
    asserts the refusal on the quantity that actually refuses — the worst-wall
    period doubling to 120 s — rather than on a verdict label that no longer
    carries it.
    """
    from app.tasks import celery_app
    from app.utils.typeahead_beat_budget import (
        RING_WALL_MAX_S,
        RING_WALL_MEDIAN_S,
        RING_WALL_MIN_S,
    )

    on_ring = grade_beat_interval(
        PROPOSED_W_MOVE_BEAT_S,
        wall_median_s=RING_WALL_MEDIAN_S,
        wall_max_s=RING_WALL_MAX_S,
        wall_min_s=RING_WALL_MIN_S,
    )
    # THE REFUSAL, on the quantity rather than the label: at the newest measured
    # worst wall a 60 s beat puts the period at nearly twice the TTL.
    assert on_ring.period_at_worst_s == 120.0
    assert on_ring.crosses_cliff_on_worst is True
    assert on_ring.is_shippable is False
    assert on_ring.verdict == BeatVerdict.MARGINAL, (
        "if this ever reads UNSAFE again the median wall has crossed the TTL too, "
        "and the live-beat guard has regained coverage of the 60s move"
    )

    # The documented gap, asserted so it cannot be forgotten: the load-bearing
    # guard's own trigger does not fire on this beat.
    assert on_ring.verdict != BeatVerdict.UNSAFE

    # ⚠️ **THE 'STALE WALL' ARM OF THIS TEST IS GONE, LAT-P079** — and its
    # disappearance is the point. It used to read SAFE by exactly zero headroom
    # (period_at_worst 60.0 == TTL 65 - margin 5), because the defaults carried
    # a `MEASURED_WALL_MAX_S` of 53.920 that three consecutive cycles had
    # already proved too low. The constant is now the honest 66.365, so the
    # optimistic reading no longer exists to assert: the defaults and the ring
    # agree, and they agree on the pessimistic answer.
    on_defaults = grade_beat_interval(PROPOSED_W_MOVE_BEAT_S)
    assert on_defaults.period_at_worst_s == on_ring.period_at_worst_s == 120.0
    assert on_defaults.is_shippable is False

    # The live beat must remain nowhere near it.
    assert float(celery_app.conf.beat_schedule["warm-typeahead"]["schedule"]) == 10.0


def test_todays_10s_beat_is_MARGINAL_at_the_honest_wall_max():
    """🔴 **THE LIVE BEAT IS NO LONGER SAFE, AND THE ONLY THING THAT CHANGED IS
    THAT THE MEASUREMENT STOPPED BEING STALE.**

    ⚠️ **RENAMED TWICE NOW, and the history is the lesson.** It began as
    `test_todays_10s_beat_is_marginal_not_safe` (45 s TTL). LAT-P075 renamed it
    to `..._is_safe_at_the_ruled_ttl_and_marginal_on_the_ring` when the TTL went
    to 65 — SAFE on the defaults, MARGINAL on the ring, both asserted so neither
    could be quoted alone. LAT-P079 substituted the honest
    `MEASURED_WALL_MAX_S = 66.365` and the two halves collapsed into one: the
    defaults now ARE the ring, and the answer is MARGINAL.

    The quantity, which is what this pins:
    P(10) = 10 * ceil(66.365 / 10) = **70 s** against a **65 s** response TTL.
    A pass that outlasts the TTL keeps nothing warm, so the live beat spends
    part of every cycle rebuilding entries that have already expired.

    No beat interval fixes this — 66.365 s exceeds the TTL on its own, so every
    quantisation of it does. It is addressed on the TTL or on the pass, which is
    exactly what the old coherence assertion's failure message said to do.
    """
    from app.utils.typeahead_beat_budget import (
        RING_WALL_MAX_S,
        RING_WALL_MEDIAN_S,
        RING_WALL_MIN_S,
    )

    ruled = grade_beat_interval(CURRENT_BEAT_INTERVAL_S)
    assert ruled.verdict == BeatVerdict.MARGINAL
    assert ruled.is_shippable is False
    assert ruled.period_at_median_s == 50.0
    assert ruled.period_at_worst_s == 70.0
    assert ruled.crosses_cliff_on_worst is True

    # The ring read that used to be the pessimistic arm now agrees with the
    # defaults — same verdict, same period. There is no optimistic reading left.
    on_ring = grade_beat_interval(
        CURRENT_BEAT_INTERVAL_S,
        wall_median_s=RING_WALL_MEDIAN_S,
        wall_max_s=RING_WALL_MAX_S,
        wall_min_s=RING_WALL_MIN_S,
    )
    assert on_ring.verdict == ruled.verdict == BeatVerdict.MARGINAL
    assert on_ring.period_at_worst_s == 70.0


def test_the_arithmetically_fitting_22s_is_still_refused_as_marginal():
    """B=22 still does not reach SAFE — the numbers moved, the verdict did not.

    ⚠️ LAT-P075: the period figures here are wall-dependent and both inputs
    changed (TTL 45 -> 65, worst wall 42.6 -> 53.920). At the swapped wall,
    22 s quantises to 66 s, which is over the 65 s TTL — so this is now MARGINAL
    by *crossing* rather than by *insufficient headroom*. Either way it is not
    shippable, and the reason this test exists is unchanged: if `SAFETY_MARGIN_S`
    is ever lowered to make an arithmetically-tidy beat pass, this is where that
    decision becomes visible.
    """
    grade = grade_beat_interval(22.0)

    # LAT-P079: 88.0, not 66.0 — the worst wall went 53.920 -> 66.365 and 22 s
    # quantises it to four beats. The verdict is unchanged, which is the
    # property this test exists to hold: the numbers move every cycle and the
    # refusal does not.
    assert grade.period_at_worst_s == 88.0
    assert grade.crosses_cliff_on_worst is True
    assert grade.crosses_cliff_on_median is False
    assert grade.verdict == BeatVerdict.MARGINAL
    assert grade.is_shippable is False


# ---------------------------------------------------------------------------
# The quantiser itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "beat_s,wall_s,expected",
    [
        # LAT-P062's own measurement: a ~31 s pass inside a 30 s beat skips every
        # other fire and quantises to ~60 s. This is the case that motivated the
        # 30 -> 10 change, reproduced as a regression pin.
        (30.0, 31.0, 60.0),
        # The floor binds when the pass is faster than MIN_PASS_PERIOD_SECONDS.
        (10.0, 12.0, 30.0),
        (10.0, 29.4, 30.0),
        # Above the floor, the wall binds and rounds up to the next beat.
        (10.0, 32.0, 40.0),
        (10.0, 42.6, 50.0),
        # An exact multiple must not be rounded up a whole extra beat.
        (10.0, 40.0, 40.0),
        (22.0, 42.6, 44.0),
        (60.0, 29.4, 60.0),
    ],
)
def test_quantised_period_arithmetic(beat_s, wall_s, expected):
    assert quantised_period_s(beat_s, wall_s) == expected


def test_quantiser_rejects_nonsense_inputs():
    with pytest.raises(ValueError):
        quantised_period_s(0, 30.0)
    with pytest.raises(ValueError):
        quantised_period_s(-10.0, 30.0)
    with pytest.raises(ValueError):
        quantised_period_s(10.0, 0)


def test_arrival_rate_matches_the_measured_share():
    """6.00 msg/min at a 10 s beat is LAT-P071's measured 72.0 % of background inflow.

    Pinned because the arrival half of the W-move's case is CORRECT and must not
    be lost while the period half is being refused — the cut really would remove
    most of the queue's arrivals.
    """
    assert background_arrivals_per_min(10.0) == 6.0
    assert background_arrivals_per_min(60.0) == 1.0
    # The cut the directive is buying, in the units LAT-P071 measured.
    total_background_per_min = 8.33
    assert round(background_arrivals_per_min(10.0) / total_background_per_min, 3) == 0.720

    with pytest.raises(ValueError):
        background_arrivals_per_min(0)


# ---------------------------------------------------------------------------
# Refusals. `REFUSED` must be reachable and distinct from `UNSAFE`.
# ---------------------------------------------------------------------------


def test_missing_wall_measurements_refuse_rather_than_default():
    """Ruling 075: where the history cannot support a derivation, refuse visibly."""
    grade = grade_beat_interval(60.0, wall_median_s=None, wall_max_s=0, wall_min_s=0)

    assert grade.verdict == BeatVerdict.REFUSED
    assert grade.period_at_worst_s is None, (
        "a refusal must not also publish a number; a reader who sees a period "
        "will use it regardless of the verdict beside it"
    )


def test_incoherent_wall_range_refuses_rather_than_reordering():
    grade = grade_beat_interval(10.0, wall_median_s=50.0, wall_max_s=30.0, wall_min_s=20.0)

    assert grade.verdict == BeatVerdict.REFUSED
    assert "incoherent" in grade.reason


def test_refused_is_distinct_from_unsafe():
    """Doctrine clause 1, applied to this module's own output.

    A caller that branches on `verdict != SAFE` treats them alike; one that
    reports to a human must not. The two must never collapse to one value.
    """
    refused = grade_beat_interval(-1.0)
    # LAT-P075: 60.0 no longer reaches UNSAFE on the defaults (TTL 45 -> 65 put a
    # 60 s quantised period back under the cliff — see the W-move test above for
    # why that is a hole rather than good news). 70 s is unambiguously unsafe on
    # any of the three wall triples: it crosses on the MEDIAN, not just the tail.
    unsafe = grade_beat_interval(70.0)

    assert refused.verdict == BeatVerdict.REFUSED
    assert unsafe.verdict == BeatVerdict.UNSAFE
    assert unsafe.crosses_cliff_on_median is True
    assert refused.verdict != unsafe.verdict
    assert refused.is_shippable is False and unsafe.is_shippable is False


def test_measured_wall_range_is_internally_coherent():
    """The module's own provenance constants must satisfy min <= median <= max.

    Cheap, and it is the input every grade above depends on.
    """
    assert MEASURED_WALL_MIN_S <= MEASURED_WALL_MEDIAN_S <= MEASURED_WALL_MAX_S


def test_the_wall_max_exceeding_the_ttl_is_DERIVED_and_currently_TRUE():
    """🔴 **THE WRONG-GATE LESSON, APPLIED TO THIS MODULE'S OWN GUARD.**

    This replaces `assert MEASURED_WALL_MAX_S < RESPONSE_CACHE_TTL_S`, whose
    failure message read: *"if a single pass wall exceeds the response TTL, no
    beat interval can help and the cliff must be addressed on the TTL or the
    pass, not here"*. That assertion stayed green for three consecutive cycles
    **only because the constant it guarded was stale** — 53.920 s against a
    measured 61.282 and then 66.365. It was a label being satisfied by a number
    nobody had refreshed, which is precisely the defect LAT-P075 found in
    `test_live_beat_interval_is_not_unsafe`.

    So the condition is now COMPUTED from the two constants and asserted as a
    quantity. The module cannot hold it at a comfortable value without either
    lowering the measured wall (a lie) or raising the TTL (a decision).
    """
    from app.utils.typeahead_beat_budget import (
        WALL_MAX_EXCEEDS_RESPONSE_TTL,
        WALL_MAX_MARGIN_S,
        WALL_MAX_UPPER_ESTIMATE_S,
        wall_max_exceeds_response_ttl,
    )

    # 🔴 DERIVED means it VARIES WITH ITS INPUTS. Asserting
    # `flag == (MEASURED_WALL_MAX_S > RESPONSE_CACHE_TTL_S)` did NOT establish
    # that: a mutation hard-coding the flag to True survived it, because the
    # computed answer is also True. Only exercising the function off its
    # defaults can tell a derivation from a constant that happens to agree.
    assert wall_max_exceeds_response_ttl(70.0, 65.0) is True
    assert wall_max_exceeds_response_ttl(60.0, 65.0) is False
    assert wall_max_exceeds_response_ttl(65.0, 65.0) is False, "strict, not >="
    assert WALL_MAX_EXCEEDS_RESPONSE_TTL == wall_max_exceeds_response_ttl(
        MEASURED_WALL_MAX_S, RESPONSE_CACHE_TTL_S
    )

    assert WALL_MAX_EXCEEDS_RESPONSE_TTL is True, (
        "the honest wall max no longer exceeds the TTL — if that is a real "
        "improvement, say so with the measurement; if the constant was lowered "
        "to make this green, that is the fourth instance of the stale-constant "
        "defect this test was rewritten to end"
    )

    # A sampled maximum is a LOWER BOUND (ruling 075), so the constant carries
    # an explicit margin whose size is argued in the module, not assumed.
    assert WALL_MAX_MARGIN_S >= 5.08, (
        "the margin is smaller than the correction the LAST re-measurement "
        "needed (53.920 -> 61.282 -> 66.365), so it cannot be a bound on the next"
    )
    assert WALL_MAX_UPPER_ESTIMATE_S == MEASURED_WALL_MAX_S + WALL_MAX_MARGIN_S


# ---------------------------------------------------------------------------
# LAT-P075 — the message-expiry derivation, and the model behind it.
# ---------------------------------------------------------------------------


def test_the_expires_derivation_returns_the_lock_ttl():
    """`expires` derives from a CONSTANT, not from a sampled maximum.

    The whole point of deriving from `_LOCK_TTL_SECONDS` rather than from the
    worst observed wall is that the wall keeps moving and the lock TTL does not.
    This program has read a sampled maximum as a bound twice and been wrong both
    times — 42.6 s by 11.3 s, then 53.920 s by 7.36 s. A value derived from the
    sample would have to be revised on each of those reads; this one does not.
    """
    from app.utils.typeahead_beat_budget import LOCK_TTL_S, derive_message_expiry_s

    assert derive_message_expiry_s() == float(LOCK_TTL_S) == 120.0

    # It does not move when the wall measurement moves — which is the property.
    assert derive_message_expiry_s(worst_wall_s=61.282) == 120.0
    assert derive_message_expiry_s(worst_wall_s=42.6) == 120.0


def test_the_expires_derivation_refuses_a_lock_ttl_under_the_measured_wall():
    """A REFUSAL, never a smaller number — ruling 075's shape.

    If `_LOCK_TTL_SECONDS` were ever lowered under the measured worst wall plus
    margin, the lock could expire under a live pass and a second pass could start
    on top of the first. No message-expiry value derived from that is safe, so
    the derivation raises rather than quietly returning the smaller figure.

    **What this would have to see to go red:** `LOCK_TTL_S` dropped to 60 while
    the ring's worst wall stands at 61.282 s — i.e. someone "tidying" the lock
    TTL toward the beat period without reading the wall.
    """
    from app.utils.typeahead_beat_budget import derive_message_expiry_s

    with pytest.raises(ValueError, match="lock TTL"):
        derive_message_expiry_s(lock_ttl_s=60.0, worst_wall_s=61.282)

    for bad in ({"beat_s": 0}, {"worst_wall_s": 0}, {"lock_ttl_s": 0}, {"margin_s": -1}):
        with pytest.raises(ValueError):
            derive_message_expiry_s(**bad)


def test_the_executable_fire_fraction_reproduces_the_measured_loss():
    """The model is graded against production, not believed.

    This is the arithmetic that identified `expires: 10` as the period
    regression's mechanism. At the values the deployed pass ring reported on
    2026-08-20T02:5xZ — expires 10 s, wall p50 45.687 s, period p50 53.521 s —
    it predicts 32.7 % of beat fires can execute at all.

    Production's own counters, read from the same endpoint in the same window,
    said 30.5 %: 26 ringed passes plus 41 counted skips = 67 executions against
    ~220 fires over 2,196 s. A 2.2-point gap on a two-thirds loss is the model
    being right about the mechanism, and it is the reason the fix targets
    `expires` rather than the TTL.
    """
    from app.utils.typeahead_beat_budget import executable_fire_fraction

    predicted = executable_fire_fraction(expires_s=10, wall_s=45.687, period_s=53.521)
    assert 0.32 <= predicted <= 0.34, predicted

    measured = 67 / 220
    assert abs(predicted - measured) < 0.05, (
        f"model {predicted:.3f} vs production {measured:.3f} — if these have "
        f"diverged, the mechanism attribution behind the expires fix is stale"
    )

    # And the repair takes it to full coverage: once a message outlives the pass,
    # every fire executes — as a pass, or as a <=71ms lock skip.
    repaired = executable_fire_fraction(expires_s=120, wall_s=45.687, period_s=53.521)
    assert repaired == 1.0


def test_the_wired_expires_matches_the_derivation():
    """The mirror that makes the derivation load-bearing rather than decorative.

    A derivation nothing consults is a comment. This asserts the beat schedule
    actually carries the derived number, so the two cannot drift.
    """
    from app.tasks import _EXPIRING_WARMER_BEATS, celery_app
    from app.utils.typeahead_beat_budget import derive_message_expiry_s

    assert _EXPIRING_WARMER_BEATS["warm-typeahead"] == derive_message_expiry_s()
    effective = celery_app.conf.beat_schedule["warm-typeahead"]["options"]["expires"]
    assert effective == derive_message_expiry_s()


def test_ring_wall_range_is_internally_coherent():
    """min <= median <= p95 <= max, on the newer measurement too."""
    from app.utils.typeahead_beat_budget import (
        RING_WALL_MAX_S,
        RING_WALL_MEDIAN_S,
        RING_WALL_MIN_S,
        RING_WALL_P95_S,
        RING_WALL_SAMPLE_PASSES,
    )

    assert RING_WALL_MIN_S <= RING_WALL_MEDIAN_S <= RING_WALL_P95_S <= RING_WALL_MAX_S
    assert RING_WALL_SAMPLE_PASSES > 0


# ---------------------------------------------------------------------------
# LAT-P075 — the period regression's cause, pinned to its real inputs.
# ---------------------------------------------------------------------------


def test_background_concurrency_mirror_matches_the_procfile():
    """The capacity number is mirrored, so the finding cannot rot silently.

    `background_slot_occupancy()` argues that the period tail is a capacity fact
    about `worker-background`. That argument is only as good as its input, and
    the input lives in a file this module cannot import. So it is pinned to the
    Procfile text — if someone raises the concurrency (which is one of the
    proposed remedies), this goes red and forces the finding to be re-derived
    rather than left standing on a number that changed underneath it.
    """
    import pathlib

    from app.utils.typeahead_beat_budget import BACKGROUND_WORKER_CONCURRENCY

    procfile = pathlib.Path(__file__).resolve().parents[1] / "Procfile"
    assert procfile.is_file(), f"Procfile not found at {procfile}"
    line = next(
        (
            ln
            for ln in procfile.read_text().splitlines()
            if ln.startswith("worker-background:")
        ),
        None,
    )
    assert line, "no worker-background entry in the Procfile"

    found = re.search(r"--concurrency=(\d+)", line)
    assert found, f"worker-background has no --concurrency: {line}"
    assert int(found.group(1)) == BACKGROUND_WORKER_CONCURRENCY, (
        f"worker-background runs --concurrency={found.group(1)} but "
        f"typeahead_beat_budget mirrors {BACKGROUND_WORKER_CONCURRENCY}. If the "
        f"concurrency was raised, re-derive background_slot_occupancy() — that "
        f"change IS the proposed period remedy and its effect must be graded."
    )


def test_the_warmer_now_owns_most_of_one_background_slot():
    """The period regression, stated as the arithmetic that produces it.

    At LAT-P062 the warmer held 32.0/50 = 64 % of one of `worker-background`'s
    two slots. At the ring median it holds ~91 %. The beat never changed; the
    wall did. That is why raising the beat, the TTL, or the message expiry cannot
    fix the period — none of them gives the queue back a slot.

    **What this would have to see to go red:** the pass wall coming back down
    (a `WARM_CONCURRENCY` raise, a smaller head), or the concurrency going up.
    Both are the remedy, so a red here is good news that must be graded, not a
    number to re-baseline.
    """
    from app.utils.typeahead_beat_budget import (
        BACKGROUND_WORKER_CONCURRENCY,
        RING_WALL_MEDIAN_S,
        background_slot_occupancy,
        free_background_slots,
    )

    now = background_slot_occupancy()
    then = background_slot_occupancy(wall_s=32.0, period_s=50.0)

    assert 0.88 <= now <= 0.95, now
    assert 0.60 <= then <= 0.70, then
    assert now > then

    # The load-bearing consequence, stated as what it actually is. An earlier
    # draft asserted `free_background_slots() < 1.0` and that is simply FALSE —
    # 2 - 0.91 = 1.09. The starvation is not a shortage of slot COUNT; it is
    # FIFO POSITION. `background` is one shared queue with no priority, so when
    # the warmer's pass ends and releases its slot, that slot goes to whichever
    # of the other 56 beats' messages is at the head of the list — not back to
    # the warmer. Behind one long co-tenant the warmer waits that long, with
    # 1.09 slots "free" the whole time.
    #
    # ⚠️ LAT-P076: this comment used to name `rebuild_typeahead_index` here.
    # It routes to `heavy` and is not a co-tenant at all — see
    # `test_rebuild_typeahead_index_is_on_heavy_and_cannot_starve_the_warmer`.
    # The observed starvers are `discover_events` and `warm_event_concepts`.
    #
    # So the number that matters is how little slack there is: the warmer alone
    # consumes MORE THAN HALF of a two-slot pool, which is what makes ordinary
    # co-tenant bursts (the :00/:15/:30/:45 backfill clusters) able to push it
    # into a multi-minute wait.
    assert free_background_slots() < 1.1
    assert BACKGROUND_WORKER_CONCURRENCY == 2
    assert now > 0.5, (
        "the warmer holds more than half of one slot; below that the co-tenancy "
        "argument weakens and the tail needs another explanation"
    )
    assert free_background_slots(concurrency=3) > free_background_slots(), (
        "one more slot is the smallest capacity remedy — stated here so the "
        "proposal has a number attached to it"
    )
    assert RING_WALL_MEDIAN_S > 32.0


def test_the_expires_fix_does_not_claim_a_period_repair():
    """🔴 A CORRECTION, pinned so it cannot be un-learned.

    An earlier draft of this cycle shipped `expires: 10 -> 120` described as
    "THE PERIOD-REGRESSION REPAIR", on #2014's 4/4 correlation plus a real
    two-thirds discard. Continued sampling separated the two claims: during a
    stall the broker pile drains on the first free slot whether the older
    messages were discarded or executed, so the next pass starts at the same
    instant either way. The discard is real; the period repair was not.

    This test pins the honest boundary. The expiry change buys full delivery, and
    at most one beat interval off the period — not the 192.9 s p95 tail.
    """
    from app.utils.typeahead_beat_budget import (
        CURRENT_BEAT_INTERVAL_S,
        executable_fire_fraction,
    )

    before = executable_fire_fraction(expires_s=10, wall_s=45.687, period_s=53.521)
    after = executable_fire_fraction(expires_s=120, wall_s=45.687, period_s=53.521)

    # What it DOES buy: delivery goes from two-thirds lost to none lost.
    assert before < 0.35 and after == 1.0

    # What it does NOT buy: the tail. The most the expiry can remove from a
    # period is one beat interval — the wait for the next fire after the lock
    # releases — which is nowhere near the 192.9s p95 or the 326.3s max.
    measured_p95_period_s = 192.905
    assert CURRENT_BEAT_INTERVAL_S < 0.1 * measured_p95_period_s, (
        "if one beat interval ever approached the period tail, the expiry change "
        "could plausibly explain it and this correction would need revisiting"
    )


# ---------------------------------------------------------------------------
# LAT-P076 — the two facts LAT-P075 got wrong about this queue, pinned so the
# next window inherits the correction rather than the claim.
# ---------------------------------------------------------------------------


def test_rebuild_typeahead_index_is_on_heavy_and_cannot_starve_the_warmer():
    """LAT-P075 named the wrong starver, and named it in three places.

    Its §3 wrote "Behind one 150 s `rebuild_typeahead_index` (p95 150,062 ms)
    ... the warmer waits that long", and the module docstring and this suite's
    own comment repeated it. `rebuild_typeahead_index` routes to **`heavy`** —
    both in `task_routes` and in its own beat `options` — so it contends for
    `worker-heavy`'s two slots and never for `worker-background`'s. It cannot
    delay the warmer by one millisecond.

    This matters beyond tidiness: a named cause is what a future window acts
    on. "Move `rebuild_typeahead_index` off `background`" is a plausible-looking
    remedy that would have changed nothing, and it is exactly the remedy the
    prose invited.

    **What this would have to see to go red:** anyone routing
    `rebuild_typeahead_index` to `background` (which would make the original
    claim true and is a real proposal someone might make), or deleting its
    explicit queue so it falls through `task_default_queue` — which IS
    `background`, so a deletion silently creates the co-tenancy this test
    denies. The fall-through is the live hazard, not the explicit re-route.
    """
    from app.tasks import celery_app

    conf = celery_app.conf
    entry = conf.beat_schedule["rebuild-typeahead-index"]
    assert entry["task"] == "app.tasks.rebuild_typeahead_index"

    # Both routing surfaces must say `heavy`. Beat options override
    # `task_routes`, so agreeing is not redundant — a disagreement means the
    # queue depends on whether the task was published by beat or by hand.
    assert entry["options"]["queue"] == "heavy", entry["options"]
    assert conf.task_routes["app.tasks.rebuild_typeahead_index"]["queue"] == "heavy"

    # And the fall-through hazard, stated as the reason the assertion above is
    # not enough on its own.
    assert conf.task_default_queue == "background", (
        "if the default queue is `background`, then DELETING a queue option is "
        "the same as routing to `background` — which is how 45 beats got here"
    )


def test_the_background_queue_carries_105_beats_and_45_are_fall_through():
    """60 beats NAME `background`. The queue carries 105.

    🔴 **MERGE RE-DERIVATION (Integrator INT-139): 104 (ux-122 fold) x 103
    (queue 419) -> 105, explicit 60.** Both lanes re-derived against a master
    that did not yet carry the other, so NEITHER number was the merged one.
    Obtained by running the census below over the merged `beat_schedule`, never
    by reconciling the two numbers arithmetically (#1910) — `104 + 103 - 102`
    happens to equal 105 here, which is luck, not a method. The fall-through
    half is UNMOVED at **45**: all four contested beats
    (`warm-search-head`, `refresh-registered-tournament-prices`,
    `sync-tournament-results`, `settlement-capture-sweep-nightly`) name their
    queue explicitly.

    🔴 **RE-DERIVED at authority/015 (2026-09-04, #2867 / D50 step 3): 115 -> 117,
    explicit 70 -> 72.** Two beats, one per sport — `stamp-nba-statpal-fixtures-hourly`
    (`crontab(minute=17)`) and `stamp-nhl-statpal-fixtures-hourly`
    (`crontab(minute=19)`) — both with an explicit `options={"queue": "background"}`.
    RE-DERIVED by RUNNING the census below over the assembled schedule, which
    printed `explicit 72 implicit 45 total 117`, never by adding two to 115
    (#1910). The fall-through half is UNMOVED at **45** — both beats name their
    queue rather than defaulting into it, the benign direction this docstring
    reserves. The cost declaration (two HTTP reads and one bounded candidate
    query per sport per pass, and why `background`) is on `BACKGROUND_BEAT_COUNT`.

    🔴 **RE-DERIVED at authority/017 (2026-09-04, #2867 / D50 step 5): 117 → 118,
    explicit 72 → 73.** One beat — `stamp-mlb-statpal-fixtures-hourly`
    (`crontab(minute=21)`) — with an explicit `options={"queue": "background"}`.
    RE-DERIVED by RUNNING the census below over the assembled schedule, which
    printed `explicit 73 implicit 45 total 118`, never by adding one to 117
    (#1910). The fall-through half is UNMOVED at **45**. The cost declaration
    (why MLB's pass is CHEAPER than its two siblings' — a rolling ~17-day window
    of 227 games rather than a 1206/1404-game season — and why `background`) is
    on `BACKGROUND_BEAT_COUNT`.

    **And this guard did its job on the way in, for the second time.** The beat
    was pushed without the re-derivation and CI backend shard 2 went red on
    `73 != 72`. The lane's focused local run under D40 had missed it because this
    file is named after `typeahead`: a `-k` band named after the feature being
    changed does not select the census that every beat moves. That is the
    reserved red behaviour working, not a break — and it is the argument for the
    guard being a SPLIT assertion in a file nobody would think to grep.

    🔴 **RE-DERIVED at LAT-P137 (2026-08-30): 107 -> 108, explicit 62 -> 63.**
    This lane added `warm-futures-categories` (`crontab(minute="*/5")`, the
    producer for the Search page's category census) with an explicit
    `options={"queue": "background"}`. RE-DERIVED by running the census below
    over the assembled schedule and printing all three numbers, never by adding
    one to the old number (#1910). The fall-through half is UNMOVED at **45** —
    the new beat named its queue rather than defaulting into it, which is the
    benign direction this docstring reserves. The cost declaration (one 1.37-
    1.59 s build per 5 min = ~0.46 % of a slot-day, and why `background` rather
    than `realtime`) is on `BACKGROUND_BEAT_COUNT`.
    🔴 **RE-DERIVED at lane1/057 STEP 0 (2026-09-02): 110 -> 111, explicit
    65 -> 66.** This lane added `sync-tennis-from-espn` (`crontab(minute="*/10")`,
    the ESPN authority channel for tennis — the sport that had none) with an
    explicit `options={"queue": "background"}`. RE-DERIVED by running the census
    below over the assembled schedule and printing all three numbers, never by
    adding one to the old number (#1910). The fall-through half is UNMOVED at
    **45** — the new beat names its queue rather than defaulting into it, the
    benign direction this docstring reserves. The cadence argument (why `*/10`
    and why a crontab rather than the 180 s interval that would have joined
    `BACKGROUND_INTERVAL_FLOOR`) is on the beat entry itself.


    🔴 **RE-DERIVED at queue 419 (2026-08-26, #2077): 102 -> 103, explicit
    57 -> 58.** This lane added `settlement-capture-sweep-nightly`
    (`crontab(minute=31, hour=10)`, the nightly settlement-capture sweep) with an
    explicit `options={"queue": "background"}`. RE-DERIVED by running the census
    below over the assembled schedule and printing all three numbers, never by
    adding one to the old number (#1910). The fall-through half is UNMOVED at
    **45** — the new beat named its queue rather than defaulting into it, which is
    the benign direction this docstring reserves. The cost declaration (one fire a
    night, 780 s worst case = ~0.9 % of a slot-day, and why `background` rather
    than `heavy`) is on `BACKGROUND_BEAT_COUNT`.

    🔴 **RE-DERIVED at LAT-P138: 107 → 108, explicit 62 → 63.**
    `warm-prop-families` (`crontab(minute=43, hour="*/6")`, the producer for the
    team prop-families tier) with an explicit `options={"queue": "background"}`.
    RE-DERIVED by running the census below and printing all three numbers, never
    by adding one (#1910). Fall-through UNMOVED at 45 — the new beat named its
    queue. ⚠️ `program/latency-123` is unmerged and moves the same constant to
    108 for a DIFFERENT beat; the merged answer is 109 and must be re-derived
    at the merge rather than taken from either branch.

    🔴 **RE-DERIVED AT THE MERGE (ux-121 x LAT-P090).** Two lanes re-derived
    this from the same base of 101 without knowing about each other: LAT-P090
    added `warm-search-head` and got 102; UX-P139 added
    `refresh-registered-tournament-prices` and `sync-tournament-results` and got
    103. The merged schedule carries all three. The number here was obtained by
    RUNNING the census below over the merged schedule — not by adding 1 and 2,
    which is the arithmetic #1910 forbids and which would have been right only
    by luck. The fall-through half is UNMOVED at 45, which is the half this test
    exists to watch: all three new beats named their queue explicitly. The cost
    declaration is on `BACKGROUND_BEAT_COUNT` in
    `app/utils/typeahead_beat_budget.py`.

    🔴 **RE-DERIVED at ruling 110 (LAT-P077): was 57 explicit / 102 total.**
    `backfill_market_shapes` and `precompute_backfill_progress` moved to
    `heavy` under the scoped two-task exception, so the EXPLICIT half fell
    57 -> 55 and the total 102 -> 100. This test going red on that move is the
    behaviour reserved below, not a break — and the count was RE-DERIVED from
    the config rather than adjusted by a delta (#1910).

    The fall-through half did NOT move, and that is the point: 45 beats are
    still here because nobody chose a queue. Ruling 110 addressed two
    explicitly-routed occupants; it did nothing about the default.

    The other 45 arrive through `task_default_queue = "background"` without
    naming anything, and they include the heaviest work on the queue:
    `turbo_collapse_futures` (mean 1,859 s), `backfill_winners` (868 s),
    `poll_polymarket_markets` (304 s), `discover_events`.

    The distinction is the whole remedy question. A queue that 57 tasks were
    assigned to is a sizing problem. A queue that 45 further tasks landed on
    because nobody chose a queue is a DEFAULT problem, and the cheapest lever
    is to stop the fall-through rather than to buy slots for it.

    **What this would have to see to go red:** the explicit/implicit split
    moving in either direction — someone giving the 45 an explicit home (good,
    and the count should then be re-derived), or new beats landing on the
    default (bad, and this is the only test that would notice). It is
    deliberately asserted as a SPLIT and not just a total, because a total
    holds constant while 45 becomes 60 and 57 becomes 42.

    🔴 **RE-DERIVED at LAT-P193 (2026-09-01, #2614): 109 → 110, explicit
    64 → 65.** This lane added `backfill-image-dimensions`
    (`crontab(minute=5, hour="*/6")`, the true-pixel-dimension backfill) with an
    explicit `options={"queue": "background"}`. RE-DERIVED by running the census
    below over the assembled schedule and printing all three numbers, never by
    adding one to the old number (#1910). The fall-through half is UNMOVED at
    **45** — the new beat named its queue rather than defaulting into it, which
    is the benign direction this docstring reserves. The cost declaration (a
    bounded 150-URL pass that drains in ~10 days and then returns `no_work`
    forever, and why `background` rather than `heavy`) is on
    `BACKGROUND_BEAT_COUNT`.

    🔴 **RE-DERIVED AT THE MERGE (live/047 → master, 2026-09-03): 111 → 112,
    explicit 66 → 67.** live/035 (`backfill-thin-event-charts`) and lane1/057
    (`sync-tennis-from-espn`) each moved the count 110 → 111 for a different
    beat, and git auto-merged THIS assertion — the two branches wrote the same
    numbers here — while the constant conflicted. That is the shape of the trap
    (#1910, INT-158): the guard goes red pointing at the constant rather than at
    the merge. Both numbers were re-derived by RUNNING the census below over the
    assembled schedule on the merged tree, never by adding. Fall-through stays
    at **45**.

    🔴 **RE-DERIVED at CAL-P998 / D47 (2026-09-04, #2771): 112 → 113, explicit
    67 → 68.** This lane added `sweep-kalshi-resolution-window`
    (`crontab(minute=20, hour=4)`, the nightly Kalshi resolution-date sweep) with
    an explicit `options={"queue": "background"}`. RE-DERIVED by running the
    census below over the assembled schedule and printing all three numbers —
    `explicit 68 implicit 45 total 113` — never by adding one to the old number
    (#1910). The fall-through half is UNMOVED at **45**, the benign direction
    this docstring reserves. The cost declaration (one fire a night, ~120 s =
    ~0.14 % of a slot-day, and why `background` rather than `heavy`) is on
    `BACKGROUND_BEAT_COUNT`.

    **And this guard did its job on the way in.** The beat shipped without the
    re-derivation, and this assertion is what caught it — as a red CI backend
    shard 1 reading `68 != 67`, found by CERT-863 rather than by the lane that
    added the beat. That is the reserved red behaviour working, not a break.

    🔴 **RE-DERIVED AT THE REBASE (authority/009 → master, 2026-09-04): 113 →
    114, explicit 68 → 69.** `stamp-nfl-statpal-fixtures-hourly` (#2867, D50)
    names `background` explicitly, so the fall-through half is UNMOVED at **45**
    — the benign direction this docstring reserves.

    This is INT-158's collision for the FOURTH time: CAL-P998 and authority/009
    each moved the constant 112 → 113 for a different beat, each correct against
    its own base, and 113 is the one number wrong on the composed tree. Note what
    that does to THIS file specifically — both branches edited the two assertions
    below to the identical `68` and `113`. The constant conflicted loudly and
    the guard did not, so the assertion is the half that can auto-merge into a
    number no longer true of the tree it is asserting about. Obtained by RUNNING
    the census below on the rebased tree, which printed `explicit 69 implicit 45
    total 114`, never by adding one (#1910). The cost declaration is on
    `BACKGROUND_BEAT_COUNT`.

    🔴 **RE-DERIVED at lane1b/053 (2026-09-06, #2927 Phase 2): 118 → 119,
    explicit 73 → 74.** `assemble-containers-hourly` (`crontab(minute=47)`, the
    event-container assembly pass) names `background` explicitly, so the
    fall-through half is UNMOVED at **45**. Obtained by RUNNING the census below
    over the assembled schedule, which printed `explicit 74 implicit 45 total
    119`, never by adding one (#1910). The cost declaration is on
    `BACKGROUND_BEAT_COUNT`.

    **This guard did its job again, and the MLB stamper's note above called the
    shot.** That note says the census "lives nowhere near the words a StatPal
    change would think to select". Substitute containers and it is the same
    sentence: the lane's focused run (D40) selected on `receipt or container`,
    this file is named after `typeahead`, and the beat shipped without the
    re-derivation. It went red in CI backend shard 1 on `74 != 73` — the second
    time in three days, and the second time the `-k` band was named after the
    feature rather than after what the change touches. **A change that adds a
    `beat_schedule` entry runs THIS file, whatever the change is about.**
    """
    from app.tasks import celery_app
    from app.utils.typeahead_beat_budget import BACKGROUND_BEAT_COUNT

    conf = celery_app.conf
    explicit = implicit = 0
    for entry in conf.beat_schedule.values():
        task = entry.get("task")
        named = (entry.get("options") or {}).get("queue") or (
            conf.task_routes.get(task) or {}
        ).get("queue")
        if named == "background":
            explicit += 1
        elif named is None and conf.task_default_queue == "background":
            implicit += 1

    assert explicit == 74, f"explicitly-routed background beats moved: {explicit}"
    assert implicit == 45, f"default-queue fall-through moved: {implicit}"
    assert explicit + implicit == BACKGROUND_BEAT_COUNT == 119

    # ruling 110's two movers are OFF this queue and ON heavy — asserted here
    # too, so a silent revert cannot restore the count without being noticed.
    from app.utils.heavy_routing_falsifier import HEAVY_MOVE_EXCEPTION

    for task in HEAVY_MOVE_EXCEPTION:
        assert conf.task_routes[task] == {"queue": "heavy"}


def test_the_demand_model_says_oversubscribed_and_the_census_says_90_percent():
    """The MODEL's rho >= 1 under mean AND p95 — and a direct census disagrees.

    🔴 **This test was renamed after it was first committed, and the rename is
    the finding.** It was `..._is_oversubscribed_on_BOTH_duration_estimators`,
    asserting a claim about the QUEUE. It only ever asserted a property of two
    CONSTANTS, and a direct 26-sample occupancy census of the same queue
    measured **90 % of slot-observations busy** — five idle, which a queue truly
    at rho >= 1 does not produce. The post-deploy period (p50 40.5-45.2 s, p95
    74.9-82.4 s) agrees with the census, not the model.

    So the model overstates, most likely because it prices every scheduled fire
    at a full run while many background beats no-op or self-gate cheaply. The
    constants are still the right input to a capacity decision — a lever should
    clear the UPPER bracket to be safe — but the name promised evidence about
    reality that the arithmetic could not carry, and the census then contradicted
    it. Renamed to say what it pins.

    A queue at rho >= 1.0 has no steady state: the backlog grows until
    something sheds it. On `background` the thing that sheds it is `expires`
    dropping warmer messages, which is why the discard was measurable at 30.5 %
    and why raising `expires` made saturation *readable* without making it
    smaller.

    Both bracket ends are asserted because either alone is arguable. The p95 sum
    prices every run at its slowest; the mean sum is the lower bound.

    **What this would have to see to go red:** the mean-estimator rho dropping
    below 1.0 at concurrency 2 — which is the remedy landing, and must be
    graded as such rather than re-baselined. It would also red if someone
    edited the measured constants without re-measuring, which is the failure
    this program keeps having (42.6 -> 53.9 -> 61.3).
    """
    from app.utils.typeahead_beat_budget import (
        BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H,
        BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H,
        background_utilisation,
    )

    lo = background_utilisation(
        demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H
    )
    hi = background_utilisation(
        demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H
    )

    assert lo >= 1.0, f"mean-estimator rho fell below 1.0 ({lo:.2f}) — re-grade"
    assert hi >= 1.0, f"p95-estimator rho fell below 1.0 ({hi:.2f}) — re-grade"
    assert 1.05 <= lo <= 1.15, lo
    assert 1.45 <= hi <= 1.55, hi

    # The queue is over capacity even with the warmer removed entirely, on the
    # upper estimator. This is why moving the warmer elsewhere RESCUES THE
    # WARMER but does not repair `background` — a distinction the remedy table
    # has to carry, because two of the four levers only do the former.
    ex = background_utilisation(
        demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H,
        include_warmer=False,
    )
    assert ex >= 1.0, ex


def test_R4_is_not_supported_by_measurement_at_concurrency_3():
    """LAT-P075 predicted period p95 < 90 s at concurrency 3. Measurement does
    not support that, and this test exists to stop it being cited as if it did.

    At three slots the utilisation bracket is 0.72 .. 1.00. The upper end is
    exactly capacity, which is still no steady state. So R4 sits on the
    assumption that the mean estimator is the right one — an assumption nobody
    has tested.

    This is a refusal to predict, not a prediction of failure. The point is
    that "concurrency 3 fixes it" must not be quoted as measured.

    **What this would have to see to go red:** the p95-estimator rho at
    concurrency 3 dropping clear of 1.0, at which point R4 IS supported and
    this test should be replaced by one that says so.
    """
    from app.utils.typeahead_beat_budget import (
        BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H,
        BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H,
        background_utilisation,
    )

    lo3 = background_utilisation(
        concurrency=3, demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H
    )
    hi3 = background_utilisation(
        concurrency=3, demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H
    )
    assert lo3 < 1.0 <= hi3, (
        f"the concurrency-3 bracket no longer STRADDLES 1.0 ({lo3:.2f}..{hi3:.2f}); "
        "R4's status has changed and must be re-graded rather than re-asserted"
    )

    # Four slots clear it under both, which is the honest content of the
    # capacity proposal: the measured-safe step is 2 -> 4, not 2 -> 3.
    lo4 = background_utilisation(
        concurrency=4, demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H
    )
    hi4 = background_utilisation(
        concurrency=4, demand_s_per_h=BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H
    )
    assert hi4 < 1.0 and lo4 < 1.0, (lo4, hi4)
