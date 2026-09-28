"""#9280 — give the Utah Mammoth row the name Polymarket calls the club, with an undo.

THE SHIP: Utah Mammoth games stop appearing as "OTHER HOCKEY · Utah" cards beside
(or instead of) the NHL game, and Thursday's Blackhawks @ Utah Mammoth (15168042)
gets its Polymarket price.

WHAT A READER SAW (production, 2026-09-28 ~03:30Z, ``/api/events/search?q=utah``)
---------------------------------------------------------------------------------

Nine Utah games listed as ``icehockey_other`` "Utah" cards with no crest, one
more created every day Polymarket lists a game (latest 15320100, Utah @
Lightning, created 2026-09-27 16:23Z). Oct 4 Utah @ Rangers is two cards: NHL
15320301 with no price, and OTHER HOCKEY 15307143 holding the Polymarket price.
And 15168042 (Blackhawks @ Utah Mammoth, Oct 2 01:30Z) has no Polymarket
reading, because its two markets (60199695/60199696, "Blackhawks vs. Utah")
still sit on voided shadow 15304618.

WHY: ONE MISSING NAME, TWO CONSUMERS
------------------------------------

Polymarket titles NHL games by nickname, and it has always called this club
``Utah``. ``covered_league_for_matchup`` resolves each side by an EXACT match on
``teams.name`` / ``alternate_names``, and row 118 carries only ``['Mammoth']``.
So ``Utah`` never resolves to the NHL, and two things built on that resolver
never fire for this one club:

1. #5544's minting refusal. Every Polymarket NHL phantom created since 9/13 is
   a Utah game; every other club resolves (Wild carries ``Minnesota``,
   Lightning ``Tampa Bay``, Blackhawks ``Blackhawks``).
2. #7904's Phase 1.5 retired-row relink (``_venue_confirmed_covered_fixture``,
   ``unambiguous_only=True``). It answers ``phase15_retired_left_alone`` for
   "Blackhawks vs. Utah".

The same table already spells this club's city for the other Utah franchise:
Utah Jazz (NBA, row 44) carries ``Utah``. The name is not new to the resolver;
only the NHL row is missing it.

WHAT CHANGES, AND ONE THING THAT GETS STRICTER
----------------------------------------------

``Utah`` now resolves to {NBA, NCAA football, NHL, ...}. The resolver takes the
INTERSECTION of both sides, so an NHL nickname opponent (``Blackhawks``,
``Rangers``) lands on the NHL alone, and a college opponent (``Iowa State``,
``Utah State``, ``Arkansas``) lands where it did. The one class that changes is
an opponent spelled as a city that is ALSO an NHL row's alternate
(``Colorado``, ``Minnesota``, ``Washington``): "Utah vs. Colorado" goes from
{ncaaf} to {ncaaf, nhl}. The minting refusal still refuses (it only asks whether
a covered league exists). The relink arms need the league NAMED, so they now
decline, where before they searched ncaaf. Over 200 days of Polymarket markets,
no such matchup exists: every Utah opponent was an NHL nickname or a college
spelled by school name. The tests pin both directions.

WHAT IT DOES
------------

This appends ``Utah`` to row 118's ``alternate_names``. It is a union: nothing
already there moves or goes. The write is a compare-and-set against the value
read a moment earlier, so if an ESPN sync unions a name in between (the syncs
only ever union, ``espn_aliases_to_store``), the statement changes 0 rows and
the run refuses rather than dropping that name.

**No backup table, and that is a proof rather than a habit** (the argument
``repair_8685_curated_team_alias_rows`` makes): the change is one appended
string the row did not hold before (a test asserts the BEFORE list lacks it,
case-insensitively). So the inverse is "remove exactly that string", and
``--restore`` is that compare-and-set. Anything an ESPN sync adds meanwhile
survives the undo. No DDL runs.

REFUSALS (the whole run stops, nothing is written)
--------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* the pinned id's row is not (icehockey_nhl, Utah Mammoth);
* a write that changes anything other than exactly one row.

    python3 scripts/repair_9280_utah_mammoth_polymarket_label.py            # dry run
    python3 scripts/repair_9280_utah_mammoth_polymarket_label.py --apply    # add 'Utah'
    python3 scripts/repair_9280_utah_mammoth_polymarket_label.py --restore  # undo
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

#: team id → (sport key, team name, label, ``alternate_names`` on the 2026-09-28 03:3xZ read).
#: The BEFORE list is the record the undo is proven against, not a restore source.
PINNED: dict[int, tuple[str, str, str, list[str]]] = {
    118: ("icehockey_nhl", "Utah Mammoth", "Utah", ["Mammoth"]),
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


def _holds(names: list, label: str) -> bool:
    return any(
        isinstance(n, str) and n.strip().lower() == label.lower() for n in names
    )


def plan(rows: dict[int, tuple[str, str, list | None]], *, restore: bool) -> dict:
    """Decide per pinned team, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(sport_key, name, alternate_names)``.
    Returns the ``(id, current, new)`` writes and the ``(id, reason)`` skips; raises
    ``Refused`` when a pinned id's row is not the pinned team.
    """
    write, skip = [], []
    for team_id, (sport_key, name, label, _before) in PINNED.items():
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
            if label not in current:
                skip.append((team_id, f"{label!r} absent, nothing to undo"))
                continue
            write.append((team_id, current, [n for n in current if n != label]))
        else:
            if _holds(current, label):
                skip.append((team_id, f"{label!r} already present"))
                continue
            write.append((team_id, current, current + [label]))
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
            "python3 scripts/repair_9280_utah_mammoth_polymarket_label.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
