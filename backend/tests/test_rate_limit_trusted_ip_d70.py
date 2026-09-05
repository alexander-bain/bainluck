"""D70 / #3297 — the trusted-address ceiling, and the forgery it must refuse.

WHAT SHIPPED. Every working window on our own Mac, plus the ``look.sh`` screenshot
browser each of them drives, leaves through one public address and shares the one
60/min anonymous bucket. They spend it continuously, so Alex's own browser asking
for ``/api/calibration`` from that machine gets a 429 and the page renders
"Failed to load calibration data". ``RATE_LIMIT_TRUSTED_IPS`` gives named
addresses a 600/min CEILING instead.

WHY THE FORGERY TEST IS THE POINT. The allowlist gates a privilege, so the address
it matches on may not be one the caller can choose. ``_get_client_ip`` reads
``X-Forwarded-For`` position 0, which is caller-supplied — measured against
production on 2026-09-05, ``curl -H 'X-Forwarded-For: 203.0.113.77'`` answered 200
from an address that was otherwise being 429'd. An allowlist on that value is an
allowlist for the internet. ``_router_peer_ip`` reads position -1, which Heroku's
router appends itself.

Both arms are pinned here: the trusted address gets the ceiling, AND a request that
merely CLAIMS to be the trusted address gets the anonymous limit. A test that only
asserted the first would pass just as happily against the total-bypass version.
"""

import pytest

from app.utils.rate_limit import (
    RateLimitMiddleware,
    _get_client_ip,
    _router_peer_ip,
    _trusted_ips,
)

TRUSTED = "198.51.100.7"
STRANGER = "203.0.113.99"


def _make_request(xff=None, client=None):
    from starlette.requests import Request

    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    if client is not None:
        scope["client"] = client
    return Request(scope)


