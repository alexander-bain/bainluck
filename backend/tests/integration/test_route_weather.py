"""Integration tests for weather API endpoints.

Covers all 7 weather sub-routes:
- GET /api/weather/featured   — hero rotation cards
- GET /api/weather/cities     — temperature distributions by city
- GET /api/weather/rain       — NYC daily + monthly city rain
- GET /api/weather/events     — natural disaster markets (hurricane/earthquake/tornado)
- GET /api/weather/climate    — long-range climate markets
- GET /api/weather/wildcards  — rare weather markets (volcano, arctic, solar)
- GET /api/weather/cross-source — markets on both Kalshi and Polymarket

Tests:
1. Each endpoint returns 200 with empty DB
2. Response shape has expected top-level keys and types
3. Seeded data flows through to the response correctly
4. POST rejection (GET-only endpoints)
5. Unknown sub-routes return 404
6. Unexpected query params are safely ignored

Uses the shared ``client`` and ``mock_db`` fixtures from conftest.py.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outcome(name, probability, *, outcome_id=1, rank=1, change_24h=None):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=change_24h,
        rank=rank,
    )


def _market(
    *,
    market_id=1,
    name="Will it rain?",
    external_id="kxweather",
    source="kalshi",
    llm_sport_category="weather",
    outcomes=None,
    resolution_date=None,
    updated_at=None,
    status="open",
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source=source,
        category="weather",
        llm_sport_category=llm_sport_category,
        outcomes=outcomes or [
            _outcome("Yes", 0.60, outcome_id=market_id * 10),
            _outcome("No", 0.40, outcome_id=market_id * 10 + 1),
        ],
        resolution_date=resolution_date or now + timedelta(days=14),
        updated_at=updated_at or now,
        status=status,
    )


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


def _query_result(items):
    return _MockResult(items)


# ============================================================================
# 1. Featured — GET /api/weather/featured
# ============================================================================


class TestWeatherFeatured:
    """GET /api/weather/featured — hero rotation cards."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/featured")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/weather/featured")
        body = resp.json()
        assert body == []

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/featured")
        assert isinstance(resp.json(), list)

    async def test_item_shape_with_seeded_market(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=101,
                name="Will a hurricane make landfall in Florida?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.72, outcome_id=1010),
                    _outcome("No", 0.28, outcome_id=1011),
                ],
                resolution_date=now + timedelta(days=30),
            )
        ])

        resp = await client.get("/api/weather/featured")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1

        item = body[0]
        assert item["q"] == "Will a hurricane make landfall in Florida?"
        assert item["prob"] == 72
        assert item["src"] == "polymarket"
        assert item["tag"] == "Hurricane"
        assert item["market_id"] == 101
        assert isinstance(item["closes"], str)

    async def test_featured_fields_present(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=201,
                name="Temperature in NYC above 90F?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.55, outcome_id=2010),
                    _outcome("No", 0.45, outcome_id=2011),
                ],
            )
        ])

        resp = await client.get("/api/weather/featured")
        body = resp.json()
        for item in body:
            assert "q" in item
            assert "prob" in item
            assert "src" in item
            assert "tag" in item
            assert "closes" in item
            assert "market_id" in item
            assert isinstance(item["q"], str)
            assert isinstance(item["prob"], (int, float))
            assert isinstance(item["src"], str)
            assert isinstance(item["tag"], str)

    async def test_prob_is_0_to_100_scale(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=301,
                name="Will it rain in NYC on Tuesday?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.65, outcome_id=3010),
                    _outcome("No", 0.35, outcome_id=3011),
                ],
            )
        ])

        resp = await client.get("/api/weather/featured")
        body = resp.json()
        for item in body:
            assert 0 <= item["prob"] <= 100

    async def test_max_five_featured(self, client, mock_db):
        """Featured endpoint caps at 5 items."""
        markets = [
            _market(
                market_id=400 + i,
                name=f"Weather question {i}?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.5 + i * 0.01, outcome_id=4000 + i * 10),
                    _outcome("No", 0.5 - i * 0.01, outcome_id=4000 + i * 10 + 1),
                ],
                resolution_date=datetime.now(timezone.utc) + timedelta(days=5 + i),
            )
            for i in range(10)
        ]
        mock_db.execute.return_value = _query_result(markets)

        resp = await client.get("/api/weather/featured")
        body = resp.json()
        assert len(body) <= 5

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/featured")
        assert resp.status_code == 405

    async def test_ignores_unexpected_query_params(self, client):
        resp = await client.get("/api/weather/featured?limit=5&foo=bar")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ============================================================================
