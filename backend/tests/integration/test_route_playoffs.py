"""Contract tests for playoff grid, league futures, and related endpoints.

Tests:
- GET /api/playoffs/{league_slug} — championship progression grid
- GET /api/playoffs/ — list available leagues
- GET /api/leagues/{sport_key} — league-scoped futures markets
- GET /api/events/search/trending — trending search queries
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.league_configs import get_all_league_slugs
from app.models import FuturesMarket, FuturesOutcome


# All configured league slugs — tests run against each
ALL_SLUGS = get_all_league_slugs()
TEAM_SPORT_SLUGS = [s for s in ALL_SLUGS if s != "golf"]
# Major leagues for deeper shape validation
MAJOR_SLUGS = [s for s in ("nba", "nhl", "mlb", "nfl") if s in ALL_SLUGS]
# Sport keys for league futures endpoint
LEAGUE_SPORT_KEYS = [
    "basketball_nba",
    "icehockey_nhl",
    "baseball_mlb",
    "americanfootball_nfl",
    "basketball_wnba",
]


def _mock_result(rows=None):
    """Create a SQLAlchemy-ish Result mock for deterministic route contracts."""
    rows = rows or []
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    result.scalars.return_value.unique.return_value.all.return_value = rows
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    result.scalar.return_value = rows[0] if rows else None
    result.fetchall.return_value = rows
    result.all.return_value = rows
    result.first.return_value = rows[0] if rows else None
    return result


def _playoff_market(
    *,
    market_id=101,
    name="NBA Championship 2025-26",
    source="odds_api",
    external_id="basketball_nba_championship_2025",
    market_tier=1,
    outcomes=None,
):
    market = FuturesMarket(
        id=market_id,
        source=source,
        external_id=external_id,
        name=name,
        category="championship",
        llm_sport_category="basketball",
        market_tier=market_tier,
        status="open",
        volume_24h=250,
    )
    market.outcomes = outcomes or [
        FuturesOutcome(
            id=201,
            market_id=market_id,
            external_id="los-angeles-lakers",
            name="Los Angeles Lakers",
            current_probability=0.35,
            last_updated=datetime.now(timezone.utc),
        ),
        FuturesOutcome(
            id=202,
            market_id=market_id,
            external_id="boston-celtics",
            name="Boston Celtics",
            current_probability=0.25,
            last_updated=datetime.now(timezone.utc),
        ),
    ]
    return market


# ============================================================================
# Playoff Grid — /api/playoffs/{league_slug}
# ============================================================================


class TestPlayoffGrid404:
    """Invalid slugs should return 404 with helpful detail."""

    async def test_invalid_slug_returns_404(self, client):
        resp = await client.get("/api/playoffs/fake-league-xyz")
        assert resp.status_code == 404

    async def test_404_body_has_detail(self, client):
        resp = await client.get("/api/playoffs/fake-league-xyz")
        body = resp.json()
        assert "detail" in body
        assert "fake-league-xyz" in body["detail"]

    async def test_404_lists_available_leagues(self, client):
        resp = await client.get("/api/playoffs/nonexistent")
        body = resp.json()
        assert "Available" in body["detail"]


class TestPlayoffGridShape:
    """Response shape for a valid league slug (mocked empty DB)."""

    async def test_valid_slug_returns_200(self, client):
        resp = await client.get("/api/playoffs/nba")
        assert resp.status_code == 200

    async def test_response_has_required_keys(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for key in [
            "league", "name", "season", "columns", "teams",
            "team_count", "last_updated", "movers", "trend_chart",
            "sources_available", "grouped_teams", "championship_market_id",
        ]:
            assert key in body, f"Missing key: {key}"

    async def test_league_matches_slug(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["league"] == "nba"

    async def test_name_is_string(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["name"], str)
        assert len(body["name"]) > 0

    async def test_season_is_string(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["season"], str)

    async def test_columns_are_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["columns"], list)

    async def test_teams_are_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["teams"], list)

    async def test_team_count_is_int(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["team_count"], int)
        assert body["team_count"] >= 0

    async def test_team_count_matches_teams_length(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["team_count"] == len(body["teams"])

    async def test_movers_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "movers" in body
        assert isinstance(body["movers"], list)

    async def test_trend_chart_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "trend_chart" in body
        assert isinstance(body["trend_chart"], dict)

    async def test_trend_chart_has_column_key(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        chart = body["trend_chart"]
        assert "column" in chart
        assert "top" in chart
        assert isinstance(chart["column"], str)
        assert isinstance(chart["top"], int)

    async def test_sources_available_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "sources_available" in body
        assert isinstance(body["sources_available"], list)

    async def test_grouped_teams_is_dict_or_none(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["grouped_teams"] is None or isinstance(body["grouped_teams"], dict)

    async def test_championship_market_id_is_int_or_none(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["championship_market_id"] is None or isinstance(body["championship_market_id"], int)

    async def test_last_updated_is_iso_string(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["last_updated"], str)
        assert "T" in body["last_updated"]

    async def test_empty_db_returns_empty_grid_contract(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["columns"] == []
        assert body["teams"] == []
        assert body["movers"] == []
        assert body["sources_available"] == []
        assert body["grouped_teams"] is None
        assert body["championship_market_id"] is None
        assert body["team_count"] == 0
        assert body["trend_chart"]["timeline"] == []
        assert body["trend_chart"]["outcomes"] == []


class TestPlayoffGridMockedData:
    """Focused non-empty grid contracts using local mocked market data."""

    async def test_mocked_championship_market_builds_team_rows(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        market = _playoff_market()
        mock_db.execute.side_effect = [
            _mock_result(),          # SET LOCAL statement_timeout
            _mock_result([]),        # matching overrides
            _mock_result([market]),  # futures markets
            _mock_result([]),        # resolved-market backfill
        ]
        monkeypatch.setattr(
            "app.routes.playoffs._get_team_metadata",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "app.routes.playoffs._compute_movers",
            AsyncMock(return_value={201: 0.30, 202: 0.20}),
        )
        monkeypatch.setattr(
            "app.routes.playoffs._build_trend_chart",
            AsyncMock(return_value={"timeline": [], "outcomes": []}),
        )

        resp = await client.get("/api/playoffs/nba?top=1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["team_count"] == 2
        assert body["sources_available"] == ["odds_api"]
        assert body["championship_market_id"] == 101
        assert body["trend_chart"]["column"] == "championship"
        assert body["trend_chart"]["top"] == 1

        team_names = {team["name"] for team in body["teams"]}
        assert team_names == {"Los Angeles Lakers", "Boston Celtics"}
        for team in body["teams"]:
            assert set(team["cells"]) == {"championship"}
            cell = team["cells"]["championship"]
            assert 0 < cell["merged_probability"] < 1
            assert cell["sources"] == [
                {
                    "source": "odds_api",
                    "probability": cell["merged_probability"],
                    "market_name": "NBA Championship 2025-26",
                }
            ]

    async def test_debug_true_includes_column_market_diagnostics(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        market = _playoff_market()
        mock_db.execute.side_effect = [
            _mock_result(),
            _mock_result([]),
            _mock_result([market]),
            _mock_result([]),
        ]
        monkeypatch.setattr(
            "app.routes.playoffs._get_team_metadata",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "app.routes.playoffs._compute_movers",
            AsyncMock(return_value={}),
        )
        monkeypatch.setattr(
            "app.routes.playoffs._build_trend_chart",
            AsyncMock(return_value={"timeline": [], "outcomes": []}),
        )

        resp = await client.get("/api/playoffs/nba?debug=true")

        assert resp.status_code == 200
        body = resp.json()
        assert "_debug_column_markets" in body
        assert body["_debug_column_markets"]["championship"] == [
            {
                "market_id": 101,
                "source": "odds_api",
                "name": "NBA Championship 2025-26",
                "external_id": "basketball_nba_championship_2025",
                "outcome_count": 2,
                "sample_outcomes": [
                    {"name": "Los Angeles Lakers", "prob": 0.35},
                    {"name": "Boston Celtics", "prob": 0.25},
                ],
            }
        ]


class TestPlayoffGridAllLeagues:
    """Every configured league slug returns 200 with valid shape."""

    @pytest.mark.parametrize("slug", ALL_SLUGS)
    async def test_all_leagues_return_200(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        assert resp.status_code == 200, f"League {slug} returned {resp.status_code}"

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_all_team_sports_have_required_keys(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        for key in ["league", "columns", "teams", "team_count"]:
            assert key in body, f"League {slug} missing key: {key}"

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_league_field_matches_slug(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert body["league"] == slug

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_teams_is_list_for_all_slugs(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert isinstance(body["teams"], list)
        assert isinstance(body["team_count"], int)

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_sources_available_for_all_slugs(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert "sources_available" in body
        assert isinstance(body["sources_available"], list)

    @pytest.mark.parametrize("slug", MAJOR_SLUGS)
    async def test_major_leagues_have_season(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert "season" in body
        assert isinstance(body["season"], str)
        assert len(body["season"]) > 0

    @pytest.mark.parametrize("slug", MAJOR_SLUGS)
    async def test_major_leagues_have_name(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert "name" in body
        assert isinstance(body["name"], str)
        assert len(body["name"]) > 0


class TestPlayoffGridColumns:
    """Column structure validation.

    With mocked empty DB, columns may be empty (populated from market data).
    These tests validate structure when columns are present.
    """

    async def test_columns_is_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["columns"], list)

    async def test_column_objects_have_key_and_label_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for col in body["columns"]:
            assert "key" in col, f"Column missing 'key': {col}"
            assert "label" in col, f"Column missing 'label': {col}"
            assert isinstance(col["key"], str)
            assert isinstance(col["label"], str)

    async def test_column_objects_have_order_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for col in body["columns"]:
            assert "order" in col, f"Column missing 'order': {col}"
            assert isinstance(col["order"], int)

    async def test_column_objects_have_sequential_flag_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for col in body["columns"]:
            assert "sequential" in col, f"Column missing 'sequential': {col}"
            assert isinstance(col["sequential"], bool)

    async def test_column_objects_have_market_id_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for col in body["columns"]:
            assert "market_id" in col, f"Column missing 'market_id': {col}"
            # market_id can be int or None
            assert col["market_id"] is None or isinstance(col["market_id"], int)

    async def test_column_keys_are_unique(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        keys = [col["key"] for col in body["columns"]]
        assert len(keys) == len(set(keys)), "Duplicate column keys found"


class TestPlayoffGridTeamRowShape:
    """Validate team row structure when teams are present.

    With empty DB, teams will be empty, so these validate the contract
    using conditional checks.
    """

    async def test_team_row_has_name(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            assert "name" in team
            assert isinstance(team["name"], str)

    async def test_team_row_has_short_name(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            assert "short_name" in team
            assert isinstance(team["short_name"], str)

    async def test_team_row_has_metadata_fields(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            # These fields should always be present (may be null)
            for field in ["team_id", "logo_url", "primary_color",
                          "secondary_color", "record", "conference",
                          "division", "region", "seed"]:
                assert field in team, f"Team missing '{field}': {team.get('name')}"

    async def test_team_row_has_cells_dict(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            assert "cells" in team
            assert isinstance(team["cells"], dict)

    async def test_team_cell_has_merged_probability(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            for col_key, cell in team["cells"].items():
                assert "merged_probability" in cell, (
                    f"Cell '{col_key}' for '{team['name']}' missing merged_probability"
                )
                prob = cell["merged_probability"]
                assert isinstance(prob, (int, float))
                assert 0 <= prob <= 1, (
                    f"Probability out of range for '{team['name']}' col '{col_key}': {prob}"
                )

    async def test_team_cell_has_sources_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            for col_key, cell in team["cells"].items():
                assert "sources" in cell
                assert isinstance(cell["sources"], list)

    async def test_team_cell_source_has_source_and_probability(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            for col_key, cell in team["cells"].items():
                for src in cell["sources"]:
                    assert "source" in src
                    assert isinstance(src["source"], str)
                    assert "probability" in src
                    assert isinstance(src["probability"], (int, float))

    async def test_team_cell_has_trend_24h(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for team in body["teams"]:
            for col_key, cell in team["cells"].items():
                assert "trend_24h" in cell
                # Can be None or a float
                if cell["trend_24h"] is not None:
                    assert isinstance(cell["trend_24h"], (int, float))


class TestPlayoffGridQueryParams:
    """Query parameter validation."""

    async def test_debug_flag_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?debug=true")
        assert resp.status_code == 200

    async def test_top_param_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?top=5")
        assert resp.status_code == 200

    async def test_hours_param_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?hours=48")
        assert resp.status_code == 200

    async def test_top_param_reflected_in_trend_chart(self, client):
        resp = await client.get("/api/playoffs/nba?top=3")
        body = resp.json()
        assert body["trend_chart"]["top"] == 3

    async def test_top_param_min_boundary(self, client):
        resp = await client.get("/api/playoffs/nba?top=1")
        assert resp.status_code == 200

    async def test_top_param_max_boundary(self, client):
        resp = await client.get("/api/playoffs/nba?top=50")
        assert resp.status_code == 200

    async def test_top_param_exceeds_max_returns_422(self, client):
        resp = await client.get("/api/playoffs/nba?top=51")
        assert resp.status_code == 422

    async def test_top_param_zero_returns_422(self, client):
        resp = await client.get("/api/playoffs/nba?top=0")
        assert resp.status_code == 422

    async def test_top_param_non_integer_returns_422(self, client):
        resp = await client.get("/api/playoffs/nba?top=abc")
        assert resp.status_code == 422

    async def test_hours_param_non_integer_returns_422(self, client):
        resp = await client.get("/api/playoffs/nba?hours=soon")
        assert resp.status_code == 422

    async def test_debug_false_omits_debug_payload(self, client):
        resp = await client.get("/api/playoffs/nba?debug=false")
        body = resp.json()
        assert resp.status_code == 200
        assert "_debug_column_markets" not in body


class TestPlayoffGridLeagueSlugBehavior:
    """League slug parameter behavior stays explicit and deterministic."""

    async def test_slug_matching_is_case_sensitive(self, client):
        resp = await client.get("/api/playoffs/NBA")
        assert resp.status_code == 404

    async def test_known_golf_slug_uses_empty_grid_when_datagolf_unconfigured(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
        resp = await client.get("/api/playoffs/golf")
        assert resp.status_code == 200
        body = resp.json()
        assert body["league"] == "golf"
        assert body["teams"] == []
        assert body["team_count"] == 0


class TestPlayoffGolfScheduleErrors:
    """External golf schedule errors should be explicit and network-free."""

    async def test_golf_schedule_without_datagolf_key_returns_503(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
        resp = await client.get("/api/playoffs/golf/schedule")
        body = resp.json()
        assert resp.status_code == 503
        assert body["detail"] == "DataGolf API not configured"


class TestPlayoffGridMovers:
    """Movers structure validation."""

    async def test_movers_is_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["movers"], list)

    async def test_mover_item_shape_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for mover in body["movers"]:
            assert "name" in mover
            assert isinstance(mover["name"], str)


# ============================================================================
# Playoff League List — /api/playoffs/
# ============================================================================


class TestPlayoffLeagueList:
    """GET /api/playoffs/ — list available leagues."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/playoffs/")
        assert resp.status_code == 200

    async def test_response_has_leagues(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        assert "leagues" in body
        assert isinstance(body["leagues"], list)
        assert len(body["leagues"]) > 0

    async def test_each_league_has_slug_and_name(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        for league in body["leagues"]:
            assert "slug" in league, f"League missing slug: {league}"
            assert "name" in league, f"League missing name: {league}"
            assert isinstance(league["slug"], str)
            assert isinstance(league["name"], str)

    async def test_each_league_has_sport_category(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        for league in body["leagues"]:
            assert "sport_category" in league
            assert isinstance(league["sport_category"], str)

    async def test_each_league_has_column_count(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        for league in body["leagues"]:
            assert "column_count" in league
            assert isinstance(league["column_count"], int)
            assert league["column_count"] > 0

    async def test_major_leagues_present(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        slugs = {l["slug"] for l in body["leagues"]}
        for slug in MAJOR_SLUGS:
            assert slug in slugs, f"Expected major league '{slug}' in league list"

    async def test_league_slugs_are_unique(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        slugs = [l["slug"] for l in body["leagues"]]
        assert len(slugs) == len(set(slugs)), "Duplicate league slugs in list"


# ============================================================================
# League Futures — /api/leagues/{sport_key}
# ============================================================================


class TestLeagueFuturesEndpoint:
    """GET /api/leagues/{sport_key} — league-scoped futures markets."""

    async def test_returns_200_for_nba(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200

    async def test_response_has_required_keys(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert "sport_key" in body
        assert "sections" in body
        assert "total_markets" in body

    async def test_sport_key_matches_request(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert body["sport_key"] == "basketball_nba"

    async def test_sections_is_dict(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert isinstance(body["sections"], dict)

    async def test_total_markets_is_non_negative_int(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert isinstance(body["total_markets"], int)
        assert body["total_markets"] >= 0

    async def test_total_markets_equals_section_sum(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        section_total = sum(len(v) for v in body["sections"].values())
        assert body["total_markets"] == section_total

    async def test_section_values_are_lists(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            assert isinstance(items, list), f"Section '{section_name}' is not a list"

    async def test_section_names_are_valid(self, client):
        """Sections should be one of the known section types."""
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        valid_sections = {"series", "awards", "props", "season_stats", "more_markets"}
        for section_name in body["sections"]:
            assert section_name in valid_sections, (
                f"Unknown section '{section_name}', expected one of {valid_sections}"
            )

    async def test_empty_db_returns_empty_sections_contract(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        assert body == {
            "sport_key": "basketball_nba",
            "sections": {},
            "total_markets": 0,
        }

    async def test_mocked_award_market_is_grouped_with_outcome_shape(
        self,
        client,
        mock_db,
    ):
        market = FuturesMarket(
            id=301,
            source="kalshi",
            external_id="KXNBAMVP-26",
            name="NBA MVP 2026",
            category="award",
            llm_sport_category="basketball",
            llm_league="nba",
            market_tier=3,
            status="open",
            canonical_market_key="basketball_nba_mvp_2026",
        )
        market.outcomes = [
            FuturesOutcome(
                id=401,
                market_id=301,
                external_id="nikola-jokic",
                name="Nikola Jokic",
                current_probability=0.42,
                opening_probability=0.30,
                probability_change_24h=0.04,
                rank=1,
                team_id=15,
            ),
            FuturesOutcome(
                id=402,
                market_id=301,
                external_id="shai-gilgeous-alexander",
                name="Shai Gilgeous-Alexander",
                current_probability=0.26,
                opening_probability=0.22,
                probability_change_24h=-0.01,
                rank=2,
                team_id=25,
            ),
        ]
        mock_db.execute.return_value = _mock_result([market])

        resp = await client.get("/api/leagues/basketball_nba")

        assert resp.status_code == 200
        body = resp.json()
        assert body["sport_key"] == "basketball_nba"
        assert body["total_markets"] == 1
        assert set(body["sections"]) == {"awards"}
        assert body["sections"]["awards"] == [
            {
                "id": 301,
                "name": "NBA MVP 2026",
                "source": "kalshi",
                "market_tier": 3,
                "category": "award",
                "resolution_date": None,
                "outcome_count": 2,
                "top_outcomes": [
                    {
                        "id": 401,
                        "name": "Nikola Jokic",
                        "probability": 0.42,
                        "opening_probability": 0.3,
                        "rank": 1,
                        "movement_24h": 0.04,
                        "team_id": 15,
                    },
                    {
                        "id": 402,
                        "name": "Shai Gilgeous-Alexander",
                        "probability": 0.26,
                        "opening_probability": 0.22,
                        "rank": 2,
                        "movement_24h": -0.01,
                        "team_id": 25,
                    },
                ],
                "canonical_market_key": "basketball_nba_mvp_2026",
                "section": "awards",
            }
        ]


class TestLeagueFuturesMarketItemShape:
    """Market item shape within league futures sections."""

    async def test_market_item_has_required_fields(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                for field in ["id", "name", "source", "top_outcomes"]:
                    assert field in item, (
                        f"Market in '{section_name}' missing '{field}'"
                    )

    async def test_market_id_is_int(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                assert isinstance(item["id"], int)

    async def test_market_name_is_string(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                assert isinstance(item["name"], str)

    async def test_market_source_is_string(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                assert isinstance(item["source"], str)

    async def test_top_outcomes_is_list(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                assert isinstance(item["top_outcomes"], list)

    async def test_outcome_item_shape(self, client):
        resp = await client.get("/api/leagues/basketball_nba")
        body = resp.json()
        for section_name, items in body["sections"].items():
            for item in items:
                for outcome in item["top_outcomes"]:
                    assert "id" in outcome
                    assert "name" in outcome
                    assert "probability" in outcome
                    assert isinstance(outcome["name"], str)
                    if outcome["probability"] is not None:
                        assert isinstance(outcome["probability"], (int, float))
                        assert 0 <= outcome["probability"] <= 1


class TestLeagueFuturesAllSportKeys:
    """All major sport keys return valid responses."""

    @pytest.mark.parametrize("sport_key", LEAGUE_SPORT_KEYS)
    async def test_major_sport_keys_return_200(self, client, sport_key):
        resp = await client.get(f"/api/leagues/{sport_key}")
        assert resp.status_code == 200

    @pytest.mark.parametrize("sport_key", LEAGUE_SPORT_KEYS)
    async def test_sport_key_reflected_in_response(self, client, sport_key):
        resp = await client.get(f"/api/leagues/{sport_key}")
        body = resp.json()
        assert body["sport_key"] == sport_key

    async def test_unknown_sport_key_returns_200_empty(self, client):
        """Unknown sport keys should still return 200 with empty sections."""
        resp = await client.get("/api/leagues/unknown_sport")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_markets"] == 0


# ============================================================================
# Trending Searches — /api/events/search/trending
# ============================================================================


class TestTrendingSearches:
    """GET /api/events/search/trending — top search queries."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/search/trending")
        assert resp.status_code == 200

    async def test_response_has_trending_key(self, client):
        resp = await client.get("/api/events/search/trending")
        body = resp.json()
        assert "trending" in body

    async def test_trending_is_list(self, client):
        resp = await client.get("/api/events/search/trending")
        body = resp.json()
        assert isinstance(body["trending"], list)

    async def test_trending_item_shape_when_present(self, client):
        resp = await client.get("/api/events/search/trending")
        body = resp.json()
        for item in body["trending"]:
            assert "query" in item
            assert "count" in item
            assert isinstance(item["query"], str)
            assert isinstance(item["count"], int)
            assert item["count"] > 0
