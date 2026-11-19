"""#6694 / #12824: historical opening lines never become a current hero.

The older fix relabelled this value. Alex's current rule removes it: no current
source means no chance. Real blends, ESPN and verified results still resolve.
"""

from app.utils.aggregation import (
    TIER_ESPN,
    TIER_SOURCES,
    compute_aggregate_probability,
    compute_aggregate_probability_tiered,
)
from app.utils.hero_probability import resolve_hero


class _Event:
    """The attributes the hero cascade reads, and nothing else."""

    def __init__(
        self,
        *,
        status="live",
        bag=None,
        espn=None,
        opening_home=None,
        opening_away=None,
        home_score=None,
        away_score=None,
        completed_at=None,
    ):
        self.status = status
        self.win_probability_sources = {} if bag is None else bag
        self.espn_win_prob_home = espn
        self.opening_home_probability = opening_home
        self.opening_away_probability = opening_away
        self.home_score = home_score
        self.away_score = away_score
        self.completed_at = completed_at


def _specimen():
    """Event 15314578's exact production state at 2026-09-19 12:06:44Z."""
    return _Event(
        status="live",
        bag={"betting_book_count": 1.0},
        opening_home=0.6414,
        opening_away=0.3586,
    )


# ── the defect itself ────────────────────────────────────────────────────────


def test_opening_only_hero_is_absent():
    assert resolve_hero(_specimen()) is None


def test_resolving_the_hero_preserves_historical_opening_fields():
    event = _specimen()
    assert resolve_hero(event) is None
    assert event.opening_home_probability == 0.6414
    assert event.opening_away_probability == 0.3586


# ── the arms that must NOT move ──────────────────────────────────────────────


def test_a_real_multi_source_blend_is_still_a_blend():
    hero = resolve_hero(
        _Event(
            bag={"betting": {"value": 0.7534}, "kalshi": {"value": 0.74}},
            opening_home=0.6414,
            opening_away=0.3586,
        )
    )

    assert hero.source == "blend"
    assert hero.home_probability != 0.6414, "the opening leaked into a real blend"


def test_an_espn_only_hero_is_still_a_blend():
    """Tier 2 is a model reading, not an opening — its label does not move."""
    hero = resolve_hero(_Event(espn=0.55, opening_home=0.6414, opening_away=0.3586))

    assert hero.source == "blend"
    assert hero.home_probability == 0.55


def test_a_finished_opening_only_game_does_not_invent_a_chance():
    """Unresolved status survives on the event; an opening is not its chance."""
    hero = resolve_hero(
        _Event(
            status="completed",
            bag={"betting_book_count": 1.0},
            opening_home=0.6414,
            opening_away=0.3586,
        )
    )

    assert hero is None


def test_nothing_at_all_is_still_none_and_never_a_zero():
    assert resolve_hero(_Event()) is None


# ── the tier vocabulary, and that the split changed no caller ────────────────


def test_the_aggregator_names_the_tier_that_answered():
    assert compute_aggregate_probability_tiered(_specimen()) == (None, None)
    assert compute_aggregate_probability_tiered(_Event(espn=0.55))[1] == TIER_ESPN
    assert (
        compute_aggregate_probability_tiered(
            _Event(bag={"betting": {"value": 0.7534}, "kalshi": {"value": 0.74}})
        )[1]
        == TIER_SOURCES
    )
    assert compute_aggregate_probability_tiered(_Event())[1] is None


def test_the_wrapper_returns_exactly_what_the_tiered_form_computes():
    """Every existing caller reads the number only, and it must not have moved.

    This is the guard for the refactor rather than for the fix: the split is
    only safe if these two can never disagree.
    """
    matrix = [
        _specimen(),
        _Event(),
        _Event(espn=0.55),
        _Event(espn=0.55, opening_home=0.6414),
        _Event(bag={"betting": {"value": 0.7534}, "kalshi": {"value": 0.74}}),
        _Event(bag={"betting_book_count": 1.0}),
        _Event(status="completed", bag={"betting_book_count": 1.0}, opening_home=0.61),
    ]
    for event in matrix:
        assert (
            compute_aggregate_probability(event)
            == compute_aggregate_probability_tiered(event)[0]
        )


# ── ruling 051: the number must never be "fixed" by reaching for one book ────


def test_a_single_book_live_price_never_becomes_the_hero():
    event = _specimen()
    event.win_probability_sources = {"betting_book_count": 1.0}
    assert resolve_hero(event) is None
