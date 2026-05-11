"""
Sport sync and event discovery tasks.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import insert

from app.models import Sport, Event, OddsSnapshot, Team
from app.services.odds_api import OddsAPIService
from app.tasks.base import get_task_session, run_async
from app.utils.name_normalization import names_match as _canonical_names_match
from app.tasks.config import (
    DISCOVER_TIER1_INTERVAL,
    DISCOVER_TIER2_INTERVAL,
    DISCOVER_TIER3_INTERVAL,
    DISCOVER_TIER4_INTERVAL,
)
from app.tasks.redis_state import get_redis_client, check_quota_guard

logger = logging.getLogger(__name__)

# Tier → discovery interval mapping
_DISCOVER_INTERVALS = {
    1: DISCOVER_TIER1_INTERVAL,
    2: DISCOVER_TIER2_INTERVAL,
    3: DISCOVER_TIER3_INTERVAL,
    4: DISCOVER_TIER4_INTERVAL,
}


def _get_discover_interval(sport_key: str) -> int:
    """Get the discovery polling interval for a sport based on its league tier."""
    from app.utils.highlights import LEAGUE_TIERS
    tier = LEAGUE_TIERS.get(sport_key, 4)
    return _DISCOVER_INTERVALS.get(tier, DISCOVER_TIER4_INTERVAL)


async def _sync_sports():
    """Async implementation of sync_sports."""
    service = OddsAPIService()

    try:
        sports_data = await service.get_sports()

        async with get_task_session() as session:
            synced = 0
            for sport in sports_data:
                if not sport.get("active", False):
                    continue

                # Upsert sport
                stmt = insert(Sport).values(
                    key=sport["key"],
                    name=sport["title"],
                    group=sport.get("group"),
                    active=True,
                ).on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "name": sport["title"],
                        "group": sport.get("group"),
                        "active": True,
                    }
                )
                await session.execute(stmt)
                synced += 1

            await session.commit()

        return {"synced": synced}
    finally:
        await service.close()


async def _find_statpal_event_for_odds_api(
    session, sport_id: int, home_team: str, away_team: str,
    commence_time: datetime
) -> Optional[Event]:
    """Find a StatPal-created event that matches an Odds API event.

    Only matches events that:
    1. Have no external_id (StatPal-created, not yet linked to Odds API)
    2. Are in the same sport
    3. Have matching team names (fuzzy)
    4. Are within 6 hours of the Odds API commence_time
    """
    window = timedelta(hours=6)
    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.external_id.is_(None),
            Event.commence_time.between(
                commence_time - window, commence_time + window
            ),
        ).limit(20)
    )
    candidates = result.scalars().all()

    logger.info(
        "StatPal match: looking for '%s' vs '%s' (sport_id=%d, time=%s) — "
        "%d candidates with external_id=NULL",
        home_team, away_team, sport_id, commence_time.isoformat(),
        len(candidates),
    )

    for candidate in candidates:
        # Check normal orientation
        home_match = _canonical_names_match(home_team, candidate.home_team_name)
        away_match = _canonical_names_match(away_team, candidate.away_team_name)

        # Check swapped home/away
        home_as_away = _canonical_names_match(home_team, candidate.away_team_name)
        away_as_home = _canonical_names_match(away_team, candidate.home_team_name)

        logger.info(
            "  candidate %d: '%s' vs '%s' (time=%s) — "
            "normal=%s/%s swapped=%s/%s",
            candidate.id, candidate.home_team_name, candidate.away_team_name,
            candidate.commence_time.isoformat() if candidate.commence_time else "?",
            home_match, away_match, home_as_away, away_as_home,
        )

        if home_match and away_match:
            logger.info("  → MATCHED (normal orientation)")
            return candidate

        if home_as_away and away_as_home:
            logger.info("  → MATCHED (swapped home/away)")
            return candidate

    logger.info("  → NO MATCH found among %d candidates", len(candidates))
    return None


async def _find_existing_event_by_teams(
    session, sport_id: int, home_team: str, away_team: str,
    commence_time: datetime, exclude_external_id: Optional[str] = None,
) -> Optional[Event]:
    """Broader dedup safety net: find ANY existing event with matching teams + time.

    Unlike _find_statpal_event_for_odds_api (which only searches external_id=NULL),
    this searches ALL events regardless of external_id. Catches duplicates no matter
    which source created them.

    Args:
        exclude_external_id: Skip events that already have this external_id
            (they're the same event, not a duplicate).
    """
    window = timedelta(hours=3)
    result = await session.execute(
        select(Event).where(
            Event.sport_id == sport_id,
            Event.commence_time.between(
                commence_time - window, commence_time + window
            ),
        ).limit(50)
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        # Skip the event we're about to create (same external_id)
        if exclude_external_id and candidate.external_id == exclude_external_id:
            continue

        # Check normal orientation
        if _canonical_names_match(home_team, candidate.home_team_name) and \
           _canonical_names_match(away_team, candidate.away_team_name):
            return candidate

        # Check swapped home/away
        if _canonical_names_match(home_team, candidate.away_team_name) and \
           _canonical_names_match(away_team, candidate.home_team_name):
            return candidate

    return None


async def _external_id_in_use(session, external_id: str) -> Optional[int]:
    """Check if an external_id is already assigned to an event.

    Returns the event ID if found, None otherwise.  Used to prevent
    UniqueViolationError when attaching an Odds API external_id to a
    StatPal or orphan event — if another event already claimed it, skip.
    """
    result = await session.execute(
        select(Event.id).where(Event.external_id == external_id).limit(1)
    )
    return result.scalar_one_or_none()


async def _discover_events():
    """
    Async implementation of discover_events.

    Polls ALL active sports (not just those with upcoming events) to discover
    new games. This ensures NCAA basketball, etc. get picked up even if they
    currently have no events in the database.
    """
    # Emergency quota guard: block discovery when quota is low
    guard_ok, guard_reason = check_quota_guard("discover_events")
    if not guard_ok:
        logger.warning("discover_events SKIPPED by quota guard: %s", guard_reason)
        return {"skipped": True, "reason": f"quota_guard:{guard_reason}"}

    from app.tasks.odds_polling import _create_or_update_snapshot

    service = OddsAPIService()

    try:
        total_events = 0
        total_new_events = 0
        total_new_teams = 0
        total_espn_corrected = 0
        sports_polled = 0
        sports_skipped = 0

        # Get Redis client for per-sport discovery frequency gating
        try:
            r = get_redis_client()
        except Exception:
            r = None

        async with get_task_session() as session:
            # Get ALL active sports (not filtering by existing events)
            result = await session.execute(
                select(Sport).where(Sport.active == True)
            )
            sports = result.scalars().all()

            for sport in sports:
                sport_key = sport.key

                # Per-sport discovery frequency gating based on league tier
                discover_interval = _get_discover_interval(sport_key)
                if r:
                    try:
                        last_discover_key = f"bainluck:last_discover:{sport_key}"
                        last_discover = r.get(last_discover_key)
                        if last_discover:
                            elapsed = datetime.now(timezone.utc).timestamp() - float(last_discover.decode())
                            if elapsed < discover_interval:
                                sports_skipped += 1
                                continue
                    except Exception:
                        pass  # If Redis fails, just poll

                try:
                    # Fetch odds for this sport
                    # QUOTA OPTIMIZATION: Discovery only needs h2h from primary US
                    # books to detect new events. Full market/region coverage
                    # happens in poll_all_odds when games are imminent.
                    # This saves 5/6 of quota vs default (3 markets × 2 regions).
                    pre_used = service.last_requests_used
                    events_data = await service.get_odds(
                        sport_key,
                        regions="us",
                        markets="h2h",
                    )
                    sports_polled += 1

                    # Record successful discovery timestamp in Redis
                    if r:
                        try:
                            last_discover_key = f"bainluck:last_discover:{sport_key}"
                            r.set(last_discover_key, str(datetime.now(timezone.utc).timestamp()), ex=86400)
                        except Exception:
                            pass

                    # Record quota from response headers
                    if service.last_requests_remaining is not None:
                        from app.tasks.redis_state import record_odds_api_quota
                        record_odds_api_quota(
                            service.last_requests_remaining,
                            service.last_requests_used or 0,
                            "discover_events",
                            pre_call_used=pre_used,
                            sport_key=sport_key,
                        )

                    # Collect all team names from this sport's events
                    all_team_names: set[str] = set()

                    # Pre-fetch ESPN schedule for unique dates in this batch
                    # to correct commence_times at creation time (especially
                    # for college sports where StatPal doesn't cover)
                    espn_events_by_date: dict[str, list] = {}
                    from app.utils.sport_keys import SPORT_LEAGUE_MAP
                    if sport_key in SPORT_LEAGUE_MAP and events_data:
                        from app.services.espn_api import ESPNAPIService
                        unique_dates: set[str] = set()
                        for ed in events_data:
                            try:
                                ct = datetime.fromisoformat(
                                    ed["commence_time"].replace(
                                        "Z", "+00:00"
                                    )
                                )
                                # ESPN uses US Eastern time for date boundaries.
                                # A 10pm ET game on Apr 14 = 2am UTC Apr 15.
                                # Check BOTH UTC date and previous day.
                                unique_dates.add(ct.strftime("%Y%m%d"))
                                unique_dates.add(
                                    (ct - timedelta(days=1)).strftime("%Y%m%d")
                                )
                            except (ValueError, KeyError):
                                continue

                        if unique_dates:
                            espn_sched = ESPNAPIService()
                            try:
                                for date_str in unique_dates:
                                    try:
                                        espn_evts = (
                                            await espn_sched.get_scoreboard(
                                                sport_key, date=date_str
                                            )
                                        )
                                        if espn_evts:
                                            espn_events_by_date[
                                                date_str
                                            ] = espn_evts
                                    except Exception as e:
                                        logger.warning(
                                            f"ESPN schedule fetch failed "
                                            f"for {sport_key}/{date_str}"
                                            f": {e}"
                                        )
                            finally:
                                await espn_sched.close()

                    for event_data in events_data:
                        commence_time = datetime.fromisoformat(
                            event_data["commence_time"].replace("Z", "+00:00")
                        )

                        # Determine event status
                        now = datetime.now(timezone.utc)
                        if commence_time <= now:
                            event_status = "live"
                        else:
                            event_status = "scheduled"

                        # Cross-reference against pre-fetched ESPN schedule
                        # Check both UTC date and previous day (ESPN uses ET boundaries)
                        espn_commence_time = None
                        espn_event_id = None
                        if espn_events_by_date:
                            date_str = commence_time.strftime("%Y%m%d")
                            prev_date = (commence_time - timedelta(days=1)).strftime("%Y%m%d")
                            espn_candidates = (
                                espn_events_by_date.get(date_str, [])
                                + espn_events_by_date.get(prev_date, [])
                            )
                            for ee in espn_candidates:
                                if not ee.home_team or not ee.away_team:
                                    continue
                                espn_home = (
                                    ee.home_team.display_name
                                    or ee.home_team.name
                                    or ""
                                )
                                espn_away = (
                                    ee.away_team.display_name
                                    or ee.away_team.name
                                    or ""
                                )
                                if _canonical_names_match(
                                    event_data["home_team"], espn_home
                                ) and _canonical_names_match(
                                    event_data["away_team"], espn_away
                                ):
                                    espn_commence_time = ee.date
                                    espn_event_id = ee.espn_id
                                    break

                            if espn_commence_time:
                                time_diff = abs(
                                    (
                                        espn_commence_time - commence_time
                                    ).total_seconds()
                                )
                                if time_diff > 300:
                                    logger.info(
                                        f"ESPN schedule correction for "
                                        f"{sport_key}: "
                                        f"{event_data['home_team']} vs "
                                        f"{event_data['away_team']}: "
                                        f"{commence_time.isoformat()} -> "
                                        f"{espn_commence_time.isoformat()}"
                                        f" (diff: {time_diff/3600:.1f}h)"
                                    )
                                    total_espn_corrected += 1
                                # Re-evaluate status with corrected time
                                if espn_commence_time > now:
                                    event_status = "scheduled"
                                elif event_status == "scheduled":
                                    event_status = "live"

                        # ── Unified event matching via Event Registry ──
                        from app.services.event_registry import (
                            find_or_create_event, EventIdentity, EventClaim,
                        )
                        identity = EventIdentity(
                            sport_key=sport_key,
                            home_team_name=event_data["home_team"],
                            away_team_name=event_data["away_team"],
                            commence_time=espn_commence_time or commence_time,
                            claim=EventClaim("odds_api", event_data["id"]),
                            commence_time_source="espn" if espn_commence_time else "odds_api",
                            status=event_status,
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        event_id = event.id

                        # Set ESPN ID if matched and not already set
                        if espn_event_id and not event.espn_id:
                            event.espn_id = espn_event_id

                        if was_created:
                            total_new_events += 1

                        total_events += 1

                        # Track team names for auto-creation below
                        all_team_names.add(event_data["home_team"])
                        all_team_names.add(event_data["away_team"])

                        # Also save odds snapshots for this event
                        # This ensures events discovered have odds data immediately
                        for bookmaker in event_data.get("bookmakers", []):
                            snapshot, is_new = await _create_or_update_snapshot(
                                session,
                                event_id,
                                bookmaker,
                                event_data
                            )
                            if is_new:
                                session.add(snapshot)

                    # Auto-create Team records for any teams not yet in the DB.
                    # This ensures college teams (Harvard, Brown, Stanford, etc.)
                    # get Team records even without ESPN scoreboard matching.
                    if all_team_names:
                        existing_result = await session.execute(
                            select(Team.name).where(
                                Team.sport_id == sport.id,
                                Team.name.in_(all_team_names),
                            )
                        )
                        existing_team_names = {
                            row[0] for row in existing_result.all()
                        }
                        new_team_names = all_team_names - existing_team_names
                        for team_name in new_team_names:
                            new_team = Team(
                                name=team_name,
                                sport_id=sport.id,
                            )
                            session.add(new_team)
                        if new_team_names:
                            await session.flush()  # Get IDs for identity registration

                            # Register Odds API identities for newly created teams
                            from app.services.team_identity import team_identity_service
                            for team_name in new_team_names:
                                # Look up the team we just created
                                team_result = await session.execute(
                                    select(Team).where(
                                        Team.name == team_name,
                                        Team.sport_id == sport.id,
                                    )
                                )
                                new_team_obj = team_result.scalar_one_or_none()
                                if new_team_obj:
                                    await team_identity_service.register_team_identity(
                                        session, new_team_obj.id, "odds_api", sport_key,
                                        source_name=team_name,
                                    )

                            total_new_teams += len(new_team_names)
                            logger.info(
                                f"Auto-created {len(new_team_names)} Team "
                                f"records for {sport_key}"
                            )

                    # Link team_ids on events that don't have them yet.
                    # This covers events created by both Odds API (this run)
                    # and StatPal (earlier). Without this, My Stuff SQL team
                    # ID filter misses events that only have team names.
                    if all_team_names:
                        team_map_result = await session.execute(
                            select(Team.name, Team.id).where(
                                Team.sport_id == sport.id,
                                Team.name.in_(all_team_names),
                            )
                        )
                        team_name_to_id = {
                            name: tid for name, tid in team_map_result.all()
                        }

                        if team_name_to_id:
                            from sqlalchemy import or_ as sql_or
                            unlinked_result = await session.execute(
                                select(Event).where(
                                    Event.sport_id == sport.id,
                                    sql_or(
                                        Event.home_team_id.is_(None),
                                        Event.away_team_id.is_(None),
                                    ),
                                    sql_or(
                                        Event.home_team_name.in_(
                                            team_name_to_id.keys()
                                        ),
                                        Event.away_team_name.in_(
                                            team_name_to_id.keys()
                                        ),
                                    ),
                                ).limit(200)
                            )
                            linked_count = 0
                            for evt in unlinked_result.scalars().all():
                                if (
                                    evt.home_team_id is None
                                    and evt.home_team_name in team_name_to_id
                                ):
                                    evt.home_team_id = team_name_to_id[
                                        evt.home_team_name
                                    ]
                                    linked_count += 1
                                if (
                                    evt.away_team_id is None
                                    and evt.away_team_name in team_name_to_id
                                ):
                                    evt.away_team_id = team_name_to_id[
                                        evt.away_team_name
                                    ]
                                    linked_count += 1
                            if linked_count:
                                logger.info(
                                    f"Linked {linked_count} team IDs on "
                                    f"events for {sport_key}"
                                )

                    # ── Post-creation audit: check for duplicates ──
                    if espn_events_by_date:
                        from app.services.event_registry import audit_event_counts
                        alerts = await audit_event_counts(
                            session, sport_key, espn_events_by_date
                        )
                        if alerts:
                            stats_key = "duplicate_alerts"
                            if stats_key not in locals():
                                duplicate_alerts = []
                            duplicate_alerts.extend(alerts)

                except Exception as e:
                    # Log but continue with other sports
                    logger.warning("Error discovering events for %s: %s", sport_key, e)
                    continue

            await session.commit()

        return {
            "sports_polled": sports_polled,
            "sports_skipped": sports_skipped,
            "events_found": total_events,
            "new_events": total_new_events,
            "new_teams": total_new_teams,
            "espn_corrected": total_espn_corrected,
        }
    finally:
        await service.close()


async def _merge_duplicate_events_impl(dry_run: bool = True):
    """Find and merge duplicate events. Runs as Celery background task."""
    from sqlalchemy import text as sa_text
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        # Find duplicate pairs — limited to 200 per run to avoid timeouts.
        # The task runs every 10 minutes so it drains the backlog over time.
        result = await session.execute(sa_text("""
            WITH dupes AS (
                SELECT a.id AS id_a, b.id AS id_b
                FROM events a
                JOIN events b ON (
                    a.sport_id = b.sport_id
                    AND a.id < b.id
                    AND LOWER(a.home_team_name) = LOWER(b.home_team_name)
                    AND LOWER(a.away_team_name) = LOWER(b.away_team_name)
                    AND ABS(EXTRACT(EPOCH FROM (a.commence_time - b.commence_time))) < 21600
                )
                WHERE a.commence_time > NOW() - INTERVAL '30 days'
                  AND b.commence_time > NOW() - INTERVAL '30 days'
                LIMIT 200
            )
            SELECT
                a.id AS id_a, a.external_id AS ext_a,
                EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = a.id LIMIT 1) AS has_snaps_a,
                a.statpal_fixture_id AS statpal_a, a.commence_time_source AS source_a,
                a.statpal_end_time AS end_a, a.home_team_id AS htid_a,
                a.away_team_id AS atid_a, a.espn_id AS espn_a,
                b.id AS id_b, b.external_id AS ext_b,
                EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = b.id LIMIT 1) AS has_snaps_b,
                b.statpal_fixture_id AS statpal_b, b.commence_time_source AS source_b,
                b.statpal_end_time AS end_b, b.home_team_id AS htid_b,
                b.away_team_id AS atid_b, b.espn_id AS espn_b,
                a.home_team_name, a.away_team_name
            FROM dupes d
            JOIN events a ON a.id = d.id_a
            JOIN events b ON b.id = d.id_b
        """))
        pairs = result.all()

        merged_count = 0
        skipped_count = 0
        delete_ids = []

        for row in pairs:
            keep_a = (row.ext_a is not None and row.has_snaps_a)
            keep_b = (row.ext_b is not None and row.has_snaps_b)

            if keep_a and not keep_b:
                keep_id, orphan_id = row.id_a, row.id_b
                orphan_has_snaps = row.has_snaps_b
                absorb = {
                    "statpal_fixture_id": row.statpal_b,
                    "commence_time_source": row.source_b,
                    "statpal_end_time": row.end_b,
                    "home_team_id": row.htid_b,
                    "away_team_id": row.atid_b,
                    "espn_id": row.espn_b,
                }
            elif keep_b and not keep_a:
                keep_id, orphan_id = row.id_b, row.id_a
                orphan_has_snaps = row.has_snaps_a
                absorb = {
                    "statpal_fixture_id": row.statpal_a,
                    "commence_time_source": row.source_a,
                    "statpal_end_time": row.end_a,
                    "home_team_id": row.htid_a,
                    "away_team_id": row.atid_a,
                    "espn_id": row.espn_a,
                }
            elif not keep_a and not keep_b:
                if row.statpal_a and not row.statpal_b:
                    keep_id, orphan_id = row.id_a, row.id_b
                    orphan_has_snaps = row.has_snaps_b
                    absorb = {}
                elif row.statpal_b and not row.statpal_a:
                    keep_id, orphan_id = row.id_b, row.id_a
                    orphan_has_snaps = row.has_snaps_a
                    absorb = {}
                else:
                    keep_id, orphan_id = row.id_a, row.id_b
                    orphan_has_snaps = row.has_snaps_b
                    absorb = {
                        "statpal_fixture_id": row.statpal_b,
                        "commence_time_source": row.source_b,
                        "statpal_end_time": row.end_b,
                        "home_team_id": row.htid_b,
                        "away_team_id": row.atid_b,
                        "espn_id": row.espn_b,
                    }
            else:
                # Both have external_id + snapshots — keep the richer one.
                # This handles The Odds API returning two IDs for the same game
                # (e.g., from different regions: us vs us2).
                keep_id, orphan_id = row.id_a, row.id_b
                orphan_has_snaps = row.has_snaps_b
                absorb = {
                    "statpal_fixture_id": row.statpal_b,
                    "commence_time_source": row.source_b,
                    "statpal_end_time": row.end_b,
                    "home_team_id": row.htid_b,
                    "away_team_id": row.atid_b,
                    "espn_id": row.espn_b,
                }

            if not dry_run:
                # Absorb metadata (only fill NULLs)
                non_null = {k: v for k, v in absorb.items() if v is not None}
                if non_null:
                    set_clauses = []
                    params = {"kid": keep_id}
                    for i, (field, value) in enumerate(non_null.items()):
                        set_clauses.append(f"{field} = COALESCE({field}, :v{i})")
                        params[f"v{i}"] = value
                    await session.execute(
                        sa_text(f"UPDATE events SET {', '.join(set_clauses)} WHERE id = :kid"),
                        params,
                    )
                # Reassign ALL FK references from orphan → keep before delete
                for table in ("odds_snapshots", "win_prob_snapshots", "score_snapshots",
                              "espn_snapshots", "scoring_plays", "odds_aggregated",
                              "line_movement_analyses", "futures_markets"):
                    await session.execute(
                        sa_text(f"UPDATE {table} SET event_id = :keep WHERE event_id = :orphan"),
                        {"keep": keep_id, "orphan": orphan_id},
                    )
                await session.execute(
                    sa_text("DELETE FROM events WHERE id = :orphan"),
                    {"orphan": orphan_id},
                )
                await session.commit()
                delete_ids.append(orphan_id)

            merged_count += 1

        if not dry_run and delete_ids:
            logger.info(f"Merged {merged_count} duplicate events, deleted {len(delete_ids)} orphans")

        return {
            "dry_run": dry_run,
            "merged": merged_count,
            "skipped": skipped_count,
            "deleted": len(delete_ids) if not dry_run else 0,
        }
