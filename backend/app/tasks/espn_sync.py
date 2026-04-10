"""
ESPN live sync, metadata enrichment, and team logo backfill tasks.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, distinct, and_, or_
from sqlalchemy.orm import selectinload

from app.models import Event, Sport
from app.tasks.base import get_task_session, run_async
from app.tasks.config import ESPN_SPORT_MAPPING
from app.utils.name_normalization import (
    token_overlap_score as _team_name_match_score,
    names_match as _canonical_names_match,
    normalize_name as _normalize_name_canonical,
)

logger = logging.getLogger(__name__)

# Pre-game status_detail strings like "Wed, March 25th at 10:00 PM EDT"
# should not be stored as period values in game_state.
_PREGAME_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)


def _sanitize_period(status_detail: str | None) -> str | None:
    """Return status_detail if it looks like a game period, else None."""
    if not status_detail:
        return None
    if _PREGAME_DATE_RE.search(status_detail):
        return None
    return status_detail


async def _enrich_events_metadata(limit: int = 50):
    """Async implementation of enrich_events_metadata."""
    from app.services import llm
    from app.models.models import Event
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stats = {
        "processed": 0,
        "enriched": 0,
        "errors": 0,
        "remaining": 0,
        "llm_available": llm.is_available(),
    }

    try:
        async with get_task_session() as session:
            # Find events without metadata (prioritize recent events)
            result = await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    Event.llm_gender.is_(None),
                    Event.llm_level.is_(None),
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            events = result.scalars().all()

            if not events:
                remaining_result = await session.execute(
                    select(Event.id).where(
                        Event.llm_gender.is_(None),
                        Event.llm_level.is_(None),
                    )
                )
                stats["remaining"] = len(remaining_result.all())
                return stats

            for event in events:
                try:
                    sport_key = event.sport.key if event.sport else None
                    text = f"{event.away_team_name} at {event.home_team_name}"

                    # Classify using heuristics + LLM fallback
                    event.llm_gender = llm.classify_gender_cached(text, sport_key)
                    event.llm_level = llm.classify_level_cached(text, sport_key)
                    event.llm_league = llm.classify_league_cached(text, sport_key)
                    event.llm_importance = llm.classify_importance_cached(text, sport_key)

                    stats["enriched"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    if stats["errors"] <= 5:
                        print(f"Error enriching event {event.id}: {e}")

                stats["processed"] += 1

            # Count remaining
            remaining_result = await session.execute(
                select(Event.id).where(
                    Event.llm_gender.is_(None),
                    Event.llm_level.is_(None),
                )
            )
            stats["remaining"] = len(remaining_result.all())

    except Exception as e:
        print(f"Enrichment task error: {e}")
        stats["errors"] += 1

    return stats


async def _sync_espn_live_events():
    """Async implementation of sync_espn_live_events."""
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport, Team, ESPNSnapshot

    stats = {
        "sports_checked": 0,
        "sports_with_live": 0,
        "events_synced": 0,
        "events_updated": 0,
        "errors": [],
    }

    def names_match(our_names: list, espn_name: str) -> bool:
        """Check if any of our name variations match an ESPN name.

        Delegates to canonical names_match() from name_normalization.py.
        """
        if not espn_name:
            return False
        return any(_canonical_names_match(name, espn_name) for name in our_names if name)

    async def upsert_team(session, team_name, espn_team, sport_id):
        """Create or update a Team record with ESPN enrichment data.

        Returns the Team record (for linking back to events), or None.
        """
        if not espn_team:
            return None
        team_result = await session.execute(
            select(Team).where(
                Team.name == team_name,
                Team.sport_id == sport_id,
            )
        )
        team = team_result.scalar_one_or_none()

        if not team:
            team = Team(
                name=team_name,
                sport_id=sport_id,
            )
            session.add(team)
            await session.flush()  # Assign team.id for FK linking

        # Update ESPN fields — but guard against overwriting correct data
        # with mismatched ESPN data (e.g., from a wrong event-level match).
        # If the team already has an espn_id that differs from this ESPN team,
        # don't apply any ESPN data — the existing ID is likely correct.
        if team.espn_id and team.espn_id != espn_team.espn_id:
            # ESPN ID mismatch — skip all ESPN data updates
            stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
            return team

        team.espn_id = espn_team.espn_id
        if espn_team.abbreviation:
            team.abbreviation = espn_team.abbreviation
        if espn_team.primary_color:
            color = espn_team.primary_color
            if not color.startswith("#"):
                color = f"#{color}"
            team.primary_color = color
        if espn_team.secondary_color:
            color = espn_team.secondary_color
            if not color.startswith("#"):
                color = f"#{color}"
            team.secondary_color = color
        if espn_team.logo_url:
            team.logo_url_small = espn_team.logo_url
            team.logo_url_large = espn_team.logo_url
        if espn_team.record:
            team.current_record = espn_team.record
        if espn_team.location:
            team.location = espn_team.location

        # Store alternate names for lookup
        alt_names = set()
        for n in [espn_team.display_name, espn_team.short_name, espn_team.nickname, espn_team.name]:
            if n and n != team_name:
                alt_names.add(n)
        if alt_names:
            existing = set(team.alternate_names or [])
            team.alternate_names = list(existing | alt_names)

        stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
        return team

    def get_event_name_variations(event):
        """Get all name variations for an event's teams."""
        home_names = [event.home_team_name]
        away_names = [event.away_team_name]
        if event.home_team_normalized:
            home_names.append(event.home_team_normalized)
        if event.away_team_normalized:
            away_names.append(event.away_team_normalized)
        if event.home_team_alt_names:
            home_names.extend(event.home_team_alt_names)
        if event.away_team_alt_names:
            away_names.extend(event.away_team_alt_names)
        return home_names, away_names

    def get_espn_name_variants(espn_team):
        """Get all name variants from an ESPN team object for matching."""
        variants = []
        for name in [espn_team.display_name, espn_team.short_name, espn_team.name, espn_team.location]:
            if name and name not in variants:
                variants.append(name)
        return variants

    def espn_names_match(our_names, espn_team):
        """Check if any of our name variations match any ESPN name variant."""
        for espn_name in get_espn_name_variants(espn_team):
            if names_match(our_names, espn_name):
                return True
        return False

    try:
        async with get_task_session() as session:
            # Find sports with live games
            live_sports_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(Event.status == "live")
            )
            live_sport_keys = [row[0] for row in live_sports_result.all()]

            # Also include sports with recently-completed events to capture
            # final win probability snapshots. The Odds API can mark events as
            # "completed" before ESPN provides its final win probability data.
            # Use commence_time to find games that started recently (last 6h).
            recently_completed_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
            recent_completed_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= recently_completed_cutoff,
                )
            )
            recently_completed_keys = [row[0] for row in recent_completed_result.all()]
            # Merge into live keys so we fetch ESPN data for them too
            for k in recently_completed_keys:
                if k not in live_sport_keys:
                    live_sport_keys.append(k)

            # Also include sports with "scheduled" events that have already
            # commenced — odds polling may be slow to mark them "live", so
            # ESPN sync should pick them up proactively.
            started_cutoff = datetime.now(timezone.utc) - timedelta(hours=5)
            started_scheduled_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(
                    Event.status == "scheduled",
                    Event.commence_time <= datetime.now(timezone.utc),
                    Event.commence_time >= started_cutoff,
                )
            )
            for row in started_scheduled_result.all():
                if row[0] not in live_sport_keys:
                    live_sport_keys.append(row[0])

            if not live_sport_keys:
                return {"status": "no_live_games", **stats}

            stats["sports_with_live"] = len(live_sport_keys)

            # Also find sports with scheduled games for team data pre-population
            scheduled_sports_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(Event.status == "scheduled")
            )
            scheduled_sport_keys = [row[0] for row in scheduled_sports_result.all()]

            # Collect all ESPN-mapped sport keys to fetch
            all_fetch_keys = set()
            for k in live_sport_keys:
                if k in ESPN_SPORT_MAPPING:
                    all_fetch_keys.add(k)
            for k in scheduled_sport_keys:
                if k in ESPN_SPORT_MAPPING:
                    all_fetch_keys.add(k)

            if not all_fetch_keys:
                return {"status": "no_espn_mapped_sports", **stats}

            # Fetch all ESPN scoreboards
            espn = ESPNAPIService()
            espn_data = {}
            try:
                for key in all_fetch_keys:
                    try:
                        events = await espn.get_scoreboard(key)
                        espn_data[key] = events or []
                    except Exception as e:
                        stats["errors"].append(f"espn_fetch_{key}: {str(e)}")
                        espn_data[key] = []
            finally:
                await espn.close()

            # Process live events (and recently-completed for final snapshots)
            for sport_key in live_sport_keys:
                stats["sports_checked"] += 1

                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue

                try:
                    events_result = await session.execute(
                        select(Event)
                        .options(selectinload(Event.sport))
                        .where(
                            Event.sport.has(key=sport_key),
                            or_(
                                Event.status == "live",
                                # Include recently-completed events so we capture
                                # final win probability data from ESPN
                                and_(
                                    Event.status.in_(["completed", "closed"]),
                                    Event.commence_time >= recently_completed_cutoff,
                                ),
                                # Include scheduled events that have already started
                                # (odds polling may be slow to flip status to "live")
                                and_(
                                    Event.status == "scheduled",
                                    Event.commence_time <= datetime.now(timezone.utc),
                                    Event.commence_time >= started_cutoff,
                                ),
                            ),
                        )
                    )
                    our_events = events_result.scalars().all()

                    # Build ESPN ID lookup for fast matching
                    espn_by_id = {}
                    for ee in espn_events:
                        if ee.espn_id:
                            espn_by_id[ee.espn_id] = ee

                    for event in our_events:
                        # Multi-signal matching: ESPN ID first, then name, then time
                        matched_espn = None
                        match_method = None

                        # 1. Match by ESPN ID (most reliable — set during scheduled sync)
                        if event.espn_id and event.espn_id in espn_by_id:
                            matched_espn = espn_by_id[event.espn_id]
                            match_method = "espn_id"

                        # 2. Fall back to name matching
                        if not matched_espn:
                            home_names, away_names = get_event_name_variations(event)
                            for ee in espn_events:
                                if not ee.home_team or not ee.away_team:
                                    continue
                                if espn_names_match(home_names, ee.home_team) and espn_names_match(away_names, ee.away_team):
                                    matched_espn = ee
                                    match_method = "name"
                                    break

                        # 3. Commence_time proximity fallback REMOVED
                        # Previously matched by time proximity when exactly 1 ESPN
                        # candidate was within 6 hours. This caused logo contamination
                        # for college sports — a single-candidate time match assigned
                        # wrong team data (same issue documented in the scheduled pass
                        # at lines 609-616 where 29 teams got Purdue's ESPN ID/logo).
                        # Name matching (step 2) is sufficient; ESPN ID (step 1)
                        # handles teams that have already been correctly linked.

                        if not matched_espn:
                            stats["events_unmatched"] = stats.get("events_unmatched", 0) + 1
                            continue

                        ee = matched_espn
                        stats["events_synced"] += 1
                        stats[f"match_{match_method}"] = stats.get(f"match_{match_method}", 0) + 1
                        changed = False

                        # Upsert team records with ESPN data (colors, logos)
                        # and link team_ids on the event for personalization filtering
                        home_team = await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                        away_team = await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)
                        if home_team and event.home_team_id != home_team.id:
                            event.home_team_id = home_team.id
                            changed = True
                        if away_team and event.away_team_id != away_team.id:
                            event.away_team_id = away_team.id
                            changed = True

                        # Register ESPN team identities for indexed lookups
                        from app.services.team_identity import team_identity_service
                        if home_team and ee.home_team:
                            await team_identity_service.register_team_identity(
                                session, home_team.id, "espn", sport_key,
                                source_id=str(ee.home_team.espn_id) if ee.home_team.espn_id else None,
                                source_name=ee.home_team.display_name or ee.home_team.name,
                            )
                        if away_team and ee.away_team:
                            await team_identity_service.register_team_identity(
                                session, away_team.id, "espn", sport_key,
                                source_id=str(ee.away_team.espn_id) if ee.away_team.espn_id else None,
                                source_name=ee.away_team.display_name or ee.away_team.name,
                            )

                        # Update ESPN ID
                        if ee.espn_id and event.espn_id != ee.espn_id:
                            event.espn_id = ee.espn_id
                            changed = True

                        # Correct commence_time from ESPN if significantly different
                        # The Odds API occasionally returns local times as UTC
                        # Skip if StatPal set the commence_time (more reliable source)
                        if ee.date and event.commence_time:
                            time_diff = abs((ee.date - event.commence_time).total_seconds())
                            if time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal":  # > 5 minutes difference
                                logger.info(
                                    f"ESPN: Correcting commence_time for event {event.id} "
                                    f"({event.home_team_name} vs {event.away_team_name}): "
                                    f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                    f"(diff: {time_diff/3600:.1f}h)"
                                )
                                event.commence_time = ee.date
                                event.commence_time_source = "espn"
                                changed = True

                        # Update game clock
                        if ee.clock and event.game_clock != ee.clock:
                            event.game_clock = ee.clock
                            changed = True

                        # Update period
                        if ee.status_detail and event.period != ee.status_detail:
                            event.period = ee.status_detail
                            changed = True

                        # Update scores
                        if ee.home_score is not None and event.home_score != ee.home_score:
                            event.home_score = ee.home_score
                            changed = True
                        if ee.away_score is not None and event.away_score != ee.away_score:
                            event.away_score = ee.away_score
                            changed = True

                        # Update broadcast info
                        if ee.broadcasts:
                            broadcast_str = ", ".join(ee.broadcasts[:3])
                            if event.broadcast_info != broadcast_str:
                                event.broadcast_info = broadcast_str
                                changed = True

                        # Update importance from ESPN season type
                        # (more reliable than LLM text classification)
                        if ee.season_type is not None:
                            espn_importance = {1: "exhibition", 2: "regular_season", 3: "playoff"}.get(ee.season_type)
                            if espn_importance and event.llm_importance != espn_importance:
                                # Don't downgrade "championship" to "playoff" —
                                # LLM text match is more specific
                                if not (event.llm_importance == "championship" and espn_importance == "playoff"):
                                    event.llm_importance = espn_importance
                                    changed = True

                        # Update ESPN win probability and save snapshot
                        if ee.home_win_probability is not None:
                            event.espn_win_prob_home = ee.home_win_probability
                            sources = event.win_probability_sources or {}
                            sources["espn"] = ee.home_win_probability
                            event.win_probability_sources = sources
                            changed = True

                            snapshot = ESPNSnapshot(
                                event_id=event.id,
                                home_win_probability=ee.home_win_probability,
                                away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                                home_score=ee.home_score,
                                away_score=ee.away_score,
                                game_clock=ee.clock,
                                period=ee.status_detail,
                            )
                            session.add(snapshot)
                            stats["snapshots_created"] = stats.get("snapshots_created", 0) + 1

                            # Also write ESPN to generic win_prob_snapshots table
                            try:
                                from app.tasks.snapshots import _create_or_update_win_prob_snapshot
                                espn_wp_snap, is_new = await _create_or_update_win_prob_snapshot(
                                    session,
                                    event_id=event.id,
                                    source="espn",
                                    home_win_probability=ee.home_win_probability,
                                    away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                                    game_state={
                                        "clock": ee.clock,
                                        "period": _sanitize_period(ee.status_detail) or (str(ee.period) if ee.period else None),
                                        "home_score": ee.home_score,
                                        "away_score": ee.away_score,
                                    },
                                )
                                if is_new:
                                    session.add(espn_wp_snap)
                            except Exception:
                                pass  # Table may not exist yet

                        # Compute statistical model win probability (live games only)
                        # Baseball doesn't have a clock — only needs period (inning)
                        has_game_progress = ee.clock or sport_key.startswith("baseball_")
                        if ee.status == "in" and ee.home_score is not None and ee.away_score is not None and has_game_progress:
                            try:
                                from app.utils.win_probability import compute_statistical_win_prob

                                # Use opening spread if available
                                pregame_spread = None
                                if event.opening_home_spread is not None:
                                    pregame_spread = float(event.opening_home_spread)

                                # Prefer numeric period for reliability
                                period_str = _sanitize_period(ee.status_detail)
                                if ee.period and not period_str:
                                    period_str = str(ee.period)

                                stat_wp = compute_statistical_win_prob(
                                    home_score=ee.home_score,
                                    away_score=ee.away_score,
                                    clock=ee.clock,
                                    period=period_str,
                                    sport_key=sport_key,
                                    pregame_spread=pregame_spread,
                                )
                                if stat_wp is not None:
                                    sources = event.win_probability_sources or {}
                                    sources["stat_model"] = round(stat_wp, 4)
                                    event.win_probability_sources = sources
                                    changed = True

                                    from app.tasks.snapshots import _create_or_update_win_prob_snapshot
                                    stat_snap, is_new = await _create_or_update_win_prob_snapshot(
                                        session,
                                        event_id=event.id,
                                        source="stat_model",
                                        home_win_probability=round(stat_wp, 4),
                                        away_win_probability=round(1.0 - stat_wp, 4),
                                        game_state={
                                            "clock": ee.clock,
                                            "period": period_str,
                                            "home_score": ee.home_score,
                                            "away_score": ee.away_score,
                                            "pregame_spread": pregame_spread,
                                            "time_source": "espn",
                                        },
                                    )
                                    if is_new:
                                        session.add(stat_snap)
                                    stats["stat_model_computed"] = stats.get("stat_model_computed", 0) + 1
                                else:
                                    logger.warning(
                                        f"stat_model returned None for event {event.id} "
                                        f"(sport={sport_key}, clock={ee.clock!r}, period={ee.status_detail!r}, "
                                        f"score={ee.home_score}-{ee.away_score})"
                                    )
                            except Exception as e:
                                logger.error(f"stat_model error for event {event.id}: {e}")
                        elif ee.status == "in":
                            # Only track missing data for live games
                            if ee.home_score is None or ee.away_score is None:
                                stats["stat_model_no_score"] = stats.get("stat_model_no_score", 0) + 1
                            elif not ee.clock:
                                stats["stat_model_no_clock"] = stats.get("stat_model_no_clock", 0) + 1

                        if changed:
                            stats["events_updated"] += 1

                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")

            # Second pass: sync team data for scheduled events
            # (so colors/logos appear before games go live, and ESPN IDs
            # are set for reliable matching when the game starts)
            for sport_key in scheduled_sport_keys:
                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue

                try:
                    events_result = await session.execute(
                        select(Event)
                        .options(selectinload(Event.sport))
                        .where(
                            Event.sport.has(key=sport_key),
                            Event.status == "scheduled",
                        )
                    )
                    scheduled_events = events_result.scalars().all()

                    # Build ESPN ID lookup for scheduled pass too
                    espn_by_id_sched = {}
                    for ee in espn_events:
                        if ee.espn_id:
                            espn_by_id_sched[ee.espn_id] = ee

                    for event in scheduled_events:
                        matched_espn = None

                        # 1. Match by ESPN ID (most reliable)
                        if event.espn_id and event.espn_id in espn_by_id_sched:
                            matched_espn = espn_by_id_sched[event.espn_id]

                        # 2. Fall back to name matching (using all ESPN name variants)
                        if not matched_espn:
                            home_names, away_names = get_event_name_variations(event)
                            for ee in espn_events:
                                if not ee.home_team or not ee.away_team:
                                    continue
                                if espn_names_match(home_names, ee.home_team) and espn_names_match(away_names, ee.away_team):
                                    matched_espn = ee
                                    break

                        # 3. Commence_time proximity fallback REMOVED
                        # Previously matched by time proximity when exactly 1 ESPN
                        # candidate was within 6 hours. This caused massive logo
                        # contamination for college sports where ESPN returns all
                        # games — a single-candidate time match assigned wrong team
                        # data (e.g., 29 teams got Purdue's ESPN ID/logo).
                        # Name matching (step 2) is sufficient; ESPN ID (step 1)
                        # handles teams that have already been correctly linked.

                        if not matched_espn:
                            continue

                        ee = matched_espn
                        home_team = await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                        away_team = await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)
                        if home_team and event.home_team_id != home_team.id:
                            event.home_team_id = home_team.id
                        if away_team and event.away_team_id != away_team.id:
                            event.away_team_id = away_team.id

                        # Register ESPN team identities for indexed lookups
                        from app.services.team_identity import team_identity_service
                        if home_team and ee.home_team:
                            await team_identity_service.register_team_identity(
                                session, home_team.id, "espn", sport_key,
                                source_id=str(ee.home_team.espn_id) if ee.home_team.espn_id else None,
                                source_name=ee.home_team.display_name or ee.home_team.name,
                            )
                        if away_team and ee.away_team:
                            await team_identity_service.register_team_identity(
                                session, away_team.id, "espn", sport_key,
                                source_id=str(ee.away_team.espn_id) if ee.away_team.espn_id else None,
                                source_name=ee.away_team.display_name or ee.away_team.name,
                            )

                        # Correct commence_time from ESPN if significantly different
                        # Skip if StatPal set the commence_time (more reliable source)
                        if ee.date and event.commence_time:
                            time_diff = abs((ee.date - event.commence_time).total_seconds())
                            if time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal":  # > 5 minutes
                                logger.info(
                                    f"ESPN: Correcting commence_time for scheduled event {event.id} "
                                    f"({event.home_team_name} vs {event.away_team_name}): "
                                    f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                    f"(diff: {time_diff/3600:.1f}h)"
                                )
                                event.commence_time = ee.date
                                event.commence_time_source = "espn"
                        if ee.broadcasts and not event.broadcast_info:
                            event.broadcast_info = ", ".join(ee.broadcasts)
                        if ee.espn_id and not event.espn_id:
                            event.espn_id = ee.espn_id
                            stats["scheduled_espn_ids_set"] = stats.get("scheduled_espn_ids_set", 0) + 1

                        # Update importance from ESPN season type for scheduled events too
                        if ee.season_type is not None:
                            espn_importance = {1: "exhibition", 2: "regular_season", 3: "playoff"}.get(ee.season_type)
                            if espn_importance and event.llm_importance != espn_importance:
                                if not (event.llm_importance == "championship" and espn_importance == "playoff"):
                                    event.llm_importance = espn_importance

                except Exception as e:
                    stats["errors"].append(f"scheduled_{sport_key}: {str(e)}")

            # Third pass: fetch box scores for recently completed events
            # that have an ESPN ID but no box_score_data yet.
            # This catches games that just finished during the previous sync cycle.
            try:
                from datetime import timedelta
                recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
                completed_result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        Event.status.in_(["completed", "closed"]),
                        Event.espn_id.isnot(None),
                        Event.box_score_data.is_(None),
                        Event.commence_time >= recent_cutoff,
                    )
                    .order_by(Event.commence_time.desc())
                    .limit(10)  # Small batch per sync cycle
                )
                box_events = completed_result.scalars().all()

                if box_events:
                    box_espn = ESPNAPIService()
                    try:
                        for event in box_events:
                            sport_key = event.sport.key if event.sport else None
                            if not sport_key or sport_key not in ESPN_SPORT_MAPPING:
                                continue
                            try:
                                context = await box_espn.get_event_context(sport_key, event.espn_id)
                                box_score = context.get("box_score", {})
                                scoring_plays = context.get("scoring_plays", [])
                                now_str = datetime.now(timezone.utc).isoformat()

                                if box_score or scoring_plays:
                                    event.box_score_data = {
                                        "source": "espn",
                                        "fetched_at": now_str,
                                        "players": box_score,
                                        "scoring_plays": scoring_plays,
                                    }
                                    stats["box_scores_fetched"] = stats.get("box_scores_fetched", 0) + 1
                                else:
                                    event.box_score_data = {
                                        "source": "espn",
                                        "error": "not_available",
                                        "fetched_at": now_str,
                                    }
                            except Exception as e:
                                logger.error(f"Box score fetch error for event {event.id}: {e}")
                    finally:
                        await box_espn.close()
            except Exception as e:
                stats["errors"].append(f"box_score_pass: {str(e)}")

            # Fourth pass: update box scores for live events (every 2 minutes)
            try:
                stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
                live_box_result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        Event.status == "live",
                        Event.espn_id.isnot(None),
                    )
                    .order_by(Event.commence_time.desc())
                    .limit(10)
                )
                live_box_events = live_box_result.scalars().all()

                live_to_fetch = []
                for ev in live_box_events:
                    if ev.box_score_data is None:
                        live_to_fetch.append(ev)
                    elif ev.box_score_data.get("live"):
                        fetched_str = ev.box_score_data.get("fetched_at")
                        if fetched_str:
                            try:
                                fetched_at = datetime.fromisoformat(fetched_str)
                                if fetched_at < stale_cutoff:
                                    live_to_fetch.append(ev)
                            except (ValueError, TypeError):
                                live_to_fetch.append(ev)
                        else:
                            live_to_fetch.append(ev)

                if live_to_fetch:
                    live_espn = ESPNAPIService()
                    try:
                        for ev in live_to_fetch:
                            sport_key = ev.sport.key if ev.sport else None
                            if not sport_key or sport_key not in ESPN_SPORT_MAPPING:
                                continue
                            try:
                                context = await live_espn.get_event_context(sport_key, ev.espn_id)
                                box_data = context.get("box_score", {})
                                scoring_plays = context.get("scoring_plays", [])
                                now_str = datetime.now(timezone.utc).isoformat()
                                if box_data or scoring_plays:
                                    ev.box_score_data = {
                                        "source": "espn",
                                        "fetched_at": now_str,
                                        "players": box_data,
                                        "scoring_plays": scoring_plays,
                                        "live": True,
                                    }
                                    stats["live_box_scores_fetched"] = (
                                        stats.get("live_box_scores_fetched", 0) + 1
                                    )
                            except Exception as e:
                                logger.error(f"Live box score error for event {ev.id}: {e}")
                    finally:
                        await live_espn.close()
            except Exception as e:
                stats["errors"].append(f"live_box_score_pass: {str(e)}")

            # Fifth pass: backfill scores for recently completed events
            # that have NO scores and NO espn_id. This catches niche sports
            # (lacrosse, etc.) that were added to ESPN_SPORT_MAPPING after
            # the events completed — they never went through the live sync.
            try:
                from datetime import timedelta
                score_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                missing_scores_result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        Event.status.in_(["completed", "closed"]),
                        Event.home_score.is_(None),
                        Event.away_score.is_(None),
                        Event.commence_time >= score_cutoff,
                    )
                    .order_by(Event.commence_time.desc())
                    .limit(20)
                )
                missing_score_events = missing_scores_result.scalars().all()

                # Group by sport key to batch ESPN fetches
                events_by_sport: dict[str, list] = {}
                for ev in missing_score_events:
                    sk = ev.sport.key if ev.sport else None
                    if sk and sk in ESPN_SPORT_MAPPING:
                        events_by_sport.setdefault(sk, []).append(ev)

                if events_by_sport:
                    score_espn = ESPNAPIService()
                    try:
                        for sport_key, events_list in events_by_sport.items():
                            try:
                                # Fetch scoreboard with date range covering these events
                                from datetime import timedelta
                                dates = set()
                                for ev in events_list:
                                    if ev.commence_time:
                                        dates.add(ev.commence_time.strftime("%Y%m%d"))
                                for date_str in dates:
                                    espn_events = await score_espn.get_scoreboard(sport_key, date=date_str)
                                    if not espn_events:
                                        continue
                                    for ev in events_list:
                                        if ev.commence_time and ev.commence_time.strftime("%Y%m%d") != date_str:
                                            continue
                                        if ev.home_score is not None:
                                            continue  # Already got scores
                                        home_names, away_names = get_event_name_variations(ev)
                                        for ee in espn_events:
                                            if not ee.home_team or not ee.away_team:
                                                continue
                                            espn_home = ee.home_team.display_name or ee.home_team.name or ""
                                            espn_away = ee.away_team.display_name or ee.away_team.name or ""
                                            if names_match(home_names, espn_home) and names_match(away_names, espn_away):
                                                if ee.home_score is not None:
                                                    ev.home_score = ee.home_score
                                                    ev.away_score = ee.away_score
                                                    if ee.status_detail:
                                                        ev.period = ee.status_detail
                                                    if ee.espn_id and not ev.espn_id:
                                                        ev.espn_id = ee.espn_id
                                                    # Upsert teams for colors/logos
                                                    home_team = await upsert_team(session, ev.home_team_name, ee.home_team, ev.sport_id)
                                                    away_team = await upsert_team(session, ev.away_team_name, ee.away_team, ev.sport_id)
                                                    if home_team and ev.home_team_id != home_team.id:
                                                        ev.home_team_id = home_team.id
                                                    if away_team and ev.away_team_id != away_team.id:
                                                        ev.away_team_id = away_team.id
                                                    stats["scores_backfilled"] = stats.get("scores_backfilled", 0) + 1
                                                    logger.info(
                                                        f"ESPN: Backfilled scores for event {ev.id} "
                                                        f"({ev.away_team_name} @ {ev.home_team_name}): "
                                                        f"{ee.away_score}-{ee.home_score}"
                                                    )
                                                break
                            except Exception as e:
                                stats["errors"].append(f"score_backfill_{sport_key}: {str(e)}")
                    finally:
                        await score_espn.close()
            except Exception as e:
                stats["errors"].append(f"score_backfill_pass: {str(e)}")

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        print(f"ESPN sync task error: {e}\n{traceback.format_exc()}")

    return stats


