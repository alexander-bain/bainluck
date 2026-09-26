"""A feed whose home/away flipped still prices each side under its own name (#8530).

SPECIMEN, production 2026-09-25 03:50Z. UFC Fight Night, 2026-09-26. Event
15314293 was created by odds_api on 09-17 as `home Rodolfo Vieira / away Robert
Bryczek`. The Odds API has since flipped the pair (MMA has no home side), and the
page read **Vieira 41% – 59% Bryczek** while DraftKings had Vieira at -162,
Kalshi at 0.59/0.60 and Polymarket at 0.595. All six fights on the card were
inverted the same way.

Cause: `_parse_snapshot_values` keys every price on the FEED's `home_team`, and
the row was found by the exact odds_api id, which needs no names. Each book's
Bryczek price was stored as `home_moneyline` on Vieira's row.

These tests drive the real `_ingest_event_odds` → `_create_or_update_snapshot` →
`_parse_snapshot_values` chain, because the stored snapshot is the defect. A
test that only calls the helper would pass on a tree where no writer calls it.
"""

import pytest
from tests.test_priorless_stat_model_defers_to_market_8522 import (
    _portable_probability_writer,  # noqa: F401 - shared recording/SQLite write seam
)

from app.tasks.odds_polling import (
    BETTING_BOOK_FLOOR,
    _ingest_event_odds,
    _orient_feed_to_row,
    _parse_snapshot_values,
)
from app.models import OddsSnapshot
from tests.test_discovery_advances_betting_consensus_5426 import (
    FUTURE,
    _ScalarResult,
)

VIEIRA = "Rodolfo Vieira"
BRYCZEK = "Robert Bryczek"

#: (book, Vieira price, Bryczek price). DraftKings is the specimen's quote.
BOOKS = [("draftkings", -162, 136), ("fanduel", -160, 130), ("betmgm", -155, 130)]


def _h2h_book(key, prices_by_name):
    return {
        "key": key,
        "markets": [
            {
                "key": "h2h",
                "outcomes": [{"name": n, "price": p} for n, p in prices_by_name.items()],
            }
        ],
    }


def _feed(home, away, books=BOOKS):
    return {
        "id": "odds-api-vieira-bryczek",
        "home_team": home,
        "away_team": away,
        "bookmakers": [_h2h_book(k, {VIEIRA: v, BRYCZEK: b}) for k, v, b in books],
    }


class _Row:
    def __init__(self, home=VIEIRA, away=BRYCZEK):
        self.id = 15314293
        self.home_team_name = home
        self.away_team_name = away
        self.win_probability_sources = {}
        self.status = "scheduled"


class _Session:
    """No prior snapshot exists; records what is added and what is written."""

    def __init__(self):
        self.added: list[OddsSnapshot] = []
        self.sources_writes: list[dict] = []
        self.opening_writes: list[dict] = []

    async def execute(self, stmt):
        descs = getattr(stmt, "column_descriptions", None) or []
        if any(d.get("entity") is OddsSnapshot for d in descs):
            return _ScalarResult(None)
        params = getattr(stmt, "_values", None) or {}
        vals = {str(k).split(".")[-1]: getattr(v, "value", v) for k, v in params.items()}
        if "win_probability_sources" in vals:
            self.sources_writes.append(vals["win_probability_sources"])
        elif any(k.startswith("opening_") for k in vals):
            self.opening_writes.append(vals)
        return _ScalarResult("scheduled")

    def add(self, obj):
        self.added.append(obj)


async def _ingest(row, feed):
    session = _Session()
    await _ingest_event_odds(session, row, feed, FUTURE, {})
    return session


class TestTheSpecimen:
    @pytest.mark.asyncio
    async def test_a_flipped_feed_stores_each_price_under_the_named_fighter(self):
        """The ship: Vieira's -162 is Vieira's price on Vieira's row."""
        session = await _ingest(_Row(), _feed(home=BRYCZEK, away=VIEIRA))

        dk = next(s for s in session.added if s.bookmaker == "draftkings")
        assert dk.home_moneyline == -162
        assert dk.away_moneyline == 136
        assert all(s.home_win_probability > 0.5 for s in session.added)

    @pytest.mark.asyncio
    async def test_the_published_consensus_names_vieira_the_favourite(self):
        """What the hero reads: `betting` and the opening line, not just a row."""
        assert len(BOOKS) >= BETTING_BOOK_FLOOR
        session = await _ingest(_Row(), _feed(home=BRYCZEK, away=VIEIRA))

        betting = session.sources_writes[-1]["betting"]["value"]
        assert 0.58 < betting < 0.62
        assert session.opening_writes[-1]["opening_home_probability"] > 0.5

    @pytest.mark.asyncio
    async def test_a_feed_in_the_rows_orientation_is_unchanged(self):
        """Control: the ordinary case writes exactly what it wrote before."""
        session = await _ingest(_Row(), _feed(home=VIEIRA, away=BRYCZEK))
        dk = next(s for s in session.added if s.bookmaker == "draftkings")
        assert (dk.home_moneyline, dk.away_moneyline) == (-162, 136)

        raw = _parse_snapshot_values(
            _h2h_book("draftkings", {VIEIRA: -162, BRYCZEK: 136}),
            _feed(home=VIEIRA, away=BRYCZEK),
        )
        assert dk.home_win_probability == raw["home_win_probability"]

    @pytest.mark.asyncio
    async def test_both_orientations_now_store_the_same_numbers(self):
        """The invariant: the feed's home/away no longer moves a stored price."""
        a = await _ingest(_Row(), _feed(home=VIEIRA, away=BRYCZEK))
        b = await _ingest(_Row(), _feed(home=BRYCZEK, away=VIEIRA))
        key = lambda s: (s.bookmaker, s.home_moneyline, s.away_moneyline, s.home_win_probability)  # noqa: E731
        assert sorted(map(key, a.added)) == sorted(map(key, b.added))


