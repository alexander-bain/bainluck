"""
Kalshi prediction market polling task.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, delete as sa_delete, select

from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


# ── Kalshi game ticker detection ─────────────────────────────────────────────

# Map Kalshi game ticker prefixes to sport labels.
# Used to detect game-level events and construct better market names.
from app.utils.sport_keys import KALSHI_TICKER_TO_DISPLAY_LABEL as _KALSHI_GAME_TICKERS  # noqa: E402


def _is_kalshi_game_ticker(event_ticker: str) -> Optional[str]:
    """
    Check if a Kalshi event ticker indicates a game-level market.

    Returns the sport label (e.g., "NBA") if it's a game ticker, or None.
    Kalshi game tickers look like "KXNBAGAME-26FEB19BOSGSW".
    """
    if not event_ticker:
        return None
    ticker_lower = event_ticker.lower()
    for prefix, sport in _KALSHI_GAME_TICKERS.items():
        if ticker_lower.startswith(prefix):
            return sport
    return None


def _build_game_market_name(
    event_title: str,
    event_ticker: str,
    market_title: Optional[str],
    yes_sub_title: Optional[str],
    no_sub_title: Optional[str],
    sport_label: str,
) -> str:
    """
    Build the best possible market name for a Kalshi game-level event.

    Kalshi game events often have generic titles like "Professional Basketball Game"
    as the series title. Team names may be in market sub-titles, individual market
    title, or the event subtitle.

    Priority:
    1. Event title if it already contains a matchup pattern (e.g., "Celtics at Warriors")
    2. Constructed from yes_sub_title/no_sub_title (e.g., "Boston Celtics at Golden State Warriors")
    3. Individual market title if different from event title
    4. Original event title (fallback)
    """
    from app.utils.prediction_market_matching import _check_game_level, _strip_category_prefix

    # Check if event title already has a usable matchup
    stripped = _strip_category_prefix(event_title)
    if _check_game_level(stripped) or _check_game_level(event_title):
        return event_title

    # Construct from sub-titles (most reliable for Kalshi game markets)
    if yes_sub_title and no_sub_title:
        return f"{yes_sub_title} at {no_sub_title}"

    # Try market title if it's different and has a matchup
    if market_title and market_title != event_title:
        mstripped = _strip_category_prefix(market_title)
        if _check_game_level(mstripped) or _check_game_level(market_title):
            return market_title

    # Fallback to original event title
    return event_title


def _parse_kalshi_ticker_name(ticker: str) -> str:
    """Extract a human-readable name from a Kalshi market ticker.

    Kalshi tickers look like 'KXCOTY-24-BELICHICK' or 'NBACHAMP-BOS'.
    We take the last segment that isn't purely numeric and title-case it.
    """
    if not ticker:
        return "Unknown"
    parts = ticker.split("-")
    # Walk backwards to find the last non-numeric segment
    for part in reversed(parts):
        if part and not part.isdigit():
            # Title-case and return (e.g. "BELICHICK" -> "Belichick")
            return part.title()
    return ticker


def _kalshi_category_to_internal(kalshi_category: Optional[str]) -> str:
    """Map Kalshi category to internal category."""
    if not kalshi_category:
        return "other"

    category_lower = kalshi_category.lower()

    # Sports categories
    if any(s in category_lower for s in ["sports", "golf", "football", "basketball", "baseball", "hockey", "soccer", "tennis"]):
        return "championship"

    # Olympics
    if "olympic" in category_lower:
        return "championship"

    # Other categories
    if "politic" in category_lower or "election" in category_lower:
        return "politics"
    if "econom" in category_lower or "fed" in category_lower or "inflation" in category_lower:
        return "economics"
    if "entertainment" in category_lower or "movie" in category_lower or "award" in category_lower:
        return "entertainment"
    if "crypto" in category_lower:
        return "crypto"
    if "tech" in category_lower:
        return "tech"
    if "weather" in category_lower or "climate" in category_lower:
        return "weather"
    if "health" in category_lower or "pandemic" in category_lower:
        return "health"
    if "legal" in category_lower or "court" in category_lower:
        return "legal"
    if "science" in category_lower or "space" in category_lower:
        return "tech"
    if "financ" in category_lower:
        return "economics"

    return "other"


def _categorize_kalshi_market(market_name: str, kalshi_category: Optional[str]) -> str:
    """
    Determine llm_sport_category for a Kalshi market using pattern matching.

    Uses the same rules engine as the admin categorization endpoint,
    plus Kalshi's own category as a fallback hint.

    Always returns a category (never None) — defaults to "other".
    """
    from app.utils.futures_categorization import categorize_by_rules, detect_league, infer_sport_from_league

    # First try pattern matching on market name (handles "Winter Olympics", "NBA MVP", etc.)
    result = categorize_by_rules(market_name)
    if result:
        return result

    # Try league detection → sport inference (e.g., "Stanley Cup" → NHL → hockey)
    league = detect_league(market_name)
    if league:
        sport = infer_sport_from_league(league)
        if sport:
            return sport

    # Fall back to Kalshi's own category as a hint
    if kalshi_category:
        cat_lower = kalshi_category.lower()
        # Map Kalshi categories directly to sport categories where unambiguous
        kalshi_to_sport = {
            "golf": "golf",
            "tennis": "tennis",
            "soccer": "soccer",
            "hockey": "hockey",
            "baseball": "baseball",
            "basketball": "basketball",
            "football": "football",
        }
        for keyword, sport in kalshi_to_sport.items():
            if keyword in cat_lower:
                return sport
        if "olympic" in cat_lower:
            return "olympics"
        if "politic" in cat_lower or "election" in cat_lower:
            return "politics"
        if "entertainment" in cat_lower:
            return "entertainment"
        if "econom" in cat_lower or "fed" in cat_lower or "inflation" in cat_lower:
            return "economics"
        if "tech" in cat_lower or "crypto" in cat_lower:
            return "tech" if "tech" in cat_lower else "crypto"
        if "weather" in cat_lower or "climate" in cat_lower:
            return "weather"
        if "health" in cat_lower:
            return "health"
        if "legal" in cat_lower or "court" in cat_lower:
            return "legal"
        if "science" in cat_lower or "space" in cat_lower:
            return "tech"
        if "financ" in cat_lower:
            return "economics"

    return "other"


async def _poll_kalshi_markets():
    """Async implementation of Kalshi polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.kalshi_api import KalshiAPIService
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import os

    # Check if Kalshi API key is configured
    if not os.getenv("KALSHI_API_KEY"):
        return {"status": "skipped", "reason": "KALSHI_API_KEY not configured"}

    service = KalshiAPIService()
    stats = {
        "events_processed": 0,
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Fetch ALL open Kalshi events (no category filter).
        # This captures sports (including Olympics subcategories like curling,
        # figure skating, etc.) + non-sports markets (politics, economics,
        # entertainment) as the site expands beyond sports.
        events = await service.get_all_events(categories=None)

        async with get_task_session() as session:
            now = datetime.now(timezone.utc)

            # One-time bulk cleanup: delete ALL orphan outcomes with NULL
            # external_id across all Kalshi markets.  These were created by
            # an older code path and can never match the upsert ON CONFLICT
            # (market_id, external_id) since NULL != NULL in SQL.
            orphan_sub = select(FuturesOutcome.id).where(
                FuturesOutcome.external_id.is_(None),
                FuturesOutcome.market_id.in_(
                    select(FuturesMarket.id).where(
                        FuturesMarket.source == "kalshi"
                    )
                ),
            )
            orphan_ids = (await session.execute(orphan_sub)).scalars().all()
            if orphan_ids:
                logger.info(
                    "Bulk cleanup: deleting %d orphan outcomes with NULL external_id",
                    len(orphan_ids),
                )
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
                logger.info("Bulk orphan cleanup complete")

            for event in events:
                try:
                    # Each Kalshi event can have multiple markets
                    # For multivariate events, we create one FuturesMarket per event
                    # with outcomes for each market within

                    if not event.markets:
                        continue

                    # Determine category and sport classification
                    category = _kalshi_category_to_internal(event.category)
                    sport_category = _categorize_kalshi_market(event.title, event.category)

                    # Skip crypto markets entirely — they consume DB space
                    # without providing value to users
                    if sport_category == "crypto" or category == "crypto":
                        continue

                    # For events with multiple markets (multivariate), create one FuturesMarket
                    # For single-market events, use the market directly
                    game_sport = _is_kalshi_game_ticker(event.event_ticker)

                    if len(event.markets) == 1:
                        market = event.markets[0]
                        commence_time = market.close_time  # When trading ends
                        expiration_time = market.expiration_time

                        # For game-level events, construct the best possible name
                        # from sub-titles (team names) since event title may be generic
                        # (e.g., "Professional Basketball Game" instead of "Celtics at Warriors")
                        if game_sport:
                            market_name = _build_game_market_name(
                                event_title=event.title,
                                event_ticker=event.event_ticker,
                                market_title=market.title,
                                yes_sub_title=market.yes_sub_title,
                                no_sub_title=market.no_sub_title,
                                sport_label=game_sport,
                            )
                        else:
                            market_name = event.title
                    else:
                        market_name = event.title
                        # Use earliest close time from all markets
                        close_times = [m.close_time for m in event.markets if m.close_time]
                        commence_time = min(close_times) if close_times else None
                        expiration_times = [m.expiration_time for m in event.markets if m.expiration_time]
                        expiration_time = max(expiration_times) if expiration_times else None

                    # Compute market tier for relevance ranking
                    from app.utils.team_linking import compute_market_tier
                    from app.utils.futures_categorization import (
                        detect_league, detect_season,
                        compute_canonical_market_key,
                        detect_market_type,
                        extract_olympic_discipline,
                        generate_category_tags,
                        is_game_prop,
                    )
                    market_tier = compute_market_tier(
                        market_name, category,
                        sport_category=sport_category,
                    )

                    # Detect league and season for cross-source matching
                    league = detect_league(market_name)
                    season = detect_season(
                        market_name, league, expiration_time,
                    )
                    # For Olympics, use specific discipline as category
                    # so curling matches curling, not all Olympics events.
                    # For sports markets, use detect_market_type for specificity
                    # (e.g., "al_cy_young" instead of generic "championship")
                    canon_category = detect_market_type(market_name)
                    if sport_category == "olympics":
                        discipline = extract_olympic_discipline(market_name)
                        if discipline:
                            canon_category = discipline
                    canonical_key = compute_canonical_market_key(
                        sport_category, league, canon_category, season,
                    )

                    # Generate category tags
                    tags = generate_category_tags(
                        market_name, sport_category, league, category,
                    )

                    # For game props, set category to "game_prop"
                    if is_game_prop(market_name):
                        category = "game_prop"

                    # Determine group hierarchy from Kalshi event structure
                    has_multiple_markets = len(event.markets) > 1
                    if has_multiple_markets or event.mutually_exclusive:
                        kalshi_group_id = f"kalshi:{event.event_ticker}"
                        kalshi_group_type = "kalshi_event"
                    else:
                        kalshi_group_id = None
                        kalshi_group_type = None

                    # Build market_metadata with event-level context
                    kalshi_metadata: dict = {}
                    if event.event_ticker:
                        kalshi_metadata["kalshi_event_ticker"] = event.event_ticker
                    if event.title:
                        kalshi_metadata["event_title"] = event.title
                    if has_multiple_markets:
                        kalshi_metadata["market_count"] = len(event.markets)

                    # Upsert the FuturesMarket
                    upsert_values = {
                        "source": "kalshi",
                        "external_id": event.event_ticker,
                        "name": market_name,
                        "category": category,
                        "llm_sport_category": sport_category,
                        "market_tier": market_tier,
                        "mutually_exclusive": event.mutually_exclusive,
                        "commence_time": commence_time,
                        "resolution_date": expiration_time,
                        "status": "open",
                        "category_tags": tags,
                        "group_id": kalshi_group_id,
                        "group_type": kalshi_group_type,
                        "group_position": 0,
                        "market_metadata": kalshi_metadata if kalshi_metadata else None,
                    }
                    update_set = {
                        "name": market_name,
                        "category": category,
                        "market_tier": market_tier,
                        "commence_time": commence_time,
                        "resolution_date": expiration_time,
                        "category_tags": tags,
                        "group_id": kalshi_group_id,
                        "group_type": kalshi_group_type,
                        "group_position": 0,
                        "market_metadata": kalshi_metadata if kalshi_metadata else None,
                        "updated_at": func.now(),
                    }
                    # Always update llm_sport_category unless new value is "other"
                    # and existing might be better (from LLM or previous categorization)
                    if sport_category and sport_category != "other":
                        update_set["llm_sport_category"] = sport_category
                    # Set league and canonical key
                    if league:
                        upsert_values["llm_league"] = league
                        update_set["llm_league"] = league
                    if canonical_key:
                        upsert_values["canonical_market_key"] = canonical_key
                        update_set["canonical_market_key"] = canonical_key

                    market_stmt = pg_insert(FuturesMarket).values(
                        **upsert_values
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_=update_set,
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    futures_market_id = result.scalar_one()
                    stats["events_processed"] += 1

                    # First pass: compute probabilities and names for all outcomes
                    outcome_data = []
                    for market in event.markets:
                        # Calculate probability from bid/ask midpoint or last price.
                        # When yes_bid is 0 (no one bidding), prefer last_price
                        # over the midpoint — last_price better reflects actual
                        # market consensus for illiquid outcomes.
                        if (market.yes_bid is not None and market.yes_bid > 0
                                and market.yes_ask is not None and market.yes_ask > 0):
                            prob = (market.yes_bid + market.yes_ask) / 2
                        elif market.last_price is not None and market.last_price > 0:
                            prob = market.last_price
                        elif (market.yes_bid is not None and market.yes_ask is not None
                              and market.yes_ask > 0):
                            # Bid is 0 but ask exists — use ask as upper bound
                            prob = market.yes_ask
                        else:
                            continue  # Skip markets without any pricing

                        american = probability_to_american(prob) if prob and prob > 0 else None

                        # For single-market events, use "Yes" as outcome name
                        # For multi-market events, prefer yes_sub_title (player/team name),
                        # then subtitle, then title if it differs from event title,
                        # then parsed ticker as last resort
                        if len(event.markets) == 1:
                            outcome_name = "Yes"
                        else:
                            if market.yes_sub_title:
                                outcome_name = market.yes_sub_title
                            elif market.subtitle:
                                outcome_name = market.subtitle
                            elif market.title and market.title != event.title:
                                outcome_name = market.title
                            else:
                                # Extract name from ticker (e.g. "COTY-24-BELICHICK" -> "Belichick")
                                outcome_name = _parse_kalshi_ticker_name(market.ticker)

                        outcome_data.append({
                            "market": market,
                            "prob": prob,
                            "american": american,
                            "outcome_name": outcome_name,
                        })

                    # Sort by probability descending to compute ranks (1 = highest)
                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Second pass: upsert outcomes with correct probability-based ranks
                    for rank, od in enumerate(outcome_data, 1):
                        market = od["market"]
                        prob = od["prob"]
                        american = od["american"]
                        outcome_name = od["outcome_name"]
                        stats["markets_processed"] += 1

                        # Upsert outcome
                        outcome_stmt = pg_insert(FuturesOutcome).values(
                            market_id=futures_market_id,
                            external_id=market.ticker,
                            name=outcome_name,
                            current_probability=prob,
                            current_american_odds=american,
                            current_yes_bid=market.yes_bid,
                            current_yes_ask=market.yes_ask,
                            opening_probability=prob,
                            opening_american_odds=american,
                            opening_captured_at=now,
                            rank=rank,
                        ).on_conflict_do_update(
                            index_elements=["market_id", "external_id"],
                            set_={
                                "name": outcome_name,
                                "current_probability": prob,
                                "current_american_odds": american,
                                "current_yes_bid": market.yes_bid,
                                "current_yes_ask": market.yes_ask,
                                "rank": rank,
                                "last_updated": func.now(),
                            }
                        ).returning(FuturesOutcome.id)

                        result = await session.execute(outcome_stmt)
                        outcome_id = result.scalar_one()
                        stats["outcomes_updated"] += 1

                        # Create snapshot with Kalshi-specific data
                        snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                            outcome_id=outcome_id,
                            bookmaker="kalshi",
                            probability=prob,
                            american_odds=american,
                            yes_bid=market.yes_bid,
                            yes_ask=market.yes_ask,
                            last_price=market.last_price,
                            captured_at=now,
                        )
                        await session.execute(snapshot_stmt)
                        stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{event.event_ticker}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    return stats
