"""#8975 — give Tuesday's Canadiens @ Maple Leafs its ESPN id back from the Sep 19 row.

THE SHIP: Tuesday's (2026-09-29 23:00Z) Canadiens @ Maple Leafs shows once,
with its live score. Today the row readers are served, 15317562, carries no
``espn_id``, and it cannot be given one: ESPN's id for that game, 401891827,
sits on 15168032 — the Sep 19 MTL @ TOR game, finished 1–4.

WHY (read from production and from ESPN 2026-09-27 00:45Z)
----------------------------------------------------------

    ESPN summary?event=401891827  MTL @ TOR  2026-09-29T23:00Z  scheduled
    ESPN summary?event=401881922  MTL @ TOR  2026-09-19T23:00Z  FINAL TOR 1-4 MTL

    events 15168032  TOR v MTL  2026-09-19 23:00Z  completed 1-4  espn_id 401891827
    events 15317562  TOR v MTL  2026-09-29 23:00Z  scheduled      espn_id NULL

15168032 is the right game with an id that points ten days ahead. No row
holds 401881922. Two harms follow: registry Step 1 resolves an ESPN claim by
exact ``espn_id``, so Tuesday's ESPN score lands on the finished row; and
``uq_events_espn_id`` refuses 401891827 to 15317562 while 15168032 holds it
(``stamp_espn_id_if_unheld`` counts it as ``events_id_held`` every pass).

The other Sep 19 row, 15311331, holds 401881923 — the split-squad game at
Bell Centre — and is not touched here.

WHAT IS WRITTEN
---------------

One transaction, in this order (the unique index is not deferrable, so the
id must leave 15168032 before it reaches 15317562):

    15168032  espn_id 401891827 -> 401881922
    15317562  espn_id NULL      -> 401891827

The run acts only when BOTH rows are exactly in the BEFORE state and each
still carries its pinned kickoff and team names; both exactly AFTER is a
no-op; any other state refuses the whole run and prints what it found. Every
UPDATE also compare-and-swaps on the value it expects.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks both rows' BEFORE ``espn_id`` in
``backup_8975_espn_id`` and refuses to write if the bank is short.
``--restore`` runs the move backwards (15317562 back to NULL first, then
15168032 back to 401891827), only while both rows are exactly AFTER.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on
a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_8975_mtl_tor_espn_id_on_the_sep19_row.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_8975_mtl_tor_espn_id_on_the_sep19_row.py --apply    # backup + move
    heroku run:detached -a bainluck -- python3 scripts/repair_8975_mtl_tor_espn_id_on_the_sep19_row.py --restore  # undo

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

BACKUP_TABLE = "backup_8975_espn_id"

SEP19_ROW = 15168032
SEP29_ROW = 15317562

#: ESPN's id for the Sep 29 game, today held by the Sep 19 row.
SEP29_ESPN_ID = "401891827"
#: ESPN's id for the Sep 19 game, held by no row today.
SEP19_ESPN_ID = "401881922"

#: event id -> (kickoff ISO UTC, home team, away team). Identity the id alone
#: cannot vouch for: the run refuses if either row no longer reads as this game.
PINNED: dict[int, tuple[str, str, str]] = {
    SEP19_ROW: ("2026-09-19T23:00:00+00:00", "Toronto Maple Leafs", "Montréal Canadiens"),
    SEP29_ROW: ("2026-09-29T23:00:00+00:00", "Toronto Maple Leafs", "Montreal Canadiens"),
}

BEFORE = {SEP19_ROW: SEP29_ESPN_ID, SEP29_ROW: None}
AFTER = {SEP19_ROW: SEP19_ESPN_ID, SEP29_ROW: SEP29_ESPN_ID}

#: The move, in the order the unique index allows. ``--restore`` walks it backwards.
MOVES: tuple[tuple[int, str | None, str | None], ...] = (
    (SEP19_ROW, SEP29_ESPN_ID, SEP19_ESPN_ID),
    (SEP29_ROW, None, SEP29_ESPN_ID),
)


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(rows: dict[int, tuple[str, str, str, str | None]], holders: dict[str, list[int]],
         *, restore: bool) -> list[tuple[int, str | None, str | None]]:
    """Return the ordered writes to make. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(kickoff_iso, home, away, espn_id)``.
    ``holders`` maps each of the two ESPN ids to every event id holding it.
    """
    missing = sorted(set(PINNED) - set(rows))
    if missing:
        raise Refused(f"row(s) {missing} missing; refusing")
    for event_id, pinned in PINNED.items():
        if rows[event_id][:3] != pinned:
            raise Refused(
                f"row {event_id} reads {rows[event_id][:3]}, pinned {pinned}; refusing"
            )
    pinned_ids = set(PINNED)
    foreign = {
        eid: sorted(set(h) - pinned_ids) for eid, h in holders.items() if set(h) - pinned_ids
    }
    if foreign:
        raise Refused(f"an unpinned row holds a pinned ESPN id {foreign}; refusing")

    state = {event_id: rows[event_id][3] for event_id in PINNED}
    source, target = (AFTER, BEFORE) if restore else (BEFORE, AFTER)
    if state == target:
        return []
    if state != source:
        raise Refused(
            f"state {state} is neither {source} nor {target}; refusing — read "
            "both rows before deciding by hand"
        )
    if restore:
        return [(event_id, new, old) for event_id, old, new in reversed(MOVES)]
    return list(MOVES)


async def _read(session) -> tuple[dict, dict]:
    got = await session.execute(
        text(
            "SELECT id, commence_time, home_team_name, away_team_name, espn_id "
            "FROM events WHERE id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    rows = {
        int(r.id): (r.commence_time.isoformat(), r.home_team_name, r.away_team_name, r.espn_id)
        for r in got
    }
    held = await session.execute(
        text("SELECT espn_id, id FROM events WHERE espn_id = ANY(:eids)"),
        {"eids": [SEP19_ESPN_ID, SEP29_ESPN_ID]},
    )
    holders: dict[str, list[int]] = {}
    for r in held:
        holders.setdefault(r.espn_id, []).append(int(r.id))
    return rows, holders


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id integer PRIMARY KEY,"
            " espn_id_before text,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, espn_id_before) "
            "SELECT id, espn_id FROM events WHERE id = ANY(:ids) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {"ids": sorted(PINNED)},
    )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT event_id, espn_id_before FROM {BACKUP_TABLE} WHERE event_id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    # Count only rows that banked the BEFORE value — a bank of the wrong state
    # would make the undo write the wrong id back.
    return sum(1 for r in banked if BEFORE[int(r.event_id)] == r.espn_id_before)


async def run(session, *, apply: bool, restore: bool) -> dict:
    rows, holders = await _read(session)
    writes = plan(rows, holders, restore=restore)
    written = 0
    if writes and (apply or restore):
        if apply:
            banked = await _backup(session)
            if banked < len(PINNED):
                raise Refused(f"backup holds {banked} of {len(PINNED)} rows; refusing to move")
        for event_id, old, new in writes:
            result = await session.execute(
                text(
                    "UPDATE events SET espn_id = :new "
                    "WHERE id = :id AND espn_id IS NOT DISTINCT FROM :old"
                ),
                {"id": event_id, "old": old, "new": new},
            )
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"row {event_id} changed under the run (espn_id no longer {old!r}); "
                    "rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    after_rows, after_holders = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"event_id": e, "espn_id_from": o, "espn_id_to": n} for e, o, n in writes
        ],
        "written": written,
        "now": {str(e): after_rows.get(e, (None,) * 4)[3] for e in PINNED},
        "holders": after_holders,
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
            "python3 scripts/repair_8975_mtl_tor_espn_id_on_the_sep19_row.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
