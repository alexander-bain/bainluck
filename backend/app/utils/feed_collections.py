"""#9653: published hubs compete with cards on Discover's canonical first page.

The ordinary composed deck supplies relevance and scores. The fixed first-page
window keeps collection membership independent of pagination size and offset.
No reserved slot, score bonus, assembly, or publication decision lives here.
"""

import asyncio
import hashlib
import inspect
import json
import logging
import math
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import container_discovery
from app.utils import request_cache as _rc
from app.utils.container_corrections import PUBLICATION_COLUMN, REVISION_COLUMN

logger = logging.getLogger(__name__)
COLLECTION_READ_BUDGET_SECONDS = 0.25
FINGERPRINT_READ_BUDGET_SECONDS = 0.5
FINGERPRINT_FAILURE_BACKOFF_SECONDS = 5.0
FINGERPRINT_LKG_MAX_AGE_SECONDS = 600.0
FINGERPRINT_FALLBACK_ERROR_LOG_SECONDS = 300.0
FINGERPRINT_REDIS_LKG_KEY = "feed:collections_fingerprint:lkg:v1"
FINGERPRINT_REDIS_LKG_TTL_SECONDS = 600
FINGERPRINT_UNAVAILABLE = "unverified"
_FINGERPRINT_SINGLEFLIGHT_KEY = "feed_collections:fingerprint"

_fingerprint_cache: tuple[float, str] | None = None
_fingerprint_retry_after: float = 0.0
_fingerprint_fallback_since: Optional[float] = None
_fingerprint_fallback_error_logged: bool = False
_fingerprint_source: str = "uninitialized"

#: #10003: what a cached collection-bearing page is keyed on. One row per
#: discoverable published root hub, as ``id:membership_revision``. The revision
#: moves on the hub and every ancestor whenever anything its reader would see
#: changes — publish, withdraw, member correction, assembly — and never moves
#: back, so two different publication states can never share a fingerprint.
_FINGERPRINT_SQL = (
    "SELECT COALESCE(string_agg("
    f"id::text || ':' || {REVISION_COLUMN}::text, ',' ORDER BY id), '') "
    "FROM containers "
    f"WHERE {PUBLICATION_COLUMN} = 'published' "
    "AND parent_container_id IS NULL "
    "AND slug ~ :slug_pattern"
)


def feed_collections_enabled(
    *, mode, include_events, my_teams_only, debug=False, include_futures=True
):
    from app.routes.containers import containers_read_enabled

    # ``include_futures``: collections are a Discover ship, and every Discover
    # request carries futures. An events-only request (the native Sports tab's
    # Live Now / Upcoming backfill, the web Sports finished lookup) renders no
    # collection card on any client, so admitting it only cost it its cache
    # (#10003: 33 ms shared hit → 0.6–3.3 s cold build).
    return (
        (mode or "discover").lower() == "discover"
        and include_events
        and include_futures
        and not my_teams_only
        and not debug
        and container_discovery.container_discovery_enabled()
        and containers_read_enabled()
    )


def _reset_fingerprint_cache_for_tests() -> None:
    """Clear the process-local fingerprint memo, backoff, and fallback state."""
    global _fingerprint_cache, _fingerprint_retry_after
    global _fingerprint_fallback_since, _fingerprint_fallback_error_logged
    global _fingerprint_source
    _fingerprint_cache = None
    _fingerprint_retry_after = 0.0
    _fingerprint_fallback_since = None
    _fingerprint_fallback_error_logged = False
    _fingerprint_source = "uninitialized"


def _is_postgres_async_session(db) -> bool:
    if not isinstance(db, AsyncSession):
        return False
    try:
        bind = db.get_bind()
    except Exception:
        bind = getattr(db, "bind", None)
    return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


async def _read_redis_lkg_fingerprint() -> Optional[tuple[str, float]]:
    """Read durable LKG collection fingerprint + age (s) from Redis, or None."""
    raw = await _rc.read_redis_lkg_text(FINGERPRINT_REDIS_LKG_KEY)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    fp = parsed.get("fp")
    read_at = parsed.get("read_at")
    if (
        not isinstance(fp, str)
        or not fp
        or isinstance(read_at, bool)
        or not isinstance(read_at, (int, float))
        or not math.isfinite(float(read_at))
    ):
        return None
    age = max(0.0, time.time() - float(read_at))
    if age >= FINGERPRINT_LKG_MAX_AGE_SECONDS:
        return None
    return fp, age


def _remember_redis_lkg_fingerprint(fingerprint: str) -> None:
    """Persist healthy fingerprint + wall-clock read timestamp to Redis LKG."""
    if not fingerprint:
        return
    encoded = json.dumps(
        {"v": 1, "fp": fingerprint, "read_at": round(time.time(), 3)},
        separators=(",", ":"),
    )
    _rc.write_redis_lkg_text(
        FINGERPRINT_REDIS_LKG_KEY, FINGERPRINT_REDIS_LKG_TTL_SECONDS, encoded
    )


