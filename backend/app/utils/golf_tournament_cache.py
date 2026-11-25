"""Per-tournament detail cache with SWR background refresh and singleflight (#13436).

Serves ``GET /api/golf/tournaments/{slug}`` and ``GolfEventAdapter`` without
forcing readers to wait on 10–50 s cold builds during live rounds while strictly
preserving the CERT-686 freshness bar:

* Never reads the hourly ``bainluck:category:golf`` key (`get_golf_cached`).
* Uses a dedicated freshness-tagged envelope in Redis (``bainluck:golf:tournament:v1:{slug}``)
  plus a durable ``:last_good`` floor and bounded per-worker L0 cache.
* While a tournament is in progress, background warmers (every 90 s DataGolf
  in-play poll and hourly category precompute) publish fresh copies proactively;
  on expiry within the last-good window, readers receive ``stale_hit`` at once
  and trigger at most one asynchronous background rebuild.
* On genuine cold misses, per-slug singleflight coalesces concurrent callers onto
  one build.
* Evolution-market richness selection (only used when no winner outcome is graded)
  is also memoized briefly in-process so fallback rebuilds do not re-count
  snapshots on every request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.utils import request_cache as _rc

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

FRESH_KEY_PREFIX = "bainluck:golf:tournament:v1:"
LAST_GOOD_SUFFIX = ":last_good"

#: Live tournaments update via ``poll_datagolf_inplay`` roughly every 90 s.
FRESH_LIVE_SECONDS = 90.0
LAST_GOOD_LIVE_SECONDS = 600.0

#: Non-live (upcoming/settled) tournaments use the 300 s feed freshness bound.
FRESH_IDLE_SECONDS = 300.0
LAST_GOOD_IDLE_SECONDS = 1800.0

#: Redis retention exceeds last-good window so transient Redis restarts recover.
REDIS_FRESH_TTL_SECONDS = 300
REDIS_LAST_GOOD_TTL_SECONDS = 1800

#: Bounded in-process L0 cache (stored as serialized JSON strings -> mutation-safe).
L0_MAX_ENTRIES = 32
L0_MAX_BYTES = 4 * 1024 * 1024
L0_RECHECK_LIVE_SECONDS = 15.0
L0_RECHECK_IDLE_SECONDS = 60.0

#: Bounded in-process memo for ungraded evolution-market snapshot richness.
RICHNESS_CACHE_TTL_SECONDS = 300.0
RICHNESS_CACHE_MAX_ENTRIES = 64

_l0_entries: "OrderedDict[str, tuple[float, float, str, int, bool, str]]" = OrderedDict()
# slug -> (fetched_mono, generated_epoch, raw_payload_json, nbytes, is_live, raw_envelope_json)
_l0_bytes = 0

_richness_cache: "OrderedDict[tuple[int, ...], tuple[float, Optional[int]]]" = OrderedDict()
_inflight: dict[str, tuple[float, "asyncio.Future[dict]"]] = {}
_bg_refresh_tasks: dict[str, "asyncio.Task[None]"] = {}


class _BuildAbandoned(Exception):
    """Internal signal when a singleflight leader is cancelled."""


def _redis_tier_enabled() -> bool:
    raw = os.getenv("GOLF_TOURNAMENT_CACHE_REDIS_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def fresh_redis_key(slug: str) -> str:
    return f"{FRESH_KEY_PREFIX}{slug}"


def last_good_redis_key(slug: str) -> str:
    return f"{FRESH_KEY_PREFIX}{slug}{LAST_GOOD_SUFFIX}"


def is_live_tournament_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    tourn = payload.get("tournament")
    if not isinstance(tourn, dict):
        return False
    return str(tourn.get("schedule_status") or "").strip().lower() == "in-progress"


def freshness_windows(is_live: bool) -> tuple[float, float]:
    if is_live:
        return FRESH_LIVE_SECONDS, LAST_GOOD_LIVE_SECONDS
    return FRESH_IDLE_SECONDS, LAST_GOOD_IDLE_SECONDS


def build_envelope(payload: dict, *, generated_at: Optional[datetime] = None) -> tuple[dict, str, bool]:
    now_dt = generated_at if generated_at is not None else datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    live = is_live_tournament_payload(payload)
    env = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_dt.astimezone(timezone.utc).isoformat(),
        "is_live": live,
        "payload": payload,
    }
    raw = json.dumps(env, default=str)
    return env, raw, live


def _parse_envelope(raw: Any, now_epoch: float) -> Optional[tuple[float, float, dict, bool, str]]:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str) or not raw:
        return None
    try:
        env = json.loads(raw)
    except Exception:
        return None
    if not isinstance(env, dict) or env.get("schema_version") != SCHEMA_VERSION:
        return None
    payload = env.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("tournament"), dict):
        return None
    gen_raw = env.get("generated_at")
    if not isinstance(gen_raw, str):
        return None
    try:
        dt = datetime.fromisoformat(gen_raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    gen_epoch = dt.timestamp()
    age = now_epoch - gen_epoch
    if age < -5.0:
        return None
    live = bool(env.get("is_live")) if "is_live" in env else is_live_tournament_payload(payload)
    _, max_last_good = freshness_windows(live)
    if age > max_last_good:
        return None
    return max(0.0, age), gen_epoch, payload, live, raw


def _l0_drop(slug: str) -> None:
    global _l0_bytes
    old = _l0_entries.pop(slug, None)
    if old is not None:
        _l0_bytes -= old[3]


def _l0_touch(slug: str) -> None:
    entry = _l0_entries.get(slug)
    if entry is None:
        return
    _, gen_epoch, raw_payload, nbytes, is_live, raw_env = entry
    _l0_entries[slug] = (time.monotonic(), gen_epoch, raw_payload, nbytes, is_live, raw_env)
    _l0_entries.move_to_end(slug)


def _l0_store(slug: str, raw_env_json: str, gen_epoch: float, payload: dict, is_live: bool) -> None:
    global _l0_bytes
    raw_payload = json.dumps(payload, default=str)
    nbytes = len(raw_payload.encode("utf-8"))
    if nbytes > L0_MAX_BYTES // 2:
        return
    _l0_drop(slug)
    _l0_entries[slug] = (time.monotonic(), gen_epoch, raw_payload, nbytes, is_live, raw_env_json)
    _l0_bytes += nbytes
    while (_l0_bytes > L0_MAX_BYTES or len(_l0_entries) > L0_MAX_ENTRIES) and _l0_entries:
        oldest_slug = next(iter(_l0_entries))
        _l0_drop(oldest_slug)


def _l0_peek(slug: str, *, allow_stale: bool = False) -> Optional[tuple[dict, str, bool, float]]:
    """Return ``(payload_copy, state, recheck_due, gen_epoch)`` from process L0 if within bounds."""
    entry = _l0_entries.get(slug)
    if entry is None:
        return None
    fetched_mono, gen_epoch, raw_payload, _, is_live, _ = entry
    now_epoch = time.time()
    age = now_epoch - gen_epoch
    fresh_s, last_good_s = freshness_windows(is_live)
    if age < -5.0 or age > last_good_s:
        _l0_drop(slug)
        return None
    recheck_s = L0_RECHECK_LIVE_SECONDS if is_live else L0_RECHECK_IDLE_SECONDS
    recheck_due = (time.monotonic() - fetched_mono) >= recheck_s
    if age <= fresh_s:
        _l0_entries.move_to_end(slug)
        return json.loads(raw_payload), "hit", recheck_due, gen_epoch
    if allow_stale:
        _l0_entries.move_to_end(slug)
        return json.loads(raw_payload), "stale_hit", True, gen_epoch
    return None


def _read_from_redis_sync_or_none(redis_conn, slug: str) -> Optional[tuple[dict, str]]:
    """Decode fresh or last-good Redis value synchronously (for sync Celery helpers)."""
    now_epoch = time.time()
    for key in (fresh_redis_key(slug), last_good_redis_key(slug)):
        raw = redis_conn.get(key)
        parsed = _parse_envelope(raw, now_epoch)
        if parsed is None:
            continue
        age, _, payload, is_live, _ = parsed
        fresh_s, _ = freshness_windows(is_live)
        state = "hit" if age <= fresh_s else "stale_hit"
        return payload, state
    return None


async def _read_from_redis_async(
    slug: str, *, min_gen_epoch: Optional[float] = None
) -> Optional[tuple[dict, str, float]]:
    if not _redis_tier_enabled():
        return None
    try:
        redis_conn = await _rc.get_shared_async_redis()
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    if redis_conn is None:
        return None
    now_epoch = time.time()
    result = await _rc.bounded_redis_call(
        lambda: redis_conn.mget([fresh_redis_key(slug), last_good_redis_key(slug)])
    )
    if not result.is_ok or not result.value:
        return None
    vals = result.value
    best_parsed = None
    for raw in vals:
        parsed = _parse_envelope(raw, now_epoch)
        if parsed is None:
            continue
        if best_parsed is None or parsed[1] > best_parsed[1]:
            best_parsed = parsed
    if best_parsed is None:
        return None
    age, gen_epoch, payload, is_live, raw_env = best_parsed
    if min_gen_epoch is not None and gen_epoch < min_gen_epoch:
        return None
    fresh_s, _ = freshness_windows(is_live)
    _l0_store(slug, raw_env, gen_epoch, payload, is_live)
    return json.loads(json.dumps(payload, default=str)), ("hit" if age <= fresh_s else "stale_hit"), gen_epoch


async def publish_tournament_payload_async(
    slug: str, payload: dict, *, generated_at: Optional[datetime] = None
) -> bool:
    """Publish one built tournament detail dict to process L0 and Redis."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tournament"), dict):
        return False
    now_dt = generated_at if generated_at is not None else datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    _, raw_env, live = build_envelope(payload, generated_at=now_dt)
    _l0_store(slug, raw_env, now_dt.timestamp(), payload, live)
    if not _redis_tier_enabled():
        return False
    try:
        redis_conn = await _rc.get_shared_async_redis()
        if redis_conn is None:
            return False
        pipe = redis_conn.pipeline(transaction=False)
        pipe.set(fresh_redis_key(slug), raw_env, ex=REDIS_FRESH_TTL_SECONDS)
        pipe.set(last_good_redis_key(slug), raw_env, ex=REDIS_LAST_GOOD_TTL_SECONDS)
        res = await _rc.bounded_redis_call(lambda: pipe.execute())
        return res.is_ok
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


