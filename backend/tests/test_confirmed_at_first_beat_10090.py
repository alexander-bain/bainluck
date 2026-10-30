"""#10090 decision J — the FIRST heartbeat after a stream opens.

SHIP. A reader who opens a live game page sees a "last updated" status that
is fresh from the first second, instead of briefly showing a minutes-old
confirmation (Alex, 12:35 PM PT 10/30: "There was a long delay when I first
launched the page before I saw my first update").

SPECIMEN (speed, production, 19:25:29Z, event 15335141): +1.09 s the first
heartbeat carried ``confirmed_at`` 385.1 s old, the next one 1.3 s later
2.3 s old. A stream on the same process had last read the event about 19:19:05
and left. Its cache entry was still there six minutes later, and ``peek``
returned it while this stream's own re-read was in flight.

THE RULE UNDER TEST. The process cache gives a value only when EVERY member's
last SUCCESSFUL read is younger than ``READ_FRESH_S``. A failed read keeps what
was known (lane1 S2) but does not make it current, and a member not read yet
blanks the value instead of being dropped from ``combine``. The replay still
paints first (lane1 R3), and the fresh value still goes out once its read lands.
"""

import asyncio
import json
import time

import pytest

from app.utils import confirmed_at as ca
from app.utils.confirmed_at import ConfirmedReads

E, F = 7, 8
STALE_S = 385.0


def _entry(c=None, h=None, w=None):
    return json.dumps({"c": c, "h": h, "w": w})


def _ms(wall):
    return int(wall * 1000)


class _Mono:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class TestTheCacheNeverServesAStaleEntry:
    @pytest.mark.asyncio
    async def test_an_entry_left_by_a_stream_minutes_ago_is_not_current(self):
        wall = time.time()
        mono = _Mono()
        gate = asyncio.Event()
        reads_seen = []

        async def fetch(ids):
            reads_seen.append(list(ids))
            if len(reads_seen) == 1:
                return {eid: [_entry(c=_ms(wall - STALE_S), w=_ms(wall - STALE_S))] for eid in ids}
            await gate.wait()
            return {eid: [_entry(c=_ms(wall - 1), w=_ms(wall - 1))] for eid in ids}

        reads = ConfirmedReads(fetch, mono=mono, wall=lambda: wall)
        await reads.current([E], 0.1)  # the earlier stream's last read
        mono.now += STALE_S  # it left; nobody read E for six minutes

        # The new stream's first peek: the re-read is in flight.
        assert reads.peek([E]) is None
        await asyncio.sleep(0)
        assert len(reads_seen) == 2
        assert reads.peek([E]) is None
        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert reads.peek([E]) == _ms(wall - 1) / 1000

    @pytest.mark.asyncio
    async def test_a_failed_re_read_keeps_the_entry_but_does_not_make_it_current(self):
        wall = time.time()
        mono = _Mono()
        up = {"ok": True}

        async def fetch(ids):
            if not up["ok"]:
                return None
            return {eid: [_entry(c=_ms(wall - STALE_S), w=_ms(wall - STALE_S))] for eid in ids}

        reads = ConfirmedReads(fetch, mono=mono, wall=lambda: wall)
        assert await reads.current([E], 0.1) == _ms(wall - STALE_S) / 1000
        mono.now += STALE_S
        up["ok"] = False
        assert await reads.current([E], 0.1) is None
        # lane1 S2 is unchanged: the failure counts as an attempt.
        assert reads._entries[E][0] == mono.now

    @pytest.mark.asyncio
    async def test_a_member_not_yet_read_blanks_the_value(self):
        """Combining only the members read so far could miss another member's
        live hold, and so overstate."""
        wall = time.time()
        mono = _Mono()
        gate = asyncio.Event()

        async def fetch(ids):
            if F in ids:
                await gate.wait()
                return {eid: [_entry(c=_ms(wall - 9), h=_ms(wall - 9), w=_ms(wall))] for eid in ids}
            return {eid: [_entry(c=_ms(wall - 1), w=_ms(wall))] for eid in ids}

        reads = ConfirmedReads(fetch, mono=mono, wall=lambda: wall)
        await reads.current([E], 0.1)
        assert reads.peek([E, F]) is None  # F's read is in flight
        gate.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert reads.peek([E, F]) == _ms(wall - 9) / 1000  # F's hold caps E

    @pytest.mark.asyncio
    async def test_a_steady_stream_inside_the_bound_keeps_its_value(self):
        wall = time.time()
        mono = _Mono()

        async def fetch(ids):
            return {eid: [_entry(c=_ms(wall - 1), w=_ms(wall))] for eid in ids}

        reads = ConfirmedReads(fetch, mono=mono, wall=lambda: wall)
        await reads.current([E], 0.1)
        # Read just under a second ago, then an idle stream pass
        # (`event_stream.FRAME_WAIT_S`): stale for the TTL, so this peek
        # starts a re-read, but a value that old is still current.
        from app.routes.event_stream import FRAME_WAIT_S

        mono.now += ca.READ_TTL_S - 0.01 + FRAME_WAIT_S
        assert reads.peek([E]) == _ms(wall - 1) / 1000


class TestTheStreamsFirstHeartbeat:
    @pytest.mark.asyncio
    async def test_a_stream_opening_on_a_stale_entry_never_sends_it(self, monkeypatch):
        """The specimen, end to end on the real route and hub: the cache holds
        a 385 s-old entry and this stream's re-read takes 0.2 s."""
        from app.routes import event_stream as mod
        from tests._event_stream_legacy_view import install_legacy_view
        from tests.test_live_push import FakePubSub, _collect

        install_legacy_view(monkeypatch)
        wall = time.time()
        offset = {"s": 0.0}
        reads_seen = []
        stale_ms, fresh_ms = _ms(wall - STALE_S), _ms(wall - 1)

        async def fetch(ids):
            reads_seen.append(list(ids))
            if len(reads_seen) == 1:
                return {eid: [_entry(c=stale_ms, w=stale_ms)] for eid in ids}
            await asyncio.sleep(0.2)
            return {eid: [_entry(c=fresh_ms, w=fresh_ms)] for eid in ids}

        reads = ConfirmedReads(fetch, mono=lambda: time.monotonic() + offset["s"])
        monkeypatch.setattr(ca, "_READS", reads)
        await reads.current([5], 0.1)  # the stream that left at 19:19
        offset["s"] = STALE_S

        monkeypatch.setattr(mod, "HEARTBEAT_INTERVAL_S", 3600.0)
        chunks = await _collect(5, FakePubSub(), monkeypatch, disconnect_after=12)
        beats = [json.loads(c.split("data: ", 1)[1]) for c in chunks
                 if c.startswith("event: heartbeat\n")]
        assert ca.iso(stale_ms / 1000) not in [b["confirmed_at"] for b in beats], beats
        # The fresh value still goes out once its read lands.
        assert beats and beats[0]["confirmed_at"] == ca.iso(fresh_ms / 1000), beats
