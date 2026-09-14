"""#6215 — take Arsenal's badge and record off 1,000 clubs that are not Arsenal.

------------------------------------------------------------------------------
WHAT A READER SEES
------------------------------------------------------------------------------
`https://bainluck.com`, search "Deportivo", 2026-09-14, 390px. The TEAMS block
returns Deportivo Achuapa (Guatemala), Deportivo Maipú (Argentina) and
Deportivo Universitario (Peru), each with a Premier-League-shaped record and a
crest placeholder reading **ARS**, **CHE**, **MNC**:

    id 4551  Deportivo Achuapa        ARS  19-7-3   soccer_epl
    id 4504  Deportivo Maipu          CHE  12-9-7   soccer_epl
    id 4229  Deportivo Universitario  MNC  18-5-5   soccer_epl
    id 4513  Fluminense               ARS  19-7-3   soccer_epl   location 'Arsenal'
    id  133  Arsenal                  ARS  4-0-0    soccer_epl   espn_id '359'

Filed by live/242 as 144 EPL rows. Measured over the whole `teams` table rather
than the one league it was spotted in: **1,077 rows carry ESPN identity fields
with no `espn_id`, and 1,014 of them wear a `location` that is another club's** —
the population this script selects, across four leagues. `Marist Red Foxes`
reads `OSU · 18-11 · Ohio State`; `Butler Bulldogs` reads
`OKST · 21-7 · Oklahoma State`.

The 63 it spares all read correct (`Oregon Ducks · Oregon`,
`Texas A&M Aggies · Texas A&M`), and getting that boundary right took two
attempts — see `location_corresponds`.

------------------------------------------------------------------------------
THE CAUSE IS FIXED IN CODE; THIS IS THE ROWS THAT CAUSE ALREADY WROTE
------------------------------------------------------------------------------
Two writers, and the second is why the population looks half-scrubbed.

``espn_helpers.upsert_team`` adopted the payload of a wrongly-matched ESPN
event. Its guard — ``if team.espn_id and team.espn_id != espn_team.espn_id`` —
exists for exactly that case and is gated on an id the row does not have, so it
could never fire for the row created twelve lines above it. The commit this
script ships with adds the arm that can: the payload's NAMES must correspond,
and if they do not the row is not even created.

``espn_sync._cleanup_bad_espn_matches`` then DETECTED those bad matches and
cleared ``espn_id``, logos, colours and ``alternate_names`` — and left
``abbreviation``, ``current_record`` and ``location``. That is precisely and
only what row 4513 still carries. It cleared the evidence and left the lie, and
it also put the population **out of its own reach**: it loads teams WITH an
``espn_id``, and these no longer have one. Nothing that runs today will find
them again. That is why a script exists at all.

------------------------------------------------------------------------------
🔴 WHAT THIS REPAIR CANNOT DO, MEASURED RATHER THAN ASSERTED
------------------------------------------------------------------------------
**It does not clear the `· EPL` caption, and no repair of the `teams` table
can.** That caption is ``sport_key`` in the search payload, which is
``teams.sport_id``, which came from ``event.sport_id`` — and the events are
themselves mis-sported:

    6606783  Fluminense v Vasco          2026-03-01  soccer_epl  espn_id NULL
    6606836  Colo Colo v U. De Chile     2026-03-01  soccer_epl  espn_id NULL
    6606692  Argentinos Jrs v Barracas   2026-03-01  soccer_epl  espn_id NULL

`soccer_epl` holds **2,249 events, 2,104 of them before June and 2,060 with no
ESPN id** — a cohort of foreign fixtures ingested under the Premier League in
Feb–May 2026. Repairing the club's sport would mean deriving the right one, and
for **740 of the 1,077 rows there is no same-named row under any other sport**
to derive it from (319 have one; 18 are orphans with no events at all).

So this script removes the borrowed BADGE, RECORD, LOCATION, crest and aliases
— the fields one writer put there and the other failed to take back — and the
mis-sported events remain a separate, larger defect with its own issue. Saying
that here rather than quietly shipping a repair whose headline is false is the
whole point of this section.

------------------------------------------------------------------------------
RUNBOOK
------------------------------------------------------------------------------
Attended, D51, and in this order. Read the plan before applying it.

    heroku run:detached -a bainluck -- python3 backend/scripts/repair_6215_borrowed_espn_identity.py
    heroku run:detached -a bainluck -- python3 backend/scripts/repair_6215_borrowed_espn_identity.py --backup
    heroku run:detached -a bainluck -- python3 backend/scripts/repair_6215_borrowed_espn_identity.py --backup --apply

Undo, one command:

    heroku run:detached -a bainluck -- python3 backend/scripts/restore_6215_borrowed_espn_identity.py --apply

`heroku run` without `:detached` fails silently in the sandbox (gotcha #48) —
verify by re-reading the rows about sixty seconds later, never by trusting an
empty stdout.

Writes refuse anywhere but ``bainluck``. ESPN sync is NOT in ``HEAVY_TASKS``
(membership tested by import: the 28-entry set contains no ESPN task at all),
so the producer is the main app and there is no heavy-release precondition —
unlike #5982, whose runbook opens with one.

``CREATE TABLE IF NOT EXISTS backup_6215_borrowed_espn_identity`` is runtime DDL
behind ``--backup``, invoked by a person, on a named app. Notice 47(c): the
invocation is the attended step, so this is not migration-class.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS  # noqa: E402
from app.utils.name_normalization import names_match, normalize_name  # noqa: E402

#: The app whose deploy carries the writer fix. ESPN sync runs on the main app.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_6215_borrowed_espn_identity"

#: Candidates: an ESPN-sourced identity with no ESPN id to justify it. The
#: correspondence test below is what separates a borrowed identity from a
#: legitimate row whose id happens to have been cleared.
_CANDIDATE_SQL = """
SELECT t.id,
       t.name,
       t.abbreviation,
       t.current_record,
       t.location,
       t.alternate_names,
       s.key AS sport_key
  FROM teams t
  JOIN sports s ON s.id = t.sport_id
 WHERE t.espn_id IS NULL
   AND (t.location IS NOT NULL
        OR t.abbreviation IS NOT NULL
        OR t.current_record IS NOT NULL)
 ORDER BY t.id