# 2. Cities — GET /api/weather/cities
# ============================================================================


class TestWeatherCities:
    """GET /api/weather/cities — temperature distributions by city."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/cities")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/weather/cities")
        assert resp.json() == []

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/cities")
        assert isinstance(resp.json(), list)

    async def test_city_item_shape_with_seeded_data(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=501,
                name="Highest temperature in New York on May 20?",
                source="kalshi",
                outcomes=[
                    _outcome("50-60°F", 0.15, outcome_id=5010, rank=1),
                    _outcome("60-70°F", 0.35, outcome_id=5011, rank=2),
                    _outcome("70-80°F", 0.40, outcome_id=5012, rank=3),
                    _outcome("80-90°F", 0.10, outcome_id=5013, rank=4),
                ],
                resolution_date=now + timedelta(days=2),
            )
        ])

        resp = await client.get("/api/weather/cities")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) >= 1

        city = body[0]
        assert "id" in city
        assert "name" in city
        assert "region" in city
        assert "high" in city
        assert isinstance(city["name"], str)
        assert isinstance(city["region"], str)

    async def test_high_structure(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=601,
                name="Highest temperature in Chicago on May 20?",
                source="kalshi",
                outcomes=[
                    _outcome("50-60°F", 0.30, outcome_id=6010, rank=1),
                    _outcome("60-70°F", 0.50, outcome_id=6011, rank=2),
                    _outcome("70-80°F", 0.20, outcome_id=6012, rank=3),
                ],
                resolution_date=now + timedelta(days=2),
            )
        ])

        resp = await client.get("/api/weather/cities")
        body = resp.json()
        assert len(body) >= 1

        high = body[0]["high"]
        assert "unit" in high
        assert high["unit"] in ("F", "C")
        assert "dist" in high
        assert isinstance(high["dist"], list)
        assert "mode" in high

    async def test_dist_items_have_label_and_prob(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=701,
                name="Highest temperature in Miami on May 20?",
                source="kalshi",
                outcomes=[
                    _outcome("70-80°F", 0.25, outcome_id=7010, rank=1),
                    _outcome("80-90°F", 0.55, outcome_id=7011, rank=2),
                    _outcome("90-100°F", 0.20, outcome_id=7012, rank=3),
                ],
                resolution_date=now + timedelta(days=2),
            )
        ])

        resp = await client.get("/api/weather/cities")
        body = resp.json()
        for city in body:
            for bucket in city["high"]["dist"]:
                assert "label" in bucket
                assert "prob" in bucket
                assert isinstance(bucket["label"], str)
                assert isinstance(bucket["prob"], (int, float))

    async def test_city_has_coordinate_fields(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=801,
                name="Highest temperature in London on May 20?",
                source="polymarket",
                outcomes=[
                    _outcome("10-15°C", 0.30, outcome_id=8010),
                    _outcome("15-20°C", 0.50, outcome_id=8011),
                    _outcome("20-25°C", 0.20, outcome_id=8012),
                ],
                resolution_date=now + timedelta(days=2),
            )
        ])

        resp = await client.get("/api/weather/cities")
        body = resp.json()
        for city in body:
            assert "x" in city
            assert "y" in city
            assert isinstance(city["x"], (int, float))
            assert isinstance(city["y"], (int, float))

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/cities")
        assert resp.status_code == 405


# ============================================================================
# 3. Rain — GET /api/weather/rain
# ============================================================================


class TestWeatherRain:
    """GET /api/weather/rain — NYC daily + monthly city rain data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/rain")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_groups(self, client):
        resp = await client.get("/api/weather/rain")
        body = resp.json()
        assert body == {"daily": [], "monthly": []}

    async def test_has_daily_and_monthly_keys(self, client):
        resp = await client.get("/api/weather/rain")
        body = resp.json()
        assert "daily" in body
        assert "monthly" in body
        assert isinstance(body["daily"], list)
        assert isinstance(body["monthly"], list)

    async def test_daily_item_shape_with_seeded_data(self, client, mock_db):
        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        mock_db.execute.side_effect = [
            # First query: daily NYC rain
            _query_result([
                _market(
                    market_id=901,
                    name="Will it rain in NYC on Tuesday?",
                    source="kalshi",
                    outcomes=[
                        _outcome("Yes", 0.73, outcome_id=9010),
                        _outcome("No", 0.27, outcome_id=9011),
                    ],
                    resolution_date=tomorrow,
                )
            ]),
            # Second query: monthly rain
            _query_result([]),
        ]

        resp = await client.get("/api/weather/rain")
        body = resp.json()
        assert len(body["daily"]) == 1

        item = body["daily"][0]
        assert "day" in item
        assert "date" in item
        assert "prob" in item
        assert "icon" in item
        assert isinstance(item["day"], str)
        assert isinstance(item["date"], str)
        assert isinstance(item["prob"], (int, float))
        assert 0 <= item["prob"] <= 100
        assert isinstance(item["icon"], str)

    async def test_monthly_item_shape_with_seeded_data(self, client, mock_db):
        now = datetime.now(timezone.utc)

        mock_db.execute.side_effect = [
            # First query: daily NYC rain
            _query_result([]),
            # Second query: monthly rain
            _query_result([
                _market(
                    market_id=1001,
                    name="Rain in Miami in June 2026",
                    source="polymarket",
                    outcomes=[
                        _outcome("Yes", 0.88, outcome_id=10010, change_24h=0.02),
                        _outcome("No", 0.12, outcome_id=10011, change_24h=-0.02),
                    ],
                    resolution_date=now + timedelta(days=30),
                )
            ]),
        ]

        resp = await client.get("/api/weather/rain")
        body = resp.json()
        assert len(body["monthly"]) == 1

        item = body["monthly"][0]
        assert "city" in item
        assert "prob" in item
        assert "src" in item
        assert "delta24h" in item
        assert isinstance(item["city"], str)
        assert isinstance(item["prob"], (int, float))
        assert isinstance(item["src"], str)
        assert isinstance(item["delta24h"], (int, float))

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/rain")
        assert resp.status_code == 405


