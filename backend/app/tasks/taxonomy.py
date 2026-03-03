"""
Taxonomy tag computation Celery task.

Computes deterministic event_tags and market_tags for events and futures markets.
Runs every 2 minutes to keep tags fresh for live events and new futures.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.tasks.base import get_task_session
from app.models.models import Event, FuturesMarket
from app.utils.aggregation import compute_aggregate_probability
from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
from app.utils.highlights import compute_highlight

logger = logging.getLogger(__name__)


async def _update_event_tags_impl(limit: int = 500) -> dict:
    """Compute and persist event_tags for events that need tagging.

    Processes:
    1. Live events (always refresh — signals change in real-time)
    2. Events updated in the last 30 min (catch newly completed games)
    3. Events with null/empty event_tags (backfill)
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)

    async with get_task_session() as session:
        # Query events needing tag updates
        stmt = (
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                or_(
                    # Live events — always refresh
                    Event.status == "live",
                    # Recently updated — catch completions
                    and_(
                        Event.status.in_(["completed", "closed", "scheduled"]),
                        Event.commence_time >= cutoff - timedelta(hours=6),
                    ),
                    # Backfill: missing tags
                    Event.event_tags == None,  # noqa: E711
                    Event.event_tags == [],
                )
            )
            .order_by(
                # Prioritize live, then recent, then backfill
                Event.status.desc(),
                Event.commence_time.desc(),
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        tagged = 0
        errors = 0

        for event in events:
            try:
                tags = _tag_event(event)
                event.event_tags = tags
                tagged += 1
            except Exception:
                logger.exception("Failed to tag event %s", event.id)
                errors += 1

        if tagged > 0:
            await session.commit()

        # --- Futures market tags ---
        futures_tagged = await _update_market_tags(session, limit=limit)

        return {
            "events_tagged": tagged,
            "events_errors": errors,
            "futures_tagged": futures_tagged,
        }


def _tag_event(event: Event) -> list[str]:
    """Compute tags for a single event using current aggregate probability."""
    sport_key = event.sport.key if event.sport else None

    # Get current aggregate probability (not just opening odds)
    current_home_prob = compute_aggregate_probability(event)
    opening_home_prob = (
        float(event.opening_home_probability)
        if event.opening_home_probability is not None
        else None
    )

    # Compute current away probability
    current_away_prob = (1.0 - current_home_prob) if current_home_prob is not None else None
    opening_away_prob = (1.0 - opening_home_prob) if opening_home_prob is not None else None

    # Compute highlight result (provides signal flags like upset, close, line_moving)
    highlight_result = None
    if opening_home_prob is not None and current_home_prob is not None:
        highlight_result = compute_highlight(
            status=event.status,
            commence_time=event.commence_time,
            sport_key=sport_key,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
        )

    # Get raw EI score
    raw_ei = float(event.raw_ei) if event.raw_ei is not None else None

    return compute_event_tags(
        sport_key=sport_key or "",
        status=event.status,
        commence_time=event.commence_time,
        llm_importance=event.llm_importance,
        llm_gender=event.llm_gender,
        llm_level=event.llm_level,
        llm_league=event.llm_league,
        raw_ei=raw_ei,
        broadcast_info=getattr(event, "broadcast_info", None),
        highlight_result=highlight_result,
    )


async def _update_market_tags(session, limit: int = 500) -> int:
    """Compute and persist market_tags for futures markets.

    Processes open markets with null/empty market_tags, plus recently updated.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)

    stmt = (
        select(FuturesMarket)
        .where(
            or_(
                # Backfill: missing tags
                FuturesMarket.market_tags == None,  # noqa: E711
                FuturesMarket.market_tags == [],
                # Recently updated open markets
                and_(
                    FuturesMarket.status == "open",
                    FuturesMarket.updated_at >= cutoff,
                ),
            )
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    markets = result.scalars().all()

    tagged = 0
    for market in markets:
        try:
            tags = compute_market_tags(
                llm_sport_category=market.llm_sport_category,
                llm_league=market.llm_league,
                llm_gender=market.llm_gender,
                llm_level=market.llm_level,
                market_tier=market.market_tier,
                category=market.category,
                status=market.status,
                resolution_date=market.resolution_date,
                source=market.source,
            )
            market.market_tags = tags
            tagged += 1
        except Exception:
            logger.exception("Failed to tag market %s", market.id)

    if tagged > 0:
        await session.commit()

    return tagged


# =============================================================================
# LLM Taxonomy Enrichment (Phase 2)
# =============================================================================


async def _enrich_taxonomy_llm_impl(
    event_limit: int = 50,
    market_limit: int = 30,
) -> dict:
    """Enrich events and futures markets with LLM-generated taxonomy tags.

    Adds tags in 4 dimensions: stakes, narrative, audience, competitive_structure.
    Uses lifecycle-stage caching to avoid re-enriching stable events.

    Priority:
    1. Live events without LLM tags for current stage
    2. Scheduled events starting within 24h
    3. Recently completed events (24h)
    4. Futures markets (tier 1-3, open, no cached taxonomy)
    """
    import asyncio
    from sqlalchemy import text
    from app.models.models import LineMovementAnalysis, FuturesOutcome, Team
    from app.services.llm import enrich_event_taxonomy, enrich_market_taxonomy, is_available
    from app.utils.event_taxonomy import merge_llm_tags, LLM_ENRICHMENT_NAMESPACES

    if not is_available():
        return {"skipped": True, "reason": "LLM unavailable (no OPENAI_API_KEY)"}

    now = datetime.now(timezone.utc)
    stats = {
        "events_enriched": 0,
        "events_skipped_cached": 0,
        "events_errors": 0,
        "markets_enriched": 0,
        "markets_skipped_cached": 0,
        "markets_errors": 0,
    }

    async with get_task_session() as session:
        # ── Fetch candidate events ──
        events = await _fetch_enrichment_candidates(session, event_limit, now)

        # ── Load existing caches in batch ──
        event_ids = [e.id for e in events]
        cache_map = await _load_taxonomy_caches(session, event_ids, "taxonomy_enrichment")

        # ── Batch-fetch championship odds for all teams ──
        champ_odds = await _batch_fetch_championship_odds(session, events)

        # ── Process events in chunks ──
        chunk_size = 10
        for i in range(0, len(events), chunk_size):
            chunk = events[i:i + chunk_size]
            for event in chunk:
                try:
                    stage = _lifecycle_stage(event.status)
                    cached = cache_map.get(event.id)

                    # Check cache: skip if same stage and not expired
                    if cached and not _cache_expired(cached, stage, now):
                        stats["events_skipped_cached"] += 1
                        continue

                    # Assemble context
                    sport_key = event.sport.key if event.sport else ""
                    home_team = event.home_team_name or ""
                    away_team = event.away_team_name or ""

                    opening_prob = (
                        float(event.opening_home_probability)
                        if event.opening_home_probability is not None
                        else None
                    )
                    current_prob = compute_aggregate_probability(event)

                    # Team records + standings
                    home_record, away_record = None, None
                    home_standings, away_standings = None, None
                    if event.home_team_id:
                        home_team_obj = await session.get(Team, event.home_team_id)
                        if home_team_obj:
                            home_record = home_team_obj.current_record
                            if home_team_obj.standings_data:
                                home_standings = _format_standings(home_team_obj.standings_data)
                    if event.away_team_id:
                        away_team_obj = await session.get(Team, event.away_team_id)
                        if away_team_obj:
                            away_record = away_team_obj.current_record
                            if away_team_obj.standings_data:
                                away_standings = _format_standings(away_team_obj.standings_data)

                    # Championship odds
                    home_champ = champ_odds.get(home_team.lower())
                    away_champ = champ_odds.get(away_team.lower())

                    # Injuries from box_score_data
                    injuries = _extract_injuries_summary(event)

                    # Call LLM
                    llm_result = enrich_event_taxonomy(
                        home_team=home_team,
                        away_team=away_team,
                        sport_key=sport_key,
                        status=event.status,
                        llm_importance=event.llm_importance,
                        opening_home_prob=opening_prob,
                        current_home_prob=current_prob,
                        home_record=home_record,
                        away_record=away_record,
                        home_standings=home_standings,
                        away_standings=away_standings,
                        home_champ_odds=home_champ,
                        away_champ_odds=away_champ,
                        broadcast_info=getattr(event, "broadcast_info", None),
                        injuries_summary=injuries,
                    )

                    if llm_result:
                        # Build flat tag list from LLM result
                        llm_tags = []
                        for ns, vals in llm_result.items():
                            for v in vals:
                                llm_tags.append(f"{ns}:{v}")

                        # Merge with existing deterministic tags
                        existing = event.event_tags or []
                        event.event_tags = merge_llm_tags(existing, llm_tags)

                        # Cache the enrichment
                        await _upsert_taxonomy_cache(
                            session, event.id, "taxonomy_enrichment",
                            stage, llm_tags, now,
                        )
                        stats["events_enriched"] += 1
                    else:
                        stats["events_errors"] += 1

                except Exception:
                    logger.exception("Failed to enrich event %s", event.id)
                    stats["events_errors"] += 1

            await session.commit()
            await asyncio.sleep(0.1)  # Rate limit between chunks

        # ── Process futures markets ──
        markets = await _fetch_market_enrichment_candidates(session, market_limit, now)
        market_ids = [m.id for m in markets]
        market_cache_map = await _load_taxonomy_caches(
            session, market_ids, "taxonomy_market", id_field="event_id",
        )

        for i in range(0, len(markets), chunk_size):
            chunk = markets[i:i + chunk_size]
            for market in chunk:
                try:
                    cached = market_cache_map.get(market.id)
                    if cached and not _cache_expired(cached, "open", now):
                        stats["markets_skipped_cached"] += 1
                        continue

                    # Top outcomes
                    top_outcomes = []
                    if market.outcomes:
                        sorted_outcomes = sorted(
                            market.outcomes,
                            key=lambda o: float(o.current_probability or 0),
                            reverse=True,
                        )
                        top_outcomes = [o.name for o in sorted_outcomes[:5] if o.name]

                    resolution = (
                        market.resolution_date.strftime("%Y-%m-%d")
                        if market.resolution_date else None
                    )

                    llm_result = enrich_market_taxonomy(
                        market_name=market.name,
                        llm_sport_category=market.llm_sport_category,
                        market_tier=market.market_tier,
                        top_outcomes=top_outcomes,
                        resolution_date=resolution,
                    )

                    if llm_result:
                        llm_tags = []
                        for ns, vals in llm_result.items():
                            for v in vals:
                                llm_tags.append(f"{ns}:{v}")

                        existing = market.market_tags or []
                        market.market_tags = merge_llm_tags(existing, llm_tags)

                        await _upsert_taxonomy_cache(
                            session, market.id, "taxonomy_market",
                            "open", llm_tags, now,
                        )
                        stats["markets_enriched"] += 1
                    else:
                        stats["markets_errors"] += 1

                except Exception:
                    logger.exception("Failed to enrich market %s", market.id)
                    stats["markets_errors"] += 1

            await session.commit()
            await asyncio.sleep(0.1)

    return stats


# ── Helpers ──────────────────────────────────────────────────────────


def _lifecycle_stage(status: str) -> str:
    """Map event status to a lifecycle stage for caching."""
    if status == "live":
        return "live"
    if status in ("completed", "closed"):
        return "completed"
    return "scheduled"


def _cache_expired(cached: dict, current_stage: str, now: datetime) -> bool:
    """Check whether a cached taxonomy enrichment should be refreshed."""
    cached_stage = cached.get("stage")
    # Stage changed → always re-enrich
    if cached_stage != current_stage:
        return True

    expires_at = cached.get("expires_at")
    if expires_at is None:
        return False  # completed events never expire
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    return now >= expires_at


async def _fetch_enrichment_candidates(session, limit: int, now: datetime):
    """Fetch events that need LLM enrichment, in priority order."""
    cutoff_24h = now - timedelta(hours=24)

    stmt = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            or_(
                # Live events
                Event.status == "live",
                # Scheduled events starting within 24h
                and_(
                    Event.status == "scheduled",
                    Event.commence_time <= now + timedelta(hours=24),
                    Event.commence_time >= now,
                ),
                # Recently completed
                and_(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= cutoff_24h,
                ),
            )
        )
        .order_by(
            # Live first, then upcoming, then completed
            Event.status.desc(),
            Event.commence_time.asc(),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def _fetch_market_enrichment_candidates(session, limit: int, now: datetime):
    """Fetch open futures markets needing LLM enrichment."""
    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.market_tier <= 3,
                FuturesMarket.market_tier == None,  # noqa: E711
            ),
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def _load_taxonomy_caches(
    session, ids: list[int], analysis_type: str, id_field: str = "event_id",
) -> dict[int, dict]:
    """Load existing taxonomy cache entries for a batch of IDs."""
    from app.models.models import LineMovementAnalysis

    if not ids:
        return {}

    stmt = (
        select(LineMovementAnalysis)
        .where(
            LineMovementAnalysis.analysis_type == analysis_type,
            LineMovementAnalysis.event_id.in_(ids),
        )
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    cache = {}
    for row in rows:
        data = row.movement_data or {}
        data["expires_at"] = row.expires_at.isoformat() if row.expires_at else None
        cache[row.event_id] = data
    return cache


async def _upsert_taxonomy_cache(
    session, entity_id: int, analysis_type: str,
    stage: str, llm_tags: list[str], now: datetime,
):
    """Insert or update a taxonomy cache entry in LineMovementAnalysis."""
    from app.models.models import LineMovementAnalysis

    # Compute TTL based on stage
    if stage == "live":
        expires_at = now + timedelta(minutes=30)
    elif stage == "scheduled":
        expires_at = now + timedelta(hours=6)
    else:
        expires_at = None  # completed never expires

    # Check for existing
    stmt = select(LineMovementAnalysis).where(
        LineMovementAnalysis.event_id == entity_id,
        LineMovementAnalysis.analysis_type == analysis_type,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    movement_data = {"stage": stage, "llm_tags": llm_tags}

    if existing:
        existing.movement_data = movement_data
        existing.expires_at = expires_at
        existing.created_at = now
    else:
        entry = LineMovementAnalysis(
            event_id=entity_id,
            analysis_type=analysis_type,
            movement_data=movement_data,
            expires_at=expires_at,
        )
        session.add(entry)


async def _batch_fetch_championship_odds(session, events) -> dict[str, float]:
    """Batch-query championship odds for all teams in the event list.

    Returns dict mapping lowercase team name → probability (0-1).
    """
    from app.models.models import FuturesOutcome, FuturesMarket

    team_names = set()
    for e in events:
        if e.home_team_name:
            team_names.add(e.home_team_name.lower())
        if e.away_team_name:
            team_names.add(e.away_team_name.lower())

    if not team_names:
        return {}

    # Single query: tier-1 outcomes with matching team names
    conditions = [
        func.lower(FuturesOutcome.name).like(f"%{name}%")
        for name in list(team_names)[:50]  # Cap to avoid huge OR
    ]
    if not conditions:
        return {}

    stmt = (
        select(FuturesOutcome.name, FuturesOutcome.current_probability)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.market_tier == 1,
            FuturesMarket.status == "open",
            or_(*conditions),
        )
        .limit(200)
    )
    result = await session.execute(stmt)

    odds_map: dict[str, float] = {}
    for row in result.all():
        name_lower = (row.name or "").lower()
        prob = float(row.current_probability) if row.current_probability else None
        if prob is None:
            continue
        for team in team_names:
            if team in name_lower:
                # Keep highest probability if multiple matches
                if team not in odds_map or prob > odds_map[team]:
                    odds_map[team] = prob
    return odds_map


def _format_standings(standings_data: dict) -> str:
    """Format standings JSONB into a compact string for LLM context."""
    parts = []
    if standings_data.get("position"):
        parts.append(f"#{standings_data['position']}")
    wins = standings_data.get("wins")
    losses = standings_data.get("losses")
    if wins is not None and losses is not None:
        parts.append(f"{wins}-{losses}")
    if standings_data.get("conference"):
        parts.append(standings_data["conference"])
    if standings_data.get("division"):
        parts.append(standings_data["division"])
    return " ".join(parts) if parts else ""


def _extract_injuries_summary(event) -> Optional[str]:
    """Extract injury info from box_score_data JSONB for LLM context."""
    bsd = getattr(event, "box_score_data", None)
    if not bsd or not isinstance(bsd, dict):
        return None

    injuries = bsd.get("injuries")
    if not injuries:
        return None

    if isinstance(injuries, list):
        # Limit to first 5 injuries for token efficiency
        summaries = []
        for inj in injuries[:5]:
            if isinstance(inj, dict):
                name = inj.get("name", "Unknown")
                status = inj.get("status", "")
                summaries.append(f"{name} ({status})" if status else name)
            elif isinstance(inj, str):
                summaries.append(inj)
        return "; ".join(summaries) if summaries else None

    return str(injuries)[:200] if injuries else None
