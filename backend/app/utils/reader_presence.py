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
from collections.abc import Iterable
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