class TestSpreadsFollowTheName:
    def test_the_spread_lands_on_the_rows_home_side(self):
        book = {
            "key": "draftkings",
            "markets": [
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": VIEIRA, "point": -1.5, "price": 120},
                        {"name": BRYCZEK, "point": 1.5, "price": -140},
                    ],
                }
            ],
        }
        oriented = _orient_feed_to_row(_feed(home=BRYCZEK, away=VIEIRA), VIEIRA, BRYCZEK)
        values = _parse_snapshot_values(book, oriented)
        assert values["home_spread"] == -1.5
        assert (values["home_spread_odds"], values["away_spread_odds"]) == (120, -140)


class TestWhenToSwap:
    def test_an_exact_swap_swaps_even_where_the_fuzzy_match_would_not(self):
        """Same-city rivals: `names_match` pairs Lakers with Clippers.

        The fuzzy test alone reads a flipped Lakers/Clippers feed as already in
        the row's orientation (every cross pair "matches"), so exact equality
        has to decide first or the one case this is for stays inverted.
        """
        feed = {"home_team": "Los Angeles Clippers", "away_team": "Los Angeles Lakers"}
        out = _orient_feed_to_row(feed, "Los Angeles Lakers", "Los Angeles Clippers")
        assert (out["home_team"], out["away_team"]) == (
            "Los Angeles Lakers",
            "Los Angeles Clippers",
        )

    def test_same_city_rivals_in_the_rows_orientation_do_not_swap(self):
        feed = {"home_team": "Los Angeles Lakers", "away_team": "Los Angeles Clippers"}
        assert _orient_feed_to_row(feed, "Los Angeles Lakers", "Los Angeles Clippers") is feed

    def test_a_spelling_difference_still_orients(self):
        """A row named by another provider: the fuzzy arm, swapped."""
        feed = {"home_team": "Boston Celtics", "away_team": "LA Clippers"}
        out = _orient_feed_to_row(feed, "Los Angeles Clippers", "Celtics")
        assert (out["home_team"], out["away_team"]) == ("LA Clippers", "Boston Celtics")

    def test_a_spelling_difference_in_the_rows_orientation_does_not_swap(self):
        feed = {"home_team": "LA Clippers", "away_team": "Boston Celtics"}
        assert _orient_feed_to_row(feed, "Los Angeles Clippers", "Celtics") is feed

    def test_a_fuzzy_match_both_ways_keeps_the_rows_orientation(self):
        """Abbreviated same-city rivals fuzzy-match in BOTH orientations.

        Neither pair is exact, so only the fuzzy arm can decide, and it must
        not swap a feed that already matches the row's own orientation.
        """
        feed = {"home_team": "LA Lakers", "away_team": "LA Clippers"}
        assert _orient_feed_to_row(feed, "Los Angeles Lakers", "Los Angeles Clippers") is feed

    def test_names_that_match_neither_way_are_left_alone(self):
        feed = {"home_team": "Alpha", "away_team": "Beta"}
        assert _orient_feed_to_row(feed, "Gamma", "Delta") is feed

    def test_a_row_with_no_names_is_left_alone(self):
        feed = {"home_team": BRYCZEK, "away_team": VIEIRA}
        assert _orient_feed_to_row(feed, None, None) is feed

    def test_the_callers_payload_is_not_mutated(self):
        """`_ingest_event_odds` callers keep using event_data after the call."""
        feed = _feed(home=BRYCZEK, away=VIEIRA)
        out = _orient_feed_to_row(feed, VIEIRA, BRYCZEK)
        assert out is not feed
        assert (feed["home_team"], feed["away_team"]) == (BRYCZEK, VIEIRA)
        assert out["bookmakers"] is feed["bookmakers"]
