"""#7501 — drain the slug-less clubs now instead of waiting for the beat.

    heroku run:detached -a bainluck -- python3 scripts/repair_7501_clubs_without_a_slug_have_no_page.py
    heroku run:detached -a bainluck -- python3 scripts/repair_7501_clubs_without_a_slug_have_no_page.py --backup
    heroku run:detached -a bainluck -- python3 scripts/repair_7501_clubs_without_a_slug_have_no_page.py --backup --apply

Undo: ``restore_7501_clubs_without_a_slug_have_no_page.py --apply``.

THIS SCRIPT IS THE SHIP'S ONE ATTENDED STEP, NOT A SHORTCUT PAST THE BEAT

``backfill-team-slugs`` fires three times an hour and calls exactly the function
this script calls, but it **refuses to write until this script's ``--backup``
has run once**, because a beat is an unattended production write and D51(b) buys
one with a backup taken first. So the order is fixed and the beat cannot skip it:

  1. ``--backup`` creates ``backup_7501_team_slug_fill`` — the one place that
     table is ever created, runtime DDL on the named app invoked by a person
     (notice 47(c)). From that moment the beat is unblocked and banks every row
     it writes, so the restore covers the beat's work as well as this script's.
  2. ``--backup --apply`` drains the whole backlog now instead of over the next
     three hours. Optional: after step 1 the beat gets there on its own.

``--apply`` without ``--backup`` is refused outright rather than quietly
proceeding — the bank is the precondition of the write, so an operator who omits
it has asked for the one thing the rule forbids (CERT-3171).

A readable plan is the default. A bare run writes nothing and prints the rung
distribution, so what the fill is about to do is checkable in one read rather
than inferred from a row count afterwards.

WHAT THE WRITE ACTUALLY IS

``UPDATE teams SET slug = :s WHERE id = :i AND slug IS NULL``, each one banked in
the same savepoint. No existing slug moves, so no URL that resolves today stops
resolving; the only observable change is that a page which 404'd starts
rendering. A row the ladder cannot place keeps its NULL and is reported, not
guessed at.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.team_slug_backfill import (  # noqa: E402
    BANK_TABLE,
    fill_missing_team_slugs,
)
from app.utils.team_slug import url_league_segment  # noqa: E402

#: The app whose database this repair belongs to. See notice 48.
PRODUCER_APP = "bainluck"

#: One apply pass. The whole population is ~4,000 rows, so this is three or four
#: transactions rather than one long-held lock on a table the ESPN sync writes.
BATCH = 1000


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
    two flags are kept separate rather than ``--apply`` silently implying
    ``--backup`` because the operator's command line is the record of what was
    authorised: a run that banks has to say so.
    """
    if getattr(args, "apply", False) and not getattr(args, "backup", False):
        return (
            "REFUSING to write: --apply requires --backup. The bank is what "
            "makes this fill reversible in one command, so it is the "
            "precondition of the write and not an option beside it. "
            "Re-run with `--backup --apply`."
        )
    return None


async def ensure_bank(s) -> None:
    """Create the bank and its key. Idempotent; safe to call on every run.

    ``team_id`` and ``slug_after`` take their types from the columns they mirror
    (#6215's lesson: one hand-typed column made a backup unrunnable, which made
    ``--apply`` refuse forever). The key is ``team_id`` alone — one club, one
    slug — so re-running ``--backup`` after a partial fill tops the table up
    rather than duplicating it.

    There is deliberately no ``slug_before`` column. Every row this mechanism
    can touch has ``slug IS NULL`` by construction, so a "before" column would
    be a column of NULLs asserting something the ``WHERE`` clause already
    guarantees.
    """
    from sqlalchemy import text

    await s.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BANK_TABLE} AS "
            "SELECT id AS team_id, slug AS slug_after, now() AS taken_at "
            "FROM teams WHERE false"
        )
    )
    await s.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {BANK_TABLE}_pk "
            f"ON {BANK_TABLE} (team_id)"
        )
    )
    await s.commit()


