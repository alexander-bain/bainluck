"""#2593 — a team's championship path stops printing another LEAGUE's title odds.

WHAT A READER SAW (production, 2026-09-27 13:18Z, 390px): the Seattle Storm's page
(WNBA, 8-36) read "Championship path — Win Conference 20% → Win Championship <1%".
The 20% is Kalshi's "West Coast Conference Men's Tournament Champion" (market
59164893, KXNCAAMBWCC-27), whose "Seattle" leg — Seattle U — was linked to the
Storm by city name. Both sides say ``basketball``, so the sport check shipped in
PR #9126 (``link_crosses_sport``) passes it. The Connecticut Sun printed the NEC
men's tournament the same way, and the Washington Commanders' path was EMPTY:
their tier-1 candidates were the NFL Super Bowl price and the College Football
National Championship's "Washington" leg, which disagree, so the tier was
withheld (#1752).

``link_crosses_league`` reads the league off the market's own venue id — a Kalshi
series, an Odds API outright key — and refuses a link whose league differs from
the team's, for one-league sports only. The fixtures below are the stored shapes
read off production (db-query 2026-09-27).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import teams as teams_route
from app.utils import market_team_sport as mts
from app.utils.sport_keys import get_sport_key_from_ticker, league_family_identity


def _market(mid, name, source, external_id, *, tier, category="basketball"):
    return SimpleNamespace(
        id=mid, name=name, source=source, external_id=external_id,
        llm_sport_category=category, market_tier=tier,
        group_id=f"g:{mid}", canonical_market_key=None,
    )


def _outcome(oid, prob, team_id):
    return SimpleNamespace(
        id=oid, current_probability=prob, rank=1, probability_change_24h=None,
        team_id=team_id,
    )


def _result(rows):
    res = MagicMock()
    res.all.return_value = list(rows)
    return res


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt, *a, **k):
        return _result(self.rows)


async def _path(team_id, sport_key, rows):
    return await teams_route._get_championship_path(
        team_id, _DB(rows), league_slug=None, team_sport_key=sport_key,
    )


def _ids(path):
    return [(e["tier"], e["market_id"]) for e in path]


# ── The Storm: the specimen ───────────────────────────────────────────────────
STORM = 13415
WNBA_TITLE = _market(9413479, "WNBA: 2026 Champion", "polymarket", "350828", tier=1)
WCC_MENS = _market(
    59164893, "West Coast Conference Men's Tournament Champion", "kalshi",
    "KXNCAAMBWCC-27", tier=2,
)
STORM_ROWS = [(_outcome(1, 0.001, STORM), WNBA_TITLE), (_outcome(2, 0.2, STORM), WCC_MENS)]


async def test_the_storm_stops_showing_seattle_us_mens_tournament_as_its_conference():
    path = await _path(STORM, "basketball_wnba", STORM_ROWS)
    assert _ids(path) == [(1, WNBA_TITLE.id)], path


async def test_without_the_league_check_the_storm_prints_win_conference_20():
    """STRAWMAN: the fixture carries the defect — with the check severed the
    college men's leg is the Storm's "Conference" step, as on production."""
    with patch.object(teams_route, "link_crosses_league", lambda *a, **k: False):
        path = await _path(STORM, "basketball_wnba", STORM_ROWS)
    assert (2, WCC_MENS.id) in _ids(path), path
    assert next(e for e in path if e["tier"] == 2)["probability"] == 0.2


# ── The Commanders: a withheld title step comes back ──────────────────────────
COMMANDERS = 17
SUPER_BOWL = _market(
    77, "NFL Super Bowl Winner", "odds_api", "americanfootball_nfl_super_bowl_winner",
    tier=1, category="football",
)
CFB_FINALIST = _market(
    182, "College Football National Championship Qualifiers", "kalshi",
    "KXNCAAFFINALIST-27", tier=1, category="football",
)
COMMANDERS_ROWS = [
    (_outcome(10, 0.0068, COMMANDERS), SUPER_BOWL),
    (_outcome(11, 0.13, COMMANDERS), CFB_FINALIST),  # the Huskies' leg
]


async def test_the_commanders_get_their_super_bowl_number_back():
    path = await _path(COMMANDERS, "americanfootball_nfl", COMMANDERS_ROWS)
    assert [(e["market_id"], e["probability"]) for e in path] == [(SUPER_BOWL.id, 0.0068)]


async def test_without_the_league_check_the_commanders_path_is_empty():
    """STRAWMAN: 0.0068 vs 0.13 disagree beyond the bar, so #1752 withholds the
    tier and the Commanders' page shows no championship path at all."""
    with patch.object(teams_route, "link_crosses_league", lambda *a, **k: False):
        path = await _path(COMMANDERS, "americanfootball_nfl", COMMANDERS_ROWS)
    assert path == []


# ── Odds API outrights carry their league in the id ───────────────────────────
ALABAMA_WOMEN = 79
NCAAB_ODDS = _market(
    3, "NCAAB Championship Winner", "odds_api", "basketball_ncaab_championship_winner",
    tier=1,
)


async def test_the_mens_ncaab_title_leaves_a_womens_team_page():
    path = await _path(ALABAMA_WOMEN, "basketball_wncaab", [(_outcome(20, 0.0138, 79), NCAAB_ODDS)])
    assert path == []


