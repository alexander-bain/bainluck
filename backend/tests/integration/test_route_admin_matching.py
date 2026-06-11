"""Contract tests for admin matching endpoints."""

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
