"""Ruling 1, same-number corollary, as an executable invariant (#1829).

    Every surface that renders a probability for the same question at the same
    instant must render the SAME number.

Alex, 2026-08-13, Red Sox @ Blue Jays (event 15192596), top of the 9th, 5-0:
the header read **87 – 13** for the Red Sox while the chart's blend line sat at
**~0** for the Blue Jays. Two answers to one question, on one screen.

This file pins the invariant on the paths that can be enforced today, and — just
as importantly — pins the measured RESIDUAL that cannot, so it is a fact in the
suite instead of a memory. See ``test_the_residual_*`` at the bottom.

No wall-clock anchors anywhere (gotcha #44): every timestamp is a literal from
the production payload.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    compute_aggregate_probability,
)

COMMENCE = datetime(2026, 8, 13, 19, 7, 0, tzinfo=timezone.utc)

# ``win_probability_sources`` exactly as production held it, home = Blue Jays.
ALEX_SPECIMEN_SOURCES = {
    "mlb": 0.001,
    "espn": 0.008,
    "kalshi": 0.565,
    "betting": 0.1347,
    "stat_model": 0.001,
}


class _FakeEvent:
    """Minimal duck-type for ``compute_aggregate_probability``."""

    def __init__(self, sources, status="live", espn=None, opening=None):
        self.win_probability_sources = sources
        self.status = status
        self.espn_win_prob_home = espn
        self.opening_home_probability = opening
        self.commence_time = COMMENCE


# ── The specimen, reproduced exactly ─────────────────────────────────────────


class TestAlexSpecimenReproduces:
    """FIXED IN UX-P072 (#1829, Alex ruling 2026-08-13: recency decay + cap).

    These two tests used to assert the DEFECT — that the hero rendered 87-13 and
    equalled the betting source verbatim. They now assert the arithmetic that
    PRODUCED it, and the number the same payload renders today. The derivation
    is kept rather than deleted: it is the only place the 42%-weight-share
    mechanism is written down as executable, and it is what justifies the value
    of ``MAX_SOURCE_WEIGHT_SHARE``.

    The fix's own evidence lives in ``test_probability_recency_and_cap.py``.
    """

    def test_the_header_that_was_87_13_now_reads_99_1(self):
        home = compute_aggregate_probability(_FakeEvent(ALEX_SPECIMEN_SOURCES))
        # Rendered: away – home, rounded to whole points.
        assert (round((1 - home) * 100), round(home * 100)) == (99, 1)
        # Toronto lost 0-7. The header now agrees with the game.

    def test_the_weight_share_that_caused_it_is_recorded_and_now_capped(self):
        """Why it happened, kept executable.

        ``betting`` carried 3.0 of 7.1 total weight (42%), so once the values
        were sorted the cumulative weight crossed the midpoint inside that
        single source's own mass — the median did not get "dragged" toward the
        sportsbook, it landed exactly ON it. A weighted median is
        outlier-resistant only when no source can straddle the midpoint alone.

        #240 Item 1 switched this function from mean to median specifically to
        stop a stale sportsbook dragging the hero. It did not stop it; it made
        the hero EQUAL to it. #1829's cap is what actually closes the mechanism.
        """
        base_share = SOURCE_WEIGHTS["betting"] / sum(
            SOURCE_WEIGHTS[k] for k in ALEX_SPECIMEN_SOURCES
        )
        assert base_share > 0.40  # the uncapped reality that produced 87-13

        from app.utils.aggregation import MAX_SOURCE_WEIGHT_SHARE, cap_weight_shares

        capped = cap_weight_shares(
            [SOURCE_WEIGHTS[k] for k in ALEX_SPECIMEN_SOURCES]
        )
        assert max(capped) / sum(capped) <= MAX_SOURCE_WEIGHT_SHARE + 1e-9

        home = compute_aggregate_probability(_FakeEvent(ALEX_SPECIMEN_SOURCES))
        assert home != pytest.approx(ALEX_SPECIMEN_SOURCES["betting"], abs=1e-6)

    def test_the_three_live_aware_models_all_said_the_game_was_over(self):
        """mlb / espn / stat_model agreed on ~0. They were out-voted."""
        live_aware = {"mlb", "espn", "stat_model"}
        for key in live_aware:
            assert ALEX_SPECIMEN_SOURCES[key] <= 0.01
        # Their combined weight (3.3) exceeds betting's 3.0, yet the median
        # still lands on betting — weight alone does not decide a median.
        assert sum(SOURCE_WEIGHTS[k] for k in live_aware) > SOURCE_WEIGHTS["betting"]


# ── The invariant, as a property over generated source sets ──────────────────


def _source_sets():
    """Deterministic sweep of source combinations (no `hypothesis` here)."""
    keys = ["mlb", "espn", "kalshi", "betting", "stat_model"]
    values = [0.0, 0.001, 0.05, 0.1347, 0.5, 0.565, 0.92, 1.0]
    out = []
    for i, v in enumerate(values):
        for j in range(1, len(keys) + 1):
            subset = keys[:j]
            out.append({k: values[(i + n) % len(values)] for n, k in enumerate(subset)})
    return out


class TestSameNumberInvariant:
    @pytest.mark.parametrize("sources", _source_sets())
    def test_hero_is_a_probability_and_is_deterministic(self, sources):
        """Whatever the inputs, the hero is one number in [0,1] and is stable.

        Determinism is the precondition for the same-number rule: two surfaces
        cannot agree if the function itself does not.
        """
        event = _FakeEvent(sources)
        first = compute_aggregate_probability(event)
        second = compute_aggregate_probability(_FakeEvent(dict(sources)))
        assert first == second
        assert first is None or 0.0 <= first <= 1.0

    @pytest.mark.parametrize("sources", _source_sets())
    def test_home_and_away_always_sum_to_one(self, sources):
        """The two halves of the hero are one number rendered twice.

        This is the cheapest same-number surface there is, and the one the
        header itself depends on: "87 – 13" must be two views of one value.
        """
        home = compute_aggregate_probability(_FakeEvent(sources))
        if home is None:
            return
        away = round(1.0 - home, 6)
        assert home + away == pytest.approx(1.0, abs=1e-9)

    @pytest.mark.parametrize("sources", _source_sets())
    def test_hero_lies_inside_its_own_source_envelope(self, sources):
        """A blend outside the range of its inputs is invented, not aggregated.

        Same check the Grid Sentinel's ground-truth self-check applies to merged
        probabilities. A median can never leave the envelope, so this is a
        regression guard on the aggregation METHOD, not on today's weights.
        """
        home = compute_aggregate_probability(_FakeEvent(sources))
        if home is None:
            return
        assert min(sources.values()) - 1e-9 <= home <= max(sources.values()) + 1e-9

    def test_a_single_source_is_rendered_verbatim(self):
        for value in (0.0, 0.37, 1.0):
            assert compute_aggregate_probability(
                _FakeEvent({"espn": value})
            ) == pytest.approx(value)


# ── The residual, recorded rather than remembered ────────────────────────────


class TestTheResidualContradiction:
    """What this queue could NOT close, held as a fact rather than a note.

    ``_pin_blend_edge`` (UX-P003) already forces the chart's LAST point to
    equal the hero. Alex still saw the contradiction, because pinning one
    endpoint reconciles a NUMBER while leaving the PICTURE saying something else:
    on 15192596 the hero read 13% while the blend line had sat at ~0.1% for the
    preceding two hours, so the line still "reads ~0" and now ends in a spike.

    The two series are computed by two different functions whose names differ by
    one letter, in the same module:

        compute_aggregate_probability   — point-in-time, NO staleness decay
        compute_aggregated_probability  — time series, WITH staleness decay

    The module docstring advertises "weighted median with staleness decay". The
    point-in-time path implements only the first half. It cannot implement the
    second: ``Event.win_probability_sources`` stores bare floats with no
    per-source timestamp, so the hero has nothing to decay against.

    Closing it is a blend-rule change (it moves every hero and the Discover
    ranking with it) and therefore needs an Alex ruling — #1829.
    """

    def test_the_two_blend_functions_are_still_distinct(self):
        """A ratchet. When these become one function, delete this test."""
        from app.utils import aggregation

        assert hasattr(aggregation, "compute_aggregate_probability")
        assert hasattr(aggregation, "compute_aggregated_probability")
        assert (
            aggregation.compute_aggregate_probability
            is not aggregation.compute_aggregated_probability
        ), "unified — close #1829 and remove TestTheResidualContradiction"

    def test_the_point_in_time_blend_CAN_now_see_staleness(self):
        """CLOSED by UX-P072. The predecessor of this test was the defect in one
        assertion — and note how it was written, because that is the lesson:

            fresh = _FakeEvent(ALEX_SPECIMEN_SOURCES)
            stale = _FakeEvent(ALEX_SPECIMEN_SOURCES)   # identical!
            assert compute_aggregate_probability(fresh) == ...(stale)

        Both events were the SAME bare-float dict, because at the time there was
        nowhere in the JSONB to express "this reading is 40 minutes old". So the
        assertion held trivially and would have gone on holding trivially after
        the fix shipped — a ratchet that could never fire. It passed green on
        the very run that broke its two siblings.

        A ratchet whose two states are indistinguishable is not a ratchet. This
        replacement can only pass if the stamps actually change the answer.

        NOT written on the five-source specimen, and the reason is worth having:
        on that payload the CAP alone already moves the hero off ``betting``, so
        aging ``betting`` further changes nothing and the test passes for the
        wrong reason. Two sources put the cap below its own three-source gate,
        which leaves the decay as the only thing that can move the number.
        """
        from datetime import datetime, timedelta, timezone

        t0 = datetime(2026, 8, 13, 21, 33, 34, tzinfo=timezone.utc)
        pair = {k: ALEX_SPECIMEN_SOURCES[k] for k in ("betting", "espn")}

        def _at(offsets):
            return _FakeEvent(
                {
                    k: {
                        "value": v,
                        "updated_at": (t0 - timedelta(seconds=offsets[k])).isoformat(),
                    }
                    for k, v in pair.items()
                }
            )

        fresh = compute_aggregate_probability(_at({"betting": 0, "espn": 0}))
        stale_book = compute_aggregate_probability(_at({"betting": 3600, "espn": 0}))

        # Fresh: betting (3.0) outweighs espn (1.5) and carries the hero.
        assert fresh == pytest.approx(pair["betting"], abs=1e-9)
        # An hour behind: it cannot out-vote the source still reporting.
        assert stale_book == pytest.approx(pair["espn"], abs=1e-9)
        assert fresh != stale_book, "the hero is still blind to per-source age"

    def test_the_dict_form_is_already_accepted_so_the_fix_is_additive(self):
        """The reader already handles ``{"value": x, ...}``.

        So stamping ``updated_at`` alongside ``value`` at write time is a
        backward-compatible change: an entry with no timestamp keeps full
        weight and today's behaviour is preserved exactly. Recorded here because
        it is the cheap half of #1829 and easy to miss.
        """
        as_floats = compute_aggregate_probability(_FakeEvent(ALEX_SPECIMEN_SOURCES))
        as_dicts = compute_aggregate_probability(
            _FakeEvent({k: {"value": v} for k, v in ALEX_SPECIMEN_SOURCES.items()})
        )
        assert as_floats == as_dicts
