"""Public v3 SSE contract through the actual singleton/folded generator."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
from time import monotonic
from uuid import UUID, uuid4

import pytest

from app.routes import event_stream as route
from app.utils import live_fanout
from app.utils.live_fanout import Subscription, _ReceivedText, Recovery
from tests.test_dnpl_authority_fanout_10090 import authority
from tests.test_dnpl_authority_hub_10090 import frame
from tests.test_folded_preview_v2_10090 import setup as folded_setup

pytestmark = pytest.mark.asyncio


class Hub:
    def __init__(self, base=None):
        self.subscriptions = {}
        self.base = base
        self.released = []

    async def subscribe(self, channel, *, authority_v3=False):
        sub = Subscription(channel, authority_v3=authority_v3)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub):
        self.released.append(sub)

    def folded_preview_base(self, event_id, **kw):
        return self.base

    async def project_recovery_quote(self, *args):
        return None


class Request:
    query_params = {"preview_protocol": "authority-v3"}

    async def is_disconnected(self):
        return False


async def stream_fixture(monkeypatch, event_id=42, members=None, base=None):
    hub = Hub(base)
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "preview_route_events", lambda: {event_id})
    monkeypatch.setattr(
        route, "latest_frames", lambda *args: asyncio.sleep(0, result=[])
    )
    monkeypatch.setattr(
        route,
        "_current_reconcile",
        lambda *args: asyncio.sleep(
            0,
            result={
                "event_id": event_id,
                "custody_id": "test",
                "removal_rev": base.revision if base else {str(event_id): 10},
            },
        ),
    )
    stream = route._stream(event_id, Request(), members)
    assert (await anext(stream)).startswith("retry:")
    assert (await anext(stream)).startswith("event: open\n")
    await next_event(stream, "reconcile")
    return hub, stream


async def next_event(stream, wanted):
    async with asyncio.timeout(1):
        async for chunk in stream:
            if chunk.startswith(f"event: {wanted}\n"):
                return json.loads(chunk.split("data: ", 1)[1])
            assert not chunk.startswith("event: preview"), (
                "unexpected preview event: " + chunk
            )
    raise AssertionError("stream ended before " + wanted)


def offer(hub, a, value):
    payload = _ReceivedText(json.dumps(value))
    payload.received_at = monotonic()
    payload.authority = a
    hub.subscriptions[f'live:event:{value["event_id"]}'].offer(payload)
    return payload


async def test_singleton_open_precedes_preview_and_charges_open_backpressure(
    monkeypatch,
):
    hub, stream = await stream_fixture(monkeypatch)
    a = authority()
    try:
        payload = offer(hub, a, frame())
        opened = await next_event(stream, "preview_open_v3")
        assert opened["authority"] == a.wire_identity()
        assert opened["members"] == [42]
        assert str(UUID(opened["stream_session"])) == opened["stream_session"]
        assert hub.subscriptions["live:event:42"].authority_v3
        # Simulate time spent suspended at the open yield, without sleeping.
        payload.received_at -= 0.2
        delivered = await next_event(stream, "preview_v3")
        assert delivered["stream_session"] == opened["stream_session"]
        assert delivered["frame"]["p"] == 0.6
        assert delivered["frame"]["preview"]["ttl_ms"] <= 59800
        assert set(delivered) == {
            "protocol",
            "event_id",
            "authority",
            "stream_session",
            "frame",
        }
    finally:
        await stream.aclose()


async def test_plain_legacy_preview_does_not_enable_v3_but_committed_still_flows(
    monkeypatch,
):
    hub, stream = await stream_fixture(monkeypatch)
    try:
        sub = hub.subscriptions["live:event:42"]
        sub.offer(json.dumps(frame()))
        sub.offer(
            json.dumps(
                {
                    "event_id": 42,
                    "p": 0.7,
                    "rev": {"42": 11},
                    "status": "live",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
        result = await next_event(stream, "probability")
        assert result["p"] == 0.7
    finally:
        await stream.aclose()


@pytest.mark.parametrize("cause", ["domain", "recovery", "expiry"])
async def test_domain_change_transport_recovery_and_expiry_reconnect(
    monkeypatch, cause
):
    hub, stream = await stream_fixture(monkeypatch)
    a = authority()
    try:
        payload = offer(hub, a, frame())
        await next_event(stream, "preview_open_v3")
        if cause == "expiry":
            payload.received_at -= 61
        else:
            await next_event(stream, "preview_v3")
            if cause == "domain":
                offer(hub, replace(a, incarnation=2, namespace=uuid4()), frame())
            else:
                hub.subscriptions["live:event:42"].offer(Recovery(1))
        result = await next_event(stream, "reconnect")
        assert (
            result["reason"]
            == {
                "domain": "authority_changed",
                "recovery": "authority_transport_recovery",
                "expiry": "preview_expired_in_transit",
            }[cause]
        )
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()


async def test_folded_preview_keeps_composition_and_binds_public_session(monkeypatch):
    _, base, kalshi, pm, _ = folded_setup()
    hub, stream = await stream_fixture(
        monkeypatch, event_id=1, members=[1, 2, 3], base=base
    )
    a = authority()
    try:
        offer(hub, a, kalshi)
        opened = await next_event(stream, "preview_open_v3")
        assert opened["members"] == [1, 2, 3]
        first = await next_event(stream, "preview_v3")
        assert first["frame"]["preview"]["fold_session"] == opened["stream_session"]
        assert first["frame"]["preview"]["folded_version"] == 2
        offer(hub, a, pm)
        both = await next_event(stream, "preview_v3")
        assert set(both["frame"]["preview"]["origin_authority"]) == {"2", "3"}
        assert both["frame"]["preview"]["base_fold_revision"] == base.revision
        assert both["stream_session"] == opened["stream_session"]
        assert (
            both["frame"]["preview"]["fold_seq"] > first["frame"]["preview"]["fold_seq"]
        )
    finally:
        await stream.aclose()
