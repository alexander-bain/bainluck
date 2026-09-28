"""#837 — a folded event's live stream carries its twins' venue frames.

THE SHIP, IN A READER'S WORDS: on a held soccer page whose Kalshi and Polymarket
prices live on a second row for the same game, the phone hears each venue move
when it happens instead of waiting for its next poll.

THE SPECIMEN. Necaxa v América, canonical 15316464, twin 15312629, 2026-09-28
04:42:22–04:43:07Z (Codex's simultaneous 45 s SSE sample). Detail folded both
rows (`blend_fold_revision` {15316464: 692, 15312629: 1103}) and its hero moved
with the twin. The canonical's stream carried ONE probability frame (betting);
the twin's carried SIX (Polymarket x5, Kalshi x1). `routes/event_stream.py`
subscribed `event_channel(event_id)` and nothing else.

WHAT IS FORWARDED, AND WHY IT IS REWRITTEN. Both installed clients drop a frame
whose `event_id` is not the page's, so the twin frame is re-addressed to the
canonical. It keeps the twin's `rev`, which orders as incomparable against the
folded hero's two-row vector — the clients' existing "re-read detail" path
(#9051) — and loses its `status`, because iOS writes a frame's status onto the
page. A twin frame on a source the canonical already holds cannot move the
gap-fill fold, so it is not forwarded at all.

🔴 THE MUTANT: drop the twin subscriptions from `_stream` (the deployed shape at
abc47645) and `test_a_twin_venue_frame_reaches_the_canonical_stream` fails.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.live_push import build_frame

CANON = 15316464
TWIN = 15312629
STRANGER = 15399999


def _frame(event_id, source="polymarket", status="live", rev=1100, p=0.045):
    return build_frame(
        event_id=event_id,
        probability=p,
        source=source,
        source_value=p,
        updated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        rev=rev,
    )


class ChannelPubSub:
    """Yields each scripted message only once its channel is subscribed.

    The hub's reader starts on the FIRST subscribe, before the route has joined
    the twin's channel; a fake that popped messages regardless would hand the
    twin's frame to nobody and make the arm below pass or fail on scheduling.
    """

    def __init__(self, messages):
        self._messages = list(messages)
        self.subscribed = []
        self.unsubscribed = []

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        pass

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        for i, message in enumerate(self._messages):
            if message["channel"] in self.subscribed:
                return self._messages.pop(i)
        await asyncio.sleep(min(timeout or 0.01, 0.01))
        return None


class _Conn:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        pass


class _Request:
    def __init__(self, passes):
        self._left = passes

    async def is_disconnected(self):
        self._left -= 1
        return self._left < 0


def _message(event_id, frame):
    return {
        "type": "message",
        "channel": f"live:event:{event_id}",
        "data": json.dumps(frame),
    }


def _fold(twins=(TWIN,), movable=("kalshi", "polymarket")):
    from app.routes.event_stream import StreamFold

    return StreamFold(twins=frozenset(twins), movable=frozenset(movable))


async def _collect(monkeypatch, messages, fold, passes=40):
    from app.routes import event_stream as mod
    from app.utils.live_fanout import fanout, reset_fanout

    pubsub = ChannelPubSub(messages)
    monkeypatch.setattr(
        "app.tasks.redis_state.get_async_redis_client", lambda: _Conn(pubsub)
    )
    monkeypatch.setattr(mod, "FRAME_WAIT_S", 0.05)
    try:
        chunks = [c async for c in mod._stream(CANON, _Request(passes), fold)]
    finally:
        pubsub.hub_subscribers = fanout().subscriber_count
        await reset_fanout()
    return chunks, pubsub


def _probability_frames(chunks):
    out = []
    lines = "".join(chunks).split("\n")
    for i, line in enumerate(lines):
        if line == "event: probability":
            out.append(json.loads(lines[i + 1][len("data: "):]))
    return out


class TestTheStreamJoinsEveryFoldMember:
    async def test_subscribes_the_canonical_and_each_twin_and_leaves_none(
        self, monkeypatch
    ):
        _, pubsub = await _collect(monkeypatch, [], _fold())
        assert pubsub.subscribed == [
            f"live:event:{CANON}",
            f"live:event:{TWIN}",
        ]
        assert pubsub.hub_subscribers == 0

    async def test_an_unfolded_event_joins_only_its_own_channel(
        self, monkeypatch
    ):
        """The default fold is today's stream, byte for byte in what it joins."""
        from app.routes.event_stream import StreamFold

        _, pubsub = await _collect(monkeypatch, [], StreamFold())
        assert pubsub.subscribed == [f"live:event:{CANON}"]


