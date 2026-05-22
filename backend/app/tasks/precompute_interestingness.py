"""Precompute market interestingness scores and cache in Redis.

Runs every 2h on the background queue. Queries all feed-eligible FuturesMarket
rows, computes interestingness via the pure scorer in
``utils/market_interestingness.py``, and stores results in a Redis hash so
``GET /api/feed`` can read them without any DB or LLM calls on the hot path.

Redis key: ``interestingness:{market_id}`` → JSON with score, reasons,
computed_at. TTL 6h so stale scores expire if the task stops running.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _precompute_interestingness() -> dict:
    """Score all feed-eligible futures markets and cache in Redis."""
    from sqlalchemy import select, func, and_, or_
    from sqlalchemy.orm import load_only, selectinload

    from app.models import FuturesMarket, FuturesOutcome
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client
    from app.utils.market_interestingness import (
        MarketInterestingnessInputs,
        score_market_interestingness,
    )

    now = datetime.now(timezone.utc)
    r = get_redis_client()
    scored = 0
    errors = 0
    started = time.monotonic()

    async with get_task_session() as session:
        # Query all feed-eligible markets: open, not event-linked, not past resolution
        result = await session.execute(
            select(FuturesMarket)
            .options(
                load_only(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.llm_sport_category,
                    FuturesMarket.canonical_market_key,
                    FuturesMarket.volume_24h,
                    FuturesMarket.updated_at,
                    FuturesMarket.resolution_date,
                    FuturesMarket.market_metadata,
                    FuturesMarket.status,
                ),
                selectinload(FuturesMarket.outcomes).load_only(
                    FuturesOutcome.current_probability,
                    FuturesOutcome.probability_change_24h,
                ),
            )
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.event_id.is_(None),
                or_(
                    FuturesMarket.resolution_date.is_(None),
                    FuturesMarket.resolution_date >= now,
                ),
            )
        )
        markets = result.scalars().unique().all()

        # Build canonical_market_key -> source count map
        canonical_keys = {
            m.canonical_market_key for m in markets if m.canonical_market_key
        }
        source_counts: dict[str, int] = {}
        if canonical_keys:
            count_result = await session.execute(
                select(
                    FuturesMarket.canonical_market_key,
                    func.count(func.distinct(FuturesMarket.source)).label("cnt"),
                )
                .where(FuturesMarket.canonical_market_key.in_(canonical_keys))
                .group_by(FuturesMarket.canonical_market_key)
            )
            source_counts = {
                row.canonical_market_key: row.cnt for row in count_result.all()
            }

    # Score each market and write to Redis
    pipe = r.pipeline(transaction=False)
    for market in markets:
        try:
            # Gather inputs from DB columns
            leader_prob = None
            max_movement = 0.0
            for outcome in market.outcomes:
                prob = (
                    float(outcome.current_probability)
                    if outcome.current_probability is not None
                    else None
                )
                if prob is not None and (leader_prob is None or prob > leader_prob):
                    leader_prob = prob
                change = (
                    float(outcome.probability_change_24h)
                    if outcome.probability_change_24h is not None
                    else None
                )
                if change is not None and abs(change) > max_movement:
                    max_movement = abs(change)

            source_count = 1
            if market.canonical_market_key:
                source_count = source_counts.get(market.canonical_market_key, 1)

            llm_quality = None
            metadata = market.market_metadata or {}
            discover_llm = metadata.get("discover_llm")
            if isinstance(discover_llm, dict):
                llm_quality = discover_llm.get("quality_score")

            inputs = MarketInterestingnessInputs(
                probability=leader_prob,
                source_count=source_count,
                updated_at=market.updated_at,
                movement_24h=max_movement if max_movement > 0 else None,
                resolution_date=market.resolution_date,
                category=market.llm_sport_category,
                volume_24h=(
                    float(market.volume_24h)
                    if market.volume_24h is not None
                    else None
                ),
                llm_quality=llm_quality,
            )
            result = score_market_interestingness(inputs, now=now)

            cache_value = json.dumps(
                {
                    "score": result.score,
                    "reasons": result.reasons,
                    "computed_at": now.isoformat(),
                }
            )
            redis_key = f"interestingness:{market.id}"
            pipe.setex(redis_key, 21600, cache_value)  # TTL 6h
            scored += 1
        except Exception:
            errors += 1
            logger.warning(
                "Failed to score interestingness for market %s", market.id, exc_info=True
            )

    pipe.execute()
    duration_ms = (time.monotonic() - started) * 1000

    return {
        "status": "ok",
        "scored": scored,
        "errors": errors,
        "total_markets": len(markets),
        "duration_ms": round(duration_ms, 1),
    }
