"""Contract tests for League Futures API: GET /api/leagues/{sport_key}.

Tests that the endpoint returns the expected response shape with correct
top-level keys and sectioned market grouping — even when the DB has no data.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers: mock FuturesMarket / FuturesOutcome for seeded tests
# ---------------------------------------------------------------------------


def _mock_outcome(
    *, outcome_id=1, name="Yes", probability=0.55, opening=None,
    rank=1, change_24h=0, team_id=None,
):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        opening_probability=opening,
        probability_change_24h=change_24h,
        rank=rank,
        team_id=team_id,
    )


def _mock_market(
    *, market_id=1, name="NBA Championship Winner", source="kalshi",
    external_id="KXNBA-CHAMP", category="championship",
    llm_sport_category="basketball", llm_league="nba",
    market_tier=1, status="open", event_id=None,
    outcomes=None, resolution_date=None,
    canonical_market_key=None,
):
    now = datetime.now(timezone.utc)
    m = SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        external_id=external_id,
        category=category,
        llm_sport_category=llm_sport_category,
        llm_league=llm_league,
        market_tier=market_tier,
        status=status,
        event_id=event_id,
        outcomes=outcomes or [
            _mock_outcome(outcome_id=market_id * 10, name="Team A", probability=0.35),
            _mock_outcome(outcome_id=market_id * 10 + 1, name="Team B", probability=0.25, rank=2),
        ],
        resolution_date=resolution_date or now + timedelta(days=90),
        canonical_market_key=canonical_market_key,
    )
    return m


def _scalars_result(items):
    """Build a mock result with .scalars().unique().all() returning items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    return result


# ============================================================================
# GET /api/leagues/{sport_key} — empty DB
# ============================================================================