class TestWhatAFoldedStreamForwards:
    async def test_a_twin_venue_frame_reaches_the_canonical_stream(
        self, monkeypatch
    ):
        chunks, _ = await _collect(
            monkeypatch, [_message(TWIN, _frame(TWIN, rev=1100))], _fold()
        )
        frames = _probability_frames(chunks)
        assert len(frames) == 1, "".join(chunks)
        forwarded = frames[0]
        # Re-addressed, or both clients drop it on the event-id guard.
        assert forwarded["event_id"] == CANON
        # Still dated by the TWIN row: incomparable to the folded vector, so
        # the client re-reads detail instead of adopting the twin's raw `p`.
        assert forwarded["rev"] == {str(TWIN): 1100}
        assert forwarded["folded_from"] == TWIN
        assert forwarded["source"] == "polymarket"
        # The twin's status never reaches the canonical's page.
        assert forwarded["status"] is None

    async def test_the_canonicals_own_frame_is_forwarded_untouched(
        self, monkeypatch
    ):
        own = _frame(CANON, source="betting", rev=692)
        chunks, _ = await _collect(monkeypatch, [_message(CANON, own)], _fold())
        assert _probability_frames(chunks) == [own]

    async def test_a_twin_frame_on_a_source_the_canonical_holds_is_dropped(
        self, monkeypatch
    ):
        """Gap-fill: the canonical's betting reading IS the fold's betting
        reading, so the twin's cannot move the hero and costs a refetch."""
        chunks, _ = await _collect(
            monkeypatch,
            [_message(TWIN, _frame(TWIN, source="betting"))],
            _fold(movable=("kalshi", "polymarket")),
        )
        assert _probability_frames(chunks) == []

    async def test_a_frame_for_a_row_outside_the_fold_is_dropped(
        self, monkeypatch
    ):
        from app.routes.event_stream import _as_canonical_frame

        assert _as_canonical_frame(_frame(STRANGER), CANON, _fold()) is None

    async def test_a_twin_that_left_live_does_not_close_the_canonical_stream(
        self, monkeypatch
    ):
        chunks, _ = await _collect(
            monkeypatch,
            [
                _message(TWIN, _frame(TWIN, status="completed", rev=1101)),
                _message(TWIN, _frame(TWIN, source="kalshi", rev=1102)),
            ],
            _fold(),
        )
        out = "".join(chunks)
        assert "event: closed" not in out
        assert [f["rev"] for f in _probability_frames(chunks)] == [
            {str(TWIN): 1101},
            {str(TWIN): 1102},
        ]

    async def test_the_canonical_leaving_live_still_closes_it(
        self, monkeypatch
    ):
        chunks, _ = await _collect(
            monkeypatch,
            [_message(CANON, _frame(CANON, status="completed"))],
            _fold(),
        )
        assert "event: closed" in "".join(chunks)


