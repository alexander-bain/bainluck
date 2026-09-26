"""
ESPN live sync, metadata enrichment, and team logo backfill tasks.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, distinct, and_, or_, func, literal
from sqlalchemy.orm import selectinload

from app.models import Event, Sport
from app.tasks.base import get_task_session, run_async
from app.tasks.config import ESPN_SPORT_MAPPING
# #3473. Imported as a module rather than by name so the two consuming loops
# below read `_failover.espn_reading(...)` — at the exact lines that used to say
# `espn_data.get(sport_key, [])`, the reader can see that a reading is being
# taken and go and find out what the three of them are.
from app.utils import authority_failover as _failover
from app.utils.event_completion import (
    AUTHORITY_BACKFILL_STATUS_SQL,
    AUTHORITY_BACKFILL_STATUSES,
    SETTLEABLE_STATUSES,
    UNSTARTED_SETTLEABLE_STATUSES,
    espn_board_date,
)
from app.utils.start_time_authority import provider_may_set_start
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


# `_sanitize_period` and its pattern moved to `app/utils/game_state.py` in #5390
# and are re-exported here so every existing importer keeps working.
#
# WHY THEY MOVED. The predicate is a pure statement about period strings, which
# is what `game_state` already is (`normalize_live_game_state` lives beside it)
# and that module imports nothing but `re`. Their old home here made every
# caller in `utils/espn_helpers.py` reach BACK into `app.tasks.espn_sync` — a
# genuine cycle, since this module imports `espn_helpers` in turn — which is
# why all five call sites used function-local imports to dodge it. CodeQL
# flagged three of them (`py/cyclic-import`) the moment #5390 added more.
# A leaf home removes the cycle instead of tiptoeing around it, and the five
# sites now share one module-level import.
from app.utils.game_state import (  # noqa: F401
    _PREGAME_DATE_RE,
    _sanitize_period,
)


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

    **AND FOR TWO SPORTS THERE IS NO READ TO HAND IT (#4320).** Soccer and
    tennis serve their schedule one calendar board at a time with no board for
    today, so no `day_offset` reaches that window — see
    `StatPalAPIService.schedule_can_cover_today`. They return
    `NO_SCHEDULE_BOARD`, which is neither an outage nor a claim of no games, and
    they return it without making a network call.
    """
    from app.services.statpal_api import (
        StatPalAPIService,
        StatPalUpstreamError,
        is_available,
        schedule_can_cover_today,
    )
    from app.utils.authority_failover import (
        DARK,
        NO_SCHEDULE_BOARD,
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

    if not schedule_can_cover_today(statpal_sport):
        # SOCCER AND TENNIS — nine of the fourteen mapped keys (#4320). Their
        # schedule is one calendar board at a time and there is no board for
        # today, so `get_schedule_fixtures` cannot be given a token that reaches
        # `reading_in_window`'s `[now - 6h, now]`. Asked BY NAME and before the
        # call, rather than by calling without a token and catching the
        # `ValueError` that comes back: that exception is this caller's bug and
        # the client raises it precisely so the two cannot arrive as one value —
        # *"a caller bug, not an upstream absence, and the two must not arrive as
        # the same empty list"*. Laundering it through the `except` below would
        # report a permanent property of StatPal's product as `STANDBY_DARK`,
        # which is a BLANK code an actor logs at ERROR, and send an operator to
        # look at a StatPal that is answering perfectly.
        return NO_SCHEDULE_BOARD, NO_SCHEDULE_BOARD

    service = StatPalAPIService()
    try:
        try:
            fixtures = await service.get_schedule_fixtures(statpal_sport)
        except StatPalUpstreamError as exc:
            logger.warning("StatPal standby schedule dark for %s: %s", sport_key, exc)
            return DARK, DARK
        except ValueError as caller_bug:
            # Bound as `caller_bug` rather than the `exc` its sibling arms use,
            # and NOT as a matter of taste. `scan_mutation_residue` (Pass B)
            # matches a mutant's replacement text as a plain SUBSTRING of any
            # changed file, and `futures_categories_warm_mutations:M9` replaces
            # a line whose entire text is this arm's ordinary spelling — four
            # spaces, then `except`, `ValueError`, `as exc` and a colon. So that
            # spelling IS another harness's mutant, and writing it here reds the
            # repo-wide guard on a line of honest source. Renaming the binding
            # is what clears it: a trailing comment does not, because the
            # literal would still be present, and neither does re-indenting,
            # because eight spaces contain four. (For the same reason this
            # comment describes the string instead of quoting it.)
            #
            # OUR bug, not StatPal's: `get_schedule_fixtures` raises this only
            # for a missing or out-of-range `day_offset`, which the guard above
            # exists to make unreachable. Kept, because "unreachable" is a claim
            # about today's mapping and this path is the one that would be wrong
            # if a new day-board sport were added to `STATPAL_SPORT_MAPPING`
            # without being added to `DAY_BOARD_SPORTS`. Logged at ERROR and
            # reported as a boundary rather than as an outage — reported and not
            # raised, because an exception out of here would be an outage in the
            # sport this whole path exists to protect (see `STANDBY_NOT_READ`).
            logger.error(
                "StatPal standby schedule CALLER BUG for %s — not an outage: %s",
                sport_key, caller_bug,
            )
            return NO_SCHEDULE_BOARD, NO_SCHEDULE_BOARD
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
    both holding a copy that can drift.

    **D104 = A4 (2026-09-09) made this path reach the network.** It used to make
    no StatPal call at all, because `flip_permitted` refused every sport. Now a
    sport in `FLIP_RULED_WITHOUT_STREAK` — read the frozenset, which has grown
    twice since this line was written (#4493, #4436) and whose members are not
    restated here for that reason (#5139) — gets its standby read
    on a pass where ESPN went dark for it: one `get_schedule_fixtures` and one
    `livescores`, via `_statpal_standby_reading`. Every other silent sport still
    costs exactly one durable ledger read and no network call, because it refuses
    at the gate first.

    **A STANDING sport reaches the network whatever the gate says (#4434),** and
    that is the point: `flip_permitted` asks "may this sport flip?", a sport that
    already has is not asking, and the standby questions are what it does need
    answered. `decide` skips the gate for it and returns `STANDBY_NOT_READ`, so
    the re-read below fires for it exactly as it does for a dark candidate. No
    sport is standing today — `AUTHORITY_BY_SPORT` is all ESPN — so this costs
    nothing until the first flip, which is the flip #4434 exists to make safe.
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
            gate = (
                failover.gate_on_unreadable_ledger(sport_key, ledger_why)
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

    **ONE OF THE TWO WRITERS IS PER SPORT AND THE OTHER IS PER PASS**, because
    that is what their signatures mean. The schedule writer takes a sport key
    and runs once per served sport; the livescore writer takes none, covers
    every live sport in one call, and so runs **once for the whole pass** no
    matter how many sports failed over (`_serve_live_from_statpal`, paying
    CERT-2052's `STANDING-STATPAL-FAILOVER-COALESCING`).

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

    **AND IT SERVES A FLIPPED SPORT THE SAME WAY (#4434).** A sport whose
    `AUTHORITY_BY_SPORT` entry is already StatPal reaches `STANDING_STATPAL`
    only after answering every standby question a failover candidate answers,
    and is then served by these same two writers — counted as
    `standing_serving`, never as `failover_serving`, because it is not in an
    outage and reporting it as one would show a permanent degradation for as
    long as it stayed flipped. Before #4434 that code was in neither set the
    loop branches on: it fell through to the `else` and logged an INFO over a
    pass that wrote no fixtures, no score and no clock.

    THE REFUSALS ARE THE OTHER HALF, and they are not consolation. `is_unserved`
    — ESPN silent AND the standby FAILED when asked — is the state where nothing
    can say what is happening in a game that is on. Logged at ERROR and counted
    apart, because every other refusal is a fact about the day and this one is a
    fault.

    **The question is asked of the DECISION, not of its code**, because one
    refusal means different things on the two paths.
    `STANDBY_CANNOT_COVER_WINDOW` is a sport StatPal publishes no board for
    (soccer and tennis, permanently — #4320). For a failover CANDIDATE that is a
    boundary of StatPal's product rather than an event on this pass: benign, not
    in `BLANK_CODES`, logged at INFO with the rest. For a sport already FLIPPED
    to StatPal it is the source of record failing to cover its own sport, which
    is a blank. Same code, opposite severity — see `is_unserved`.

    **The receipts.** Every decision that is not the ordinary `ESPN_ANSWERED` is
    published on the task summary, served or not — an outage the site rode out
    is otherwise indistinguishable from one that never happened. A per-pass
    series rather than edge-triggered records, so activation and deactivation
    are both recoverable by differencing consecutive passes and no stored flag
    can be stranded by a lost write.
    """
    from app.utils.authority_failover import (
        FAILOVER_CODES,
        STANDING_STATPAL,
        is_unserved,
    )

    receipts = []
    served: list[str] = []
    for sport_key in sorted(decisions):
        decision = decisions[sport_key]
        receipts.append(decision.as_receipt())

        if decision.code in FAILOVER_CODES:
            stats["failover_serving"] = stats.get("failover_serving", 0) + 1
            logger.warning(
                "AUTHORITY FAILOVER for %s (%s): %s",
                sport_key, decision.code, decision.why,
            )
            served.append(sport_key)
            await _serve_schedule_from_statpal(sport_key, stats)
        elif decision.code == STANDING_STATPAL:
            # #4434. A FLIPPED sport, whose standby has just answered every
            # question a failover candidate's does. It is served by the same two
            # writers and counted APART: this is not an outage, it is the normal
            # state of a sport whose source of record is StatPal, and folding it
            # into `failover_serving` would report a permanent degradation for
            # as long as it stayed flipped.
            #
            # Before #4434 this branch did not exist: `STANDING_STATPAL` was in
            # neither set, fell to the `else`, and logged an INFO over a pass
            # that wrote no fixtures, no score and no clock.
            stats["standing_serving"] = stats.get("standing_serving", 0) + 1
            logger.info(
                "AUTHORITY STANDING for %s (%s): %s",
                sport_key, decision.code, decision.why,
            )
            served.append(sport_key)
            await _serve_schedule_from_statpal(sport_key, stats)
        elif is_unserved(decision):
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

    # ONE live write for the whole pass, however many sports failed over.
    # `STANDING-STATPAL-FAILOVER-COALESCING` (CERT-2052), paid before it could
    # bite: see `_serve_live_from_statpal`.
    if served:
        await _serve_live_from_statpal(served, stats)

    if receipts:
        stats["failover"] = receipts


async def _serve_schedule_from_statpal(sport_key: str, stats: dict) -> None:
    """Run StatPal's schedule writer for ONE sport, now, inside this pass.

    The per-sport half of serving. `_sync_statpal_schedules` takes a sport key
    and writes that sport's fixtures, so it is called once per failed-over
    sport and there is nothing to coalesce here — three dark sports need three
    schedule writes because they are three different reads.

    Guarded and counted on its own. A schedule write that worked and a live
    write that failed is a real, partial outcome and must not be reported as
    either a clean serve or a total failure.
    """
    from app.tasks.statpal_sync import _sync_statpal_schedules

    try:
        result = await _sync_statpal_schedules(sport_key)
        stats["failover_schedule_writes"] = (
            stats.get("failover_schedule_writes", 0) + 1
        )
        logger.info("failover schedule write for %s: %s", sport_key, result)
    except Exception as exc:  # noqa: BLE001 — counted, never swallowed
        stats["errors"].append(f"failover_schedule_{sport_key}: {exc}")
        logger.warning("failover schedule write failed for %s: %s", sport_key, exc)


async def _serve_live_from_statpal(sports: list[str], stats: dict) -> None:
    """Run StatPal's livescore writer ONCE for every sport this pass served.

    **`_sync_statpal_livescores()` takes no sport key.** It looks up every sport
    that currently has a live event in our database and advances all of them, so
    one call already covers every failed-over sport. The first cut called it
    from inside the per-sport loop, which was harmless while at most one sport
    could ever be permitted and became N identical full passes over every live
    sport the moment two could — N times the StatPal calls and N times the
    writes, inside a beat that already runs every 30 seconds.

    That is CERT-2052's `STANDING-STATPAL-FAILOVER-COALESCING`: *"before multiple
    sports flip, call the global livescore writer once per pass or prove
    300-second runtime and concurrent-write idempotence against its 30-second
    beat."* This is the first branch, taken deliberately — the cheap fix, made
    before the condition that needs it (NFL, NBA and NHL are all at day 2 of
    D50's seven as of 2026-09-06, so they can first flip together).

    WHAT IS NOT PRESERVED, said out loud: calling it N times used to mean N-1
    incidental retries if the first call raised. That was never a designed
    retry and it is not one worth buying at this price — the livescore beat's
    own 30-second cadence is the retry, and a failure here is recorded rather
    than swallowed.

    Counted so the summary cannot be misread. `failover_live_writes` counts
    CALLS (0 or 1 per pass, unchanged for the one-sport case that is all
    production can reach today) and `failover_live_sports_covered` counts the
    sports that call served — because "one live write" beside "three sports
    served" is otherwise indistinguishable from two sports going unserved.
    """
    from app.tasks.statpal_sync import _sync_statpal_livescores

    covered = ",".join(sports)
    try:
        result = await _sync_statpal_livescores()
        stats["failover_live_writes"] = stats.get("failover_live_writes", 0) + 1
        stats["failover_live_sports_covered"] = (
            stats.get("failover_live_sports_covered", 0) + len(sports)
        )
        logger.info("failover live write (for %s): %s", covered, result)
    except Exception as exc:  # noqa: BLE001 — counted, never swallowed
        # One error for one failed call, naming every sport it left uncovered.
        # Byte-identical to the old per-sport string when one sport served.
        stats["errors"].append(f"failover_live_{covered}: {exc}")
        logger.warning("failover live write failed for %s: %s", covered, exc)


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

            # ── Ask the authority about the day the match is filed under ──
            #
            # BEFORE the no-live-games return, deliberately. A straggler is
            # precisely a row nothing is live for any more, so gating this pass
            # on today's slate would skip exactly the population it exists to
            # reach — and `_find_sport_keys_to_sync` has no `suspended` arm, so
            # a sport whose only unsettled row is suspended contributes nothing
            # to `live_sport_keys` at all.
            straggler_espn = ESPNAPIService()
            try:
                await _settle_authority_stragglers(
                    session,
                    straggler_espn,
                    datetime.now(timezone.utc),
                    stats,
                    update_event_fields_from_espn,
                )
            except Exception as e:
                stats["errors"].append(f"authority_stragglers: {str(e)}")
                logger.warning(
                    "Authority straggler pass failed: %s", e, exc_info=True
                )

            # ── And the rows that aged out of that window entirely (#6280) ──
            #
            # Its OWN try/except, not the one above: the two arms select
            # disjoint populations, so a failure to reach the stranded backlog
            # must not cost the liveness-adjacent pass its run, or the reverse.
            try:
                await _settle_deep_authority_stragglers(
                    session,
                    straggler_espn,
                    datetime.now(timezone.utc),
                    stats,
                    update_event_fields_from_espn,
                )
            except Exception as e:
                stats["errors"].append(f"deep_authority_stragglers: {str(e)}")
                logger.warning(
                    "Deep authority straggler pass failed: %s", e, exc_info=True
                )

            # ── And the stranded rows that were never LATE, only MISDATED ──
            #
            # Third try/except for the same reason the second one exists: this
            # arm asks a different channel (the anchor, not the board) and a
            # failure here must not cost the two settle passes their run. It
            # runs AFTER them deliberately — a row the settle door has just
            # finished has left the candidate states and is never re-examined.
            try:
                await _recover_unstarted_authority_fixtures(
                    session,
                    straggler_espn,
                    datetime.now(timezone.utc),
                    stats,
                )
            except Exception as e:
                stats["errors"].append(f"unstarted_authority_recovery: {str(e)}")
                logger.warning(
                    "Unstarted authority recovery pass failed: %s", e, exc_info=True
                )
            finally:
                await straggler_espn.close()

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
            full_slate_boards: dict = {}
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
                # #8682. The pre-game pass's own board, fetched through the same
                # connection. Only for sports whose undated board is a featured
                # slice (`ESPN_FULL_SLATE_GROUPS`); the live pass keeps
                # `espn_data`, so what it matches and creates from is unchanged.
                full_slate_boards = await _fetch_full_slate_boards(
                    espn, scheduled_sport_keys, stats
                )
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

            # #5697. Its own service, and it has to outlive the fetch loop
            # above — that one closes `espn` in a `finally` before this pass
            # ever runs, so the second question cannot be asked through it.
            # Opened here rather than per sport so one connection pool serves
            # the whole pass, and closed below whatever the loop does.
            widen_espn = ESPNAPIService()

            async def _fetch_dated_board(sport_key: str, board_day: str):
                return await widen_espn.get_scoreboard(sport_key, date=board_day)

            try:
                for sport_key in live_sport_keys:
                    stats["sports_checked"] += 1

                    if sport_key not in ESPN_SPORT_MAPPING:
                        continue

                    # `espn_data.get(sport_key, [])` used to stand here, and it
                    # is the line #3473 is about: it mapped "ESPN went dark" and
                    # "ESPN says there are no games" onto one `[]` and one
                    # `continue`, undoing the distinction the fetch loop above
                    # had just taken care to preserve. The reading keeps the two
                    # apart; the branch below is the same for both because there
                    # is nothing ESPN can contribute either way, and what
                    # differs — whether anything fails over — was decided above.
                    if (
                        _failover.espn_reading(espn_data, sport_key)
                        != _failover.FIXTURES
                    ):
                        continue
                    espn_events = espn_data[sport_key]

                    try:
                        await _process_live_sport(
                            session, sport_key, espn_events, stats,
                            recently_completed_cutoff, started_cutoff,
                            espn_names_match, upsert_team,
                            register_espn_team_identities,
                            match_event_to_espn, update_event_fields_from_espn,
                            write_espn_win_probability,
                            compute_and_write_stat_model,
                            create_events_from_unmatched_espn,
                            dated_board_fetcher=_fetch_dated_board,
                        )
                    except Exception as e:
                        stats["errors"].append(f"{sport_key}: {str(e)}")
            finally:
                await widen_espn.close()

            # ── Second pass: scheduled events (team pre-population) ─
            for sport_key in scheduled_sport_keys:
                if sport_key not in ESPN_SPORT_MAPPING:
                    continue
                # Same reading, same reason as the pass above (#3473). The
                # decision was taken once, before either loop.
                if _failover.espn_reading(espn_data, sport_key) != _failover.FIXTURES:
                    continue
                espn_events = scheduled_board_for(
                    sport_key, espn_data[sport_key], full_slate_boards
                )
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


#: How far back a straggler is worth asking about. Deliberately the same 48h as
#: :data:`SUSPENDED_RESUME_WINDOW` — the two arms reach the same rows from
#: opposite directions (that one puts a suspended match back on court, this one
#: ends it) and a row either arm can reach should not depend on which asked.
AUTHORITY_STRAGGLER_LOOKBACK = timedelta(hours=48)

#: A match is a straggler only once it has had time to be one. Two hours past
#: its own kickoff is comfortably inside every sport's minimum duration, so this
#: never races a genuinely live game to the settle door — and the door itself
#: refuses anything ESPN has not marked ``completed`` regardless.
AUTHORITY_STRAGGLER_MIN_AGE = timedelta(hours=2)


# ── PAST THE WINDOW, AN ANCHORED ROW IS STRANDED FOR GOOD (#6280) ────────────
#
# The lookback above bounds the only pass that can settle a `live`/`suspended`
# row from ESPN. The other drain — `suspended` → `retired` — is keyed on the row
# being UNREACHABLE (`suspended_row_is_unreachable`: no provider id of any kind).
# So a row WITH an `espn_id` that misses the 48h settle window falls in a gap
# nothing selects: too anchored to be retired, too old to be settled. It does not
# age out, it does not recover, and no later pass revisits it.
#
# MEASURED on production 2026-09-15 02:2xZ: the whole stranded population is
# SEVEN rows, all 7-30 days old, in five (sport, board day) groups — 4 NCAAF and
# 3 MLS. There is no ancient tail. Read back against ESPN's own dated boards by
# id (standing notice 26), the seven split three ways, and the split is the
# design:
#
#   * FOUR are on their own board as `state=post completed=True` — Illinois
#     42-23 UAB, FSU 24-27 SMU, Portland 5-4 Minnesota, Vancouver 1-3 St. Louis.
#     These settle, and their SCORES are corrected in the same write: we were
#     serving FSU-SMU as 17-24 six days after it finished 24-27.
#   * TWO are marquee college-football fixtures THAT HAVE NOT BEEN PLAYED
#     (Michigan State @ Michigan, Auburn @ Georgia). ESPN files them under their
#     November/October board days, so the board for the September date our row
#     carries does not contain their id at all.
#   * ONE is a genuine postponement (15291065, FC Cincinnati v D.C. United),
#     moved to an October board. Same shape: absent from the day we ask about.
#
# THE LAST THREE ARE WHY THIS ARM NEEDS A CLOCK OF ITS OWN. They requalify on
# every single pass and can never resolve, so a widened window on a 60s beat
# would re-ask five boards forever — ~7,200 extra ESPN requests a day against a
# task whose p95 already overruns its own period (111.5s, see
# `MAX_DATED_BOARDS_PER_SPORT`) — for a three-row stock that will never move.
# A stalest-first queue with a per-pass budget and no stamp is worse still: the
# three that cannot advance sit at the head of it forever and starve the rows
# behind them. So the sort key is one THE WORK ADVANCES — when we last ASKED,
# not when the match kicked off — and it is written whether or not the ask
# settled anything.
#
#: How long before this arm asks about the same row again. Sized on what it is
#: protecting: the beat is 60s, so a re-ask cooldown of six hours turns the
#: permanent residue from ~7,200 requests a day into twenty. A row that has NEVER
#: been asked is not subject to it — it is picked up on the very next pass — so
#: this delays nothing a reader is waiting on.
AUTHORITY_DEEP_STRAGGLER_REASK = timedelta(hours=6)

#: Board fetches this arm may add to one pass. Twice the liveness path's ceiling
#: (`MAX_DATED_BOARDS_PER_SPORT`), and it can afford to be because it runs on the
#: cooldown above rather than every pass: the measured five-group pile drains in
#: two passes from cold, and steady state is zero. The budget is the blast radius
#: of the cooldown being wrong, not the ordinary cost.
MAX_DEEP_STRAGGLER_BOARDS_PER_PASS = 4

#: Ceiling on rows loaded into memory. The population is structurally small and
#: measured at seven, but a SELECT with no bound is a promise about the future
#: rather than a fact about now.
#:
#: ⚠️ THE "SEVEN" ABOVE WAS A PROPERTY OF THE STATUS FILTER, NOT OF THE WORLD
#: (#5501). It was measured over `live`/`suspended`, which is the set this arm
#: selected, so it could not count the rows stranded in the third state. On
#: 2026-09-23 those numbered 328 MLB rows with an `espn_id`, all past 48h. The
#: ceiling now binds on a cold start; it drains rather than starves, because a
#: settled row leaves the candidate states and frees its slot for an older one.
MAX_DEEP_STRAGGLER_CANDIDATES = 200

#: The states this arm reaches. `scheduled` is here and NOT in
#: :data:`~app.utils.event_completion.SETTLEABLE_STATUSES` — see
#: :func:`~app.utils.event_completion.authority_may_settle` for why the
#: permission is this arm's alone: 48h past kickoff, matched by `espn_id`, and
#: settled only on ESPN's own `post`/`completed` (#5501).
#: Derived, not spelled out, so a state added to either set reaches this arm
#: without a second edit here — the bug this arm exists to fix is a status
#: filter that fell out of step with the states rows actually sit in.
DEEP_STRAGGLER_STATUSES = sorted(
    SETTLEABLE_STATUSES | UNSTARTED_SETTLEABLE_STATUSES
)

#: Where the last-asked stamp lives. `win_probability_sources` carries
#: non-probability facts already — `statpal_end_time` and `ESPN_NOT_STARTED_KEY`
#: both ride it for exactly this reason — so this needs no migration and no
#: column. Written with a Core UPDATE, never by attribute assignment: an
#: in-place change to a JSONB value is invisible to the ORM's change tracking
#: and is silently dropped (gotcha #4).
DEEP_STRAGGLER_ASKED_KEY = "deep_straggler_asked_at"


# ── THE OTHER HALF OF THE STRANDED SEVEN: THE GAME THAT NEVER KICKED OFF ─────
#
# `_settle_deep_authority_stragglers` above reaches the stranded population by
# asking the BOARD DAY our row carries. That is the right question for a game
# that finished — but three of the measured seven are not late, they are
# MISDATED, and for them the board day our row carries is the defect itself.
# ESPN files them under their real November/October dates, so the September
# board we fetch does not contain their id and the settle pass is a no-op on
# exactly the rows a reader can see are wrong:
#
#   * 15175988 Michigan State @ Michigan — we say Sep 4, ESPN says **Nov 7**
#   * 14870016 Auburn @ Georgia          — we say Sep 5, ESPN says **Oct 17**
#   * 15291065 D.C. United @ FC Cincinnati — we say Sep 6, ESPN says **Oct 21**
#
# MEASURED against ESPN by id 2026-09-15 04:3xZ (standing notice 26 — the venue's
# own answer, not our mirror): all three are `STATUS_SCHEDULED`, `state=pre`,
# `completed=false`, both competitor scores absent, and the team names match our
# row exactly. They have not been played. Our row calls them `suspended` with a
# kickoff 9-10 days past, which is why the page draws a "Since Start" win-
# probability chart (the web chart cuts on `commence_time`, and `suspended`
# selects that tab) over a flat 87% line for a game that kicks off in November.
#
# SO THIS ARM INVERTS THE QUESTION THE WAY `reconcile_anchor_schedule` DOES —
# "what game IS this row's anchor?", one `summary?event=` call per row — because
# that is the only channel that can reach a fixture no board we fetch contains.
# It does not widen the settle arms: their door needs `state="post"` AND
# `completed=True`, this one needs `state="pre"` AND a start in the FUTURE, and
# no ESPN answer satisfies both. The two are mutually exclusive on the ANSWER,
# which is a stronger disjointness than a window boundary.
#
# WHY IT WRITES THE STATE AND NOT ONLY THE CLOCK. `reconcile_anchor_schedule`
# deliberately writes `commence_time` alone, and for its own population that is
# right. Here it would be a half-repair that invents a state with no precedent:
# production carries ZERO `suspended` rows with a future kickoff (measured
# 2026-09-15 04:4xZ), so moving only the clock would leave these three as the
# only ones, still labelled "No result reported", still charted as a game that
# started. The authority's answer is a single consistent fact — *this fixture
# has not been played and starts at T* — and the row is made to say that or
# nothing at all.
#
#: How long before this arm re-asks about the same row. Same six hours and the
#: same reasoning as :data:`AUTHORITY_DEEP_STRAGGLER_REASK`: on a 60s beat an
#: uncooled re-ask would spend ~1,440 ESPN calls a day per permanently-stuck row.
#: A row that has NEVER been asked is not subject to it and is picked up on the
#: next pass, so this delays no repair a reader is waiting on.
AUTHORITY_UNSTARTED_REASK = timedelta(hours=6)

#: ESPN calls this arm may add to one pass. Unlike the settle arms this is one
#: call PER ROW rather than per board day, so the budget is the wall-clock cost
#: directly: 4 x ~0.59s (re-measured in `reconcile_anchor_schedule`) against a
#: beat whose p95 already overruns its 60s period. The measured stock is three
#: and drains in one pass; the budget bounds the blast radius of the cooldown
#: being wrong, not the ordinary cost.
MAX_UNSTARTED_RECOVERY_ASKS_PER_PASS = 4

#: This arm's own queue stamp, beside :data:`DEEP_STRAGGLER_ASKED_KEY` and for
#: the same reason (gotcha #41 / the stalest-first livelock): the sort key must
#: be one the work ADVANCES, and "when we last asked" is, while "when it was
#: scheduled" is not. A SEPARATE key from the deep arm's because the two ask
#: different questions on different channels — sharing one stamp would let a
#: board fetch silence an anchor dereference that had never run.
UNSTARTED_RECOVERY_ASKED_KEY = "unstarted_recovery_asked_at"

#: The Redis key that turns the unreachable-suspended arm on, and the number of
#: rows it may retire per pass. ABSENT OR 0 MEANS THE ARM DOES NOTHING — not
#: "unbounded", not "default on" — and the arm does not even issue its SELECT.
#:
#: A BUDGET RATHER THAN A BOOLEAN, because this arm's population is a standing
#: backlog and a flow at once and there is no row property that separates them
#: (#5532: both are the same rows, distinguished only by whether they arrived
#: before or after this ships). An unbounded first pass would retire ~10,700 rows
#: in one 60-second beat with no backup taken — the thing D51 exists to stop. A
#: per-pass budget makes the drain rate an attended decision: the D51 backup is
#: taken, the key is set, the backlog drains at a chosen rate, and the key STAYS
#: set so the door remains shut against the ~600/day that keep arriving.
#:
#: The one-command undo is ``DEL`` on this key, which is what lets it be flipped
#: under D51(b) / standing notice 39 rather than needing a deploy.
UNREACHABLE_SUSPENDED_BUDGET_KEY = "events:unreachable_suspended_budget"

#: The D51 restore rail, and the arm's SECOND gate. Every row this arm retires is
#: written here in the same transaction, so the undo is exact.
#:
#: 🔴 IT HAD TO BE AN ID LIST AND NOT THE PREDICATE, and the number says why.
#: The obvious cheap restore is "un-void everything matching the retirement
#: predicate" — no table, nothing to maintain. MEASURED on production
#: 2026-09-12 (fingerprint ``295937d629781eeb``): of 4,320 rows already
#: ``voided`` for entirely unrelated reasons, **2,544 match this predicate
#: exactly**. That restore would have resurrected all 2,544 as ``suspended``,
#: which is a bigger data defect than the one being undone, and it would have
#: looked like a clean one-command rollback while doing it.
#:
#: ABSENT TABLE ⇒ THE ARM DOES NOT RUN. The table is created by the attended
#: enable step (``backend/scripts/unreachable_suspended_door.py --create-backup``,
#: runtime DDL behind a human invocation, standing notice 47(c)), so the arm
#: cannot write a terminal anybody is unable to take back.
UNREACHABLE_SUSPENDED_BACKUP_TABLE = "backup_unreachable_suspended_5532"

#: The backup table's shape, in ONE place — #7035.
#:
#: The enable script owns the `CREATE TABLE`, two arms insert into it, and the
#: real-Postgres gate has to stand one up to drive them. Three copies of four
#: column declarations is three chances for the gate to prove a retirement
#: against a table the script does not create. The script imports this and the
#: gate imports this, so the table under test is the table production gets.
#:
#: `IF NOT EXISTS` is part of the statement rather than the caller's problem: the
#: enable step is re-runnable by a person who does not remember whether they ran
#: it, which is the state that step is usually invoked in.
UNREACHABLE_SUSPENDED_BACKUP_DDL = (
    f"CREATE TABLE IF NOT EXISTS {UNREACHABLE_SUSPENDED_BACKUP_TABLE} ("
    "  event_id BIGINT PRIMARY KEY,"
    "  previous_status TEXT NOT NULL,"
    "  commence_time TIMESTAMPTZ,"
    "  retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    ")"
)

#: Ceiling on whatever the key says, so a fat-fingered value cannot turn one beat
#: into an unreviewable mass write. The key chooses a rate; this bounds the blast
#: radius of choosing it wrong.
UNREACHABLE_SUSPENDED_MAX_BUDGET = 500

#: THE IN-FLIGHT REGISTRY, and it exists because closing the door is not enough
#: (CERT-2757, repair ``5532-RESTORE-FENCES-IN-FLIGHT-RETIREMENT``).
#:
#: ``--restore`` deletes the budget key first, which stops every FUTURE pass. It
#: does nothing about a pass that already read the key: that budget is latched in
#: this process's memory, its transaction has not committed, and it will happily
#: land a ``voided`` write AFTER the restore's UPDATE has handed the row back.
#: Reproduced by the grader — restore reported 0 rows and the row finished
#: ``voided``, which is the rollback silently reversing the operator in a second,
#: subtler way than the one CERT-2753 caught.
#:
#: So the budget read and the retirement write are bracketed: a pass that latches
#: a positive budget writes a field here before it reads, and clears it after its
#: transaction has committed. Restore closes the door and then WAITS for this to
#: drain. Registering BEFORE the read is the whole ordering — register after, and
#: a pass that read a positive budget is invisible for the instant restore looks.
UNREACHABLE_SUSPENDED_INFLIGHT_KEY = "events:unreachable_suspended_inflight"

#: How long a marker is honoured when nobody clears it, and it is SIZED ON THE
#: BOUND THAT IS ENFORCED, not on the one that is handy. The handy number is the
#: 60s beat; the enforced number is Celery's global ``task_time_limit`` (300s),
#: which is what actually stops this task — it declares no limit of its own, and
#: it IS hard-killed in production. A pass killed mid-retirement can never clear
#: its own marker, so without an expiry one hard kill would block every restore
#: forever; with one sized under the kill, a live pass would lose its marker and
#: the fence would open under it. Hence: the hard kill plus a margin.
#:
#: ``test_the_inflight_ttl_outlasts_the_hard_kill_that_is_enforced_5532`` asserts
#: the gap against the configured limit, so the two cannot drift into a hole.
UNREACHABLE_SUSPENDED_INFLIGHT_TTL = 360

#: Per-pass ceiling on the #7260 revival arm.
#:
#: SIZED ON THE CADENCE, NOT ON THE BACKLOG. `revive_retired_future_starts` fires
#: every 10 minutes, so 25 drains the 135 rows measured on 2026-09-20 inside an
#: hour while keeping each pass's twin screen — one bounded read per candidate —
#: cheap. It is a blast-radius bound rather than a throttle: a REVIVED row leaves
#: the population for good (`scheduled` is not `voided`, and the retirement arm
#: selects only `suspended` rows whose start is already past, so neither can
#: re-select it and the two cannot oscillate).
#:
#: 🔴 A REFUSED ROW DOES NOT LEAVE, AND THE SENTENCE ABOVE ONCE SAID "a recall
#: that returns nothing" AS IF IT DID. That was the whole of #7260's second
#: defect. A row refused for having a surviving counterpart stays `voided`, so
#: the recall re-selects it on every single pass, in the same kickoff order, for
#: ever. Once the refused set is larger than this cap it occupies the whole of
#: every pass and no row behind it is ever screened again — measured on
#: production 2026-09-21 07:1xZ: 84 ledger rows with a future start, 69 of them
#: refusals, 38 of those sorting ahead of the first revivable row against a cap
#: of 25, and the population byte-stable across seven consecutive passes while
#: four WNBA playoff games sat invisible behind it. Gotcha #34 in a second
#: costume: one counter shared between work and not-work starves the tail.
#: :data:`UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS` is the separation.
#:
#: Deliberately NOT behind the Redis door the retirement arm uses. That door
#: exists because that arm writes a TERMINAL; this one writes a row back onto the
#: schedule, per-row screened and trivially undone, which is the same argument
#: `_is_bogus_future_settled`'s two siblings above already run on with no door at
#: all. A door here would also defeat the ship: an arm that needs an attended
#: enable leaves the games invisible until somebody remembers to turn it on.
UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS = 25

#: How many candidates one pass may SCREEN, as distinct from how many it WRITES.
#:
#: THE WRITE CAP ABOVE IS A BLAST RADIUS; THIS IS A COST BOUND. They were one
#: number, and because a refusal costs a screen but writes nothing, the single
#: number silently became "how far down the queue this arm can ever see". Two
#: names, because they answer two questions and only one of them is about risk.
#:
#: SIZED ON THE POPULATION, NOT ON THE CADENCE — the opposite of its sibling, and
#: deliberately. What it has to clear is the REFUSED prefix, so it is sized above
#: the largest future-start ledger population ever measured: 163 rows (production
#: 2026-09-20 14:29Z), against 84 on 2026-09-21. 400 carries that peak with room
#: for the refusal set to keep growing as the catch-all twins accrue, and the
#: screen is one narrowed read per candidate — the whole 84-row population
#: screens in 97ms measured through `db-query`, so the ceiling costs a fraction
#: of a ten-minute beat even when it is reached.
#:
#: 🔴 EXHAUSTING IT IS REPORTED, NEVER SILENT. A budget that can be exceeded
#: re-admits the exact defect it was added for, so a pass that screens to the
#: ceiling and still writes nothing sets `screen_budget_exhausted` and logs a
#: warning naming this constant. The starvation was invisible for a day because
#: nothing in the arm could tell "there is no work" from "I never got to it";
#: that distinction is now in the stats dict.
UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS = 400

#: Where the #7594 take-back arm writes the status it swapped FROM.
#:
#: THE SAME TABLE THE ONE-SHOT REPAIR BANKS INTO, ON PURPOSE. This arm is that
#: script's forward half — the same rule, asked continuously instead of once —
#: so `scripts/restore_7594_revoid_published_reversed_twins.py --apply` is the
#: undo for both, and there is one bank and one undo line for one repair rather
#: than two that can disagree. The script imports this name rather than spelling
#: its own copy, so the two cannot drift.
#:
#: 🔴 IT IS A ROLLBACK OF A PASS, NOT A VETO OF THE RULE. Restoring puts a row
#: back in the status it was taken from; if the rule still holds on it, the next
#: pass takes it back again — which is correct for an arm that is a rule rather
#: than an event. Disagreeing with the RULE is a code change, not a restore.
REVIVED_TWIN_TAKEBACK_BANK_TABLE = "bak_7594_revoid_published_reversed_twins"

#: Per-pass ceiling on the #7594 take-back arm.
#:
#: A BLAST-RADIUS BOUND, AND IT IS THE ONLY ONE, WHICH IS A DECISION. This arm
#: writes a TERMINAL, and the sibling arm that does the same sits behind an
#: attended Redis door — so the omission is stated rather than inherited. That
#: door exists because `suspended_row_is_unreachable` retires a large population
#: off a PREDICATE: 13,588 rows so far, and 2,544 unrelated rows match the rule.
#: This arm's population is membership of that arm's own ledger minus the rows
#: it already retired — 61 rows on production 2026-09-21 — every one of which is
#: individually screened against a counterpart a reader can still reach and then
#: put through four evidence refusals. The blast radius is named and small, and
#: the cost of an attended enable is the one the revival arm's own constant
#: argues against above: the wrong page stays wrong until somebody remembers.
REVIVED_TWIN_TAKEBACK_MAX_PER_PASS = 25


def unreachable_suspended_floor():
    """How long past kick-off before the last door is agreed to be shut? (#6347)

    A FUNCTION, and not an expression inlined in the arm, because a test cannot
    call an expression. Written as a local, the derivation could only be checked
    by scanning the arm's source for the word ``max`` — and a mutation that
    swapped it for ``min`` survived that scan while the test's own copy of the
    formula went on reporting the right answer. A floor the guard reimplements
    is a floor the guard cannot guard.

    THE FLOOR IS THE LAST DOOR TO SHUT, PLUS THE MARGIN. Two doors are enforced
    on the populations this arm retires, and they are different windows:

      * ``SUSPENDED_RESUME_WINDOW`` — the ``suspended → live`` resume arm, which
        is what the id-less #5532 population waits out;
      * :data:`~app.tasks.odds_polling.ODDS_SCORES_LOOKBACK` — the scores fetch,
        which IS keyed on ``external_id`` and so is the door the #6347
        ``odds_api`` population waits out.

    ``max`` rather than either name, so admitting a further class later cannot
    silently leave its own door open.
    """
    from app.tasks.odds_polling import ODDS_SCORES_LOOKBACK
    from app.utils.event_completion import UNREACHABLE_SUSPENDED_MARGIN

    return (
        max(SUSPENDED_RESUME_WINDOW, ODDS_SCORES_LOOKBACK)
        + UNREACHABLE_SUSPENDED_MARGIN
    )


async def _row_has_market_anchor(session, event_id) -> bool:
    """Does any prediction market hang off this event? (#6347)

    The verdict's ``market_anchored`` argument. It is a separate read rather
    than a flag carried off the screen's JOIN on purpose: the screen's job is to
    be a cheap filter, and ``suspended_row_is_unreachable`` is written so that
    every refusal it makes can be given a counter-example by a test. A boolean
    smuggled out of a WHERE clause cannot be.

    Any source counts, not just ``kalshi``/``polymarket``. The two named doors
    are the ones measured open today; a market of any provenance is evidence
    something upstream still holds this row, and this arm writes a terminal.
    """
    from app.models import FuturesMarket

    return bool(
        (
            await session.execute(
                select(FuturesMarket.id)
                .where(FuturesMarket.event_id == event_id)
                .limit(1)
            )
        ).scalar()
    )


#: Per-pass ceiling on the #7035 venue-void retirement arm.
#:
#: SIZED OFF THE MEASURED POPULATION, not off a cadence. The arm's own screen —
#: suspended, past the floor, no score, no `completed_at`, every market a Kalshi
#: resolved one, nothing graded — returns **30 rows on production** (2026-09-23),
#: of which the venue voids roughly three in ten on a 14-ticker sample. So the
#: standing backlog is a couple of dozen and the inflow is a postponement rate,
#: which is rare against the rate games finish. 25 drains it in two passes and
#: keeps the per-pass cost of the Python-side void read bounded at 25 events'
#: worth of markets however the screen's population moves later.
VENUE_VOIDED_SUSPENDED_MAX_PER_PASS = 25


async def _row_markets_all_venue_voided(session, event_id) -> bool:
    """Did the venue settle EVERY market on this event without grading it?

    The ``every_market_venue_voided`` argument of
    :func:`~app.utils.event_completion.venue_voided_row_is_retirable` — #7035.

    READ IN PYTHON, DELIBERATELY. ``venue_voided`` is a key inside a ``jsonb``
    column and the operator that reaches it, ``->>``, is Postgres-only, while
    this task's band guards execute against ``sqlite://``. The caller's screen is
    plain columns and cuts the table to 30 rows, so loading each survivor's
    markets and asking in Python costs nothing and keeps the arm dialect-free.

    🔴 EVERY, AND THE EMPTY CASE IS FALSE. ``all()`` over an empty list is True,
    which would make a legless event "fully voided" and retire a row the venue
    was never asked about — the vacuous-satisfaction trap the capture's own
    selection carries an ``EXISTS`` to avoid one layer up. The explicit emptiness
    test here is the second guard against it, and it is not redundant with the
    caller's ``EXISTS``: this function is the one that states the rule, and a
    rule that only exists as a WHERE clause is a rule no test can put a
    counter-example to.

    ``is True`` rather than a truth test. The capture writes a JSON boolean, so a
    correctly stamped row round-trips as Python ``True``; a string ``"true"``, a
    ``1``, or the timestamp that the NEGATIVE stamp
    (``venue_void_checked_at``) writes are all truthy and none of them is this
    fact. The identity test is what keeps "the venue declined to grade it" from
    being satisfied by "we asked and it graded it".
    """
    from app.models import FuturesMarket
    from app.utils.kalshi_resolution_window import VENUE_VOIDED_METADATA_KEY

    rows = (
        await session.execute(
            select(FuturesMarket.market_metadata).where(
                FuturesMarket.event_id == event_id
            )
        )
    ).all()
    if not rows:
        return False
    return all(
        (metadata or {}).get(VENUE_VOIDED_METADATA_KEY) is True
        for (metadata,) in rows
    )


async def _row_has_graded_outcome(session, event_id) -> bool:
    """Has anything already written a winner against this event? (#7035)

    The ``has_graded_outcome`` argument of
    :func:`~app.utils.event_completion.venue_voided_row_is_retirable`, and it is
    the CONTRADICTION test rather than a duplicate of the screen's. A graded
    outcome says a result was reported; the void stamp says none ever was. Both
    cannot be true, and when our own data disagrees with the venue's word this
    arm declines to write a terminal rather than choosing a side.

    Fail-closed direction: the caller refuses on anything that is not literally
    ``False``, so a read that cannot answer stops a retirement rather than
    permitting one.
    """
    from app.models import FuturesMarket, FuturesOutcome

    return bool(
        (
            await session.execute(
                select(FuturesOutcome.id)
                .join(
                    FuturesMarket,
                    FuturesMarket.id == FuturesOutcome.market_id,
                )
                .where(
                    FuturesMarket.event_id == event_id,
                    FuturesOutcome.is_winner.is_(True),
                )
                .limit(1)
            )
        ).scalar()
    )


async def _retire_venue_voided_suspended_rows(session, now, floor) -> dict:
    """Retire suspended rows the VENUE has already answered with "no result".

    The consumer of the #7035 void capture, and the reason that capture is a
    ship rather than a column. `kalshi_resolution_sweep` reads Kalshi's own
    `result='scalar'` off a settled event and stamps
    `market_metadata.venue_voided`; nothing acted on it, so the postponed
    fixture went on being served with "No result reported" under it. This is
    what acts on it.

    🔴 IT LIVES HERE AND IS CALLED FROM `kalshi_resolution_sweep`, NOT FROM
    `_transition_event_statuses_impl` — AND THAT IS MEASURED, NOT TIDINESS. It
    was composed into that task first, which is the obvious home: this is the
    second `suspended →` retirement arm and the first one is there. It reddened
    **79 guards across seven other ships** (#2772, #2591, #5324, #4075, q076,
    the staleness net and `test_event_completion`) that this ship does not
    touch. The cause is not a missing method on a double: those doubles answer
    `session.execute` POSITIONALLY — `rows = self._selects.pop(0)` — so ANY new
    statement anywhere in that thousand-line function shifts every later
    statement onto the wrong canned result and exhausts the list. There is no
    version of this arm that can be added to that task without rewriting seven
    other ships' fixtures.

    `run_resolved_voids` is the right caller on its own merits, which is why
    this is not a workaround. That task IS the capture that writes the fact;
    running the consumer at the end of it makes the chain a read-after-write in
    one beat instead of two arms agreeing about a column. Its own docstring
    already records this exact lesson being learned once — composing this
    capture into `run_recent_finals` "broke six guards belonging to #5024,
    #4655 and #5596 … Loosening three other ships' guards to fit this one in
    would have been the wrong repair for the right complaint." Same complaint,
    same repair, one layer out.

    A MODULE-LEVEL FUNCTION, NOT A BLOCK IN THE TASK, AND THAT IS THE POINT.
    `_transition_event_statuses_impl` is a thousand lines that need a whole
    session's worth of fixtures to enter, so an arm living inside it can only be
    guarded by reading its source — and a `getsource` scan cannot tell a screen
    that selects the specimen from one that selects nothing. Here a gate seeds a
    real Postgres, calls this, and reads the row's status back. That is the
    difference between guarding that the code exists and guarding that it works.

    THE SECOND WARRANT FOR AN EXISTING WRITE. `suspended_row_is_unreachable`
    retires a row nothing can reach; this retires a row whose answer has already
    arrived. Same terminal, same backup-first ordering, same restore script — a
    different reason to be sure, argued in `venue_voided_row_is_retirable`.

    WHY NOT WIDEN THE SIBLING. The fixture #7035 was filed for is held by it
    twice over — market-anchored AND in an ESPN-covered sport — so opening one
    of those doors would not move it and opening both would widen a rule that
    retired 13,595 rows in five days, in order to move four. The predicate's
    docstring carries the measurement.

    Returns the two counters the caller merges into its stats. `screened` beside
    `retired` on purpose: a pass where the screen returned rows and the verdict
    refused every one of them is the arm working, and it must not read the same
    as a pass that selected nothing (`app/utils/task_verdict.py`'s line — "it
    returned" is not "it worked").
    """
    from sqlalchemy import text as _sql_text

    from app.models import FuturesMarket, FuturesOutcome
    from app.utils.event_completion import (
        EVENT_SUSPENDED,
        UNREACHABLE_SUSPENDED_TERMINAL,
        venue_voided_row_is_retirable,
    )
    from app.utils.kalshi_resolution_window import (
        KALSHI_MARKET_SOURCE,
        KALSHI_RESOLVED_STATUS,
    )

    stats = {
        "venue_voided_suspended_screened": 0,
        "venue_voided_suspended_retired": 0,
    }

    # THE SCREEN IS PLAIN COLUMNS, AND THE VOID QUESTION IS NOT IN IT.
    # `venue_voided` lives inside a `jsonb` column and the operator that reaches
    # it, `->>`, is Postgres-only, while this task's band guards execute against
    # `sqlite://`. So the screen asks everything it can ask portably — enough to
    # cut the table to 30 rows on production — and the void question is answered
    # in Python off the loaded markets, once per surviving row.
    #
    # `NOT EXISTS (a market that is not kalshi-and-resolved)` is the selective
    # one, and it is deliberately the NEGATIVE form: "every market is
    # kalshi+resolved". The positive spelling (`EXISTS (a kalshi resolved
    # market)`) would admit an event carrying one voided leg and one OPEN market
    # of another source, whose open market is a door still standing. `EXISTS (any
    # market)` beside it is what stops a legless row satisfying the NOT EXISTS
    # vacuously — the same refusal, for the same reason, that the capture's own
    # selection makes one layer up.
    any_market = (
        select(FuturesMarket.id)
        .where(FuturesMarket.event_id == Event.id)
        .exists()
    )
    foreign_market = (
        select(FuturesMarket.id)
        .where(
            FuturesMarket.event_id == Event.id,
            ~and_(
                FuturesMarket.source == KALSHI_MARKET_SOURCE,
                FuturesMarket.status == KALSHI_RESOLVED_STATUS,
            ),
        )
        .exists()
    )
    graded_outcome = (
        select(FuturesOutcome.id)
        .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
        .where(
            FuturesMarket.event_id == Event.id,
            FuturesOutcome.is_winner.is_(True),
        )
        .exists()
    )
    result = await session.execute(
        select(Event)
        .where(
            Event.status == EVENT_SUSPENDED,
            Event.commence_time.is_not(None),
            Event.commence_time < now - floor,
            Event.home_score.is_(None),
            Event.away_score.is_(None),
            Event.completed_at.is_(None),
            any_market,
            ~foreign_market,
            ~graded_outcome,
        )
        # Oldest first, for the reason the sibling gives: the fixture a reader
        # has been staring at longest is the one to fix first.
        .order_by(Event.commence_time.asc())
        .limit(VENUE_VOIDED_SUSPENDED_MAX_PER_PASS)
    )
    candidates = result.scalars().all()
    if not candidates:
        return stats

    # THE RESTORE RAIL IS A GATE, NOT A LOG, AND IT IS THIS ARM'S OWN. The
    # sibling arm computes its `backup_present` only while its Redis budget is
    # non-zero, so reading that variable would tie this arm's safety to whether
    # that arm happens to be switched on — and would read a stale True if its
    # budget were later zeroed. One `to_regclass`, asked for this arm, answering
    # only for this arm. Asked BEFORE the loop, so a missing table refuses the
    # whole pass rather than the first row of it.
    #
    # THE SAME TABLE ON PURPOSE. Its shape (event_id, previous_status,
    # commence_time, retired_at) is exactly what a restore needs,
    # `scripts/unreachable_suspended_door.py --restore` already gives these rows
    # back, and a second table would be DDL nobody has run — the ship would not
    # pay until someone remembered. The consequence is stated rather than
    # discovered: a row retired here is also a member of #7260's revival ledger,
    # so a void whose clock later moves into the future with no surviving
    # counterpart can be revived. That IS the rescheduled fixture and reviving it
    # is right; it cannot flap back here, because this arm's floor test
    # (`commence_time < now - floor`) is false for a future clock.
    backup_present = (await session.execute(
        _sql_text("SELECT to_regclass(:t) IS NOT NULL"),
        {"t": f"public.{UNREACHABLE_SUSPENDED_BACKUP_TABLE}"},
    )).scalar()
    if not backup_present:
        logger.warning(
            "#7035 venue-voided arm skipped: backup table %s does not exist, "
            "so a retirement could not be undone. Run "
            "scripts/unreachable_suspended_door.py --create-backup.",
            UNREACHABLE_SUSPENDED_BACKUP_TABLE,
        )
        return stats

    for event in candidates:
        stats["venue_voided_suspended_screened"] += 1
        if not venue_voided_row_is_retirable(
            event.status,
            event.commence_time,
            event.home_score,
            event.away_score,
            event.completed_at,
            now,
            floor,
            # Re-asked rather than trusted off the screen, the way the sibling
            # re-asks its market test — and #6927 is why that sentence is worth
            # anything only when the two askings do not hang from the same hook.
            # These do not: the screen asked `source`/`status` columns and said
            # nothing whatever about `venue_voided`, which is the whole verdict.
            every_market_venue_voided=(
                await _row_markets_all_venue_voided(session, event.id)
            ),
            has_graded_outcome=(
                await _row_has_graded_outcome(session, event.id)
            ),
        ):
            continue
        # BACKUP FIRST, IN THE SAME TRANSACTION — the sibling's ordering, and
        # D51's, stated as code rather than as a runbook step: if this insert
        # raises, the status write never happens.
        await session.execute(
            _sql_text(
                f"INSERT INTO {UNREACHABLE_SUSPENDED_BACKUP_TABLE} "
                "(event_id, previous_status, commence_time, retired_at) "
                "VALUES (:id, :prev, :commence, NOW()) "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "id": event.id,
                "prev": event.status,
                "commence": event.commence_time,
            },
        )
        event.status = UNREACHABLE_SUSPENDED_TERMINAL
        stats["venue_voided_suspended_retired"] += 1
        logger.info(
            "#7035 retired event %s (%s vs %s) suspended→%s: every market on it "
            "is a Kalshi market the venue settled without naming an outcome, no "
            "graded outcome of ours contradicts it, no score, no completed_at, "
            "and %.0fh past its own start. The venue reported no result because "
            "there was none.",
            event.id, event.home_team_name, event.away_team_name,
            UNREACHABLE_SUSPENDED_TERMINAL,
            (now - event.commence_time).total_seconds() / 3600,
        )
    return stats



#: How far apart two rows for one fixture may sit and still be the same fixture.
#:
#: The window is wide because the whole population this screens is rows whose
#: clock was WRONG (#4590: `commence_time` minted as the ingest clock). A tight
#: window would ask the twin test to trust the very field whose unreliability
#: created the defect — it would read "no survivor" for a genuine duplicate whose
#: own clock is off by a day and revive straight into the harm the screen exists
#: to prevent. 30h spans a date-line slip plus a postponement to the next
#: evening; erring wide costs a refusal (a row stays invisible, and #2693 gets
#: it), erring narrow costs a twin.
SURVIVING_COUNTERPART_WINDOW = timedelta(hours=30)


async def _row_has_surviving_counterpart(session, event) -> bool:
    """Does a row a reader can still reach hold this same fixture? (#7260)

    ``bool`` half of :func:`_surviving_counterpart_rows`, which is where the rule
    lives. Kept as its own name because that is the question this arm's verdict
    asks, and because the fail-closed answer is TRUE — "we could not show this
    row is an orphan" has to refuse a revival, and an empty list would permit
    one (#7594/CERT-3199).
    """
    return _counterpart_screen_refuses(
        await _surviving_counterpart_rows(session, event)
    )


def _counterpart_screen_refuses(rows) -> bool:
    """Read :func:`_surviving_counterpart_rows`'s three answers as one boolean.

    ``None`` (the screen could not be run) and a non-empty list both mean "do not
    treat this row as the only card for its fixture". Written once, here, so the
    two callers cannot read the sentinel in opposite directions — which is the
    single way this refactor could have put a twin back on a reader's screen.
    """
    return rows is None or bool(rows)


async def _surviving_counterpart_rows(session, event):
    """Which reachable rows hold this same fixture? ``(id, status)`` each. (#7260)

    Returns ``None`` when the screen cannot be run at all — a row with no usable
    name, or a sport with no family — because "we cannot tell" must fail closed
    in both of this function's uses, and a caller that flattened it to an empty
    list would read it as "this row is an orphan" and publish a twin.

    🔴 IT RETURNS THE ROWS, NOT A VERDICT, AND THAT IS #7594's REPAIR
    (CERT-3199's ``7594-FIRST-TAKEBACK-CANNOT-RETIRE-THE-LAST-CARD``). A boolean
    is a fact about the instant it was read, and the take-back repair then wrote
    on the strength of it one statement later: the canonical could retire in
    between, the compare-and-swap on the subject's own status still matched, and
    both rows committed retired — zero cards for a game, reported as success. A
    caller cannot close that window with a boolean, because it has nothing to
    bind its write to. With the ids and the statuses in hand it can make the
    take-back conditional on the very rows this screen accepted still being in
    the very statuses it accepted them in, in ONE statement. The rule stays
    here, in Python, where a test can put a counter-example to it; the caller's
    SQL re-checks only the liveness of the ids this function named.

    The revival verdict's ``has_surviving_counterpart`` argument, and the line
    between this arm and #2693's twin authority (D39). Kept a separate read for
    the reason :func:`_row_has_market_anchor` gives: a boolean smuggled out of a
    WHERE clause is a rule no test can put a counter-example to.

    "Reachable" is spelled as NOT retired rather than as an allowlist of live
    statuses. A `completed` sibling is every bit as much a second row for one
    game as a `scheduled` one — the harm in gotcha #32 is two rows, not two
    upcoming rows — and an allowlist would silently stop screening the day a
    status is added to the vocabulary, which is exactly how #4114 happened.

    Name containment runs BOTH directions because the two rows come from
    different mints and one is routinely the other's prefix ("Maple Leafs" vs
    "Toronto Maple Leafs"). Matched on ``COALESCE(normalized, name)`` so a row
    that has been through normalisation is compared on the same footing as one
    that has not.

    🔴 AND THE PAIRING IS ORIENTATION-BLIND, WHICH THE FIRST SHIP LEARNED THE
    HARD WAY. Asking home↔home AND away↔away only is the same mistake in a
    second dimension as the ``sport_id`` screen CERT-3173 blocked: the two rows
    come from different mints, so they disagree about which side is HOME every
    bit as routinely as they disagree about the league key. Measured on
    production 2026-09-20 ~20:18Z, after the arm's first passes went out:

        already revived, duplicate now on the site      5   4 NHL, 1 WNBA
        still voided, would duplicate on a later pass  13   all NHL
        refused by the same-orientation screen alone    0   of those 18

    Re-read at 20:29Z, two passes later: 9 live and 9 pending. The total holds
    at 18 while the beat converts pending into live every ten minutes — the
    harm curve, rather than an estimate of it.

    `15302884` "Hurricanes v Panthers" was published beside `15312312`
    "Florida Panthers v Carolina Hurricanes" — one game, same minute, adjacent
    rows in `/api/events/search?q=hurricanes`. The containment test was never
    the problem ("hurricanes" IS inside "carolina hurricanes"); the sides were
    simply swapped, so the survivor could not enter the screen at all.

    A REVERSED FIXTURE INSIDE ±30h IS NOT A SECOND GAME. Two clubs do not meet
    twice at each other's rink inside thirty hours, and the measurement agrees:
    17 of the 18 crossed pairs share their kickoff to the MINUTE. So the
    widening costs no legitimate revival, and it errs in the direction this
    function's own contract already argues for — wide refuses a row that stays
    invisible (#2693 gets it), narrow puts a twin on a reader's screen.

    SCREEN IN SQL, VERDICT IN PYTHON — the same split the retirement arm makes,
    and here it is also what makes the read affordable. Measured 2026-09-20: the
    ±30h window alone returns up to **940** rows for a `soccer_other` candidate
    (881 on average), and this runs per candidate. Pushing the containment into
    the WHERE clause cuts that to the handful that could possibly match, while
    the Python pass below re-asks the same question so the rule still has a place
    a test can put a counter-example to.

    THE STATUS TEST IS DELIBERATELY NOT IN THE SCREEN. :data:`RETIRED_STATUSES`
    is documented as a membership set that is never spent on an ``IN`` — "the
    surfaces that emit SQL are allowlists and must stay allowlists" — so it is
    asked in Python, where it is a frozenset lookup, and the screen stays a pure
    narrowing.

    🔴 THE SPORT TEST IS A FAMILY, NOT A ``sport_id``, AND THAT IS THE WHOLE
    SAFETY OF THIS ARM (CERT-3173). The first presentation asked
    ``Event.sport_id == event.sport_id`` and was blocked for it. Every row this
    ship revives is in a CATCH-ALL sport (measured: 114 ``soccer_other``, 42
    ``icehockey_other``, 7 ``basketball_other``), and a catch-all's twin
    routinely sits under the canonical league key instead —
    ``event_twin_fold._merge_catchall_leagues`` exists for exactly that shape and
    names the pairs it folds (``soccer_other`` × ``soccer_netherlands_eredivisie``,
    × ``soccer_mexico_ligamx``, …). Those survivors have a different ``sport_id``,
    so they could not enter the screen at all: the arm would have read "orphan"
    for a fixture a reader can already see and published its hidden sibling as a
    second scheduled game — the precise harm this function exists to refuse.

    THE FAMILY IS STILL A GUARD AND DROPPING IT WOULD BE WORSE THAN ``sport_id``.
    The same fold measured 65 CROSS-SPORT pairs sharing squashed club names and a
    minute — 59 ``baseball_other`` × ``esports``, 5 ``americanfootball_other`` ×
    ``esports``, 1 ``basketball_other`` × ``baseball_npb`` — which are a
    classification defect somebody else owns and are emphatically not one fixture
    each. A screen with no sport test would read every one of them as a survivor
    and refuse 65 revivals it should make. :func:`sport_family_key` keeps the
    cross-family refusal and only widens WITHIN a sport.

    Widening the screen can only ever ADD candidates, and a candidate can only
    ever make this return ``True`` — a refusal. That is the direction
    :data:`SURVIVING_COUNTERPART_WINDOW` already argues for at length: erring
    wide costs a row that stays invisible and #2693 gets it, erring narrow costs
    a twin on a reader's screen.
    """
    from app.utils.event_completion import is_retired_event_status
    from app.utils.sport_keys import sport_family_key

    home = (event.home_team_normalized or event.home_team_name or "").lower()
    away = (event.away_team_normalized or event.away_team_name or "").lower()
    if not home or not away:
        # FAIL CLOSED. A row with no usable name cannot be shown to be an
        # orphan, and the cost of guessing wrong is a twin. `None`, not `[]`:
        # see `_counterpart_screen_refuses`.
        return None

    # One extra PK read per candidate rather than a join in the caller's recall,
    # and it is affordable because the pass is capped at
    # `UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS` rows every ten minutes. The key
    # cannot be read off `event.sport` — the caller holds a bare `session.get`
    # row, and touching a lazy relationship on an async session raises.
    family = sport_family_key(
        (await session.execute(
            select(Sport.key).where(Sport.id == event.sport_id)
        )).scalar()
    )
    if family is None:
        # FAIL CLOSED again, and for the same reason as the nameless row above:
        # a row whose sport we cannot name cannot be shown to be an orphan.
        return None

    home_col = func.lower(
        func.coalesce(Event.home_team_normalized, Event.home_team_name)
    )
    away_col = func.lower(
        func.coalesce(Event.away_team_normalized, Event.away_team_name)
    )

    def _overlaps(col, name: str):
        """Either string contains the other — the mint-agnostic name test."""
        return or_(
            func.strpos(col, name) > 0,
            func.strpos(literal(name), col) > 0,
        )

    others = (await session.execute(
        select(
            Event.id,
            Event.status,
            Event.home_team_normalized,
            Event.home_team_name,
            Event.away_team_normalized,
            Event.away_team_name,
        ).join(
            Sport, Sport.id == Event.sport_id
        ).where(
            Event.id != event.id,
            Sport.key.startswith(family, autoescape=True),
            Event.commence_time
            >= event.commence_time - SURVIVING_COUNTERPART_WINDOW,
            Event.commence_time
            <= event.commence_time + SURVIVING_COUNTERPART_WINDOW,
            # Both pairings, because the two rows disagree about which side is
            # home as routinely as they disagree about the league key.
            or_(
                and_(
                    _overlaps(home_col, home),
                    _overlaps(away_col, away),
                ),
                and_(
                    _overlaps(away_col, home),
                    _overlaps(home_col, away),
                ),
            ),
        )
    )).all()

    def _same(a: str, b: str) -> bool:
        return a in b or b in a

    # EVERY match, not the first one. A caller binding a write to "the canonical
    # is still there" has to be told about all of them, or a fixture with two
    # reachable siblings would have its take-back refused the moment the one
    # this loop happened to see first moved (#7594).
    survivors: list[tuple[int, str]] = []
    for row in others:
        if is_retired_event_status(row.status):
            continue
        other_home = (row.home_team_normalized or row.home_team_name or "").lower()
        other_away = (row.away_team_normalized or row.away_team_name or "").lower()
        if not other_home or not other_away:
            continue
        if (_same(home, other_home) and _same(away, other_away)) or (
            _same(home, other_away) and _same(away, other_home)
        ):
            survivors.append((row.id, row.status))
    return survivors


def _unreachable_suspended_budget() -> int:
    """How many rows may this pass retire? 0 unless an attended step said so.

    Every failure — no Redis, an unparseable value, a negative one — returns 0.
    An arm that writes a terminal status must fail CLOSED: "the config read
    broke" and "the operator asked for this" cannot be allowed to look alike.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(UNREACHABLE_SUSPENDED_BUDGET_KEY)
        if raw is None:
            return 0
        budget = int(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception as exc:
        logger.info(
            "Unreachable-suspended budget unreadable, arm stays off: %s", exc
        )
        return 0
    if budget <= 0:
        return 0
    return min(budget, UNREACHABLE_SUSPENDED_MAX_BUDGET)


def _latch_unreachable_suspended_budget() -> tuple[int, Optional[str]]:
    """Read the budget AND announce this pass, in that bracket, or refuse.

    Returns ``(budget, token)``. A positive budget always comes with a token the
    caller must hand back to :func:`_release_unreachable_suspended_inflight`
    after its transaction has committed; ``(0, None)`` means this pass retires
    nothing.

    🔴 THE REGISTRATION PRECEDES THE READ, and reversing those two lines
    reintroduces exactly the defect this exists to close (CERT-2757). Register
    afterwards and there is an instant where a pass holds a positive budget and
    nothing in Redis says so — restore looks, sees a clean registry, and updates
    rows out from under a writer that is about to void them again.

    A pass that cannot register does not run. That is the same fail-closed rule
    the budget read already follows, for the same reason: "the fence is broken"
    and "the operator asked for this" must not look alike. The cost of being
    wrong here is a pass that retires nothing, which is the off state.
    """
    import time
    import uuid

    token = uuid.uuid4().hex
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        client.hset(
            UNREACHABLE_SUSPENDED_INFLIGHT_KEY,
            token,
            str(time.time() + UNREACHABLE_SUSPENDED_INFLIGHT_TTL),
        )
        # Refreshed on every registration so the registry cannot outlive the
        # passes in it. Each refresh is at least as long as the field just
        # written, so the hash never expires under a live marker.
        client.expire(
            UNREACHABLE_SUSPENDED_INFLIGHT_KEY, UNREACHABLE_SUSPENDED_INFLIGHT_TTL
        )
    except Exception as exc:
        logger.info(
            "Unreachable-suspended pass could not register as in flight, "
            "arm stays off: %s",
            exc,
        )
        return 0, None

    budget = _unreachable_suspended_budget()
    if budget <= 0:
        # Nothing to fence. Hand the marker back immediately rather than leaving
        # a restore to wait out a pass that was never going to write.
        _release_unreachable_suspended_inflight(token)
        return 0, None
    return budget, token


def _release_unreachable_suspended_inflight(token: Optional[str]) -> None:
    """Drop this pass's marker. Best effort — the TTL is the guarantee.

    Called after the transaction has COMMITTED, never before: the marker exists
    to cover the window in which a retirement is written but not yet durable,
    and releasing inside that window is the same as never holding it.

    A release that fails leaves restore waiting out the TTL, which is slower and
    still correct. There is no failure mode here worth raising into a task that
    has already done its work.
    """
    if not token:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().hdel(UNREACHABLE_SUSPENDED_INFLIGHT_KEY, token)
    except Exception as exc:
        logger.info(
            "Unreachable-suspended in-flight marker %s not cleared; the %ds "
            "expiry will retire it: %s",
            token, UNREACHABLE_SUSPENDED_INFLIGHT_TTL, exc,
        )


async def _settle_authority_stragglers(session, espn, now, stats, update_fields_fn):
    """End a match the authority finished on a board day we never asked about.

    #4652. The mechanism, the measurement and why widening the status filters
    alone is inert are all in
    :func:`~app.utils.event_completion.authority_board_day_has_rolled`. This is
    the pass that acts on it.

    ── MATCHED ON ``espn_id`` ONLY, WHICH IS THE WHOLE SAFETY CASE ──

    The obvious implementation is to merge the prior day's board into
    ``espn_data[sport_key]`` and let the existing pass run. That is the one
    thing this must not do. ``match_event_to_espn`` falls back to NAME matching
    with no time guard at all (``espn_helpers`` says so in its own header), and
    yesterday's finished LAFC fixture and today's scheduled LAFC fixture are the
    same two names — so merging the boards would let a finished game's score and
    a Final settle onto a match that has not kicked off. That is gotcha #32's
    class and CERT-752's failure mode in one step.

    So this pass never matches by name. It looks each candidate up by its own
    ``espn_id`` in the board for its own day, and a board that does not contain
    that id is a no-op. Asking the wrong day therefore costs a request and
    changes nothing, which is what makes the date arithmetic safe to be wrong.

    Nothing here decides that a match is over: :func:`update_fields_fn` settles
    only on ``state="post"`` **and** ``completed=True``
    (``espn_terminal_state``), so a postponed or abandoned fixture — event
    15291065, FC Cincinnati v D.C. United, is in this very candidate set at 0-0
    — reaches the door and is correctly refused.
    """
    from app.utils.event_completion import (
        EVENT_SUSPENDED,
        authority_board_day_has_rolled,
        espn_board_date,
    )

    stats["straggler_candidates"] = 0
    stats["straggler_boards_fetched"] = 0
    stats["straggler_settled"] = 0

    result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            # The two states an authority may still end (`authority_may_settle`
            # admits exactly these). A settled row is left alone — re-ending it
            # rewrites history for no reader.
            Event.status.in_(["live", EVENT_SUSPENDED]),
            Event.espn_id.isnot(None),
            Event.commence_time >= now - AUTHORITY_STRAGGLER_LOOKBACK,
            Event.commence_time <= now - AUTHORITY_STRAGGLER_MIN_AGE,
        )
    )

    groups: dict[tuple[str, str], list] = {}
    for event in result.scalars().all():
        # A row whose board day is still today is already reachable by the
        # ordinary pass; asking again would just spend a request to agree.
        if not authority_board_day_has_rolled(event.commence_time, now):
            continue
        sport_key = event.sport.key if event.sport else ""
        if sport_key not in ESPN_SPORT_MAPPING:
            continue
        groups.setdefault(
            (sport_key, espn_board_date(event.commence_time)), []
        ).append(event)

    stats["straggler_candidates"] = sum(len(v) for v in groups.values())

    await _ask_boards_by_espn_id(
        session, espn, sorted(groups.items()), stats, update_fields_fn,
        stat_prefix="straggler",
        log_tag=(
            "#4652 straggler: event %d (%s vs %s, %s) %s → %s from the %s "
            "board — the day it was filed under, not the day we were asking "
            "about."
        ),
    )


async def _ask_boards_by_espn_id(
    session, espn, ordered_groups, stats, update_fields_fn, *,
    stat_prefix, log_tag, on_asked=None, allow_unstarted=False,
):
    """Fetch each (sport, board day) board and settle its rows BY ``espn_id``.

    The shared body of both straggler arms — the shallow one above and the deep
    one below — so the safety case those two docstrings make lives in exactly one
    place. ``ordered_groups`` is an already-ordered sequence of
    ``((sport_key, board_date), [event, ...])``; each arm decides its own
    candidates and its own order, and neither decides how a board is read.

    ``allow_unstarted`` is forwarded verbatim to ``update_fields_fn`` and read
    by nobody here. It is part of that collaborator's CONTRACT, stated in this
    signature rather than bound into the callable by the one arm that sets it
    (#5501) — a ``partial`` at the call site passes the same keyword while
    leaving every stand-in door looking compatible, and a stand-in that does not
    accept it raises ``TypeError`` into the per-row ``except`` below, where it
    is indistinguishable from a bad row and settles nothing.

    ``on_asked`` is called with each group's events once the board has been
    ASKED FOR, whether or not it answered. The deep arm advances its queue on
    that call, so it must fire on the dark path too: a sport whose board is
    persistently dark would otherwise hold the head of a stalest-first queue
    forever, which is the livelock the stamp exists to prevent.

    ⚠️ IT FIRES AFTER THE ROW LOOP, NOT BEFORE, AND THAT ORDERING IS LOAD-BEARING.
    ``update_fields_fn`` writes ``win_probability_sources`` itself (three sites in
    ``espn_helpers``), and each one re-assigns the in-memory value after its Core
    UPDATE so the object stays in step. A caller that merges a key into that same
    JSONB — which is exactly what the deep arm's stamp does — therefore has to
    read it once the door has finished with it, or it writes back a dict the door
    has already moved on from and silently drops the probability it just stored.
    """
    for (sport_key, board_date), events in ordered_groups:
        # Per-group, so one sport's dark board or bad row cannot wipe the pass
        # for every other sport (gotcha #42).
        try:
            board = await espn.get_scoreboard(sport_key, date=board_date)
        except Exception as e:
            stats["errors"].append(
                f"{stat_prefix}_fetch_{sport_key}_{board_date}: {str(e)}"
            )
            if on_asked is not None:
                await on_asked(events)
            continue

        if board is None:
            # AUTHORITY DARK — ESPN did not answer. An absence from a board
            # nobody served proves nothing (#3473), so nothing is settled.
            stats["authority_dark_sports"] += 1
            logger.warning(
                "ESPN board %s authority dark for %s — %d straggler(s) left "
                "as they are", board_date, sport_key, len(events),
            )
            if on_asked is not None:
                await on_asked(events)
            continue

        stats[f"{stat_prefix}_boards_fetched"] += 1
        by_id = {ee.espn_id: ee for ee in board if ee.espn_id}
        claimed_espn_ids = {e.espn_id for e in events if e.espn_id}

        for event in events:
            matched = by_id.get(event.espn_id)
            if matched is None:
                continue
            was = event.status
            try:
                await update_fields_fn(
                    session, event, matched, claimed_espn_ids, stats,
                    allow_unstarted=allow_unstarted,
                )
            except Exception as e:
                stats["errors"].append(
                    f"{stat_prefix}_update_{event.id}: {str(e)}"
                )
                continue
            if event.status != was:
                stats[f"{stat_prefix}_settled"] += 1
                logger.info(
                    log_tag,
                    event.id, event.home_team_name, event.away_team_name,
                    sport_key, was, event.status, board_date,
                )

        if on_asked is not None:
            await on_asked(events)


def _deep_straggler_asked_at(event, now) -> Optional[datetime]:
    """When did the deep arm last ASK about this row? ``None`` for never.

    ``None`` is also the answer for a stamp that cannot be read and for one that
    sits in the FUTURE, and both defaults are deliberate: this value is a queue
    position, and the failure mode to avoid is a row that can never reach the
    head of the queue again. A garbled stamp or a clock that ran backwards would
    park a settleable row forever; treating either as "never asked" costs one
    board fetch and self-heals on the next write.

    ``now`` is a parameter rather than a clock read for the reason every other
    time-dependent policy in this module takes one: a function that reads its own
    clock cannot be tested against a fixed anchor (gotcha #44).
    """
    sources = getattr(event, "win_probability_sources", None) or {}
    raw = sources.get(DEEP_STRAGGLER_ASKED_KEY)
    if not raw:
        return None
    try:
        asked = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if asked.tzinfo is None:
        asked = asked.replace(tzinfo=timezone.utc)
    if asked > now:
        return None
    return asked


async def _settle_deep_authority_stragglers(
    session, espn, now, stats, update_fields_fn
):
    """Reach the anchored rows that aged out of the settle window (#6280).

    ``_settle_authority_stragglers`` above asks about the right BOARD DAY but
    only for rows inside :data:`AUTHORITY_STRAGGLER_LOOKBACK`. This arm is the
    same question asked of the rows that fell past it — the permanently stranded
    population described at :data:`AUTHORITY_DEEP_STRAGGLER_REASK`, which nothing
    else selects.

    ── IT ALSO REACHES ``scheduled`` NOW, AND THAT IS WHERE THE ROWS WERE (#5501) ──

    The arm shipped selecting ``live``/``suspended``, and its measured population
    of seven was taken over that same pair — so the census could only ever count
    the states the filter named. A row that never got its ``scheduled → live``
    promotion is stranded in the identical way and by the identical mechanism,
    and was invisible to the arm built for the gap. Measured 2026-09-23: 820 rows
    over seven days past kickoff sat ``scheduled``, 328 of them with an
    ``espn_id`` this arm can anchor on, and NONE of those 328 shared that id with
    any other row — so settling them by id cannot mint a second row for a game.
    :data:`DEEP_STRAGGLER_STATUSES` is the widened set; the permission to write a
    Final onto one of them is passed to the door explicitly at the call below and
    is this arm's alone.

    ── STRICTLY DISJOINT FROM THE SHALLOW ARM, WHICH IS THE WHOLE SAFETY CASE ──

    The candidate window is ``commence_time < now - AUTHORITY_STRAGGLER_LOOKBACK``
    — the exact complement of the shallow arm's, not an overlap. So this cannot
    change what the shallow arm does, cannot double-fetch a board it already
    fetched in the same pass, and cannot put a row the liveness path is actively
    working into a six-hour cooldown. The two arms partition the anchored
    unsettled population on one boundary; move the boundary and they still
    partition it.

    It settles through the same door as every other authority write —
    ``update_fields_fn`` requires ``state="post"`` AND ``completed=True``
    (``espn_terminal_state``) — and it matches BY ``espn_id`` ONLY, never by
    name, for the reason ``_settle_authority_stragglers`` sets out at length: a
    name match across board days lets a finished game's Final land on a fixture
    that has not kicked off (gotcha #32, CERT-752's class). Here that is not a
    theoretical worry. Three of the seven rows in the measured population are
    fixtures ESPN has filed under a LATER board day than the one our row carries
    — two unplayed college-football games and one postponement — so the board
    this arm fetches for them does not contain their id and the pass is a no-op
    on exactly the rows that must not be settled. They are refused a step before
    the door, by absence rather than by judgement.

    ``authority_board_day_has_rolled`` is not consulted: it is structurally True
    for everything past 48 hours, and a guard that cannot return False on its own
    candidate set is a vacuous one.
    """
    from sqlalchemy import update as sql_update

    from app.utils.event_completion import espn_board_date

    stats["deep_straggler_candidates"] = 0
    stats["deep_straggler_eligible"] = 0
    stats["deep_straggler_groups"] = 0
    stats["deep_straggler_boards_fetched"] = 0
    stats["deep_straggler_settled"] = 0
    stats["deep_straggler_asked"] = 0

    result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(DEEP_STRAGGLER_STATUSES),
            Event.espn_id.isnot(None),
            Event.commence_time < now - AUTHORITY_STRAGGLER_LOOKBACK,
        )
        .order_by(Event.commence_time.desc())
        .limit(MAX_DEEP_STRAGGLER_CANDIDATES)
    )
    candidates = result.scalars().all()
    stats["deep_straggler_candidates"] = len(candidates)

    # THE COOLDOWN AND THE ORDER ARE BOTH READ OFF THE SAME STAMP, in Python
    # rather than in SQL. The population is bounded by the SELECT above and
    # measured at seven; keeping the queue arithmetic out of a JSONB expression
    # keeps it testable without a database, which is how every other policy in
    # this module is tested.
    cooldown_floor = now - AUTHORITY_DEEP_STRAGGLER_REASK
    groups: dict[tuple[str, str], list] = {}
    asked_by_group: dict[tuple[str, str], datetime] = {}
    never = datetime.min.replace(tzinfo=timezone.utc)

    for event in candidates:
        sport_key = event.sport.key if event.sport else ""
        if sport_key not in ESPN_SPORT_MAPPING:
            continue
        asked = _deep_straggler_asked_at(event, now)
        if asked is not None and asked > cooldown_floor:
            continue
        key = (sport_key, espn_board_date(event.commence_time))
        groups.setdefault(key, []).append(event)
        # A group is as stale as its stalest row, so one never-asked row pulls
        # its whole board day forward — the board is fetched once either way.
        stamp = asked or never
        if key not in asked_by_group or stamp < asked_by_group[key]:
            asked_by_group[key] = stamp

    stats["deep_straggler_eligible"] = sum(len(v) for v in groups.values())
    stats["deep_straggler_groups"] = len(groups)
    if not groups:
        return

    # Stalest first, then a stable tiebreak so a pass is reproducible.
    ordered = sorted(groups.items(), key=lambda kv: (asked_by_group[kv[0]], kv[0]))
    ordered = ordered[:MAX_DEEP_STRAGGLER_BOARDS_PER_PASS]

    async def _stamp_asked(events):
        """Advance the queue for every row this pass actually asked about.

        Rows the ask SETTLED are skipped: they have left the candidate states,
        so they can never be selected again and a stamp on them is residue.

        THE PREDICATE IS THE ARM'S OWN CANDIDATE SET, NOT THE SETTLE DOOR'S
        (#5501). Those were the same thing while the arm selected exactly the
        settleable states. They are not now: a `scheduled` candidate the board
        did not settle would fail a bare `authority_may_settle`, be read as
        "already left the candidate states", and go unstamped — so it would
        re-ask its board every pass forever, which is the livelock the stamp
        exists to prevent.
        """
        for event in events:
            if event.status not in DEEP_STRAGGLER_STATUSES:
                continue
            updated = dict(getattr(event, "win_probability_sources", None) or {})
            updated[DEEP_STRAGGLER_ASKED_KEY] = now.isoformat()
            try:
                await session.execute(
                    sql_update(Event)
                    .where(Event.id == event.id)
                    .values(win_probability_sources=updated)
                )
            except Exception as e:
                stats["errors"].append(
                    f"deep_straggler_stamp_{event.id}: {str(e)}"
                )
                continue
            # Keep the in-memory row consistent with the write, so a second
            # read inside the same pass sees the same queue position.
            event.win_probability_sources = updated
            stats["deep_straggler_asked"] += 1

    # THE PERMISSION IS GRANTED HERE AND NOWHERE ELSE (#5501). By this line the
    # row has cleared every condition the flag's contract names: past the 48h
    # window (the SELECT), and about to be matched BY `espn_id` against its own
    # board day and settled only on ESPN's `post`/`completed` (the door). The
    # shallow arm and the liveness pass call the same door without it.
    await _ask_boards_by_espn_id(
        session, espn, ordered, stats, update_fields_fn,
        allow_unstarted=True,
        stat_prefix="deep_straggler",
        log_tag=(
            "#6280/#5501 deep straggler: event %d (%s vs %s, %s) %s → %s from "
            "the %s board — anchored, past the 48h settle window, and stranded "
            "until now."
        ),
        on_asked=_stamp_asked,
    )


def _unstarted_recovery_asked_at(event, now):
    """When this arm last asked about `event`, or None if it never has."""
    sources = getattr(event, "win_probability_sources", None) or {}
    raw = sources.get(UNSTARTED_RECOVERY_ASKED_KEY)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        # An unparseable stamp is treated as "never asked" rather than skipped.
        # The failure mode of forgetting is one extra call; the failure mode of
        # skipping is a row that is never revisited again.
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _recover_unstarted_authority_fixtures(session, espn, now, stats):
    """Restore the misdated fixtures the board arms cannot reach (#6280).

    The complement of :func:`_settle_deep_authority_stragglers`: those rows are
    late, these are MISDATED, and the block comment at
    :data:`AUTHORITY_UNSTARTED_REASK` sets out the measurement and the reason
    this asks the anchor rather than the board.

    ── THE FOUR GATES, AND WHY EACH ONE IS NOT THE OTHERS ──

    1. ``get_event`` returned an answer. It is ``None`` for a 404 AND for a dark
       authority (``ESPNAuthorityDark`` is swallowed there), and neither is
       evidence about the fixture — gotcha #53. No answer, no write, and the
       row keeps its place in the queue.
    2. ESPN says ``scheduled`` with BOTH scores absent. A fixture with a score
       has been played whatever its status string says.
    3. ESPN's start is in the FUTURE. This is the gate that makes the arm safe
       against its own worst case: if the anchor named a game that already
       happened, the write would move a played game's clock forward and hide it.
       It is also the narrow reading of Alex's 2026-09-14 constraint — *a
       scheduled kickoff is not evidence of an actual start* — so a scheduled
       time is used to set a SCHEDULED kickoff and never to assert that a game
       started or finished.
    4. The teams agree with the anchor. A disagreement means the id is wrong,
       not the clock, and that is
       ``repair_authority_id_collisions``' question — refused here, never
       guessed at.

    Plus one refusal taken from the registry rather than reinvented: a row whose
    clock came from a provider that outranks ESPN (``mlb_schedule_repair``) is
    left alone — ``utils.start_time_authority.provider_may_set_start``, the one
    call every start-time rail makes (#8653). This arm used to skip StatPal
    clocks instead, copying a precedence that was upside down: the registry
    ranks ESPN above StatPal, and a stale StatPal start is exactly the row that
    needs ESPN's.

    THE WRITE IS A COMPARE-AND-WRITE (#6056). It touches four live-state columns
    (``period``, ``game_clock``, and the two scores), so it goes through
    ``write_row_if_unmoved`` rather than a bare Core ``update``. The predicate is
    what this arm's decision actually CONSUMED — ``status`` and ``commence_time``,
    the two facts that made the row a candidate — and not position, which this
    arm never reads and which is NULL on these rows anyway; a position predicate
    here would compile, run green and arbitrate nothing.
    """
    from sqlalchemy import update as sql_update

    from app.utils.event_completion import EVENT_SUSPENDED
    from app.utils.live_state_write import write_row_if_unmoved

    stats["unstarted_recovery_candidates"] = 0
    stats["unstarted_recovery_eligible"] = 0
    stats["unstarted_recovery_asked"] = 0
    stats["unstarted_recovery_recovered"] = 0
    stats["unstarted_recovery_refused_teams"] = 0
    stats["unstarted_recovery_no_answer"] = 0
    stats["unstarted_recovery_row_moved"] = 0

    result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["live", EVENT_SUSPENDED]),
            Event.espn_id.isnot(None),
            Event.commence_time < now - AUTHORITY_STRAGGLER_LOOKBACK,
        )
        .order_by(Event.commence_time.desc())
        .limit(MAX_DEEP_STRAGGLER_CANDIDATES)
    )
    candidates = result.scalars().all()
    stats["unstarted_recovery_candidates"] = len(candidates)

    cooldown_floor = now - AUTHORITY_UNSTARTED_REASK
    never = datetime.min.replace(tzinfo=timezone.utc)
    eligible = []
    for event in candidates:
        sport_key = event.sport.key if event.sport else ""
        if sport_key not in ESPN_SPORT_MAPPING:
            continue
        # A provider ESPN does not outrank owns this row's clock; see the
        # docstring.
        if not provider_may_set_start(event.commence_time_source, "espn"):
            continue
        asked = _unstarted_recovery_asked_at(event, now)
        if asked is not None and asked > cooldown_floor:
            continue
        eligible.append((asked or never, event.id, sport_key, event))

    stats["unstarted_recovery_eligible"] = len(eligible)
    if not eligible:
        return

    # Stalest ASK first — never stalest kickoff, which is the key the work
    # cannot advance — then the id for a reproducible pass.
    eligible.sort(key=lambda item: (item[0], item[1]))

    for _asked, _event_id, sport_key, event in eligible[
        :MAX_UNSTARTED_RECOVERY_ASKS_PER_PASS
    ]:
        try:
            espn_event = await espn.get_event(sport_key, event.espn_id)
        except Exception as e:
            stats["errors"].append(f"unstarted_recovery_{event.id}: {str(e)}")
            continue

        recovered = False
        if espn_event is None:
            # Gate 1 — absent or dark, indistinguishable here and both silent.
            stats["unstarted_recovery_no_answer"] += 1
        else:
            starts_at = getattr(espn_event, "date", None)
            if starts_at is not None and starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=timezone.utc)
            unplayed = (
                espn_event.status == "scheduled"  # gate 2
                and espn_event.home_score is None
                and espn_event.away_score is None
            )
            in_future = starts_at is not None and starts_at > now  # gate 3
            if unplayed and in_future:
                home_names, away_names = get_event_name_variations(event)
                teams_agree = bool(
                    espn_event.home_team
                    and espn_event.away_team
                    and espn_team_matches(home_names, espn_event.home_team)
                    and espn_team_matches(away_names, espn_event.away_team)
                )
                if not teams_agree:  # gate 4
                    stats["unstarted_recovery_refused_teams"] += 1
                else:
                    # Read BEFORE the write — the log's whole value is the pair
                    # of clocks, and the CAS below updates the instance itself.
                    previous_clock = event.commence_time
                    previous_status = event.status
                    # THE PREDICATE IS WHAT THE DECISION CONSUMED (#6056), which
                    # here is not position but the two facts that made this row a
                    # candidate at all: it was unsettled, and its clock was the
                    # stale one. If a settle arm finished it or another rail
                    # corrected its clock between the SELECT and now, this row is
                    # no longer the thing we decided about and the write refuses.
                    # Deliberately NOT a period/game_clock predicate: this arm
                    # never reads position, and on these rows both are routinely
                    # NULL, so such a predicate could never refuse — the vacuous
                    # compare-and-write `write_row_if_unmoved` warns about.
                    try:
                        landed = await write_row_if_unmoved(
                            session,
                            event,
                            {
                                "commence_time": starts_at,
                                "commence_time_source": "espn",
                                "status": "scheduled",
                                "home_score": None,
                                "away_score": None,
                                "period": None,
                                "game_clock": None,
                            },
                            observed={
                                "status": previous_status,
                                "commence_time": previous_clock,
                            },
                            what="unstarted authority recovery",
                        )
                    except Exception as e:
                        stats["errors"].append(
                            f"unstarted_recovery_write_{event.id}: {str(e)}"
                        )
                        continue
                    if not landed:
                        # The row moved under us. It is not recovered, so it
                        # keeps its place in the queue and is asked again.
                        stats["unstarted_recovery_row_moved"] += 1
                    else:
                        recovered = True
                        stats["unstarted_recovery_recovered"] += 1
                        logger.info(
                            "#6280 unstarted recovery: event %d (%s vs %s, %s) "
                            "was %s at %s — ESPN's anchor %s says it is "
                            "scheduled for %s and has not been played. "
                            "Restored to scheduled.",
                            event.id,
                            event.away_team_name,
                            event.home_team_name,
                            sport_key,
                            previous_status,
                            previous_clock.isoformat() if previous_clock else None,
                            event.espn_id,
                            starts_at.isoformat(),
                        )

        if recovered:
            # It has left the candidate states, so it can never be selected
            # again and a stamp on it would be residue — the lesson the deep
            # arm's `_stamp_asked` records one function up.
            continue
        # Merged onto whatever the deep arm may have written THIS pass: the
        # identity map hands both arms the same ORM object and that arm mirrors
        # its own stamp, so reading the attribute here cannot lose it.
        updated = dict(getattr(event, "win_probability_sources", None) or {})
        updated[UNSTARTED_RECOVERY_ASKED_KEY] = now.isoformat()
        try:
            await session.execute(
                sql_update(Event)
                .where(Event.id == event.id)
                .values(win_probability_sources=updated)
            )
        except Exception as e:
            stats["errors"].append(f"unstarted_recovery_stamp_{event.id}: {str(e)}")
            continue
        event.win_probability_sources = updated
        stats["unstarted_recovery_asked"] += 1


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


#: How many distinct board days one sport may ask about in a single pass
#: (#5697). One is the ordinary answer; the second exists for the fixture still
#: being played when Eastern midnight passes, which is filed under yesterday's
#: board while it is live. Anything beyond that is not a live game, and the
#: cost lands on `sync_espn_live_events`, which already overruns its own 60 s
#: period (p95 111.5 s) — so the ceiling is deliberate, not defensive.
MAX_DATED_BOARDS_PER_SPORT = 2


async def _process_live_sport(
    session, sport_key, espn_events, stats,
    recently_completed_cutoff, started_cutoff,
    espn_names_match, upsert_team_fn, register_identities_fn,
    match_event_fn, update_fields_fn, write_win_prob_fn,
    compute_stat_model_fn, create_unmatched_fn,
    dated_board_fetcher=None,
):
    """Process all live/recently-completed events for one sport.

    Handles event matching, field updates, win probability, stat model,
    team upsert, identity registration, and creation of new events
    from unmatched ESPN games.

    ``dated_board_fetcher`` is ``async (sport_key, "YYYYMMDD") -> list | None``.
    When supplied, an event the undated board cannot account for gets a second
    question asked about **its own** board day — see :func:`_widened_pool_for`.
    """
    from app.models.models import Event, Team
    from sqlalchemy import and_, or_, update as sql_update
    # Function-local for the same reason every other `espn_helpers` import in
    # this module is: the two modules import each other (header, line 62).
    from app.utils.espn_helpers import (
        clear_authority_not_started,
        espn_pregame_filler,
        espn_scheduled_demotes_live,
        espn_scheduled_marks_not_started,
        play_evidence,
        stamp_authority_not_started,
    )
    from app.utils.live_state_write import write_live_state_if_unmoved

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

    # ── THE UNDATED BOARD IS A CURATED SLICE, NOT THE DAY'S SLATE (#5697) ──
    #
    # #4652 found that the undated board answers about *today*, and ends after
    # Eastern midnight go unread. This is the other half of the same root
    # cause, and the one that shows on the page while the game is on: even
    # for today, `GET /scoreboard` with no date is a FEATURED subset.
    #
    # MEASURED, ESPN's own API, 2026-09-12 22:25Z (standing notice 26):
    #
    #     GET football/college-football/scoreboard                  24 events
    #     GET football/college-football/scoreboard?limit=200        24 events
    #     GET football/college-football/scoreboard?dates=20260912   80 events
    #
    # `?limit=200` on the undated call also returns 24, so this is not a page
    # size — it is a different question. All 11 of the NCAAF games that carried
    # NO SCORE through their entire 3h26m were absent from the 24 and present
    # in the 80; all five that tracked live were in the 24. The same pass
    # reported `events_synced: 5, events_unmatched: 23`.
    #
    # What a reader got for those 11: `LIVE`, `live · 1m ago`, `⟳ 20s`, a
    # moving chart and `Projected final: 23 – 31`, over a game the page could
    # not name the score of — every freshness signal green and correct, which
    # is the worst shape, because nothing tells them the number is missing
    # rather than 0–0. Then one ScoreSnapshot at +240 min when a dated path
    # finally settled it.
    #
    # ── WHY THE POOL IS PER-EVENT AND NOT MERGED ──
    #
    # #4652's safety case: "LAFC" on the 9/9 board and "LAFC" on the 9/10 board
    # are the same string, so merging another day's board into the shared pool
    # would let a finished score and a Final land on a fixture that has not
    # kicked off (gotcha #32 / CERT-752's class). So the widened pool is built
    # for ONE event, from the board day of that event's OWN commence_time, and
    # is never appended to `espn_events` — `create_unmatched_fn` below still
    # sees exactly the board it saw before, so no event is created off a board
    # this widening fetched.
    #
    # That is the first of two independent guards. The second is already in the
    # matcher and is measured, not assumed: since #2049 the name arm authorizes
    # through `select_authorized_espn_candidate`, which refuses any candidate
    # more than `NAME_ONLY_SAME_GAME_SECONDS` (3 h) from our own
    # `commence_time`. (#4652's prose predates that and still says the name arm
    # has no time guard; it has one.)
    boards_by_day: dict[str, list] = {}

    async def _widened_pool_for(event):
        """(pool, by_id) for one event's own board day, or ``None``.

        ``None`` means there is nothing new to match against — no fetcher, the
        per-sport ceiling is spent, the authority went dark, or the dated board
        added no game the undated one did not already carry.
        """
        if dated_board_fetcher is None:
            return None
        commence = getattr(event, "commence_time", None)
        if commence is None:
            return None
        day = espn_board_date(commence)
        if day not in boards_by_day:
            if len(boards_by_day) >= MAX_DATED_BOARDS_PER_SPORT:
                stats["dated_board_days_skipped"] = (
                    stats.get("dated_board_days_skipped", 0) + 1
                )
                return None
            try:
                board = await dated_board_fetcher(sport_key, day)
            except Exception as e:
                stats["errors"].append(f"dated_board_{sport_key}_{day}: {str(e)}")
                board = None
            # AUTHORITY DARK (`None`) and a genuinely empty slate (`[]`) are
            # different facts, and this pass acts on neither: it only ever ADDS
            # candidates, so it has nothing to say when there are none. The
            # empty list is cached so one dark board is not re-asked per event.
            if board is None:
                stats["dated_board_dark"] = stats.get("dated_board_dark", 0) + 1
            else:
                stats["dated_board_fetches"] = (
                    stats.get("dated_board_fetches", 0) + 1
                )
            boards_by_day[day] = board or []

        extra = [
            ee for ee in boards_by_day[day]
            if not ee.espn_id or ee.espn_id not in espn_by_id
        ]
        if not extra:
            return None
        pool = list(espn_events) + extra
        by_id = dict(espn_by_id)
        for ee in extra:
            if ee.espn_id:
                by_id[ee.espn_id] = ee
        return pool, by_id

    for event in our_events:
        matched_espn, match_method = match_event_fn(
            event, espn_events, espn_by_id, claimed_espn_ids, espn_names_match,
        )

        if not matched_espn:
            widened = await _widened_pool_for(event)
            if widened is not None:
                pool, by_id = widened
                matched_espn, match_method = match_event_fn(
                    event, pool, by_id, claimed_espn_ids, espn_names_match,
                )
                if matched_espn:
                    stats["events_matched_on_dated_board"] = (
                        stats.get("events_matched_on_dated_board", 0) + 1
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

        # ── THE AUTHORITY SAYS NOBODY HAS STARTED (#5324, second half) ──
        #
        # Read AFTER `update_fields_fn` on purpose: that call is what lands
        # ESPN's score, period and clock on the row, so the observation guard
        # inside the predicate judges this pass's facts rather than last
        # pass's. It is also what corrects `commence_time` to ESPN's own — the
        # slide we ingest correctly and then go on contradicting.
        #
        # ANCHORED ROWS ONLY. A name match can fold onto the wrong sibling
        # (gotcha #32 — the same two teams play again on Thursday), and a
        # status write driven by a mis-matched board entry would blank a game
        # that is genuinely being played. `espn_terminal_write_is_fold` exists
        # because that fold is real; ruling 048's id-anchored correspondence is
        # the bar for a claim about identity, and this is one. The tennis
        # authority write next door is likewise anchored-only.
        #
        # THE BOARD'S OWN FILLER IS NOT EVIDENCE AGAINST THE BOARD (#5324,
        # team-sport half). A pre-game ESPN board publishes clock "0:00" (MLB
        # also period "Scheduled") and score 0; a row that took those before
        # the updater stopped copying them would refuse this demotion forever
        # on values the authority wrote while saying "not started". Judged with
        # them removed, and — when the authority does say not started —
        # withdrawn from the row too, because the promoter's hold reads the ROW
        # (`authority_not_started_holds`) and would otherwise be superseded by
        # the same filler one beat later.
        _filler = (
            espn_pregame_filler(
                ee.status, _sanitize_period(ee.status_detail), ee.clock,
                ee.home_score, ee.away_score,
                period=event.period, game_clock=event.game_clock,
                home_score=event.home_score, away_score=event.away_score,
            )
            if match_method == "espn_id" else {}
        )
        # Read only for anchored rows, as the predicates below always were —
        # an unanchored pass never consults the row's live state here.
        if match_method == "espn_id":
            _ev_period = None if "period" in _filler else event.period
            _ev_clock = None if "game_clock" in _filler else event.game_clock
            _ev_home = None if "home_score" in _filler else event.home_score
            _ev_away = None if "away_score" in _filler else event.away_score
        else:
            _ev_period = _ev_clock = _ev_home = _ev_away = None
        _authority_says_not_started = match_method == "espn_id" and (
            espn_scheduled_marks_not_started(
                event.status, ee.status,
                home_score=_ev_home, away_score=_ev_away,
                period=_ev_period, game_clock=_ev_clock,
            )
        )
        if _authority_says_not_started and _filler:
            # Compare-and-write on the four columns (#6056): if another writer
            # moved the row since we read it, something real may have landed,
            # so this pass neither withdraws nor demotes.
            _withdrawn = await write_live_state_if_unmoved(
                session, event, _filler,
                observed_period=event.period,
                observed_clock=event.game_clock,
                observed_home_score=event.home_score,
                observed_away_score=event.away_score,
                what="ESPN pre-game filler withdrawal (#5324)",
            )
            if _withdrawn:
                stats["pregame_filler_withdrawn"] = (
                    stats.get("pregame_filler_withdrawn", 0) + 1
                )
                changed = True
            else:
                _authority_says_not_started = False
        _demotes = _authority_says_not_started and espn_scheduled_demotes_live(
            event.status, ee.status,
            home_score=_ev_home, away_score=_ev_away,
            period=_ev_period, game_clock=_ev_clock,
        )
        if _demotes:
            logger.info(
                "ESPN authority demotes LIVE -> scheduled: event %d (%s vs %s) "
                "— ESPN reports STATUS_SCHEDULED, our commence %s (#5324)",
                event.id, event.home_team_name, event.away_team_name,
                event.commence_time.isoformat() if event.commence_time else None,
            )
            # THE STATUS ALONE DOES NOT SURVIVE (CERT-2777's required repair).
            #
            # `_transition_event_statuses_impl` runs on the same 60s realtime
            # beat and promotes `scheduled` + `commence_time <= now` straight
            # back to `live`, so writing only the status buys one minute. The
            # authority's statement travels with it, in the JSONB mirror, and
            # the promoter honours it until positive play evidence supersedes
            # it (`authority_not_started_holds`).
            #
            # ONE Core update for both fields, and the ORM object mirrored
            # after it — the idiom `write_espn_win_prob` uses six hundred lines
            # up, and for its reason: an ORM attribute assignment mixed with
            # Core updates on the same row can fail to flush (gotcha #4/#5),
            # and a JSONB value mutated in place is not tracked at all.
            _wps_not_started = stamp_authority_not_started(
                event.win_probability_sources, datetime.now(timezone.utc)
            )
            await session.execute(
                sql_update(Event)
                .where(Event.id == event.id)
                .values(
                    status="scheduled",
                    win_probability_sources=_wps_not_started,
                )
            )
            event.status = "scheduled"
            event.win_probability_sources = _wps_not_started
            stats["live_demoted_by_authority"] = (
                stats.get("live_demoted_by_authority", 0) + 1
            )
            changed = True
        elif _authority_says_not_started:
            # THE SECOND, THIRD AND FOURTH `scheduled` PASS (CERT-2782).
            #
            # The row is already `scheduled` — there is nothing to demote — but
            # the authority is still saying the game has not begun, so the
            # marker is REFRESHED rather than left to age out. Without this the
            # hold would expire on its TTL while ESPN was still, every 60
            # seconds, telling us the game had not started.
            #
            # The first cut had no branch here at all: it read "the demotion
            # did not fire" as "clear the marker", so this pass DELETED the
            # fact the previous one recorded and the next transition put the
            # row back to LIVE. That is the flicker, with a period of two
            # passes instead of one.
            _wps_refreshed = stamp_authority_not_started(
                event.win_probability_sources, datetime.now(timezone.utc)
            )
            await session.execute(
                sql_update(Event)
                .where(Event.id == event.id)
                .values(win_probability_sources=_wps_refreshed)
            )
            event.win_probability_sources = _wps_refreshed
            stats["authority_not_started_refreshed"] = (
                stats.get("authority_not_started_refreshed", 0) + 1
            )
            changed = True
        elif match_method == "espn_id" and play_evidence(
            event.home_score, event.away_score, event.period, event.game_clock,
        ):
            # CLEARED ONLY ON POSITIVE PLAY, which is the whole correction.
            #
            # The marker is a claim that the game has not begun. Only evidence
            # that it HAS may retract it — the same `play_evidence` the hold is
            # superseded by and the demotion refuses on, so no pass can clear a
            # fact another pass would immediately re-stamp. An ambiguous or
            # unrecognised ESPN state (`status_delayed` above all) leaves the
            # marker exactly where it is; silence retracts nothing.
            _wps_cleared = clear_authority_not_started(event.win_probability_sources)
            if _wps_cleared is not event.win_probability_sources:
                await session.execute(
                    sql_update(Event)
                    .where(Event.id == event.id)
                    .values(win_probability_sources=_wps_cleared)
                )
                event.win_probability_sources = _wps_cleared
                stats["authority_not_started_cleared"] = (
                    stats.get("authority_not_started_cleared", 0) + 1
                )
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


async def _fetch_full_slate_boards(espn, scheduled_sport_keys, stats) -> dict:
    """``{sport_key: [ESPNEvent, ...]}`` — the whole-group board, per sport (#8682).

    Only sports in ``ESPN_FULL_SLATE_GROUPS`` are asked. A sport whose ask came
    back dark (``None``) or raised is simply ABSENT, and
    :func:`scheduled_board_for` then falls back to the featured board the pass
    has always used — this can only ever add games, never take the pass's
    board away.
    """
    from app.services.espn_api import ESPN_FULL_SLATE_GROUPS

    boards: dict = {}
    for key in scheduled_sport_keys:
        groups = ESPN_FULL_SLATE_GROUPS.get(key)
        if not groups:
            continue
        try:
            board = await espn.get_scoreboard(key, groups=groups)
        except Exception as e:
            stats["errors"].append(f"espn_full_slate_{key}: {str(e)}")
            continue
        if board is None:
            stats["full_slate_dark"] = stats.get("full_slate_dark", 0) + 1
            continue
        boards[key] = board
        stats.setdefault("full_slate_events", {})[key] = len(board)
    return boards


def scheduled_board_for(sport_key, featured_board, full_slate_boards) -> list:
    """The board the pre-game pass matches against (#8682).

    The full-group board when one answered with games, else the featured board.
    An EMPTY full-group answer does not replace a featured board that has games:
    the full slate is a superset by construction, so an empty one beside a
    non-empty featured one is the odd answer, and the pass keeps what it had.
    """
    full = full_slate_boards.get(sport_key)
    return full if full else featured_board

def espn_abbreviation_corresponds(abbreviation, *names) -> bool:
    """True when an ESPN abbreviation can be derived from the club's own name.

    ESPN's AFL list carries two records named "Sydney Swans" (#6432): id 4 is
    SYD/syd.png, id 19 is GCFC/gcfc.png — Gold Coast's media filed under
    Sydney's name. The names are identical, so the name comparison
    `_cleanup_bad_espn_matches` performs cannot tell them apart. The
    abbreviation is the only witness the record carries against itself.

    Two ways to correspond, because real clubs build abbreviations both ways:
    the letters in order ("SYD" through s-y-d-n-e-y, "STK" through s-t-k-ilda)
    or the club's initials as a prefix ("NMFC" opens with N-M for North
    Melbourne, then adds letters the name never had). "GCFC" is neither for
    "Sydney Swans", and no other record on the real 19-team roster is accused.
    """
    if not abbreviation:
        return False
    abbr = "".join(ch for ch in abbreviation.lower() if ch.isalnum())
    if not abbr:
        return False
    for name in names:
        if not name:
            continue
        tokens = "".join(
            ch if ch.isalnum() else " " for ch in name.lower()
        ).split()
        if not tokens:
            continue
        initials = "".join(token[0] for token in tokens)
        if abbr.startswith(initials):
            return True
        letters = iter("".join(tokens))
        if all(ch in letters for ch in abbr):
            return True
    return False


def _espn_record_is_self_consistent(espn_team) -> bool:
    return espn_abbreviation_corresponds(
        espn_team.abbreviation,
        espn_team.display_name,
        espn_team.short_name,
        espn_team.name,
    )


def build_espn_name_lookup(espn_teams):
    """Index an ESPN team list by id and by name, refusing ambiguous names.

    A plain ``{name.lower(): team}`` dict silently keeps whichever record ESPN
    listed LAST, which is how a Sydney Swans row came to hold Gold Coast's
    badge (#6432). A name two records answer to is ambiguous: resolve it only
    when exactly one of them is self-consistent, and otherwise leave the name
    out of the lookup rather than let list order decide.

    Returns ``(by_id, by_name, name_candidates, collisions)``; the candidates
    map is what :func:`consistent_same_name_sibling` reads.
    """
    by_id = {}
    name_candidates = {}
    for espn_team in espn_teams:
        by_id[espn_team.espn_id] = espn_team
        # Skip et.name (mascot-only like "Buckeyes") and et.nickname — these
        # cause false positives when multiple teams share a mascot.
        for name in (espn_team.display_name, espn_team.short_name):
            if name and len(name) >= 4:
                bucket = name_candidates.setdefault(name.lower(), [])
                if all(other.espn_id != espn_team.espn_id for other in bucket):
                    bucket.append(espn_team)

    by_name = {}
    collisions = {"resolved": 0, "refused": 0}
    for name_key, candidates in name_candidates.items():
        if len(candidates) == 1:
            by_name[name_key] = candidates[0]
            continue
        consistent = [et for et in candidates if _espn_record_is_self_consistent(et)]
        if len(consistent) == 1:
            by_name[name_key] = consistent[0]
            collisions["resolved"] += 1
        else:
            collisions["refused"] += 1
            logger.warning(
                "ESPN name %r is answered by %d records and no abbreviation "
                "settles it — refusing the name rather than taking the last: %s",
                name_key,
                len(candidates),
                [(et.espn_id, et.abbreviation) for et in candidates],
            )
    return by_id, by_name, name_candidates, collisions


def consistent_same_name_sibling(matched_espn, name_candidates):
    """The record a poisoned anchor should point at, or ``None``.

    An ``espn_id`` already on our row wins every match here, and
    :func:`_backfill_team_logos` never revisits a row that has a logo — so a
    row stamped with ESPN's corrupt duplicate can never be corrected by the
    name path, and the `espn_id`-mismatch guard in ``upsert_team`` then refuses
    every real payload for the club. When the anchored record is not
    self-consistent and exactly one record sharing its name is, that one is the
    club. Anything less certain returns ``None``: an odd abbreviation on its
    own is not evidence.
    """
    if matched_espn is None or _espn_record_is_self_consistent(matched_espn):
        return None
    for name in (matched_espn.display_name, matched_espn.short_name):
        if not name or len(name) < 4:
            continue
        candidates = name_candidates.get(name.lower()) or []
        consistent = [et for et in candidates if _espn_record_is_self_consistent(et)]
        if len(consistent) == 1 and consistent[0].espn_id != matched_espn.espn_id:
            return consistent[0]
    return None


def espn_aliases_to_store(team_name, existing, matched_espn, *, match_was_exact, repointed_from):
    """The ``alternate_names`` the logo backfill writes, or ``None`` to leave them.

    Aliases are identity, held to the bar the ``espn_id`` write beside them is
    held to: an exact name, the stored id, or a repoint. A token-overlap score
    of 0.51 names SOME club, and unioning that club's names into our row makes
    it answer to them in search and — on the next pass, when the borrowed name
    exact-matches — in this very lookup (#8353: Akron Zips carried "Michigan
    Wolverines" and "Eastern Michigan Eagles"; twelve women's-basketball rows
    carried "West Virginia Mountaineers"). The crest may still come from a fuzzy
    hit on a row that has none (#4750's rule is about overwriting); a name never.
    """
    if matched_espn is None or not (match_was_exact or repointed_from):
        return None
    alt_names = set(existing or [])
    for n in (
        matched_espn.display_name,
        matched_espn.short_name,
        matched_espn.nickname,
        matched_espn.name,
    ):
        if n and n != team_name:
            alt_names.add(n)
    return list(alt_names) if alt_names else None


async def _backfill_team_logos():
    """Async implementation of backfill_team_logos."""
    from app.services.espn_api import ESPNAPIService, SPORT_LEAGUE_MAP
    from app.models.models import Team, Sport
    from sqlalchemy import or_, select

    stats = {
        "sports_checked": 0,
        "teams_fetched": 0,
        "teams_updated": 0,
        "espn_anchors_repointed": 0,
        "espn_name_collisions_resolved": 0,
        "espn_name_collisions_refused": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find under-enriched teams, grouped by sport. A missing
            # abbreviation admits the #6432 rows: a team anchored to ESPN's
            # corrupt duplicate keeps the wrong crest AND never gets a badge,
            # because `upsert_team` refuses every payload whose id disagrees
            # with the stored one. Measured 2026-09-15: 8,259 rows have no
            # logo, and the abbreviation arm adds 157 — a bounded widening,
            # and those 157 are write-protected below unless the match is
            # exact.
            result = await session.execute(
                select(Team, Sport.key)
                .join(Sport)
                .where(
                    or_(
                        Team.logo_url_small.is_(None),
                        Team.abbreviation.is_(None),
                    )
                )
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

                    # Build lookup of ESPN teams by various name forms. A name
                    # two records answer to is refused, never taken by list
                    # order (#6432) — see `build_espn_name_lookup`.
                    (
                        espn_by_id,
                        espn_by_name,
                        espn_name_candidates,
                        collisions,
                    ) = build_espn_name_lookup(espn_teams)
                    stats["espn_name_collisions_resolved"] += collisions["resolved"]
                    stats["espn_name_collisions_refused"] += collisions["refused"]

                    # Try to match our teams to ESPN teams
                    for team in teams_by_sport.get(sport_key, []):
                        matched_espn = None
                        match_was_exact = False
                        repointed_from = None
                        had_media = bool(team.logo_url_small)

                        # Match by ESPN ID first (most reliable)
                        if team.espn_id and team.espn_id in espn_by_id:
                            matched_espn = espn_by_id[team.espn_id]
                            match_was_exact = True
                            sibling = consistent_same_name_sibling(
                                matched_espn, espn_name_candidates
                            )
                            if sibling is not None:
                                repointed_from = matched_espn.espn_id
                                matched_espn = sibling
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

                        # A row that already carries a crest is only in this
                        # pass because its abbreviation is missing. A token
                        # score of 0.51 must never overwrite media that is
                        # already right (#4750's class) — an exact name, the
                        # stored id, or a repoint, or nothing at all.
                        if had_media and not (match_was_exact or repointed_from):
                            continue

                        if matched_espn and matched_espn.logo_url:
                            if repointed_from or not had_media:
                                team.logo_url_small = matched_espn.logo_url
                                team.logo_url_large = matched_espn.logo_url
                            if repointed_from:
                                # The anchor itself was the defect: it pinned
                                # the wrong club's media AND made `upsert_team`
                                # refuse every real payload for this club.
                                logger.warning(
                                    "Repointing team %s (%r) from ESPN id %s to "
                                    "%s — %r does not correspond to %r",
                                    team.id,
                                    team.name,
                                    repointed_from,
                                    matched_espn.espn_id,
                                    espn_by_id[repointed_from].abbreviation,
                                    espn_by_id[repointed_from].display_name,
                                )
                                stats["espn_anchors_repointed"] += 1
                            # Only set espn_id from exact or ID matches, not
                            # fuzzy scoring — or from a repoint, which is an
                            # id match whose record accused itself. ONE write
                            # site on purpose: the #2049 census keys on the
                            # statement, so a second copy would hide behind
                            # this one's allowlist reason.
                            if repointed_from or (
                                not team.espn_id and match_was_exact
                            ):
                                team.espn_id = matched_espn.espn_id
                            if (
                                matched_espn.abbreviation
                                and not team.abbreviation
                                and (match_was_exact or repointed_from)
                            ):
                                team.abbreviation = matched_espn.abbreviation
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
                            # Store alternate names for future matching —
                            # never from a fuzzy hit (#8353).
                            alt_names = espn_aliases_to_store(
                                team.name,
                                team.alternate_names,
                                matched_espn,
                                match_was_exact=match_was_exact,
                                repointed_from=repointed_from,
                            )
                            if alt_names is not None:
                                team.alternate_names = alt_names
                            stats["teams_updated"] += 1
            finally:
                await espn.close()

    except Exception as e:
        stats["errors"].append(f"Task error: {str(e)}")
        import traceback
        logger.warning("Team logo backfill error: %s", e, exc_info=True)

    return stats


#: Everything on a Team row that came out of an ESPN payload, EXCEPT the
#: ``espn_id`` itself — its write stays at the call site so the #2693 espn_id
#: write census keeps seeing it where it has always been.
#:
#: Module-level rather than a closure so a test can call it. A clear whose only
#: witness is a source scan is a clear nobody can prove covers a field.
ESPN_SOURCED_IDENTITY_FIELDS = (
    "logo_url_small",
    "logo_url_large",
    "primary_color",
    "secondary_color",
    # Contaminated alternate_names may hold the wrong club's ESPN names.
    "alternate_names",
    # The reader-visible three (#6215): badge, record and location.
    "abbreviation",
    "current_record",
    "location",
)


def clear_espn_sourced_identity(team) -> None:
    """Drop every ESPN-sourced identity field from ``team``.

    See :data:`ESPN_SOURCED_IDENTITY_FIELDS`. Named as a list rather than eight
    statements so the set is one thing a reader and a test can both point at.
    """
    for field in ESPN_SOURCED_IDENTITY_FIELDS:
        setattr(team, field, None)


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
        """Clear all ESPN-sourced data from a team record.

        "All" was three fields short of all until #6215, and the three it
        omitted are the ones a reader actually sees. Production 2026-09-14:
        Fluminense, Grêmio, Colo Colo and 141 other clubs sit under
        ``soccer_epl`` reading ``ARS · 19-7-3 · Arsenal`` with no ESPN id, no
        logo, no colours and no alternate names — the exact fingerprint of a
        row this function cleared. It detected the bad match correctly and then
        left the badge, the record and the location behind, so the alarm was
        silenced while the lie stayed on the page.

        Every writer of these three is ESPN-sourced, checked rather than
        assumed: ``espn_helpers.upsert_team`` (all three, from the payload),
        ``admin_providers.sync_espn_teams`` (abbreviation and record, from the
        same payloads), and ``routes/user.py``'s auto-create, which copies
        ``location`` from a donor Team that got it from one of the first two.
        There is no non-ESPN source for them to lose, which is why clearing
        them here is a clear and not a deletion.
        """
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
        clear_espn_sourced_identity(team)

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
                        # #3790: "do we still owe this row a box score?", never
                        # "is this row final?". A suspended match is the one we
                        # have admitted we cannot score, so it is the last row
                        # that should be unreachable here.
                        Event.status.in_(AUTHORITY_BACKFILL_STATUSES),
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
                                # #3790, the non-calibration arm of the same
                                # question — kept identical to the arm above so
                                # the two orderings cannot disagree about WHICH
                                # rows are eligible, only about their order.
                                Event.status.in_(AUTHORITY_BACKFILL_STATUSES),
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
                    # 🔴 #3790, and this is the site that mattered most. Every
                    # other backfill needs an `espn_id` to do its job; this is
                    # the one that GOES AND GETS the espn_id. A suspended row
                    # with no anchor cannot be reached by `espn_helpers`' direct
                    # authority door either — that door opens off the espn_id —
                    # so excluding it here did not delay the fix, it removed the
                    # last path by which the row could ever be scored.
                    Event.status.in_(AUTHORITY_BACKFILL_STATUSES),
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


#: The status set the future-commence repair recalls and judges. ONE spelling,
#: because two spellings drifting is the bug that created #4114: `suspended`
#: entered the vocabulary (live/048) after the guard below was written and only
#: the guard's private copy was updated — the backend twin of #4002's iOS defect.
#: The recall query and `_is_bogus_future_settled` both read THIS name; a status
#: added here is judged, and a status not here is never touched.
FUTURE_SETTLED_STATUSES = ("completed", "closed", "suspended")

#: The statuses in which a tennis row's score is a claim about a FINISHED match,
#: and so the only ones the illegal-score withdrawal below is allowed to reach.
#:
#: MOVED to :mod:`app.utils.espn_tennis_anchor` by CERT-2958 and deliberately
#: NOT re-exported here. It began beside the withdrawal arm because that was its
#: only reader; the Odds API score writer is now a second one, so the tuple
#: belongs beside the rule it qualifies rather than inside one of the two tasks
#: that ask it. There is no module-scope import standing in for it because the
#: anchor rail pulls :mod:`app.services.espn_tennis` in behind it — the same
#: reason :func:`settled_tennis_score_is_impossible` is imported inside the
#: function that uses it, a few hundred lines down. Readers import it from the
#: anchor; the two call sites in this module do it in-function.

#: How many illegal tennis scores one 60-second pass may withdraw. The measured
#: standing population is 26 (production 2026-09-16), so the first pass clears it
#: whole and every later pass sees the arrivals alone. The cap is not throughput
#: management — it is the blast-radius bound on a rule that nulls a column, and
#: saturating it means the population is not the one this arm was measured
#: against, which is why it is logged as a finding rather than silently retried.
MAX_ILLEGAL_TENNIS_SCORES_PER_PASS = 200


def illegal_settled_tennis_score_recall():
    """The FETCH half of #2772's withdrawal — every row it could possibly act on.

    A named function rather than an inline ``select`` because a fetch and a
    judgment that disagree is the failure this arm is most exposed to, and the
    only way to prove they agree is to be able to run the fetch against a real
    Postgres on rows whose verdict is already known — see
    ``tests/integration/test_illegal_settled_tennis_score_recall_2772_pg.py``.
    The judgment itself is
    :func:`~app.utils.espn_tennis_anchor.settled_tennis_score_is_impossible`
    and it is re-applied to every row this returns; nothing is withdrawn on the
    strength of the SQL alone.

    THE RECALL READS THE SAME CONSTANT THE JUDGMENT READS
    (:data:`~app.utils.espn_tennis_anchor.COMPLETED_WINNER_SET_COUNTS`), which
    is #4114's lesson applied before it can bite: two spellings of one rule
    drift, and the half that drifts silently is always the recall, because a
    row it never returns cannot fail a test about the judgment.

    It is a selective query rather than "every settled tennis row decided in
    Python" for one measured reason: there are 720 settled tennis rows carrying
    a score and 26 of them are illegal, so the Python-side form would re-walk
    694 correct rows every 60 seconds forever. Measured on production
    2026-09-16 with ``EXPLAIN (ANALYZE)``: **116.6 ms**, 26 rows, a bitmap index
    scan on ``ix_events_sport_id`` — and once the standing population is cleared
    the same query returns nothing for the same cost.
    """
    from app.utils.espn_tennis_anchor import (
        COMPLETED_WINNER_SET_COUNTS,
        TENNIS_STATUSES_CLAIMING_A_RESULT,
    )

    return (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.like("tennis%"),
            Event.status.in_(TENNIS_STATUSES_CLAIMING_A_RESULT),
            Event.home_score.isnot(None),
            Event.away_score.isnot(None),
            ~and_(
                func.greatest(Event.home_score, Event.away_score).in_(
                    COMPLETED_WINNER_SET_COUNTS
                ),
                Event.home_score != Event.away_score,
            ),
        )
        # A capped SELECT with no ORDER BY hands back a different page every
        # pass, so a saturated one would be unreproducible exactly when it
        # matters. Ordered by the primary key rather than by age because the cap
        # is 200 against a measured 26: at one page a minute no plausible
        # backlog survives long enough for an age order to matter, and
        # determinism is the whole benefit on offer.
        .order_by(Event.id)
        .limit(MAX_ILLEGAL_TENNIS_SCORES_PER_PASS)
    )


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

    ``suspended`` IS IN THIS SET (#4114). It was not, for the same reason the
    iOS half of #4002 broke: ``suspended`` was added to the status vocabulary
    by live/048 *after* this guard was written, and every reader that spelled
    the settled set for itself kept the two-value copy. Nothing here re-derived
    it, so a suspended row with a future kickoff had no repair at all — Ohio
    State @ Texas (416569) sat ``suspended`` with a 2026-09-12 kickoff, four
    days out, because it was suspended legitimately while carrying a WRONG past
    commence_time and the later ESPN correction moved the clock forward without
    re-evaluating the status. Neither suspend-writer can produce this state
    directly: ``backfill_winners.py`` requires ``commence_time < NOW() - 2
    days`` and the ``live → suspended`` arm below requires a past commence and
    ``status='live'``. The state is only reachable by a commence_time REWRITE,
    which is exactly the cross-merge recurrence this guard already exists for.

    ``suspended`` is non-terminal, so un-suspending is strictly safer than
    un-settling: the ``suspended → live`` arm below already flips these rows
    back on their own, but only within ``SUSPENDED_RESUME_WINDOW`` of a PAST
    commence — it looks backwards and can never reach a future-kickoff row.
    The two arms are disjoint by construction (past vs ``now + 1h``).
    """
    if status not in FUTURE_SETTLED_STATUSES:
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
      30 min. Non-terminal, deliberately — see below. Since #3946 the duration
      is ``wall_clock_bound_hours``, not the sport maximum flat: a row NOTHING
      has ever reported on — no score, no period, no authority anchor, no play
      snapshot ever — cannot be the long five-setter the tennis maximum was
      widened for, so it does not inherit the widening.
    - suspended → live: a source that reports on the game is captured again.
    - suspended → retired: nothing can EVER select the row again — no provider
      id of any kind, and past the resume window by a margin. Off by default and
      budgeted per pass; see :data:`UNREACHABLE_SUSPENDED_BUDGET_KEY` and
      :func:`~app.utils.event_completion.suspended_row_is_unreachable`.

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
    from app.utils.event_completion import (
        UNOBSERVED_MAX_HOURS,
        commence_time_is_a_reported_start,
    )
    # #5324: the authority's "not started" reaches this zero-API-call task
    # through the row, so honouring it costs an import and no query.
    from app.utils.espn_helpers import authority_not_started_holds

    stats = {"scheduled_to_live": 0, "live_to_suspended": 0, "suspended_to_live": 0}
    # Declared out here because it is RELEASED out here — after the session
    # block, which is where the transaction commits (`get_task_session` commits
    # on a clean exit). Releasing inside the block would clear the fence while
    # the retirement it is fencing is still uncommitted (CERT-2757).
    unreachable_inflight_token: Optional[str] = None

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

        # #5324 / CERT-2777: A CLOCK DOES NOT OVERRULE THE AUTHORITY.
        #
        # The second hold, and the reason the first one is not enough. ESPN's
        # live sync demotes an anchored row to `scheduled` when the authority
        # positively reports the game has NOT begun — and this loop, sixty
        # seconds later on the same realtime beat, would select that row
        # (`scheduled`, `commence_time <= now`) and promote it straight back.
        # The two beats would then trade the row between them indefinitely and
        # the reader would keep seeing `LIVE 0 0` on a game nobody has started.
        #
        # `commence_time` is not corrected here, and deliberately: we do not
        # know the new start time — only that the old one has passed without a
        # start — and writing a start nobody reported is the manufacture
        # `commence_time_is_a_reported_start` exists to refuse one field over.
        # The row keeps its stand-in and stops driving state off it, exactly as
        # that predicate's own docstring puts it.
        #
        # The hold ends on evidence, not on a timeout: any anchored ESPN pass
        # that is not "not started" clears the marker, and positive play
        # (a non-zero score, a period, a clock) overrules it inside the
        # predicate even before the clearing pass lands. Its TTL is only the
        # backstop for a dead poller. Zero extra queries — the marker rides the
        # JSONB already loaded on the row.
        stats["held_authority_not_started"] = 0

        # #8755: A START THE ONLY SOURCE HAS WITHDRAWN IS NOT A START.
        #
        # The third hold. An odds_api start is a reported start — until the Odds
        # API drops the event from a feed it is still publishing. Liberty @ Lynx
        # (15318133) was last listed 46h before its made-up 00:30Z start, was
        # promoted at it, and read LIVE with no score under a two-day-old line
        # while ESPN had the game on Sunday. One read for the candidates that
        # could be held (odds_api, no authority id, no play), none otherwise.
        stats["held_withdrawn_listing"] = 0
        from app.utils.espn_helpers import play_evidence
        from app.utils.event_completion import (
            ODDS_API_COMMENCE_SOURCE,
            ODDS_API_LISTING_SIGHTINGS_SQL,
            WITHDRAWN_LISTING_GAP,
            odds_api_listing_withdrawn,
            row_carries_an_authority_id,
        )

        listing_candidates = [
            event.id
            for event in started_events
            if event.commence_time_source == ODDS_API_COMMENCE_SOURCE
            and not row_carries_an_authority_id(event.espn_id, event.statpal_fixture_id)
            and not play_evidence(
                event.home_score, event.away_score, event.period, event.game_clock
            )
        ]
        listing_sightings: dict[int, tuple] = {}
        if listing_candidates:
            from sqlalchemy import text as _sql_text

            sighting_rows = (await session.execute(
                _sql_text(ODDS_API_LISTING_SIGHTINGS_SQL),
                {
                    "event_ids": listing_candidates,
                    "stale_before": now - WITHDRAWN_LISTING_GAP,
                    "siblings_from": now - timedelta(hours=24),
                    "siblings_to": now + timedelta(days=7),
                },
            )).all()
            listing_sightings = {
                r.listing_event_id: (r.listing_last_seen, r.sport_last_seen)
                for r in sighting_rows
            }

        for event in started_events:
            if not commence_time_is_a_reported_start(event.commence_time_source):
                stats["held_derived_start"] += 1
                continue
            if authority_not_started_holds(
                event.win_probability_sources,
                now,
                home_score=event.home_score,
                away_score=event.away_score,
                period=event.period,
                game_clock=event.game_clock,
            ):
                stats["held_authority_not_started"] += 1
                continue
            if event.id in listing_sightings and odds_api_listing_withdrawn(
                event.commence_time_source,
                event.espn_id,
                event.statpal_fixture_id,
                play_evidence(
                    event.home_score, event.away_score, event.period, event.game_clock
                ),
                *listing_sightings[event.id],
            ):
                stats["held_withdrawn_listing"] += 1
                continue
            event.status = "live"
            stats["scheduled_to_live"] += 1

        # --- live → suspended, ON THE VENUE'S WORD (rung 2 of §R) ---
        #
        # The rung `EVENT-GRAPH-DOCTRINE` §R declared on 2026-09-02 and left
        # unwired. "Only an authority post or a venue settlement ends a match"
        # is what the log line at the bottom of the next arm has been saying for
        # nineteen days, and only the first half of it was ever true here.
        #
        # THE DIFFERENCE FROM THE ARM BELOW IS THE TRIGGER, NOT THE WRITE. This
        # one has no clock. A settlement is a positive statement of record, so
        # it needs no elapsed time to become evidence — and the rows it serves
        # are exactly the ones a clock cannot reach in time, because their
        # stored kickoff is a Kalshi `close_time` (gotcha #14) that lands AFTER
        # the match. MEASURED, production 2026-09-21 22:40Z:
        # `/events/15316500` (Manzano v Pieri) badged **LIVE with a 20-second
        # refresh countdown**, hero **"No price"**, and a dead-flat 99% line
        # drawn from 2:30 PM to **3:38 PM** — the read minute — on a match
        # Kalshi settled at 1:40 PM. 67 minutes past a stored kickoff, against a
        # 3.0h unobserved tennis bound: the staleness arm could not have touched
        # it for another two hours, and #920's live edge grows the flat segment
        # for every one of those minutes.
        #
        # WHAT IT DOES NOT DO, listed because each omission was a choice:
        #
        #   * It does not write `completed_at`. The venue settles a MARKET, and
        #     a settlement clock is a market clock: on 20 of the 25 rows
        #     measured that evening the settlement instant lands BEFORE our own
        #     `commence_time`, so spending it as a game-end time would break the
        #     `completed_at >= commence_time` invariant (gotcha #46) on most of
        #     the population and hand the sentinel a matching-layer P1 that is
        #     really a clock-provenance bug. NULL says what is true: the match
        #     is over and nothing told us when.
        #   * It does not grade the blend. That is the write CERT-752 removed
        #     from the arm below, and its defect survives the change of
        #     evidence: the grade was taken from `home_score`/`away_score`, and
        #     these rows carry NULL scores, not results.
        #   * It does not reach rows that are already `suspended`. 2,683 of them
        #     carry a resolved market today; that is a repair over history with
        #     its own blast radius, and this is a producer change — the same
        #     line live/048 drew in the other direction.
        #
        # Why `suspended` rather than `closed`, measured rather than asserted:
        # see `SUSPEND_ON_VENUE_SETTLEMENT_SQL`.
        from sqlalchemy import text as _sql_text

        from app.utils.event_completion import (
            SUSPEND_ON_VENUE_SETTLEMENT_SQL,
            VENUE_SETTLED_GAME_MARKETS_SQL,
            venue_settlement_ends_the_match,
            winning_outcome_names_a_competitor,
        )
        from app.utils.game_market_class import classify_game_market_class

        stats["suspended_by_venue_settlement"] = 0
        # Counted, not inferred from the difference: an event whose ONLY settled
        # markets are derivatives is the near-miss this arm exists to refuse, so
        # "we looked and declined" must be distinguishable from "we never
        # looked" in the log (gotcha #53). It counts BOTH refusal shapes — the
        # derivative conjunct 1 reads in the name, and the one only conjunct 4
        # can see — so a rise here is the near-miss rate, not a fault. The
        # 2026-09-21 22:0xZ slate read 5; re-measured 2026-09-22 00:3xZ after
        # conjunct 4 landed it reads 1 of 9 candidate events (the NRFI row on
        # 15316384), the population having churned between the two reads.
        stats["held_derivative_settlement_only"] = 0
        settled_event_ids: set[int] = set()

        candidate_rows = (await session.execute(
            _sql_text(VENUE_SETTLED_GAME_MARKETS_SQL), {"now": now}
        )).all()
        settling: dict = {}
        looked_at: set = set()
        for row in candidate_rows:
            looked_at.add(row.event_id)
            if venue_settlement_ends_the_match(
                classify_game_market_class(
                    row.market_name, row.market_external_id, row.sport_key
                ),
                row.market_status,
                row.winner_source,
                winning_outcome_names_a_competitor(
                    row.winner_outcome_name, row.home_team_name, row.away_team_name
                ),
            ):
                settling.setdefault(row.event_id, row)
        stats["held_derivative_settlement_only"] = len(looked_at) - len(settling)

        if settling:
            settled_event_ids = set(settling)
            result = await session.execute(
                _sql_text(SUSPEND_ON_VENUE_SETTLEMENT_SQL),
                {"event_ids": sorted(settled_event_ids)},
            )
            # The CAS's own rowcount, never `len(settling)`: the two differ by
            # exactly the rows something with standing settled between the
            # SELECT and the UPDATE, and that difference is the thing a reader
            # of this counter would want to know about.
            written = result.rowcount or 0
            stats["suspended_by_venue_settlement"] = written
            for row in settling.values():
                # A RULING, not a receipt — the CAS may have matched fewer rows
                # than this loop names, and the line below is where that is
                # reported. A per-row "wrote it" that the write did not make
                # true is the shape of log that sends a reader hunting.
                logger.info(
                    "live/494 ruled event %s (%s vs %s) off the live board on "
                    "rung 2: the venue settled %r, its full-contest winner "
                    "market, with a %s verdict. No completed_at (a settlement "
                    "clock is a market clock, not a game-end time) and no "
                    "blend grade (the scores are NULL, not a result); the "
                    "venue's own grade is what the page prints.",
                    row.event_id, row.home_team_name, row.away_team_name,
                    row.market_name, row.winner_source,
                )
            if written != len(settling):
                logger.info(
                    "live/494 rung 2 ruled %d events off the live board and "
                    "the compare-and-set wrote %d: the difference is rows "
                    "something with standing settled between the read and the "
                    "write, and their verdict stands.",
                    len(settling), written,
                )

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
        #
        # #3946: the floor has to know about BOTH bounds. `UNOBSERVED_MAX_HOURS`
        # narrows the wall clock for a row nothing has ever reported on, and
        # soccer's 2.5 is below the shortest sport maximum (3.0) — so a floor
        # taken from `SPORT_MAX_DURATIONS` alone would never fetch the rows the
        # narrower bound exists for, and the whole rule would read as correct
        # while suspending nothing. Queue 067's lesson, one function over: a
        # guard is not wired by being correct.
        min_max_hours = min(
            min(SPORT_MAX_DURATIONS.values()), min(UNOBSERVED_MAX_HOURS.values())
        )

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

        from app.models import FuturesMarket
        from app.utils.event_completion import (
            EVENT_SUSPENDED,
            LAST_POST_COMMENCE_SNAPSHOT_SQL,
            ODDS_API_COMMENCE_SOURCE,
            UNREACHABLE_SUSPENDED_MARGIN,
            UNREACHABLE_SUSPENDED_TERMINAL,
            event_has_never_been_observed,
            game_may_still_be_running,
            suspended_row_is_unreachable,
            wall_clock_bound_hours,
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
        # Counted separately from `live_to_suspended` so the narrower bound can
        # never hide inside the total it contributes to: "how many did the
        # unobserved rule reach today" is a question the log must answer.
        stats["suspended_unobserved"] = 0

        for event in live_events:
            # A row rung 2 already took off the board is not a stale live row.
            # It lands in the same state, so double-handling it would not
            # corrupt anything — it would MISCOUNT, attributing to a wall clock
            # a transition a settlement made, and `live_to_suspended` is the
            # number that says how often we are guessing (gotcha #5: a silent
            # dependence on flush ordering is not a design).
            if event.id in settled_event_ids:
                continue
            sport_key = event.sport.key if event.sport else ""
            max_hours = SPORT_MAX_DURATIONS.get("default", 4.0)
            for prefix, duration in SPORT_MAX_DURATIONS.items():
                if prefix != "default" and sport_key.startswith(prefix):
                    max_hours = duration
                    break

            # #3946. A sport maximum is sized by the LONGEST format the sport
            # has — tennis is 6.0 for a Slam five-setter — and that widening is
            # what protects a long match the still-running guard cannot tell
            # apart from a finished one. A row nothing has ever reported on
            # cannot be that match, so it does not inherit the widening.
            never_observed = event_has_never_been_observed(
                event.home_score,
                event.away_score,
                event.period,
                event.espn_id,
                event.statpal_fixture_id,
                last_snaps.get(event.id),
                sport_key,
            )
            bound_hours = wall_clock_bound_hours(sport_key, max_hours, never_observed)

            hours_since_start = (now - event.commence_time).total_seconds() / 3600
            if hours_since_start > bound_hours + 0.5:
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
                if never_observed:
                    stats["suspended_unobserved"] += 1
                logger.info(
                    "live/048 suspended event %s (%s vs %s): %.1fh since start "
                    "exceeds the %.1fh %s bound (sport maximum %.1fh, "
                    "unobserved=%s) and no play-reporting source has been "
                    "captured. Not closed, not graded — only an authority post "
                    "or a venue settlement ends a match.",
                    event.id, event.home_team_name, event.away_team_name,
                    hours_since_start, bound_hours, sport_key or "default",
                    max_hours, never_observed,
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

        # --- suspended → retired (the door that was never there) ---
        #
        # #5532/#5130. The arm above is the ONLY writer that re-selects a
        # suspended row, and it looks back exactly SUSPENDED_RESUME_WINDOW. Past
        # that window a row with no provider id has no writer left anywhere in
        # the tree — the full enumeration, and the measurement, are in
        # `suspended_row_is_unreachable`. So `suspended` stopped being the
        # non-terminal state this file argues it is and became the quietest
        # possible terminal: one that still says "paused" to every reader that
        # buckets it, two years after the fixture.
        #
        # THE FLOOR IS DERIVED, NOT RESTATED. A margin on top of the very window
        # the arm above uses, computed from that constant, so the two can never
        # drift into a gap where a row is unreachable by one rule and still
        # resumable by the other.
        #
        # #6347 WIDENED THE POPULATION, SO THE FLOOR HAD TO GROW WITH IT — and
        # it is a named function so a test can call the real one instead of
        # keeping a copy of the formula. See `unreachable_suspended_floor`.
        unreachable_floor = unreachable_suspended_floor()
        stats["unreachable_suspended_retired"] = 0
        (
            stats["unreachable_suspended_budget"],
            unreachable_inflight_token,
        ) = _latch_unreachable_suspended_budget()

        if stats["unreachable_suspended_budget"] > 0:
            # THE ANCHOR-ACQUISITION EXCLUSION, and it is the one channel that
            # does not need an id (see the predicate's docstring). The SAME
            # `ESPN_SPORT_MAPPING` keys `_backfill_espn_ids` resolves to sport
            # ids, read the same way — not a copied list — so a sport added to
            # ESPN coverage starts protecting rows here on the same deploy.
            # MEASURED 2026-09-12: 111 of 10,704 rows are held by this.
            espn_covered_ids = [
                r[0] for r in (await session.execute(
                    select(Sport.id).where(
                        Sport.key.in_(list(ESPN_SPORT_MAPPING.keys()))
                    )
                )).all()
            ]
            # FAIL CLOSED ON AN EMPTY ALLOWLIST. `notin_([])` is TRUE in SQL, so
            # an empty list does not exclude ESPN sports — it stops excluding
            # anything, and the Python test `sport_id in []` agrees with it, so
            # both halves of the guard would say "retire" in unison. 26 mapped
            # keys resolving to zero sport rows is a broken read, never a real
            # state; the arm declines the pass and says so.
            if not espn_covered_ids:
                stats["unreachable_suspended_budget"] = 0
                logger.warning(
                    "#5532 unreachable-suspended arm skipped: ESPN_SPORT_MAPPING "
                    "(%d keys) resolved to no sport ids, so the anchor-"
                    "acquisition exclusion cannot be applied.",
                    len(ESPN_SPORT_MAPPING),
                )
            # THE RESTORE RAIL IS A GATE, NOT A LOG. No backup table, no writes
            # — the arm cannot retire a row it would be unable to give back
            # (D51). One `to_regclass` per pass, and only while the budget is
            # set, so the off state still costs nothing.
            backup_present = (await session.execute(
                _sql_text("SELECT to_regclass(:t) IS NOT NULL"),
                {"t": f"public.{UNREACHABLE_SUSPENDED_BACKUP_TABLE}"},
            )).scalar()
            if not backup_present:
                stats["unreachable_suspended_budget"] = 0
                logger.warning(
                    "#5532 unreachable-suspended arm skipped: backup table %s "
                    "does not exist, so a retirement could not be undone. Run "
                    "scripts/unreachable_suspended_door.py --create-backup.",
                    UNREACHABLE_SUSPENDED_BACKUP_TABLE,
                )
        else:
            espn_covered_ids = []

        if stats["unreachable_suspended_budget"] > 0:
            # The SELECT is the cheap SCREEN; `suspended_row_is_unreachable` is
            # the VERDICT, and it is re-asked on every row the screen returns.
            # Deliberately not one query doing both: the predicate carries the
            # score/`completed_at` refusals, and a rule that only ever exists as
            # a WHERE clause is a rule no test can put a counter-example to.
            # Oldest first — this drains a backlog and serves a flow at once, and
            # newest-first starves the tail (gotcha #41). The floor is the other
            # half of that bound: the population is not expiring, so a floor plus
            # oldest-first is the whole ordering question here.
            #
            # #6347 — THE SCREEN ADMITS A SECOND CLASS, AND THE MARKET TEST IS
            # PART OF THE SCREEN BECAUSE THE PREDICATE CANNOT GO AND LOOK. An
            # `odds_api` row's remaining doors are `polymarket` and
            # `kalshi_resolution_sweep`, both of which admit `suspended`
            # explicitly and both of which reach a row only through a market
            # hanging off it. That is a JOIN, not a column, so the screen asks
            # it and hands the answer to the verdict as `market_anchored`.
            # Measured: 150 of the 711 `odds_api` rows carry such a market and
            # are refused here.
            market_anchored_exists = (
                select(FuturesMarket.id)
                .where(FuturesMarket.event_id == Event.id)
                .exists()
            )
            unreachable_result = await session.execute(
                select(Event)
                .where(
                    Event.status == EVENT_SUSPENDED,
                    # #6927: the market test is a CONJUNCT of the whole screen,
                    # not a member of the second arm. Nested inside the `and_`
                    # it was asked only of rows whose `external_id` was present,
                    # so a row with no `external_id` walked past the one rule
                    # that was there to stop it. 7,360 of the 13,595 rows this
                    # arm retired since 09-13 carried markets, and every one
                    # came through the unguarded arm.
                    or_(
                        Event.external_id.is_(None),
                        Event.commence_time_source == ODDS_API_COMMENCE_SOURCE,
                    ),
                    ~market_anchored_exists,
                    Event.espn_id.is_(None),
                    Event.statpal_fixture_id.is_(None),
                    Event.home_score.is_(None),
                    Event.away_score.is_(None),
                    Event.completed_at.is_(None),
                    Event.sport_id.notin_(espn_covered_ids),
                    Event.commence_time < now - unreachable_floor,
                )
                .order_by(Event.commence_time.asc())
                .limit(stats["unreachable_suspended_budget"])
            )
            for event in unreachable_result.scalars().all():
                if not suspended_row_is_unreachable(
                    event.status,
                    event.commence_time,
                    event.external_id,
                    event.espn_id,
                    event.statpal_fixture_id,
                    event.home_score,
                    event.away_score,
                    event.completed_at,
                    event.sport_id in espn_covered_ids,
                    now,
                    unreachable_floor,
                    commence_time_source=event.commence_time_source,
                    # The screen already excluded market-anchored rows, so this
                    # is the second asking of the same question — deliberately,
                    # per the comment above the SELECT: the verdict never trusts
                    # the WHERE clause to have carried a rule for it.
                    #
                    # 🔴 THAT SENTENCE WAS FALSE FOR HALF THE POPULATION UNTIL
                    # #6927, and this is the exact shape of comment that lets a
                    # gap live. The screen excluded market-anchored rows only
                    # on its `external_id`-present arm; the verdict's own market
                    # test was nested in the same place, so BOTH askings were
                    # inside the same branch and the "second asking" was no
                    # independent check at all. Two copies of one rule do not
                    # make a belt and braces if they hang from the same hook.
                    # Both are unconditional now.
                    market_anchored=await _row_has_market_anchor(
                        session, event.id
                    ),
                ):
                    continue
                # BACKUP FIRST, IN THE SAME TRANSACTION. If this insert raises,
                # the status write never happens — which is the ordering D51
                # asks for, stated as code rather than as a runbook step.
                await session.execute(
                    _sql_text(
                        f"INSERT INTO {UNREACHABLE_SUSPENDED_BACKUP_TABLE} "
                        "(event_id, previous_status, commence_time, retired_at) "
                        "VALUES (:id, :prev, :commence, NOW()) "
                        "ON CONFLICT (event_id) DO NOTHING"
                    ),
                    {
                        "id": event.id,
                        "prev": event.status,
                        "commence": event.commence_time,
                    },
                )
                event.status = UNREACHABLE_SUSPENDED_TERMINAL
                stats["unreachable_suspended_retired"] += 1
                logger.info(
                    "#5532 retired event %s (%s vs %s) suspended→%s: no "
                    "external_id, espn_id or statpal_fixture_id, %.0fh past its "
                    "own start and %.0fh past the resume window, no score and no "
                    "completed_at. Nothing can reach this row again.",
                    event.id, event.home_team_name, event.away_team_name,
                    UNREACHABLE_SUSPENDED_TERMINAL,
                    (now - event.commence_time).total_seconds() / 3600,
                    (now - event.commence_time - SUSPENDED_RESUME_WINDOW)
                    .total_seconds() / 3600,
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
        # Recall reads the SAME constant the judgment reads (#4114) — this is
        # only the fetch; `_is_bogus_future_settled` below is the decision.
        future_settled_result = await session.execute(
            select(Event).where(
                Event.status.in_(FUTURE_SETTLED_STATUSES),
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

        # --- Repair: a SETTLED TENNIS row holding a score no completed match
        #     could end on → withdraw the SCORE, keep the settlement (#2772) ---
        #
        # 26 rows on production say a tennis match finished 0-0, 1-0, 1-1 or 0-1
        # — `Iga Swiatek 0 - 0 Elena Rybakina` sits in `/api/events/search
        # ?q=Swiatek` among seven correctly-scored neighbours. A settled 0-0 is
        # worse than a blank: a blank says "we don't know", a 0-0 says "we know,
        # and it was nil-all".
        #
        # 🔴 WHAT THE READER LOSES, SAID HERE RATHER THAN DISCOVERED LATER. The
        # event hero's settled treatment asks its authorities in order and rung
        # 1 is `home_score > away_score` (`frontend/lib/eventOutcome.ts`, #2443),
        # so on the 11 rows carrying `1-0`/`0-1` this withdrawal takes the WON
        # badge with the number. `/events/15187830` today reads "Zhang 1 —
        # Ostapenko 0, FINAL, WON, Zhang 100%" on a page that says in its own
        # words "the scoreboard reports sets"; after this it falls through to
        # rung 2 (the tournament container) or to a bare Final. That is
        # deliberate and it is not a new judgement: `authority_score` already
        # REFUSES to write a decided `1-0`, because ESPN awards an abandoned set
        # to nobody and the count can name the LOSER as ahead — five of the six
        # retirements on the 2026-09-03 board. A verdict derived from a count
        # the authority will not state is a verdict we cannot stand behind, and
        # the inverted-winner defect (gotcha #21) is the one this trade buys off.
        #
        # RESIDUAL, NOT FIXED HERE: `backfill_winners` grades moneyline markets
        # off the same column and skips only TIES, so those 11 rows have already
        # written 289 `is_winner` grades from a frozen partial score (measured
        # 2026-09-16 over 9 rows carrying markets). This arm stops the class
        # recurring; it does not un-grade what is written. Recorded on #2772.
        #
        # THE SCORE IS WITHDRAWN AND THE SETTLEMENT IS NOT, which is the one
        # decision in this arm that could have gone the other way. The two
        # repairs above un-settle, and both may: one is bounded to the last 12
        # hours, the other to rows dated in the FUTURE — in each case the match
        # has not been played and "scheduled" is the truth. These have. The
        # oldest is 43 days old and every one of them finished weeks ago, so
        # sending them back to `scheduled` would replace a wrong score with a
        # wrong STATE, and the state is the louder lie (a match five weeks past
        # reading "upcoming" on the reader's shelf). What we actually lack is
        # the score, and the honest rendering of a score we lack is no score.
        #
        # NOT SCOPED TO THE UNANCHORED ROWS even though all 26 are unanchored.
        # The invariant is a property of the SCORE, not of how the row was
        # written, and keying on `espn_id IS NULL` would be keying on today's
        # cause — the same mistake lane1b/287 names: key on the invariant, not
        # on the clear. An anchored row cannot reach this state today because
        # `authority_score` refuses first; if one ever does, it is the same lie.
        # Imported here rather than at module scope for the same reason
        # `_settle_authority_stragglers` does it: this module reaches the tennis
        # anchor rail from inside functions only, and the rail pulls the ESPN
        # tennis service in behind it.
        from app.utils.espn_tennis_anchor import settled_tennis_score_is_impossible

        stats["withdrew_illegal_tennis_score"] = 0
        _illegal_tennis = await session.execute(illegal_settled_tennis_score_recall())
        _illegal_rows = _illegal_tennis.scalars().all()
        for event in _illegal_rows:
            if not settled_tennis_score_is_impossible(
                home_score=event.home_score, away_score=event.away_score
            ):
                continue
            logger.info(
                "#2772 withdrawing an illegal settled tennis score: event %s "
                "(%s vs %s) is %s holding %s-%s, which no completed tennis "
                "match could end on. Score cleared; status and completed_at "
                "left alone — the match finished, we just cannot say how.",
                event.id, event.home_team_name, event.away_team_name,
                event.status, event.home_score, event.away_score,
            )
            event.home_score = None
            event.away_score = None
            stats["withdrew_illegal_tennis_score"] += 1
        if len(_illegal_rows) >= MAX_ILLEGAL_TENNIS_SCORES_PER_PASS:
            logger.warning(
                "#2772 illegal-tennis-score withdrawal SATURATED its per-pass "
                "cap of %d. The measured standing population was 26; a full "
                "page means either a backlog this arm has never seen or a "
                "writer producing them faster than one a minute.",
                MAX_ILLEGAL_TENNIS_SCORES_PER_PASS,
            )

        # `held_derived_start` is in the trigger and in the message: a guard that
        # declines silently reads as "there was nothing to do", and this one
        # holds ~40 rows a night on its own. Same reason `detect_and_close_stale_
        # events` logs its three held_* counters beside its closed count.
        if (stats["scheduled_to_live"] > 0 or stats["live_to_suspended"] > 0
                or stats["suspended_to_live"] > 0
                or stats["repaired_bogus_completed"] > 0
                or stats["unsettled_future_commence"] > 0
                or stats["held_derived_start"] > 0
                or stats["held_withdrawn_listing"] > 0
                or stats["withdrew_illegal_tennis_score"] > 0
                or stats["unreachable_suspended_retired"] > 0):
            logger.info(
                "Status transitions: %d scheduled→live, %d live→suspended, "
                "%d suspended→live, %d repaired, %d un-settled-future-commence, "
                "%d illegal tennis scores withdrawn, "
                "%d held (derived start), %d held (withdrawn listing), "
                "%d held (still running), "
                "%d suspended→%s (unreachable, budget %d)",
                stats["scheduled_to_live"], stats["live_to_suspended"],
                stats["suspended_to_live"],
                stats["repaired_bogus_completed"],
                stats["unsettled_future_commence"],
                stats["withdrew_illegal_tennis_score"],
                stats["held_derived_start"],
                stats["held_withdrawn_listing"],
                stats["held_still_running"],
                stats["unreachable_suspended_retired"],
                UNREACHABLE_SUSPENDED_TERMINAL,
                stats["unreachable_suspended_budget"],
            )

    # OUTSIDE THE BLOCK ON PURPOSE: the `async with` above is what commits, so
    # this is the first line at which any retirement this pass wrote is durable
    # and a restore may safely act (CERT-2757). An exception skips it and the
    # marker's expiry cleans up — which is the right direction, because an
    # exception also rolled the retirement back.
    _release_unreachable_suspended_inflight(unreachable_inflight_token)
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


async def _revive_retired_future_starts_impl() -> dict:
    """Give back a #5532-retired row whose start has moved into the future (#7260).

    WHAT A READER SEES WITHOUT THIS. 135 upcoming games are absent from the site,
    the NHL's whole opening week among them, because the only row we hold for
    each is ``voided`` — which every list surface excludes by allowlist and the
    by-id read hides. ``/search?q=maple leafs`` renders the question "Predators
    vs. Maple Leafs — Maple Leafs 53% — Oct 6" and the game behind it has no
    page. We show the question and hide the game.

    Measured on production 2026-09-20 14:29Z: 163 rows are ``voided`` with a
    future start (114 ``soccer_other``, 42 ``icehockey_other``, 7
    ``basketball_other``), up from 75 the day before, and all 163 were retired
    by the #5532 arm.

    RE-MEASURED 14:46Z WITH THE SHIPPED PREDICATE — this exact recall (the
    backup-table join and the ``+ RETIRED_REVIVAL_TOLERANCE`` cutoff) and the
    family screen below, `2177692c9718a4a4`:

        candidates                                    93
          ... refused, a surviving row holds it       27   all `soccer_other`
          ... REVIVED                                 66   42 NHL, 8 WNBA, 16 soccer

    THE POPULATION DRAINS AS WELL AS ACCRUES, and the drain is the reason this
    is a ten-minute beat and not a daily one. 163 became 93 in the seventeen
    minutes between those two reads — Saturday's 15:30Z kickoff slot passing —
    and a row whose start passes while it is still ``voided`` is not deferred,
    it is LOST: the game was never on the site and never will be.

    THE VOID WAS CORRECT WHEN IT FIRED and this task does not second-guess it;
    ``retired_row_start_moved_into_future`` carries that argument in full, along
    with why a guard on the retire decision is inert (``future_dated`` at
    retirement is 0 across all 13,588 retirements) and why the scope is the
    backup table's id list rather than the retirement predicate (2,544 unrelated
    ``voided`` rows match that predicate).

    NOT AN ARM OF ``_transition_event_statuses_impl``, though its siblings there
    are the same shape of repair. That task is the 60s ``realtime`` beat and
    every arm in it is an O(small) single-table select; this one joins the backup
    table and then asks a per-row twin screen, and the population it serves moves
    on the timescale of SCHEDULE CORRECTIONS — hours, not seconds. Running it
    1,440 times a day to do nothing 1,439 of them would be paying a realtime
    budget for a background job. Its own beat also keeps it out of that
    function's select sequence, which its tests pin positionally.
    """
    from sqlalchemy import text as _sql_text

    from app.utils.event_completion import (
        RETIRED_REVIVAL_TOLERANCE,
        UNREACHABLE_SUSPENDED_TERMINAL,
        retired_row_start_moved_into_future,
    )

    stats = {
        "candidates": 0,
        "screened": 0,
        "revived": 0,
        "refused_surviving_twin": 0,
        "screen_budget_exhausted": False,
        "backup_table_present": False,
    }

    async with get_task_session() as session:
        now = datetime.now(timezone.utc)

        # THE JOIN IS THE SCOPE AND THE TABLE'S ABSENCE IS A NO-OP, NOT AN ERROR.
        # No backup table ⇒ this arm never retired anything ⇒ there is nothing to
        # give back. But the JOIN would RAISE rather than return empty, so the
        # existence check comes first — the same `to_regclass` gate the
        # retirement arm puts ahead of its own write, for the same reason.
        stats["backup_table_present"] = bool(
            (await session.execute(
                _sql_text("SELECT to_regclass(:t) IS NOT NULL"),
                {"t": f"public.{UNREACHABLE_SUSPENDED_BACKUP_TABLE}"},
            )).scalar()
        )
        if not stats["backup_table_present"]:
            logger.info(
                "#7260 revival skipped: %s does not exist, so this arm has "
                "retired nothing to give back.",
                UNREACHABLE_SUSPENDED_BACKUP_TABLE,
            )
            return stats

        # Oldest first: the soonest kickoff is the one a reader is most likely to
        # be looking for tonight, and draining in arrival order starves the tail
        # (gotcha #41). The population is not expiring — a future-dated row only
        # becomes more urgent as its start approaches — so oldest-first is the
        # whole ordering question here.
        #
        # 🔴 THE LIMIT IS THE SCREEN BUDGET, NOT THE WRITE CAP, AND THE SWAP IS
        # THE FIX. Under the write cap this recall returned the same 25 rows on
        # every pass for ever, because a row refused by the twin screen stays
        # `voided` and so stays in the recall — oldest-first then guarantees the
        # refused prefix is re-read instead of the tail, rather than protecting
        # the tail as the comment above intends. The write cap now bounds the
        # loop below; this bounds what the loop may look at.
        candidate_ids = (await session.execute(
            _sql_text(
                "SELECT e.id FROM events e JOIN "
                f"{UNREACHABLE_SUSPENDED_BACKUP_TABLE} b ON b.event_id = e.id "
                "WHERE e.status = :terminal AND e.commence_time > :cutoff "
                "ORDER BY e.commence_time ASC LIMIT :cap"
            ),
            {
                "terminal": UNREACHABLE_SUSPENDED_TERMINAL,
                "cutoff": now + RETIRED_REVIVAL_TOLERANCE,
                "cap": UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS,
            },
        )).scalars().all()
        stats["candidates"] = len(candidate_ids)

        for event_id in candidate_ids:
            # The write cap, spent only on rows this pass actually gives back.
            # Checked at the TOP so a pass that reaches it stops screening too:
            # the remaining candidates are the next pass's head, and screening
            # them here would pay their cost twice and report a `screened` count
            # that overstates what the budget bought.
            if stats["revived"] >= UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS:
                break
            stats["screened"] += 1
            event = await session.get(Event, event_id)
            if event is None:
                continue
            # The twin screen is ASKED PER ROW and it is a JOIN, not a column, so
            # the recall cannot carry it — the same reason `market_anchored` is
            # handed to the retirement verdict rather than left in its WHERE
            # clause. Measured 2026-09-20 14:46Z under the shipped family
            # screen: 27 of the 93 candidates have a survivor and every one is
            # `soccer_other`; all 42 NHL and all 8 WNBA rows are orphans, so the
            # marquee population this ship exists for carries no twin risk.
            #
            # 19 of those 27 are refusals the FIRST presentation would not have
            # made (CERT-3173), because their survivor sits under a canonical
            # league key. `15306885` — Villarreal CF v Levante UD, `soccer_other`
            # — has FOUR scheduled `soccer_spain_la_liga` rows at its own kickoff.
            # Reviving it would have published a fifth card for one match.
            has_twin = await _row_has_surviving_counterpart(session, event)
            if not retired_row_start_moved_into_future(
                event.status,
                event.commence_time,
                now,
                retired_by_the_arm=True,
                has_surviving_counterpart=has_twin,
            ):
                if has_twin:
                    stats["refused_surviving_twin"] += 1
                continue
            event.status = "scheduled"
            stats["revived"] += 1
            logger.info(
                "#7260 revived event %s (%s vs %s) %s→scheduled: retired by the "
                "#5532 arm, start has since moved to %s (%.0fh from now) and no "
                "surviving row holds this fixture.",
                event.id, event.home_team_name, event.away_team_name,
                UNREACHABLE_SUSPENDED_TERMINAL,
                event.commence_time,
                (event.commence_time - now).total_seconds() / 3600,
            )

        # "I found no work" and "I never got to the work" are different answers
        # and the arm used to give the same one for both — which is why this
        # starved in silence for a day while `revived: 0` read as a drained
        # population. A pass that fills its screen budget and still writes
        # nothing is reporting that the refused prefix has outgrown the budget.
        if (
            stats["candidates"] >= UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS
            and stats["revived"] == 0
        ):
            stats["screen_budget_exhausted"] = True
            logger.warning(
                "#7260 revival screened its whole budget of %s candidates and "
                "revived none (%s refused for a surviving twin). The refused "
                "prefix has outgrown "
                "UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS, so rows "
                "behind it are no longer being reached — raise it.",
                UNREACHABLE_SUSPENDED_REVIVE_SCREEN_MAX_PER_PASS,
                stats["refused_surviving_twin"],
            )

    # The pair's other half, in its own transaction (#7594). Run AFTER the
    # revival rather than before it so a pass reads as one story in the log:
    # what went back on the schedule, then what came off it. The two cannot
    # fight over a row — the revival only ever selects `voided` rows and the
    # take-back never selects one.
    stats.update(await _take_back_revived_twins_impl())
    return stats


async def _take_back_revived_twins_impl() -> dict:
    """Take back a revived row a reader can now see twice (#7594).

    WHAT A READER SEES WITHOUT THIS. ``/search?q=hurricanes`` on production,
    2026-09-21 04:1xZ, two adjacent cards for one game:

        15302884  OTHER HOCKEY  Hurricanes / Panthers   "No result reported"
        15312312  NHL           Panthers / Hurricanes   "Sep 20 FINAL 6-3"

    The same game contradicting itself about whether it has been played. Three
    NHL fixtures and one WNBA fixture are in that shape tonight
    (``15302881`` Kraken/Flames, ``15302882`` Utah/Avalanche, ``15302884``
    Hurricanes/Panthers, ``15306880`` Portland Fire/LA Sparks).

    🔴 THE REVIVAL SCREEN IS ASKED ONCE. THIS IS THE ARM THAT ASKS IT AGAIN.
    :func:`_revive_retired_future_starts_impl` refuses a revival while a
    surviving row holds the fixture, and since #7594 it asks in both
    orientations — but that verdict is a fact about the instant of revival. A
    row legitimately revived on Monday as the only card for Friday's game
    becomes a twin the moment a canonical is minted on Thursday, and until now
    nothing re-examined it. The one-shot repair that cleaned up after the
    orientation-blind screen could only reach rows still AHEAD of their kickoff,
    because past kickoff it had no way to say which row was the keeper.

    🔴 AND NOTHING ELSE WOULD EVER CLEAN THESE. Measured 2026-09-21: all four
    carry markets (4, 5, 6 and 11 rows in ``futures_markets``), so
    :func:`~app.utils.event_completion.suspended_row_is_unreachable` refuses
    them on ``market_anchored`` and the #5532 retirement arm will never take
    them — correctly, by its own rule. They are permanent until this arm exists.

    THE POPULATION IS THE LEDGER MINUS WHAT THE ARM RETIRED, measured the same
    minute: 13,503 ``voided`` (invisible, not ours), 48 ``scheduled`` still
    ahead of their own kickoff, 10 ``suspended`` and 3 ``live`` past it. Of the
    13 reachable-and-past-kickoff rows the shipped screen finds a counterpart
    for 4, and in all 4 the counterpart carries the result while the subject
    carries none. The other 9 are orphans and are kept.

    🔴 THE SUBJECT'S STATUS IS NOT ``scheduled``, AND THAT IS WHY THE RECALL
    CANNOT BE THE ONE-SHOT'S WITH ITS CLOCK FLIPPED. ``15302884`` was revived
    ``voided → scheduled`` and then drifted to ``suspended`` when its kickoff
    passed with no data. A recall keyed on ``status = 'scheduled'`` selects none
    of the four. So the SQL narrows on one thing — not the terminal this arm
    writes — and :func:`~app.utils.event_completion.is_retired_event_status`
    catches the ``merged`` half in Python, where the rule already lives
    (:data:`~app.utils.event_completion.RETIRED_STATUSES` is documented as a
    membership set that is never spent on an ``IN``).

    ORDERED BY DISTANCE FROM NOW, WHICH IS THE ONLY ORDERING THAT CANNOT STARVE
    (gotcha #41). This population does not expire and it does not fully drain:
    a row the screen refuses stays in it forever, so both a plain oldest-first
    and a plain newest-first eventually fill the head with permanent refusals
    and starve the end where the harm is. Absolute distance from the present
    sorts the rows a reader is actually looking at — tonight's results, tonight's
    fixtures — to the front from BOTH directions, and parks the undecidable tail
    at the back where it belongs. The cap is then a blast-radius bound rather
    than a throttle.

    THE RESTORE RAIL IS A GATE, NOT A LOG — the #5532 arm's rule, and this arm
    earns it for the same reason: it writes a terminal, so it may not write one
    it could not give back. No bank table, no writes, and the arm says so once
    per pass in the log.
    """
    from sqlalchemy import text as _sql_text

    from app.utils.event_completion import (
        UNREACHABLE_SUSPENDED_TERMINAL,
        is_retired_event_status,
        revived_twin_may_be_taken_back,
        row_carries_a_result,
        row_carries_an_authority_id,
    )

    stats = {
        "takeback_candidates": 0,
        "taken_back": 0,
        "takeback_kept_orphan": 0,
        "takeback_kept_subject_evidenced": 0,
        "takeback_kept_a_different_game": 0,
        "takeback_kept_no_evidenced_counterpart": 0,
        "takeback_unscreenable": 0,
        "takeback_lost_race": 0,
        "takeback_bank_present": False,
    }

    async with get_task_session() as session:
        for table, why in (
            (
                UNREACHABLE_SUSPENDED_BACKUP_TABLE,
                "this arm revived nothing, so there is nothing to take back",
            ),
            (
                REVIVED_TWIN_TAKEBACK_BANK_TABLE,
                "a take-back could not be undone, so none is written "
                "(run scripts/repair_7594_revoid_published_reversed_twins.py "
                "--backup once to create it)",
            ),
        ):
            if not (await session.execute(
                _sql_text("SELECT to_regclass(:t) IS NOT NULL"),
                {"t": f"public.{table}"},
            )).scalar():
                logger.warning(
                    "#7594 take-back skipped: %s does not exist, so %s.",
                    table, why,
                )
                return stats
        stats["takeback_bank_present"] = True

        # SCREEN IN SQL, VERDICT IN PYTHON. The only thing this excludes is the
        # terminal the arm itself writes — 13,503 of the 13,566 ledger rows,
        # which is what makes the recall affordable. Every other test belongs to
        # `revived_twin_may_be_taken_back`, where a test can put a
        # counter-example to it.
        candidate_ids = (await session.execute(
            _sql_text(
                "SELECT e.id FROM events e JOIN "
                f"{UNREACHABLE_SUSPENDED_BACKUP_TABLE} b ON b.event_id = e.id "
                "WHERE e.status <> :terminal "
                "ORDER BY abs(extract(epoch FROM (e.commence_time - now()))) "
                "ASC, e.id ASC LIMIT :cap"
            ),
            {
                "terminal": UNREACHABLE_SUSPENDED_TERMINAL,
                "cap": REVIVED_TWIN_TAKEBACK_MAX_PER_PASS,
            },
        )).scalars().all()

        for event_id in candidate_ids:
            event = await session.get(Event, event_id)
            if event is None or is_retired_event_status(event.status):
                continue
            stats["takeback_candidates"] += 1

            survivors = await _surviving_counterpart_rows(session, event)
            if survivors is None:
                # 🔴 THE SENTINEL READS THE OTHER WAY ROUND HERE, AND CONFLATING
                # THE TWO WOULD BE THE WHOLE DEFECT. `None` means the screen
                # could not be run at all, and `_counterpart_screen_refuses`
                # folds it in with "a survivor exists" because for the REVIVAL
                # both answers mean "do not publish". For a take-back they are
                # opposites: a survivor licenses a write, and "we could not tell"
                # must never be spent as one. So this arm reads the three
                # answers itself rather than through that boolean.
                stats["takeback_unscreenable"] += 1
                continue
            if not survivors:
                stats["takeback_kept_orphan"] += 1
                continue

            # Read once and spent twice — on the verdict and on the counter that
            # explains it — so the log can say WHICH refusal fired without the
            # caller re-deriving a rule that lives in the predicate.
            subject_has_result = row_carries_a_result(
                event.home_score, event.away_score, event.completed_at
            )
            subject_has_anchor = row_carries_an_authority_id(
                event.espn_id, event.statpal_fixture_id
            )
            # 🔴 THE SCREEN NAMES CANDIDATES; THIS NAMES THE SAME GAME
            # (CERT-3213). The screen's ±30h window is sized for a refusal, and
            # 640 measured pairs of provably-distinct real games sit inside it.
            # So the destructive write is licensed only by a counterpart that
            # starts within an hour of this row — and the take-back is bound to
            # THOSE ids, not to every id the screen returned.
            same_fixture, evidenced = await _counterparts_that_are_the_same_game(
                session, [row_id for row_id, _st in survivors], event.commence_time
            )
            if not revived_twin_may_be_taken_back(
                retired_by_the_arm=True,
                has_surviving_counterpart=True,
                subject_carries_result=subject_has_result,
                subject_carries_authority_id=subject_has_anchor,
                a_survivor_proves_the_same_fixture=bool(same_fixture),
                a_survivor_carries_evidence=bool(evidenced),
            ):
                if subject_has_result or subject_has_anchor:
                    stats["takeback_kept_subject_evidenced"] += 1
                elif not same_fixture:
                    stats["takeback_kept_a_different_game"] += 1
                else:
                    stats["takeback_kept_no_evidenced_counterpart"] += 1
                continue

            proven = [pair for pair in survivors if pair[0] in set(same_fixture)]
            if await _take_back_one_revived_twin(session, event, proven):
                stats["taken_back"] += 1
            else:
                # A lost compare-and-swap is not retried in-pass. The beat fires
                # every ten minutes and re-screens from scratch, so the retry is
                # the next pass reading a database that has settled — rather
                # than this one fighting a writer that is still mid-move. The
                # one-shot repair retries because it gets one invocation.
                stats["takeback_lost_race"] += 1

    return stats


async def _counterparts_that_are_the_same_game(session, ids, subject_commence):
    """Of these candidates, which are the same GAME, and which of those hold
    evidence? Returns ``(same_fixture_ids, evidenced_ids)``. (#7594, CERT-3213)

    Both halves of the keeper question the screen cannot answer. It returns
    ``(id, status)`` because that is what the take-back's compare-and-swap binds
    to, and widening its contract would change a function two shipped callers
    already depend on — so this is one indexed read by primary key instead.

    🔴 ``evidenced`` IS A SUBSET OF ``same_fixture``, NOT AN INDEPENDENT LIST.
    An evidenced row that is a DIFFERENT game — the first leg of a doubleheader,
    finished, 6h earlier — is exactly the input CERT-3213 falsified the arm on.
    Computing the two separately and asking the predicate for "some survivor is
    the same game AND some survivor is evidenced" would let those two conditions
    be satisfied by two different rows, which is the same defect wearing a test.
    """
    from app.utils.event_completion import (
        row_carries_a_result,
        row_carries_an_authority_id,
        starts_prove_the_same_fixture,
    )

    if not ids:
        return [], []
    rows = (await session.execute(
        select(
            Event.id,
            Event.commence_time,
            Event.home_score,
            Event.away_score,
            Event.completed_at,
            Event.espn_id,
            Event.statpal_fixture_id,
        ).where(Event.id.in_(list(ids)))
    )).all()
    same_fixture = [
        row
        for row in rows
        if starts_prove_the_same_fixture(subject_commence, row.commence_time)
    ]
    return (
        [row.id for row in same_fixture],
        [
            row.id
            for row in same_fixture
            if row_carries_a_result(
                row.home_score, row.away_score, row.completed_at
            )
            or row_carries_an_authority_id(row.espn_id, row.statpal_fixture_id)
        ],
    )


async def _take_back_revived_twin_bank(session, event_id, before) -> None:
    """Record the status this take-back swapped FROM, so it can be given back."""
    from sqlalchemy import text as _sql_text

    from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL

    await session.execute(
        _sql_text(
            f"INSERT INTO {REVIVED_TWIN_TAKEBACK_BANK_TABLE} "
            "(event_id, status_before, status_after, taken_at) "
            "VALUES (:i, :b, :a, now()) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {"i": event_id, "b": before, "a": UNREACHABLE_SUSPENDED_TERMINAL},
    )


async def _own_the_counterparts(session, ids) -> list[tuple[int, str]]:
    """Take row ownership of the counterparts, then read their statuses. (#7594)

    Returns the ``(id, status)`` pairs that are STILL reachable, read under the
    lock and therefore true until this transaction ends.

    ``FOR UPDATE`` is the one read that BLOCKS, which is the whole point:
    whatever the interleaving, the competing writer either committed before
    this read (it is seen), or is mid-transaction (this read waits for it and
    then sees it), or arrives afterwards (it waits for the take-back's own
    transaction and re-evaluates against a database in which the subject is
    already retired). ``ORDER BY id`` is the deadlock discipline.

    ITS OWN FUNCTION SO THE STRAWMAN CAN REMOVE IT. A two-session test that
    proves the lock works is only worth its runtime beside one that removes the
    lock and REQUIRES the fixture to empty — otherwise a rig whose second
    session silently did nothing reads as a pass.
    """
    from app.utils.event_completion import is_retired_event_status

    locked = (await session.execute(
        select(Event.id, Event.status)
        .where(Event.id.in_(list(ids)))
        .order_by(Event.id)
        .with_for_update()
    )).all()
    return [
        (row_id, status)
        for row_id, status in locked
        if not is_retired_event_status(status)
    ]


async def _take_back_one_revived_twin(session, event, survivors) -> bool:
    """Swap this row to the terminal, or lose the race and write nothing. (#7594)

    🔴 THE SWAP IS ON BOTH ROWS AT ONCE, AND THAT IS CERT-3199's AND CERT-3204's
    FINDING CARRIED FORWARD INTO THE BEAT. A screen is a fact about the instant
    it was read and the write is a different instant: if the canonical retires
    in between, a compare-and-swap on this row's own status still matches, both
    rows commit retired, and the fixture has ZERO reader-visible cards — the
    #7260 harm produced by its own repair. So the take-back is conditioned, in
    one statement, on one of the rows the screen just accepted still being in
    the status it accepted it in.

    🔴 AND THE COUNTERPARTS ARE OWNED FIRST, BECAUSE THE ``EXISTS`` ALONE CANNOT
    SEE A WRITER THAT COMMITS AFTER THE SNAPSHOT (CERT-3204). Under READ
    COMMITTED the subquery is evaluated against the statement's snapshot and
    MVCC readers never block, so a concurrent retirement of the canonical is
    invisible to it. ``FOR UPDATE`` is the one read that blocks; ``ORDER BY id``
    is the deadlock discipline. ``with_for_update()`` rather than raw SQL so the
    sqlite rail the race tests drive ignores the clause instead of failing to
    parse it.

    THE RULE DOES NOT MOVE INTO SQL. ``_surviving_counterpart_rows`` still
    decides in Python which rows are the same fixture and hands back the ids it
    accepted; the WHERE clause re-checks only their liveness.

    THE BANK IS WRITTEN AFTER THE SWAP AND ONLY ON A WIN, which is the ordering
    the one-shot repair arrived at the hard way: both are in one transaction, so
    banking first buys nothing for durability, and it costs correctness — a bank
    row asserting a ``status_after`` we never wrote would let the undo drag a
    row back on a claim nobody earned.
    """
    from sqlalchemy import text as _sql_text

    from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL

    live_counterparts = await _own_the_counterparts(
        session, [row_id for row_id, _st in survivors]
    )
    if not live_counterparts:
        # The counterpart went away under us, so this row is now the only card
        # for the fixture. Voiding it would delete the game from the site.
        return False

    before = event.status
    params = {
        "after": UNREACHABLE_SUSPENDED_TERMINAL,
        "i": event.id,
        "before": before,
    }
    bound = []
    for n, (other_id, other_status) in enumerate(live_counterparts):
        bound.append(f"(c.id = :c{n}_id AND c.status = :c{n}_status)")
        params[f"c{n}_id"] = other_id
        params[f"c{n}_status"] = other_status

    moved = (await session.execute(
        _sql_text(
            "UPDATE events SET status = :after "
            "WHERE id = :i AND status = :before "
            "AND EXISTS (SELECT 1 FROM events c WHERE "
            + " OR ".join(bound)
            + ")"
        ),
        params,
    )).rowcount
    if not moved:
        return False

    await _take_back_revived_twin_bank(session, event.id, before)
    logger.info(
        "#7594 took back event %s (%s vs %s) %s→%s: revived by the #7260 arm, "
        "no score, no completed_at and no authority id, while %s holds this "
        "fixture with a result or an anchor.",
        event.id, event.home_team_name, event.away_team_name, before,
        UNREACHABLE_SUSPENDED_TERMINAL,
        ", ".join(str(row_id) for row_id, _st in live_counterparts),
    )
    return True


def _wp_backfill_snap_time(commence, index: int, total: int, sport_key, now):
    """Synthetic captured_at for backfill WP point ``index`` of ``total``.

    Spreads points evenly across a realistic game window [commence, commence +
    sport_duration], hard-clamped to ``now`` so a synthetic timeline can NEVER
    extend past the real game end / current time (the #922 stale-tail bug).

    #8514: NO LONGER USED BY THE BACKFILL, which stamps each point at its play's
    evidenced ``wallclock`` instead. An evenly spread time is still invented —
    15318166's backfill ran 27 min after the final, so its window was 180 min
    for a 153-min game, the line trailed every source and nine rows landed after
    the final reading 84–91%. Kept only for the finished #2486 repair script.
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


#: #8514: how far back the backfill re-reads a finished game whose ESPN rows
#: are all pre-#8514 estimates, and how many such games one run takes. About
#: ten games a day were backfilled before the fix (measured 2026-09-25 over the
#: 14 days before), so 40 per six-hourly run drains a month in about two days
#: and cannot crowd out the first-time arm, which keeps its own limit.
_WP_RESTAMP_WINDOW_DAYS = 30
_WP_RESTAMP_LIMIT = 40


def _wp_backfill_evidenced_time(point: dict, now: datetime) -> Optional[datetime]:
    """The instant a backfilled ESPN point belongs at, or None (#8514).

    That is the ``wallclock`` of the play the point follows, as
    ``ESPNAPIService.get_win_probability`` joined it. A point without one has no
    evidenced time and is not stored: a guessed time is what #8514 removed, and
    one missing point costs the chart nothing a wrong one would not cost more.
    A wallclock in the future is not evidence of anything.
    """
    at = point.get("wallclock")
    if not isinstance(at, datetime):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if at > now:
        return None
    return at


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

    #8514 — EVERY POINT IS STAMPED AT ITS PLAY'S WALLCLOCK. Each ESPN point names
    a play, and the play carries the instant it happened; the point is stored
    there, with ``time_basis = "play_wallclock"``, or not at all. Before this the
    points were spread evenly from kick-off to the earlier of a sport-length
    guess and "now", so a game backfilled 27 minutes after its final drew a line
    that trailed every other source and carried readings after the final. The
    newest-first run also re-reads, in a separate arm with its own limit, a
    finished game from the last ``_WP_RESTAMP_WINDOW_DAYS`` whose ESPN rows are
    all such estimates; the route then serves the evidenced rows in their place
    (`winprob_evidence.drop_superseded_estimates`). Nothing is deleted, and a
    point already stored at the same instant is not stored twice — the table has
    no unique key, so ``ON CONFLICT DO NOTHING`` alone never deduplicated.
    """
    import asyncio as _asyncio
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.services.espn_api import ESPNAPIService
    from app.models.models import WinProbSnapshot
    from app.utils.winprob_evidence import PLAY_WALLCLOCK_BASIS

    stats = {
        "events_checked": 0, "events_backfilled": 0,
        "snapshots_created": 0, "api_empty": 0, "already_covered": 0,
        # #8514
        "restamp_candidates": 0, "points_unevidenced": 0,
        "points_already_stored": 0,
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
                    WHERE e.status IN (""" + AUTHORITY_BACKFILL_STATUS_SQL + """)
                      AND e.espn_id IS NOT NULL
                      AND snap_cnt.cnt < 10
                    ORDER BY e.commence_time """ + ("ASC" if oldest_first else "DESC") + """
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            events = list(result.fetchall())

            # #8514: the re-read arm. Its own query and limit, because the arm
            # above is permanently full of games ESPN publishes no series for
            # (NHL and soccer have none) — anything ordered behind it is never
            # reached. The lateral's window test references only the outer row,
            # so Postgres runs it as a one-time filter and reads no snapshot rows
            # for a game outside the window (EXPLAIN on production 2026-09-25).
            if not oldest_first:
                restamp = await session.execute(
                    text("""
                        SELECT e.id, e.espn_id, e.commence_time,
                               s.key AS sport_key,
                               spread.n AS espn_snap_count
                        FROM events e
                        JOIN sports s ON s.id = e.sport_id
                        JOIN LATERAL (
                            SELECT COUNT(*) AS n,
                                   COALESCE(bool_or(
                                       wps.game_state->>'backfilled' = 'true'
                                       AND wps.game_state ? 'seconds_left'
                                       AND NOT wps.game_state ? 'time_basis'
                                   ), false) AS has_estimate,
                                   COALESCE(bool_or(
                                       wps.game_state->>'time_basis' = :basis
                                   ), false) AS has_evidenced
                            FROM win_prob_snapshots wps
                            WHERE wps.event_id = e.id AND wps.source = 'espn'
                              AND e.commence_time >= :window_start
                        ) spread ON true
                        WHERE e.status IN (""" + AUTHORITY_BACKFILL_STATUS_SQL + """)
                          AND e.espn_id IS NOT NULL
                          AND e.commence_time >= :window_start
                          AND spread.has_estimate
                          AND NOT spread.has_evidenced
                        ORDER BY e.commence_time DESC
                        LIMIT :limit
                    """),
                    {
                        "basis": PLAY_WALLCLOCK_BASIS,
                        "window_start": datetime.now(timezone.utc)
                        - timedelta(days=_WP_RESTAMP_WINDOW_DAYS),
                        "limit": _WP_RESTAMP_LIMIT,
                    },
                )
                restamp_rows = list(restamp.fetchall())
                stats["restamp_candidates"] = len(restamp_rows)
                seen_ids = {row.id for row in restamp_rows}
                events = restamp_rows + [
                    row for row in events if row.id not in seen_ids
                ]

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
                    _wp_now = datetime.now(timezone.utc)
                    stored_at = {
                        row[0] for row in (await session.execute(
                            text(
                                "SELECT captured_at FROM win_prob_snapshots "
                                "WHERE event_id = :e AND source = 'espn'"
                            ),
                            {"e": event_row.id},
                        )).fetchall()
                    }

                    for point in wp_data:
                        home_wp = point.get("home_win_probability")
                        if home_wp is None:
                            continue

                        snap_time = _wp_backfill_evidenced_time(point, _wp_now)
                        if snap_time is None:
                            stats["points_unevidenced"] += 1
                            continue
                        if snap_time in stored_at:
                            stats["points_already_stored"] += 1
                            continue
                        stored_at.add(snap_time)

                        stmt = pg_insert(WinProbSnapshot).values(
                            event_id=event_row.id,
                            source="espn",
                            home_win_probability=round(home_wp, 4),
                            away_win_probability=round(1.0 - home_wp, 4),
                            captured_at=snap_time,
                            game_state={
                                "seconds_left": point.get("seconds_left"),
                                "backfilled": True,
                                "time_basis": PLAY_WALLCLOCK_BASIS,
                                "play_id": point.get("play_id"),
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
        "ESPN win prob backfill: %d checked, %d backfilled, %d snapshots "
        "(%d re-read candidates, %d points without a play time, %d already stored)",
        stats["events_checked"], stats["events_backfilled"],
        stats["snapshots_created"], stats["restamp_candidates"],
        stats["points_unevidenced"], stats["points_already_stored"],
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
        result_refuted_by_format,
        sets_to_win,
        state_contradiction,
    )
    from app.utils.espn_id_stamp import STAMPED, stamp_espn_id_if_unheld
    from app.utils.live_state_write import write_row_if_unmoved
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
        # live/203: rows whose #5324 authority marker this pass wrote — stamped
        # when ESPN says the match has not begun, cleared when it reports play.
        # Eagerly zeroed like its siblings, so the key APPEARING at all on the
        # first beat after a release is the deployment proof for this ship.
        "authority_hold_writes": 0,
        # lane1/064: the score half. `score_writes` counts rows the authority
        # moved; `score_blanks_filled` is the SHIP — a settled row that printed
        # nothing and now prints the result; `score_corrections` is a row whose
        # existing score the authority overruled. `score_refused` is keyed by
        # reason, because "no score" is four different findings.
        "score_writes": 0,
        "score_blanks_filled": 0,
        "score_corrections": 0,
        "score_refused": {},
        # live/224 (#6056): score writes dropped because another producer moved
        # this row's score between the decision and the write. Eagerly zeroed
        # like its siblings, so a 0 is a reading and not an absence (gotcha #53)
        # — and so the key APPEARING on the first beat after a release is the
        # deployment proof for this half of the ship.
        "score_write_lost_race": 0,
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

                # THE REFUSAL IS COUNTED WHERE IT IS MADE (#5987). Silently
                # declining the authority is how a rail stops working without
                # anyone noticing: a board that starts publishing short finals
                # for a real reason must show up as a number, not as rows that
                # quietly never settle.
                if result_refuted_by_format(competition):
                    stats["decided_refused"] = stats.get("decided_refused", 0) + 1
                    logger.warning(
                        "Tennis FINAL REFUSED: event %s (%s v %s) — ESPN says %s "
                        "but the winner holds %s of the %s sets this format needs",
                        event.id, ours[0], ours[1], competition.get("status_name"),
                        next(
                            (s.get("sets_won") for s in (competition.get("sides") or [])
                             if s.get("winner")),
                            None,
                        ),
                        sets_to_win(competition),
                    )

                changes = authority_write(
                    now=now,
                    our_status=event.status,
                    our_completed_at=event.completed_at,
                    our_commence_time=event.commence_time,
                    our_commence_time_source=event.commence_time_source,
                    competition=competition,
                    our_sources=event.win_probability_sources,
                    our_home_score=event.home_score,
                    our_away_score=event.away_score,
                )
                if "status" in changes:
                    event.status = changes["status"]
                    stats["status_writes"] += 1
                if "win_probability_sources" in changes:
                    # THE HOLD THE CLOCK PROMOTER HONOURS (#5324).
                    #
                    # A WHOLE new dict, never an in-place edit: a JSONB value
                    # mutated in place is invisible to the ORM's change tracking
                    # and is silently dropped (gotcha #4) — the single most
                    # expensive way for this repair to look like it works. The
                    # helper returns a fresh object for exactly this reason, and
                    # plain attribute assignment is what this task uses for
                    # every other column, so no Core update is mixed in here
                    # (gotcha #5).
                    event.win_probability_sources = changes[
                        "win_probability_sources"
                    ]
                    stats["authority_hold_writes"] += 1
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
                    # THE PROVENANCE TRAVELS WITH THE VALUE (#5971).
                    #
                    # Without it the row holds ESPN's clock under an
                    # `odds_api` stamp, and `event_registry`'s authority rule
                    # — which reads the STAMP, not where the value came from —
                    # then lets the next Odds poll revise it back as "a
                    # provider correcting its own record". That is the
                    # ping-pong measured on the US Open men's final: 18:00 →
                    # 18:15 → 18:00 → 18:15 → 18:13:40 in seventeen minutes,
                    # which silently dropped the first twelve minutes of the
                    # match from the `Since Start` chart.
                    #
                    # Read off `changes` rather than assigned as a literal so
                    # the refusal (StatPal owns this start) can never arrive
                    # here as a stamp without a value.
                    event.commence_time_source = changes["commence_time_source"]
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
                # ═══ THE POSITION THIS DECISION IS TAKEN AT (live/224, #6056) ═══
                #
                # Captured ONCE, here, and handed to both the decision below and
                # the compare-and-write that lands it. `authority_score_write`
                # decides by comparing ESPN against exactly these two values, so
                # exactly these two are what the write must re-assert: if either
                # moved while this pass was still working, the decision was taken
                # against a row that no longer exists and the write is dropped.
                #
                # NOT re-read at the write — that is the whole point, and it is
                # asserted structurally rather than by comment, because a fresh
                # read there compares the row against itself and matches every
                # time (`test_the_cas_is_given_a_captured_position_never_a_fresh_read_6056`).
                #
                # POSITION IS DELIBERATELY NOT THE PREDICATE HERE. This pass
                # never reads or writes `period`/`game_clock`, and on a tennis
                # row both are routinely NULL — predicating on them would be a
                # compare-and-write that cannot refuse.
                _observed_home = event.home_score
                _observed_away = event.away_score

                was_blank = _observed_home is None and _observed_away is None
                score = authority_score_write(
                    ours=ours,
                    our_home_score=_observed_home,
                    our_away_score=_observed_away,
                    competition=competition,
                )
                if score["reason"] is not None:
                    stats["score_refused"][score["reason"]] = (
                        stats["score_refused"].get(score["reason"], 0) + 1
                    )
                elif score["changes"] and not await write_row_if_unmoved(
                    session,
                    event,
                    score["changes"],
                    observed={
                        "home_score": _observed_home,
                        "away_score": _observed_away,
                    },
                    what="tennis score",
                ):
                    # LOST THE RACE. Another producer wrote this row's score
                    # between the read above and this statement, so the row
                    # already holds a later observation than the one this pass
                    # is carrying. Dropping it is the correct response — the
                    # next beat is five minutes away — but a refusal nobody
                    # counts is indistinguishable from a quiet beat, which is
                    # how this whole class stayed invisible.
                    stats["score_write_lost_race"] += 1
                elif score["changes"]:
                    # BOTH NUMBERS READ BEFORE EITHER IS WRITTEN — the log below
                    # is a before/after, and `write_row_if_unmoved` has already
                    # mirrored the new values onto the instance, so `before`
                    # must come off the captured pair and not off `event`.
                    before = (_observed_home, _observed_away)
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
