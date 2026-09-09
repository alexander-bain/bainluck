"""`/api/admin/statpal/status` advertises only routes that exist — #2907, CERT-2381.

## The block this repairs

The #2907 retirement removed three StatPal task bodies, their beats and their
three admin trigger routes, because the venue does not publish the paths behind
them (`{sport}/fixtures/{id}/playbyplay`, `{sport}/teams`, team stats) and the
tasks banked 632 successes / 0 failures per 24h for work that could not happen.

CERT-2381 BLOCKed it on a surface the diff missed: `GET /api/admin/statpal/status`
kept returning 200 and kept advertising `sync_plays`, `sync_rosters` and
`sync_team_stats`, while POSTing each of the three returned **404**. That is the
same false-success shape one layer up — a directory an operator reads to decide
what to trigger, telling them about work that cannot be triggered. Gotcha #53:
"it returned" is not "it worked", and here "it is listed" was not "it exists".

## Why the contract is derived, not retyped

The obvious guard is a second list of the four surviving endpoints. That guard
passes forever after the route it names is deleted, because both copies are
prose. So every assertion below resolves the status payload's own values against
`app.main.app`'s mounted route table — the thing that actually answers the
request. A retired route can then only pass this file by still existing.

Read as a pair with `tests/test_statpal_retired_paths_2907.py` (21 tests), which
covers the accessors, models, tasks, beats and routes. This file covers the one
surface that survives the retirement and has to describe it correctly.
"""
import os

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.main import app
from app.routes.admin_providers import statpal_status

ADMIN_TOKEN = "statpal-status-contract-2907"

#: The three the retirement removed. Named here as literals ON PURPOSE — this is
#: the one place a hard-coded list is the right shape, because the assertion is
#: an ABSENCE and an absence cannot be derived from the app's route table (a
#: route that does not exist leaves nothing to enumerate).
RETIRED_ENDPOINT_KEYS = ("sync_plays", "sync_rosters", "sync_team_stats")
RETIRED_ENDPOINT_PATHS = (
    "/api/admin/statpal/sync-plays",
    "/api/admin/statpal/sync-rosters",
    "/api/admin/statpal/sync-team-stats",
)


def _request(*, token=ADMIN_TOKEN):
    """A minimal authenticated ASGI request.

    `_check_admin_secret` accepts the token ONLY via `Authorization: Bearer`
    (queue #252 item 3 removed the `?secret=` path), so the header is the whole
    of the authentication and a test that skipped it would be exercising a
    different code path from the operator's.
    """
    headers = [] if token is None else [(b"authorization", f"Bearer {token}".encode())]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/admin/statpal/status",
            "headers": headers,
            "query_string": b"",
        }
    )


@pytest.fixture()
def _admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    yield ADMIN_TOKEN


@pytest.fixture()
def _payload(_admin_token):
    import asyncio

    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        statpal_status(request=_request(), secret=None)
    )


def _mounted_routes():
    """(method, path) for every route the app actually serves."""
    mounted = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            mounted.add((method.upper(), route.path))
    return mounted


def _advertised(payload):
    """[(key, method, path)] parsed out of the status payload's own strings."""
    parsed = []
    for key, spec in payload["endpoints"].items():
        method, _, path = spec.partition(" ")
        parsed.append((key, method.upper(), path))
    return parsed


