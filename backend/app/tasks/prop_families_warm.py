"""Producer for the team prop-families tier (LAT-P138, #1249 follow-up).

Two tasks, and the difference between them is who decided the rebuild:

* ``_refresh_prop_families`` — ONE team, dispatched by ``routes/prop_families.py``
  under a single-flight lock after it has served the 24h mirror. A burst of
  readers behind one TTL expiry produces one rebuild rather than one per reader.
* ``_warm_prop_families`` — the BEAT. It selects the reachable team set and
  dispatches the per-team task for each one, so the mirror never lapses on a page
  a person can actually reach.

🔴 WHY THIS TIER GETS A PRODUCER AND `routes/hub.py` DELIBERATELY DOES NOT.
The hub module says, in as many words, that its stale-while-revalidate keeps
itself warm off real traffic and a beat would be a second producer racing the
route's. LAT-P137 measured that assumption on a sibling tier
(``/api/futures/categories``) and it did not hold: across 32 minutes every single
rebuild was one of the measuring session's own probes, so the mirror lapsed and
readers paid the full build. The two arguments are reconciled by SIZE, not by
preference:

* a hub rebuild was 2.7 s at its worst and there are five hubs;
* a prop-families rebuild is **2.6-16.8 s** (seven teams, first touch, production
  ``64b7a034``) and the reachable set is 82 teams.

A tier whose cold build is sixteen seconds cannot be left to hope somebody
visited in the last day. The race the hub module warns about is handled the same
way the route handles concurrent readers — this producer acquires the SAME
single-flight lock and passes the SAME owner token, so a beat pass arriving while
a reader-triggered rebuild is in flight dispatches nothing for that team.

THE REACHABLE SET, DECLARED RATHER THAN GUESSED.
Only teams with a roster are slow: the roster IS the pattern list, and cost is
linear in it (41 patterns 13.4 s, the same 10 patterns 2.2 s). Measured on
production 2026-08-30:

    9,625 teams total
      367 have a non-empty roster            <- the only ones that can be slow
    1,475 have an event in the next 14 days
       82 have BOTH                          <- warmed here

The 285 rostered teams with no near fixture keep the route's own
stale-while-revalidate, and the 9,258 rosterless teams were never slow (one
pattern, not 41). Warming all 367 unconditionally would be four times the
database work for the teams nobody is looking at this fortnight.
"""

import logging

logger = logging.getLogger(__name__)

#: How far ahead a fixture counts as "reachable". A fortnight, because that is
#: the horizon over which a team turns up in the feed, in search and on an event
#: page a person can tap through from — not a tuning knob for the warm cost.
REACHABLE_HORIZON_DAYS = 14

#: And how far BACK. A team whose game finished last night is still one tap from
#: a result card, and its prop families are exactly what a person checks after.
REACHABLE_LOOKBACK_DAYS = 1

#: Hard ceiling on one pass's fan-out. Not a target — a backstop, so a roster
#: backfill or a schedule import cannot turn one beat tick into thousands of
#: multi-second rebuilds. When it binds, the pass says so out loud (no silent
#: caps): the verdict carries `truncated` and the count that was dropped.
MAX_TEAMS_PER_PASS = 200

#: The `limit=` the warmer builds for. The route's default, and therefore the
#: only cap value a browser ever asks for; a `?limit=` reader gets its own key
#: and its own build, which is the point of `cap` being IN the key.
WARM_CAP = 400

#: Bounds one team's rebuild. Comfortably above the slowest measured cold build
#: (16.8 s, Chiefs) and well under the task's own soft_time_limit, so a wedged
#: build is reported by this timeout rather than vanishing into a SIGKILL
#: (project_celery_sigkill_untracked).
PER_TEAM_TIMEOUT_SECONDS = 60


