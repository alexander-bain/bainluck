"""Cache policy for the `/api/event/{key}` concept tier (#1107, LAT-P021).

Extracted out of `routes/event.py` under ruling 005 (extract-on-touch): this queue
changes the tier's serve decision, its fallback, and its write path, so the policy
comes out of the route and into a module that can be tested without a web request,
and the tier converts to the cache envelope (`docs/contracts/cache-envelope.md`)
on its way through.

WHAT WAS WRONG, measured in production 2026-08-09 (LAT-P021 Item 0):

    21:07:33  event:golf:pga-championship   200  10.977s   cold build; writes primary(60s)+stale(24h)
    21:08:09  event:golf:pga-championship   200   0.437s   t+36s, inside the 60s TTL
    21:09:18  event:golf:pga-championship   200  18.537s   t+105s, TTL expired

The third read is the defect. The primary had expired and a 96-second-old, complete,
healthy 24h snapshot was sitting one Redis key away — and the request walked straight
past it into a full rebuild. The 24h mirror was only ever consulted when the adapter
*raised*; a plain TTL expiry, which is the overwhelmingly common cache event, never
reached it. So every organic reader of a page not read once a minute paid 10-30s, and
`event:golf:the-open-championship` paid 30s and then a **503** at Heroku's H12 boundary
(the dyno finished the build ~35s in and warmed the cache for the *next* reader).

The fix is serve-stale-while-revalidate: a miss serves the mirror immediately and
schedules exactly one background rebuild. That is what makes the miss rate stop
mattering — a miss costs 0.44s instead of 30s.

Three further defects Codex C224 found in this tier are closed here too:
  * a malformed primary used to disable Redis for the whole request (the bare
    `except Exception: _rc = None`), so it skipped the healthy mirror AND the
    write-back. Decoding is tolerant now and never disarms the client.
  * no single-flight, so N concurrent readers past the TTL each ran a full build.
  * no age or status disclosure on a fallback that could serve 24h-old content.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

# Primary TTL. Unchanged at 60s: it still governs how fresh a *live* hit is, and
# the underlying live polling runs every ~2 min. What changed is that expiry no
# longer costs the user a rebuild, so this number stopped being a latency knob.
ENVELOPE_TTL = 60

# The mirror. Now a first-class serve path rather than an error handler.
STALE_TTL = 86400

# LAT-P014: a known-absent key short-circuits before the adapter runs. Kept short
# so a tournament that appears mid-window is at most this late.
NEGATIVE_TTL = 60
NEGATIVE_SENTINEL = "404"

# Single-flight window for the background revalidation. Longer than the slowest
# measured cold build (~35s for The Open) so a burst of readers behind one expiry
# triggers exactly one rebuild, and short enough that a worker that died holding
# it cannot wedge the key for long.
REFRESH_LOCK_TTL = 120

# Envelope `generation` (contract field 1). BUMP THIS when the payload shape
# changes: a cached payload built by a generation that is no longer deployed is
# refused on read and rebuilt, which is also what makes the very first deploy of
# this module self-healing — every pre-envelope payload already in Redis reads as
# a miss rather than being served without disclosure.
GENERATION = 2

CACHE_PREFIX = "bainluck:event_concept:"

# The envelope lives under this top-level key. Additive: no existing key of the
# concept payload changes name, type, or meaning.
ENVELOPE_FIELD = "cache"

AVAILABILITY_LIVE = "live"
AVAILABILITY_STALE_OK = "stale_ok"
AVAILABILITY_UNAVAILABLE = "unavailable"

QUALITY_FULL = "full"
QUALITY_PARTIAL = "partial"
QUALITY_DEGRADED = "degraded"


@dataclass(frozen=True)
class ConceptCacheKeys:
    """Every Redis key this tier owns for one concept key."""

    primary: str
    stale: str
    negative: str
    refresh_lock: str


def cache_keys(key: str) -> ConceptCacheKeys:
    base = f"{CACHE_PREFIX}{key}"
    return ConceptCacheKeys(
        primary=base,
        stale=f"{base}:stale",
        negative=f"{base}:404",
        refresh_lock=f"{base}:refreshing",
    )


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def stamp_envelope(
    result: dict[str, Any],
    *,
    created_at: datetime,
    lifecycle_watermark: datetime | None,
    quality: str = QUALITY_FULL,
) -> dict[str, Any]:
    """Attach the producer half of the cache envelope to a freshly built payload.

    `availability` is deliberately NOT set here. It is the *serve* decision, and
    the same stored payload is `live` when read inside the TTL and `stale_ok`
    when read from the mirror — so it is stamped on the way out, by
    `with_availability`, not on the way in.

    `created_at` is when the CONTENT was computed, per the contract. It is baked
    into the stored bytes, so a payload served from the 24h mirror reports the
    age of the content and not the age of the read.
    """
    enveloped = dict(result)
    enveloped[ENVELOPE_FIELD] = {
        "generation": GENERATION,
        "created_at": _iso(created_at),
        "quality": quality,
        # Filled in at serve time; present here so the field is never absent.
        "availability": None,
        "lifecycle_watermark": _iso(lifecycle_watermark),
    }
    return enveloped


def with_availability(payload: dict[str, Any], availability: str) -> dict[str, Any]:
    """Publish the serve decision (contract rule 1: the producer decides, the
    consumer reads — a client must never re-derive freshness from `created_at`)."""
    out = dict(payload)
    envelope = dict(out.get(ENVELOPE_FIELD) or {})
    envelope["availability"] = availability
    out[ENVELOPE_FIELD] = envelope
    return out


def is_current_generation(payload: Any) -> bool:
    """True only for a payload this deploy is willing to serve.

    A pre-envelope payload (no `cache` block) and a payload from another
    generation both read as False, so both are rebuilt rather than served
    without disclosure.
    """
    if not isinstance(payload, dict):
        return False
    envelope = payload.get(ENVELOPE_FIELD)
    if not isinstance(envelope, dict):
        return False
    return envelope.get("generation") == GENERATION


def payload_created_at(payload: dict[str, Any]) -> datetime | None:
    envelope = payload.get(ENVELOPE_FIELD) if isinstance(payload, dict) else None
    if not isinstance(envelope, dict):
        return None
    return _parse_iso(envelope.get("created_at"))


def payload_age_seconds(payload: dict[str, Any], now: datetime | None = None) -> float | None:
    created = payload_created_at(payload)
    if created is None:
        return None
    return ((now or _utcnow()) - created).total_seconds()


# ---------------------------------------------------------------------------
# Tolerant codec
# ---------------------------------------------------------------------------


def decode_payload(raw: Any) -> dict[str, Any] | None:
    """Decode a cached value, returning None for anything unusable.

    Deliberately total. The old route wrapped the decode in the same
    `except Exception` that owned the Redis handle, so one corrupt primary
    disarmed the client for the rest of the request — skipping a perfectly
    healthy mirror on the read side and dropping the write-back on the way out
    (Codex C224). A corrupt value is a miss, nothing more.
    """
    if raw is None:
        return None
    try:
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        value = json.loads(text)
    except Exception:
        logger.warning("event-concept cache: discarding undecodable cached value")
        return None
    return value if isinstance(value, dict) else None


def encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Watermark
# ---------------------------------------------------------------------------


def collect_market_ids(result: dict[str, Any]) -> list[int]:
    """Every FuturesMarket id this payload was assembled from.

    Pure, so the watermark's input set is testable without a database.
    """
    ids: set[int] = set()

    for child in _as_list(result.get("children")):
        _add_int(ids, child.get("market_id") if isinstance(child, dict) else None)

    for section in _as_list(result.get("sections")):
        if not isinstance(section, dict):
            continue
        for mid in _as_list(section.get("market_ids")):
            _add_int(ids, mid)

    primary = result.get("primary")
    if isinstance(primary, dict):
        _add_int(ids, primary.get("evolution_market_id"))

    return sorted(ids)


def payload_as_of(result: dict[str, Any]) -> datetime | None:
    """The live-play `as_of` the golf fuse publishes, when there is one.

    Only populated during live play; settled and upcoming majors carry null.
    That is why it is one input to the watermark and not the whole of it.
    """
    event = result.get("event")
    if not isinstance(event, dict):
        return None
    return _parse_iso(event.get("as_of"))


async def compute_watermark(db, result: dict[str, Any]) -> datetime | None:
    """The newest upstream fact this payload reflects (contract field 5).

    `max(FuturesMarket.updated_at)` over exactly the markets in the payload,
    combined with the live `as_of` when the fuse published one. One indexed
    aggregate over ~30 primary keys — it runs only on a BUILD, which already
    costs 10-30s, never on a serve.

    Answers the question `created_at` cannot: whether a payload we recomputed a
    minute ago is reflecting a source that stopped updating yesterday.
    """
    candidates: list[datetime] = []

    as_of = payload_as_of(result)
    if as_of is not None:
        candidates.append(as_of)

    market_ids = collect_market_ids(result)
    if market_ids:
        try:
            from sqlalchemy import func, select

            from app.models.models import FuturesMarket

            newest = await db.scalar(
                select(func.max(FuturesMarket.updated_at)).where(
                    FuturesMarket.id.in_(market_ids)
                )
            )
            if isinstance(newest, datetime):
                candidates.append(_as_utc(newest))
            elif newest is not None:
                # Not a datetime, so not a watermark. Publishing null is the
                # honest answer; coercing whatever this is would put a fabricated
                # freshness claim on the payload, which is the exact failure the
                # field exists to prevent.
                logger.warning(
                    "event-concept cache: watermark query returned %s, not a datetime",
                    type(newest).__name__,
                )
        except Exception:
            # A watermark we could not compute must not cost the user the page.
            # It reads as null, and the contract's point is that a null we
            # published is still a published answer.
            logger.warning("event-concept cache: watermark query failed", exc_info=True)

    return max(candidates) if candidates else None


# ---------------------------------------------------------------------------
# Redis helpers — every one of these is best-effort by construction
# ---------------------------------------------------------------------------


def read_slot(rc, key: str) -> dict[str, Any] | None:
    """Read one cache slot, returning a usable current-generation payload or None."""
    if rc is None:
        return None
    try:
        raw = rc.get(key)
    except Exception:
        logger.warning("event-concept cache: read failed for %s", key)
        return None
    payload = decode_payload(raw)
    if payload is None or not is_current_generation(payload):
        return None
    return payload


def write_payload(rc, keys: ConceptCacheKeys, payload: dict[str, Any]) -> None:
    """Write both slots and clear any negative. Never raises."""
    if rc is None:
        return
    try:
        encoded = encode_payload(payload)
        rc.setex(keys.primary, ENVELOPE_TTL, encoded)
        rc.setex(keys.stale, STALE_TTL, encoded)
        # A key that now resolves must not keep a negative entry behind it.
        rc.delete(keys.negative)
    except Exception:
        logger.warning("event-concept cache: write failed for %s", keys.primary)


def write_negative(rc, keys: ConceptCacheKeys) -> None:
    if rc is None:
        return
    try:
        rc.setex(keys.negative, NEGATIVE_TTL, NEGATIVE_SENTINEL)
    except Exception:
        logger.warning("event-concept cache: negative write failed for %s", keys.negative)


def has_negative(rc, keys: ConceptCacheKeys) -> bool:
    if rc is None:
        return False
    try:
        return bool(rc.get(keys.negative))
    except Exception:
        return False


def acquire_refresh_lock(rc, keys: ConceptCacheKeys) -> bool:
    """Single-flight. True for exactly one caller per REFRESH_LOCK_TTL window."""
    if rc is None:
        return False
    try:
        return bool(rc.set(keys.refresh_lock, "1", nx=True, ex=REFRESH_LOCK_TTL))
    except Exception:
        return False


def release_refresh_lock(rc, keys: ConceptCacheKeys) -> None:
    if rc is None:
        return
    try:
        rc.delete(keys.refresh_lock)
    except Exception:
        pass


def get_client():
    """The bounded shared client, or None. Never raises (gotcha #39: a sync Redis
    client with no socket timeout can freeze the event loop; `get_redis_client()`
    is bounded by default and must never be hand-rolled here)."""
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The shared build path — one implementation for the route and the warmer
# ---------------------------------------------------------------------------


async def build_and_cache(key: str, db, rc=None, adapter=None) -> dict[str, Any] | None:
    """Build the concept envelope for `key`, stamp it, and write both slots.

    Returns the stamped payload, or None when the key resolves to nothing (in
    which case the negative is recorded). Raises whatever the adapter raises —
    the caller decides whether a stale mirror can rescue it.

    Shared by `routes/event.py` and the warmer task so the two can never drift
    on TTL, envelope, or key shape. `adapter` is passed in by the route, which
    has already resolved it to answer the unknown-domain 404; the warmer leaves
    it None and this resolves it.
    """
    from app.utils.event_concept import (
        get_adapter,
        parse_event_key,
        strip_competitor_wire_leaks,
    )

    domain, slug = parse_event_key(key)
    if adapter is None:
        adapter = get_adapter(domain)
    if adapter is None:
        return None

    keys = cache_keys(key)

    envelope = await adapter.build_event(slug, db)
    if envelope is None:
        write_negative(rc, keys)
        return None

    # L2-48/L2-118: probability-only product — strip odds from the wire before
    # anything is stamped or stored.
    result = strip_competitor_wire_leaks(envelope)

    watermark = await compute_watermark(db, result)
    stamped = stamp_envelope(result, created_at=_utcnow(), lifecycle_watermark=watermark)

    write_payload(rc, keys, stamped)
    return stamped


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    # Total by construction. The envelope is stamped on the response path of a
    # page that is already the subject of a p0, so a surprising value here must
    # publish a null rather than raise on the way out.
    if not isinstance(value, datetime):
        return None
    return _as_utc(value).isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except Exception:
        return None


def _as_list(value: Any) -> Iterable[Any]:
    return value if isinstance(value, list) else ()


def _add_int(target: set[int], value: Any) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        target.add(value)
    elif isinstance(value, str) and value.isdigit():
        target.add(int(value))
