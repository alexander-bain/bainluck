"""#1494 — Flow Sentinel: authenticated admin flows + explicit UNKNOWN.

Two false-green rails, one shape: *a check that cannot measure reported a pass.*

1. Queue #252 Item 3 removed ``?secret=`` query-param admin auth. Three flows
   (``chart_density``, ``season_aggregate_linkage``, ``team_identity_dupes``)
   were never migrated, so every admin request they made returned **403** — and
   each mapped that 403 to ``{"checked": 0, "passed": True}``. The scorecard
   counted them as PASSED. Three checks reported clean for weeks while being
   structurally incapable of verifying anything.

2. ``search_gold_set`` scored a hard **503** identically to a legitimate "no
   result". On 2026-07-31 it recorded three 503s from ``/api/events/search`` and
   still reported ``passed: true`` — search was down and its own regression
   guard said green (#1494 criterion 3).

The invariant these tests pin: **checked == 0 can never be a pass**, and no
credential may reach any surface that gets written down.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tasks.flow_sentinel import (
    _admin_headers,
    _redact,
    _run_chart_density,
    _run_season_aggregate_linkage,
    _run_team_identity_dupes,
    _unknown_flow,
    flow_outcome,
    gold_set_transport_errors,
)


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------
class TestFlowOutcome:
    def test_checked_zero_can_never_pass(self):
        """The single load-bearing rule. Zero checks means zero evidence."""
        assert flow_outcome({"checked": 0, "passed": True, "failures": []}) == "unknown"

    def test_explicit_unknown_is_unknown(self):
        assert flow_outcome(_unknown_flow("chart_density", "403")) == "unknown"

    def test_skipped_is_unknown(self):
        assert flow_outcome(
            {"checked": 0, "passed": True, "skipped": True, "failures": []}
        ) == "unknown"

    def test_real_pass_still_passes(self):
        assert flow_outcome({"checked": 12, "passed": True, "failures": []}) == "pass"

    def test_real_failure_still_fails(self):
        assert flow_outcome(
            {"checked": 5, "passed": False, "failures": [{"detail": "x"}]}
        ) == "fail"

    def test_failure_with_zero_checked_is_still_a_failure(self):
        """A crashed flow reports checked=0 with a failure — that is a FAIL
        (it files), not an UNKNOWN (which does not)."""
        assert flow_outcome(
            {"checked": 0, "passed": False, "failures": [{"detail": "crashed"}]}
        ) == "fail"


class TestUnknownFlowShape:
    def test_unknown_never_files_and_never_resolves(self):
        result = _unknown_flow("team_identity_dupes", "403 Forbidden")
        assert result["unknown"] is True
        assert result["checked"] == 0
        assert result["failures"] == []   # nothing to file
        assert result["passed"] is True   # so the failing->file path is untouched
        assert flow_outcome(result) == "unknown"  # ...but it is not counted as a pass


# ---------------------------------------------------------------------------
# Bearer transport
# ---------------------------------------------------------------------------
class TestAdminHeaders:
    def test_bearer_header_built_from_admin_token(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": "tok-abc-123"}):
            assert _admin_headers() == {"Authorization": "Bearer tok-abc-123"}

    def test_no_token_returns_none(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            assert _admin_headers() is None


class TestRedaction:
    def test_token_scrubbed_from_arbitrary_text(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": "super-secret-token"}):
            out = _redact("failed for https://api/x?secret=super-secret-token")
        assert "super-secret-token" not in out
        assert "<redacted>" in out

    def test_secret_query_param_scrubbed_even_without_env(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
            out = _redact("GET /api/admin/db-query?secret=abcdef123&limit=1")
        assert "abcdef123" not in out

    def test_short_token_does_not_scrub_everything(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN": "ab"}):
            assert _redact("stable") == "stable"


# ---------------------------------------------------------------------------
# The three admin flows: deterministic transport fixtures
# ---------------------------------------------------------------------------
def _client_raising(exc):
    client = MagicMock()
    client.get = AsyncMock(side_effect=exc)
    client.post = AsyncMock(side_effect=exc)
    return client


def _http_error(status: int):
    request = httpx.Request("GET", f"https://api.bainluck.com/api/admin/x?secret=LEAK")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"Server error '{status}' for url '{request.url}'",
        request=request, response=response,
    )


ADMIN_FLOWS = [
    ("chart_density", _run_chart_density),
    ("season_aggregate_linkage", _run_season_aggregate_linkage),
    ("team_identity_dupes", _run_team_identity_dupes),
]


@pytest.mark.parametrize("flow_name,runner", ADMIN_FLOWS)
@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
@pytest.mark.asyncio
async def test_admin_flow_auth_and_5xx_are_unknown_never_pass(flow_name, runner, status):
    """The regression that started this: a 403 must NOT count as a pass."""
    with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
        result = await runner(_client_raising(_http_error(status)))
    assert result["flow"] == flow_name
    assert result["checked"] == 0
    assert result["unknown"] is True
    assert flow_outcome(result) == "unknown"


@pytest.mark.parametrize("flow_name,runner", ADMIN_FLOWS)
@pytest.mark.asyncio
async def test_admin_flow_timeout_is_unknown(flow_name, runner):
    with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
        result = await runner(_client_raising(httpx.ReadTimeout("timed out")))
    assert flow_outcome(result) == "unknown"


@pytest.mark.parametrize("flow_name,runner", ADMIN_FLOWS)
@pytest.mark.asyncio
async def test_admin_flow_malformed_json_is_unknown(flow_name, runner):
    with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
        result = await runner(_client_raising(ValueError("not json")))
    assert flow_outcome(result) == "unknown"


@pytest.mark.parametrize("flow_name,runner", ADMIN_FLOWS)
@pytest.mark.asyncio
async def test_admin_flow_without_token_is_unknown(flow_name, runner):
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    with patch.dict(os.environ, {"ADMIN_TOKEN": ""}):
        result = await runner(client)
    assert flow_outcome(result) == "unknown"
    # No request is issued when it could not possibly authenticate.
    client.get.assert_not_awaited()
    client.post.assert_not_awaited()


@pytest.mark.parametrize("flow_name,runner", ADMIN_FLOWS)
@pytest.mark.asyncio
async def test_no_credential_reaches_the_evidence(flow_name, runner):
    """Evidence lands verbatim in a PUBLIC GitHub issue body."""
    with patch.dict(os.environ, {"ADMIN_TOKEN": "LEAK"}):
        result = await runner(_client_raising(_http_error(403)))
    blob = repr(result)
    assert "LEAK" not in blob
    assert "secret=" not in blob or "secret=<redacted>" in blob


# ---------------------------------------------------------------------------
# The three admin flows: Bearer transport + true pass/fail preserved
# ---------------------------------------------------------------------------
class TestBearerTransportAndTruePassFail:
    @pytest.mark.asyncio
    async def test_chart_density_sends_bearer_not_query_secret(self):
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={
                "census": {"chart_density": {"overall_below_bar_pct": 10.0,
                                             "bar_points_per_hour": 1}}
            }),
        ))
        with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
            result = await _run_chart_density(client)

        kwargs = client.get.await_args.kwargs
        args = client.get.await_args.args
        assert kwargs.get("headers") == {"Authorization": "Bearer tok"}
        assert kwargs.get("params") in (None, {})
        assert "secret" not in str(args) + str(kwargs)
        assert result["checked"] == 1
        assert flow_outcome(result) == "pass"

    @pytest.mark.asyncio
    async def test_season_aggregate_pass_and_fail_semantics_intact(self):
        def _client(count):
            c = MagicMock()
            c.post = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"rows": [[count]]}),
            ))
            return c

        with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
            clean = await _run_season_aggregate_linkage(_client(0))
            dirty = await _run_season_aggregate_linkage(_client(7))

        assert flow_outcome(clean) == "pass"
        assert clean["evidence"]["season_aggregate_linked_markets"] == 0
        assert flow_outcome(dirty) == "fail"
        assert len(dirty["failures"]) == 1

    @pytest.mark.asyncio
    async def test_season_aggregate_uses_bearer_header(self):
        c = MagicMock()
        c.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"rows": [[0]]}),
        ))
        with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
            await _run_season_aggregate_linkage(c)
        assert c.post.await_args.kwargs["headers"] == {"Authorization": "Bearer tok"}
        assert "secret" not in str(c.post.await_args.kwargs.get("params") or {})

    @pytest.mark.asyncio
    async def test_team_identity_dupes_bearer_and_pass_fail(self):
        def _client(pairs, awaiting):
            c = MagicMock()
            c.post = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"pairs_remaining": pairs}),
            ))
            c.get = AsyncMock(return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"awaiting": awaiting}),
            ))
            return c

        with patch.dict(os.environ, {"ADMIN_TOKEN": "tok"}):
            clean_client = _client(0, 1)
            clean = await _run_team_identity_dupes(clean_client)
            dirty = await _run_team_identity_dupes(_client(4, 1))

        assert flow_outcome(clean) == "pass"
        assert clean["checked"] == 2
        assert flow_outcome(dirty) == "fail"
        # Bearer on both calls; the dry-run flag still travels as a query param.
        assert clean_client.post.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert clean_client.post.await_args.kwargs["params"] == {"apply": "false"}
        assert clean_client.get.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


# ---------------------------------------------------------------------------
# #1494 criterion 3 — a 5xx gold query is not a legitimate miss
# ---------------------------------------------------------------------------
class TestGoldSetTransportErrors:
    def test_transport_error_detected_on_expected_miss_entry(self):
        """The exact 2026-07-31 shape: three 503s on `expected_found: False`
        entries, which the old scoring counted as correct behaviour."""
        results = [
            {"query": "lebron james", "expected_found": False, "found": False,
             "error": "Server error '503 Service Unavailable'"},
            {"query": "world series", "expected_found": True, "found": True},
        ]
        errs = gold_set_transport_errors(results)
        assert [r["query"] for r in errs] == ["lebron james"]

    def test_clean_run_has_no_transport_errors(self):
        results = [
            {"query": "a", "expected_found": True, "found": True},
            {"query": "b", "expected_found": False, "found": False},
        ]
        assert gold_set_transport_errors(results) == []

    def test_legitimate_miss_is_not_a_transport_error(self):
        """A genuine 'this entity correctly returns nothing' must stay a pass —
        the guard must not flip every expected-miss into a failure."""
        assert gold_set_transport_errors(
            [{"query": "nonexistent", "expected_found": False, "found": False}]
        ) == []


@pytest.mark.asyncio
async def test_search_gold_set_fails_on_5xx():
    """End-to-end: search returning 503 makes the flow FAIL, not pass."""
    from app.tasks import flow_sentinel as fs

    client = MagicMock()
    client.get = AsyncMock(side_effect=_http_error(503))

    with patch.object(fs, "GOLD_SET", [("lebron james", False), ("world series", True)]):
        result = await fs._run_search_gold_set(client, canary=False)

    assert result["passed"] is False
    assert flow_outcome(result) == "fail"
    assert len(result["evidence"]["transport_errors"]) == 2
    # Every failing query is named so the issue body is actionable.
    assert {f["query"] for f in result["failures"]} == {"lebron james", "world series"}


@pytest.mark.asyncio
async def test_search_gold_set_passes_when_healthy():
    """Adjacent direction: the healthy path is unchanged."""
    from app.tasks import flow_sentinel as fs

    payload = {"results": [{"id": 1}], "event_concepts": [], "futures": [],
               "futures_families": []}
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(
        raise_for_status=MagicMock(), json=MagicMock(return_value=payload),
    ))

    with patch.object(fs, "GOLD_SET", [("world series", True)]):
        result = await fs._run_search_gold_set(client, canary=False)

    assert result["passed"] is True
    assert result["evidence"]["transport_errors"] == []
    assert flow_outcome(result) == "pass"
