"""ux/1036 Tier A — the pre-match reading a settled card prints, and its source.

Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none of
these show pre-event probability?"* The cards carried one grey `Opened 40/60`
footnote and nothing else, and that number is the SPORTSBOOK median — the only
writer of ``Event.opening_*``.

These guard the two decisions the fix makes: the LADDER (Kalshi → Polymarket →
books, ordered and never merged) and the LABEL (only a non-prediction-market rung
carries one).
"""

import pytest

from app.utils.prematch_reading import (
    BOOKS_SOURCE,
    PREMATCH_LADDER,
    PREDICTION_MARKET_SOURCES,
    is_prediction_market_source,
    needs_source_label,
    prematch_source_rank,
    resolve_prematch_reading,
)


# ── The ladder ───────────────────────────────────────────────────────────────


def test_kalshi_wins_over_polymarket_and_books():
    """Alex's order, and the reason it is an order rather than a blend: a card
    that averages "what Kalshi thought" with "what the books thought" prints a
    number no venue ever quoted."""
    reading = resolve_prematch_reading(
        by_source={"kalshi": (0.62, 0.38), "polymarket": (0.71, 0.29)},
        books_home=0.55,
        books_away=0.45,
    )
    assert reading == {
        "home_probability": 0.62,
        "away_probability": 0.38,
        "source": "kalshi",
    }


def test_polymarket_wins_over_books_when_kalshi_is_absent():
    reading = resolve_prematch_reading(
        by_source={"polymarket": (0.71, 0.29)},
        books_home=0.55,
        books_away=0.45,
    )
    assert reading["source"] == "polymarket"
    assert reading["home_probability"] == 0.71


def test_books_are_the_floor_not_the_absence():
    """The books rung is a real reading. "Never blank when any pre-match reading
    exists" (Alex, #2747) is the whole point of having a third rung."""
    reading = resolve_prematch_reading(by_source={}, books_home=0.55, books_away=0.45)
    assert reading["source"] == BOOKS_SOURCE
    assert reading["home_probability"] == 0.55


def test_nothing_at_any_rung_is_none_and_none_means_print_nothing():
    assert resolve_prematch_reading(by_source={}, books_home=None) is None


def test_an_unusable_upper_rung_falls_through_rather_than_blanking_the_card():
    """A rung that holds a number we cannot print is not "this event has no
    prior". The single-block form the tennis hub used could not tell those
    apart; this is the case that proves the ladder keeps walking."""
    reading = resolve_prematch_reading(
        by_source={"kalshi": (None, None), "polymarket": (0.71, 0.29)},
        books_home=0.55,
    )
    assert reading["source"] == "polymarket"


def test_a_settled_price_that_leaked_past_the_clock_filter_is_refused():
    """1.0 is not a forecast, it is the result read back. It would render as the
    strongest claim on the card, made by an artefact — so the rung is skipped and
    the ladder falls through to one that priced the question."""
    reading = resolve_prematch_reading(
        by_source={"kalshi": (1.0, 0.0), "polymarket": (0.71, 0.29)},
        books_home=0.55,
    )
    assert reading["source"] == "polymarket"


# ── The pair ─────────────────────────────────────────────────────────────────


def test_a_served_complement_is_used_rather_than_re_derived():
    reading = resolve_prematch_reading(by_source={"kalshi": (0.615, 0.385)})
    assert reading["away_probability"] == 0.385


def test_a_served_away_that_is_not_a_complement_is_derived_from_home():
    """Two numbers that do not answer one question must not be printed side by
    side in fixed positions. Home is the anchor; away is rebuilt from it."""
    reading = resolve_prematch_reading(by_source={"kalshi": (0.60, 0.75)})
    assert reading["home_probability"] == 0.60
    assert reading["away_probability"] == pytest.approx(0.40)


def test_a_missing_away_is_derived():
    reading = resolve_prematch_reading(by_source={"kalshi": (0.60, None)})
    assert reading["away_probability"] == pytest.approx(0.40)


# ── The label ────────────────────────────────────────────────────────────────


def test_only_the_books_rung_needs_a_label():
    """Alex: "labelled when not a prediction market." A prediction-market
    opening is what this product is about and reads as itself."""
    for source in PREDICTION_MARKET_SOURCES:
        assert is_prediction_market_source(source)
        assert not needs_source_label(source)
    assert not is_prediction_market_source(BOOKS_SOURCE)
    assert needs_source_label(BOOKS_SOURCE)


def test_the_label_is_generic_and_never_a_venue_name():
    """`Event.opening_*` is a MEDIAN across whichever books were still quoting
    (#1841), so there is no single venue to name and naming one would be false —
    quite apart from ruling 141 keeping venue names out of narrative copy."""
    assert BOOKS_SOURCE == "books"
    assert "kalshi" not in BOOKS_SOURCE
    assert "polymarket" not in BOOKS_SOURCE


# ── The shared order ─────────────────────────────────────────────────────────


def test_the_rank_is_the_ladder_and_the_hub_sorts_by_the_same_one():
    """`prematch_source_rank` exists so the tennis hub, which CHOOSES between two
    readings it already holds, cannot grow a second copy of Alex's ordering."""
    assert PREMATCH_LADDER == ("kalshi", "polymarket", "books")
    ranks = [prematch_source_rank(s) for s in PREMATCH_LADDER]
    assert ranks == sorted(ranks) == [0, 1, 2]


def test_an_unknown_source_sorts_last_rather_than_first():
    """Still usable, never preferred: an unrecognised rung is not a reason to
    discard a reading, and it is not a reason to trust it over Kalshi."""
    assert prematch_source_rank("statpal") > prematch_source_rank("polymarket")
    assert prematch_source_rank(None) > prematch_source_rank(BOOKS_SOURCE)
