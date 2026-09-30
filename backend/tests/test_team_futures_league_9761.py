"""#9761 — a college team page stops listing its former players' NFL props.

WHAT A READER SAW (production, 2026-09-30 16:18Z, 390px):
``/sport/football/ncaaf/team/lsu-tigers`` listed "Award · Mansoor Delane ·
Pro Football: 2026-27 AP Defensive Rookie of the Year Winner 6%" AFTER the
linker had set that leg's ``team_id`` to NULL (outcome 211383725, db-query
16:15Z). ``GET /api/teams/lsu-tigers-ncaaf`` served it with ``matched_team`` 9:
the award query's ROSTER branch matched "Mansoor Delane" on LSU's roster, and
its sport test passes because NFL and college football are both ``football``.

The fixtures carry the stored shapes: the Polymarket market names the NFL only
through its event slug (``pro-football-…``), Kalshi's rookie board through its
series (``KXNFLOROTY``); no ``sport_id``; every leg unbound. These tests drive
the real ``_query_team_futures`` through the roster branch and the FK branch.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routes import futures as futures_route
from app.routes.user import _query_team_futures

LSU_NCAAF = 9
NFL_TEAM = 4242
LSU_ROSTER = [{"name": "Mansoor Delane"}, {"name": "Garrett Nussmeier"}]


def _outcome(oid, name, prob, *, team_id=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=None, current_yes_ask=None,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"X-{oid}", probability_change_24h=0.0, rank=1,
    )


def _market(mid, name, outcomes, *, source, external_id, slug=None, tier=3):
    return SimpleNamespace(
        id=mid, name=name, source=source, external_id=external_id, group_id=None,
        status="open", llm_sport_category="football", resolution_date=None,
        market_metadata={"polymarket_event_slug": slug} if slug else None,
        market_type="field", event_id=None, market_tier=tier,
        canonical_market_key=None, outcomes=outcomes,
    )


# Production ids, 2026-09-30.
DELANE_DROY = _market(
    56933332, "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner",
    [_outcome(211383725, "Mansoor Delane", 0.06)],
    source="polymarket", external_id="741436",
    slug="pro-football-2026-27-ap-defensive-rookie-of-the-year-winner",
)
NFL_OROY = _market(
    8122710, "Offensive Rookie of the Year Winner?",
    [_outcome(43605907, "Garrett Nussmeier", 0.02)],
    source="kalshi", external_id="KXNFLOROTY-27",
)
# The college's own award board: same sport, the college's league. It stays.
HEISMAN = _market(
    90000001, "Heisman Trophy Winner",
    [_outcome(90000011, "Garrett Nussmeier", 0.12)],
    source="kalshi", external_id="KXHEISMAN-26",
)
# A Polymarket market whose slug names no league is no claim; it stays.
UNCLAIMED_SLUG = _market(
    90000002, "College Football Defensive Player of the Year",
    [_outcome(90000012, "Mansoor Delane", 0.04)],
    source="polymarket", external_id="999", slug="cfb-dpoy-2026",
)
MARKETS = [DELANE_DROY, NFL_OROY, HEISMAN, UNCLAIMED_SLUG]


def _result(rows):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    return res


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _DB:
    """Team load, the FK branch, the name branch, the award query, stats, reload."""

    def __init__(self, team_id, team_sport_key, markets, *, roster=LSU_ROSTER):
        self.team_id = team_id
        self.team_sport_key = team_sport_key
        self.markets = markets
        self.roster = roster

    async def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        where = sql.split("WHERE", 1)[-1]
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=self.team_id, name="LSU Tigers", sport_id=7, espn_id=None,
                roster_players=self.roster, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, self.team_sport_key)])
        if "futures_outcomes.team_id IN" in where:
            return _result([
                (o, m, None)
                for m in self.markets for o in m.outcomes if o.team_id == self.team_id
            ])
        if "futures_outcomes.name" in where:
            return _result([])  # no leg is named "LSU Tigers"
        if "futures_markets.name" in where:  # the award query: every award leg
            return _result([(o, m, None) for m in self.markets for o in m.outcomes])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            return _result(list(self.markets))
        return _result([])


def _served(data):
    return {i["market_id"] for i in data["items"]}


async def _run(db):
    async def _nothing_refused(_db, markets):
        return {m.id: set() for m in markets}

    with patch.object(futures_route, "withheld_price_outcome_ids_for_markets",
                      _nothing_refused):
        return await _query_team_futures([db.team_id], db, limit=30)


async def test_the_college_page_keeps_only_its_own_leagues_awards():
    served = _served(await _run(_DB(LSU_NCAAF, "americanfootball_ncaaf", MARKETS)))
    assert served == {HEISMAN.id, UNCLAIMED_SLUG.id}


async def test_the_polymarket_leg_is_refused_by_its_event_slug():
    served = _served(await _run(_DB(LSU_NCAAF, "americanfootball_ncaaf", [DELANE_DROY])))
    assert served == set()


async def test_the_kalshi_leg_is_refused_by_its_series():
    served = _served(await _run(_DB(LSU_NCAAF, "americanfootball_ncaaf", [NFL_OROY])))
    assert served == set()


async def test_strawman_the_same_rows_reach_a_team_of_the_markets_own_league():
    # The fixture is not empty: an NFL club with the same roster names keeps both
    # NFL legs, so the refusals above are the league test and nothing else.
    served = _served(await _run(_DB(NFL_TEAM, "americanfootball_nfl", MARKETS)))
    assert {DELANE_DROY.id, NFL_OROY.id} <= served


async def test_an_fk_link_outside_the_league_is_refused_too():
    # A leg the linker has not yet drained keeps its stored team_id; the page
    # must not wait for the drain to stop printing it.
    bound = _market(
        56933332, DELANE_DROY.name,
        [_outcome(211383725, "Mansoor Delane", 0.06, team_id=LSU_NCAAF)],
        source="polymarket", external_id="741436",
        slug="pro-football-2026-27-ap-defensive-rookie-of-the-year-winner",
    )
    db = _DB(LSU_NCAAF, "americanfootball_ncaaf", [bound], roster=None)
    assert _served(await _run(db)) == set()
