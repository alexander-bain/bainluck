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
    from app.tasks.enrich_tmdb import (
        _extract_quoted_title,
        _fetch_tmdb_trending,
        _fetch_music_charts,
        _normalize_title,
    )

    now = datetime.now(timezone.utc)
    r = get_redis_client()
    scored = 0
    errors = 0
    started = time.monotonic()

    # #882 slice 4: load the TMDB-trending title set (cached 12h in Redis so the
    # 2h interestingness run doesn't hammer TMDB). Empty set = feature no-ops.
    trending_titles: set[str] = set()
    try:
        cached = r.get("tmdb:trending_titles")
        if cached:
            trending_titles = set(json.loads(cached))
        else:
            trending_titles = await _fetch_tmdb_trending()
            if trending_titles:
                r.setex("tmdb:trending_titles", 43200, json.dumps(sorted(trending_titles)))
    except Exception:
        logger.warning("TMDB trending load failed — interestingness runs without it", exc_info=True)
        trending_titles = set()

    # #882 slice 3: load the music-charts title set (cached 12h; same pattern).
    charting_titles: set[str] = set()
    try:
        cached_m = r.get("music:charting_titles")
        if cached_m:
            charting_titles = set(json.loads(cached_m))
        else:
            charting_titles = await _fetch_music_charts()
            if charting_titles:
                r.setex("music:charting_titles", 43200, json.dumps(sorted(charting_titles)))
    except Exception:
        logger.warning("Music charts load failed — interestingness runs without it", exc_info=True)
        charting_titles = set()

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

            # #882 slice 4: entertainment-only TMDB-trending match (bounded boost).
            # Reliable signals: a quoted subject title, OR a trending title (>=5
            # chars) appearing in the normalized market name.
            is_trending = False
            is_charting = False
            if market.llm_sport_category == "entertainment" and (
                trending_titles or charting_titles
            ):
                quoted = _normalize_title(_extract_quoted_title(market.name))
                norm_name = _normalize_title(market.name)
                if trending_titles:
                    if quoted and quoted in trending_titles:
                        is_trending = True
                    else:
                        is_trending = any(
                            len(t) >= 5 and t in norm_name for t in trending_titles
                        )
                if charting_titles:
                    if quoted and quoted in charting_titles:
                        is_charting = True
                    else:
                        is_charting = any(
                            len(t) >= 5 and t in norm_name for t in charting_titles
                        )

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
                trending=is_trending,
                charting=is_charting,
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
