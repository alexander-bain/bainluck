"""#11534 — Season Futures refuses a board whose prices stopped, as the market page does.

WHAT A READER SAW (Patriots team page, 390px, 2026-10-23 23:00Z, after #11543 went
live and Prop Races came back clean): Season Futures still printed an Award card
"Will Drake Maye win the Pro Football Championship MVP? 27%" — market 479,
``KXNFLSBMVP-26``, last season's game. The Seahawks page printed Sam Darnold at
44.5% from the same board. Every leg was last written 2026-02-04 with a real
bid/ask, so the five shared arms #8503 wired here refuse none of them;
``/api/futures/479`` serves all 79 legs ``null`` on the stopped-board rule (#8011).

These drive ``_query_team_futures`` through the real shared screen and the real
``_board_staleness_withheld`` (the composition Prop Races uses); only the
database is faked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import prop_families as prop_families_route
from app.routes.user import _query_team_futures

pytestmark = pytest.mark.asyncio

PATRIOTS = 11
NOW = datetime.now(timezone.utc)
FEB = datetime(2026, 2, 4, 4, 45, 7, tzinfo=timezone.utc)


def _outcome(oid, name, prob, bid, ask, *, stamp, team_id=PATRIOTS, rank=1,
             is_winner=False, resolution_source=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=bid, current_yes_ask=ask,
        resolution_source=resolution_source, is_winner=is_winner,
        volume_24h=None, volume_24h_at=None, last_updated=stamp,
        price_changed_at=None, volume=None, team_id=team_id,
        external_id=f"K-{oid}", probability_change_24h=0.0, rank=rank,
    )


def _market(mid, name, outcomes, *, updated_at):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", group_id=f"kalshi:{mid}",
        status="open", llm_sport_category="football", resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        market_tier=3, canonical_market_key=None, updated_at=updated_at,
        outcomes=outcomes,
    )


def _sb_mvp(stamp):
    """Production shape of market 479's Patriots leg (db-query 2026-10-23)."""
    return _market(479, "Pro Football Championship MVP?", [
        _outcome(6983, "Will Drake Maye win the Pro Football Championship Game MVP?",
                 0.265, 0.26, 0.27, stamp=stamp),
        _outcome(6990, "Will Sam Darnold win the Pro Football Championship Game MVP?",
                 0.445, 0.44, 0.45, stamp=stamp, team_id=None, rank=2),
    ], updated_at=stamp)


def _dpoy():
    """A board observed today — the control that must survive untouched."""
    return _market(900, "NFL Defensive Player of the Year", [
        _outcome(20, "Christian Gonzalez", 0.048, 0.04, 0.056, stamp=NOW),
        _outcome(21, "Myles Garrett", 0.30, 0.29, 0.31, stamp=NOW,
                 team_id=None, rank=2),
    ], updated_at=NOW)


def _result(rows, scalar=None):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    res.scalar_one_or_none.return_value = scalar
    return res


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def commit(self):
        self.db.savepoint_log.append("commit")

    async def rollback(self):
        self.db.savepoint_log.append("rollback")


class _DB:
    def __init__(self, markets):
        self.markets = markets
        self.savepoint_log: list[str] = []
        self.fleet_reads = 0

    async def begin_nested(self):
        return _Savepoint(self)

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "max(futures_outcomes.last_updated)" in sql:
            self.fleet_reads += 1
            return _result([], scalar=NOW)  # the fleet is writing prices today
        if "FROM teams JOIN sports" in sql:
            team = SimpleNamespace(
                id=PATRIOTS, name="New England Patriots", sport_id=1, espn_id="17",
                roster_players=None, logo_url_small=None, logo_url=None,
                primary_color=None,
            )
            return _result([(team, "americanfootball_nfl")])
        if "futures_outcomes.team_id IN" in sql and "futures_markets" in sql:
            return _result([
                (o, m, "americanfootball_nfl")
                for m in self.markets for o in m.outcomes if o.team_id == PATRIOTS
            ])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), None) for m in self.markets])
        if "FROM futures_markets" in sql and "futures_outcomes" not in sql.split("WHERE")[0]:
            return _result(list(self.markets))
        return _result([])


def _served(data):
    return {i["market_id"]: i["probability"] for i in data["items"]}


async def _run(markets):
    db = _DB(markets)
    data = await _query_team_futures([PATRIOTS], db, limit=30)
    return data, db


async def test_last_seasons_stopped_board_leaves_season_futures():
    data, db = await _run([_sb_mvp(FEB), _dpoy()])
    assert 479 not in _served(data), data["items"]
    assert db.fleet_reads == 1  # only the stopped board asks the fleet
    assert db.savepoint_log == ["commit"]  # a completed screen, not a fail-open


async def test_the_observed_control_board_is_untouched():
    data, _db = await _run([_sb_mvp(FEB), _dpoy()])
    assert _served(data) == {900: 0.048}


async def test_the_same_board_observed_today_prints():
    """STRAWMAN — the fixture's prices pass the five arms; only the stamp
    withholds them. Observed today, the same leg prints at its stored number."""
    data, db = await _run([_sb_mvp(NOW), _dpoy()])
    assert _served(data)[479] == 0.265
    assert db.fleet_reads == 0  # a recent board costs no fleet read


async def test_without_the_board_rules_the_specimen_would_print():
    """STRAWMAN — removing the union brings the Patriots specimen back."""
    async def _nothing(_db, _market):
        return set()

    with patch.object(prop_families_route, "_board_staleness_withheld", _nothing):
        data, _db = await _run([_sb_mvp(FEB), _dpoy()])
    assert _served(data)[479] == 0.265


async def test_a_graded_board_is_a_result_and_stays():
    """#8011's exemption: a board somebody settled is a result, however old."""
    graded = _sb_mvp(FEB)
    for o in graded.outcomes:
        o.resolution_source = "api_settlement"
    graded.outcomes[1].is_winner = True
    data, _db = await _run([graded, _dpoy()])
    assert 479 in _served(data)
