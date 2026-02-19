"""
Polymarket prediction market polling task.

Fetches sports and non-sports prediction market data from Polymarket's
public API (no API key required). Stores as futures markets/outcomes
with source="polymarket".
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


# =========================================================================
# Tag-to-category mapping
# =========================================================================

# Map Polymarket tags to our internal llm_sport_category values.
# Polymarket provides rich tagging — use it to avoid unnecessary LLM calls.
_TAG_TO_CATEGORY: dict[str, str] = {
    # Sports
    "nba": "basketball",
    "basketball": "basketball",
    "ncaab": "basketball",
    "wnba": "basketball",
    "nfl": "football",
    "football": "football",
    "ncaaf": "football",
    "college football": "football",
    "mlb": "baseball",
    "baseball": "baseball",
    "nhl": "hockey",
    "hockey": "hockey",
    "ufc": "mma",
    "mma": "mma",
    "fighting": "mma",
    "soccer": "soccer",
    "epl": "soccer",
    "premier league": "soccer",
    "la liga": "soccer",
    "champions league": "soccer",
    "ucl": "soccer",
    "bundesliga": "soccer",
    "serie a": "soccer",
    "mls": "soccer",
    "ligue 1": "soccer",
    "liga mx": "soccer",
    "copa america": "soccer",
    "world cup": "soccer",
    "fifa": "soccer",
    "golf": "golf",
    "pga": "golf",
    "masters": "golf",
    "tennis": "tennis",
    "atp": "tennis",
    "wta": "tennis",
    "wimbledon": "tennis",
    "us open tennis": "tennis",
    "boxing": "boxing",
    "cricket": "cricket",
    "ipl": "cricket",
    "rugby": "rugby",
    "motorsports": "motorsports",
    "f1": "motorsports",
    "formula 1": "motorsports",
    "nascar": "motorsports",
    "indycar": "motorsports",
    "motogp": "motorsports",
    "olympics": "olympics",
    "olympic": "olympics",
    "summer olympics": "olympics",
    "winter olympics": "olympics",
    "esports": "esports",
    "gaming": "esports",
    "horse racing": "horse_racing",
    "horse-racing": "horse_racing",
    "kentucky derby": "horse_racing",
    "lacrosse": "lacrosse",
    "cycling": "other",
    "swimming": "olympics",
    "track and field": "olympics",
    "athletics": "olympics",
    # Non-sports
    "politics": "politics",
    "elections": "politics",
    "trump": "politics",
    "congress": "politics",
    "senate": "politics",
    "entertainment": "entertainment",
    "oscars": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "tv": "entertainment",
    "awards": "entertainment",
    "grammys": "entertainment",
    "emmys": "entertainment",
    "crypto": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "solana": "crypto",
    "defi": "crypto",
    "nft": "crypto",
    "economy": "economics",
    "fed": "economics",
    "inflation": "economics",
    "gdp": "economics",
    "interest rates": "economics",
    "stocks": "economics",
    "stock market": "economics",
    "tech": "tech",
    "ai": "tech",
    "science": "tech",
    "spacex": "tech",
    "apple": "tech",
    "google": "tech",
    "weather": "weather",
    "climate": "weather",
    "hurricane": "weather",
    "temperature": "weather",
    # Geopolitics / International
    "geopolitics": "geopolitics",
    "war": "geopolitics",
    "ukraine": "geopolitics",
    "russia": "geopolitics",
    "china": "geopolitics",
    "nato": "geopolitics",
    "middle east": "geopolitics",
    "israel": "geopolitics",
    "iran": "geopolitics",
    "north korea": "geopolitics",
    "nuclear": "geopolitics",
    "sanctions": "geopolitics",
    "diplomacy": "geopolitics",
    "conflict": "geopolitics",
    # Legal / Regulatory
    "legal": "legal",
    "supreme court": "legal",
    "scotus": "legal",
    "regulation": "legal",
    "lawsuit": "legal",
    "trial": "legal",
    "indictment": "legal",
    # Health / Science
    "health": "health",
    "pandemic": "health",
    "covid": "health",
    "vaccine": "health",
    "fda": "health",
    "bird flu": "health",
    "virus": "health",
    # Space / Science
    "space": "tech",
    "nasa": "tech",
    "mars": "tech",
    "rocket": "tech",
    # Finance (more specific)
    "finance": "economics",
    "markets": "economics",
    "wall street": "economics",
    "ipo": "economics",
    "earnings": "economics",
    "bonds": "economics",
    "commodities": "economics",
    "real estate": "economics",
    "housing": "economics",
    "tariffs": "economics",
    "trade war": "economics",
    # Education / Academic
    "education": "culture",
    "university": "culture",
    "nobel": "culture",
    # Social / Culture
    "social media": "culture",
    "tiktok": "culture",
    "twitter": "culture",
    "celebrity": "entertainment",
    "pop culture": "entertainment",
    # Broad catch-alls
    "culture": "entertainment",
    "world": "politics",
    "news": "politics",
    "global": "geopolitics",
    "environment": "weather",
    # Note: "sports" is NOT in this dict — it's handled specially in
    # _tags_to_category() as a fallback that returns ("championship", None)
}

# Categories that map to "championship" internal category for sport-linked futures
_SPORT_CATEGORIES = {
    "basketball", "football", "baseball", "hockey", "mma", "soccer",
    "golf", "tennis", "boxing", "cricket", "rugby", "motorsports",
    "olympics", "esports", "horse_racing", "lacrosse",
}


def _tags_to_category(tags: list[str]) -> tuple[str, Optional[str]]:
    """
    Map Polymarket tags to (internal_category, llm_sport_category).

    Returns:
        Tuple of (category for FuturesMarket.category, llm_sport_category)
    """
    llm_sport_category = None

    for tag in tags:
        tag_lower = tag.lower().strip()
        if tag_lower in _TAG_TO_CATEGORY:
            mapped = _TAG_TO_CATEGORY[tag_lower]
            if mapped in _SPORT_CATEGORIES:
                return "championship", mapped
            else:
                return mapped, mapped

    # If "Sports" tag is present but no specific sport matched
    for tag in tags:
        if tag.lower().strip() == "sports":
            return "championship", None

    return "other", None


# =========================================================================
# Polling implementation
# =========================================================================

async def _poll_polymarket_markets():
    """Async implementation of Polymarket polling."""
    import asyncio
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.odds_math import probability_to_american
    from app.utils.team_linking import compute_market_tier
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    service = PolymarketAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    BATCH_SIZE = 50  # Commit every N events to limit memory

    try:
        # Stream events page-by-page instead of loading all into memory.
        # Each page is processed and committed in batches.
        max_pages = 100
        seen_ids: set[str] = set()
        batch: list = []

        for page in range(max_pages):
            if page > 0:
                await asyncio.sleep(0.3)

            try:
                events_data = await service.get_events(
                    active=True, closed=False, limit=100, offset=page * 100,
                )
            except Exception as e:
                logger.warning("Error fetching Polymarket page %d: %s", page, e)
                break

            if not events_data:
                break

            for event_data in events_data:
                event_id = str(event_data.get("id", ""))
                if not event_id or event_id in seen_ids:
                    continue
                seen_ids.add(event_id)

                parsed = service._parse_event(event_data)
                if parsed and parsed.markets:
                    batch.append(parsed)

                # Process batch when full
                if len(batch) >= BATCH_SIZE:
                    await _process_event_batch(
                        batch, stats, FuturesMarket, FuturesOutcome,
                        FuturesOddsSnapshot, pg_insert, probability_to_american,
                        compute_market_tier,
                    )
                    batch.clear()

            if len(events_data) < 100:
                break

        # Process remaining events
        if batch:
            await _process_event_batch(
                batch, stats, FuturesMarket, FuturesOutcome,
                FuturesOddsSnapshot, pg_insert, probability_to_american,
                compute_market_tier,
            )
            batch.clear()

        pages_fetched = page + 1 if events_data is not None else page
        logger.info(
            "Polymarket: fetched %d unique events across %d pages",
            len(seen_ids), pages_fetched,
        )
        if pages_fetched >= max_pages:
            logger.warning(
                "Polymarket: hit page cap (%d). There may be more events — "
                "consider raising max_pages.",
                max_pages,
            )

        stats["pages_fetched"] = pages_fetched
        stats["unique_events_seen"] = len(seen_ids)
        stats["hit_page_cap"] = pages_fetched >= max_pages

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    logger.info(
        "Polymarket poll complete: %d events, %d outcomes, %d snapshots, %d errors",
        stats["events_processed"],
        stats["outcomes_updated"],
        stats["snapshots_created"],
        len(stats["errors"]),
    )
    return stats


async def _process_event_batch(
    events, stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
    pg_insert, probability_to_american, compute_market_tier,
):
    """Process and commit a batch of Polymarket events."""
    from app.utils.futures_categorization import (
        categorize_by_rules, detect_league as _detect_league,
        infer_sport_from_league as _infer,
        detect_league, detect_season,
        compute_canonical_market_key,
        extract_olympic_discipline,
        generate_category_tags,
    )

    # Non-sport categories that shouldn't flip to "championship"
    _NON_SPORT_CATEGORIES = {
        "other", "politics", "economics", "tech", "crypto",
        "weather", "health", "geopolitics", "legal",
        "culture", "entertainment",
    }

    async with get_task_session() as session:
        now = datetime.now(timezone.utc)

        for event in events:
            try:
                if not event.markets:
                    continue

                # Determine category from tags
                category, llm_sport_category = _tags_to_category(event.tags)

                # Fall back to pattern matching + league inference if tags didn't help
                if not llm_sport_category or llm_sport_category == "other":
                    rules_result = categorize_by_rules(event.title)
                    if rules_result:
                        llm_sport_category = rules_result
                    else:
                        _league = _detect_league(event.title)
                        if _league:
                            _sport = _infer(_league)
                            if _sport:
                                llm_sport_category = _sport

                    # If we found a sport category, ensure category is "championship"
                    if llm_sport_category and llm_sport_category not in _NON_SPORT_CATEGORIES:
                        category = "championship"

                # Compute market tier
                market_tier = compute_market_tier(event.title, category)

                # Timing: use event start/end dates
                commence_time = event.start_date
                resolution_date = event.end_date

                # Detect league and season for cross-source matching
                league = detect_league(event.title)
                season = detect_season(event.title, league, resolution_date)

                # For Olympics, use specific discipline as category
                canon_category = category
                if llm_sport_category == "olympics":
                    discipline = extract_olympic_discipline(event.title)
                    if discipline:
                        canon_category = discipline
                canonical_key = compute_canonical_market_key(
                    llm_sport_category, league, canon_category, season,
                )

                # Generate category tags
                tags = generate_category_tags(
                    event.title, llm_sport_category, league, category,
                )

                # Build update set for on-conflict
                update_set = {
                    "name": event.title,
                    "market_tier": market_tier,
                    "llm_league": league,
                    "canonical_market_key": canonical_key,
                    "commence_time": commence_time,
                    "resolution_date": resolution_date,
                    "status": "open" if event.active else "resolved",
                    "category_tags": tags,
                    "updated_at": func.now(),
                }
                # Only update llm_sport_category if we have a non-"other" value
                if llm_sport_category and llm_sport_category != "other":
                    update_set["llm_sport_category"] = llm_sport_category

                # Upsert FuturesMarket
                market_stmt = pg_insert(FuturesMarket).values(
                    source="polymarket",
                    external_id=event.id,
                    name=event.title,
                    category=category,
                    llm_sport_category=llm_sport_category,
                    llm_league=league,
                    canonical_market_key=canonical_key,
                    market_tier=market_tier,
                    mutually_exclusive=event.neg_risk,
                    commence_time=commence_time,
                    resolution_date=resolution_date,
                    status="open" if event.active else "resolved",
                    category_tags=tags,
                ).on_conflict_do_update(
                    index_elements=["source", "external_id"],
                    set_=update_set,
                ).returning(FuturesMarket.id)

                result = await session.execute(market_stmt)
                futures_market_id = result.scalar_one()
                stats["events_processed"] += 1

                # Collect outcome data for ranking
                outcome_data = []

                if event.neg_risk and len(event.markets) > 1:
                    # NegRisk multi-outcome event: each market is one outcome
                    for market in event.markets:
                        if not market.outcome_prices:
                            continue

                        prob = market.outcome_prices[0] if market.outcome_prices else None
                        if prob is None or prob <= 0:
                            continue

                        outcome_name = _extract_outcome_name(
                            market.question, event.title
                        )

                        outcome_data.append({
                            "external_id": market.condition_id,
                            "name": outcome_name,
                            "prob": prob,
                            "yes_bid": market.best_bid,
                            "yes_ask": market.best_ask,
                            "last_price": market.last_trade_price,
                        })
                else:
                    # Single-market or non-negRisk event
                    for market in event.markets:
                        if not market.outcome_prices:
                            continue

                        prob = market.outcome_prices[0] if market.outcome_prices else None
                        if prob is None or prob <= 0:
                            continue

                        if len(event.markets) == 1:
                            outcome_name = "Yes"
                        else:
                            outcome_name = _extract_outcome_name(
                                market.question, event.title
                            )

                        outcome_data.append({
                            "external_id": market.condition_id,
                            "name": outcome_name,
                            "prob": prob,
                            "yes_bid": market.best_bid,
                            "yes_ask": market.best_ask,
                            "last_price": market.last_trade_price,
                        })

                # Sort by probability descending to compute ranks
                outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                # Upsert outcomes with ranks
                for rank, od in enumerate(outcome_data, 1):
                    prob = od["prob"]
                    american = probability_to_american(prob) if 0 < prob < 1 else None
                    stats["markets_processed"] += 1

                    outcome_stmt = pg_insert(FuturesOutcome).values(
                        market_id=futures_market_id,
                        external_id=od["external_id"],
                        name=od["name"],
                        current_probability=prob,
                        current_american_odds=american,
                        current_yes_bid=od["yes_bid"],
                        current_yes_ask=od["yes_ask"],
                        opening_probability=prob,
                        opening_american_odds=american,
                        opening_captured_at=now,
                        rank=rank,
                    ).on_conflict_do_update(
                        index_elements=["market_id", "external_id"],
                        set_={
                            "name": od["name"],
                            "current_probability": prob,
                            "current_american_odds": american,
                            "current_yes_bid": od["yes_bid"],
                            "current_yes_ask": od["yes_ask"],
                            "rank": rank,
                            "last_updated": func.now(),
                        },
                    ).returning(FuturesOutcome.id)

                    result = await session.execute(outcome_stmt)
                    outcome_id = result.scalar_one()
                    stats["outcomes_updated"] += 1

                    # Create snapshot
                    snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                        outcome_id=outcome_id,
                        bookmaker="polymarket",
                        probability=prob,
                        american_odds=american,
                        yes_bid=od["yes_bid"],
                        yes_ask=od["yes_ask"],
                        last_price=od["last_price"],
                        captured_at=now,
                    )
                    await session.execute(snapshot_stmt)
                    stats["snapshots_created"] += 1

            except Exception as e:
                stats["errors"].append(f"{event.id}: {str(e)}")
                continue

        await session.commit()


def _extract_outcome_name(question: str, event_title: str) -> str:
    """
    Extract a clean outcome name from a Polymarket market question.

    For negRisk markets, the question is often like:
    "Will the Los Angeles Lakers win the 2025-26 NBA Championship?"
    We want to extract "Los Angeles Lakers".

    Falls back to the full question if extraction fails.
    """
    if not question:
        return "Unknown"

    # Common patterns: "Will X win...", "Will X be...", "X to win..."
    import re

    # "Will the X win/be/become..."
    match = re.match(
        r"^Will\s+(?:the\s+)?(.+?)\s+(?:win|be|become|make|reach|qualify|finish)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # "X to win..."
    match = re.match(
        r"^(.+?)\s+to\s+(?:win|be|become|make|reach)\b",
        question,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # If question is short enough, use it directly (minus trailing ?)
    cleaned = question.rstrip("?").strip()
    if len(cleaned) <= 60:
        return cleaned

    # Last resort: use first 60 chars
    return cleaned[:60]