def _make_app(anon_limit="3/minute", trusted_limit="8/minute"):
    """Minimal app on the in-memory limiter, with small limits so the two
    ceilings are distinguishable in a handful of requests."""
    import app.utils.rate_limit as rl_mod
    from fastapi import FastAPI

    rl_mod.ANON_RATE_LIMIT = anon_limit
    rl_mod.TRUSTED_RATE_LIMIT = trusted_limit
    # Force a re-parse: the limit singletons are cached across tests.
    rl_mod._anon_limit = None
    rl_mod._auth_limit = None
    rl_mod._admin_limit = None
    rl_mod._trusted_limit = None
    rl_mod._rate_limiter = None

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/calibration")
    async def calibration():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Every test starts with no allowlist and no Redis, so the in-memory
    fallback path is the one under test and no state leaks between cases."""
    import app.utils.rate_limit as rl_mod

    monkeypatch.delenv("RATE_LIMIT_TRUSTED_IPS", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_TLS_URL", raising=False)
    monkeypatch.delenv("BYPASS_RATE_LIMITS", raising=False)
    rl_mod._trusted_ip_cache = ("", frozenset())
    rl_mod._async_rl_redis = None
    rl_mod._async_rl_unavailable = True
    yield
    rl_mod._trusted_ip_cache = ("", frozenset())
    rl_mod._async_rl_unavailable = False


# ---------------------------------------------------------------------------
# _router_peer_ip vs _get_client_ip — the two must NOT agree on a forged chain
# ---------------------------------------------------------------------------


class TestRouterPeerIp:
    def test_reads_the_last_entry_not_the_first(self):
        """The router appends itself, so position -1 is ours and 0 is theirs."""
        req = _make_request(xff=f"{STRANGER}, {TRUSTED}")
        assert _router_peer_ip(req) == TRUSTED
        assert _get_client_ip(req) == STRANGER

    def test_single_entry_chain_is_that_entry(self):
        req = _make_request(xff=TRUSTED)
        assert _router_peer_ip(req) == TRUSTED

    def test_falls_back_to_socket_peer_without_the_header(self):
        req = _make_request(client=("192.0.2.5", 1234))
        assert _router_peer_ip(req) == "192.0.2.5"

    def test_unknown_when_nothing_identifies_the_peer(self):
        assert _router_peer_ip(_make_request()) == "unknown"

    def test_whitespace_and_empty_segments_do_not_shift_the_position(self):
        """A caller padding the chain with blanks must not push our entry off
        the end — ``'a, ,b,'`` still resolves to ``b``."""
        req = _make_request(xff=f"{STRANGER}, , {TRUSTED} ,")
        assert _router_peer_ip(req) == TRUSTED


# ---------------------------------------------------------------------------
# The allowlist parser
# ---------------------------------------------------------------------------


class TestTrustedIpsParsing:
    def test_unset_is_empty_so_the_default_changes_nothing(self):
        assert _trusted_ips() == frozenset()

    def test_comma_separated_with_padding(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", f" {TRUSTED} , 192.0.2.9 ")
        assert _trusted_ips() == frozenset({TRUSTED, "192.0.2.9"})

    def test_blank_entries_are_dropped(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", f",,{TRUSTED},,")
        assert _trusted_ips() == frozenset({TRUSTED})

    def test_empty_string_grants_nothing(self, monkeypatch):
        """An empty value must not parse to a set containing '' — otherwise a
        request whose peer resolves to '' would be trusted."""
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", "   ")
        assert _trusted_ips() == frozenset()

    def test_cache_follows_a_changed_value(self, monkeypatch):
        """The cache is keyed on the raw string, so a config change is picked up
        rather than pinned for the life of the process."""
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        assert _trusted_ips() == frozenset({TRUSTED})
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", STRANGER)
        assert _trusted_ips() == frozenset({STRANGER})


# ---------------------------------------------------------------------------
# End to end through the middleware
# ---------------------------------------------------------------------------


class TestTrustedCeilingEndToEnd:
    def test_without_the_allowlist_the_trusted_address_is_just_anonymous(self):
        """The shipped default. Nothing changes for anyone until the var is set."""
        from starlette.testclient import TestClient

        client = TestClient(_make_app(anon_limit="3/minute"))
        hdr = {"X-Forwarded-For": TRUSTED}
        for _ in range(3):
            assert client.get("/api/calibration", headers=hdr).status_code == 200
        assert client.get("/api/calibration", headers=hdr).status_code == 429

    def test_trusted_address_gets_the_higher_ceiling(self, monkeypatch):
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app(anon_limit="3/minute", trusted_limit="8/minute"))
        hdr = {"X-Forwarded-For": TRUSTED}
        for i in range(8):
            resp = client.get("/api/calibration", headers=hdr)
            assert resp.status_code == 200, f"request {i + 1} should pass the ceiling"
        assert client.get("/api/calibration", headers=hdr).status_code == 429

    def test_it_is_a_ceiling_and_not_an_exemption(self, monkeypatch):
        """The Queue 315 rule. A trusted address is still metered — if this ever
        returns 200 forever, someone turned the ceiling into a bypass."""
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app(anon_limit="3/minute", trusted_limit="5/minute"))
        hdr = {"X-Forwarded-For": TRUSTED}
        codes = [
            client.get("/api/calibration", headers=hdr).status_code for _ in range(12)
        ]
        assert 429 in codes, "a trusted address must still hit a limit"
        assert codes.count(200) == 5

    def test_a_forged_claim_to_the_trusted_address_gets_the_ANONYMOUS_limit(
        self, monkeypatch
    ):
        """🔴 THE LOAD-BEARING CASE.

        A stranger prepends the trusted address to their own chain, exactly as our
        own production probe did. Heroku appends their real address, so the chain
        that arrives is ``TRUSTED, STRANGER``. They must be metered at 3, not 8 —
        if this test goes green at 8 the allowlist has become a public bypass.
        """
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app(anon_limit="3/minute", trusted_limit="8/minute"))
        hdr = {"X-Forwarded-For": f"{TRUSTED}, {STRANGER}"}
        for i in range(3):
            assert client.get("/api/calibration", headers=hdr).status_code == 200, i
        assert client.get("/api/calibration", headers=hdr).status_code == 429

    def test_a_forger_cannot_spend_the_trusted_bucket(self, monkeypatch):
        """The forger's requests key on their own address, so they cannot deny
        service to the machine the allowlist exists to unblock. This is why the
        trusted key is `trusted:<ip>` and not the bare address."""
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app(anon_limit="3/minute", trusted_limit="8/minute"))

        forged = {"X-Forwarded-For": f"{TRUSTED}, {STRANGER}"}
        for _ in range(6):
            client.get("/api/calibration", headers=forged)

        # The real machine still has its full ceiling.
        real = {"X-Forwarded-For": TRUSTED}
        for i in range(8):
            resp = client.get("/api/calibration", headers=real)
            assert resp.status_code == 200, f"trusted request {i + 1} was starved"

    def test_a_non_listed_address_is_unaffected(self, monkeypatch):
        from starlette.testclient import TestClient

        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        client = TestClient(_make_app(anon_limit="3/minute", trusted_limit="8/minute"))
        hdr = {"X-Forwarded-For": STRANGER}
        for _ in range(3):
            assert client.get("/api/calibration", headers=hdr).status_code == 200
        assert client.get("/api/calibration", headers=hdr).status_code == 429
