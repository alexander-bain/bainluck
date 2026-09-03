"""
Sport sync and event discovery tasks.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, case
from sqlalchemy.dialects.postgresql import insert

from app.models import Sport, Event, OddsSnapshot, Team
from app.services.event_registry import ODDS_LISTING_IS_NOT_A_DEREFERENCE
from app.services.odds_api import OddsAPIService
from app.tasks.base import get_task_session, run_async
from app.utils.event_child_repoint import repoint_event_children
from app.utils.match_receipts import record_twin_merge_receipts
from app.utils.name_normalization import names_match as _canonical_names_match
from app.utils.espn_candidate_selection import select_espn_candidate
from app.utils.espn_id_stamp import (
    REFUSED as ESPN_STAMP_REFUSED,
    stamp_espn_id_if_unheld,
)
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
        # #2017: espn_id stamps refused because another row already held the id.
        # A refusal is the guard WORKING and a duplicate existing — it must be
        # visible in the task summary, or the guard is indistinguishable from a
        # guard that never fired.
        total_espn_id_refused = 0
        claimed_espn_ids: set[str] = set()
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
                                        if espn_evts is None:
                                            # AUTHORITY DARK (lane1/045): ESPN
                                            # did not answer. Leave the date out
                                            # of the map entirely rather than
                                            # recording an empty slate.
                                            logger.warning(
                                                "ESPN schedule authority dark "
                                                f"for {sport_key}/{date_str}"
                                            )
                                        elif espn_evts:
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
                            # #1980: this pool spans TWO days on purpose (ESPN
                            # buckets by ET), so for an MLB series or a
                            # back-to-back it contains the SAME two clubs twice.
                            # Selecting on names alone and taking the first hit
                            # stamped the neighbouring day's game — the ±15/±30
                            # espn_id offsets against a correct commence_time
                            # that #1980's rail has been repairing. The selector
                            # breaks that tie on time, which is the only signal
                            # that tells the two games apart.
                            espn_commence_time, espn_event_id = (
                                select_espn_candidate(
                                    espn_candidates,
                                    event_data["home_team"],
                                    event_data["away_team"],
                                    commence_time,
                                )
                            )

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
                            # Ruling 048: NOT arm B — the Odds listing is not a
                            # dereference. An ESPN commence correction may refine
                            # the TIME, but it does not turn an odds_api listing id
                            # into a dereferenced one, and the claim here is still
                            # made in odds_api's name. If this path ever wants arm B
                            # it must claim as "espn" with the espn id it resolved.
                            claim=EventClaim(
                                "odds_api", event_data["id"],
                                schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE,
                            ),
                            commence_time_source="espn" if espn_commence_time else "odds_api",
                            status=event_status,
                        )
                        event, was_created = await find_or_create_event(
                            session, identity,
                        )
                        event_id = event.id

                        # Set ESPN ID if matched — but never onto a row when
                        # ANOTHER row already holds that id (#2017).
                        #
                        # This assignment used to be a raw column write that
                        # asked only "does THIS row have an espn_id?". Running
                        # in the same transaction as the CREATE above, it
                        # stamped the keeper's espn_id onto a freshly created
                        # duplicate — so the duplicate was BORN carrying a
                        # collision that a non-UNIQUE ix_events_espn_id accepts
                        # in silence. The id here came from a NAME match against
                        # the ESPN scoreboard, not a dereference (ruling 042);
                        # refusing is not an identity decision, it is a refusal
                        # to fabricate one.
                        if espn_event_id:
                            verdict, _holder = await stamp_espn_id_if_unheld(
                                session, event, espn_event_id,
                                context=f"discover_events[{sport_key}]",
                                claimed=claimed_espn_ids,
                            )
                            if verdict == ESPN_STAMP_REFUSED:
                                total_espn_id_refused += 1

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
                    # Uses fuzzy matching to avoid creating "Stanford" when
                    # "Stanford Cardinal" already exists (and vice versa).
                    if all_team_names:
                        existing_result = await session.execute(
                            select(Team.name).where(
                                Team.sport_id == sport.id,
                            )
                        )
                        existing_team_names = {
                            row[0] for row in existing_result.all()
                        }
                        new_team_names = set()
                        for candidate in all_team_names:
                            # Exact match
                            if candidate in existing_team_names:
                                continue
                            # Fuzzy match against existing teams
                            if any(
                                _canonical_names_match(candidate, existing)
                                for existing in existing_team_names
                            ):
                                continue
                            new_team_names.add(candidate)
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
            "espn_id_stamps_refused": total_espn_id_refused,
        }
    finally:
        await service.close()


async def _merge_duplicate_events_impl(dry_run: bool = True):
    """Find and merge duplicate events. Runs as Celery background task."""
    from sqlalchemy import text as sa_text
    from app.tasks.base import get_task_session
    from app.utils.event_absorption_guard import assert_absorbable_now
    from app.utils.event_merge_invariant import (
        UnanchoredMergeRefused,
        assert_mergeable,
        shared_provider_id_sql,
    )

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
                    AND ABS(EXTRACT(EPOCH FROM (a.commence_time - b.commence_time))) < 21600
                    AND (
                        -- Normal orientation
                        (LOWER(a.home_team_name) = LOWER(b.home_team_name)
                         AND LOWER(a.away_team_name) = LOWER(b.away_team_name))
                        OR
                        -- Swapped home/away
                        (LOWER(a.home_team_name) = LOWER(b.away_team_name)
                         AND LOWER(a.away_team_name) = LOWER(b.home_team_name))
                        OR
                        -- Normalized names (handles "NY Knicks" vs "New York Knicks")
                        (LOWER(COALESCE(a.home_team_normalized, a.home_team_name)) =
                         LOWER(COALESCE(b.home_team_normalized, b.home_team_name))
                         AND LOWER(COALESCE(a.away_team_normalized, a.away_team_name)) =
                             LOWER(COALESCE(b.away_team_normalized, b.away_team_name)))
                    )
                    -- ── RULING 048 APPLIES TO THE DRAIN, NOT ONLY THE INGEST ──
                    -- Everything above this line is name + a 6h window and NO id:
                    -- the exact predicate 048 forbids, and this task DELETEs the
                    -- loser and repoints its FKs, so a wrong pairing here destroys
                    -- data just as surely as a wrong absorption did.
                    --
                    -- R6 (codex C-CERT-1801-R5): the invariant is no longer written
                    -- here. It comes from `app/utils/event_merge_invariant.py`, and
                    -- the same module re-checks every pair in Python before the
                    -- delete. R5's version of this clause had a second arm — "one
                    -- side is id-less AND no THIRD row shares the window" — which
                    -- reads as a safety check and is not one: a 13:05/18:35
                    -- doubleheader IS the complete pair, so there is no third row,
                    -- and the drain deleted the game the registry had just
                    -- correctly created. Uniqueness is not identity.
                    AND """ + shared_provider_id_sql("a", "b") + """
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
        refused_count = 0
        uncorroborated_count = 0
        delete_ids = []
        child_moves: dict[str, dict[str, int]] = {
            "repointed": {}, "dropped_as_duplicate": {}
        }
        # LINKLOSS-02: how many of the moved market links this run could
        # EXPLAIN afterwards. Reported, not just written, because a receipt
        # write that silently stops is worse than none — every consumer reads
        # the resulting silence as "no links moved" (gotcha #53).
        market_receipts_written = 0

        for row in pairs:
            # R6: the SQL above already required a shared provider id, and this
            # asks again on the row in hand. The redundancy is deliberate — the
            # query proves the candidate set was built correctly today, this
            # proves THIS pair is safe to destroy now, and a future hand-edit to
            # a 90-line SQL string cannot quietly reopen the doubleheader delete.
            # A refusal skips the pair and drains the rest (gotcha #42).
            try:
                assert_mergeable(
                    {"external_id": row.ext_a, "espn_id": row.espn_a,
                     "statpal_fixture_id": row.statpal_a, "id": row.id_a},
                    {"external_id": row.ext_b, "espn_id": row.espn_b,
                     "statpal_fixture_id": row.statpal_b, "id": row.id_b},
                    context="merge_duplicate_events",
                )
            except UnanchoredMergeRefused as exc:
                refused_count += 1
                logger.warning("merge_duplicate_events refused a pair: %s", exc)
                continue

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
                # #1947: the LAST check before anything is destroyed, on the rows
                # as the database holds them right now, locked FOR UPDATE. The
                # `assert_mergeable` above ran on values from the candidate
                # SELECT and on arm A alone — and arm A is not sufficient:
                # production holds espn_id values shared by genuinely different
                # games. Until this call existed, the `< 21600` in the SQL above
                # was the ONLY thing standing between that and a deleted game,
                # and it lives in one caller's query string, not in the rule.
                try:
                    await assert_absorbable_now(
                        session,
                        keep_id=keep_id,
                        orphan_id=orphan_id,
                        context="merge_duplicate_events",
                    )
                except UnanchoredMergeRefused as exc:
                    # A SEPARATE counter from `refused_unanchored`, deliberately.
                    # That one means "arm A said no" — the SQL and the Python
                    # disagreed about a shared id. This one means "arm A said
                    # yes and the evidence did not back it up", which is the
                    # #1947 collision class and a different thing to go and
                    # look at. Folding them together would hide whichever is
                    # rarer behind whichever is not.
                    uncorroborated_count += 1
                    logger.warning(
                        "merge_duplicate_events refused a pair at delete time: %s", exc
                    )
                    continue

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
                # Reassign ALL FK references from orphan → keep before delete.
                # R4: this used to be an inline eight-tuple literal — a SECOND
                # hand-written copy of the list, free to drift from the module-level
                # one the other rail used AND from the schema, which it did. Both are
                # one derived call now (app/utils/event_child_repoint.py).
                moved = await repoint_event_children(
                    session, keep_id=keep_id, orphan_id=orphan_id
                )
                # Popped before folding: `markets` is a list of rows, not a
                # per-table count, and _merge_child_moves takes counts.
                moved_markets = moved.pop("markets", [])
                _merge_child_moves(child_moves, moved)
                await session.execute(
                    sa_text("DELETE FROM events WHERE id = :orphan"),
                    {"orphan": orphan_id},
                )
                await session.commit()
                # AFTER the commit, on the receipts' own session (LINKLOSS-02).
                # Each claim is re-read against the committed row before it is
                # published, and the write can never fail the merge.
                market_receipts_written += await record_twin_merge_receipts(
                    moved_markets,
                    previous_event_id=orphan_id,
                    new_event_id=keep_id,
                )
                delete_ids.append(orphan_id)

            merged_count += 1

        if not dry_run and delete_ids:
            logger.info(f"Merged {merged_count} duplicate events, deleted {len(delete_ids)} orphans")

        return {
            "dry_run": dry_run,
            "merged": merged_count,
            "skipped": skipped_count,
            # Reported, not swallowed: a non-zero count means the SQL and the
            # Python guard disagreed, which is either drift in this query or a
            # provider column added in one place and not the other.
            "refused_unanchored": refused_count,
            # #1947: arm A passed and the corroboration did not. A non-zero
            # count here is a pair the pre-guard drain would have DELETED —
            # worth an eye, not an alarm, since the invariant refused it.
            "refused_uncorroborated": uncorroborated_count,
            "deleted": len(delete_ids) if not dry_run else 0,
            # R4's silent half, made loud. Every child row this rail moved, per
            # table — including the two the old hand-list never named, one of
            # which (game_moments) was being CASCADE-destroyed unmentioned on
            # every merge. `dropped_as_duplicate` is the rows the survivor
            # already held an equivalent of under an event-scoped UNIQUE key;
            # they are deleted deliberately, so they are reported deliberately.
            "child_rows_repointed": child_moves["repointed"],
            "child_rows_dropped_as_duplicate": child_moves["dropped_as_duplicate"],
            # LINKLOSS-02: markets whose move onto the survivor is now on the
            # record as `superseded_by_twin_merge`, not as an unexplained
            # link loss.
            "market_link_receipts_written": market_receipts_written,
        }


def _merge_child_moves(
    total: dict[str, dict[str, int]], one_pair: dict[str, dict[str, int]]
) -> None:
    """Fold one pair's per-table repoint counts into the run total, in place."""
    for bucket, counts in one_pair.items():
        target = total.setdefault(bucket, {})
        for table, n in counts.items():
            target[table] = target.get(table, 0) + n


