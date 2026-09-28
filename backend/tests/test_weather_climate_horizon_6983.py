"""#6983 — /weather's climate card: honest horizons, soonest-first, each question once.

Three defects on one card, read on production 2026-09-18 and again 2026-09-28:

1. "Will there be an at least 8.0 magnitude earthquake in California before 2028?"
   (resolves 2028-12-31) sat under the column headed "2026 · This year", because
   ``_classify_scale`` returned "2026" as a fallthrough for anything not 2030/2050.
2. Every column was ordered by ``closes``, the "Fri, Apr 16" display string, so rows
   sorted by weekday name, not by date.
3. The same question printed twice on one page: the quake under Seismic activity
   and under climate; "Will a supervolcano erupt before 2050?" under 2050 and on
   Wild Cards.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.weather import _format_closes, get_climate, get_wildcards
from tests.integration.test_route_weather import _market, _query_result


def _db(markets):
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result(markets))
    return db


@pytest.mark.asyncio
async def test_a_market_settling_in_2028_is_not_filed_under_the_near_column():
    now = datetime.now(timezone.utc)
    served = await get_climate(_db([
        _market(market_id=1, name="Will Lake Mead fall below 1,000 ft before 2028?",
                resolution_date=now + timedelta(days=820)),
        # Control: same shape, inside a year — stays in the near column, so the
        # rule is a horizon and not "everything moves out".
        _market(market_id=2, name="Will 2026 be the hottest year ever?",
                resolution_date=now + timedelta(days=200)),
    ]))
    scale = {i["q"]: i["scale"] for i in served}
    assert scale["Will Lake Mead fall below 1,000 ft before 2028?"] == "2030"
    assert scale["Will 2026 be the hottest year ever?"] == "2026"


@pytest.mark.asyncio
async def test_each_column_is_ordered_soonest_first_not_by_weekday_name():
    now = datetime.now(timezone.utc)
    # Pick three dates, earliest to latest, whose display strings sort the
    # OTHER way — the only arrangement where the old key and the right key
    # disagree on every pair. Found by search, so no clock can dodge it.
    picked: list[datetime] = []
    for offset in range(30, 330):
        d = now + timedelta(days=offset)
        if not picked or _format_closes(d) < _format_closes(picked[-1]):
            picked.append(d)
        if len(picked) == 3:
            break
    assert len(picked) == 3
    names = ["Hottest September on record?", "Hottest October on record?",
             "Hottest November on record?"]
    # Fed latest-first, so payload order cannot pass by echoing input order.
    served = await get_climate(_db([
        _market(market_id=10 + i, name=names[i], resolution_date=picked[i])
        for i in reversed(range(3))
    ]))
    assert [i["q"] for i in served] == names
    # The strawman the old key produces: alphabetical by weekday string.
    assert sorted(names, key=lambda n: _format_closes(picked[names.index(n)])) != names
    assert all("_res_date" not in i for i in served)


@pytest.mark.asyncio
async def test_a_question_another_card_owns_is_not_repeated_on_climate():
    now = datetime.now(timezone.utc)
    quake = "Will there be an at least 8.0 magnitude earthquake in California before 2028?"
    volcano = "Will a supervolcano erupt before 2050?"
    climate_q = "EU meets its 2030 climate goals?"
    markets = [
        _market(market_id=21, name=quake, resolution_date=now + timedelta(days=820)),
        _market(market_id=22, name=volcano, resolution_date=now + timedelta(days=8800)),
        _market(market_id=23, name=climate_q, resolution_date=now + timedelta(days=1600)),
    ]
    climate = [i["q"] for i in await get_climate(_db(markets))]
    assert quake not in climate
    assert volcano not in climate
    assert climate == [climate_q]
    # The volcano still has its one home.
    wild = [i["q"] for i in await get_wildcards(_db([markets[1]]))]
    assert wild == [volcano]
