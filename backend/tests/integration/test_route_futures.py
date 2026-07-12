"""Contract tests for futures endpoints.

- GET /api/futures/{market_id} — market detail
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _result_unique_all(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _result_all(values):
    result = MagicMock()
    result.all.return_value = values
    return result


def _result_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _sport(key="basketball_nba", name="NBA"):
    return SimpleNamespace(key=key, name=name)


def _outcome(
    outcome_id,
    name,
    *,
    probability=0.5,
    american_odds=100,
    rank=1,
    movement=None,
):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        current_american_odds=american_odds,
        rank=rank,
        probability_change_24h=movement,
        rank_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        last_updated=None,
    )


def _market(
    market_id=42,
    *,
    outcomes=(),
    sport=None,
    canonical_market_key=None,
):
    now = datetime(2026, 5, 17, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name="NBA Championship Winner",
        description="Winner of the NBA Finals",
        sport=sport or _sport(),
        category="championship",
        llm_sport_category="basketball",
        status="open",
        source="kalshi",
        external_id="KXNBA-CHAMP",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=now,
        outcomes=list(outcomes),
        category_tags=["sports", "basketball"],
        created_at=now,
        updated_at=now,
        group_id="nba-champ",
        canonical_market_key=canonical_market_key,
        hook_description="NBA title market",
        image_url="https://example.com/nba.jpg",
    )


class TestFuturesList:
    """GET /api/futures — market list contract."""

    async def test_empty_response_contract(self, client, mock_db):
        mock_db.execute.return_value = _result_unique_all([])

        resp = await client.get("/api/futures")

        assert resp.status_code == 200
        assert resp.json() == {"markets": [], "count": 0}

    async def test_market_summary_shape_filters_placeholders_and_sorts(
        self,
        client,
        mock_db,
    ):
        market = _market(
            outcomes=[
                _outcome(1, "Player A", probability=0.99, rank=1),
                _outcome(2, "Celtics", probability=0.7, rank=2, movement=0.08),
                _outcome(3, "Thunder", probability=0.2, rank=3),
            ],
            canonical_market_key="basketball:nba:championship",
        )
        source_row = SimpleNamespace(
            canonical_market_key="basketball:nba:championship",
            source_count=2,
            sources=["polymarket", "kalshi"],
        )
        mock_db.execute.side_effect = [
            _result_unique_all([market]),
            _result_all([source_row]),
        ]

        resp = await client.get("/api/futures?status=all")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["markets"][0]
        assert set(item) == {
            "id",
            "name",
            "sport",
            "sport_name",
            "category",
            "llm_sport_category",
            "status",
            "source",
            "resolution_date",
            "top_outcomes",
            "outcome_count",
            "category_tags",
            "updated_at",
            "source_count",
            "sources",
        }
        assert item["source_count"] == 2
        assert item["sources"] == ["kalshi", "polymarket"]
        assert item["outcome_count"] == 2
        assert [outcome["name"] for outcome in item["top_outcomes"]] == [
            "Celtics",
            "Thunder",
        ]


class TestFuturesMovers:
    """GET /api/futures/movers — movement list contract."""

    async def test_empty_response_contract(self, client, mock_db):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result

        resp = await client.get("/api/futures/movers?hours=12&limit=5")

        assert resp.status_code == 200
        assert resp.json() == {"movers": [], "timeframe_hours": 12}


class TestFuturesMarketDetail:
    """GET /api/futures/{market_id} — single market detail."""

    async def test_mocked_market_detail_contract(self, client, mock_db):
        market = _market(
            outcomes=[
                _outcome(1, "Player B", probability=1.0),
                _outcome(2, "Celtics", probability=0.64, rank=1, movement=0.04),
            ],
        )
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(market),
            _result_all([("Kalshi",), ("Polymarket",)]),
            # source_breakdown: latest per (outcome, bookmaker) with rn=1
            _result_all([(2, "Kalshi", 0.62, ts), (2, "Polymarket", 0.66, ts)]),
        ]

        resp = await client.get("/api/futures/42")

        assert resp.status_code == 200
        body = resp.json()
        expected_keys = {
            "id",
            "name",
            "description",
            "sport",
            "sport_name",
            "category",
            "llm_sport_category",
            "status",
            "source",
            "external_id",
            "mutually_exclusive",
            "commence_time",
            "resolution_date",
            "outcomes",
            "outcome_count",
            "bookmakers",
            "category_tags",
            "created_at",
            "updated_at",
            "group_id",
            "canonical_market_key",
            "hook_description",
            "image_url",
            "event_concept_key",
            "hub_slug",
            "source_breakdown",
        }
        assert set(body) == expected_keys
        assert body["id"] == 42
        assert body["bookmakers"] == ["Kalshi", "Polymarket"]
        assert body["outcome_count"] == 1
        assert body["outcomes"][0]["name"] == "Celtics"
        assert len(body["source_breakdown"]) == 2
        assert body["source_breakdown"][0]["source"] == "Kalshi"
        assert body["source_breakdown"][1]["source"] == "Polymarket"

    async def test_nonexistent_market_returns_404(self, client):
        resp = await client.get("/api/futures/999999")
        assert resp.status_code == 404

    async def test_invalid_id_returns_403(self, client):
        resp = await client.get("/api/futures/not-a-number")
        assert resp.status_code == 422
