"""Contract tests for admin taxonomy endpoints (/api/admin/futures/*, /api/admin/taxonomy/*, /api/admin/events/*)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------


class TestTaxonomyAuthGuards:
    """All taxonomy admin endpoints reject invalid secrets with 403."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/futures/categorization-status?secret=bad",
            "/api/admin/futures/uncategorized?secret=bad",
            "/api/admin/futures/metadata-status?secret=bad",
            "/api/admin/events/metadata-status?secret=bad",
            "/api/admin/taxonomy/debug-redis?secret=bad",
            "/api/admin/taxonomy/task/abc123?secret=bad",
            "/api/admin/taxonomy/vocabulary?secret=bad",
            "/api/admin/taxonomy/dashboard?secret=bad",
            "/api/admin/taxonomy/enrichment-status?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403
        assert resp.json() ["detail"] in ("Invalid admin secret", "Admin auth not configured")

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/futures/categorize?secret=bad",
            "/api/admin/futures/recategorize-other?secret=bad",
            "/api/admin/futures/regenerate-tags?secret=bad",
            "/api/admin/futures/force-categorize?secret=bad",
            "/api/admin/futures/enrich-metadata?secret=bad",
            "/api/admin/events/enrich-metadata?secret=bad",
            "/api/admin/taxonomy/backfill?secret=bad",
            "/api/admin/taxonomy/enrich?secret=bad",
        ],
    )
    async def test_post_rejects_bad_secret(self, client, path):
        resp = await client.post(path)
        assert resp.status_code == 403
        assert resp.json() ["detail"] in ("Invalid admin secret", "Admin auth not configured")

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/futures/categorization-status",
            "/api/admin/taxonomy/vocabulary",
            "/api/admin/taxonomy/dashboard",
        ],
    )
    async def test_missing_secret_returns_403(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Futures categorization endpoints (Celery-queued)
# ---------------------------------------------------------------------------


class TestFuturesCategorize:
    """POST /api/admin/futures/categorize — queues a Celery task."""

    async def test_returns_queued_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-abc-123"

        with patch(
            "app.tasks.categorize_futures_task"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/futures/categorize", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "task-abc-123"
        assert "message" in body


class TestFuturesRecategorizeOther:
    """POST /api/admin/futures/recategorize-other — re-run rules."""

    async def test_returns_queued_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-recat-456"

        with patch(
            "app.tasks.recategorize_other_task"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/futures/recategorize-other", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "task-recat-456"


class TestFuturesRegenerateTags:
    """POST /api/admin/futures/regenerate-tags."""

    async def test_returns_queued_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-tags-789"

        with patch(
            "app.tasks.regenerate_tags_task"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/futures/regenerate-tags", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "task-tags-789"


class TestFuturesForceCategorize:
    """POST /api/admin/futures/force-categorize."""

    async def test_returns_queued_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-force-999"

        with patch(
            "app.tasks.categorize_futures_task"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/futures/force-categorize", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"


# ---------------------------------------------------------------------------
# Categorization / metadata status (DB-backed)
# ---------------------------------------------------------------------------


class TestFuturesCategorizationStatus:
    """GET /api/admin/futures/categorization-status."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        # Mock the aggregate query result
        row = SimpleNamespace(
            total=1000, with_sport_id=600, with_llm_category=300, uncategorized=100
        )
        mock_db.execute.return_value.one.return_value = row

        with patch("app.services.llm.is_available", return_value=False):
            resp = await client.get(
                "/api/admin/futures/categorization-status", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "with_sport_id" in body
        assert "with_llm_category" in body
        assert "uncategorized" in body
        assert "completion_pct" in body
        assert "llm_available" in body
        assert body["total"] == 1000
        assert body["completion_pct"] == 90.0


class TestFuturesUncategorized:
    """GET /api/admin/futures/uncategorized."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        # Mock returns empty list (no uncategorized markets)
        resp = await client.get(
            "/api/admin/futures/uncategorized", headers={"Authorization": "Bearer test-secret"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "count" in body
        assert "markets" in body
        assert "hint" in body
        assert isinstance(body["markets"], list)


class TestEventsMetadataStatus:
    """GET /api/admin/events/metadata-status."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        row = SimpleNamespace(
            total=500, with_gender=400, with_level=350,
            with_league=300, with_importance=250, un_enriched=80
        )
        mock_db.execute.return_value.one.return_value = row

        with patch("app.services.llm.is_available", return_value=True):
            resp = await client.get(
                "/api/admin/events/metadata-status", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        for key in ("total", "with_gender", "with_level", "with_league",
                     "with_importance", "un_enriched", "llm_available", "completion_pct"):
            assert key in body
        assert body["llm_available"] is True
        assert body["completion_pct"] == 84.0


class TestFuturesMetadataStatus:
    """GET /api/admin/futures/metadata-status."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        row = SimpleNamespace(
            total=2000, with_gender=1500, with_level=1400,
            with_league=1300, un_enriched=400
        )
        mock_db.execute.return_value.one.return_value = row

        with patch("app.services.llm.is_available", return_value=False):
            resp = await client.get(
                "/api/admin/futures/metadata-status", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        for key in ("total", "with_gender", "with_level", "with_league",
                     "un_enriched", "llm_available", "completion_pct"):
            assert key in body
        assert body["completion_pct"] == 80.0


# ---------------------------------------------------------------------------
# Taxonomy endpoints
# ---------------------------------------------------------------------------


class TestTaxonomyDebugRedis:
    """GET /api/admin/taxonomy/debug-redis."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("redis.from_url", return_value=mock_redis):
            resp = await client.get(
                "/api/admin/taxonomy/debug-redis", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "taxonomy_debug" in body
        assert "llm_enrich_gate" in body


class TestTaxonomyBackfill:
    """POST /api/admin/taxonomy/backfill — queues or runs sync."""

    async def test_queued_mode_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-backfill-001"

        with patch(
            "app.tasks.update_event_tags"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/taxonomy/backfill", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "task-backfill-001"


class TestTaxonomyTaskStatus:
    """GET /api/admin/taxonomy/task/{task_id}."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_result = MagicMock()
        mock_result.state = "PENDING"
        mock_result.result = None

        mock_app = MagicMock()
        mock_app.AsyncResult.return_value = mock_result

        with patch("app.tasks.celery_app", mock_app):
            resp = await client.get(
                "/api/admin/taxonomy/task/fake-task-id", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "fake-task-id"
        assert body["state"] == "PENDING"


class TestTaxonomyVocabulary:
    """GET /api/admin/taxonomy/vocabulary — controlled tag vocabulary."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        resp = await client.get(
            "/api/admin/taxonomy/vocabulary", headers={"Authorization": "Bearer test-secret"}
        )

        assert resp.status_code == 200
        body = resp.json()
        # Vocabulary returns {namespace: [sorted values]}
        assert isinstance(body, dict)
        for namespace, values in body.items():
            assert isinstance(namespace, str)
            assert isinstance(values, list)
            # Values should be sorted
            assert values == sorted(values)


class TestTaxonomyDashboard:
    """GET /api/admin/taxonomy/dashboard — tag distribution dashboard."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        # The dashboard runs 6 raw SQL queries, all returning empty rows
        # mock_db.execute already returns empty results from conftest
        resp = await client.get(
            "/api/admin/taxonomy/dashboard", headers={"Authorization": "Bearer test-secret"}
        )

        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "generated_at",
            "event_coverage",
            "futures_coverage",
            "event_tag_distribution",
            "futures_tag_distribution",
            "sport_distribution",
            "signal_distribution",
        ):
            assert key in body
        assert isinstance(body["event_tag_distribution"], list)
        assert isinstance(body["futures_tag_distribution"], list)
        assert isinstance(body["sport_distribution"], list)

    async def test_classification_health_envelope_present_and_green_on_empty_db(
        self, client, mock_db, monkeypatch
    ):
        """UX-P001: the versioned verdict rides alongside raw coverage, and an
        empty population (nothing to be wrong) reads GREEN, not 'attention'."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        resp = await client.get(
            "/api/admin/taxonomy/dashboard",
            headers={"Authorization": "Bearer test-secret"},
        )

        assert resp.status_code == 200
        health = resp.json()["classification_health"]
        assert health["version"] >= 1
        assert health["verdict"] == "green"
        assert health["census_complete"] is True
        assert health["actionable"]["count"] == 0
        for key in ("numerator", "denominator", "events", "futures"):
            assert key in health["eligible"]


class TestTaxonomyEnrich:
    """POST /api/admin/taxonomy/enrich — LLM enrichment."""

    async def test_returns_queued_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_task = MagicMock()
        mock_task.id = "task-enrich-001"

        with patch(
            "app.tasks.enrich_taxonomy_llm"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            resp = await client.post(
                "/api/admin/taxonomy/enrich", headers={"Authorization": "Bearer test-secret"}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "task-enrich-001"


class TestTaxonomyEnrichmentStatus:
    """GET /api/admin/taxonomy/enrichment-status."""

    async def test_returns_200_with_valid_secret(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        # Runs raw SQL queries — mock_db returns empty results
        resp = await client.get(
            "/api/admin/taxonomy/enrichment-status", headers={"Authorization": "Bearer test-secret"}
        )

        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "generated_at",
            "llm_namespaces",
            "event_enrichment",
            "market_enrichment",
            "llm_tag_distribution",
            "cache_status",
        ):
            assert key in body
        assert isinstance(body["llm_namespaces"], list)
        assert isinstance(body["llm_tag_distribution"], list)
        assert isinstance(body["cache_status"], dict)