def publish_tournament_payload_sync(
    slug: str,
    payload: dict,
    *,
    redis_client: Any = None,
    generated_at: Optional[datetime] = None,
) -> bool:
    """Synchronous publish variant for Celery tasks holding a sync Redis client."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tournament"), dict):
        return False
    now_dt = generated_at if generated_at is not None else datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    _, raw_env, live = build_envelope(payload, generated_at=now_dt)
    _l0_store(slug, raw_env, now_dt.timestamp(), payload, live)
    if redis_client is None:
        return False
    try:
        pipe = redis_client.pipeline(transaction=False)
        pipe.set(fresh_redis_key(slug), raw_env, ex=REDIS_FRESH_TTL_SECONDS)
        pipe.set(last_good_redis_key(slug), raw_env, ex=REDIS_LAST_GOOD_TTL_SECONDS)
        pipe.execute()
        return True
    except Exception:
        return False


def _trigger_bg_refresh(slug: str, bg_builder: Optional[Callable[[], Awaitable[dict]]]) -> None:
    """Kick off at most one detached background rebuild per slug for stale SWR hits."""
    if bg_builder is None:
        return
    existing = _bg_refresh_tasks.get(slug)
    if existing is not None and not existing.done():
        return

    async def _runner() -> None:
        try:
            payload = await bg_builder()
            if isinstance(payload, dict):
                await publish_tournament_payload_async(slug, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Golf tournament SWR background refresh failed", exc_info=True)
        finally:
            if _bg_refresh_tasks.get(slug) is task:
                _bg_refresh_tasks.pop(slug, None)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_runner())
    _bg_refresh_tasks[slug] = task


async def _singleflight_build(
    slug: str,
    builder: Callable[[], Awaitable[dict]],
    *,
    asked_at: Optional[float] = None,
) -> tuple[dict, str]:
    while True:
        inflight = _inflight.get(slug)
        if inflight is None:
            break
        started_at, shared = inflight
        if asked_at is not None and started_at <= asked_at:
            # A caller requesting fresh=True waits for a strictly newer build if
            # one was started later, otherwise starts its own after current finishes.
            try:
                await asyncio.shield(shared)
            except Exception:
                logger.debug("Prior in-flight golf tournament build failed before fresh bypass")
            if _inflight.get(slug, (None, None))[1] is shared:
                continue
            continue
        try:
            payload = await asyncio.shield(shared)
            return json.loads(json.dumps(payload, default=str)), "coalesced"
        except _BuildAbandoned:
            continue

    started_at = time.monotonic()
    shared: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
    shared.add_done_callback(lambda f: f.cancelled() or f.exception())
    _inflight[slug] = (started_at, shared)
    try:
        payload = await builder()
        if isinstance(payload, dict) and isinstance(payload.get("tournament"), dict):
            await publish_tournament_payload_async(slug, payload)
    except Exception as exc:
        if _inflight.get(slug, (None, None))[1] is shared:
            _inflight.pop(slug, None)
        if not shared.done():
            shared.set_exception(exc)
        raise
    except BaseException:
        if _inflight.get(slug, (None, None))[1] is shared:
            _inflight.pop(slug, None)
        if not shared.done():
            shared.set_exception(_BuildAbandoned())
        raise
    if _inflight.get(slug, (None, None))[1] is shared:
        _inflight.pop(slug, None)
    if not shared.done():
        shared.set_result(payload)
    return json.loads(json.dumps(payload, default=str)), ("bypass" if asked_at is not None else "miss")


async def get_or_build(
    slug: str,
    *,
    builder: Callable[[], Awaitable[dict]],
    bg_builder: Optional[Callable[[], Awaitable[dict]]] = None,
    fresh: bool = False,
) -> tuple[dict, str]:
    """Return ``(payload_dict, cache_state)`` where state is hit/stale_hit/coalesced/miss/bypass."""
    if fresh:
        return await _singleflight_build(slug, builder, asked_at=time.monotonic())

    l0 = _l0_peek(slug, allow_stale=False)
    if l0 is not None:
        payload, state, recheck_due, l0_gen_epoch = l0
        if not recheck_due:
            return payload, state
        # L0 throttle expired: check Redis quickly in case background worker updated it,
        # without ever rolling L0 back to an older Redis envelope.
        redis_hit = await _read_from_redis_async(slug, min_gen_epoch=l0_gen_epoch)
        if redis_hit is not None:
            r_payload, r_state, _ = redis_hit
            if r_state == "stale_hit":
                _trigger_bg_refresh(slug, bg_builder)
            return r_payload, r_state
        _l0_touch(slug)
        return payload, state

    redis_hit = await _read_from_redis_async(slug)
    if redis_hit is not None:
        r_payload, r_state, _ = redis_hit
        if r_state == "stale_hit":
            _trigger_bg_refresh(slug, bg_builder)
        return r_payload, r_state

    # Check if L0 has a stale-but-valid last-good copy (e.g. Redis disabled/unreachable).
    l0_stale = _l0_peek(slug, allow_stale=True)
    if l0_stale is not None:
        s_payload, s_state, _, _ = l0_stale
        _trigger_bg_refresh(slug, bg_builder)
        return s_payload, s_state

    return await _singleflight_build(slug, builder)


def get_cached_richness_pick(eligible_ids: list[int]) -> tuple[bool, Optional[int]]:
    """Return ``(found, market_id)`` from bounded 300 s richness memo."""
    key = tuple(eligible_ids)
    item = _richness_cache.get(key)
    if item is None:
        return False, None
    ts, market_id = item
    if (time.monotonic() - ts) >= RICHNESS_CACHE_TTL_SECONDS:
        _richness_cache.pop(key, None)
        return False, None
    _richness_cache.move_to_end(key)
    return True, market_id


def set_cached_richness_pick(eligible_ids: list[int], market_id: Optional[int]) -> None:
    key = tuple(eligible_ids)
    _richness_cache.pop(key, None)
    _richness_cache[key] = (time.monotonic(), market_id)
    while len(_richness_cache) > RICHNESS_CACHE_MAX_ENTRIES:
        _richness_cache.popitem(last=False)


def _reset_for_tests() -> None:
    global _l0_bytes
    _l0_entries.clear()
    _l0_bytes = 0
    _richness_cache.clear()
    _inflight.clear()
    for task in list(_bg_refresh_tasks.values()):
        try:
            task.cancel()
        except RuntimeError:
            logger.debug("Skipping golf background refresh task cancel on closed loop")
    _bg_refresh_tasks.clear()