# A module-level `_EVENT_FK_TABLES` tuple stood here, shared by the rail above, the
# rail below, and reconcile_unanchored_events._absorb. R4 (C-DELETE-RAIL-PRE): it
# held EIGHT tables and SQLAlchemy metadata declared TEN FKs to events.id. The two it
# missed failed in opposite directions and neither was visible in any response —
# game_moments is ON DELETE CASCADE, so the loser's moments were silently destroyed by
# every merge; ranking_judgments has no ON DELETE action, so a merge whose loser held a
# human judgment failed with an FK violation.
#
# Adding two names would have been the same hand-list one commit later, so all three
# rails now go through app/utils/event_child_repoint.repoint_event_children, whose
# table list is DERIVED from the schema on every call and which pre-dedupes the two
# children carrying an event-scoped UNIQUE constraint. That module explains why it is
# not part of event_fk_inventory: that inventory's Disposition has no TRANSFER value
# on purpose, because the PRUNE rail must never repoint.


async def _merge_degenerate_combat_events_impl(dry_run: bool = True, limit: int = 500):
    """Merge degenerate ``home==away`` fight events into their real odds event.

    #175 Item 3 — the "15132461 class" cleanup. Before the Item 2 grammar fix, a
    UFC/boxing fight-winner market whose matchup parsed to a single competitor
    auto-created a degenerate event ("Benoit Saint-Denis vs Benoit Saint-Denis")
    and linked its Kalshi markets there — orphaning them from the real
    odds-registry event ("Saint-Denis vs Pimblett", carrying the betting line).
    The standard ``_merge_duplicate_events_impl`` never catches these: it requires
    BOTH team names to match, and a degenerate shares only ONE.

    The matcher here is degenerate-aware: for each ``home==away`` event it finds
    the ONE non-degenerate event in the same sport + ±28h window whose home OR
    away matches the degenerate's (single) fighter — the May-2026 merge lessons
    apply, so it checks BOTH orientations via normalized ``names_match``. The real
    (odds-registry) event SURVIVES; the degenerate's markets/snapshots repoint to
    it and the degenerate is deleted. Verify-first: ``dry_run`` counts the pairs
    without writing. Skips any degenerate with 0 or >1 real matches (never guesses
    which fight it belongs to). A degenerate with no real counterpart is left
    alone (nothing to unify into).

    #180 Item 2 — DOMAIN-AGNOSTIC by construction. Despite the "combat" name (kept
    to avoid a beat-key/task-name/admin-route rename blast radius), the SELECT is
    NOT combat-gated: it scans EVERY ``home==away`` event in any sport with a
    ``sport_id`` and heals whatever has a unique counterpart. Production proof
    (2026-07-13 dry-run): 219 degenerates scanned across esports/baseball_other/
    NCAA Baseball/MMA/soccer_other/Boxing/Tennis/WNBA → merged the 1 with a unique
    real counterpart. The residual is IRREDUCIBLE VIA SAFE MERGE, not a bug here:
    ~195 have NO real counterpart in the DB (esports single-name events whose real
    matchup was never ingested — an upstream esports event-creation issue, its own
    work item) and ~23 are ambiguous (>1 candidate in the window — never guess).
    Census→0 is therefore gated on the upstream fix, not on this matcher.
    """
    from sqlalchemy import text as sa_text
    from app.tasks.base import get_task_session

    _WINDOW_SEC = 28 * 3600  # matches the event-registry structured-match window

    async with get_task_session() as session:
        degen_rows = (await session.execute(sa_text(
            "SELECT id, sport_id, home_team_name, commence_time, "
            "       external_id, espn_id, statpal_fixture_id, "
            "       home_team_id, away_team_id "
            "FROM events "
            "WHERE lower(home_team_name) = lower(away_team_name) "
            "  AND sport_id IS NOT NULL "
            "ORDER BY id DESC LIMIT :lim"
        ), {"lim": limit})).all()

        merged = 0
        skipped_no_match = 0
        skipped_ambiguous = 0
        refused_anchored = 0
        refused_pairs = []
        merged_pairs = []
        child_moves: dict[str, dict[str, int]] = {
            "repointed": {}, "dropped_as_duplicate": {}
        }
        # LINKLOSS-02: how many of the moved market links this run could
        # EXPLAIN afterwards. Reported, not just written, because a receipt
        # write that silently stops is worse than none — every consumer reads
        # the resulting silence as "no links moved" (gotcha #53).
        market_receipts_written = 0

        for d in degen_rows:
            # R6 → R7 (#1801): DELETION REQUIRES EVIDENCE OF THE ARTIFACT, not
            # merely the shape of one. This check is FIRST — before the window
            # scan — because a row that may not be deleted should not have a
            # deletion candidate computed for it at all.
            #
            # The rail used to reason: `home_team_name == away_team_name` is not
            # a fixture, because nothing competes against itself, therefore the
            # row is a corrupt ingest artifact and may be deleted once a unique
            # real counterpart is found. The premise is sound and the conclusion
            # does not follow. `Event` carries `home_team_id` and `away_team_id`
            # as separate nullable FKs, and no constraint anywhere says that
            # equal DISPLAY LABELS mean the same participant — two distinct
            # teams can share a short name ("United", "City", "Cardinals"), and
            # a provider that fills the label from the wrong field produces a
            # row that looks degenerate while being a real, anchored game.
            #
            # C-CERT-1801-R6 executed that specimen: event 9001 carried
            # `external_id`, `espn_id` AND `statpal_fixture_id`, with
            # `home_team_id=101` and `away_team_id=202` — three provider anchors
            # and two distinct participants — and the rail returned `merged=1`,
            # executed `DELETE FROM events WHERE id = 9001`, and committed. That
            # is ruling 042's failure class exactly: LABEL EQUALITY READ AS
            # IDENTITY. The old code selected all three provider IDs and then
            # ignored them, which is what let the belief survive being written
            # down next to its own counter-evidence.
            #
            # So the test is now the artifact's actual signature, and both halves
            # must hold: no authoritative identity from any provider, AND no
            # distinct participant IDs. A row failing either half is refused and
            # counted — never deleted, never silently skipped. Refusing is not a
            # regression in the repair: a genuine single-participant artifact has
            # nothing to be anchored BY, which is what makes it an artifact.
            #
            # Note this is deliberately NOT the ruling-048 shared-provider-ID
            # invariant, which was tried here and measured: it refuses every pair
            # (a degenerate row shares no provider ID with the real event), makes
            # the rail a permanent no-op, and trades a corruption cleanup for
            # nothing. Ruling 048 asks "are these the same event?"; this asks
            # "is this row real?" — different questions, and only the second one
            # is answerable about a row with one participant.
            anchors = (d.external_id, d.espn_id, d.statpal_fixture_id)
            has_authoritative_identity = any(a is not None for a in anchors)
            has_distinct_participants = (
                d.home_team_id is not None
                and d.away_team_id is not None
                and d.home_team_id != d.away_team_id
            )
            if has_authoritative_identity or has_distinct_participants:
                refused_anchored += 1
                refused_pairs.append({
                    "id": d.id,
                    "label": d.home_team_name,
                    "anchors": [
                        n for n, a in zip(
                            ("external_id", "espn_id", "statpal_fixture_id"), anchors
                        ) if a is not None
                    ],
                    "home_team_id": d.home_team_id,
                    "away_team_id": d.away_team_id,
                })
                continue

            fighter = d.home_team_name
            candidates = (await session.execute(sa_text(
                "SELECT id, home_team_name, away_team_name, "
                "       external_id, espn_id, statpal_fixture_id FROM events "
                "WHERE sport_id = :sid AND id <> :did "
                "  AND lower(home_team_name) <> lower(away_team_name) "
                "  AND ABS(EXTRACT(EPOCH FROM (commence_time - :ct))) < :win"
            ), {"sid": d.sport_id, "did": d.id, "ct": d.commence_time,
                "win": _WINDOW_SEC})).all()

            # A real event matches iff the degenerate's single fighter is one of
            # its two competitors (either orientation).
            reals = [
                c.id for c in candidates
                if _canonical_names_match(fighter, c.home_team_name)
                or _canonical_names_match(fighter, c.away_team_name)
            ]
            if not reals:
                skipped_no_match += 1
                continue
            if len(set(reals)) > 1:
                skipped_ambiguous += 1
                continue

            keep_id, orphan_id = reals[0], d.id

            # Every row reaching here has already been proven unanchored and
            # single-participant by the check at the top of the loop (R7). The
            # ambiguity refusal above remains the second safety: >1 candidate
            # never guesses which fight the artifact belongs to.
            merged_pairs.append({"orphan": orphan_id, "keep": keep_id, "fighter": fighter})

            if not dry_run:
                moved = await repoint_event_children(
                    session, keep_id=keep_id, orphan_id=orphan_id
                )
                # Popped before folding: `markets` is a list of rows, not a
                # per-table count, and _merge_child_moves takes counts.
                moved_markets = moved.pop("markets", [])
                _merge_child_moves(child_moves, moved)
                await session.execute(
                    sa_text("DELETE FROM events WHERE id = :orphan"),
                    {"orphan": orphan_id},
                )
                await session.commit()
                # AFTER the commit, on the receipts' own session (LINKLOSS-02).
                # Each claim is re-read against the committed row before it is
                # published, and the write can never fail the merge.
                market_receipts_written += await record_twin_merge_receipts(
                    moved_markets,
                    previous_event_id=orphan_id,
                    new_event_id=keep_id,
                )
            merged += 1

        if not dry_run and merged:
            logger.info("Merged %d degenerate combat events into real events", merged)

        return {
            "dry_run": dry_run,
            "degenerate_scanned": len(degen_rows),
            "merged": merged,
            "skipped_no_match": skipped_no_match,
            "skipped_ambiguous": skipped_ambiguous,
            # Reported, not just counted: a refusal is the rail declining to
            # delete something that LOOKS degenerate but carries provider
            # anchors or two distinct participants. A non-zero value is a
            # standing signal that some upstream writer is producing real rows
            # with equal display labels — which is a bug worth seeing, and was
            # invisible while the rail simply deleted them (#1801 R6→R7).
            "refused_anchored": refused_anchored,
            "refused_sample": refused_pairs[:15],
            "sample": merged_pairs[:15],
            # R4: see the same two keys on _merge_duplicate_events_impl.
            "child_rows_repointed": child_moves["repointed"],
            "child_rows_dropped_as_duplicate": child_moves["dropped_as_duplicate"],
            # LINKLOSS-02: markets whose move onto the survivor is now on the
            # record as `superseded_by_twin_merge`, not as an unexplained
            # link loss.
            "market_link_receipts_written": market_receipts_written,
        }
