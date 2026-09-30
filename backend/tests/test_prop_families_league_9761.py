"""#9761 — a college team's Prop Races stop carrying the NFL's boards.

WHAT A READER SAW (production, 2026-09-30 16:18Z, 390px):
``/sport/football/ncaaf/team/notre-dame-fighting-irish`` opened PROP RACES with
"Offensive Rookie Of The Year — Jeremiyah Love 44% · Jadarian Price 6% ·
Malachi Fields 1%": Kalshi's NFL board ``KXNFLOROTY-27`` (market 8122710), every
leg ``team_id`` NULL. Notre Dame's roster still lists all three, so the roster
branch matched them, and nothing in the side screen asked which LEAGUE a market
is for — NFL and college football are one sport. ``_withhold_other_side`` now
asks ``link_crosses_league`` (the linker's and the championship path's refusal).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import Select

from app.routes import prop_families as route

NCAAF_ID, NFL_ID = 21, 22
SPORT_KEYS = {NCAAF_ID: "americanfootball_ncaaf", NFL_ID: "americanfootball_nfl"}


def _market(mid, name, source, external_id, *, slug=None):
    return SimpleNamespace(
        id=mid, name=name, source=source, external_id=external_id,
        sport_id=None, group_id=f"{source}:{external_id}", status="open",
        resolution_date=None, llm_sport_category="football",
        market_metadata={"polymarket_event_slug": slug} if slug else {},
    )


def _leg(oid, name, market, prob):
    outcome = SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        market_id=market.id, is_winner=False,
    )
    return (outcome, market)


# Production ids and prices, 2026-09-30.
OROY = _market(8122710, "Offensive Rookie of the Year Winner?", "kalshi", "KXNFLOROTY-27")
DROY = _market(
    56933332, "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner",
    "polymarket", "741436",
    slug="pro-football-2026-27-ap-defensive-rookie-of-the-year-winner",
)
# The college's own board: same sport, the college's league. It stays.
HEISMAN = _market(90000001, "Heisman Trophy Winner", "kalshi", "KXHEISMAN-26")

NFL_ROWS = [
    _leg(43605906, "Jeremiyah Love", OROY, 0.435),
    _leg(43605908, "Jadarian Price", OROY, 0.055),
    _leg(211383725, "Jeremiyah Love", DROY, 0.06),
    _leg(211383726, "Jadarian Price", DROY, 0.02),
]
COLLEGE_ROWS = [
    _leg(90000011, "CJ Carr", HEISMAN, 0.12),
    _leg(90000012, "Jeremiyah Love", HEISMAN, 0.03),
]


def _rows_result(items):
    result = MagicMock()
    result.all.return_value = list(items)
    scalars = MagicMock()
    scalars.all.return_value = []
    result.scalars.return_value = scalars
    return result


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt, *args, **kwargs):
        rendered = str(stmt)
        if "statement_timeout" in rendered:
            return _rows_result([])
        if isinstance(stmt, Select) and "futures_outcomes" in rendered:
            return _rows_result(self.rows)
        if isinstance(stmt, Select) and "FROM sports" in rendered:
            return _rows_result(list(SPORT_KEYS.items()))
        return _rows_result([])

    async def rollback(self):
        pass


def _team(*, sport_id, tid=835, slug="notre-dame-fighting-irish-ncaaf"):
    return SimpleNamespace(
        id=tid, name="Notre Dame Fighting Irish", slug=slug, sport_id=sport_id,
        roster_players=[{"name": "Jeremiyah Love"}, {"name": "Jadarian Price"},
                        {"name": "CJ Carr"}],
    )


async def _build(team, rows):
    with patch.object(route, "withheld_price_outcome_ids_for_markets",
                      AsyncMock(return_value={})):
        payload, unusable = await route.build_prop_families(team, _DB(rows), 50)
    assert unusable is False
    return payload


def _market_ids(payload):
    return {row["market_id"] for fam in payload["families"] for row in fam["rows"]}


async def test_the_college_page_keeps_only_its_own_leagues_boards():
    payload = await _build(_team(sport_id=NCAAF_ID), NFL_ROWS + COLLEGE_ROWS)
    assert _market_ids(payload) == {HEISMAN.id}


async def test_the_nfl_boards_alone_leave_no_card():
    # The reader-visible specimen: only NFL legs matched, so no race at all.
    payload = await _build(_team(sport_id=NCAAF_ID), NFL_ROWS)
    assert payload["families"] == []


async def test_strawman_an_nfl_page_keeps_both_nfl_boards():
    # The same rows on a team of the markets' own league survive the screen, so
    # the refusals above are the league test, not an empty build.
    payload = await _build(_team(sport_id=NFL_ID, tid=4242, slug="nfl-club"), NFL_ROWS)
    assert _market_ids(payload) == {OROY.id, DROY.id}