# ============================================================================
# 4. Events — GET /api/weather/events
# ============================================================================


class TestWeatherEvents:
    """GET /api/weather/events — natural disaster markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/events")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_groups(self, client):
        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert body == {"hurricane": [], "earthquake": [], "tornadoes": []}

    async def test_has_three_event_groups(self, client):
        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert "hurricane" in body
        assert "earthquake" in body
        assert "tornadoes" in body
        assert isinstance(body["hurricane"], list)
        assert isinstance(body["earthquake"], list)
        assert isinstance(body["tornadoes"], list)

    async def test_hurricane_market_populates_hurricane_group(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1101,
                name="Will a hurricane hit the Gulf Coast in 2026?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.40, outcome_id=11010),
                    _outcome("No", 0.60, outcome_id=11011),
                ],
                resolution_date=now + timedelta(days=90),
            )
        ])

        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert len(body["hurricane"]) == 1
        assert body["earthquake"] == []
        assert body["tornadoes"] == []

        item = body["hurricane"][0]
        assert item["q"] == "Will a hurricane hit the Gulf Coast in 2026?"
        assert item["prob"] == 60  # highest prob is "No" at 60%
        assert item["src"] == "kalshi"
        assert isinstance(item["closes"], str)

    async def test_earthquake_market_populates_earthquake_group(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1201,
                name="Will an earthquake of magnitude 7+ hit California?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.15, outcome_id=12010),
                    _outcome("No", 0.85, outcome_id=12011),
                ],
                resolution_date=now + timedelta(days=180),
            )
        ])

        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert len(body["earthquake"]) == 1
        assert body["hurricane"] == []
        assert body["tornadoes"] == []

    async def test_tornado_market_populates_tornadoes_group(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1301,
                name="Will a tornado hit Oklahoma in May 2026?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.55, outcome_id=13010),
                    _outcome("No", 0.45, outcome_id=13011),
                ],
                resolution_date=now + timedelta(days=14),
            )
        ])

        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert len(body["tornadoes"]) == 1
        assert body["hurricane"] == []
        assert body["earthquake"] == []

    async def test_event_items_have_no_internal_keys(self, client, mock_db):
        """Ensure _res_date internal sort key is stripped from response."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1401,
                name="Will a hurricane make landfall in 2026?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.30, outcome_id=14010),
                    _outcome("No", 0.70, outcome_id=14011),
                ],
                resolution_date=now + timedelta(days=60),
            )
        ])

        resp = await client.get("/api/weather/events")
        body = resp.json()
        for group in body.values():
            for item in group:
                assert "_res_date" not in item

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/events")
        assert resp.status_code == 405