class TestLeagueFuturesEmpty:
    """GET /api/leagues/{sport_key} with no data in DB."""

    async def test_returns_200_for_known_sport(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200

    async def test_has_top_level_keys(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert "sport_key" in body
        assert "sections" in body
        assert "total_markets" in body

    async def test_sport_key_echoed_back(self, client):
        resp = await client.get("/api/leagues/icehockey_nhl")
        body = resp.json()
        assert body["sport_key"] == "icehockey_nhl"

    async def test_empty_db_has_zero_markets(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert body["total_markets"] == 0
        # Empty sections are removed, so sections should be empty dict
        assert body["sections"] == {}

    @pytest.mark.parametrize("sport_key", [
        "basketball_nba",
        "icehockey_nhl",
        "baseball_mlb",
        "americanfootball_nfl",
        "basketball_wnba",
        "soccer_epl",
        "soccer_usa_mls",
        "mma_mixed_martial_arts",
    ])
    async def test_returns_200_for_all_known_sports(self, client, sport_key):
        resp = await client.get(f"/api/leagues/{sport_key}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sport_key"] == sport_key

    async def test_unknown_sport_returns_200_empty(self, client):
        """Unknown sport keys should still return 200 with empty sections."""
        resp = await client.get("/api/leagues/curling_world")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sport_key"] == "curling_world"
        assert body["total_markets"] == 0


# ============================================================================
# GET /api/leagues/{sport_key} — seeded data
# ============================================================================


class TestLeagueFuturesSeeded:
    """Tests with seeded mock market data."""

    async def test_awards_market_classified_correctly(self, client, mock_db):
        """A tier-3 market should appear in the awards section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=10,
                name="NBA MVP Winner 2025-26",
                market_tier=3,
                category="award",
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-MVP",
                outcomes=[
                    _mock_outcome(outcome_id=100, name="Luka Doncic", probability=0.30),
                    _mock_outcome(outcome_id=101, name="Nikola Jokic", probability=0.25, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_markets"] == 1
        assert "awards" in body["sections"]
        assert len(body["sections"]["awards"]) == 1
        award = body["sections"]["awards"][0]
        assert award["name"] == "NBA MVP Winner 2025-26"
        assert award["section"] == "awards"

    async def test_series_market_classified_correctly(self, client, mock_db):
        """A market with 'series' in the name and tier 5 goes to series section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=20,
                name="Bruins vs Rangers - Series Winner",
                market_tier=5,
                llm_sport_category="hockey",
                llm_league="nhl",
                external_id="KXNHL-SERIES-BOS-NYR",
                outcomes=[
                    _mock_outcome(outcome_id=200, name="Bruins", probability=0.55),
                    _mock_outcome(outcome_id=201, name="Rangers", probability=0.45, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/icehockey_nhl")
        assert resp.status_code == 200
        body = resp.json()
        assert "series" in body["sections"]
        assert body["sections"]["series"][0]["name"] == "Bruins vs Rangers - Series Winner"

    async def test_props_market_classified_correctly(self, client, mock_db):
        """A market with 'win total' in name goes to props section."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=30,
                name="Yankees Win Total Over 95.5",
                market_tier=5,
                category="team_prop",
                llm_sport_category="baseball",
                llm_league="mlb",
                external_id="KXMLB-WINTOTAL-NYY",
                outcomes=[
                    _mock_outcome(outcome_id=300, name="Over", probability=0.48),
                    _mock_outcome(outcome_id=301, name="Under", probability=0.52, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/baseball_mlb")
        assert resp.status_code == 200
        body = resp.json()
        assert "props" in body["sections"]
        assert body["sections"]["props"][0]["name"] == "Yankees Win Total Over 95.5"

    async def test_championship_tier_markets_excluded_from_sections(
        self, client, mock_db
    ):
        """Tier 1/2 markets (championship/conference) are excluded — they're on the grid."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=40,
                name="NBA Championship Winner",
                market_tier=1,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-CHAMP",
            ),
            _mock_market(
                market_id=41,
                name="Eastern Conference Winner",
                market_tier=2,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-EAST",
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        # Both championship-tier markets excluded
        assert body["total_markets"] == 0
        assert body["sections"] == {}

    async def test_market_item_shape(self, client, mock_db):
        """Each market in a section should have the expected fields."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=50,
                name="NFL Defensive Player of the Year",
                market_tier=3,
                category="award",
                llm_sport_category="football",
                llm_league="nfl",
                external_id="KXNFL-DPOY",
                canonical_market_key="nfl_dpoy_2026",
            ),
        ])

        resp = await client.get("/api/leagues/americanfootball_nfl")
        assert resp.status_code == 200
        body = resp.json()
        market = body["sections"]["awards"][0]
        expected_keys = {
            "id", "name", "source", "market_tier", "category",
            "resolution_date", "outcome_count", "top_outcomes",
            "canonical_market_key", "section",
        }
        assert expected_keys.issubset(set(market.keys()))
        assert isinstance(market["top_outcomes"], list)
        assert len(market["top_outcomes"]) > 0

    async def test_outcome_item_shape(self, client, mock_db):
        """Each outcome should have id, name, probability, rank, etc."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=60,
                name="Vezina Trophy Winner",
                market_tier=3,
                llm_sport_category="hockey",
                llm_league="nhl",
                external_id="KXNHL-VEZINA",
                outcomes=[
                    _mock_outcome(
                        outcome_id=600, name="Connor Hellebuyck",
                        probability=0.40, opening=0.25, change_24h=0.02, team_id=42,
                    ),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/icehockey_nhl")
        assert resp.status_code == 200
        outcome = resp.json()["sections"]["awards"][0]["top_outcomes"][0]
        assert outcome["id"] == 600
        assert outcome["name"] == "Connor Hellebuyck"
        assert outcome["probability"] == 0.40
        assert outcome["opening_probability"] == 0.25
        assert outcome["movement_24h"] == 0.02
        assert outcome["team_id"] == 42
        assert outcome["rank"] == 1

    async def test_resolved_markets_filtered_out(self, client, mock_db):
        """Markets with leader >= 97% and opening >= 85% should be excluded."""
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=70,
                name="Effectively Resolved Award",
                market_tier=3,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-RESOLVED",
                outcomes=[
                    _mock_outcome(
                        outcome_id=700, name="Winner", probability=0.98, opening=0.90,
                    ),
                    _mock_outcome(
                        outcome_id=701, name="Loser", probability=0.02, rank=2, opening=0.10,
                    ),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_markets"] == 0


class TestEsportsCategoryWideFutures:
    """L2-92 (B4): the esports hub is category-wide + futures-only. There is no
    esports championship GRID, so championship-tier title/winner markets must be
    surfaced in a dedicated "futures" section instead of being dropped (as they
    are for grid sports). Matchup exclusion is a SQL-level filter, so it's not
    exercised by the mock DB — this pins the Python-side remap."""

    async def test_championship_tier_esports_surfaces_in_futures(self, client, mock_db):
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=80,
                name="LCK 2026 Season Winner",
                market_tier=1,
                llm_sport_category="esports",
                llm_league="lol",
                external_id="KXLOL-LCK26",
                outcomes=[
                    _mock_outcome(outcome_id=800, name="T1", probability=0.35),
                    _mock_outcome(outcome_id=801, name="Gen.G", probability=0.30, rank=2),
                ],
            ),
        ])

        resp = await client.get("/api/leagues/esports")
        assert resp.status_code == 200
        body = resp.json()
        # NOT dropped as a grid championship — surfaced in the futures section.
        assert "futures" in body["sections"], body["sections"].keys()
        assert body["sections"]["futures"][0]["name"] == "LCK 2026 Season Winner"
        assert body["sections"]["futures"][0]["section"] == "futures"

    async def test_grid_sports_still_drop_championship(self, client, mock_db):
        # Guard: the remap is esports-only — NBA championship markets are still
        # excluded (they live on the playoff grid).
        mock_db.execute.return_value = _scalars_result([
            _mock_market(
                market_id=81,
                name="NBA Championship Winner",
                market_tier=1,
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-CHAMP",
            ),
        ])
        body = (await client.get("/api/leagues/basketball_nba")).json()
        assert "futures" not in body["sections"]
        assert body["total_markets"] == 0


# ============================================================================
# HTTP behavior
# ============================================================================


class TestLeagueFuturesHTTPBehavior:
    """General HTTP contract checks."""

    async def test_rejects_post(self, client):
        resp = await client.post("/api/leagues/basketball_nba")
        assert resp.status_code == 405

    async def test_unexpected_query_params_ignored(self, client):
        resp = await client.get("/api/leagues/basketball_nba?limit=5&source=kalshi")
        assert resp.status_code == 200
        body = resp.json()
        assert "sport_key" in body
