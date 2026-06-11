"""Contract tests for admin team endpoints."""

import pytest


class TestTeamAdminAuthGuards:
    """Team admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/team-identity/status?secret=bad",
            "/api/admin/team-identity/unmapped?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/team-identity/status",
            "/api/admin/team-identity/unmapped",
        ],
    )
    async def test_missing_secret_returns_403(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403
