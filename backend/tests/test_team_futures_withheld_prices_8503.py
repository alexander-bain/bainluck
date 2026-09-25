"""#8503 — the team page's Season Futures withholds the legs the market page withholds.

WHAT A READER SAW (Eagles team page, 390px, 2026-09-25 ~01:40Z): Season Futures
read "Jalen Hurts — Fantasy Football: 2026-27 Top 5 Scoring QBs 50%" and
"A.J. Brown — Fantasy Football: 2026-27 Top 5 Scoring FLEX 50%". Both are
untraded Polymarket books (bid 0.01 / ask 0.98-0.99, no trade), and
``/api/futures/59385197`` / ``/api/futures/59385167`` serve both legs as
``probability: null``. #8480 screened the Prop Races block of the same page
(#8478); ``_query_team_futures`` — which also serves "Your Teams' Futures" —
never asked the shared screen.

These tests drive ``_query_team_futures`` through the REAL
``withheld_price_outcome_ids_for_markets`` with the book shapes read off
production (db-query 2026-09-25), so a change to the shared arms reaches this
surface's guard too. The strawman and fail-open tests patch the helper, and only
to prove the fixture carries the defect and the failure direction.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import futures as futures_route
from app.routes.user import _query_team_futures

pytestmark = pytest.mark.asyncio

EAGLES = 549


def _outcome(oid, name, prob, bid, ask, *, team_id=None, rank=1):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=bid, current_yes_ask=ask,
        resolution_source=None, is_winner=False,
        volume_24h=None, volume_24h_at=None, last_updated=None,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"0x{oid:064x}", probability_change_24h=0.0, rank=rank,
    )


def _market(mid, name, outcomes, *, market_type="field", source="polymarket"):
    return SimpleNamespace(
        id=mid, name=name, source=source, group_id=f"{source}:{mid}",
        status="open", llm_sport_category="football", resolution_date=None,
        market_metadata=None, market_type=market_type, event_id=None,
        market_tier=5, canonical_market_key=None, outcomes=outcomes,
    )


# 59385197 — Top 5 Scoring QBs (field): Hurts is the untraded 0.01/0.99 book the
# market page refuses; Dart and Ward are priced legs of the same board.
HURTS = _outcome(220952518, "Jalen Hurts", 0.5, 0.01, 0.99, team_id=EAGLES)
QBS = _market(59385197, "Fantasy Football: 2026-27 Top 5 Scoring QBs", [
    HURTS,
    _outcome(220916260, "Jaxson Dart", 0.08, 0.01, 0.15, rank=2),
    _outcome(220916269, "Cam Ward", 0.055, 0.01, 0.10, rank=3),
])
# 59385167 — Top 5 Scoring FLEX (duel): both legs untraded 0.01/0.98 at 0.5.
BROWN = _outcome(220916128, "A.J. Brown", 0.5, 0.01, 0.98, team_id=EAGLES)
FLEX = _market(59385167, "Fantasy Football: 2026-27 Top 5 Scoring FLEX", [
    BROWN, _outcome(220916127, "Rashee Rice", 0.5, 0.01, 0.98, rank=2),
], market_type="duel")
# CONTROL — a 50% the market page also prints (a tight, real book). It stays.
WINS = _outcome(231028204, "Philadelphia Eagles", 0.5, 0.49, 0.51, team_id=EAGLES)
WIN_TOTALS = _market(59609683, "Pro Football: 2026 Regular Season Win Totals", [
    WINS, _outcome(231028205, "Buffalo Bills", 0.52, 0.51, 0.53, rank=2),
])

MARKETS = [QBS, FLEX, WIN_TOTALS]


def _result(rows):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    return res


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def commit(self):
        self.db.savepoint_log.append("commit")

    async def rollback(self):
        self.db.savepoint_log.append("rollback")


class _DB:
    """Dispatches on the statement: team load, the FK branch, the market reload."""

    def __init__(self, markets=MARKETS):
        self.markets = markets
        self.market_loads: list[str] = []
        self.savepoint_log: list[str] = []
        self.fk_calls = 0

    async def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=EAGLES, name="Philadelphia Eagles", sport_id=1, espn_id="21",
                roster_players=None, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, "americanfootball_nfl")])
        if "futures_outcomes.team_id IN" in sql and "futures_markets" in sql:
            self.fk_calls += 1
            return _result([
                (o, m, "americanfootball_nfl")
                for m in self.markets for o in m.outcomes if o.team_id == EAGLES
            ])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            self.market_loads.append(sql)
            return _result(list(self.markets))
        return _result([])  # name branch, trade reads: nothing on record


def _served(data):
    return {(i["market_id"], i["outcome_name"]): i["probability"] for i in data["items"]}


async def _run(db=None):
    db = db or _DB()
    data = await _query_team_futures([EAGLES], db, limit=30)
    return data, db


async def test_the_two_legs_the_market_page_refuses_leave_season_futures():
    data, db = await _run()
    served = _served(data)
    assert (QBS.id, "Jalen Hurts") not in served, served
    assert (FLEX.id, "A.J. Brown") not in served, served
    assert db.savepoint_log == ["commit"]


async def test_the_priced_fifty_percent_control_stays_at_its_stored_number():
    data, _db = await _run()
    assert _served(data) == {(WIN_TOTALS.id, "Philadelphia Eagles"): 0.5}


async def test_without_the_screen_the_specimens_would_print():
    """STRAWMAN — the fixture really carries the defect. With the screen
    answering "nothing refused", both 50% rows come back, so the tests above
    fail for the right reason if the wiring is removed."""
    async def _nothing(_db, markets):
        return {m.id: set() for m in markets}

    with patch.object(futures_route, "withheld_price_outcome_ids_for_markets", _nothing):
        data, _db = await _run()
    served = _served(data)
    assert served[(QBS.id, "Jalen Hurts")] == 0.5
    assert served[(FLEX.id, "A.J. Brown")] == 0.5


async def test_the_screen_judges_the_whole_market_not_the_team_leg():
    """The FK branch fetches only the Eagles leg; the field arms need every leg,
    so the screen reloads the matched markets themselves, once."""
    _d, db = await _run()
    assert len(db.market_loads) == 1
    assert "futures_markets.id IN" in db.market_loads[0]


async def test_a_priced_leg_of_the_same_market_still_takes_the_slot():
    """The refusal runs BEFORE the one-outcome-per-market pick: when the top
    Eagles leg is refused, the market's next priced Eagles leg is served."""
    refused = _outcome(1, "Philadelphia Eagles", 0.5, 0.01, 0.99, team_id=EAGLES)
    priced = _outcome(2, "Philadelphia Eagles (over 10.5)", 0.3, 0.29, 0.31,
                      team_id=EAGLES, rank=2)
    board = _market(77, "Pro Football: Eagles Season Wins", [
        refused, priced, _outcome(3, "Field", 0.2, 0.19, 0.21, rank=3),
    ])
    data, _db = await _run(_DB([board]))
    assert _served(data) == {(77, "Philadelphia Eagles (over 10.5)"): 0.3}


async def test_a_failed_screen_fails_open_inside_its_savepoint():
    async def _boom(_db, _markets):
        raise RuntimeError("screen down")

    with patch.object(futures_route, "withheld_price_outcome_ids_for_markets", _boom):
        data, db = await _run()
    # Today's numbers, and the savepoint — not the request's transaction — rolled back.
    assert (QBS.id, "Jalen Hurts") in _served(data)
    assert db.savepoint_log == ["rollback"]


async def test_no_matched_market_means_no_reload_and_no_savepoint():
    db = _DB([])
    data, db = await _run(db)
    assert data["items"] == []
    assert db.market_loads == []
    assert db.savepoint_log == []
