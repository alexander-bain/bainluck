"""Bounded 60s L1 + Redis L2 cache for newest venue trade rows (#11931).

`withheld_price_outcome_ids_for_markets` queries the 51 GB
`futures_odds_snapshots` table for the newest `(outcome_id, last_price)` rows
per venue. On a cold Sports list build (`mode=sports`), that single stage
measured 940 ms (35% of `sports_futures`, up to 1.4 s under DB load), while
the underlying Kalshi/Polymarket snapshot writers run at 2-minute (live) to
1-2 hour (catalog) cadences.

Caching ONLY the newest `(outcome_id, last_price)` trade rows per
`(venue, outcome_id)` for 60 seconds (inside the 120-second live-poll cadence)
keeps all six withheld-price verdict arms running fresh on live `FuturesOutcome`
rows while sharing the snapshot read across web dynos, worker prewarms, and
`/api/futures/{id}` detail pages (preserving card-vs-page parity).

Distinction preserved verbatim:
- `[]`     -> no snapshot row exists for `(venue, outcome_id)` (absent from
              `_newest_kalshi_trades` dict; `has_trade_evidence=False`).
- `[None]` -> newest snapshot exists with `last_price IS NULL` (present in
              `_newest_kalshi_trades` dict with value `None`).
- `[0.42]` -> newest snapshot trade price(s).

Kill switches:
- `WITHHELD_TRADES_CACHE_ENABLED=0` disables both L1 and L2 (default ON).
- `WITHHELD_TRADES_CACHE_SHARED_ENABLED=0` disables Redis L2 only (default ON).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Sequence

logger = logging.getLogger(__name__)

WITHHELD_TRADES_CACHE_ENV = "WITHHELD_TRADES_CACHE_ENABLED"
WITHHELD_TRADES_CACHE_SHARED_ENV = "WITHHELD_TRADES_CACHE_SHARED_ENABLED"
WITHHELD_TRADES_CACHE_TTL_SECONDS = 60.0
_L1_MAX_ENTRIES = 8192
_L2_PREFIX = "withheld_trades:v1"

_l1_lock = threading.Lock()
_l1_cache: OrderedDict[tuple[int, str, int], tuple[float, list[float | None]]] = (
    OrderedDict()
)


def clear_withheld_trades_cache() -> None:
    """Clear the process-local L1 cache (tests)."""
    with _l1_lock:
        _l1_cache.clear()


def withheld_trades_cache_enabled() -> bool:
    raw = os.environ.get(WITHHELD_TRADES_CACHE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def withheld_trades_cache_shared_enabled() -> bool:
    raw = os.environ.get(WITHHELD_TRADES_CACHE_SHARED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _l1_get(engine_key: int, venue: str, outcome_id: int) -> list[float | None] | None:
    now_mono = time.monotonic()
    key = (engine_key, venue, outcome_id)
    with _l1_lock:
        entry = _l1_cache.get(key)
        if entry is None:
            return None
        expires_at, prices = entry
        if now_mono >= expires_at:
            _l1_cache.pop(key, None)
            return None
        _l1_cache.move_to_end(key)
        return list(prices)


def _l1_set_many(
    engine_key: int, venue: str, by_outcome: dict[int, list[float | None]]
) -> None:
    if not by_outcome:
        return
    expires_at = time.monotonic() + WITHHELD_TRADES_CACHE_TTL_SECONDS
    with _l1_lock:
        for oid, prices in by_outcome.items():
            key = (engine_key, venue, oid)
            _l1_cache[key] = (expires_at, list(prices))
            _l1_cache.move_to_end(key)
        while len(_l1_cache) > _L1_MAX_ENTRIES:
            _l1_cache.popitem(last=False)


def _l2_key(venue: str, outcome_id: int) -> str:
    return f"{_L2_PREFIX}:{venue}:{outcome_id}"


def _decode_prices(raw: Any) -> list[float | None] | None:
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, list):
        return None
    out: list[float | None] = []
    for item in parsed:
        if item is None:
            out.append(None)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            out.append(float(item))
        else:
            return None
    return out


async def _shared_redis():
    if not withheld_trades_cache_shared_enabled():
        return None
    try:
        from app.utils.redis_client import get_shared_async_redis

        return await get_shared_async_redis()
    except Exception:
        return None


async def resolve_cached_venue_trades(
    venue: str,
    outcome_ids: Sequence[int],
    *,
    engine_key: int = 0,
) -> tuple[dict[int, list[float | None]], list[int]]:
    """Return ``(hits, missed_ids)`` from L1 + Redis L2 for ``(venue, outcome_ids)``."""
    unique_ids = sorted({int(oid) for oid in outcome_ids})
    if not unique_ids or not withheld_trades_cache_enabled():
        return {}, unique_ids

    hits: dict[int, list[float | None]] = {}
    l1_misses: list[int] = []
    for oid in unique_ids:
        cached = _l1_get(engine_key, venue, oid)
        if cached is not None:
            hits[oid] = cached
        else:
            l1_misses.append(oid)

    if not l1_misses:
        return hits, []

    client = await _shared_redis()
    if client is None:
        return hits, l1_misses

    try:
        from app.utils.request_cache import bounded_redis_call

        keys = [_l2_key(venue, oid) for oid in l1_misses]
        res = await bounded_redis_call(
            lambda: client.mget(keys),
            treat_none_as_miss=False,
        )
        raw_vals = res.value if res.is_ok and isinstance(res.value, (list, tuple)) else None
    except Exception:
        logger.debug("withheld_trades_cache L2 read failed", exc_info=True)
        raw_vals = None

    if not raw_vals or len(raw_vals) != len(l1_misses):
        return hits, l1_misses

    l2_hits: dict[int, list[float | None]] = {}
    still_missed: list[int] = []
    for oid, raw in zip(l1_misses, raw_vals):
        decoded = _decode_prices(raw)
        if decoded is not None:
            hits[oid] = decoded
            l2_hits[oid] = decoded
        else:
            still_missed.append(oid)

    if l2_hits:
        _l1_set_many(engine_key, venue, l2_hits)
    return hits, still_missed


async def store_cached_venue_trades(
    venue: str,
    queried_ids: Sequence[int],
    fetched_rows: Sequence[tuple[int, Any]],
    *,
    engine_key: int = 0,
) -> None:
    """Populate L1 and Redis L2 from fresh DB ``(outcome_id, last_price)`` rows."""
    if not queried_ids or not withheld_trades_cache_enabled():
        return

    grouped: dict[int, list[float | None]] = {int(oid): [] for oid in queried_ids}
    for oid, price in fetched_rows:
        oid_int = int(oid)
        if oid_int not in grouped:
            continue
        grouped[oid_int].append(float(price) if price is not None else None)

    _l1_set_many(engine_key, venue, grouped)

    client = await _shared_redis()
    if client is None:
        return

    try:
        from app.utils.request_cache import bounded_redis_call

        ttl = int(WITHHELD_TRADES_CACHE_TTL_SECONDS)

        async def _write_pipeline() -> None:
            pipe = client.pipeline(transaction=False)
            for oid, prices in grouped.items():
                pipe.setex(_l2_key(venue, oid), ttl, json.dumps(prices))
            await pipe.execute()

        await bounded_redis_call(_write_pipeline, treat_none_as_miss=False)
    except Exception:
        logger.debug("withheld_trades_cache L2 write failed", exc_info=True)
