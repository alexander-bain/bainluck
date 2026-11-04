"""#10090 — a held market's venue move, shown at arrival (Discover futures cards).

WHAT A READER SEES. A Kalshi or Polymarket futures/prop card in view on Discover
moves when the venue's price arrives at our socket, instead of after the
socket's flush, its committed invalidation (`market_quote_push`) and the card's
price-card re-read (`routes/feed_prices`).

HOW. At the instant a venue consumer puts a price into its flush buffer
(`kalshi_ws.handle_ticker`; `polymarket_ws.handle_price` / `handle_trade`), it
calls :meth:`MarketPreviewPublisher.note` with the market id and outcome id it
already holds in its in-memory ticker/token maps and the probability it just
buffered. The flush stays the write behind, unchanged: this module opens no
database session and reads no row. It publishes a PROVISIONAL frame on the
market's existing channel (``live:market:<id>``):

    {"type": "market_preview", "preview": true, "market_id", "source",
     "outcomes": [{"outcome_id", "p", "observed_at"}], "seq", "ttl_ms",
     "published_at"}

``routes/market_stream`` forwards it under its own SSE event name
(``market_preview``); a client overlays it on a card only while its
``observed_at`` is newer than the card's committed observation for that outcome
and before ``ttl_ms``. The committed re-read with an equal-or-newer observation
replaces it; a reconnect clears it. A frame without ``invalidation: true`` is
refused by :func:`market_quote_push.parse_market_frame`, so a web dyno that
predates this module drops it.

COST BOUNDS (the hard acceptance):

* Only HELD markets publish — a market whose ``live:market:<id>`` channel a web
  dyno's SSE hub holds (``reader_presence.HeldEventCache.market_ids``: one
  background ``PUBSUB CHANNELS`` read per process every 2 s, never per tick).
* Change-only: an outcome whose price equals the last published value for it
  is dropped; a burst that returns to the published value publishes nothing.
* Coalesced per market: at most one frame per market per
  :data:`PREVIEW_WINDOW_S`, carrying the newest price per outcome. The first
  move in a quiet window goes at once (leading edge); later ones in the window
  ride the next frame (trailing edge), so the last price in a burst is never
  lost.
* Never a settled or graded leg: a market the consumer saw settle (its own
  in-memory refusal) or one :meth:`refuse_market` / :meth:`refuse_outcome`
  named is never previewed, and ``0 < p < 1`` only — a terminal 0 or 1 is
  settlement's to write.
* Publishing runs in ONE drain task per consumer, off the socket's reader and
  outside its buffer lock; it reuses the bounded pipelined transport of
  `market_quote_push.publish_market_changes` on the consumer's own Redis client.

THE GAP. A Polymarket open contract the open-contract admission cannot pair to
its tokens (``markets_unpaired``, `polymarket_open_contracts`) never reaches the
socket, so it gets no preview and stays on the 30-second poll / committed read.

Kill switch: ``MARKET_PREVIEW_PUBLISH=0`` (read when a consumer starts; default
on). See docs/live-settings.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from app.utils.market_quote_push import SOURCES

logger = logging.getLogger(__name__)

MARKET_PREVIEW_ENV = "MARKET_PREVIEW_PUBLISH"
PREVIEW_FRAME_TYPE = "market_preview"
#: At most one frame per market per window. 250 ms keeps the added wait inside
#: the 0.5 s venue-to-screen bar for a market that moves again inside the window
#: (the first move in a quiet window is not delayed at all).
PREVIEW_WINDOW_S = 0.25
#: How long a client may show a preview the committed path has not replaced.
#: Covers the flush (0.25 s in production, 5 s after a receipt-previewed Kalshi
#: game), the invalidation and the paced price-card re-read (≥ 2 s apart).
PREVIEW_TTL_MS = 10_000
#: How often a publisher re-asks the process's held set (itself re-read from
#: Redis in the background every 2 s, `reader_presence.HeldEventCache`).
HELD_RECHECK_S = 0.25
#: A parsed frame's bounds (a frame is one market's changed legs).
MAX_PREVIEW_OUTCOMES = 500
MAX_PREVIEW_TTL_MS = 60_000
#: Book-keeping for markets published long ago is dropped past this size.
_PRUNE_AT = 2048
_PRUNE_IDLE_S = 60.0


def market_preview_enabled() -> bool:
    """``MARKET_PREVIEW_PUBLISH``: unset or anything but ``0`` is on."""
    return os.getenv(MARKET_PREVIEW_ENV, "1").strip() != "0"


def _held_market_ids() -> frozenset:
    from app.utils.reader_presence import held_event_cache

    return held_event_cache().market_ids()


async def _send(frames: list[dict], client) -> int:
    """The committed invalidations' bounded, pipelined PUBLISH (never raises)."""
    from app.utils.market_quote_push import publish_market_changes

    return await publish_market_changes(frames, client)


