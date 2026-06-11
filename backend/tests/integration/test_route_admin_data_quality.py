"""Contract tests for admin data-quality endpoints."""

import pytest


class TestDataQualityAuthGuards:
    """Data quality admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/snapshots/stats?secret=bad",
            "/api/admin/futures/groups/status?secret=bad",
            "/api/admin/db/storage-analysis?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403

    async def test_missing_secret_returns_403(self, client):
        resp = await client.get("/api/admin/snapshots/stats")
        assert resp.status_code == 403
