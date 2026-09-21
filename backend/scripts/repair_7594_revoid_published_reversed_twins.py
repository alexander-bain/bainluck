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
``UPDATE events SET status = 'voided' WHERE id = :i AND status = :before AND
EXISTS (a row the screen just accepted, still in the status it accepted it in)``
— a compare-and-swap on BOTH rows at once. On this row's own status, so a row
another writer has moved on is never overwritten on a stale read; and on the
canonical's, so the take-back is licensed only while a card a reader can reach
still holds the fixture. Either half missing is a rowcount of 0, the row is
re-read, and the attempt is made again against what the database actually says
(below). Nothing else on the row is touched: no score, no blend, no
``commence_time``.

🔴 THE SECOND HALF IS CERT-3199's REPAIR, AND A RE-ASKED SCREEN COULD NOT DO IT.
A screen is a fact about the instant it was read; the write is a different
instant. Retire the canonical in between and a swap conditioned on this row's
status alone still matches — both rows commit retired, the pass reports success,
and the fixture has ZERO reader-visible cards. That is the #7260 defect produced
by its own repair, so the condition has to travel INSIDE the statement. The rule
about which rows are the same fixture does not move into SQL: ``espn_sync``'s
``_surviving_counterpart_rows`` still decides that in Python and hands back the
ids it accepted, and the WHERE clause re-checks only their liveness.

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

🔴 AND REPORTING A LOST ROW IS NOT DISPOSING OF IT (CERT-3197). Reporting was
this script's whole answer to a lost swap, on the argument that "voiding a live
fixture is not in this ship". That argument is wrong on this population, and it
is wrong in the reader's direction: the row that loses the swap loses it by
kicking off, so the outcome it bought was a duplicate that is not merely still on
the site but now the LIVE card for a game whose canonical row is live beside it —
the exact harm of the ship — while ``run()`` exited 0 and called it out of scope.
A row that this pass has already decided is a duplicate does not stop being one
by starting. So a lost swap is now re-attempted against the status the row
actually moved to — an atomic own, never a blind overwrite, because every attempt
is a compare-and-swap on a status just read — and the screen is re-asked before
each retry, so the take-back happens only while a canonical row a reader can
reach still holds the fixture. :func:`own_or_dispose` is that loop, and the four
ways it can legitimately stop writing (the row is gone; another arm retired it;
its canonical has disappeared, which makes this the last card and keeping it
correct; it was owned) are named outcomes rather than one silent ``skipped``.

When none of those is reached — something keeps moving the row and it is still
reader-visible beside its canonical — the pass has failed at the thing it exists
to do, and **it exits nonzero**. An operator, a wrapper and a re-run all read the
exit code before they read the prose; a pass that prints ``NOT CLEAN`` and exits
0 is telling the truth to a human and the opposite to everything else.

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
    REVIVED_TWIN_TAKEBACK_BANK_TABLE,
    UNREACHABLE_SUSPENDED_BACKUP_TABLE,
    _row_has_surviving_counterpart,
    _surviving_counterpart_rows,
)
from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL  # noqa: E402

#: The app whose database this repair belongs to. See notice 48. The #7260 arm
#: runs on the main app's `worker-background`, so this is the producer.
PRODUCER_APP = "bainluck"

#: Where the pre-repair statuses go. One row per event taken back.
#:
#: IMPORTED, NOT SPELLED, since the forward arm landed. This script and
#: `_take_back_revived_twins_impl` are one repair asked once and asked
#: continuously; they bank into the same table so that
#: `restore_…_reversed_twins.py --apply` is the single undo for both, and
#: importing the name is what stops the two from drifting into two tables with
#: one undo pointed at whichever was written first.
BANK_TABLE = REVIVED_TWIN_TAKEBACK_BANK_TABLE

#: How many times a lost compare-and-swap is re-issued against the status the
#: row actually moved to before the pass declares the row unresolved.
#:
#: Bounded rather than "until it wins" because the competing writer is a beat
#: that fires forever: an unbounded retry against a row something is rewriting
#: every second is a pass that never returns, which is a worse outcome than a
#: named failure. Three is enough for the shape that actually occurs here — a
#: single `scheduled → live` kickoff, where attempt two wins — and anything that
#: survives three swaps is a row under continuous write that this script should
#: be reporting rather than fighting.
LOST_RACE_ATTEMPTS = 3