class MarketPreviewPublisher:
    """One venue consumer's market previews. See the module docstring.

    ``client`` returns the consumer's async Redis client (called only when a
    frame is sent). ``held`` returns the held market ids (default: the
    process's :class:`~app.utils.reader_presence.HeldEventCache`). ``refused``
    is the consumer's own in-memory settled test for a market, if it has one.
    """

    def __init__(
        self,
        source: str,
        client: Callable[[], Any],
        *,
        held: Callable[[], Iterable[int]] | None = None,
        refused: Callable[[int], bool] | None = None,
        enabled: bool | None = None,
        window_s: float = PREVIEW_WINDOW_S,
        ttl_ms: int = PREVIEW_TTL_MS,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        if source not in SOURCES:
            raise ValueError(f"unsupported preview source {source!r}")
        self.source = source
        self._client = client
        self._held = held or _held_market_ids
        self._refused = refused
        self.enabled = market_preview_enabled() if enabled is None else bool(enabled)
        self._window_s = window_s
        self._ttl_ms = int(ttl_ms)
        self._clock = clock
        self._wall = wall
        # market -> outcome -> (price, receipt wall time), newest per outcome.
        self._pending: dict[int, dict[int, tuple[float, float]]] = {}
        # market -> outcome -> last published price.
        self._sent: dict[int, dict[int, float]] = {}
        self._next_at: dict[int, float] = {}
        self._refused_markets: set[int] = set()
        self._refused_outcomes: set[int] = set()
        self._seq = 0
        # The held set, re-asked at most every HELD_RECHECK_S: a tick for a
        # market nobody holds (nearly all of them) costs a clock read and one
        # set lookup.
        self._held_ids: frozenset = frozenset()
        self._held_at = -math.inf
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None
        self.frames = 0
        self.failures = 0

    # ----------------------------------------------------------- hot path --

    def note(self, market_id: Any, outcome_id: Any, probability: Any) -> None:
        """A price just entered the flush buffer. Synchronous, no I/O; never raises."""
        try:
            if not self.enabled or market_id is None or outcome_id is None:
                return
            now = self._clock()
            if now - self._held_at >= HELD_RECHECK_S:
                self._held_ids = frozenset(self._held())
                self._held_at = now
            if market_id not in self._held_ids:
                return
            if market_id in self._refused_markets or outcome_id in self._refused_outcomes:
                return
            price = round(float(probability), 6)
            if not 0.0 < price < 1.0:
                return
            if self._refused is not None and self._refused(market_id):
                return
            pending = self._pending.get(market_id)
            sent = self._sent.get(market_id)
            if sent is not None and sent.get(outcome_id) == price:
                # Back at what readers already have: nothing to say.
                if pending is not None and pending.pop(outcome_id, None) is not None and not pending:
                    del self._pending[market_id]
                return
            if pending is None:
                pending = self._pending[market_id] = {}
            pending[outcome_id] = (price, self._wall())
            self._kick()
        except Exception:  # noqa: BLE001 — a preview never costs the price
            logger.debug("market_preview[%s]: note failed", self.source, exc_info=True)

    def refuse_market(self, market_id: int) -> None:
        """This market settled: never preview it again in this process."""
        self._refused_markets.add(market_id)
        self._pending.pop(market_id, None)

    def refuse_outcome(self, outcome_id: int) -> None:
        """This leg was graded: never preview it again in this process."""
        self._refused_outcomes.add(outcome_id)
        self.forget((outcome_id,))

    def forget(self, outcome_ids: Iterable[int]) -> None:
        """Drop these legs' unsent prices (a book withdrew them)."""
        drop = set(outcome_ids)
        if not drop:
            return
        for market_id in list(self._pending):
            pending = self._pending[market_id]
            for oid in drop.intersection(pending):
                del pending[oid]
            if not pending:
                del self._pending[market_id]
        for sent in self._sent.values():
            for oid in drop.intersection(sent):
                del sent[oid]

    def _kick(self) -> None:
        task = self._task
        if task is not None and not task.done():
            if self._wake is not None:
                self._wake.set()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop here: the next note inside the loop sends it
        self._task = loop.create_task(self._drain(), name=f"market-preview-{self.source}")

    # -------------------------------------------------------------- drain --

    async def _drain(self) -> None:
        """Send what is due; sleep until the next market's window opens; exit idle."""
        self._wake = wake = asyncio.Event()
        while self._pending:
            wake.clear()
            frames = self._due_frames(self._clock())
            if frames:
                await self._publish(frames)
            if not self._pending:
                break
            now = self._clock()
            wait = min(self._next_at.get(mid, now) for mid in self._pending) - now
            if wait > 0:
                try:
                    await asyncio.wait_for(wake.wait(), timeout=wait)
                except asyncio.TimeoutError:
                    # The window ended with no new note: loop round and publish what is due.
                    continue

    def _due_frames(self, now: float) -> list[dict]:
        frames = []
        for market_id in list(self._pending):
            if self._next_at.get(market_id, -math.inf) > now:
                continue
            outcomes = self._pending.pop(market_id)
            if market_id in self._refused_markets or (
                self._refused is not None and self._refused(market_id)
            ):
                continue
            sent = self._sent.setdefault(market_id, {})
            rows = [
                (oid, price, at) for oid, (price, at) in sorted(outcomes.items())
                if oid not in self._refused_outcomes and sent.get(oid) != price
            ]
            if not rows:
                continue
            frames.append(self._frame(market_id, rows))
            for oid, price, _at in rows:
                sent[oid] = price
            self._next_at[market_id] = now + self._window_s
        if len(self._next_at) > _PRUNE_AT:
            for market_id in [m for m, at in self._next_at.items()
                              if at < now - _PRUNE_IDLE_S and m not in self._pending]:
                self._next_at.pop(market_id, None)
                self._sent.pop(market_id, None)
        return frames

    def _next_seq(self) -> int:
        # Monotonic in this process, and past any earlier process's numbers
        # (microseconds of wall time), so a restarted consumer is not fenced out.
        self._seq = max(self._seq + 1, time.time_ns() // 1000)
        return self._seq

    def _frame(self, market_id: int, rows) -> dict:
        return {
            "type": PREVIEW_FRAME_TYPE,
            "preview": True,
            "market_id": market_id,
            "source": self.source,
            "outcomes": [
                {
                    "outcome_id": oid,
                    "p": price,
                    "observed_at": datetime.fromtimestamp(at, timezone.utc).isoformat(),
                }
                for oid, price, at in rows
            ],
            "seq": self._next_seq(),
            "ttl_ms": self._ttl_ms,
        }

    async def _publish(self, frames: list[dict]) -> None:
        try:
            client = self._client()
        except Exception:  # noqa: BLE001
            self.failures += 1
            logger.debug("market_preview[%s]: no Redis client", self.source, exc_info=True)
            return
        sent = await _send(frames, client)
        self.frames += sent
        if sent < len(frames):
            self.failures += 1


# --------------------------------------------------------------- reader --


def _positive_id(value: Any) -> bool:
    return type(value) is int and value > 0


def _stamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("a timestamp is required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("a timestamp needs its zone")
    return stamp.astimezone(timezone.utc)


def parse_market_preview(raw: Any) -> dict | None:
    """A well-formed preview frame, or None (malformed traffic is ignored)."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str) or PREVIEW_FRAME_TYPE not in raw:
            return None
        frame = json.loads(raw)
        if (not isinstance(frame, dict) or frame.get("type") != PREVIEW_FRAME_TYPE
                or frame.get("preview") is not True or "invalidation" in frame):
            return None
        market_id, source = frame["market_id"], frame["source"]
        seq, ttl_ms = frame["seq"], frame["ttl_ms"]
        if not _positive_id(market_id) or source not in SOURCES or not _positive_id(seq):
            return None
        if type(ttl_ms) is not int or not 0 < ttl_ms <= MAX_PREVIEW_TTL_MS:
            return None
        outcomes = frame["outcomes"]
        if not isinstance(outcomes, list) or not 0 < len(outcomes) <= MAX_PREVIEW_OUTCOMES:
            return None
        parsed, seen = [], set()
        for row in outcomes:
            if not isinstance(row, dict):
                return None
            oid, price = row["outcome_id"], row["p"]
            if not _positive_id(oid) or oid in seen:
                return None
            if type(price) not in (int, float) or not 0 < price < 1:
                return None
            seen.add(oid)
            parsed.append({
                "outcome_id": oid, "p": float(price),
                "observed_at": _stamp(row["observed_at"]).isoformat(),
            })
        return {
            "type": PREVIEW_FRAME_TYPE,
            "preview": True,
            "market_id": market_id,
            "source": source,
            "outcomes": parsed,
            "seq": seq,
            "ttl_ms": ttl_ms,
            "published_at": _stamp(frame["published_at"]).isoformat(),
        }
    except (KeyError, TypeError, ValueError, OverflowError, UnicodeError):
        return None
