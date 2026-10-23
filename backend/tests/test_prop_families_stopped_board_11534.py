"""#11534 — Prop Races refuses a board whose prices stopped, as the market page does.

WHAT A READER SAW (Patriots team page, 2026-10-23 18:40Z, a FULL build with the
price screen run to completion): "Super Bowl MVP — Drake Maye 26.5%" and
seventeen more legs from ``KXNFLSBMVP-26``, last season's game. Every leg was
last written 2026-02-04 with a real bid/ask (0.26/0.27), so none of the six
shared arms refuse it. ``/api/futures/479`` serves all 79 legs ``null`` with
``prices_withheld: 79`` on the stopped-board rule (#8011), which the market page
unions OUTSIDE the six arms — and which this route never asked.

These drive ``build_prop_families`` through the real screen and the real
``stale_observation_keys`` / ``unobserved_board_keys`` / ``_fleet_newest_observation``;
only the database is faked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.routes import prop_families as route

pytestmark = pytest.mark.asyncio

PATRIOTS = 11
NOW = datetime.now(timezone.utc)
FEB = datetime(2026, 2, 4, 4, 45, 7, tzinfo=timezone.utc)


def _outcome(oid, name, prob, bid, ask, *, stamp, team_id=PATRIOTS,
             is_winner=False, resolution_source=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_yes_bid=bid, current_yes_ask=ask,
        resolution_source=resolution_source, is_winner=is_winner,
        volume_24h=None, volume_24h_at=None, last_updated=stamp,
        price_changed_at=None, volume=None, team_id=team_id,
    )


def _market(mid, name, outcomes, *, updated_at, status="open"):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", group_id=f"kalshi:{mid}",
        status=status, llm_sport_category="football", resolution_date=None,
        market_metadata=None, market_type="field", event_id=None,
        updated_at=updated_at, outcomes=outcomes,
    )


def _sb_mvp(stamp, **leg_kw):
    """Production shape of market 479's Patriots legs (db-query 2026-10-23)."""
    return _market(479, "Pro Football Championship MVP?", [
        _outcome(6983, "Drake Maye", 0.265, 0.26, 0.27, stamp=stamp, **leg_kw),
        _outcome(6960, "Rhamondre Stevenson", 0.025, 0.02, 0.03, stamp=stamp, **leg_kw),
    ], updated_at=stamp)


def _dpoy():
    """A board observed today — the control that must survive untouched."""
    return _market(900, "NFL Defensive Player of the Year", [
        _outcome(20, "Christian Gonzalez", 0.048, 0.04, 0.056, stamp=NOW),
        _outcome(21, "Milton Williams", 0.0155, 0.01, 0.021, stamp=NOW),
    ], updated_at=NOW)


def _result(rows, scalar=None):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    res.scalar_one_or_none.return_value = scalar
    return res


class _DB:
    def __init__(self, markets):
        self.markets = {m.id: m for m in markets}
        self.branch_calls = 0
        self.fleet_reads = 0

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        if "statement_timeout" in sql:
            return _result([])
        if "max(futures_outcomes.last_updated)" in sql:
            self.fleet_reads += 1
            return _result([], scalar=NOW)  # the fleet is writing prices today
        if "futures_outcomes" in sql and "futures_markets" in sql:
            self.branch_calls += 1
            rows = [(o, m) for m in self.markets.values() for o in m.outcomes]
            return _result(rows if self.branch_calls == 1 else [])
        if "FROM futures_markets" in sql:
            return _result(list(self.markets.values()))
        return _result([])

    async def rollback(self):
        pass


def _team():
    return SimpleNamespace(id=PATRIOTS, name="New England Patriots",
                           slug="new-england-patriots", roster_players=[])


def _entities(payload):
    return {r["entity"]: r["probability"] for f in payload["families"] for r in f["rows"]}


async def _build(markets):
    db = _DB(markets)
    payload, unusable = await route.build_prop_families(_team(), db, 400)
    return payload, unusable, db


async def test_last_seasons_stopped_board_leaves_the_page():
    payload, unusable, db = await _build([_sb_mvp(FEB), _dpoy()])
    assert unusable is False
    ents = _entities(payload)
    assert "Drake Maye" not in ents, ents
    assert "Rhamondre Stevenson" not in ents, ents
    assert db.fleet_reads == 1  # only the stopped board asks the fleet
    # A completed screen, not a fail-closed one: the build is not partial for it.
    assert route._BRANCH_PRICE_SCREEN not in str(payload), payload


async def test_the_observed_control_board_is_untouched():
    payload, _u, _db = await _build([_sb_mvp(FEB), _dpoy()])
    assert _entities(payload) == {"Christian Gonzalez": 0.048, "Milton Williams": 0.0155}


async def test_the_same_board_observed_today_prints():
    """STRAWMAN — the fixture's prices pass the six arms; only the stamp withholds
    them. Observed today, the same legs print at their stored numbers."""
    payload, _u, db = await _build([_sb_mvp(NOW), _dpoy()])
    ents = _entities(payload)
    assert ents["Drake Maye"] == 0.265
    assert db.fleet_reads == 0  # a recent board costs no fleet read


async def test_without_the_board_rules_the_specimen_would_print():
    """STRAWMAN — removing the union brings the Patriots specimen back."""
    async def _nothing(_db, _market):
        return set()

    with patch.object(route, "_board_staleness_withheld", _nothing):
        payload, _u, _db = await _build([_sb_mvp(FEB), _dpoy()])
    assert _entities(payload)["Drake Maye"] == 0.265


async def test_a_graded_board_is_a_result_and_stays():
    """#8011's exemption: a board somebody settled is a result, however old."""
    graded = _sb_mvp(FEB, is_winner=False, resolution_source="api_settlement")
    graded.outcomes[0].is_winner = True
    payload, _u, _db = await _build([graded, _dpoy()])
    assert "Drake Maye" in _entities(payload)
