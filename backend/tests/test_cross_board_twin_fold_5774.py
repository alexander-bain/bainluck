"""#5774 — an FBS team hosting an FCS team is one game, so it is one card.

Wake Forest v Merrimack, 2026-11-07 20:30Z, was two live cards with the same
63–0 on the board: `15340133` under `americanfootball_ncaaf` (ESPN-anchored, the
Odds API's FBS id) and `15343739` under `americanfootball_ncaaf_fcs` (the Odds
API's FCS id, created that morning, 91 Polymarket markets). `league_identity`
keeps the FCS key its own league on purpose, so the strict twin key put the two
rows in two groups and every list surface served both.

These drive the real fold, and the real page-side candidate read over SQLite:

  A  the specimen folds to one card: the anchored row survives and carries the
     other row's venue;
  B  nothing else folds: another minute, other clubs, two ESPN ids, a row with
     no sport loaded, and FCS-only or FBS-only pairs keep today's answer;
  C  the survivor's page reads the absorbed row (its markets), the loser's page
     absorbs nothing, and a third league is never a candidate.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, selectinload


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.event_twin_fold import (  # noqa: E402
    CROSS_BOARD_TWIN_KEYS,
    cross_board_identity,
    fold_twin_events,
)
from tests.test_survivor_page_reads_absorbed_twin_3391 import _SyncAsAsync  # noqa: E402

KICKOFF = datetime(2026, 11, 7, 20, 30, tzinfo=timezone.utc)
FBS, FCS, NFL = "americanfootball_ncaaf", "americanfootball_ncaaf_fcs", "americanfootball_nfl"
S_FBS, S_FCS, S_NFL = 101, 102, 103
FBS_ROW, FCS_ROW = 15340133, 15343739
WAKE, MERRIMACK = "Wake Forest Demon Deacons", "Merrimack Warriors"
POLYMARKET = {"value": 0.999, "updated_at": "2026-11-07T23:30:00+00:00"}
ESPN = {"value": 0.998, "updated_at": "2026-11-07T23:31:00+00:00"}


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads (see #5918's file for why not a MagicMock)."""

    def __init__(self, id, home, away, *, sport_key, sport_id, commence_time=KICKOFF,
                 home_score=77, away_score=0, espn_id=None, external_id=None, sources=None):
        self.id = id
        self.sport_id = sport_id
        if sport_key is not None:
            self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = "espn" if espn_id else "odds_api"
        self.win_probability_sources = sources
        self.status = "completed"


def _fbs(**kw):
    fields = dict(sport_key=FBS, sport_id=S_FBS, espn_id="401858290",
                  external_id="db87d6d1c7367ec043155f226c12ebbc", sources={"espn": ESPN})
    fields.update(kw)
    return _Row(FBS_ROW, WAKE, MERRIMACK, **fields)


def _fcs(**kw):
    fields = dict(sport_key=FCS, sport_id=S_FCS,
                  external_id="45c39b58fedcd1ce96ef9c8a8119ee39", sources={"polymarket": POLYMARKET})
    fields.update(kw)
    return _Row(FCS_ROW, WAKE, MERRIMACK, **fields)


def _ids(result):
    return [row.id for row in result.events]


class TestTheSpecimenIsOneCard:
    def test_the_two_boards_fold_to_one_card(self):
        result = fold_twin_events([_fbs(), _fcs()])
        assert _ids(result) == [FBS_ROW]
        assert result.dropped_ids == [FCS_ROW]
        assert result.survivor_of == {FCS_ROW: FBS_ROW}

    def test_the_card_carries_the_other_boards_venue(self):
        """The blend is the product: the FCS row's Polymarket reading is not lost."""
        merged = fold_twin_events([_fbs(), _fcs()]).merged_sources[FBS_ROW]
        assert merged["polymarket"] == POLYMARKET and merged["espn"] == ESPN

    def test_the_order_the_rows_arrive_in_does_not_change_the_survivor(self):
        assert _ids(fold_twin_events([_fcs(), _fbs()])) == [FBS_ROW]

    def test_the_survivor_is_the_anchored_row_even_when_the_other_has_more_venues(self):
        """`twin_identity_rank`, unchanged: the ESPN-anchored row is the one the page,
        the chart and settlement reach."""
        richer = _fcs(sources={"polymarket": POLYMARKET, "kalshi": POLYMARKET, "betting": POLYMARKET})
        assert _ids(fold_twin_events([_fbs(), richer])) == [FBS_ROW]