def _maybe_log_fallback_error(now: float, copy_age: Optional[float]) -> None:
    global _fingerprint_fallback_error_logged
    if (
        _fingerprint_fallback_since is not None
        and not _fingerprint_fallback_error_logged
        and (now - _fingerprint_fallback_since) >= FINGERPRINT_FALLBACK_ERROR_LOG_SECONDS
    ):
        _fingerprint_fallback_error_logged = True
        logger.error(
            "Discover collection fingerprint fallback active for %.0fs (copy_age_s=%s)",
            now - _fingerprint_fallback_since,
            f"{copy_age:.0f}" if copy_age is not None else "none",
        )


async def _fallback_lkg_fingerprint(now: Optional[float] = None) -> Optional[str]:
    """Return unexpired process or Redis LKG (< 10 min), else None."""
    global _fingerprint_cache, _fingerprint_source
    t = time.monotonic() if now is None else float(now)
    if _fingerprint_cache is not None:
        age = max(0.0, t - _fingerprint_cache[0])
        if age < FINGERPRINT_LKG_MAX_AGE_SECONDS:
            if _fingerprint_source != "fallback_redis":
                _fingerprint_source = "fallback_process"
            _maybe_log_fallback_error(t, age)
            return _fingerprint_cache[1]
        _fingerprint_cache = None

    redis_hit = await _read_redis_lkg_fingerprint()
    if redis_hit is not None:
        redis_fp, redis_age = redis_hit
        _fingerprint_cache = (t - redis_age, redis_fp)
        _fingerprint_source = "fallback_redis"
        _maybe_log_fallback_error(t, redis_age)
        return redis_fp

    _fingerprint_source = "fallback_expired"
    _maybe_log_fallback_error(t, None)
    return None


def _record_fingerprint_healthy(fp: str) -> None:
    global _fingerprint_cache, _fingerprint_retry_after
    global _fingerprint_fallback_since, _fingerprint_fallback_error_logged
    global _fingerprint_source
    _fingerprint_cache = (time.monotonic(), fp)
    _fingerprint_retry_after = 0.0
    _fingerprint_fallback_since = None
    _fingerprint_fallback_error_logged = False
    _fingerprint_source = "fresh"


def _record_fingerprint_failed(now_fail: float) -> None:
    global _fingerprint_retry_after, _fingerprint_fallback_since
    _fingerprint_retry_after = now_fail + FINGERPRINT_FAILURE_BACKOFF_SECONDS
    if _fingerprint_fallback_since is None:
        _fingerprint_fallback_since = now_fail


def get_fingerprint_cache_status(*, now: Optional[float] = None) -> dict:
    """Zero-I/O fallback visibility snapshot for ``/api/health``."""
    t = time.monotonic() if now is None else float(now)
    copy_age = (
        max(0.0, t - _fingerprint_cache[0])
        if _fingerprint_cache is not None
        else None
    )
    fallback_duration = (
        max(0.0, t - _fingerprint_fallback_since)
        if _fingerprint_fallback_since is not None
        else None
    )
    if _fingerprint_fallback_since is not None:
        state = (
            "fallback"
            if copy_age is not None and copy_age < FINGERPRINT_LKG_MAX_AGE_SECONDS
            else "fallback_expired"
        )
    elif _fingerprint_source == "fresh" and _fingerprint_cache is not None:
        state = "fresh"
    else:
        state = "uninitialized"
    return {
        "state": state,
        "source": _fingerprint_source,
        "copy_age_seconds": round(copy_age, 1) if copy_age is not None else None,
        "fallback_duration_seconds": (
            round(fallback_duration, 1) if fallback_duration is not None else None
        ),
        "max_age_seconds": FINGERPRINT_LKG_MAX_AGE_SECONDS,
    }


