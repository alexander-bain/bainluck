"""Nightly uncovered-family container proposer task (Decision 386: A, #12221 Item 10).

Reads uncovered open futures markets, runs interest-ranked ``propose_top_containers``,
persists up to ``max_proposals`` (default 5) **preview-only** Kit container pages
idempotently by ``family_fingerprint`` in Redis, and never auto-publishes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket
from app.utils.container_proposer import normalize_market_record, propose_top_containers

logger = logging.getLogger(__name__)

CONTAINER_PREVIEWS_REDIS_KEY = "containers:kit_previews:v1"
CONTAINER_PREVIEWS_DECK_KEY_PREFIX = "containers:kit_previews:v1:deck:"
CONTAINER_PREVIEWS_TTL_SECONDS = 7 * 86400


def compute_deck_id(pages: list[dict[str, Any]], *, snapshot_captured_at: str) -> str:
    """Deterministic immutable deck identifier over frozen page order and fingerprints."""
    fp_pairs = [
        {
            "slug": str(p.get("slug") or ""),
            "page_fingerprint": str(p.get("page_fingerprint") or p.get("family_fingerprint") or ""),
        }
        for p in pages
    ]
    digest = hashlib.sha256(
        json.dumps(
            {"snapshot_captured_at": snapshot_captured_at, "pages": fp_pairs},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"kit-deck-{digest}"


async def load_covered_market_ids(session: Any) -> set[int]:
    """Load market IDs already covered by persisted containers, Midterms, and round-ups."""
    from app.tasks.grouping_sentinel import _GRAPH_SQL, collection_ids, definition_coverage

    covered: set[int] = set(collection_ids())
    try:
        rows = (await session.execute(text(_GRAPH_SQL))).all()
        for r in rows:
            val = r[0] if not hasattr(r, "child_id") else r.child_id
            if val is not None:
                covered.add(int(val))
    except Exception:
        logger.warning("[container-proposer] graph SQL coverage read failed; continuing with collection/definition IDs", exc_info=True)
        if hasattr(session, "rollback"):
            try:
                await session.rollback()
            except Exception as rollback_exc:
                logger.debug("[container-proposer] rollback after graph SQL read failed: %s", rollback_exc)
    try:
        def_ids, _stats = await definition_coverage(session)
        covered |= def_ids
    except Exception:
        logger.warning("[container-proposer] definition_coverage read failed; continuing with DB/Midterms IDs", exc_info=True)
        if hasattr(session, "rollback"):
            try:
                await session.rollback()
            except Exception as rollback_exc:
                logger.debug("[container-proposer] rollback after definition_coverage failed: %s", rollback_exc)
    return covered


async def load_covered_public_set_names(session: Any) -> set[str]:
    """Load slug and title strings of published public containers for covered-core overlap checks."""
    names: set[str] = set()
    try:
        rows = (await session.execute(text("SELECT slug, title FROM containers"))).all()
        for r in rows:
            slug_val = r[0] if not hasattr(r, "slug") else r.slug
            title_val = r[1] if not hasattr(r, "title") else r.title
            if slug_val:
                names.add(str(slug_val))
            if title_val:
                names.add(str(title_val))
    except Exception:
        logger.warning("[container-proposer] container name lookup failed; continuing with ID coverage only", exc_info=True)
        if hasattr(session, "rollback"):
            try:
                await session.rollback()
            except Exception as rollback_exc:
                logger.debug("[container-proposer] rollback after container name lookup failed: %s", rollback_exc)
    return names


def merge_preview_store(
    existing: Mapping[str, Any] | None,
    new_pages: list[dict[str, Any]],
    *,
    now: datetime,
    covered_ids_count: int = 0,
    timings_ms: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Idempotently merge new preview pages by ``family_fingerprint`` with frozen deck_id."""
    by_fp: dict[str, dict[str, Any]] = {}
    if isinstance(existing, Mapping):
        for page in existing.get("pages") or ():
            if not isinstance(page, Mapping):
                continue
            fp = str(page.get("family_fingerprint") or page.get("slug") or "")
            if fp:
                by_fp[fp] = {**dict(page), "state": "preview"}

    added = 0
    updated = 0
    for page in new_pages:
        clean_page = {**dict(page), "state": "preview"}
        fp = str(clean_page.get("family_fingerprint") or clean_page.get("slug") or "")
        if not fp:
            continue
        if fp in by_fp:
            updated += 1
        else:
            added += 1
        by_fp[fp] = clean_page

    ordered_pages = list(by_fp.values())
    updated_at_iso = now.isoformat()
    deck_id = compute_deck_id(ordered_pages, snapshot_captured_at=updated_at_iso)
    return {
        "kit_page_version": 1,
        "status": "ready" if ordered_pages else "not_built_yet",
        "deck_id": deck_id,
        "updated_at": updated_at_iso,
        "covered_ids_count": int(covered_ids_count),
        "timings_ms": dict(timings_ms) if timings_ms is not None else None,
        "count": len(ordered_pages),
        "added_last_run": added,
        "updated_last_run": updated,
        "pages": ordered_pages,
    }