async def _backfill_team_logos():
    """Async implementation of backfill_team_logos."""
    from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP
    from app.models.models import Team, Sport
    from sqlalchemy import select

    stats = {
        "sports_checked": 0,
        "teams_fetched": 0,
        "teams_updated": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find teams missing logos, grouped by sport
            result = await session.execute(
                select(Team, Sport.key)
                .join(Sport)
                .where(Team.logo_url_small.is_(None))
            )
            teams_missing_logos = result.all()

            if not teams_missing_logos:
                return {"status": "no_teams_missing_logos", **stats}

            # Group by sport key
            sport_keys_needed = set()
            teams_by_sport = {}
            for team, sport_key in teams_missing_logos:
                if sport_key in SPORT_LEAGUE_MAP:
                    sport_keys_needed.add(sport_key)
                    teams_by_sport.setdefault(sport_key, []).append(team)

            if not sport_keys_needed:
                return {"status": "no_espn_mapped_sports_need_logos", **stats}

            # Fetch teams from ESPN for each sport
            espn = ESPNAPIService()
            try:
                for sport_key in sport_keys_needed:
                    stats["sports_checked"] += 1
                    try:
                        espn_teams = await espn.get_teams(sport_key)
                        stats["teams_fetched"] += len(espn_teams)
                    except Exception as e:
                        stats["errors"].append(f"fetch_{sport_key}: {str(e)}")
                        continue

                    if not espn_teams:
                        continue

                    # Build lookup of ESPN teams by various name forms
                    # Skip et.name (mascot-only like "Buckeyes", "Bulldogs") and
                    # et.nickname (often same as mascot) — these cause false positives
                    # when multiple teams share a mascot.
                    espn_by_id = {}
                    espn_by_name = {}
                    for et in espn_teams:
                        espn_by_id[et.espn_id] = et
                        for name in [et.display_name, et.short_name]:
                            if name and len(name) >= 4:
                                espn_by_name[name.lower()] = et

                    # Try to match our teams to ESPN teams
                    for team in teams_by_sport.get(sport_key, []):
                        matched_espn = None
                        match_was_exact = False

                        # Match by ESPN ID first (most reliable)
                        if team.espn_id and team.espn_id in espn_by_id:
                            matched_espn = espn_by_id[team.espn_id]
                            match_was_exact = True
                        else:
                            # Match by name
                            names_to_check = [team.name]
                            if team.alternate_names:
                                names_to_check.extend(team.alternate_names)

                            for name in names_to_check:
                                name_lower = name.lower()
                                # Exact match in dict (fast path)
                                if name_lower in espn_by_name:
                                    matched_espn = espn_by_name[name_lower]
                                    match_was_exact = True
                                    break
                                # Token-overlap scoring (replaces substring matching)
                                best_score = 0.0
                                best_et = None
                                for espn_name, et in espn_by_name.items():
                                    score = _team_name_match_score(name, espn_name)
                                    if score > best_score:
                                        best_score = score
                                        best_et = et
                                if best_score > 0.5:
                                    matched_espn = best_et
                                    match_was_exact = False
                                    break

                        if matched_espn and matched_espn.logo_url:
                            team.logo_url_small = matched_espn.logo_url
                            team.logo_url_large = matched_espn.logo_url
                            # Only set espn_id from exact or ID matches, not fuzzy scoring
                            if not team.espn_id and match_was_exact:
                                team.espn_id = matched_espn.espn_id
                            if matched_espn.primary_color and not team.primary_color:
                                color = matched_espn.primary_color
                                if not color.startswith("#"):
                                    color = f"#{color}"
                                team.primary_color = color
                            if matched_espn.secondary_color and not team.secondary_color:
                                color = matched_espn.secondary_color
                                if not color.startswith("#"):
                                    color = f"#{color}"
                                team.secondary_color = color
                            # Store alternate names for future matching
                            alt_names = set(team.alternate_names or [])
                            for n in [matched_espn.display_name, matched_espn.short_name, matched_espn.nickname, matched_espn.name]:
                                if n and n != team.name:
                                    alt_names.add(n)
                            if alt_names:
                                team.alternate_names = list(alt_names)
                            stats["teams_updated"] += 1
            finally:
                await espn.close()

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        print(f"Team logo backfill error: {e}\n{traceback.format_exc()}")

    return stats


async def _cleanup_bad_espn_matches():
    """One-time cleanup for Team records with incorrect ESPN ID assignments.

    Two-phase cleanup:
    Phase 1: Find duplicate ESPN IDs (multiple teams sharing the same espn_id)
             and clear all but the best-matching team for each.
    Phase 2: Validates remaining teams' espn_id by looking up the ESPN team
             and comparing names using _team_name_match_score(). Clears ESPN
             data (ID, logos, colors) for teams that don't pass the threshold.
    """
    from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP
    from app.models.models import Team, Sport, TeamIdentityMapping

    stats = {
        "teams_checked": 0,
        "teams_valid": 0,
        "teams_cleared": 0,
        "duplicate_groups_found": 0,
        "duplicates_cleared": 0,
        "identity_mappings_cleared": 0,
        "errors": [],
        "cleared_teams": [],
    }

    # Track team IDs that had ESPN data cleared, for identity mapping cleanup
    cleared_team_ids = []

    def _clear_espn_data(team, reason, extra=None):
        """Clear all ESPN-sourced data from a team record."""
        info = {
            "team": team.name,
            "team_id": team.id,
            "espn_id": team.espn_id,
            "reason": reason,
        }
        if extra:
            info.update(extra)
        stats["cleared_teams"].append(info)
        cleared_team_ids.append(team.id)
        team.espn_id = None
        team.logo_url_small = None
        team.logo_url_large = None
        team.primary_color = None
        team.secondary_color = None
        # Clear contaminated alternate_names — they may contain wrong ESPN names
        team.alternate_names = None

    try:
        async with get_task_session() as session:
            # Load all teams with espn_id set, grouped by sport
            result = await session.execute(
                select(Team, Sport.key)
                .join(Sport)
                .where(Team.espn_id.isnot(None))
            )
            teams_with_espn = result.all()

            if not teams_with_espn:
                return {"status": "no_teams_with_espn_id", **stats}

            # Group by sport key
            teams_by_sport = {}
            for team, sport_key in teams_with_espn:
                if sport_key in SPORT_LEAGUE_MAP:
                    teams_by_sport.setdefault(sport_key, []).append(team)

            if not teams_by_sport:
                return {"status": "no_espn_mapped_sports", **stats}

            # Fetch ESPN teams for each sport and validate
            espn = ESPNAPIService()
            try:
                for sport_key, teams in teams_by_sport.items():
                    try:
                        espn_teams = await espn.get_teams(sport_key)
                    except Exception as e:
                        stats["errors"].append(f"fetch_{sport_key}: {str(e)}")
                        continue

                    if not espn_teams:
                        continue

                    # Build espn_id → ESPN team lookup
                    espn_by_id = {et.espn_id: et for et in espn_teams}

                    # --- Phase 1: Find and clear duplicate ESPN IDs ---
                    # Group our teams by espn_id
                    teams_by_espn_id = {}
                    for team in teams:
                        teams_by_espn_id.setdefault(team.espn_id, []).append(team)

                    for eid, group in teams_by_espn_id.items():
                        if len(group) <= 1:
                            continue  # No duplicates for this ESPN ID

                        stats["duplicate_groups_found"] += 1
                        espn_team = espn_by_id.get(eid)
                        espn_display = (espn_team.display_name or espn_team.name or "") if espn_team else ""

                        # Score each team against the ESPN name
                        scored = []
                        for team in group:
                            best = _team_name_match_score(team.name, espn_display)
                            scored.append((best, team))
                        scored.sort(key=lambda x: x[0], reverse=True)

                        # Keep the best match, clear the rest
                        best_score, best_team = scored[0]
                        for score, team in scored[1:]:
                            logger.info(
                                f"Cleanup: duplicate ESPN ID {eid} — "
                                f"clearing '{team.name}' (score {score:.2f}), "
                                f"keeping '{best_team.name}' (score {best_score:.2f})"
                            )
                            _clear_espn_data(team, "duplicate_espn_id", {
                                "espn_name": espn_display,
                                "score": round(score, 2),
                                "kept_team": best_team.name,
                            })
                            stats["duplicates_cleared"] += 1
                            stats["teams_cleared"] += 1

                        # If even the best match is bad, clear it too
                        if best_score <= 0.5:
                            logger.info(
                                f"Cleanup: duplicate ESPN ID {eid} — "
                                f"even best match '{best_team.name}' has score {best_score:.2f} — clearing"
                            )
                            _clear_espn_data(best_team, "duplicate_espn_id_all_bad", {
                                "espn_name": espn_display,
                                "score": round(best_score, 2),
                            })
                            stats["duplicates_cleared"] += 1
                            stats["teams_cleared"] += 1

                    # --- Phase 2: Validate remaining teams' ESPN IDs ---
                    for team in teams:
                        if team.espn_id is None:
                            continue  # Already cleared in Phase 1

                        stats["teams_checked"] += 1
                        espn_team = espn_by_id.get(team.espn_id)

                        if not espn_team:
                            # ESPN ID not found in current API data — clear it
                            logger.info(
                                f"Cleanup: ESPN ID {team.espn_id} not found for "
                                f"team '{team.name}' ({sport_key}) — clearing"
                            )
                            _clear_espn_data(team, "espn_id_not_found")
                            stats["teams_cleared"] += 1
                            continue

                        # Validate name match
                        espn_display = espn_team.display_name or espn_team.name or ""
                        score = _team_name_match_score(team.name, espn_display)

                        # Also check alternate names for a better score
                        if team.alternate_names:
                            for alt in team.alternate_names:
                                alt_score = _team_name_match_score(alt, espn_display)
                                if alt_score > score:
                                    score = alt_score

                        if score > 0.5:
                            stats["teams_valid"] += 1
                        else:
                            logger.info(
                                f"Cleanup: team '{team.name}' matched to ESPN "
                                f"'{espn_display}' with score {score:.2f} — clearing"
                            )
                            _clear_espn_data(team, "low_match_score", {
                                "espn_name": espn_display,
                                "score": round(score, 2),
                            })
                            stats["teams_cleared"] += 1

            finally:
                await espn.close()

            # --- Phase 3: Clear poisoned identity mappings ---
            # Delete team_identity_mapping rows for cleared teams where source='espn'
            # to prevent poisoned fast-path lookups from re-contaminating teams.
            if cleared_team_ids:
                from sqlalchemy import delete
                result = await session.execute(
                    delete(TeamIdentityMapping).where(
                        TeamIdentityMapping.team_id.in_(cleared_team_ids),
                        TeamIdentityMapping.source == "espn",
                    )
                )
                stats["identity_mappings_cleared"] = result.rowcount
                logger.info(
                    f"Cleanup: cleared {result.rowcount} ESPN identity mappings "
                    f"for {len(cleared_team_ids)} teams"
                )

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        logger.error(f"Cleanup bad ESPN matches error: {e}\n{traceback.format_exc()}")

    return stats


async def _backfill_box_scores(limit: int = 100):
    """Fetch ESPN box scores for recently completed/live events missing box_score_data.

    Called by admin endpoint POST /api/admin/espn/backfill-boxscores.
    Queries completed/closed/live events with espn_id set and box_score_data NULL,
    ordered by most recent first. For live events, box_score_data is refreshed
    each call (enables live stat prop display).
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport
    import asyncio as _asyncio

    stats = {
        "checked": 0,
        "fetched": 0,
        "errors": 0,
        "skipped_no_data": 0,
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    or_(
                        # Live events: always refresh box scores
                        and_(
                            Event.status == "live",
                            Event.espn_id.isnot(None),
                        ),
                        # Completed/closed: only if missing
                        and_(
                            Event.status.in_(["completed", "closed"]),
                            Event.espn_id.isnot(None),
                            Event.box_score_data.is_(None),
                        ),
                    )
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            events = result.scalars().all()

            if not events:
                return {"status": "no_events_to_backfill", **stats}

            espn = ESPNAPIService()
            try:
                for event in events:
                    stats["checked"] += 1
                    sport_key = event.sport.key if event.sport else None
                    if not sport_key or sport_key not in ESPN_SPORT_MAPPING:
                        continue

                    try:
                        context = await espn.get_event_context(sport_key, event.espn_id)
                        box_score = context.get("box_score", {})
                        scoring_plays = context.get("scoring_plays", [])

                        now_str = datetime.now(timezone.utc).isoformat()

                        if box_score or scoring_plays:
                            event.box_score_data = {
                                "source": "espn",
                                "fetched_at": now_str,
                                "players": box_score,
                                "scoring_plays": scoring_plays,
                            }
                            stats["fetched"] += 1
                            logger.info(
                                f"Box score fetched for event {event.id} "
                                f"({event.home_team_name} vs {event.away_team_name}): "
                                f"{len(box_score)} players"
                            )
                        else:
                            # Mark as unavailable to avoid infinite retries
                            event.box_score_data = {
                                "source": "espn",
                                "error": "not_available",
                                "fetched_at": now_str,
                            }
                            stats["skipped_no_data"] += 1

                        # Rate limit between requests
                        await _asyncio.sleep(0.5)

                    except Exception as e:
                        stats["errors"] += 1
                        logger.error(f"Box score fetch error for event {event.id}: {e}")

            finally:
                await espn.close()

    except Exception as e:
        stats["errors"] += 1
        import traceback
        logger.error(f"Box score backfill error: {e}\n{traceback.format_exc()}")

    return stats


async def _transition_event_statuses_impl() -> dict:
    """Transition event statuses based on commence_time (zero API calls).

    This breaks the circular dependency where downstream tasks (ESPN sync,
    StatPal livescores, prediction market live polling) all filter by
    status='live', but that status was only set by Odds API polling which
    may be throttled by quota conservation or adaptive slowdown.

    Transitions:
    - scheduled → live: commence_time <= now (game has started)
    - live → closed: commence_time + max_duration has passed AND no score
      updates in the last 30 min (likely ended, no data source caught it)
    """
    from app.tasks.base import get_task_session
    from app.tasks.config import SPORT_MAX_DURATIONS

    stats = {"scheduled_to_live": 0, "live_to_closed": 0}

    async with get_task_session() as session:
        now = datetime.now(timezone.utc)

        # --- scheduled → live ---
        # Find events that have started but are still marked "scheduled"
        started_result = await session.execute(
            select(Event)
            .where(
                Event.status == "scheduled",
                Event.commence_time <= now,
                # Only within the last 24h to avoid touching ancient events
                Event.commence_time >= now - timedelta(hours=24),
            )
        )
        started_events = started_result.scalars().all()

        for event in started_events:
            event.status = "live"
            stats["scheduled_to_live"] += 1

        # --- live → closed (fallback staleness) ---
        # For events that have been "live" longer than their sport's max
        # duration and have no recent score updates. This is a safety net;
        # the primary staleness checker in odds_polling handles most cases.
        stale_cutoff = now - timedelta(minutes=30)

        live_result = await session.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status == "live",
                # Started more than 5 hours ago (conservative — covers most sports)
                Event.commence_time <= now - timedelta(hours=5),
            )
        )
        live_events = live_result.scalars().all()

        for event in live_events:
            sport_key = event.sport.key if event.sport else ""
            max_hours = SPORT_MAX_DURATIONS.get("default", 4.0)
            for prefix, duration in SPORT_MAX_DURATIONS.items():
                if prefix != "default" and sport_key.startswith(prefix):
                    max_hours = duration
                    break

            hours_since_start = (now - event.commence_time).total_seconds() / 3600
            if hours_since_start > max_hours + 1.0:
                # Well past expected duration — close it
                event.status = "closed"
                stats["live_to_closed"] += 1

        if stats["scheduled_to_live"] > 0 or stats["live_to_closed"] > 0:
            logger.info(
                "Status transitions: %d scheduled→live, %d live→closed",
                stats["scheduled_to_live"], stats["live_to_closed"],
            )

    return stats
