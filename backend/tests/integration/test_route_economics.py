"""Integration tests for GET /api/economics.

Validates response shape, empty-DB defaults, theme structure,
seeded-data behavior, and HTTP method rejection.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Helpers for building mock market / outcome objects
# ---------------------------------------------------------------------------


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


def _query_result(items):
    return _MockResult(items)


def _outcome(name, probability, *, outcome_id=1, rank=1, change_24h=0):
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
    name="Will the event happen?",
    external_id="kxmock",
    source="kalshi",
    category="news",
    llm_sport_category="economics",
    outcomes=None,
    resolution_date=None,
    updated_at=None,
    volume_24h=1000,
    image_url=None,
    hook_description=None,
    status="open",
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source=source,
        category=category,
        llm_sport_category=llm_sport_category,
        outcomes=outcomes or [
            _outcome("Yes", 0.55, outcome_id=market_id * 10, rank=1),
            _outcome("No", 0.45, outcome_id=market_id * 10 + 1, rank=2),
        ],
        resolution_date=resolution_date or now + timedelta(days=30),
        updated_at=updated_at or now,
        volume_24h=volume_24h,
        image_url=image_url,
        hook_description=hook_description,
        status=status,
    )


# ============================================================================
# Basic response shape (empty DB)
# ============================================================================


class TestEconomicsBasicShape:
    """GET /api/economics with empty DB returns a valid, complete structure."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/economics")
        assert resp.status_code == 200

    async def test_top_level_keys(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        expected = {"total_markets", "updated_at", "themes", "by_source", "cross_source"}
        assert expected == set(body.keys()), f"Unexpected keys: {set(body.keys()) - expected}"

    async def test_total_markets_zero_when_empty(self, client):
        body = (await client.get("/api/economics")).json()
        assert body["total_markets"] == 0

    async def test_updated_at_is_iso(self, client):
        body = (await client.get("/api/economics")).json()
        assert isinstance(body["updated_at"], str)
        assert "T" in body["updated_at"]

    async def test_cross_source_empty_list(self, client):
        body = (await client.get("/api/economics")).json()
        assert body["cross_source"] == []

    async def test_by_source_both_zero(self, client):
        body = (await client.get("/api/economics")).json()
        assert body["by_source"] == {"kalshi": 0, "polymarket": 0}


# ============================================================================
# Theme structure validation
# ============================================================================


class TestEconomicsThemes:
    """Each theme section has the expected sub-keys and correct types."""

    EXPECTED_THEMES = {
        "fed", "inflation", "jobs", "recession",
        "markets", "energy", "housing", "trade", "government",
    }

    async def test_all_theme_keys_present(self, client):
        body = (await client.get("/api/economics")).json()
        assert self.EXPECTED_THEMES == set(body["themes"].keys())

    async def test_fed_structure(self, client):
        fed = (await client.get("/api/economics")).json()["themes"]["fed"]
        assert isinstance(fed["count"], int) and fed["count"] >= 0
        assert isinstance(fed["fomc_meetings"], list)
        assert isinstance(fed["rate_cuts"], list)
        assert isinstance(fed["side_markets"], list)

    async def test_inflation_structure(self, client):
        inf = (await client.get("/api/economics")).json()["themes"]["inflation"]
        assert isinstance(inf["count"], int) and inf["count"] >= 0
        assert isinstance(inf["cpi_releases"], list)
        assert isinstance(inf["side_markets"], list)

    async def test_jobs_structure(self, client):
        jobs = (await client.get("/api/economics")).json()["themes"]["jobs"]
        assert isinstance(jobs["count"], int) and jobs["count"] >= 0
        assert isinstance(jobs["markets"], list)

    async def test_recession_structure(self, client):
        rec = (await client.get("/api/economics")).json()["themes"]["recession"]
        assert isinstance(rec["count"], int) and rec["count"] >= 0
        assert isinstance(rec["gdp_quarters"], list)
        assert isinstance(rec["side_markets"], list)
        # main_prob is null when empty
        assert rec["main_prob"] is None

    async def test_markets_structure(self, client):
        mkts = (await client.get("/api/economics")).json()["themes"]["markets"]
        assert isinstance(mkts["count"], int) and mkts["count"] >= 0
        assert isinstance(mkts["today"], list)
        assert isinstance(mkts["stocks"], list)
        assert isinstance(mkts["side_markets"], list)

    async def test_energy_structure(self, client):
        energy = (await client.get("/api/economics")).json()["themes"]["energy"]
        assert isinstance(energy["count"], int) and energy["count"] >= 0
        assert isinstance(energy["gas"], list)
        assert isinstance(energy["oil"], list)

    async def test_housing_structure(self, client):
        housing = (await client.get("/api/economics")).json()["themes"]["housing"]
        assert isinstance(housing["count"], int) and housing["count"] >= 0
        assert isinstance(housing["mortgage_brackets"], list)
        assert isinstance(housing["markets"], list)

    async def test_trade_structure(self, client):
        trade = (await client.get("/api/economics")).json()["themes"]["trade"]
        assert isinstance(trade["count"], int) and trade["count"] >= 0
        assert isinstance(trade["markets"], list)

    async def test_government_structure(self, client):
        gov = (await client.get("/api/economics")).json()["themes"]["government"]
        assert isinstance(gov["count"], int) and gov["count"] >= 0
        assert isinstance(gov["markets"], list)

    async def test_all_empty_counts_are_zero(self, client):
        body = (await client.get("/api/economics")).json()
        for key, section in body["themes"].items():
            assert section["count"] == 0, f"{key} count should be 0 with empty DB"


# ============================================================================
# Seeded data — single market per theme
# ============================================================================


class TestEconomicsSeededFed:
    """Fed rate-cuts market is classified and structured correctly."""

    async def test_fed_rate_cuts_populates(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=10,
                name="How many Fed rate cuts in 2026?",
                external_id="kxfedcuts-2026",
                source="polymarket",
                outcomes=[
                    _outcome("0 cuts", 0.20, outcome_id=100, rank=1),
                    _outcome("1 cut", 0.45, outcome_id=101, rank=2),
                    _outcome("2+ cuts", 0.35, outcome_id=102, rank=3),
                ],
            ),
        ])

        body = (await client.get("/api/economics")).json()
        assert body["total_markets"] == 1
        assert body["themes"]["fed"]["count"] == 1
        assert body["themes"]["fed"]["rate_cuts"] == [
            [20.0, "0 cuts"],
            [45.0, "1 cut"],
            [35.0, "2+ cuts"],
        ]

    async def test_fomc_meeting_populates(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=11,
                name="Fed funds rate after Jun 2026 FOMC meeting?",
                external_id="kxfedfunds-jun2026",
                source="kalshi",
                outcomes=[
                    _outcome("4.00%", 0.30, outcome_id=110, rank=1),
                    _outcome("4.25%", 0.50, outcome_id=111, rank=2),
                    _outcome("4.50%", 0.20, outcome_id=112, rank=3),
                ],
            ),
        ])

        body = (await client.get("/api/economics")).json()
        fed = body["themes"]["fed"]
        assert fed["count"] == 1
        assert len(fed["fomc_meetings"]) == 1
        meeting = fed["fomc_meetings"][0]
        assert "date" in meeting
        assert "dist" in meeting
        assert "market_id" in meeting
        assert isinstance(meeting["dist"], list)


