"""
Polymarket prediction market polling task.

Fetches sports and non-sports prediction market data from Polymarket's
public API (no API key required). Stores as futures markets/outcomes
with source="polymarket".
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text

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


def _is_tradeable_opening(prob: Optional[float], has_trading: bool) -> bool:
    """Whether `prob` is a valid opening probability worth stamping.

    #137: an opening only makes sense at a real, tradeable, non-degenerate price.
    A price of exactly 0.0 or 1.0 is a settled/placeholder value, not an opening —
    stamping it on both sides of a decomposed Over/Under market produced the
    impossible both-sides=1.0 binaries that poisoned the calibration curve and the
    price_moved dimension. Requiring 0 < prob < 1 guarantees a binary's two sides
    can never both open at 1.0.
    """
    return bool(has_trading) and prob is not None and 0.0 < prob < 1.0


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

        # Cleanup: delete anonymized "Player XX" reserved-slot outcomes (#953).
        # Polymarket pre-creates empty slots named "Player AD"/"Player AG" with no
        # recoverable name (verified in the raw payload: groupItemTitle="Player AD",
        # prices=None, bid=0, lastTrade=0). The broadened _is_placeholder_outcome
        # now skips them at ingestion, but rows ingested before that fix persist and
        # render at ~0.5 across ~44 award/round-leader markets. Remove them so they
        # stop surfacing everywhere (idempotent — re-runs find none; real named
        # candidates in the same markets are untouched). Display fix only; these are
        # OPEN, unresolved, NULL cal_prob/volume rows — not an is_winner mutation
        # (gotcha #21).
        try:
            async with get_task_session() as session:
                from sqlalchemy import delete as sa_delete
                from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
                # Scope to OPEN/active markets only: that is where placeholders
                # render, and it keeps the cleanup away from resolved-market rows
                # (gotcha #21 — never disturb settled data).
                placeholder_sub = select(FuturesOutcome.id).where(
                    FuturesOutcome.name.op("~")(r"^Player [A-Z]+$"),
                    FuturesOutcome.market_id.in_(
                        select(FuturesMarket.id).where(
                            FuturesMarket.source == "polymarket",
                            FuturesMarket.status.in_(["open", "active"]),
                        )
                    ),
                )
                placeholder_ids = (await session.execute(placeholder_sub)).scalars().all()
                if placeholder_ids:
                    logger.info(
                        "Cleanup: deleting %d Polymarket 'Player XX' placeholder outcomes (#953)",
                        len(placeholder_ids),
                    )
                    await session.execute(
                        sa_delete(FuturesOddsSnapshot).where(
                            FuturesOddsSnapshot.outcome_id.in_(placeholder_ids)
                        )
                    )
                    await session.execute(
                        sa_delete(FuturesOutcome).where(
                            FuturesOutcome.id.in_(placeholder_ids)
                        )
                    )
                    await session.commit()
                    logger.info(
                        "Polymarket placeholder cleanup complete: %d deleted",
                        len(placeholder_ids),
                    )
        except Exception as e:
            logger.warning("Polymarket placeholder cleanup failed (non-fatal): %s", e)

        # Stream events page-by-page instead of loading all into memory.
        # Each page is processed and committed in batches.
        #
        # #219E (creation freeze, poly edition): Polymarket's Gamma API changed
        # (~2026-07-14) to CAP offset pagination at offset 2000 — offset>=2100
        # now returns HTTP 422 "offset too large, use /events/keyset". Combined
        # with the previous default sort (oldest-first by id), the poll was stuck
        # perpetually re-scanning the OLDEST ~2000 active events (all already in
        # DB) and could NEVER reach newly-created markets → daily creation fell
        # off a cliff from ~1000-2000/day to <10/day while the poll kept
        # SUCCEEDING (it just re-updated the same old set). Fix: order the scan
        # NEWEST-first (order=startDate desc, below) so new markets land on the
        # first pages, and bound max_pages to the 2000-offset cap so we never
        # burn calls on the guaranteed-422 tail. Durable follow-up: migrate to
        # /events/keyset for uncapped coverage (see #219E report).
        max_pages = 20  # offset 0..1900 — the Gamma offset-2000 hard cap
        seen_ids: set[str] = set()
        batch: list = []

        # #984: bound the pagination to a time budget under the 540s soft limit.
        # poll_polymarket scanned up to 130 active pages + an 80-page settled-
        # sports pass with NO time guard, busting the wall (consec=13, 0
        # successes >24h — the sole driver of critical health). Mirror the #969
        # inner-bound: a per-page budget check breaks before the wall, and a
        # rotating Redis page cursor resumes next run so coverage rotates across
        # runs instead of re-scanning the same early pages each time.
        import time as _time
        _start = _time.monotonic()
        _MAX_SECONDS = 420  # 120s margin under the 540s soft limit
        from app.tasks.redis_state import get_redis_client
        _rc = get_redis_client()
        _poll_cursor_key = "bainluck:polymarket_poll_page"
        _resume_page = int(_rc.get(_poll_cursor_key) or 0)
        if not (0 <= _resume_page < max_pages):
            _resume_page = 0

        events_data = None
        pages_fetched = 0
        budget_hit = False
        for _i in range(max_pages):
            page = (_resume_page + _i) % max_pages
            if _time.monotonic() - _start > _MAX_SECONDS:
                _rc.setex(_poll_cursor_key, 86400, str(page))  # resume here next run
                logger.info(
                    "Polymarket poll: time budget (%ds) hit after %d pages "
                    "(resume page %d next run)", _MAX_SECONDS, _i, page,
                )
                budget_hit = True
                break
            if _i > 0:
                await asyncio.sleep(0.3)

            try:
                # #219E: NEWEST-first. The Gamma default sort is oldest-first,
                # which — under the new offset-2000 cap — pinned the poll on the
                # oldest (already-ingested) active events and created nothing.
                # order=startDate + ascending=False puts newly-created markets on
                # the first pages, well inside the 2000-offset window.
                events_data = await service.get_events(
                    active=True, closed=False, limit=100, offset=page * 100,
                    order="startDate", ascending=False,
                )
            except Exception as e:
                logger.warning("Error fetching Polymarket page %d: %s", page, e)
                # #219E: a 422 "offset too large" means we hit the Gamma cap —
                # reset the cursor so the next run restarts at the newest page
                # instead of sticking at an always-422 offset.
                if "offset too large" in str(e) or "422" in str(e):
                    _rc.setex(_poll_cursor_key, 86400, "0")
                break

            pages_fetched += 1
            if not events_data:
                # wrapped past the end of the active set — reset cursor, stop
                _rc.setex(_poll_cursor_key, 86400, "0")
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
                # reached the last active page — next run starts fresh
                _rc.setex(_poll_cursor_key, 86400, "0")
                break
        else:
            # full max_pages sweep with no early break — reset cursor
            _rc.setex(_poll_cursor_key, 86400, "0")

        # Process remaining events
        if batch:
            await _process_event_batch(
                batch, stats, FuturesMarket, FuturesOutcome,
                FuturesOddsSnapshot, pg_insert, probability_to_american,
                compute_market_tier,
            )
            batch.clear()

        logger.info(
            "Polymarket: fetched %d unique events across %d pages (budget_hit=%s)",
            len(seen_ids), pages_fetched, budget_hit,
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

        # Supplementary pass: fetch settled sports game events by tag.
        # The main scan (active=True, closed=False) only gets open events.
        # Settled game events are needed for source coverage + calibration.
        # #173/#1024: mma/boxing were absent, so a poly fight event the main scan
        # missed while open (e.g. a budget-truncated cycle) could NEVER be
        # recovered — the poly half of A5's combat cross-source blend. Confirmed
        # live: gamma tag_slug=mma / =boxing return settled UFC/boxing events.
        # The pass is budget-guarded (per-tag + per-page `_MAX_SECONDS` breaks),
        # so extending the tag list can't push the task past the 540s wall.
        #
        # #174 Item 2: CATEGORY-AGNOSTIC. A hand list is the "hand-built net has
        # holes" class (golf-class → combat-class, same bug rediscovered). Enumerate
        # tags from the SOURCE (`get_tags`) minus crypto, keep the proven sports tags
        # as a PRIORITY head (never regress), and rotate the remainder through a
        # resumable cursor so any category is reached within a few runs and per-run
        # work stays bounded (gotcha #34). Fallback-safe: any enumeration failure
        # falls back to the hand list, so behavior can only ever improve, never break.
        _PRIORITY_TAG_SLUGS = [
            "baseball", "basketball", "hockey", "football", "mma", "boxing",
        ]
        _TAGS_PER_RUN = 14  # priority(6) + ~8 rotated; well within _MAX_SECONDS
        _tag_cursor_key = "bainluck:poly_settled_tag_cursor"
        try:
            from app.utils.settled_recovery import extract_tag_slugs, select_rotation

            _all_tags = extract_tag_slugs(await service.get_tags(limit=200))
            if _all_tags:
                _cursor_pos = int(_rc.get(_tag_cursor_key) or 0)
                _SPORTS_TAG_SLUGS, _next_pos = select_rotation(
                    _all_tags, _PRIORITY_TAG_SLUGS, _cursor_pos, _TAGS_PER_RUN
                )
                _rc.setex(_tag_cursor_key, 86400 * 14, str(_next_pos))
                logger.info(
                    "Polymarket settled-recovery: %d tags at source, scanning %d "
                    "this run (priority + rotated from %d)",
                    len(_all_tags), len(_SPORTS_TAG_SLUGS), _cursor_pos,
                )
            else:
                _SPORTS_TAG_SLUGS = _PRIORITY_TAG_SLUGS
        except Exception as _tag_err:
            logger.warning(
                "Polymarket tag enumeration failed (%s) — falling back to hand list",
                _tag_err,
            )
            _SPORTS_TAG_SLUGS = _PRIORITY_TAG_SLUGS
        supplemented = 0
        for tag_slug in _SPORTS_TAG_SLUGS:
            # #984: skip the settled-sports pass entirely if the main scan already
            # spent the budget — it must not push the task past the 540s wall.
            if budget_hit or (_time.monotonic() - _start) > _MAX_SECONDS:
                budget_hit = True
                break
            tag_offset = 0
            max_tag_pages = 20
            for _tp in range(max_tag_pages):
                if (_time.monotonic() - _start) > _MAX_SECONDS:
                    budget_hit = True
                    break
                try:
                    await asyncio.sleep(0.3)
                    tag_events = await service.get_events(
                        active=None,
                        closed=True,
                        tag_slug=tag_slug,
                        limit=100,
                        offset=tag_offset,
                        order="startDate",
                        ascending=False,
                    )
                    if not tag_events:
                        break
                    for event_data in tag_events:
                        eid = str(event_data.get("id", ""))
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)
                        parsed = service._parse_event(event_data)
                        if parsed and parsed.markets:
                            batch.append(parsed)
                            supplemented += 1
                    if batch:
                        await _process_event_batch(
                            batch, stats, FuturesMarket, FuturesOutcome,
                            FuturesOddsSnapshot, pg_insert, probability_to_american,
                            compute_market_tier,
                        )
                        batch.clear()
                    tag_offset += 100
                    if len(tag_events) < 100:
                        break
                except Exception as e:
                    logger.debug("Polymarket supplementary %s page %d: %s", tag_slug, _tp, e)
                    break
        if supplemented:
            logger.info("Polymarket supplementary sports fetch added %d events", supplemented)

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
    from app.utils.editorial_patterns import matches_editorial_recall as _matches_editorial_recall

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
                if len(event.markets) > 1:
                    poly_metadata["market_count"] = len(event.markets)

                # #173/#1024: matchup-title write-hook AT INGEST. A game event's
                # decomposed sub-markets (spread/prop rows) don't name both
                # participants in their own `name` (gotcha #18), so the grammar
                # adapter yields ZERO participants and the poly market_event
                # shadow link can't be reproduced. The one-shot backfill stamped
                # `market_metadata['matchup_title']` after the fact, but new rows
                # ingested since got NOTHING until a manual re-run — the 0%-on-
                # new-rows gap. Recover the group matchup from the sibling names
                # (source-native, non-circular — a moneyline/O-U sibling names
                # "A vs. B") and stamp it here so fresh rows carry it at birth.
                # None for non-game groups (no "vs" sibling), so it's a no-op for
                # awards/negrisk questions.
                _group_matchup_title = None
                if len(event.markets) > 1:
                    from app.utils.polymarket_matchup_backfill import (
                        group_matchup as _group_matchup,
                    )
                    _group_matchup_title = _group_matchup(
                        [event.title or ""] + [m.question or "" for m in event.markets]
                    )
                    if _group_matchup_title:
                        poly_metadata["matchup_title"] = _group_matchup_title

                # Aggregate volume/liquidity from event + markets
                poly_volume = int(event.volume) if event.volume else None
                poly_liquidity = float(event.liquidity) if event.liquidity else None
                poly_volume_24h = sum(
                    int(m.volume_24h or 0) for m in event.markets
                ) or None

                _editorial = _matches_editorial_recall(event.title)
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
                    "is_editorial_recall": _editorial,
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
                    is_editorial_recall=_editorial,
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
                        prob = _resolve_market_probability(market)

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
                        prob = _resolve_market_probability(market)

                        if prob is None or prob <= 0:
                            continue

                        sub_name = market.question or event.title
                        sub_tier = compute_market_tier(sub_name, category, sport_category=llm_sport_category)

                        # #173/#1024: stamp the group matchup title onto every
                        # sub-market of a game group at ingest. On conflict, MERGE
                        # into existing metadata (never clobber) with the same
                        # COALESCE(md,'{}') || jsonb_build_object idiom the backfill
                        # uses, so re-ingests and prior backfills stay idempotent.
                        sub_meta_insert = (
                            {"matchup_title": _group_matchup_title}
                            if _group_matchup_title
                            else None
                        )
                        sub_set = {
                            "name": sub_name,
                            "market_tier": sub_tier,
                            "status": "open" if event.active else "resolved",
                            "event_id": parent_event_id,
                            "updated_at": func.now(),
                        }
                        if _group_matchup_title:
                            from sqlalchemy import cast as _sa_cast, literal as _sa_literal
                            from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
                            sub_set["market_metadata"] = func.coalesce(
                                FuturesMarket.market_metadata,
                                _sa_cast(_sa_literal("{}"), _PG_JSONB),
                            ).op("||")(
                                func.jsonb_build_object("matchup_title", _group_matchup_title)
                            )

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
                            market_metadata=sub_meta_insert,
                        ).on_conflict_do_update(
                            index_elements=["source", "external_id"],
                            set_=sub_set,
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
                        # An opening only makes sense at a real, non-degenerate price.
                        # A price of exactly 0.0/1.0 is a settled/placeholder value, not a
                        # tradeable opening — stamping it produced the impossible
                        # both-sides=1.0 binaries (#137 opening artifact).
                        sub_has_open = _is_tradeable_opening(prob, sub_has_trading)
                        sub_opening = prob if sub_has_open else None
                        sub_opening_am = over_american if sub_has_open else None
                        sub_opening_at = now if sub_has_open else None

                        # Forward-capture per-outcome volume so the traded/untraded
                        # calibration tag stays populated without a re-backfill.
                        # fo.volume is Integer — cap to avoid overflow on the
                        # multi-billion-dollar markets.
                        sub_vol = (
                            min(int(market.volume), 2_000_000_000)
                            if getattr(market, "volume", None)
                            else None
                        )

                        over_update: dict = {
                            "current_probability": prob,
                            "current_american_odds": over_american,
                            "current_yes_bid": market.best_bid,
                            "current_yes_ask": market.best_ask,
                            "rank": 1,
                            "probability_change_24h": prob - FuturesOutcome.current_probability,
                            "volume": sub_vol,
                            "last_updated": func.now(),
                        }
                        if sub_has_open:
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
                            volume=sub_vol,
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

                            # The Under/No side must open at ITS OWN price, not the
                            # Over/Yes price. Using `sub_opening` (the over prob) here
                            # made every Under outcome store the over-side probability,
                            # so calibration_probability (which falls back to
                            # opening_probability when no snapshot exists) inherited the
                            # wrong side — the #137 poly-Under sign-flip class.
                            sub_under_has_open = _is_tradeable_opening(
                                under_prob, sub_has_trading
                            )
                            sub_under_opening = under_prob if sub_under_has_open else None

                            under_update: dict = {
                                "current_probability": under_prob,
                                "current_american_odds": under_american,
                                "rank": 2,
                                "volume": sub_vol,
                                "last_updated": func.now(),
                            }
                            if sub_under_has_open:
                                under_update["opening_probability"] = func.coalesce(
                                    FuturesOutcome.opening_probability, under_prob
                                )

                            under_stmt = pg_insert(FuturesOutcome).values(
                                market_id=sub_market_id,
                                external_id=f"{market.condition_id}_no",
                                name=under_name,
                                current_probability=under_prob,
                                current_american_odds=under_american,
                                opening_probability=sub_under_opening,
                                opening_american_odds=under_american if sub_has_trading else None,
                                opening_captured_at=sub_opening_at,
                                rank=2,
                                volume=sub_vol,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_=under_update,
                            ).returning(FuturesOutcome.id)
                            under_result = await session.execute(under_stmt)
                            under_outcome_id = under_result.scalar_one()

                            # Write a snapshot for the Under side too (the Over side
                            # gets one above). Without this the Under outcome has no
                            # price history and calibration_probability falls back to
                            # opening_probability — the root of the sign-flip class.
                            under_snap_stmt = pg_insert(FuturesOddsSnapshot).values(
                                outcome_id=under_outcome_id,
                                bookmaker="polymarket",
                                probability=under_prob,
                                american_odds=under_american,
                                captured_at=now,
                            )
                            await session.execute(under_snap_stmt)

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
                        prob = _resolve_market_probability(market)

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
    limit: int = 500,
    fidelity: int = 60,
    interval: str = "max",
    mode: str = "resolved_zero",
):
    """Backfill historical price data for Polymarket outcomes.

    Modes:
      resolved_zero — resolved markets with zero snapshots (calibration).
      open_sparse   — open/active feed-visible markets with no snapshots
                      in the last 7 days (chart quality for Discover).

    Uses the CLOB API /prices-history endpoint (works for both active
    and resolved markets, no API key required).
    """
    import asyncio
    import json as json_module
    from app.models.models import FuturesOddsSnapshot

    stats = {
        "mode": mode,
        "outcomes_processed": 0, "outcomes_skipped": 0,
        "snapshots_created": 0, "events_fetched": 0,
        "api_empty": 0, "errors": [],
    }

    try:
        from app.services.polymarket_api import PolymarketAPIService

        async with get_task_session() as session:
            if mode == "open_sparse":
                result = await session.execute(
                    text("""
                        SELECT fo.id, fo.external_id,
                               fm.external_id AS market_external_id
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
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
                        SELECT fo.id, fo.external_id,
                               COALESCE(
                                   fm.market_metadata->>'polymarket_event_id',
                                   REPLACE(fm.group_id, 'polymarket:', ''),
                                   fm.external_id
                               ) AS market_external_id
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.source = 'polymarket'
                          AND fm.status = 'resolved'
                          AND NOT EXISTS (
                              SELECT 1 FROM futures_odds_snapshots fos
                              WHERE fos.outcome_id = fo.id
                          )
                        ORDER BY fm.updated_at DESC
                        LIMIT :limit
                    """),
                    {"limit": limit},
                )
            outcomes_to_backfill = result.fetchall()

            if not outcomes_to_backfill:
                return {**stats, "status": "nothing_to_backfill"}

            by_event: dict[str, list[dict]] = {}
            for row in outcomes_to_backfill:
                by_event.setdefault(row.market_external_id, []).append({
                    "outcome_id": row.id,
                    "condition_id": row.external_id,
                })

            logger.info(
                "PM price history backfill: %d outcomes across %d events",
                len(outcomes_to_backfill), len(by_event),
            )

            service = PolymarketAPIService()
            try:
                for event_id, outcomes in by_event.items():
                    event_data = await service.get_event_by_id(event_id)
                    if not event_data:
                        stats["errors"].append(f"event_{event_id}: not_found")
                        continue
                    stats["events_fetched"] += 1

                    token_map: dict[str, str] = {}
                    for market in event_data.get("markets", []):
                        cid = market.get("conditionId")
                        clob_ids_raw = market.get("clobTokenIds", "[]")
                        try:
                            clob_ids = json_module.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
                        except (json_module.JSONDecodeError, TypeError):
                            clob_ids = []
                        if cid and clob_ids:
                            token_map[cid] = clob_ids[0]

                    for outcome in outcomes:
                        cid = outcome["condition_id"]
                        token_id = (
                            token_map.get(cid)
                            or token_map.get(cid.rstrip("_yes").rstrip("_no"))
                        )
                        if not token_id:
                            stats["outcomes_skipped"] += 1
                            continue

                        try:
                            history = await service.get_prices_history(
                                token_id=token_id,
                                interval=interval, fidelity=fidelity,
                            )
                        except Exception as e:
                            stats["errors"].append(f"{outcome['outcome_id']}: {str(e)[:80]}")
                            continue

                        if not history:
                            stats["api_empty"] += 1
                            continue

                        from sqlalchemy.dialects.postgresql import insert as pg_insert
                        batch_values = [
                            {
                                "outcome_id": outcome["outcome_id"],
                                "bookmaker": "polymarket",
                                "probability": round(float(pt["p"]), 6),
                                "last_price": round(float(pt["p"]), 4),
                                "captured_at": datetime.fromtimestamp(pt["t"], tz=timezone.utc),
                            }
                            for pt in history
                            if pt.get("t") is not None and pt.get("p") is not None
                        ]

                        if batch_values:
                            for i in range(0, len(batch_values), 100):
                                stmt = pg_insert(FuturesOddsSnapshot).values(batch_values[i:i + 100])
                                await session.execute(stmt.on_conflict_do_nothing())
                            stats["snapshots_created"] += len(batch_values)

                            first_price = batch_values[0]["probability"]
                            if 0 < first_price < 1:
                                await session.execute(
                                    text("""
                                        UPDATE futures_outcomes
                                        SET opening_probability = :price,
                                            opening_source = 'clob_history'
                                        WHERE id = :oid
                                          AND opening_probability IS NULL
                                    """),
                                    {"price": first_price, "oid": outcome["outcome_id"]},
                                )

                        stats["outcomes_processed"] += 1
                        await asyncio.sleep(0.1)

                    await asyncio.sleep(0.1)

                await session.commit()
            finally:
                await service.close()

    except Exception as e:
        logger.error("PM price history backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    return stats


def _is_placeholder_outcome(market) -> bool:
    """
    Detect Polymarket placeholder/reserved-slot markets.

    Polymarket pre-creates empty sub-markets for multi-outcome events before
    the real candidates are announced. These have names like "Player B",
    "Player S", "Player N" and typically:
      - outcomePrices = ["1", "0"] or [] (no real pricing)
      - bestBid = 0 or None (nobody is buying)
      - lastTradePrice = 0 or None (never traded)

    Without this filter, the "1.0" price makes them show up as 100% favorites.
    """
    import re

    # Check question or groupItemTitle for placeholder patterns
    name = market.group_item_title or market.question or ""

    # "Player XX" reserved-slot pattern — one OR MORE uppercase letters.
    # Polymarket switches to 2-letter suffixes ("Player AD", "Player AG") once a
    # field exceeds 26 slots; the original single-letter regex missed those, so
    # ~44 OPEN award/round-leader markets leaked anonymized "Player AD" @ ~0.5
    # across 7 sports (#953). The raw payload exposes no real name for these
    # (groupItemTitle="Player AD", prices=None, bid=0, lastTrade=0), so suppress.
    if re.match(r"^Player\s+[A-Z]+$", name.strip()):
        return True

    # "Will Player XX win/be/..." in the question
    if re.search(r"\bPlayer\s+[A-Z]+\b", market.question or ""):
        return True

    # Additional heuristic: no trading activity AND price is exactly 1.0
    # (real 100% favorites still have lastTradePrice > 0)
    if market.outcome_prices and market.outcome_prices[0] >= 0.995:
        has_trading = (
            (market.best_bid is not None and market.best_bid > 0)
            or (market.last_trade_price is not None and market.last_trade_price > 0)
        )
        if not has_trading:
            return True

    return False


def _resolve_market_probability(market) -> float | None:
    """
    Resolve the Yes-side probability for a Polymarket market.

    Priority: outcomePrices[0] → bid/ask midpoint → lastTradePrice.

    Skips placeholder markets that Polymarket creates as reserved slots
    (e.g., "Player B", "Player S"). These have:
      - empty outcomePrices ([]) or ["1", "0"]
      - bestBid = 0 or None
      - bestAsk = 1 (max spread, no real market-making)
      - lastTradePrice = 0 or None
    Without this filter, the ask-only fallback or the raw 1.0 price would
    set prob = 1.0 (100%), making placeholders look like favorites.
    """
    # Reject known placeholder markets before examining prices
    if _is_placeholder_outcome(market):
        return None

    # #151 cp-capture guard: real price discovery leaves orderbook/trade evidence.
    # A live bid, a real (sub-max) ask, or a last trade all count. Gamma's
    # precomputed ``outcomePrices`` is populated for reserved/untraded slots too,
    # so trusting it blind seeded ~150K resolved poly outcomes near ~0.50 that
    # actually resolve ~0.19 (win-rate census, Queue #151) — dragging poly
    # calibration MCE to 4.01. Require this evidence for MID-RANGE prices only;
    # extreme prices (<=0.05 / >=0.95) can legitimately have a cleared book
    # (near-certain outcomes) and are left permissive.
    has_market = (
        (market.best_bid is not None and market.best_bid > 0)
        or (market.last_trade_price is not None and market.last_trade_price > 0)
        or (market.best_ask is not None and 0 < market.best_ask < 0.99)
    )

    prob = market.outcome_prices[0] if market.outcome_prices else None

    if prob is not None and prob > 0:
        # A mid-range outcomePrice with no orderbook and no trade is a
        # placeholder/synthetic quote, not price discovery — skip the snapshot
        # (it is re-captured next cycle once a real bid/trade appears).
        if 0.05 < prob < 0.95 and not has_market:
            return None
        return prob

    # Midpoint fallback: both bid and ask must be present and positive
    if (market.best_bid is not None and market.best_bid > 0
            and market.best_ask is not None and market.best_ask > 0):
        return (market.best_bid + market.best_ask) / 2

    # Last trade fallback
    if market.last_trade_price is not None and market.last_trade_price > 0:
        return market.last_trade_price

    # Ask-only fallback: reject if ask >= 0.99 (placeholder/no real market)
    if (market.best_ask is not None
            and market.best_ask > 0
            and market.best_ask < 0.99):
        return market.best_ask

    # No reliable price — skip this market
    return None


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


async def _sync_polymarket_resolved_status():
    """Scan closed Polymarket events and update market status to 'resolved'.

    The regular polling task only fetches active events (active=True,
    closed=False). Once a Polymarket event closes, we never see it again
    and the market status stays 'open' in our DB. This blocks all
    downstream pipelines (calibration, winner backfill, snapshot backfill).

    This task is the Polymarket equivalent of Kalshi's settled events
    backfill Phase 1 (gotcha #97).
    """
    import asyncio
    from app.services.polymarket_api import PolymarketAPIService

    import json as json_module

    stats = {
        "events_fetched": 0, "markets_resolved": 0,
        "outcomes_updated": 0,
        "already_resolved": 0, "not_in_db": 0, "errors": [],
    }

    async with get_task_session() as session:
        open_count = await session.execute(
            text("""
                SELECT COUNT(*) FROM futures_markets
                WHERE source = 'polymarket' AND status != 'resolved'
            """)
        )
        total_open = open_count.scalar()
        if total_open == 0:
            logger.info("Polymarket status sync: no open markets, skipping")
            return {**stats, "skipped": True}

    service = PolymarketAPIService()
    try:
        from app.tasks.redis_state import get_redis_client
        _rc = get_redis_client()
        _offset_key = "bainluck:polymarket_sync_offset"
        offset = int(_rc.get(_offset_key) or 0)
        max_events = 100000
        zero_update_pages = 0

        while stats["events_fetched"] < max_events:
            try:
                events_data = await service.get_events(
                    active=False, closed=True,
                    limit=100, offset=offset,
                )
            except Exception as e:
                stats["errors"].append(f"API page {offset}: {e}")
                break

            if not events_data:
                break

            stats["events_fetched"] += len(events_data)

            condition_ids = []
            # Map condition_id -> (yes_price, no_price)
            settlement_prices: dict[str, tuple[float, float | None]] = {}
            for event_data in events_data:
                for market in event_data.get("markets") or []:
                    cid = market.get("conditionId")
                    if cid:
                        condition_ids.append(cid)
                        # Parse outcomePrices — JSON-encoded string array
                        raw_prices = market.get("outcomePrices", "[]")
                        try:
                            if isinstance(raw_prices, str):
                                prices = json_module.loads(raw_prices)
                            elif isinstance(raw_prices, list):
                                prices = raw_prices
                            else:
                                prices = []
                            if prices:
                                yes_price = float(prices[0])
                                no_price = float(prices[1]) if len(prices) > 1 else None
                                settlement_prices[cid] = (yes_price, no_price)
                        except (json_module.JSONDecodeError, ValueError, IndexError):
                            pass

            if condition_ids:
                # Also include _yes/_no suffixed external_ids for sub-market
                # outcome matching and condition_ids as market external_ids
                # for sub-market FuturesMarket status resolution.
                extended_cids = list(condition_ids)
                for cid in condition_ids:
                    extended_cids.append(f"{cid}_yes")
                    extended_cids.append(f"{cid}_no")

                async with get_task_session() as session:
                    # Resolve parent markets via outcome external_id match
                    result = await session.execute(
                        text("""
                            UPDATE futures_markets
                            SET status = 'resolved'
                            WHERE source = 'polymarket'
                              AND status != 'resolved'
                              AND (
                                  id IN (
                                      SELECT fo.market_id
                                      FROM futures_outcomes fo
                                      WHERE fo.external_id = ANY(:cids)
                                  )
                                  OR external_id = ANY(:raw_cids)
                              )
                        """),
                        {"cids": extended_cids, "raw_cids": condition_ids},
                    )
                    page_resolved = result.rowcount

                    # Batch update settlement prices + set is_winner + resolution_source.
                    # All settlement prices with yes_price >= 0.95 are winners;
                    # all with yes_price <= 0.05 are losers.
                    page_outcomes_updated = 0
                    winner_cids = []
                    loser_cids = []
                    for cid, (yes_price, no_price) in settlement_prices.items():
                        if yes_price >= 0.95:
                            winner_cids.extend([cid, f"{cid}_yes"])
                            loser_cids.append(f"{cid}_no")
                        elif yes_price <= 0.05:
                            loser_cids.extend([cid, f"{cid}_yes"])
                            winner_cids.append(f"{cid}_no")

                    if winner_cids:
                        r_w = await session.execute(
                            text("""
                                UPDATE futures_outcomes
                                SET current_probability = 1.0,
                                    is_winner = true,
                                    resolution_source = 'api_settlement'
                                WHERE external_id = ANY(:cids)
                                  AND COALESCE(resolution_source, '') != 'api_settlement'
                            """),
                            {"cids": winner_cids},
                        )
                        page_outcomes_updated += r_w.rowcount

                    if loser_cids:
                        r_l = await session.execute(
                            text("""
                                UPDATE futures_outcomes
                                SET current_probability = 0.0,
                                    is_winner = false,
                                    resolution_source = 'api_settlement'
                                WHERE external_id = ANY(:cids)
                                  AND COALESCE(resolution_source, '') != 'api_settlement'
                            """),
                            {"cids": loser_cids},
                        )
                        page_outcomes_updated += r_l.rowcount

                    if page_resolved > 0 or page_outcomes_updated > 0:
                        await session.commit()
                        stats["markets_resolved"] += page_resolved
                        stats["outcomes_updated"] += page_outcomes_updated
                        zero_update_pages = 0
                    else:
                        zero_update_pages += 1

            if zero_update_pages >= 100:
                # Reset to start for next run
                _rc.delete(_offset_key)
                break

            offset += 100
            _rc.setex(_offset_key, 86400 * 7, str(offset))
            await asyncio.sleep(0.1)

            if stats["events_fetched"] % 5000 == 0:
                logger.info(
                    "Polymarket status sync: %d events, %d resolved, %d outcomes updated",
                    stats["events_fetched"], stats["markets_resolved"],
                    stats["outcomes_updated"],
                )

    except Exception as e:
        stats["errors"].append(f"task_error: {str(e)[:200]}")
    finally:
        await service.close()

    logger.info(
        "Polymarket status sync: %d events fetched, %d markets resolved, %d outcomes updated",
        stats["events_fetched"], stats["markets_resolved"], stats["outcomes_updated"],
    )
    return stats


async def _backfill_polymarket_volume(max_pages: int = 200):
    """Backfill per-outcome volume for Polymarket from the Gamma API.

    Polymarket polling stored only event-level AGGREGATE volume; per-outcome
    (per-condition) volume was never written, so ~all resolved Polymarket
    outcomes have NULL ``volume`` — which blocks the traded/untraded
    calibration tag for that source. This pages CLOSED markets from Gamma
    (each carries ``conditionId`` + ``volume``) high-volume-first and
    bulk-updates ``fo.volume`` keyed on condition_id / _yes / _no.

    VP-efficient + queue-safe: bulk set-based writes (one ``UPDATE ... FROM
    unnest`` per page, not per row), Redis offset cursor (resumable),
    time-boxed at 480s, 429-backoff, write-on-change. Run OUT-OF-BAND (its own
    dyno / low-priority queue) — never contend with live polling. Gotchas: #6
    (commit per batch), #899 (no broad in-memory pull), #36 (don't catch-all —
    distinguish 429 from real errors). fo.volume is an Integer column, so cap
    at ~2B to avoid overflow on the handful of multi-billion-dollar markets
    (the magnitude beyond that is irrelevant to a traded/threshold tag).
    """
    import asyncio
    import time as _time
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.redis_state import get_redis_client

    stats = {"pages": 0, "markets": 0, "rows_updated": 0, "wrapped": False, "errors": []}
    _CAP = 2_000_000_000

    _rc = get_redis_client()
    cursor_key = "bainluck:poly_volume_backfill"
    offset = int(_rc.get(cursor_key) or 0)
    svc = PolymarketAPIService()
    _start = _time.monotonic()

    try:
        for _ in range(max_pages):
            if (_time.monotonic() - _start) > 480:
                break
            try:
                markets = await svc.get_markets(
                    active=None, closed=True, limit=100, offset=offset,
                    order="volume", ascending=False,
                )
            except Exception as e:
                if "429" in str(e):
                    await asyncio.sleep(5)
                    continue
                stats["errors"].append(str(e)[:200])
                break

            if not markets:
                # Reached the end — reset cursor so a later run restarts and
                # picks up newly-resolved markets.
                _rc.delete(cursor_key)
                stats["wrapped"] = True
                break

            offset += len(markets)
            _rc.setex(cursor_key, 86400 * 7, str(offset))
            stats["pages"] += 1

            cids, vols = [], []
            for m in markets:
                cid = m.get("conditionId") or m.get("condition_id")
                vraw = m.get("volume")
                if vraw is None:
                    vraw = m.get("volumeNum")
                if cid and vraw is not None:
                    try:
                        cids.append(cid)
                        vols.append(min(int(float(vraw)), _CAP))
                    except (ValueError, TypeError):
                        pass

            if not cids:
                continue
            stats["markets"] += len(cids)

            async with get_task_session() as session:
                r = await session.execute(
                    text("""
                        UPDATE futures_outcomes fo
                        SET volume = v.vol, last_updated = NOW()
                        FROM unnest(CAST(:cids AS text[]), CAST(:vols AS bigint[])) AS v(cid, vol)
                        WHERE fo.external_id IN (v.cid, v.cid || '_yes', v.cid || '_no')
                          AND fo.volume IS DISTINCT FROM v.vol
                    """),
                    {"cids": cids, "vols": vols},
                )
                stats["rows_updated"] += r.rowcount
                await session.commit()

        logger.info(
            "Polymarket volume backfill: %d pages, %d markets, %d rows updated (wrapped=%s, %d errors)",
            stats["pages"], stats["markets"], stats["rows_updated"],
            stats["wrapped"], len(stats["errors"]),
        )
    except Exception as e:
        stats["errors"].append(str(e)[:200])
        logger.error("Polymarket volume backfill error: %s", e)

    return stats
