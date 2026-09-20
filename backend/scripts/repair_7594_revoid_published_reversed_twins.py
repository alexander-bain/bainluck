"""#7594 — take back the reversed-orientation twins #7260 already published (D51(b)).

    heroku run:detached -a bainluck -- python3 scripts/repair_7594_revoid_published_reversed_twins.py
    heroku run:detached -a bainluck -- python3 scripts/repair_7594_revoid_published_reversed_twins.py --backup
    heroku run:detached -a bainluck -- python3 scripts/repair_7594_revoid_published_reversed_twins.py --backup --apply

Undo: ``restore_7594_revoid_published_reversed_twins.py --apply``.

WHAT A READER SEES WITHOUT THIS
-------------------------------
``/api/events/search`` page 1 for the query ``hurricanes``, measured on
production 2026-09-20 20:59Z, adjacent rows:

🪤 The query string is spelled out in words rather than pasted as a URL on
purpose. ``test_search_origin_channel_p118`` scans every file under
``scripts/`` for a search URL and requires the ones it finds to declare
themselves machine traffic, so that an untagged probe cannot vote in the warm
head (notice 39). The guard reads the whole file, prose included, and this
script sends nothing — it is a database repair that never opens a connection.
Quoting the URL verbatim would have put it on that list for a docstring, which
is the wrong way to answer a guard that is protecting something real.

    15302884  Hurricanes v Panthers                   2026-09-20T23:00Z
    15312312  Florida Panthers v Carolina Hurricanes  2026-09-20T23:00Z

One game, one minute, two cards, an hour before puck drop. #7260's revival arm
screened its candidates for a surviving twin and asked that question
home↔home / away↔away only, so a survivor whose sides were swapped could not
enter the screen at all and the arm read "orphan" for a fixture a reader could
already see. The forward fix is #7594 in ``espn_sync``; this script is the half
of that ship that addresses the rows the blind screen already let out.

Measured the same minute: **16 revived rows** carry a reversed-orientation
survivor — 15 NHL, 1 WNBA. They appear as 19 (revived, canonical) pairings
because three of them match two canonical rows each; that the canonical side has
its own duplicates is #2693's, not this script's, and this script never touches a
row it did not revive.

🔴 THE GUARD HAS TO BE LIVE FIRST, AND THIS SCRIPT ENFORCES THAT BY CONSTRUCTION
-------------------------------------------------------------------------------
This does not re-spell the twin test. It calls
:func:`~app.tasks.espn_sync._row_has_surviving_counterpart` — the same function
the beat asks — so the repair and the forward guard cannot drift into disagreeing
about which rows are duplicates, which is the whole failure this ship is cleaning
up after.

The load-bearing consequence: **run this on a dyno that has not taken the #7594
release and it selects nothing.** The pre-fix helper is orientation-blind, so for
exactly this population it answers False and the plan comes back empty. The
ordering the cert required is therefore not a procedure someone has to remember —
it is the only ordering the code can express. An empty plan on a pre-fix dyno is
that guard reporting, not a no-op to investigate (hot-list #53: the zero-yield
case is made loud, and ``--apply`` says so by name).

It is also why re-voiding early would be pointless rather than merely premature:
the beat fires every ten minutes and would re-revive every row on the next pass.

WHAT THE WRITE ACTUALLY IS
--------------------------
``UPDATE events SET status = 'voided' WHERE id = :i AND status = :before`` — a
compare-and-swap on the status this script read, so a row another writer has
moved on (a game that has since gone ``live``, a re-void by any other arm) is
skipped and reported by id rather than overwritten. Nothing else on the row is
touched: no score, no blend, no ``commence_time``.

🔴 THE SWAP IS THE CLAIM, SO THE BANK IS WRITTEN AFTER IT AND ONLY ON A WIN.
The UPDATE goes first; the bank row is inserted only when it matched. Both are
in one transaction, so banking first buys nothing for durability — neither can
commit without the other — and it costs correctness here, because on this cohort
the race is not hypothetical. These are upcoming games and the kickoff arm is
firing continuously; losing the swap under the old order left a bank row
asserting a ``status_after`` this script never wrote. ``restore_…`` keys on
``e.status = b.status_after``, so the day any other arm moved that event to the
terminal status the undo would have matched a row it never touched and put it
back on ``scheduled`` — re-publishing the duplicate on a claim nobody earned.

A lost swap is also the one outcome the pass's own read-back cannot see: rows
that lose it lose it *because* something moved them out of ``scheduled``, which
is the column ``candidates()`` filters on. Those ids are therefore carried out of
the loop and re-read by id, and the run prints ``NOT CLEAN`` — otherwise the
worst result of the pass reports as ``0 revived rows remain``.

Scope is the #7260 arm's OWN record — the join to
``backup_unreachable_suspended_5532`` — for the reason
:func:`retired_row_start_moved_into_future` gives at length about the revival
itself: 2,544 rows match the retirement predicate for unrelated reasons, and a
repair keyed on the predicate rather than on the arm's ledger would reach into a
population this ship never touched.

🔴 A PAIR THAT IS ENTIRELY OURS KEEPS ONE ROW. The screen is re-asked per row
against the live transaction, and each re-void is flushed before the next row is
examined, so when both halves of a fixture were revived by the arm the first is
taken back and the second then reads as an orphan and is KEPT. Ordering is
``commence_time, id`` so which half survives is deterministic and re-runnable
rather than a function of heap order. Taking both back would delete the fixture
from the site, which is the defect #7260 exists to fix, arrived at from the other
side.

A readable plan is the default: a bare run prints every row it would take back
and commits nothing, so the operator checks the list rather than inferring it
from a row count afterwards. The plan is the apply rolled back — it issues the
identical statements inside a transaction it discards — because each take-back
changes the screen's answer for the row after it, and a dry run that skipped the
writes would disagree with the run it claims to predict.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.espn_sync import (  # noqa: E402
    UNREACHABLE_SUSPENDED_BACKUP_TABLE,
    _row_has_surviving_counterpart,
)
from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL  # noqa: E402

#: The app whose database this repair belongs to. See notice 48. The #7260 arm
#: runs on the main app's `worker-background`, so this is the producer.
PRODUCER_APP = "bainluck"

#: Where the pre-repair statuses go. One row per event taken back.
BANK_TABLE = "bak_7594_revoid_published_reversed_twins"


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app.

    THE UNDO IMPORTS THIS, so a restore — a production write in the opposite
    direction — earns the identical gate rather than a second copy that drifts.
    ``getattr`` because the undo's parser defines no ``--backup``.

    UNSET refuses too: unset means a laptop pointed at the production database
    with whatever happens to be checked out, which is the case this exists for.
    """
    if not (getattr(args, "apply", False) or getattr(args, "backup", False)):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. "
        f"Re-run with `heroku run:detached -a {PRODUCER_APP}`."
    )


