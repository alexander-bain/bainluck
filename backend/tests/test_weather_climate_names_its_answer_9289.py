"""#9289 — the /weather climate card says which outcome its number prices.

Production 2026-09-28 04:28Z: "EV market share in 2030? — 84%" (84% of "Above
10%"), "How low will Lake Powell drop? — 70%" (of "Above 3,510 ft"). Every other
/weather card served `leader`; get_climate did not. Outcomes below are the stored
rows' names and prices.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.weather import get_climate
from tests.integration.test_route_weather import _market, _outcome, _query_result


def _db(markets):
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result(markets))
    return db


@pytest.mark.asyncio
async def test_each_climate_row_names_the_outcome_its_number_prices():
    now = datetime.now(timezone.utc)
    served = await get_climate(_db([
        _market(market_id=1, name="EV market share in 2030?",
                resolution_date=now + timedelta(days=1220),
                # Upper rungs under 50% so the ladder-median rule (#9283) and
                # the plain leader agree — this file tests the NAME, not which rung.
                outcomes=[_outcome("Above 10%", 0.845, outcome_id=11),
                          _outcome("Above 20%", 0.31, outcome_id=12),
                          _outcome("Above 30%", 0.12, outcome_id=13)]),
        _market(market_id=2, name="What will be the largest source of global primary energy consumption in 2030?",
                resolution_date=now + timedelta(days=1555),
                outcomes=[_outcome("Oil", 0.61, outcome_id=21),
                          _outcome("Coal", 0.2, outcome_id=22),
                          _outcome("Natural gas", 0.19, outcome_id=23)]),
        # A yes/no question answers itself: its row carries the key, as null.
        _market(market_id=3, name="Will 2026 be the hottest year ever?",
                resolution_date=now + timedelta(days=95),
                outcomes=[_outcome("Yes", 0.65, outcome_id=31),
                          _outcome("No", 0.35, outcome_id=32)]),
    ]))
    by_q = {i["q"]: i for i in served}
    assert by_q["EV market share in 2030?"]["leader"] == "Above 10%"
    assert by_q["EV market share in 2030?"]["prob"] == 84
    assert by_q["What will be the largest source of global primary energy consumption in 2030?"]["leader"] == "Oil"
    assert "leader" in by_q["Will 2026 be the hottest year ever?"]
    assert by_q["Will 2026 be the hottest year ever?"]["leader"] is None