async def load_open_markets_snapshot(
    session: Any,
    *,
    limit: int = 2500,
) -> list[dict[str, Any]]:
    """Bounded read of open FuturesMarket rows with outcomes for proposer runs."""
    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.settled_at.is_(None),
        )
        .order_by(FuturesMarket.volume_24h.desc().nullslast(), FuturesMarket.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [normalize_market_record(r) for r in rows]


async def run_nightly_container_proposer(
    *,
    session: Any | None = None,
    markets: list[dict[str, Any]] | None = None,
    covered_ids: frozenset[int] | set[int] | None = None,
    covered_public_set_names: Iterable[str] | None = None,
    dismissed_keys: tuple[str, ...] = (),
    now: datetime | None = None,
    max_proposals: int = 5,
    audit_top_n: int = 15,
    redis_client: Any | None = None,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one nightly uncovered-family proposal pass (preview only, never auto-published)."""
    t_total_start = time.perf_counter()
    ref_now = now if now is not None else datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    snapshot_load_ms = 0.0
    coverage_load_ms = 0.0
    resolved_covered: set[int] | frozenset[int] = covered_ids if covered_ids is not None else set()
    resolved_set_names: set[str] | tuple[str, ...] = tuple(covered_public_set_names) if covered_public_set_names is not None else ()

    async def _load_from_session(db_sess: Any) -> tuple[list[dict[str, Any]] | None, set[int] | frozenset[int], set[str] | tuple[str, ...]]:
        nonlocal snapshot_load_ms, coverage_load_ms
        loaded_markets = markets
        loaded_covered = resolved_covered
        loaded_names: set[str] | tuple[str, ...] = resolved_set_names
        if loaded_markets is None:
            t0 = time.perf_counter()
            loaded_markets = await load_open_markets_snapshot(db_sess)
            snapshot_load_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if covered_ids is None:
            t1 = time.perf_counter()
            loaded_covered = await load_covered_market_ids(db_sess)
            coverage_load_ms = round((time.perf_counter() - t1) * 1000.0, 2)
        if covered_public_set_names is None:
            loaded_names = await load_covered_public_set_names(db_sess)
        return loaded_markets, loaded_covered, loaded_names

    if markets is None or covered_ids is None:
        if session is not None:
            markets, resolved_covered, resolved_set_names = await _load_from_session(session)
        elif session_factory is not None:
            async with session_factory() as db_sess:
                markets, resolved_covered, resolved_set_names = await _load_from_session(db_sess)
        elif markets is None:
            from app.tasks.base import get_task_session
            async with get_task_session() as db_sess:
                markets, resolved_covered, resolved_set_names = await _load_from_session(db_sess)

    t_propose_start = time.perf_counter()
    result = propose_top_containers(
        markets or (),
        covered_ids=resolved_covered,
        covered_public_set_names=resolved_set_names,
        now=ref_now,
        max_proposals=max_proposals,
        audit_top_n=audit_top_n,
        dismissed_keys=dismissed_keys,
    )
    propose_ms = round((time.perf_counter() - t_propose_start) * 1000.0, 2)
    total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 2)
    timings_ms = {
        "snapshot_load_ms": snapshot_load_ms,
        "coverage_load_ms": coverage_load_ms,
        "propose_ms": propose_ms,
        "total_ms": total_ms,
    }

    stored_payload: dict[str, Any] | None = None
    if redis_client is not None:
        raw_prev = redis_client.get(CONTAINER_PREVIEWS_REDIS_KEY)
        prev_obj = json.loads(raw_prev) if raw_prev else None
        stored_payload = merge_preview_store(
            prev_obj,
            result["pages"],
            now=ref_now,
            covered_ids_count=len(resolved_covered),
            timings_ms=timings_ms,
        )
        serialized = json.dumps(stored_payload)
        redis_client.set(
            CONTAINER_PREVIEWS_REDIS_KEY,
            serialized,
            ex=CONTAINER_PREVIEWS_TTL_SECONDS,
        )
        deck_id = stored_payload.get("deck_id")
        if deck_id:
            redis_client.set(
                f"{CONTAINER_PREVIEWS_DECK_KEY_PREFIX}{deck_id}",
                serialized,
                ex=CONTAINER_PREVIEWS_TTL_SECONDS,
            )

    logger.info(
        "[container-proposer] uncovered_families=%d proposed=%d audited=%d covered_ids=%d total_ms=%.2f",
        result["uncovered_family_count"],
        result["count"],
        len(result["ranked_audit"]),
        len(resolved_covered),
        total_ms,
    )
    return {
        "status": "complete",
        "snapshot_captured_at": result["snapshot_captured_at"],
        "deck_id": stored_payload.get("deck_id") if stored_payload else compute_deck_id(result["pages"], snapshot_captured_at=result["snapshot_captured_at"]),
        "covered_ids_count": len(resolved_covered),
        "timings_ms": timings_ms,
        "uncovered_family_count": result["uncovered_family_count"],
        "proposed_count": result["count"],
        "pages": result["pages"],
        "ranked_audit": result["ranked_audit"],
        "store": stored_payload,
    }


def propose_uncovered_containers(*, max_proposals: int = 5) -> dict[str, Any]:
    """Synchronous task entrypoint invoking ``run_nightly_container_proposer``."""
    import asyncio
    from app.tasks.redis_state import get_redis_client

    redis_client = get_redis_client()
    return asyncio.run(
        run_nightly_container_proposer(
            max_proposals=max_proposals,
            redis_client=redis_client,
        )
    )
