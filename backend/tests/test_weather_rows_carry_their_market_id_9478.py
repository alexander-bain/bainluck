"""#9478 — every /weather row names the market a tap should open.

/api/weather/featured served `market_id` on every row; /events (hurricane,
earthquake, tornadoes), /climate and /wildcards did not, so ux's rows (PR #9480)
had nothing to link to and a tap went nowhere. Each row now carries the id of
the FuturesMarket it was built from — the same id /featured serves, the one
/futures/{id} opens.

The ids below are deliberately unlike the outcome ids and list positions, so a
row that served the wrong number (an outcome id, an index) fails here.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.weather import get_climate, get_events, get_wildcards
from tests.integration.test_route_weather import _market, _outcome, _query_result


def _db(markets):
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result(markets))
    return db


def _yes_no(market_id, name, yes, **kw):
    return _market(
        market_id=market_id,
        name=name,
        outcomes=[_outcome("Yes", yes, outcome_id=market_id * 10),
                  _outcome("No", 1 - yes, outcome_id=market_id * 10 + 1)],
        **kw,
    )


@pytest.mark.asyncio
async def test_each_event_row_carries_its_own_market_id():
    # A clock inside every title's period: /events drops past-period titles
    # (#10331), so on a later clock these rows would not be served at all.
    served = await get_events(_db([
        _yes_no(62786086, "Will a Category 5 hurricane make landfall in 2026?", 0.2),
        _yes_no(41503, "Will a magnitude 8.0 earthquake hit in 2026?", 0.3),
        _yes_no(9917, "Number of tornadoes in Oct 2026 above 100?", 0.55),
    ]), now=datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc))
    ids = {row["q"]: row["market_id"] for group in served.values() for row in group}
    assert ids == {
        "Will a Category 5 hurricane make landfall in 2026?": 62786086,
        "Will a magnitude 8.0 earthquake hit in 2026?": 41503,
        "Number of tornadoes in Oct 2026 above 100?": 9917,
    }
    assert [len(served[g]) for g in ("hurricane", "earthquake", "tornadoes")] == [1, 1, 1]


@pytest.mark.asyncio
async def test_each_climate_row_carries_its_own_market_id():
    now = datetime.now(timezone.utc)
    served = await get_climate(_db([
        _yes_no(70001, "Will 2026 be the hottest year ever?", 0.65,
                resolution_date=now + timedelta(days=95)),
        _yes_no(80413, "Will global CO2 emissions fall by 2030?", 0.12,
                resolution_date=now + timedelta(days=1500)),
    ]))
    assert {row["q"]: row["market_id"] for row in served} == {
        "Will 2026 be the hottest year ever?": 70001,
        "Will global CO2 emissions fall by 2030?": 80413,
    }


@pytest.mark.asyncio
async def test_each_wildcard_row_carries_its_own_market_id():
    served = await get_wildcards(_db([
        _yes_no(55123, "Will a supervolcano erupt before 2050?", 0.03),
        _yes_no(66231, "Will a major solar storm hit Earth in 2026?", 0.4),
    ]))
    assert {row["q"]: row["market_id"] for row in served} == {
        "Will a supervolcano erupt before 2050?": 55123,
        "Will a major solar storm hit Earth in 2026?": 66231,
    }
