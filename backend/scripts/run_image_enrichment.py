#!/usr/bin/env python3
"""Enrich ALL open markets missing images/hooks — not just recent ones."""
import asyncio
import logging
logging.basicConfig(level=logging.INFO)

from sqlalchemy import select, update, or_
from app.tasks.base import get_task_session
from app.tasks.enrich_markets import _fetch_pexels_image, _extract_image_keywords

async def enrich_all():
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client

    stats = {"images": 0, "hooks": 0, "total": 0}
    client = _get_client()

    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                or_(
                    FuturesMarket.image_url.is_(None),
                    FuturesMarket.hook_description.is_(None),
                ),
            )
            .limit(500)
        )
        markets = result.scalars().all()
        print(f"Found {len(markets)} markets needing enrichment")

        for i, market in enumerate(markets):
            stats["total"] += 1
            if i % 25 == 0:
                print(f"  Processing {i}/{len(markets)}...")

            if not market.image_url:
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

            if not market.hook_description and client:
                outcome_result = await session.execute(
                    select(FuturesOutcome.name, FuturesOutcome.current_probability)
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
                                f"Write ONE sentence (max 100 chars) about this prediction market. "
                                f"Be specific.\nMarket: {market.name}\nLeader: {leader.name} at {prob}\nHook:"}],
                            max_tokens=50, temperature=0.7,
                        )
                        hook = response.choices[0].message.content.strip().strip('"\'')
                        await session.execute(
                            update(FuturesMarket)
                            .where(FuturesMarket.id == market.id)
                            .values(hook_description=hook[:300])
                        )
                        stats["hooks"] += 1
                    except Exception as e:
                        print(f"  Hook error: {e}")

            await asyncio.sleep(0.3)

            if i % 50 == 49:
                await session.commit()
                print(f"  Committed batch at {i+1}")

        await session.commit()

    print(f"Done: {stats}")

asyncio.run(enrich_all())
