"""#7514 — a finished soccer card stops handing the draw to the away team when
the BOOKS rung answers.

── THE DEFECT ──────────────────────────────────────────────────────────────────

#6277 stopped the away slot carrying the whole draw, but only for the rungs that
can carry a draw as evidence. Its own resolver docstring named the gap: "the
books rung ... never carries one: ``Event.opening_*`` has no draw column, which
is #1011 and is not this fix." So on a draw-priced sport the books rung fell
through to ``1 - home`` unconditionally, and that is the rung that answers in
production.

Measured on production 2026-09-20 14:00Z, ``GET /api/feed?mode=sports&limit=120``
— the eight finished soccer cards carrying a usable pair, grouped by the rung
that answered:

    kalshi (carries a draw)   5 cards   worst gap   1.3pt
    books  (no draw column)   3 cards   worst gap  26.0pt

The three books cards are the specimens below. Each away figure is the stored
``opening_away_probability``, which since #1011 is de-vigged across the whole
quoted board and IS that team's price — ``utils/draw_priced_winner`` says so in
terms, and then ``_pair`` deleted it.

── WHAT THIS FILE PINS ─────────────────────────────────────────────────────────

Both arms, because a fix for one is a defect in the other:

* a draw-priced books pair KEEPS its sourced away, and
* a two-way books pair is STILL re-complemented.

The second is the one that matters. ``away_is_the_complement`` answers False for
every two-way sport by its own first line, so an arm written without the
``sport_prices_a_draw`` gate would keep a stale MLB away and silently delete the
coherence guard for the whole fleet. ``test_two_way_incoherent_pair_is_still_
rebuilt`` fails if that gate is ever dropped.
"""

from __future__ import annotations

import pytest

from app.utils.prematch_reading import resolve_prematch_reading


SOCCER = "soccer_germany_bundesliga2"
TWO_WAY = "baseball_mlb"


# (label, sport, books_home, books_away, the away price the card must print)
#
# The three production specimens. `expected_away` is the venue's own de-vigged
# price for that team; the pre-fix payload printed `1 - home` instead, which is
# the fourth column.
PRODUCTION_SPECIMENS = [
    # FC Seoul @ Pohang Steelers (15311786) — printed 81%, Seoul's price was .545
    ("fc-seoul-at-pohang", "soccer_korea_kleague1", 0.195, 0.545, 0.805),
    # FC St. Pauli @ FC Energie Cottbus (15311880) — printed 70%, price was .455
    ("st-pauli-at-cottbus", SOCCER, 0.302, 0.455, 0.698),
    # Gwangju FC @ Jeonbuk (15311606) — printed 33%, Gwangju's price was .129
    ("gwangju-at-jeonbuk", "soccer_korea_kleague1", 0.668, 0.129, 0.332),
]


@pytest.mark.parametrize(
    "label,sport,books_home,books_away,pre_fix_away",
    PRODUCTION_SPECIMENS,
    ids=[row[0] for row in PRODUCTION_SPECIMENS],
)
def test_books_rung_serves_the_sourced_away_price(
    label, sport, books_home, books_away, pre_fix_away
):
    """The away figure on the card is the board's, not ``1 - home``."""
    reading = resolve_prematch_reading(
        books_home=books_home, books_away=books_away, sport=sport
    )

    assert reading is not None
    assert reading["source"] == "books"
    assert reading["home_probability"] == pytest.approx(books_home)
    assert reading["away_probability"] == pytest.approx(books_away)
    # And it is no longer the complement the card used to print.
    assert reading["away_probability"] != pytest.approx(pre_fix_away)


def test_two_way_incoherent_pair_is_still_rebuilt():
    """THE GUARD THAT MUST NOT BE DELETED.

    On a two-way sport a pair that does not sum to one is still two numbers that
    are not the two sides of one question, and the away slot is still rebuilt
    from the side we trust. This is the arm that fails if a future edit drops the
    ``sport_prices_a_draw`` gate in ``_pair``, because ``away_is_the_complement``
    answers False for MLB and would otherwise wave the stale value straight
    through.
    """
    reading = resolve_prematch_reading(
        books_home=0.60, books_away=0.19, sport=TWO_WAY
    )

    assert reading is not None
    assert reading["away_probability"] == pytest.approx(0.40)


def test_two_way_coherent_pair_is_untouched():
    """Every MLB/NFL/NBA card keeps the number it has today."""
    reading = resolve_prematch_reading(
        books_home=0.532, books_away=0.468, sport=TWO_WAY
    )

    assert reading is not None
    assert reading["home_probability"] == pytest.approx(0.532)
    assert reading["away_probability"] == pytest.approx(0.468)


def test_absent_sport_is_byte_identical_to_the_old_behaviour():
    """Every caller that has not been wired behaves exactly as before.

    `tournament_slate._pair_probabilities` is the live instance — golf and tennis
    price no draw, so the arm is unreachable there, but the contract is pinned
    rather than assumed.
    """
    with_sport = resolve_prematch_reading(books_home=0.302, books_away=0.455)
    assert with_sport is not None
    assert with_sport["away_probability"] == pytest.approx(0.698)


def test_a_draw_priced_away_that_IS_the_complement_is_not_promoted():
    """#6238's withholding story survives.

    When the stored away already equals ``1 - home`` it is not a sourced price,
    it is the complement wearing a team's name. The arm must not launder it into
    one. The value is unchanged either way; what matters is that it travels the
    fall-through, so the meaning stays "we could not source this".
    """
    reading = resolve_prematch_reading(
        books_home=0.36, books_away=0.64, sport=SOCCER
    )

    assert reading is not None
    assert reading["away_probability"] == pytest.approx(0.64)


def test_a_draw_carrying_rung_still_wins_before_the_sport_arm():
    """The five kalshi cards in the production read never reach the new arm.

    Real evidence beats evidence of last resort: a rung that offers a draw that
    closes the partition returns at #6277's arm, above this one.
    """
    reading = resolve_prematch_reading(
        by_source={"kalshi": {"home": 0.505, "away": 0.245, "draw": 0.25}},
        books_home=0.302,
        books_away=0.455,
        sport=SOCCER,
    )

    assert reading is not None
    assert reading["source"] == "kalshi"
    assert reading["away_probability"] == pytest.approx(0.245)
