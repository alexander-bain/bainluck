"""#12368: a live NFL game keeps a Discover seat after kickoff.

THE READER'S PAGE (Sun Nov 8, 10:16-10:21 AM PT): seven NFL Week 9 games were
live in the first quarter, and ``GET /api/feed?limit=25&event_pct=0.15`` seated
none of them in its top 20. Its three event seats, 11-13, went to Princeton @
Siena (NCAAB, 15343879), Panthers @ Bruins (NHL, 15343803) and Aston Villa @
Manchester United (EPL, 15335247).

WHERE THOSE SEATS COME FROM. ``compose_lead`` puts up to three live games at the
front of Discover, and #5105's opening seating then moves those three to seats
11-13. Until this fix the three were picked by rank alone. Before kickoff #4898
protects up to three marquee games into the lead; at kickoff that protection
ends and each game competes on its live score, which reads drama (closeness,
lead changes, momentum) that a first-quarter game has barely had time to make.
Sunday's 7:15 AM ranking snapshot has the shape: the live Bengals @ Falcons game
served at 35 in seat 12, behind a live EPL match served at 97.

The page did not record the cards' scores, so the ranks below are illustrative.
The lead picked by rank alone, so ANY three live games ranked above the NFL
games took all three seats, and on master these fixtures reproduce the reported
seats exactly. The tags are the ones the cards serve, computed from the sport
key when the card is built (``compute_event_tags``): the NFL, NHL and EPL cards
carry ``tier:1`` and the NCAAB card ``tier:2``. So with the fix the NHL and EPL
games keep two seats on rank, and the third goes to an NFL game instead of
Princeton @ Siena.

THE FIX keeps rank as the order within each group, and puts a live tier-1 game
ahead of a lower-tier one: the marquee line the arms on both sides of the live
window already draw (#4898 before kickoff, #4681 after the final). No score is
touched and nothing is dropped.
"""

from datetime import datetime, timedelta, timezone

from app.routes.feed import _discover_event_is_marquee
from app.utils import tonights_games
from app.utils.discover_opening_seating import OPENING_SEATS, seat_opening
from app.utils.event_taxonomy import compute_event_tags
from app.utils.tonights_games import compose_lead

