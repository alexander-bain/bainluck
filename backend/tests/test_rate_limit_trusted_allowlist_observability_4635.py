"""#4635 — telling "armed and matching" apart from "armed and matching nothing".

WHAT THIS SHIPS. `GET /api/admin/rate-limit/trusted-allowlist` answers, from
outside the dyno, whether D70's allowlist is granting anybody the 600/min ceiling.

🔴 WHY THE CONFIGURED COUNT IS NOT THE THING TO ASSERT, AND WHY THE ISSUE ASKED
FOR IT ANYWAY. #4635 was filed as "log `trusted rate-limit allowlist: N
address(es)` on first resolution". Then it was measured. On 2026-09-10, 14:08–14:13
PT, `RATE_LIMIT_TRUSTED_IPS` was set — one entry, live since v4388 — and 165
anonymous requests from a lane sandbox 429'd at #68 and #39, i.e. at ~60/minute,
i.e. entirely inside the shared anonymous bucket. Under a 600/min ceiling not one
of them could have been refused. The cause was not a rotated address: the lane
egress belongs to a shared corporate NAT the allowlist never described. A log line
reading `1 address(es)` would have been perfectly true throughout, and would have
read as healthy for the ≥17 hours nobody noticed.

So the test that matters here is `test_armed_but_matching_nothing_is_NAMED`. A
suite that only pinned the count, or only pinned the happy path, would go green
against a build that reproduces the September defect exactly.

THE SECOND LOAD-BEARING CASE is `test_the_published_state_never_carries_an
_address`. `_trusted_ips()`'s docstring keeps the value out of tracked files
because it identifies an operator's network; an admin endpoint that prints it back
would walk around that rule rather than through it. The assertion is on the KEY
SET, not on a substring search, so a field ADDED later that carries an address
fails this test instead of quietly passing it.
"""

import json

import pytest

import app.utils.rate_limit as rate_limit_module
from app.utils.rate_limit import RateLimitMiddleware, trusted_allowlist_state

TRUSTED = "198.51.100.7"
STRANGER = "203.0.113.99"

#: Exactly the fields the endpoint publishes. Pinned as a SET so that adding one
#: is a deliberate act with a test change attached — see the module docstring.
PUBLISHED_FIELDS = {
    "verdict",
    "configured_entries",
    "matched_requests",
    "unmatched_requests",
    "observed_seconds",
    "dyno",
}


def _make_app(anon_limit="60/minute", trusted_limit="600/minute"):
    """Minimal app on the in-memory limiter.

    The ceilings stay at their real values here: this file counts BRANCHES, not
    refusals, so it never needs to provoke a 429 — and lowering `ANON_RATE_LIMIT`
    is what leaked out of `test_rate_limit_trusted_ip_d70.py` and reddened a
    stranger's file on a shard re-pack. Nothing is gained by repeating it.
    """
    from fastapi import FastAPI

    rate_limit_module.ANON_RATE_LIMIT = anon_limit
    rate_limit_module.TRUSTED_RATE_LIMIT = trusted_limit
    rate_limit_module._anon_limit = None
    rate_limit_module._auth_limit = None
    rate_limit_module._admin_limit = None
    rate_limit_module._trusted_limit = None
    rate_limit_module._rate_limiter = None

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/calibration")
    async def calibration():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """No allowlist, no Redis, zeroed counters — and everything restored after.

    The counters are process globals, so without the reset a case would read
    whatever an earlier case left and the verdicts would depend on collection
    order. The ceiling restore is the lesson from the D70 file's own docstring.
    """
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_IPS", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_TLS_URL", raising=False)
    monkeypatch.delenv("BYPASS_RATE_LIMITS", raising=False)
    monkeypatch.delenv("DYNO", raising=False)

    saved_ceilings = (
        rate_limit_module.ANON_RATE_LIMIT,
        rate_limit_module.TRUSTED_RATE_LIMIT,
    )

    rate_limit_module._trusted_ip_cache = ("", frozenset())
    rate_limit_module._async_rl_redis = None
    rate_limit_module._async_rl_unavailable = True
    rate_limit_module._reset_trusted_observations()
    yield
    rate_limit_module._trusted_ip_cache = ("", frozenset())
    rate_limit_module._async_rl_unavailable = False
    rate_limit_module._reset_trusted_observations()

    rate_limit_module.ANON_RATE_LIMIT, rate_limit_module.TRUSTED_RATE_LIMIT = (
        saved_ceilings
    )
    rate_limit_module._anon_limit = None
    rate_limit_module._auth_limit = None
    rate_limit_module._admin_limit = None
    rate_limit_module._trusted_limit = None
    rate_limit_module._rate_limiter = None


def _drive(client, peer, n):
    """Send ``n`` requests whose ROUTER-SEEN address is ``peer``.

    The chain arrives as ``<claim>, <peer>`` because Heroku's router appends what
    it actually saw. Driving the real middleware is the point: a test that called
    the counter helper directly would pass against a build where the middleware
    never calls it.
    """
    hdr = {"X-Forwarded-For": f"192.0.2.1, {peer}"}
    for _ in range(n):
        assert client.get("/api/calibration", headers=hdr).status_code == 200


