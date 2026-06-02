"""
Kalshi prediction market polling task.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
import sentry_sdk
from sqlalchemy import func, delete as sa_delete, select, text, update as sa_update
from sqlalchemy.exc import SQLAlchemyError

from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


# ── Kalshi game ticker detection ─────────────────────────────────────────────

# Map Kalshi game ticker prefixes to sport labels.
# Used to detect game-level events and construct better market names.
from app.utils.sport_keys import KALSHI_TICKER_TO_DISPLAY_LABEL as _KALSHI_GAME_TICKERS  # noqa: E402
from app.utils.editorial_patterns import matches_editorial_recall as _matches_editorial_recall  # noqa: E402


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


import re as _re

_GENERIC_OUTCOME_PATTERNS = _re.compile(
    r"^(?:"
    r"Ticker [A-Z]"           # "Ticker D", "Ticker H"
    r"|Option [A-Z0-9]+"      # "Option 1", "Option A"
    r"|Choice [A-Z0-9]+"      # "Choice 1"
    r"|Person [A-Z0-9]+"       # "Person B", "Person G"
    r"|Team [A-Z0-9]+"         # "Team 1", "Team A"
    r"|Player [A-Z0-9]+"       # "Player 1"
    r"|Candidate [A-Z0-9]+"   # "Candidate 1"
    r"|[A-Z]$"                # Single letters only (not "Yes"/"No")
    r"|[0-9]+$"               # Pure numbers
    r")$",
    _re.IGNORECASE,
)


def _is_generic_outcome_name(name: str) -> bool:
    """Check if an outcome name is generic/obfuscated and should be skipped.

    Returns True for names like "Ticker D", "Option 1", single letters, etc.
    These indicate Kalshi hasn't provided a real outcome label.
    """
    if not name:
        return True
    return bool(_GENERIC_OUTCOME_PATTERNS.match(name.strip()))


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


def _categorize_kalshi_market(market_name: str, kalshi_category: Optional[str], event_ticker: Optional[str] = None) -> str:
    """
    Determine llm_sport_category for a Kalshi market using pattern matching.

    Classification cascade (first match wins):
    1. Ticker prefix → sport key (authoritative — KXNHL is always hockey)
    2. Rules engine on market name
    3. League detection → sport inference
    4. Kalshi's own category as fallback

    Always returns a category (never None) — defaults to "other".
    """
    from app.utils.futures_categorization import categorize_by_rules, detect_league, infer_sport_from_league

    # 1. Ticker prefix → sport category (AUTHORITATIVE — ticker never lies.
    # Must come first because ambiguous names like "Eastern Conference" match
    # multiple sports but the ticker disambiguates: KXNHLEAST = hockey)
    if event_ticker:
        from app.utils.sport_keys import get_sport_key_from_ticker, SPORT_PREFIX_TO_LLM_CATEGORY
        sport_key = get_sport_key_from_ticker(event_ticker)
        if sport_key:
            prefix = sport_key.split("_")[0] if sport_key else None
            if prefix and prefix in SPORT_PREFIX_TO_LLM_CATEGORY:
                return SPORT_PREFIX_TO_LLM_CATEGORY[prefix]

    # 2. Pattern matching on market name
    result = categorize_by_rules(market_name)
    if result:
        return result

    # 3. League detection → sport inference
    league = detect_league(market_name)
    if league:
        sport = infer_sport_from_league(league)
        if sport:
            return sport

    # 4. Fall back to Kalshi's own category as a hint
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
        "by_category": {},
        "crypto_skipped": 0,
        "total_api_events": 0,
    }

    try:
        # Fetch ALL open Kalshi events (no category filter).
        # This captures sports (including Olympics subcategories like curling,
        # figure skating, etc.) + non-sports markets (politics, economics,
        # entertainment) as the site expands beyond sports.
        events = await service.get_all_events(categories=None)
        stats["total_api_events"] = len(events)

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
                    sport_category = _categorize_kalshi_market(event.title, event.category, event.event_ticker)

                    # Skip crypto markets entirely — they consume DB space
                    # without providing value to users
                    if sport_category == "crypto" or category == "crypto":
                        stats["crypto_skipped"] += 1
                        continue
                    stats["by_category"][sport_category] = stats["by_category"].get(sport_category, 0) + 1

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
                    from app.utils.market_label_normalization import compute_market_tier
                    from app.utils.futures_categorization import (
                        detect_league, detect_season,
                        compute_canonical_market_key,
                        detect_market_type,
                        extract_olympic_discipline,
                        generate_category_tags,
                        is_game_prop,
                    )
                    # Check for game props BEFORE computing tier —
                    # game props must be tier 5, not inherit from category
                    if is_game_prop(market_name):
                        category = "game_prop"

                    market_tier = compute_market_tier(
                        market_name, category,
                        sport_category=sport_category,
                    )
                    # Force tier 5 for game props regardless of name patterns
                    if category == "game_prop":
                        market_tier = 5

                    # Detect league and season for cross-source matching
                    league = detect_league(market_name, sport_category=sport_category)
                    season = detect_season(
                        market_name, league, expiration_time,
                    )
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

                    # Always assign group_id for calibration, feed dedup, and
                    # category page grouping.
                    kalshi_group_id = f"kalshi:{event.event_ticker}"
                    if len(event.markets) > 1 or event.mutually_exclusive:
                        kalshi_group_type = "kalshi_event"
                    else:
                        kalshi_group_type = "kalshi_single"

                    # Build market_metadata with event-level context
                    kalshi_metadata: dict = {}
                    if event.event_ticker:
                        kalshi_metadata["kalshi_event_ticker"] = event.event_ticker
                    if event.title:
                        kalshi_metadata["event_title"] = event.title
                    if len(event.markets) > 1:
                        kalshi_metadata["market_count"] = len(event.markets)

                    # Aggregate volume across all markets in this event
                    total_volume = sum(m.volume or 0 for m in event.markets) or None
                    total_volume_24h = sum(m.volume_24h or 0 for m in event.markets) or None
                    total_open_interest = sum(m.open_interest or 0 for m in event.markets) or None

                    # Derive market status from Kalshi API data.
                    # A market is "resolved" only when ALL sub-markets in the
                    # event are closed or settled. This unblocks backfill_winners
                    # which only processes status='resolved' rows.
                    all_settled = all(
                        m.status in ("closed", "settled")
                        for m in event.markets
                    )
                    market_status = "resolved" if all_settled else "open"

                    # Upsert the FuturesMarket
                    _editorial = _matches_editorial_recall(market_name)
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
                        "status": market_status,
                        "category_tags": tags,
                        "group_id": kalshi_group_id,
                        "group_type": kalshi_group_type,
                        "group_position": 0,
                        "market_metadata": kalshi_metadata if kalshi_metadata else None,
                        "volume": total_volume,
                        "volume_24h": total_volume_24h,
                        "open_interest": total_open_interest,
                        "volume_updated_at": func.now(),
                        "is_editorial_recall": _editorial,
                    }
                    update_set = {
                        "name": market_name,
                        "category": category,
                        "market_tier": market_tier,
                        "status": market_status,
                        "commence_time": commence_time,
                        "resolution_date": expiration_time,
                        "category_tags": tags,
                        "group_id": kalshi_group_id,
                        "group_type": kalshi_group_type,
                        "group_position": 0,
                        "market_metadata": kalshi_metadata if kalshi_metadata else None,
                        "updated_at": func.now(),
                        "volume": total_volume,
                        "volume_24h": total_volume_24h,
                        "open_interest": total_open_interest,
                        "volume_updated_at": func.now(),
                        "is_editorial_recall": _editorial,
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
                              and market.yes_ask > 0 and market.yes_ask <= 0.50):
                            prob = market.yes_ask
                        else:
                            continue  # Skip markets without any pricing

                        american = probability_to_american(prob) if prob and prob > 0 else None

                        # For single-market events, use "Yes" as outcome name
                        # For multi-market events, prefer yes_sub_title (player/team name),
                        # then subtitle, then title if it differs from event title,
                        # then parsed ticker as last resort.
                        # Skip yes_sub_title if it looks generic/obfuscated.
                        if len(event.markets) == 1:
                            outcome_name = "Yes"
                        else:
                            sub = market.yes_sub_title
                            if sub and not _is_generic_outcome_name(sub):
                                outcome_name = sub
                            elif market.subtitle and not _is_generic_outcome_name(market.subtitle):
                                outcome_name = market.subtitle
                            elif market.title and market.title != event.title:
                                outcome_name = market.title
                            else:
                                outcome_name = _parse_kalshi_ticker_name(market.ticker)

                        outcome_data.append({
                            "market": market,
                            "prob": prob,
                            "american": american,
                            "outcome_name": outcome_name,
                        })

                    # Null out stale outcomes: if an outcome exists in the DB but
                    # Kalshi returns no pricing (bid/ask/last all NULL), its probability
                    # is stale from a previous poll. Clear it to prevent phantom data
                    # (e.g., Game 2's 1H total pricing showing on Game 3's page).
                    priced_tickers = {od["market"].ticker for od in outcome_data}
                    all_tickers = {m.ticker for m in event.markets}
                    unpriced_tickers = all_tickers - priced_tickers
                    if unpriced_tickers:
                        await session.execute(
                            sa_update(FuturesOutcome)
                            .where(
                                FuturesOutcome.market_id == futures_market_id,
                                FuturesOutcome.external_id.in_(list(unpriced_tickers)),
                            )
                            .values(
                                current_probability=None,
                                current_american_odds=None,
                                current_yes_bid=None,
                                current_yes_ask=None,
                                last_updated=func.now(),
                            )
                        )

                    # Sort by probability descending to compute ranks (1 = highest)
                    outcome_data.sort(key=lambda x: x["prob"], reverse=True)

                    # Second pass: upsert outcomes with correct probability-based ranks
                    for rank, od in enumerate(outcome_data, 1):
                        market = od["market"]
                        prob = od["prob"]
                        american = od["american"]
                        outcome_name = od["outcome_name"]
                        stats["markets_processed"] += 1

                        # Only set opening_probability when there's real trading
                        # activity. A wide bid-ask spread or zero volume means the
                        # price is a placeholder, not a real market signal.
                        has_real_trading = (
                            market.yes_bid is not None
                            and market.yes_bid > 0
                            and market.yes_ask is not None
                            and (market.yes_ask - market.yes_bid) < 0.50
                        )
                        opening_prob = prob if has_real_trading else None
                        opening_american = american if has_real_trading else None
                        opening_at = now if has_real_trading else None

                        # Forward capture: set is_winner when Kalshi has
                        # settlement data, so we don't rely on backfill
                        is_winner_value = None
                        if market.result is not None:
                            is_winner_value = market.result == "yes"

                        # Upsert outcome
                        update_set: dict = {
                            "name": outcome_name,
                            "current_probability": prob,
                            "current_american_odds": american,
                            "current_yes_bid": market.yes_bid,
                            "current_yes_ask": market.yes_ask,
                            "rank": rank,
                            "probability_change_24h": prob - FuturesOutcome.current_probability,
                            "rank_change_24h": FuturesOutcome.rank - rank,
                            "last_updated": func.now(),
                        }
                        if is_winner_value is not None:
                            update_set["is_winner"] = is_winner_value
                            update_set["resolution_source"] = "api_settlement"
                        # Backfill opening_probability if it was NULL (market had
                        # no trading on first capture) and now has real trading
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
                            update_set["opening_source"] = func.coalesce(
                                FuturesOutcome.opening_source, "bid_ask_midpoint"
                            )

                        outcome_stmt = pg_insert(FuturesOutcome).values(
                            market_id=futures_market_id,
                            external_id=market.ticker,
                            name=outcome_name,
                            current_probability=prob,
                            current_american_odds=american,
                            current_yes_bid=market.yes_bid,
                            current_yes_ask=market.yes_ask,
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

                except (httpx.HTTPError, ValueError, KeyError, SQLAlchemyError) as e:
                    stats["errors"].append(f"{event.event_ticker}: {str(e)}")
                    continue

            await session.commit()

        # Post-commit: fix commence_time for golf and hockey markets.
        # Kalshi sets commence_time = market close_time (resolution date), but
        # calibration and feed need the actual event start date.
        try:
            golf_fixed = await _fix_golf_commence_times()
            stats["golf_commence_fixed"] = golf_fixed
        except Exception as e:
            logger.warning("Golf commence_time fix failed: %s", e)
            stats["golf_commence_fixed"] = 0

        try:
            hockey_fixed = await _fix_hockey_commence_times()
            stats["hockey_commence_fixed"] = hockey_fixed
        except Exception as e:
            logger.warning("Hockey commence_time fix failed: %s", e)
            stats["hockey_commence_fixed"] = 0

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    # Zero-events heartbeat: alert if we fetched events but processed none
    if stats.get("events_processed", 0) == 0 and stats.get("total_api_events", 0) > 0:
        logger.critical(
            "Kalshi poll processed 0/%d events — ingestion may be broken",
            stats["total_api_events"],
        )
        sentry_sdk.capture_message(
            f"Kalshi ingestion failure: 0/{stats['total_api_events']} events processed",
            level="error",
        )

    logger.info(
        "Kalshi poll: %d API events → %d processed, %d markets, %d outcomes, %d snapshots, %d crypto skipped, %d errors | by_category: %s",
        stats["total_api_events"], stats["events_processed"], stats["markets_processed"],
        stats["outcomes_updated"], stats["snapshots_created"], stats["crypto_skipped"],
        len(stats["errors"]), stats["by_category"],
    )
    return stats


async def _fix_golf_commence_times() -> int:
    """Fix commence_time on Kalshi golf markets — DB-only, no API calls.

    Kalshi sets commence_time = market close_time (= resolution date, typically
    Sunday evening). For calibration, we need commence_time to be the eve of
    Round 1 so the closing line captures pre-tournament prices.

    Heuristic: set commence_time = close_time - 4.5 days (tournaments are 4 days,
    minus 12h to land on the eve of Round 1). This is approximate but far better
    than using the resolution date, which captures in-play prices.

    Falls back to DataGolf schedule when available (more precise).
    """
    from datetime import timedelta

    # Try DataGolf schedule first (precise but requires API)
    try:
        from app.routes.golf import _get_golf_schedule, _normalize_tournament
        schedule = await _get_golf_schedule()
    except Exception:
        schedule = None

    schedule_by_key: dict[str, str] = {}
    if schedule:
        for s in schedule:
            if s.get("key") and s.get("start_date"):
                schedule_by_key[s["key"]] = s["start_date"]

    async with get_task_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, commence_time
                FROM futures_markets
                WHERE source = 'kalshi'
                  AND llm_sport_category = 'golf'
                  AND commence_time IS NOT NULL
                  AND status = 'resolved'
            """)
        )
        markets = result.fetchall()
        logger.info("Golf commence_time fix: %d resolved golf markets found, schedule=%s",
                     len(markets), "available" if schedule else "UNAVAILABLE")

        fixed = 0
        fixed_ids = []
        for m in markets:
            target_dt = None

            # Try DataGolf schedule (precise)
            if schedule:
                from app.routes.golf import _normalize_tournament
                tourn_key = _normalize_tournament(m.name, schedule)
                if tourn_key != "other" and tourn_key in schedule_by_key:
                    try:
                        target_dt = datetime.fromisoformat(
                            schedule_by_key[tourn_key]
                        ) - timedelta(hours=18)
                    except (ValueError, TypeError):
                        pass

            # Fallback: close_time - 4.5 days
            if target_dt is None and m.commence_time:
                target_dt = m.commence_time - timedelta(days=4, hours=12)

            if target_dt and m.commence_time and abs(
                (m.commence_time - target_dt).total_seconds()
            ) > 3600:
                await session.execute(
                    text("UPDATE futures_markets SET commence_time = :start WHERE id = :id"),
                    {"start": target_dt, "id": m.id},
                )
                fixed += 1
                fixed_ids.append(m.id)

        if fixed_ids:
            await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    WHERE fo.market_id = ANY(:ids)
                      AND fo.calibration_probability IS NOT NULL
                """),
                {"ids": fixed_ids},
            )
            await session.commit()
            logger.info("Fixed commence_time for %d Kalshi golf markets (reset %d market cal_probs)", fixed, len(fixed_ids))

        return fixed


async def _fix_hockey_commence_times() -> int:
    """Fix commence_time on Kalshi hockey markets using linked Event data.

    For hockey game markets WITH event_id: copy commence_time from the Event.
    For markets WITHOUT event_id: derive game date from ticker via
    extract_game_date_from_ticker(). Resets calibration_probability on
    affected outcomes so the backfill recomputes with correct closing lines.
    """
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    async with get_task_session() as session:
        # Pass 1: Markets linked to an Event — copy Event.commence_time
        result1 = await session.execute(
            text("""
                UPDATE futures_markets fm
                SET commence_time = e.commence_time
                FROM events e
                WHERE fm.event_id = e.id
                  AND fm.source = 'kalshi'
                  AND fm.llm_sport_category = 'hockey'
                  AND e.commence_time IS NOT NULL
                  AND (fm.commence_time IS NULL
                       OR ABS(EXTRACT(EPOCH FROM fm.commence_time - e.commence_time)) > 86400)
                RETURNING fm.id
            """)
        )
        linked_ids = [r[0] for r in result1.fetchall()]
        linked_fixed = len(linked_ids)

        # Pass 2: Unlinked markets — derive from ticker
        result2 = await session.execute(
            text("""
                SELECT id, name, commence_time,
                       market_metadata->>'ticker' AS ticker,
                       external_id
                FROM futures_markets
                WHERE source = 'kalshi'
                  AND llm_sport_category = 'hockey'
                  AND event_id IS NULL
                  AND commence_time IS NOT NULL
            """)
        )
        unlinked = result2.fetchall()
        ticker_fixed = 0
        ticker_ids = []
        for m in unlinked:
            ticker = m.ticker or m.external_id or ""
            game_date = extract_game_date_from_ticker(ticker)
            if game_date and m.commence_time:
                if abs((m.commence_time - game_date).total_seconds()) > 86400:
                    await session.execute(
                        text("UPDATE futures_markets SET commence_time = :dt WHERE id = :id"),
                        {"dt": game_date, "id": m.id},
                    )
                    ticker_fixed += 1
                    ticker_ids.append(m.id)

        fixed_ids = linked_ids + ticker_ids
        if fixed_ids:
            await session.execute(
                text("""
                    UPDATE futures_outcomes fo
                    SET calibration_probability = NULL
                    WHERE fo.market_id = ANY(:ids)
                      AND fo.calibration_probability IS NOT NULL
                """),
                {"ids": fixed_ids},
            )
            await session.commit()
            logger.info(
                "Fixed commence_time for %d Kalshi hockey markets "
                "(linked=%d, ticker=%d, reset %d market cal_probs)",
                len(fixed_ids), linked_fixed, ticker_fixed, len(fixed_ids),
            )

        return linked_fixed + ticker_fixed


async def _backfill_from_settled_events(limit: int = 5000):
    """Recover historical prices and fix market status from Kalshi settled events.

    Two-phase approach:
    Phase 1 (status resolution): Scan ALL series and update market status
      to 'resolved' for any Kalshi market appearing in the settled events API.
      This runs unconditionally — no limit, no early exit. Ensures the
      calibration pipeline, is_winner backfill, and candlestick backfill
      can process these markets.
    Phase 2 (snapshot backfill): Create closing-price snapshots for outcomes
      that have no snapshots at all. Respects the limit parameter.
    """
    import asyncio
    from app.models.models import FuturesOddsSnapshot, FuturesOutcome

    stats = {
        "events_scanned": 0, "markets_matched": 0,
        "snapshots_created": 0, "opening_set": 0,
        "markets_resolved": 0,
        "api_pages": 0, "api_empty": 0, "errors": [],
    }

    # Dynamically discover all Kalshi series with unresolved markets
    # instead of a hardcoded list that misses esports, baseball HR, soccer BTTS, etc.
    async with get_task_session() as session:
        series_result = await session.execute(
            text("""
                SELECT DISTINCT regexp_replace(external_id, '-.*', '') AS series_prefix
                FROM futures_markets
                WHERE source = 'kalshi'
                  AND status IN ('open', 'resolved')
                  AND external_id ~ '^KX'
                ORDER BY 1
            """)
        )
        SERIES_PREFIXES = [r[0] for r in series_result.all()]
    logger.info("Settled events: discovered %d series prefixes", len(SERIES_PREFIXES))

    try:
        from app.services.kalshi_api import KalshiAPIService
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        service = KalshiAPIService()
        try:
            async with get_task_session() as session:
                total_snapshots = 0

                # Process series that need work, with a time budget.
                # Check all series (fast EXISTS query), then process
                # each one until we've used ~10 min of the 15-min limit.
                import time as _time
                _start_time = _time.monotonic()
                _MAX_SECONDS = 600  # 10 min budget, leaving 5 min headroom

                series_needing_work = []
                for candidate in SERIES_PREFIXES:
                    needs_work = await session.execute(
                        text("""
                            SELECT EXISTS (
                                SELECT 1 FROM futures_markets fm
                                WHERE fm.source = 'kalshi'
                                  AND fm.external_id LIKE :prefix || '%'
                                  AND (
                                      fm.status != 'resolved'
                                      OR EXISTS (
                                          SELECT 1 FROM futures_outcomes fo
                                          WHERE fo.market_id = fm.id
                                            AND COALESCE(fo.resolution_source, '') != 'api_settlement'
                                      )
                                  )
                                LIMIT 1
                            )
                        """),
                        {"prefix": candidate},
                    )
                    if needs_work.scalar():
                        series_needing_work.append(candidate)

                # Sort: Tier 1 game series first (most guesses to fix)
                _PRIORITY = [
                    "KXNBAGAME", "KXNBASPREAD", "KXNBATEAMTOTAL", "KXNBAPTS",
                    "KXNBAREB", "KXNBAAST", "KXNBA3PT", "KXNBA2HWINNER",
                    "KXMLBSTGAME", "KXMLBSTSPREAD", "KXMLBSTTOTAL",
                    "KXNHLGAME", "KXNHLGOAL", "KXNHLPTS", "KXNHLFIRSTGOAL",
                    "KXNCAAMBGAME", "KXNCAAMBSPREAD",
                ]
                def _sort_key(s):
                    try:
                        return _PRIORITY.index(s)
                    except ValueError:
                        return len(_PRIORITY)

                series_needing_work.sort(key=_sort_key)

                logger.info(
                    "Settled events: %d/%d series need work: %s",
                    len(series_needing_work), len(SERIES_PREFIXES),
                    series_needing_work[:5],
                )

                if not series_needing_work:
                    return stats

                for series in series_needing_work:
                    if (_time.monotonic() - _start_time) > _MAX_SECONDS:
                        logger.info("Settled events: time budget exhausted after %d series",
                                    series_needing_work.index(series))
                        break
                    cursor = None
                    series_resolved = 0
                    series_snapshots = 0

                    for page_num in range(50):
                        for _retry in range(3):
                            try:
                                events, cursor = await service.get_events(
                                    status="settled",
                                    series_ticker=series,
                                    with_nested_markets=True,
                                    limit=200,
                                    cursor=cursor,
                                )
                                break
                            except Exception as api_err:
                                if "429" in str(api_err):
                                    await asyncio.sleep(5 * (_retry + 1))
                                    continue
                                raise
                        stats["api_pages"] += 1

                        if not events:
                            break

                        page_tickers = []
                        for event_data in events:
                            stats["events_scanned"] += 1
                            for mkt in (event_data.get("markets") or []):
                                ticker = mkt.get("ticker", "")
                                if ticker:
                                    page_tickers.append(ticker)

                        if not page_tickers:
                            if not cursor:
                                break
                            continue

                        # --- Phase 1: Always resolve market status ---
                        resolve_result = await session.execute(
                            text("""
                                UPDATE futures_markets
                                SET status = 'resolved'
                                WHERE source = 'kalshi'
                                  AND status != 'resolved'
                                  AND id IN (
                                      SELECT fo.market_id
                                      FROM futures_outcomes fo
                                      WHERE fo.external_id = ANY(:tickers)
                                  )
                            """),
                            {"tickers": page_tickers},
                        )
                        if resolve_result.rowcount > 0:
                            series_resolved += resolve_result.rowcount
                            stats["markets_resolved"] += resolve_result.rowcount

                        # --- Phase 2: Snapshot backfill (respects limit) ---
                        if total_snapshots < limit:
                            matched = await session.execute(
                                text("""
                                    SELECT fo.id, fo.external_id,
                                           fo.opening_probability
                                    FROM futures_outcomes fo
                                    JOIN futures_markets fm ON fo.market_id = fm.id
                                    WHERE fo.external_id = ANY(:tickers)
                                      AND fm.source = 'kalshi'
                                      AND fo.calibration_probability IS NULL
                                      AND NOT EXISTS (
                                          SELECT 1 FROM futures_odds_snapshots fos
                                          WHERE fos.outcome_id = fo.id
                                      )
                                """),
                                {"tickers": page_tickers},
                            )
                            needs_snap = {r.external_id: r for r in matched.fetchall()}

                            for event_data in events:
                                for mkt in (event_data.get("markets") or []):
                                    ticker = mkt.get("ticker", "")
                                    if ticker not in needs_snap:
                                        continue

                                    row = needs_snap[ticker]
                                    last_price_str = mkt.get("last_price_dollars")
                                    close_time_str = (
                                        mkt.get("close_time")
                                        or mkt.get("expiration_time")
                                    )

                                    if not last_price_str:
                                        stats["api_empty"] += 1
                                        continue

                                    try:
                                        price = float(last_price_str)
                                    except (ValueError, TypeError):
                                        continue

                                    if price <= 0 or price >= 1:
                                        continue

                                    try:
                                        from dateutil.parser import parse as dt_parse
                                        captured = (
                                            dt_parse(close_time_str)
                                            if close_time_str
                                            else datetime.now(timezone.utc)
                                        )
                                    except Exception:
                                        captured = datetime.now(timezone.utc)

                                    stmt = pg_insert(FuturesOddsSnapshot).values(
                                        outcome_id=row.id,
                                        bookmaker="kalshi",
                                        probability=round(price, 6),
                                        last_price=round(price, 4),
                                        captured_at=captured,
                                    ).on_conflict_do_nothing()
                                    await session.execute(stmt)
                                    stats["snapshots_created"] += 1
                                    series_snapshots += 1
                                    total_snapshots += 1

                                    if row.opening_probability is None:
                                        await session.execute(
                                            text("""
                                                UPDATE futures_outcomes
                                                SET opening_probability = :price,
                                                    opening_captured_at = :ts
                                                WHERE id = :id
                                                  AND opening_probability IS NULL
                                            """),
                                            {"price": price, "ts": captured, "id": row.id},
                                        )
                                        stats["opening_set"] += 1

                        # --- Phase 3: Winner resolution from API result field ---
                        # Bulk UPDATE: collect all ticker→result pairs from the page,
                        # then resolve winners and losers in two batch UPDATEs.
                        winners_set = 0
                        yes_tickers = []
                        no_tickers = []
                        for event_data in events:
                            for mkt in (event_data.get("markets") or []):
                                ticker = mkt.get("ticker", "")
                                result = mkt.get("result")
                                if not ticker or result is None:
                                    continue
                                if result == "yes":
                                    yes_tickers.append(ticker)
                                else:
                                    no_tickers.append(ticker)

                        if yes_tickers:
                            r_yes = await session.execute(
                                text("""
                                    UPDATE futures_outcomes
                                    SET is_winner = true,
                                        resolution_source = 'api_settlement'
                                    WHERE external_id = ANY(:tickers)
                                      AND COALESCE(resolution_source, '') != 'api_settlement'
                                      AND market_id IN (
                                          SELECT id FROM futures_markets
                                          WHERE source = 'kalshi'
                                      )
                                """),
                                {"tickers": yes_tickers},
                            )
                            winners_set += r_yes.rowcount

                        if no_tickers:
                            r_no = await session.execute(
                                text("""
                                    UPDATE futures_outcomes
                                    SET is_winner = false,
                                        resolution_source = 'api_settlement'
                                    WHERE external_id = ANY(:tickers)
                                      AND COALESCE(resolution_source, '') != 'api_settlement'
                                      AND market_id IN (
                                          SELECT id FROM futures_markets
                                          WHERE source = 'kalshi'
                                      )
                                """),
                                {"tickers": no_tickers},
                            )
                            winners_set += r_no.rowcount

                        stats.setdefault("winners_resolved", 0)
                        stats["winners_resolved"] += winners_set
                        if yes_tickers or no_tickers:
                            logger.info(
                                "Phase 3: series=%s page=%d yes=%d no=%d updated=%d",
                                series, page_num, len(yes_tickers),
                                len(no_tickers), winners_set,
                            )

                        await session.commit()

                        if not cursor:
                            break
                        await asyncio.sleep(1.0)

                    if series_resolved > 0 or series_snapshots > 0 or stats.get("winners_resolved", 0) > 0:
                        logger.info(
                            "Settled events: series=%s resolved=%d snapshots=%d winners=%d",
                            series, series_resolved, series_snapshots,
                            stats.get("winners_resolved", 0),
                        )

        finally:
            await service.close()

    except Exception as e:
        logger.error("Settled events backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    return stats


async def _backfill_kalshi_price_history(
    limit: int = 500,
    mode: str = "resolved_zero",
):
    """Backfill historical price data for Kalshi outcomes.

    Modes:
      resolved_zero — resolved markets with zero snapshots (calibration).
      open_sparse   — open/active feed-visible markets with no snapshots
                      in the last 7 days (chart quality for Discover).

    Uses the Kalshi batch candlesticks API (GET /markets/candlesticks)
    to fetch hourly price history.  The old per-market endpoint
    (GET /markets/{ticker}/candlesticks) was deprecated and returns 404.
    """
    import asyncio
    from app.models.models import FuturesOddsSnapshot

    stats = {
        "mode": mode,
        "outcomes_processed": 0, "outcomes_skipped": 0,
        "snapshots_created": 0, "api_empty": 0, "errors": [],
    }

    try:
        from app.services.kalshi_api import KalshiAPIService

        async with get_task_session() as session:
            if mode == "open_sparse":
                result = await session.execute(
                    text("""
                        SELECT fo.id AS outcome_id, fo.external_id AS ticker,
                               fm.external_id AS event_ticker
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'kalshi'
                          AND fm.status IN ('open', 'active')
                          AND (fm.image_url IS NOT NULL
                               OR fm.hook_description IS NOT NULL)
                          AND NOT EXISTS (
                              SELECT 1 FROM futures_odds_snapshots fos
                              WHERE fos.outcome_id = fo.id
                                AND fos.captured_at > NOW() - INTERVAL '7 days'
                          )
                        ORDER BY fm.updated_at DESC
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )
            else:
                result = await session.execute(
                    text("""
                        SELECT fo.id AS outcome_id, fo.external_id AS ticker,
                               fm.external_id AS event_ticker
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'kalshi'
                          AND fm.status = 'resolved'
                          AND (
                              NOT EXISTS (
                                  SELECT 1 FROM futures_odds_snapshots fos
                                  WHERE fos.outcome_id = fo.id
                              )
                              OR fo.opening_probability IS NULL
                          )
                        ORDER BY fm.resolution_date DESC NULLS LAST
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )
            outcomes = result.fetchall()

            if not outcomes:
                return {**stats, "status": "nothing_to_backfill"}

            logger.info("Kalshi price history backfill: %d outcomes", len(outcomes))

            service = KalshiAPIService()
            try:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                for row in outcomes:
                    try:
                        candles = await service.get_market_candlesticks(
                            ticker=row.ticker, period_interval=60,
                        )
                    except Exception as e:
                        stats["errors"].append(f"{row.ticker}: {str(e)[:80]}")
                        continue

                    if not candles:
                        stats["api_empty"] += 1
                        continue

                    batch_values = []
                    for c in candles:
                        ts = c.get("t")
                        prob = c.get("yes_price")
                        if ts is None or prob is None:
                            continue
                        prob = float(prob)
                        if prob <= 0 or prob >= 1:
                            continue
                        captured = datetime.fromtimestamp(ts, tz=timezone.utc)
                        batch_values.append({
                            "outcome_id": row.outcome_id,
                            "bookmaker": "kalshi",
                            "probability": round(prob, 6),
                            "last_price": round(prob, 4),
                            "captured_at": captured,
                        })

                    if batch_values:
                        for i in range(0, len(batch_values), 100):
                            stmt = pg_insert(FuturesOddsSnapshot).values(batch_values[i:i + 100])
                            await session.execute(stmt.on_conflict_do_nothing())
                        stats["snapshots_created"] += len(batch_values)

                        # Set opening_probability from earliest snapshot if not already set
                        earliest = batch_values[0]  # candles are sorted chronologically
                        await session.execute(
                            text("""
                                UPDATE futures_outcomes
                                SET opening_probability = :prob,
                                    opening_captured_at = :ts
                                WHERE id = :id AND opening_probability IS NULL
                            """),
                            {"prob": earliest["probability"], "ts": earliest["captured_at"], "id": row.outcome_id},
                        )

                    stats["outcomes_processed"] += 1
                    if stats["outcomes_processed"] % 50 == 0:
                        await session.commit()
                        logger.info("Kalshi history: %d/%d outcomes, %d snapshots, %d empty",
                                    stats["outcomes_processed"], len(outcomes),
                                    stats["snapshots_created"], stats["api_empty"])
                    await asyncio.sleep(0.05)

                await session.commit()
            finally:
                await service.close()

    except Exception as e:
        logger.error("Kalshi price history backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    return stats
