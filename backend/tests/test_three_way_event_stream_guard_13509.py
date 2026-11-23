"""#13509 — live event streams omit ``p`` on three-way draw games while keeping two-way games unchanged."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import event_stream as route
from app.utils import live_fanout
from tests._event_stream_legacy_view import install_legacy_view


@pytest.fixture(autouse=True)
def _legacy_wire_view(monkeypatch):
    """Stub connect/recovery DB coverage while leaving ``route._stream`` unwrapped."""
    install_legacy_view(monkeypatch, drop_reconcile=False)


class _Request:
    def __init__(self, preview_protocol: str | None = None):
        self.query_params = (
            {"preview_protocol": preview_protocol} if preview_protocol else {}
        )

    async def is_disconnected(self) -> bool:
        return False


class _ScalarResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self) -> list:
        return list(self._rows)


class _FakeSession:
    def __init__(self, events: list):
        self._events = events

    async def execute(self, _stmt):
        return _ScalarResult(self._events)


class _SessionMaker:
    def __init__(self, events: list):
        self._events = events
        self.opened = 0
        self.closed = 0

    def __call__(self):
        return self

    async def __aenter__(self):
        self.opened += 1
        return _FakeSession(self._events)

    async def __aexit__(self, *args):
        self.closed += 1
        return False


class _Hub:
    def __init__(self):
        self.subscriptions: dict[str, live_fanout.Subscription] = {}
        self.released: list[str] = []
        self.projected_calls = 0

    async def subscribe(self, channel: str):
        sub = live_fanout.Subscription(channel)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub: live_fanout.Subscription) -> None:
        self.released.append(sub.channel)

    async def project_folded_quote(self, event_id: int, frame: dict):
        self.projected_calls += 1
        return {"event_id": event_id, "hero_probability": frame.get("p")}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wire_frame(event_id: int, rev: int, p: float, *, status: str = "live") -> dict:
    return {
        "event_id": event_id,
        "p": p,
        "source": "polymarket",
        "source_value": p,
        "rev": {str(event_id): rev},
        "updated_at": _now_iso(),
        "status": status,
        "source_snapshot": {
            "event_id": event_id,
            "rev": {str(event_id): rev},
            "win_probability_sources": {
                "polymarket": {"value": p, "updated_at": _now_iso()}
            },
        },
    }


def _parse_sse(chunk: str) -> tuple[str, dict] | None:
    event_name = None
    data_raw = None
    for line in chunk.splitlines():
        if line.startswith("event: "):
            event_name = line[len("event: ") :].strip()
        elif line.startswith("data: "):
            data_raw = line[len("data: ") :].strip()
    if event_name is None or data_raw is None:
        return None
    return event_name, json.loads(data_raw)


async def _advance_to_open(iterator) -> None:
    """Consume retry + open SSE chunks so hub subscriptions are registered."""
    for _ in range(5):
        chunk = await asyncio.wait_for(anext(iterator), timeout=1.0)
        if chunk.startswith("event: open\n"):
            return
    raise AssertionError("Stream did not emit event: open")


async def _collect_until(
    iterator,
    *,
    stop_on_events: int | None = None,
    stop_on_closed: bool = False,
) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []

    async def _drain():
        async for chunk in iterator:
            item = _parse_sse(chunk)
            if item is None:
                continue
            parsed.append(item)
            if stop_on_closed and item[0] == "closed":
                break
            if (
                stop_on_events is not None
                and sum(1 for name, _ in parsed if name == "probability")
                >= stop_on_events
            ):
                break

    try:
        await asyncio.wait_for(_drain(), timeout=2.0)
    finally:
        await iterator.aclose()
    return parsed


def _setup_stream_deps(monkeypatch, *, events: list, contributor_ids: list[int], replay: list, hub: _Hub):
    maker = _SessionMaker(events)
    monkeypatch.setattr(route, "async_session_maker", maker)
    monkeypatch.setattr(route, "_event_status", AsyncMock(return_value="live"))
    monkeypatch.setattr(route, "_fold_stream_ids", AsyncMock(return_value=contributor_ids))
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=replay))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)
    monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 60.0)
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    return maker


@pytest.mark.asyncio
async def test_three_way_soccer_stream_strips_p_on_replay_and_live_ticks(monkeypatch):
    event_id = 15344466
    soccer_row = SimpleNamespace(
        id=event_id,
        sport=SimpleNamespace(key="soccer_greece_super_league"),
        win_probability_sources={
            "betting": {
                "value": 0.2634,
                "away_value": 0.2820,
                "draw_value": 0.4546,
            }
        },
    )
    replay_frame = _wire_frame(event_id, 41, 0.256, status="live")
    live_frame = _wire_frame(event_id, 42, 0.249, status="live")
    terminal_frame = _wire_frame(event_id, 43, 0.01, status="completed")

    hub = _Hub()
    maker = _setup_stream_deps(
        monkeypatch,
        events=[soccer_row],
        contributor_ids=[event_id],
        replay=[(event_id, json.dumps(replay_frame))],
        hub=hub,
    )

    response = await route.stream_event(event_id, _Request())
    assert (maker.opened, maker.closed) == (1, 1)

    iterator = response.body_iterator
    try:
        await _advance_to_open(iterator)
        sub = hub.subscriptions[f"live:event:{event_id}"]
        sub.offer(json.dumps(live_frame))
        sub.offer(json.dumps(terminal_frame))
        events = await _collect_until(iterator, stop_on_closed=True)
    except Exception:
        await iterator.aclose()
        raise

    prob_frames = [payload for name, payload in events if name == "probability"]
    assert len(prob_frames) == 3
    assert [payload["rev"] for payload in prob_frames] == [
        {str(event_id): 41},
        {str(event_id): 42},
        {str(event_id): 43},
    ]
    for payload in prob_frames:
        assert payload["event_id"] == event_id
        assert payload["p"] is None
        assert "source_snapshot" not in payload
        assert payload["updated_at"]
    assert prob_frames[-1]["status"] == "completed"
    assert any(name == "closed" for name, _ in events)


@pytest.mark.asyncio
async def test_two_way_game_stream_unchanged(monkeypatch):
    event_id = 15352464
    two_way_row = SimpleNamespace(
        id=event_id,
        sport=SimpleNamespace(key="basketball_nba"),
        win_probability_sources={"kalshi": {"value": 0.62}},
    )
    replay_frame = _wire_frame(event_id, 10, 0.62, status="live")
    live_frame = _wire_frame(event_id, 11, 0.64, status="live")

    hub = _Hub()
    maker = _setup_stream_deps(
        monkeypatch,
        events=[two_way_row],
        contributor_ids=[event_id],
        replay=[(event_id, json.dumps(replay_frame))],
        hub=hub,
    )

    response = await route.stream_event(event_id, _Request())
    assert (maker.opened, maker.closed) == (1, 1)

    iterator = response.body_iterator
    try:
        await _advance_to_open(iterator)
        hub.subscriptions[f"live:event:{event_id}"].offer(json.dumps(live_frame))
        events = await _collect_until(iterator, stop_on_events=2)
    except Exception:
        await iterator.aclose()
        raise

    prob_frames = [payload for name, payload in events if name == "probability"]
    assert [payload["p"] for payload in prob_frames] == [0.62, 0.64]
    assert all("source_snapshot" in payload for payload in prob_frames)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sport_key,sources,expected",
    [
        ("icehockey_nhl", {"betting": {"value": 0.35, "away_value": 0.40, "draw_value": 0.25}}, True),
        ("soccer_epl", {}, True),
        ("basketball_nba", {"kalshi": {"value": 0.62}}, False),
    ],
)
async def test_draw_guard_covers_non_soccer_draw_value_and_empty_soccer_sources(
    sport_key: str, sources: dict, expected: bool
):
    row = SimpleNamespace(
        id=1,
        sport=SimpleNamespace(key=sport_key),
        win_probability_sources=sources,
    )
    db = _FakeSession([row])
    assert await route._event_has_draw_chance(db, 1, [1]) is expected


@pytest.mark.asyncio
async def test_folded_three_way_stream_suppresses_folded_quote_and_preview(monkeypatch):
    canon_id, twin_id = 10, 20
    soccer_row = SimpleNamespace(
        id=canon_id,
        sport=SimpleNamespace(key="soccer_usa_mls"),
        win_probability_sources={},
    )
    hub = _Hub()
    _setup_stream_deps(
        monkeypatch,
        events=[soccer_row],
        contributor_ids=[canon_id, twin_id],
        replay=[],
        hub=hub,
    )
    monkeypatch.setattr(route, "preview_route_events", lambda: {canon_id})

    response = await route.stream_event(canon_id, _Request(preview_protocol="folded-v1"))

    iterator = response.body_iterator
    try:
        await _advance_to_open(iterator)
        hub.subscriptions[f"live:event:{canon_id}"].offer(
            json.dumps(
                {
                    "event_id": canon_id,
                    "updated_at": _now_iso(),
                    "preview": {"kind": "blend", "p": 0.51, "epoch": 1, "seq": 1},
                }
            )
        )
        hub.subscriptions[f"live:event:{canon_id}"].offer(
            json.dumps(_wire_frame(canon_id, 5, 0.51, status="live"))
        )
        hub.subscriptions[f"live:event:{twin_id}"].offer(
            json.dumps(_wire_frame(twin_id, 7, 0.48, status="live"))
        )
        events = await _collect_until(iterator, stop_on_events=2)
    except Exception:
        await iterator.aclose()
        raise

    event_names = [name for name, _ in events]
    prob_frames = [payload for name, payload in events if name == "probability"]

    assert len(prob_frames) == 2
    assert all(payload["p"] is None for payload in prob_frames)
    assert all(not payload.get("folded_quote_pending") for payload in prob_frames)
    assert "folded_probability" not in event_names
    assert "preview" not in event_names
    assert hub.projected_calls == 0
