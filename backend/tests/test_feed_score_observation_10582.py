"""Feed and fresh card scores carry their own observation, independent of prices."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.routes import feed, feed_prices
from app.utils.personalization import PersonalizationContext
from app.utils.proven_duplicates import FoldedBlendView
from tests.test_feed_price_cards_9515 import NOW, event, result
from tests.test_feed_score_events_resilience import _mock_db


@pytest.mark.asyncio
@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("source,age", [("espn", 30), ("statpal", 90), ("odds_api", 10)])
async def test_score_clock_preserved_independent_of_probability(monkeypatch, fresh, source, age):
    value = event()
    value.home_score, value.away_score = 5, 1
    value.score_source = source
    value.score_observed_at = NOW - timedelta(seconds=age)
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    monkeypatch.setattr(feed, "_get_championship_probabilities", AsyncMock(return_value={}))
    if fresh:
        db = AsyncMock()
        db.execute.return_value = result([value])
        monkeypatch.setattr(feed_prices, "folded_probability_sources_with_revision", AsyncMock(return_value=(
            {"kalshi": {"value": .97, "updated_at": NOW.isoformat()}}, {"1": 7})))
        items, states = await feed_prices._event_cards(db, [value.id], NOW)
        assert states == {f"event-{value.id}": "updated"}
    else:
        items = await feed._score_events(_mock_db([value]), NOW, None, PersonalizationContext())
    data = next(item["data"] for item in items if item["data"]["id"] == value.id)
    assert (data["home_score"], data["away_score"]) == (5, 1)
    assert data["score_source"] == source
    assert data["score_observed_at"] == value.score_observed_at.isoformat()
    assert data["score_observed_at"] != NOW.isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize("source,clock", [(None, None), ("espn", None), (None, NOW)])
async def test_unknown_or_half_stamp_stays_absent(monkeypatch, source, clock):
    value = event()
    value.score_source, value.score_observed_at = source, clock
    monkeypatch.setattr(feed, "enrich_event_team_data", AsyncMock())
    db = AsyncMock()
    db.execute.return_value = result([])
    items = await feed._score_events(db, NOW, None, PersonalizationContext(),
        price_refresh_events=[FoldedBlendView(value, value.win_probability_sources)])
    assert items
    assert "score_source" not in items[0]["data"]
    assert "score_observed_at" not in items[0]["data"]
