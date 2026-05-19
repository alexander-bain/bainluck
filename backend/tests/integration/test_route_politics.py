"""Integration tests for GET /api/politics.

Validates response shape, empty-DB defaults, presidential candidate
structure, congressional chamber control, normalization, and HTTP
method rejection.
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
    llm_sport_category="politics",
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


class TestPoliticsBasicShape:
    """GET /api/politics with empty DB returns a valid, complete structure."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/politics")
        assert resp.status_code == 200

    async def test_top_level_keys(self, client):
        body = (await client.get("/api/politics")).json()
        expected = {"total_markets", "updated_at", "themes", "by_source", "cross_source"}
        assert expected == set(body.keys()), f"Unexpected keys: {set(body.keys()) - expected}"

    async def test_total_markets_zero_when_empty(self, client):
        body = (await client.get("/api/politics")).json()
        assert body["total_markets"] == 0

    async def test_updated_at_is_iso(self, client):
        body = (await client.get("/api/politics")).json()
        assert isinstance(body["updated_at"], str)
        assert "T" in body["updated_at"]

    async def test_cross_source_empty_list(self, client):
        body = (await client.get("/api/politics")).json()
        assert body["cross_source"] == []

    async def test_by_source_both_zero(self, client):
        body = (await client.get("/api/politics")).json()
        assert body["by_source"] == {"kalshi": 0, "polymarket": 0}


# ============================================================================
# Theme structure validation
# ============================================================================


class TestPoliticsThemes:
    """Each theme section has the expected sub-keys and correct types."""

    EXPECTED_THEMES = {
        "presidential", "congressional", "gubernatorial",
        "policy", "scotus", "international", "other",
    }

    async def test_all_theme_keys_present(self, client):
        body = (await client.get("/api/politics")).json()
        assert self.EXPECTED_THEMES == set(body["themes"].keys())

    async def test_presidential_structure(self, client):
        pres = (await client.get("/api/politics")).json()["themes"]["presidential"]
        assert isinstance(pres["count"], int) and pres["count"] >= 0
        assert isinstance(pres["candidates"], list)
        assert isinstance(pres["has_dual_source"], bool)
        assert isinstance(pres["side_markets"], list)
        # headline_q and market IDs are null when empty
        assert pres["headline_q"] is None
        assert pres["kalshi_market_id"] is None
        assert pres["poly_market_id"] is None

    async def test_congressional_structure(self, client):
        cong = (await client.get("/api/politics")).json()["themes"]["congressional"]
        assert isinstance(cong["count"], int) and cong["count"] >= 0
        assert isinstance(cong["markets"], list)
        assert "chamber_control" in cong
        chamber = cong["chamber_control"]
        assert "senate" in chamber
        assert "house" in chamber
        # senate_map is null when empty
        assert "senate_map" in cong

    async def test_simple_theme_structure(self, client):
        """Gubernatorial, policy, scotus, international, other all share count+markets shape."""
        body = (await client.get("/api/politics")).json()
        for key in ("gubernatorial", "policy", "scotus", "international", "other"):
            section = body["themes"][key]
            assert isinstance(section["count"], int), f"{key} missing count"
            assert isinstance(section["markets"], list), f"{key} missing markets"
            assert section["count"] == 0, f"{key} count should be 0 with empty DB"

    async def test_empty_presidential_has_no_candidates(self, client):
        body = (await client.get("/api/politics")).json()
        assert body["themes"]["presidential"]["candidates"] == []
        assert body["themes"]["presidential"]["has_dual_source"] is False


# ============================================================================
# Seeded presidential data
# ============================================================================


