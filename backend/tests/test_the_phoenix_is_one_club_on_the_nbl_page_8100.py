"""Guard: Perth Wildcats v S.E. Melbourne Phoenix is one card, with Polymarket (#8100).

THE PAGE. ``/api/events/search?q=Perth Wildcats`` on 2026-09-30 served Friday's
game (2026-10-02 11:30Z) twice, adjacent:

    15319245  basketball_other  Perth Wildcats v South East Melbourne Phoenix  11:30Z  polymarket_venue, id-less, 4 markets
    15320512  basketball_nbl    Perth Wildcats v S.E. Melbourne Phoenix        11:36Z  Odds API (external_id), sportsbooks only

The other nine NBL clubs do not do this: Tasmania v Melbourne (15318654 +
15320510, six minutes apart) is one card carrying Kalshi, Polymarket and
sportsbooks, because the Polymarket row was placed in ``basketball_nbl`` and
the anchored-claim kickoff pass joined it. The Phoenix is the one club whose
Polymarket spelling is not our ``teams`` spelling, so it missed placement, the
fold's squashed-name key and ``_fuzzy_team_match``.

WHAT EACH ARM DEFENDS:

* the ship: the pair, once both rows sit in ``basketball_nbl``, folds to the
  Odds API row and that card carries the Polymarket reading;
* the table is what does it (mutant: an empty table leaves two cards);
* the one-off repair is needed: the same pair across the catch-all stays two
  cards, because the kickoff pass is same-league and a priced shadow is only
  folded at its own minute;
* placement: the next Phoenix row lands in ``basketball_nbl`` (mutant: empty
  table leaves it in the catch-all);
* nothing else moves: Phoenix Suns / Mercury / Hagen, bare "Phoenix", and the
  other NBL clubs squash and match exactly as before;
* the repair script selects only a Phoenix venue spelling against an NBL club,
  and refuses off production.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils import event_twin_fold, venue_club_spellings
from app.utils.event_twin_fold import fold_twin_events, team_name_fold_key
from app.utils.prediction_market_matching import _fuzzy_team_match
from app.tasks.prediction_market_matching import placeable_league_for_matchup
from scripts import repair_8100_phoenix_rows_in_the_catchall as repair

TIP_OFF = datetime(2026, 10, 2, 11, 30, tzinfo=timezone.utc)
ODDS_API_DRIFT = timedelta(minutes=6)

NBL = "basketball_nbl"
CATCHALL = "basketball_other"
POLYMARKET_PHOENIX = "South East Melbourne Phoenix"
OUR_PHOENIX = "S.E. Melbourne Phoenix"

NBL_CLUBS = (
    "Adelaide 36ers", "Brisbane Bullets", "Cairns Taipans", "Illawarra Hawks",
    "Melbourne United", "New Zealand Breakers", "Perth Wildcats",
    OUR_PHOENIX, "Sydney Kings", "Tasmania JackJumpers",
)


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of ``Event`` the fold reads. Not a MagicMock: an auto-attribute
    mock makes every ``external_id`` truthy, and that truthiness is the licence."""

    def __init__(self, id, *, sport_key, home, away, commence_time,
                 external_id=None, sources=None, status="scheduled"):
        self.id = id
        self.sport_id = {NBL: 7101, CATCHALL: 7199}[sport_key]
        self.sport = _Sport(self.sport_id, sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.home_score = None
        self.away_score = None
        self.espn_id = None
        self.external_id = external_id
        self.win_probability_sources = sources
        self.status = status
        self.opening_home_probability = None
        self.opening_away_probability = None


def _specimen(claim_sport=NBL):
    """15319245 and 15320512 as read on production 2026-09-30 14:2xZ."""
    claim = _Row(
        15319245, sport_key=claim_sport,
        home="Perth Wildcats", away=POLYMARKET_PHOENIX,
        commence_time=TIP_OFF, sources={"polymarket": 0.49},
    )
    anchored = _Row(
        15320512, sport_key=NBL,
        home="Perth Wildcats", away=OUR_PHOENIX,
        commence_time=TIP_OFF + ODDS_API_DRIFT,
        external_id="odds-api-15320512", sources={"betting_book_count": 7},
    )
    return claim, anchored


class TestTheShip:
    def test_the_pair_is_one_card_on_the_odds_api_row(self):
        claim, anchored = _specimen()

        result = fold_twin_events([claim, anchored])

        assert [e.id for e in result.events] == [15320512]
        assert result.dropped_ids == [15319245]

    def test_the_one_card_carries_polymarket(self):
        claim, anchored = _specimen()

        result = fold_twin_events([claim, anchored])

        assert result.merged_sources[15320512].get("polymarket") == 0.49

    def test_without_the_table_entry_it_is_two_cards(self, monkeypatch):
        """Mutant: the table is the only thing joining the two spellings."""
        monkeypatch.setattr(event_twin_fold, "_VENUE_SQUASHED", {})
        claim, anchored = _specimen()

        assert len(fold_twin_events([claim, anchored]).events) == 2

    def test_left_in_the_catchall_it_is_still_two_cards(self):
        """Why the repair script exists. The kickoff pass is same-league, and a
        catch-all shadow that still holds its price is only folded at its own
        minute. 15319245 sits in ``basketball_other`` until it is moved."""
        claim, anchored = _specimen(claim_sport=CATCHALL)

        assert len(fold_twin_events([claim, anchored]).events) == 2


class TestTheSquashMovesOnlyTheNamedClub:
    def test_both_spellings_squash_alike(self):
        assert team_name_fold_key(POLYMARKET_PHOENIX) == team_name_fold_key(OUR_PHOENIX)
        assert team_name_fold_key(OUR_PHOENIX) == "semelbournephoenix"

    @pytest.mark.parametrize("name,squashed", [
        ("Phoenix Suns", "phoenixsuns"),
        ("Phoenix Mercury", "phoenixmercury"),
        ("Phoenix Hagen", "phoenixhagen"),
        ("Phoenix", "phoenix"),
        ("South East Melbourne", "southeastmelbourne"),
        ("Melbourne United", "melbourneunited"),
        ("South East Melbourne Phoenix Reserves", "southeastmelbournephoenixreserves"),
    ])
    def test_every_other_name_squashes_as_before(self, name, squashed):
        assert team_name_fold_key(name) == squashed


class TestTheMatcherNamesTheClub:
    def test_both_directions_match(self):
        assert _fuzzy_team_match(POLYMARKET_PHOENIX, OUR_PHOENIX)
        assert _fuzzy_team_match(OUR_PHOENIX, POLYMARKET_PHOENIX)

    @pytest.mark.parametrize("other", [
        "Phoenix Suns", "Phoenix Mercury", "Phoenix Hagen", "Melbourne United",
    ])
    def test_it_reaches_no_other_club(self, other):
        assert not _fuzzy_team_match(POLYMARKET_PHOENIX, other)


class _TeamRow:
    def __init__(self, name, league):
        self._values = (name, None, league)

    def __iter__(self):
        return iter(self._values)


class _FakeSession:
    """Club arm first, alias arm second, as ``leagues_by_side_for_matchup`` asks."""

    def __init__(self):
        self._arms = [
            [_TeamRow(club, NBL) for club in NBL_CLUBS]
            + [_TeamRow("Phoenix Suns", "basketball_nba")],
            [],
        ]
        self.calls = 0

    async def execute(self, statement):
        arm = self._arms[min(self.calls, len(self._arms) - 1)]
        self.calls += 1
        return list(arm)


class TestTheNextPhoenixRowIsPlacedInTheNbl:
    @pytest.mark.asyncio
    async def test_perth_v_the_phoenix_is_placed(self):
        assert await placeable_league_for_matchup(
            _FakeSession(), "Perth Wildcats", POLYMARKET_PHOENIX, CATCHALL,
        ) == NBL

    @pytest.mark.asyncio
    async def test_without_the_table_entry_it_stays_in_the_catchall(self, monkeypatch):
        """Mutant: the measured production state before this change."""
        monkeypatch.setattr(venue_club_spellings, "VENUE_CLUB_SPELLINGS", {})
        assert await placeable_league_for_matchup(
            _FakeSession(), "Perth Wildcats", POLYMARKET_PHOENIX, CATCHALL,
        ) is None

    @pytest.mark.asyncio
    async def test_a_club_the_table_does_not_name_is_unchanged(self):
        assert await placeable_league_for_matchup(
            _FakeSession(), "Perth Wildcats", "Phoenix", CATCHALL,
        ) is None


class TestTheTable:
    def test_entries_are_whole_names_that_differ(self):
        for venue, ours in venue_club_spellings.VENUE_CLUB_SPELLINGS.items():
            assert venue != ours
            assert len(venue.split()) >= 2 and len(ours.split()) >= 2
            assert team_name_fold_key(venue) == team_name_fold_key(ours)

    def test_no_venue_spelling_is_another_entrys_club(self):
        table = venue_club_spellings.VENUE_CLUB_SPELLINGS
        assert not set(table) & set(table.values())

    def test_spellings_of_reads_our_name_case_insensitively(self):
        assert venue_club_spellings.venue_spellings_of("s.e. melbourne phoenix") == {
            POLYMARKET_PHOENIX.lower()
        }
        assert venue_club_spellings.venue_spellings_of("Perth Wildcats") == frozenset()
        assert venue_club_spellings.venue_spellings_of(None) == frozenset()


class TestTheRepairSelectsOnlyThePhoenixRows:
    LEAGUE_TEAMS = set(NBL_CLUBS)

    @pytest.mark.parametrize("home,away", [
        ("Perth Wildcats", POLYMARKET_PHOENIX),   # 15319245
        (POLYMARKET_PHOENIX, "Illawarra Hawks"),  # 15319859
    ])
    def test_the_two_production_rows_are_eligible(self, home, away):
        assert repair.eligible(home, away, self.LEAGUE_TEAMS)

    @pytest.mark.parametrize("home,away", [
        ("Perth Wildcats", "Adelaide 36ers"),       # already placed in the NBL
        ("Phoenix Mercury", "Dallas Wings"),        # 15306453, WNBA in the catch-all
        ("Phoenix Hagen", "Ratiopharm Ulm"),        # 15314864, German league
        (POLYMARKET_PHOENIX, "Phoenix Suns"),       # the other side is not NBL
        ("Perth Wildcats", OUR_PHOENIX),            # our spelling: not a venue mint's name
    ])
    def test_nothing_else_is(self, home, away):
        assert not repair.eligible(home, away, self.LEAGUE_TEAMS)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": ""})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