# ============================================================================
# 5. Climate — GET /api/weather/climate
# ============================================================================


class TestWeatherClimate:
    """GET /api/weather/climate — long-range climate markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/climate")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/weather/climate")
        assert resp.json() == []

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/climate")
        assert isinstance(resp.json(), list)

    async def test_climate_item_shape(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1501,
                name="Will 2026 be the hottest year on record?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.62, outcome_id=15010),
                    _outcome("No", 0.38, outcome_id=15011),
                ],
                resolution_date=now + timedelta(days=200),
            )
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert len(body) >= 1

        item = body[0]
        assert "q" in item
        assert "prob" in item
        assert "src" in item
        assert "closes" in item
        assert "scale" in item
        assert isinstance(item["q"], str)
        assert isinstance(item["prob"], (int, float))
        assert isinstance(item["src"], str)
        assert item["scale"] in ("2026", "2030", "2050")

    async def test_scale_classification_2050(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1601,
                name="Will CO2 levels exceed 500 ppm by 2050?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.45, outcome_id=16010),
                    _outcome("No", 0.55, outcome_id=16011),
                ],
                resolution_date=now + timedelta(days=365 * 25),
            )
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert len(body) >= 1
        assert body[0]["scale"] == "2050"

    async def test_excludes_temperature_and_rain_markets(self, client, mock_db):
        """Climate should filter out temperature/rain/snow/daily markets."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1701,
                name="Highest temperature in NYC on May 20?",
                source="kalshi",
                outcomes=[
                    _outcome("70-80°F", 0.50, outcome_id=17010),
                    _outcome("80-90°F", 0.50, outcome_id=17011),
                ],
                resolution_date=now + timedelta(days=300),
            )
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/climate")
        assert resp.status_code == 405


# ============================================================================
# 6. Wildcards — GET /api/weather/wildcards
# ============================================================================


