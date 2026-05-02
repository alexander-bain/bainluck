"""
Market enrichment tasks: image fetching and LLM hook descriptions.

Runs nightly to enrich FuturesMarket rows with:
1. image_url — relevant photo from Pexels API
2. hook_description — LLM-generated 1-sentence hook explaining why the market is interesting
"""

import os
import logging
import asyncio
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")


def _extract_image_keywords(name: str, category: str | None) -> str:
    name = re.sub(r"\b(Winner|Over/Under|O/U|Spread|Total|Moneyline)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(on|at|in|the|a|an|of|for|to|vs\.?|by)\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\d{4}[-/]\d{2,4}", "", name)
    name = re.sub(r"[:\-–—|()#]", " ", name)
    words = [w for w in name.split() if len(w) > 2][:4]
    if not words and category:
        words = [category]
    return " ".join(words)


async def _fetch_pexels_image(query: str) -> str | None:
    if not PEXELS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY},
            )
            if resp.status_code != 200:
                logger.warning("Pexels API returned %d for query '%s'", resp.status_code, query)
                return None
            data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                return None
            return photos[0]["src"]["medium"]
    except Exception as e:
        logger.error("Pexels fetch error for '%s': %s", query, e)
        return None


async def enrich_market_images(limit: int = 50):
    """Fetch images from Pexels for markets missing image_url."""
    from app.models.models import FuturesMarket

    if not PEXELS_API_KEY:
        logger.info("PEXELS_API_KEY not set — skipping image enrichment")
        return {"skipped": True}

    stats = {"fetched": 0, "found": 0, "errors": 0}

    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket.id, FuturesMarket.name, FuturesMarket.llm_sport_category)
            .where(
                FuturesMarket.image_url.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.volume_24h.desc().nullslast())
            .limit(limit)
        )
        markets = result.all()

        for market_id, name, category in markets:
            query = _extract_image_keywords(name, category)
            if not query.strip():
                continue

            url = await _fetch_pexels_image(query)
            stats["fetched"] += 1

            if url:
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market_id)
                    .values(image_url=url)
                )
                stats["found"] += 1
            else:
                stats["errors"] += 1

            await asyncio.sleep(0.5)

        await session.commit()

    logger.info("Image enrichment: %s", stats)
    return stats


async def enrich_market_hooks(limit: int = 50):
    """Generate LLM hook descriptions for markets missing hook_description."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client

    client = _get_client()
    if not client:
        logger.info("OpenAI not available — skipping hook enrichment")
        return {"skipped": True}

    stats = {"processed": 0, "generated": 0, "errors": 0}

    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.hook_description.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(
                FuturesMarket.market_tier.asc().nullslast(),
                FuturesMarket.resolution_date.asc().nullslast(),
            )
            .limit(limit)
        )
        markets = result.scalars().all()

        for market in markets:
            # Get top outcomes for context
            outcome_result = await session.execute(
                select(FuturesOutcome.name, FuturesOutcome.current_probability, FuturesOutcome.probability_change_24h)
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(5)
            )
            outcomes = outcome_result.all()
            if not outcomes:
                continue

            leader = outcomes[0]
            leader_prob = f"{int((leader.current_probability or 0) * 100)}%"
            movement = leader.probability_change_24h
            movement_str = ""
            if movement and abs(movement) >= 0.01:
                movement_str = f" {'Up' if movement > 0 else 'Down'} {abs(int(movement * 100))}% in 24h."

            resolve_str = ""
            if market.resolution_date:
                resolve_str = f" Resolves {market.resolution_date.strftime('%b %d')}."

            runner_up = outcomes[1] if len(outcomes) > 1 else None
            runner_str = ""
            if runner_up and runner_up.current_probability and runner_up.current_probability > 0.05:
                runner_str = f" Runner-up: {runner_up.name} at {int(runner_up.current_probability * 100)}%."

            prompt = (
                f"Write a single compelling sentence (max 120 chars) describing this prediction market for a casual audience. "
                f"Be specific and interesting — explain WHAT'S HAPPENING, not just what the market is.\n\n"
                f"Market: {market.name}\n"
                f"Leader: {leader.name} at {leader_prob}{movement_str}{runner_str}{resolve_str}\n"
                f"Category: {market.llm_sport_category or 'general'}\n\n"
                f"Example good hooks:\n"
                f'- "SGA has locked up MVP since January — no challenger within 30 points"\n'
                f'- "Oil tumbled 8% after OPEC surprise output hike"\n'
                f'- "Down from 45% after Vatican denied the visit request"\n'
                f"Your hook:"
            )

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=60,
                    temperature=0.7,
                )
                hook = response.choices[0].message.content.strip().strip('"').strip("'")
                if len(hook) > 300:
                    hook = hook[:297] + "..."

                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(hook_description=hook)
                )
                stats["generated"] += 1
            except Exception as e:
                logger.error("Hook generation error for market %d: %s", market.id, e)
                stats["errors"] += 1

            stats["processed"] += 1
            await asyncio.sleep(0.3)

        await session.commit()

    logger.info("Hook enrichment: %s", stats)
    return stats
