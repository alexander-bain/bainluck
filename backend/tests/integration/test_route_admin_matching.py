"""Contract tests for admin matching endpoints."""

from unittest.mock import MagicMock, patch

import pytest


class TestMatchingAuthGuards:
    """Matching admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/prediction-markets/link-rate?secret=bad",
            "/api/admin/prediction-markets/status?secret=bad",
            "/api/admin/prediction-markets/tier1-compliance?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/prediction-markets/link-rate",
            "/api/admin/prediction-markets/status",
        ],
    )
    async def test_missing_secret_returns_403(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403


class TestSeedTriggerAuthGuards:
    """#171 — the seed/backfill trigger endpoints reject bad/missing secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/entity-registry/seed?secret=bad",
            "/api/admin/polymarket/backfill-matchups?secret=bad",
        ],
    )
    async def test_post_rejects_bad_secret(self, client, path):
        resp = await client.post(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/entity-registry/seed",
            "/api/admin/polymarket/backfill-matchups",
        ],
    )
    async def test_post_missing_secret_returns_403(self, client, path):
        resp = await client.post(path)
        assert resp.status_code == 403


class TestSeedTriggers:
    """#171/#1020/#1021 — triggers enqueue the task and return its id."""

    async def test_entity_registry_seed_queues_task(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
        mock_task = MagicMock()
        mock_task.delay.return_value.id = "fake-seed-task"
        with patch("app.tasks.seed_entity_registry", mock_task):
            resp = await client.post(
                "/api/admin/entity-registry/seed", headers={"Authorization": "Bearer test-secret"}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "fake-seed-task"
        assert body["persons_only"] is True  # default
        mock_task.delay.assert_called_once_with(True)

    async def test_entity_registry_seed_respects_persons_only_false(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
        mock_task = MagicMock()
        mock_task.delay.return_value.id = "fake-seed-task"
        with patch("app.tasks.seed_entity_registry", mock_task):
            resp = await client.post(
                "/api/admin/entity-registry/seed?persons_only=false", headers={"Authorization": "Bearer test-secret"}
            )
        assert resp.status_code == 200
        assert resp.json()["persons_only"] is False
        mock_task.delay.assert_called_once_with(False)

    async def test_polymarket_backfill_matchups_queues_task(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
        mock_task = MagicMock()
        mock_task.delay.return_value.id = "fake-backfill-task"
        with patch("app.tasks.backfill_polymarket_matchups", mock_task):
            resp = await client.post(
                "/api/admin/polymarket/backfill-matchups", headers={"Authorization": "Bearer test-secret"}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["task_id"] == "fake-backfill-task"
        assert body["all_groups"] is False  # default = linked only
        mock_task.delay.assert_called_once_with(False)


class TestSeedTasksRegistered:
    """The on-demand tasks must be registered so the triggers can enqueue them."""

    def test_tasks_are_registered(self):
        from app.tasks import celery_app

        assert "app.tasks.seed_entity_registry" in celery_app.tasks
        assert "app.tasks.backfill_polymarket_matchups" in celery_app.tasks

    def test_tasks_are_importable(self):
        from app.tasks import (  # noqa: F401
            backfill_polymarket_matchups,
            seed_entity_registry,
        )
