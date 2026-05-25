"""Helpers for human labeling queues."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RankingJudgment


def review_key_for_feed_item(item: dict) -> tuple[str, int] | None:
    """Return the stable judgment identity key for a feed/debug item."""
    item_type = item.get("type")
    if item_type not in {"futures", "event"}:
        return None
    data = item.get("data") or {}
    item_id = data.get("id")
    if item_id is None:
        return None
    try:
        return item_type, int(item_id)
    except (TypeError, ValueError):
        return None


def filter_reviewed_feed_items(
    items: list[dict],
    reviewed_keys: set[tuple[str, int]],
) -> tuple[list[dict], int]:
    if not reviewed_keys:
        return items, 0
    kept: list[dict] = []
    filtered = 0
    for item in items:
        key = review_key_for_feed_item(item)
        if key and key in reviewed_keys:
            filtered += 1
            continue
        kept.append(item)
    return kept, filtered


async def load_reviewed_ranking_keys(
    db: AsyncSession,
    *,
    reviewer: str | None,
    surface: str | None,
) -> set[tuple[str, int]]:
    """Load futures/event keys that already have human ranking judgments."""
    filters = [RankingJudgment.item_type.in_(["futures", "event"])]
    if reviewer:
        filters.append(RankingJudgment.reviewer == reviewer)
    if surface:
        filters.append(RankingJudgment.surface == surface)

    result = await db.execute(
        select(
            RankingJudgment.item_type,
            RankingJudgment.market_id,
            RankingJudgment.event_id,
        ).where(*filters)
    )
    reviewed: set[tuple[str, int]] = set()
    for item_type, market_id, event_id in result.all():
        if item_type == "futures" and market_id is not None:
            reviewed.add(("futures", int(market_id)))
        elif item_type == "event" and event_id is not None:
            reviewed.add(("event", int(event_id)))
    return reviewed