class TestTheVerdictSeparatesArmedFromWorking:
    def test_armed_but_matching_nothing_is_NAMED(self, monkeypatch):
        """🔴 THE SEPTEMBER STATE. Configured, traffic arriving, zero matches.

        Every fact the original "log the count" ask would have published is
        healthy here — the var is set, it parses, it holds one address. The only
        thing that says otherwise is that nothing matched it.
        """
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app())
        _drive(client, STRANGER, 5)

        state = trusted_allowlist_state()
        assert state["verdict"] == "armed_but_matching_nothing"
        assert state["configured_entries"] == 1, "the count alone still reads fine"
        assert state["matched_requests"] == 0
        assert state["unmatched_requests"] == 5

    def test_armed_and_matching_when_the_listed_address_calls(self, monkeypatch):
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app())
        _drive(client, TRUSTED, 4)

        state = trusted_allowlist_state()
        assert state["verdict"] == "armed_and_matching"
        assert state["matched_requests"] == 4
        assert state["unmatched_requests"] == 0

    def test_armed_with_no_traffic_is_NOT_reported_as_broken(self, monkeypatch):
        """A freshly booted dyno has seen nothing and must say so.

        Collapsing this into the defect verdict would make the read-out cry wolf
        on every release, which is how a signal stops being read.
        """
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)

        state = trusted_allowlist_state()
        assert state["verdict"] == "armed_no_traffic_yet"
        assert state["matched_requests"] == 0
        assert state["unmatched_requests"] == 0

    def test_unset_is_the_default_and_is_not_a_defect(self):
        """No allowlist configured, real traffic flowing: `unset`, not a warning.

        The counters must stay at zero, which is the assertion that the branch
        costs an unconfigured deploy nothing at all — the whole hot-path
        constraint in #4635, expressed as an observable rather than as a comment.
        """
        from starlette.testclient import TestClient

        client = TestClient(_make_app())
        _drive(client, STRANGER, 5)

        state = trusted_allowlist_state()
        assert state["verdict"] == "unset"
        assert state["configured_entries"] == 0
        assert (state["matched_requests"], state["unmatched_requests"]) == (0, 0)

    def test_one_matching_request_moves_the_verdict_off_the_defect(self, monkeypatch):
        """The verdict is derived, not constant.

        A build that hard-coded `armed_but_matching_nothing` would pass the first
        case in this class. It cannot pass this one.
        """
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app())

        _drive(client, STRANGER, 3)
        assert trusted_allowlist_state()["verdict"] == "armed_but_matching_nothing"

        _drive(client, TRUSTED, 1)
        after = trusted_allowlist_state()
        assert after["verdict"] == "armed_and_matching"
        assert (after["matched_requests"], after["unmatched_requests"]) == (1, 3)

    def test_a_forged_claim_to_the_trusted_address_counts_as_a_MISS(self, monkeypatch):
        """A stranger prepending the trusted address is not a match, and the
        read-out must not be fooled into reporting the allowlist healthy by
        traffic that never received the ceiling."""
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app())

        hdr = {"X-Forwarded-For": f"{TRUSTED}, {STRANGER}"}
        for _ in range(3):
            assert client.get("/api/calibration", headers=hdr).status_code == 200

        state = trusted_allowlist_state()
        assert state["verdict"] == "armed_but_matching_nothing"
        assert state["matched_requests"] == 0


class TestThePublishedStateCarriesNoOperatorIdentity:
    def test_the_published_state_never_carries_an_address(self, monkeypatch):
        """🔴 THE CREDENTIAL-RULE GUARD.

        Pinned on the KEY SET rather than on `TRUSTED not in json`, because a
        substring search passes whenever the test's fixture value happens to
        differ from the one a future field would leak. If someone adds
        `"entries": [...]`, this fails.
        """
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", f"{TRUSTED},{STRANGER}")

        state = trusted_allowlist_state()
        assert set(state) == PUBLISHED_FIELDS

        blob = json.dumps(state)
        assert TRUSTED not in blob
        assert STRANGER not in blob
        assert state["configured_entries"] == 2, "the COUNT is published, not the set"

    def test_every_published_value_is_a_count_a_verdict_or_the_dyno(self, monkeypatch):
        """No field may be free text sourced from config. `verdict` is checked
        against the closed vocabulary; `dyno` is Heroku's own label, which names
        a process and not a network."""
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        monkeypatch.setenv("DYNO", "web.3")

        state = trusted_allowlist_state()
        assert state["verdict"] in {
            "unset",
            "armed_no_traffic_yet",
            "armed_and_matching",
            "armed_but_matching_nothing",
        }
        assert state["dyno"] == "web.3"
        for field in ("configured_entries", "matched_requests", "unmatched_requests"):
            assert isinstance(state[field], int)
        assert isinstance(state["observed_seconds"], float)


class TestTheAdminSurface:
    def test_the_endpoint_returns_the_state(self, monkeypatch):
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.routes import admin_rate_limit

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)

        app = FastAPI()
        app.include_router(admin_rate_limit.router, prefix="/api")
        resp = TestClient(app).get("/api/admin/rate-limit/trusted-allowlist")

        assert resp.status_code == 200
        assert set(resp.json()) == PUBLISHED_FIELDS
        assert resp.json()["verdict"] == "armed_no_traffic_yet"

    def test_it_is_mounted_under_admin_and_nowhere_public(self):
        """#4635: a public surface advertises that an allowlist exists. The path
        is asserted on the ROUTER's own prefix so a later move off `/admin` is a
        test failure rather than a quiet exposure."""
        from app.routes import admin_rate_limit

        assert admin_rate_limit.router.prefix == "/admin/rate-limit"
        paths = [route.path for route in admin_rate_limit.router.routes]
        assert paths == ["/admin/rate-limit/trusted-allowlist"]

    def test_the_app_mounts_it_behind_the_admin_dependencies(self):
        """gotcha #2: an admin router that is imported but not included is a 404,
        and one included without `ADMIN_ROUTER_DEPENDENCIES` is a public read."""
        from app.main import app

        matches = [
            r
            for r in app.routes
            if getattr(r, "path", None) == "/api/admin/rate-limit/trusted-allowlist"
        ]
        assert len(matches) == 1, "route is not mounted on the real app"
        assert matches[0].dependencies, "mounted without the admin dependencies"
