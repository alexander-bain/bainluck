"""
ESPN live sync, metadata enrichment, and team logo backfill tasks.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, distinct, and_, or_, update as _sql_update
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


def espn_names_match(our_names: list[str], espn_team) -> bool:
    """Check if any of our name variations match any ESPN name variant.

    Args:
        our_names: List of our team name variations (from get_event_name_variations)
        espn_team: ESPN team object with display_name, short_name, name, location
    """
    espn_variants = []
    for attr in ("display_name", "short_name", "name", "location"):
        name = getattr(espn_team, attr, None)
        if name and name not in espn_variants:
            espn_variants.append(name)

    for our_name in our_names:
        for espn_name in espn_variants:
            if _canonical_names_match(our_name, espn_name):
                return True
    return False


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
                        logger.warning("Error enriching event %s: %s", event.id, e)

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
        logger.warning("Enrichment task error: %s", e)
        stats["errors"] += 1

    return stats


def _espn_names_match_any(our_names: list, espn_name: str) -> bool:
    """Check if any of our name variations match an ESPN name."""
    if not espn_name:
        return False
    return any(_canonical_names_match(name, espn_name) for name in our_names if name)


def get_event_name_variations(event) -> tuple[list[str], list[str]]:
    """Get all name variations for an event's home and away teams."""
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


def get_espn_name_variants(espn_team) -> list[str]:
    """Get all name variants from an ESPN team object for matching."""
    variants = []
    for name in [espn_team.display_name, espn_team.short_name, espn_team.name, espn_team.location]:
        if name and name not in variants:
            variants.append(name)
    return variants


def espn_team_matches(our_names: list, espn_team) -> bool:
    """Check if any of our name variations match any ESPN name variant."""
    for espn_name in get_espn_name_variants(espn_team):
        if _espn_names_match_any(our_names, espn_name):
            return True
    return False


