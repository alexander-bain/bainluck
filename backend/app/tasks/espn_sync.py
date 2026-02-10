"""
ESPN live sync, metadata enrichment, and team logo backfill tasks.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, distinct
from sqlalchemy.orm import selectinload

from app.models import Event, Sport
from app.tasks.base import get_task_session, run_async
from app.tasks.config import ESPN_SPORT_MAPPING

logger = logging.getLogger(__name__)


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

    def _normalize_name(name: str) -> str:
        """Normalize team name for matching — strip accents, unify quotes/apostrophes."""
        import unicodedata
        # Normalize unicode (NFD decomposition) then strip combining marks (accents)
        normalized = unicodedata.normalize("NFD", name)
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Unify all apostrophe/quote variants to standard ASCII apostrophe
        for ch in ("\u2018", "\u2019", "\u02BB", "\u02BC", "\u0060", "\u00B4", "\u2032"):
            normalized = normalized.replace(ch, "'")
        return normalized.lower().strip()

    def names_match(our_names: list, espn_name: str) -> bool:
        """Name matching with unicode normalization — check if any name is a substring of the other."""
        espn_lower = _normalize_name(espn_name or "")
        for name in our_names:
            name_lower = _normalize_name(name)
            if name_lower in espn_lower or espn_lower in name_lower:
                return True
        return False

    async def upsert_team(session, team_name, espn_team, sport_id):
        """Create or update a Team record with ESPN enrichment data."""
        if not espn_team:
            return
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

        # Update ESPN fields
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

    try:
        async with get_task_session() as session:
            # Find sports with live games
            live_sports_result = await session.execute(
                select(distinct(Sport.key))
                .join(Event)
                .where(Event.status == "live")
            )
            live_sport_keys = [row[0] for row in live_sports_result.all()]

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

            # Process live events
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
                            Event.status == "live",
                        )
                    )
                    our_events = events_result.scalars().all()

                    for event in our_events:
                        home_names, away_names = get_event_name_variations(event)

                        for ee in espn_events:
                            if not ee.home_team or not ee.away_team:
                                continue

                            espn_home = ee.home_team.display_name or ee.home_team.name or ""
                            espn_away = ee.away_team.display_name or ee.away_team.name or ""

                            if names_match(home_names, espn_home) and names_match(away_names, espn_away):
                                stats["events_synced"] += 1
                                changed = False

                                # Upsert team records with ESPN data (colors, logos)
                                await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                                await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)

                                # Update ESPN ID
                                if ee.espn_id and event.espn_id != ee.espn_id:
                                    event.espn_id = ee.espn_id
                                    changed = True

                                # Correct commence_time from ESPN if significantly different
                                # The Odds API occasionally returns local times as UTC
                                if ee.date and event.commence_time:
                                    time_diff = abs((ee.date - event.commence_time).total_seconds())
                                    if time_diff > 300:  # > 5 minutes difference
                                        print(
                                            f"ESPN: Correcting commence_time for event {event.id} "
                                            f"({event.home_team_name} vs {event.away_team_name}): "
                                            f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                            f"(diff: {time_diff/3600:.1f}h)"
                                        )
                                        event.commence_time = ee.date
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
                                        from app.tasks.odds_polling import _create_or_update_win_prob_snapshot
                                        espn_wp_snap, is_new = await _create_or_update_win_prob_snapshot(
                                            session,
                                            event_id=event.id,
                                            source="espn",
                                            home_win_probability=ee.home_win_probability,
                                            away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                                            game_state={
                                                "clock": ee.clock,
                                                "period": ee.status_detail,
                                                "home_score": ee.home_score,
                                                "away_score": ee.away_score,
                                            },
                                        )
                                        if is_new:
                                            session.add(espn_wp_snap)
                                    except Exception:
                                        pass  # Table may not exist yet

                                # Compute statistical model win probability (live games only)
                                if ee.status == "in" and ee.home_score is not None and ee.away_score is not None and ee.clock:
                                    try:
                                        from app.utils.win_probability import compute_statistical_win_prob

                                        # Use opening spread if available
                                        pregame_spread = None
                                        if event.opening_home_spread is not None:
                                            pregame_spread = float(event.opening_home_spread)

                                        # Prefer numeric period for reliability
                                        period_str = ee.status_detail
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

                                            from app.tasks.odds_polling import _create_or_update_win_prob_snapshot
                                            stat_snap, is_new = await _create_or_update_win_prob_snapshot(
                                                session,
                                                event_id=event.id,
                                                source="stat_model",
                                                home_win_probability=round(stat_wp, 4),
                                                away_win_probability=round(1.0 - stat_wp, 4),
                                                game_state={
                                                    "clock": ee.clock,
                                                    "period": ee.status_detail,
                                                    "home_score": ee.home_score,
                                                    "away_score": ee.away_score,
                                                    "pregame_spread": pregame_spread,
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

                                break  # Found match, move to next event

                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")

            # Second pass: sync team data for scheduled events
            # (so colors/logos appear before games go live)
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

                    for event in scheduled_events:
                        home_names, away_names = get_event_name_variations(event)

                        for ee in espn_events:
                            if not ee.home_team or not ee.away_team:
                                continue
                            espn_home = ee.home_team.display_name or ee.home_team.name or ""
                            espn_away = ee.away_team.display_name or ee.away_team.name or ""

                            if names_match(home_names, espn_home) and names_match(away_names, espn_away):
                                await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id)
                                await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id)
                                # Correct commence_time from ESPN if significantly different
                                if ee.date and event.commence_time:
                                    time_diff = abs((ee.date - event.commence_time).total_seconds())
                                    if time_diff > 300:  # > 5 minutes
                                        print(
                                            f"ESPN: Correcting commence_time for scheduled event {event.id} "
                                            f"({event.home_team_name} vs {event.away_team_name}): "
                                            f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                                            f"(diff: {time_diff/3600:.1f}h)"
                                        )
                                        event.commence_time = ee.date
                                if ee.broadcasts and not event.broadcast_info:
                                    event.broadcast_info = ", ".join(ee.broadcasts)
                                if ee.espn_id and not event.espn_id:
                                    event.espn_id = ee.espn_id
                                break
                except Exception as e:
                    stats["errors"].append(f"scheduled_{sport_key}: {str(e)}")

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
                    espn_by_id = {}
                    espn_by_name = {}
                    for et in espn_teams:
                        espn_by_id[et.espn_id] = et
                        for name in [et.display_name, et.name, et.short_name, et.nickname]:
                            if name:
                                espn_by_name[name.lower()] = et

                    # Try to match our teams to ESPN teams
                    for team in teams_by_sport.get(sport_key, []):
                        matched_espn = None

                        # Match by ESPN ID first (most reliable)
                        if team.espn_id and team.espn_id in espn_by_id:
                            matched_espn = espn_by_id[team.espn_id]
                        else:
                            # Match by name
                            names_to_check = [team.name]
                            if team.alternate_names:
                                names_to_check.extend(team.alternate_names)

                            for name in names_to_check:
                                name_lower = name.lower()
                                # Exact match
                                if name_lower in espn_by_name:
                                    matched_espn = espn_by_name[name_lower]
                                    break
                                # Substring match
                                for espn_name, et in espn_by_name.items():
                                    if name_lower in espn_name or espn_name in name_lower:
                                        matched_espn = et
                                        break
                                if matched_espn:
                                    break

                        if matched_espn and matched_espn.logo_url:
                            team.logo_url_small = matched_espn.logo_url
                            team.logo_url_large = matched_espn.logo_url
                            if not team.espn_id:
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
