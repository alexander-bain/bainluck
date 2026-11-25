"""In-process response cache and singleflight for futures market-page reads (#13350).

Covers the five market-page endpoints in ``app.routes.futures``:

  * ``GET /api/futures/{market_id}`` (<= 15 s)
  * ``GET /api/futures/{market_id}/history`` (<= 60 s)
  * ``GET /api/futures/{market_id}/progression`` (<= 60 s)
  * ``GET /api/futures/{market_id}/related-events`` (<= 60 s)
  * ``GET /api/futures/groups/{group_id}`` (<= 60 s)

PROCESS MEMORY ONLY, NEVER REDIS. Production Redis is 50 MB allkeys-lru
(``middleware/latency.py``): storing large serialized market/history bodies
there would evict quota state and sentinel verdicts regardless of TTL. Storing
already-encoded UTF-8 JSON bytes in a bounded ``OrderedDict`` caps worker
memory and preserves every price timestamp verbatim so reader-visible price
ages always reflect when the price was read, never when the cache copy was
created.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from app.utils import request_cache as _rc

DETAIL_TTL = 15.0
SUBROUTE_TTL = 60.0

#: Per-worker ceiling on cached body bytes. Oldest entries evict first.
MAX_BYTES = 16 * 1024 * 1024
#: Oversized bodies are returned directly without evicting everything else.
MAX_ENTRY_BYTES = 2 * 1024 * 1024

# key -> (stored_monotonic, ttl_seconds, encoded_body)
_entries: "OrderedDict[tuple, tuple[float, float, bytes]]" = OrderedDict()
_total_bytes = 0
_fresh_builds: dict[tuple, tuple[float, "asyncio.Future[bytes]"]] = {}


class _BuildAbandoned(Exception):
    """Raised internally to waiting callers when a leader is cancelled."""


def detail_key(market_id: int, representation: str) -> tuple:
    return (
        "detail",
        int(market_id),
        "verified_title" if representation == "verified_title" else "source",
    )


def history_key(
    market_id: int,
    outcome_id: Optional[int],
    hours: int,
    top_n: int,
    champion: Optional[str],
    history_range: Optional[str],
) -> tuple:
    clean_champion = (
        champion.strip() if isinstance(champion, str) and champion.strip() else None
    )
    clean_range = (
        history_range.strip().lower()
        if isinstance(history_range, str) and history_range.strip()
        else None
    )
    return (
        "history",
        int(market_id),
        int(outcome_id) if outcome_id is not None else None,
        int(hours),
        int(top_n),
        clean_champion,
        clean_range,
    )


def progression_key(
    market_id: int,
    top_n: int,
    golf_card_receipt: Optional[str],
) -> tuple:
    clean_receipt = (
        golf_card_receipt
        if isinstance(golf_card_receipt, str) and golf_card_receipt
        else None
    )
    return ("progression", int(market_id), int(top_n), clean_receipt)


def related_events_key(market_id: int) -> tuple:
    return ("related_events", int(market_id))


def group_key(group_id: str) -> tuple:
    return ("group", str(group_id))


def detail_ttl(payload) -> float:
    return DETAIL_TTL if isinstance(payload, dict) else 0.0


def subroute_ttl(payload) -> float:
    return SUBROUTE_TTL if isinstance(payload, dict) else 0.0


def history_ttl(payload) -> float:
    if not isinstance(payload, dict):
        return 0.0
    venue = payload.get("venue_history")
    if isinstance(venue, dict) and venue.get("fill") == "requested":
        return 0.0
    return SUBROUTE_TTL


def related_events_ttl(
    payload, *, now_dt: Optional[datetime] = None
) -> float:
    if not isinstance(payload, dict):
        return 0.0
    ttl = SUBROUTE_TTL
    events = payload.get("events")
    if not isinstance(events, list):
        return ttl
    ref = now_dt if now_dt is not None else datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "scheduled":
            continue
        raw_commence = event.get("commence_time")
        if not isinstance(raw_commence, str) or not raw_commence:
            continue
        try:
            commence_dt = datetime.fromisoformat(raw_commence)
        except ValueError:
            continue
        if commence_dt.tzinfo is None:
            commence_dt = commence_dt.replace(tzinfo=timezone.utc)
        delta = (commence_dt - ref).total_seconds()
        if delta <= 0:
            return 0.0
        ttl = min(ttl, delta)
    return ttl


def read(key: tuple, now: Optional[float] = None) -> Optional[bytes]:
    """Return cached serialized JSON bytes for ``key``, or ``None``."""
    entry = _entries.get(key)
    if entry is None:
        return None
    stored_at, ttl, body = entry
    current = now if now is not None else time.monotonic()
    if current - stored_at >= ttl:
        _drop(key)
        return None
    _entries.move_to_end(key)
    return body


def write(
    key: tuple,
    body: bytes,
    ttl: float,
    now: Optional[float] = None,
) -> None:
    """Store serialized JSON bytes for ``key`` under the process LRU cap."""
    global _total_bytes
    if ttl <= 0 or len(body) > MAX_ENTRY_BYTES:
        return
    _drop(key)
    current = now if now is not None else time.monotonic()
    _entries[key] = (current, float(ttl), body)
    _total_bytes += len(body)
    while _total_bytes > MAX_BYTES and _entries:
        _drop(next(iter(_entries)))


def _drop(key: tuple) -> None:
    global _total_bytes
    entry = _entries.pop(key, None)
    if entry is not None:
        _total_bytes -= len(entry[2])


def total_bytes() -> int:
    return _total_bytes


def _reset_for_tests() -> None:
    global _total_bytes
    _entries.clear()
    _total_bytes = 0
    _fresh_builds.clear()


def _encode_body(payload: dict) -> bytes:
    return JSONResponse(content=jsonable_encoder(payload)).body


def _json_response(body: bytes, cache_state: str) -> Response:
    return Response(
        content=body,
        media_type="application/json",
        headers={"X-Feed-Cache": cache_state},
    )


async def _coalesced_fresh_build(
    key: tuple,
    asked_at: float,
    build: Callable[[], Awaitable[dict]],
) -> bytes:
    """Coalesce ``fresh=true`` callers onto a build started strictly after ``asked_at``."""
    while True:
        inflight = _fresh_builds.get(key)
        if inflight is None:
            break
        started_at, shared = inflight
        try:
            body = await asyncio.shield(shared)
        except _BuildAbandoned:
            continue
        except Exception:
            if started_at > asked_at:
                raise
            continue
        if started_at > asked_at:
            return body

    started_at = time.monotonic()
    shared: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
    shared.add_done_callback(lambda f: f.cancelled() or f.exception())
    _fresh_builds[key] = (started_at, shared)
    try:
        payload = await build()
        body = _encode_body(payload)
    except Exception as exc:
        if _fresh_builds.get(key, (None, None))[1] is shared:
            del _fresh_builds[key]
        if not shared.done():
            shared.set_exception(exc)
        raise
    except BaseException:
        if _fresh_builds.get(key, (None, None))[1] is shared:
            del _fresh_builds[key]
        if not shared.done():
            shared.set_exception(_BuildAbandoned())
        raise
    if _fresh_builds.get(key, (None, None))[1] is shared:
        del _fresh_builds[key]
    if not shared.done():
        shared.set_result(body)
    return body


async def serve_cached_or_build(
    *,
    key: tuple,
    fresh: bool,
    build: Callable[[], Awaitable[dict]],
    ttl_for: Callable[[dict], float],
) -> Response:
    """Serve a cached futures-page body or build once under per-key singleflight."""
    if fresh:
        body = await _coalesced_fresh_build(key, time.monotonic(), build)
        return _json_response(body, "bypass")

    flight_key = f"futures_page:{repr(key)}"
    while True:
        hit = read(key)
        if hit is not None:
            return _json_response(hit, "hit")

        leader, fut = _rc.begin_build(flight_key)
        if not leader:
            try:
                body = await asyncio.shield(fut)
            except asyncio.CancelledError:
                raise
            except _BuildAbandoned:
                continue
            except Exception:
                raise
            return _json_response(body, "coalesced")

        try:
            payload = await build()
            body = _encode_body(payload)
        except Exception as exc:
            _rc.finish_build(flight_key, fut, exc=exc)
            if fut.done() and not fut.cancelled():
                fut.exception()
            raise
        except BaseException:
            _rc.finish_build(flight_key, fut, exc=_BuildAbandoned())
            if fut.done() and not fut.cancelled():
                fut.exception()
            raise

        ttl = ttl_for(payload)
        if ttl > 0:
            write(key, body, ttl)
        _rc.finish_build(flight_key, fut, result=body)
        return _json_response(body, "miss")
