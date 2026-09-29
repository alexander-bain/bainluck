"""#9482 — the NHL page spells the Canadiens and the Blues one way.

THE SHIP: every upcoming Canadiens card reads ``Montreal Canadiens`` and every
upcoming Blues card reads ``St Louis Blues``. On production 2026-09-29 the page
printed both ``Montreal Canadiens`` and ``Montréal Canadiens``, and both
``St Louis Blues`` and ``St. Louis Blues``: each card prints its own row's
stored name, and the rows were minted by different providers.

WHY THE CODE FIX ALONE IS NOT ENOUGH TODAY
------------------------------------------

``app/utils/espn_team_spelling.py`` makes the ESPN passes correct a
spelling-only difference — but those passes read today's board, so the Oct 3
and Oct 6 Canadiens games would keep ``Montréal`` until their own game day.

THE CANONICAL ROW PER CLUB
--------------------------

The card also serves slug, record and standings from the BOUND team row, so the
spelling follows the row StatPal's standings writer keeps current (the #9229
tie-break), read 2026-09-29:

    568  Montreal Canadiens  espn 10  standings 2026-09-29   <- canonical
    3706 Montréal Canadiens  espn 10  standings 2026-09-28
    3705 St Louis Blues      espn 19  standings 2026-09-29   <- canonical
    571  St. Louis Blues     espn 19  standings 2026-05-05

WHAT IS WRITTEN (one transaction, every UPDATE compare-and-swaps)
-----------------------------------------------------------------

    15169778  away  'Montréal Canadiens' / 3706  ->  'Montreal Canadiens' / 568
    15169783  home  'Montréal Canadiens' / 3706  ->  'Montreal Canadiens' / 568
    15319664  away  'St. Louis Blues'    / 3705  ->  'St Louis Blues'     / 3705

The third is a spelling on a side already bound to 3705. Left alone, the ESPN
pass would resolve ``St. Louis Blues`` by exact name to 571 on game day and move
the side onto May's standings.

The run acts only when every pinned side is exactly BEFORE (kickoff pinned
too); all AFTER is a no-op; any mix refuses the whole run and prints it.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks each side's BEFORE name and team id in
``backup_9482_team_spelling`` and refuses to write if the bank is short.
``--restore`` writes the BEFORE values back, only while every side is AFTER.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on a
named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_9482_nhl_club_spelling_on_upcoming_games.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_9482_nhl_club_spelling_on_upcoming_games.py --apply    # backup + write
    heroku run:detached -a bainluck -- python3 scripts/repair_9482_nhl_club_spelling_on_upcoming_games.py --restore  # undo

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

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_9482_team_spelling"

#: (event id, side) -> (kickoff ISO UTC, (name, team id) BEFORE, (name, team id) AFTER)
SIDES: dict[tuple[int, str], tuple[str, tuple[str, int], tuple[str, int]]] = {
    (15169778, "away"): (
        "2026-10-03T23:00:00+00:00",
        ("Montréal Canadiens", 3706), ("Montreal Canadiens", 568),
    ),
    (15169783, "home"): (
        "2026-10-06T23:00:00+00:00",
        ("Montréal Canadiens", 3706), ("Montreal Canadiens", 568),
    ),
    (15319664, "away"): (
        "2026-10-04T01:00:00+00:00",
        ("St. Louis Blues", 3705), ("St Louis Blues", 3705),
    ),
}

EVENT_IDS = sorted({event_id for event_id, _ in SIDES})


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(state: dict[tuple[int, str], tuple[str, tuple[str, int]]], *, restore: bool
         ) -> list[tuple[int, str, tuple[str, int], tuple[str, int]]]:
    """Return ``(event_id, side, from, to)`` writes. Pure, so the unit file drives it.

    ``state`` maps each pinned side that EXISTS to ``(kickoff_iso, (name, team_id))``.
    """
    missing = sorted(set(SIDES) - set(state))
    if missing:
        raise Refused(f"side(s) {missing} missing; refusing")
    for key, (kickoff, _before, _after) in SIDES.items():
        if state[key][0] != kickoff:
            raise Refused(f"{key} kicks off {state[key][0]}, pinned {kickoff}; refusing")
    now = {key: state[key][1] for key in SIDES}
    before = {key: spec[1] for key, spec in SIDES.items()}
    after = {key: spec[2] for key, spec in SIDES.items()}
    source, target = (after, before) if restore else (before, after)
    if now == target:
        return []
    if now != source:
        raise Refused(
            f"state {now} is neither {source} nor {target}; refusing — read the "
            "rows before deciding by hand"
        )
    return [(event_id, side, source[(event_id, side)], target[(event_id, side)])
            for event_id, side in sorted(SIDES)]


async def _read(session) -> dict:
    got = await session.execute(
        text(
            "SELECT id, commence_time, home_team_name, home_team_id, "
            "away_team_name, away_team_id FROM events WHERE id = ANY(:ids)"
        ),
        {"ids": EVENT_IDS},
    )
    rows = {int(r.id): r for r in got}
    state = {}
    for event_id, side in SIDES:
        row = rows.get(event_id)
        if row is None:
            continue
        state[(event_id, side)] = (
            row.commence_time.isoformat(),
            (getattr(row, f"{side}_team_name"), getattr(row, f"{side}_team_id")),
        )
    return state


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id integer NOT NULL,"
            " side text NOT NULL,"
            " team_name_before text,"
            " team_id_before integer,"
            " taken_at timestamptz NOT NULL DEFAULT now(),"
            " PRIMARY KEY (event_id, side))"
        )
    )
    for event_id, side in SIDES:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_TABLE} (event_id, side, team_name_before, team_id_before) "
                f"SELECT id, :side, {side}_team_name, {side}_team_id FROM events WHERE id = :id "
                "ON CONFLICT (event_id, side) DO NOTHING"
            ),
            {"id": event_id, "side": side},
        )
    await session.commit()
    banked = await session.execute(
        text(f"SELECT event_id, side, team_name_before, team_id_before FROM {BACKUP_TABLE}")
    )
    # Count only sides that banked the BEFORE value — a bank of the wrong state
    # would make the undo write the wrong name back.
    return sum(
        1 for r in banked
        if (int(r.event_id), r.side) in SIDES
        and SIDES[(int(r.event_id), r.side)][1] == (r.team_name_before, r.team_id_before)
    )


async def run(session, *, apply: bool, restore: bool) -> dict:
    writes = plan(await _read(session), restore=restore)
    written = 0
    if writes and (apply or restore):
        if apply:
            banked = await _backup(session)
            if banked < len(SIDES):
                raise Refused(f"backup holds {banked} of {len(SIDES)} sides; refusing to write")
        for event_id, side, (old_name, old_id), (new_name, new_id) in writes:
            result = await session.execute(
                text(
                    f"UPDATE events SET {side}_team_name = :new_name, {side}_team_id = :new_id "
                    f"WHERE id = :id AND {side}_team_name = :old_name AND {side}_team_id = :old_id"
                ),
                {"id": event_id, "old_name": old_name, "old_id": old_id,
                 "new_name": new_name, "new_id": new_id},
            )
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"{event_id} {side} changed under the run (no longer "
                    f"{old_name!r}/{old_id}); rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    after = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"event_id": e, "side": s, "from": list(o), "to": list(n)} for e, s, o, n in writes
        ],
        "written": written,
        "now": {f"{e}:{s}": list(after[(e, s)][1]) for e, s in SIDES if (e, s) in after},
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
            "python3 scripts/repair_9482_nhl_club_spelling_on_upcoming_games.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
