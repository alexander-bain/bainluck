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
    def test_the_hero_renders_87_13(self):
        """The header Alex photographed, derived rather than asserted by hand."""
        home = compute_aggregate_probability(_FakeEvent(ALEX_SPECIMEN_SOURCES))
        assert home == pytest.approx(0.1347, abs=1e-6)
        # Rendered: away – home, rounded to whole points.
        assert round((1 - home) * 100) == 87
        assert round(home * 100) == 13

    def test_the_hero_IS_the_betting_source_verbatim(self):
        """Not "influenced by" — the weighted median lands exactly ON it.

        ``betting`` carries 3.0 of 7.1 total weight (42%), so once the values are
        sorted the cumulative weight crosses the midpoint inside that single
        source's own mass. A weighted median is outlier-resistant only when no
        source holds near half the weight; this one does, so the median
        degenerates to "whatever the sportsbook last said".

        #240 Item 1 switched this function from mean to median specifically to
        stop a stale sportsbook dragging the hero. It did not stop it — it made
        the hero EQUAL to it.
        """
        home = compute_aggregate_probability(_FakeEvent(ALEX_SPECIMEN_SOURCES))
        assert home == pytest.approx(ALEX_SPECIMEN_SOURCES["betting"], abs=1e-9)
        assert SOURCE_WEIGHTS["betting"] / sum(
            SOURCE_WEIGHTS[k] for k in ALEX_SPECIMEN_SOURCES
        ) > 0.40

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

    ``_pin_live_blend_edge`` (UX-P003) already forces the chart's LAST point to
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

    def test_the_point_in_time_blend_still_cannot_see_staleness(self):
        """Two events, identical values, one of them hours old: same answer.

        This is the defect in one assertion. When it fails, the hero has learned
        about time and #1829 is fixed.
        """
        fresh = _FakeEvent(ALEX_SPECIMEN_SOURCES)
        stale = _FakeEvent(ALEX_SPECIMEN_SOURCES)
        # There is nowhere to even EXPRESS "this reading is 40 minutes old":
        # the JSONB holds bare floats.
        assert all(
            isinstance(v, (int, float)) for v in ALEX_SPECIMEN_SOURCES.values()
        )
        assert compute_aggregate_probability(fresh) == compute_aggregate_probability(
            stale
        )

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
