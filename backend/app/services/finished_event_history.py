"""Finished-game `/api/events/{id}/history` durable materialization & invalidation (#13606 Part 1).

Serves BOTH `range="all"` (iPhone `?hours=N` with no `range` + Web "All") and
`range="since_start"` (Web default + updated iPhone) from one persisted canonical
`"all"` payload stored in existing `durable_state_snapshots` (`no DDL migration`):

- `range="all"`: returned directly from PostgreSQL in one primary-key lookup.
- `range="since_start"`: derived in memory via `_omit_pre_kickoff_points` +
  `_withhold_undrawable_source_series` with zero snapshot-table scans.
- Invalidation (Condition 1):
  * In-memory `Event` fields + 5 small indexed tables (`score_snapshots`,
    `espn_snapshots`, `scoring_plays`, `game_moments`, `futures_markets` /
    `futures_outcomes`) are verified on read via a single lightweight
    aggregate fingerprint query.
  * The two large unindexed-by-id history tables (`win_prob_snapshots`,
    `odds_snapshots`) invalidate directly at every writer via
    `invalidate_finished_event_history` / `invalidate_finished_event_history_sync`.
  * Note: `venue_history_points` (#11929 / 371:A) and `futures_odds_snapshots`
    are NOT read by `get_event_odds_history`, so they require neither check.
- Retention (Condition 2): no age expiry or 30-day pruning in this version;
  revisit at 10 GB (`measure_finished_event_history_storage` reports size).
- Day-1 materializer cap (Condition 3): default 5 events per run with explicit
  per-event `build_s` logging on the `background` Celery queue.
- Cold miss on an unstored finished game (Condition 4): controlled via
  `FINISHED_EVENT_HISTORY_COLD_MISS_MODE` (`read_through` vs `since_start_fallback`).
"""

from __future__ import annotations

import contextvars
import copy
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import event_history_cache as ehc
from app.utils.durable_state import DurableEnvelope, canonical_json

logger = logging.getLogger(__name__)

FINISHED_HISTORY_SCHEMA_VERSION = "finished_event_history_v1"
FINISHED_HISTORY_IDENTITY_PREFIX = "finished_event_history:v1:"
FINISHED_HISTORY_SOURCE = "finished_event_chart_materializer"
FINISHED_HISTORY_READ_THROUGH_SOURCE = "finished_event_chart_read_through"

DEFAULT_BATCH_SIZE = 5
MAX_BATCH_SIZE = 50
MATERIALIZE_MIN_AGE_MINUTES = 35
MATERIALIZE_LOOKBACK_DAYS = 7
COLD_ENQUEUE_COOLDOWN_S = 300.0
MATERIALIZE_DEFER_TTL_S = 21600
WALL_BUDGET_DEFAULT_S = 240.0

COLD_MISS_READ_THROUGH = "read_through"
COLD_MISS_SINCE_START_FALLBACK = "since_start_fallback"

TRANSIENT_REFILL_REASONS: frozenset[str] = frozenset(
    {"already_claimed", "hourly_cap", "no_redis", "background_deferred"}
)

_BYPASS_DURABLE_VAR: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "finished_event_history_bypass_durable", default=False
)
_MATERIALIZER_CONTEXT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "finished_event_history_materializer", default=False
)

_ENQUEUE_LOCK = threading.Lock()
_LOCAL_ENQUEUE_AT: dict[int, float] = {}
_DEFER_LOCK = threading.Lock()
_LOCAL_DEFER_AT: dict[int, float] = {}


def is_on_demand_refill_pending(on_demand_backfill: Any) -> bool:
    """True when `on_demand_backfill` indicates the chart is awaiting a venue refill or was transiently blocked."""
    if not isinstance(on_demand_backfill, dict):
        return False
    return bool(on_demand_backfill.get("enqueue")) or (
        on_demand_backfill.get("reason") in TRANSIENT_REFILL_REASONS
    )


