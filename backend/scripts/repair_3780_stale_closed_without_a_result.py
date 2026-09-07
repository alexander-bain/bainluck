"""#3780 — 25 league pages stop headlining "Recent Results" over eight rows that report none.

THE SHIP. `https://bainluck.com/sport/baseball/baseball_kbo` and twenty-four
other league pages render a section headed **Recent Results** containing eight
cards, and not one of them prints a result. Measured against the serving
endpoint on 2026-09-06, `/api/leagues/baseball_kbo` returned
`8 results / 6 unreported / 8 scoreless`, and its eight "results" were the
Sep 1-2 KBO fixtures — NC Dinos v Kia Tigers, Doosan Bears v LG Twins and six
more — every one of them `status='closed'` with `home_score = away_score =
NULL`. `baseball_npb` and `tennis_atp` printed the identical shape.

This is #3748's ship arriving in full. That change moved every `suspended` row
onto the No-result rail and `unreported_games` went 0 → 6; the results rail
stayed eight-deep and result-less because a SECOND population took the vacated
slots. It was an unmasking, not a regression, and this is the rest of it.

------------------------------------------------------------------------------
WHAT THESE ROWS ARE — the producer is already fixed, the rows were never repaired
------------------------------------------------------------------------------

They are the output of the pre-CERT-752 staleness nets. Until `0ee26b71`
(live/048, 2026-09-02) `odds_polling.detect_and_close_stale_events` and
`espn_sync._transition_event_statuses_impl` both ended a match on a wall clock:
finding no admitted snapshot they wrote `status='closed'` — Final to every
client — plus a `completed_at` derived from `now()`. CERT-752 ruled that out and
`event_completion` now states the rule in as many words: *wall-clock silence is
not on the ladder at all; it is the ABSENCE of every rung, and absence cannot
end a match.* Both nets write :data:`EVENT_SUSPENDED` today.

The rule stopped the producer. Nobody swept the rows it had already produced,
and the league rail's lookback is fourteen days, so they keep arriving on the
page. The daily census makes the landing unmistakable — this is the count of
result-less `closed` rows by their own commence date, measured 2026-09-06:

    … Aug 30    516      Sep 01    519
      Aug 31    296      Sep 02    175      ← 0ee26b71 deploys
                         Sep 03      5
                         Sep 04+     0

Nothing has entered the cohort since. It is frozen, finite, and fully inside
the horizon of the surface it breaks.

------------------------------------------------------------------------------
WHY THE STATUS IS THE BUG, AND NOT THE RAIL AND NOT THE INGEST
------------------------------------------------------------------------------

Both of the obvious repairs are wrong, and both are refused by tests that
already exist:

  * **Not the rail.** "Route a scoreless `closed` row to the No-result rail" is
    a rail reading the scoreline, and
    `test_the_two_rails_are_jointly_exhaustive_3211
    ::test_no_rail_reads_the_scoreline_at_all` fails exactly that, on purpose:
    a row's rail is a function of `(status, time)` and nothing else, or a Final
    whose score has not been backfilled yet flickers between rails as the
    backfill runs.
  * **Not the ingest.** There is no score to fetch. The cohort is 49 sport keys
    led by `soccer_other`, `tennis_other` and `esports`; none carries an
    `espn_id`, none a `statpal_end_time`, none a `box_score_data`. Nothing ever
    watched these matches, which is precisely why the staleness net was the
    only thing left to speak about them.

The row's STATUS is its own statement about whether a result was reported, and
these rows carry a word the codebase has already ruled they were never entitled
to. Repair the statement.

🔴 AND IT IS NOT ONLY COSMETIC, which is the half worth arguing.
:func:`~app.utils.event_completion.authority_may_settle` admits `suspended` and
refuses `closed` — "churning `closed` into `completed` rewrites history for no
reader". So a wall clock writing the terminal word did not merely mislabel these
rows, it made them **permanently unsettleable**: if ESPN or a venue ever reports
how one of them ended, the settlement path will decline to write it. Moving them
to `suspended` reopens the door that should never have been shut.

------------------------------------------------------------------------------
THE POPULATION, MEASURED ON PRODUCTION 2026-09-06/07
------------------------------------------------------------------------------

Inside the league results rail's own fourteen-day lookback:

    8,282 rows   49 sport keys   676 with a wall-clock completed_at
    0 with a score      0 with an espn_id      0 with a statpal_end_time
    0 with a box score

And what a reader sees, simulating the real rail (top 8 by commence_time,
14-day window) across every league:

    31 leagues have at least one result-less row in their eight visible slots
    25 of them have NOTHING ELSE — 20 at 8/8, plus icehockey_liiga 7/7,
       motorsport_other 7/7, rugbyleague_nrlw 6/6, cricket_international_t20
       4/4, cricket_other 3/3

Six leagues gain real results they cannot currently show: `soccer_concacaf_
leagues_cup` has five Finals pushed off the page by three of these rows,
`aussierules_afl` four, `soccer_fa_cup` seven, `soccer_germany_dfb_pokal` five.

------------------------------------------------------------------------------
WHAT THIS REPAIR REFUSES TO TOUCH
------------------------------------------------------------------------------

Each clause of :func:`unsettle_refusal_reason` is a rung of the ladder saying
something about the match, and any one of them means a source — not a wall
clock — put this row where it is:

    a score (either side)   rung 3 reported on the game
    statpal_end_time        rung 1 watched it end; the surviving `closed` arm
                            of `detect_and_close_stale_events` writes exactly
                            this pair and is correct to
    espn_id                 the authority can still speak about this row through
                            `_backfill_box_scores`, which selects on
                            `status IN ('completed','closed')`; unsettling it
                            would take it out of that backfill's reach
    box_score_data          rung 3 again, in full

`completed` is out of scope entirely — it is the AUTHORITY's word and no
staleness net has ever written it.

⚠️ WHAT IT KNOWINGLY LEAVES. 416 of the 8,282 carry a `win_probability_sources`
blend that reads as graded. Un-grading a blend is a settlement action, it is the
settlement path's to make, and it is invisible on these rails either way (the
shared card suppresses the chips, the bar and the projection for a row with no
reported result — CERT-799). Filed, not fixed here. Likewise the tail: the same
cohort is ~73,000 rows at thirty days, which is the TEAM page's lookback rather
than the league page's. This repair is scoped to the horizon of the surface it
is fixing, which is the same "a horizon is not a gap" boundary
`app/utils/event_rails.py` already draws; widening it is a decision, not an
oversight, and `--lookback-days` is how.

------------------------------------------------------------------------------
RUNNING IT (D51 — backup first, one-command restore)
------------------------------------------------------------------------------

    python3 scripts/repair_3780_stale_closed_without_a_result.py             # dry run
    python3 scripts/repair_3780_stale_closed_without_a_result.py --backup --apply

Heroku one-off (gotcha #48 — detached, and PROJECT_PATH=backend puts scripts at
/app, so NO `cd backend`; the script must be on the DEPLOYED SLUG to run at all):

    heroku run:detached "python3 scripts/repair_3780_stale_closed_without_a_result.py --backup --apply" -a bainluck

Undo:

    heroku run:detached "python3 scripts/restore_3780_stale_closed_without_a_result.py --apply" -a bainluck
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import DateTime, String, bindparam, text  # noqa: E402

# IMPORTED, never restated. The status vocabulary and the surface's own lookback
# are both shipped constants: if `suspended` stops being the ladder's silence
# state, or the league rail changes its horizon, this script follows rather than
# repairing to a number that used to be true.
from app.routes.league_futures import RESULTS_LOOKBACK_DAYS  # noqa: E402
from app.utils.event_completion import (  # noqa: E402
    EVENT_SUSPENDED,
    SETTLED_STATUSES,
    authority_may_settle,
)

#: The terminal word a wall clock wrote and was never entitled to write.
#: `completed` is deliberately NOT in scope — see the docstring.
TARGET_STATUS = "closed"

#: The ladder's silence state, which is what these rows actually are.
UNSETTLED_STATUS = EVENT_SUSPENDED

BAK_TABLE = "bak_3780_stale_closed_status"

# Asserted at import so the repair cannot outlive its premise. If somebody makes
# `suspended` terminal, or drops `closed` from the settled vocabulary, this
# script stops importing rather than writing a word whose meaning has moved.
assert TARGET_STATUS in SETTLED_STATUSES, (
    f"{TARGET_STATUS!r} is no longer in SETTLED_STATUSES {sorted(SETTLED_STATUSES)} "
    "— it has stopped meaning Final and this repair has lost its subject"
)
assert UNSETTLED_STATUS not in SETTLED_STATUSES, (
    f"{UNSETTLED_STATUS!r} is now in SETTLED_STATUSES — writing it would assert "
    "the very result this repair exists to stop asserting"
)
assert authority_may_settle(UNSETTLED_STATUS) and not authority_may_settle(
    TARGET_STATUS
), (
    "the door this repair reopens has moved: `authority_may_settle` must admit "
    f"{UNSETTLED_STATUS!r} and refuse {TARGET_STATUS!r}"
)

#: Sanity band, measured on production 2026-09-06/07 at the default lookback. A
#: repair that finds nothing and reports success is the worst outcome there is
#: (gotcha #53 — an empty result is a response shape, not an absence), and one
#: that finds an order of magnitude more has had its premise change underneath
#: it. Only checked at the DEFAULT lookback: widening the window legitimately
#: multiplies the population, so the band would be a number about a different
#: question.
MIN_EXPECTED_POPULATION = 2_000
MAX_EXPECTED_POPULATION = 20_000

#: Pre-registered census. `--apply` refuses unless the live measurement still
#: shows zeros on every ladder rung, so this docstring's claims and the dyno's
#: result cannot drift apart unnoticed.
EXPECTED_ZEROS = ("with_score", "with_statpal_end", "with_espn_id", "with_box_score")


def horizon_floor(now: datetime, lookback_days: int = RESULTS_LOOKBACK_DAYS):
    """The oldest `commence_time` this repair will touch.

    Offset from an injected anchor, never a branch on the clock (gotcha #44), so
    the guard can sweep a matrix and the SQL and the Python predicate can be
    handed the same bound.
    """
    return now - timedelta(days=lookback_days)


def as_aware(value):
    """Coerce a commence_time to a UTC-aware datetime, or ``None``.

    Three callers hand this three different things and the planner is only
    worth having if it survives all three:

      * production (asyncpg, `DateTime(timezone=True)`) → already aware;
      * the guard's sqlite corpus → a NAIVE datetime, because sqlite has no
        timezone type and the dialect drops the offset on the way in;
      * `POST /api/admin/db-query` → an ISO **string**, which is the shape that
        makes it possible to replay this plan over production rows BEFORE any
        write instead of spending the repair's own refusals as the instrument.

    A naive value is read as UTC rather than rejected: every one of these
    columns is written in UTC, and the alternative — a `TypeError` deep inside
    a comparison — is how a pre-flight silently stops covering the real rows.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def unsettle_refusal_reason(row, *, floor) -> str | None:
    """Why this row must KEEP its Final, or ``None`` if it must lose it.

    PURE, and the single definition of the population: :data:`_TARGET_WHERE` is
    the same rule in SQL and
    `tests/test_a_result_less_row_is_never_final_3780.py` executes both over one
    corpus and fails on any disagreement. A repair whose plan and whose UPDATE
    are two independent readings of "which rows" is how a sweep quietly moves a
    row nobody adjudicated.

    ``row`` is anything with the six attributes below — an ORM `Event`, a
    `Row`, or a plain object built from a `db-query` result, which is what lets
    the plan be replayed against production BEFORE any write.
    """
    if row.status != TARGET_STATUS:
        return (
            f"status is {row.status!r}, not {TARGET_STATUS!r} — `completed` is the "
            "authority's word and no staleness net has ever written it, and "
            "anything non-terminal is not asserting a result to begin with"
        )
    if row.home_score is not None or row.away_score is not None:
        return (
            "a scoreline is present — something reported ON this game (ladder "
            "rung 3), so its Final is not a wall clock's"
        )
    if row.statpal_end_time is not None:
        return (
            "statpal_end_time is set — rung 1 watched the match and said when it "
            "ended; this is the one arm of the staleness net that may still close"
        )
    if row.espn_id is not None:
        return (
            "an ESPN id is stamped — `_backfill_box_scores` selects on "
            "`status IN ('completed','closed')`, so unsettling this row takes it "
            "out of the reach of the authority that can still score it"
        )
    if row.box_score_data is not None:
        return "a box score is present — rung 3 reported on this game in full"
    commence_time = as_aware(row.commence_time)
    if commence_time is None:
        return (
            "no commence_time — a row we cannot place on the clock is one we have "
            "no standing to move (the same rule `started_without_result` applies)"
        )
    if commence_time < as_aware(floor):
        return (
            "older than the surface's own lookback — a horizon, not a gap: it "
            "applies to a real Final exactly as it applies to this row"
        )
    return None


#: The SQL twin of :func:`unsettle_refusal_reason`. Bind-parameterised on the
#: time bound rather than spelling `now() - interval '14 days'`, for two
#: reasons: the guard executes this exact string against sqlite, and a repair
#: that reads the clock inside its own WHERE cannot be handed the same anchor
#: its plan was built on.
_TARGET_WHERE = """
       status = :closed
   AND home_score IS NULL
   AND away_score IS NULL
   AND statpal_end_time IS NULL
   AND espn_id IS NULL
   AND box_score_data IS NULL
   AND commence_time IS NOT NULL
   AND commence_time >= :floor
"""

_TARGET_IDS_SQL = f"SELECT id FROM events WHERE {_TARGET_WHERE} ORDER BY id"

#: The write itself, as ONE string two callers spend: :func:`unsettle_rows` on
#: production and the guard against a sqlite corpus. A test that retypes the
#: UPDATE proves a statement nobody runs.
#:
#: `completed_at = NULL` is not tidying. The pre-CERT-752 net stamped a
#: wall-clock game-end time in the same write as the false Final, and every one
#: of production's 2,268 `suspended` rows carries `completed_at IS NULL`; a
#: suspended row holding a game-end time is the contradiction CERT-752 was filed
#: about, wearing a different status.
_UNSETTLE_SQL = (
    "UPDATE events SET status = :suspended, completed_at = NULL "
    "WHERE id = :eid AND status = :closed"
)


def statement(sql: str):
    """`text(sql)` with the two shared binds TYPED, for every statement above.

    The types are not decoration. `:floor` is a timezone-aware datetime, and an
    untyped `text()` bind hands it straight to the driver: asyncpg would take it,
    and the guard's sqlite would render it in a format that does not compare
    against the column's own storage format — so the SQL half of the rule would
    silently select nothing and the "plan and SQL agree" test would pass over two
    empty sets. Typing the bind makes one string mean one thing on both.
    """
    return text(sql).bindparams(
        bindparam("closed", type_=String),
        bindparam("floor", type_=DateTime(timezone=True)),
    )

#: The census counts each refusal clause SEPARATELY over the `closed` rows in
#: the window, so "0 with a score" is measured on the dyno rather than quoted
#: from this file's docstring. `EXPECTED_ZEROS` then gates `--apply` on them.
_CENSUS_SQL = f"""
SELECT count(*) FILTER (WHERE {_TARGET_WHERE}) AS population,
       count(*) FILTER (WHERE {_TARGET_WHERE} AND completed_at IS NOT NULL)
           AS population_with_completed_at,
       count(*) AS closed_in_window,
       count(*) FILTER (WHERE home_score IS NOT NULL OR away_score IS NOT NULL)
           AS with_score,
       count(*) FILTER (WHERE statpal_end_time IS NOT NULL) AS with_statpal_end,
       count(*) FILTER (WHERE espn_id IS NOT NULL)          AS with_espn_id,
       count(*) FILTER (WHERE box_score_data IS NOT NULL)   AS with_box_score
  FROM events
 WHERE status = :closed
   AND commence_time IS NOT NULL
   AND commence_time >= :floor
"""

#: THE SHIP, not the population. How many of the eight slots a reader can
#: actually see are result-less, league by league — the same top-8-by-commence
#: window `league_futures.recent_results_query` renders.
_RAIL_SQL = f"""
SELECT league, count(*) AS visible, sum(no_result) AS no_result
  FROM (
        SELECT s.key AS league,
               CASE WHEN {_TARGET_WHERE} THEN 1 ELSE 0 END AS no_result,
               row_number() OVER (PARTITION BY s.key
                                  ORDER BY e.commence_time DESC) AS rn
          FROM events e
          JOIN sports s ON s.id = e.sport_id
         WHERE e.status IN ('completed', 'closed')
           AND e.commence_time >= :floor
       ) ranked
 WHERE rn <= 8
 GROUP BY league
HAVING sum(no_result) > 0
 ORDER BY sum(no_result) DESC, league
"""


def population_refusal_reason(measured: dict, *, default_window: bool) -> str | None:
    """Why the measured population must NOT be unsettled, or ``None``.

    Pure, so the gate is unit-testable without a database. The band is skipped
    on a non-default window because it is a claim about the fourteen-day one.
    """
    population = measured.get("population", 0)
    if default_window:
        if population < MIN_EXPECTED_POPULATION:
            return (
                f"population {population} is below the floor "
                f"{MIN_EXPECTED_POPULATION} — either this repair has already run, "
                "or the census it was built on no longer describes production. "
                "Re-measure before writing anything."
            )
        if population > MAX_EXPECTED_POPULATION:
            return (
                f"population {population} exceeds the ceiling "
                f"{MAX_EXPECTED_POPULATION} — the cohort is supposed to be FROZEN "
                "(nothing has entered it since 0ee26b71 deployed on 2026-09-02). "
                "A cohort that is growing means a fourth writer of `closed` on a "
                "wall clock; find it before sweeping."
            )
    for field in EXPECTED_ZEROS:
        count = measured.get(field, 0)
        if count:
            return (
                f"{count} row(s) in the window have {field} — this repair's whole "
                "licence is that NO rung of the ladder spoke about these rows, and "
                "that has stopped being true. Adjudicate them before sweeping."
            )
    return None


async def measure(session, *, floor) -> dict:
    """Census + the user-visible rail composition. Read-only."""
    params = {"closed": TARGET_STATUS, "floor": floor}
    census = (await session.execute(statement(_CENSUS_SQL), params)).one()
    rails = (await session.execute(statement(_RAIL_SQL), params)).all()
    return {
        "population": census.population,
        "population_with_completed_at": census.population_with_completed_at,
        "closed_in_window": census.closed_in_window,
        "with_score": census.with_score,
        "with_statpal_end": census.with_statpal_end,
        "with_espn_id": census.with_espn_id,
        "with_box_score": census.with_box_score,
        "leagues_with_a_result_less_row": len(rails),
        "leagues_with_no_real_result_at_all": sum(
            1 for r in rails if r.visible == r.no_result
        ),
        "worst_leagues": [
            {"league": r.league, "visible": r.visible, "no_result": r.no_result}
            for r in rails[:12]
        ],
    }


async def ensure_backup(session, *, floor) -> int:
    """Create the D51 backup table and bank the CURRENT status AND completed_at.

    Both columns, because the repair writes both: a `suspended` row carrying a
    game-end time is the `live`-plus-`completed_at` contradiction CERT-752 was
    filed about, wearing a different status. Measured 2026-09-06, all 2,268
    suspended rows on production carry `completed_at IS NULL`; this repair keeps
    that true.

    `ON CONFLICT DO NOTHING` keeps the FIRST banked pair, which is the pre-repair
    one — a re-run after a partial apply must not overwrite a banked `closed`
    with the `suspended` it just wrote.
    """
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  old_status text NOT NULL,"
            "  old_completed_at timestamptz,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = (
        await session.execute(
            statement(
                f"INSERT INTO {BAK_TABLE} (event_id, old_status, old_completed_at) "
                f"SELECT id, status, completed_at FROM events WHERE {_TARGET_WHERE} "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {"closed": TARGET_STATUS, "floor": floor},
        )
    ).rowcount or 0
    await session.commit()
    return banked


async def unsettle_rows(
    session, event_ids: list[int], *, progress_every: int = 500
) -> tuple[int, list[int]]:
    """Write `suspended` and clear `completed_at`, ONE ROW PER TRANSACTION.

    Deliberately not a batch UPDATE and deliberately without a short
    `lock_timeout`: `events` is write-hot (constant poller and backfill locks),
    and a batched or lock-impatient one-off rolls back on every row. A
    single-row UPDATE willing to WAIT for the lock succeeds. Slow is the point.

    The `AND status = :closed` in the WHERE is what makes a re-run safe and what
    makes a concurrent poller's write win: if something with standing has settled
    the row since the plan was built, this touches nothing.

    Returns ``(written, failed_ids)``. Failed ids are RETAINED rather than only
    printed: on a detached dyno whose stdout nobody reads, a printed FAILED line
    that does not reach the exit code is indistinguishable from a clean run —
    "it returned" is not "it worked" (gotcha #53).
    """
    written = 0
    failed: list[int] = []
    for index, event_id in enumerate(event_ids, start=1):
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(_UNSETTLE_SQL),
                    {
                        "suspended": UNSETTLED_STATUS,
                        "closed": TARGET_STATUS,
                        "eid": event_id,
                    },
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {event_id} after 3 attempts: {exc}")
                    failed.append(event_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(event_ids)} processed, {written} unsettled")
    return written, failed


async def run(*, backup: bool, apply: bool, lookback_days: int) -> None:
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    floor = horizon_floor(now, lookback_days)
    default_window = lookback_days == RESULTS_LOOKBACK_DAYS
    params = {"closed": TARGET_STATUS, "floor": floor}

    print(f"=== #3780 · result-less Finals, {lookback_days}-day window ===")
    print(f"horizon floor: {floor.isoformat()}")
    if not default_window:
        print(
            f"⚠️  NON-DEFAULT WINDOW (the league rail's own lookback is "
            f"{RESULTS_LOOKBACK_DAYS} days) — the population band is not applied"
        )

    async with get_task_session() as session:
        before = await measure(session, floor=floor)
        print(json.dumps(before, indent=2))

        if before["population"] == 0:
            print("\nNothing to repair — population already 0 (idempotent no-op).")
            return

        blocked = population_refusal_reason(before, default_window=default_window)
        if blocked and apply:
            print(f"\nREFUSING TO APPLY: {blocked}")
            sys.exit(1)
        if blocked:
            print(f"\nWOULD REFUSE: {blocked}")

        if backup:
            banked = await ensure_backup(session, floor=floor)
            total = (
                await session.execute(text(f"SELECT count(*) FROM {BAK_TABLE}"))
            ).scalar() or 0
            print(f"\nBACKUP: banked {banked} new row(s); {total} total in {BAK_TABLE}")

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {before['population']} rows would go "
                f"{TARGET_STATUS!r} → {UNSETTLED_STATUS!r} with completed_at cleared. "
                "Re-run with --backup --apply."
            )
            return

        if not backup:
            print("\nREFUSING: --apply requires --backup in the same run (D51)")
            sys.exit(1)

        event_ids = [
            r.id
            for r in (await session.execute(statement(_TARGET_IDS_SQL), params)).all()
        ]
        print(f"\nUNSETTLING {len(event_ids)} rows, one transaction each …")
        written, failed = await unsettle_rows(session, event_ids)

        after = await measure(session, floor=floor)
        print(f"\nCOMMITTED: {written} rows {TARGET_STATUS!r} → {UNSETTLED_STATUS!r}.")
        print(json.dumps({"before": before, "after": after}, indent=2))
        print(
            "\nUndo: python3 scripts/restore_3780_stale_closed_without_a_result.py "
            "--apply"
        )

        problems = []
        if failed:
            problems.append(
                f"{len(failed)} row(s) exhausted their retries and still claim a "
                f"Final: {failed[:20]}{' …' if len(failed) > 20 else ''}"
            )
        if after["population"]:
            problems.append(
                f"{after['population']} row(s) of the target population remain — "
                "the sweep is incomplete"
            )
        if problems:
            print("\n❌ #3780 INCOMPLETE — the repair did NOT finish:")
            for problem in problems:
                print(f"  - {problem}")
            print(
                "\nThe committed rows are durable, so re-running with "
                "--backup --apply resumes from here."
            )
            sys.exit(1)

        print(
            f"\n✅ #3780: 0 result-less Finals inside the {lookback_days}-day rail "
            f"(was {before['population']} rows across "
            f"{before['leagues_with_a_result_less_row']} leagues, "
            f"{before['leagues_with_no_real_result_at_all']} of which had nothing "
            "else in their eight visible slots)."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--backup", action="store_true", help="top up the D51 backup table"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the repair (requires --backup)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=RESULTS_LOOKBACK_DAYS,
        help=(
            "how far back to sweep. Defaults to the league results rail's own "
            f"lookback ({RESULTS_LOOKBACK_DAYS}) — the horizon of the surface "
            "this repair is for. 30 covers the team page as well, at roughly "
            "nine times the rows."
        ),
    )
    args = parser.parse_args()
    asyncio.run(
        run(backup=args.backup, apply=args.apply, lookback_days=args.lookback_days)
    )


if __name__ == "__main__":
    main()
