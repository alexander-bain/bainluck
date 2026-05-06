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
from datetime import datetime, timedelta, timezone

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


def _load_polymarket_blurbs() -> list[dict]:
    """Load curated Polymarket email blurbs for few-shot examples."""
    import json
    from pathlib import Path
    blurb_file = Path(__file__).parent.parent / "data" / "polymarket_blurbs.json"
    if not blurb_file.exists():
        return []
    try:
        return json.loads(blurb_file.read_text())
    except Exception:
        return []


def _needs_regeneration(market, current_leader_name: str, now: datetime) -> bool:
    """Check if an existing hook should be regenerated."""
    if not market.hook_description:
        return True
    if not market.hook_generated_at:
        return True
    age_hours = (now - market.hook_generated_at).total_seconds() / 3600
    if age_hours < 24 and market.hook_leader_at_generation == current_leader_name:
        return False
    if market.hook_leader_at_generation and market.hook_leader_at_generation != current_leader_name:
        return True
    if age_hours >= 24:
        return True
    return False


async def enrich_market_hooks(limit: int = 50):
    """Generate Polymarket-style context blurbs for markets."""
    import random
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.llm import _get_client
    from sqlalchemy import or_

    client = _get_client()
    if not client:
        logger.info("OpenAI not available — skipping hook enrichment")
        return {"skipped": True}

    now = datetime.now(timezone.utc)
    stats = {"processed": 0, "generated": 0, "regenerated": 0, "skipped": 0, "errors": 0}

    blurbs = _load_polymarket_blurbs()

    async with get_task_session() as session:
        # Prioritize markets missing hooks entirely over stale regenerations
        result = await session.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.status == "open",
                or_(
                    FuturesMarket.hook_description.is_(None),
                    FuturesMarket.hook_generated_at.is_(None),
                    FuturesMarket.hook_generated_at < now - timedelta(hours=24),
                ),
            )
            .order_by(
                FuturesMarket.hook_description.is_(None).desc(),
                FuturesMarket.market_tier.asc().nullslast(),
                FuturesMarket.resolution_date.asc().nullslast(),
            )
            .limit(limit * 3)
        )
        candidates = result.scalars().all()

        processed = 0
        for market in candidates:
            if processed >= limit:
                break

            outcome_result = await session.execute(
                select(
                    FuturesOutcome.name,
                    FuturesOutcome.current_probability,
                    FuturesOutcome.opening_probability,
                    FuturesOutcome.probability_change_24h,
                )
                .where(FuturesOutcome.market_id == market.id)
                .order_by(FuturesOutcome.rank.asc().nullslast())
                .limit(5)
            )
            outcomes = outcome_result.all()
            if not outcomes:
                continue

            leader = outcomes[0]
            leader_name = leader.name

            if not _needs_regeneration(market, leader_name, now):
                stats["skipped"] += 1
                continue

            was_regen = market.hook_description is not None

            # Build leaderboard context
            leaderboard_lines = []
            for i, o in enumerate(outcomes):
                prob = int((o.current_probability or 0) * 100)
                opening = int((o.opening_probability or 0) * 100) if o.opening_probability else None
                change = o.probability_change_24h
                parts = [f"#{i+1} {o.name}: {prob}%"]
                if opening and abs(prob - opening) >= 3:
                    parts.append(f"(opened {opening}%)")
                if change and abs(change) >= 0.01:
                    parts.append(f"{'↑' if change > 0 else '↓'}{abs(int(change * 100))}% 24h")
                leaderboard_lines.append(" ".join(parts))

            resolve_str = ""
            if market.resolution_date:
                resolve_str = f"Resolves: {market.resolution_date.strftime('%b %d, %Y')}"

            volume_str = ""
            if market.volume_24h and market.volume_24h > 0:
                vol = market.volume_24h
                if vol >= 1_000_000:
                    volume_str = f"24h volume: ${vol/1_000_000:.1f}M"
                elif vol >= 1_000:
                    volume_str = f"24h volume: ${vol/1_000:.0f}K"

            # Pick 2-3 random Polymarket blurb examples for variety
            examples = random.sample(blurbs, min(3, len(blurbs))) if blurbs else []
            example_str = "\n".join(f'- "{ex["blurb"]}"' for ex in examples) if examples else (
                '- "The son of former Brazilian president Bolsonaro has surged into the lead, buoyed by new polls showing right-wing momentum"\n'
                '- "Cameron Young is running away with the Cadillac Championship after a tournament-record 64 in round one"\n'
                '- "Fed Chair Powell hinted at rate cuts, sending this market surging — three of four economists now expect a cut by September"'
            )

            prompt = (
                f"Write 1-2 sentences (max 250 chars) explaining WHY a reader should care about this topic RIGHT NOW. "
                f"Write like a journalist, not a market description. Focus on what happened, what changed, or why this matters. "
                f"NEVER include specific percentages or probability numbers — those are shown separately and go stale. "
                f"NEVER reference prediction markets, Polymarket, Kalshi, odds, traders, betting, or gambling — write as pure news context.\n\n"
                f"Market: {market.name}\n"
                f"Category: {market.llm_sport_category or 'general'}\n"
                f"Leaderboard:\n" + "\n".join(leaderboard_lines) + "\n"
                f"{resolve_str}\n"
                f"{volume_str}\n\n"
                f"Examples of great hooks:\n{example_str}\n\n"
                f"Your hook:"
            )

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.7,
                )
                hook = response.choices[0].message.content.strip().strip('"').strip("'")
                if "%" in hook:
                    hook = re.sub(r"\d+(\.\d+)?%", "", hook).strip()
                    hook = re.sub(r"\s{2,}", " ", hook)
                if len(hook) > 500:
                    hook = hook[:497] + "..."

                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market.id)
                    .values(
                        hook_description=hook,
                        hook_generated_at=now,
                        hook_leader_at_generation=leader_name,
                    )
                )
                stats["generated"] += 1
                if was_regen:
                    stats["regenerated"] += 1
            except Exception as e:
                logger.error("Hook generation error for market %d: %s", market.id, e)
                stats["errors"] += 1

            stats["processed"] += 1
            processed += 1
            await asyncio.sleep(0.3)

        await session.commit()

    logger.info("Hook enrichment: %s", stats)
    return stats
