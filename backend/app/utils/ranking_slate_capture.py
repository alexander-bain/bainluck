"""#12095 Decide 37-B: the nightly slate capture (reads the served Discover deck).

Split from ``app/utils/ranking_eval.py`` so the feed route, which imports that
module for the switch and the ranker version, never sits in an import cycle
with the code that calls the feed route: this module imports ``app.routes.feed``
(lazily) and nothing imports this module back from there.

Off unless ``RANKING_SNAPSHOTS`` is on; see ``ranking_eval`` for the slate shape.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.utils.ranking_eval import (
    MAX_CANDIDATES,
    RETENTION_DAYS,
    SLATE_ID_MAX,
    STALE_PRICE_AGE_S,
    SURFACE_DISCOVER,
    build_slate,
    ranker_version,
    ranking_snapshots_enabled,
)

logger = logging.getLogger(__name__)


def _anonymous_request():
    from starlette.requests import Request

    return Request(
        {"type": "http", "method": "GET", "path": "/api/feed", "headers": [], "query_string": b""}
    )


async def read_served_discover_deck(db: Any) -> dict:
    """The Discover deck exactly as an anonymous reader's ``GET /api/feed`` gets
    it: the route function itself, anonymous, no pin, first page wide enough to
    hold the whole deck."""
    from fastapi import Response

    from app.routes.feed import get_feed

    return await get_feed(
        response=Response(),
        request=_anonymous_request(),
        limit=MAX_CANDIDATES,
        offset=0,
        sport=None,
        category=None,
        include_events=True,
        include_futures=True,
        my_teams_only=False,
        mode=None,
        tags=None,
        event_pct=None,
        edition=None,
        debug=False,
        debug_ground_truth=False,
        debug_personalization=False,
        exclude_reviewed=False,
        reviewer=None,
        reviewed_surface=None,
        secret=None,
        db=db,
        user=None,
    )


async def read_scored_futures(db: Any, now: datetime) -> list[dict]:
    """The anonymous futures pool in the ranker's own order (#142's read)."""
    from app.routes.feed import _rank_key, _score_futures
    from app.utils.personalization import PersonalizationContext

    scored = await _score_futures(db, now, None, PersonalizationContext())
    scored.sort(key=_rank_key, reverse=True)
    return scored


async def read_market_facts(db: Any, futures_ids: list[int]) -> dict[int, dict]:
    """Per futures id: the largest |24h move| across its outcomes, the market's
    ``updated_at``, its ``market_tier`` and its stored ``market_tags`` (#11937:
    the ``stakes:*`` tags live only on the row). One indexed read by primary key."""
    if not futures_ids:
        return {}
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    rows = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id.in_(futures_ids))
    )
    facts: dict[int, dict] = {}
    for market in rows.scalars().all():
        moves = [
            abs(float(o.probability_change_24h))
            for o in market.outcomes
            if o.probability_change_24h is not None
        ]
        facts[market.id] = {
            "movement_24h": max(moves) if moves else None,
            "updated_at": market.updated_at,
            "market_tier": market.market_tier,
            "market_tags": list(market.market_tags or []),
        }
    return facts


async def read_event_facts(db: Any, event_ids: list[int]) -> dict[int, dict]:
    """Per event id: the row's stored ``event_tags`` (#11937). A served game card
    carries only the inline tags, which hold no ``stakes:*``; the event scorer
    boosts on the stored ones. One indexed read by primary key, two columns."""
    if not event_ids:
        return {}
    from sqlalchemy import select

    from app.models.models import Event

    rows = await db.execute(select(Event.id, Event.event_tags).where(Event.id.in_(event_ids)))
    return {eid: {"event_tags": list(tags or [])} for eid, tags in rows.all()}


def _ids(items: list[dict], kind: str) -> list[int]:
    """Integer ids of ``kind`` cards among ``items`` and their bundle members."""
    found: set[int] = set()
    for it in items:
        cards = [it]
        if it.get("type") == "bundle":
            cards += [m for m in ((it.get("data") or {}).get("items") or []) if isinstance(m, dict)]
        for card in cards:
            ident = (card.get("data") or {}).get("id")
            if card.get("type") == kind and isinstance(ident, int) and not isinstance(ident, bool):
                found.add(ident)
    return sorted(found)


def _not_captured(result: dict[str, Any]) -> dict[str, Any]:
    """A night with no slate is loud: logged at ERROR, never a quiet WARNING."""
    logger.error("ranking slate: nothing captured: %s", result)
    return result


async def snapshot_ranking_slate(
    db: Any,
    *,
    now: datetime | None = None,
    surface: str = SURFACE_DISCOVER,
    read_deck=read_served_discover_deck,
    read_pool=read_scored_futures,
    read_facts=read_market_facts,
    read_events=read_event_facts,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Take one slate snapshot. Returns a run summary; never raises past a
    failed read (the summary says what failed). Off unless the switch is on.

    Statuses: ``ok``; ``ok_partial`` (stored, but the candidate pool, the
    market facts or the event facts read failed — ``pool_error`` /
    ``facts_error`` / ``event_facts_error`` say which, so a failure never reads
    as an empty pool); ``deck_read_failed``,
    ``degraded_deck``, ``empty_deck`` (nothing stored, logged at ERROR)."""
    if not ranking_snapshots_enabled(environ):
        return {"status": "disabled"}
    from sqlalchemy import delete

    from app.models.models import RankingSlateSnapshot

    now = now or datetime.now(timezone.utc)
    try:
        payload = await read_deck(db)
    except Exception as exc:  # noqa: BLE001 — a failed capture is reported, not raised
        return _not_captured({"status": "deck_read_failed", "error": str(exc)[:200]})
    if not isinstance(payload, dict) or payload.get("build_quality", "complete") != "complete":
        reason = payload.get("degraded_reason") if isinstance(payload, dict) else "no_payload"
        return _not_captured({"status": "degraded_deck", "reason": reason})
    served = list(payload.get("items") or [])
    edition = payload.get("edition")
    if not served or not edition:
        return _not_captured({"status": "empty_deck", "served": len(served)})

    pool_error = facts_error = None
    try:
        pool = await read_pool(db, now)
    except Exception as exc:  # noqa: BLE001 — the served order alone is still a slate
        pool_error = str(exc)[:200]
        logger.error("ranking slate: candidate pool read failed: %s", pool_error)
        pool = []
    futures_ids = _ids([*served, *pool], "futures")
    try:
        facts = await read_facts(db, futures_ids)
    except Exception as exc:  # noqa: BLE001 — card payload features still stand
        facts_error = str(exc)[:200]
        logger.error("ranking slate: market facts read failed: %s", facts_error)
        facts = {}
    event_facts_error = None
    try:
        event_facts = await read_events(db, _ids(served, "event"))
    except Exception as exc:  # noqa: BLE001 — stakes then read unknown, never empty
        event_facts_error = str(exc)[:200]
        logger.error("ranking slate: event facts read failed: %s", event_facts_error)
        event_facts = {}

    served_order, candidates = build_slate(
        served, pool, now=now, market_facts=facts, event_facts=event_facts
    )
    version = ranker_version(environ)
    summary = {
        "served_count": len(served_order),
        "candidate_count": len(candidates),
        "pool_scored": len(pool),
        "deck_total": payload.get("total"),
        "deck_cache_status": (payload.get("cache") or {}).get("status")
        if isinstance(payload.get("cache"), dict)
        else None,
        "stale_rule_s": STALE_PRICE_AGE_S,
        "not_stored": ["movement_1h", "movement_7d"],
        "pool_error": pool_error,
        "facts_error": facts_error,
        "event_facts_error": event_facts_error,
    }
    row_id = str(uuid4())
    db.add(
        RankingSlateSnapshot(
            id=row_id,
            surface=surface,
            slate_id=str(edition)[:SLATE_ID_MAX],
            captured_at=now,
            ranker_version=version,
            served_order=served_order,
            candidates=candidates,
            summary=summary,
        )
    )
    await db.execute(
        delete(RankingSlateSnapshot).where(
            RankingSlateSnapshot.captured_at < now - timedelta(days=RETENTION_DAYS)
        )
    )
    await db.commit()
    return {
        "status": "ok_partial" if (pool_error or facts_error or event_facts_error) else "ok",
        "id": row_id,
        "slate_id": str(edition)[:SLATE_ID_MAX],
        "ranker_version": version,
        **summary,
    }


