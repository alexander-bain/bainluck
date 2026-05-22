"""Contract tests for admin event endpoints."""

import pytest


class TestEventAdminAuthGuards:
    """Event admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/schedule/accuracy?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403