class TestEconomicsSeededInflation:
    """CPI market is classified under inflation with correct bracket shape."""

    async def test_cpi_populates_inflation(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=20,
                name="CPI YoY for May 2026?",
                external_id="kxcpi-may2026",
                source="kalshi",
                outcomes=[
                    _outcome("2.0%-2.5%", 0.25, outcome_id=200, rank=1),
                    _outcome("2.5%-3.0%", 0.40, outcome_id=201, rank=2),
                    _outcome("3.0%+", 0.35, outcome_id=202, rank=3),
                ],
            ),
        ])

        body = (await client.get("/api/economics")).json()
        inf = body["themes"]["inflation"]
        assert inf["count"] == 1
        assert len(inf["cpi_releases"]) == 1
        cpi = inf["cpi_releases"][0]
        assert cpi["mo"] == "May"
        assert isinstance(cpi["brackets"], list)
        assert len(cpi["brackets"]) == 3
        assert "peakIs" in cpi


class TestEconomicsSeededRecession:
    """Recession binary market sets main_prob correctly."""

    async def test_recession_main_prob(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=30,
                name="Will there be a US recession in 2026?",
                external_id="kxrecession-2026",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.35, outcome_id=300, rank=1),
                    _outcome("No", 0.65, outcome_id=301, rank=2),
                ],
            ),
        ])

        body = (await client.get("/api/economics")).json()
        rec = body["themes"]["recession"]
        assert rec["count"] == 1
        assert rec["main_prob"] == 35.0


class TestEconomicsSeededJobs:
    """Jobs market is classified and placed in the jobs section."""

    async def test_jobs_market(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(
                market_id=40,
                name="Unemployment rate above 4.5% by Dec 2026?",
                external_id="kxunemployment-dec2026",
                source="kalshi",
                outcomes=[
                    _outcome("Yes", 0.25, outcome_id=400, rank=1),
                    _outcome("No", 0.75, outcome_id=401, rank=2),
                ],
            ),
        ])

        body = (await client.get("/api/economics")).json()
        assert body["themes"]["jobs"]["count"] == 1
        assert len(body["themes"]["jobs"]["markets"]) == 1
        row = body["themes"]["jobs"]["markets"][0]
        assert row["q"] == "Unemployment rate above 4.5% by Dec 2026?"
        assert row["market_id"] == 40


class TestEconomicsSeededBySource:
    """by_source counts reflect the actual market sources."""

    async def test_mixed_sources(self, client, mock_db):
        mock_db.execute.return_value = _query_result([
            _market(market_id=50, name="Fed rate cut?", external_id="kxfedcuts-a", source="kalshi"),
            _market(market_id=51, name="GDP growth?", external_id="poly-gdp", source="polymarket"),
            _market(market_id=52, name="Oil price?", external_id="kxoil-a", source="kalshi"),
        ])

        body = (await client.get("/api/economics")).json()
        assert body["total_markets"] == 3
        assert body["by_source"]["kalshi"] == 2
        assert body["by_source"]["polymarket"] == 1


# ============================================================================
# HTTP method rejection
# ============================================================================


class TestEconomicsHTTPMethods:
    """Only GET is allowed on /api/economics."""

    async def test_post_rejected(self, client):
        resp = await client.post("/api/economics")
        assert resp.status_code == 405

    async def test_put_rejected(self, client):
        resp = await client.put("/api/economics")
        assert resp.status_code == 405

    async def test_delete_rejected(self, client):
        resp = await client.delete("/api/economics")
        assert resp.status_code == 405


# ============================================================================
# Query parameter resilience
# ============================================================================


class TestEconomicsQueryParams:
    """Unknown query parameters are silently ignored."""

    async def test_extra_params_ignored(self, client):
        resp = await client.get("/api/economics?limit=5&source=kalshi&bogus=yes")
        assert resp.status_code == 200
        body = resp.json()
        assert "themes" in body
