"""#8975 (second anchor) — give Tuesday's Canadiens @ Maple Leafs its sportsbook id back from the Sep 19 row.

THE SHIP: Tuesday's (2026-09-29 23:00Z) Canadiens @ Maple Leafs shows once,
with its sportsbook price beside Kalshi and Polymarket. Today its card, row
15317562, blends Kalshi and Polymarket only: every sportsbook line for the
game is written to 15168032 — the Sep 19 MTL @ TOR game, finished 1–4.

WHY (read from production 2026-09-28 07:4xZ)
--------------------------------------------

The #8975 repair (PR #8994, applied 2026-09-27 01:41Z) moved the ESPN id.
The same row carries a second anchor for the same Tuesday game, the Odds API
``external_id``:

    events 15168032  TOR v MTL  2026-09-19 23:00Z  completed 1-4  external_id 485b2953…
    events 15317562  TOR v MTL  2026-09-29 23:00Z  scheduled      external_id NULL

    odds_snapshots on 15168032: 1,832 rows 9/17 -> 2026-09-28 04:35Z, 17 sportsbooks,
    every day AFTER the Sep 19 final (220 on 9/20, 429 on 9/26, 240 on 9/27)
    odds_snapshots on 15317562: 0

A game that ended on Sep 19 is not priced for nine days after it; the only
MTL @ TOR still to play is Tuesday's. The row was minted by the Odds API in
July in one batch with its neighbours 15168031 (Sep 29 21:00Z) and 15168033
(Sep 30 00:00Z), i.e. as Tuesday's game, before the Sep 19 final was written
onto it. Registry Step 1 resolves an odds_api claim by exact ``external_id``
(``_find_by_source_id``), so every poll keeps landing on the finished row;
``external_id`` is UNIQUE, so the id cannot be given to 15317562 while
15168032 holds it.

WHAT IS WRITTEN
---------------

One transaction, in this order (the unique constraint is not deferrable, so
the id must leave 15168032 before it reaches 15317562):

    15168032  external_id 485b2953… -> NULL
    15317562  external_id NULL      -> 485b2953…

Nothing else moves: the 1,832 banked snapshots stay where they are. The next
odds poll finds 15317562 by the id and writes its lines there.

The run acts only when BOTH rows are exactly in the BEFORE state and each
still carries its pinned kickoff and team names; both exactly AFTER is a
no-op; any other state refuses the whole run and prints what it found. Every
UPDATE also compare-and-swaps on the value it expects.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks both rows' BEFORE ``external_id`` in
``backup_8975b_external_id`` and refuses to write if the bank is short.
``--restore`` runs the move backwards (15317562 back to NULL first, then
15168032 back to the id), only while both rows are exactly AFTER.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on
a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_8975b_mtl_tor_odds_id_on_the_sep19_row.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_8975b_mtl_tor_odds_id_on_the_sep19_row.py --apply    # backup + move
    heroku run:detached -a bainluck -- python3 scripts/repair_8975b_mtl_tor_odds_id_on_the_sep19_row.py --restore  # undo

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

BACKUP_TABLE = "backup_8975b_external_id"

SEP19_ROW = 15168032
SEP29_ROW = 15317562

#: The Odds API's id for the Sep 29 game, today held by the Sep 19 row.
SEP29_ODDS_ID = "485b295347cb22f002e014cb87813ed7"

#: event id -> (kickoff ISO UTC, home team, away team). Identity the id alone
#: cannot vouch for: the run refuses if either row no longer reads as this game.
PINNED: dict[int, tuple[str, str, str]] = {
    SEP19_ROW: ("2026-09-19T23:00:00+00:00", "Toronto Maple Leafs", "Montréal Canadiens"),
    SEP29_ROW: ("2026-09-29T23:00:00+00:00", "Toronto Maple Leafs", "Montreal Canadiens"),
}

BEFORE = {SEP19_ROW: SEP29_ODDS_ID, SEP29_ROW: None}
AFTER = {SEP19_ROW: None, SEP29_ROW: SEP29_ODDS_ID}

#: The move, in the order the unique constraint allows. ``--restore`` walks it backwards.
MOVES: tuple[tuple[int, str | None, str | None], ...] = (
    (SEP19_ROW, SEP29_ODDS_ID, None),
    (SEP29_ROW, None, SEP29_ODDS_ID),
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


def plan(rows: dict[int, tuple[str, str, str, str | None]], holders: list[int],
         *, restore: bool) -> list[tuple[int, str | None, str | None]]:
    """Return the ordered writes to make. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(kickoff_iso, home, away, external_id)``.
    ``holders`` is every event id holding ``SEP29_ODDS_ID``.
    """
    missing = sorted(set(PINNED) - set(rows))
    if missing:
        raise Refused(f"row(s) {missing} missing; refusing")
    for event_id, pinned in PINNED.items():
        if rows[event_id][:3] != pinned:
            raise Refused(
                f"row {event_id} reads {rows[event_id][:3]}, pinned {pinned}; refusing"
            )
    foreign = sorted(set(holders) - set(PINNED))
    if foreign:
        raise Refused(f"unpinned row(s) {foreign} hold {SEP29_ODDS_ID}; refusing")

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


async def _read(session) -> tuple[dict, list[int]]:
    got = await session.execute(
        text(
            "SELECT id, commence_time, home_team_name, away_team_name, external_id "
            "FROM events WHERE id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    rows = {
        int(r.id): (r.commence_time.isoformat(), r.home_team_name, r.away_team_name, r.external_id)
        for r in got
    }
    held = await session.execute(
        text("SELECT id FROM events WHERE external_id = :xid"), {"xid": SEP29_ODDS_ID}
    )
    return rows, sorted(int(r.id) for r in held)


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id integer PRIMARY KEY,"
            " external_id_before text,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, external_id_before) "
            "SELECT id, external_id FROM events WHERE id = ANY(:ids) "
            "ON CONFLICT (event_id) DO NOTHING"
        ),
        {"ids": sorted(PINNED)},
    )
    await session.commit()
    banked = await session.execute(
        text(
            f"SELECT event_id, external_id_before FROM {BACKUP_TABLE} WHERE event_id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    # Count only rows that banked the BEFORE value — a bank of the wrong state
    # would make the undo write the wrong id back.
    return sum(1 for r in banked if BEFORE[int(r.event_id)] == r.external_id_before)


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
                    "UPDATE events SET external_id = :new "
                    "WHERE id = :id AND external_id IS NOT DISTINCT FROM :old"
                ),
                {"id": event_id, "old": old, "new": new},
            )
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"row {event_id} changed under the run (external_id no longer {old!r}); "
                    "rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    after_rows, after_holders = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"event_id": e, "external_id_from": o, "external_id_to": n} for e, o, n in writes
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
            "python3 scripts/repair_8975b_mtl_tor_odds_id_on_the_sep19_row.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
