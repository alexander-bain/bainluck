"""Bounded L1 + Redis L2 shared caches for ``_query_team_futures`` (#13762).

Eliminates repeated cold DB work across clubs sharing league futures boards,
multiple web workers/dynos, and the sibling ``/api/me/team-futures`` and
``/api/shared/team-futures`` endpoints while keeping freshness within the #13741
ceilings: 60 s for season/award futures (including season rows on a playing
club's page), 15 s when a market is linked to an event, and team page response
caching clamped to the earliest remaining piece expiry.

Active ONLY for real PostgreSQL ``AsyncSession`` callers
(``team_page_cache.is_real_pg_engine`` checks live in ``routes/user.py``), and
gated by ``TEAM_FUTURES_SHARED_CACHE_ENABLED`` (default ``"1"``). All Redis I/O
reuses ``get_shared_async_redis`` + ``bounded_redis_call`` so missing or slow
Redis degrades transparently to cold DB reads without opening new pools.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Sequence

from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

logger = logging.getLogger(__name__)

TEAM_FUTURES_SHARED_CACHE_ENV = "TEAM_FUTURES_SHARED_CACHE_ENABLED"
AWARD_Q2_TTL_SECONDS = 60.0
MARKET_CACHE_TTL_SEASON_SECONDS = 60.0
MARKET_CACHE_TTL_EVENT_SECONDS = 15.0
TEAM_FUTURES_REDIS_DEADLINE_MS = 250

_AWARD_Q2_L2_KEY = "team_futures:award_q2:v1"
_MKT_STATS_L2_PREFIX = "team_futures:mkt_stats:v1:"
_MKT_SCREEN_L2_PREFIX = "team_futures:mkt_screen:v1:"

_L1_MARKET_MAX_ENTRIES = 4096

_l1_lock = threading.Lock()
_l1_stats: OrderedDict[tuple[int, int], tuple[float, int, float | None, float]] = OrderedDict()
_l1_screen: OrderedDict[tuple[int, int], tuple[float, frozenset[int], float]] = OrderedDict()


def team_futures_shared_cache_enabled() -> bool:
    """Global kill switch for Part 2 shared ``_query_team_futures`` caches."""
    raw = os.environ.get(TEAM_FUTURES_SHARED_CACHE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _redis_configured() -> bool:
    return bool(os.getenv("REDIS_URL", "").strip())


def clear_team_futures_shared_cache() -> None:
    """Clear process-local L1 market stats and screen caches (tests)."""
    with _l1_lock:
        _l1_stats.clear()
        _l1_screen.clear()


def _stats_l2_key(market_id: int) -> str:
    return f"{_MKT_STATS_L2_PREFIX}{int(market_id)}"


def _screen_l2_key(market_id: int) -> str:
    return f"{_MKT_SCREEN_L2_PREFIX}{int(market_id)}"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _serialize_award_rows(rows: Sequence[tuple[Any, Any, Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for o, m, sk in rows:
        res_date = getattr(m, "resolution_date", None)
        res_iso = res_date.isoformat() if isinstance(res_date, datetime) else res_date
        o_dict = {
            "id": o.id,
            "market_id": o.market_id,
            "external_id": getattr(o, "external_id", None),
            "name": o.name,
            "team_id": o.team_id,
            "current_probability": o.current_probability,
            "probability_change_24h": o.probability_change_24h,
            "current_yes_bid": getattr(o, "current_yes_bid", None),
            "current_yes_ask": getattr(o, "current_yes_ask", None),
            "rank": o.rank,
            "is_winner": o.is_winner,
            "resolution_source": getattr(o, "resolution_source", None),
        }
        m_dict = {
            "id": m.id,
            "source": m.source,
            "external_id": getattr(m, "external_id", None),
            "sport_id": getattr(m, "sport_id", None),
            "event_id": getattr(m, "event_id", None),
            "name": m.name,
            "llm_sport_category": m.llm_sport_category,
            "market_tier": m.market_tier,
            "market_type": getattr(m, "market_type", None),
            "status": getattr(m, "status", "open"),
            "resolution_date": res_iso,
            "canonical_market_key": m.canonical_market_key,
            "market_metadata": getattr(m, "market_metadata", None),
        }
        out.append([o_dict, m_dict, sk])
    return out


def _deserialize_award_rows(encoded_rows: Any) -> list[tuple[SimpleNamespace, SimpleNamespace, Any]] | None:
    if not isinstance(encoded_rows, list):
        return None
    out: list[tuple[SimpleNamespace, SimpleNamespace, Any]] = []
    for entry in encoded_rows:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            return None
        o_dict, m_dict, sk = entry
        if not isinstance(o_dict, dict) or not isinstance(m_dict, dict):
            return None
        m_copy = dict(m_dict)
        res_raw = m_copy.get("resolution_date")
        if isinstance(res_raw, str):
            try:
                m_copy["resolution_date"] = datetime.fromisoformat(res_raw)
            except ValueError:
                return None
        elif res_raw is not None and not isinstance(res_raw, datetime):
            return None
        out.append((SimpleNamespace(**o_dict), SimpleNamespace(**m_copy), sk))
    return out


async def read_award_outcomes_cache(scope_key: int) -> tuple[float, list[tuple[SimpleNamespace, SimpleNamespace, Any]]] | None:
    """Read shared ``q2`` award snapshot from Redis L2 if fresh within 60 s."""
    del scope_key  # Single Postgres DB backs Redis L2 across workers.
    if not team_futures_shared_cache_enabled() or not _redis_configured():
        return None
    try:
        client = await get_shared_async_redis()
        res = await bounded_redis_call(
            lambda: client.get(_AWARD_Q2_L2_KEY),
            deadline_ms=TEAM_FUTURES_REDIS_DEADLINE_MS,
        )
    except Exception:
        logger.debug("team_futures q2 L2 read failed", exc_info=True)
        return None
    if not res.is_ok or res.value is None:
        return None
    try:
        text = res.value.decode("utf-8") if isinstance(res.value, (bytes, bytearray)) else str(res.value)
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    ts = parsed.get("ts")
    if not isinstance(ts, (int, float)):
        return None
    age = time.time() - float(ts)
    if age < 0.0:
        age = 0.0
    if age >= AWARD_Q2_TTL_SECONDS:
        return None
    rows = _deserialize_award_rows(parsed.get("rows"))
    if rows is None:
        return None
    return float(ts), rows


async def write_award_outcomes_cache(
    scope_key: int,
    wall_ts: float,
    rows: Sequence[tuple[Any, Any, Any]],
) -> None:
    """Publish ``q2`` award snapshot to Redis L2 with a 60 s expiry."""
    del scope_key
    if not team_futures_shared_cache_enabled() or not _redis_configured():
        return
    try:
        payload = json.dumps(
            {"ts": float(wall_ts), "rows": _serialize_award_rows(rows)},
            default=_json_default,
        )
        client = await get_shared_async_redis()
        await bounded_redis_call(
            lambda: client.setex(_AWARD_Q2_L2_KEY, int(AWARD_Q2_TTL_SECONDS), payload),
            deadline_ms=TEAM_FUTURES_REDIS_DEADLINE_MS,
            treat_none_as_miss=False,
        )
    except Exception:
        logger.debug("team_futures q2 L2 write failed", exc_info=True)


def _l1_get_stats_and_screen(
    scope_key: int,
    market_ids: Sequence[int],
    *,
    include_screen: bool,
) -> tuple[dict[int, tuple[int, float | None, float]], dict[int, tuple[set[int], float]]]:
    now_mono = time.monotonic()
    stats_hits: dict[int, tuple[int, float | None, float]] = {}
    screen_hits: dict[int, tuple[set[int], float]] = {}
    with _l1_lock:
        for mid in market_ids:
            key = (scope_key, mid)
            s_entry = _l1_stats.get(key)
            if s_entry is not None:
                expires_at, tot, fsum, written_at = s_entry
                if now_mono < expires_at:
                    _l1_stats.move_to_end(key)
                    stats_hits[mid] = (tot, fsum, written_at)
                else:
                    _l1_stats.pop(key, None)
            if include_screen:
                sc_entry = _l1_screen.get(key)
                if sc_entry is not None:
                    expires_at, withheld_fs, written_at = sc_entry
                    if now_mono < expires_at:
                        _l1_screen.move_to_end(key)
                        screen_hits[mid] = (set(withheld_fs), written_at)
                    else:
                        _l1_screen.pop(key, None)
    return stats_hits, screen_hits


def _l1_set_market_entries(
    scope_key: int,
    *,
    stats_entries: dict[int, tuple[int, float | None, float, float]],
    screen_entries: dict[int, tuple[set[int], float, float]],
) -> None:
    if not stats_entries and not screen_entries:
        return
    now_mono = time.monotonic()
    with _l1_lock:
        for mid, (tot, fsum, written_at, ttl_rem) in stats_entries.items():
            if ttl_rem <= 0.0:
                continue
            key = (scope_key, mid)
            _l1_stats[key] = (now_mono + ttl_rem, int(tot), fsum, float(written_at))
            _l1_stats.move_to_end(key)
        while len(_l1_stats) > _L1_MARKET_MAX_ENTRIES:
            _l1_stats.popitem(last=False)

        for mid, (withheld_ids, written_at, ttl_rem) in screen_entries.items():
            if ttl_rem <= 0.0:
                continue
            key = (scope_key, mid)
            _l1_screen[key] = (now_mono + ttl_rem, frozenset(withheld_ids), float(written_at))
            _l1_screen.move_to_end(key)
        while len(_l1_screen) > _L1_MARKET_MAX_ENTRIES:
            _l1_screen.popitem(last=False)


def _decode_json_list(raw: Any) -> list[Any] | None:
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, list) else None


async def read_market_stats_and_screen(
    scope_key: int,
    market_ids: Sequence[int],
    *,
    include_screen: bool,
) -> tuple[dict[int, tuple[int, float | None, float]], dict[int, tuple[set[int], float]]]:
    """Resolve cached per-market ``stats`` and ``screen`` verdicts (L1 + single ``MGET``)."""
    unique_ids = list(dict.fromkeys(int(m) for m in market_ids))
    if not unique_ids or not team_futures_shared_cache_enabled():
        return {}, {}

    stats_hits, screen_hits = _l1_get_stats_and_screen(
        scope_key, unique_ids, include_screen=include_screen
    )
    missing_stats = [mid for mid in unique_ids if mid not in stats_hits]
    missing_screen = (
        [mid for mid in unique_ids if mid not in screen_hits] if include_screen else []
    )
    if (not missing_stats and not missing_screen) or not _redis_configured():
        return stats_hits, screen_hits

    keys = [_stats_l2_key(mid) for mid in missing_stats] + [
        _screen_l2_key(mid) for mid in missing_screen
    ]
    try:
        client = await get_shared_async_redis()
        res = await bounded_redis_call(
            lambda: client.mget(keys),
            deadline_ms=TEAM_FUTURES_REDIS_DEADLINE_MS,
            treat_none_as_miss=False,
        )
    except Exception:
        logger.debug("team_futures market L2 mget failed", exc_info=True)
        return stats_hits, screen_hits

    if not res.is_ok or not isinstance(res.value, (list, tuple)) or len(res.value) != len(keys):
        return stats_hits, screen_hits

    now_wall = time.time()
    n_stats = len(missing_stats)
    l1_stats_fill: dict[int, tuple[int, float | None, float, float]] = {}
    l1_screen_fill: dict[int, tuple[set[int], float, float]] = {}

    for mid, raw in zip(missing_stats, res.value[:n_stats]):
        parsed = _decode_json_list(raw)
        if not parsed or len(parsed) != 4:
            continue
        tot, fsum, written_at, entry_ttl = parsed
        if (
            isinstance(tot, bool)
            or not isinstance(tot, int)
            or isinstance(written_at, bool)
            or not isinstance(written_at, (int, float))
            or isinstance(entry_ttl, bool)
            or not isinstance(entry_ttl, (int, float))
        ):
            continue
        if fsum is not None and (isinstance(fsum, bool) or not isinstance(fsum, (int, float))):
            continue
        age = max(0.0, now_wall - float(written_at))
        rem_ttl = float(entry_ttl) - age
        if rem_ttl <= 0.0:
            continue
        fsum_val = float(fsum) if fsum is not None else None
        stats_hits[mid] = (tot, fsum_val, float(written_at))
        l1_stats_fill[mid] = (tot, fsum_val, float(written_at), min(rem_ttl, float(entry_ttl)))

    for mid, raw in zip(missing_screen, res.value[n_stats:]):
        parsed = _decode_json_list(raw)
        if not parsed or len(parsed) != 3:
            continue
        withheld_list, written_at, entry_ttl = parsed
        if (
            not isinstance(withheld_list, list)
            or isinstance(written_at, bool)
            or not isinstance(written_at, (int, float))
            or isinstance(entry_ttl, bool)
            or not isinstance(entry_ttl, (int, float))
        ):
            continue
        age = max(0.0, now_wall - float(written_at))
        rem_ttl = float(entry_ttl) - age
        if rem_ttl <= 0.0:
            continue
        w_set = {int(x) for x in withheld_list}
        screen_hits[mid] = (w_set, float(written_at))
        l1_screen_fill[mid] = (w_set, float(written_at), min(rem_ttl, float(entry_ttl)))

    _l1_set_market_entries(
        scope_key, stats_entries=l1_stats_fill, screen_entries=l1_screen_fill
    )
    return stats_hits, screen_hits


async def write_market_stats_and_screen(
    scope_key: int,
    *,
    stats_entries: dict[int, tuple[int, float | None, float]],
    screen_entries: dict[int, tuple[set[int], float]],
    ttl_by_mid: dict[int, float],
) -> None:
    """Publish per-market ``stats`` and sound ``screen`` verdicts (L1 + single pipeline)."""
    if not team_futures_shared_cache_enabled():
        return
    if not stats_entries and not screen_entries:
        return

    l1_stats_fill: dict[int, tuple[int, float | None, float, float]] = {}
    l1_screen_fill: dict[int, tuple[set[int], float, float]] = {}
    for mid, (tot, fsum, written_at) in stats_entries.items():
        ttl = float(ttl_by_mid.get(mid, MARKET_CACHE_TTL_SEASON_SECONDS))
        if ttl > 0.0:
            l1_stats_fill[mid] = (int(tot), fsum, float(written_at), ttl)
    for mid, (w_set, written_at) in screen_entries.items():
        ttl = float(ttl_by_mid.get(mid, MARKET_CACHE_TTL_SEASON_SECONDS))
        if ttl > 0.0:
            l1_screen_fill[mid] = (set(w_set), float(written_at), ttl)

    _l1_set_market_entries(
        scope_key, stats_entries=l1_stats_fill, screen_entries=l1_screen_fill
    )

    if not _redis_configured():
        return
    try:
        client = await get_shared_async_redis()

        async def _write_pipe() -> None:
            pipe = client.pipeline(transaction=False)
            for mid, (tot, fsum, written_at, ttl) in l1_stats_fill.items():
                payload = json.dumps(
                    [tot, fsum, written_at, ttl],
                    default=_json_default,
                )
                pipe.setex(_stats_l2_key(mid), max(1, int(ttl)), payload)
            for mid, (w_set, written_at, ttl) in l1_screen_fill.items():
                payload = json.dumps(
                    [sorted(w_set), written_at, ttl],
                )
                pipe.setex(_screen_l2_key(mid), max(1, int(ttl)), payload)
            await pipe.execute()

        await bounded_redis_call(
            _write_pipe,
            deadline_ms=TEAM_FUTURES_REDIS_DEADLINE_MS,
            treat_none_as_miss=False,
        )
    except Exception:
        logger.debug("team_futures market L2 write failed", exc_info=True)
