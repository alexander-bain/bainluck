"""#5821 — re-date the Polymarket-born rows that carry a LISTING stamp, not a kickoff.

CERT-2793 BLOCK, required repair `5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE`.

------------------------------------------------------------------------------
WHAT A READER SEES, AND THE SPECIMEN THE ISSUE NAMES
------------------------------------------------------------------------------
Searching for "Al Nassr" serves ONE AFC Champions League fixture TWICE, both
reading `live`, for a match that has not kicked off. Measured on production
2026-09-13 10:2xZ (`db-query`):

    15311503  Al Ain FC v Al Nassr Club  commence 2026-09-13 03:46:20Z  suspended
              holds Gamma container 1014622  venue_game_start 2026-09-15T16:00:00Z
    15311506  Al Ain FC v Al Nassr Club  commence 2026-09-13 03:16:17Z  suspended
              holds Gamma container 1014521  venue_game_start 2026-09-15T16:00:00Z

Two rows, thirty minutes apart, for one match kicking off two days later. The
thirty minutes are not a fixture difference — they are two INGEST instants.
Gamma's `startDate` is when the market was listed; the fixture instant is a
different field, and we already store it, per market, as
`market_metadata['venue_game_start']` (`tasks.polymarket`, read by
`prediction_market_matching.venue_game_start`).

(The endpoint is named in prose rather than written as a query URL, and that is
deliberate. `test_every_search_probing_script_declares_itself_machine_traffic`
treats the search path followed by a query separator, in ANY file under
`scripts/`, as a script addressing a search surface — one that must therefore
tag itself `x-bainluck-origin` so our own robots never vote in the warm head
(notice 39). This script sends no request of any kind. Naming the surface
without building its URL is the honest side of that line; declaring machine
traffic a script never emits would be the dishonest one. Twice, in fact: the
first rewrite still spelled the URL inside this very parenthesis and reddened
the same guard.)

------------------------------------------------------------------------------
WHY THIS IS THE REPAIR AND NOT A NEW FOLD KEY
------------------------------------------------------------------------------
`event_twin_fold.twin_fold_key` is `(sport_id, away, home, commence MINUTE)`.
The two rows above agree on sport and on both names, exactly. The ONLY thing
keeping them apart is the minute, and the minute is wrong on BOTH rows.

Correct the date from the value the venue already published and already sits in
our own database, and the pair folds through machinery that has been serving
five rails since #4100 — no new key, no widened matching rule, nothing for
ruling 048 to permit. The defect is a wrong instant, not a wrong relationship,
which is why this repair never touches a link, a market or a row's identity.
(It writes a second column, `status`, for a subset of the same rows; the section
TWO COLUMNS, NOT ONE below is why, and it is a consequence of the wrong instant
rather than a second repair riding along.)

------------------------------------------------------------------------------
SCOPE — FUTURE FIXTURES ONLY, AND THAT IS A DELIBERATE NARROWING
------------------------------------------------------------------------------
Measured on production 2026-09-13 10:3xZ. Events whose `commence_time_source`
is `polymarket` and which are linked to a Polymarket market carrying a
`venue_game_start`:

    603   events disagree with their own venue's fixture instant
    -27   AMBIGUOUS: linked markets carry >1 distinct venue instant   (refused)
    576   unambiguous
    -234  whose corrected instant is in the PAST                      (out of scope)
    342   IN SCOPE

The 234 past ones are excluded on purpose. 148 of them are `closed` and their
dates feed settlement and calibration windows; moving a settled row's clock is a
different question with a different blast radius, and the reader-visible defect
is not there. It is entirely in the not-yet-played set:

    342   rows in scope, of which 40 currently serve as `live` and 302
          as `suspended` for matches that have NOT kicked off
    0     carry a score
    0     carry `completed_at`
    0     move BACKWARDS in time (every correction is listing -> later kickoff)
    0.29d smallest correction        27.44d largest

WHAT THE READER GETS, MEASURED RATHER THAN ASSERTED: among the in-scope rows,
110 fixture groups (same sport, same two names, same corrected minute) currently
hold 230 rows between them. After the re-date those 230 rows fold to 110 cards —
**120 duplicate cards stop being served.**

------------------------------------------------------------------------------
TWO COLUMNS, NOT ONE — CERT-2797's BLOCK, AND IT WAS RIGHT
------------------------------------------------------------------------------
The first cut of this script wrote `commence_time` alone, on the argument that
`served_event_status` already downgrades a premature `live` (Q438) so the clock
was the only thing needing repair. That is true of **40** of the 342 rows and
false of the other **302**, which are `suspended` — and `enforce_live_requires_
start` passes `suspended` through VERBATIM, by design and with its reason
written down: *"this rule only ever downgrades a premature `live`, and a
suspended row makes no claim about being played"*. `suspended` is also in
`EVENT_PLAYABLE_STATUSES` and the web client buckets it with live. So 302
corrected rows would have kept reading paused-with-no-result for matches days
away, on the very rails this repair exists to fix. Required repair
`5821-FUTURE-SUSPENDED-ROWS-BECOME-SCHEDULED`.

So the write is `commence_time` AND `status`, and the status half is narrower
than the date half by construction (:func:`planned_write`):

  * only a row whose corrected instant is in the FUTURE,
  * only from `live` or `suspended` — never from a terminal state,
  * only to `scheduled`, the vocabulary's own not-started value
    (`lifecycle.EVENT_NOT_STARTED`, imported rather than spelled).

🔴 IT IS NOT A LIFECYCLE CHANGE. Teaching `served_event_status` to downgrade
`suspended` too would repair these rows AND silently re-label every genuinely
postponed future fixture on the site, which is a real and different thing for a
row to be saying. The rows here are not postponed; they were born or promoted
off a clock that was wrong. Fixing the population is right, fixing the rule is
not, and the two are easy to confuse because they produce the same page for this
population and different pages for everyone else.

------------------------------------------------------------------------------
WHAT THIS DOES NOT CLAIM
------------------------------------------------------------------------------
It is a CLEANUP, not a prevention. Nothing here stops the next Gamma listing
being written as a kickoff — that is #5862, and it is not built. So the
population regrows, and this script is idempotent and re-runnable by design (a
row whose clock already agrees with its venue instant is not in the population).

It also does not close #5821 on its own. PR #5864 stops FUTURE container
siblings becoming two rows; this collapses the ones that already are, and only
those with a venue signal. Split pairs with no `venue_game_start` on either side
are untouched and stay open.

------------------------------------------------------------------------------
WHY NOT `reconcile_anchor_schedule`
------------------------------------------------------------------------------
That rail already rewrites `commence_time` + `commence_time_source` from an
authority, with a durable undo and an attended apply, and reusing it was the
first thing considered. It cannot reach these rows: its authority is ESPN
`summary?event=<id>`, so it needs an `espn_id`, and its own compare-and-set
pins `Event.espn_id == decision.espn_id`. These rows are Polymarket-born and
anchorless. Teaching a nightly sentinel's shared code a second authority, during
launch week, to serve a one-off cleanup is a larger change with a wider blast
radius than this file. The sibling is named here so nobody has to re-derive
that.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------
`--apply` REFUSES until `--backup` has copied every in-scope row's CURRENT
`commence_time` AND `status` into `backup_5821_event_dates`, and until the
reconciliation is content-exact on BOTH: a backup that merely holds the id is
not a backup, and neither is one taken before another writer moved the row
(`5621-BACKUP-RECONCILIATION-MUST-BE-CONTENT-EXACT`, the lesson this inherits
rather than relearns).

    UNDO: python3 scripts/restore_5821_polymarket_listing_dates.py --apply

The write is a per-row compare-and-set on BOTH values the plan was made from, so
a row that moved between the read and the write is SKIPPED and reported, never
overwritten.

🔴 THE BACKUP IS ALSO THE APPLY'S RECEIPT, AND THE UNDO READS THE RECEIPT AND
NOT THE PLAN (`5821-RESTORE-ONLY-SUCCESSFUL-CAS`). A backup taken before the
write knows what every in-scope row HELD; it does not know which rows the write
actually landed on. So each successful compare-and-set stamps its own row with
`applied_commence_time` / `applied_status`, and the restore reverts only rows
carrying those — itself by compare-and-set against them. A skipped row is
therefore untouched by the undo, instead of being "restored" to a value nobody
overwrote, which is the same class of defect as a stale backup pointing the
other way.

`CREATE TABLE IF NOT EXISTS backup_5821_event_dates` is runtime DDL executed
only when a person invokes `--backup` on a named app — notice 47(c), NOT
migration-class: the invocation is the attended step.

🔴 AND THE FIRST DRY RUN MUST NOT NEED THAT TABLE TO EXIST
(`5821-FIRST-DRY-RUN-WITHOUT-BACKUP-TABLE`). Step 0 of the runbook is a dry run
on a database where `--backup` has never run, so the reconciliation query
reaches for a relation that is not there — and the first cut of this script
raised `UndefinedTable` on the exact command its own header tells an operator to
run first. The reconciliation now asks `to_regclass` before it asks anything
else and reports "no backup yet" as the honest answer, which is also the correct
one: every in-scope row is unbacked, so `--apply` would refuse anyway.

------------------------------------------------------------------------------
RUNBOOK (attended — Alex, or whoever the desk names)
------------------------------------------------------------------------------
    0.  anywhere, reads nothing but the database:
        python3 scripts/repair_5821_polymarket_listing_dates.py

    1.  heroku run:detached -a bainluck-heavy \\
            "python3 scripts/repair_5821_polymarket_listing_dates.py --backup"

    2.  heroku run:detached -a bainluck-heavy \\
            "python3 scripts/repair_5821_polymarket_listing_dates.py --apply"

Steps 1 and 2 are not advice: `--backup`/`--apply` refuse unless
`HEROKU_APP_NAME` is `bainluck-heavy`. **`match_prediction_markets` is in
`HEAVY_TASKS` and it is the task that auto-creates these rows with the listing
stamp**, so that app is where the producer actually runs. (`poll_polymarket_
markets` is NOT heavy — it runs on the main app — but it only writes
`market_metadata`, never `events.commence_time`, which is why the heavy app is
the one that matters here. Checked against `app.tasks.HEAVY_TASKS`, not
assumed.) A dry run only reads, so step 0 runs anywhere.

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The app the PRODUCER runs on. `match_prediction_markets` — the task that
#: auto-creates these rows, stamping the Gamma listing instant onto
#: `commence_time` — is in `HEAVY_TASKS`, and since the heavy split that means
#: `bainluck-heavy`, released separately from the web app and routinely behind
#: it (standing notice 48). `poll_polymarket_markets` is deliberately NOT named
#: here: it is not heavy, and it writes `market_metadata`, never this column.
#: `test_the_runbook_targets_the_producer_app_5821` ties this constant to
#: HEAVY_TASKS membership so moving the creator off heavy reddens a test
#: instead of leaving the runbook quietly lying.
PRODUCER_APP = "bainluck-heavy"

#: Only this provenance is re-dated. An event dated by odds_api, ESPN, StatPal
#: or Kalshi is NOT in scope even when a linked Polymarket market disagrees with
#: it: Gamma disagreeing with ESPN is not evidence that ESPN is wrong, and the
#: defect this repairs is specifically a Gamma LISTING stamp written as a
#: kickoff. Measured 2026-09-13: excluding those sources leaves 108 event-market
#: pairs alone, 25 of which disagree by more than a minute.
IN_SCOPE_COMMENCE_SOURCE = "polymarket"

#: Seconds of disagreement below which there is nothing to repair. Also what
#: makes the script idempotent: after an apply the corrected rows agree exactly
#: and drop out of the population, so a second run is a no-op that says so.
MIN_DISAGREEMENT_SECONDS = 60

#: Sanity ceiling, not a floor (gotcha #53's inverse for a WRITER). Measured
#: population 2026-09-13 10:3xZ is 342. A predicate that has gone wide should
#: stop and be looked at rather than re-date a thousand rows.
MAX_EXPECTED_POPULATION = 600

#: A correction larger than this is not believed. Measured largest today is
#: 27.44 days — a Gamma listing published a month before the fixture — so this
#: is roughly 2x the observed maximum. It exists for the day the venue field
#: carries a garbage instant, where the alternative is silently moving a fixture
#: to next year.
MAX_MOVE_DAYS = 60

#: THE POPULATION. Four clauses, each one an exclusion with a reason:
#:
#:   `commence_time_source = 'polymarket'`   this provenance only (above)
#:   `n_starts = 1`                          the linked markets AGREE on the
#:                                           fixture instant. 27 events have
#:                                           markets carrying two or more
#:                                           different instants; there is no
#:                                           honest way to pick one, so they are
#:                                           refused rather than guessed at.
#:   `v.start > now()`                       future fixtures only (see SCOPE)
#:   `abs(...) > :min_seconds`               something to actually repair
#:
#: `m.source = 'polymarket'` on the inner select is belt to the braces: the key
#: is only stamped by the Polymarket ingest today, and pinning the source means
#: a future writer of that key on another provider's market cannot re-date an
#: event through this script without somebody editing this line.
_POPULATION_SQL = """
SELECT e.id,
       e.status,
       e.commence_time                AS ours,
       v.start                        AS venue,
       e.home_team_name               AS h,
       e.away_team_name               AS a,
       e.home_score,
       e.away_score,
       e.completed_at,
       s.key                          AS sport_key
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  JOIN (
        SELECT x.event_id,
               min(x.start)               AS start,
               count(DISTINCT x.start)    AS n_starts
          FROM (
                SELECT m.event_id,
                       (m.market_metadata->>'venue_game_start')::timestamptz
                           AS start
                  FROM futures_markets m
                 WHERE m.source = 'polymarket'
                   AND m.event_id IS NOT NULL
                   AND m.market_metadata->>'venue_game_start' IS NOT NULL
               ) x
         GROUP BY x.event_id
       ) v ON v.event_id = e.id
 WHERE e.commence_time_source = :source
   AND v.n_starts = 1
   AND v.start > now()
   AND abs(extract(epoch FROM (e.commence_time - v.start))) > :min_seconds
 ORDER BY v.start, e.id
