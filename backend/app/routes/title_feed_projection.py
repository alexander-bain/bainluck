"""Use the verified title board for the Sports preview and its quote refresh."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.utils.futures_source_mark import (
    describe_field_normalization,
    verified_futures_source_mark,
)
from app.utils.futures_verified_title import (
    Composition,
    Refusal,
    SUPER_BOWL_2027_BOARD_ID,
)
from app.utils.source_mark import no_source_mark


async def project_super_bowl_card(
    items: list[dict],
    db: AsyncSession,
    *,
    wait_seconds: float = 0.0,
) -> list[dict]:
    """Render the held title verdict without a venue scan on the feed session.

    The request can start the existing singleflight resolver on a spare
    connection. A worker warming the page can wait for that same resolver.
    Until it has an answer, the card keeps its place with its prices withheld.
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
    from app.routes.futures import _held_verified_title

    verdict = _held_verified_title(SUPER_BOWL_2027_BOARD_ID)
    engine = getattr(db, "bind", None)
    if (
        verdict is None
        and isinstance(engine, AsyncEngine)
        and _verified_title_pool_available(engine)
    ):
        task = _verified_title_in_background(engine, SUPER_BOWL_2027_BOARD_ID)
        if wait_seconds > 0:
            try:
                verdict = await asyncio.wait_for(
                    asyncio.shield(task), timeout=wait_seconds
                )
            except TimeoutError:
                pass

    item = items[index]
    data = item["data"]
    prewarmed = data.get("representation") == "verified_title"
    # A completed membership refusal uses the same source board as detail.
    if (
        isinstance(verdict, Refusal)
        and verdict.reason != "resolver_error"
        and not prewarmed
    ):
        return items
    if verdict is None and prewarmed:
        return items  # The prewarmed page already carries the verified field.

    rows = []
    sources = []
    if isinstance(verdict, Composition) and verdict.display_overlay is not None:
        sources = verdict.contributing_sources
        for outcome_id, fields in verdict.display_overlay.items():
            overlay = verdict.overlay.get(outcome_id)
            if (
                overlay is None
                or fields.get("name") is None
                or fields["probability"] is None
            ):
                continue
            mark = verified_futures_source_mark(
                overlay.source_inputs,
                overlay.probability,
                overlay.aggregation_rule,
            )
            describe_field_normalization(
                mark,
                input_probability=overlay.probability,
                displayed_probability=fields["probability"],
            )
            rows.append(
                {"id": outcome_id, **fields, "source_mark": mark, "movement": None}
            )
        rows.sort(key=lambda row: row["probability"], reverse=True)
    else:
        rows = [
            {
                "id": row["id"],
                "name": row["name"],
                "probability": None,
                "source_mark": no_source_mark("no_probability"),
                "movement": None,
            }
            for row in data.get("top_outcomes") or ()
        ]

    revision_by_id = data.get("outcome_revision_at") or {}
    top_outcomes = rows[:3]
    for rank, row in enumerate(top_outcomes, 1):
        row["rank"] = rank if row["probability"] is not None else None
        if stamp := revision_by_id.get(str(row["id"])):
            row["price_revision_at"] = row["price_observed_at"] = stamp
    projected = {
        **data,
        "top_outcomes": top_outcomes,
        "source_count": len(sources),
        "sources": list(sources),
        "representation": "verified_title" if sources else None,
        "full_field_rendered": bool(rows)
        and all(row.get("rendered_percent") is not None for row in rows),
        "card_sum_reason": None,
        "price_observed_at": None,
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
