"""#9127 — thirteen college-basketball rows stop wearing another school's crest.

THE SHIP: searching "hornets" shows Alabama State and Delaware State with their own
crests, not Sacramento State's; Norfolk State stops wearing Michigan State's, Texas
State Montana State's, San Diego San Diego State's, App State Mount St. Mary's, and
the women's Army and Hampton rows stop wearing Fairleigh Dickinson's and East
Carolina's. Central Arkansas stops wearing Arkansas's for the second time.

WHY (read from production 2026-09-27 ~15:50Z)
----------------------------------------------

``_backfill_team_logos`` filled a crest-less row from whatever ESPN club a token
score above 0.5 picked, and ESPN's ``/teams?limit=100`` lists under a third of
Division I, so an unlisted school's best hit was a listed school sharing its mascot
("Delaware St Hornets" / "Sacramento State Hornets" = 0.67). The same fuzzy hit
wrote the colours and, before #8353, the other school's names; on some rows a later
pass then exact-matched a borrowed name and stamped the other school's ``espn_id``
and abbreviation too (Alabama St Hornets held ``16``/``SAC``, Sacramento's). The
code half (``espn_media_may_be_written``) stops the fuzzy fill; this script heals
the rows already wearing another school.

THE POPULATION
--------------

Every ``basketball_ncaab`` / ``basketball_wncaab`` row whose ``teamlogos/ncaa/500/<id>``
crest is shared, within its sport, with a DIFFERENT school (same-school duplicate
rows such as "Harvard" / "Harvard Crimson" excluded), minus the rightful holder.
Every event bound to these thirteen rows carries the row's own name (checked:
0 mismatches), so the row's identity is right and only its ESPN-sourced fields are
someone else's. Each AFTER value was read from ESPN's own team endpoint
(``site.api.espn.com/.../teams/<id>``) through ``ESPNAPIService._parse_team``;
aliases keep the row's own names, drop the other school's, and add ESPN's names
the way ``espn_aliases_to_store`` would. No row in either sport holds any AFTER id.

Deliberately NOT here: Sacramento St Hornets (1126) and Mt. St. Mary's (2661)
keep their correct crests and gain no id; East Carolina's ``OSU`` and FDU's ``TEX``
abbreviations and Michigan St's San José aliases are wrong but wear no other
school's crest.

THE BACKUP IS THE PIN
---------------------

A row is written only when all six fields and its alias SET equal the pinned
BEFORE (compare-and-swap, in the UPDATE's own WHERE); ``--restore`` writes BEFORE
back only where the row holds exactly AFTER. A row touched since is reported and
skipped, both ways. No DDL runs (not notice 47(c)). The repaired rows carry a crest
and an abbreviation, so the logo backfill never selects them again.

REFUSALS (nothing is written)
-----------------------------

* ``HEROKU_APP_NAME`` is not ``bainluck`` / ``bainluck-heavy``;
* a pinned row's ``name`` is not the pinned name (the id no longer means that team).

    python3 scripts/repair_9127_foreign_team_crests.py            # dry run
    python3 scripts/repair_9127_foreign_team_crests.py --apply    # repair
    python3 scripts/repair_9127_foreign_team_crests.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

#: The scalar fields compared and written; ``logo`` is both logo columns.
SCALARS = ("espn_id", "abbreviation", "logo", "primary_color", "secondary_color")


class Row(NamedTuple):
    name: str
    before: dict
    after: dict


#: team id → the row as read from production (BEFORE) and as ESPN has it (AFTER).
PINNED: dict[int, Row] = {
    702: Row(  # basketball_ncaab, wore Montana State (147); ESPN 326 = Texas State Bobcats
        'Texas State Bobcats',
        before={'espn_id': None, 'abbreviation': 'TXST', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/147.png', 'primary_color': '#00205c', 'secondary_color': '#bc955c', 'alternate_names': ['Bobcats', 'Montana St', 'Montana State Bobcats', 'Texas St']},
        after={'espn_id': '326', 'abbreviation': 'TXST', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/326.png', 'primary_color': '#501214', 'secondary_color': '#6a5638', 'alternate_names': ['Bobcats', 'Texas St']},
    ),
    724: Row(  # basketball_ncaab, wore Arkansas (8); ESPN 2110 = Central Arkansas Bears
        'Central Arkansas Bears',
        before={'espn_id': None, 'abbreviation': 'CARK', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/8.png', 'primary_color': '#a41f35', 'secondary_color': '#ffffff', 'alternate_names': ['Bears', 'C Arkansas']},
        after={'espn_id': '2110', 'abbreviation': 'CARK', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2110.png', 'primary_color': '#a7a9ac', 'secondary_color': '#8e959a', 'alternate_names': ['Bears', 'C Arkansas']},
    ),
    1066: Row(  # basketball_ncaab, wore Michigan State (127); ESPN 2450 = Norfolk State Spartans
        'Norfolk St Spartans',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/127.png', 'primary_color': '#173f35', 'secondary_color': '#ffffff', 'alternate_names': ['Michigan St', 'Michigan State Spartans', 'Spartans']},
        after={'espn_id': '2450', 'abbreviation': 'NORF', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2450.png', 'primary_color': '#0c8968', 'secondary_color': '#fdb813', 'alternate_names': ['Norfolk St', 'Norfolk State Spartans', 'Spartans']},
    ),
    1161: Row(  # basketball_ncaab, wore Mount St. Mary's (116); ESPN 2026 = App State Mountaineers
        'Appalachian St Mountaineers',
        before={'espn_id': '116', 'abbreviation': 'MSM', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/116.png', 'primary_color': '#005596', 'secondary_color': '#ebebeb', 'alternate_names': ['Mount St Marys', "Mount St. Mary's Mountaineers", 'Mountaineers']},
        after={'espn_id': '2026', 'abbreviation': 'APP', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2026.png', 'primary_color': '#000000', 'secondary_color': '#ffcd00', 'alternate_names': ['App State', 'App State Mountaineers', 'Mountaineers']},
    ),
    1171: Row(  # basketball_ncaab, wore San Diego State (21); ESPN 301 = San Diego Toreros
        'San Diego Toreros',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/21.png', 'primary_color': '#c41230', 'secondary_color': '#000000', 'alternate_names': ['Aztecs', 'San Diego St', 'San Diego State Aztecs']},
        after={'espn_id': '301', 'abbreviation': 'USD', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/301.png', 'primary_color': '#2f99d4', 'secondary_color': '#2f99d4', 'alternate_names': ['San Diego', 'Toreros']},
    ),
    1186: Row(  # basketball_ncaab, wore Sacramento State (16); ESPN 2169 = Delaware State Hornets
        'Delaware St Hornets',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/16.png', 'primary_color': '#00573C', 'secondary_color': '#cdb97d', 'alternate_names': ['Hornets', 'Sacramento St', 'Sacramento State Hornets']},
        after={'espn_id': '2169', 'abbreviation': 'DSU', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2169.png', 'primary_color': '#009cdb', 'secondary_color': '#d51c28', 'alternate_names': ['Delaware St', 'Delaware State Hornets', 'Hornets']},
    ),
    1209: Row(  # basketball_ncaab, wore Sacramento State (16); ESPN 2011 = Alabama State Hornets
        'Alabama St Hornets',
        before={'espn_id': '16', 'abbreviation': 'SAC', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/16.png', 'primary_color': '#00573C', 'secondary_color': '#cdb97d', 'alternate_names': ['Hornets', 'Sacramento St', 'Sacramento State Hornets']},
        after={'espn_id': '2011', 'abbreviation': 'ALST', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2011.png', 'primary_color': '#e9a900', 'secondary_color': '#0a0a0a', 'alternate_names': ['Alabama St', 'Alabama State Hornets', 'Hornets']},
    ),
    2396: Row(  # basketball_wncaab, wore Fairleigh Dickinson (161); ESPN 349 = Army Black Knights
        'Army Knights',
        before={'espn_id': '161', 'abbreviation': 'FDU', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/161.png', 'primary_color': '#72293c', 'secondary_color': '#28334a', 'alternate_names': ['FDU', 'Fairleigh Dickinson Knights', 'Knights']},
        after={'espn_id': '349', 'abbreviation': 'ARMY', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/349.png', 'primary_color': '#000000', 'secondary_color': '#d3bc8d', 'alternate_names': ['Army', 'Army Black Knights', 'Black Knights']},
    ),
    2561: Row(  # basketball_wncaab, wore Michigan State (127); ESPN 2450 = Norfolk State Spartans
        'Norfolk St Spartans',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/127.png', 'primary_color': '#173f35', 'secondary_color': '#ffffff', 'alternate_names': ['Michigan St', 'Michigan State Spartans', 'Spartans']},
        after={'espn_id': '2450', 'abbreviation': 'NORF', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2450.png', 'primary_color': '#0c8968', 'secondary_color': '#fdb813', 'alternate_names': ['Norfolk St', 'Norfolk State Spartans', 'Spartans']},
    ),
    2873: Row(  # basketball_wncaab, wore East Carolina (151); ESPN 2261 = Hampton Lady Pirates
        'Hampton Pirates',
        before={'espn_id': '151', 'abbreviation': 'ECU', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/151.png', 'primary_color': '#582c83', 'secondary_color': '#ffc72c', 'alternate_names': ['East Carolina', 'East Carolina Pirates', 'Pirates']},
        after={'espn_id': '2261', 'abbreviation': 'HAMP', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2261.png', 'primary_color': '#0067AC', 'secondary_color': None, 'alternate_names': ['Hampton', 'Hampton Lady Pirates', 'Lady Pirates', 'Pirates']},
    ),
    7319: Row(  # basketball_wncaab, wore San Diego State (21); ESPN 301 = San Diego Toreros
        'San Diego Toreros',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/21.png', 'primary_color': '#a6192e', 'secondary_color': '#000000', 'alternate_names': ['Aztecs', 'San Diego St', 'San Diego State Aztecs']},
        after={'espn_id': '301', 'abbreviation': 'USD', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/301.png', 'primary_color': '#2f99d4', 'secondary_color': '#2f99d4', 'alternate_names': ['San Diego', 'Toreros']},
    ),
    8990: Row(  # basketball_wncaab, wore Sacramento State (16); ESPN 2169 = Delaware State Hornets
        'Delaware St Hornets',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/16.png', 'primary_color': '#00573C', 'secondary_color': '#cdb97d', 'alternate_names': ['Hornets', 'Sacramento St', 'Sacramento State Hornets']},
        after={'espn_id': '2169', 'abbreviation': 'DSU', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2169.png', 'primary_color': '#009cdb', 'secondary_color': '#d51c28', 'alternate_names': ['Delaware St', 'Delaware State Hornets', 'Hornets']},
    ),
    9744: Row(  # basketball_wncaab, wore Sacramento State (16); ESPN 2011 = Alabama State Lady Hornets
        'Alabama St Hornets',
        before={'espn_id': None, 'abbreviation': None, 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/16.png', 'primary_color': '#00573C', 'secondary_color': '#cdb97d', 'alternate_names': ['Hornets', 'Sacramento St', 'Sacramento State Hornets']},
        after={'espn_id': '2011', 'abbreviation': 'ALST', 'logo': 'https://a.espncdn.com/i/teamlogos/ncaa/500/2011.png', 'primary_color': '#e9a900', 'secondary_color': '#0a0a0a', 'alternate_names': ['Alabama St', 'Alabama State Lady Hornets', 'Hornets', 'Lady Hornets']},
    ),
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


def holds(current: dict, state: dict) -> bool:
    """``current`` (as read) equals ``state`` on every field; aliases as a set."""
    if current.get("logo_url_small") != state["logo"] or current.get("logo_url_large") != state["logo"]:
        return False
    for field in SCALARS:
        if field != "logo" and current.get(field) != state[field]:
            return False
    return sorted(set(current.get("alternate_names") or [])) == sorted(set(state["alternate_names"]))


def plan(rows: dict[int, dict], *, restore: bool) -> dict:
    """Decide per pinned row from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to its read columns; an id absent
    from ``rows`` is missing.
    """
    wrong = sorted(i for i, r in rows.items() if i in PINNED and r["name"] != PINNED[i].name)
    if wrong:
        raise Refused(f"row(s) {wrong} no longer carry their pinned name; refusing")
    write, skip = [], []
    for team_id, row in PINNED.items():
        if team_id not in rows:
            skip.append((team_id, "row missing"))
            continue
        want_from, want_to = (row.after, row.before) if restore else (row.before, row.after)
        if holds(rows[team_id], want_from):
            write.append((team_id, want_from, want_to))
        elif holds(rows[team_id], want_to):
            skip.append((team_id, "already " + ("restored" if restore else "repaired")))
        else:
            skip.append((team_id, "changed since the pin"))
    return {"write": write, "skip": skip}


_COLUMNS = (
    "name, espn_id, abbreviation, logo_url_small, logo_url_large, "
    "primary_color, secondary_color, alternate_names"
)

#: One statement, its own compare-and-swap: every BEFORE field in the WHERE, the
#: alias set by containment both ways (order-free, as the backfill writes a set).
_UPDATE = text(
    "UPDATE teams SET espn_id = :to_espn_id, abbreviation = :to_abbreviation, "
    "logo_url_small = :to_logo, logo_url_large = :to_logo, "
    "primary_color = :to_primary_color, secondary_color = :to_secondary_color, "
    "alternate_names = CAST(:to_alternate_names AS jsonb) "
    "WHERE id = :id "
    "AND espn_id IS NOT DISTINCT FROM :from_espn_id "
    "AND abbreviation IS NOT DISTINCT FROM :from_abbreviation "
    "AND logo_url_small IS NOT DISTINCT FROM :from_logo "
    "AND logo_url_large IS NOT DISTINCT FROM :from_logo "
    "AND primary_color IS NOT DISTINCT FROM :from_primary_color "
    "AND secondary_color IS NOT DISTINCT FROM :from_secondary_color "
    "AND alternate_names @> CAST(:from_alternate_names AS jsonb) "
    "AND alternate_names <@ CAST(:from_alternate_names AS jsonb)"
)


def update_params(team_id: int, want_from: dict, want_to: dict) -> dict:
    params = {"id": team_id}
    for prefix, state in (("from_", want_from), ("to_", want_to)):
        for field in SCALARS:
            params[prefix + field] = state[field]
        params[prefix + "alternate_names"] = json.dumps(state["alternate_names"])
    return params


async def _read(session) -> dict:
    got = await session.execute(
        text(f"SELECT id, {_COLUMNS} FROM teams WHERE id = ANY(:ids)"),
        {"ids": sorted(PINNED)},
    )
    return {int(r.id): dict(r._mapping) for r in got}


async def run(session, *, apply: bool, restore: bool) -> dict:
    decided = plan(await _read(session), restore=restore)
    written = 0
    if apply or restore:
        for team_id, want_from, want_to in decided["write"]:
            result = await session.execute(_UPDATE, update_params(team_id, want_from, want_to))
            if result.rowcount != 1:
                raise Refused(
                    f"team {team_id}: changed {result.rowcount} rows, expected 1 "
                    "(moved between the read and the write); nothing committed"
                )
            written += 1
        await session.commit()
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "write": [team_id for team_id, _f, _t in decided["write"]],
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
            "python3 scripts/repair_9127_foreign_team_crests.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
