"""#3134 — every card in /weather's Wild Cards row is labelled a wild card.

Production 2026-09-28 05:40Z: /api/weather/wildcards served "Will a supervolcano
erupt before 2050?" with tag "Weather" beside four "Wild card" siblings. The
route admits rows by substring (`ilike %volcano%`) while `_derive_tag` needs a
word boundary, so compound titles got in and fell through to the default.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.weather import _derive_tag, get_wildcards
from tests.integration.test_route_weather import _market, _outcome, _query_result


@pytest.mark.asyncio
async def test_every_wildcard_row_is_tagged_wild_card():
    now = datetime.now(timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_query_result([
        _market(market_id=1, name="Will a supervolcano erupt before 2050?",
                source="kalshi", resolution_date=now + timedelta(days=8500),
                outcomes=[_outcome("Yes", 0.285, outcome_id=11),
                          _outcome("No", 0.715, outcome_id=12)]),
        _market(market_id=2, name="Major volcano eruption in 2026?",
                source="kalshi", resolution_date=now + timedelta(days=270),
                outcomes=[_outcome("At least 1", 0.345, outcome_id=21),
                          _outcome("0", 0.655, outcome_id=22)]),
    ]))
    # Strawman: the title classifier alone still misfiles the specimen, so this
    # test would fail if the route went back to asking it.
    assert _derive_tag("Will a supervolcano erupt before 2050?") == "Weather"

    served = await get_wildcards(db)
    assert {i["q"] for i in served} == {
        "Will a supervolcano erupt before 2050?", "Major volcano eruption in 2026?"}
    assert [i["tag"] for i in served] == ["Wild card", "Wild card"]
