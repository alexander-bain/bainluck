"""#9017 — take another school's ESPN id, crest and record off 22 team rows.

------------------------------------------------------------------------------
WHAT A READER SEES
------------------------------------------------------------------------------
`https://bainluck.com/search?q=miami%20hurricanes`, 390px, 2026-09-27 02:33Z.
The Teams block lists "Miami (FL) — 35-15" and "Miami (OH) — 35-15", both with
the Hurricanes "U". Miami (OH) is the RedHawks. The row holds Miami's ESPN id:

    14629  'Miami (OH)'  espn_id 176  (ESPN 176 = Miami Hurricanes)
           alternate_names ['Miami Hurricanes', 'Miami', 'Hurricanes']

Same shape, measured over every one of the 1,607 team rows holding an ESPN id
(production 2026-09-27 02:5xZ): `Florida` holds North Florida's id and `North
Florida` holds Florida's; `Texas State` holds Texas's; `Oregon State` Oregon's;
`Kansas State` Kansas's; and two FCS football rows playing this season,
`Bethune-Cookman Wildcats` (Davidson's id) and `South Carolina State Bulldogs`
(Drake's). 22 rows in all, 20 of them NCAA baseball.

------------------------------------------------------------------------------
THE VERDICT: THE ROW'S OWN NAME NAMES A DIFFERENT ESPN CLUB
------------------------------------------------------------------------------
#7419 closed this class for the eight leagues it measured, and only on the
writer's rename arm, which fires when a payload for the row's OWN club arrives.
College baseball is out of season until February, so no such payload is coming
and the rows stay sealed.

The house correspondence predicate cannot decide these rows — it is the reason
they exist. `espn_identity_corresponds('Texas State', None, <Texas Longhorns>)`
is True: ESPN's short name for Texas is `Texas`, which sits inside `Texas State`
with nothing distinctive left on ESPN's side, so the rival veto does not fire.
`Miami (OH)` against `Miami` is the same subset shape. Tightening that on token
shape alone was measured and rejected: a "qualifier word" veto refuses the right
club on 13 of 1,607 rows (`Nicholls State`/`Nicholls`, `Miami (FL)`/`Miami`,
`Queens (NC)`/`Queens University`), because ESPN drops `State` and parentheticals
for some schools and not others. Token shape cannot tell `Texas State` from
`Nicholls State`.

ESPN's own directory can. `Texas State` is the exact name of a DIFFERENT ESPN
team (Texas State Bobcats); `Nicholls State` names no other team. So a
row is foreign only on positive evidence, both halves required:

1. its name does not name the club its stored id belongs to (neither
   ``espn_payload_renames_the_stored_id`` nor a light-normalized form), and
2. its name IS one of the names of another team in the same ESPN directory.

Light normalization (case, punctuation, whitespace) and not ``normalize_name``:
the latter strips a trailing ``c``, which makes the #6974 fragment row
`Los Angeles C` (id 12, the Clippers, correct) read as `los angeles`, the
Lakers' location. Under light normalization it names no other team and stays.

The full ESPN directory is read with ``limit=1000``; ``get_teams`` asks for 100,
and college baseball lists 437.

------------------------------------------------------------------------------
WHAT THIS DOES NOT DO
------------------------------------------------------------------------------
* The writer hole stays. A new id-less row can still take a flagship's payload
  through the subset shape above. Fixing it needs the directory at write time.
* Rows whose foreign id names a club spelled unlike any other ESPN team stay
  (`Appalachian St Mountaineers` holding Mount St. Mary's). Precision first:
  this rail holds an UPDATE.
* Leagues ESPN serves no directory for (NCAA lacrosse returns 0 teams) are
  skipped whole, and said so.

------------------------------------------------------------------------------
RUNBOOK
------------------------------------------------------------------------------
D51: a backup first, a one-command undo. Read the plan before applying it.

    heroku run:detached -a bainluck -- python3 scripts/repair_9017_foreign_espn_id.py
    heroku run:detached -a bainluck -- python3 scripts/repair_9017_foreign_espn_id.py --backup
    heroku run:detached -a bainluck -- python3 scripts/repair_9017_foreign_espn_id.py --backup --apply

Undo:

    heroku run:detached -a bainluck -- python3 scripts/restore_9017_foreign_espn_id.py --apply

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): verify by
re-reading the rows about sixty seconds later.

ESPN sync is not in ``HEAVY_TASKS``, so the producer is the main app. Writes
refuse anywhere but ``bainluck``. ``CREATE TABLE IF NOT EXISTS
backup_9017_foreign_espn_id`` is runtime DDL behind ``--backup``, invoked by a
person on a named app (notice 47(c)): not migration-class.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS  # noqa: E402
from app.utils.espn_helpers import espn_payload_renames_the_stored_id  # noqa: E402

#: ESPN sync runs on the main app.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_9017_foreign_espn_id"

#: Every row carrying an ESPN id. The verdict, not the query, picks the 22.
_CANDIDATE_SQL = """
SELECT t.id, t.name, t.espn_id, t.current_record, s.key AS sport_key
  FROM teams t
  JOIN sports s ON s.id = t.sport_id
 WHERE t.espn_id IS NOT NULL
 ORDER BY t.id