class TestEveryAdvertisedEndpointResolves:

    def test_the_payload_advertises_at_least_one_endpoint(self, _payload):
        """The liveness arm.

        Without it, deleting the whole `endpoints` dict would make every
        parametrised assertion below vacuous and this file would go green on a
        status route that describes nothing at all.
        """
        assert len(_payload["endpoints"]) >= 1

    def test_every_advertised_method_and_path_is_mounted(self, _payload):
        """The block's required guard, stated as one assertion over all of them.

        Resolved against `app.routes`, so the only way to advertise a path is to
        serve it. Reported as a set difference rather than per-entry so a failure
        names every stale row at once instead of one per re-run.
        """
        mounted = _mounted_routes()
        advertised = {(m, p) for _key, m, p in _advertised(_payload)}
        assert advertised <= mounted, (
            "the status route advertises endpoints the app does not serve: "
            f"{sorted(advertised - mounted)}"
        )

    def test_the_task_status_route_keeps_its_path_parameter(self, _payload):
        """`GET /api/admin/statpal/task/{task_id}` must match the mounted
        template verbatim, braces included. A payload that spelled it
        `.../task/{taskId}` would be a string an operator cannot use and the set
        comparison above is what catches it — pinned separately because it is the
        one advertised path that is not a literal.
        """
        assert ("GET", "/api/admin/statpal/task/{task_id}") in _mounted_routes()


class TestTheRetiredThreeAreGone:

    @pytest.mark.parametrize("key", RETIRED_ENDPOINT_KEYS)
    def test_the_status_payload_no_longer_advertises_it(self, _payload, key):
        assert key not in _payload["endpoints"], (
            f"{key} was retired with its task, beat and route in #2907; the "
            "status route must not keep telling an operator it exists"
        )

    @pytest.mark.parametrize("path", RETIRED_ENDPOINT_PATHS)
    def test_the_route_itself_is_not_mounted(self, _payload, path):
        """The other half of the block: the payload and the app must agree.

        CERT-2381's finding was precisely a disagreement between them — the entry
        was present and the route was 404 — so proving the entry is gone without
        proving the route is gone would leave the pair untested in the opposite
        direction.
        """
        assert all(p != path for _m, p in _mounted_routes())


class TestTheSurvivingIntegrationIsUntouched:
    """Both arms (gotcha #43): the retirement must not have taken live work.

    StatPal's injuries product is real — 89 events carry `statpal_injuries` in
    `win_probability_sources`, measured 2026-09-09 — and schedules and standings
    both run. A guard that only proved three things vanished would pass equally
    well if all seven had.
    """

    @pytest.mark.parametrize(
        "key", ["sync_schedules", "sync_injuries", "sync_standings", "task_status"]
    )
    def test_the_survivor_is_still_advertised(self, _payload, key):
        assert key in _payload["endpoints"]

    def test_the_mapped_sports_are_still_reported(self, _payload):
        assert _payload["mapped_sports"], (
            "STATPAL_SPORT_MAPPING is what the schedule sync iterates; an empty "
            "list here would mean the retirement reached the mapping"
        )

    def test_the_api_key_flag_is_still_reported(self, _payload):
        assert "api_key_configured" in _payload


class TestTheRouteIsStillProtected:

    def test_an_unauthenticated_read_is_refused(self, _admin_token):
        """The directory names every trigger an operator has; it is not public.

        Asserted because this file's other tests all call the route WITH a token,
        and a suite that only ever authenticates cannot notice auth being removed.
        """
        import asyncio

        with pytest.raises(HTTPException) as excinfo:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                statpal_status(request=_request(token=None), secret=None)
            )
        assert excinfo.value.status_code == 403

    def test_the_deprecated_query_secret_is_not_honoured(self, _admin_token):
        """Queue #252 item 3: `?secret=` is rejected even when it is correct."""
        import asyncio

        with pytest.raises(HTTPException) as excinfo:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                statpal_status(request=_request(token=None), secret=os.environ["ADMIN_TOKEN"])
            )
        assert excinfo.value.status_code == 403


class TestTheHeadersHelperIsNotLying:
    """A control on this file's own scaffolding.

    `_request` builds an ASGI scope by hand. If the header list were malformed,
    `bearer_credentials` would read nothing, every authenticated test above would
    401/403, and the file would fail loudly — but a subtler slip (a header that
    parses but is ignored) would make the auth tests pass for the wrong reason.
    """

    def test_the_authorization_header_round_trips(self):
        assert Headers(scope=_request().scope)["authorization"] == f"Bearer {ADMIN_TOKEN}"
