"""Guard for the best-effort server-side GA4 emitter (#209 Item 4 rider).

It must NEVER raise or block the caller, and must no-op (returning False) when the
Measurement Protocol secret is unset — logging loudly rather than silently
swallowing the event (the GITHUB_TOKEN-unset lesson).
"""
import asyncio

import pytest

from app.utils.measurement import emit_ga4_event


def test_no_secret_is_noop_not_error(monkeypatch, caplog):
    monkeypatch.delenv("GA4_MP_API_SECRET", raising=False)
    import logging

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            emit_ga4_event("push_sent", {"payload_id": "digest-20260716", "recipients": 3})
        )
    assert result is False
    assert any("GA4_MP_API_SECRET unset" in r.message for r in caplog.records)


def test_network_failure_is_swallowed(monkeypatch):
    """With a secret set but the endpoint unreachable, it returns False, never
    raises — the send task must survive a slow/failing GA endpoint."""
    monkeypatch.setenv("GA4_MP_API_SECRET", "test-secret")

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("network down")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _BoomClient)
    result = asyncio.run(emit_ga4_event("push_sent", {"payload_id": "x"}, timeout=0.1))
    assert result is False