def durable_enabled() -> bool:
    """Kill switch (`FINISHED_EVENT_HISTORY_DURABLE_ENABLED`, default on)."""
    raw = os.getenv("FINISHED_EVENT_HISTORY_DURABLE_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def cold_miss_mode() -> str:
    """Condition 4 switch: `read_through` (default) or `since_start_fallback`."""
    raw = os.getenv("FINISHED_EVENT_HISTORY_COLD_MISS_MODE", COLD_MISS_READ_THROUGH)
    norm = raw.strip().lower()
    if norm == COLD_MISS_SINCE_START_FALLBACK:
        return COLD_MISS_SINCE_START_FALLBACK
    return COLD_MISS_READ_THROUGH


def configured_batch_size(override: Optional[int] = None) -> int:
    """Condition 3: start small on day one (default 5 events per run)."""
    if override is not None:
        return max(1, min(MAX_BATCH_SIZE, int(override)))
    raw = os.getenv("FINISHED_EVENT_HISTORY_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = DEFAULT_BATCH_SIZE
    return max(1, min(MAX_BATCH_SIZE, parsed))


def durable_identity(event_id: int) -> str:
    return f"{FINISHED_HISTORY_IDENTITY_PREFIX}{int(event_id)}"


@contextmanager
def bypass_durable_context():
    """Run the route builder bypassing durable reads and cold-miss fallbacks."""
    token = _BYPASS_DURABLE_VAR.set(True)
    try:
        yield
    finally:
        _BYPASS_DURABLE_VAR.reset(token)


def is_durable_bypassed() -> bool:
    return bool(_BYPASS_DURABLE_VAR.get())


@contextmanager
def materializer_context():
    """Mark background materializer execution so route builds defer reader on-demand backfill."""
    token = _MATERIALIZER_CONTEXT.set(True)
    try:
        yield
    finally:
        _MATERIALIZER_CONTEXT.reset(token)


def in_materializer_context() -> bool:
    return bool(_MATERIALIZER_CONTEXT.get())


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _is_mock_object(obj: Any) -> bool:
    try:
        from unittest.mock import Base as _MockBase

        return isinstance(obj, _MockBase)
    except Exception:  # pragma: no cover
        return False


def session_supports_durable(db: Any) -> bool:
    """True when `db` is a real PostgreSQL SQLAlchemy AsyncSession supporting savepoints."""
    if db is None or _is_mock_object(db) or not hasattr(db, "begin_nested") or not hasattr(db, "execute"):
        return False
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False
    try:
        bind = get_bind()
    except Exception:
        return False
    dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", None) == "postgresql"


def _session_supports_invalidation(db: Any) -> bool:
    """True for any real AsyncSession/Session backed by PG or SQLite (skip test stubs/mocks)."""
    if db is None or _is_mock_object(db) or not hasattr(db, "execute") or not hasattr(db, "begin_nested"):
        return False
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False
    try:
        bind = get_bind()
    except Exception:
        return False
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    return dialect_name in ("postgresql", "sqlite")


def _normalized_tags(raw_tags: Any) -> list[str]:
    """Portable sorted tag list (asyncpg yields list, SQLite text yields JSON)."""
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except ValueError:
            return []
    if not isinstance(raw_tags, (list, tuple)):
        return []
    return sorted(str(t) for t in raw_tags if isinstance(t, str))


def event_state_fingerprint(
    event: Any,
    absorbed: Sequence[Any],
    series_event_ids: Sequence[int],
) -> dict[str, Any]:
    """Deterministic fingerprint of the already-loaded `Event` & duplicate fold."""
    from app.utils.proven_duplicates import canonical_id_from_tags

    box = getattr(event, "box_score_data", None)
    scoring_plays = box.get("scoring_plays") if isinstance(box, dict) else None
    wps_hash = hashlib.sha256(
        canonical_json(getattr(event, "win_probability_sources", None)).encode("utf-8")
    ).hexdigest()
    box_hash = hashlib.sha256(canonical_json(scoring_plays).encode("utf-8")).hexdigest()
    absorbed_fp = [
        [
            int(getattr(r, "id", 0) or 0),
            getattr(r, "status", None),
            _iso_or_none(getattr(r, "completed_at", None)),
            getattr(r, "home_score", None),
            getattr(r, "away_score", None),
            getattr(r, "win_probability_sources_rev", None),
        ]
        for r in sorted(absorbed or (), key=lambda x: int(getattr(x, "id", 0) or 0))
    ]
    raw_tags = getattr(event, "event_tags", None)
    return {
        "canonical_event_id": int(getattr(event, "id", 0) or 0),
        "status": getattr(event, "status", None),
        "completed_at": _iso_or_none(getattr(event, "completed_at", None)),
        "commence_time": _iso_or_none(getattr(event, "commence_time", None)),
        "commence_time_source": getattr(event, "commence_time_source", None),
        "statpal_end_time": _iso_or_none(getattr(event, "statpal_end_time", None)),
        "home_score": getattr(event, "home_score", None),
        "away_score": getattr(event, "away_score", None),
        "period": getattr(event, "period", None),
        "game_clock": getattr(event, "game_clock", None),
        "score_observed_at": _iso_or_none(getattr(event, "score_observed_at", None)),
        "home_team_name": getattr(event, "home_team_name", None),
        "away_team_name": getattr(event, "away_team_name", None),
        "duplicate_of_id": canonical_id_from_tags(raw_tags),
        "event_tags": _normalized_tags(raw_tags),
        "win_probability_sources_rev": getattr(event, "win_probability_sources_rev", None),
        "series_event_ids": sorted({int(eid) for eid in (series_event_ids or ())}),
        "absorbed": absorbed_fp,
        "wps_sha256": wps_hash,
        "box_plays_sha256": box_hash,
    }


_SMALL_TABLES_FP_SQL = text(
    """
    SELECT
        sc.cnt AS sc_cnt, sc.max_id AS sc_max_id, sc.max_ts AS sc_max_ts,
        ep.cnt AS ep_cnt, ep.max_id AS ep_max_id, ep.max_ts AS ep_max_ts,
        sp.cnt AS sp_cnt, sp.max_id AS sp_max_id, sp.max_ts AS sp_max_ts,
        gm.cnt AS gm_cnt, gm.max_id AS gm_max_id, gm.max_ts AS gm_max_ts,
        fm.cnt AS fm_cnt, fm.max_id AS fm_max_id, fm.max_ts AS fm_max_ts,
        fo.cnt AS fo_cnt, fo.max_id AS fo_max_id, fo.max_lu AS fo_max_lu, fo.max_pc AS fo_max_pc
    FROM (
        SELECT COUNT(*) AS cnt, MAX(id) AS max_id, MAX(captured_at) AS max_ts
        FROM score_snapshots WHERE event_id IN :series_ids
    ) sc
    CROSS JOIN (
        SELECT COUNT(*) AS cnt, MAX(id) AS max_id, MAX(captured_at) AS max_ts
        FROM espn_snapshots WHERE event_id = :eid
    ) ep
    CROSS JOIN (
        SELECT COUNT(*) AS cnt, MAX(id) AS max_id, MAX(captured_at) AS max_ts
        FROM scoring_plays WHERE event_id = :eid
    ) sp
    CROSS JOIN (
        SELECT COUNT(*) AS cnt, MAX(id) AS max_id, MAX(created_at) AS max_ts
        FROM game_moments WHERE event_id = :eid
    ) gm
    CROSS JOIN (
        SELECT COUNT(*) AS cnt, MAX(id) AS max_id, MAX(updated_at) AS max_ts
        FROM futures_markets WHERE event_id = :eid
    ) fm
    CROSS JOIN (
        SELECT
            COUNT(*) AS cnt,
            MAX(o.id) AS max_id,
            MAX(o.last_updated) AS max_lu,
            MAX(o.price_changed_at) AS max_pc
        FROM futures_outcomes o
        JOIN futures_markets m ON m.id = o.market_id
        WHERE m.event_id = :eid
    ) fo
    """
).bindparams(bindparam("series_ids", expanding=True))


async def compute_small_tables_fingerprint(
    db: AsyncSession,
    event_id: int,
    series_event_ids: Sequence[int],
) -> Optional[dict[str, Any]]:
    """One indexed round trip across the 5 small history tables (`score_snapshots`,
    `espn_snapshots`, `scoring_plays`, `game_moments`, `futures_markets`/`futures_outcomes`).
    """
    ids = sorted({int(event_id), *(int(i) for i in (series_event_ids or ()))})
    nested = None
    try:
        nested = await db.begin_nested()
        row = (
            await db.execute(_SMALL_TABLES_FP_SQL, {"eid": int(event_id), "series_ids": ids})
        ).mappings().first()
    except Exception as exc:  # noqa: BLE001 — fail open so chart always serves
        logger.warning(
            "finished_event_history: small-tables fingerprint failed for %s: %s",
            event_id, str(exc)[:160],
        )
        return None
    finally:
        if nested is not None:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001
                pass

    if row is None:
        return None
    return {
        "sc": [int(row["sc_cnt"] or 0), row["sc_max_id"], _iso_or_none(row["sc_max_ts"])],
        "ep": [int(row["ep_cnt"] or 0), row["ep_max_id"], _iso_or_none(row["ep_max_ts"])],
        "sp": [int(row["sp_cnt"] or 0), row["sp_max_id"], _iso_or_none(row["sp_max_ts"])],
        "gm": [int(row["gm_cnt"] or 0), row["gm_max_id"], _iso_or_none(row["gm_max_ts"])],
        "fm": [int(row["fm_cnt"] or 0), row["fm_max_id"], _iso_or_none(row["fm_max_ts"])],
        "fo": [
            int(row["fo_cnt"] or 0),
            row["fo_max_id"],
            _iso_or_none(row["fo_max_lu"]),
            _iso_or_none(row["fo_max_pc"]),
        ],
    }


def build_fingerprint(
    event: Any,
    absorbed: Sequence[Any],
    series_event_ids: Sequence[int],
    tables_fp: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event": event_state_fingerprint(event, absorbed, series_event_ids),
        "tables": tables_fp,
    }


async def read_finished_event_history(
    db: AsyncSession,
    event_id: int,
) -> Optional[dict[str, Any]]:
    """Read durable `"all"` envelope wrapper (`{"v": 1, "fingerprint": ..., "payload": ...}`),
    using a rolled-back savepoint so `SET LOCAL statement_timeout` never leaks.
    """
    from app.services.durable_snapshots import read_snapshot

    nested = None
    read = None
    try:
        nested = await db.begin_nested()
        read = await read_snapshot(
            db,
            durable_identity(event_id),
            expected_version=FINISHED_HISTORY_SCHEMA_VERSION,
            max_age_s=float("inf"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "finished_event_history: durable read failed for %s: %s",
            event_id, str(exc)[:160],
        )
        return None
    finally:
        if nested is not None:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001
                pass

    if read is None or not read.ok or read.envelope is None:
        return None
    body = read.envelope.payload
    if not isinstance(body, dict):
        return None
    if not isinstance(body.get("payload"), dict) or not isinstance(body.get("fingerprint"), dict):
        return None
    return body


async def write_finished_event_history(
    db: AsyncSession,
    event_id: int,
    *,
    payload: dict[str, Any],
    fingerprint: dict[str, Any],
    source: str,
    encoded_size_fn: Callable[[dict[str, Any]], bytes],
    max_entry_bytes: int = ehc.MAX_ENTRY_BYTES,
    commit: bool = True,
) -> dict[str, Any]:
    """Persist complete `"all"` finished chart payload into `durable_state_snapshots`."""
    from app.services.durable_snapshots import (
        PUBLISH_STATUS_DURABLE,
        publish_snapshot_in_txn,
    )

    try:
        raw_bytes = encoded_size_fn(payload)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"encode_failed: {exc}"[:200]}

    if len(raw_bytes) > max_entry_bytes:
        return {"status": "skipped", "reason": "oversized", "bytes": len(raw_bytes)}

    envelope = DurableEnvelope.build(
        identity=durable_identity(event_id),
        schema_version=FINISHED_HISTORY_SCHEMA_VERSION,
        payload={
            "v": 1,
            "fingerprint": fingerprint,
            "payload": payload,
        },
        generated_at=datetime.now(timezone.utc),
        complete=True,
        source=source,
    )

    nested = None
    try:
        nested = await db.begin_nested()
        stage = await publish_snapshot_in_txn(db, envelope)
        if stage.get("status") in PUBLISH_STATUS_DURABLE:
            await nested.commit()
            nested = None
            if commit:
                await db.commit()
        else:
            await nested.rollback()
            nested = None
        return {**stage, "bytes": len(raw_bytes)}
    except Exception as exc:  # noqa: BLE001
        if nested is not None:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.warning(
            "finished_event_history: durable publish failed for %s: %s",
            event_id, str(exc)[:160],
        )
        return {"status": "error", "error": str(exc)[:200], "bytes": len(raw_bytes)}


def derive_since_start_payload(
    all_payload: dict[str, Any],
    *,
    commence_time: Any,
    omit_fn: Callable[..., bool],
    withhold_fn: Callable[..., None],
) -> dict[str, Any]:
    """Derive a `range="since_start"` payload in memory from a stored `"all"` payload."""
    out = dict(all_payload)
    history = copy.deepcopy(all_payload.get("history") or [])
    bookmaker_history = copy.deepcopy(all_payload.get("bookmaker_history") or {})
    win_prob_history = copy.deepcopy(all_payload.get("win_prob_history") or {})
    win_prob_sources_meta = copy.deepcopy(all_payload.get("win_prob_sources") or {})
    raw_agg = all_payload.get("aggregate_line")
    aggregate_line = copy.deepcopy(raw_agg) if isinstance(raw_agg, list) else []
    espn_history = copy.deepcopy(all_payload.get("espn_history") or [])

    pre_window_omitted = omit_fn(
        commence_time=commence_time,
        start_is_kickoff=bool(out.get("commence_time_is_kickoff", True)),
        history=history,
        bookmaker_history=bookmaker_history,
        win_prob_history=win_prob_history,
        win_prob_sources_meta=win_prob_sources_meta,
        aggregate_line=aggregate_line,
        espn_history=espn_history,
    )
    withhold_fn(win_prob_history, win_prob_sources_meta)

    out["history"] = history
    out["bookmaker_history"] = bookmaker_history
    out["win_prob_history"] = win_prob_history
    out["win_prob_sources"] = win_prob_sources_meta
    out["aggregate_line"] = aggregate_line if aggregate_line else None
    out["pre_window_omitted"] = bool(pre_window_omitted)
    out["points"] = len(history)
    out["bookmaker_count"] = len(bookmaker_history)
    return out


_RESOLVE_DUP_SQL = text(
    "SELECT id, event_tags FROM events WHERE id IN :eids"
).bindparams(bindparam("eids", expanding=True))

_DELETE_DURABLE_SQL = text(
    "DELETE FROM durable_state_snapshots WHERE identity IN :identities"
).bindparams(bindparam("identities", expanding=True))


def _expanded_invalidation_identities(rows: Sequence[Any], clean_ids: Sequence[int]) -> list[str]:
    from app.utils.proven_duplicates import canonical_id_from_tags

    expanded = set(clean_ids)
    for row in rows:
        raw_tags = getattr(row, "event_tags", None)
        if raw_tags is None and isinstance(row, tuple) and len(row) > 1:
            raw_tags = row[1]
        dup_id = canonical_id_from_tags(raw_tags)
        if dup_id:
            expanded.add(int(dup_id))
    for eid in expanded:
        ehc.invalidate_event(eid)
    return [durable_identity(eid) for eid in sorted(expanded)]


def _normalize_event_ids(event_ids: Iterable[Any]) -> list[int]:
    out: set[int] = set()
    for raw in event_ids:
        if raw is None:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out.add(val)
    return sorted(out)


async def invalidate_finished_event_history(
    db: Any,
    event_ids: Iterable[Any],
) -> int:
    """Invalidate durable + process L1 finished-history entries for `event_ids` and any canonical parents.

    Runs inside caller's transaction via a savepoint so a missing/errored table
    never aborts an unrelated writer transaction. Never commits or rolls back `db`.
    """
    clean_ids = _normalize_event_ids(event_ids)
    if not clean_ids:
        return 0
    for eid in clean_ids:
        ehc.invalidate_event(eid)
    if not _session_supports_invalidation(db):
        return 0

    nested = None
    try:
        nested = await db.begin_nested()
        rows = (await db.execute(_RESOLVE_DUP_SQL, {"eids": clean_ids})).all()
        identities = _expanded_invalidation_identities(rows, clean_ids)
        res = await db.execute(_DELETE_DURABLE_SQL, {"identities": identities})
        await nested.commit()
        nested = None
        return int(getattr(res, "rowcount", 0) or 0)
    except Exception as exc:  # noqa: BLE001 — invalidation never breaks a writer
        if nested is not None:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.debug(
            "finished_event_history: async invalidation skipped for %s: %s",
            clean_ids[:5], str(exc)[:160],
        )
        return 0


def invalidate_finished_event_history_sync(
    session: Any,
    event_ids: Iterable[Any],
) -> int:
    """Synchronous twin of :func:`invalidate_finished_event_history`."""
    clean_ids = _normalize_event_ids(event_ids)
    if not clean_ids:
        return 0
    for eid in clean_ids:
        ehc.invalidate_event(eid)
    if not _session_supports_invalidation(session):
        return 0

    nested = None
    try:
        nested = session.begin_nested()
        rows = session.execute(_RESOLVE_DUP_SQL, {"eids": clean_ids}).all()
        identities = _expanded_invalidation_identities(rows, clean_ids)
        res = session.execute(_DELETE_DURABLE_SQL, {"identities": identities})
        nested.commit()
        nested = None
        return int(getattr(res, "rowcount", 0) or 0)
    except Exception as exc:  # noqa: BLE001
        if nested is not None:
            try:
                nested.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.debug(
            "finished_event_history: sync invalidation skipped for %s: %s",
            clean_ids[:5], str(exc)[:160],
        )
        return 0


def claim_cold_materialization(event_id: int, *, ttl_s: float = COLD_ENQUEUE_COOLDOWN_S) -> bool:
    """Best-effort dedupe claim before dispatching background materialization from a route."""
    eid = int(event_id)
    key = f"finished_event_history:materialize_claim:{eid}"
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if client is not None:
            if client.set(key, "1", nx=True, ex=int(ttl_s)):
                return True
            return False
    except Exception:  # noqa: BLE001 — fall through to process-local dedupe
        pass

    now = time.monotonic()
    with _ENQUEUE_LOCK:
        # Prune expired process-local entries lazily
        expired = [k for k, ts in _LOCAL_ENQUEUE_AT.items() if now - ts >= ttl_s]
        for k in expired:
            _LOCAL_ENQUEUE_AT.pop(k, None)
        if eid in _LOCAL_ENQUEUE_AT:
            return False
        _LOCAL_ENQUEUE_AT[eid] = now
        return True


def _reset_claims_for_tests() -> None:
    with _ENQUEUE_LOCK:
        _LOCAL_ENQUEUE_AT.clear()
    with _DEFER_LOCK:
        _LOCAL_DEFER_AT.clear()


def _defer_key(event_id: int) -> str:
    return f"finished_event_history:materialize_defer:{int(event_id)}"


def mark_materialization_deferred(
    event_id: Any, *, ttl_s: float = MATERIALIZE_DEFER_TTL_S
) -> None:
    """Remember briefly that an un-writable event was skipped so it cannot starve the batch head."""
    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        return
    if eid <= 0:
        return
    with _DEFER_LOCK:
        _LOCAL_DEFER_AT[eid] = time.monotonic()
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if client is not None:
            client.set(_defer_key(eid), "1", ex=int(ttl_s))
    except Exception:  # noqa: BLE001 — best-effort cross-worker defer
        pass


def filter_deferred_materializations(
    event_ids: Sequence[int], *, ttl_s: float = MATERIALIZE_DEFER_TTL_S
) -> list[int]:
    """Exclude events temporarily deferred in local memory or Redis, preserving candidate order."""
    now = time.monotonic()
    with _DEFER_LOCK:
        expired = [k for k, ts in _LOCAL_DEFER_AT.items() if now - ts >= ttl_s]
        for k in expired:
            _LOCAL_DEFER_AT.pop(k, None)
        remaining = [int(eid) for eid in event_ids if int(eid) not in _LOCAL_DEFER_AT]
    if not remaining:
        return []
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        if client is not None:
            vals = client.mget([_defer_key(eid) for eid in remaining])
            if isinstance(vals, (list, tuple)) and len(vals) == len(remaining):
                return [eid for eid, val in zip(remaining, vals) if val is None]
    except Exception:  # noqa: BLE001 — process-local filter already ran
        pass
    return remaining


async def select_finished_chart_candidates(
    db: AsyncSession,
    *,
    limit: int,
    now: Optional[datetime] = None,
) -> list[int]:
    from sqlalchemy import String, cast, literal, or_, select

    from app.models.models import DurableStateSnapshot, Event
    from app.utils.proven_duplicates import not_a_proven_duplicate

    ref_now = now or datetime.now(timezone.utc)
    max_completed = ref_now - timedelta(minutes=MATERIALIZE_MIN_AGE_MINUTES)
    min_completed = ref_now - timedelta(days=MATERIALIZE_LOOKBACK_DAYS)
    ident_expr = literal(FINISHED_HISTORY_IDENTITY_PREFIX) + cast(Event.id, String)
    target_limit = max(1, int(limit))
    fetch_limit = min(max(target_limit * 4, 25), 200)
    stmt = (
        select(Event.id)
        .outerjoin(
            DurableStateSnapshot,
            DurableStateSnapshot.identity == ident_expr,
        )
        .where(
            Event.status.in_(("completed", "closed")),
            not_a_proven_duplicate(),
            Event.completed_at.isnot(None),
            Event.completed_at <= max_completed,
            Event.completed_at >= min_completed,
            or_(Event.commence_time.is_(None), Event.commence_time <= ref_now),
            or_(
                DurableStateSnapshot.identity.is_(None),
                DurableStateSnapshot.schema_version != FINISHED_HISTORY_SCHEMA_VERSION,
                DurableStateSnapshot.complete.is_(False),
            ),
        )
        .order_by(Event.completed_at.desc(), Event.id.desc())
        .limit(fetch_limit)
    )
    rows = (await db.execute(stmt)).all()
    candidates = [int(r[0]) for r in rows]
    return filter_deferred_materializations(candidates)[:target_limit]


async def materialize_finished_event_charts_async(
    session_factory: Callable[[], Any],
    *,
    event_ids: Optional[Sequence[int]] = None,
    limit: Optional[int] = None,
    wall_budget_s: float = WALL_BUDGET_DEFAULT_S,
) -> dict[str, Any]:
    """Build and durably store complete finished `"all"` charts (Condition 3: 5/run default)."""
    from fastapi import Response
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import Event
    from app.routes import events as events_route
    from app.tasks.odds_polling import get_max_duration_for_sport
    from app.utils.proven_duplicates import folded_series_event_ids
    from app.utils.serve_fold_absorbed import (
        serve_fold_absorbed_rows_with_completeness,
    )

    if not durable_enabled():
        return {"status": "disabled", "processed": 0, "written": 0}

    cap = configured_batch_size(limit)
    targets: list[int] = _normalize_event_ids(event_ids) if event_ids else []
    if not targets:
        async with session_factory() as db:
            targets = await select_finished_chart_candidates(db, limit=cap)
    else:
        targets = targets[:cap]

    t_start = time.monotonic()
    stats: dict[str, Any] = {
        "status": "ok",
        "batch_limit": cap,
        "selected": len(targets),
        "processed": 0,
        "written": 0,
        "skipped": 0,
        "errors": 0,
        "per_event": [],
    }

    for eid in targets:
        if time.monotonic() - t_start >= wall_budget_s:
            stats["stopped_early"] = "wall_budget"
            break
        ev_t0 = time.monotonic()
        entry: dict[str, Any] = {"event_id": eid, "status": "unknown"}
        try:
            async with session_factory() as db:
                ev_res = await db.execute(
                    select(Event).options(selectinload(Event.sport)).where(Event.id == eid)
                )
                event = ev_res.scalar_one_or_none()
                if event is None:
                    entry["status"] = "not_found"
                    stats["skipped"] += 1
                    stats["per_event"].append(entry)
                    continue
                served = await events_route.resolve_served_event(
                    db, event, requested_id=eid
                )
                canonical = served.event
                canonical_id = int(served.event_id)
                now_utc = datetime.now(timezone.utc)
                if not events_route._event_is_really_finished(canonical, now_utc):
                    entry["status"] = "not_finished"
                    stats["skipped"] += 1
                    stats["per_event"].append(entry)
                    continue
                commence_cap = None
                if canonical.commence_time:
                    sport_key = canonical.sport.key if canonical.sport else ""
                    max_hours = get_max_duration_for_sport(sport_key)
                    commence_cap = canonical.commence_time + timedelta(
                        hours=max_hours + 0.5
                    )
                end_cap = events_route._finished_event_end_cap(
                    canonical.completed_at, canonical.commence_time, commence_cap
                )
                if end_cap is None or now_utc < end_cap:
                    entry["status"] = "within_grace_window"
                    mark_materialization_deferred(canonical_id)
                    if eid != canonical_id:
                        mark_materialization_deferred(eid)
                    stats["skipped"] += 1
                    stats["per_event"].append(entry)
                    continue

                marks, token = ehc.begin_marks()
                try:
                    with bypass_durable_context(), materializer_context():
                        payload = await events_route.get_event_odds_history(
                            canonical_id,
                            hours=48,
                            chart_range=events_route.EVENT_HISTORY_RANGE_ALL,
                            response=Response(),
                            db=db,
                            fresh=False,
                        )
                finally:
                    ehc.end_marks(token)

                refill = payload.get("on_demand_backfill") if isinstance(payload, dict) else None
                refill_pending = is_on_demand_refill_pending(refill)
                if not marks.finished or marks.partial or refill_pending:
                    entry["status"] = (
                        "partial" if marks.partial
                        else "on_demand_pending" if refill_pending
                        else "incomplete_marks"
                    )
                    mark_materialization_deferred(canonical_id)
                    if eid != canonical_id:
                        mark_materialization_deferred(eid)
                    stats["skipped"] += 1
                    stats["per_event"].append(entry)
                    continue

                absorbed, _ = await serve_fold_absorbed_rows_with_completeness(db, canonical)
                series_ids = await folded_series_event_ids(db, canonical_id, absorbed)
                tables_fp = await compute_small_tables_fingerprint(db, canonical_id, series_ids)
                if tables_fp is None:
                    entry["status"] = "fingerprint_failed"
                    mark_materialization_deferred(canonical_id)
                    stats["errors"] += 1
                    stats["per_event"].append(entry)
                    continue
                fp = build_fingerprint(canonical, absorbed, series_ids, tables_fp)

                res = await write_finished_event_history(
                    db,
                    canonical_id,
                    payload=payload,
                    fingerprint=fp,
                    source=FINISHED_HISTORY_SOURCE,
                    encoded_size_fn=events_route._encode_history_payload,
                    commit=True,
                )
                build_s = round(time.monotonic() - ev_t0, 3)
                entry.update(
                    {
                        "canonical_event_id": canonical_id,
                        "status": res.get("status", "unknown"),
                        "build_s": build_s,
                        "bytes": res.get("bytes"),
                    }
                )
                if res.get("status") in ("ok", "superseded"):
                    stats["written"] += 1
                elif res.get("status") == "skipped":
                    mark_materialization_deferred(canonical_id)
                    if eid != canonical_id:
                        mark_materialization_deferred(eid)
                    stats["skipped"] += 1
                else:
                    mark_materialization_deferred(canonical_id)
                    stats["errors"] += 1
                logger.info(
                    "finished_event_history: materialize event_id=%s canonical=%s status=%s build_s=%.3f bytes=%s",
                    eid, canonical_id, entry["status"], build_s, entry.get("bytes"),
                )
        except Exception as exc:  # noqa: BLE001
            build_s = round(time.monotonic() - ev_t0, 3)
            entry = {"event_id": eid, "status": "error", "build_s": build_s, "error": str(exc)[:160]}
            mark_materialization_deferred(eid)
            stats["errors"] += 1
            logger.warning(
                "finished_event_history: materialize error event_id=%s build_s=%.3f: %s",
                eid, build_s, str(exc)[:160],
            )
        stats["processed"] += 1
        stats["per_event"].append(entry)

    stats["elapsed_s"] = round(time.monotonic() - t_start, 3)
    return stats


_STORAGE_MEASURE_SQL = text(
    """
    SELECT
        COUNT(*) AS row_count,
        COALESCE(SUM(pg_column_size(payload)), 0) AS payload_bytes,
        pg_total_relation_size('durable_state_snapshots') AS table_total_bytes
    FROM durable_state_snapshots
    WHERE identity LIKE :like_prefix
    """
)


async def measure_finished_event_history_storage(db: AsyncSession) -> dict[str, int]:
    """Condition 2: weekly size check helper for `#13606` (revisit at 10 GB)."""
    row = (
        await db.execute(
            _STORAGE_MEASURE_SQL,
            {"like_prefix": f"{FINISHED_HISTORY_IDENTITY_PREFIX}%"},
        )
    ).mappings().first()
    if row is None:
        return {"row_count": 0, "payload_bytes": 0, "table_total_bytes": 0}
    return {
        "row_count": int(row["row_count"] or 0),
        "payload_bytes": int(row["payload_bytes"] or 0),
        "table_total_bytes": int(row["table_total_bytes"] or 0),
    }