"""


#: The statuses a re-dated FUTURE row may be lifted out of. An allowlist, and
#: the same shape of decision as `EVENT_PLAYABLE_STATUSES` next door: a status
#: nobody thought of must be left alone rather than quietly rewritten.
#:
#: `live` and `suspended` are the two this population wears (40 and 302 of 342,
#: measured). Both are claims about a match in progress, and neither can be true
#: of a fixture whose own venue says it starts days from now. Everything else —
#: `closed`, `completed`, `voided`, `merged`, and anything added upstream
#: tomorrow — is a terminal or unknown state this repair has no business
#: touching, so it keeps its status and gets only its clock corrected.
LIFTABLE_IN_PROGRESS_STATUSES = frozenset({"live", "suspended"})


def planned_write(status, ours, venue, now) -> dict:
    """The columns this repair would write for ONE row. Pure: no DB, no clock.

    Separated from the statement that executes it so the decision can be tested
    without Postgres — the population query is Postgres-only by construction and
    the guard suite has no Postgres, which is exactly how the status half of this
    repair was missing for a whole presentation (CERT-2797).

    Returns `{}` when there is nothing to do, so a caller can treat an empty plan
    as a skip rather than writing a no-op.
    """
    from app.utils.lifecycle import EVENT_NOT_STARTED

    if venue is None or ours is None or venue == ours:
        return {}

    write = {"commence_time": venue}
    if venue > now and status in LIFTABLE_IN_PROGRESS_STATUSES:
        write["status"] = EVENT_NOT_STARTED
    return write


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must happen on the
    producer's app: `match_prediction_markets` is in `HEAVY_TASKS`, and it is
    the task that mints these rows off the listing stamp, so that app is the
    only interpreter whose deployed code is the code that could put the defect
    back while we are writing.

    `HEROKU_APP_NAME` comes from the `runtime-dyno-metadata` lab, enabled on
    both apps. UNSET refuses too rather than falling through — unset means a
    laptop pointed at the production database with whatever happens to be
    checked out, which is precisely the case this gate exists to stop.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        "`match_prediction_markets` — the task that mints these rows off the "
        "listing stamp — is in HEAVY_TASKS, so the code that can put the defect "
        f"back is what is deployed to '{PRODUCER_APP}', an app released "
        "separately from the web app and routinely behind it (standing notice "
        f"48). Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        rows = (
            await s.execute(
                text(_POPULATION_SQL),
                {
                    "source": IN_SCOPE_COMMENCE_SOURCE,
                    "min_seconds": MIN_DISAGREEMENT_SECONDS,
                },
            )
        ).all()

        print("=== #5821 Polymarket listing dates — population ===")
        if not rows:
            print("Nothing to repair — population is 0 (idempotent no-op).")
            return 0

        for r in rows[:40]:
            move = (r.venue - r.ours).total_seconds() / 86400.0
            print(
                f"  {r.id:>9} {str(r.status)[:9]:<9} {str(r.sport_key)[:16]:<16} "
                f"{str(r.a)[:18]:<18}@{str(r.h)[:18]:<18} "
                f"{str(r.ours)[:16]} -> {str(r.venue)[:16]}  (+{move:.2f}d)"
            )
        if len(rows) > 40:
            print(f"  … and {len(rows) - 40} more (this is a SAMPLE, not the set)")

        # Every refusal below is stated as a COUNT over the whole population,
        # never over the sample printed above.
        scored = [
            r for r in rows if r.home_score is not None or r.away_score is not None
        ]
        finished = [r for r in rows if r.completed_at is not None]
        backwards = [r for r in rows if r.venue < r.ours]
        far = [
            r
            for r in rows
            if abs((r.venue - r.ours).total_seconds()) > MAX_MOVE_DAYS * 86400
        ]
        print(
            f"  events={len(rows)}  scored={len(scored)}  finished={len(finished)}  "
            f"moves_backwards={len(backwards)}  beyond_{MAX_MOVE_DAYS}d={len(far)}"
        )

        if len(rows) > MAX_EXPECTED_POPULATION:
            print(
                f"\nREFUSING: {len(rows)} rows exceeds MAX_EXPECTED_POPULATION="
                f"{MAX_EXPECTED_POPULATION}. The predicate matched far more than "
                "the measured population; look before writing."
            )
            return 2

        if scored or finished:
            # A row that is in the FUTURE and already has a result is a
            # contradiction, and re-dating it would be acting on the half of the
            # contradiction we happen to be holding. Measured 0 today; this is
            # here for the day it is not.
            print(
                f"\nREFUSING: {len(scored)} row(s) carry a score and "
                f"{len(finished)} carry `completed_at`, yet their venue instant "
                "is in the future. That is a contradiction, not a date defect — "
                "investigate before moving any clock."
            )
            return 2

        if backwards:
            print(
                f"\nREFUSING: {len(backwards)} correction(s) move a fixture "
                "EARLIER. The defect is a LISTING stamp preceding a kickoff, so "
                "every correction should move forward; a backwards one means the "
                "venue field is not what this repair believes it is."
            )
            return 2

        if far:
            print(
                f"\nREFUSING: {len(far)} correction(s) exceed {MAX_MOVE_DAYS} "
                "days. Largest measured on production is 27.44d; beyond this the "
                "venue instant is not believed."
            )
            return 2

        event_ids = [r.id for r in rows]

        now = datetime.now(timezone.utc)
        plans = {r.id: planned_write(r.status, r.ours, r.venue, now) for r in rows}
        lifted = sum(1 for p in plans.values() if "status" in p)
        print(
            f"  would re-date {len(plans)} and lift {lifted} out of "
            f"{sorted(LIFTABLE_IN_PROGRESS_STATUSES)} to `scheduled`"
        )

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_5821_event_dates ("
                    "id bigint PRIMARY KEY, "
                    "commence_time timestamptz, "
                    "status text, "
                    # The RECEIPT half: written by --apply, never by --backup, so
                    # the undo can tell a row it moved from a row it planned to.
                    "applied_commence_time timestamptz, "
                    "applied_status text)"
                )
            )
            await s.execute(
                text(
                    # DO UPDATE, not DO NOTHING: a second --backup after another
                    # writer moved a row must REFRESH it, or the undo restores a
                    # value that was never the one we overwrote. The receipt
                    # columns are cleared with it — a refreshed backup describes
                    # a row that has NOT been written by this run.
                    "INSERT INTO backup_5821_event_dates "
                    "(id, commence_time, status) "
                    "SELECT id, commence_time, status FROM events "
                    "WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "commence_time = EXCLUDED.commence_time, "
                    "status = EXCLUDED.status, "
                    "applied_commence_time = NULL, "
                    "applied_status = NULL"
                ),
                {"ids": event_ids},
            )
            await s.commit()
            print(f"  copied {len(event_ids)} event clocks and statuses")

        # `5821-FIRST-DRY-RUN-WITHOUT-BACKUP-TABLE`: step 0 of the runbook is a
        # dry run on a database where `--backup` has never run. Asking the
        # relation a question before asking whether it exists made the script's
        # own documented first command raise `UndefinedTable`.
        backup_exists = (
            await s.execute(
                text("SELECT to_regclass('public.backup_5821_event_dates') IS NOT NULL")
            )
        ).scalar()

        if not backup_exists:
            stale = len(event_ids)
            print(
                "\n=== backup reconciliation === no backup table yet — every "
                f"one of the {stale} in-scope rows is unbacked (this is the "
                "expected reading on a first dry run)"
            )
        else:
            stale = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM events e WHERE e.id = ANY(:ids) AND "
                        "NOT EXISTS (SELECT 1 FROM backup_5821_event_dates b "
                        "WHERE b.id = e.id "
                        "AND b.commence_time IS NOT DISTINCT FROM e.commence_time "
                        "AND b.status IS NOT DISTINCT FROM e.status)"
                    ),
                    {"ids": event_ids},
                )
            ).scalar()
            print(
                f"\n=== backup reconciliation (content-exact, both columns) === "
                f"unbacked-or-stale={stale}"
            )

        if not args.apply:
            print(
                f"\nDRY RUN — nothing written. Would re-date {len(event_ids)} "
                "events from their Gamma listing stamp to their venue fixture "
                f"instant, and lift {lifted} of them to `scheduled`."
            )
            return 0

        if stale:
            print(
                "\nREFUSING --apply: the backup does not match the rows about to "
                "be written — either a row is unbacked, or it MOVED since the "
                "backup was taken and the undo would restore a value that was "
                "never overwritten. Re-run --backup."
            )
            return 2

        written = 0
        skipped = []
        for r in rows:
            plan = plans.get(r.id) or {}
            if not plan:
                skipped.append(r.id)
                continue
            # Compare-and-set on BOTH values the plan was made from. rowcount 0
            # is a real finding — the row moved under us — not a silent pass.
            new_status = plan.get("status", r.status)
            result = await s.execute(
                text(
                    "UPDATE events SET commence_time = :venue, status = :new_status "
                    "WHERE id = :id AND commence_time = :ours AND status = :ours_status"
                ),
                {
                    "venue": plan["commence_time"],
                    "new_status": new_status,
                    "id": r.id,
                    "ours": r.ours,
                    "ours_status": r.status,
                },
            )
            if result.rowcount:
                written += 1
                # The receipt, written in the same transaction as the change it
                # attests to, so the undo can never offer to revert a row this
                # run did not touch (`5821-RESTORE-ONLY-SUCCESSFUL-CAS`).
                await s.execute(
                    text(
                        "UPDATE backup_5821_event_dates SET "
                        "applied_commence_time = :venue, applied_status = :st "
                        "WHERE id = :id"
                    ),
                    {"venue": plan["commence_time"], "st": new_status, "id": r.id},
                )
            else:
                skipped.append(r.id)
        await s.commit()

        print(f"\nAPPLIED: re-dated {written} events, {lifted} lifted to `scheduled`.")
        if skipped:
            print(
                f"  SKIPPED {len(skipped)} that moved between the read and the "
                f"write, or had nothing to write: {skipped[:20]}"
            )
        print("UNDO: python3 scripts/restore_5821_polymarket_listing_dates.py --apply")
        return 0


def main():
    p = argparse.ArgumentParser(description="#5821 Polymarket listing-date repair")
    p.add_argument("--backup", action="store_true", help="copy in-scope clocks")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit no-op form of the default; reads only",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
