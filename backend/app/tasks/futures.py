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
                    from app.utils.futures_categorization import (
                        categorize_by_rules, detect_league,
                        detect_season, compute_canonical_market_key,
                    )
                    inferred_category = _infer_category(sport_key)
                    market_tier = compute_market_tier(market_name, inferred_category)

                    # Detect league and sport category
                    sport_category = categorize_by_rules(market_name, sport_key)
                    league = detect_league(market_name, sport_key)
                    season = detect_season(market_name, league)

                    # Compute canonical key for cross-source matching
                    canonical_key = compute_canonical_market_key(
                        sport_category, league, inferred_category, season,
                    )

                    # Generate category tags
                    from app.utils.futures_categorization import generate_category_tags
                    tags = generate_category_tags(
                        market_name, sport_category, league, inferred_category,
                    )

                    # Upsert the market
                    market_stmt = pg_insert(FuturesMarket).values(
                        source="odds_api",
                        external_id=sport_key,
                        sport_id=sport_id,
                        name=market_name,
                        category=inferred_category,
                        market_tier=market_tier,
                        llm_sport_category=sport_category,
                        llm_league=league,
                        canonical_market_key=canonical_key,
                        category_tags=tags,
                        mutually_exclusive=True,
                        status="open",
                    ).on_conflict_do_update(
                        index_elements=["source", "external_id"],
                        set_={
                            "name": market_name,
                            "sport_id": sport_id,  # Update sport link on every sync
                            "market_tier": market_tier,
                            "llm_sport_category": sport_category,
                            "llm_league": league,
                            "canonical_market_key": canonical_key,
                            "category_tags": tags,
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


# =========================================================================
# Background categorization
# =========================================================================

async def _categorize_futures_impl(limit: int = 100, force_llm: bool = False):
    """
    Categorize uncategorized futures markets in the background.

    Uses rules first (fast, free), then LLM fallback for unmatched markets.
    Runs as a Celery task to avoid Heroku's 30-second request timeout.
    """
    from sqlalchemy import select
    from app.models import FuturesMarket
    from app.utils.futures_categorization import categorize_market, categorize_by_rules
    from app.services import llm

    stats = {
        "processed": 0,
        "categorized": 0,
        "by_category": {},
        "errors": [],
        "sample_results": [],
    }

    try:
        async with get_task_session() as session:
            # Find uncategorized markets
            result = await session.execute(
                select(FuturesMarket)
                .where(
                    FuturesMarket.sport_id.is_(None),
                    FuturesMarket.llm_sport_category.is_(None),
                )
                .limit(limit)
            )
            markets = result.scalars().all()

            if not markets:
                stats["message"] = "No uncategorized markets found"
                return stats

            llm_available = llm.is_available()

            for market in markets:
                try:
                    if force_llm and llm_available:
                        category = llm.classify_futures_market(market.name)
                    else:
                        category = categorize_market(
                            market.name, use_llm=llm_available
                        )

                    if category:
                        market.llm_sport_category = category
                        stats["categorized"] += 1
                        stats["by_category"][category] = (
                            stats["by_category"].get(category, 0) + 1
                        )
                        if len(stats["sample_results"]) < 20:
                            stats["sample_results"].append({
                                "id": market.id,
                                "name": market.name,
                                "category": category,
                            })
                except Exception as e:
                    stats["errors"].append(f"{market.id}: {str(e)}")

                stats["processed"] += 1

            await session.commit()

            # Count remaining
            remaining_result = await session.execute(
                select(func.count(FuturesMarket.id))
                .where(
                    FuturesMarket.sport_id.is_(None),
                    FuturesMarket.llm_sport_category.is_(None),
                )
            )
            stats["remaining"] = remaining_result.scalar_one()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    stats["message"] = (
        f"Categorized {stats['categorized']}/{stats['processed']} markets. "
        f"{stats.get('remaining', '?')} remaining."
    )

    logger.info(
        "Futures categorization complete: %d/%d categorized, %d remaining",
        stats["categorized"],
        stats["processed"],
        stats.get("remaining", -1),
    )
    return stats


async def _recategorize_other_impl(limit: int = 500):
    """
    Multi-phase recategorization for markets currently tagged 'other'.

    Phase 1: Pattern matching (fast, free, deterministic)
    Phase 2: League inference (fast, free)
    Phase 3: LLM with outcome context (smart, constrained to known categories)
    Phase 4: Open-ended LLM classification (unconstrained, future-proof)
    + Tag enrichment: LLM generates tags for sparse-tag markets

    When new patterns are added, Phase 1 catches them. Phase 3 uses
    outcome names as context for disambiguation. Phase 4 lets the LLM
    freely name categories — handling novel market types that don't fit
    any predefined category without code changes.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models import FuturesMarket, FuturesOutcome
    from app.utils.futures_categorization import (
        categorize_by_rules, detect_league, infer_sport_from_league,
        generate_category_tags,
    )
    from app.services import llm

    stats = {
        "processed": 0,
        "reclassified": 0,
        "reclassified_by_rules": 0,
        "reclassified_by_league": 0,
        "reclassified_by_llm": 0,
        "reclassified_by_open_ended": 0,
        "tags_enriched": 0,
        "novel_categories": [],
        "by_category": {},
        "sample_results": [],
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Eagerly load outcomes so we can pass names to LLM
            result = await session.execute(
                select(FuturesMarket)
                .options(selectinload(FuturesMarket.outcomes))
                .where(FuturesMarket.llm_sport_category == "other")
                .limit(limit)
            )
            markets = result.scalars().all()

            if not markets:
                stats["message"] = "No 'other' markets to re-check"
                return stats

            llm_available = llm.is_available()
            llm_batch = []  # Collect markets for LLM phase

            for market in markets:
                stats["processed"] += 1
                try:
                    # Phase 1: Re-run pattern matching (new patterns + game prop detection)
                    sport_key = (
                        market.external_id
                        if market.source == "odds_api"
                        else None
                    )
                    category = categorize_by_rules(market.name, sport_key)
                    if category and category != "other":
                        market.llm_sport_category = category
                        # Generate tags
                        market.category_tags = generate_category_tags(
                            market.name, category, market.llm_league,
                            market.category,
                        )
                        stats["reclassified"] += 1
                        stats["reclassified_by_rules"] += 1
                        stats["by_category"][category] = (
                            stats["by_category"].get(category, 0) + 1
                        )
                        if len(stats["sample_results"]) < 20:
                            stats["sample_results"].append({
                                "id": market.id,
                                "name": market.name,
                                "old": "other",
                                "new": category,
                                "method": "rules",
                            })
                        continue

                    # Phase 2: Infer sport from league detection
                    league = market.llm_league
                    if not league:
                        league = detect_league(market.name, sport_key)
                        if league:
                            market.llm_league = league

                    if league:
                        sport = infer_sport_from_league(league)
                        if sport and sport != "other":
                            market.llm_sport_category = sport
                            market.category_tags = generate_category_tags(
                                market.name, sport, league,
                                market.category,
                            )
                            stats["reclassified"] += 1
                            stats["reclassified_by_league"] += 1
                            stats["by_category"][sport] = (
                                stats["by_category"].get(sport, 0) + 1
                            )
                            if len(stats["sample_results"]) < 20:
                                stats["sample_results"].append({
                                    "id": market.id,
                                    "name": market.name,
                                    "old": "other",
                                    "new": sport,
                                    "method": f"league:{league}",
                                })
                            continue

                    # Phase 3: Queue for LLM with outcome context
                    if llm_available:
                        llm_batch.append(market)

                except Exception as e:
                    stats["errors"].append(f"{market.id}: {str(e)}")

            # Phase 3: LLM classification with outcome names as context
            if llm_batch:
                for market in llm_batch:
                    try:
                        # Get outcome names for context
                        outcome_names = [
                            o.name for o in market.outcomes
                            if o.name and o.name not in ("Yes", "No")
                        ]

                        if outcome_names:
                            result_cat = llm.classify_futures_market_with_outcomes(
                                market.name, outcome_names,
                            )
                        else:
                            result_cat = llm.classify_futures_market(market.name)

                        if result_cat and result_cat != "other":
                            market.llm_sport_category = result_cat
                            market.category_tags = generate_category_tags(
                                market.name, result_cat, market.llm_league,
                                market.category,
                            )
                            stats["reclassified"] += 1
                            stats["reclassified_by_llm"] += 1
                            stats["by_category"][result_cat] = (
                                stats["by_category"].get(result_cat, 0) + 1
                            )
                            if len(stats["sample_results"]) < 20:
                                stats["sample_results"].append({
                                    "id": market.id,
                                    "name": market.name,
                                    "old": "other",
                                    "new": result_cat,
                                    "method": f"llm+outcomes({len(outcome_names)})",
                                })
                    except Exception as e:
                        stats["errors"].append(f"LLM {market.id}: {str(e)}")

            # Phase 4: Open-ended (unconstrained) classification
            # For markets Phase 3 still left as "other", ask the LLM to
            # freely name a category. This handles novel market types that
            # don't fit SPORT_CATEGORIES without requiring code changes.
            still_other = [
                m for m in llm_batch
                if m.llm_sport_category == "other"
            ] if llm_batch else []

            if still_other:
                for market in still_other:
                    try:
                        outcome_names = [
                            o.name for o in market.outcomes
                            if o.name and o.name not in ("Yes", "No")
                        ]
                        result_cat = llm.classify_open_ended(
                            market.name, outcome_names or None,
                        )
                        if result_cat and result_cat != "other":
                            # Check if this is a novel category
                            known = [c.lower() for c in llm.SPORT_CATEGORIES]
                            if result_cat.lower() not in known:
                                stats["novel_categories"].append(result_cat)

                            market.llm_sport_category = result_cat
                            tags = generate_category_tags(
                                market.name, result_cat,
                                market.llm_league, market.category,
                            )
                            # Ensure the open-ended category itself is a tag
                            if result_cat not in tags:
                                tags = sorted(set(tags) | {result_cat})
                            market.category_tags = tags
                            stats["reclassified"] += 1
                            stats["reclassified_by_open_ended"] += 1
                            stats["by_category"][result_cat] = (
                                stats["by_category"].get(result_cat, 0) + 1
                            )
                            if len(stats["sample_results"]) < 30:
                                stats["sample_results"].append({
                                    "id": market.id,
                                    "name": market.name,
                                    "old": "other",
                                    "new": result_cat,
                                    "method": "open_ended",
                                })
                    except Exception as e:
                        stats["errors"].append(
                            f"Open-ended {market.id}: {str(e)}"
                        )

            # Tag enrichment: For markets with sparse tags (≤1),
            # ask the LLM to generate richer tags. Limit to 200 per run.
            if llm_available:
                sparse_markets = [
                    m for m in markets
                    if len(m.category_tags or []) <= 1
                ][:200]

                for market in sparse_markets:
                    try:
                        outcome_names = [
                            o.name for o in market.outcomes
                            if o.name and o.name not in ("Yes", "No")
                        ]
                        new_tags = llm.generate_tags_via_llm(
                            market.name,
                            outcome_names=outcome_names or None,
                            existing_tags=market.category_tags,
                        )
                        if len(new_tags) > len(market.category_tags or []):
                            market.category_tags = new_tags
                            stats["tags_enriched"] += 1
                    except Exception as e:
                        stats["errors"].append(
                            f"Tags {market.id}: {str(e)}"
                        )

            await session.commit()

            # Count remaining 'other'
            remaining_result = await session.execute(
                select(func.count(FuturesMarket.id))
                .where(FuturesMarket.llm_sport_category == "other")
            )
            stats["remaining_other"] = remaining_result.scalar_one()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    novel = stats.get("novel_categories", [])
    novel_str = f" Novel categories: {novel}" if novel else ""
    stats["message"] = (
        f"Re-checked {stats['processed']} 'other' markets, "
        f"reclassified {stats['reclassified']} "
        f"(rules:{stats['reclassified_by_rules']}, "
        f"league:{stats['reclassified_by_league']}, "
        f"llm:{stats['reclassified_by_llm']}, "
        f"open_ended:{stats['reclassified_by_open_ended']}). "
        f"Tags enriched: {stats['tags_enriched']}. "
        f"{stats.get('remaining_other', '?')} still 'other'.{novel_str}"
    )

    logger.info(
        "Recategorize-other complete: %d/%d reclassified "
        "(rules=%d, league=%d, llm=%d, open_ended=%d), "
        "tags_enriched=%d, novel=%s",
        stats["reclassified"],
        stats["processed"],
        stats["reclassified_by_rules"],
        stats["reclassified_by_league"],
        stats["reclassified_by_llm"],
        stats["reclassified_by_open_ended"],
        stats["tags_enriched"],
        novel or "none",
    )
    return stats
