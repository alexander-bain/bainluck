"""#7188 — 32 futures legs wear a same-city rival's identity.

------------------------------------------------------------------------------
WHAT A READER SEES
------------------------------------------------------------------------------
`https://bainluck.com`, "MLB World Series Champion 2026", 2026-09-19. The Mets
leg carries the YANKEES' crest and links to the Yankees' team page. The same
substitution runs through nine live baseball markets and the NFL's division and
championship ladders:

    market 114584  MLB World Series Champion 2026   'New York Mets'   -> 6610 Yankees
    market    268  NL East Division Winner          'New York M'      -> 6610 Yankees
    market    275  Pro Baseball Champion            'Los Angeles D'   -> 10712 Angels
    market  53675  AFC West Division Winner         'Los Angeles C'   ->   544 Rams
    market  40533  2027 Pro Football Champion       'Los Angeles C'   ->   544 Rams

32 legs, three families. The issue reported the Mets one; measuring the whole
`futures_outcomes` table rather than the market it was spotted in found the
Dodgers and Chargers families too, and the Chargers family is the largest.

------------------------------------------------------------------------------
THE CAUSE IS ALREADY FIXED IN CODE; THIS IS THE ROWS THAT CAUSE ALREADY WROTE
------------------------------------------------------------------------------
🔴 **The issue's stated cause is stale, and that is why a repair exists rather
than a matcher change.** #7188 says `New York M` binds to the Yankees today via
the bare `New York` alias. It does not: running the DEPLOYED
``match_outcome_to_team`` against the real `teams` rows returns **None** — both
6610 and 10737 carry a bare `New York` alias, so the ambiguity guard already
refuses the fragment. These 32 rows are **historical write-once residue** from
before that guard, and nothing that runs today would write them again or take
them back. ``futures_outcomes.team_id`` is filled by a drain that selects
``team_id IS NULL``; a row that is already (wrongly) bound is out of its reach
forever. That is the whole reason this file exists.

The live half of #7188 is the opposite sign — the same bare-city alias defeats
the EXACT club name, so `'New York Yankees'` also returns None and 862 legs sit
unbound — and it is fixed in code by PR #7301, not here.

------------------------------------------------------------------------------
🔴 WHAT THIS REPAIR DOES NOT TOUCH, AND WHY
------------------------------------------------------------------------------
**The 12 legs bound to team 12649.** That row's `name` IS the fragment
`'Los Angeles C'` (sport 2, NBA; the real Clippers are 537). Repointing a leg
off it would leave the bad `teams` row behind to be matched again, so it is a
wrong-identity row-class defect — the same class as #7262 arm 3 — and it is not
this script's population. The SPORT guard below is what keeps it out
structurally rather than by my remembering to exclude it: see `plan_violations`.

**The one leg bound to team 863.** 863 is `New York Mets` under sport 33178,
`baseball_mlb_preseason`. Every MLB club has a preseason twin at a LOWER id, so
a name lookup for "New York Mets" returns 863 before it returns 10737 — and
that is exactly how a repair like this one picks the wrong target. Encoded as a
guard rather than a comment: a repoint whose source and target disagree on
`sport_id` is refused.

------------------------------------------------------------------------------
RUNBOOK
------------------------------------------------------------------------------
Attended, D51(b), in this order. Read the plan before applying it.

    heroku run:detached -a bainluck -- python3 scripts/repair_7188_futures_leg_bound_to_a_city_sibling.py
    heroku run:detached -a bainluck -- python3 scripts/repair_7188_futures_leg_bound_to_a_city_sibling.py --backup
    heroku run:detached -a bainluck -- python3 scripts/repair_7188_futures_leg_bound_to_a_city_sibling.py --backup --apply

Undo, one command:

    heroku run:detached -a bainluck -- python3 scripts/restore_7188_futures_leg_bound_to_a_city_sibling.py --apply

`heroku run` without `:detached` fails silently in the sandbox (gotcha #48) —
verify by re-reading the rows about sixty seconds later, never by trusting an
empty stdout.

Writes refuse anywhere but ``bainluck``. ``_backfill_team_links`` is NOT in
``HEAVY_TASKS`` (membership tested by import: the 28-entry set holds no
team-linking backfill), so the producer is the main app and there is no
heavy-release precondition — unlike #5982, whose runbook opens with one.

``CREATE TABLE IF NOT EXISTS backup_7188_futures_leg_city_sibling`` is runtime
DDL behind ``--backup``, invoked by a person, on a named app. Notice 47(c): the
invocation is the attended step, so this is NOT migration-class. Its column
types are derived from `futures_outcomes` by ``CREATE TABLE AS SELECT ... WHERE
false`` rather than declared by hand — #6215's backup was unrunnable for a week
because one hand-typed column disagreed with the model.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: The app whose deploy carries the writer. `_backfill_team_links` runs on the
#: main app; see the header for the HEAVY_TASKS membership test.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_7188_futures_leg_city_sibling"


@dataclass(frozen=True)
class Repoint:
    """One family: legs named ``leg_names``, bound to ``wrong``, belong to ``right``.

    An explicit table, not a re-derivation. The matcher cannot be asked to
    redo this: `'New York M'` is a TRUNCATED fragment that no correct matcher
    will ever bind (PR #7301 deliberately keeps refusing it), so the only
    honest way to say where these rows belong is to say it, with the evidence
    in `why`, and then let `plan_violations` check the claim against the live
    `teams` rows rather than trusting the ids I typed.
    """

    leg_names: tuple[str, ...]
    wrong: int
    right: int
    why: str


REPOINTS: tuple[Repoint, ...] = (
    Repoint(
        leg_names=("New York M", "New York Mets"),
        wrong=6610,  # New York Yankees
        right=10737,  # New York Mets  (NOT 863 — that is the preseason twin)
        why="9 legs incl. MLB World Series Champion 2026 and NL East Division Winner",
    ),
    Repoint(
        leg_names=("Los Angeles D",),
        wrong=10712,  # Los Angeles Angels
        right=10707,  # Los Angeles Dodgers
        why="8 legs incl. Pro Baseball Champion and NL West Division Winner",
    ),
    Repoint(
        leg_names=("Los Angeles C",),
        wrong=544,  # Los Angeles RAMS — the issue's own table says Chargers, and is wrong
        right=556,  # Los Angeles Chargers
        why="15 legs incl. AFC West Division Winner and 2027 Pro Football Champion",
    ),
)


def is_prefix_of(leg_name: str, club_name: str) -> bool:
    """Is ``leg_name`` a leading whole-word run of ``club_name``?

    The venue truncates a club to a fixed width (`'New York M'`,
    `'Los Angeles D'`), so a leg name is a PREFIX of its club's name or it is
    somebody else's. Substring would be wrong in the usual direction and also
    in an unusual one: "Angeles D" is a substring of "Los Angeles Dodgers" and
    names no club at all.

    Character prefix, not word prefix, because the truncation cuts mid-word by
    construction — `'New York M'` must be admitted by `'New York Mets'`.
    """
    if not leg_name or not club_name:
        return False
    return club_name.casefold().startswith(leg_name.casefold())


def plan_violations(repoints, teams_by_id) -> list[str]:
    """Check every repoint against the live `teams` rows. Empty list = safe.

    Three guards, and each one is a mistake that was actually available while
    writing this file:

    1. **The target's name must start with the leg name.** Catches a mistyped
       target id. It is also the positive evidence that the repoint is right at
       all: `'Los Angeles C'` starts `'Los Angeles Chargers'`.
    2. **The current binding's name must NOT start with the leg name.** This is
       what makes the row a DEFECT rather than my opinion — `'Los Angeles C'`
       does not start `'Los Angeles Rams'`. Without this arm the script would
       happily "repair" correctly-bound rows.
    3. **Source and target must agree on `sport_id`.** The preseason-twin trap
       (863 vs 10737). It also, and separately, is the only guard that keeps
       team 12649 out: 12649 is literally NAMED `'Los Angeles C'`, so guard 1
       would admit it as a target — it fails only on sport (2 vs 1). Two guards
       are load-bearing for one row; neither alone is enough.
    """
    problems: list[str] = []
    for rp in repoints:
        src = teams_by_id.get(rp.wrong)
        dst = teams_by_id.get(rp.right)
        if src is None or dst is None:
            missing = rp.wrong if src is None else rp.right
            problems.append(f"team {missing} does not exist")
            continue
        if src.sport_id != dst.sport_id:
            problems.append(
                f"{rp.wrong} ({src.name}, sport {src.sport_id}) and "
                f"{rp.right} ({dst.name}, sport {dst.sport_id}) are different "
                f"sports — preseason twin or wrong-identity row"
            )
        for leg in rp.leg_names:
            if not is_prefix_of(leg, dst.name):
                problems.append(
                    f"{leg!r} is not a prefix of target {rp.right} ({dst.name!r})"
                )
            if is_prefix_of(leg, src.name):
                problems.append(
                    f"{leg!r} IS a prefix of current {rp.wrong} ({src.name!r}) — "
                    f"that binding is not obviously wrong, refusing to move it"
                )
    return problems


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app.

    THE UNDO IMPORTS THIS, so a restore — a production write in the opposite
    direction, and the one most likely to be typed in a hurry — earns the
    identical gate. ``getattr`` because the undo's parser defines no
    ``--backup``.

    UNSET refuses too. Unset means a laptop pointed at the production database
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


#: Candidate legs, per family. `name = ANY(:legs)` is exact — these are stored
#: venue labels, not free text, and a LIKE here would sweep in every club whose
#: name merely starts the same way.
_CANDIDATE_SQL = """
SELECT fo.id AS outcome_id,
       fo.market_id,
       fo.name,
       fo.team_id,
       fm.name AS market_name,
       fm.status,
       (SELECT count(*) FROM futures_outcomes o2
         WHERE o2.market_id = fo.market_id AND o2.team_id = :right) AS on_target
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
 WHERE fo.team_id = :wrong
   AND fo.name = ANY(:legs)
 ORDER BY fo.market_id
"""


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    if args.apply and not args.backup:
        print(
            "REFUSING: --apply without --backup. D51 makes the backup the price "
            f"of an unattended write, and the undo reads {BACKUP_TABLE}."
        )
        return 2

    async with get_task_session() as s:
        team_ids = sorted({i for rp in REPOINTS for i in (rp.wrong, rp.right)})
        team_rows = (
            await s.execute(
                text("SELECT id, name, sport_id FROM teams WHERE id = ANY(:ids)"),
                {"ids": team_ids},
            )
        ).all()
        teams_by_id = {r.id: r for r in team_rows}

        problems = plan_violations(REPOINTS, teams_by_id)
        if problems:
            print("REFUSING: the repoint table disagrees with the live teams rows.")
            for p in problems:
                print(f"  - {p}")
            return 2

        plan: list[tuple[int, int, int]] = []  # (outcome_id, from, to)
        collisions: list[str] = []

        for rp in REPOINTS:
            src, dst = teams_by_id[rp.wrong], teams_by_id[rp.right]
            rows = (
                await s.execute(
                    text(_CANDIDATE_SQL),
                    {"wrong": rp.wrong, "right": rp.right, "legs": list(rp.leg_names)},
                )
            ).all()
            print(f"\n{src.name} ({rp.wrong}) -> {dst.name} ({rp.right}): {len(rows)} legs")
            print(f"  {rp.why}")
            for r in rows:
                if r.on_target:
                    # 🔴 Measured clean on 2026-09-19 (0/32), and checked at RUN
                    # time anyway: between the measurement and the apply, the
                    # drain or a venue re-ingest can add the correct leg, and
                    # repointing onto it would put two legs for one club on one
                    # market — a ladder that double-counts a team.
                    collisions.append(
                        f"  SKIP  outcome {r.outcome_id} market {r.market_id} "
                        f"{r.name!r}: {dst.name} already has a leg there"
                    )
                    continue
                plan.append((r.outcome_id, r.team_id, rp.right))
                print(
                    f"    {r.outcome_id:>9}  market {r.market_id:<7} {r.name!r:<16} "
                    f"[{r.status}] {r.market_name}"
                )

        if collisions:
            print("\ncollisions skipped (target already on that market):")
            for c in collisions:
                print(c)

        print(f"\nplan: {len(plan)} legs to repoint, {len(collisions)} skipped")

        if not plan:
            print(
                "REFUSING: zero legs to repoint. Either the repair has already "
                "run or the query no longer matches the schema — a clean zero "
                "here is a broken read, not a healthy table."
            )
            return 2

        if not (args.backup or args.apply):
            print("\nplan only. Re-run with --backup, then --backup --apply.")
            return 0

        ids = [p[0] for p in plan]

        if args.backup:
            # Types derived from `futures_outcomes`, never declared (#6215's
            # lesson: one hand-typed column made that backup unrunnable, which
            # made --apply refuse forever). Both columns are the team FK, so
            # both are selected from `team_id`.
            await s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
                    "SELECT id AS outcome_id, market_id, name AS leg_name,"
                    " team_id AS team_id_before, team_id AS team_id_after,"
                    " now() AS taken_at "
                    "FROM futures_outcomes WHERE false"
                )
            )
            # CTAS carries no constraints, so the ON CONFLICT below needs this.
            # Idempotent: re-running --backup is safe.
            await s.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {BACKUP_TABLE}_pk "
                    f"ON {BACKUP_TABLE} (outcome_id)"
                )
            )
            for outcome_id, before, after in plan:
                await s.execute(
                    text(
                        f"INSERT INTO {BACKUP_TABLE} "
                        "(outcome_id, market_id, leg_name, team_id_before, team_id_after) "
                        "SELECT id, market_id, name, :before, :after "
                        "FROM futures_outcomes WHERE id = :id "
                        "ON CONFLICT (outcome_id) DO NOTHING"
                    ),
                    {"id": outcome_id, "before": before, "after": after},
                )
            await s.commit()
            banked = (
                await s.execute(
                    text(
                        f"SELECT count(*) FROM {BACKUP_TABLE} "
                        "WHERE outcome_id = ANY(:ids)"
                    ),
                    {"ids": ids},
                )
            ).scalar_one()
            print(f"\nbacked up: {banked} of {len(ids)} planned rows in {BACKUP_TABLE}")
            if banked < len(ids):
                print(
                    "REFUSING to apply: the backup holds fewer rows than the plan. "
                    "An undo that cannot restore every row it is about to change "
                    "is not an undo."
                )
                return 2

        if args.apply:
            moved = 0
            for outcome_id, _before, after in plan:
                result = await s.execute(
                    text("UPDATE futures_outcomes SET team_id = :to WHERE id = :id"),
                    {"to": after, "id": outcome_id},
                )
                moved += result.rowcount
            await s.commit()
            # Read back from disk rather than trusting rowcount (gotcha #53).
            stale = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM futures_outcomes "
                        "WHERE id = ANY(:ids) AND team_id = ANY(:wrong)"
                    ),
                    {"ids": ids, "wrong": [rp.wrong for rp in REPOINTS]},
                )
            ).scalar_one()
            print(f"\napplied: {moved} legs; still bound to a city sibling: {stale}")
            return 0 if stale == 0 else 1

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="bank the current bindings")
    p.add_argument("--apply", action="store_true", help="write the repair")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