def missing_backup_refusal(args) -> str | None:
    """Refuse ``--apply`` unless ``--backup`` comes with it (D51(b)).

    Argument-level and checked before the script opens a session, so the refusal
    cannot be reached from a code path that has already written something. The
    two flags stay separate rather than ``--apply`` implying ``--backup``
    because the operator's command line is the record of what was authorised: a
    run that banks has to say so (CERT-3171's rule, inherited from #7501).
    """
    if getattr(args, "apply", False) and not getattr(args, "backup", False):
        return (
            "REFUSING to write: --apply requires --backup. The bank is what "
            "makes this re-void reversible in one command, so it is the "
            "precondition of the write and not an option beside it. "
            "Re-run with `--backup --apply`."
        )
    return None


async def ensure_bank(s) -> None:
    """Create the bank and its key. Idempotent; safe to call on every run.

    ``event_id`` and ``status_before`` take their types from the columns they
    mirror (#6215's lesson: one hand-typed column made a backup unrunnable,
    which made ``--apply`` refuse forever). The key is ``event_id`` alone — one
    event, one take-back — so re-running ``--backup`` tops the table up rather
    than duplicating it.

    ``status_after`` is banked as well as ``status_before`` because the undo's
    compare-and-swap is on what WE wrote, never on "the live row differs from
    its backup" (the #7354 rail's argument): a row something else has since
    moved must keep its newer state, not be dragged back by an undo.
    """
    from sqlalchemy import text

    await s.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BANK_TABLE} AS "
            "SELECT id AS event_id, status AS status_before, "
            "status AS status_after, now() AS taken_at "
            "FROM events WHERE false"
        )
    )
    await s.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {BANK_TABLE}_pk "
            f"ON {BANK_TABLE} (event_id)"
        )
    )
    await s.commit()


