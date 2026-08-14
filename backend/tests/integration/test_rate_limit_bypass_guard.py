"""The integration suite must never be able to rate-limit itself.

UX-P072 (#1829) found the suite sitting exactly on the limiter's
`60 per 1 minute`. Adding one ordinary test — one more GET, in a different
file, against a different fixture — pushed it over, and the failure landed on
an unrelated futures test as a bare `KeyError: 'items'`. The baseline was
green, so the obvious reading was "the production change broke the feed". It
had not; the counter was simply full. The real response was
`429 {"detail": "Rate limit exceeded: 60 per 1 minute"}`.

`BYPASS_RATE_LIMITS` was already set — but only inside the `client` fixture in
`conftest.py`, so `seeded_client` and `event_detail_client`, defined in their
own test modules, never got it. It is now set from an AUTOUSE fixture, which is
what makes that class of miss impossible.

This file guards that fixture. Note the client below is built LOCALLY and
deliberately does NOT set the env var itself: the shared `client` fixture sets
`BYPASS_RATE_LIMITS` in its own body, so a guard written against it passes even
with the autouse fixture deleted — which is exactly what the first draft of
this file did, and a plant is the only reason that is known rather than assumed.

If this goes red, do not raise the threshold — the bypass has stopped working,
and every other integration test is one request from a spurious failure.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

# Must not be in `_EXEMPT_PREFIXES` ("/docs", "/openapi.json", "/redoc",
# "/health"), or this measures nothing.
PROBE_PATH = "/api/feed?limit=1"
ANONYMOUS_LIMIT_PER_MINUTE = 60


@pytest.fixture
async def unbypassed_client(mock_db):
    """A client that inherits the bypass ONLY from the autouse fixture."""
    from app.main import app

    async def _mock_get_db():
        yield mock_db

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


class TestRateLimitBypassIsActive:
    async def test_the_bypass_env_var_is_set(self):
        import os

        assert os.getenv("BYPASS_RATE_LIMITS") == "1", (
            "the autouse _bypass_rate_limits fixture in "
            "tests/integration/conftest.py has been removed or renamed"
        )

    async def test_more_requests_than_the_limit_are_never_refused(
        self, unbypassed_client
    ):
        """The mechanism, exercised rather than asserted."""
        statuses = []
        for _ in range(ANONYMOUS_LIMIT_PER_MINUTE + 30):
            resp = await unbypassed_client.get(PROBE_PATH)
            statuses.append(resp.status_code)

        refused = [i for i, s in enumerate(statuses) if s == 429]
        assert not refused, (
            f"rate limiter active in the integration suite: {len(refused)} of "
            f"{len(statuses)} requests refused, first at #{refused[0]}"
        )

    def test_the_probe_path_is_not_exempt(self):
        """Otherwise the test above passes forever and proves nothing."""
        from app.utils.rate_limit import _EXEMPT_PREFIXES

        path = PROBE_PATH.split("?")[0]
        assert not any(path.startswith(p) for p in _EXEMPT_PREFIXES), (
            f"{path} is exempt from rate limiting — pick a probe path that is not"
        )
