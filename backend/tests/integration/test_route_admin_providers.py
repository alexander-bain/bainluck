"""Contract tests for admin provider endpoints."""

import pytest


class TestProviderAuthGuards:
    """Provider admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/kalshi/debug-discovery?secret=bad",
            "/api/admin/futures/sports?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/kalshi/debug-discovery",
            "/api/admin/futures/sports",
        ],
    )
    async def test_missing_secret_returns_403(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403