# Sun Nov 8, 10:16 AM PT: the reader's page. Every fixture offsets from this and
# every pass is handed it (gotcha #44).
NOW = datetime(2026, 11, 8, 18, 16, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(minutes=16)

NFL = [
    (14780573, "Philadelphia Eagles", "New York Giants"),
    (14969876, "New Orleans Saints", "Cleveland Browns"),
    (14969877, "Indianapolis Colts", "Dallas Cowboys"),
    (14969878, "Miami Dolphins", "Detroit Lions"),
    (14969879, "Kansas City Chiefs", "New York Jets"),
    (14969880, "Washington Commanders", "Los Angeles Rams"),
    (15184631, "Carolina Panthers", "Denver Broncos"),
]
NFL_IDS = {event_id for event_id, _, _ in NFL}
PRINCETON, BRUINS, VILLA = 15343879, 15343803, 15335247


def live_game(event_id, home, away, *, sport, rank, crests=True, scores=(0, 0)):
    data = {
        "id": event_id,
        "sport": sport,
        "status": "live",
        "home_team": home,
        "away_team": away,
        "home_score": scores[0],
        "away_score": scores[1],
        "commence_time": KICKOFF.isoformat().replace("+00:00", "Z"),
        # The tags the card serves: computed from the sport key at build time.
        "event_tags": compute_event_tags(
            sport_key=sport, status="live", commence_time=KICKOFF
        ),
    }
    if crests:
        data["home_team_data"] = {"logo_small": "h"}
        data["away_team_data"] = {"logo_small": "a"}
    return {
        "type": "event",
        "score": min(98, int(rank)),
        "_rank_score": float(rank),
        "headline": "Live",
        "data": data,
    }


def nfl_games(rank=35):
    # 35 is the Discover cap a non-exceptional live game is held to.
    return [
        live_game(event_id, home, away, sport="americanfootball_nfl", rank=rank)
        for event_id, home, away in NFL
    ]


def princeton(rank=104):
    return live_game(
        PRINCETON,
        "Siena Saints",
        "Princeton Tigers",
        sport="basketball_ncaab",
        rank=rank,
    )


def bruins(rank=101):
    return live_game(
        BRUINS,
        "Boston Bruins",
        "Florida Panthers",
        sport="icehockey_nhl",
        rank=rank,
    )


def villa(rank=97):
    return live_game(
        VILLA,
        "Manchester United",
        "Aston Villa",
        sport="soccer_epl",
        rank=rank,
    )


def futures(n=20):
    return [
        {
            "type": "futures",
            "score": int(98 - i * 0.5),
            "_rank_score": 98.0 - i * 0.5,
            "data": {"id": 9000 + i, "name": f"market {i}"},
        }
        for i in range(n)
    ]


def ranked(cards):
    return sorted(cards, key=lambda it: -it["_rank_score"])


def ids(items):
    return [it["data"]["id"] for it in items]


def reported_deck():
    """The deck ``compose_lead`` receives: the first page as the ranker left it
    (three sports cards among twenty futures), the NFL games below it."""
    return ranked(futures() + [princeton(), bruins(), villa()]) + nfl_games()


def served(deck):
    lead = compose_lead(deck, NOW, include_tonights_games=True)
    outcome = seat_opening(lead, now=NOW)
    assert outcome.changed, outcome.detail
    return outcome.items


class TestTheReportedPage:
    def test_a_live_nfl_game_takes_a_live_seat(self):
        page = served(reported_deck())
        seats_11_to_13 = ids(page[OPENING_SEATS : OPENING_SEATS + 3])
        assert seats_11_to_13 == [BRUINS, VILLA, 14780573], seats_11_to_13

    def test_the_top_twenty_holds_a_live_nfl_game(self):
        page = served(reported_deck())
        assert NFL_IDS & set(ids(page[:20])), ids(page[:20])

    def test_the_lower_tier_games_stay_on_the_page(self):
        # Promote, never drop: they leave the lead, not the deck, and here they
        # still sit inside the first page, right behind it.
        deck = reported_deck()
        page = served(deck)
        assert sorted(ids(page)) == sorted(ids(deck))
        assert {PRINCETON, BRUINS} <= set(ids(page[:20]))


class TestRankStillDecidesInsideEachGroup:
    def test_among_live_marquee_games_the_higher_rank_leads(self):
        lead = compose_lead([*nfl_games(), villa()], NOW, include_tonights_games=True)
        assert ids(lead[:3]) == [VILLA, 14780573, 14969876]

    def test_with_no_marquee_game_live_the_lead_is_rank_order_as_before(self):
        # Two live WNCAAB games from Mon Nov 9, beside Princeton: all tier 2.
        oklahoma_st = live_game(
            15345289,
            "Oklahoma St Cowgirls",
            "Northwestern St Demons",
            sport="basketball_wncaab",
            rank=35,
        )
        samford = live_game(
            15345290,
            "Samford Bulldogs",
            "UNC Asheville Bulldogs",
            sport="basketball_wncaab",
            rank=92,
        )
        deck = ranked(futures(5) + [oklahoma_st, samford, princeton()])
        lead = compose_lead(deck, NOW, include_tonights_games=True)
        assert ids(lead[:3]) == [PRINCETON, 15345290, 15345289]


class TestEverythingElseIsUnchanged:
    def test_a_marquee_game_still_needs_both_crests_to_lead(self):
        nfl = live_game(
            14780573,
            "Philadelphia Eagles",
            "New York Giants",
            sport="americanfootball_nfl",
            rank=35,
            crests=False,
        )
        lead = compose_lead([princeton(), nfl], NOW, include_tonights_games=True)
        assert ids(lead) == [PRINCETON, 14780573]

    def test_a_marquee_game_still_needs_a_score_to_lead(self):
        nfl = live_game(
            14780573,
            "Philadelphia Eagles",
            "New York Giants",
            sport="americanfootball_nfl",
            rank=35,
            scores=(None, None),
        )
        lead = compose_lead([princeton(), nfl], NOW, include_tonights_games=True)
        assert ids(lead) == [PRINCETON, 14780573]

    def test_a_live_game_still_leads_an_upcoming_marquee_game(self):
        upcoming = live_game(
            14969881,
            "Los Angeles Chargers",
            "Houston Texans",
            sport="americanfootball_nfl",
            rank=77,
        )
        upcoming["data"].update(
            status="scheduled",
            home_score=None,
            away_score=None,
            commence_time=(NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        lead = compose_lead([upcoming, princeton()], NOW, include_tonights_games=True)
        assert ids(lead) == [PRINCETON, 14969881]

    def test_no_score_is_touched(self):
        deck = reported_deck()
        before = [(it["score"], it["_rank_score"]) for it in deck]
        compose_lead(deck, NOW, include_tonights_games=True)
        assert [(it["score"], it["_rank_score"]) for it in deck] == before

    def test_the_marquee_line_is_the_one_the_feed_draws(self):
        cards = [
            villa(),
            princeton(),
            *nfl_games()[:1],
            live_game(1, "A", "B", sport="basketball_wncaab", rank=35),
            {"type": "event", "data": {}},
            {"type": "event"},
        ]
        mirrored = [tonights_games._is_marquee_game(c) for c in cards]
        assert mirrored == [_discover_event_is_marquee(c) for c in cards]
        assert mirrored == [True, False, True, False, False, False]


# ── #12368 (b): one lead seat per top-tier league (Fable, 6:03 PM PT Mon Nov 9) ──
#
# Mon Nov 9 at 5:45 PM PT (`GET /api/feed?limit=40&event_pct=0.15`, ranker
# `a8fef3e938a9`): the night's only NFL game, Bills @ Vikings, was live at seat 29.
# Three live NBA games held all three lead seats, at scores 98, 94 and 94; the NFL
# game served at 82. Every one is tier 1, so #12469's marquee group could not
# separate them, and rank alone gave the NBA the whole lead.
LAKERS, CAVALIERS, PACERS, BILLS = 15344868, 15344806, 15344871, 14780576


def monday_night():
    return [
        live_game(LAKERS, "Atlanta Hawks", "Los Angeles Lakers",
                  sport="basketball_nba", rank=98),
        live_game(CAVALIERS, "Charlotte Hornets", "Cleveland Cavaliers",
                  sport="basketball_nba", rank=94),
        live_game(PACERS, "Dallas Mavericks", "Indiana Pacers",
                  sport="basketball_nba", rank=94),
        live_game(BILLS, "Minnesota Vikings", "Buffalo Bills",
                  sport="americanfootball_nfl", rank=82),
    ]


class TestOneLeadSeatPerTopTierLeague:
    def test_the_nights_only_nfl_game_takes_a_lead_seat(self):
        deck = ranked(futures() + monday_night())
        lead = compose_lead(deck, NOW, include_tonights_games=True)
        assert ids(lead[:3]) == [LAKERS, BILLS, CAVALIERS]

    def test_it_lands_in_the_seated_lead_inside_the_top_twenty(self):
        page = served(ranked(futures() + monday_night()))
        seats_11_to_13 = ids(page[OPENING_SEATS : OPENING_SEATS + 3])
        assert BILLS in seats_11_to_13, seats_11_to_13
        assert BILLS in ids(page[:20])

    def test_two_games_from_one_league_keep_their_rank_order(self):
        # NBA's second game still follows its first, and the tie at 94 keeps the
        # feed's own order (Cavaliers before Pacers), exactly as before.
        lead = compose_lead(ranked(monday_night()), NOW, include_tonights_games=True)
        nba = [i for i in ids(lead) if i != BILLS]
        assert nba == [LAKERS, CAVALIERS, PACERS]

    def test_with_one_league_live_it_is_plain_rank_order(self):
        nba_only = [g for g in monday_night() if g["data"]["id"] != BILLS]
        lead = compose_lead(list(reversed(nba_only)), NOW, include_tonights_games=True)
        assert ids(lead) == [LAKERS, PACERS, CAVALIERS]

    def test_sundays_page_is_unchanged(self):
        # Bruins, Villa and one NFL game are each their league's first turn.
        page = served(reported_deck())
        assert ids(page[OPENING_SEATS : OPENING_SEATS + 3]) == [BRUINS, VILLA, 14780573]

    def test_a_lower_tier_game_still_waits_for_every_marquee_game(self):
        # The turn applies inside the marquee group only: a tier-2 game ranked
        # above them all still comes after the NBA's second and third games.
        lead = compose_lead(
            [princeton(rank=120), *monday_night()], NOW,
            include_tonights_games=True, max_lead=5,
        )
        assert ids(lead) == [LAKERS, BILLS, CAVALIERS, PACERS, PRINCETON]
