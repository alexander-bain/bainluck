"""
Extracted helpers for ESPN sync — team upsert, event matching, and per-pass logic.

Pulled out of the 950-line `_sync_espn_live_events` god function in
`app/tasks/espn_sync.py` to keep the orchestrator thin and each helper testable.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update as _sql_update

from app.utils.name_normalization import names_match as _canonical_names_match

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Team upsert
# ---------------------------------------------------------------------------

async def upsert_team(session, team_name, espn_team, sport_id, team_cache=None, stats=None):
    """Create or update a Team record with ESPN enrichment data.

    Returns the Team record (for linking back to events), or None.
    """
    from app.models.models import Team

    if not espn_team:
        return None

    team = team_cache.get((team_name, sport_id)) if team_cache is not None else None
    if team is None:
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
        if team_cache is not None:
            team_cache[(team_name, sport_id)] = team

    # Update ESPN fields — but guard against overwriting correct data
    # with mismatched ESPN data (e.g., from a wrong event-level match).
    # If the team already has an espn_id that differs from this ESPN team,
    # don't apply any ESPN data — the existing ID is likely correct.
    if team.espn_id and team.espn_id != espn_team.espn_id:
        # ESPN ID mismatch — skip all ESPN data updates
        if stats is not None:
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

    if stats is not None:
        stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
    return team


# ---------------------------------------------------------------------------
# Team identity registration
# ---------------------------------------------------------------------------

async def register_espn_team_identities(
    session, home_team, away_team, ee, sport_key, identity_cache
):
    """Register ESPN team identities for home and away teams (cached)."""
    from app.services.team_identity import team_identity_service

    if home_team and ee.home_team and (home_team.id, "espn") not in identity_cache:
        await team_identity_service.register_team_identity(
            session, home_team.id, "espn", sport_key,
            source_id=str(ee.home_team.espn_id) if ee.home_team.espn_id else None,
            source_name=ee.home_team.display_name or ee.home_team.name,
        )
        identity_cache.add((home_team.id, "espn"))
    if away_team and ee.away_team and (away_team.id, "espn") not in identity_cache:
        await team_identity_service.register_team_identity(
            session, away_team.id, "espn", sport_key,
            source_id=str(ee.away_team.espn_id) if ee.away_team.espn_id else None,
            source_name=ee.away_team.display_name or ee.away_team.name,
        )
        identity_cache.add((away_team.id, "espn"))


# ---------------------------------------------------------------------------
# Event ↔ ESPN matching
# ---------------------------------------------------------------------------

def match_event_to_espn(event, espn_events, espn_by_id, claimed_espn_ids, espn_names_match):
    """Match one of our events to an ESPN scoreboard entry.

    Returns (matched_espn_event, match_method) or (None, None).
    Uses a two-signal cascade:
      1. ESPN ID (most reliable — set during scheduled sync)
      2. Name matching (all ESPN name variants)
    """
    from app.tasks.espn_sync import get_event_name_variations

    # 1. Match by ESPN ID (most reliable — set during scheduled sync)
    if event.espn_id and event.espn_id in espn_by_id:
        return espn_by_id[event.espn_id], "espn_id"

    # 2. Fall back to name matching
    home_names, away_names = get_event_name_variations(event)
    for ee in espn_events:
        if not ee.home_team or not ee.away_team:
            continue
        # Skip ESPN games already claimed by another event
        if ee.espn_id and ee.espn_id in claimed_espn_ids:
            continue
        if espn_names_match(home_names, ee.home_team) and espn_names_match(away_names, ee.away_team):
            return ee, "name"

    # 3. Commence_time proximity fallback REMOVED
    # Previously matched by time proximity when exactly 1 ESPN
    # candidate was within 6 hours. This caused logo contamination
    # for college sports — a single-candidate time match assigned
    # wrong team data. Name matching (step 2) is sufficient.

    return None, None


# ---------------------------------------------------------------------------
# Live event field updates
# ---------------------------------------------------------------------------

async def update_event_fields_from_espn(session, event, ee, claimed_espn_ids, stats):
    """Update clock, scores, broadcast, importance, and commence_time from ESPN.

    Returns True if any field changed.
    """
    from app.models.models import Event

    changed = False

    # Correct commence_time from ESPN if significantly different
    # The Odds API occasionally returns local times as UTC
    # Skip if StatPal set the commence_time (more reliable source)
    if ee.date and event.commence_time:
        time_diff = abs((ee.date - event.commence_time).total_seconds())
        if time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal":
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

    return changed


# ---------------------------------------------------------------------------
# ESPN win probability + snapshot writing
# ---------------------------------------------------------------------------

async def write_espn_win_probability(session, event, ee, match_method, claimed_espn_ids, stats):
    """Write ESPN win probability to event and create ESPN + win_prob snapshots.

    Returns True if any change was made.
    """
    from app.models.models import Event, ESPNSnapshot
    from app.tasks.espn_sync import _sanitize_period

    if ee.home_win_probability is None:
        return False

    # Write espn_win_prob_home, win_probability_sources, AND espn_id
    # in one atomic Core update. espn_id was previously set via ORM
    # attribute assignment which could fail to flush when mixed with
    # Core updates on the same row.
    _wps = dict(event.win_probability_sources or {})
    _wps["espn"] = round(ee.home_win_probability, 4)
    _update_vals: dict = {
        "win_probability_sources": _wps,
        "espn_win_prob_home": ee.home_win_probability,
    }
    if ee.espn_id and ee.espn_id not in claimed_espn_ids:
        _update_vals["espn_id"] = ee.espn_id
        claimed_espn_ids.add(ee.espn_id)
    await session.execute(
        _sql_update(Event)
        .where(Event.id == event.id)
        .values(**_update_vals)
    )
    event.win_probability_sources = _wps

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

    # Write ESPN to win_prob_snapshots only for espn_id matches.
    # Name-based matches can be false positives (especially
    # college sports), contaminating the probability time-series.
    if match_method == "espn_id":
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

    return True


# ---------------------------------------------------------------------------
# Statistical model win probability
# ---------------------------------------------------------------------------

async def compute_and_write_stat_model(session, event, ee, sport_key, stats):
    """Compute statistical model win probability for live games and write snapshot.

    Only runs for espn_id matches with active game progress.
    Returns True if stat_model was computed and written.
    """
    from app.models.models import Event
    from app.tasks.espn_sync import _sanitize_period

    has_game_progress = ee.clock or sport_key.startswith("baseball_")
    if ee.status != "in" or ee.home_score is None or ee.away_score is None or not has_game_progress:
        # Track missing data for live games
        if ee.status == "in":
            if ee.home_score is None or ee.away_score is None:
                stats["stat_model_no_score"] = stats.get("stat_model_no_score", 0) + 1
            elif not ee.clock:
                stats["stat_model_no_clock"] = stats.get("stat_model_no_clock", 0) + 1
        return False

    try:
        from app.utils.win_probability import compute_statistical_win_prob

        # Use opening spread if available
        pregame_spread = None
        if event.opening_home_spread is not None:
            pregame_spread = float(event.opening_home_spread)

        # Pass opening probability as prior so the model
        # doesn't start at 50% when no spread is available.
        opening_prob = None
        if event.opening_home_probability is not None:
            opening_prob = float(event.opening_home_probability)

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
            opening_home_probability=opening_prob,
        )
        if stat_wp is not None:
            _wps2 = dict(event.win_probability_sources or {})
            _wps2["stat_model"] = round(stat_wp, 4)
            await session.execute(
                _sql_update(Event)
                .where(Event.id == event.id)
                .values(win_probability_sources=_wps2)
            )
            event.win_probability_sources = _wps2

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
            return True
        else:
            logger.warning(
                f"stat_model returned None for event {event.id} "
                f"(sport={sport_key}, clock={ee.clock!r}, period={ee.status_detail!r}, "
                f"score={ee.home_score}-{ee.away_score})"
            )
    except Exception as e:
        logger.error(f"stat_model error for event {event.id}: {e}")

    return False


# ---------------------------------------------------------------------------
# Create events from unmatched ESPN games
# ---------------------------------------------------------------------------

async def create_events_from_unmatched_espn(session, our_events, espn_events, sport_key, stats):
    """Create Event records for ESPN games that don't match any of our events.

    ESPN is a first-class source. If ESPN has a game and we don't, create it.
    Other sources (Odds API, StatPal) will find it later via the Event Registry.
    """
    from app.models.models import Event, ESPNSnapshot

    matched_espn_ids = set()
    for event in our_events:
        if event.espn_id:
            matched_espn_ids.add(event.espn_id)

    from app.services.event_registry import (
        find_or_create_event as _foc,
        EventIdentity as _EI,
        EventClaim as _EC,
    )
    for ee in espn_events:
        if not ee.espn_id or ee.espn_id in matched_espn_ids:
            continue
        if not ee.home_team or not ee.away_team:
            continue
        espn_home = ee.home_team.display_name or ee.home_team.name or ""
        espn_away = ee.away_team.display_name or ee.away_team.name or ""
        if not espn_home or not espn_away:
            continue

        try:
            identity = _EI(
                sport_key=sport_key,
                home_team_name=espn_home,
                away_team_name=espn_away,
                commence_time=ee.date,
                claim=_EC("espn", ee.espn_id),
                commence_time_source="espn",
                status="live" if ee.status == "in" else (
                    "completed" if ee.status in ("post", "final") else "scheduled"
                ),
            )
            event, created = await _foc(session, identity)

            # Write win probability snapshot
            if ee.home_win_probability is not None:
                _wps3 = dict(event.win_probability_sources or {})
                _wps3["espn"] = round(ee.home_win_probability, 4)
                await session.execute(
                    _sql_update(Event)
                    .where(Event.id == event.id)
                    .values(
                        win_probability_sources=_wps3,
                        espn_win_prob_home=ee.home_win_probability,
                    )
                )
                event.win_probability_sources = _wps3

                snapshot = ESPNSnapshot(
                    event_id=event.id,
                    home_win_probability=ee.home_win_probability,
                    away_win_probability=1.0 - ee.home_win_probability,
                    home_score=ee.home_score,
                    away_score=ee.away_score,
                    game_clock=ee.clock,
                    period=ee.status_detail,
                )
                session.add(snapshot)

            if ee.status in ("post", "final") and not event.completed_at:
                await session.execute(
                    _sql_update(Event)
                    .where(Event.id == event.id)
                    .values(completed_at=datetime.now(timezone.utc))
                )

            if created:
                stats["espn_events_created"] = stats.get("espn_events_created", 0) + 1
                logger.info(
                    "ESPN: created event %d for %s: %s vs %s (espn_id=%s)",
                    event.id, sport_key, espn_home, espn_away, ee.espn_id,
                )
            else:
                stats["espn_events_attached"] = stats.get("espn_events_attached", 0) + 1
        except Exception as exc:
            logger.warning("ESPN create/attach failed for %s vs %s: %s", espn_home, espn_away, exc)


# ---------------------------------------------------------------------------
# Scheduled events pass (team data pre-population)
# ---------------------------------------------------------------------------

async def sync_scheduled_events(session, sport_key, espn_events, stats):
    """Second pass: sync team data for scheduled events.

    Pre-populates colors/logos before games go live, and sets ESPN IDs
    for reliable matching when the game starts.
    """
    from app.models.models import Event, Team
    from sqlalchemy.orm import selectinload
    from app.tasks.espn_sync import get_event_name_variations, espn_team_matches

    events_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.sport.has(key=sport_key),
            Event.status == "scheduled",
        )
    )
    scheduled_events = events_result.scalars().all()

    # Batch-load teams for this sport to avoid N+1 queries
    sched_sport_obj = scheduled_events[0].sport if scheduled_events else None
    if sched_sport_obj:
        _sched_team_result = await session.execute(
            select(Team).where(Team.sport_id == sched_sport_obj.id)
        )
        sched_team_cache = {(t.name, t.sport_id): t for t in _sched_team_result.scalars().all()}
    else:
        sched_team_cache = {}

    # Build ESPN ID lookup for scheduled pass
    espn_by_id_sched = {}
    for ee in espn_events:
        if ee.espn_id:
            espn_by_id_sched[ee.espn_id] = ee

    stats["scheduled_pass"] = stats.get("scheduled_pass", {})
    stats["scheduled_pass"][sport_key] = {
        "our_events": len(scheduled_events),
        "espn_events": len(espn_events),
    }

    sched_identity_cache: set[tuple[int, str]] = set()
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
                if espn_team_matches(home_names, ee.home_team) and espn_team_matches(away_names, ee.away_team):
                    matched_espn = ee
                    break

        # 3. Commence_time proximity fallback REMOVED
        # Caused massive logo contamination for college sports.

        if not matched_espn:
            continue

        ee = matched_espn
        home_team = await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id, sched_team_cache, stats)
        away_team = await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id, sched_team_cache, stats)
        if home_team and event.home_team_id != home_team.id:
            event.home_team_id = home_team.id
        if away_team and event.away_team_id != away_team.id:
            event.away_team_id = away_team.id

        # Register ESPN team identities (cached to avoid re-registering)
        await register_espn_team_identities(
            session, home_team, away_team, ee, sport_key, sched_identity_cache
        )

        # Correct commence_time from ESPN if significantly different
        # Skip if StatPal set the commence_time (more reliable source)
        if ee.date and event.commence_time:
            time_diff = abs((ee.date - event.commence_time).total_seconds())
            if time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal":
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


# ---------------------------------------------------------------------------
# Box score fetching (completed + live)
# ---------------------------------------------------------------------------

async def fetch_completed_box_scores(session, stats):
    """Third pass: fetch box scores for recently completed events
    that have an ESPN ID but no box_score_data yet.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event
    from app.tasks.config import ESPN_SPORT_MAPPING
    from sqlalchemy.orm import selectinload
    import json as _json_mod
    from sqlalchemy import text as _raw_text

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
        .limit(10)
    )
    box_events = completed_result.scalars().all()

    if not box_events:
        return

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
                    bsd = {
                        "source": "espn",
                        "fetched_at": now_str,
                        "players": box_score,
                        "scoring_plays": scoring_plays,
                    }
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(bsd), "eid": event.id},
                    )
                    event.box_score_data = bsd
                    stats["box_scores_fetched"] = stats.get("box_scores_fetched", 0) + 1
                else:
                    err_bsd = {
                        "source": "espn",
                        "error": "not_available",
                        "fetched_at": now_str,
                    }
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(err_bsd), "eid": event.id},
                    )
                    event.box_score_data = err_bsd
            except Exception as e:
                logger.error(f"Box score fetch error for event {event.id}: {e}")
    finally:
        await box_espn.close()