def print_plan(pairs, rows_by_id) -> None:
    """The rung each row lands on, which is the thing worth checking.

    Rung 1 is the club that simply never had a slug. Rung 2 means another sport
    already holds its clean name — the 855-row cohort — and the suffix has to be
    the URL's league segment, not the migration's token, or the page it mints is
    one the frontend never links to.
    """
    rungs: Counter = Counter()
    for team_id, slug in pairs:
        name_slug, sport_key = rows_by_id.get(team_id, ("", None))
        segment = url_league_segment(sport_key)
        if slug == name_slug:
            rungs["1 clean name"] += 1
        elif segment and slug == f"{name_slug}-{segment}":
            rungs["2 name + league segment"] += 1
        elif slug.endswith(f"-{team_id}"):
            rungs["3 name + id"] += 1
        else:
            rungs["4 team-id"] += 1

    for rung, n in sorted(rungs.items()):
        print(f"  rung {rung}: {n}")
    for team_id, slug in pairs[:10]:
        print(f"    {team_id} -> {slug}")
    if len(pairs) > 10:
        print(f"    … and {len(pairs) - 10} more")


async def run(args) -> int:
    from sqlalchemy import func, select

    from app.models.models import Sport, Team
    from app.tasks.base import get_task_session
    from app.utils.slugify import slugify

    for refusal in (missing_backup_refusal(args), wrong_app_refusal(args)):
        if refusal:
            print(refusal)
            return 2

    async with get_task_session() as s:
        total = (await s.execute(select(func.count()).select_from(Team))).scalar_one()
        missing = (
            await s.execute(
                select(func.count()).select_from(Team).where(Team.slug.is_(None))
            )
        ).scalar_one()
        print(
            f"teams: {total} rows, {missing} with no slug ({missing * 100 // max(total, 1)}%)"
        )

        # The bank FIRST, and before the drained-backlog return below. Creating
        # it is what unblocks the beat, and the beat's job outlives this
        # backlog: every club `upsert_team` mints from here on is born with a
        # NULL slug. A `--backup` that no-opped because today's backlog happens
        # to be empty would leave the beat refusing forever on tomorrow's rows.
        if args.backup:
            from sqlalchemy import text

            await ensure_bank(s)
            banked = (
                await s.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
            ).scalar_one()
            print(f"{BANK_TABLE}: ready, {banked} rows banked so far")

        if not missing:
            print("Nothing to do: every club has a slug.")
            return 0

        # The plan, always — including on an --apply run, so the ledger the
        # operator reads is the one the write produced and not a second query.
        rows_by_id = {
            team_id: (slugify(name or ""), sport_key)
            for team_id, name, sport_key in (
                await s.execute(
                    select(Team.id, Team.name, Sport.key)
                    .join(Sport, Sport.id == Team.sport_id, isouter=True)
                    .where(Team.slug.is_(None))
                )
            ).all()
        }

        if not args.apply:
            stats = await fill_missing_team_slugs(s, limit=missing, dry_run=True)
            print(
                f"plan: {stats['written']} would be slugged, "
                f"{stats['unresolved']} unresolvable"
            )
            print_plan(stats["pairs"], rows_by_id)
            print("plan only. Re-run with --backup --apply.")
            return 0

        written, unresolved, errors = 0, 0, 0
        while True:
            stats = await fill_missing_team_slugs(s, limit=BATCH)
            written += stats["written"]
            unresolved += stats["unresolved"]
            errors += stats["errors"]
            print(
                f"pass: examined={stats['examined']} written={stats['written']} "
                f"unresolved={stats['unresolved']} errors={stats['errors']} "
                f"remaining={stats['remaining']} banked={stats['banked']}"
            )
            print_plan(stats["pairs"], rows_by_id)
            # Stop on a pass that moved nothing, not on `remaining == 0`: the
            # unresolvable tail keeps `remaining` non-zero forever and a loop
            # keyed on it would never exit.
            if stats["written"] == 0:
                break

        # Read the column back rather than trusting the counters (hot-list #53).
        left = (
            await s.execute(
                select(func.count()).select_from(Team).where(Team.slug.is_(None))
            )
        ).scalar_one()
        print(
            f"done: written={written} unresolved={unresolved} errors={errors}; "
            f"{left} clubs still have no slug"
        )
        return 0 if errors == 0 else 1


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="create/top up the bank")
    p.add_argument("--apply", action="store_true", help="write the slugs")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
