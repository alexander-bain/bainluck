"""#9076 — put the five college-football nicknames onto their teams' rows, with an undo.

THE SHIP: typing ``horns`` / ``vols`` / ``noles`` / ``bama`` / ``huskers`` puts that
college team on the /search TEAMS card. On 2026-09-27 10:13Z the search route served
``horns`` ``teams=[Charlotte Hornets, Dandy Town Hornets, TCU Horned Frogs, Alabama St
Hornets, Delaware St Hornets]`` and the other four ``teams=[]``. (This script sends no
request; it writes rows.)

WHY THE ROWS LACK THEM
----------------------

``8c75a0e343`` (#9076, CERT-3637, live in v5159) added the five aliases to
``app/config/team_aliases.py``. The games and markets rails read that map at query
time, so they moved. The TEAMS card does not: it reads ``teams.alternate_names``
(``routes/events.py``, the Teams FTS + ``_aliases`` scorer input), and the config
reaches that column only through ``backfill_curated_team_aliases.py --apply``, which
never ran for these five. Production read 2026-09-27 10:13Z: each name has exactly one
``americanfootball_ncaaf`` row and none carries its alias. This is the same gap, and the
same repair, as ``repair_8685_curated_team_alias_rows.py`` (paid 2026-09-26 13:46Z).

WHY A DEDICATED SCRIPT, NOT THE BACKFILL
----------------------------------------

The backfill walks the whole curated map, has no production guard and no undo. This
touches exactly the five pinned rows and ships the inverse (D51(b)). The config maps
each alias to the ncaaf club only, so the ncaab / baseball rows of the same schools are
not touched.

WHAT IT DOES
------------

For each pinned team id: append its alias to ``alternate_names`` (a union — nothing
already there moves or goes). Each write is a compare-and-set against the value read a
moment earlier, so an ESPN sync that unions a name in between makes the statement
change 0 rows and the run refuses rather than dropping that name.

**No backup table, and that is a proof rather than a habit** (the argument
``repair_8685_curated_team_alias_rows`` makes): the change to each row is exactly one
appended string that ``PINNED`` names and that the row did not hold before (a test
asserts no pinned BEFORE list holds its alias, case-insensitively). So the inverse is
"remove exactly that string", and ``--restore`` is that compare-and-set. Anything else
an ESPN sync adds meanwhile survives the undo. No DDL runs, so this is a data write,
not notice 47(c) runtime DDL.

PER-ROW SKIPS (reported, never written)
---------------------------------------

* the row is missing;
* apply: the alias is already there (any case) — this ran already, or someone else
  put it there;
* restore: the alias is not there — nothing to undo.

REFUSALS (the whole run stops, nothing is written)
--------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* a pinned id whose row is not the pinned (sport, team) — the id no longer means
  what the read meant;
* a write that changes other than exactly one row.

    python3 scripts/repair_9076_college_team_alias_rows.py            # dry run
    python3 scripts/repair_9076_college_team_alias_rows.py --apply    # add the five
    python3 scripts/repair_9076_college_team_alias_rows.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

#: team id → (sport key, team name, alias, ``alternate_names`` on the 2026-09-27 10:13Z read).
#: The BEFORE lists are the record the undo is proven against, not a restore source.
PINNED: dict[int, tuple[str, str, str, list[str]]] = {
    834: ("americanfootball_ncaaf", "Texas Longhorns", "horns", ["Longhorns", "Texas"]),
    15937: ("americanfootball_ncaaf", "Tennessee Volunteers", "vols",
            ["Tennessee", "Volunteers"]),
    13473: ("americanfootball_ncaaf", "Florida State Seminoles", "noles",
            ["Seminoles", "Florida St"]),
    15262: ("americanfootball_ncaaf", "Alabama Crimson Tide", "bama",
            ["Crimson Tide", "Alabama"]),
    15349: ("americanfootball_ncaaf", "Nebraska Cornhuskers", "huskers",
            ["Nebraska", "Cornhuskers"]),
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


def _holds(names: list, alias: str) -> bool:
    return any(isinstance(n, str) and n.strip().lower() == alias for n in names)


def plan(rows: dict[int, tuple[str, str, list | None]], *, restore: bool) -> dict:
    """Decide per pinned team, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(sport_key, name, alternate_names)``.
    Returns the ``(id, current, new)`` writes and the ``(id, reason)`` skips; raises
    ``Refused`` when a pinned id's row is not the pinned team.
    """
    write, skip = [], []
    for team_id, (sport_key, name, alias, _before) in PINNED.items():
        if team_id not in rows:
            skip.append((team_id, "row missing"))
            continue
        got_sport, got_name, names = rows[team_id]
        if (got_sport, got_name) != (sport_key, name):
            raise Refused(
                f"team {team_id} is ({got_sport!r}, {got_name!r}), "
                f"pinned as ({sport_key!r}, {name!r})"
            )
        current = list(names or [])
        if restore:
            if alias not in current:
                skip.append((team_id, f"{alias!r} absent, nothing to undo"))
                continue
            write.append((team_id, current, [n for n in current if n != alias]))
        else:
            if _holds(current, alias):
                skip.append((team_id, f"{alias!r} already present"))
                continue
            write.append((team_id, current, current + [alias]))
    return {"write": write, "skip": skip}


def _as_list(value) -> list | None:
    # A raw `text()` read can hand JSONB back as its JSON text, depending on the
    # driver's codecs; the ORM hands back the list.
    return json.loads(value) if isinstance(value, str) else value


async def _read(session) -> dict[int, tuple[str, str, list | None]]:
    got = await session.execute(
        text(
            "SELECT t.id, sp.key AS sport_key, t.name, t.alternate_names FROM teams t "
            "JOIN sports sp ON sp.id = t.sport_id WHERE t.id = ANY(:ids)"
        ),
        {"ids": list(PINNED)},
    )
    return {
        int(r.id): (r.sport_key, r.name, _as_list(r.alternate_names)) for r in got
    }


# The WHERE re-states the compare half: a name an ESPN sync unions in between the read
# and the write makes this change 0 rows, and the run refuses instead of dropping it.
# jsonb equality is order-sensitive for arrays, which is what "unchanged" means here.
_CAS_SQL = (
    "UPDATE teams SET alternate_names = CAST(:new AS jsonb) "
    "WHERE id = :id AND alternate_names IS NOT DISTINCT FROM CAST(:current AS jsonb)"
)


async def run(session, *, apply: bool, restore: bool) -> dict:
    rows = await _read(session)
    decided = plan(rows, restore=restore)
    written = 0
    if apply or restore:
        for team_id, current, new in decided["write"]:
            result = await session.execute(
                text(_CAS_SQL),
                {
                    "id": team_id,
                    "current": json.dumps(current) if rows[team_id][2] is not None else None,
                    "new": json.dumps(new),
                },
            )
            if result.rowcount != 1:
                raise Refused(
                    f"team {team_id}: expected to change 1 row, changed {result.rowcount}"
                )
            written += 1
        await session.commit()
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "write": decided["write"],
        "skip": decided["skip"],
        "written": written,
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
    print(json.dumps(out, indent=2))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_9076_college_team_alias_rows.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