class TestNothingElseFolds:
    def test_another_minute_keeps_its_own_card(self):
        later = _fcs(commence_time=KICKOFF + timedelta(minutes=1))
        assert sorted(_ids(fold_twin_events([_fbs(), later]))) == [FBS_ROW, FCS_ROW]

    def test_another_game_at_the_same_minute_keeps_its_own_card(self):
        other = _Row(15343740, "Elon Phoenix", "Merrimack Warriors", sport_key=FCS, sport_id=S_FCS,
                     external_id="aa")
        assert sorted(_ids(fold_twin_events([_fbs(), other]))) == [FBS_ROW, 15343740]

    def test_two_espn_ids_are_two_games(self):
        both_anchored = _fcs(espn_id="401858999")
        assert sorted(_ids(fold_twin_events([_fbs(), both_anchored]))) == [FBS_ROW, FCS_ROW]

    def test_with_no_sport_loaded_the_pair_still_serves_two_cards(self):
        """The strawman: the merge reads the board from the row's sport, so a row
        whose sport was not loaded keys on `sport_id` and is never joined."""
        result = fold_twin_events([_fbs(sport_key=None), _fcs(sport_key=None)])
        assert sorted(_ids(result)) == [FBS_ROW, FCS_ROW]

    def test_an_fcs_row_alone_is_untouched(self):
        assert _ids(fold_twin_events([_fcs()])) == [FCS_ROW]

    def test_another_league_never_joins(self):
        nfl = _Row(15343741, WAKE, MERRIMACK, sport_key=NFL, sport_id=S_NFL, external_id="nfl")
        assert sorted(_ids(fold_twin_events([_fcs(), nfl]))) == [FCS_ROW, 15343741]

    def test_the_fbs_board_still_folds_its_own_twins(self):
        twin = _Row(15340134, WAKE, MERRIMACK, sport_key=FBS, sport_id=S_FBS, external_id="x")
        assert _ids(fold_twin_events([_fbs(), twin])) == [FBS_ROW]

    def test_only_the_fcs_board_is_aliased(self):
        assert CROSS_BOARD_TWIN_KEYS == {FCS: FBS}
        assert cross_board_identity(FCS) == "football/college-football"
        assert cross_board_identity(FBS) is None and cross_board_identity(None) is None


def _engine():
    from app.models.models import FuturesMarket

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_FBS, key=FBS, name="NCAAF"))
        s.add(Sport(id=S_FCS, key=FCS, name="NCAAF FCS"))
        s.add(Sport(id=S_NFL, key=NFL, name="NFL"))
        common = dict(home_team_name=WAKE, away_team_name=MERRIMACK, commence_time=KICKOFF,
                      status="completed", home_score=77, away_score=0)
        s.add(Event(id=FBS_ROW, sport_id=S_FBS, espn_id="401858290", commence_time_source="espn",
                    external_id="db87d6d1c7367ec043155f226c12ebbc",
                    win_probability_sources={"espn": ESPN}, **common))
        s.add(Event(id=FCS_ROW, sport_id=S_FCS, commence_time_source="odds_api",
                    external_id="45c39b58fedcd1ce96ef9c8a8119ee39",
                    win_probability_sources={"polymarket": POLYMARKET}, **common))
        s.add(Event(id=15343741, sport_id=S_NFL, commence_time_source="odds_api",
                    external_id="nfl-row", **common))
        s.add(FuturesMarket(id=9774, event_id=FCS_ROW, sport_id=S_FCS, source="polymarket",
                            external_id="pm-wake-merrimack-total", name="Wake Forest vs Merrimack - Total",
                            category="game", llm_sport_category="americanfootball",
                            market_type="game_prop", status="open"))
        s.commit()
    return eng


def _absorbed(eng, event_id):
    from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        event = asyncio.run(
            db.execute(select(Event).options(selectinload(Event.sport)).where(Event.id == event_id))
        ).scalar_one()
        return sorted(r.id for r in asyncio.run(serve_fold_absorbed_rows(db, event)))


class TestTheSurvivorsPageReadsTheOtherBoard:
    def test_the_survivors_page_absorbs_the_fcs_row(self):
        """The card opens onto the game's markets, which live on the FCS row."""
        assert _absorbed(_engine(), FBS_ROW) == [FCS_ROW]

    def test_the_losers_own_page_absorbs_nothing(self):
        assert _absorbed(_engine(), FCS_ROW) == []

    def test_the_fcs_board_reads_the_fbs_board_as_a_candidate(self):
        from app.utils.serve_fold_absorbed import _foldable_sport_ids

        eng = _engine()
        with Session(eng) as s:
            db = _SyncAsAsync(s)
            assert sorted(asyncio.run(_foldable_sport_ids(db, FCS))) == [S_FBS, S_FCS]
            assert sorted(asyncio.run(_foldable_sport_ids(db, FBS))) == [S_FBS, S_FCS]
            assert asyncio.run(_foldable_sport_ids(db, NFL)) == [S_NFL]
