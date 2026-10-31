"""#10090 — the markets a reader is looking at right now, for the venue rails.

``POLYMARKET_WS_OPEN_SCOPE=slate`` narrows the Polymarket socket to live and
near-start markets, and the 30-second poll takes the rest. Two signals keep a
market a reader can see on the fast rails, and both rails read them here so they
cannot drift:

HELD (:func:`read_reader_presence`). The web process's SSE hub
(``utils/live_fanout``) holds ONE Redis subscription per channel any of its
readers holds: ``live:market:<id>`` (``routes/market_stream``, up to 50 visible
markets per reader) and ``live:event:<id>`` (``routes/event_stream``, the event
page and its fold members). A release with no reader left queues the channel's
UNSUBSCRIBE, sent on the reader loop's next pass (``_housekeep``). Nothing else
subscribes to those channels, so ``PUBSUB CHANNELS`` over the two patterns is
the held set across every web dyno, with no web change. The read is one bounded
command per pattern; any failure raises :class:`PresenceUnreadable`, and the
callers' rule is that an unreadable signal narrows nothing.

SERVED (:func:`served_market_ids`). The markets a page is serving now: Discover
page one, the category pages and the tournament registers — the same three
signals ``futures_price_refresh`` reads. Best-effort: a signal that cannot be
read contributes nothing.

Both are synchronous (a sync Redis client bounded at 2 s, small file reads); the
venue process calls them through ``asyncio.to_thread``.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.utils.live_push import event_channel
from app.utils.market_quote_push import market_channel

logger = logging.getLogger(__name__)

#: The channel prefixes, taken from the publishers' own builders.
MARKET_CHANNEL_PREFIX = market_channel(0)[:-1]
EVENT_CHANNEL_PREFIX = event_channel(0)[:-1]


class PresenceUnreadable(RuntimeError):
    """The held set could not be read; callers narrow nothing on it."""


@dataclass(frozen=True)
class ReaderPresence:
    """Market and event ids with at least one reader holding their stream."""

    market_ids: frozenset = frozenset()
    event_ids: frozenset = frozenset()


def _ids(channels: Iterable, prefix: str) -> frozenset:
    out = set()
    for channel in channels:
        if isinstance(channel, bytes):
            channel = channel.decode("utf-8", "replace")
        if not isinstance(channel, str) or not channel.startswith(prefix):
            continue
        tail = channel[len(prefix):]
        if tail.isdigit():
            out.add(int(tail))
    return frozenset(out)


def presence_from_channels(market_channels: Iterable, event_channels: Iterable) -> ReaderPresence:
    """The held ids named by ``PUBSUB CHANNELS`` replies (malformed names skipped)."""
    return ReaderPresence(
        market_ids=_ids(market_channels, MARKET_CHANNEL_PREFIX),
        event_ids=_ids(event_channels, EVENT_CHANNEL_PREFIX),
    )


def read_reader_presence(client=None) -> ReaderPresence:
    """``PUBSUB CHANNELS live:market:*`` and ``live:event:*``, parsed.

    Raises :class:`PresenceUnreadable` on any failure (no client, refused
    command, timeout): an empty answer and an unread one are never confused.
    """
    try:
        if client is None:
            from app.tasks.redis_state import get_redis_client

            client = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        markets = client.pubsub_channels(f"{MARKET_CHANNEL_PREFIX}*")
        events = client.pubsub_channels(f"{EVENT_CHANNEL_PREFIX}*")
    except Exception as exc:  # noqa: BLE001 — classified for the caller
        raise PresenceUnreadable(f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(markets, (list, tuple, set)) or not isinstance(
        events, (list, tuple, set)
    ):
        raise PresenceUnreadable("PUBSUB CHANNELS returned no list")
    return presence_from_channels(markets, events)


def served_market_ids() -> list[int]:
    """Markets a page is serving now: Discover page one, category pages, registers.

    Best-effort: each signal that cannot be read contributes nothing.
    """
    ids: set[int] = set()
    try:
        from app.utils.feed_served_markets import served_signal

        ids.update(int(i) for i in served_signal().ids)
    except Exception as exc:  # noqa: BLE001 — a missing signal narrows, never fails
        logger.warning("reader_presence: served signal unreadable: %s", exc)
    try:
        from app.utils.category_served_markets import category_served_market_ids

        ids.update(int(i) for i in category_served_market_ids().ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reader_presence: category signal unreadable: %s", exc)
    try:
        from app.utils.tournament_register import registered_market_ids

        ids.update(int(i) for i in registered_market_ids())
    except Exception as exc:  # noqa: BLE001
        logger.warning("reader_presence: register signal unreadable: %s", exc)
    return sorted(ids)


#: #10090 held-first stamps: how often a venue process re-reads the held event
#: set, and how long the last good read stays in use while later reads fail.
HELD_EVENTS_REFRESH_S = 2.0
HELD_EVENTS_STALE_S = 30.0


def _held_presence_read() -> ReaderPresence:
    """`read_reader_presence` on a fast-fail client: a hung Redis costs this
    background read, never a stamp."""
    from app.tasks.redis_state import get_redis_client

    return read_reader_presence(get_redis_client(
        socket_timeout=1.0, socket_connect_timeout=1.0, fast_fail=True,
    ))


class HeldEventCache:
    """#10090 — the event ids a reader holds, for ordering a venue's stamps.

    Never blocks its caller: a call that finds the set older than
    ``refresh_s`` starts ONE daemon thread running ``read`` and returns the set
    it already has. A failed read keeps the last good set until ``stale_s``,
    then the answer is empty, and empty means no preference (today's order).
    A process forked while a read was in flight starts its own.
    """

    def __init__(
        self,
        read: Callable[[], ReaderPresence] = _held_presence_read,
        *,
        refresh_s: float = HELD_EVENTS_REFRESH_S,
        stale_s: float = HELD_EVENTS_STALE_S,
        clock: Callable[[], float] = time.monotonic,
        start: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._read = read
        self._refresh_s = refresh_s
        self._stale_s = stale_s
        self._clock = clock
        self._start = start or self._start_thread
        self._lock = threading.Lock()
        self._ids: frozenset = frozenset()
        self._read_at: float | None = None
        self._attempt_at = -math.inf
        self._reading_pid: int | None = None
        self.reads = 0
        self.failures = 0

    @staticmethod
    def _start_thread(target: Callable[[], None]) -> None:
        threading.Thread(target=target, name="reader-held-events", daemon=True).start()

    def event_ids(self) -> frozenset:
        now = self._clock()
        with self._lock:
            pid = os.getpid()
            if self._reading_pid is not None and self._reading_pid != pid:
                self._reading_pid = None
            start = self._reading_pid is None and now - self._attempt_at >= self._refresh_s
            if start:
                self._attempt_at = now
                self._reading_pid = pid
            fresh = self._read_at is not None and now - self._read_at <= self._stale_s
            ids = self._ids if fresh else frozenset()
        if start:
            try:
                self._start(self._run)
            except Exception:  # noqa: BLE001 — no thread: the next call tries again
                with self._lock:
                    self._reading_pid = None
        return ids

    def _run(self) -> None:
        try:
            ids = frozenset(self._read().event_ids)
        except Exception as exc:  # noqa: BLE001 — the last good set stands until stale
            with self._lock:
                self._reading_pid = None
                self.failures += 1
                failures = self.failures
            if failures == 1 or failures % 1000 == 0:
                logger.warning("reader_presence: held events unreadable (%d): %s",
                               failures, exc)
            return
        with self._lock:
            self._reading_pid = None
            self._ids = ids
            self._read_at = self._clock()
            self.reads += 1


_HELD_EVENTS: HeldEventCache | None = None


def held_event_cache() -> HeldEventCache:
    """The process's held-event cache (one venue process per dyno run)."""
    global _HELD_EVENTS
    if _HELD_EVENTS is None:
        _HELD_EVENTS = HeldEventCache()
    return _HELD_EVENTS
