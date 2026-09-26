"""#8949 — take other schools' ESPN identity off 55 college-baseball team rows.

THE SHIP: searching "cowboys" lists only clubs called Cowboys. Today the TEAMS
block also offers "Fresno State · 34-19" under Oklahoma State's crest, because
row 14624 is named Fresno State and holds Oklahoma State's ESPN id, badge,
record, location and aliases.

WHY (read from production 2026-09-26 22:40Z)
--------------------------------------------

Every `baseball_ncaa` team row with an ``espn_id`` (434) was dereferenced
against ESPN's own ``/college-baseball/teams/{id}`` page and the row's NAME
compared with the club that page names, using the writer's own predicate
(``espn_helpers.espn_identity_corresponds`` with no aliases — the aliases were
written from the same payload, so they cannot vouch for it). 55 fail, and every
one reads as another school: Wichita State, Virginia State, Wright State and
St. John's all hold Oklahoma State's ``110``; Ohio State holds Penn State's
``414``; Oklahoma State holds Kennesaw State's ``307``.

All 55 were minted March–May 2026, before ``upsert_team`` learned to refuse a
payload whose names do not correspond (#6215) and before the alias write was
held to the id's bar (#8353). The writers are fixed; these are the rows they
already wrote. #8353 named this sport as out of its scope ("a foreign-espn_id
defect, not a borrowed alias"); this is that defect.

Nothing that runs today reaches them: ``_cleanup_bad_espn_matches`` is not
scheduled, and its name test admits a row's aliases, which vouch for exactly
the foreign club.

WHAT IS WRITTEN
---------------

For each pinned row: ``espn_id`` and every field in
``ESPN_SOURCED_IDENTITY_FIELDS`` set to NULL — the same clear the cleanup task
applies. The ``team_identity_mapping`` rows are NOT touched: the two ``espn``
mappings on these rows (12755 → 195 St. John's, 14670 → 150 Mississippi State)
name the row's own school.

A row is written only while it still carries its pinned name AND pinned
``espn_id`` (compare-and-swap in the UPDATE itself). A pinned name that no
longer matches refuses the whole run: the id no longer means that team.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks each row's BEFORE values in ``backup_8949_foreign_espn_id``
(one jsonb object per team) and refuses to write if the bank is short.
``--restore`` writes BEFORE back only where the row's ``espn_id`` is still NULL;
a row the ESPN backfill has refilled since is reported and skipped.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on a
named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_8949_foreign_espn_id_teams.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_8949_foreign_espn_id_teams.py --apply    # backup + clear
    heroku run:detached -a bainluck -- python3 scripts/repair_8949_foreign_espn_id_teams.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_8949_foreign_espn_id"

#: Every column the clear writes, in one order the backup and restore share.
CLEARED_FIELDS = ("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)

#: team id -> (name, espn_id held, the club ESPN's page for that id names).
PINNED: dict[int, tuple[str, str, str]] = {
    12748: ('Morehead State', '288', 'Illinois State Redbirds'),
    12750: ('Alcorn State', '197', 'Missouri State Bears'),
    12751: ('Arkansas Pine Bluff', '58', 'Arkansas Razorbacks'),
    12754: ('California Baptist', '263', 'Dallas Baptist Patriots'),
    12755: ("St. John's", '110', 'Oklahoma State Cowboys'),
    12756: ('Central Michigan', '349', 'Eastern Michigan Eagles'),
    12759: ('Georgia State', '147', 'Texas State Bobcats'),
    12899: ('Texas Southern', '123', 'Texas A&M Aggies'),
    12900: ('Houston Christian', '190', 'Sam Houston Bearkats'),
    12954: ('Oklahoma State', '307', 'Kennesaw State Owls'),
    12962: ('Wright State', '110', 'Oklahoma State Cowboys'),
    13384: ('Michigan State', '463', 'Western Michigan Broncos'),
    13385: ('Western Michigan', '88', 'Michigan State Spartans'),
    13438: ('Kentucky St.', '197', 'Missouri State Bears'),
    13439: ('Eastern Kentucky', '84', 'Western Kentucky Hilltoppers'),
    13440: ('Appalachian State', '197', 'Missouri State Bears'),
    13441: ('Western Carolina', '84', 'Western Kentucky Hilltoppers'),
    13442: ('Wichita State', '110', 'Oklahoma State Cowboys'),
    13463: ('Washington State', '307', 'Kennesaw State Owls'),
    13464: ('Utah Tech', '173', 'Louisiana Tech Bulldogs'),
    13752: ('Florida State', '296', 'North Florida Ospreys'),
    13753: ('Virginia State', '110', 'Oklahoma State Cowboys'),
    13754: ('Norfolk State', '206', 'Wichita State Shockers'),
    13951: ('Grambling State', '320', 'Arkansas State Red Wolves'),
    14013: ('Murray State', '271', 'App State Mountaineers'),
    14014: ('Southern Illinois', '138', 'Georgia Southern Eagles'),
    14018: ('Georgia Southern', '432', 'Southern Illinois Salukis'),
    14019: ('Southern Indiana', '432', 'Southern Illinois Salukis'),
    14053: ('Coastal Carolina', '94', 'East Carolina Pirates'),
    14598: ('UC Riverside', '448', 'UC Davis Aggies'),
    14621: ('Tarleton State', '59', 'Arizona State Sun Devils'),
    14624: ('Fresno State', '110', 'Oklahoma State Cowboys'),
    14627: ('Ohio State', '414', 'Penn State Nittany Lions'),
    14628: ('Ball State', '72', 'Florida State Seminoles'),
    14630: ('Indiana State', '72', 'Florida State Seminoles'),
    14632: ('Kennesaw State', '73', 'Jacksonville State Gamecocks'),
    14633: ('UNC Greensboro', '152', 'UNC Wilmington Seahawks'),
    14639: ('Jacksonville State', '320', 'Arkansas State Red Wolves'),
    14640: ('Jackson State', '307', 'Kennesaw State Owls'),
    14642: ('Southeast Missouri', '197', 'Missouri State Bears'),
    14644: ('Charleston Southern', '192', 'Southern Miss Golden Eagles'),
    14646: ('Cal State Fullerton', '327', 'Cal State Bakersfield Roadrunners'),
    14648: ('Northwestern St.', '197', 'Missouri State Bears'),
    14649: ('Arizona State', '197', 'Missouri State Bears'),
    14650: ('Kent State', '108', 'Ohio State Buckeyes'),
    14651: ('Alabama State', '197', 'Missouri State Bears'),
    14653: ('South Alabama', '76', 'South Florida Bulls'),
    14654: ('Georgia Tech', '129699', 'West Georgia Wolves'),
    14655: ('West Georgia', '358', 'Georgia State Panthers'),
    14659: ('UC Davis', '67', 'UC Riverside Highlanders'),
    14668: ('Tarleton State', '59', 'Arizona State Sun Devils'),
    14670: ('Mississippi State', '197', 'Missouri State Bears'),
    14671: ('St. Ambrose', '88', 'Michigan State Spartans'),
    14672: ('Western Illinois', '288', 'Illinois State Redbirds'),
    14697: ('Louisiana Christian', '309', 'SE Louisiana Lions'),
}


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(rows: dict[int, tuple[str, str | None]], *, restore: bool) -> dict:
    """Decide per pinned row from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(name, espn_id)``.
    """
    wrong = sorted(i for i, r in rows.items() if i in PINNED and r[0] != PINNED[i][0])
    if wrong:
        raise Refused(f"row(s) {wrong} no longer carry their pinned name; refusing")
    write, skip = [], []
    for team_id, (_name, espn_id, _espn_club) in PINNED.items():
        if team_id not in rows:
            skip.append((team_id, "row missing"))
            continue
        current = rows[team_id][1]
        if restore:
            if current is None:
                write.append(team_id)
            elif current == espn_id:
                skip.append((team_id, "never cleared"))
            else:
                skip.append((team_id, f"refilled since the clear (espn_id {current})"))
        elif current == espn_id:
            write.append(team_id)
        elif current is None:
            skip.append((team_id, "already cleared"))
        else:
            skip.append((team_id, f"espn_id changed since the pin ({current})"))
    return {"write": write, "skip": skip}


async def _read(session) -> dict:
    got = await session.execute(
        text("SELECT id, name, espn_id FROM teams WHERE id = ANY(:ids)"),
        {"ids": sorted(PINNED)},
    )
    return {int(r.id): (r.name, r.espn_id) for r in got}


async def _backup(session, ids: list[int]) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " team_id integer PRIMARY KEY,"
            " before jsonb NOT NULL,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    pairs = ", ".join(f"'{f}', {f}" for f in CLEARED_FIELDS)
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (team_id, before) "
            f"SELECT id, jsonb_build_object({pairs}) FROM teams "
            "WHERE id = ANY(:ids) ON CONFLICT (team_id) DO NOTHING"
        ),
        {"ids": ids},
    )
    await session.commit()
    banked = await session.execute(
        text(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE team_id = ANY(:ids)"),
        {"ids": ids},
    )
    return int(banked.scalar_one())


async def run(session, *, apply: bool, restore: bool) -> dict:
    decided = plan(await _read(session), restore=restore)
    ids = decided["write"]
    written = 0
    if apply and ids:
        banked = await _backup(session, ids)
        if banked < len(ids):
            raise Refused(f"backup holds {banked} of {len(ids)} rows; refusing to clear")
        sets = ", ".join(f"{f} = NULL" for f in CLEARED_FIELDS)
        for team_id in ids:
            name, espn_id, _ = PINNED[team_id]
            result = await session.execute(
                text(
                    f"UPDATE teams SET {sets} "
                    "WHERE id = :id AND name = :name AND espn_id = :espn_id"
                ),
                {"id": team_id, "name": name, "espn_id": espn_id},
            )
            written += result.rowcount
        await session.commit()
    elif restore and ids:
        # `->` keeps alternate_names jsonb; a JSON null must come back as SQL NULL.
        sets = ", ".join(
            "alternate_names = NULLIF(b.before->'alternate_names', 'null'::jsonb)"
            if f == "alternate_names"
            else f"{f} = b.before->>'{f}'"
            for f in CLEARED_FIELDS
        )
        for team_id in ids:
            result = await session.execute(
                text(
                    f"UPDATE teams SET {sets} FROM {BACKUP_TABLE} b "
                    "WHERE teams.id = :id AND b.team_id = teams.id "
                    "AND teams.name = :name AND teams.espn_id IS NULL"
                ),
                {"id": team_id, "name": PINNED[team_id][0]},
            )
            written += result.rowcount
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    after = await _read(session)
    still_foreign = sorted(
        i for i, (_, espn_id, _) in PINNED.items() if after.get(i, (None, None))[1] == espn_id
    )
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": len(ids),
        "written": written,
        "skip": decided["skip"],
        "still_holding_pinned_espn_id": still_foreign,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        try:
            out = await run(session, apply=args.apply, restore=args.restore)
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_8949_foreign_espn_id_teams.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
