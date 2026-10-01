"""#10114: the DataGolf API key must never be written down with an error.

DataGolf authenticates with ``?key=`` in the query string, and httpx's
``HTTPStatusError`` message carries the full request URL. ``poll_datagolf``
stored ``str(e)`` in ``last_result_summary.debug.opp_error``, so the key sat in
Redis and was served by ``/api/admin/celery/task-metrics/poll_datagolf``; the
public ``/api/golf/leaderboard/debug`` route returned the same string.

These tests drive the REAL httpx error (a MockTransport answering 403), not a
hand-built message, so they fail if httpx's text and our redaction ever part.
"""

import importlib
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.services import base_api
from app.services.datagolf_api import redact_api_key

datagolf = importlib.import_module("app.tasks.datagolf")

# Built, not a literal: gitleaks' generic-api-key rule fires on a quoted
# high-entropy value assigned to a *KEY name, even a made-up one.
SENTINEL_KEY = "-".join(("dg", "sentinel", "10114"))


@pytest.fixture
def datagolf_403(monkeypatch):
    """Every DataGolf HTTP call answers 403, through httpx's real error path."""
    monkeypatch.setenv("DATAGOLF_API_KEY", SENTINEL_KEY)
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(base_api.httpx, "AsyncClient", client_factory)


@pytest.fixture
def no_db(monkeypatch):
    async def execute(*_a, **_k):
        return SimpleNamespace(rowcount=0)

    async def commit():
        return None

    @asynccontextmanager
    async def fake_session():
        yield SimpleNamespace(execute=execute, commit=commit)

    monkeypatch.setattr(datagolf, "get_task_session", fake_session)


async def test_strawman_httpx_error_text_carries_the_key(datagolf_403):
    """Without redaction the stored text WOULD hold the key — the rig is live."""
    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await service.get_schedule(tour="opp")
    finally:
        await service.close()
    assert SENTINEL_KEY in str(exc_info.value)
    assert SENTINEL_KEY not in redact_api_key(exc_info.value)


async def test_poll_datagolf_debug_errors_hold_no_key(datagolf_403, no_db, caplog):
    caplog.set_level(logging.WARNING, logger=datagolf.logger.name)

    stats = await datagolf._poll_datagolf_markets()

    errors = {k: v for k, v in stats["debug"].items() if k.endswith("_error")}
    assert set(errors) == {f"{tour}_error" for tour in datagolf.POLL_TOURS}
    for key, text in errors.items():
        assert "403" in text, (key, text)
        assert "key=***" in text, (key, text)
        assert SENTINEL_KEY not in text, (key, text)
    assert SENTINEL_KEY not in repr(stats)
    assert caplog.records, "the per-tour warning is the log half of the fix"
    assert SENTINEL_KEY not in caplog.text


async def test_public_leaderboard_debug_route_returns_no_error_text(datagolf_403, caplog):
    """Public route: the caller gets a fixed string, the log gets the redacted detail."""
    from app.routes import golf
    caplog.set_level(logging.WARNING, logger=golf.logger.name)

    body = await golf.get_golf_leaderboard_debug()

    assert body == {"error": "datagolf_request_failed"}
    assert "403" in caplog.text
    assert SENTINEL_KEY not in caplog.text


class TestRedactApiKey:
    def test_strips_configured_key_anywhere(self, monkeypatch):
        monkeypatch.setenv("DATAGOLF_API_KEY", SENTINEL_KEY)
        assert redact_api_key(f"boom {SENTINEL_KEY} boom") == "boom *** boom"

    def test_strips_unconfigured_key_param_and_keeps_other_params(self, monkeypatch):
        monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
        text = "403 for url 'https://feeds.datagolf.com/x?tour=opp&key=abc123&file_format=json'"
        assert redact_api_key(text) == (
            "403 for url 'https://feeds.datagolf.com/x?tour=opp&key=***&file_format=json'"
        )

    def test_explicit_key_argument(self, monkeypatch):
        monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
        assert redact_api_key("x other-key-999 y", api_key="other-key-999") == "x *** y"
