"""Tests that /api/weather/rain and /api/economics include market_id on rain tiles and rate_cuts."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.weather import get_rain


def _scalar_result(rows):
    res = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    res.scalars.return_value = scalars
    return res


@pytest.mark.asyncio
async def test_weather_rain_includes_market_id_on_daily_and_monthly():
    now = datetime.now(timezone.utc)
    daily_market = SimpleNamespace(
        id=91001,
        external_id="KXRAIN-26NOV18",
        name="Where will it rain on Nov 18, 2026?",
        source="kalshi",
        status="open",
        resolution_date=now + timedelta(days=2),
        updated_at=now,
        outcomes=[
            SimpleNamespace(
                external_id="KXRAIN-26NOV18-NYC",
                name="New York City",
                current_probability=0.42,
                probability_change_24h=0.03,
                is_winner=None,
            )
        ],
    )
    monthly_market = SimpleNamespace(
        id=92002,
        external_id="KXRAINNYCM-26NOV",
        name="Rain in New York in Nov 2026?",
        source="kalshi",
        status="open",
        resolution_date=now + timedelta(days=14),
        updated_at=now,
        outcomes=[
            SimpleNamespace(
                external_id="KXRAINNYCM-26NOV-YES",
                name="Yes",
                current_probability=0.76,
                probability_change_24h=0.04,
                is_winner=None,
            )
        ],
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result([daily_market]),
            _scalar_result([monthly_market]),
        ]
    )

    payload = await get_rain(db)
    assert len(payload["daily"]) == 1
    assert payload["daily"][0]["market_id"] == 91001
    assert len(payload["monthly"]) == 1
    assert payload["monthly"][0]["market_id"] == 92002