class TestTheConnectLookup:
    async def test_the_fold_is_read_in_the_one_connect_session(
        self, monkeypatch
    ):
        from app.routes import event_stream as mod
        from tests.test_live_push import TrackingSessionMaker

        maker = TrackingSessionMaker()
        monkeypatch.setattr(mod, "async_session_maker", maker)
        seen = []

        async def _live(_session, _event_id):
            return "live"

        async def _fold_of(session, event_id):
            seen.append(event_id)
            return _fold()

        monkeypatch.setattr(mod, "_event_status", _live)
        monkeypatch.setattr(mod, "_stream_fold", _fold_of)
        await mod.stream_event(CANON, _Request(0))
        assert seen == [CANON]
        assert (maker.opened, maker.closed) == (1, 1)

    async def test_a_non_live_event_reads_no_fold(self, monkeypatch):
        from fastapi import HTTPException

        from app.routes import event_stream as mod
        from tests.test_live_push import TrackingSessionMaker

        monkeypatch.setattr(mod, "async_session_maker", TrackingSessionMaker())

        async def _scheduled(_session, _event_id):
            return "scheduled"

        async def _fold_of(session, event_id):
            raise AssertionError("fold read for a stream that is refused")

        monkeypatch.setattr(mod, "_event_status", _scheduled)
        monkeypatch.setattr(mod, "_stream_fold", _fold_of)
        with pytest.raises(HTTPException) as refused:
            await mod.stream_event(CANON, _Request(0))
        assert refused.value.status_code == 409

    async def test_a_failed_fold_lookup_still_streams_the_canonical(
        self, monkeypatch, caplog
    ):
        from app.routes import event_stream as mod
        from tests.test_live_push import TrackingSessionMaker

        monkeypatch.setattr(mod, "async_session_maker", TrackingSessionMaker())

        async def _live(_session, _event_id):
            return "live"

        async def _broken(session, event_id):
            raise RuntimeError("db went away")

        captured = {}

        def _capture(event_id, request, fold):
            captured["fold"] = fold

            async def _empty():
                if False:
                    yield ""

            return _empty()

        monkeypatch.setattr(mod, "_event_status", _live)
        monkeypatch.setattr(mod, "_stream_fold", _broken)
        monkeypatch.setattr(mod, "_stream", _capture)
        with caplog.at_level("WARNING"):
            await mod.stream_event(CANON, _Request(0))
        assert captured["fold"] == mod.StreamFold()
        assert "fold lookup failed" in caplog.text


class TestStreamFoldReadsWhatDetailFolds:
    async def test_members_come_from_the_detail_routes_two_fold_reads(
        self, monkeypatch
    ):
        """Absorbed rows AND oriented tagged twins, from the same helpers the
        detail route hands its blend fold — and the movable set is every
        weighted source the canonical does not already hold."""
        from app.routes import event_stream as mod
        from app.utils import proven_duplicates, serve_fold_absorbed
        from app.utils.aggregation import SOURCE_WEIGHTS

        event = SimpleNamespace(
            id=CANON,
            win_probability_sources={
                "betting": {"value": 0.04, "updated_at": "2026-09-28T04:42:50Z"},
                "kalshi": None,  # a present key with no reading holds nothing
                "statpal_plays": [],
            },
        )
        absorbed = [SimpleNamespace(id=TWIN)]

        async def _absorbed(db, ev):
            assert ev is event
            return absorbed

        async def _series_ids(db, canonical_id, rows):
            assert (canonical_id, rows) == (CANON, absorbed)
            return [CANON, TWIN]

        monkeypatch.setattr(serve_fold_absorbed, "serve_fold_absorbed_rows", _absorbed)
        monkeypatch.setattr(
            proven_duplicates, "folded_series_event_ids", _series_ids
        )

        class _Db:
            async def execute(self, _stmt):
                return SimpleNamespace(scalar_one_or_none=lambda: event)

        fold = await mod._stream_fold(_Db(), CANON)
        assert fold.twins == frozenset({TWIN})
        assert fold.movable == frozenset(SOURCE_WEIGHTS) - {"betting"}
        assert "kalshi" in fold.movable and "polymarket" in fold.movable

    async def test_an_event_with_no_twins_folds_nothing(self, monkeypatch):
        from app.routes import event_stream as mod
        from app.utils import proven_duplicates, serve_fold_absorbed

        async def _absorbed(db, ev):
            return []

        async def _series_ids(db, canonical_id, rows):
            return [canonical_id]

        monkeypatch.setattr(serve_fold_absorbed, "serve_fold_absorbed_rows", _absorbed)
        monkeypatch.setattr(
            proven_duplicates, "folded_series_event_ids", _series_ids
        )

        class _Db:
            async def execute(self, _stmt):
                return SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(
                        id=CANON, win_probability_sources={}
                    )
                )

        assert await mod._stream_fold(_Db(), CANON) == mod.StreamFold()

    def test_detail_hands_its_blend_fold_the_same_absorbed_rows(self):
        """If detail ever folds from a different member set, this names it."""
        from app.routes import events

        source = inspect.getsource(events)
        assert "absorbed = await serve_fold_absorbed_rows(db, event)" in source
        assert (
            "folded_probability_sources_with_revision(db, event, absorbed)"
            in source
        )
