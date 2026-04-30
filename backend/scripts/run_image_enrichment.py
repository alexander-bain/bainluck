#!/usr/bin/env python3
"""One-shot script to populate market images and hooks for feed-visible markets."""
import asyncio
import logging
logging.basicConfig(level=logging.INFO)

from sqlalchemy import select, update
from app.tasks.base import get_task_session
from app.tasks.enrich_markets import _fetch_pexels_image, _extract_image_keywords

async def enrich_feed_markets():
    """Enrich markets that actually appear in the feed."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client

    stats = {"images": 0, "hooks": 0}
    client = _get_client()

    async with get_task_session() as session:
        # Get open markets ordered by how the feed would rank them
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.image_url.is_(None),
            )
            .order_by(FuturesMarket.updated_at.desc())
            .limit(200)
        )
        markets = result.scalars().all()
        print(f"Found {len(markets)} markets missing images")

        for market in markets:
            # Image
            query = _extract_image_keywords(market.name, market.llm_sport_category)
            if query.strip():
                url = await _fetch_pexels_image(query)
                if url:
                    await session.execute(
                        update(FuturesMarket)
                        .where(FuturesMarket.id == market.id)
                        .values(image_url=url)
                    )
                    stats["images"] += 1

            # Hook
            if not market.hook_description and client:
                outcome_result = await session.execute(
                    select(FuturesOutcome.name, FuturesOutcome.current_probability, FuturesOutcome.probability_change_24h)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank.asc().nullslast())
                    .limit(3)
                )
                outcomes = outcome_result.all()
                if outcomes:
                    leader = outcomes[0]
                    prob = f"{int((leader.current_probability or 0) * 100)}%"
                    try:
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content":
                                f"Write ONE compelling sentence (max 100 chars) about this prediction market for a casual audience. "
                                f"Be specific about what's happening.\n\n"
                                f"Market: {market.name}\nLeader: {leader.name} at {prob}\n"
                                f"Category: {market.llm_sport_category or 'general'}\nYour hook:"}],
                            max_tokens=50,
                            temperature=0.7,
                        )
                        hook = response.choices[0].message.content.strip().strip('"').strip("'")
                        await session.execute(
                            update(FuturesMarket)
                            .where(FuturesMarket.id == market.id)
                            .values(hook_description=hook[:300])
                        )
                        stats["hooks"] += 1
                    except Exception as e:
                        print(f"  Hook error for {market.id}: {e}")

            await asyncio.sleep(0.3)

        await session.commit()

    print(f"Done: {stats}")

asyncio.run(enrich_feed_markets())
