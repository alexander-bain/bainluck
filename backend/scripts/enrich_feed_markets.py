#!/usr/bin/env python3
"""Enrich the exact markets that appear in the feed right now."""
import asyncio
import logging
import httpx
logging.basicConfig(level=logging.INFO)

from sqlalchemy import select, update
from app.tasks.base import get_task_session
from app.tasks.enrich_markets import _fetch_pexels_image, _extract_image_keywords

API_BASE = "https://api.bainluck.com"

async def get_feed_market_ids():
    """Fetch feed and extract futures market IDs."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{API_BASE}/api/feed", params={"limit": 200})
        data = resp.json()
        ids = []
        for item in data.get("items", []):
            if item["type"] == "futures":
                ids.append(item["data"]["id"])
        return ids

async def enrich_specific(market_ids):
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client

    client = _get_client()
    stats = {"images": 0, "hooks": 0}

    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket).where(FuturesMarket.id.in_(market_ids))
        )
        markets = result.scalars().all()
        print(f"Enriching {len(markets)} feed markets")

        for market in markets:
            if not market.image_url:
                query = _extract_image_keywords(market.name, market.llm_sport_category)
                if query.strip():
                    url = await _fetch_pexels_image(query)
                    if url:
                        await session.execute(
                            update(FuturesMarket).where(FuturesMarket.id == market.id)
                            .values(image_url=url)
                        )
                        stats["images"] += 1
                    await asyncio.sleep(0.5)

            if not market.hook_description and client:
                outcomes = (await session.execute(
                    select(FuturesOutcome.name, FuturesOutcome.current_probability)
                    .where(FuturesOutcome.market_id == market.id)
                    .order_by(FuturesOutcome.rank.asc().nullslast()).limit(3)
                )).all()
                if outcomes:
                    leader = outcomes[0]
                    prob = f"{int((leader.current_probability or 0) * 100)}%"
                    try:
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content":
                                f"Write ONE sentence (max 100 chars) about this prediction market. "
                                f"Be specific. NEVER mention percentages or probability numbers.\n"
                                f"Market: {market.name}\nLeader: {leader.name}\nHook:"}],
                            max_tokens=50, temperature=0.7,
                        )
                        hook = response.choices[0].message.content.strip().strip('"\'')
                        await session.execute(
                            update(FuturesMarket).where(FuturesMarket.id == market.id)
                            .values(hook_description=hook[:300])
                        )
                        stats["hooks"] += 1
                    except Exception as e:
                        print(f"  Hook error: {e}")

        await session.commit()
    print(f"Done: {stats}")

async def main():
    ids = await get_feed_market_ids()
    print(f"Feed has {len(ids)} futures markets")
    await enrich_specific(ids)

asyncio.run(main())
