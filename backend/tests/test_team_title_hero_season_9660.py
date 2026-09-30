"""#9660 — a team page's "Championship" hero reads THIS season's title market.

Production, 2026-09-29: the Knicks' hero read "CHAMPIONSHIP 10%" and the
Thunder's 26.5% — Kalshi's "2026 Pro Basketball Cup Champion", the in-season NBA
Cup — and the Celtics had no Championship at all. `_get_championship_path` cut
"future-season" markets at ``now.year`` (2026), and the 2026-27 season's title
markets are named for the year their final is played ("2027 Pro Basketball
Champion", "Pro Football: 2027 Champion", "2026-27 Stanley Cup® Finals Winner"),
so every one was dropped and the Cup board was the only tier-1 survivor.

The cutoff is now the year the league's current season ENDS. Letting this season's
markets in also let in the neighbours that had only been hidden by the year
filter or by a tier that disagreed with itself, so a Cup board, a finals-matchup
pairing, a seed, a "reach the stage" market, an award and a conference board
filed at tier 1 are never a title step. Fixtures are the production rows (names,
tickers, keys and prices as stored on 2026-09-29).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes import teams as teams_mod
from app.utils import season_windows

_NOW = datetime(2026, 9, 29, 17, 0, tzinfo=timezone.utc)


def _row(tier, name, prob, *, source, ext, key=None, mid, category=None):
    outcome = SimpleNamespace(
        current_probability=prob, rank=1, probability_change_24h=None, is_winner=False
    )
    market = SimpleNamespace(
        market_tier=tier,
        name=name,
        canonical_market_key=key,
        id=mid,
        group_id=None,
        source=source,
        external_id=ext,
        llm_sport_category=category,
    )
    return outcome, market


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _Result(self._rows)


async def _path(rows, league, sport_key, now=_NOW):
    return await teams_mod._get_championship_path(
        1, _DB(rows), league_slug=league, now=now, team_sport_key=sport_key
    )


def _by_tier(path):
    return {p["tier"]: p for p in path}


# --- the NBA: Knicks, Thunder ------------------------------------------------

_KALSHI_CUP = ("2026 Pro Basketball Cup Champion", "KXNBACUP-26", "basketball::championship:2026", 52755817)
_POLY_CUP = ("NBA: 2026 NBA Cup Winner", "877683", "basketball:NBA:championship:2025-26", 59249431)
_KALSHI_TITLE = ("2027 Pro Basketball Champion", "KXNBA-27", "basketball::championship:2027", 52755651)
_POLY_TITLE = ("NBA: 2027 Champion", "478277", "basketball:NBA:championship:2026-27", 20569230)
_BOOKS_TITLE = ("NBA Championship Winner", "basketball_nba_championship_winner", "basketball:NBA:championship:", 2)


def _nba(spec, prob, source, tier=1):
    name, ext, key, mid = spec
    return _row(tier, name, prob, source=source, ext=ext, key=key, mid=mid, category="basketball")


def _knicks_rows():
    return [
        _nba(_KALSHI_CUP, 0.115, "kalshi"),
        _nba(_POLY_CUP, 0.115, "polymarket"),
        _nba(_KALSHI_TITLE, 0.085, "kalshi"),
        _nba(_POLY_TITLE, 0.125, "polymarket"),
        _nba(_BOOKS_TITLE, 0.080439, "odds_api"),
        _row(4, "Pro Basketball Atlantic Division Winner", 0.345, source="kalshi",
             ext="KXNBAATLANTIC-27", key="basketball::division:2027", mid=52755700,
             category="basketball"),
    ]


@pytest.mark.asyncio
async def test_knicks_hero_is_the_2027_title_not_the_cup():
    tiers = _by_tier(await _path(_knicks_rows(), "nba", "basketball_nba"))

    title = tiers[1]
    assert title["label"] == "Championship"
    assert "Cup" not in title["market_name"]
    assert title["market_name"] == "NBA: 2027 Champion"
    # The mean of the three sources pricing the NBA title — the Cup legs are out.
    assert title["probability"] == pytest.approx((0.085 + 0.125 + 0.080439) / 3, abs=1e-4)


@pytest.mark.asyncio
async def test_every_step_is_stamped_with_the_one_current_season():
    path = await _path(_knicks_rows(), "nba", "basketball_nba")
    # Kalshi spells the season "2027", Polymarket "2026-27"; mixed spellings made
    # the page's season chip blank. One season, one spelling.
    assert {p["season"] for p in path} == {"2026-27"}


@pytest.mark.asyncio
async def test_a_cup_only_team_gets_no_championship():
    rows = [_nba(_KALSHI_CUP, 0.265, "kalshi"), _nba(_POLY_CUP, 0.195, "polymarket")]
    assert await _path(rows, "nba", "basketball_nba") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec, source", [(_KALSHI_CUP, "kalshi"), (_POLY_CUP, "polymarket")])
async def test_each_venues_cup_board_is_refused_by_its_name(spec, source):
    # Polymarket's Cup board is keyed to the 2025-26 season today, so the
    # prior-season filter happens to drop it; with no key (its name says 2026,
    # this season) only the Cup refusal stands between it and the hero.
    name, ext, _key, mid = spec
    rows = [_row(1, name, 0.195, source=source, ext=ext, key=None, mid=mid, category="basketball")]
    assert await _path(rows, "nba", "basketball_nba") == []


@pytest.mark.asyncio
async def test_next_seasons_title_is_still_future():
    rows = [_row(1, "2028 Pro Basketball Champion", 0.07, source="kalshi",
                 ext="KXNBA-28", key="basketball::championship:2028", mid=9)]
    assert await _path(rows, "nba", "basketball_nba") == []


# --- the NFL: Chiefs, Jets ---------------------------------------------------


@pytest.mark.asyncio
async def test_chiefs_title_step_reads_all_three_sources():
    rows = [
        _row(1, "2027 Pro Football Champion", 0.075, source="kalshi", ext="KXSB-27",
             key="football::championship:2027", mid=40533, category="football"),
        _row(1, "Pro Football: 2027 Champion", 0.0865, source="polymarket", ext="202857",
             key="football::championship:2027", mid=129037, category="football"),
        _row(1, "NFL Super Bowl Winner", 0.070196, source="odds_api",
             ext="americanfootball_nfl_super_bowl_winner", key="football:NFL:championship:",
             mid=86832, category="football"),
        _row(1, "2028 Pro Football Champion", 0.06, source="kalshi", ext="KXSB-28",
             key="football::championship:2028", mid=40534, category="football"),
    ]
    title = _by_tier(await _path(rows, "nfl", "americanfootball_nfl"))[1]
    assert title["probability"] == pytest.approx((0.075 + 0.0865 + 0.070196) / 3, abs=1e-4)
    assert title["season"] == "2026"


@pytest.mark.asyncio
async def test_a_playoff_seed_is_not_the_conference_step():
    rows = [
        _row(2, "Pro Football: 2027 AFC Champion", 0.06, source="polymarket", ext="203722",
             key="football::conference:2027", mid=129172, category="football"),
        _row(2, "Pro Football Playoffs: AFC #3 Seed", 0.20, source="kalshi",
             ext="KXNFLSEED-27AFC3", mid=61000001, category="football"),
        _row(2, "Pro Football: 2026-27 AFC #1 Seed", 0.09, source="polymarket", ext="962594",
             mid=60166145, category="football"),
    ]
    conf = _by_tier(await _path(rows, "nfl", "americanfootball_nfl"))[2]
    assert conf["market_name"] == "Pro Football: 2027 AFC Champion"
    assert conf["probability"] == pytest.approx(0.06)


# --- the NHL: the Stanley Cup is the title, a finals pairing is not ------------


@pytest.mark.asyncio
async def test_stanley_cup_is_the_title_and_a_finals_matchup_is_not():
    rows = [
        _row(1, "2026-27 Stanley Cup® Finals Winner", 0.08, source="kalshi", ext="KXNHL-27",
             key="hockey:NHL:championship:2026-27", mid=52755659, category="hockey"),
        _row(1, "NHL: 2027 Champion", 0.085, source="polymarket", ext="588160",
             key="hockey:NHL:championship:2026-27", mid=35961638, category="hockey"),
    ] + [
        _row(1, "2026-27 Stanley Cup Final Matchup", p, source="kalshi",
             ext="KXTEAMSINSC-27", key="hockey:NHL:championship:2026-27", mid=61461615,
             category="hockey")
        for p in (0.04, 0.05, 0.06, 0.04)
    ]
    title = _by_tier(await _path(rows, "nhl", "icehockey_nhl"))[1]
    assert title["probability"] == pytest.approx((0.08 + 0.085) / 2, abs=1e-4)
    assert title["season"] == "2026-27"


# --- MLB keeps the calendar-year cutoff ----------------------------------------


@pytest.mark.asyncio
async def test_mlb_2027_world_series_is_still_next_season_in_september():
    rows = [
        _row(1, "MLB World Series Champion 2026", 0.30, source="polymarket", ext="179312",
             key="baseball:MLB:championship:2026", mid=114584, category="baseball"),
        _row(1, "2027 World Series Winner", 0.10, source="polymarket", ext="1",
             key="baseball:MLB:championship:2027", mid=12, category="baseball"),
    ]
    title = _by_tier(await _path(rows, "mlb", "baseball_mlb"))[1]
    assert title["market_name"] == "MLB World Series Champion 2026"
    assert title["probability"] == pytest.approx(0.30)


# --- season_end_year ------------------------------------------------------------


@pytest.mark.parametrize(
    "league, when, expected",
    [
        ("nba", datetime(2026, 9, 29, tzinfo=timezone.utc), 2027),  # preseason of 2026-27
        ("nba", datetime(2027, 3, 1, tzinfo=timezone.utc), 2027),  # mid-season
        ("nba", datetime(2026, 8, 1, tzinfo=timezone.utc), 2027),  # offseason → upcoming
        ("nba", datetime(2026, 6, 1, tzinfo=timezone.utc), 2026),  # 2025-26 Finals
        ("nhl", datetime(2026, 9, 29, tzinfo=timezone.utc), 2027),
        ("nfl", datetime(2026, 9, 29, tzinfo=timezone.utc), 2027),  # Super Bowl LXI, Feb 2027
        ("nfl", datetime(2027, 1, 20, tzinfo=timezone.utc), 2027),  # the same season's playoffs
        ("nfl", datetime(2027, 5, 1, tzinfo=timezone.utc), 2028),  # offseason → upcoming
        ("mlb", datetime(2026, 9, 29, tzinfo=timezone.utc), 2026),
        ("mlb", datetime(2026, 11, 15, tzinfo=timezone.utc), 2027),
        ("epl", datetime(2026, 9, 29, tzinfo=timezone.utc), None),
        ("", datetime(2026, 9, 29, tzinfo=timezone.utc), None),
    ],
)
def test_season_end_year(league, when, expected):
    assert season_windows.season_end_year(league, when) == expected


# --- the question each tier claims ----------------------------------------------
# Production names (2026-09-29) that sat at tier 1, 2 or 4 and would print as
# "Championship", "Conference" or "Division". Each one trips exactly one refusal.


@pytest.mark.parametrize(
    "name",
    [
        "2026 Pro Basketball Cup Champion",  # the NBA Cup (Kalshi)
        "NBA: 2026 NBA Cup Winner",  # the NBA Cup (Polymarket)
        "2026-27 Stanley Cup Final Matchup",  # a pairing of two finalists
        "Pro Football Playoffs: AFC #3 Seed",  # a seed
        "NFL Conference Championship Qualifiers",  # reaching the game
        "NCAA Football: Team to Qualify for 2026 Sun Belt Championship Game",
        "Pro Football: Team to advance to AFC Championship",
        "NCAA Football: Team to make College Football Playoff",  # tier 4 "Division" 84%
        "Pro Football Teams to go Undefeated in their Division",
        "AFC Defensive Player of the Month",
        "MLB: NL Platinum Glove Winner",  # the Giants' "Championship"
        "MLB: Outstanding DH Winner",
        "MLB: 2026 AL Hank Aaron Winner",
        "National League Cy Young Finalists",
        "National League MVP Finalists",
    ],
)
def test_a_step_that_is_not_its_tiers_question_is_refused(name):
    assert teams_mod._answers_its_tier(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "2026-27 Stanley Cup® Finals Winner",
        "NHL: 2027 Champion",
        "NFL Super Bowl Winner",
        "Pro Football: 2027 AFC Champion",
        "NFC Championship Winner",
        "Pro Football: NFC East Champion",
        "Pro Basketball Eastern Conference Champion",
        "NHL Western Conference Finals Winner",
        "MLB World Series Champion 2026",
        "MLB: 2026 National League Champion",
        "College Football National Championship Winner",
        "NCAAF Championship Winner",
        "FIFA World Cup Winner",
    ],
)
def test_a_real_title_question_still_answers_its_tier(name):
    assert teams_mod._answers_its_tier(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "College Football Sun Belt Championship Winner",
        "College Football SEC Championship Winner",
        "College Football Big Ten Champions",
        "College Football Mountain West Championship Winner",
        "Big Ten Regular Season Champion",
        "NBA Eastern Conference Champion",
    ],
)
def test_a_conference_title_filed_at_tier_one_is_withheld(name):
    assert teams_mod._is_a_conference_title_at_tier_one(1, name) is True
    # The same board at tier 2 is the Conference step it is.
    assert teams_mod._is_a_conference_title_at_tier_one(2, name) is False


@pytest.mark.parametrize(
    "name",
    [
        "College Football National Championship Winner",
        "NCAAF Championship Winner",
        "2027 Pro Football Champion",
        "2026-27 Stanley Cup® Finals Winner",
        "MLB World Series Champion 2026",
        "Masters Tournament Winner",
    ],
)
def test_a_national_title_at_tier_one_is_not_a_conference(name):
    assert teams_mod._is_a_conference_title_at_tier_one(1, name) is False


@pytest.mark.asyncio
async def test_a_sun_belt_school_does_not_read_its_conference_board_as_championship():
    rows = [
        _row(1, "College Football Sun Belt Championship Winner", 0.20, source="kalshi",
             ext="KXNCAAFSBELT-26", key="football::championship:2027", mid=1, category="football"),
        _row(2, "NCAA Football 2026 Sun Belt Conference: Winner", 0.19, source="polymarket",
             ext="1", mid=2, category="football"),
    ]
    tiers = _by_tier(await _path(rows, None, "americanfootball_ncaaf"))
    assert 1 not in tiers
    assert tiers[2]["probability"] == pytest.approx(0.19)