async def test_the_mens_ncaab_title_stays_on_the_mens_team_page():
    path = await _path(672, "basketball_ncaab", [(_outcome(21, 0.0138, 672), NCAAB_ODDS)])
    assert _ids(path) == [(1, NCAAB_ODDS.id)]


# ── The unmasking guard: series the ticker maps do not carry ──────────────────
# Refusing a mapped wrong-league candidate can CLEAR a tier that was withheld
# only because it disagreed with an unmapped one — which then prints. Measured on
# the 2026-09-27 replay before the supplement existed.
HOUSTON_CFB = 15300
AFC_CHAMP = _market(31616, "AFC Championship Winner", "kalshi", "KXNFLAFCCHAMP-27",
                    tier=2, category="football")
DIV_UNDEFEATED = _market(
    60473206, "Pro Football Teams to go Undefeated in their Division", "kalshi",
    "KXNFLDIVUNDEFEATED-27", tier=4, category="football",
)
PLAYOFF = _market(62679, "Pro Football Playoff Qualifiers", "kalshi", "KXNFLPLAYOFF-27",
                  tier=4, category="football")


async def test_no_nfl_row_is_unmasked_on_a_college_football_page():
    rows = [
        (_outcome(30, 0.065, HOUSTON_CFB), AFC_CHAMP),
        (_outcome(31, 0.11, HOUSTON_CFB), DIV_UNDEFEATED),
        (_outcome(32, 0.525, HOUSTON_CFB), PLAYOFF),
    ]
    path = await _path(HOUSTON_CFB, "americanfootball_ncaaf", rows)
    assert path == [], path


async def test_the_mens_tournament_rounds_leave_a_womens_page():
    baylor_women = 194
    qualifiers = _market(13785914, "Men's Championship Game Qualifiers", "kalshi",
                         "KXMARMADROUND-27T2", tier=1)
    uac = _market(59164888, "United Athletic Conference Men's Tournament Champion",
                  "kalshi", "KXNCAAMBUAC-27", tier=2)
    rows = [(_outcome(40, 0.28, baylor_women), qualifiers), (_outcome(41, 0.25, baylor_women), uac)]
    assert await _path(baylor_women, "basketball_wncaab", rows) == []


def test_every_supplement_series_is_unmapped_or_agrees_with_the_ticker_maps():
    """The supplement is read only when the ticker maps answer None. If a series
    is later mapped there, the two must name the same league — otherwise this
    file's table would be silently shadowed by a different answer."""
    for series, sport_key in mts._SERIES_LEAGUE_SUPPLEMENT.items():
        mapped = get_sport_key_from_ticker(f"{series.upper()}-27")
        if mapped is not None:
            assert league_family_identity(mapped) == league_family_identity(sport_key), series


def test_the_supplement_matches_a_whole_series_not_a_stem():
    assert mts._series_league_supplement("KXNFLSEED-27AFC7") == "americanfootball_nfl"
    assert mts._series_league_supplement("KXNFLSEEDX-27") is None
    assert mts._series_league_supplement("KXNFLX-26") is None


# ── Controls: what the check must NOT refuse ──────────────────────────────────
async def test_a_same_league_kalshi_market_stays():
    grizzlies = 5
    west = _market(52755681, "Pro Basketball Western Conference Champion", "kalshi",
                   "KXNBAWEST-27", tier=2)
    path = await _path(grizzlies, "basketball_nba", [(_outcome(50, 0.01, grizzlies), west)])
    assert _ids(path) == [(2, west.id)]


async def test_an_unmapped_series_is_no_claim():
    mystery = _market(1, "Some Conference Champion", "kalshi", "KXSOMETHINGNEW-27", tier=2)
    path = await _path(STORM, "basketball_wnba", [(_outcome(60, 0.2, STORM), mystery)])
    assert _ids(path) == [(2, 1)]


async def test_an_odds_api_key_naming_no_known_league_is_no_claim():
    """Only a base the league map knows is a league; anything else fails open."""
    unknown = _market(4, "New League Championship Winner", "odds_api",
                      "basketball_newleague_championship_winner", tier=1)
    path = await _path(5, "basketball_nba", [(_outcome(80, 0.02, 5), unknown)])
    assert _ids(path) == [(1, 4)]


async def test_a_soccer_club_keeps_a_continental_competition():
    """Soccer is not a one-league sport: a club's path may hold the Champions
    League beside its league."""
    ucl = _market(2, "Champions League Winner", "kalshi", "KXUCL-26", tier=1, category="soccer")
    assert get_sport_key_from_ticker("KXUCL-26")  # the control only testifies if mapped
    path = await _path(359, "soccer_epl", [(_outcome(70, 0.2, 359), ucl)])
    assert _ids(path) == [(1, 2)]


async def test_a_caller_with_no_sport_key_keeps_the_old_path():
    path = await _path(STORM, None, STORM_ROWS)
    assert (2, WCC_MENS.id) in _ids(path)


def test_a_preseason_team_key_is_the_same_league():
    assert not mts.link_crosses_league("kalshi", "KXNBAWEST-27", "basketball_nba_preseason")


# ── Title-question fragments added alongside (#1752's predicate) ──────────────
def test_realignment_and_host_city_questions_are_not_title_steps():
    assert not teams_route._answers_its_tier("College Football: Teams to leave their Conference")
    assert not teams_route._answers_its_tier("Who will host the 2031 Pro Football Championship?")
    assert teams_route._answers_its_tier("NCAA Football 2026 Big 12 Conference: Winner")