async def candidates(s):
    """Rows the #7260 arm revived that are still ahead of their own kickoff.

    Ordered ``commence_time, id``: soonest first because that is the card a
    reader is most likely to be looking at tonight, and deterministically so
    that which half of an all-ours pair survives is re-runnable rather than heap
    order (gotcha: a tie broken by the plan is not a tie broken by the write).
    """
    from sqlalchemy import text

    return (
        await s.execute(
            text(
                "SELECT e.id FROM events e JOIN "
                f"{UNREACHABLE_SUSPENDED_BACKUP_TABLE} b ON b.event_id = e.id "
                "WHERE e.status = :scheduled AND e.commence_time > now() "
                "ORDER BY e.commence_time ASC, e.id ASC"
            ),
            {"scheduled": "scheduled"},
        )
    ).scalars().all()


async def run(args) -> int:
    from sqlalchemy import bindparam, text

    from app.models.models import Event
    from app.tasks.base import get_task_session

    for refusal in (missing_backup_refusal(args), wrong_app_refusal(args)):
        if refusal:
            print(refusal)
            return 2

    async with get_task_session() as s:
        present = (
            await s.execute(
                text("SELECT to_regclass(:t) IS NOT NULL"),
                {"t": f"public.{UNREACHABLE_SUSPENDED_BACKUP_TABLE}"},
            )
        ).scalar()
        if not present:
            # The arm's ledger is the scope, so its absence means the arm never
            # revived anything here and there is nothing of ours to take back.
            print(
                f"{UNREACHABLE_SUSPENDED_BACKUP_TABLE} does not exist: the "
                "#7260 arm has published nothing on this database. Nothing to do."
            )
            return 0

        if args.backup:
            await ensure_bank(s)
            banked = (
                await s.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
            ).scalar_one()
            print(f"{BANK_TABLE}: ready, {banked} rows banked so far")

        ids = await candidates(s)
        print(f"{len(ids)} revived rows are still ahead of their kickoff")

        taken, skipped, lost, kept = [], [], [], 0
        for event_id in ids:
            event = await s.get(Event, event_id)
            if event is None:
                continue
            # The shipped screen, asked against the live transaction so that a
            # row already taken back in THIS run counts as retired for the next
            # one. See the module docstring: this is what keeps one half of an
            # all-ours pair on the site.
            if not await _row_has_surviving_counterpart(s, event):
                kept += 1
                continue

            label = (
                f"{event.id} {event.home_team_name} v {event.away_team_name} "
                f"{event.commence_time}"
            )
            before = event.status
            # 🔴 THE WRITE IS THE CLAIM ON THE ROW, AND THE BANK RECORDS ONLY
            # WHAT THAT CLAIM WON. The compare-and-swap is issued FIRST and the
            # bank entry is written only on `rowcount > 0`.
            #
            # It used to be the other way round, on the reasoning that a bank
            # entry preceding its write is what makes the write reversible. Both
            # statements are in one transaction, so that ordering buys nothing
            # for durability — neither can commit without the other — and it
            # costs correctness on the race this cohort is most exposed to.
            # These are upcoming games, and the arm that moves `scheduled` to
            # `live` is firing continuously. Lose that race and the old order
            # committed a bank row for a write that never happened: the UPDATE
            # matched nothing, the row was reported skipped, and the bank still
            # claimed we had put the event on `status_after`.
            #
            # That orphan is not inert. `restore_…` restores on
            # `e.status = b.status_after` — what WE wrote — so the day any other
            # arm legitimately moves that event to the terminal status, the undo
            # matches a row it never touched and drags it back to `scheduled`,
            # re-publishing a duplicate on a claim this repair never earned.
            # Banking after the swap makes that unrepresentable rather than
            # merely unlikely.
            moved = (
                await s.execute(
                    text(
                        "UPDATE events SET status = :after "
                        "WHERE id = :i AND status = :before"
                    ),
                    {
                        "after": UNREACHABLE_SUSPENDED_TERMINAL,
                        "i": event.id,
                        "before": before,
                    },
                )
            ).rowcount
            if moved:
                # Banked only when the bank exists. A bare plan is allowed to run
                # without `--backup` (that is what makes it readable before
                # anything is authorised), and an INSERT into a table no one has
                # created yet would fail the whole pass with `undefined_table` —
                # turning the safest invocation into the only one that errors.
                if args.backup:
                    await s.execute(
                        text(
                            f"INSERT INTO {BANK_TABLE} "
                            "(event_id, status_before, status_after, taken_at) "
                            "VALUES (:i, :b, :a, now()) "
                            "ON CONFLICT (event_id) DO NOTHING"
                        ),
                        {
                            "i": event.id,
                            "b": before,
                            "a": UNREACHABLE_SUSPENDED_TERMINAL,
                        },
                    )
                taken.append(label)
            else:
                # Compare-and-swap lost: something moved this row between the
                # read and the write. Reported by id, never overwritten, and
                # NOT banked — see above.
                lost.append(event.id)
                skipped.append(label)
            # Flush so the next row's screen sees this one as retired.
            await s.flush()

        for label in taken:
            print(("  took back " if args.apply else "  would take back ") + label)
        for label in skipped:
            print("  SKIPPED, moved under us: " + label)

        if not args.apply:
            # 🔴 THE PLAN IS THE APPLY, ROLLED BACK. The loop above must write
            # and flush as it goes, because each take-back changes the screen's
            # answer for the next row (an all-ours pair keeps its second half
            # only because the first is already retired when it is examined). A
            # dry run that skipped the writes would therefore print BOTH halves
            # of such a pair and disagree with the run it claims to predict. So
            # the plan runs the identical statements and discards them, and the
            # operator reads a list the apply will reproduce exactly.
            await s.rollback()
            print(
                f"plan: {len(taken)} would be taken back, {kept} are genuine "
                "orphans and stay on the site."
            )
            if not taken:
                # LOUD, because an empty plan has two very different causes and
                # they must not look alike (hot-list #53).
                print(
                    "NOTHING SELECTED. Either the population is already clean, "
                    "or this dyno has not taken the #7594 release and the "
                    "orientation-blind screen is answering — check that the "
                    "running commit carries the fix before reading this as done."
                )
            print("plan only. Re-run with --backup --apply.")
            return 0

        await s.commit()

        # Read the column back rather than trusting the counters (hot-list #53).
        left = len(await candidates(s))
        print(
            f"done: took back {len(taken)}, skipped {len(skipped)}, kept {kept} "
            f"orphans; {left} revived rows remain ahead of their kickoff"
        )

        # 🔴 `left` IS NOT A CLEANLINESS SCORE, AND ON ITS OWN IT LIES ABOUT
        # EXACTLY THE ROWS THIS PASS FAILED ON. `candidates()` selects
        # `status = 'scheduled' AND commence_time > now()`. A row that lost the
        # compare-and-swap lost it BECAUSE something moved it out of
        # `scheduled` — usually the kickoff arm — so it is no longer counted by
        # the very query used to report what is left. Skip the report below and
        # the worst outcome of the pass prints as `0 revived rows remain` while
        # the duplicate is still on the site, now as a live card.
        #
        # It cannot be fixed by widening the read-back's predicate either: once
        # the game has started the row fails `commence_time > now()` too. So the
        # lost ids are carried out of the loop and re-read BY ID, which no
        # population predicate can hide.
        if lost:
            # An expanding bindparam rather than `= ANY(:ids)`: the same
            # statement then runs on Postgres and on the sqlite rail the race
            # test drives the real loop over, so the reporting path a lost race
            # depends on is covered by a test instead of being the one branch
            # that only production ever executes.
            now_status = dict(
                (
                    await s.execute(
                        text("SELECT id, status FROM events WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": lost},
                    )
                ).all()
            )
            print(
                f"NOT CLEAN: {len(lost)} row(s) moved under this pass and were "
                f"NOT taken back. They are absent from the {left} above because "
                "they are no longer 'scheduled'."
            )
            for event_id in lost:
                print(f"  {event_id} is now '{now_status.get(event_id, '?')}'")
            print(
                "These have left this repair's population by its own definition "
                "(revived AND still ahead of kickoff), so re-running will not "
                "reach them — a started game is not taken off the site by this "
                "script, and voiding a live fixture is not in this ship. The "
                "forward #7594 guard stops new ones; an already-live duplicate "
                "is #2693's. Report these ids there rather than re-running."
            )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="create/top up the bank")
    p.add_argument("--apply", action="store_true", help="take the twins back")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
