"""#8353 — strip other schools' names from 28 college-basketball team rows.

THE SHIP: typing "wolverines" in the search box offers Michigan, not Akron Zips;
"eagles" stops offering Akron; "west virginia" offers West Virginia, not Rutgers,
Stetson and ten other women's teams.

WHY (read from production 2026-09-24 05:50Z)
---------------------------------------------

``_backfill_team_logos`` unioned the names of whatever ESPN club a token-overlap
score of 0.51 picked into ``teams.alternate_names`` — the ``espn_id`` write beside
it refused fuzzy hits, the alias write did not. The code half of #8353
(``espn_aliases_to_store``) holds aliases to the id's bar from now on; this script
heals the rows already carrying a borrowed school.

THE POPULATION, AND HOW IT WAS CHOSEN
-------------------------------------

A row T is in scope when one of its aliases is, verbatim, the name of another team O
in the same sport, and T and O are not one club under two names (both ESPN ids
known and equal — "Detroit" / "Detroit Pistons" — is excluded). The strip removes O's
name and every alias O answers to on any row bearing O's name, never T's own name.
Pinned to the two college-basketball sports (ids 3 and 14), where every hit is a
different school: all 28 rows below keep their own school's names and nothing else.

Central Arkansas Bears (724) also wears the Arkansas Razorbacks crest (ESPN ``8``),
from the same fuzzy match; its two logo columns are cleared so the backfill refills
them by exact name. Apply this AFTER the code half is live, or that refill can
re-borrow.

DELIBERATELY NOT IN SCOPE
-------------------------

* sport 18168 (41 hits) — "Ohio State" / "Ohio State Buckeyes" pairs whose ESPN ids
  sit in a mixed namespace ("Alabama" holds South Alabama's ``57``). That is a
  foreign-``espn_id`` defect, not a borrowed alias; stripping there would delete a
  school's own location.
* LAFC (13537) — "Los Angeles FC" is LAFC.
* rows whose ``espn_id`` itself is another school's (Hampton ``151`` = East Carolina,
  Richmond ``158`` = Nebraska, Army ``161`` = FDU) — same-id pairs, excluded by rule.

THE BACKUP IS THE PIN
---------------------

Each row is written only when its current alias set equals the pinned BEFORE set
exactly (compare-and-swap); ``--restore`` writes BEFORE back only where the row holds
exactly AFTER. A row the backfill has touched since is reported and skipped, both
ways. The logo is cleared only where both columns still hold the Razorbacks crest and
restored only where both are still NULL. No DDL runs (not notice 47(c)).

REFUSALS (nothing is written)
-----------------------------

* ``HEROKU_APP_NAME`` is not ``bainluck`` / ``bainluck-heavy``;
* a pinned row's ``name`` is not the pinned name (the id no longer means that team).

    python3 scripts/repair_8353_foreign_team_aliases.py            # dry run
    python3 scripts/repair_8353_foreign_team_aliases.py --apply    # strip
    python3 scripts/repair_8353_foreign_team_aliases.py --restore  # undo
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

#: team id → (name, alias list BEFORE, alias list AFTER), as read from production.
PINNED: dict[int, tuple[str, list[str], list[str]]] = {
    157: (  # sport 3, espn 154 — carried Florida Gators
        "Wake Forest Demon Deacons",
        ["Demon Deacons", "Florida Gators", "Gators", "Wake Forest", "Florida"],
        ["Demon Deacons", "Wake Forest"],
    ),
    172: (  # sport 3, espn 201 — carried Houston Cougars
        "Oklahoma Sooners",
        ["Houston Cougars", "Oklahoma", "Houston", "Sooners", "Cougars"],
        ["Oklahoma", "Sooners"],
    ),
    271: (  # sport 3, espn 2 — carried Texas Tech Red Raiders
        "Auburn Tigers",
        ["Texas Tech", "Texas Tech Red Raiders", "Tigers", "Red Raiders", "Auburn"],
        ["Tigers", "Auburn"],
    ),
    507: (  # sport 3, espn 46 — carried Eastern Michigan Eagles
        "Georgetown Hoyas",
        ["Georgetown", "Eastern Michigan Eagles", "Eagles", "E Michigan", "Hoyas"],
        ["Georgetown", "Hoyas"],
    ),
    724: (  # sport 3, espn None — carried Arkansas Razorbacks
        "Central Arkansas Bears",
        ["Bears", "Razorbacks", "Arkansas Razorbacks", "Arkansas", "C Arkansas"],
        ["Bears", "C Arkansas"],
    ),
    769: (  # sport 3, espn 189 — carried Eastern Michigan Eagles
        "Bowling Green Falcons",
        ["Eagles", "Bowling Green", "E Michigan", "Falcons", "Eastern Michigan Eagles"],
        ["Bowling Green", "Falcons"],
    ),
    3113: (  # sport 3, espn 2006 — carried Michigan Wolverines, Eastern Michigan Eagles
        "Akron Zips",
        ["Michigan Wolverines", "Michigan", "Wolverines", "Eastern Michigan Eagles", "Eagles", "Akron", "E Michigan", "Zips"],
        ["Akron", "Zips"],
    ),
    76: (  # sport 14, espn 135 — carried Iowa Hawkeyes
        "Minnesota Golden Gophers",
        ["Minnesota", "Iowa Hawkeyes", "Golden Gophers", "Iowa", "Hawkeyes"],
        ["Minnesota", "Golden Gophers"],
    ),
    120: (  # sport 14, espn 163 — carried West Virginia Mountaineers
        "Princeton Tigers",
        ["Princeton", "West Virginia Mountaineers", "West Virginia", "Tigers", "Mountaineers"],
        ["Princeton", "Tigers"],
    ),
    190: (  # sport 14, espn 38 — carried Baylor Bears
        "Colorado Buffaloes",
        ["Buffaloes", "Baylor", "Bears", "Baylor Bears", "Colorado"],
        ["Buffaloes", "Colorado"],
    ),
    235: (  # sport 14, espn 201 — carried Iowa Hawkeyes
        "Oklahoma Sooners",
        ["Hawkeyes", "Sooners", "Iowa", "Oklahoma", "Iowa Hawkeyes"],
        ["Sooners", "Oklahoma"],
    ),
    398: (  # sport 14, espn 77 — carried Iowa Hawkeyes
        "Northwestern Wildcats",
        ["Hawkeyes", "Iowa Hawkeyes", "Northwestern", "Wildcats", "Iowa"],
        ["Northwestern", "Wildcats"],
    ),
    669: (  # sport 14, espn 222 — carried Iowa Hawkeyes
        "Villanova Wildcats",
        ["Wildcats", "Villanova", "Iowa", "Hawkeyes", "Iowa Hawkeyes"],
        ["Wildcats", "Villanova"],
    ),
    735: (  # sport 14, espn 152 — carried Iowa Hawkeyes
        "NC State Wolfpack",
        ["Iowa", "NC State", "Hawkeyes", "Iowa Hawkeyes", "Wolfpack", "north carolina state"],
        ["NC State", "Wolfpack", "north carolina state"],
    ),
    2399: (  # sport 14, espn 46 — carried West Virginia Mountaineers
        "Georgetown Hoyas",
        ["Hoyas", "Mountaineers", "Georgetown", "West Virginia", "West Virginia Mountaineers"],
        ["Hoyas", "Georgetown"],
    ),
    2400: (  # sport 14, espn 197 — carried Oklahoma Sooners
        "Oklahoma St Cowgirls",
        ["Sooners", "Oklahoma State Cowgirls", "Oklahoma", "Cowgirls", "Oklahoma Sooners", "Oklahoma St"],
        ["Oklahoma State Cowgirls", "Cowgirls", "Oklahoma St"],
    ),
    2407: (  # sport 14, espn None — carried West Virginia Mountaineers
        "Utah Utes",
        ["Mountaineers", "Utah", "West Virginia", "West Virginia Mountaineers", "Utes"],
        ["Utah", "Utes"],
    ),
    2415: (  # sport 14, espn 9 — carried West Virginia Mountaineers
        "Arizona St Sun Devils",
        ["Arizona State Sun Devils", "West Virginia", "West Virginia Mountaineers", "Arizona St", "Mountaineers", "Sun Devils"],
        ["Arizona State Sun Devils", "Arizona St", "Sun Devils"],
    ),
    2557: (  # sport 14, espn 167 — carried West Virginia Mountaineers
        "New Mexico Lobos",
        ["Mountaineers", "New Mexico", "Lobos", "West Virginia Mountaineers", "West Virginia"],
        ["New Mexico", "Lobos"],
    ),
    2558: (  # sport 14, espn 56 — carried West Virginia Mountaineers
        "Stetson Hatters",
        ["Stetson", "West Virginia Mountaineers", "Mountaineers", "West Virginia", "Hatters"],
        ["Stetson", "Hatters"],
    ),
    2564: (  # sport 14, espn 164 — carried West Virginia Mountaineers
        "Rutgers Scarlet Knights",
        ["West Virginia Mountaineers", "Scarlet Knights", "Mountaineers", "West Virginia", "Rutgers"],
        ["Scarlet Knights", "Rutgers"],
    ),
    2600: (  # sport 14, espn 107 — carried West Virginia Mountaineers
        "Holy Cross Crusaders",
        ["West Virginia", "Mountaineers", "Crusaders", "Holy Cross", "West Virginia Mountaineers"],
        ["Crusaders", "Holy Cross"],
    ),
    2601: (  # sport 14, espn 2623 — carried West Virginia Mountaineers
        "Missouri St Bears",
        ["West Virginia", "Missouri State Bears", "West Virginia Mountaineers", "Missouri St", "Mountaineers", "Bears"],
        ["Missouri State Bears", "Missouri St", "Bears"],
    ),
    2608: (  # sport 14, espn 338 — carried West Virginia Mountaineers
        "Kennesaw St Owls",
        ["Kennesaw St", "Kennesaw State Owls", "Mountaineers", "Owls", "West Virginia", "West Virginia Mountaineers"],
        ["Kennesaw St", "Kennesaw State Owls", "Owls"],
    ),
    2610: (  # sport 14, espn 2710 — carried West Virginia Mountaineers
        "Western Illinois Leathernecks",
        ["West Virginia", "Leathernecks", "Mountaineers", "W Illinois", "West Virginia Mountaineers"],
        ["Leathernecks", "W Illinois"],
    ),
    2705: (  # sport 14, espn 58 — carried West Virginia Mountaineers
        "South Florida Bulls",
        ["South Florida", "Bulls", "West Virginia", "West Virginia Mountaineers", "Mountaineers"],
        ["South Florida", "Bulls"],
    ),
    2835: (  # sport 14, espn 103 — carried Iowa Hawkeyes
        "Boston College Eagles",
        ["Hawkeyes", "Eagles", "Boston College", "Iowa", "Iowa Hawkeyes"],
        ["Eagles", "Boston College"],
    ),
    3764: (  # sport 14, espn 36 — carried Colorado Buffaloes
        "Colorado St Rams",
        ["Rams", "Colorado State Rams", "Colorado St", "Buffaloes", "Colorado Buffaloes", "Colorado"],
        ["Rams", "Colorado State Rams", "Colorado St"],
    ),
}

#: team id → the foreign crest both logo columns hold.
LOGO_CLEAR: dict[int, str] = {
    724: "https://a.espncdn.com/i/teamlogos/ncaa/500/8.png",  # Arkansas Razorbacks
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


def _same(a, b) -> bool:
    return sorted(a or []) == sorted(b or [])


def plan(rows: dict[int, tuple[str, list | None, str | None, str | None]], *, restore: bool) -> dict:
    """Decide per pinned row from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(name, alternate_names,
    logo_url_small, logo_url_large)``; an id absent from ``rows`` is missing.
    """
    wrong = sorted(
        i for i, r in rows.items() if i in PINNED and r[0] != PINNED[i][0]
    )
    if wrong:
        raise Refused(f"row(s) {wrong} no longer carry their pinned name; refusing")
    aliases, logos, skip = [], [], []
    for team_id, (_name, before, after) in PINNED.items():
        if team_id not in rows:
            skip.append((team_id, "row missing"))
            continue
        current = rows[team_id][1]
        want_from, want_to = (after, before) if restore else (before, after)
        if _same(current, want_from):
            aliases.append((team_id, want_to))
        elif _same(current, want_to):
            skip.append((team_id, "already " + ("restored" if restore else "stripped")))
        else:
            skip.append((team_id, "aliases changed since the pin"))
    for team_id, crest in LOGO_CLEAR.items():
        if team_id not in rows:
            continue
        small, large = rows[team_id][2], rows[team_id][3]
        if restore:
            if small is None and large is None:
                logos.append((team_id, crest))
            else:
                skip.append((team_id, "logo refilled since the clear"))
        elif small == crest and large == crest:
            logos.append((team_id, None))
        else:
            skip.append((team_id, "logo no longer the pinned crest"))
    return {"aliases": aliases, "logos": logos, "skip": skip}


async def _read(session) -> dict:
    ids = sorted(set(PINNED) | set(LOGO_CLEAR))
    got = await session.execute(
        text(
            "SELECT id, name, alternate_names, logo_url_small, logo_url_large "
            "FROM teams WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    return {
        int(r.id): (r.name, r.alternate_names, r.logo_url_small, r.logo_url_large)
        for r in got
    }


async def run(session, *, apply: bool, restore: bool) -> dict:
    decided = plan(await _read(session), restore=restore)
    written = 0
    if apply or restore:
        for team_id, names in decided["aliases"]:
            result = await session.execute(
                text(
                    "UPDATE teams SET alternate_names = CAST(:names AS jsonb) "
                    "WHERE id = :id"
                ),
                {"id": team_id, "names": json.dumps(names)},
            )
            if result.rowcount != 1:
                raise Refused(f"team {team_id}: changed {result.rowcount} rows, expected 1")
            written += 1
        for team_id, crest in decided["logos"]:
            result = await session.execute(
                text(
                    "UPDATE teams SET logo_url_small = :crest, logo_url_large = :crest "
                    "WHERE id = :id"
                ),
                {"id": team_id, "crest": crest},
            )
            if result.rowcount != 1:
                raise Refused(f"team {team_id}: changed {result.rowcount} rows, expected 1")
            written += 1
        await session.commit()
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "aliases": decided["aliases"],
        "logos": decided["logos"],
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
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_8353_foreign_team_aliases.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
