"""Response cache and real-PG detection for ``GET /api/teams/{identifier}`` (#13573)."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

logger = logging.getLogger(__name__)

TEAM_PAGE_TTL_LIVE_SECONDS = 15
TEAM_PAGE_TTL_DEFAULT_SECONDS = 60
TEAM_PAGE_L1_MAX_SIZE = 256
TEAM_PAGE_REDIS_PREFIX = "bainluck:team_page:v1:"
TEAM_PAGE_REDIS_DEADLINE_MS = 250

_l1_lock = threading.Lock()
_l1_cache: OrderedDict[tuple[int, str], tuple[float, dict]] = OrderedDict()
_inflight_locks: dict[tuple[int, int, str], asyncio.Lock] = {}


def is_real_pg_engine(db: Any) -> bool:
    """True only for real AsyncSessions backed by a PostgreSQL engine pool.

    Excludes SQLite sessions, MagicMock objects, and unit-test SimpleNamespace
    bind stubs that lack a SQLAlchemy ``pool``.
    """
    if not isinstance(db, AsyncSession):
        return False
    try:
        bind = db.get_bind()
    except Exception:
        return False
    return (
        getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"
        and getattr(bind, "pool", None) is not None
    )


def cache_scope_key(db: Any) -> int:
    """Return a process-local engine scope key (falls back to session id)."""
    if isinstance(db, AsyncSession):
        try:
            bind = db.get_bind()
            if bind is not None:
                return id(bind)
        except Exception:
            return id(db)
    return id(db)


def normalize_team_cache_id(identifier: str) -> str:
    """Normalize team slug/id key for response caching."""
    return identifier.strip().lower()


def ttl_for_team_payload(resp: dict) -> int:
    """Use 15s TTL while any upcoming fixture is live; 60s otherwise."""
    if any(
        isinstance(ev, dict) and ev.get("status") == "live"
        for ev in (resp.get("upcoming_events") or ())
    ):
        return TEAM_PAGE_TTL_LIVE_SECONDS
    return TEAM_PAGE_TTL_DEFAULT_SECONDS


def clear_team_page_l1_cache() -> None:
    """Clear the process-local L1 cache (for tests/benchmarks)."""
    with _l1_lock:
        _l1_cache.clear()


def get_inflight_lock(scope_key: int, norm_id: str) -> asyncio.Lock:
    """Loop-bound per-(scope, identifier) singleflight lock."""
    loop_key = (id(asyncio.get_running_loop()), scope_key, norm_id)
    lock = _inflight_locks.get(loop_key)
    if lock is None:
        if len(_inflight_locks) > 512:
            for k in [kk for kk, lk in _inflight_locks.items() if not lk.locked()][:256]:
                _inflight_locks.pop(k, None)
        lock = asyncio.Lock()
        _inflight_locks[loop_key] = lock
    return lock


def _store_l1(key: tuple[int, str], expires_at: float, payload: dict) -> None:
    copied = copy.deepcopy(payload)
    with _l1_lock:
        _l1_cache[key] = (expires_at, copied)
        _l1_cache.move_to_end(key)
        while len(_l1_cache) > TEAM_PAGE_L1_MAX_SIZE:
            _l1_cache.popitem(last=False)


async def read_team_page_cache(scope_key: int, norm_id: str) -> dict | None:
    """Read team page payload from L1 or shared Redis (fail-open on errors)."""
    key = (scope_key, norm_id)
    now_mono = time.monotonic()
    with _l1_lock:
        entry = _l1_cache.get(key)
        if entry is not None:
            expires_at, cached = entry
            if expires_at > now_mono:
                _l1_cache.move_to_end(key)
                return copy.deepcopy(cached)
            _l1_cache.pop(key, None)

    if not os.getenv("REDIS_URL", "").strip():
        return None

    try:
        client = await get_shared_async_redis()
        redis_key = f"{TEAM_PAGE_REDIS_PREFIX}{norm_id}"
        res = await bounded_redis_call(
            lambda: client.get(redis_key),
            deadline_ms=TEAM_PAGE_REDIS_DEADLINE_MS,
        )
    except Exception:
        logger.debug("team page cache redis read failed", exc_info=True)
        return None

    if not res.is_ok or not res.value:
        return None

    try:
        envelope = json.loads(res.value)
    except Exception:
        logger.debug("team page cache decode failed", exc_info=True)
        return None

    if not isinstance(envelope, dict):
        return None
    ts = envelope.get("ts")
    ttl = envelope.get("ttl")
    payload = envelope.get("payload")
    if (
        not isinstance(ts, (int, float))
        or not isinstance(ttl, (int, float))
        or not isinstance(payload, dict)
    ):
        return None

    rem = (float(ts) + float(ttl)) - time.time()
    if rem <= 0:
        return None

    _store_l1(key, time.monotonic() + rem, payload)
    return copy.deepcopy(payload)


async def write_team_page_cache(
    scope_key: int,
    norm_id: str,
    payload: dict,
    *,
    max_expires_at: float | None = None,
    oldest_source_ts: float | None = None,
) -> None:
    """Write team page payload to L1 and shared Redis, clamped to piece freshness."""
    base_ttl = float(ttl_for_team_payload(payload))
    now_wall = time.time()
    eff_expires_at = now_wall + base_ttl
    if max_expires_at is not None:
        eff_expires_at = min(eff_expires_at, float(max_expires_at))
    elif oldest_source_ts is not None:
        eff_expires_at = min(eff_expires_at, float(oldest_source_ts) + base_ttl)
    rem = min(base_ttl, eff_expires_at - now_wall)
    if rem <= 0.0:
        return

    key = (scope_key, norm_id)
    _store_l1(key, time.monotonic() + rem, payload)

    if not os.getenv("REDIS_URL", "").strip():
        return

    try:
        encoded = json.dumps(
            {"ts": now_wall, "ttl": rem, "payload": payload},
            default=str,
        )
        redis_ttl = max(1, int(math.ceil(rem)))
        client = await get_shared_async_redis()
        redis_key = f"{TEAM_PAGE_REDIS_PREFIX}{norm_id}"
        await bounded_redis_call(
            lambda: client.setex(redis_key, redis_ttl, encoded),
            deadline_ms=TEAM_PAGE_REDIS_DEADLINE_MS,
        )
    except Exception:
        logger.debug("team page cache redis write failed", exc_info=True)