async def fetch_live_box_scores(session, stats):
    """Fourth pass: update box scores for live events (every 2 minutes)."""
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event
    from app.tasks.config import ESPN_SPORT_MAPPING
    from sqlalchemy.orm import selectinload
    import json as _json_mod
    from sqlalchemy import text as _raw_text

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

    if not live_to_fetch:
        return

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
                    bsd = {
                        "source": "espn",
                        "fetched_at": now_str,
                        "players": box_data,
                        "scoring_plays": scoring_plays,
                        "live": True,
                    }
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(bsd), "eid": ev.id},
                    )
                    ev.box_score_data = bsd
                    stats["live_box_scores_fetched"] = (
                        stats.get("live_box_scores_fetched", 0) + 1
                    )
            except Exception as e:
                logger.error(f"Live box score error for event {ev.id}: {e}")
    finally:
        await live_espn.close()


# ---------------------------------------------------------------------------
# Score backfill for completed events with no scores/ESPN ID
# ---------------------------------------------------------------------------

async def backfill_missing_scores(session, stats):
    """Fifth pass: backfill scores for recently completed events
    that have NO scores and NO espn_id. Catches niche sports that were
    added to ESPN_SPORT_MAPPING after the events completed.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Team
    from app.tasks.config import ESPN_SPORT_MAPPING
    from app.tasks.espn_sync import get_event_name_variations
    from app.utils.name_normalization import names_match as _canonical_names_match
    from sqlalchemy.orm import selectinload

    def names_match(our_names: list, espn_name: str) -> bool:
        if not espn_name:
            return False
        return any(_canonical_names_match(name, espn_name) for name in our_names if name)

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

    if not events_by_sport:
        return

    # Batch-load teams for score backfill to avoid N+1
    backfill_team_cache = {}
    for _sk, _evts in events_by_sport.items():
        if _evts and _evts[0].sport:
            _bt_result = await session.execute(
                select(Team).where(Team.sport_id == _evts[0].sport.id)
            )
            for t in _bt_result.scalars().all():
                backfill_team_cache[(t.name, t.sport_id)] = t

    score_espn = ESPNAPIService()
    try:
        for sport_key, events_list in events_by_sport.items():
            try:
                # Fetch scoreboard with date range covering these events
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
                                    home_team = await upsert_team(session, ev.home_team_name, ee.home_team, ev.sport_id, backfill_team_cache, stats)
                                    away_team = await upsert_team(session, ev.away_team_name, ee.away_team, ev.sport_id, backfill_team_cache, stats)
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
