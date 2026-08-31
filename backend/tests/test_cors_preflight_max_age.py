"""LAT-P175 / #2431: the CORS preflight cache lifetime is CHOSEN, not inherited.

The Discover feed request carries `x-session-id`, a non-simple header, which makes
every `bainluck.com` → `api.bainluck.com` feed GET a preflighted request. Starlette's
`CORSMiddleware` defaults `max_age` to 600 s, so before this fix any load more than
ten minutes after the previous one re-paid a full preflight round trip — measured at
215-252 ms on production — BEFORE the feed GET was allowed to start.

The defect was not that 600 was too low. It was that **nobody chose 600**; the
framework did. So these guards assert the value is passed explicitly AND that the
served header carries it, and the explicitness check is deliberately independent of
whatever Starlette's default happens to be in a future version.

These tests read the DEPLOYED app (`app.main.app`). A locally-constructed
`CORSMiddleware` fixture would pass no matter what `main.py` does.
"""

import pytest
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient


#: Chrome's hard cap on preflight-cache lifetime. Larger values are silently
#: clamped to this, so it is the largest value that is honest about what the
#: browser will actually do.
EXPECTED_MAX_AGE = 7200

#: What Starlette hands you when `max_age` is omitted. Pinned as a literal on
#: purpose: if a future Starlette changes its default, this test still describes
#: the bug that was fixed rather than silently re-aligning with the framework.
STARLETTE_INHERITED_DEFAULT = 600


def _cors_middleware_options():
    """The kwargs `main.py` actually registered CORSMiddleware with."""
    from app.main import app as main_app

    for mw in main_app.user_middleware:
        if mw.cls is CORSMiddleware:
            return getattr(mw, "kwargs", {}) or {}
    pytest.fail("CORSMiddleware is not registered on app.main.app at all")


class TestCorsPreflightMaxAgeIsChosen:
    def test_max_age_is_passed_explicitly_not_inherited(self):
        """The regression this exists for: deleting `max_age=` from main.py silently
        reverts to Starlette's default and nothing else in the suite notices."""
        options = _cors_middleware_options()

        assert "max_age" in options, (
            "main.py must pass max_age= to CORSMiddleware explicitly. Omitting it "
            f"inherits Starlette's default of {STARLETTE_INHERITED_DEFAULT}s, which "
            "is the #2431 defect: a re-paid ~215ms preflight on every load more "
            "than ten minutes after the last one."
        )
        assert options["max_age"] == EXPECTED_MAX_AGE, (
            f"expected max_age={EXPECTED_MAX_AGE} (Chrome's preflight-cache cap); "
            f"got {options['max_age']}"
        )

    def test_served_preflight_carries_the_chosen_max_age(self):
        """Test the thing that RUNS: the middleware as wired, on a real OPTIONS
        preflight shaped like the Discover feed's (x-session-id is what makes the
        feed request preflighted in the first place)."""
        from app.main import app as main_app

        client = TestClient(main_app)
        resp = client.options(
            "/api/feed",
            headers={
                "Origin": "https://bainluck.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-session-id",
            },
        )

        assert resp.status_code == 200, resp.text
        served = resp.headers.get("access-control-max-age")
        assert served is not None, (
            "the preflight response carried no Access-Control-Max-Age at all"
        )
        assert int(served) == EXPECTED_MAX_AGE, (
            f"served Access-Control-Max-Age={served}, expected {EXPECTED_MAX_AGE}"
        )
        assert int(served) != STARLETTE_INHERITED_DEFAULT, (
            "the served preflight lifetime is Starlette's inherited default — "
            "max_age was dropped from main.py"
        )
