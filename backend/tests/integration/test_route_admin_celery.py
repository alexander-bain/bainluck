"""Contract tests for admin Celery endpoints (/api/admin/celery/*)."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Auth guard tests — every endpoint must reject bad / missing secrets
# ---------------------------------------------------------------------------


class TestCeleryAuthGuards:
    """All Celery admin endpoints reject invalid secrets with 403."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/celery/health?secret=bad",
            "/api/admin/celery/dashboard?secret=bad",
            "/api/admin/celery/task-metrics/some_task?secret=bad",
            "/api/admin/celery/inspect?secret=bad",
            "/api/admin/celery-debug?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Invalid admin secret"}

    async def test_purge_rejects_bad_secret(self, client):
        resp = await client.post("/api/admin/celery-purge-background?secret=bad")
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Invalid admin secret"}

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/celery/health",
            "/api/admin/celery/dashboard",
            "/api/admin/celery/inspect",
            "/api/admin/celery-debug",
        ],
    )
    async def test_missing_secret_returns_422(self, client, path):
        """Query param `secret` is required — omitting it returns 422."""
        resp = await client.get(path)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy-path response shape tests
# ---------------------------------------------------------------------------


class TestCeleryHealth:
    """GET /api/admin/celery/health — worker heartbeat check."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # no heartbeat yet

        with patch(
            "app.tasks.redis_state.get_redis_client", return_value=mock_redis
        ):
            resp = await client.get(
                "/api/admin/celery/health?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("healthy", "unhealthy", "unknown", "error")

    async def test_unknown_when_no_heartbeat(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch(
            "app.tasks.redis_state.get_redis_client", return_value=mock_redis
        ):
            resp = await client.get(
                "/api/admin/celery/health?secret=test-secret"
            )

        body = resp.json()
        assert body["status"] == "unknown"
        assert "message" in body

    async def test_error_on_redis_failure(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        with patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=Exception("connection refused"),
        ):
            resp = await client.get(
                "/api/admin/celery/health?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert "message" in body


class TestCeleryDashboard:
    """GET /api/admin/celery/dashboard — task-level health overview."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # no heartbeat

        with (
            patch(
                "app.tasks.redis_state.get_all_task_metrics", return_value=[]
            ),
            patch(
                "app.tasks.redis_state.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.tasks.redis_state.get_odds_api_quota", return_value=None
            ),
        ):
            resp = await client.get(
                "/api/admin/celery/dashboard?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        # Verify top-level response shape
        assert "overall_health" in body
        assert "worker_status" in body
        assert "tracked_tasks" in body
        assert "critical_tasks" in body
        assert "degraded_tasks" in body
        assert "tasks" in body
        assert "odds_api_quota" in body
        assert isinstance(body["tasks"], list)
        assert isinstance(body["critical_tasks"], list)
        assert isinstance(body["degraded_tasks"], list)

    async def test_no_data_health_when_empty(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with (
            patch(
                "app.tasks.redis_state.get_all_task_metrics", return_value=[]
            ),
            patch(
                "app.tasks.redis_state.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "app.tasks.redis_state.get_odds_api_quota", return_value=None
            ),
        ):
            resp = await client.get(
                "/api/admin/celery/dashboard?secret=test-secret"
            )

        body = resp.json()
        # Worker unknown + no tasks => worker_down or no_data
        assert body["overall_health"] in ("no_data", "worker_down")


class TestCeleryTaskMetrics:
    """GET /api/admin/celery/task-metrics/{task_name}."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        with patch(
            "app.tasks.redis_state.get_task_metrics", return_value={}
        ):
            resp = await client.get(
                "/api/admin/celery/task-metrics/poll_odds?secret=test-secret"
            )

        assert resp.status_code == 200


class TestCeleryInspect:
    """GET /api/admin/celery/inspect — worker inspection."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_inspect = MagicMock()
        mock_inspect.registered.return_value = {}
        mock_inspect.active.return_value = {}
        mock_inspect.reserved.return_value = {}

        mock_app = MagicMock()
        mock_app.control.inspect.return_value = mock_inspect

        with patch("app.tasks.celery_app", mock_app):
            resp = await client.get(
                "/api/admin/celery/inspect?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


class TestCeleryPurgeBackground:
    """POST /api/admin/celery-purge-background."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_app = MagicMock()
        mock_app.control.purge.return_value = 5

        with patch("app.tasks.celery_app", mock_app):
            resp = await client.post(
                "/api/admin/celery-purge-background?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "purged" in body
        assert body["purged"] == 5


class TestCeleryDebug:
    """GET /api/admin/celery-debug — detailed worker + queue debug info."""

    async def test_returns_200_with_valid_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {"worker1": {"ok": "pong"}}
        mock_inspect.active.return_value = {}
        mock_inspect.registered.return_value = {"worker1": ["task_a", "task_b"]}
        mock_inspect.stats.return_value = {
            "worker1": {"total": {}, "pool": {"max-concurrency": 4}}
        }

        mock_app = MagicMock()
        mock_app.control.inspect.return_value = mock_inspect
        mock_app.conf.broker_url = "redis://localhost:6379/0"

        mock_redis_instance = MagicMock()
        mock_redis_instance.llen.return_value = 0
        mock_redis_instance.info.return_value = {
            "used_memory_human": "1M",
            "connected_clients": 3,
        }

        with (
            patch("app.tasks.celery_app", mock_app),
            patch("redis.from_url", return_value=mock_redis_instance),
        ):
            resp = await client.get(
                "/api/admin/celery-debug?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "queue_lengths" in body
        assert "redis_info" in body
        assert isinstance(body["queue_lengths"], dict)
        for key in ("background", "realtime", "celery"):
            assert key in body["queue_lengths"]

    async def test_response_shape_on_inspect_error(self, client, monkeypatch):
        """Even if Celery inspect fails, the endpoint returns 200 with an error key."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_app = MagicMock()
        mock_app.control.inspect.side_effect = Exception("broker down")
        mock_app.conf.broker_url = "redis://localhost:6379/0"

        mock_redis_instance = MagicMock()
        mock_redis_instance.llen.return_value = 0
        mock_redis_instance.info.return_value = {
            "used_memory_human": "1M",
            "connected_clients": 1,
        }

        with (
            patch("app.tasks.celery_app", mock_app),
            patch("redis.from_url", return_value=mock_redis_instance),
        ):
            resp = await client.get(
                "/api/admin/celery-debug?secret=test-secret"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "inspect_error" in body