#: Why a row `own_or_dispose` did not write was safe to leave, in the operator's
#: words. Every non-writing outcome has an entry, so a new one added to that
#: function without a reason a reader can check raises a `KeyError` on the very
#: first run rather than printing a blank.
_WHY_LEFT_ALONE = {
    "gone": "the row no longer exists",
    "already_retired": "another arm retired it first",
    "last_row_standing": "its canonical disappeared, so this is the only card",
    "unscreenable": (
        "the shipped screen cannot run on this row, so there is no canonical "
        "to bind the take-back to"
    ),
}


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


async def own_the_canonical(s, ids) -> list[tuple[int, str]]:
    """Take row ownership of the counterparts, then read their statuses. (CERT-3204)

    Returns the `(id, status)` pairs that are STILL reachable, read under the
    lock and therefore true until this transaction ends.

    🔴 WHY A CORRELATED ``EXISTS`` IN THE UPDATE WAS NOT ENOUGH, which is the
    whole of CERT-3204's finding. Under READ COMMITTED a statement's subquery is
    evaluated against that statement's snapshot, and MVCC readers do not block —
    so a writer that retires the canonical and commits AFTER the snapshot is
    taken cannot be seen by the subquery, while the subject's own row is updated
    perfectly happily. Both rows commit retired and the fixture has zero
    reader-visible cards: the window is narrower than the one CERT-3199 found,
    and exactly as fatal.

    ``FOR UPDATE`` closes it because it is the one read that DOES block. Whatever
    the interleaving:

    * the competing writer got there first and committed ⇒ this read returns the
      retired status, the caller keeps its row, and nothing is written;
    * the competing writer is mid-transaction ⇒ this read WAITS for it, then
      returns the committed status, which is the case above;
    * the competing writer arrives after this read ⇒ it waits for the take-back's
      own transaction, so it re-evaluates against a database in which the subject
      is already retired, rather than against the one this pass started in.

    There is no fourth order. The pair can no longer be judged concurrently by
    two writers who each believe the other row is alive.

    ``ORDER BY id`` is the deadlock discipline: two passes that lock the same two
    rows take them in the same sequence. ``with_for_update()`` rather than raw
    SQL so the sqlite rail the race tests drive ignores the clause instead of
    failing to parse it — sqlite serialises writers anyway, which is why the
    interleaving this closes needs REAL Postgres and two REAL sessions to prove
    (``tests/integration/test_7594_canonical_ownership_pg.py``).
    """
    from sqlalchemy import select as _select

    from app.models.models import Event
    from app.utils.event_completion import is_retired_event_status

    locked = (
        await s.execute(
            _select(Event.id, Event.status)
            .where(Event.id.in_(list(ids)))
            .order_by(Event.id)
            .with_for_update()
        )
    ).all()
    return [
        (row_id, status)
        for row_id, status in locked
        if not is_retired_event_status(status)
    ]


