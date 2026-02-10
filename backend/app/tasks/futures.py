"""
Futures/outrights polling task (The Odds API).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func

from app.services.odds_api import OddsAPIService
from app.tasks.base import get_task_session, run_async

logger = logging.getLogger(__name__)


def _infer_base_sport(sport_key: str) -> str:
    """Infer the base sport key from a futures sport key.

    Examples:
        basketball_nba_championship_winner -> basketball_nba
        americanfootball_nfl_super_bowl_winner -> americanfootball_nfl
        baseball_mlb_world_series_winner -> baseball_mlb
        icehockey_nhl_championship_winner -> icehockey_nhl
        soccer_epl_winner -> soccer_epl
    """
    # Common futures suffixes to strip (order matters - longer/compound first)
    suffixes = [
        # Compound suffixes (must come first)
        "_championship_winner",
        "_super_bowl_winner",
        "_world_series_winner",
        "_stanley_cup_winner",
        "_division_winner",
        "_conference_winner",
        # Simple suffixes
        "_championship",
        "_winner",
        "_mvp",
    ]

    result = sport_key

    # Keep stripping suffixes until no more match
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if result.endswith(suffix):
                result = result[:-len(suffix)]
                changed = True
                break  # Restart from beginning after each strip

    return result


def _infer_category(sport_key: str) -> str:
    """Infer the market category from the sport key."""
    key_lower = sport_key.lower()

    if "championship" in key_lower or "winner" in key_lower:
        return "championship"
    elif "mvp" in key_lower:
        return "mvp"
    elif "division" in key_lower:
        return "division"
    elif "conference" in key_lower:
        return "conference"
    else:
        return "other"


def _aggregate_futures_outcomes(markets_data) -> dict:
    """Aggregate outcome odds across multiple bookmakers.

    Normalizes each bookmaker's implied probabilities to remove the vig
    (overround) before averaging across bookmakers. Without normalization,
    implied probabilities from American odds sum to >100% (often 130-150%
    for markets with many outcomes), inflating every outcome's probability.

    Returns a dict mapping outcome names to aggregated data:
    {
        "Lakers": {
            "probability": 0.11,  # Average of vig-removed probs across books
            "bookmakers": {
                "draftkings": {"probability": 0.14, "american_odds": 600},
                "fanduel": {"probability": 0.16, "american_odds": 525},
            }
        }
    }
    """
    from statistics import mean
    from collections import defaultdict

    # First pass: group outcomes by bookmaker to calculate per-bookmaker totals
    bookmaker_outcomes = defaultdict(list)  # bookmaker -> [(name, probability, american_odds)]

    for market in markets_data:
        bookmaker = market.bookmaker
        for outcome in market.outcomes:
            bookmaker_outcomes[bookmaker].append(
                (outcome.name, outcome.probability, outcome.american_odds)
            )

    # Second pass: normalize each bookmaker's probabilities to sum to 1.0
    # This removes the vig/overround
    outcomes = {}

    for bookmaker, bm_outcomes in bookmaker_outcomes.items():
        total_prob = sum(prob for _, prob, _ in bm_outcomes)

        for name, raw_prob, american_odds in bm_outcomes:
            # Normalize: divide by total so all outcomes sum to 1.0
            normalized_prob = raw_prob / total_prob if total_prob > 0 else raw_prob

            if name not in outcomes:
                outcomes[name] = {
                    "normalized_probabilities": [],
                    "bookmakers": {},
                }

            outcomes[name]["normalized_probabilities"].append(normalized_prob)
            outcomes[name]["bookmakers"][bookmaker] = {
                "probability": raw_prob,  # Keep raw implied prob for bookmaker display
                "american_odds": american_odds,
            }

    # Calculate average normalized probability for each outcome
    result = {}
    for name, data in outcomes.items():
        result[name] = {
            "probability": mean(data["normalized_probabilities"]),
            "bookmakers": data["bookmakers"],
        }

    return result


async def _poll_futures_odds():
    """Async implementation of futures polling."""
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Sport
    from app.utils.odds_math import american_to_probability, probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select
    from datetime import timedelta

    service = OddsAPIService()
    stats = {
        "markets_processed": 0,
        "outcomes_updated": 0,
        "snapshots_created": 0,
        "errors": [],
    }

    try:
        # Discover sports with outrights
        outright_sports = await service.get_sports_with_outrights()
        sport_keys = [s["key"] for s in outright_sports]

        async with get_task_session() as session:
            # Get or create sport records for linking
            sport_result = await session.execute(
                select(Sport.id, Sport.key)
            )
            sport_map = {row.key: row.id for row in sport_result.all()}

            for sport_key in sport_keys:
                try:
                    api_response = await service.get_futures_odds(sport_key)
                    markets_data = service._parse_futures(api_response, sport_key)

                    if not markets_data:
                        continue

                    # Get market name from first result
                    market_name = markets_data[0].market_name if markets_data else sport_key

                    # Find or infer the base sport for linking
                    # e.g., "basketball_nba_championship" -> "basketball_nba"
                    base_sport_key = _infer_base_sport(sport_key)
                    sport_id = sport_map.get(base_sport_key)

                    # Compute market tier for relevance ranking
                    from app.utils.team_linking import compute_market_tier
                    inferred_category = _infer_category(sport_key)
                    market_tier = compute_market_tier(market_name, inferred_category)

                    # Upsert the market
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="odds_api",
                        external_id=sport_key,
                        sport_id=sport_id,
                        name=market_name,
                        category=inferred_category,
                        market_tier=market_tier,
                        mutually_exclusive=True,
                        status="open",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": market_name,
                            "sport_id": sport_id,  # Update sport link on every sync
                            "market_tier": market_tier,
                            "updated_at": func.now(),
                        }
                    ).returning(FuturesMarket.id)

                    result = await session.execute(market_stmt)
                    market_id = result.scalar_one()
                    stats["markets_processed"] += 1

                    # Aggregate outcomes across bookmakers
                    outcome_odds = _aggregate_futures_outcomes(markets_data)

                    # Get existing outcomes for this market
                    existing_result = await session.execute(
                        select(FuturesOutcome)
                        .where(FuturesOutcome.market_id == market_id)
                    )
                    existing_outcomes = {o.external_id: o for o in existing_result.scalars().all()}

                    # Compute ranks (1 = highest probability)
                    ranked_outcomes = sorted(
                        outcome_odds.items(),
                        key=lambda x: x[1]["probability"],
                        reverse=True
                    )

                    now = datetime.now(timezone.utc)
                    yesterday = now - timedelta(hours=24)

                    for rank, (outcome_name, odds_data) in enumerate(ranked_outcomes, 1):
                        prob = odds_data["probability"]
                        american = probability_to_american(prob)

                        # Check if outcome exists
                        existing = existing_outcomes.get(outcome_name)

                        if existing:
                            # Calculate 24h change
                            old_prob = float(existing.current_probability) if existing.current_probability else None
                            prob_change = prob - old_prob if old_prob else None

                            old_rank = existing.rank
                            rank_change = old_rank - rank if old_rank else None

                            # Update existing outcome
                            existing.current_probability = prob
                            existing.current_american_odds = american
                            existing.probability_change_24h = prob_change
                            existing.rank = rank
                            existing.rank_change_24h = rank_change
                            existing.last_updated = now

                            # Set opening odds if not set
                            if existing.opening_probability is None:
                                existing.opening_probability = prob
                                existing.opening_american_odds = american
                                existing.opening_captured_at = now

                            outcome_id = existing.id
                        else:
                            # Create new outcome
                            outcome_stmt = pg_insert(FuturesOutcome).values(
                                market_id=market_id,
                                external_id=outcome_name,
                                name=outcome_name,
                                current_probability=prob,
                                current_american_odds=american,
                                opening_probability=prob,
                                opening_american_odds=american,
                                opening_captured_at=now,
                                rank=rank,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_={
                                    "current_probability": prob,
                                    "current_american_odds": american,
                                    "rank": rank,
                                    "last_updated": func.now(),
                                }
                            ).returning(FuturesOutcome.id)

                            result = await session.execute(outcome_stmt)
                            outcome_id = result.scalar_one()

                        stats["outcomes_updated"] += 1

                        # Create snapshots for each bookmaker
                        for bookmaker, bm_odds in odds_data["bookmakers"].items():
                            snapshot_stmt = pg_insert(FuturesOddsSnapshot).values(
                                outcome_id=outcome_id,
                                bookmaker=bookmaker,
                                probability=bm_odds["probability"],
                                american_odds=bm_odds["american_odds"],
                                captured_at=now,
                            )
                            await session.execute(snapshot_stmt)
                            stats["snapshots_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")
                    continue

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    finally:
        await service.close()

    return stats
