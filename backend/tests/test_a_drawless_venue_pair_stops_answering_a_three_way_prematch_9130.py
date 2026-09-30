"""#9130 — a settled soccer page stops saying "WON · 71% pregame" while its own
chart starts the winner at 45%.

── THE DEFECT ──────────────────────────────────────────────────────────────────

``/events/15314006`` (LA Galaxy 3–2 Colorado Rapids, MLS), 2026-09-27 11:52Z:
the hero read "LA Galaxy · WON · 71% pregame". The only Kalshi market is the
three-way ``KXMLSGAME-26SEP26LAGCOL`` (LAG / TIE / COL), and every Kalshi
``win_prob_snapshots`` row before kickoff was the chart backfill reading
COLORADO's leg: home = 1 − P(Colorado) = P(Galaxy) + P(draw), draw NULL. The last
one, 0.7050 / 0.2950 / NULL, is what the page printed. Galaxy's own leg and the
books (opening 0.4488 / 0.2921) both said ~45%, and so did the chart.

``_pair`` cannot refuse that row: home + away = 1.000, so it is coherent by
construction. On a draw-priced sport the missing draw IS the evidence — a
three-way game has no honest two-number reading — so the rung is not asked and
the ladder falls to the next venue or the books.

── WHAT THIS FILE PINS ─────────────────────────────────────────────────────────

* the specimen serves the books' 45%, on the resolver AND on the page route;
* a venue reading that CARRIES its draw still answers first (#6277);
* a draw-less venue pair on a draw sport that is NOT a complement still answers
  through #7514's arm — only the complement shape is the fabrication;
* two-way sports and callers that pass no sport are byte-identical.
"""

from __future__ import annotations

import asyncio

import pytest

from app.routes.events import _settled_prematch_odds
from app.utils.prematch_reading import (
    _is_a_two_way_reading_of_a_three_way_game,
    resolve_prematch_reading,
)

from tests.test_settled_event_page_serves_the_cards_prematch_reading_8315 import (
    _PrematchSession,
    _event,
    _feed_prematch,
    _row,
)

MLS = "soccer_usa_mls"

# The stored rows and columns of /events/15314006, as measured.
SPECIMEN_KALSHI = (0.7050, 0.2950, None)
SPECIMEN_BOOKS = (0.4488, 0.2921)


def _resolve(by_source, sport=MLS, books=SPECIMEN_BOOKS):
    return resolve_prematch_reading(
        by_source=by_source, books_home=books[0], books_away=books[1], sport=sport
    )


# ── The specimen ─────────────────────────────────────────────────────────────


def test_the_specimen_serves_the_books_45_not_the_backfills_71():
    reading = _resolve({"kalshi": SPECIMEN_KALSHI})

    assert reading["source"] == "books"
    assert reading["home_probability"] == pytest.approx(0.4488)
    assert reading["away_probability"] == pytest.approx(0.2921)


def test_the_before_reproduces_the_photographed_71_without_a_sport():
    """The BEFORE, so nobody has to take the screenshot on trust: with no sport
    to say a draw exists, the row answers as it did on production."""
    reading = _resolve({"kalshi": SPECIMEN_KALSHI}, sport=None)

    assert reading["source"] == "kalshi"
    assert reading["home_probability"] == pytest.approx(0.705)


def test_the_settled_page_route_serves_the_books_rung_and_matches_the_card():
    event = _event(sport_key=MLS, home=SPECIMEN_BOOKS[0], away=SPECIMEN_BOOKS[1])
    rows = [_row("kalshi", *SPECIMEN_KALSHI)]

    page = asyncio.run(_settled_prematch_odds(_PrematchSession(rows), event, MLS))

    assert page["source"] == "books"
    assert page["home_rendered_percent"] == 45
    assert page == _feed_prematch(event, rows)


# ── What must still answer ───────────────────────────────────────────────────


def test_a_venue_reading_that_carries_its_draw_still_answers_first():
    reading = _resolve({"kalshi": (0.45, 0.29, 0.26)})

    assert reading["source"] == "kalshi"
    assert reading["home_probability"] == pytest.approx(0.45)
    assert reading["away_probability"] == pytest.approx(0.29)


def test_a_skipped_kalshi_falls_to_a_polymarket_that_carries_its_draw():
    reading = _resolve(
        {"kalshi": SPECIMEN_KALSHI, "polymarket": (0.44, 0.30, 0.26)}
    )

    assert reading["source"] == "polymarket"
    assert reading["home_probability"] == pytest.approx(0.44)


def test_a_drawless_pair_that_is_not_a_complement_still_answers():
    """Only the ``1 − home`` shape is the fabrication. A short pair keeps its
    sourced away through #7514's arm, as the books rung does."""
    reading = _resolve({"kalshi": (0.45, 0.29, None)})

    assert reading["source"] == "kalshi"
    assert reading["away_probability"] == pytest.approx(0.29)


@pytest.mark.parametrize("sport", ["baseball_mlb", "americanfootball_nfl", None, ""])
def test_a_two_way_or_unnamed_sport_is_untouched(sport):
    reading = _resolve({"kalshi": (0.62, 0.38, None)}, sport=sport)

    assert reading["source"] == "kalshi"
    assert reading["home_probability"] == pytest.approx(0.62)
    assert reading["away_probability"] == pytest.approx(0.38)


# ── The shapes that are refused ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "served",
    [
        (0.7050, 0.2950, None),  # the specimen, a tuple
        (0.7050, 0.2950),  # a pre-#6277 two-element tuple
        (0.45, None, None),  # away absent: _pair would derive 1 - home
        {"home": 0.705, "away": 0.295, "draw": None},  # the Mapping form
    ],
)
def test_every_drawless_complement_shape_falls_through(served):
    assert _resolve({"kalshi": served})["source"] == "books"


def test_with_nothing_else_held_the_card_prints_no_prematch_number():
    """Deliberate: the one case the ladder goes blank. A number that is
    P(home) + P(draw) as often as P(home) is not a pre-match price, and the
    ladder's "never blank" promise is for readings, not for this."""
    assert _resolve({"kalshi": SPECIMEN_KALSHI}, books=(None, None)) is None


def test_the_predicate_needs_a_usable_home_to_refuse_anything():
    assert not _is_a_two_way_reading_of_a_three_way_game(None, 0.3, None, MLS)
    assert not _is_a_two_way_reading_of_a_three_way_game(1.0, 0.0, None, MLS)