async def _refresh_prop_families(team_id: int, cap: int, token: str | None = None) -> dict:
    """Rebuild and re-cache ONE team's prop families. Never raises.

    `token` is the refresh-lock owner token the DISPATCHER acquired: the acquire
    and the release live in different processes, so ownership travels in the
    message (#1678 finding 1). It is optional only so a message already in the
    broker at deploy time still executes — a signature that drops an argument
    rejects every in-flight message with a TypeError. Passing `None` means "I hold
    no lock", and the build still runs while that lock is left to lapse on its own
    TTL rather than being deleted by a producer that cannot prove it owns it.

    🔴 THE SESSION COMES FROM `tasks.base.get_task_session`, NEVER FROM THE ROUTE
    MODULE. `routes/prop_families.py` reaches its session through FastAPI's
    dependency, which is bound to the WEB process's event loop; a Celery worker
    that opened it would get "attached to a different loop" at runtime and no
    unit test with the session patched out could see it. LAT-P137 shipped that
    bug into a first draft on the sibling tier and caught it by reading, not by
    testing.
    """
    import asyncio

    from app.routes.prop_families import (
        build_and_cache_prop_families,
        prop_families_cache_keys,
    )
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import get_client, release_refresh_lock
    from sqlalchemy import select

    from app.models import Team

    rc = get_client()
    keys = prop_families_cache_keys(team_id, cap)
    try:
        async with get_task_session() as db:
            team = (
                await db.execute(select(Team).where(Team.id == int(team_id)))
            ).scalars().first()
            if team is None:
                # Not an error worth retrying: a team id that does not resolve is
                # a stale message, not a broken build. "Unknown" and "broken" are
                # different facts (gotcha #53).
                logger.warning("refresh_prop_families: no team %s", team_id)
                return {
                    "terminal": "complete",
                    "team_id": team_id,
                    "reason": "unknown_team",
                    "rebuilt": 0,
                }
            _payload, degraded = await asyncio.wait_for(
                build_and_cache_prop_families(team, db, cap, rc),
                timeout=PER_TEAM_TIMEOUT_SECONDS,
            )
    except Exception:
        logger.exception("refresh_prop_families: rebuild failed for team %s", team_id)
        return {"terminal": "failed", "team_id": team_id, "rebuilt": 0}
    finally:
        release_refresh_lock(rc, keys, token)

    if degraded:
        # The build ran and produced nothing storable. That is a FAILED pass, not
        # a quiet success: `build_and_cache_prop_families` deliberately does not
        # write a degraded payload, so the mirror this task exists to keep alive
        # is exactly as old as it was before.
        return {"terminal": "failed", "team_id": team_id, "rebuilt": 0, "degraded": True}
    return {"terminal": "complete", "team_id": team_id, "rebuilt": 1}


async def _warm_prop_families() -> dict:
    """Dispatch one rebuild per reachable team. Never raises.

    Returns the verdict the beat reports: how many teams the predicate selected,
    how many were dispatched, and how many were skipped because somebody else
    already held that team's refresh lock (a reader beat us to it — the correct
    outcome, not a miss).
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, or_, select

    from app.models import Event, Team
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import acquire_refresh_lock, get_client

    now = datetime.now(timezone.utc)
    rc = get_client()

    try:
        async with get_task_session() as db:
            q = (
                select(Team.id)
                .join(
                    Event,
                    or_(Event.home_team_id == Team.id, Event.away_team_id == Team.id),
                )
                .where(
                    Team.roster_players.isnot(None),
                    func.jsonb_array_length(Team.roster_players) > 0,
                    Event.commence_time
                    >= now - timedelta(days=REACHABLE_LOOKBACK_DAYS),
                    Event.commence_time
                    <= now + timedelta(days=REACHABLE_HORIZON_DAYS),
                )
                .distinct()
            )
            team_ids = [int(t) for t in (await db.execute(q)).scalars().all()]
    except Exception:
        logger.exception("warm_prop_families: could not select the reachable set")
        return {"terminal": "failed", "selected": 0, "dispatched": 0}

    selected = len(team_ids)
    truncated = max(0, selected - MAX_TEAMS_PER_PASS)
    if truncated:
        # No silent caps: a pass that covered less than it selected says which
        # number it covered and which it dropped.
        logger.warning(
            "warm_prop_families: %d teams selected, capped to %d (%d dropped)",
            selected, MAX_TEAMS_PER_PASS, truncated,
        )
    team_ids = team_ids[:MAX_TEAMS_PER_PASS]

    from app.routes.prop_families import prop_families_cache_keys

    dispatched = 0
    locked_out = 0
    for team_id in team_ids:
        keys = prop_families_cache_keys(team_id, WARM_CAP)
        token = acquire_refresh_lock(rc, keys)
        if not token:
            # A reader-triggered rebuild for this team is already in flight. This
            # is the race `routes/hub.py` warns a beat would create, closed by
            # taking the same lock the route takes.
            locked_out += 1
            continue
        try:
            from app.tasks import celery_app

            celery_app.send_task(
                "app.tasks.refresh_prop_families",
                args=[team_id, WARM_CAP, token],
                queue="background",
            )
            dispatched += 1
        except Exception:
            from app.utils.event_concept_cache import release_refresh_lock

            logger.warning(
                "warm_prop_families: dispatch failed for team %s", team_id,
                exc_info=True,
            )
            release_refresh_lock(rc, keys, token)

    # A pass that dispatched nothing while it had teams to warm is a FAILED pass.
    # `send_task` reports that the broker took the message, never that a worker
    # ran it, so this is the strongest claim this task is entitled to make — and
    # it is still stronger than "it returned" (`app/utils/task_verdict.py`).
    terminal = "complete" if (dispatched or not team_ids) else "failed"
    return {
        "terminal": terminal,
        "selected": selected,
        "dispatched": dispatched,
        "locked_out": locked_out,
        "truncated": truncated,
    }
