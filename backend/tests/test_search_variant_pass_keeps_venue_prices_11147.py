"""#11147 — search stops hiding a preseason game's Kalshi + Polymarket row.

Not a regression of #7700: that pass still collapses every NHL preseason twin it
collapsed before. It now declines a pair only when dropping the loser would take
a venue price off the page, and leaves that pair to the twin fold, which unions
the two rows' venues.

Alex's rage shake 177 (2026-10-16 22:14Z, Search tab): "There's a Celtics
preseason game starting in ~50 minutes and it's only matched to the sportsbooks,
not Kalshi or PM." The rows below carry the values production stored for them
(db-query, 2026-10-16 22:5xZ):

    15327537  basketball_nba            23:00Z  espn_id 401898407  kalshi, polymarket, espn_not_started_at
    15330945  basketball_nba_preseason  23:10Z  odds_api           betting, betting_book_count

`/api/events/search?q=celtics` served only 15330945. Real `Event` objects, not
MagicMock, because the fold keys on attributes a MagicMock answers truthily.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models.models import Event, Sport
from app.routes.events import _typeahead_fold_twins
from app.utils import search_fixture_dedup
from app.utils.aggregation import SOURCE_WEIGHTS
from app.utils.event_twin_fold import fold_twin_events
from app.utils.search_fixture_dedup import (
    VENUE_PRICE_SOURCES,
    collapse_duplicate_fixtures,
)

NBA = Sport(id=21, key="basketball_nba", name="NBA", group="Basketball", active=True)
NBA_PRE = Sport(id=22, key="basketball_nba_preseason", name="NBA Preseason",
                group="Basketball", active=True)
NHL = Sport(id=31, key="icehockey_nhl", name="NHL", group="Ice Hockey", active=True)
NHL_PRE = Sport(id=32, key="icehockey_nhl_preseason", name="NHL Preseason",
                group="Ice Hockey", active=True)

TIP = datetime(2026, 10, 16, 23, 0, tzinfo=timezone.utc)


def _event(id, sport, *, commence, sources, espn_id=None, external_id=None,
           source=None, status="scheduled", scores=(None, None),
           home="Philadelphia 76ers", away="Boston Celtics"):
    e = Event(
        id=id,
        sport_id=sport.id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status=status,
        espn_id=espn_id,
        external_id=external_id,
        commence_time_source=source,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
    )
    e.sport = sport
    return e


def _nba_parent():
    return _event(
        15327537, NBA, commence=TIP, espn_id="401898407", source="statpal",
        sources={
            "kalshi": {"value": 0.33},
            "polymarket": {"value": 0.335},
            "espn_not_started_at": "2026-10-16T22:50:00Z",
        },
    )


def _nba_variant():
    return _event(
        15330945, NBA_PRE, commence=TIP + timedelta(minutes=10),
        external_id="304a287828bbf16b32f47afcf2dc0060", source="odds_api",
        sources={"betting": {"value": 0.33}, "betting_book_count": 6},
    )


def _search_chain(rows):
    """What `/api/events/search` runs: the dedup, then the twin fold."""
    kept, _ = collapse_duplicate_fixtures(rows)
    return fold_twin_events(kept)


class TestTheNbaSpecimen:
    def test_the_dedup_leaves_both_rows_for_the_fold(self):
        kept, dropped = collapse_duplicate_fixtures([_nba_variant(), _nba_parent()])
        assert sorted(e.id for e in kept) == [15327537, 15330945]
        assert dropped == 0

    def test_search_serves_one_card_carrying_all_three_venues(self):
        fold = _search_chain([_nba_variant(), _nba_parent()])
        assert [e.id for e in fold.events] == [15327537], (
            "the ESPN-anchored row is the one whose page carries Kalshi and "
            "Polymarket; the fold elects it"
        )
        merged = fold.merged_sources[15327537]
        assert {"kalshi", "polymarket", "betting"} <= set(merged)

    def test_the_typeahead_suggestion_opens_the_priced_page(self):
        kept, _ = collapse_duplicate_fixtures([_nba_variant(), _nba_parent()])
        assert [e.id for e in _typeahead_fold_twins(kept, set())] == [15327537]

    def test_strawman_without_the_hold_the_variant_hides_the_priced_row(self):
        """The defect, reproduced: the guard above must be what keeps the row."""
        with patch.object(search_fixture_dedup, "_hides_a_venue_price",
                          return_value=False):
            fold = _search_chain([_nba_variant(), _nba_parent()])
        assert [e.id for e in fold.events] == [15330945]
        assert "kalshi" not in (fold.events[0].win_probability_sources or {})

    def test_order_independent(self):
        a = _search_chain([_nba_parent(), _nba_variant()])
        b = _search_chain([_nba_variant(), _nba_parent()])
        assert [e.id for e in a.events] == [e.id for e in b.events] == [15327537]


class TestTheNhlShapeIsUnchanged:
    """#7700's direction: prices on the variant, nothing priced on the parent."""

    def _pair(self, parent_sources, variant_sources, status="completed"):
        scores = (2, 4) if status == "completed" else (None, None)
        parent = _event(15312340, NHL, commence=datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
                        espn_id="401800001", status=status, scores=scores,
                        sources=parent_sources, home="Calgary Flames",
                        away="Seattle Kraken")
        variant = _event(15316214, NHL_PRE,
                         commence=datetime(2026, 9, 21, 0, 8, 24, tzinfo=timezone.utc),
                         external_id="abc", status=status, scores=scores,
                         sources=variant_sources, home="Calgary Flames",
                         away="Seattle Kraken")
        return parent, variant

    def test_a_model_only_parent_still_collapses_onto_the_priced_variant(self):
        """Measured 2026-10-16: 12 completed NHL pairs read stat_model vs betting."""
        parent, variant = self._pair({"stat_model": {"value": 0.4}},
                                     {"betting": {"value": 0.41}})
        kept, dropped = collapse_duplicate_fixtures([parent, variant])
        assert [e.id for e in kept] == [15316214]
        assert dropped == 1

    def test_an_unpriced_parent_still_collapses_onto_the_priced_variant(self):
        parent, variant = self._pair(None, {"betting": {"value": 0.41}},
                                     status="scheduled")
        kept, dropped = collapse_duplicate_fixtures([parent, variant])
        assert [e.id for e in kept] == [15316214]
        assert dropped == 1

    def test_a_parent_holding_a_venue_the_variant_lacks_is_unioned_not_hidden(self):
        """Measured 2026-10-16: 5 completed NHL pairs read polymarket vs betting."""
        parent, variant = self._pair(
            {"polymarket": {"value": 0.4}, "stat_model": {"value": 0.4}},
            {"betting": {"value": 0.41}},
        )
        kept, dropped = collapse_duplicate_fixtures([parent, variant])
        assert dropped == 0
        fold = fold_twin_events(kept)
        assert len(fold.events) == 1
        merged = fold.merged_sources[fold.events[0].id]
        assert {"polymarket", "betting"} <= set(merged)