async def feed_collections_cache_fingerprint(
    db, *, max_age_seconds=0.0, budget_seconds: float = FINGERPRINT_READ_BUDGET_SECONDS
):
    """The publication state a collection-bearing page may be cached under, or None.

    #10003 + #13350. ``add_feed_collections`` reads publication on every BUILD;
    this lets a built page be reused while that publication state holds, with
    bounded query timeout, singleflight refresh, 5 s failure backoff, and
    process/Redis last-known-good fallback (capped at 10 min) so a slow or
    failing DB check never switches Discover's cache off.

    When ``max_age_seconds == 0.0`` (default / prewarm / strict tests), no LKG
    fallback is returned on failure, preserving ``None`` -> did not verify.
    """
    global _fingerprint_fallback_since
    now = time.monotonic()
    max_age_seconds = min(max(0.0, float(max_age_seconds)), 5.0)
    timeout_s = max(0.0, float(budget_seconds))

    if max_age_seconds > 0:
        if (
            _fingerprint_cache is not None
            and _fingerprint_source == "fresh"
            and (now - _fingerprint_cache[0]) < max_age_seconds
        ):
            return _fingerprint_cache[1]
        if now < _fingerprint_retry_after:
            return await _fallback_lkg_fingerprint(now)

    async def _query_db() -> Optional[str]:
        if timeout_s <= 0:
            return None
        try:
            if _is_postgres_async_session(db):
                timeout_ms = max(1, int(timeout_s * 1000))
                async def _pg_run():
                    async with db.begin_nested():
                        prev_res = await db.execute(
                            text("SELECT current_setting('statement_timeout')")
                        )
                        prev_timeout = prev_res.scalar() if prev_res is not None else None
                        await db.execute(
                            text("SELECT set_config('statement_timeout', :val, true)"),
                            {"val": f"{timeout_ms}ms"},
                        )
                        raw = (
                            await db.execute(
                                text(_FINGERPRINT_SQL),
                                {"slug_pattern": container_discovery.DISCOVERABLE_SLUG_PATTERN},
                            )
                        ).scalar()
                        await db.execute(
                            text("SELECT set_config('statement_timeout', :val, true)"),
                            {"val": str(prev_timeout) if prev_timeout is not None else "0"},
                        )
                        return raw

                raw = await asyncio.wait_for(_pg_run(), timeout=timeout_s + 0.25)
            else:
                async def _generic_run():
                    begin_nested = getattr(db, "begin_nested", None)
                    cm = begin_nested() if callable(begin_nested) else None
                    if hasattr(cm, "__aenter__") and hasattr(cm, "__aexit__"):
                        async with cm:
                            return (
                                await db.execute(
                                    text(_FINGERPRINT_SQL),
                                    {
                                        "slug_pattern": container_discovery.DISCOVERABLE_SLUG_PATTERN
                                    },
                                )
                            ).scalar()
                    if inspect.iscoroutine(cm):
                        cm.close()
                    return (
                        await db.execute(
                            text(_FINGERPRINT_SQL),
                            {"slug_pattern": container_discovery.DISCOVERABLE_SLUG_PATTERN},
                        )
                    ).scalar()

                raw = await asyncio.wait_for(_generic_run(), timeout=timeout_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            if isinstance(db, AsyncSession) and not db.is_active:
                try:
                    await db.rollback()
                except Exception:
                    logger.debug("Fingerprint rollback failed", exc_info=True)
            logger.warning(
                "Discover collection fingerprint read failed; preserving cache",
                exc_info=True,
            )
            return None
        if not isinstance(raw, str):
            return None
        return hashlib.sha256(f"v1|{raw}".encode()).hexdigest()[:16]

    if max_age_seconds <= 0:
        fp = await _query_db()
        if fp is not None:
            _remember_redis_lkg_fingerprint(fp)
        return fp

    leader, fut = _rc.begin_build(_FINGERPRINT_SINGLEFLIGHT_KEY)
    if not leader:
        try:
            res = await asyncio.wait_for(
                asyncio.shield(fut), timeout=max(0.05, timeout_s + 0.25)
            )
            if res is not None:
                return res
        except asyncio.CancelledError:
            raise
        except Exception:
            # Waiter timed out or leader failed; fall back to LKG.
            pass
        if _fingerprint_fallback_since is None:
            _fingerprint_fallback_since = time.monotonic()
        return await _fallback_lkg_fingerprint()

    try:
        fp = await _query_db()
        if fp is not None:
            _record_fingerprint_healthy(fp)
            _remember_redis_lkg_fingerprint(fp)
            _rc.finish_build(_FINGERPRINT_SINGLEFLIGHT_KEY, fut, result=fp)
            return fp
        now_fail = time.monotonic()
        _record_fingerprint_failed(now_fail)
        fallback = await _fallback_lkg_fingerprint(now_fail)
        _rc.finish_build(_FINGERPRINT_SINGLEFLIGHT_KEY, fut, result=fallback)
        return fallback
    except BaseException as exc:
        _rc.finish_build(
            _FINGERPRINT_SINGLEFLIGHT_KEY,
            fut,
            exc=(
                exc
                if isinstance(exc, Exception)
                else RuntimeError("fingerprint read cancelled")
            ),
        )
        if fut.done() and not fut.cancelled():
            fut.exception()
        raise


#: #10290: which branch ``add_feed_collections`` took, for an ``observe`` hook.
COLLECTIONS_NO_PAGE_GAMES = "no_page_games"
COLLECTIONS_NO_BUDGET = "no_budget"
COLLECTIONS_READ_FAILED = "read_failed"
COLLECTIONS_READ = "read"


async def add_feed_collections(
    db,
    items,
    *,
    rank_key,
    page_window=20,
    budget_seconds=COLLECTION_READ_BUDGET_SECONDS,
    observe=None,
):
    """Insert eligible cards before their strongest member in the composed deck.

    Read publication on every serve; callers must not cache the resulting deck.
    The existing key selects the strongest visible member; its actual position
    determines placement. Composition has already moved cards out of key order,
    so a key scan cannot determine that position. A hub inherits the member's
    score and recency without a bonus. The producer card remains intact under
    ``data``, the normal feed envelope.

    ``observe`` (#10290), when given, is called once as ``observe(branch,
    collections)`` with one of the ``COLLECTIONS_*`` branches and, for
    ``COLLECTIONS_READ``, the cards the read returned (``None`` otherwise). It
    is how a display capture freezes this stage's only input; it changes
    nothing here.
    """
    games = _page_games(items, page_window)
    if not games or budget_seconds <= 0:
        if observe is not None:
            observe(
                COLLECTIONS_NO_PAGE_GAMES if not games else COLLECTIONS_NO_BUDGET,
                None,
            )
        return items
    timeout_s = min(budget_seconds, COLLECTION_READ_BUDGET_SECONDS)
    try:
        if isinstance(db, AsyncSession):
            # #11931: enforce the collection read budget server-side inside a
            # SAVEPOINT so Postgres itself cancels at `timeout_ms` instead of
            # stalling `db.rollback()` for 2-10 s on a cancelled asyncpg query.
            # On error, savepoint rollback reverts `set_config(..., true)`
            # automatically. On success, releasing a savepoint keeps a local GUC
            # for the enclosing transaction, so restore the prior value first.
            # Keep generous client-side backstop slack (`+ 0.5 s`) so Postgres
            # delivers QueryCanceledError cleanly over the wire rather than
            # `asyncio.wait_for` tearing down the asyncpg connection.
            timeout_ms = max(1, int(timeout_s * 1000))
            async with db.begin_nested():
                prev_res = await db.execute(
                    text("SELECT current_setting('statement_timeout')")
                )
                prev_timeout = prev_res.scalar() if prev_res is not None else None
                await db.execute(
                    text("SELECT set_config('statement_timeout', :val, true)"),
                    {"val": f"{timeout_ms}ms"},
                )
                read = await asyncio.wait_for(
                    container_discovery.discover_collections(db, event_ids=games),
                    timeout=timeout_s + 0.5,
                )
                await db.execute(
                    text("SELECT set_config('statement_timeout', :val, true)"),
                    {"val": str(prev_timeout) if prev_timeout is not None else "0"},
                )
        else:
            read = await asyncio.wait_for(
                container_discovery.discover_collections(db, event_ids=games),
                timeout=timeout_s,
            )
    except Exception:
        # A cancelled/failed statement can leave the session aborted (on the
        # non-savepoint path, or if the client-side backstop invalidated the
        # asyncpg connection). Ordinary cards are already serialized; restore it
        # for subsequent feed reads.
        if not isinstance(db, AsyncSession) or not db.is_active:
            await db.rollback()
        logger.warning(
            "Discover collection read failed; keeping ordinary cards", exc_info=True
        )
        if observe is not None:
            observe(COLLECTIONS_READ_FAILED, None)
        return items

    if observe is not None:
        observe(COLLECTIONS_READ, read.collections)
    return insert_feed_collections(
        items, read.collections, rank_key=rank_key, page_window=page_window
    )


def _page_games(items, page_window):
    return {
        item["data"]["id"]: item
        for item in items[:page_window]
        if item.get("type") == "event" and item.get("data", {}).get("id") is not None
    }


def insert_feed_collections(items, collections, *, rank_key, page_window=20):
    """The pure half of ``add_feed_collections``: place already-read cards.

    Split out for #10290 so the offline display replay places frozen cards by
    running this, not a copy. No I/O and no clock; ``items`` is not mutated.
    """
    games = _page_games(items, page_window)
    additions = []
    for card in collections:
        members = [games[i] for i in card["matched_event_ids"] if i in games]
        if not members:
            continue
        strongest = max(members, key=rank_key)
        additions.append(
            (
                strongest,
                {
                    "type": "collection",
                    "score": strongest.get("score", 0),
                    "_rank_score": strongest.get(
                        "_rank_score", strongest.get("score", 0)
                    ),
                    "_sort_time": strongest.get("_sort_time", 0),
                    "reason": card["name"],
                    "headline": None,
                    "data": card,
                },
            )
        )
    if not additions:
        return items
    result = list(items)
    for strongest, card in sorted(
        additions, key=lambda addition: rank_key(addition[1]), reverse=True
    ):
        result.insert(result.index(strongest), card)
    return result
