"""#9593 — a women's team page stops printing the men's title odds as its own.

WHAT A READER SAW (production, 2026-09-29 ~08:55Z, 390px):
``/sport/soccer/uefa_champs_league_women/team/arsenal`` (Arsenal WOMEN) led with
"CHAMPIONSHIP 59%", which is Kalshi's men's *English Premier League Champion*
leg (market 31834301, 58.5%). ``GET /api/teams/arsenal-women`` ``futures`` held
30 markets, 29 of them men's. The men's page (``/api/teams/arsenal``, team 1826,
``soccer_england_efl_cup``) served the same 30, including *UEFA Women's Champions
League 2026-27 Winner 8.5%*.

Both clubs are ``soccer``, so the #2593 sport test passes. The market's
``sport_id`` is NULL (read off production 2026-09-29), and "Arsenal"
name-matches both clubs. These tests drive the real ``_query_team_futures``
through the FK branch AND the name branch with those stored shapes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.routes import futures as futures_route
from app.routes import user as user_route
from app.routes.user import _query_team_futures
from app.utils.market_team_sport import link_crosses_gender

ARSENAL_MEN = 1826
ARSENAL_WOMEN = 11857


def _outcome(oid, name, prob, *, team_id=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=None, current_yes_ask=None,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"X-{oid}", probability_change_24h=0.0, rank=1,
    )


def _market(mid, name, outcomes, *, category="soccer", tier=1, external_id=None):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=external_id, group_id=None,
        status="open", llm_sport_category=category, resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        market_tier=tier, canonical_market_key=None, outcomes=outcomes,
    )


# Production ids and prices, 2026-09-29. The EPL leg is stored on the MEN's row.
EPL = _market(31834301, "English Premier League Champion",
              [_outcome(1, "Arsenal", 0.585, team_id=ARSENAL_MEN)])
UWCL = _market(60607654, "UEFA Women's Champions League 2026-27 Winner",
               [_outcome(2, "Arsenal", 0.085)])
CLUB_OF_YEAR = _market(60775211, "Men's Club of the Year Winner 2026",
                       [_outcome(3, "Arsenal", 0.06)], tier=5)
ARSENAL_MARKETS = [EPL, UWCL, CLUB_OF_YEAR]


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
    """Team load, the FK branch, the NAME branch, the stats read, the market reload."""

    def __init__(self, team_id, team_name, team_sport_key, markets):
        self.team_id = team_id
        self.team_name = team_name
        self.team_sport_key = team_sport_key
        self.markets = markets

    async def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        where = sql.split("WHERE", 1)[-1]
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=self.team_id, name=self.team_name, sport_id=7, espn_id=None,
                roster_players=None, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, self.team_sport_key)])
        if "futures_outcomes.team_id IN" in where:
            return _result([
                (o, m, None)
                for m in self.markets for o in m.outcomes if o.team_id == self.team_id
            ])
        if "futures_outcomes.name" in where:
            return _result([
                (o, m, None)
                for m in self.markets for o in m.outcomes
                if self.team_name.lower() in (o.name or "").lower()
            ])
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


def _women_page():
    return _DB(ARSENAL_WOMEN, "Arsenal", "soccer_uefa_champs_league_women", ARSENAL_MARKETS)


def _men_page():
    return _DB(ARSENAL_MEN, "Arsenal", "soccer_england_efl_cup", ARSENAL_MARKETS)


async def test_the_womens_page_keeps_only_the_womens_champions_league():
    assert _served(await _run(_women_page())) == {UWCL.id}


async def test_the_mens_page_drops_the_womens_champions_league_and_keeps_its_own():
    assert _served(await _run(_men_page())) == {EPL.id, CLUB_OF_YEAR.id}


async def test_without_the_check_the_59_percent_prints_on_the_womens_page():
    """STRAWMAN: the fixture carries the defect. With the side test switched off,
    the EPL leg returns to the women's page through the name branch, and the
    first test fails for the right reason."""
    with patch.object(user_route, "_link_crosses_gender", lambda *_a: False):
        served = _served(await _run(_women_page()))
    assert EPL.id in served and CLUB_OF_YEAR.id in served


async def test_a_stored_link_to_a_womens_row_is_refused_too():
    """The FK branch. The WNCAAB rows carry the men's tournament by stored link
    (production 2026-09-29: "Men's Round of 16 Qualifiers" on 5 `basketball_wncaab`
    rows, "NCAAB Championship Winner" on 36). The women's twin stays."""
    tid = 5001
    mens = _market(1, "Men's Round of 16 Qualifiers",
                   [_outcome(11, "Alabama", 0.3, team_id=tid)], category="basketball")
    ncaab = _market(2, "NCAAB Championship Winner",
                    [_outcome(12, "Alabama", 0.04, team_id=tid)], category="basketball")
    womens = _market(3, "Women's Round of 16 Qualifiers",
                     [_outcome(13, "Alabama", 0.4, team_id=tid)], category="basketball")
    db = _DB(tid, "Alabama Crimson Tide", "basketball_wncaab", [mens, ncaab, womens])
    assert _served(await _run(db)) == {3}


