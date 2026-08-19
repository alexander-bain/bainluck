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


def test_the_proposed_60s_w_move_is_unsafe():
    """Fable's LAT-P072 item 2 proposal, graded. Pinned so the refusal is durable.

    Not an opinion about the directive: it is the arithmetic. At 60 s the
    quantiser is coarser than the entire measured wall distribution, so the
    period is 60 s for every reachable wall and there is no branch under 45 s.
    """
    grade = grade_beat_interval(PROPOSED_W_MOVE_BEAT_S)

    assert grade.verdict == BeatVerdict.UNSAFE
    assert grade.is_shippable is False
    assert grade.period_at_median_s == 60.0
    assert grade.period_at_worst_s == 60.0
    assert grade.period_at_best_s == 60.0, (
        "even the FASTEST measured pass quantises to 60s — that is what makes "
        "this unconditional rather than a tail risk"
    )
    assert grade.crosses_cliff_on_median is True


def test_todays_10s_beat_is_marginal_not_safe():
    """Honesty pin: the status quo is not clean either, and must not read as clean.

    At the worst measured wall (42.6 s) a 10 s beat quantises to 50 s, over the
    45 s TTL — and production has measured the live period at 42.5-51.7 s, so the
    upper tail is already crossing. Asserting SAFE here would be the comfortable
    lie; asserting MARGINAL keeps #1866's residual visible.
    """
    grade = grade_beat_interval(CURRENT_BEAT_INTERVAL_S)

    assert grade.verdict == BeatVerdict.MARGINAL
    assert grade.is_shippable is False
    assert grade.period_at_median_s == 40.0
    assert grade.period_at_worst_s == 50.0
    assert grade.crosses_cliff_on_median is False
    assert grade.crosses_cliff_on_worst is True


def test_the_arithmetically_fitting_22s_is_still_refused_as_marginal():
    """B=22 lands the period at 44 s across the whole measured range — and is not SAFE.

    1.4 s of headroom against a maximum drawn from 20 passes is a coincidence of
    arithmetic, not a margin. If `SAFETY_MARGIN_S` were ever lowered to make this
    pass, this test is where that decision becomes visible.
    """
    grade = grade_beat_interval(22.0)

    assert grade.period_at_worst_s == 44.0
    assert grade.crosses_cliff_on_worst is False
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
    unsafe = grade_beat_interval(60.0)

    assert refused.verdict == BeatVerdict.REFUSED
    assert unsafe.verdict == BeatVerdict.UNSAFE
    assert refused.verdict != unsafe.verdict
    assert refused.is_shippable is False and unsafe.is_shippable is False


def test_measured_wall_range_is_internally_coherent():
    """The module's own provenance constants must satisfy min <= median <= max.

    Cheap, and it is the input every grade above depends on.
    """
    assert MEASURED_WALL_MIN_S <= MEASURED_WALL_MEDIAN_S <= MEASURED_WALL_MAX_S
    assert MEASURED_WALL_MAX_S < RESPONSE_CACHE_TTL_S, (
        "if a single pass wall exceeds the response TTL, no beat interval can "
        "help and the cliff must be addressed on the TTL or the pass, not here"
    )
