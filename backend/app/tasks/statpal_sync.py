"""StatPal sync task — schedules, injuries, game times, and play-by-play.

StatPal serves as the canonical source for:
1. **Event schedules** — fixture lists with accurate start times (corrects The Odds API time errors)
2. **Rosters** — player names, positions, jersey numbers (supplements ESPN)
3. **Injuries** — structured injury reports for "Why Did the Line Move?" context
4. **Game start/end times** — authoritative window for when markets should be open/close
5. **Play-by-play** — scoring plays and key events that explain probability movements

The sync task runs on three cadences:
- Schedules: hourly — upserts fixtures, corrects commence_time, populates end_time
- Injuries: every 15 min — injury reports feed into line movement analysis
- Live plays: every 60s — play-by-play for live games (scoring context for Pulse)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update, and_, or_, func

from app.tasks.base import get_task_session
from app.tasks.config import STATPAL_SPORT_MAPPING

logger = logging.getLogger(__name__)


async def _sync_statpal_schedules(sport_key: Optional[str] = None) -> dict:
    """Sync fixture schedules from StatPal for all mapped sports.

    For each sport, fetches today's + upcoming fixtures and:
    - Corrects commence_time on existing events (The Odds API sometimes has wrong times)
    - Populates end_time for finished games (market close window)
    - Stores StatPal fixture ID on events for later play-by-play lookups

    Args:
        sport_key: If provided, only sync this sport. Otherwise syncs all mapped sports.

    Returns:
        Summary dict with counts per sport.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    if not sport_keys:
        return {"skipped": True, "reason": f"sport_key {sport_key!r} not in STATPAL_SPORT_MAPPING"}

    service = StatPalAPIService()
    total_updated = 0
    total_fixtures = 0
    details = []

    total_created = 0

    # Track StatPal fixture IDs already processed in this run
    # to prevent duplicates across soccer league iterations
    # (all map to StatPal sport="soccer" but have different sport_ids)
    seen_fixture_ids: set[str] = set()

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                # Find the Sport record
                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    continue

                sport_id = sport_row.id

                # Fetch schedule — season-schedule returns full season for v1 sports
                # We'll filter to a useful window (yesterday to +7 days) in the loop
                fixtures = await service.get_fixtures(statpal_sport)

                # Also fetch live scores to get current game state
                live = await service.get_live_scores(statpal_sport)
                live_by_teams = {}
                for f in live:
                    key = _fixture_match_key(f.home_team, f.away_team)
                    live_by_teams[key] = f

                sport_updated = 0
                sport_created = 0
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(days=1)
                window_end = now + timedelta(days=7)

                for fixture in fixtures:
                    if not fixture.home_team or not fixture.away_team:
                        continue

                    # Filter to relevant window — skip fixtures outside -1d to +7d
                    if fixture.start_time:
                        if fixture.start_time < window_start or fixture.start_time > window_end:
                            continue

                    total_fixtures += 1

                    # Dedup: skip if this StatPal fixture was already processed
                    # in a prior sport key iteration (e.g., soccer_epl and soccer_usa_mls
                    # both query StatPal sport="soccer" and get identical fixtures)
                    if fixture.fixture_id:
                        if fixture.fixture_id in seen_fixture_ids:
                            continue
                        seen_fixture_ids.add(fixture.fixture_id)

                    # Find matching event in our DB by team names + time proximity
                    match_key = _fixture_match_key(fixture.home_team, fixture.away_team)
                    live_data = live_by_teams.get(match_key)

                    # ── Unified event matching via Event Registry ──
                    # Only create events for future games
                    if not fixture.start_time or fixture.start_time <= now:
                        # For past fixtures, try to find existing event to enrich
                        event = None
                        if fixture.fixture_id:
                            fid_result = await session.execute(
                                select(Event).where(
                                    Event.statpal_fixture_id == fixture.fixture_id
                                )
                            )
                            event = fid_result.scalar_one_or_none()
                        if not event:
                            continue  # Past game, no existing event — skip
                    else:
                        from app.services.event_registry import (
                            find_or_create_event, EventIdentity, EventClaim,
                        )
                        claim_id = fixture.fixture_id or f"statpal_{fixture.home_team}_{fixture.away_team}"
                        identity = EventIdentity(
                            sport_key=our_key,
                            home_team_name=fixture.home_team,
                            away_team_name=fixture.away_team,
                            commence_time=fixture.start_time,
                            claim=EventClaim("statpal", claim_id),
                            commence_time_source="statpal",
                            status="scheduled",
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        if was_created:
                            sport_created += 1

                    updated = False

                    # Resolve and register team identities for future indexed lookups
                    from app.services.team_identity import team_identity_service
                    home_team = await team_identity_service.resolve_team(
                        session, "statpal", our_key,
                        source_name=fixture.home_team,
                    )
                    away_team = await team_identity_service.resolve_team(
                        session, "statpal", our_key,
                        source_name=fixture.away_team,
                    )
                    if home_team and not event.home_team_id:
                        event.home_team_id = home_team.id
                        updated = True
                    if away_team and not event.away_team_id:
                        event.away_team_id = away_team.id
                        updated = True

                    # Correct commence_time if StatPal has a different (likely more accurate) time
                    if fixture.start_time and event.commence_time:
                        diff = abs((fixture.start_time - event.commence_time).total_seconds())
                        # Only correct if >5 min difference (avoids timezone rounding)
                        if diff > 300:
                            logger.info(
                                f"StatPal: correcting commence_time for event {event.id} "
                                f"({event.home_team_name} vs {event.away_team_name}): "
                                f"{event.commence_time} -> {fixture.start_time}"
                            )
                            event.commence_time = fixture.start_time
                            if hasattr(event, "commence_time_source"):
                                event.commence_time_source = "statpal"
                            updated = True
                    if fixture.fixture_id and not _get_statpal_id(event):
                        _set_statpal_id(event, fixture.fixture_id)
                        updated = True

                    # Populate end_time for finished games
                    if fixture.end_time and fixture.status == "finished":
                        # Write to dedicated column
                        if hasattr(event, "statpal_end_time") and not event.statpal_end_time:
                            event.statpal_end_time = fixture.end_time
                            updated = True
                        # Also write to JSONB for backward compatibility
                        sources = event.win_probability_sources or {}
                        if "statpal_end_time" not in sources:
                            sources["statpal_end_time"] = fixture.end_time.isoformat()
                            event.win_probability_sources = sources
                            updated = True

                    # Update scores from live data if available
                    if live_data and live_data.status == "live":
                        if live_data.home_score is not None:
                            event.home_score = live_data.home_score
                        if live_data.away_score is not None:
                            event.away_score = live_data.away_score
                        updated = True

                    if updated:
                        sport_updated += 1

                # Create events for live games missing from DB (playoff gap fix).
                # StatPal season-schedule doesn't include playoffs, but livescores does.
                from app.services.event_registry import (
                    find_or_create_event, EventIdentity, EventClaim,
                )
                live_created = 0
                for live_fix in live:
                    if not live_fix.home_team or not live_fix.away_team:
                        continue
                    if not live_fix.start_time:
                        continue
                    key = _fixture_match_key(live_fix.home_team, live_fix.away_team)
                    # Check if we already have this game
                    existing = await session.execute(
                        select(Event.id).where(
                            Event.sport_id == sport_id,
                            func.lower(Event.home_team_name) == live_fix.home_team.lower(),
                            func.lower(Event.away_team_name) == live_fix.away_team.lower(),
                            Event.commence_time.between(
                                live_fix.start_time - timedelta(hours=6),
                                live_fix.start_time + timedelta(hours=6),
                            ),
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        continue
                    # Create the missing event
                    claim_id = live_fix.fixture_id or f"statpal_live_{live_fix.home_team}_{live_fix.away_team}"
                    identity = EventIdentity(
                        sport_key=our_key,
                        home_team_name=live_fix.home_team,
                        away_team_name=live_fix.away_team,
                        commence_time=live_fix.start_time,
                        claim=EventClaim("statpal", claim_id),
                        commence_time_source="statpal",
                        status="live",
                    )
                    event, was_created = await find_or_create_event(
                        session, identity,
                    )
                    if was_created:
                        live_created += 1
                        if live_fix.home_score is not None:
                            event.home_score = live_fix.home_score
                        if live_fix.away_score is not None:
                            event.away_score = live_fix.away_score
                        logger.info(
                            "Created event from live StatPal: %s vs %s (%s)",
                            live_fix.away_team, live_fix.home_team, our_key,
                        )
                sport_created += live_created

                total_updated += sport_updated
                total_created += sport_created
                details.append({
                    "sport": our_key,
                    "fixtures_fetched": len(fixtures),
                    "events_updated": sport_updated,
                    "events_created": sport_created,
                    "live_games": len(live),
                    "live_created": live_created,
                })

                # Rate limit between sports
                await asyncio.sleep(0.5)

    finally:
        await service.close()

    return {
        "events_updated": total_updated,
        "events_created": total_created,
        "total_fixtures_fetched": total_fixtures,
        "sports": details,
    }


async def _sync_statpal_injuries(sport_key: Optional[str] = None) -> dict:
    """Sync injury reports from StatPal for line movement analysis.

    Injuries are stored in the LineMovementAnalysis table as structured context,
    making them available for "Why Did the Line Move?" LLM explanations.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with injury counts per sport.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    if not sport_keys:
        return {"skipped": True, "reason": f"sport_key {sport_key!r} not in STATPAL_SPORT_MAPPING"}

    service = StatPalAPIService()
    total_injuries = 0
    total_events_enriched = 0
    details = []

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                # Find the Sport record
                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    continue

                sport_id = sport_row.id

                injuries = await service.get_injuries(statpal_sport)
                if not injuries:
                    details.append({"sport": our_key, "injuries_fetched": 0, "events_enriched": 0})
                    await asyncio.sleep(0.3)
                    continue

                # Group injuries by team name for efficient event lookup
                injuries_by_team: dict[str, list] = {}
                for inj in injuries:
                    team_lower = inj.team.lower()
                    if team_lower not in injuries_by_team:
                        injuries_by_team[team_lower] = []
                    injuries_by_team[team_lower].append(inj)

                # Find upcoming/live events for this sport to attach injuries to
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=6)
                window_end = now + timedelta(days=2)

                result = await session.execute(
                    select(Event).where(
                        Event.sport_id == sport_id,
                        Event.commence_time.between(window_start, window_end),
                        Event.status.in_(["scheduled", "live"]),
                    )
                )
                events = result.scalars().all()

                sport_enriched = 0
                for event in events:
                    event_injuries = []

                    # Match injuries to event by team name
                    for team_name in [event.home_team_name, event.away_team_name]:
                        team_lower = team_name.lower()
                        # Check exact match and suffix match
                        for key, team_injuries in injuries_by_team.items():
                            if key == team_lower or key.endswith(team_lower.split()[-1]) or team_lower.endswith(key.split()[-1]):
                                event_injuries.extend(team_injuries)

                    if event_injuries:
                        # Store injury context in win_probability_sources JSONB
                        sources = event.win_probability_sources or {}
                        sources["statpal_injuries"] = [
                            {
                                "player": inj.player_name,
                                "team": inj.team,
                                "status": inj.status,
                                "type": inj.injury_type,
                                "detail": inj.detail,
                            }
                            for inj in event_injuries[:10]  # Cap at 10 per event
                        ]
                        sources["statpal_injuries_updated"] = now.isoformat()
                        event.win_probability_sources = sources
                        sport_enriched += 1

                total_injuries += len(injuries)
                total_events_enriched += sport_enriched
                details.append({
                    "sport": our_key,
                    "injuries_fetched": len(injuries),
                    "events_enriched": sport_enriched,
                })

                await asyncio.sleep(0.3)

    finally:
        await service.close()

    return {
        "total_injuries": total_injuries,
        "events_enriched": total_events_enriched,
        "sports": details,
    }


async def _sync_statpal_live_plays(sport_key: Optional[str] = None) -> dict:
    """Fetch play-by-play data for live games from StatPal.

    Writes ALL plays to the scoring_plays table (persistent, queryable).
    This data feeds into "Why Did the Line Move?" by correlating specific
    plays with odds movements (e.g., "Odds jumped 9% after a Tatum three
    that capped a 12-0 run").

    Also keeps last 10 plays in JSONB for backward compatibility.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with play counts.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    from app.tasks.config import STATPAL_PBP_SPORTS

    # Only attempt PBP for sports that actually support it (NFL only).
    # Other sports return 404, wasting API calls.
    if sport_key:
        statpal_sport_id = STATPAL_SPORT_MAPPING.get(sport_key)
        sport_keys = [sport_key] if statpal_sport_id and statpal_sport_id in STATPAL_PBP_SPORTS else []
    else:
        sport_keys = [
            k for k, v in STATPAL_SPORT_MAPPING.items()
            if v in STATPAL_PBP_SPORTS
        ]

    if not sport_keys:
        return {"skipped": True, "reason": "no PBP-capable sports to sync"}

    service = StatPalAPIService()
    total_plays = 0
    total_events = 0
    total_rows_inserted = 0
    details = []

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport
            from app.models.models import ScoringPlay, ScoreSnapshot

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    continue

                sport_id = sport_row.id

                # Find live events with StatPal fixture IDs
                result = await session.execute(
                    select(Event).where(
                        Event.sport_id == sport_id,
                        Event.status == "live",
                    )
                )
                live_events = result.scalars().all()

                sport_plays = 0
                sport_events = 0
                sport_rows_inserted = 0

                for event in live_events:
                    statpal_id = _get_statpal_id(event)
                    if not statpal_id:
                        continue

                    plays = await service.get_play_by_play(statpal_sport, statpal_id)
                    if not plays:
                        continue

                    # --- Write ALL plays to scoring_plays table (persistent) ---
                    # Dedup: check which (period, game_clock) combos already exist
                    existing_result = await session.execute(
                        select(
                            ScoringPlay.period,
                            ScoringPlay.game_clock,
                            ScoringPlay.description,
                        ).where(
                            ScoringPlay.event_id == event.id,
                            ScoringPlay.source == "statpal",
                        )
                    )
                    existing_keys = {
                        (r.period, r.game_clock, r.description)
                        for r in existing_result.all()
                    }

                    new_plays = []
                    for p in plays:
                        dedup_key = (p.period, p.clock, (p.description or "")[:500])
                        if dedup_key in existing_keys:
                            continue
                        existing_keys.add(dedup_key)  # Prevent dupes within this batch
                        new_plays.append(
                            ScoringPlay(
                                event_id=event.id,
                                source="statpal",
                                period=p.period,
                                game_clock=p.clock,
                                description=(p.description or "")[:500],
                                play_type=p.play_type,
                                team_name=p.team,
                                player_name=p.player,
                                home_score=p.home_score,
                                away_score=p.away_score,
                            )
                        )

                    if new_plays:
                        session.add_all(new_plays)
                        sport_rows_inserted += len(new_plays)

                        # --- Enrich score history from play-by-play ---
                        # Write ScoreSnapshot for each score transition in new plays.
                        # This fills gaps in the sparse score data from odds polling,
                        # giving the Score Differential chart a continuous line.
                        last_score_result = await session.execute(
                            select(ScoreSnapshot.home_score, ScoreSnapshot.away_score)
                            .where(ScoreSnapshot.event_id == event.id)
                            .order_by(ScoreSnapshot.captured_at.desc())
                            .limit(1)
                        )
                        last_score = last_score_result.first()
                        prev_h = last_score.home_score if last_score else None
                        prev_a = last_score.away_score if last_score else None

                        score_snaps = []
                        for sp in new_plays:
                            if sp.home_score is not None and sp.away_score is not None:
                                if sp.home_score != prev_h or sp.away_score != prev_a:
                                    score_snaps.append(ScoreSnapshot(
                                        event_id=event.id,
                                        home_score=sp.home_score,
                                        away_score=sp.away_score,
                                    ))
                                    prev_h = sp.home_score
                                    prev_a = sp.away_score

                        if score_snaps:
                            session.add_all(score_snaps)

                    # --- Backward compat: last 10 plays in JSONB ---
                    recent_plays = plays[-10:]
                    sources = event.win_probability_sources or {}
                    sources["statpal_plays"] = [
                        {
                            "period": p.period,
                            "clock": p.clock,
                            "description": p.description[:200],
                            "type": p.play_type,
                            "team": p.team,
                            "player": p.player,
                            "home_score": p.home_score,
                            "away_score": p.away_score,
                            "captured_at": datetime.now(timezone.utc).isoformat(),
                        }
                        for p in recent_plays
                    ]
                    sources["statpal_plays_updated"] = datetime.now(timezone.utc).isoformat()
                    event.win_probability_sources = sources

                    sport_plays += len(plays)
                    sport_events += 1

                    # Rate limit between games
                    await asyncio.sleep(0.5)

                # Flush after each sport to persist rows
                if sport_rows_inserted > 0:
                    await session.flush()

                total_plays += sport_plays
                total_events += sport_events
                total_rows_inserted += sport_rows_inserted
                if sport_events > 0:
                    details.append({
                        "sport": our_key,
                        "live_events_with_plays": sport_events,
                        "total_plays": sport_plays,
                        "rows_inserted": sport_rows_inserted,
                    })

    finally:
        await service.close()

    return {
        "total_plays": total_plays,
        "live_events_with_plays": total_events,
        "rows_inserted": total_rows_inserted,
        "sports": details,
    }


async def _sync_statpal_livescores() -> dict:
    """Poll StatPal livescores for real-time game state updates.

    StatPal updates livescores every 15 seconds across all 13 sports.
    This task runs every 30 seconds and updates:
    - Current score (home_score, away_score)
    - Game period/status via ScoreSnapshot enrichment
    - Event status transitions (live → completed)

    Unlike the hourly schedule sync, this is a lightweight call that only
    hits the livescores endpoint (not the full season schedule).
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    service = StatPalAPIService()
    total_updated = 0
    total_score_snaps = 0
    details = []

    # Only poll sports that are likely to have live games right now.
    # We check which sports have live events in our DB first, then
    # only call StatPal livescores for those sports.
    try:
        async with get_task_session() as session:
            from app.models import Event, Sport
            from app.models.models import ScoreSnapshot

            # Find which StatPal sports have live events
            live_sport_result = await session.execute(
                select(Sport.key, Sport.id).join(
                    Event, Event.sport_id == Sport.id
                ).where(
                    Event.status == "live"
                ).distinct()
            )
            live_sports = {
                row.key: row.id
                for row in live_sport_result.all()
                if row.key in STATPAL_SPORT_MAPPING
            }

            if not live_sports:
                return {"skipped": True, "reason": "no live events for StatPal sports"}

            # Deduplicate StatPal sport identifiers (multiple leagues → same sport)
            seen_statpal_sports: set[str] = set()

            for our_key, sport_id in live_sports.items():
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                # Skip if we already polled this StatPal sport (e.g., multiple soccer leagues)
                if statpal_sport in seen_statpal_sports:
                    continue
                seen_statpal_sports.add(statpal_sport)

                live_fixtures = await service.get_live_scores(statpal_sport)
                if not live_fixtures:
                    continue

                # Build lookup by team names
                fixture_by_teams: dict[str, object] = {}
                for f in live_fixtures:
                    key = _fixture_match_key(f.home_team, f.away_team)
                    fixture_by_teams[key] = f

                # Find our live events for ALL sport keys that map to this StatPal sport
                matching_sport_keys = [
                    k for k, v in STATPAL_SPORT_MAPPING.items()
                    if v == statpal_sport and k in live_sports
                ]
                sport_ids = [live_sports[k] for k in matching_sport_keys]

                events_result = await session.execute(
                    select(Event).where(
                        Event.sport_id.in_(sport_ids),
                        Event.status == "live",
                    )
                )
                live_events = events_result.scalars().all()

                sport_updated = 0
                sport_snaps = 0

                for event in live_events:
                    match_key = _fixture_match_key(
                        event.home_team_name or "",
                        event.away_team_name or "",
                    )
                    fixture = fixture_by_teams.get(match_key)
                    if not fixture:
                        continue

                    updated = False

                    # Update period/clock from StatPal raw_status (e.g., "Q3", "1H", "HT")
                    if fixture.raw_status and fixture.raw_status not in ("live", "Live"):
                        if event.period != fixture.raw_status:
                            event.period = fixture.raw_status
                            updated = True

                    # Update scores
                    if fixture.home_score is not None and fixture.home_score != event.home_score:
                        event.home_score = fixture.home_score
                        updated = True
                    if fixture.away_score is not None and fixture.away_score != event.away_score:
                        event.away_score = fixture.away_score
                        updated = True

                    # Write ScoreSnapshot for score enrichment (feeds Score Differential chart)
                    if updated and fixture.home_score is not None and fixture.away_score is not None:
                        # Check if this score is different from the last snapshot
                        last_snap_result = await session.execute(
                            select(ScoreSnapshot.home_score, ScoreSnapshot.away_score)
                            .where(ScoreSnapshot.event_id == event.id)
                            .order_by(ScoreSnapshot.captured_at.desc())
                            .limit(1)
                        )
                        last_snap = last_snap_result.first()
                        if (
                            not last_snap
                            or last_snap.home_score != fixture.home_score
                            or last_snap.away_score != fixture.away_score
                        ):
                            session.add(ScoreSnapshot(
                                event_id=event.id,
                                home_score=fixture.home_score,
                                away_score=fixture.away_score,
                            ))
                            sport_snaps += 1

                    # Link StatPal fixture ID if not already linked
                    if fixture.fixture_id and not _get_statpal_id(event):
                        _set_statpal_id(event, fixture.fixture_id)
                        updated = True

                    if updated:
                        sport_updated += 1

                total_updated += sport_updated
                total_score_snaps += sport_snaps
                details.append({
                    "sport": statpal_sport,
                    "live_fixtures": len(live_fixtures),
                    "events_updated": sport_updated,
                    "score_snapshots": sport_snaps,
                })

    finally:
        await service.close()

    return {
        "events_updated": total_updated,
        "score_snapshots_created": total_score_snaps,
        "sports_polled": len(details),
        "sports": details,
    }


async def _sync_statpal_rosters(sport_key: Optional[str] = None) -> dict:
    """Sync team rosters from StatPal, supplementing ESPN data.

    StatPal provides roster data with positions and jersey numbers. This
    supplements the existing ESPN + MLB Stats API roster sync by providing
    an additional data source with potentially better coverage for some sports.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with update counts.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    service = StatPalAPIService()
    total_updated = 0
    details = []

    try:
        async with get_task_session() as session:
            from app.models import Team, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    continue

                sport_id = sport_row.id

                # Fetch teams from StatPal
                statpal_teams = await service.get_teams(statpal_sport)
                if not statpal_teams:
                    details.append({"sport": our_key, "status": "no_teams_from_statpal"})
                    continue

                # Get our DB teams for matching
                result = await session.execute(
                    select(Team).where(Team.sport_id == sport_id)
                )
                db_teams = result.scalars().all()

                # Build name lookup
                db_by_name: dict[str, Team] = {}
                for t in db_teams:
                    db_by_name[t.name.lower()] = t
                    parts = t.name.split()
                    if len(parts) >= 2:
                        db_by_name[parts[-1].lower()] = t

                sport_updated = 0
                for sp_team in statpal_teams:
                    # Match StatPal team to our DB team
                    db_team = db_by_name.get(sp_team.name.lower())
                    if not db_team and sp_team.short_name:
                        db_team = db_by_name.get(sp_team.short_name.lower())

                    if not db_team:
                        continue

                    # Register identity mapping for future lookups
                    from app.services.team_identity import team_identity_service
                    await team_identity_service.register_team_identity(
                        session, db_team.id, "statpal", our_key,
                        source_id=sp_team.team_id if hasattr(sp_team, 'team_id') else None,
                        source_name=sp_team.name,
                    )

                    # Only update roster if we don't already have ESPN data
                    # (ESPN is our primary source — StatPal supplements gaps)
                    if db_team.roster_players:
                        continue

                    # Fetch roster
                    players = await service.get_roster(statpal_sport, sp_team.team_id)
                    if not players:
                        continue

                    # Build roster_players JSONB entries
                    import unicodedata

                    entries = []
                    seen = set()
                    for p in players:
                        if p.name in seen:
                            continue
                        seen.add(p.name)

                        entry = {"name": p.name}
                        if p.position:
                            entry["position"] = p.position
                        entries.append(entry)

                        # ASCII variant for matching
                        ascii_name = "".join(
                            c for c in unicodedata.normalize("NFD", p.name)
                            if unicodedata.category(c) != "Mn"
                        )
                        if ascii_name != p.name and ascii_name not in seen:
                            seen.add(ascii_name)
                            entries.append(ascii_name)

                    entries.sort(key=lambda x: x["name"] if isinstance(x, dict) else x)

                    await session.execute(
                        update(Team)
                        .where(Team.id == db_team.id)
                        .values(roster_players=entries)
                    )
                    sport_updated += 1

                    await asyncio.sleep(0.3)

                total_updated += sport_updated
                details.append({
                    "sport": our_key,
                    "statpal_teams": len(statpal_teams),
                    "teams_updated": sport_updated,
                })

    finally:
        await service.close()

    return {
        "teams_updated": total_updated,
        "sports": details,
    }


# =============================================================================
# Helper functions
# =============================================================================


def _fixture_match_key(home: str, away: str) -> str:
    """Create a normalized key for matching fixtures to events."""
    import unicodedata

    def _normalize(s: str) -> str:
        s = "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )
        return s.lower().strip()

    return f"{_normalize(home)}|{_normalize(away)}"


async def _find_matching_event(session, Event, sport_id: int, fixture) -> Optional:
    """Find a matching Event record for a StatPal fixture.

    Uses token-overlap name matching + time proximity (±6 hours) to find the best match.
    """
    from app.utils.name_normalization import token_overlap_score, normalize_name

    if not fixture.home_team or not fixture.away_team:
        return None

    home_lower = normalize_name(fixture.home_team)
    away_lower = normalize_name(fixture.away_team)

    # Build time window
    if fixture.start_time:
        window_start = fixture.start_time - timedelta(hours=6)
        window_end = fixture.start_time + timedelta(hours=6)
    else:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=1)
        window_end = now + timedelta(days=7)

    # Query for candidates — broader filter using multiple last-word tokens
    # to catch more candidates for scoring
    from sqlalchemy import func as sqlfunc

    # Use last meaningful word from each team (skip 1-char words)
    home_words = [w for w in home_lower.split() if len(w) > 2]
    away_words = [w for w in away_lower.split() if len(w) > 2]
    home_last = home_words[-1] if home_words else home_lower.split()[-1]
    away_last = away_words[-1] if away_words else away_lower.split()[-1]

    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.commence_time.between(window_start, window_end),
            or_(
                sqlfunc.lower(Event.home_team_name).contains(home_last),
                sqlfunc.lower(Event.away_team_name).contains(away_last),
                sqlfunc.lower(Event.home_team_name).contains(home_words[0] if home_words else home_last),
                sqlfunc.lower(Event.away_team_name).contains(away_words[0] if away_words else away_last),
            ),
        ).limit(20)
    )
    candidates = result.scalars().all()

    if not candidates:
        return None

    # Score candidates using token_overlap_score for robust name matching
    best = None
    best_score = -1.0

    for event in candidates:
        home_score = token_overlap_score(fixture.home_team, event.home_team_name)
        away_score = token_overlap_score(fixture.away_team, event.away_team_name)

        # Require both teams to match at some level
        if home_score < 0.4 or away_score < 0.4:
            continue

        score = home_score + away_score  # 0.0 - 2.0

        # Time proximity bonus (up to 0.3)
        if fixture.start_time and event.commence_time:
            diff_hours = abs((fixture.start_time - event.commence_time).total_seconds()) / 3600
            if diff_hours < 1:
                score += 0.3
            elif diff_hours < 3:
                score += 0.2
            elif diff_hours < 6:
                score += 0.1

        if score > best_score:
            best_score = score
            best = event

    # Require minimum combined score of 1.0 (both teams at least partially match)
    return best if best_score >= 1.0 else None


def _get_statpal_id(event) -> Optional[str]:
    """Get the StatPal fixture ID stored on an event."""
    # Prefer the dedicated column, fall back to JSONB
    if hasattr(event, "statpal_fixture_id") and event.statpal_fixture_id:
        return event.statpal_fixture_id
    sources = event.win_probability_sources or {}
    return sources.get("statpal_fixture_id")


def _set_statpal_id(event, fixture_id: str):
    """Store the StatPal fixture ID on an event."""
    # Write to dedicated column
    if hasattr(event, "statpal_fixture_id"):
        event.statpal_fixture_id = fixture_id
    # Also write to JSONB for backward compatibility during migration
    sources = event.win_probability_sources or {}
    sources["statpal_fixture_id"] = fixture_id
    event.win_probability_sources = sources


# =============================================================================
# Standings sync
# =============================================================================


async def _sync_statpal_standings(sport_key: Optional[str] = None) -> dict:
    """Sync league standings from StatPal and store on Team records.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with update counts.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    service = StatPalAPIService()
    total_updated = 0
    details = []
    now = datetime.now(timezone.utc)

    try:
        async with get_task_session() as session:
            from app.models import Team, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    details.append({"sport": our_key, "status": "sport_not_found"})
                    continue

                sport_id = sport_row.id

                # Fetch standings from StatPal
                standings_data = await service.get_standings(statpal_sport)
                if not standings_data:
                    details.append({"sport": our_key, "status": "no_standings"})
                    continue

                # Get our DB teams for matching
                result = await session.execute(
                    select(Team).where(Team.sport_id == sport_id)
                )
                db_teams = result.scalars().all()

                # Build name lookup (lowercase name → Team)
                db_by_name: dict[str, Team] = {}
                for t in db_teams:
                    db_by_name[t.name.lower()] = t
                    if t.alternate_names:
                        for alt in t.alternate_names:
                            db_by_name[alt.lower()] = t

                sport_updated = 0

                # Parse standings — StatPal returns nested format:
                # {"standings": {"tournament": {"league": [{"division": [{"team": [...]}]}]}}}
                teams_list = []
                if isinstance(standings_data, list):
                    teams_list = standings_data
                elif isinstance(standings_data, dict):
                    inner = standings_data.get("standings", standings_data)
                    if isinstance(inner, list):
                        teams_list = inner
                    elif isinstance(inner, dict):
                        # Navigate: tournament.league[].division[].team[]
                        tournament = inner.get("tournament", inner)
                        if isinstance(tournament, dict):
                            leagues = tournament.get("league", [])
                            if isinstance(leagues, dict):
                                leagues = [leagues]
                            for league in leagues:
                                if not isinstance(league, dict):
                                    continue
                                league_name = league.get("name", "")
                                divisions = league.get("division", [])
                                if isinstance(divisions, dict):
                                    divisions = [divisions]
                                for div in divisions:
                                    if not isinstance(div, dict):
                                        continue
                                    div_name = div.get("name", "")
                                    div_teams = div.get("team", [])
                                    if isinstance(div_teams, dict):
                                        div_teams = [div_teams]
                                    for t in div_teams:
                                        if isinstance(t, dict):
                                            # Inject conference/division from structure
                                            t["_conference"] = league_name
                                            t["_division"] = div_name
                                            teams_list.append(t)
                        # Fallback: groups/teams patterns
                        if not teams_list:
                            if "groups" in inner:
                                for group in inner.get("groups", []):
                                    teams_list.extend(group.get("teams", []))
                            elif "teams" in inner:
                                teams_list = inner["teams"]
                    if not teams_list:
                        logger.info(f"Standings for {our_key}: unexpected format, keys={list(standings_data.keys())}")

                logger.info(f"Standings for {our_key}: parsed {len(teams_list)} teams")

                for team_entry in teams_list:
                    if not isinstance(team_entry, dict):
                        continue

                    # Try to match to our team
                    team_name = (team_entry.get("name") or team_entry.get("team_name") or "").strip()
                    if not team_name:
                        continue

                    db_team = db_by_name.get(team_name.lower())
                    if not db_team:
                        # Try suffix match (e.g., "Celtics" matches "Boston Celtics")
                        last_word = team_name.split()[-1].lower()
                        for key, t in db_by_name.items():
                            if key.endswith(last_word) or last_word in key:
                                db_team = t
                                break

                    if not db_team:
                        logger.debug(f"Standings: no match for '{team_name}' in {our_key}")
                        continue

                    # Extract standings fields — map StatPal names to our canonical names
                    parsed = {}
                    # StatPal uses "won"/"lost", we normalize to "wins"/"losses"
                    wins = team_entry.get("won") or team_entry.get("wins")
                    losses = team_entry.get("lost") or team_entry.get("losses")
                    if wins is not None:
                        parsed["wins"] = int(wins)
                    if losses is not None:
                        parsed["losses"] = int(losses)

                    # Direct fields — numeric
                    for src, dst in [
                        ("draws", "draws"), ("ties", "ties"),
                        ("points", "points"),
                        ("goals_for", "goals_for"), ("goals_against", "goals_against"),
                        ("goal_difference", "goal_difference"),
                        ("position", "conf_rank"),
                    ]:
                        val = team_entry.get(src)
                        if val is not None:
                            try:
                                parsed[dst] = int(val)
                            except (ValueError, TypeError):
                                parsed[dst] = val

                    # Direct fields — string/mixed
                    for src, dst in [
                        ("gb", "games_behind"),
                        ("streak", "streak"),
                        ("last_10", "last_10"),
                        ("home_record", "home_record"),
                        ("road_record", "road_record"),
                    ]:
                        val = team_entry.get(src)
                        if val is not None:
                            parsed[dst] = val

                    # Win percentage — use StatPal's "percentage" or compute
                    pct = team_entry.get("percentage") or team_entry.get("pct")
                    if pct:
                        parsed["pct"] = str(pct)
                    elif "wins" in parsed and "losses" in parsed:
                        w, l = parsed["wins"], parsed["losses"]
                        if w + l > 0:
                            parsed["pct"] = f".{round(1000 * w / (w + l)):03d}"

                    # Conference/division from structure (injected during parsing)
                    if team_entry.get("_conference"):
                        parsed["conference"] = team_entry["_conference"]
                    if team_entry.get("_division"):
                        parsed["division"] = team_entry["_division"]

                    if parsed:
                        db_team.standings_data = parsed
                        db_team.standings_updated_at = now
                        sport_updated += 1

                total_updated += sport_updated
                details.append({
                    "sport": our_key,
                    "teams_in_standings": len(teams_list),
                    "teams_updated": sport_updated,
                })

                await asyncio.sleep(0.3)

    finally:
        await service.close()

    return {
        "total_teams_updated": total_updated,
        "details": details,
    }


# =============================================================================
# Team stats sync
# =============================================================================


async def _sync_statpal_team_stats(sport_key: Optional[str] = None) -> dict:
    """Sync season-level team statistics from StatPal.

    Args:
        sport_key: If provided, only sync this sport.

    Returns:
        Summary dict with update counts.
    """
    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set"}

    if sport_key:
        sport_keys = [sport_key] if sport_key in STATPAL_SPORT_MAPPING else []
    else:
        sport_keys = list(STATPAL_SPORT_MAPPING.keys())

    service = StatPalAPIService()
    total_updated = 0
    details = []
    now = datetime.now(timezone.utc)

    try:
        async with get_task_session() as session:
            from app.models import Team, Sport

            for our_key in sport_keys:
                statpal_sport = STATPAL_SPORT_MAPPING[our_key]

                sport_result = await session.execute(
                    select(Sport.id).where(Sport.key == our_key)
                )
                sport_row = sport_result.first()
                if not sport_row:
                    continue

                sport_id = sport_row.id

                # Get teams with statpal_team_id
                result = await session.execute(
                    select(Team).where(
                        Team.sport_id == sport_id,
                        Team.statpal_team_id.isnot(None),
                    )
                )
                teams = result.scalars().all()

                sport_updated = 0
                for team in teams:
                    stats_data = await service.get_team_stats(
                        statpal_sport, team.statpal_team_id
                    )
                    if stats_data and isinstance(stats_data, dict):
                        team.season_stats = stats_data
                        team.season_stats_updated_at = now
                        sport_updated += 1

                    # Rate limit between teams
                    await asyncio.sleep(0.5)

                total_updated += sport_updated
                details.append({
                    "sport": our_key,
                    "teams_with_statpal_id": len(teams),
                    "teams_updated": sport_updated,
                })

    finally:
        await service.close()

    return {
        "total_teams_updated": total_updated,
        "details": details,
    }