class TestWeatherWildcards:
    """GET /api/weather/wildcards — rare weather markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/wildcards")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/weather/wildcards")
        assert resp.json() == []

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/wildcards")
        assert isinstance(resp.json(), list)

    async def test_wildcard_item_shape(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1801,
                name="Will a volcano erupt in Yellowstone by 2030?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.02, outcome_id=18010),
                    _outcome("No", 0.98, outcome_id=18011),
                ],
                resolution_date=now + timedelta(days=365 * 4),
            )
        ])

        resp = await client.get("/api/weather/wildcards")
        body = resp.json()
        assert len(body) >= 1

        item = body[0]
        assert "q" in item
        assert "prob" in item
        assert "src" in item
        assert "closes" in item
        assert "tag" in item
        assert isinstance(item["q"], str)
        assert isinstance(item["prob"], (int, float))
        assert isinstance(item["src"], str)
        assert isinstance(item["tag"], str)
        assert item["tag"] == "Wild card"

    async def test_sorted_by_probability_descending(self, client, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=1901,
                name="Will a volcano erupt in Iceland?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.30, outcome_id=19010),
                    _outcome("No", 0.70, outcome_id=19011),
                ],
                resolution_date=now + timedelta(days=90),
            ),
            _market(
                market_id=1902,
                name="Will the arctic ice cap reach record low?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.55, outcome_id=19020),
                    _outcome("No", 0.45, outcome_id=19021),
                ],
                resolution_date=now + timedelta(days=120),
            ),
        ])

        resp = await client.get("/api/weather/wildcards")
        body = resp.json()
        assert len(body) == 2
        # Sorted by prob desc: 70 (No from volcano) >= 55 (Yes from arctic)
        assert body[0]["prob"] >= body[1]["prob"]

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/wildcards")
        assert resp.status_code == 405


# ============================================================================
# 7. Cross-source — GET /api/weather/cross-source
# ============================================================================


class TestWeatherCrossSource:
    """GET /api/weather/cross-source — markets on both Kalshi and Polymarket."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/cross-source")
        assert resp.status_code == 200

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/weather/cross-source")
        assert resp.json() == []

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/cross-source")
        assert isinstance(resp.json(), list)

    async def test_cross_source_match_shape(self, client, mock_db):
        """When the same question exists on both platforms, a match appears."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=2001,
                name="Will a hurricane hit Florida in 2026?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.45, outcome_id=20010),
                    _outcome("No", 0.55, outcome_id=20011),
                ],
                resolution_date=now + timedelta(days=90),
            ),
            _market(
                market_id=2002,
                name="Will a hurricane hit Florida in 2026?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.52, outcome_id=20020),
                    _outcome("No", 0.48, outcome_id=20021),
                ],
                resolution_date=now + timedelta(days=90),
            ),
        ])

        resp = await client.get("/api/weather/cross-source")
        body = resp.json()
        assert len(body) == 1

        match = body[0]
        assert "q" in match
        assert "kalshi" in match
        assert "poly" in match
        assert "delta" in match
        assert "category" in match
        assert "kalshi_market_id" in match
        assert "poly_market_id" in match
        assert isinstance(match["kalshi"], (int, float))
        assert isinstance(match["poly"], (int, float))
        assert isinstance(match["delta"], (int, float))
        assert match["delta"] >= 0

    async def test_no_match_when_single_source(self, client, mock_db):
        """Markets from only one source should not produce cross-source matches."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=2101,
                name="Will it snow in LA?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.01, outcome_id=21010),
                    _outcome("No", 0.99, outcome_id=21011),
                ],
                resolution_date=now + timedelta(days=30),
            ),
        ])

        resp = await client.get("/api/weather/cross-source")
        body = resp.json()
        assert body == []

    async def test_rejects_post(self, client):
        resp = await client.post("/api/weather/cross-source")
        assert resp.status_code == 405


# ============================================================================
# 8. Zombie market / health exclusion tests
# ============================================================================