async def own_or_dispose(s, event, *, bank: bool) -> tuple[str, str | None]:
    """Take this row back, or establish that not writing it is safe. (CERT-3197)

    Returns ``(outcome, status)``, where ``outcome`` is one of:

    ``took``
        The compare-and-swap matched. ``status`` is what it swapped FROM, which
        is what the bank records and what the undo will restore — not the status
        the row had when the pass first read it, if a retry won on a later one.
    ``gone``
        The row no longer exists. Nothing to take back.
    ``already_retired``
        Some other arm retired it while this pass was running. The reader's
        screen is in the state this repair wanted; writing again would only
        overwrite someone else's terminal status with our own.
    ``last_row_standing``
        The counterpart disappeared under us, so this row is now the only card
        for the fixture. Voiding it would delete the game from the site — the
        #7260 defect, arrived at from the other side — so it is KEPT.
    ``unscreenable``
        The shipped screen could not be run on this row at all (no usable name,
        or a sport with no family). There is no canonical to bind the take-back
        to, so nothing is written. MEASURED 2026-09-21 over the whole #7260
        ledger — 13,566 rows, of which 0 lack a name and 0 lack a sport key — so
        this branch costs nothing on the population that exists; it is here so
        that "we could not tell" can never be spent as "go ahead".
    ``unresolved``
        Still reader-visible beside a surviving canonical after every attempt.
        The caller must not report this pass as clean, and must not exit 0.

    🔴 EVERY WRITE HERE IS A COMPARE-AND-SWAP ON A STATUS THIS FUNCTION JUST
    READ. "Own the row" is not "overwrite whatever is there": a retry re-reads
    the status, re-asks the shipped screen, and swaps from the value it read, so
    a third writer landing between the read and the retry loses the same way the
    first race lost, and is retried the same way rather than silently clobbered.

    🔴 AND THE SWAP IS ON BOTH ROWS AT ONCE, IN ONE STATEMENT — CERT-3199's
    ``7594-FIRST-TAKEBACK-CANNOT-RETIRE-THE-LAST-CARD``. Re-asking the screen
    before each attempt is not enough and could never be: a screen is a fact
    about the instant it was read, and the write is a different instant. If the
    canonical retires in between, the compare-and-swap on this row's own status
    still matches, both rows commit retired, and the pass reports success over a
    fixture with ZERO reader-visible cards — the #7260 harm, produced by its own
    repair. So the UPDATE carries its own ``EXISTS``: it may only match while one
    of the rows the screen just accepted is still in the status the screen
    accepted it in. Lose that race and the rowcount is 0 and the loop re-screens,
    exactly as it does for a lost race on this row's own status.

    THE RULE ITSELF DOES NOT MOVE INTO SQL, and that distinction is the whole
    reason this is safe to do. ``_surviving_counterpart_rows`` still decides in
    Python which rows are the same fixture — name containment both ways, the
    sport family, the ±30h window — and hands back the ids it accepted. The
    WHERE clause below re-checks only the LIVENESS of those ids. A test can
    still put a counter-example to the rule, because the rule is still a
    function.
    """
    from sqlalchemy import text

    from app.utils.event_completion import is_retired_event_status

    before = event.status
    for _attempt in range(LOST_RACE_ATTEMPTS + 1):
        survivors = await _surviving_counterpart_rows(s, event)
        if survivors is None:
            return "unscreenable", before
        if not survivors:
            return "last_row_standing", before

        survivors = await own_the_canonical(s, [row_id for row_id, _st in survivors])
        if not survivors:
            return "last_row_standing", before

        params = {
            "after": UNREACHABLE_SUSPENDED_TERMINAL,
            "i": event.id,
            "before": before,
        }
        # One `(id, status)` pair per accepted counterpart, ORed: the take-back
        # is licensed while ANY of them is still standing as it was read. All of
        # them, not the first — a fixture with two reachable siblings must not
        # have its take-back refused because one of them moved.
        bound = []
        for n, (other_id, other_status) in enumerate(survivors):
            bound.append(f"(c.id = :c{n}_id AND c.status = :c{n}_status)")
            params[f"c{n}_id"] = other_id
            params[f"c{n}_status"] = other_status

        moved = (
            await s.execute(
                text(
                    "UPDATE events SET status = :after "
                    "WHERE id = :i AND status = :before "
                    "AND EXISTS (SELECT 1 FROM events c WHERE "
                    + " OR ".join(bound)
                    + ")"
                ),
                params,
            )
        ).rowcount
        if moved:
            # Banked only when the bank exists. A bare plan is allowed to run
            # without `--backup` (that is what makes it readable before anything
            # is authorised), and an INSERT into a table no one has created yet
            # would fail the whole pass with `undefined_table` — turning the
            # safest invocation into the only one that errors.
            if bank:
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
            return "took", before

        # Lost — and the statement above has TWO ways to lose now, so the first
        # question is which row moved. Read this one BY ID: never from the ORM
        # object, which still holds the status this pass read, and never from
        # `candidates()`, whose predicate is the thing the row has just left.
        now_status = (
            await s.execute(
                text("SELECT status FROM events WHERE id = :i"), {"i": event.id}
            )
        ).scalar()
        if now_status is None:
            return "gone", None
        if is_retired_event_status(now_status):
            return "already_retired", now_status
        # Unchanged here means the CANONICAL is what moved, and the next
        # iteration's screen is what says so — it returns the survivors as they
        # are NOW, so an empty answer ends the loop at `last_row_standing` and a
        # changed status is what the next attempt binds to.
        before = now_status

    return "unresolved", before


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

        taken, disposed, unresolved, kept = [], [], [], 0
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
            # 🔴 THE WRITE IS THE CLAIM ON THE ROW, AND THE BANK RECORDS ONLY
            # WHAT THAT CLAIM WON — see `own_or_dispose`, which owns both the
            # swap and the bank so the two orderings cannot be separated by a
            # later edit. A lost swap is re-attempted against the status the row
            # moved to, and the outcomes where not writing is correct are named
            # rather than collapsed into one `skipped`.
            outcome, status = await own_or_dispose(s, event, bank=args.backup)
            if outcome == "took":
                taken.append((label, status))
            elif outcome == "unresolved":
                unresolved.append((event.id, status, label))
            else:
                disposed.append((event.id, outcome, status, label))
            # Flush so the next row's screen sees this one as retired.
            await s.flush()

        for label, status in taken:
            verb = "  took back " if args.apply else "  would take back "
            # The status it was swapped FROM is printed because after a retry it
            # is no longer the one `candidates()` selected on, and it is what the
            # undo restores.
            print(f"{verb}{label} (from '{status}')")
        for event_id, outcome, status, label in disposed:
            print(f"  LEFT ALONE ({_WHY_LEFT_ALONE[outcome]}, now '{status}'): {label}")
        for event_id, status, label in unresolved:
            print(f"  NOT TAKEN BACK, still '{status}' beside its canonical: {label}")

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
            if unresolved:
                # The plan predicts the apply's EXIT CODE too, not just its
                # list. Its writes are discarded, so an unresolved row here is a
                # statement about the population rather than a change left
                # half-made — but it is the same statement, and an operator who
                # reads `$?` before the prose should learn it from the safe
                # invocation.
                print(
                    f"NOT CLEAN: {len(unresolved)} row(s) were rewritten by "
                    "something else faster than this pass could own them. The "
                    "apply would report the same."
                )
                return 1
            return 0

        await s.commit()

        # Read the column back rather than trusting the counters (hot-list #53).
        left = len(await candidates(s))
        print(
            f"done: took back {len(taken)}, left alone {len(disposed)}, "
            f"unresolved {len(unresolved)}, kept {kept} orphans; "
            f"{left} revived rows remain ahead of their kickoff"
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
        # unresolved ids are carried out of the loop and re-read BY ID, which no
        # population predicate can hide.
        if unresolved:
            from app.utils.event_completion import is_retired_event_status

            # An expanding bindparam rather than `= ANY(:ids)`: the same
            # statement then runs on Postgres and on the sqlite rail the race
            # test drives the real loop over, so the reporting path a lost race
            # depends on is covered by a test instead of being the one branch
            # that only production ever executes.
            #
            # And it is read AFTER the commit, not reused from the loop: the
            # verdict this pass leaves behind has to be a statement about the
            # committed database. A row something else retired in the meantime
            # is resolved however it got there, and saying otherwise would make
            # the exit code fire on a screen that is already correct.
            ids_unresolved = [event_id for event_id, _s, _l in unresolved]
            now_status = dict(
                (
                    await s.execute(
                        text("SELECT id, status FROM events WHERE id IN :ids").bindparams(
                            bindparam("ids", expanding=True)
                        ),
                        {"ids": ids_unresolved},
                    )
                ).all()
            )
            still_visible = [
                event_id
                for event_id in ids_unresolved
                if event_id in now_status
                and not is_retired_event_status(now_status[event_id])
            ]
            print(
                f"NOT CLEAN: {len(still_visible)} row(s) kept moving under this "
                f"pass and are STILL on the site beside their canonical row. "
                f"They are absent from the {left} above because they are no "
                "longer 'scheduled'."
            )
            for event_id in ids_unresolved:
                print(f"  {event_id} is now '{now_status.get(event_id, 'deleted')}'")
            print(
                f"Each was re-attempted {LOST_RACE_ATTEMPTS} times against the "
                "status it had actually moved to, and something rewrote it every "
                "time. Re-run the script: the population is defined by the "
                "#7260 arm's ledger, not by 'scheduled', so a started game is "
                "still reachable by a later pass."
            )
            if still_visible:
                # 🔴 THE EXIT CODE IS THE PART A WRAPPER READS. Printing NOT
                # CLEAN and returning 0 told a human the truth and everything
                # else the opposite (CERT-3197).
                return 1
            print("...and all of them have since been retired by another arm.")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="create/top up the bank")
    p.add_argument("--apply", action="store_true", help="take the twins back")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
