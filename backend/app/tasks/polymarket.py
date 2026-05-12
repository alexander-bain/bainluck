"""
Polymarket prediction market polling task.

Fetches sports and non-sports prediction market data from Polymarket's
public API (no API key required). Stores as futures markets/outcomes
with source="polymarket".
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

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
    from app.utils.market_label_normalization import compute_market_tier
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    service = PolymarketAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
        "by_category": {},
        "crypto_skipped": 0,
        "total_api_events": 0,
    }

    BATCH_SIZE = 50  # Commit every N events to limit memory

    try:
        # One-time cleanup: delete orphan outcomes with NULL external_id
        try:
            async with get_task_session() as session:
                from sqlalchemy import delete as sa_delete
                from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
                orphan_sub = select(FuturesOutcome.id).where(
                    FuturesOutcome.external_id.is_(None),
                    FuturesOutcome.market_id.in_(
                        select(FuturesMarket.id).where(
                            FuturesMarket.source == "polymarket"
                        )
                    ),
                )
                orphan_ids = (await session.execute(orphan_sub)).scalars().all()
                if orphan_ids:
                    logger.info("Cleanup: deleting %d Polymarket orphan outcomes with NULL external_id", len(orphan_ids))
                    await session.execute(
                        sa_delete(FuturesOddsSnapshot).where(
                            FuturesOddsSnapshot.outcome_id.in_(orphan_ids)
                        )
                    )
                    await session.execute(
                        sa_delete(FuturesOutcome).where(
                            FuturesOutcome.id.in_(orphan_ids)
                        )
                    )
                    await session.commit()
                    logger.info("Polymarket orphan cleanup complete: %d deleted", len(orphan_ids))
        except Exception as e:
            logger.warning("Polymarket orphan cleanup failed (non-fatal): %s", e)

        # Stream events page-by-page instead of loading all into memory.
        # Each page is processed and committed in batches.
        max_pages = 130  # 13,000 events — Polymarket has 10,500+ active events
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

    stats["total_api_events"] = len(seen_ids)
    logger.info(
        "Polymarket poll: %d API events → %d processed, %d markets, %d outcomes, %d snapshots, %d crypto skipped, %d errors | by_category: %s",
        stats["total_api_events"], stats["events_processed"], stats["markets_processed"],
        stats["outcomes_updated"], stats["snapshots_created"], stats["crypto_skipped"],
        len(stats["errors"]), stats["by_category"],
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
        detect_market_type,
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

                # Skip crypto markets entirely — they consume DB space
                # without providing value to users
                if llm_sport_category == "crypto" or category == "crypto":
                    stats["crypto_skipped"] += 1
                    continue

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
                    stats["by_category"][llm_sport_category or "unknown"] = stats["by_category"].get(llm_sport_category or "unknown", 0) + 1
                    if llm_sport_category and llm_sport_category not in _NON_SPORT_CATEGORIES:
                        category = "championship"

                # Override non-sport tags when the title clearly contains a sport
                # (e.g., "Pro Baseball: 2026 AL Cy Young Winner" tagged "awards" → "entertainment")
                elif llm_sport_category in _NON_SPORT_CATEGORIES:
                    rules_result = categorize_by_rules(event.title)
                    if rules_result and rules_result not in _NON_SPORT_CATEGORIES:
                        llm_sport_category = rules_result
                        category = "championship"
                    else:
                        _league = _detect_league(event.title)
                        if _league:
                            _sport = _infer(_league)
                            if _sport and _sport not in _NON_SPORT_CATEGORIES:
                                llm_sport_category = _sport
                                category = "championship"

                # Compute market tier
                market_tier = compute_market_tier(
                    event.title, category,
                    sport_category=llm_sport_category,
                )

                # Timing: use event start/end dates
                commence_time = event.start_date
                resolution_date = event.end_date

                # Detect league and season for cross-source matching
                league = detect_league(event.title, sport_category=llm_sport_category)
                season = detect_season(event.title, league, resolution_date)

                # For Olympics, use specific discipline as category.
                # For sports markets, use detect_market_type for specificity
                # (e.g., "al_cy_young" instead of generic "championship")
                canon_category = detect_market_type(event.title)
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

                # Always assign group_id so markets can be grouped for calibration,
                # feed dedup, and category pages. Single-market events get group_id
                # too — the calibration query's group_size >= 3 threshold naturally
                # ignores groups of size 1.
                poly_group_id = f"polymarket:{event.id}"
                if event.neg_risk:
                    poly_group_type = "negrisk"
                elif len(event.markets) > 1:
                    poly_group_type = "polymarket_event"
                else:
                    poly_group_type = "polymarket_single"

                # Build market_metadata with event-level context
                poly_metadata: dict = {}
                if event.id:
                    poly_metadata["polymarket_event_id"] = event.id
                if event.title:
                    poly_metadata["event_title"] = event.title
                if event.neg_risk:
                    poly_metadata["neg_risk"] = True
                if has_multiple_markets:
                    poly_metadata["market_count"] = len(event.markets)

                # Aggregate volume/liquidity from event + markets
                poly_volume = int(event.volume) if event.volume else None
                poly_liquidity = float(event.liquidity) if event.liquidity else None
                poly_volume_24h = sum(
                    int(m.volume_24h or 0) for m in event.markets
                ) or None

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
                    "group_id": poly_group_id,
                    "group_type": poly_group_type,
                    "group_position": 0,
                    "market_metadata": poly_metadata if poly_metadata else None,
                    "updated_at": func.now(),
                    "volume": poly_volume,
                    "volume_24h": poly_volume_24h,
                    "liquidity": poly_liquidity,
                    "volume_updated_at": func.now(),
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
                    group_id=poly_group_id,
                    group_type=poly_group_type,
                    group_position=0,
                    market_metadata=poly_metadata if poly_metadata else None,
                    volume=poly_volume,
                    volume_24h=poly_volume_24h,
                    liquidity=poly_liquidity,
                    volume_updated_at=func.now(),
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
                        prob = market.outcome_prices[0] if market.outcome_prices else None

                        if prob is None or prob <= 0:
                            if (market.best_bid is not None and market.best_bid > 0
                                    and market.best_ask is not None and market.best_ask > 0):
                                prob = (market.best_bid + market.best_ask) / 2
                            elif market.last_trade_price is not None and market.last_trade_price > 0:
                                prob = market.last_trade_price
                            elif market.best_ask is not None and market.best_ask > 0:
                                prob = market.best_ask

                        if prob is None or prob <= 0:
                            continue

                        # Prefer groupItemTitle (e.g., "33°F or below") over question parsing
                        outcome_name = market.group_item_title or _extract_outcome_name(
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
                elif not event.neg_risk and len(event.markets) > 1:
                    # Game-level event: each sub-market (moneyline, spread, O/U,
                    # player props) becomes its own FuturesMarket row. Without this,
                    # all 40 sub-markets are flattened into outcomes of a single
                    # FuturesMarket, making player props invisible to the game-markets
                    # endpoint (which classifies by market name, not outcome name).
                    #
                    # The parent FuturesMarket (created above) serves as the group
                    # anchor. Each sub-market inherits its event_id, sport category,
                    # and group_id for linkage.
                    parent_market_id = futures_market_id

                    # Check if parent is already linked to an event
                    _parent_eid_r = await session.execute(
                        select(FuturesMarket.event_id).where(FuturesMarket.id == parent_market_id)
                    )
                    parent_event_id = _parent_eid_r.scalar_one_or_none()

                    for market in event.markets:
                        prob = market.outcome_prices[0] if market.outcome_prices else None

                        if prob is None or prob <= 0:
                            if (market.best_bid is not None and market.best_bid > 0
                                    and market.best_ask is not None and market.best_ask > 0):
                                prob = (market.best_bid + market.best_ask) / 2
                            elif market.last_trade_price is not None and market.last_trade_price > 0:
                                prob = market.last_trade_price
                            elif market.best_ask is not None and market.best_ask > 0:
                                prob = market.best_ask

                        if prob is None or prob <= 0:
                            continue

                        sub_name = market.question or event.title
                        sub_tier = compute_market_tier(sub_name, category, sport_category=llm_sport_category)

                        sub_stmt = pg_insert(FuturesMarket).values(
                            source="polymarket",
                            external_id=market.condition_id,
                            name=sub_name,
                            category="game_prop",
                            llm_sport_category=llm_sport_category,
                            llm_league=league,
                            market_tier=sub_tier,
                            mutually_exclusive=True,
                            commence_time=commence_time,
                            resolution_date=resolution_date,
                            status="open" if event.active else "resolved",
                            group_id=poly_group_id,
                            group_type="polymarket_sub_market",
                            event_id=parent_event_id,
                        ).on_conflict_do_update(
                            index_elements=["source", "external_id"],
                            set_={
                                "name": sub_name,
                                "market_tier": sub_tier,
                                "status": "open" if event.active else "resolved",
                                "event_id": parent_event_id,
                                "updated_at": func.now(),
                            },
                        ).returning(FuturesMarket.id)

                        sub_result = await session.execute(sub_stmt)
                        sub_market_id = sub_result.scalar_one()

                        # Create Over/Yes outcome
                        over_name = "Over" if "o/u" in sub_name.lower() else "Yes"
                        over_american = probability_to_american(prob) if 0 < prob < 1 else None

                        sub_has_trading = (
                            market.best_bid is not None and market.best_bid > 0
                        ) or (
                            market.last_trade_price is not None and market.last_trade_price > 0
                        )
                        sub_opening = prob if sub_has_trading else None
                        sub_opening_am = over_american if sub_has_trading else None
                        sub_opening_at = now if sub_has_trading else None

                        over_update: dict = {
                            "current_probability": prob,
                            "current_american_odds": over_american,
                            "current_yes_bid": market.best_bid,
                            "current_yes_ask": market.best_ask,
                            "rank": 1,
                            "probability_change_24h": prob - FuturesOutcome.current_probability,
                            "last_updated": func.now(),
                        }
                        if sub_has_trading:
                            over_update["opening_probability"] = func.coalesce(
                                FuturesOutcome.opening_probability, prob
                            )

                        over_stmt = pg_insert(FuturesOutcome).values(
                            market_id=sub_market_id,
                            external_id=f"{market.condition_id}_yes",
                            name=over_name,
                            current_probability=prob,
                            current_american_odds=over_american,
                            current_yes_bid=market.best_bid,
                            current_yes_ask=market.best_ask,
                            opening_probability=sub_opening,
                            opening_american_odds=sub_opening_am,
                            opening_captured_at=sub_opening_at,
                            rank=1,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_=over_update,
                        ).returning(FuturesOutcome.id)

                        over_result = await session.execute(over_stmt)
                        over_outcome_id = over_result.scalar_one()

                        snap_stmt = pg_insert(FuturesOddsSnapshot).values(
                            outcome_id=over_outcome_id,
                            bookmaker="polymarket",
                            probability=prob,
                            american_odds=over_american,
                            yes_bid=market.best_bid,
                            yes_ask=market.best_ask,
                            last_price=market.last_trade_price,
                            captured_at=now,
                        )
                        await session.execute(snap_stmt)

                        # Create Under/No outcome if available
                        if len(market.outcome_prices) > 1:
                            under_prob = market.outcome_prices[1]
                            under_name = "Under" if "o/u" in sub_name.lower() else "No"
                            under_american = probability_to_american(under_prob) if 0 < under_prob < 1 else None

                            under_update: dict = {
                                "current_probability": under_prob,
                                "current_american_odds": under_american,
                                "rank": 2,
                                "last_updated": func.now(),
                            }
                            if sub_has_trading:
                                under_update["opening_probability"] = func.coalesce(
                                    FuturesOutcome.opening_probability, under_prob
                                )

                            under_stmt = pg_insert(FuturesOutcome).values(
                                market_id=sub_market_id,
                                external_id=f"{market.condition_id}_no",
                                name=under_name,
                                current_probability=under_prob,
                                current_american_odds=under_american,
                                opening_probability=sub_opening if sub_has_trading else None,
                                opening_american_odds=under_american if sub_has_trading else None,
                                opening_captured_at=sub_opening_at,
                                rank=2,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_=under_update,
                            )
                            await session.execute(under_stmt)

                        stats["markets_processed"] += 1
                        stats["outcomes_updated"] += 2
                        stats["snapshots_created"] += 1
                        stats["sub_markets_created"] = stats.get("sub_markets_created", 0) + 1

                    # Also keep parent market outcomes (for the moneyline matching task)
                    for market in event.markets:
                        prob = market.outcome_prices[0] if market.outcome_prices else None
                        if prob is None or prob <= 0:
                            continue
                        outcome_name = market.group_item_title or _extract_outcome_name(
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
                    # Single-market event
                    for market in event.markets:
                        prob = market.outcome_prices[0] if market.outcome_prices else None

                        if prob is None or prob <= 0:
                            if (market.best_bid is not None and market.best_bid > 0
                                    and market.best_ask is not None and market.best_ask > 0):
                                prob = (market.best_bid + market.best_ask) / 2
                            elif market.last_trade_price is not None and market.last_trade_price > 0:
                                prob = market.last_trade_price
                            elif market.best_ask is not None and market.best_ask > 0:
                                prob = market.best_ask

                        if prob is None or prob <= 0:
                            continue

                        outcome_data.append({
                            "external_id": market.condition_id,
                            "name": "Yes",
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

                    # Only set opening_probability when there's real trading.
                    # A wide bid-ask spread or no bids means placeholder pricing.
                    has_real_trading = (
                        od["yes_bid"] is not None
                        and od["yes_bid"] > 0
                        and od["yes_ask"] is not None
                        and (od["yes_ask"] - od["yes_bid"]) < 0.50
                    ) or (
                        od.get("last_price") is not None and od["last_price"] > 0
                    )
                    opening_prob = prob if has_real_trading else None
                    opening_american = american if has_real_trading else None
                    opening_at = now if has_real_trading else None

                    update_set: dict = {
                        "name": od["name"],
                        "current_probability": prob,
                        "current_american_odds": american,
                        "current_yes_bid": od["yes_bid"],
                        "current_yes_ask": od["yes_ask"],
                        "rank": rank,
                        "probability_change_24h": prob - FuturesOutcome.current_probability,
                        "rank_change_24h": FuturesOutcome.rank - rank,
                        "last_updated": func.now(),
                    }
                    if has_real_trading:
                        update_set["opening_probability"] = func.coalesce(
                            FuturesOutcome.opening_probability, prob
                        )
                        update_set["opening_american_odds"] = func.coalesce(
                            FuturesOutcome.opening_american_odds, american
                        )
                        update_set["opening_captured_at"] = func.coalesce(
                            FuturesOutcome.opening_captured_at, now
                        )

                    outcome_stmt = pg_insert(FuturesOutcome).values(
                        market_id=futures_market_id,
                        external_id=od["external_id"],
                        name=od["name"],
                        current_probability=prob,
                        current_american_odds=american,
                        current_yes_bid=od["yes_bid"],
                        current_yes_ask=od["yes_ask"],
                        opening_probability=opening_prob,
                        opening_american_odds=opening_american,
                        opening_captured_at=opening_at,
                        rank=rank,
                    ).on_conflict_do_update(
                        index_elements=["market_id", "external_id"],
                        set_=update_set,
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

        # Propagate event_id from parent markets to their sub-markets.
        # The matching task links parent game markets (e.g., "Magic vs. Pistons")
        # to events, but sub-markets (player props, spreads) inherit the link
        # from their parent via group_id.
        from sqlalchemy import text as _text
        prop_result = await session.execute(_text("""
            UPDATE futures_markets sub
            SET event_id = parent.event_id
            FROM futures_markets parent
            WHERE sub.group_type = 'polymarket_sub_market'
              AND sub.event_id IS NULL
              AND sub.group_id IS NOT NULL
              AND parent.source = 'polymarket'
              AND parent.group_type = 'polymarket_event'
              AND parent.group_id = sub.group_id
              AND parent.event_id IS NOT NULL
        """))
        if prop_result.rowcount > 0:
            stats["sub_markets_linked"] = prop_result.rowcount

        await session.commit()


async def _backfill_polymarket_price_history(
    limit: int = 50,
    fidelity: int = 60,
    interval: str = "max",
):
    """
    Backfill historical price data for Polymarket outcomes.

    Fetches price history from Polymarket's CLOB API (/prices-history)
    and stores as FuturesOddsSnapshot rows. This gives us time-series data
    for Polymarket markets without needing to have been polling them.

    Args:
        limit: Max outcomes to process per run
        fidelity: Price data granularity in minutes (60 = hourly)
        interval: Time range ('1h', '6h', '1d', '1w', 'max')
    """
    import asyncio
    import json as json_module
    from sqlalchemy import select, text
    from app.models.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot

    stats = {
        "outcomes_processed": 0,
        "outcomes_skipped": 0,
        "snapshots_created": 0,
        "events_fetched": 0,
        "errors": [],
    }

    try:
        from app.services.polymarket_api import PolymarketAPIService

        async with get_task_session() as session:
            # Find Polymarket outcomes that have few or no historical snapshots.
            # We prioritize outcomes with the least snapshot coverage.
            result = await session.execute(
                text("""
                    SELECT fo.id, fo.external_id, fo.name, fm.external_id AS market_external_id,
                           COUNT(fos.id) AS snapshot_count
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fo.market_id = fm.id
                    LEFT JOIN futures_odds_snapshots fos ON fos.outcome_id = fo.id
                    WHERE fm.source = 'polymarket'
                      AND fo.current_probability IS NOT NULL
                    GROUP BY fo.id, fo.external_id, fo.name, fm.external_id
                    HAVING COUNT(fos.id) < 24
                    ORDER BY COUNT(fos.id) ASC, fo.id
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            outcomes_to_backfill = result.fetchall()

            if not outcomes_to_backfill:
                return {**stats, "status": "nothing_to_backfill"}

            # Group outcomes by their market's external_id (Polymarket event ID)
            # so we can batch-fetch events
            by_event = {}
            for row in outcomes_to_backfill:
                event_id = row.market_external_id
                if event_id not in by_event:
                    by_event[event_id] = []
                by_event[event_id].append({
                    "outcome_id": row.id,
                    "condition_id": row.external_id,
                    "name": row.name,
                })

            logger.info(
                "Polymarket price history backfill: %d outcomes across %d events",
                len(outcomes_to_backfill),
                len(by_event),
            )

            service = PolymarketAPIService()
            try:
                for event_id, outcomes in by_event.items():
                    # Fetch event from Gamma API to get clobTokenIds
                    event_data = await service.get_event_by_id(event_id)
                    if not event_data:
                        stats["errors"].append(f"event_{event_id}: fetch_failed")
                        continue
                    stats["events_fetched"] += 1

                    # Build condition_id → clob_token_id map from event's markets
                    token_map = {}
                    for market in event_data.get("markets", []):
                        cid = market.get("conditionId")
                        clob_ids_raw = market.get("clobTokenIds", "[]")
                        try:
                            if isinstance(clob_ids_raw, str):
                                clob_ids = json_module.loads(clob_ids_raw)
                            else:
                                clob_ids = clob_ids_raw
                        except (json_module.JSONDecodeError, TypeError):
                            clob_ids = []
                        if cid and clob_ids:
                            token_map[cid] = clob_ids[0]  # First token = "Yes" side

                    for outcome in outcomes:
                        token_id = token_map.get(outcome["condition_id"])
                        if not token_id:
                            stats["outcomes_skipped"] += 1
                            continue

                        # Fetch price history
                        try:
                            history = await service.get_prices_history(
                                token_id=token_id,
                                interval=interval,
                                fidelity=fidelity,
                            )
                        except Exception as e:
                            stats["errors"].append(
                                f"outcome_{outcome['outcome_id']}: history_fetch: {str(e)[:100]}"
                            )
                            continue

                        if not history:
                            stats["outcomes_skipped"] += 1
                            continue

                        # Insert historical snapshots (skip duplicates via ON CONFLICT)
                        from sqlalchemy.dialects.postgresql import insert as pg_insert

                        batch_values = []
                        for point in history:
                            ts = point.get("t")
                            price = point.get("p")
                            if ts is None or price is None:
                                continue
                            captured = datetime.fromtimestamp(ts, tz=timezone.utc)
                            batch_values.append({
                                "outcome_id": outcome["outcome_id"],
                                "bookmaker": "polymarket",
                                "probability": round(float(price), 6),
                                "last_price": round(float(price), 4),
                                "captured_at": captured,
                            })

                        if batch_values:
                            # Insert in chunks to avoid huge queries
                            for i in range(0, len(batch_values), 100):
                                chunk = batch_values[i:i + 100]
                                stmt = pg_insert(FuturesOddsSnapshot).values(chunk)
                                stmt = stmt.on_conflict_do_nothing()
                                await session.execute(stmt)
                            stats["snapshots_created"] += len(batch_values)

                        stats["outcomes_processed"] += 1

                        # Rate limit: 0.3s between price history requests
                        await asyncio.sleep(0.3)

                    # Rate limit between events
                    await asyncio.sleep(0.3)

                await session.commit()

            finally:
                await service.close()

    except Exception as e:
        logger.error("Polymarket price history backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    return stats


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