class TestWhatCountsAsAVenuePrice:
    def test_bookkeeping_keys_are_not_prices(self):
        """`betting_book_count` / `espn_not_started_at` must not hold a pair."""
        parent = _event(1, NBA, commence=TIP, espn_id="1",
                        sources={"espn_not_started_at": "x"})
        variant = _event(2, NBA_PRE, commence=TIP + timedelta(minutes=10),
                         sources={"betting": {"value": 0.5}, "betting_book_count": 6})
        kept, dropped = collapse_duplicate_fixtures([parent, variant])
        assert [e.id for e in kept] == [2]
        assert dropped == 1

    def test_an_empty_venue_entry_is_not_a_price(self):
        parent = _event(1, NBA, commence=TIP, espn_id="1",
                        sources={"kalshi": None, "polymarket": {}})
        variant = _event(2, NBA_PRE, commence=TIP + timedelta(minutes=10),
                         sources={"betting": {"value": 0.5}})
        kept, _ = collapse_duplicate_fixtures([parent, variant])
        assert [e.id for e in kept] == [2]

    def test_the_venue_set_is_aggregations_market_sources(self):
        assert VENUE_PRICE_SOURCES <= set(SOURCE_WEIGHTS)
        assert VENUE_PRICE_SOURCES == {"betting", "kalshi", "polymarket"}