async def _sync_espn_live_events():
    """Async implementation of sync_espn_live_events.

    Orchestrates five passes over ESPN data:
      1. Live/recently-completed event sync (scores, clock, win prob, stat model)
      2. Scheduled event team pre-population (colors, logos, ESPN IDs)
      3. Completed box score fetching
      4. Live box score refreshing
      5. Score backfill for niche sports
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport, Team
    from app.utils.espn_helpers import (
        upsert_team,
        register_espn_team_identities,
        match_event_to_espn,
        update_event_fields_from_espn,
        write_espn_win_probability,
        compute_and_write_stat_model,
        create_events_from_unmatched_espn,
        sync_scheduled_events,
        fetch_completed_box_scores,
        fetch_live_box_scores,
        backfill_missing_scores,
    )

    stats = {
        "sports_checked": 0,
        "sports_with_live": 0,
        "events_synced": 0,
        "events_updated": 0,
        "errors": [],
    }

    espn_names_match = espn_team_matches

    try:
        async with get_task_session() as session:
            # ── Discover which sports need ESPN data ──────────────
            live_sport_keys, scheduled_sport_keys = await _find_sport_keys_to_sync(session)

            if not live_sport_keys:
                return {"status": "no_live_games", **stats}

            stats["sports_with_live"] = len(live_sport_keys)

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

            # ── Fetch all ESPN scoreboards ────────────────────────
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

            # ── First pass: live + recently-completed events ─────
            recently_completed_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
            started_cutoff = datetime.now(timezone.utc) - timedelta(hours=5)

            for sport_key in live_sport_keys:
                stats["sports_checked"] += 1

                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue

                try:
                    await _process_live_sport(
                        session, sport_key, espn_events, stats,
                        recently_completed_cutoff, started_cutoff,
                        espn_names_match, upsert_team, register_espn_team_identities,
                        match_event_to_espn, update_event_fields_from_espn,
                        write_espn_win_probability, compute_and_write_stat_model,
                        create_events_from_unmatched_espn,
                    )
                except Exception as e:
                    stats["errors"].append(f"{sport_key}: {str(e)}")

            # ── Second pass: scheduled events (team pre-population) ─
            for sport_key in scheduled_sport_keys:
                if sport_key not in ESPN_SPORT_MAPPING:
                    continue
                espn_events = espn_data.get(sport_key, [])
                if not espn_events:
                    continue
                try:
                    await sync_scheduled_events(session, sport_key, espn_events, stats)
                except Exception as e:
                    stats["errors"].append(f"scheduled_{sport_key}: {str(e)}")

            # ── Third pass: completed box scores ─────────────────
            try:
                await fetch_completed_box_scores(session, stats)
            except Exception as e:
                stats["errors"].append(f"box_score_pass: {str(e)}")

            # ── Fourth pass: live box scores ─────────────────────
            try:
                await fetch_live_box_scores(session, stats)
            except Exception as e:
                stats["errors"].append(f"live_box_score_pass: {str(e)}")

            # ── Fifth pass: score backfill ───────────────────────
            try:
                await backfill_missing_scores(session, stats)
            except Exception as e:
                stats["errors"].append(f"score_backfill_pass: {str(e)}")

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        logger.warning("ESPN sync task error: %s", e, exc_info=True)

    return stats


async def _find_sport_keys_to_sync(session):
    """Discover which sports have live, recently-completed, or scheduled events.

    Returns (live_sport_keys, scheduled_sport_keys).
    """
    from app.models.models import Event, Sport

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
    recently_completed_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    recent_completed_result = await session.execute(
        select(distinct(Sport.key))
        .join(Event)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.commence_time >= recently_completed_cutoff,
        )
    )
    for row in recent_completed_result.all():
        if row[0] not in live_sport_keys:
            live_sport_keys.append(row[0])

    # Also include sports with "scheduled" events that have already
    # commenced -- odds polling may be slow to mark them "live".
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

    # Find sports with scheduled games for team data pre-population
    scheduled_sports_result = await session.execute(
        select(distinct(Sport.key))
        .join(Event)
        .where(Event.status == "scheduled")
    )
    scheduled_sport_keys = [row[0] for row in scheduled_sports_result.all()]

    return live_sport_keys, scheduled_sport_keys


async def _process_live_sport(
    session, sport_key, espn_events, stats,
    recently_completed_cutoff, started_cutoff,
    espn_names_match, upsert_team_fn, register_identities_fn,
    match_event_fn, update_fields_fn, write_win_prob_fn,
    compute_stat_model_fn, create_unmatched_fn,
):
    """Process all live/recently-completed events for one sport.

    Handles event matching, field updates, win probability, stat model,
    team upsert, identity registration, and creation of new events
    from unmatched ESPN games.
    """
    from app.models.models import Event, Team
    from sqlalchemy import and_, or_

    events_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.sport.has(key=sport_key),
            or_(
                Event.status == "live",
                and_(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= recently_completed_cutoff,
                ),
                and_(
                    Event.status == "scheduled",
                    Event.commence_time <= datetime.now(timezone.utc),
                    Event.commence_time >= started_cutoff,
                ),
            ),
        )
    )
    our_events = events_result.scalars().all()

    # Batch-load teams for this sport to avoid N+1 queries in upsert_team
    sport_obj = our_events[0].sport if our_events else None
    if sport_obj:
        _team_result = await session.execute(
            select(Team).where(Team.sport_id == sport_obj.id)
        )
        team_cache = {(t.name, t.sport_id): t for t in _team_result.scalars().all()}
    else:
        team_cache = {}

    # Build ESPN ID lookup for fast matching
    espn_by_id = {}
    for ee in espn_events:
        if ee.espn_id:
            espn_by_id[ee.espn_id] = ee

    # Cache for team identity registration
    identity_cache: set[tuple[int, str]] = set()

    # Track ESPN IDs claimed this cycle to prevent collision
    claimed_espn_ids: set[str] = set()
    for ev in our_events:
        if ev.espn_id:
            claimed_espn_ids.add(ev.espn_id)

    for event in our_events:
        matched_espn, match_method = match_event_fn(
            event, espn_events, espn_by_id, claimed_espn_ids, espn_names_match,
        )

        if not matched_espn:
            stats["events_unmatched"] = stats.get("events_unmatched", 0) + 1
            if sport_key in ("basketball_nba", "icehockey_nhl", "baseball_mlb", "americanfootball_nfl"):
                logger.warning(
                    "ESPN unmatched: %s %s vs %s (espn_id=%s, id=%d). "
                    "ESPN has %d events for this sport.",
                    sport_key, event.home_team_name, event.away_team_name,
                    event.espn_id, event.id, len(espn_events),
                )
            continue

        ee = matched_espn
        stats["events_synced"] += 1
        stats[f"match_{match_method}"] = stats.get(f"match_{match_method}", 0) + 1
        changed = False

        # Upsert team records with ESPN data (colors, logos)
        home_team = await upsert_team_fn(session, event.home_team_name, ee.home_team, event.sport_id, team_cache, stats)
        away_team = await upsert_team_fn(session, event.away_team_name, ee.away_team, event.sport_id, team_cache, stats)
        if home_team and event.home_team_id != home_team.id:
            event.home_team_id = home_team.id
            changed = True
        if away_team and event.away_team_id != away_team.id:
            event.away_team_id = away_team.id
            changed = True

        # Register ESPN team identities
        await register_identities_fn(
            session, home_team, away_team, ee, sport_key, identity_cache,
        )

        # Update clock, scores, broadcast, importance, commence_time
        fields_changed = await update_fields_fn(session, event, ee, claimed_espn_ids, stats)
        if fields_changed:
            changed = True

        # ESPN win probability + snapshots
        wp_changed = await write_win_prob_fn(session, event, ee, match_method, claimed_espn_ids, stats)
        if wp_changed:
            changed = True

        # Statistical model win probability (espn_id matches only)
        if match_method == "espn_id":
            sm_changed = await compute_stat_model_fn(session, event, ee, sport_key, stats)
            if sm_changed:
                changed = True
        elif ee.status == "in":
            # Track missing data for live games
            if ee.home_score is None or ee.away_score is None:
                stats["stat_model_no_score"] = stats.get("stat_model_no_score", 0) + 1
            elif not ee.clock:
                stats["stat_model_no_clock"] = stats.get("stat_model_no_clock", 0) + 1

        if changed:
            stats["events_updated"] += 1

    # Create events for unmatched ESPN games
    await create_unmatched_fn(session, our_events, espn_events, sport_key, stats)


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
        logger.warning("Team logo backfill error: %s", e, exc_info=True)

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


async def _backfill_box_scores(limit: int = 100, priority_calibration: bool = False):
    """Fetch ESPN box scores for completed/live events missing box_score_data.

    When priority_calibration=True, prioritizes events that have Kalshi
    player prop markets needing is_winner resolution. This ensures the
    first box scores backfilled are the ones that directly improve
    calibration accuracy.
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
            if priority_calibration:
                from app.models.models import FuturesMarket
                result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        Event.status.in_(["completed", "closed"]),
                        Event.espn_id.isnot(None),
                        Event.box_score_data.is_(None),
                        Event.id.in_(
                            select(FuturesMarket.event_id).where(
                                FuturesMarket.source == "kalshi",
                                FuturesMarket.event_id.isnot(None),
                                FuturesMarket.status == "resolved",
                            )
                        ),
                    )
                    .order_by(Event.commence_time.desc())
                    .limit(limit)
                )
            else:
                result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        or_(
                            and_(
                                Event.status == "live",
                                Event.espn_id.isnot(None),
                            ),
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


async def _backfill_espn_ids(limit: int = 1000):
    """Backfill ESPN IDs on completed events that don't have one.

    Queries ESPN's scoreboard API for past dates, matches completed events
    by team name, and sets espn_id. This enables box score fetching for
    games that weren't live during our ESPN sync window.

    Processes ALL historical events (no time-window limit). Works backwards
    from the most recent unmatched event. Respectful: 0.5s sleep between
    API calls.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport
    import asyncio as _asyncio

    stats = {"dates_checked": 0, "events_matched": 0, "already_had_id": 0, "errors": 0}

    espn_sports = list(ESPN_SPORT_MAPPING.keys())

    try:
        async with get_task_session() as session:
            # Find completed events without ESPN IDs in ESPN-supported sports
            result = await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    Event.status.in_(["completed", "closed"]),
                    Event.espn_id.is_(None),
                    Event.commence_time.isnot(None),
                    Event.home_team_name.isnot(None),
                    Event.away_team_name.isnot(None),
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            events = result.scalars().all()

            if not events:
                return {"status": "no_events_to_backfill", **stats}

            # Filter to ESPN-supported sports
            events = [e for e in events if e.sport and e.sport.key in ESPN_SPORT_MAPPING]
            if not events:
                return {"status": "no_espn_sports_to_backfill", **stats}

            # Group by (sport, date) to minimize API calls
            from collections import defaultdict
            by_sport_date: dict[tuple[str, str], list] = defaultdict(list)
            for event in events:
                sport_key = event.sport.key
                date_str = event.commence_time.strftime("%Y%m%d")
                by_sport_date[(sport_key, date_str)].append(event)

            espn = ESPNAPIService()
            try:
                for (sport_key, date_str), date_events in list(by_sport_date.items())[:200]:
                    stats["dates_checked"] += 1

                    try:
                        espn_events = await espn.get_scoreboard(sport_key, date=date_str)
                    except Exception as e:
                        stats["errors"] += 1
                        logger.warning(f"ESPN scoreboard error for {sport_key}/{date_str}: {e}")
                        continue

                    if not espn_events:
                        continue

                    for event in date_events:
                        home_names, away_names = get_event_name_variations(event)
                        for ee in espn_events:
                            if not ee.home_team or not ee.away_team:
                                continue
                            if (espn_team_matches(home_names, ee.home_team)
                                    and espn_team_matches(away_names, ee.away_team)):
                                event.espn_id = ee.espn_id
                                stats["events_matched"] += 1
                                logger.info(
                                    f"ESPN ID backfill: matched event {event.id} "
                                    f"({event.home_team_name} vs {event.away_team_name}) "
                                    f"→ ESPN {ee.espn_id}"
                                )
                                break

                    await _asyncio.sleep(0.5)

                await session.commit()

            finally:
                await espn.close()

    except Exception as e:
        stats["errors"] += 1
        import traceback
        logger.error(f"ESPN ID backfill error: {e}\n{traceback.format_exc()}")

    logger.info(
        "ESPN ID backfill: %d dates checked, %d events matched, %d errors",
        stats["dates_checked"], stats["events_matched"], stats["errors"],
    )
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
        # duration. This is a safety net; the primary mechanism is ESPN
        # sync setting status="completed" when it sees post/final.
        # BR76: previously used a 5-hour hardcoded minimum, causing NBA
        # games (~2.5h) to stay "live" for 2.5+ hours after ending when
        # ESPN sync missed the transition.

        # Find the minimum max_duration across all sports so we only
        # fetch events that could possibly qualify for transition.
        min_max_hours = min(SPORT_MAX_DURATIONS.values())

        live_result = await session.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.status == "live",
                # Use the shortest sport duration as the query cutoff;
                # per-sport filtering happens in the loop below.
                Event.commence_time <= now - timedelta(hours=min_max_hours),
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
            if hours_since_start > max_hours + 0.5:
                event.status = "closed"
                if not event.completed_at:
                    event.completed_at = now
                stats["live_to_closed"] += 1

                # Write resolved win probability for prediction market sources.
                # Without this, Kalshi/Polymarket stay at their last mid-game
                # probability instead of resolving to 1.0/0.0.
                if (event.home_score is not None
                        and event.away_score is not None):
                    if event.home_score > event.away_score:
                        resolved_home = 1.0
                    elif event.home_score < event.away_score:
                        resolved_home = 0.0
                    else:
                        resolved_home = 0.5
                    wp_sources = event.win_probability_sources or {}
                    wp_sources["final_result"] = resolved_home
                    for src_key in ("kalshi", "polymarket"):
                        if src_key in wp_sources:
                            wp_sources[src_key]["value"] = resolved_home
                    await session.execute(
                        _sql_update(Event)
                        .where(Event.id == event.id)
                        .values(win_probability_sources=wp_sources)
                    )
                    stats.setdefault("pm_resolved", 0)
                    stats["pm_resolved"] += 1

        # --- Repair: completed with 0-0 → scheduled/live ---
        # The Odds API occasionally returns completed=true for games that
        # haven't started. Reset these to the correct status.
        stats["repaired_bogus_completed"] = 0
        bogus_result = await session.execute(
            select(Event).where(
                Event.status == "completed",
                Event.home_score == 0,
                Event.away_score == 0,
                Event.completed_at.is_(None),
                Event.commence_time >= now - timedelta(hours=12),
            )
        )
        for event in bogus_result.scalars().all():
            if event.commence_time > now:
                event.status = "scheduled"
            else:
                event.status = "live"
            event.home_score = None
            event.away_score = None
            stats["repaired_bogus_completed"] += 1

        if stats["scheduled_to_live"] > 0 or stats["live_to_closed"] > 0 or stats["repaired_bogus_completed"] > 0:
            logger.info(
                "Status transitions: %d scheduled→live, %d live→closed, %d repaired (pm_resolved=%d)",
                stats["scheduled_to_live"], stats["live_to_closed"],
                stats["repaired_bogus_completed"],
                stats.get("pm_resolved", 0),
            )

    return stats


async def _backfill_espn_win_probability(limit: int = 200):
    """Backfill ESPN win probability for completed events with sparse snapshots.

    The live sync captures probability every 60s, but if it misses a game
    (worker downtime, task starvation), that game's probability chart is lost.
    ESPN's /summary endpoint has the full play-by-play probability curve
    retroactively — this task fetches it for recently completed games.

    Processes ALL historical events (no time-window limit). Only processes
    events with espn_id (confirmed match) and fewer than 10
    win_prob_snapshots from the espn source.
    """
    import asyncio as _asyncio
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.services.espn_api import ESPNAPIService
    from app.models.models import WinProbSnapshot

    stats = {
        "events_checked": 0, "events_backfilled": 0,
        "snapshots_created": 0, "api_empty": 0, "already_covered": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT e.id, e.espn_id, e.commence_time,
                           s.key AS sport_key,
                           snap_cnt.cnt AS espn_snap_count
                    FROM events e
                    JOIN sports s ON s.id = e.sport_id
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS cnt FROM win_prob_snapshots wps
                        WHERE wps.event_id = e.id AND wps.source = 'espn'
                    ) snap_cnt ON true
                    WHERE e.status IN ('completed', 'closed')
                      AND e.espn_id IS NOT NULL
                      AND snap_cnt.cnt < 10
                    ORDER BY e.commence_time DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            events = result.fetchall()

            if not events:
                return {**stats, "status": "nothing_to_backfill"}

            logger.info("ESPN win prob backfill: %d events to process", len(events))

            service = ESPNAPIService()
            try:
                for event_row in events:
                    stats["events_checked"] += 1
                    sport_key = event_row.sport_key

                    if sport_key not in ESPN_SPORT_MAPPING:
                        continue

                    try:
                        wp_data = await service.get_win_probability(
                            sport_key, event_row.espn_id,
                        )
                    except Exception as e:
                        stats["errors"].append(f"event_{event_row.id}: {str(e)[:80]}")
                        continue

                    if not wp_data:
                        stats["api_empty"] += 1
                        continue

                    event_snapshots = 0
                    commence = event_row.commence_time

                    for i, point in enumerate(wp_data):
                        home_wp = point.get("home_win_probability")
                        if home_wp is None:
                            continue

                        seconds_left = point.get("seconds_left")
                        snap_time = (
                            commence + timedelta(seconds=i * 30)
                            if commence
                            else datetime.now(timezone.utc)
                        )

                        stmt = pg_insert(WinProbSnapshot).values(
                            event_id=event_row.id,
                            source="espn",
                            home_win_probability=round(home_wp, 4),
                            away_win_probability=round(1.0 - home_wp, 4),
                            captured_at=snap_time,
                            game_state={
                                "seconds_left": seconds_left,
                                "backfilled": True,
                            },
                        ).on_conflict_do_nothing()
                        await session.execute(stmt)
                        event_snapshots += 1

                    if event_snapshots > 0:
                        stats["events_backfilled"] += 1
                        stats["snapshots_created"] += event_snapshots

                    if stats["events_checked"] % 10 == 0:
                        await session.commit()
                        logger.info(
                            "ESPN win prob backfill: %d/%d events, %d snapshots",
                            stats["events_checked"], len(events),
                            stats["snapshots_created"],
                        )

                    await _asyncio.sleep(0.5)

                await session.commit()
            finally:
                await service.close()

    except Exception as e:
        logger.error("ESPN win prob backfill error: %s", e)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    logger.info(
        "ESPN win prob backfill: %d checked, %d backfilled, %d snapshots",
        stats["events_checked"], stats["events_backfilled"],
        stats["snapshots_created"],
    )
    return stats
