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
from itertools import zip_longest
from typing import Optional

from sqlalchemy import select, update, and_, or_, func

from app.tasks.base import get_task_session
from app.tasks.config import STATPAL_SPORT_MAPPING
from app.utils.team_binding_invariant import accept_team_binding
from app.utils.game_pairing import Pairing, live_write_is_premature, pair_verdict

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

    # #1918. A refusal here means an upstream index proposed a club that is not the
    # one this row names — previously invisible, because the write simply succeeded.
    # Surfaced in the task result so a spike is a finding rather than a log line
    # nobody reads (the same treatment `refused_anchored` got on the merge rail).
    binding_stats: dict = {}

    # #1945/#1947. Both counters are surfaced in the task result for the same
    # reason `binding_stats` is: a refusal that only logs is a refusal nobody
    # measures, and these two are the ones that stand between a live score and a
    # game that has not been played yet.
    live_pair_refused = 0
    premature_live_skipped = 0
    # Q438: creations this path DOWNGRADED to 'scheduled' because the game had
    # not started. Always present; 0 is a reading, not an absence (gotcha #53).
    premature_live_created_as_scheduled = 0

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
                    # #1945: `live_by_teams` is keyed on the team pair ALONE. In a
                    # 3-4 game MLB series every fixture in this -1d/+7d window
                    # shares that key with tonight's live game, so an unchecked
                    # `live_data` writes tonight's score onto a row dated two days
                    # out. The team pair is a matchup; only matchup + instant is a
                    # game. UNKNOWN (a live row with no start time) is NOT trusted
                    # here — the premature guard at the write site below is the
                    # unconditional backstop, so refusing costs a score update we
                    # could not justify, never one we could.
                    if live_data is not None and pair_verdict(
                        fixture.start_time, getattr(live_data, "start_time", None),
                    ) is not Pairing.SAME:
                        live_pair_refused += 1
                        live_data = None

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
                            STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                        )
                        claim_id = fixture.fixture_id or f"statpal_{fixture.home_team}_{fixture.away_team}"
                        identity = EventIdentity(
                            sport_key=our_key,
                            home_team_name=fixture.home_team,
                            away_team_name=fixture.away_team,
                            commence_time=fixture.start_time,
                            # Ruling 048: NOT arm B. `get_fixtures(sport)` is a
                            # season-schedule LISTING — we asked by sport and got
                            # rows back — so a fixture id arriving alongside its
                            # teams and date is co-arrival, not dereference.
                            # Measured 54/54 wrong-game absorptions on this site.
                            # (The synthesized `statpal_<home>_<away>` fallback id
                            # was never an anchor either — a label wearing an id's
                            # clothing, ruling 042 — so nothing is lost by no
                            # longer distinguishing the two.)
                            claim=EventClaim(
                                "statpal", claim_id,
                                schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                            ),
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
                    # #1918: `resolve_team` reads `team_identity_mapping`, and 15 of
                    # the 30 statpal/baseball_mlb rows in that table name one club and
                    # point at another (one poisoned batch, 2026-03-25, never updated
                    # since). The exact-source_name hit is step 2 — the service's
                    # highest-confidence path — so nothing downstream doubts it, and
                    # this line wrote ~5 wrong-club sides a day. Dereference before
                    # binding; on refusal leave the column NULL for a name-keyed
                    # binder to fill correctly next cycle.
                    if not event.home_team_id and accept_team_binding(
                        side="home",
                        row_name=event.home_team_name,
                        team=home_team,
                        event_sport_id=event.sport_id,
                        source="statpal",
                        event_id=event.id,
                        stats=binding_stats,
                    ):
                        event.home_team_id = home_team.id
                        updated = True
                    if not event.away_team_id and accept_team_binding(
                        side="away",
                        row_name=event.away_team_name,
                        team=away_team,
                        event_sport_id=event.sport_id,
                        source="statpal",
                        event_id=event.id,
                        stats=binding_stats,
                    ):
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
                        # BR76: also transition status to completed
                        if event.status == "live":
                            event.status = "completed"
                            if not event.completed_at:
                                event.completed_at = fixture.end_time
                            updated = True

                    # Update scores from live data if available.
                    # #1945/#1947: a row whose own commence_time is still in the
                    # future cannot hold a live score, whatever the provider says —
                    # it is describing a different game. This is the guard ESPN has
                    # carried since #1207 and StatPal did not; same predicate, one
                    # implementation (`app/utils/game_pairing.py`).
                    if live_data and live_data.status == "live":
                        if live_write_is_premature(event.commence_time, now):
                            premature_live_skipped += 1
                            logger.warning(
                                "StatPal premature-live guard: refused live score on "
                                "event %d (%s vs %s) — commence_time %s is still in "
                                "the future (now %s) (#1945)",
                                event.id, event.home_team_name, event.away_team_name,
                                event.commence_time.isoformat() if event.commence_time else None,
                                now.isoformat(),
                            )
                        else:
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
                    STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
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
                    # Create the missing event.
                    #
                    # #1945/Q438 — the row is created either way (the playoff gap
                    # this path exists to fill is real), but it may only be
                    # created LIVE once its own start time has arrived. Same
                    # predicate as the score write above; one implementation.
                    #
                    # 🔴 MEASURED on production 2026-08-29: this path had created
                    # **48 events since 2026-05-15, and all 48 were created
                    # BEFORE their own commence_time** — it has never once
                    # created a game that was actually in progress. 46 have since
                    # rolled to `completed`; the two still sitting `live` were
                    # 15292756 (Colts vs Lions) and 15292757 (Titans vs Bears),
                    # minted 2026-08-26 for an 2026-08-29 kickoff and badged LIVE
                    # on the NFL league page for three days.
                    premature_create = live_write_is_premature(
                        live_fix.start_time, now
                    )
                    if premature_create:
                        premature_live_created_as_scheduled += 1
                        logger.warning(
                            "StatPal premature-live guard: creating %s vs %s (%s) as "
                            "'scheduled', not 'live' — start_time %s is still in the "
                            "future (now %s) (#1945/Q438)",
                            live_fix.home_team, live_fix.away_team, our_key,
                            live_fix.start_time.isoformat() if live_fix.start_time else None,
                            now.isoformat(),
                        )
                    claim_id = live_fix.fixture_id or f"statpal_live_{live_fix.home_team}_{live_fix.away_team}"
                    identity = EventIdentity(
                        sport_key=our_key,
                        home_team_name=live_fix.home_team,
                        away_team_name=live_fix.away_team,
                        commence_time=live_fix.start_time,
                        # Ruling 048: NOT arm B — see the season-schedule site
                        # above. `get_live_scores(sport)` is a listing too. This
                        # is the WORSE of the two sites: the ±6h pre-check just
                        # above strips the same-game case, so everything that
                        # reached the ±28h matcher was the adjacent game in the
                        # series — measured 8/8 wrong-game, at +21.9h/−24h/+4h/
                        # −24h/+22h/−20h/−20h/−20h.
                        claim=EventClaim(
                            "statpal", claim_id,
                            schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE,
                        ),
                        commence_time_source="statpal",
                        status="scheduled" if premature_create else "live",
                    )
                    event, was_created = await find_or_create_event(
                        session, identity,
                    )
                    if was_created:
                        live_created += 1
                        # The status downgrade above and the score are the SAME
                        # claim — a game that has not started has no score to
                        # carry either, and writing one would restore the exact
                        # contradiction (`scheduled` + a live score) one field
                        # over. The sibling score path 100 lines up refuses on
                        # this predicate; so does this one.
                        if not premature_create:
                            if live_fix.home_score is not None:
                                event.home_score = live_fix.home_score
                            if live_fix.away_score is not None:
                                event.away_score = live_fix.away_score
                        logger.info(
                            "Created event from live StatPal: %s vs %s (%s) as %s",
                            live_fix.away_team, live_fix.home_team, our_key,
                            "scheduled (premature)" if premature_create else "live",
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
        # Always present, and 0 is the meaningful reading — an absent key would make
        # "the guard found nothing" indistinguishable from "the guard did not run".
        "team_binding_refused": binding_stats.get("team_binding_refused", 0),
        "team_binding_refused_detail": {
            k: v for k, v in binding_stats.items() if k != "team_binding_refused"
        },
        # #1945/#1947 — same rule: always present, 0 is a reading.
        "live_pair_refused": live_pair_refused,
        "premature_live_skipped": premature_live_skipped,
        "premature_live_created_as_scheduled": premature_live_created_as_scheduled,
    }


#: Which of OUR sport keys can receive a given StatPal sport's injuries.
#:
#: `STATPAL_SPORT_MAPPING` lists seven soccer keys because those are the ones we
#: pull SCHEDULES for. StatPal's injury product is one call covering twenty
#: leagues, and 105 of the 168 soccer events in the attach window on 2026-09-06
#: sat under keys the map does not name (`soccer_brazil_campeonato`,
#: `soccer_mexico_ligamx`, `soccer_other`, …). Restricting the attach to the
#: schedule map would throw away most of the coverage for no reason: the pair
#: rule decides what belongs to what, not the league key.
#:
#: Widening `STATPAL_SPORT_MAPPING` itself would change what the schedule sync
#: creates, which is a different ship with a different blast radius. This is
#: local to the injury attach and says so.
_INJURY_EVENT_SPORT_PREFIX: dict[str, str] = {"soccer": "soccer"}


def _interleave_sides(injuries: list) -> list:
    """Home, away, home, away … so a 10-cap cannot silence one whole team.

    A shared cap over two unequal populations empties the smaller one first. In
    the 2026-09-06 payload, 22 of 146 fixtures carried more than ten sidelined
    players and **4 of them would have shown only one side** in vendor order —
    and the reader that consumes this list attributes a line move to the team
    that FELL, so a game where only the home side survived the cap can never
    explain an away-side drop, however many away players are hurt.

    Order within a side is preserved; nothing is dropped here, only reordered.
    """
    home = [inj for inj in injuries if inj.is_home]
    away = [inj for inj in injuries if not inj.is_home]
    ordered = []
    for pair in zip_longest(home, away):
        ordered.extend(inj for inj in pair if inj is not None)
    return ordered


async def _sync_statpal_injuries(sport_key: Optional[str] = None) -> dict:
    """Sync injury reports from StatPal onto events for line-movement context.

    Injuries land in `Event.win_probability_sources['statpal_injuries']`, which
    `routes/events.py` merges with ESPN's (ESPN wins a name collision) to ground
    the "Why did the line move?" explanation.

    Three things here are load-bearing and each replaced something that made the
    task incapable of producing a row:

    * **One fetch per StatPal sport, not per Odds-API key.** Seven of our keys
      map to `soccer`; the old loop asked for the same 224 KB payload seven times
      an hour and attributed each copy to one league.
    * **`get_injuries_result`, not `get_injuries`.** "The venue has no injury
      product for this sport", "we asked and it broke" and "nobody is hurt" were
      the same empty list (gotcha #53). Only the middle one is an alarm, and the
      terminal below now says which happened.
    * **A Core `update()` for the JSONB write.** Gotcha #4.

    Args:
        sport_key: If provided, only sync the StatPal sport this key maps to.

    Returns:
        Summary dict carrying a `terminal` — `statpal_injuries` is enrolled in
        `task_verdict.ENFORCED_TASKS`, so a run that could not read the venue
        reads NOT-GREEN instead of looking like a quiet day.
    """
    from app.services.statpal_api import StatPalAPIService, is_available
    from app.utils.statpal_injury_attach import Fixture, choose_fixture

    if not is_available():
        return {"skipped": True, "reason": "STATPAL_API_KEY not set", "terminal": "skipped"}

    if sport_key:
        statpal_sports = (
            [STATPAL_SPORT_MAPPING[sport_key]] if sport_key in STATPAL_SPORT_MAPPING else []
        )
    else:
        # dict.fromkeys: dedupe, order preserved — seven soccer keys, one fetch.
        statpal_sports = list(dict.fromkeys(STATPAL_SPORT_MAPPING.values()))

    if not statpal_sports:
        return {
            "skipped": True,
            "reason": f"sport_key {sport_key!r} not in STATPAL_SPORT_MAPPING",
            "terminal": "skipped",
        }

    service = StatPalAPIService()
    total_injuries = 0
    total_events_enriched = 0
    total_events_cleared = 0
    details = []
    fetch_failures = []

    try:
        async with get_task_session() as session:
            from app.models import Event, Sport

            for statpal_sport in statpal_sports:
                fetch = await service.get_injuries_result(statpal_sport)

                if not fetch.asked:
                    # Not a failure and not a quiet day: the venue publishes no
                    # injury path for this sport at all (#2907). Recorded so the
                    # absence is legible without re-probing.
                    details.append({
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "injuries_fetched": 0,
                        "events_enriched": 0,
                    })
                    continue

                if fetch.is_alarm:
                    fetch_failures.append(
                        {"statpal_sport": statpal_sport, "endpoint": fetch.endpoint}
                    )
                    details.append({
                        "statpal_sport": statpal_sport,
                        "reason": fetch.reason,
                        "injuries_fetched": 0,
                        "events_enriched": 0,
                    })
                    await asyncio.sleep(0.3)
                    continue

                injuries = fetch.injuries
                total_injuries += len(injuries)

                # Group by the FIXTURE the player's team is playing, keeping both
                # sides of it — the attach decision needs the pair, not the team.
                by_fixture: dict[str, list] = {}
                fixtures: dict[str, Fixture] = {}
                for inj in injuries:
                    home, away = (
                        (inj.team, inj.opponent) if inj.is_home
                        else (inj.opponent, inj.team)
                    )
                    # `main_id` is present on 1,002 of the 1,004 rows served on
                    # 2026-09-06; one fixture published only a fallback. The
                    # last-resort key is built from HOME|AWAY, never
                    # team|opponent, or the two sides of one match key
                    # differently and split it into two fixtures.
                    key = (
                        inj.fixture_main_id
                        or (inj.fixture_fallback_ids[0] if inj.fixture_fallback_ids else None)
                        or f"{home}|{away}|{inj.fixture_date}"
                    )
                    by_fixture.setdefault(key, []).append(inj)
                    if key not in fixtures:
                        fixtures[key] = Fixture(
                            key=key,
                            home=home,
                            away=away,
                            fixture_date=(
                                inj.fixture_date.date() if inj.fixture_date else None
                            ),
                        )

                prefix = _INJURY_EVENT_SPORT_PREFIX.get(statpal_sport)
                if prefix:
                    sport_filter = Sport.key.like(f"{prefix}%")
                else:
                    our_keys = [
                        k for k, v in STATPAL_SPORT_MAPPING.items() if v == statpal_sport
                    ]
                    sport_filter = Sport.key.in_(our_keys)

                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=6)
                window_end = now + timedelta(days=2)

                result = await session.execute(
                    select(
                        Event.id,
                        Event.home_team_name,
                        Event.away_team_name,
                        Event.commence_time,
                        Event.win_probability_sources,
                    )
                    .join(Sport, Sport.id == Event.sport_id)
                    .where(
                        sport_filter,
                        Event.commence_time.between(window_start, window_end),
                        Event.status.in_(["scheduled", "live"]),
                    )
                )
                events = result.all()

                enriched = 0
                cleared = 0
                candidates = list(fixtures.values())
                for event in events:
                    chosen = choose_fixture(
                        event.home_team_name,
                        event.away_team_name,
                        event.commence_time.date() if event.commence_time else None,
                        candidates,
                    )

                    sources = dict(event.win_probability_sources or {})

                    if not chosen:
                        # A SUCCESSFUL snapshot that does not list this fixture is
                        # current information: there is nobody sidelined for it
                        # now. Writing only additively would leave yesterday's
                        # list in place forever, and `routes/events.py` reads it
                        # with no freshness check — so a recovered player would
                        # keep being printed as the cause of a line move. This
                        # branch is reachable ONLY on `ok`/`empty`; a
                        # `fetch_failed` sport returned long before here, so a
                        # bad upstream day never deletes what we already know.
                        if "statpal_injuries" not in sources:
                            continue
                        sources.pop("statpal_injuries", None)
                        sources.pop("statpal_injuries_updated", None)
                        cleared += 1
                    else:
                        sources["statpal_injuries"] = [
                            {
                                "player": inj.player_name,
                                "team": inj.team,
                                "status": inj.status,
                                "type": inj.injury_type,
                                "detail": inj.detail,
                            }
                            for inj in _interleave_sides(by_fixture[chosen])[:10]
                        ]
                        sources["statpal_injuries_updated"] = now.isoformat()
                        enriched += 1

                    # Core update, not ORM attribute assignment (gotcha #4).
                    await session.execute(
                        update(Event)
                        .where(Event.id == event.id)
                        .values(win_probability_sources=sources)
                    )

                total_events_enriched += enriched
                total_events_cleared += cleared
                details.append({
                    "statpal_sport": statpal_sport,
                    "reason": fetch.reason,
                    "injuries_fetched": len(injuries),
                    "fixtures_with_injuries": len(by_fixture),
                    "events_considered": len(events),
                    "events_enriched": enriched,
                    "events_cleared": cleared,
                })

                await asyncio.sleep(0.3)

    finally:
        await service.close()

    # A run that could not read a supported venue path is FAILED, not a quiet
    # day — that confusion is the whole reason this task wrote nothing for as
    # long as it existed and nothing said so.
    terminal = "failed" if fetch_failures else "complete"

    return {
        "terminal": terminal,
        "total_injuries": total_injuries,
        "events_enriched": total_events_enriched,
        "events_cleared": total_events_cleared,
        "fetch_failures": fetch_failures,
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
    # #1945: a refusal that only logs is a refusal nobody measures.
    premature_live_skipped = 0
    _now = datetime.now(timezone.utc)

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

                    # #1945: this is the third site keyed on the team pair alone,
                    # and it is the PROPAGATOR — the `status='live'` query above has
                    # no time bound, so once a future-dated row has been flipped
                    # live it keeps being fed tonight's score every 60s. A row that
                    # has not started cannot be live; refuse and let the row's own
                    # status transition fix it, rather than keep it plausible.
                    if live_write_is_premature(event.commence_time, _now):
                        premature_live_skipped += 1
                        logger.warning(
                            "StatPal premature-live guard: refused live score on "
                            "event %d (%s vs %s) — commence_time %s is still in the "
                            "future (now %s) (#1945)",
                            event.id, event.home_team_name, event.away_team_name,
                            event.commence_time.isoformat() if event.commence_time else None,
                            _now.isoformat(),
                        )
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
        "premature_live_skipped": premature_live_skipped,
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


def live_row_bears_state(fixture) -> bool:
    """Can `_sync_statpal_livescores` advance an event's SCORE or PERIOD from this row?

    #3473 / CERT-2047. Lives here, beside the writer whose behaviour it
    describes, and is exported for `utils/authority_failover`'s readiness check
    — because a failover that accepts a row the writer will skip declares
    StatPal to be serving over a pass that writes nothing. Readiness and the
    writer have to answer "is this row useful?" the same way, and the only
    reliable way to make two answers agree is to have one.

    It mirrors, exactly, the three conditions the loop above sets `updated` on
    that touch game state:

      * `fixture.home_score is not None` / `away_score is not None`;
      * a `raw_status` that is not the bare literal `live`/`Live` — the loop
        writes `event.period` only from a raw status that says something more
        than "this is a live game" (`Q3`, `1H`, `HT`).

    It deliberately does NOT count the fourth `updated` branch, the
    `fixture_id` backfill. That link is an id repair, not live state: it would
    let a `scheduled` row with no scores and no period read as "StatPal is
    serving this game", which is the precise mistake CERT-2047 caught.

    Proven against the writer rather than asserted:
    `test_a_stateless_live_row_advances_nothing_through_the_real_writer` runs
    the real task over a row this rejects and shows score and period unmoved.
    """
    if getattr(fixture, "home_score", None) is not None:
        return True
    if getattr(fixture, "away_score", None) is not None:
        return True
    raw = getattr(fixture, "raw_status", None)
    return bool(raw and raw not in ("live", "Live"))


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