"""


def location_corresponds(name, location) -> bool:
    """Is ``location`` this club's own, rather than another club's?

    ``names_match`` alone is WRONG here, and measuring it is what found that.
    ESPN's ``location`` is the school or city and ``name`` is usually the
    mascot form, so the two differ by a trailing nickname — and ``names_match``
    refuses prefix containment on purpose ("South Carolina" must not match
    "South Carolina State"). That refusal is right for its own question and
    fatal for this one:

        names_match("Evansville Purple Aces", "Evansville")  -> False
        names_match("Duke Blue Devils",       "Duke")        -> False

    Both are correct rows. Measured over all 2,511 rows carrying a location, the
    bare `names_match` test called **1,017** of the 1,077 candidates borrowed;
    adding word-boundary prefix containment in either direction brings it to
    **1,014** and — more to the point — moves `Evansville Purple Aces`,
    `Duke Blue Devils`, `Oregon Ducks`, `Texas A&M Aggies` and 59 others out of
    the population. Every one of the 63 spared reads correct; the first twelve
    borrowed read `Butler Bulldogs · Oklahoma State`, `SMU Mustangs · Iowa`,
    `Marshall Thundering Herd · Eastern Michigan`.

    PREFIX, not substring. "Michigan" must not be admitted by "Eastern
    Michigan": ESPN composes `display_name` as ``location + " " + name``, so the
    location is a LEADING run of whole words or it is somebody else's.
    """
    if not name or not location:
        # Nothing to compare is not evidence of a lie — see `identity_is_borrowed`.
        return True
    if names_match(name, location):
        return True
    ours = normalize_name(name).split()
    theirs = normalize_name(location).split()
    if not ours or not theirs:
        return True
    return ours[: len(theirs)] == theirs or theirs[: len(ours)] == ours


def identity_is_borrowed(name, location, alternate_names=None) -> bool:
    """Does this row's stored ESPN identity name a DIFFERENT club?

    The same question ``espn_helpers.espn_identity_corresponds`` asks of a
    PAYLOAD, asked of a ROW. One difference, and it is deliberate:
    ``alternate_names`` is NOT admitted as evidence here. On the writer's side
    the aliases are OURS and the names are ESPN's, so the comparison is between
    two independent sources. On a stored row BOTH were written by the same
    adoption, so letting the aliases vouch for the location is circular — and
    measurably so: rows 173 and 197 carry a mixture of their own names and the
    borrowed club's (``Marshall Thundering Herd`` holds `Michigan Wolverines`,
    `SMU Mustangs` holds `Iowa Hawkeyes`), and admitting aliases would let
    exactly those half-contaminated rows certify themselves as clean. The
    parameter is kept so the signature reads like the writer's and so a caller
    passing it is not silently wrong.

    Fail-OPEN, the opposite of the writer's default and for the opposite
    reason: this one holds the UPDATE. The writer refuses on silence because
    its cost is a missing crest; a repair that cleared on silence would erase
    legitimate rows whose only sin is a null ``location``.
    """
    return not location_corresponds(name, location)


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
            "of an unattended write, and the undo reads "
            f"{BACKUP_TABLE}."
        )
        return 2

    async with get_task_session() as s:
        rows = (await s.execute(text(_CANDIDATE_SQL))).all()
        borrowed = [
            r for r in rows if identity_is_borrowed(r.name, r.location, r.alternate_names)
        ]

        print(f"candidates (ESPN identity, no espn_id): {len(rows)}")
        print(f"borrowed (name does not correspond):    {len(borrowed)}")
        if not rows:
            print(
                "REFUSING: zero candidates. Either the repair has already run or "
                "the query no longer matches the schema — a clean zero over a "
                "population this size is a broken read, not a healthy table."
            )
            return 2

        by_sport: dict[str, int] = {}
        for r in borrowed:
            by_sport[r.sport_key] = by_sport.get(r.sport_key, 0) + 1
        for key, n in sorted(by_sport.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>5}  {key}")

        print("\nsample (first 10):")
        for r in borrowed[:10]:
            print(
                f"  {r.id:>7}  {r.name!r:<34} {r.abbreviation!r:<8} "
                f"{r.current_record!r:<10} location={r.location!r}"
            )

        print(
            "\nNOT repaired by this script, by measurement: the sport. "
            f"{len(borrowed)} rows keep their current sport_key, so a row minted "
            "under soccer_epl still reads '· EPL' in search. See this file's "
            "header — the events are mis-sported too and the right sport is not "
            "derivable from the row for most of them."
        )

        if not (args.backup or args.apply):
            print("\nplan only. Re-run with --backup, then --backup --apply.")
            return 0

        ids = [r.id for r in borrowed]

        if args.backup:
            await s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
                    "  team_id integer PRIMARY KEY,"
                    "  abbreviation text,"
                    "  current_record text,"
                    "  location text,"
                    "  logo_url_small text,"
                    "  logo_url_large text,"
                    "  primary_color text,"
                    "  secondary_color text,"
                    "  alternate_names text[],"
                    "  taken_at timestamptz NOT NULL DEFAULT now()"
                    ")"
                )
            )
            await s.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} "
                    "(team_id, abbreviation, current_record, location,"
                    " logo_url_small, logo_url_large, primary_color,"
                    " secondary_color, alternate_names) "
                    "SELECT id, abbreviation, current_record, location,"
                    " logo_url_small, logo_url_large, primary_color,"
                    " secondary_color, alternate_names "
                    "FROM teams WHERE id = ANY(:ids) "
                    "ON CONFLICT (team_id) DO NOTHING"
                ),
                {"ids": ids},
            )
            await s.commit()
            banked = (
                await s.execute(text(f"SELECT count(*) FROM {BACKUP_TABLE}"))
            ).scalar_one()
            print(f"\nbacked up: {banked} rows in {BACKUP_TABLE}")
            if banked < len(ids):
                print(
                    "REFUSING to apply: the backup holds fewer rows than the plan. "
                    "An undo that cannot restore every row it is about to change "
                    "is not an undo."
                )
                return 2

        if args.apply:
            sets = ", ".join(f"{f} = NULL" for f in ESPN_SOURCED_IDENTITY_FIELDS)
            result = await s.execute(
                text(f"UPDATE teams SET {sets} WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
            await s.commit()
            # Read back from disk rather than trusting rowcount (gotcha #53).
            still = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM teams "
                        "WHERE id = ANY(:ids) AND (abbreviation IS NOT NULL "
                        "OR current_record IS NOT NULL OR location IS NOT NULL)"
                    ),
                    {"ids": ids},
                )
            ).scalar_one()
            print(f"\napplied: {result.rowcount} rows; still carrying identity: {still}")
            return 0 if still == 0 else 1

    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    p.add_argument("--backup", action="store_true", help="bank the current values")
    p.add_argument("--apply", action="store_true", help="write the repair")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
