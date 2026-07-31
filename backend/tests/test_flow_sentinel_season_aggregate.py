"""Queue #246 Item 3 / #1220 — the standing regression guard: a season-aggregate
market (Head-to-Head Win Total / Season Series Winner / …) carrying an event_id is
a mislink. The Flow Sentinel asserts the census stays 0 via admin db-query, and a
missing/broken admin path is SKIPPED (never a cry-wolf file)."""
import pytest

from app.tasks.flow_sentinel import _run_season_aggregate_linkage


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal httpx.AsyncClient stand-in capturing the db-query call."""

    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc
        self.last_call = None

    # #1494: the flow now authenticates with `Authorization: Bearer` instead of
    # the removed `?secret=` query param, so the stand-in accepts headers.
    async def post(self, path, params=None, json=None, headers=None):
        self.last_call = {"path": path, "params": params, "json": json,
                          "headers": headers}
        if self._raise:
            raise self._raise
        return _FakeResp(self._payload)


@pytest.mark.asyncio
async def test_zero_linked_passes(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    client = _FakeClient(payload={"columns": ["n"], "rows": [[0]]})
    result = await _run_season_aggregate_linkage(client)
    assert result["passed"] is True
    assert result["failures"] == []
    assert result["evidence"]["season_aggregate_linked_markets"] == 0
    # asserts the guard actually queried the season-agg predicate
    assert "Head-to-Head Win Total" in client.last_call["json"]["sql"]
    assert client.last_call["path"] == "/api/admin/db-query"
    # #1494: Bearer transport, and no credential in the URL/query string.
    assert client.last_call["headers"] == {"Authorization": "Bearer secret"}
    assert "secret" not in str(client.last_call["params"] or {})


@pytest.mark.asyncio
async def test_nonzero_linked_fails_and_files(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    client = _FakeClient(payload={"columns": ["n"], "rows": [[7]]})
    result = await _run_season_aggregate_linkage(client)
    assert result["passed"] is False
    assert len(result["failures"]) == 1
    assert "7 season-aggregate" in result["failures"][0]["detail"]
    assert result["evidence"]["season_aggregate_linked_markets"] == 7


@pytest.mark.asyncio
async def test_missing_admin_token_is_skipped(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    result = await _run_season_aggregate_linkage(_FakeClient())
    assert result["passed"] is True
    assert result["skipped"] is True
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_broken_query_is_skipped_not_filed(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    client = _FakeClient(raise_exc=RuntimeError("db-query 500"))
    result = await _run_season_aggregate_linkage(client)
    assert result["passed"] is True  # cry-wolf discipline: don't file on our own break
    assert result["skipped"] is True
    assert "db-query failed" in result["evidence"]["reason"]