class TestPoliticsPresidential:
    """Presidential headline market builds candidate list with normalization."""

    async def test_single_source_candidates(self, client, mock_db):
        """Kalshi-only headline with 3 candidates returns normalized probs."""
        mock_db.execute.side_effect = [
            # First query: market fetch
            _query_result([
                _market(
                    market_id=100,
                    name="Who will win the 2028 presidential election?",
                    external_id="kxpresident2028",
                    source="kalshi",
                    outcomes=[
                        _outcome("Trump", 0.80, outcome_id=1001, rank=1),
                        _outcome("Harris", 0.70, outcome_id=1002, rank=2),
                        _outcome("Newsom", 0.50, outcome_id=1003, rank=3),
                    ],
                ),
            ]),
            # Second query: history snapshots (empty)
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        pres = body["themes"]["presidential"]
        assert pres["count"] == 1
        assert pres["headline_q"] == "Who will win the 2028 presidential election?"
        assert pres["kalshi_market_id"] == 100
        assert pres["poly_market_id"] is None
        assert pres["has_dual_source"] is False

        candidates = pres["candidates"]
        assert len(candidates) == 3
        assert candidates[0]["name"] == "Trump"

        # Probabilities should be normalized: 80+70+50=200 > 105
        total = sum(c["kalshi"] for c in candidates)
        assert abs(total - 100.0) < 1.0, f"Kalshi probs should sum to ~100, got {total}"

    async def test_party_detection(self, client, mock_db):
        """Known politician names get correct party labels."""
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=101,
                    name="Who will win the 2028 presidential election?",
                    external_id="kxpresident2028",
                    source="kalshi",
                    outcomes=[
                        _outcome("Trump", 0.50, outcome_id=1010, rank=1),
                        _outcome("Newsom", 0.30, outcome_id=1011, rank=2),
                        _outcome("Unknown Person", 0.20, outcome_id=1012, rank=3),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        candidates = body["themes"]["presidential"]["candidates"]
        parties = {c["name"]: c["party"] for c in candidates}
        assert parties["Trump"] == "R"
        assert parties["Newsom"] == "D"
        assert parties["Unknown Person"] == "I"

    async def test_dual_source_merge(self, client, mock_db):
        """Two headline markets (Kalshi + Polymarket) merge into one candidate list."""
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=200,
                    name="Who will win the 2028 presidential election?",
                    external_id="kxpresident2028",
                    source="kalshi",
                    outcomes=[
                        _outcome("Trump", 0.45, outcome_id=2001, rank=1),
                        _outcome("Harris", 0.35, outcome_id=2002, rank=2),
                        _outcome("DeSantis", 0.20, outcome_id=2003, rank=3),
                    ],
                ),
                _market(
                    market_id=201,
                    name="Next President of the United States",
                    external_id="poly-nextpresident",
                    source="polymarket",
                    outcomes=[
                        _outcome("Trump", 0.48, outcome_id=2011, rank=1),
                        _outcome("Harris", 0.32, outcome_id=2012, rank=2),
                        _outcome("DeSantis", 0.20, outcome_id=2013, rank=3),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        pres = body["themes"]["presidential"]
        assert pres["has_dual_source"] is True
        assert pres["kalshi_market_id"] == 200
        assert pres["poly_market_id"] == 201

        candidates = pres["candidates"]
        assert len(candidates) == 3
        # Each candidate should have both sources
        for c in candidates:
            assert c["kalshi"] is not None
            assert c["poly"] is not None
            assert c["merged"] is not None
        # Sorted by merged descending
        merged_vals = [c["merged"] for c in candidates]
        assert merged_vals == sorted(merged_vals, reverse=True)


class TestPoliticsPresidentialNormalization:
    """Independent binary markets (sum > 105%) must be normalized per source."""

    async def test_high_sum_normalized(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=300,
                    name="Who will win the 2028 presidential election?",
                    external_id="kxpresident2028",
                    source="kalshi",
                    outcomes=[
                        _outcome("Trump", 0.90, outcome_id=3001, rank=1),
                        _outcome("Harris", 0.85, outcome_id=3002, rank=2),
                        _outcome("Newsom", 0.60, outcome_id=3003, rank=3),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        candidates = body["themes"]["presidential"]["candidates"]
        # 90+85+60 = 235% raw, should be normalized
        kalshi_sum = sum(c["kalshi"] for c in candidates)
        assert kalshi_sum <= 101.0, f"Normalized sum should be ~100, got {kalshi_sum}"


# ============================================================================
# Congressional section
# ============================================================================


class TestPoliticsCongressional:
    """Congressional section with chamber control and senate map."""

    async def test_chamber_control_from_senate_market(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=400,
                    name="Which party will control the Senate in 2027?",
                    external_id="kxsenate-control-2027",
                    source="kalshi",
                    llm_sport_category="politics",
                    outcomes=[
                        _outcome("Republican", 0.62, outcome_id=4001, rank=1),
                        _outcome("Democrat", 0.38, outcome_id=4002, rank=2),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        chamber = body["themes"]["congressional"]["chamber_control"]
        assert chamber["senate"] is not None
        assert chamber["senate"]["gop"] == 62.0
        assert chamber["senate"]["dem"] == 38.0

    async def test_senate_map_from_state_race(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=401,
                    name="Who wins Ohio Senate race 2026?",
                    external_id="kxsenate26-oh",
                    source="kalshi",
                    llm_sport_category="politics",
                    outcomes=[
                        _outcome("Tim Ryan (D)", 0.45, outcome_id=4011, rank=1),
                        _outcome("JD Vance (R)", 0.55, outcome_id=4012, rank=2),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        senate_map = body["themes"]["congressional"]["senate_map"]
        assert senate_map is not None
        assert "OH" in senate_map
        assert senate_map["OH"] == 45.0


# ============================================================================
# Theme classification
# ============================================================================


class TestPoliticsClassification:
    """Markets land in the right theme section based on ticker/name."""

    async def test_scotus_market_classified(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=500,
                    name="Will a Supreme Court justice retire in 2026?",
                    external_id="kxscotus-retire-2026",
                    source="kalshi",
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        assert body["themes"]["scotus"]["count"] == 1
        assert len(body["themes"]["scotus"]["markets"]) == 1

    async def test_policy_market_classified(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=501,
                    name="Will the tariff bill pass the House?",
                    external_id="kxtariff-bill-2026",
                    source="kalshi",
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        assert body["themes"]["policy"]["count"] == 1

    async def test_international_market_classified(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=502,
                    name="Will Germany hold early elections?",
                    external_id="poly-germany-election",
                    source="polymarket",
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        assert body["themes"]["international"]["count"] == 1


# ============================================================================
# Non-politics filtering
# ============================================================================


class TestPoliticsNonPoliticsFilter:
    """Markets with entertainment/sports/weather keywords are filtered out."""

    async def test_sports_market_excluded(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=600,
                    name="Will the NBA champion be from the East?",
                    external_id="kxnba-east",
                    source="kalshi",
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        # Market is in total (it matches the query) but should be filtered from themes
        all_theme_counts = sum(s["count"] for s in body["themes"].values())
        assert all_theme_counts == 0

    async def test_entertainment_market_excluded(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=601,
                    name="Will Taylor Swift win a Grammy?",
                    external_id="kxgrammy-swift",
                    source="kalshi",
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        all_theme_counts = sum(s["count"] for s in body["themes"].values())
        assert all_theme_counts == 0


# ============================================================================
# by_source counts
# ============================================================================


class TestPoliticsBySource:
    """by_source correctly counts markets per source."""

    async def test_mixed_sources(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(market_id=700, name="Senate control?", external_id="kxsenate-a", source="kalshi"),
                _market(market_id=701, name="Will tariffs increase?", external_id="poly-tariff", source="polymarket"),
                _market(market_id=702, name="Governor race?", external_id="kxgov-a", source="kalshi"),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        assert body["total_markets"] == 3
        assert body["by_source"]["kalshi"] == 2
        assert body["by_source"]["polymarket"] == 1


# ============================================================================
# Market row shape
# ============================================================================


class TestPoliticsMarketRowShape:
    """Market rows in theme sections have the expected fields."""

    async def test_market_row_has_required_fields(self, client, mock_db):
        mock_db.execute.side_effect = [
            _query_result([
                _market(
                    market_id=800,
                    name="Will the immigration bill pass?",
                    external_id="kxbill-immigration",
                    source="kalshi",
                    outcomes=[
                        _outcome("Yes", 0.60, outcome_id=8001, rank=1),
                        _outcome("No", 0.40, outcome_id=8002, rank=2),
                    ],
                ),
            ]),
            _query_result([]),
        ]

        body = (await client.get("/api/politics")).json()
        markets = body["themes"]["policy"]["markets"]
        assert len(markets) == 1
        row = markets[0]
        assert "q" in row
        assert "prob" in row
        assert "src" in row
        assert "market_id" in row
        assert "top_outcomes" in row
        assert "outcome_count" in row
        assert isinstance(row["top_outcomes"], list)
        assert row["outcome_count"] == 2


# ============================================================================
# HTTP method rejection
# ============================================================================


class TestPoliticsHTTPMethods:
    """Only GET is allowed on /api/politics."""

    async def test_post_rejected(self, client):
        resp = await client.post("/api/politics")
        assert resp.status_code == 405

    async def test_put_rejected(self, client):
        resp = await client.put("/api/politics")
        assert resp.status_code == 405

    async def test_delete_rejected(self, client):
        resp = await client.delete("/api/politics")
        assert resp.status_code == 405


# ============================================================================
# Query parameter resilience
# ============================================================================


class TestPoliticsQueryParams:
    """Unknown query parameters are silently ignored."""

    async def test_extra_params_ignored(self, client):
        resp = await client.get("/api/politics?limit=5&source=kalshi&bogus=yes")
        assert resp.status_code == 200
        body = resp.json()
        assert "themes" in body
