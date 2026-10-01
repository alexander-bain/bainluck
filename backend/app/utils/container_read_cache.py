"""The published hub's served bytes, cached per (slug, revision). #9982.

SHIP: a reader who opens the NFL Week 4 hub, or comes Back to it from a game,
sees the games right away instead of "Loading collection…". (Pillar: DISCOVER /
FORMATTING.)

## The measurement

``GET /api/containers/nfl-2026-week-4`` (3,479 members, 3.47 MB) served in
4.95 s / 5.20 s TTFB on 2026-10-01 02:10Z; the latency ring's five events for
the route read ``db_ms`` 0.8–3.4 s and ``app_ms`` 2.8–5.7 s at 18 statements —
hydrating 3,463 boards and their outcomes, every request. The web hub re-reads
with ``no-store`` on every mount, focus and pageshow, so every Back paid it, and
the client gives up at 12 s while Week 4 is expected to grow.

## What this module is

The pure half of the route's response cache: the key, the freshness policy, and
the stored envelope. The I/O (process-local tier, Redis tier, singleflight,
background refresh) lives in ``app.routes.containers``.

* **The key carries the published revision.** Membership comes from ONE
  published read (#9651), and the route reads it before it consults this cache,
  so a republish is a different key the instant it commits — a reader is never
  served revision N's members under revision N+1. Only the CARDS age.
* **The cards age on the feed's clock, not a new one.** A card here is the same
  card ``GET /api/events`` and search serve, so its freshness mirrors the Discover
  feed's response cache: a payload with a live game is fresh for
  ``FEED_RESPONSE_TTL_LIVE_SECONDS`` and servable stale (while one rebuild runs
  in the background) up to ``FEED_RESPONSE_STALE_TTL_LIVE_SECONDS``; any other
  payload uses the anonymous feed's 60 s / 300 s. Imported, not copied, so the
  two cannot drift.
* **A scheduled game's kickoff caps the life of the whole payload**, the way the
  event detail route caps an unstarted entry (#4582): a hub cached at 12:58 for a
  1:00 kickoff expires at 1:00 plus the live TTL, so "scheduled" is never served
  for minutes after a game started.
* **The envelope carries its own deadlines.** ``fresh_until`` / ``stale_until``
  are computed once, from the payload, when it is built, and written beside the
  bytes; a reader of either tier never parses 3.5 MB to decide whether to serve
  it. ``built_at`` is the age origin and survives a copy between tiers.
"""

from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.feed_cache import (
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    FEED_RESPONSE_TTL_ANON_SECONDS,
    FEED_RESPONSE_TTL_LIVE_SECONDS,
)

#: Bumped when the payload shape changes, so a release never serves a body the
#: new code would not have built.
CONTAINER_READ_CACHE_VERSION = "v1"
CONTAINER_READ_CACHE_PREFIX = "container_read"

#: The fresh / stale-servable windows (seconds) — see the module docstring.
CONTAINER_READ_FRESH_TTL_SECONDS = FEED_RESPONSE_TTL_ANON_SECONDS
CONTAINER_READ_STALE_TTL_SECONDS = FEED_RESPONSE_STALE_TTL_SECONDS
CONTAINER_READ_FRESH_TTL_LIVE_SECONDS = FEED_RESPONSE_TTL_LIVE_SECONDS
CONTAINER_READ_STALE_TTL_LIVE_SECONDS = FEED_RESPONSE_STALE_TTL_LIVE_SECONDS


def container_read_cache_enabled() -> bool:
    """A kill switch, read at call time; ON unless set to ``false``."""
    return os.getenv("CONTAINERS_READ_CACHE_ENABLED", "true").strip().lower() != "false"


def container_read_cache_key(slug: str, revision: Optional[int], include_children: bool) -> str:
    scope = "all" if include_children else "own"
    return (
        f"{CONTAINER_READ_CACHE_PREFIX}:{CONTAINER_READ_CACHE_VERSION}:"
        f"{slug}:r{revision}:{scope}"
    )


def _event_cards(payload: Any):
    if not isinstance(payload, dict):
        return
    for section in payload.get("sections") or ():
        if not isinstance(section, dict):
            continue
        for member in section.get("members") or ():
            if isinstance(member, dict) and member.get("type") == "event":
                card = member.get("card")
                if isinstance(card, dict):
                    yield card


def _as_epoch(raw: Any) -> Optional[float]:
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def payload_deadlines(payload: Any, built_at: float) -> tuple[float, float]:
    """``(fresh_until, stale_until)`` as epoch seconds for a just-built payload.

    Pure. One live game card makes the whole payload live (a page is only as
    fresh as its fastest-moving card). A ``scheduled`` game caps both windows at
    its kickoff plus the live fresh TTL. Anything unparseable only ever falls
    back to the ordinary windows, never to a longer one.
    """
    live = False
    kickoff_cap: Optional[float] = None
    for card in _event_cards(payload):
        status = card.get("status")
        if status == "live":
            live = True
        elif status == "scheduled":
            start = _as_epoch(card.get("commence_time"))
            if start is not None:
                cap = max(start - built_at, 0.0) + CONTAINER_READ_FRESH_TTL_LIVE_SECONDS
                kickoff_cap = cap if kickoff_cap is None else min(kickoff_cap, cap)
    if live:
        fresh, stale = CONTAINER_READ_FRESH_TTL_LIVE_SECONDS, CONTAINER_READ_STALE_TTL_LIVE_SECONDS
    else:
        fresh, stale = CONTAINER_READ_FRESH_TTL_SECONDS, CONTAINER_READ_STALE_TTL_SECONDS
    if kickoff_cap is not None:
        fresh, stale = min(fresh, kickoff_cap), min(stale, kickoff_cap)
    return built_at + fresh, built_at + stale


@dataclass(frozen=True)
class CachedRead:
    """One served body and the deadlines it was built with."""

    body: bytes
    built_at: float
    fresh_until: float
    stale_until: float

    def is_fresh(self, now: float) -> bool:
        return now < self.fresh_until

    def is_servable(self, now: float) -> bool:
        return now < self.stale_until


def encode_entry(entry: CachedRead) -> bytes:
    """The Redis value: a one-line header, then the body, zlib-compressed.

    Compressed because Redis here is Premium-0 / 50 MB / allkeys-lru, where a
    3.5 MB value would evict colder keys other rails depend on; Week 4's body is
    ~220 KB compressed.
    """
    # ``repr`` round-trips a float exactly. A rounded stamp made a shared copy
    # look newer than the identical local one it was published from (CI, #9982).
    head = f"{entry.built_at!r} {entry.fresh_until!r} {entry.stale_until!r}\n"
    return zlib.compress(head.encode("ascii") + entry.body, 6)


def decode_entry(raw: Any) -> Optional[CachedRead]:
    """The inverse of :func:`encode_entry`; ``None`` for anything malformed."""
    if not isinstance(raw, (bytes, bytearray)):
        return None
    try:
        data = zlib.decompress(bytes(raw))
        head, body = data.split(b"\n", 1)
        built_at, fresh_until, stale_until = (float(x) for x in head.decode("ascii").split())
    except (zlib.error, ValueError, UnicodeDecodeError):
        return None
    return CachedRead(body=body, built_at=built_at, fresh_until=fresh_until, stale_until=stale_until)
