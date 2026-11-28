"""Use the verified title board for the Sports preview and its quote refresh."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.utils import request_cache
from app.utils.futures_source_mark import (
    describe_field_normalization,
    verified_futures_source_mark,
)
from app.utils.futures_verified_title import (
    Composition,
    Refusal,
    SUPER_BOWL_2027_BOARD_ID,
    parse_aware,
)

logger = logging.getLogger(__name__)
_SHARED_KEY = f"sports:verified-title:v1:{SUPER_BOWL_2027_BOARD_ID}"
_CACHE_OP_MS = 50


def _has_price(row: dict) -> bool:
    probability = row.get("probability")
    return isinstance(probability, (int, float)) and 0 <= probability <= 1


def _title_projection(verdict: Composition) -> dict | None:
    """Build the same three rows for a local verdict and its shared copy."""
    rows = []
    for outcome_id, fields in (verdict.display_overlay or {}).items():
        overlay = verdict.overlay.get(outcome_id)
        if overlay is None or not fields.get("name") or not _has_price(fields):
            continue
        mark = verified_futures_source_mark(
            overlay.source_inputs, overlay.probability, overlay.aggregation_rule
        )
        describe_field_normalization(
            mark,
            input_probability=overlay.probability,
            displayed_probability=fields["probability"],
        )
        rows.append({"id": outcome_id, **fields, "source_mark": mark, "movement": None})
    if not rows or not verdict.contributing_sources:
        return None
    rows.sort(key=lambda row: row["probability"], reverse=True)
    top = rows[:3]
    clocks = [parse_aware(verdict.overlay[row["id"]].observed_at) for row in top]
    return {
        "top_outcomes": top,
        "sources": verdict.contributing_sources,
        "full_field_rendered": all(row.get("rendered_percent") is not None for row in rows),
        "price_observed_at": min(clocks).isoformat() if all(clocks) else None,
    }


async def remember_super_bowl_projection(verdict: Composition, ttl: float) -> None:
    if not math.isfinite(ttl) or ttl <= 0:
        return

    async def store():
        projection = _title_projection(verdict)
        if projection is None:
            return None
        body = json.dumps({"saved_at": time.time(), "projection": projection})
        client = await request_cache.get_shared_async_redis()
        # One agreed reading for the hold window, even when several cold
        # workers finish resolving at once.
        return await client.set(_SHARED_KEY, body, ex=math.ceil(ttl), nx=True)

    await request_cache.bounded_redis_call(store, deadline_ms=_CACHE_OP_MS)


async def _shared_title_projection(ttl: float) -> dict | None:
    if not math.isfinite(ttl) or ttl <= 0:
        return None

    async def read():
        client = await request_cache.get_shared_async_redis()
        return await client.get(_SHARED_KEY)

    result = await request_cache.bounded_redis_call(read, deadline_ms=_CACHE_OP_MS)
    if not result.is_ok or not isinstance(result.value, (str, bytes)):
        return None
    try:
        saved = json.loads(result.value)
        age = time.time() - saved["saved_at"]
        projection = saved["projection"]
        rows = projection["top_outcomes"]
        sources = projection["sources"]
        if (
            0 <= age < ttl and isinstance(rows, list) and 0 < len(rows) <= 3
            and isinstance(sources, list) and sources
            and all(isinstance(source, str) for source in sources)
            and all(isinstance(row, dict) and row.get("id") is not None
                    and row.get("name") and _has_price(row) for row in rows)
        ):
            return projection
    except (KeyError, TypeError, ValueError):
        logger.debug("Malformed shared Sports title projection", exc_info=True)
    return None


async def project_super_bowl_card(
    items: list[dict],
    db: AsyncSession,
    *,
    wait_seconds: float = 0.0,
    allow_shared: bool = True,
) -> list[dict]:
    """Render the held title verdict without a venue scan on the feed session.

    The request can start the existing singleflight resolver on a spare
    connection. A worker warming the page can wait for that same resolver.
    A cold worker can read the shared verified projection in the same hold
    window. An unpriced preview stays off the page while the resolver runs.
    """
    index = next(
        (
            index
            for index, item in enumerate(items)
            if item.get("type") == "futures"
            and (item.get("data") or {}).get("id") == SUPER_BOWL_2027_BOARD_ID
            and item["data"].get("status") == "open"
        ),
        None,
    )
    if index is None:
        return items

    from app.routes.events import (
        _verified_title_in_background,
        _verified_title_pool_available,
    )
    from app.routes.futures import _held_verified_title, _verified_title_cache_seconds

    item = items[index]
    data = item["data"]
    prewarmed = data.get("representation") == "verified_title"
    verdict = _held_verified_title(SUPER_BOWL_2027_BOARD_ID)
    projection = _title_projection(verdict) if isinstance(verdict, Composition) else None
    if verdict is None and allow_shared:
        projection = await _shared_title_projection(_verified_title_cache_seconds())
    engine = getattr(db, "bind", None)
    if (
        verdict is None
        and isinstance(engine, AsyncEngine)
        and _verified_title_pool_available(engine)
    ):
        task = _verified_title_in_background(engine, SUPER_BOWL_2027_BOARD_ID)
        if wait_seconds > 0 and projection is None:
            try:
                verdict = await asyncio.wait_for(
                    asyncio.shield(task), timeout=wait_seconds
                )
                if isinstance(verdict, Composition):
                    projection = _title_projection(verdict)
            except TimeoutError:
                pass

    if projection is None:
        # A completed membership refusal uses the same source board as detail.
        use_source = (
            isinstance(verdict, Refusal)
            and verdict.reason != "resolver_error"
            and not prewarmed
        )
        if use_source or (verdict is None and prewarmed):
            original = data.get("top_outcomes") or []
            priced = [row for row in original if _has_price(row)]
            if priced:
                if len(priced) == len(original):
                    return items
                updated = {**item, "data": {**data, "top_outcomes": priced}}
                return [*items[:index], updated, *items[index + 1 :]]
        logger.info("sports title projection withheld market_id=%s", SUPER_BOWL_2027_BOARD_ID)
        return items[:index] + items[index + 1 :]

    revision_by_id = data.get("outcome_revision_at") or {}
    top_outcomes = [dict(row) for row in projection["top_outcomes"]]
    for rank, row in enumerate(top_outcomes, 1):
        row["rank"] = rank
        if stamp := revision_by_id.get(str(row["id"])):
            row["price_revision_at"] = row["price_observed_at"] = stamp
    projected = {
        **data,
        **projection,
        "top_outcomes": top_outcomes,
        "source_count": len(projection["sources"]),
        "representation": "verified_title",
        "card_sum_reason": None,
        "hook_description": None,
    }
    updated = {
        **item,
        "data": projected,
        "headline": None,
        "reason": None,
        "context_summary": None,
    }
    return [*items[:index], updated, *items[index + 1 :]]
