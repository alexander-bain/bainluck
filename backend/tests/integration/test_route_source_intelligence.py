"""Contract tests for Source Intelligence API.

Tests that the source-intelligence endpoint returns the expected response
shape with correct top-level keys and nested structure — even when the DB
has no data (mock returns empty results for all raw SQL queries).

The main endpoint uses raw SQL text() queries with try/except fallbacks,
so empty mock results produce valid empty-data responses.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper: make a mock result that behaves like SQLAlchemy's raw-SQL Result
# ---------------------------------------------------------------------------

def _raw_result(rows=None):
    """Mock for db.execute(text(...)) returning named-tuple-like rows."""
    result = MagicMock()
    result.all.return_value = rows or []
    result.fetchall.return_value = rows or []
    result.first.return_value = rows[0] if rows else None

    # scalar helpers
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    if rows and len(rows) == 1 and hasattr(rows[0], "_fields") is False:
        # Single-column scalar
        pass

    # Also support .scalars().all() path
    scalars = MagicMock()
    scalars.all.return_value = rows or []
    scalars.first.return_value = rows[0] if rows else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars

    # Support .one() for single-row results
    if rows and len(rows) == 1:
        result.one.return_value = rows[0]

    return result


# ============================================================================
# GET /api/source-intelligence — main endpoint
# ============================================================================


class TestSourceIntelligenceMain:
    """GET /api/source-intelligence — cross-source disagreement analysis."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        assert resp.status_code == 200

    async def test_has_top_level_keys(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert "generated_at" in body
        assert "coverage" in body
        assert "source_accuracy" in body
        assert "disagreements" in body
        assert "case_studies" in body

    async def test_generated_at_is_iso_string(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert isinstance(body["generated_at"], str)
        assert "T" in body["generated_at"]

    async def test_coverage_structure(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        cov = body["coverage"]
        assert "total_events" in cov
        assert "multi_source_events" in cov
        assert "by_source_count" in cov
        assert "by_sport" in cov
        assert isinstance(cov["total_events"], int)
        assert isinstance(cov["multi_source_events"], int)
        assert isinstance(cov["by_source_count"], list)
        assert isinstance(cov["by_sport"], list)

    async def test_source_accuracy_is_list(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert isinstance(body["source_accuracy"], list)

    async def test_disagreements_structure(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        dis = body["disagreements"]
        assert "total_comparisons" in dis
        assert "rate_5pp" in dis
        assert "rate_10pp" in dis
        assert "rate_20pp" in dis
        assert "by_sport" in dis
        assert "pairwise" in dis
        assert isinstance(dis["total_comparisons"], int)
        assert isinstance(dis["by_sport"], list)
        assert isinstance(dis["pairwise"], list)

    async def test_case_studies_is_list(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert isinstance(body["case_studies"], list)

    async def test_empty_db_returns_zeroed_coverage(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert body["coverage"]["total_events"] == 0
        assert body["coverage"]["multi_source_events"] == 0
        assert body["coverage"]["by_sport"] == []

    async def test_empty_db_returns_zero_disagreements(self, client):
        resp = await client.get("/api/source-intelligence?refresh=true")
        body = resp.json()
        assert body["disagreements"]["total_comparisons"] == 0
        assert body["disagreements"]["rate_5pp"] == 0

    async def test_cache_respects_refresh_param(self, client):
        """Two calls with refresh=true should both succeed."""
        resp1 = await client.get("/api/source-intelligence?refresh=true")
        resp2 = await client.get("/api/source-intelligence?refresh=true")
        assert resp1.status_code == 200
        assert resp2.status_code == 200


# ============================================================================
# GET /api/source-intelligence/linked-markets — event market audit
# ============================================================================


class TestLinkedMarketsAudit:
    """GET /api/source-intelligence/linked-markets?event_id=N."""

    async def test_returns_200_with_event_id(self, client):
        resp = await client.get("/api/source-intelligence/linked-markets?event_id=1")
        assert resp.status_code == 200

    async def test_has_expected_keys(self, client):
        resp = await client.get("/api/source-intelligence/linked-markets?event_id=1")
        body = resp.json()
        assert "event_id" in body
        assert "linked_markets" in body
        assert "snapshot_market_sources" in body
        assert body["event_id"] == 1
        assert isinstance(body["linked_markets"], list)
        assert isinstance(body["snapshot_market_sources"], list)

    async def test_empty_db_returns_empty_lists(self, client):
        resp = await client.get("/api/source-intelligence/linked-markets?event_id=999")
        body = resp.json()
        assert body["linked_markets"] == []
        assert body["snapshot_market_sources"] == []

    async def test_missing_event_id_returns_422(self, client):
        resp = await client.get("/api/source-intelligence/linked-markets")
        assert resp.status_code == 422


# ============================================================================
# GET /api/source-intelligence/prop-snapshot-audit
# ============================================================================


class TestPropSnapshotAudit:
    """GET /api/source-intelligence/prop-snapshot-audit."""

    async def test_returns_200(self, client, mock_db):
        # This endpoint needs two execute calls: one for market names,
        # one for no-game-state count.  Provide appropriate mock results.
        no_gs_row = SimpleNamespace(snap_count=0, event_count=0)
        no_gs_result = _raw_result([no_gs_row])
        no_gs_result.one.return_value = no_gs_row

        # First call: SET timeout (returns nothing useful)
        # Second call: market_names_sql (returns empty list)
        # Third call: no_gs_sql (returns single row)
        mock_db.execute.side_effect = [
            _raw_result(),     # SET LOCAL statement_timeout
            _raw_result([]),   # market names query
            no_gs_result,      # no-game-state query
        ]

        resp = await client.get("/api/source-intelligence/prop-snapshot-audit")
        assert resp.status_code == 200

    async def test_has_expected_keys(self, client, mock_db):
        no_gs_row = SimpleNamespace(snap_count=0, event_count=0)
        no_gs_result = _raw_result([no_gs_row])
        no_gs_result.one.return_value = no_gs_row

        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
            no_gs_result,
        ]

        resp = await client.get("/api/source-intelligence/prop-snapshot-audit")
        body = resp.json()
        assert "moneyline_snapshots" in body
        assert "moneyline_events" in body
        assert "prop_snapshots" in body
        assert "prop_events" in body
        assert "no_game_state_snapshots" in body
        assert "no_game_state_events" in body
        assert "prop_market_types" in body

    async def test_empty_db_zeroed_counts(self, client, mock_db):
        no_gs_row = SimpleNamespace(snap_count=0, event_count=0)
        no_gs_result = _raw_result([no_gs_row])
        no_gs_result.one.return_value = no_gs_row

        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
            no_gs_result,
        ]

        resp = await client.get("/api/source-intelligence/prop-snapshot-audit")
        body = resp.json()
        assert body["moneyline_snapshots"] == 0
        assert body["prop_snapshots"] == 0
        assert body["no_game_state_snapshots"] == 0
        assert body["prop_market_types"] == []


# ============================================================================
# GET /api/source-intelligence/oscillation-audit
# ============================================================================


class TestOscillationAudit:
    """GET /api/source-intelligence/oscillation-audit."""

    async def test_returns_200(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),    # SET timeout
            _raw_result([]),  # oscillation query
        ]
        resp = await client.get("/api/source-intelligence/oscillation-audit")
        assert resp.status_code == 200

    async def test_has_expected_keys(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
        ]
        resp = await client.get("/api/source-intelligence/oscillation-audit")
        body = resp.json()
        assert "total_oscillating" in body
        assert "espn_id_null" in body
        assert "espn_id_set" in body
        assert "with_score_backwards" in body
        assert "by_sport" in body
        assert "events" in body

    async def test_empty_db_returns_zeroed(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
        ]
        resp = await client.get("/api/source-intelligence/oscillation-audit")
        body = resp.json()
        assert body["total_oscillating"] == 0
        assert body["events"] == []
        assert body["by_sport"] == {}


# ============================================================================
# GET /api/source-intelligence/date-mismatch-audit
# ============================================================================


class TestDateMismatchAudit:
    """GET /api/source-intelligence/date-mismatch-audit."""

    async def test_returns_200(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),    # SET timeout
            _raw_result([]),  # main query
        ]
        resp = await client.get("/api/source-intelligence/date-mismatch-audit")
        assert resp.status_code == 200

    async def test_has_expected_keys(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
        ]
        resp = await client.get("/api/source-intelligence/date-mismatch-audit")
        body = resp.json()
        assert "markets_checked" in body
        assert "date_mismatches" in body
        assert "mismatches" in body
        assert isinstance(body["mismatches"], list)

    async def test_empty_db_returns_zeroed(self, client, mock_db):
        mock_db.execute.side_effect = [
            _raw_result(),
            _raw_result([]),
        ]
        resp = await client.get("/api/source-intelligence/date-mismatch-audit")
        body = resp.json()
        assert body["markets_checked"] == 0
        assert body["date_mismatches"] == 0
        assert body["mismatches"] == []


# ============================================================================
# POST admin endpoints — require auth
# ============================================================================


class TestSourceIntelligenceAdminEndpoints:
    """Admin write endpoints must reject bad secrets."""

    async def test_fix_mismatches_rejects_bad_secret(self, client):
        resp = await client.post(
            "/api/source-intelligence/fix-date-mismatches?secret=bad"
        )
        assert resp.status_code == 403

    async def test_cleanup_orphaned_rejects_bad_secret(self, client):
        resp = await client.post(
            "/api/source-intelligence/cleanup-orphaned-snapshots?secret=bad"
        )
        assert resp.status_code == 403

    async def test_cleanup_oscillation_rejects_bad_secret(self, client):
        resp = await client.post(
            "/api/source-intelligence/cleanup-oscillation?secret=bad"
        )
        assert resp.status_code == 403

    async def test_post_endpoints_reject_get(self, client):
        """POST-only admin endpoints should reject GET."""
        for path in [
            "/api/source-intelligence/fix-date-mismatches",
            "/api/source-intelligence/cleanup-orphaned-snapshots",
            "/api/source-intelligence/cleanup-oscillation",
        ]:
            resp = await client.get(path)
            assert resp.status_code == 405, f"GET {path} should be 405"


# ============================================================================
# HTTP behavior
# ============================================================================


class TestFairFightComparison:
    """GET /api/source-intelligence/fair-fight — paired MCE comparison."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        assert resp.status_code == 200

    async def test_has_top_level_keys(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert "generated_at" in body
        assert "methodology" in body
        assert "min_shared_threshold" in body
        assert "pairs" in body

    async def test_generated_at_is_iso_string(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert isinstance(body["generated_at"], str)
        assert "T" in body["generated_at"]

    async def test_pairs_is_list(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert isinstance(body["pairs"], list)

    async def test_min_shared_threshold_is_positive(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert body["min_shared_threshold"] >= 1

    async def test_methodology_is_nonempty_string(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert isinstance(body["methodology"], str)
        assert len(body["methodology"]) > 10

    async def test_empty_db_returns_empty_pairs(self, client):
        resp = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        body = resp.json()
        assert body["pairs"] == []

    async def test_rejects_post(self, client):
        resp = await client.post("/api/source-intelligence/fair-fight")
        assert resp.status_code == 405

    async def test_cache_respects_refresh_param(self, client):
        resp1 = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        resp2 = await client.get("/api/source-intelligence/fair-fight?refresh=true")
        assert resp1.status_code == 200
        assert resp2.status_code == 200


# ============================================================================
# Unit tests for _compute_mce helper
# ============================================================================


class TestComputeMCE:
    """Unit tests for the MCE computation helper."""

    def test_empty_input_returns_none(self):
        from app.routes.source_intelligence import _compute_mce
        assert _compute_mce([], []) is None

    def test_perfect_calibration_returns_zero(self):
        """All predictions in 90-100% bucket, all win -> MCE = 0."""
        from app.routes.source_intelligence import _compute_mce
        probs = [0.95, 0.96, 0.97, 0.98, 0.99]
        outcomes = [True, True, True, True, True]
        mce = _compute_mce(probs, outcomes)
        assert mce is not None
        # avg_prob ~ 0.97, actual = 1.0, error ~ 3pp
        assert mce < 5.0

    def test_terrible_calibration_is_high(self):
        """Predict 90%+ but all lose -> high MCE."""
        from app.routes.source_intelligence import _compute_mce
        probs = [0.95, 0.96, 0.97, 0.98, 0.99]
        outcomes = [False, False, False, False, False]
        mce = _compute_mce(probs, outcomes)
        assert mce is not None
        assert mce > 90.0  # avg_prob ~ 0.97, actual = 0.0

    def test_multiple_buckets(self):
        """Predictions across multiple buckets."""
        from app.routes.source_intelligence import _compute_mce
        probs = [0.15, 0.25, 0.55, 0.75, 0.85, 0.95]
        outcomes = [False, False, True, True, True, True]
        mce = _compute_mce(probs, outcomes)
        assert mce is not None
        assert 0.0 <= mce <= 100.0

    def test_returns_percentage_points(self):
        """MCE should be in percentage points, not raw fraction."""
        from app.routes.source_intelligence import _compute_mce
        probs = [0.5] * 100
        outcomes = [True] * 50 + [False] * 50
        mce = _compute_mce(probs, outcomes)
        assert mce is not None
        # Perfect calibration at 50%
        assert mce < 1.0  # should be ~0pp


# ============================================================================
# HTTP behavior
# ============================================================================


class TestSourceIntelligenceHTTPBehavior:
    """General HTTP contract checks."""

    async def test_main_endpoint_rejects_post(self, client):
        resp = await client.post("/api/source-intelligence")
        assert resp.status_code == 405

    async def test_unknown_subroute_returns_404(self, client):
        resp = await client.get("/api/source-intelligence/not-a-thing")
        assert resp.status_code in (404, 405)

    async def test_unexpected_query_params_ignored(self, client):
        resp = await client.get(
            "/api/source-intelligence?refresh=true&foo=bar&limit=999"
        )
        assert resp.status_code == 200
