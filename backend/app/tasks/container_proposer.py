"""Nightly uncovered-family container proposer task (Decision 386: A, #12221 Item 10).

Reads uncovered open futures markets, runs interest-ranked ``propose_top_containers``,
persists up to ``max_proposals`` (default 5) **preview-only** Kit container pages
idempotently by ``family_fingerprint`` in Redis, and never auto-publishes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket
from app.utils.container_proposer import normalize_market_record, propose_top_containers

logger = logging.getLogger(__name__)

CONTAINER_PREVIEWS_REDIS_KEY = "containers:kit_previews:v1"
CONTAINER_PREVIEWS_TTL_SECONDS = 7 * 86400


def merge_preview_store(
    existing: Mapping[str, Any] | None,
    new_pages: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Idempotently merge new preview pages by ``family_fingerprint`` (always state='preview')."""
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
    return {
        "kit_page_version": 1,
        "updated_at": now.isoformat(),
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
    covered_ids: frozenset[int] | set[int] = frozenset(),
    dismissed_keys: tuple[str, ...] = (),
    now: datetime | None = None,
    max_proposals: int = 5,
    audit_top_n: int = 15,
    redis_client: Any | None = None,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one nightly uncovered-family proposal pass (preview only, never auto-published)."""
    ref_now = now if now is not None else datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    if markets is None:
        if session is not None:
            markets = await load_open_markets_snapshot(session)
        elif session_factory is not None:
            async with session_factory() as db_sess:
                markets = await load_open_markets_snapshot(db_sess)
        else:
            from app.tasks.base import get_task_session
            async with get_task_session() as db_sess:
                markets = await load_open_markets_snapshot(db_sess)

    result = propose_top_containers(
        markets or (),
        covered_ids=covered_ids,
        now=ref_now,
        max_proposals=max_proposals,
        audit_top_n=audit_top_n,
        dismissed_keys=dismissed_keys,
    )

    stored_payload: dict[str, Any] | None = None
    if redis_client is not None:
        raw_prev = redis_client.get(CONTAINER_PREVIEWS_REDIS_KEY)
        prev_obj = json.loads(raw_prev) if raw_prev else None
        stored_payload = merge_preview_store(prev_obj, result["pages"], now=ref_now)
        redis_client.set(
            CONTAINER_PREVIEWS_REDIS_KEY,
            json.dumps(stored_payload),
            ex=CONTAINER_PREVIEWS_TTL_SECONDS,
        )

    logger.info(
        "[container-proposer] uncovered_families=%d proposed=%d audited=%d",
        result["uncovered_family_count"],
        result["count"],
        len(result["ranked_audit"]),
    )
    return {
        "status": "complete",
        "snapshot_captured_at": result["snapshot_captured_at"],
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
