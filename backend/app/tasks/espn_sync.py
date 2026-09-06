"""
ESPN live sync, metadata enrichment, and team logo backfill tasks.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, distinct, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models import Event, Sport
from app.tasks.base import get_task_session, run_async
from app.tasks.config import ESPN_SPORT_MAPPING
# #3473. Imported as a module rather than by name so the two consuming loops
# below read `_failover.espn_reading(...)` — at the exact lines that used to say
# `espn_data.get(sport_key, [])`, the reader can see that a reading is being
# taken and go and find out what the three of them are.
from app.utils import authority_failover as _failover
from app.utils.team_binding_invariant import accept_team_binding
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


async def _statpal_standby_reading(sport_key: str) -> tuple[str, str]:
    """StatPal's two readings for `sport_key`, read the only way that can say "dark".

    Returns `(schedule, live)`. TWO, because StatPal serves the ship's two
    halves from two endpoints and readiness needs both: `season-schedule` says a
    game exists, `livescores` says what is happening in it. Checking only the
    first is how a schedule-healthy, live-dark StatPal got reported as serving a
    sport whose score and clock were frozen (CERT-2044).

    `StatPalAPIService.get_fixtures` cannot answer this question. It ends with
    `if not data: return []`, so an upstream failure and a sport with no games
    arrive as the same empty list — the identical collapse this whole ship
    exists to undo, on the other side of the comparison. Failing ESPN over to a
    standby on the strength of a `[]` that might mean "we could not ask" would
    replace one silent authority with another.

    `get_schedule_fixtures` is the authority read path program step 1 built for
    exactly this: it raises `StatPalUpstreamError` rather than returning `[]`
    when StatPal did not answer, and its own docstring says why — *"no games is
    the finding it exists to report and a swallowed failure forges it"*.

    **AND IT IS COUNTED OVER A WINDOW, NOT IN FULL.** That endpoint answers with
    a whole season — 321 NFL games, 1,206 NBA, 1,404 NHL — while
    `get_scoreboard` answers about today. Comparing the two unfiltered says
    "StatPal has fixtures and ESPN does not" on every quiet day there has ever
    been. `reading_in_window` is where that is fixed and where the window is
    argued; this function's job is to hand it the raw read and the clock.
    """
    from app.services.statpal_api import (
        StatPalAPIService,
        StatPalUpstreamError,
        is_available,
    )
    from app.utils.authority_failover import (
        DARK,
        active_fixtures,
        live_reading_for,
        reading_in_window,
    )
    from app.utils.sport_keys import STATPAL_SPORT_MAPPING

    statpal_sport = STATPAL_SPORT_MAPPING.get(sport_key)
    if not statpal_sport or not is_available():
        # No mapping, or no key configured. Reported as DARK rather than EMPTY:
        # we did not ask, so StatPal has said nothing about this sport, and
        # `decide` must refuse rather than read our own silence as theirs.
        return DARK, DARK

    service = StatPalAPIService()
    try:
        try:
            fixtures = await service.get_schedule_fixtures(statpal_sport)
        except StatPalUpstreamError as exc:
            logger.warning("StatPal standby schedule dark for %s: %s", sport_key, exc)
            return DARK, DARK
        except Exception as exc:  # noqa: BLE001 — classified, never swallowed
            logger.warning("StatPal standby schedule failed for %s: %s", sport_key, exc)
            return DARK, DARK

        # THE SECOND HALF, and the one readiness used to skip (CERT-2044).
        # `get_live_fixtures` is `livescores` through the authority door — it
        # raises where `get_live_scores` returns `[]`, which is the whole
        # reason it is the one called here.
        try:
            live_rows = await service.get_live_fixtures(statpal_sport)
        except StatPalUpstreamError as exc:
            logger.warning("StatPal standby LIVE path dark for %s: %s", sport_key, exc)
            live_rows = None
        except Exception as exc:  # noqa: BLE001 — classified, never swallowed
            logger.warning("StatPal standby live read failed for %s: %s", sport_key, exc)
            live_rows = None
    finally:
        await service.close()

    now = datetime.now(timezone.utc)
    schedule, detail = reading_in_window(fixtures, now=now)

    # AND THE LIVE HALF IS ABOUT THE GAMES AT RISK, NOT THE ENDPOINT (CERT-2046).
    # An answering `livescores` is not evidence on its own: a schedule saying a
    # game kicked off an hour ago and a live board carrying nothing are two
    # readings from one provider that contradict each other, and the writer —
    # which keys live rows to events by team pair — would skip every one of
    # them. So the check is coverage of the active fixtures by rows that CARRY
    # STATE, using the WRITER'S OWN key function and the WRITER'S OWN
    # usefulness predicate, so readiness and the writer cannot disagree about
    # what "the same game" or "a row worth having" means.
    from app.tasks.statpal_sync import _fixture_match_key, live_row_bears_state

    live, live_detail = live_reading_for(
        active_fixtures(fixtures, now=now),
        live_rows,
        key=_fixture_match_key,
        bears_state=live_row_bears_state,
    )
    logger.info(
        "StatPal standby for %s: schedule=%s %s | live=%s %s",
        sport_key, schedule, detail, live, live_detail,
    )
    return schedule, live


async def _decide_failovers(espn_data: dict, fetch_keys, stats: dict) -> dict:
    """Per sport ESPN did not answer for: who serves it, and does anything act?

    Called once per pass, between the fetch and the passes that consume it, so
    both consuming loops read one decision rather than each re-deriving it.

    **Why the gate is asked before the standby is read.** `decide` refuses on
    `flip_permitted` before it looks at StatPal, and reports `STANDBY_NOT_READ`
    if it gets that far without one — so this function asks it, and only goes to
    the network when the answer says the standby could have mattered. The
    ordering lives in the pure function and the caller obeys it, rather than
    both holding a copy that can drift. Today `flip_permitted` refuses every
    sport, so **this path makes no StatPal call at all** and costs one durable
    read per silent sport per pass.
    """
    from app.config.authority_by_sport import flip_permitted
    from app.services.authority_ledger import read_ledger_days
    from app.utils import authority_failover as failover
    from app.utils.authority_agreement import SHADOW_STAMPERS

    decisions: dict[str, object] = {}
    for sport_key in sorted(fetch_keys):
        reading = failover.espn_reading(espn_data, sport_key)
        if reading == failover.FIXTURES:
            continue

        if sport_key not in SHADOW_STAMPERS:
            # No dark id join for this sport, so there is nothing to fail over
            # onto and no ledger to read — `flip_permitted` refuses on exactly
            # this before it ever looks at days. Asked here so a pass over a
            # dozen quiet sports costs no durable reads at all; the refusal and
            # its wording still come from the gate, never from a second copy.
            gate = flip_permitted(sport_key, [])
        else:
            days, ledger_why = await read_ledger_days(sport_key)
            # A ledger we could not read is not a streak of zero and is not a
            # permission either. It refuses, carrying its own reason, so an
            # outage in the snapshot store can never open this gate.
            gate = (
                (False, ledger_why)
                if days is None
                else flip_permitted(sport_key, days)
            )

        decision = failover.decide(sport_key, espn=reading, gate=gate)
        if decision.code == failover.STANDBY_NOT_READ:
            schedule, live = await _statpal_standby_reading(sport_key)
            decision = failover.decide(
                sport_key,
                espn=reading,
                gate=gate,
                statpal=schedule,
                statpal_live=live,
            )
        decisions[sport_key] = decision
    return decisions


async def _act_on_failovers(decisions: dict, stats: dict) -> None:
    """Serve the sports ESPN went dark on, and say loudly when nobody can.

    THE ACT: for a sport whose failover is permitted and whose standby is proven
    able to cover it, this **runs StatPal's schedule and livescore writers
    in-line, now** — `_sync_statpal_schedules(sport_key)` and
    `_sync_statpal_livescores()`, the async implementations behind the beats.
    Fixtures land, and score, period and status advance on the games ESPN has
    stopped reporting. That is the ship: the site keeps showing that sport's
    games instead of freezing on last-known state.

    **WHY THE IMPLEMENTATIONS AND NOT THE TASKS.** An earlier cut called
    `.delay()` on the two Celery tasks and went straight through
    `test_celery_result_retention.test_no_task_dispatches_another_task`, which
    bans intra-task dispatch across `app/tasks/` with no allowlist: a dispatch
    could grow a result consumer the route scan would never see. Calling the
    coroutines directly has none of that hazard — no message, no result backend,
    no second worker — and it is strictly better for the ship anyway, because
    the work happens inside this pass instead of whenever a queue gets to it.
    An outage is the wrong moment to add a hop.

    Called AFTER `_sync_espn_live_events` closes its session, because each
    writer opens its own (gotchas #5, #6).

    **AND IT IS BOUNDED.** Each writer is wrapped: a StatPal failure during an
    ESPN outage must degrade to "nobody served this sport", recorded, and must
    never take down the ESPN pass that is still working for every other sport.

    THE REFUSALS ARE THE OTHER HALF, and they are not consolation.
    `BLANK_CODES` — ESPN silent AND the standby unable to cover — is the state
    where nothing can say what is happening in a game that is on. Logged at
    ERROR and counted apart, because every other refusal is a fact about the day
    and this one is a fault.

    **The receipts.** Every decision that is not the ordinary `ESPN_ANSWERED` is
    published on the task summary, served or not — an outage the site rode out
    is otherwise indistinguishable from one that never happened. A per-pass
    series rather than edge-triggered records, so activation and deactivation
    are both recoverable by differencing consecutive passes and no stored flag
    can be stranded by a lost write.
    """
    from app.utils.authority_failover import BLANK_CODES, FAILOVER_CODES

    receipts = []
    for sport_key in sorted(decisions):
        decision = decisions[sport_key]
        receipts.append(decision.as_receipt())

        if decision.code in FAILOVER_CODES:
            stats["failover_serving"] = stats.get("failover_serving", 0) + 1
            logger.warning(
                "AUTHORITY FAILOVER for %s (%s): %s",
                sport_key, decision.code, decision.why,
            )
            await _serve_from_statpal(sport_key, stats)
        elif decision.code in BLANK_CODES:
            stats["failover_uncovered"] = stats.get("failover_uncovered", 0) + 1
            logger.error(
                "AUTHORITY UNCOVERED for %s (%s): %s",
                sport_key, decision.code, decision.why,
            )
        else:
            logger.info(
                "ESPN silent for %s — no failover (%s): %s",
                sport_key, decision.code, decision.why,
            )

    if receipts:
        stats["failover"] = receipts


async def _serve_from_statpal(sport_key: str, stats: dict) -> None:
    """Run StatPal's own writers for one sport, now, inside this pass.

    Both halves, matching what readiness proved: the schedule writer so the
    sport's fixtures keep landing, and the livescore writer so score, period and
    status keep moving on the ones already under way. Readiness checked both
    endpoints; serving only one would have made half that check a question
    nothing acted on.

    Each is separately guarded and separately counted. A schedule write that
    worked and a live write that failed is a real, partial outcome and must not
    be reported as either a clean serve or a total failure.
    """
    from app.tasks.statpal_sync import (
        _sync_statpal_livescores,
        _sync_statpal_schedules,
    )

    try:
        result = await _sync_statpal_schedules(sport_key)
        stats["failover_schedule_writes"] = (
            stats.get("failover_schedule_writes", 0) + 1
        )
        logger.info("failover schedule write for %s: %s", sport_key, result)
    except Exception as exc:  # noqa: BLE001 — counted, never swallowed
        stats["errors"].append(f"failover_schedule_{sport_key}: {exc}")
        logger.warning("failover schedule write failed for %s: %s", sport_key, exc)

    try:
        result = await _sync_statpal_livescores()
        stats["failover_live_writes"] = stats.get("failover_live_writes", 0) + 1
        logger.info("failover live write (for %s): %s", sport_key, result)
    except Exception as exc:  # noqa: BLE001 — counted, never swallowed
        stats["errors"].append(f"failover_live_{sport_key}: {exc}")
        logger.warning("failover live write failed for %s: %s", sport_key, exc)


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
        # lane1/045: sports whose scoreboard ESPN did NOT answer for. Counted
        # separately from an empty slate — a dark sport is skipped, never read
        # as "no games".
        "authority_dark_sports": 0,
        # #3473. Sports StatPal is serving through the outage, and sports
        # NOBODY is serving. Two counters, and the second is the alarming one:
        # `failover_uncovered` is ESPN silent with a standby that cannot cover,
        # which is the state in which the site actually goes blank.
        "failover_serving": 0,
        "failover_uncovered": 0,
        # What the serving actually managed. Separate from `failover_serving`
        # because a decision to serve and a write that landed are different
        # facts, and the gap between them is the interesting number.
        "failover_schedule_writes": 0,
        "failover_live_writes": 0,
        "errors": [],
    }

    espn_names_match = espn_team_matches
    failover_decisions: dict = {}

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
                        if events is None:
                            # AUTHORITY DARK — ESPN did not answer. The key is
                            # left ABSENT rather than set to [], so no pass can
                            # read this sport's silence as an empty slate.
                            stats["authority_dark_sports"] += 1
                            logger.warning(
                                "ESPN scoreboard authority dark for %s — sport "
                                "skipped, last known state kept", key,
                            )
                            continue
                        espn_data[key] = events
                    except Exception as e:
                        stats["errors"].append(f"espn_fetch_{key}: {str(e)}")
            finally:
                await espn.close()

            # ── Who serves a sport ESPN did not answer for? (#3473) ─
            #
            # BEFORE the passes, because both of them consume the same silence
            # and neither may read it as an empty slate. This is the step-7
            # question, and it is answered here rather than inside the loops so
            # that a sport is decided once per pass and receipted once.
            failover_decisions = await _decide_failovers(
                espn_data, all_fetch_keys, stats
            )

            # ── First pass: live + recently-completed events ─────
            recently_completed_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
            started_cutoff = datetime.now(timezone.utc) - timedelta(hours=5)

            for sport_key in live_sport_keys:
                stats["sports_checked"] += 1

                if sport_key not in ESPN_SPORT_MAPPING:
                    continue

                # `espn_data.get(sport_key, [])` used to stand here, and it is
                # the line #3473 is about: it mapped "ESPN went dark" and "ESPN
                # says there are no games" onto one `[]` and one `continue`,
                # undoing the distinction the fetch loop above had just taken
                # care to preserve. The reading keeps the two apart; the branch
                # below is the same for both because there is nothing ESPN can
                # contribute either way, and what differs — whether anything
                # fails over — was decided above.
                if _failover.espn_reading(espn_data, sport_key) != _failover.FIXTURES:
                    continue
                espn_events = espn_data[sport_key]

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
                # Same reading, same reason as the pass above (#3473). The
                # decision was taken once, before either loop.
                if _failover.espn_reading(espn_data, sport_key) != _failover.FIXTURES:
                    continue
                espn_events = espn_data[sport_key]
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

        # OUTSIDE the `async with` on purpose. `_act_on_failovers` runs the
        # StatPal writers, and each opens its OWN `get_task_session()`; calling
        # them while this task still holds one would nest two sessions on the
        # same task, which is a connection-pool and flush-ordering hazard this
        # repo has paid for (gotchas #5, #6). The decision was taken inside,
        # where `espn_data` lives; the serving happens once this session is
        # closed and nothing of ours is still in flight.
        await _act_on_failovers(failover_decisions, stats)

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
        # #1918. This path is name-keyed and sound by construction today (`upsert_team`
        # resolves within `event.sport_id` from the event's own name), but it OVERWRITES
        # an existing id rather than only filling NULLs — so it is the one site where a
        # future loosening of `upsert_team`'s fuzzy fallback could replace a correct
        # binding with a wrong one. The guard costs nothing and states the invariant here
        # too, rather than leaving it true by accident.
        if event.home_team_id != getattr(home_team, "id", None) and accept_team_binding(
            side="home",
            row_name=event.home_team_name,
            team=home_team,
            event_sport_id=event.sport_id,
            source="espn",
            event_id=event.id,
            stats=stats,
        ):
            event.home_team_id = home_team.id
            changed = True
        if event.away_team_id != getattr(away_team, "id", None) and accept_team_binding(
            side="away",
            row_name=event.away_team_name,
            team=away_team,
            event_sport_id=event.sport_id,
            source="espn",
            event_id=event.id,
            stats=stats,
        ):
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
                        if espn_teams is None:
                            # AUTHORITY DARK — not "this league has no teams".
                            stats["errors"].append(f"authority_dark_{sport_key}")
                            logger.warning(
                                "ESPN teams authority dark for %s — logos left "
                                "as they are", sport_key,
                            )
                            continue
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

                    if espn_teams is None:
                        # AUTHORITY DARK. This pass CLEARS a team's espn_id when
                        # the id is absent from the fetched roster, so a silent
                        # [] here would wipe every ESPN link in the league. A
                        # sport we could not read is skipped whole.
                        stats["errors"].append(f"authority_dark_{sport_key}")
                        logger.warning(
                            "ESPN teams authority dark for %s — espn_id "
                            "validation SKIPPED, no ids cleared", sport_key,
                        )
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


def _corrected_final_score(our_home, our_away, espn_home, espn_away, espn_is_final=True):
    """Decide the score to write from an ESPN summary, or None to leave as-is.

    Fixes the OPS-137 / #805-adjacent bug where a finished game is stuck at a 0-0
    placeholder (live capture missed the final) and the old backfill never
    corrected it because it only wrote when ``home_score IS None``. Verified vs
    ESPN: espn_id 401815890 = 4-9 / 401815887 = 4-5 while we stored 0-0.

    Writes the ESPN final ONLY when we have no score OR a 0-0 placeholder AND
    ESPN actually scored (positive total). False-positive-safe:
    - a genuinely scoreless / POSTPONED game (ESPN total 0, e.g. 401815854) is
      left untouched, so postponed 0-0 rows are never given a fake score;
    - a real non-zero stored score is NEVER overwritten (gotcha #21).
    This only corrects the score; is_winner is left to the resolver, which grades
    off the corrected value on its own cadence.
    """
    # #980/#981: only correct from a CONFIRMED-FINAL ESPN game. A prematurely-
    # "completed" event (status bug) can be mid-game on ESPN; writing that
    # in-progress score as a final corrupts the score (and calibration). When
    # ESPN's final status is unknown, do NOT write (conservative).
    if not espn_is_final:
        return None
    if espn_home is None:
        return None
    espn_total = (espn_home or 0) + (espn_away or 0)
    our_total = (our_home or 0) + (our_away or 0)
    if espn_total > 0 and our_total == 0:
        return (espn_home, espn_away)
    return None


async def _backfill_box_scores(
    limit: int = 100,
    priority_calibration: bool = False,
    oldest_first: bool = False,
):
    """Fetch ESPN box scores for completed/live events missing box_score_data.

    When priority_calibration=True, prioritizes events that have Kalshi
    player prop markets needing is_winner resolution. This ensures the
    first box scores backfilled are the ones that directly improve
    calibration accuracy.

    When oldest_first=True, the re-fetch gate is ordered ascending by
    commence_time instead of the default newest-first. This is a one-shot
    drain mode (#816): the period-score re-fetch backlog is processed
    newest-first by the beat, so the oldest stuck cohort (e.g. the Feb/Mar
    NCAAB 1H espn_id events) never gets reached by bounded runs while fresh
    daily games keep entering at the top. An ascending one-shot drains the
    tail first.

    Also backfills game scores (home_score/away_score) from the same
    ESPN summary response when they are missing.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Sport
    import asyncio as _asyncio

    stats = {
        "checked": 0,
        "fetched": 0,
        "errors": 0,
        "skipped_no_data": 0,
        "scores_backfilled": 0,
    }

    try:
        async with get_task_session() as session:
            # #816 drain mode: process the oldest stuck events first so the
            # Feb/Mar cohort at the tail of the newest-first backlog is reached.
            _order = (
                Event.commence_time.asc()
                if oldest_first
                else Event.commence_time.desc()
            )
            if priority_calibration:
                from app.models.models import FuturesMarket
                result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(
                        Event.status.in_(["completed", "closed"]),
                        Event.espn_id.isnot(None),
                        or_(
                            Event.box_score_data.is_(None),
                            Event.home_score.is_(None),
                            # Re-select events that were box-scored BEFORE period
                            # extraction existed: they have box_score_data but no
                            # home_period_scores, so the 1H resolver's halftime
                            # fallback has nothing to read (#816). The
                            # period_scores_checked_at marker stops us re-fetching
                            # events ESPN has no period data for on every run.
                            and_(
                                Event.box_score_data.isnot(None),
                                ~Event.box_score_data.op("?")("home_period_scores"),
                                ~Event.box_score_data.op("?")("period_scores_checked_at"),
                            ),
                        ),
                        Event.id.in_(
                            select(FuturesMarket.event_id).where(
                                FuturesMarket.source == "kalshi",
                                FuturesMarket.event_id.isnot(None),
                                FuturesMarket.status == "resolved",
                            )
                        ),
                    )
                    .order_by(_order)
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
                                or_(
                                    Event.box_score_data.is_(None),
                                    # #980 follow-up: box_score'd events stuck at a
                                    # 0 total (live capture missed the final) that
                                    # the box-IS-None branch excludes. Re-feed once
                                    # to pull the real ESPN final; the
                                    # scores_checked_at marker prevents re-polling
                                    # legit-0 games (postponed / 0-0 soccer draws).
                                    and_(
                                        Event.box_score_data.isnot(None),
                                        ~Event.box_score_data.op("?")(
                                            "scores_checked_at"
                                        ),
                                        (
                                            func.coalesce(Event.home_score, 0)
                                            + func.coalesce(Event.away_score, 0)
                                        )
                                        == 0,
                                    ),
                                ),
                            ),
                        )
                    )
                    .order_by(_order)
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
                        if context is None:
                            # AUTHORITY DARK — leave the event exactly as it is.
                            stats["authority_dark"] = stats.get("authority_dark", 0) + 1
                            continue
                        box_score = context.get("box_score", {})
                        scoring_plays = context.get("scoring_plays", [])
                        scores = context.get("scores", {})

                        now_str = datetime.now(timezone.utc).isoformat()

                        _fix = _corrected_final_score(
                            event.home_score,
                            event.away_score,
                            scores.get("home_score"),
                            scores.get("away_score"),
                            espn_is_final=bool(scores.get("is_final")),
                        )
                        if _fix is not None:
                            event.home_score, event.away_score = _fix
                            stats["scores_backfilled"] += 1

                        if box_score or scoring_plays:
                            box_data = {
                                "source": "espn",
                                "fetched_at": now_str,
                                "players": box_score,
                                "scoring_plays": scoring_plays,
                            }
                            if scores.get("home_period_scores"):
                                box_data["home_period_scores"] = scores["home_period_scores"]
                                box_data["away_period_scores"] = scores.get("away_period_scores", [])
                            event.box_score_data = box_data
                            stats["fetched"] += 1
                        elif event.box_score_data is None:
                            event.box_score_data = {
                                "source": "espn",
                                "error": "not_available",
                                "fetched_at": now_str,
                            }
                            stats["skipped_no_data"] += 1

                        # Anti-thrash (#816): stamp a period-check marker on every
                        # processed event so the re-fetch gate cannot re-select it
                        # forever when ESPN has no period data. Reassign a NEW dict
                        # so SQLAlchemy detects the JSONB change.
                        if (
                            isinstance(event.box_score_data, dict)
                            and "period_scores_checked_at" not in event.box_score_data
                        ):
                            _bsd = dict(event.box_score_data)
                            _bsd["period_scores_checked_at"] = now_str
                            event.box_score_data = _bsd

                        # #980 follow-up anti-thrash: mark score-checked so the
                        # 0-total re-feed branch can't re-poll legit-0 events
                        # (postponed / 0-0 soccer draws — ESPN total 0, no
                        # correction) forever. Only reached on a successful ESPN
                        # response; transient failures raise and retry next run.
                        if (
                            isinstance(event.box_score_data, dict)
                            and "scores_checked_at" not in event.box_score_data
                        ):
                            _bsd2 = dict(event.box_score_data)
                            _bsd2["scores_checked_at"] = now_str
                            event.box_score_data = _bsd2

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
    from app.utils.espn_candidate_selection import select_authorized_espn_candidate
    import asyncio as _asyncio

    stats = {
        "dates_checked": 0, "events_matched": 0, "already_had_id": 0,
        "errors": 0, "events_refused": 0,
    }

    espn_sports = list(ESPN_SPORT_MAPPING.keys())

    try:
        async with get_task_session() as session:
            # Find completed events without ESPN IDs in ESPN-supported sports
            # Filter to ESPN sports IN the SQL query (not post-filter) to
            # avoid 86K non-ESPN events consuming the limit.
            espn_sport_ids_result = await session.execute(
                select(Sport.id).where(Sport.key.in_(espn_sports))
            )
            espn_sport_ids = [r[0] for r in espn_sport_ids_result.all()]

            result = await session.execute(
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    Event.status.in_(["completed", "closed"]),
                    Event.espn_id.is_(None),
                    Event.commence_time.isnot(None),
                    Event.home_team_name.isnot(None),
                    Event.away_team_name.isnot(None),
                    Event.sport_id.in_(espn_sport_ids),
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            events = result.scalars().all()

            if not events:
                return {"status": "no_events_to_backfill", **stats}

            # Group by (sport, date) to minimize API calls
            from collections import defaultdict
            by_sport_date: dict[tuple[str, str], list] = defaultdict(list)
            for event in events:
                sport_key = event.sport.key
                date_str = event.commence_time.strftime("%Y%m%d")
                by_sport_date[(sport_key, date_str)].append(event)

            # `stamp_espn_id_if_unheld`'s in-pass set (#2017). The DB check
            # alone is nearly sufficient, and "nearly" is the word that makes a
            # guard accidental: this pass groups by (sport, date), so the two
            # halves of a same-day twin pair are stamped inside one uncommitted
            # transaction and only this set sees the first one.
            from app.utils.espn_id_stamp import STAMPED, stamp_espn_id_if_unheld
            claimed_espn_ids: set = set()

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

                    if espn_events is None:
                        # AUTHORITY DARK — an event's absence from a board we
                        # never received is not evidence about the event.
                        stats["authority_dark"] = stats.get("authority_dark", 0) + 1
                        logger.warning(
                            "ESPN scoreboard authority dark for %s/%s — %d events "
                            "left untouched", sport_key, date_str, len(date_events),
                        )
                        continue

                    if not espn_events:
                        continue

                    for event in date_events:
                        home_names, away_names = get_event_name_variations(event)
                        # #2049: was "first team-name match in the date
                        # scoreboard, raw ORM stamp, no time gate at all" — one
                        # of the five sibling manufacturers codex censused.
                        matched, reason = select_authorized_espn_candidate(
                            espn_events,
                            event.commence_time,
                            is_name_match=lambda ee: (
                                espn_team_matches(home_names, ee.home_team)
                                and espn_team_matches(away_names, ee.away_team)
                            ),
                            # FF1/#2058: this rail targets events with no id, so
                            # the anchor is normally absent — pass it anyway so a
                            # partially-stamped row is corroborated, not refused.
                            anchor_espn_id=getattr(event, "espn_id", None),
                        )
                        if matched is not None:
                            # #2693 CERT-784: this used to be a raw
                            # `event.espn_id = matched.espn_id` with no holder
                            # check — the one authorized writer that still
                            # bypassed the #2017 guard. It is the writer that
                            # makes the step-2 repair non-durable: the repair
                            # unstamps a twin, this task runs six hours later,
                            # selects it (`espn_id IS NULL`), name-matches the
                            # same ESPN fixture and hands the contested id
                            # straight back. A unique index would then be
                            # uninstallable again and the hub's Finished link
                            # would correctly go dead a second time.
                            verdict, holder_id = await stamp_espn_id_if_unheld(
                                session, event, matched.espn_id,
                                context="espn_id backfill",
                                claimed=claimed_espn_ids,
                            )
                            if verdict == STAMPED:
                                stats["events_matched"] += 1
                                logger.info(
                                    f"ESPN ID backfill: matched event {event.id} "
                                    f"({event.home_team_name} vs {event.away_team_name}) "
                                    f"→ ESPN {matched.espn_id}"
                                )
                            else:
                                # COUNTED. A guard whose refusals are invisible
                                # reads exactly like a guard that never fired.
                                stats["events_id_held"] = (
                                    stats.get("events_id_held", 0) + 1
                                )
                                stats.setdefault("held_examples", [])
                                if len(stats["held_examples"]) < 20:
                                    stats["held_examples"].append({
                                        "event_id": event.id,
                                        "espn_id": matched.espn_id,
                                        "holder_event_id": holder_id,
                                    })
                        elif reason != "no-name-match":
                            stats["events_refused"] = stats.get("events_refused", 0) + 1
                            logger.info(
                                f"ESPN ID backfill REFUSED event {event.id} "
                                f"({event.home_team_name} vs {event.away_team_name}): "
                                f"{reason}"
                            )

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


def _apply_final_pm_win_prob(wp_sources: dict | None, resolved_home: float) -> dict:
    """Stamp the resolved final win probability onto the prediction-market
    sources of a win_probability_sources map.

    #1000: each source entry is EITHER a dict {"value": ...} OR a bare float —
    aggregation.py accepts both. The old inline code did
    ``wp_sources[src]["value"] = ...`` unconditionally, which raised
    "TypeError: 'float' object does not support item assignment" on the bare-float
    entries (2,245 events, stalling live→closed transitions).

    #1829: entries are now normalised to the stamped dict form on the way out,
    and — the part that matters — a REWRITTEN value always gets a FRESH
    ``updated_at``. Carrying an old stamp forward onto a new number is worse
    than having no stamp at all: it is a wrong answer to "how old is this?",
    and the hero's recency decay believes it.

    ── NO CALLER, AND SAID OUT LOUD (live/048) ──

    Its ONLY caller was the staleness net's ``live → closed`` arm, and CERT-752
    is the record of what that caller did: it resolved the blend to 1.0/0.0 off
    a partial score on a suspended match. Removing it is the repair, so this is
    left correct and tested but unreferenced rather than quietly deleted,
    because what it does is right and only its trigger was wrong.

    The gap it leaves is REAL and is not this change's to close: nothing now
    resolves prediction-market sources when the AUTHORITY settles an event
    either. That was already true before this change — measured 2026-09-02, only
    20 of 1,267 authority-``completed`` scored events in a 14-day window carry a
    ``final_result`` stamp, because a row ESPN settles never reached the net's
    arm in the first place. Wiring this to the authority's own post/final write
    is the right home for it and is carried forward, not smuggled in here.
    """
    from app.utils.aggregation import stamp_source_reading

    wp_sources = stamp_source_reading(wp_sources, "final_result", resolved_home)
    for src_key in ("kalshi", "polymarket"):
        if src_key not in wp_sources:
            continue
        wp_sources = stamp_source_reading(wp_sources, src_key, resolved_home)
    return wp_sources


def _is_bogus_future_settled(status, commence_time, home_score, away_score, now) -> bool:
    """Invariant guard (gotcha #32/#46): a SETTLED event cannot start in the
    future. ``completed_at >= commence_time`` must hold; a completed/closed event
    whose ``commence_time`` is meaningfully in the future is the cross-merge
    recurrence (#190) — a stale settlement stuck on a row whose ``commence_time``
    was later overwritten to a FUTURE series game (Phillies play the same
    opponent again two nights later; the row is re-used, gotcha #32).

    Only matches rows carrying NO real result (0-0 or null scores) — an MLB/
    NBA/NHL/NFL game can never legitimately finish 0-0, so 0-0 means "never
    played". A settled row with a REAL non-zero score is a DIFFERENT class
    (commence overwrite of a genuinely-played game); we deliberately do NOT
    match it here so un-settling never destroys a real result — that class needs
    a registry-side commence fix, not a status reset.

    A 1h future tolerance avoids a settlement/refinement race on a just-final
    game whose commence is momentarily nudged forward a few minutes.
    """
    if status not in ("completed", "closed"):
        return False
    if commence_time is None or commence_time <= now + timedelta(hours=1):
        return False
    return (home_score in (None, 0)) and (away_score in (None, 0))


#: How far back the ``suspended → live`` arm looks. See the query for why it is
#: not the 24 hours the ``scheduled → live`` arm uses.
SUSPENDED_RESUME_WINDOW = timedelta(hours=48)


async def _transition_event_statuses_impl() -> dict:
    """Transition event statuses based on commence_time (zero API calls).

    This breaks the circular dependency where downstream tasks (ESPN sync,
    StatPal livescores, prediction market live polling) all filter by
    status='live', but that status was only set by Odds API polling which
    may be throttled by quota conservation or adaptive slowdown.

    Transitions:
    - scheduled → live: commence_time <= now (game has started)
    - live → suspended: commence_time + max_duration has passed AND no source
      that REPORTS ON the game has captured a post-commence snapshot in the last
      30 min. Non-terminal, deliberately — see below.
    - suspended → live: a source that reports on the game is captured again.

    That second condition was claimed here for a long time but never actually
    implemented, which made this the producer of the CAL-P002 frozen-final-score
    class: a game running long is closed while still being played, its mid-game
    score becomes the permanent final, and the blend below is graded off it.

    ═══ THIS NET NO LONGER ENDS A MATCH (live/048, CERT-752) ═══

    It used to write ``closed`` here, stamp a ``completed_at`` derived from the
    last snapshot, and resolve the prediction-market blend to 1.0/0.0 off
    whatever score the row happened to be carrying. Every one of those three is
    a claim that a game is OVER, made on the strength of nobody having said
    anything — and ``EVENT-GRAPH-DOCTRINE`` §R puts silence below the lowest
    rung of the state ladder. Only the authority's ``post`` or a venue
    settlement ends a match; this net has neither, so it now writes
    :data:`~app.utils.event_completion.EVENT_SUSPENDED` and grades nothing.

    MEASURED, why it had to change (CERT-752, production 2026-09-02). Six US
    Open matches were suspended mid-match with partial scores — 0-1, 2-1, 1-2,
    0-0, not one a legal completed tennis result — and ESPN had all six
    scheduled to RESUME that afternoon. Fixing the hold guard (a Kalshi price
    tick is not evidence of play) correctly stopped them reading LIVE forever,
    and then handed them straight to this fallback, which produced
    ``status='closed'``, ``pm_resolved=1`` and a blend graded off 1-2. A false
    LIVE traded for a false FINAL, and only one of the two grades.

    MEASURED, what it costs (same date, 14-day window). The prediction-market
    resolution removed from this arm had stamped ``final_result`` on **6** rows
    in fourteen days — 6 of the 1,470 scored settled events in the window, and
    the 6 likeliest of all to have been graded off a partial score, since a row
    the authority settled never reaches this arm at all. The wider
    reclassification is ~500 rows a day moving from ``closed`` to ``suspended``,
    89% of them esports: a category with no schedule-of-record (doctrine rule 8)
    where 47,615 of 48,390 such rows carry no venue market either, so no rung of
    the ladder has ever spoken about them. They stop claiming a Final nobody
    reported. Rows already ``closed`` are left alone — this changes the producer,
    not the history.
    """
    from app.tasks.base import get_task_session
    from app.tasks.config import SPORT_MAX_DURATIONS
    from app.utils.event_completion import commence_time_is_a_reported_start

    stats = {"scheduled_to_live": 0, "live_to_suspended": 0, "suspended_to_live": 0}

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

        # q076: A STAND-IN IS NOT A START, SO IT DOES NOT START THE CLOCK.
        #
        # This promotion is the first domino. Everything downstream measures
        # `hours_since_start` from `commence_time` — this function's own
        # live→closed arm below, and `odds_polling.detect_and_close_stale_events`
        # — so a row promoted off a time nobody reported is settled off one too,
        # at the sport's maximum duration, with no score.
        #
        # `commence_time_is_a_reported_start` reads the writer's own provenance
        # stamp, never the hour or the clustering (q066b: a Saturday 3pm card
        # genuinely is ten simultaneous kickoffs). Measured cost of declining:
        # zero real results — all 705 rows this provenance has ever had closed
        # are unscored. See the predicate for the full census.
        stats["held_derived_start"] = 0

        for event in started_events:
            if not commence_time_is_a_reported_start(event.commence_time_source):
                stats["held_derived_start"] += 1
                continue
            event.status = "live"
            stats["scheduled_to_live"] += 1

        # --- live → suspended (fallback staleness) ---
        # For events that have been "live" longer than their sport's max
        # duration. This is a safety net; the primary mechanism is ESPN
        # sync setting status="completed" when it sees post/final.
        # BR76: previously used a 5-hour hardcoded minimum, causing NBA
        # games (~2.5h) to stay "live" for 2.5+ hours after ending when
        # ESPN sync missed the transition.
        #
        # live/048: the arm still FIRES on exactly the same rows — the change is
        # in what it is entitled to conclude. It stops the row claiming to be
        # live, which is the real defect a stuck row has, and it stops there.

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

        # The guard this docstring has always promised but never implemented.
        # A wall-clock timeout is not evidence a game is over — long games (extra
        # innings, overtime, a rain delay) blow through max_duration while still
        # being played, and closing one freezes whatever mid-game score the last
        # poll wrote AND grades the blend off it. That is the CAL-P002 producer:
        # an NBA row was found settled on a literal halftime score with the
        # derived winner inverted. One batched query answers both "is it still
        # running?" and "when did it end?" (gotcha #22 — completed_at is a
        # game-end time, never a backend processing timestamp).
        from sqlalchemy import text as _sql_text

        from app.utils.event_completion import (
            EVENT_SUSPENDED,
            LAST_POST_COMMENCE_SNAPSHOT_SQL,
            game_may_still_be_running,
        )

        last_snaps: dict = {}
        if live_events:
            last_snaps = {
                row.event_id: row.last_snap
                for row in (await session.execute(
                    _sql_text(LAST_POST_COMMENCE_SNAPSHOT_SQL),
                    {"event_ids": [e.id for e in live_events]},
                )).all()
            }

        stats["held_still_running"] = 0

        for event in live_events:
            sport_key = event.sport.key if event.sport else ""
            max_hours = SPORT_MAX_DURATIONS.get("default", 4.0)
            for prefix, duration in SPORT_MAX_DURATIONS.items():
                if prefix != "default" and sport_key.startswith(prefix):
                    max_hours = duration
                    break

            hours_since_start = (now - event.commence_time).total_seconds() / 3600
            if hours_since_start > max_hours + 0.5:
                last_snap = last_snaps.get(event.id)
                if game_may_still_be_running(last_snap, now):
                    # Leave it live. The next pass re-checks, and a real source
                    # will almost always settle it before we need to guess.
                    stats["held_still_running"] += 1
                    continue

                # SUSPENDED, NOT CLOSED — and nothing else written (live/048).
                #
                # Three writes used to happen here and all three are gone,
                # because each one is a claim that the match is OVER made on the
                # strength of silence:
                #
                #   1. `status = "closed"`. Every client renders closed as
                #      Final. The row is now `suspended`: still wrong to call it
                #      live, still not a claim that anybody won.
                #   2. `completed_at = derive_completed_at(...)`. A game-end
                #      time for a game we cannot say has ended. Leaving it NULL
                #      is the same argument `derive_completed_at` already makes
                #      about `now()` — a visible gap beats a plausible-looking
                #      wrong value nothing will ever question (gotcha #22) — and
                #      it is load-bearing here: `venue_live_write_is_a_
                #      resurrection` reads a NULL `completed_at` as "not
                #      settled", which is what lets the scores feed put a
                #      resumed match straight back to live.
                #   3. The prediction-market resolution to 1.0/0.0 off
                #      `home_score`/`away_score`. This is the one CERT-752
                #      named: those scores are whatever the last poll wrote,
                #      and on a suspended match that is a PARTIAL score. 1-2 in
                #      sets graded as a loss. A score is only a result when
                #      something reported it as one, and silence never does.
                #      Measured cost of removing it: 6 rows in fourteen days.
                event.status = EVENT_SUSPENDED
                stats["live_to_suspended"] += 1
                logger.info(
                    "live/048 suspended event %s (%s vs %s): %.1fh since start "
                    "exceeds the %.1fh %s maximum and no play-reporting source "
                    "has been captured. Not closed, not graded — only an "
                    "authority post or a venue settlement ends a match.",
                    event.id, event.home_team_name, event.away_team_name,
                    hours_since_start, max_hours, sport_key or "default",
                )

        # --- suspended → live (the door back) ---
        #
        # The mirror of the hold above, and what stops `suspended` being a
        # quieter way of stranding a match: the same evidence that would have
        # HELD a live row — a source that reports on the game, captured inside
        # STILL_ACTIVE_MINUTES — puts a suspended row back on court.
        #
        # This is rung 3 of the ladder reaching a row rung 1 cannot. The
        # authority already has its own doors (`espn_helpers` settles or resumes
        # an anchored row directly, and since lane1/057 that includes tennis),
        # but most of the suspended population is in categories no
        # schedule-of-record covers, and for those this is the only way home.
        # It is deliberately the SAME predicate and the SAME venue-price
        # exclusion, so a Kalshi tick cannot resume a match any more than it
        # could hold one.
        suspended_result = await session.execute(
            select(Event).where(
                Event.status == EVENT_SUSPENDED,
                # 48h, NOT the 24h the scheduled→live arm above uses, and the
                # difference is the whole reason this state exists. The
                # canonical case is a US Open match suspended after dark and
                # resumed the following AFTERNOON — the CERT-752 specimen was
                # already 15h past its recorded start when the net first saw it,
                # so a 24h window would have expired on exactly the fixtures
                # this arm is for. 48h covers an overnight suspension plus a
                # full day's slip and still bounds the scan to about a thousand
                # rows at the measured rate, on an indexed column.
                #
                # The bound only limits the NON-authority path. An anchored row
                # — every US Open match, since lane1/057 — is reached by
                # `espn_helpers` directly off its espn_id with no window at all.
                Event.commence_time >= now - SUSPENDED_RESUME_WINDOW,
            )
        )
        suspended_events = suspended_result.scalars().all()

        if suspended_events:
            resume_snaps = {
                row.event_id: row.last_snap
                for row in (await session.execute(
                    _sql_text(LAST_POST_COMMENCE_SNAPSHOT_SQL),
                    {"event_ids": [e.id for e in suspended_events]},
                )).all()
            }
            for event in suspended_events:
                if game_may_still_be_running(resume_snaps.get(event.id), now):
                    event.status = "live"
                    stats["suspended_to_live"] += 1
                    logger.info(
                        "live/048 resumed event %s (%s vs %s): a play-reporting "
                        "source captured it again.",
                        event.id, event.home_team_name, event.away_team_name,
                    )

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

        # --- Repair: SETTLED with a FUTURE commence_time → un-settle ---
        # A settled game cannot start in the future (invariant completed_at >=
        # commence_time, gotcha #32/#46). This is the cross-merge recurrence
        # (#190/Queue #234): a stale settlement (status + completed_at, from an
        # earlier game that never captured a score) stuck on a row whose
        # commence_time was later overwritten to a future series game. The
        # bogus-completed repair above misses these because they DO carry a
        # (phantom) completed_at. Gate on _is_bogus_future_settled so a settled
        # row with a REAL score is never clobbered. Resets to scheduled + clears
        # the phantom completed_at/0-0 scores so live polling re-drives it; the
        # flow-sentinel resolved_state check then reads GREEN.
        stats["unsettled_future_commence"] = 0
        future_settled_result = await session.execute(
            select(Event).where(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time > now + timedelta(hours=1),
            )
        )
        for event in future_settled_result.scalars().all():
            if _is_bogus_future_settled(
                event.status, event.commence_time,
                event.home_score, event.away_score, now,
            ):
                event.status = "scheduled"
                event.completed_at = None
                event.home_score = None
                event.away_score = None
                stats["unsettled_future_commence"] += 1

        # `held_derived_start` is in the trigger and in the message: a guard that
        # declines silently reads as "there was nothing to do", and this one
        # holds ~40 rows a night on its own. Same reason `detect_and_close_stale_
        # events` logs its three held_* counters beside its closed count.
        if (stats["scheduled_to_live"] > 0 or stats["live_to_suspended"] > 0
                or stats["suspended_to_live"] > 0
                or stats["repaired_bogus_completed"] > 0
                or stats["unsettled_future_commence"] > 0
                or stats["held_derived_start"] > 0):
            logger.info(
                "Status transitions: %d scheduled→live, %d live→suspended, "
                "%d suspended→live, %d repaired, %d un-settled-future-commence, "
                "%d held (derived start), %d held (still running)",
                stats["scheduled_to_live"], stats["live_to_suspended"],
                stats["suspended_to_live"],
                stats["repaired_bogus_completed"],
                stats["unsettled_future_commence"],
                stats["held_derived_start"],
                stats["held_still_running"],
            )

    return stats


# #922: realistic per-sport game durations for spacing the ESPN WP backfill
# timeline. ESPN's WP feed returns hundreds of per-play points; the old
# `commence + i*30s` stamping assumed a fixed 30s cadence and overran the real
# game by hours on long games — late-game points (≈100% in a blowout) landed
# past the true end, even into the future, producing the chart "stale tail".
_WP_BACKFILL_DURATION_HOURS = {
    "baseball": 3.5,
    "basketball": 2.75,
    "americanfootball": 3.5,
    "icehockey": 3.0,
    "soccer": 2.5,
    "mma": 3.5,
}
_WP_BACKFILL_DEFAULT_HOURS = 3.0


def _wp_backfill_snap_time(commence, index: int, total: int, sport_key, now):
    """Synthetic captured_at for backfill WP point ``index`` of ``total``.

    Spreads points evenly across a realistic game window [commence, commence +
    sport_duration], hard-clamped to ``now`` so a synthetic timeline can NEVER
    extend past the real game end / current time (the #922 stale-tail bug).
    """
    if not commence:
        return now
    family = (sport_key or "").split("_")[0].lower()
    cap_hours = _WP_BACKFILL_DURATION_HOURS.get(family, _WP_BACKFILL_DEFAULT_HOURS)
    window_end = commence + timedelta(hours=cap_hours)
    if window_end > now:
        window_end = now  # never stamp past the present
    span = max((window_end - commence).total_seconds(), 0.0)
    if total <= 1 or span == 0.0:
        return commence
    return commence + timedelta(seconds=span * (index / (total - 1)))


async def _backfill_espn_win_probability(limit: int = 200, oldest_first: bool = False):
    """Backfill ESPN win probability for completed events with sparse snapshots.

    The live sync captures probability every 60s, but if it misses a game
    (worker downtime, task starvation), that game's probability chart is lost.
    ESPN's /summary endpoint has the full play-by-play probability curve
    retroactively — this task fetches it for recently completed games.
    (Probed 2026-07-15: ESPN still serves the winprobability array for a ~5-month-
    old NBA game — 502 points — so the old tail IS recoverable, not aged out.)

    Processes ALL historical events (no time-window limit). Only processes
    events with espn_id (confirmed match) and fewer than 10
    win_prob_snapshots from the espn source.

    `oldest_first=True` reverses the scan order to reach the OLD tail that the
    default newest-first pass can never drain (gotcha #41: newer rows starve a
    bounded run before it reaches what needs fixing). Wired as a separate daily
    beat so both ends of the backlog make progress.
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
                    ORDER BY e.commence_time """ + ("ASC" if oldest_first else "DESC") + """
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
                    _wp_now = datetime.now(timezone.utc)
                    _wp_total = len(wp_data)

                    for i, point in enumerate(wp_data):
                        home_wp = point.get("home_win_probability")
                        if home_wp is None:
                            continue

                        seconds_left = point.get("seconds_left")
                        # #922: spread points across the real game window (clamped
                        # to now) instead of a naive 30s/point timeline that ran
                        # hours past the game end into the future (the stale tail).
                        snap_time = _wp_backfill_snap_time(
                            commence, i, _wp_total, sport_key, _wp_now
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


#: How far either side of now a tennis event may sit and still be a candidate
#: for today's scoreboard. The board carries a whole tournament — the US Open's
#: 478 singles competitions run from 8/24 qualifying to the final — so the
#: window has to cover a fortnight of draw either way, and bounding it is what
#: keeps 30,199 historical tennis rows out of every cycle.
TENNIS_ANCHOR_WINDOW_DAYS = 21

#: Sport-key prefix for every tennis bucket: `tennis_atp`, `tennis_wta`,
#: `tennis_other`, and the per-tournament keys below them.
TENNIS_SPORT_KEY_PREFIX = "tennis"


async def _sync_tennis_from_espn(limit: int = 1000, dates: str | None = None) -> dict:
    """Anchor tennis events to ESPN competitions, then let ESPN write their state.

    ═══ THE GAP THIS CLOSES (lane1/057 STEP 0) ═══

    This module had no tennis path — the string appeared zero times in 1,739
    lines — and could not have had one: every write here goes through
    ``espn_id``, and on 2026-09-02 **zero of 30,199 tennis events had one**.  So
    the sport whose fixtures move most (a start slips hours behind a five-setter
    on the same court) was the one sport the authority could not correct, and
    what corrected it instead was a wall-clock staleness net.  Three US Open
    rows held ``status='live'`` AND a ``completed_at`` simultaneously as a
    result, which the serve layer resolves as *completed* — a card printing
    "Final" over a match in its fourth set.

    ONE fetch, both jobs.  The anchor and the state write read the same
    scoreboard in the same pass deliberately: fetching twice would double the
    load on ESPN and, worse, let the link and the state come from two different
    boards, so a match could be anchored from one read and settled from another
    taken minutes later.

    Per-event ``try``/``except`` (gotcha #42): one unparseable row must never
    cost the pass its other 193.
    """
    from app.services import espn_tennis
    from app.utils.espn_tennis_anchor import (
        anchor_receipt,
        anchorable_sport_keys,
        authority_score_write,
        authority_write,
        games_line_write,
        state_contradiction,
    )
    from app.utils.espn_id_stamp import STAMPED, stamp_espn_id_if_unheld
    import asyncio as _asyncio

    stats: dict = {
        "tours_fetched": 0,
        "fetch_errors": [],
        "competitions": 0,
        "events_considered": 0,
        "anchored": 0,
        "already_anchored": 0,
        "by_method": {},
        "refused": {},
        "status_writes": 0,
        "completions_revoked": 0,
        "commence_writes": 0,
        # lane1/064: the score half. `score_writes` counts rows the authority
        # moved; `score_blanks_filled` is the SHIP — a settled row that printed
        # nothing and now prints the result; `score_corrections` is a row whose
        # existing score the authority overruled. `score_refused` is keyed by
        # reason, because "no score" is four different findings.
        "score_writes": 0,
        "score_blanks_filled": 0,
        "score_corrections": 0,
        "score_refused": {},
        # live/073: the GAMES line, off the same read. `line_writes` counts rows
        # whose stored line the authority moved; `line_refused` is keyed by
        # reason for the same reason `score_refused` is.
        "line_writes": 0,
        # Re-confirmations of an UNCHANGED in-play line (#3242). Kept apart from
        # `line_writes` so that metric stays a count of movement; this one is a
        # count of live rows the pass reached, which is the other useful number.
        "line_stamp_refreshes": 0,
        "line_refused": {},
        "contradictions": {},
        "row_errors": 0,
        "stamp_refused": 0,
    }

    # ═══ THE BOARD ═══
    #
    # `fetch_scoreboards` is the synchronous reader `espn_tennis` exposes for
    # offline ingest; run OFF THE LOOP rather than called directly, because it
    # is two blocking httpx requests and this task shares a worker with the
    # realtime queue.
    payloads, errors = await _asyncio.to_thread(espn_tennis.fetch_scoreboards, dates)
    stats["tours_fetched"] = len(payloads)
    stats["fetch_errors"] = errors

    if not payloads:
        # AUTHORITY DARK. Both tours failed, so we know nothing — and an empty
        # board is a fact about the read, never about the fixtures (gotcha #53).
        # Returning early rather than iterating means not one row is touched.
        logger.warning("Tennis ESPN sync: authority dark, both tours failed: %s", errors)
        return {"status": "authority_dark", **stats}

    competitions = espn_tennis.scoreboard_competitions(payloads)
    stats["competitions"] = len(competitions)
    by_id = {c["espn_competition_id"]: c for c in competitions}

    if not competitions:
        # A 200 that mentions no singles competition is an empty answer wearing
        # a 200 — no tournament today, or a scoreboard that has rolled over.
        logger.info("Tennis ESPN sync: no singles competitions on the board")
        return {"status": "no_competitions", **stats}

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=TENNIS_ANCHOR_WINDOW_DAYS)
    window_end = now + timedelta(days=TENNIS_ANCHOR_WINDOW_DAYS)

    async with get_task_session() as session:
        # ═══ ONLY THE BUCKETS THAT NAME A TOURNAMENT ON THIS BOARD ═══
        #
        # See `anchorable_sport_keys`. Widening this to every `tennis%` row does
        # not add coverage — it adds CONTESTS, because a `tennis_atp` row and its
        # `tennis_atp_us_open` twin are one match written twice and the
        # at-most-one-event rule then anchors neither.
        #
        # Resolved as a cheap DISTINCT over `sports` rather than a LIKE over
        # `events`: the token comparison is a fold ESPN's "US Open" and our
        # `us_open` both pass through, and expressing that in SQL would mean
        # de-normalising the token back into a pattern and getting the rule
        # subtly different from the one in the anchor module.
        key_rows = await session.execute(
            select(Sport.key).where(Sport.key.like(f"{TENNIS_SPORT_KEY_PREFIX}%"))
        )
        wanted_keys = anchorable_sport_keys(
            [k for (k,) in key_rows.all()], competitions
        )
        stats["sport_keys"] = wanted_keys
        if not wanted_keys:
            # The board carries a tournament we hold no bucket for. Not an
            # error, and not something to widen our way out of.
            logger.info(
                "Tennis ESPN sync: board carries %s, no matching sport bucket",
                sorted({c["event_name"] for c in competitions})[:5],
            )
            return {"status": "no_matching_bucket", **stats}

        result = await session.execute(
            select(Event)
            .join(Sport, Sport.id == Event.sport_id)
            .where(
                Sport.key.in_(wanted_keys),
                Event.commence_time.isnot(None),
                Event.commence_time >= window_start,
                Event.commence_time <= window_end,
                Event.home_team_name.isnot(None),
                Event.away_team_name.isnot(None),
            )
            .order_by(Event.commence_time.desc())
            .limit(limit)
        )
        events = result.scalars().all()
        stats["events_considered"] = len(events)

        # ═══ PHASE 1: RECEIPTS FOR EVERY ROW, WRITES FOR NONE ═══
        #
        # Anchoring is resolved for the whole population BEFORE anything is
        # written, because "is this competition contested" is a question about
        # the set and a row-at-a-time loop cannot ask it.
        receipts: dict[int, dict] = {}
        claimants: dict[str, list[int]] = {}
        for event in events:
            try:
                # `our_commence_time` is the TOURNAMENT discriminator, and it is
                # load-bearing: the unordered pair is a key within a draw and
                # not across them, so two players who met in Cincinnati and
                # again at Flushing Meadows produce one key for two matches.
                # Without it, 58 competitions were claimed by more than one of
                # our events and the authority write became a channel for
                # copying the US Open's state onto a Cincinnati row.
                receipt = anchor_receipt(
                    [event.home_team_name, event.away_team_name],
                    competitions,
                    our_commence_time=event.commence_time,
                )
            except Exception as exc:  # noqa: BLE001
                stats["row_errors"] += 1
                logger.warning("Tennis anchor: event %s failed: %s", event.id, exc)
                continue
            receipts[event.id] = receipt
            if receipt["espn_competition_id"]:
                claimants.setdefault(receipt["espn_competition_id"], []).append(event.id)

        # ═══ AN ESPN COMPETITION ANCHORS AT MOST ONE OF OUR EVENTS ═══
        #
        # THE INVARIANT, ENFORCED AT WRITE TIME RATHER THAN HOPED FOR. Measured
        # 2026-09-02 over the 1,000 in-window tennis rows: even with the
        # tournament gate, **47 competitions were claimed by two of our events**
        # — genuine duplicate instances of one match (a `tennis_wta` row and its
        # `tennis_wta_us_open` twin, or two rows in the same bucket).
        #
        # Writing the id on both would not merely record a duplicate. It would
        # ARM `merge-duplicate-events`, which runs every 30 minutes with
        # `dry_run=False` and DELETES the loser of any same-sport, same-name,
        # within-6h pair **that shares a provider id** — and `espn_id` is one of
        # the three (`event_merge_invariant.PROVIDER_ID_COLUMNS`). Tennis is
        # immune to that path today only because no tennis row has an `espn_id`.
        # Stamping twins would hand a data-destructive task a sport it has never
        # touched, as a side effect of a job that was asked to write a link.
        #
        # So a contested competition anchors NOBODY, and the contest is reported
        # with both event ids. Refusing is also the honest answer: we do not know
        # which twin is canonical, and picking one silently is a guess. The twin
        # cleanup is its own step of the durable-matching program (#2693 step 2),
        # where it re-points links rather than deleting rows.
        contested = {c: ids for c, ids in claimants.items() if len(ids) > 1}
        stats["contested_competitions"] = len(contested)
        stats["contested_events"] = sum(len(ids) for ids in contested.values())
        stats["contested_detail"] = {c: ids for c, ids in list(contested.items())[:50]}
        for comp, ids in contested.items():
            logger.warning(
                "Tennis anchor CONTESTED: ESPN %s claimed by events %s — none anchored",
                comp, ids,
            )

        # ═══ PHASE 2: THE WRITES ═══
        #
        # `claimed` is `stamp_espn_id_if_unheld`'s in-pass set. It overlaps the
        # contested check above and is kept anyway: that check can only see the
        # population THIS pass selected, and the twin of a US Open row lives in
        # `tennis_atp`, which this pass deliberately does not query.
        claimed_ids: set = set()
        for event in events:
            try:
                receipt = receipts.get(event.id)
                if receipt is None:
                    continue
                ours = [event.home_team_name, event.away_team_name]
                comp_id = receipt["espn_competition_id"]

                if comp_id is not None and len(claimants.get(comp_id, [])) > 1:
                    # Contested — see the block above. Not counted as a refusal:
                    # the matcher did its job, and the defect is that two of our
                    # rows are one match.
                    continue

                if comp_id is None:
                    reason = receipt["reason"]
                    stats["refused"][reason] = stats["refused"].get(reason, 0) + 1
                    # A REFUSAL IS A FINDING, NOT A MISS. `absent_players` names
                    # the player ESPN's draw does not contain, which is the
                    # difference between "our matcher is weak" and "this fixture
                    # is fabricated" — and only the second is actionable.
                    if receipt["absent_players"]:
                        logger.warning(
                            "Tennis anchor REFUSED event %s (%s v %s): %s — not in draw: %s",
                            event.id, ours[0], ours[1], reason,
                            ", ".join(receipt["absent_players"]),
                        )
                    continue

                if event.espn_id == comp_id:
                    stats["already_anchored"] += 1
                else:
                    # THROUGH THE GUARDED STAMP, NOT A RAW ASSIGNMENT (#2017,
                    # ruling 042). It asks the question this task cannot: does
                    # ANOTHER ROW ALREADY HOLD THIS ID — a database check, where
                    # the contested pass above is only an in-memory one over the
                    # rows this task selected. `ix_events_espn_id` is not UNIQUE,
                    # so nothing else would refuse the contradiction.
                    verdict, holder = await stamp_espn_id_if_unheld(
                        session, event, comp_id,
                        context="tennis-espn-anchor", claimed=claimed_ids,
                    )
                    if verdict != STAMPED:
                        # Refused, so this row has no anchor and the authority
                        # has no channel to it. Writing state anyway would be
                        # the link's authority without the link.
                        stats["stamp_refused"] = stats.get("stamp_refused", 0) + 1
                        if holder is not None:
                            stats.setdefault("stamp_refused_holders", {})[
                                str(event.id)] = holder
                        continue
                    stats["anchored"] += 1
                    method = receipt["method"]
                    stats["by_method"][method] = stats["by_method"].get(method, 0) + 1
                    logger.info(
                        "Tennis anchor: event %s (%s v %s) -> ESPN %s via %s",
                        event.id, ours[0], ours[1], comp_id, method,
                    )

                competition = by_id[comp_id]

                # REPORTED BEFORE IT IS REPAIRED. The contradiction is counted
                # against the state we found, so the needle measures the defect
                # rather than the fix — a count that drops because this pass
                # already wrote is a count that can never reach zero honestly.
                contradiction = state_contradiction(
                    event.status, event.completed_at, competition["state"],
                    competition=competition, now=now,
                )
                if contradiction:
                    stats["contradictions"][contradiction] = (
                        stats["contradictions"].get(contradiction, 0) + 1
                    )
                    logger.warning(
                        "Tennis contradiction %s: event %s (%s v %s) ours=%s/%s espn=%s",
                        contradiction, event.id, ours[0], ours[1],
                        event.status, event.completed_at, competition["state"],
                    )

                changes = authority_write(
                    now=now,
                    our_status=event.status,
                    our_completed_at=event.completed_at,
                    our_commence_time=event.commence_time,
                    competition=competition,
                )
                if "status" in changes:
                    event.status = changes["status"]
                    stats["status_writes"] += 1
                if "completed_at" in changes:
                    # THE REVOKE — the clause that did not exist anywhere.
                    event.completed_at = changes["completed_at"]
                    stats["completions_revoked"] += 1
                    logger.warning(
                        "Tennis close REVOKED: event %s (%s v %s) — ESPN reports play",
                        event.id, ours[0], ours[1],
                    )
                if "commence_time" in changes:
                    event.commence_time = changes["commence_time"]
                    stats["commence_writes"] += 1

                # ═══ THE SCORE, THROUGH THE SAME ANCHOR AND THE SAME READ ═══
                #
                # 37 anchored US Open rows were `closed` with no score at all
                # while ESPN held the full result — Alcaraz over Safiullin
                # 6-4, 6-4, 6-4, closed blank by a wall-clock net on an Odds API
                # session-start default. A search for "Safiullin" returned seven
                # cards saying FINAL with nothing under them.
                #
                # Deliberately AFTER the state block and unconditional on it: a
                # `decided` row that is already settled gets NO status change
                # (`closed` and `completed` are both settled and churning one
                # into the other rewrites history for no reader) — which is
                # exactly the population that has been blank for four days. A
                # score write gated on a status write would have skipped all 37.
                was_blank = event.home_score is None and event.away_score is None
                score = authority_score_write(
                    ours=ours,
                    our_home_score=event.home_score,
                    our_away_score=event.away_score,
                    competition=competition,
                )
                if score["reason"] is not None:
                    stats["score_refused"][score["reason"]] = (
                        stats["score_refused"].get(score["reason"], 0) + 1
                    )
                elif score["changes"]:
                    # BOTH NUMBERS READ BEFORE EITHER IS WRITTEN — the log below
                    # is a before/after and would print the same pair twice if
                    # the assignment came first.
                    before = (event.home_score, event.away_score)
                    event.home_score = score["changes"].get(
                        "home_score", event.home_score
                    )
                    event.away_score = score["changes"].get(
                        "away_score", event.away_score
                    )
                    stats["score_writes"] += 1
                    if was_blank:
                        stats["score_blanks_filled"] += 1
                    else:
                        # THE AUTHORITY OVERRULING A SCORE FEED (§R rung 1 over
                        # rung 3). Logged at WARNING with both numbers: a
                        # correction is a claim that something else was wrong,
                        # and it should be readable without a database.
                        stats["score_corrections"] += 1
                        logger.warning(
                            "Tennis score CORRECTED: event %s (%s v %s) %s-%s -> %s-%s",
                            event.id, ours[0], ours[1],
                            before[0], before[1],
                            event.home_score, event.away_score,
                        )

                # ═══ AND THE GAMES UNDER IT (live/073) ═══
                #
                # The set score says WHO won; the line says what by. A US Open
                # match page prints `0 – 3` today and, three cards further
                # down, "the scoreboard reports sets, this market quotes games
                # — we did not record the games played" over a Games map frozen
                # on its pre-game quote. Measured 2026-09-05: 207 of the 211
                # settled tennis rows of the last 10 days are anchored here, and
                # 0 of 211 carry any box score — so every one of those pages
                # says it. The number was already in `competition["sides"]`,
                # parsed, on the read this task was already doing.
                #
                # Unconditional on the score write above for the same reason
                # that one is unconditional on the state write: the population
                # that needs it most is the row the authority already agrees
                # with, which produces no `changes` at all.
                # `observed_at` is this pass's clock, and it is what makes the
                # page able to say how old the games count is (#3242). Measured
                # on production 2026-09-05: ESPN had a match's first game at
                # 15:12, our page showed it at 15:22, and nothing on the page
                # said so — the `LIVE · 1s ago` badge beside it is the win-prob
                # write's age, a different number entirely. Only in-play rows
                # are stamped; see `games_line_write`.
                line = games_line_write(
                    ours=ours,
                    our_box_score_data=event.box_score_data,
                    competition=competition,
                    observed_at=now,
                )
                if line["reason"] is not None:
                    stats["line_refused"][line["reason"]] = (
                        stats["line_refused"].get(line["reason"], 0) + 1
                    )
                elif line["box_score_data"] is not None:
                    # A WHOLE NEW DICT, not a key set on the old one — an
                    # in-place JSONB edit does not flush (gotcha #4).
                    event.box_score_data = line["box_score_data"]
                    # MOVEMENT AND CONFIRMATION ARE COUNTED APART. `line_writes`
                    # has always meant "the line changed"; re-stamping an
                    # unchanged in-play line is a different event and folding it
                    # in would turn the metric into a count of live rows.
                    if line["moved"]:
                        stats["line_writes"] += 1
                    else:
                        stats["line_stamp_refreshes"] += 1

            except Exception as exc:  # noqa: BLE001 — one row never costs the pass
                stats["row_errors"] += 1
                logger.warning("Tennis ESPN sync: event %s failed: %s", event.id, exc)

        await session.commit()

    logger.info(
        "Tennis ESPN sync: %d events, %d anchored (%d already), %d refused, "
        "%d status writes, %d closes revoked, %d contradictions, "
        "%d score writes (%d blanks filled, %d corrected), %d scores refused, "
        "%d games lines written (%d in-play re-stamped), %d lines refused",
        stats["events_considered"], stats["anchored"], stats["already_anchored"],
        sum(stats["refused"].values()), stats["status_writes"],
        stats["completions_revoked"], sum(stats["contradictions"].values()),
        stats["score_writes"], stats["score_blanks_filled"],
        stats["score_corrections"], sum(stats["score_refused"].values()),
        stats["line_writes"], stats["line_stamp_refreshes"],
        sum(stats["line_refused"].values()),
    )
    return {"status": "ok", **stats}