"""

#: The measured population is 22 (production, 2026-09-27). A verdict that
#: suddenly names many more is a misread directory or a changed ESPN payload,
#: not a bigger defect: the writes refuse and the plan says why.
MAX_FOREIGN_ROWS = 30

#: The fields the repair clears; the undo restores exactly these.
CLEARED_FIELDS = ("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)

#: Clears a row only while it still holds the id AND name the plan judged
#: (CERT-3604's follow-up). ESPN sync runs every few minutes on this app, so
#: a row can be re-enriched between the read and the write; that row is left
#: alone and reported, never cleared on a verdict about values it no longer has.
_APPLY_SQL = (
    "UPDATE teams AS t SET "
    + ", ".join(f"{f} = NULL" for f in CLEARED_FIELDS)
    + " FROM unnest(CAST(:ids AS integer[]), CAST(:espn_ids AS varchar[]),"
    " CAST(:names AS varchar[])) AS p(id, espn_id, name)"
    " WHERE t.id = p.id AND t.espn_id = p.espn_id AND t.name = p.name"
    " RETURNING t.id"
)

_PUNCT = re.compile(r"[.,'’]")
_SPACE = re.compile(r"\s+")


def light(name) -> str:
    """Case, punctuation and whitespace only — see the header for why not more."""
    return _SPACE.sub(" ", _PUNCT.sub("", (name or "").lower())).strip()


def espn_names(team) -> set[str]:
    """Every spelling ESPN uses for this club, light-normalized."""
    location = getattr(team, "location", None) or ""
    mascot = getattr(team, "name", None) or ""
    values = (
        getattr(team, "display_name", None),
        getattr(team, "short_name", None),
        getattr(team, "nickname", None),
        location,
        f"{location} {mascot}".strip(),
    )
    return {light(v) for v in values if v and light(v)}


def names_another_espn_club(name, owner, directory) -> list:
    """The OTHER ESPN teams this row's own name names; ``[]`` keeps the row.

    ``owner`` is the ESPN team the row's stored id belongs to. A row that names
    its owner is kept even if its name also names someone else — it is not
    wearing a foreign identity, whatever else is true of it.
    """
    ours = light(name)
    if not ours or owner is None:
        return []
    if espn_payload_renames_the_stored_id(name, owner) or ours in espn_names(owner):
        return []
    # The owner cannot appear here: a name in its spellings returned above.
    return [t for t in directory if ours in espn_names(t)]


async def fetch_directory(svc, sport_key):
    """The whole ESPN team directory for ``sport_key``, or ``None`` if unread.

    ``None`` covers no mapping, ESPN not answering, and an empty list: this
    verdict rests on the directory being complete, so a sport whose directory
    we could not see is skipped, never judged against nothing.
    """
    from app.services.espn_api import ESPN_API_BASE, ESPNAuthorityDark

    path = svc._get_espn_path(sport_key)
    if not path:
        return None
    sport, league = path
    try:
        data = await svc._get(f"{ESPN_API_BASE}/{sport}/{league}/teams?limit=1000")
    except ESPNAuthorityDark:
        return None
    raw = ((data or {}).get("sports") or [{}])[0].get("leagues") or [{}]
    teams = [svc._parse_team(t) for t in raw[0].get("teams", [])]
    teams = [t for t in teams if t]
    return teams or None


def plan(rows, directories) -> tuple[list, dict]:
    """``(foreign, skipped)``: the rows to clear and why others were not judged."""
    foreign, skipped = [], {}
    for r in rows:
        directory = directories.get(r.sport_key)
        if not directory:
            skipped[r.sport_key] = skipped.get(r.sport_key, 0) + 1
            continue
        owner = next((t for t in directory if t.espn_id == r.espn_id), None)
        if owner is None:
            skipped["(id not in directory)"] = skipped.get("(id not in directory)", 0) + 1
            continue
        others = names_another_espn_club(r.name, owner, directory)
        if others:
            foreign.append((r, owner, others))
    return foreign, skipped


def ceiling_refusal(n: int) -> str | None:
    """Refuse a write whose population is far past the measured one."""
    if n <= MAX_FOREIGN_ROWS:
        return None
    return (
        f"REFUSING to write: the verdict names {n} rows, the measured population "
        f"is 22 and the ceiling is {MAX_FOREIGN_ROWS}. Read the plan above; a "
        "directory that misread or changed shape makes right rows look foreign."
    )


def cas_params(foreign) -> dict:
    """The planned (id, espn_id, name) triples, as ``_APPLY_SQL`` binds them."""
    return {
        "ids": [r.id for r, _, _ in foreign],
        "espn_ids": [r.espn_id for r, _, _ in foreign],
        "names": [r.name for r, _, _ in foreign],
    }


def wrong_app_refusal(args) -> str | None:
    """Refuse a write from anywhere but the producer app; the undo imports this."""
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

    from app.services.espn_api import ESPNAPIService
    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2
    if args.apply and not args.backup:
        print(f"REFUSING: --apply without --backup. The undo reads {BACKUP_TABLE}.")
        return 2

    async with get_task_session() as s:
        rows = (await s.execute(text(_CANDIDATE_SQL))).all()
        print(f"candidates (team rows holding an ESPN id): {len(rows)}")
        if not rows:
            print("REFUSING: zero candidates is a broken read, not a clean table.")
            return 2

        svc = ESPNAPIService()
        directories = {}
        for key in sorted({r.sport_key for r in rows}):
            directories[key] = await fetch_directory(svc, key)
            n = len(directories[key]) if directories[key] else 0
            print(f"  directory {key:<32} {n:>4} teams")

        foreign, skipped = plan(rows, directories)
        for key, n in sorted(skipped.items()):
            print(f"  not judged: {n:>4} rows  {key}")
        print(f"\nforeign (name names a different ESPN club): {len(foreign)}")
        for r, owner, others in foreign:
            print(
                f"  {r.id:>7}  {r.sport_key:<28} {r.name!r:<34} "
                f"record={r.current_record!r:<9} holds {r.espn_id} "
                f"({owner.display_name}); names {[o.display_name for o in others]}"
            )

        if not (args.backup or args.apply):
            if ceiling_refusal(len(foreign)):
                print(f"\n{ceiling_refusal(len(foreign))}")
            print("\nplan only. Re-run with --backup, then --backup --apply.")
            return 0
        if not foreign:
            print("\nnothing to write.")
            return 0
        over = ceiling_refusal(len(foreign))
        if over:
            print(f"\n{over}")
            return 2

        ids = [r.id for r, _, _ in foreign]
        cols = ", ".join(CLEARED_FIELDS)

        if args.backup:
            # Types derived from `teams` (CERT-2880: a hand-typed backup schema
            # got `alternate_names` wrong and made #6215's repair unrunnable).
            await s.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
                    f"SELECT id AS team_id, {cols}, now() AS taken_at "
                    "FROM teams WHERE false"
                )
            )
            await s.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {BACKUP_TABLE}_pk "
                    f"ON {BACKUP_TABLE} (team_id)"
                )
            )
            await s.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} (team_id, {cols}) "
                    f"SELECT id, {cols} FROM teams WHERE id = ANY(:ids) "
                    "ON CONFLICT (team_id) DO NOTHING"
                ),
                {"ids": ids},
            )
            await s.commit()
            banked = (
                await s.execute(
                    text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE team_id = ANY(:ids)"),
                    {"ids": ids},
                )
            ).scalar_one()
            print(f"\nbacked up: {banked} of {len(ids)} rows in {BACKUP_TABLE}")
            if banked < len(ids):
                print("REFUSING to apply: the backup does not hold every planned row.")
                return 2

        if args.apply:
            written = sorted(
                (await s.execute(text(_APPLY_SQL), cas_params(foreign))).scalars().all()
            )
            await s.commit()
            moved = sorted(set(ids) - set(written))
            if moved:
                print(f"\nchanged since the plan, NOT written: {moved}")
            # Read back from disk, not rowcount (gotcha #53).
            still = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM teams WHERE id = ANY(:ids) "
                        "AND (espn_id IS NOT NULL OR current_record IS NOT NULL "
                        "OR logo_url_small IS NOT NULL)"
                    ),
                    {"ids": written},
                )
            ).scalar_one()
            print(f"\napplied: {len(written)} rows; still carrying identity: {still}")
            return 0 if still == 0 else 1

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="bank the current values")
    p.add_argument("--apply", action="store_true", help="write the repair")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
