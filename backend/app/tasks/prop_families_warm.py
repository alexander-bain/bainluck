"""Producer for the team prop-families tier (LAT-P138, #1249 follow-up).

Two entry points, and the difference between them is who decided the rebuild:

* ``_refresh_prop_families`` — ONE team, dispatched by ``routes/prop_families.py``
  under a single-flight lock after it has served the 24h mirror. A burst of
  readers behind one TTL expiry produces one rebuild rather than one per reader.
* ``_warm_prop_families`` — the BEAT. It walks the reachable team set and rebuilds
  each one **INLINE**, so the mirror never lapses on a page a person can reach.

🔴 THE BEAT REBUILDS INLINE RATHER THAN FANNING OUT, AND THAT IS A REPO RULE, NOT
A PREFERENCE. `tests/test_celery_result_retention.py::test_no_task_dispatches_
another_task` scans every module under `app/tasks/` for `.delay(`, `.apply_async(`
and `send_task(` and fails on any of them: results are suppressed for tasks
nothing reads, and the consumer set is re-derived by AST-walking dispatch sites
under `app/routes`, `app/services` and `app/utils` ONLY — so a task that
dispatches a task can grow a result consumer that scan will never see. The first
draft of this file fanned out one message per team and the full suite caught it.

Building inline means the pass must live inside a Celery time limit, and the
slowest single build measured is 16.8 s. So the pass is BUDGETED and RESUMABLE:
it works a rotating slice of the reachable set until `PASS_BUDGET_SECONDS` is
spent, records where it stopped, and starts there next time. That is the
oldest-first-within-a-floor discipline of gotcha #41 applied to a warm list —
what matters is that no team waits longer than the mirror, not that one pass
covers everyone.

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

🔴 LAT-P158 — A FIXTURE IS THE WRONG QUESTION TO ASK ABOUT A SEASON-LONG MARKET.
The paragraph above is right that the reachable set must be declared, and wrong
about what makes a team reachable. "Has a game in the next fortnight" is a GAME
CLOCK signal, and this surface has no game clock: `routes/prop_families.py` says
so itself — *"Prop families are season-long questions ('Next Team', MVP races,
threshold ladders) whose probabilities move on the futures poll cadence, not on a
game clock"*. Gating the warm set on a fixture therefore excludes exactly the
teams whose prop markets are most alive: an OFFSEASON team with championship,
MVP and Next Team futures trading has no fixture for two months and is precisely
the page a person opens to see them.

Measured on production `767db311`, 2026-08-31, five team pages, first touch:

    oklahoma-city-thunder    13,262 ms   99 props   NO fixture -> never warmed
    golden-state-warriors    11,896 ms   84 props   NO fixture -> never warmed
    new-york-knicks           8,924 ms   76 props   NO fixture -> never warmed
    los-angeles-dodgers-mlb     251 ms    ~ props   fixture    -> warm, mirror
    detroit-tigers-mlb          272 ms    ~ props   fixture    -> warm, mirror

A 35-50x difference decided by nothing but whether the sport is in season. And
the exclusion is not a fringe: **the fifteen teams holding the most prop markets
in the entire database are all NBA, 59-99 outcomes each, and on 2026-08-31 every
one of them was outside the warm set.** Census the same day: 367 rostered, 100
fixture-reachable, and **182 rostered teams hold props with no fixture in the
window** — 96 of them holding ten or more.

So a team is reachable if it has a near fixture OR it holds enough prop markets
to make a page worth warming (`MIN_PROPS_TO_WARM`). This does NOT increase the
database work a pass does: `PASS_BUDGET_SECONDS` bounds the pass, not the
population, so a wider set changes WHICH teams a pass builds and how long a full
cycle takes — not how hard any hour hits Postgres.
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

#: The SECOND way in, for teams a fixture window cannot see (LAT-P158).
#:
#: Ten, because a family needs **two distinct entities** to be emitted at all
#: (`utils/prop_families.group_prop_families`: "Only families with >= 2 DISTINCT
#: entities are emitted — a single market is not a family"). A team holding a
#: handful of prop outcomes scattered across markets usually renders no family at
#: all, so warming it warms an empty page and spends a slot a 99-prop team needs.
#:
#: It is also what keeps the union inside `MAX_TEAMS_PER_PASS`, which is the
#: population bound the coverage contract is asserted against. Measured
#: 2026-08-31: 100 fixture-reachable + 96 prop-reachable = 196 of a 200 ceiling.
#: If that ever crosses, the pass truncates FAIRLY (rotate-then-cap, below) and
#: says so, rather than silently never warming the tail.
MIN_PROPS_TO_WARM = 10

#: Hard ceiling on how many teams one pass will consider. Not a target — a
#: backstop, so a roster backfill or a schedule import cannot turn one beat tick
#: into an unbounded walk. When it binds, the pass says so out loud (no silent
#: caps): the verdict carries `truncated` and the count that was dropped.
MAX_TEAMS_PER_PASS = 200

#: The slowest cold build this lane has measured: Chiefs, 16,797 ms, first touch
#: on production `64b7a034`. Rounded UP to whole seconds. Everything below is
#: derived from it, so re-measuring it re-derives the budget and the cadence
#: instead of leaving three literals to drift apart (#2236).
SLOWEST_MEASURED_BUILD_SECONDS = 17

#: 🔴 THE PASS IS BUDGETED, NOT COUNTED, BECAUSE THE BUILD IS NOT UNIFORM.
#: Measured first touch across seven teams: 2,627 ms (Celtics) to 16,797 ms
#: (Chiefs), driven by roster size. A pass counted in TEAMS would be 20 s on one
#: sample of the population and five minutes on another; a pass counted in
#: SECONDS is the same length whichever teams come up.
#:
#: 180 s is the smallest budget that satisfies the coverage contract with the
#: hourly beat: at the pessimistic rate of `SLOWEST_MEASURED_BUILD_SECONDS` per
#: team it clears 10 teams a pass, so a FULL `MAX_TEAMS_PER_PASS` list is covered
#: in 20 passes = 20 h, inside the 24 h mirror with four hours to spare. The
#: guard asserts that arithmetic rather than the number.
PASS_BUDGET_SECONDS = 180

#: Where the last pass stopped, so the next one does not re-warm the same head
#: while the tail never gets a turn (gotcha #34: one counter shared across a loop
#: starves whatever comes late). Plain Redis rather than the cache tier — this is
#: producer bookkeeping, not a served payload, and it must not look like one.
CURSOR_KEY = "bainluck:prop_families:warm_cursor"

#: A cursor that outlives a fortnight of fixtures is describing a team set that
#: no longer exists. Long enough to survive a deploy gap, short enough that a
#: stale position self-heals.
CURSOR_TTL_SECONDS = 86400

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


def _read_cursor(rc) -> int:
    """Where the previous pass stopped. Any unreadable value is position 0 —
    a broken cursor must degrade to "start again", never to "warm nothing"."""
    if rc is None:
        return 0
    try:
        raw = rc.get(CURSOR_KEY)
        return int(raw) if raw is not None else 0
    except Exception:
        return 0


def _write_cursor(rc, team_id: int) -> None:
    if rc is None:
        return
    try:
        rc.setex(CURSOR_KEY, CURSOR_TTL_SECONDS, str(int(team_id)))
    except Exception:
        logger.warning("warm_prop_families: cursor write failed", exc_info=True)


async def _warm_prop_families() -> dict:
    """Rebuild a budgeted slice of the reachable team set, INLINE. Never raises.

    Returns the verdict the beat reports: how many teams the predicate selected,
    how many were rebuilt, how many were skipped because a reader already held
    that team's refresh lock (the correct outcome, not a miss), and how many were
    deferred to the next pass because the budget ran out.
    """
    import asyncio
    import time
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, or_, select

    from app.models import Event, FuturesMarket, FuturesOutcome, Team
    from app.routes.prop_families import (
        _INCLUDED_STATUSES,
        build_and_cache_prop_families,
        prop_families_cache_keys,
    )
    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import (
        acquire_refresh_lock,
        get_client,
        release_refresh_lock,
    )

    now = datetime.now(timezone.utc)
    started = time.monotonic()
    rc = get_client()

    try:
        async with get_task_session() as db:
            _rostered = (
                Team.roster_players.isnot(None),
                func.jsonb_array_length(Team.roster_players) > 0,
            )

            # Way in #1: a fixture inside the window. The in-season page.
            q_fixture = (
                select(Team.id)
                .join(
                    Event,
                    or_(Event.home_team_id == Team.id, Event.away_team_id == Team.id),
                )
                .where(
                    *_rostered,
                    Event.commence_time
                    >= now - timedelta(days=REACHABLE_LOOKBACK_DAYS),
                    Event.commence_time
                    <= now + timedelta(days=REACHABLE_HORIZON_DAYS),
                )
                .distinct()
            )

            # Way in #2 (LAT-P158): enough live prop markets to be worth warming,
            # fixture or no fixture. Counted the way the route's FK branch counts
            # — non-event markets in the statuses the route actually surfaces —
            # so the warm set and the thing being warmed agree about what a prop
            # is. Anything else and the warmer selects a population the builder
            # does not serve.
            q_props = (
                select(FuturesOutcome.team_id)
                .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                .join(Team, Team.id == FuturesOutcome.team_id)
                .where(
                    *_rostered,
                    FuturesMarket.event_id.is_(None),
                    FuturesMarket.status.in_(_INCLUDED_STATUSES),
                )
                .group_by(FuturesOutcome.team_id)
                .having(func.count(FuturesOutcome.id) >= MIN_PROPS_TO_WARM)
            )

            # Ordered by id because the cursor rotation below is an id walk; the
            # union is a SET, and which teams a truncated pass drops is decided by
            # the rotation, not by the primary key (see the cap, below).
            q = (
                select(Team.id)
                .where(or_(Team.id.in_(q_fixture), Team.id.in_(q_props)))
                .order_by(Team.id)
            )
            team_ids = [int(t) for t in (await db.execute(q)).scalars().all()]
    except Exception:
        logger.exception("warm_prop_families: could not select the reachable set")
        return {"terminal": "failed", "selected": 0, "rebuilt": 0}

    selected = len(team_ids)
    truncated = max(0, selected - MAX_TEAMS_PER_PASS)
    if truncated:
        # No silent caps: a pass that covered less than it selected says which
        # number it covered and which it dropped.
        logger.warning(
            "warm_prop_families: %d teams selected, capped to %d (%d dropped)",
            selected, MAX_TEAMS_PER_PASS, truncated,
        )

    # 🔴 ROTATE FIRST, THEN CAP (LAT-P158). The cap used to be applied to the
    # id-ordered list BEFORE the rotation, which made `MAX_TEAMS_PER_PASS` a
    # permanent membership test rather than a per-pass slice: every team past
    # position 200 by primary key would be dropped by EVERY pass and never warmed
    # at all. It did not bind while the set was 100 teams; LAT-P158 widens the set
    # towards that ceiling, and a widening that starves its own tail is not a
    # widening (gotcha #34 — one counter shared across a loop starves whatever
    # comes late; here it was the same 200 ids winning every hour).
    #
    # Rotating first makes the cap mean "how many this pass does", and the cursor
    # guarantees the next pass resumes where this one stopped, so a set larger
    # than the cap is covered ACROSS passes instead of never.
    cursor = _read_cursor(rc)
    start = 0
    for index, team_id in enumerate(team_ids):
        if team_id > cursor:
            start = index
            break
    ordered = (team_ids[start:] + team_ids[:start])[:MAX_TEAMS_PER_PASS]

    rebuilt = 0
    locked_out = 0
    failed = 0
    deferred = 0
    last_done: int | None = None

    for position, team_id in enumerate(ordered):
        if time.monotonic() - started >= PASS_BUDGET_SECONDS:
            # Out of budget, not out of work. The remainder is DEFERRED and
            # counted, and the cursor already points at where to resume.
            deferred = len(ordered) - position
            break

        keys = prop_families_cache_keys(team_id, WARM_CAP)
        token = acquire_refresh_lock(rc, keys)
        if not token:
            # A reader-triggered rebuild for this team is already in flight. This
            # is the race `routes/hub.py` warns a beat would create, closed by
            # taking the same lock the route takes.
            locked_out += 1
            last_done = team_id
            continue
        try:
            async with get_task_session() as db:
                team = (
                    await db.execute(select(Team).where(Team.id == team_id))
                ).scalars().first()
                if team is None:
                    continue
                _payload, degraded = await asyncio.wait_for(
                    build_and_cache_prop_families(team, db, WARM_CAP, rc),
                    timeout=PER_TEAM_TIMEOUT_SECONDS,
                )
            if degraded:
                failed += 1
            else:
                rebuilt += 1
        except Exception:
            # One bad team must never wipe the pass (gotcha #42).
            logger.warning(
                "warm_prop_families: rebuild failed for team %s", team_id,
                exc_info=True,
            )
            failed += 1
        finally:
            release_refresh_lock(rc, keys, token)
            last_done = team_id

    if last_done is not None:
        _write_cursor(rc, last_done)

    # A pass that had teams to warm and rebuilt none of them is a FAILED pass —
    # unless every one of them was already being rebuilt by a reader, which is
    # the tier working. "It returned" is not "it worked"
    # (`app/utils/task_verdict.py`).
    if not ordered:
        terminal = "complete"
    elif rebuilt or (locked_out and not failed):
        terminal = "complete"
    else:
        terminal = "failed"
    return {
        "terminal": terminal,
        "selected": selected,
        "rebuilt": rebuilt,
        "locked_out": locked_out,
        "failed": failed,
        "deferred": deferred,
        "truncated": truncated,
        "seconds": round(time.monotonic() - started, 1),
    }