async def test_a_womens_ticker_keeps_an_unmarked_market_on_a_wnba_page():
    """The page reads the venue id, not only the name: Kalshi's "Caitlin Clark's
    Next Team" (KXWNBANEXTTEAM) names no side, and it is the Fever's market."""
    tid = 7001
    clark = _market(5, "Caitlin Clark's Next Team",
                    [_outcome(15, "Indiana Fever", 0.8, team_id=tid)],
                    category="basketball", tier=5,
                    external_id="KXWNBANEXTTEAM-27CCLARK22")
    relocation = _market(6, "Portland to Announce a Relocation before the 2027-28 Season",
                         [_outcome(16, "Indiana Fever", 0.1, team_id=tid)],
                         category="basketball", tier=5,
                         external_id="KXNBARELOCATION-27POR")
    db = _DB(tid, "Indiana Fever", "basketball_wnba", [clark, relocation])
    assert _served(await _run(db)) == {5}


async def test_a_tennis_mixed_field_market_stays_on_a_wta_player():
    """Tennis is exempt from the unmarked rule. "Who will win a Grand Slam in
    2027?" lists Sabalenka beside the men, so an unmarked name is no claim."""
    tid = 6001
    slam = _market(4, "Who will win a Grand Slam in 2027?",
                   [_outcome(14, "Aryna Sabalenka", 0.3, team_id=tid)], category="tennis")
    db = _DB(tid, "Aryna Sabalenka", "tennis_wta_us_open", [slam])
    assert _served(await _run(db)) == {4}


def test_the_rule_by_case():
    w, m = "soccer_uefa_champs_league_women", "soccer_epl"
    assert link_crosses_gender("English Premier League Champion", w)
    assert not link_crosses_gender("UEFA Women's Champions League 2026-27 Winner", w)
    assert link_crosses_gender("UEFA Women's Champions League 2026-27 Winner", m)
    assert not link_crosses_gender("Men's Club of the Year Winner 2026", m)
    # "Men's" is never read as "Women's".
    assert link_crosses_gender("Men's Club of the Year Winner 2026", w)
    # Leagues whose names carry no "women".
    assert not link_crosses_gender("WNBA: 2026 Champion", "basketball_wnba")
    assert link_crosses_gender("WNBA: 2026 Champion", "basketball_nba")
    assert not link_crosses_gender(
        "College Basketball (W): Undefeated Regular Season", "basketball_wncaab")
    assert link_crosses_gender(
        "College Basketball (M): Undefeated Regular Season", "basketball_wncaab")
    # A women's sport key on the market is women's evidence without the word.
    assert not link_crosses_gender("Champion", w, market_sport_key="basketball_wnba")
    # The league a Kalshi ticker names is evidence too: "Caitlin Clark's Next
    # Team" (KXWNBANEXTTEAM, production 2026-09-29) stays on the Fever, and a
    # men's series (KXNCAAMBKENPOMTOP) still leaves a WNCAAB page.
    assert not link_crosses_gender(
        "Caitlin Clark's Next Team", "basketball_wnba",
        market_source="kalshi", market_external_id="KXWNBANEXTTEAM-27CCLARK22")
    assert link_crosses_gender(
        "Caitlin Clark's Next Team", "basketball_wnba",
        market_source="kalshi", market_external_id="KXNBANEXTTEAM-27X")
    assert link_crosses_gender(
        "Final KenPom Ratings: Top 25 Teams", "basketball_wncaab",
        market_source="kalshi", market_external_id="KXNCAAMBKENPOMTOP-27FINALT25")
    # A key that cannot say its side never refuses.
    assert not link_crosses_gender("UEFA Women's Champions League Winner", "soccer_other")
    assert not link_crosses_gender("English Premier League Champion", None)
