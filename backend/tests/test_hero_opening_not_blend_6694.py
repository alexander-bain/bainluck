"""#6694 — an opening-only hero must not be served as a blend.

THE DEFECT. ``resolve_hero`` documents a three-arm cascade (settled → blend →
opening) and calls ``opening`` load-bearing vocabulary: "nobody has quoted this
since the line was posted". That arm was unreachable. ``compute_aggregate_
probability``'s own Tier 3 returns ``opening_home_probability``, so the blend arm
above it answered first on every event that has an opening, and the opening arm
could never be reached to make its claim.

Measured on production 2026-09-19 12:00–12:40Z: 486 events in a two-day window
carry the signature (no weighted source in the bag, no ESPN reading, an opening
on file), 8 live at that minute, all served ``hero_probability_source: "blend"``.
Specimen 15314578 (Uganda–Kenya, live) printed a 64% hero captioned as a live
blend above a chart whose own series ended at 78%.

🔴 WHAT THIS FIX IS NOT. It does NOT move the number, and the test at the bottom
of this file exists to keep it that way. On the specimen the bag holds
``betting_book_count: 1`` with no ``betting`` reading because RULING 051 DROPS
the sportsbook consensus below ``BETTING_BOOK_FLOOR`` — "a consensus of one is
not a consensus". The 78% on the chart is that single book. Reaching for it to
"close the gap" would rebuild #1841 (an 87-13 hero for a team trailing 5-0), so
the honest hero here is the opening, correctly labelled.
"""

from app.utils.aggregation import (
    TIER_ESPN,
    TIER_OPENING,
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


def test_opening_only_hero_is_labelled_opening_not_blend():
    hero = resolve_hero(_specimen())

    assert hero is not None
    assert hero.source == "opening", (
        "an opening-only event was served as a blend — this is #6694, and it is "
        "the claim that is wrong, not the number"
    )


def test_opening_only_hero_number_is_unchanged_by_the_relabel():
    """The value must be byte-identical to what production served before."""
    hero = resolve_hero(_specimen())

    assert hero.home_probability == 0.6414
    assert hero.away_probability == 0.3586


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


def test_a_finished_opening_only_game_keeps_final_unresolved():
    """CERT-1938 outranks this fix.

    "This game is over and we cannot name a winner" is a strictly more urgent
    claim than where the line opened, so the finished arm is exempt from the
    relabel. Without this the fix would quietly delete that signal from every
    finished game that never attracted a second source.
    """
    hero = resolve_hero(
        _Event(
            status="completed",
            bag={"betting_book_count": 1.0},
            opening_home=0.6414,
            opening_away=0.3586,
        )
    )

    assert hero.source == "final_unresolved"
    assert hero.home_probability == 0.6414


def test_nothing_at_all_is_still_none_and_never_a_zero():
    assert resolve_hero(_Event()) is None


# ── the tier vocabulary, and that the split changed no caller ────────────────


def test_the_aggregator_names_the_tier_that_answered():
    assert compute_aggregate_probability_tiered(_specimen())[1] == TIER_OPENING
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
    """The tempting wrong fix, pinned shut.

    The obvious reading of #6694 is "the hero is stale, serve the live
    sportsbook consensus instead". On the specimen that consensus is ONE book
    (``betting_book_count: 1``, below ``BETTING_BOOK_FLOOR``), which ruling 051
    deliberately refuses to publish. A future lane closing the hero/chart gap
    that way would be rebuilding #1841, so this asserts the hero stays on the
    opening even though a fresher single-book number exists on the event.
    """
    event = _specimen()
    event.win_probability_sources = {"betting_book_count": 1.0}

    hero = resolve_hero(event)

    assert hero.home_probability == 0.6414
    assert hero.source == "opening"