class TestWeatherZombieMarketExclusion:
    """Verify that resolved/past-resolution markets are excluded."""

    async def test_past_resolution_market_excluded_from_featured(self, client, mock_db):
        """A market whose resolution_date is in the past should not appear."""
        now = datetime.now(timezone.utc)
        # Both markets pass through mock_db (no SQL filter in mock),
        # but the featured endpoint skips markets with days < 0.5
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3001,
                name="Will it rain in NYC yesterday?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.60, outcome_id=30010),
                    _outcome("No", 0.40, outcome_id=30011),
                ],
                resolution_date=now - timedelta(days=2),
            ),
            _market(
                market_id=3002,
                name="Will it rain in NYC next week?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.55, outcome_id=30020),
                    _outcome("No", 0.45, outcome_id=30021),
                ],
                resolution_date=now + timedelta(days=7),
            ),
        ])

        resp = await client.get("/api/weather/featured")
        body = resp.json()
        # The past-resolution market should be filtered by the
        # featured scoring (days < 0.5 → skipped). Only the future one remains.
        names = [item["q"] for item in body]
        assert "Will it rain in NYC yesterday?" not in names
        assert "Will it rain in NYC next week?" in names

    async def test_open_future_market_passes_through(self, client, mock_db):
        """An open market with a future resolution_date should appear."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3003,
                name="Will a hurricane hit Florida in 2026?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.45, outcome_id=30030),
                    _outcome("No", 0.55, outcome_id=30031),
                ],
                resolution_date=now + timedelta(days=60),
                status="open",
            ),
        ])

        resp = await client.get("/api/weather/featured")
        body = resp.json()
        assert len(body) == 1
        assert body[0]["q"] == "Will a hurricane hit Florida in 2026?"


class TestWeatherHealthExclusion:
    """Verify that health/pandemic markets are excluded from climate section."""

    async def test_pandemic_market_excluded_from_climate(self, client, mock_db):
        """Markets about pandemics should not appear in climate results."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3101,
                name="Will a pandemic be declared by 2030?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.20, outcome_id=31010),
                    _outcome("No", 0.80, outcome_id=31011),
                ],
                resolution_date=now + timedelta(days=365 * 4),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []

    async def test_bird_flu_market_excluded_from_climate(self, client, mock_db):
        """Bird flu markets should not appear in climate results."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3102,
                name="Will bird flu reach 1000 US cases by 2030?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.15, outcome_id=31020),
                    _outcome("No", 0.85, outcome_id=31021),
                ],
                resolution_date=now + timedelta(days=365 * 4),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []

    async def test_virus_outbreak_excluded_from_climate(self, client, mock_db):
        """Virus outbreak markets should not appear in climate results."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3103,
                name="Will a major virus outbreak occur by 2050?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.30, outcome_id=31030),
                    _outcome("No", 0.70, outcome_id=31031),
                ],
                resolution_date=now + timedelta(days=365 * 24),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []

    async def test_h5n1_excluded_from_climate(self, client, mock_db):
        """H5N1 markets should not appear in climate results."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3104,
                name="Will H5N1 become a global emergency by 2030?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.10, outcome_id=31040),
                    _outcome("No", 0.90, outcome_id=31041),
                ],
                resolution_date=now + timedelta(days=365 * 4),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []

    async def test_legitimate_climate_market_passes_through(self, client, mock_db):
        """A real climate market should still appear."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3105,
                name="Will 2026 be the hottest year on record?",
                source="polymarket",
                outcomes=[
                    _outcome("Yes", 0.62, outcome_id=31050),
                    _outcome("No", 0.38, outcome_id=31051),
                ],
                resolution_date=now + timedelta(days=200),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert len(body) == 1
        assert body[0]["q"] == "Will 2026 be the hottest year on record?"

    async def test_disease_excluded_from_climate(self, client, mock_db):
        """Disease markets should not appear in climate results."""
        now = datetime.now(timezone.utc)
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=3106,
                name="Will a new disease emerge by 2030?",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.25, outcome_id=31060),
                    _outcome("No", 0.75, outcome_id=31061),
                ],
                resolution_date=now + timedelta(days=365 * 4),
            ),
        ])

        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert body == []


# ============================================================================
# Error handling and edge cases
# ============================================================================


class TestWeatherErrorHandling:
    """Error handling, 404s, and parameter behavior."""

    async def test_unknown_subroute_returns_404(self, client):
        resp = await client.get("/api/weather/not-a-real-endpoint")
        assert resp.status_code == 404

    async def test_another_unknown_subroute_returns_404(self, client):
        resp = await client.get("/api/weather/forecast")
        assert resp.status_code == 404

    @pytest.mark.parametrize("endpoint", [
        "/api/weather/featured",
        "/api/weather/cities",
        "/api/weather/rain",
        "/api/weather/events",
        "/api/weather/climate",
        "/api/weather/wildcards",
        "/api/weather/cross-source",
    ])
    async def test_all_endpoints_reject_post(self, client, endpoint):
        resp = await client.post(endpoint)
        assert resp.status_code == 405

    @pytest.mark.parametrize("endpoint", [
        "/api/weather/featured",
        "/api/weather/cities",
        "/api/weather/rain",
        "/api/weather/events",
        "/api/weather/climate",
        "/api/weather/wildcards",
        "/api/weather/cross-source",
    ])
    async def test_unexpected_query_params_ignored(self, client, endpoint):
        resp = await client.get(f"{endpoint}?limit=abc&offset=-1&source=test")
        assert resp.status_code == 200

    @pytest.mark.parametrize("endpoint", [
        "/api/weather/featured",
        "/api/weather/cities",
        "/api/weather/rain",
        "/api/weather/events",
        "/api/weather/climate",
        "/api/weather/wildcards",
        "/api/weather/cross-source",
    ])
    async def test_all_endpoints_return_200(self, client, endpoint):
        resp = await client.get(endpoint)
        assert resp.status_code == 200
