"""#2978 — NLCS Game 2's ESPN id moves off the finished Game 1 row onto Game 2.

THE SHIP: NLCS Game 2 (Brewers v Dodgers, 2026-10-12 21:00Z) is anchored to
its own ESPN game, and the finished Game 1 stays finished.

WHY (production + ESPN, read 2026-10-12 11:4xZ)
-----------------------------------------------

    events 15326811  MIL v LAD  2026-10-12 00:00Z  completed 2-1  espn_id 401908031  (odds_api)
    events 15326812  MIL v LAD  2026-10-12 00:00Z  completed 2-1  espn_id 401908030  (espn)
    events 15329040  MIL v LAD  2026-10-12 21:00Z  scheduled      espn_id NULL       (odds_api)

ESPN's own summary: 401908030 = "NLCS - Game 1", Final MIL 2 LAD 1;
401908031 = "NLCS - Game 2", 2026-10-12T21:00Z, Scheduled.

So the Game 1 row 15326811 wears Game 2's id. ``uq_events_espn_id`` refuses
the id to the Game 2 row while 15326811 holds it, so every live pass
name-matches Game 2 and logs "stamp REFUSED … event 15326811 already holds
it". The Game 2 row then has no ESPN anchor: no ESPN line on its chart (ESPN
win-prob snapshots are written for id matches only) and no box score. And
after tonight's final, ``game_state_backfill`` fetches the box score by
``espn_id`` — so Game 2's box score would be written onto Game 1's row.

WHAT IS WRITTEN
---------------

One transaction, in this order (the unique index is not deferrable, so the
id must leave 15326811 before it reaches 15329040):

    15326811  espn_id 401908031 -> NULL
    15329040  espn_id NULL      -> 401908031

15326811 gets NULL, not 401908030: Game 1's real id is already on 15326812,
the ESPN-created row for the same game, and the unique index allows one
holder. Those two rows are one game twice; folding them is a separate repair
and nothing here touches 15326812. With a NULL, the id backfill cannot hand
401908031 back: it is held by 15329040, and its ESPN start is 21h from
15326811's kickoff, past every time gate.

Nothing else moves: scores, status, ``box_score_data`` and snapshots stay
where they are.

The run acts only when both rows are exactly in the BEFORE state and each
still reads as its pinned game; both exactly AFTER is a no-op; any other
state refuses the whole run and prints what it found. Game 1 is finished,
so its kickoff is pinned to the minute. Game 2's kickoff may still be nudged
by a schedule writer before first pitch, so it is pinned to within 3 hours
of 21:00Z (the same-game bound ``NAME_ONLY_SAME_GAME_SECONDS``). Every
UPDATE also compare-and-swaps on the value it expects. The run also refuses
if any unpinned row holds 401908031, or if a provider anchor binds 401908031
to any event other than Game 2.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks both rows' BEFORE ``espn_id`` in
``backup_2978_espn_id`` and refuses to write if the bank is short.
``--restore`` runs the move backwards (15329040 back to NULL first, then
15326811 back to the id), only while both rows are exactly AFTER.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on
a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_2978_nlcs_game2_espn_id_on_the_game1_row.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_2978_nlcs_game2_espn_id_on_the_game1_row.py --apply    # backup + move
    heroku run:detached -a bainluck -- python3 scripts/repair_2978_nlcs_game2_espn_id_on_the_game1_row.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_2978_espn_id"

GAME1_ROW = 15326811
GAME2_ROW = 15329040

#: ESPN's id for NLCS Game 2, today held by the Game 1 row.
GAME2_ESPN_ID = "401908031"

HOME = "Milwaukee Brewers"
AWAY = "Los Angeles Dodgers"

#: event id -> (kickoff ISO UTC, home team, away team). Identity the id alone
#: cannot vouch for: the run refuses if either row no longer reads as this game.
PINNED: dict[int, tuple[str, str, str]] = {
    GAME1_ROW: ("2026-10-12T00:00:00+00:00", HOME, AWAY),
    GAME2_ROW: ("2026-10-12T21:00:00+00:00", HOME, AWAY),
}

#: How far each row's kickoff may sit from its pinned one. Game 1 is final and
#: frozen; Game 2 may be nudged before first pitch by a schedule writer.
KICKOFF_SLACK_S: dict[int, int] = {GAME1_ROW: 0, GAME2_ROW: 3 * 60 * 60}

BEFORE = {GAME1_ROW: GAME2_ESPN_ID, GAME2_ROW: None}
AFTER = {GAME1_ROW: None, GAME2_ROW: GAME2_ESPN_ID}

#: The move, in the order the unique index allows. ``--restore`` walks it backwards.
MOVES: tuple[tuple[int, str | None, str | None], ...] = (
    (GAME1_ROW, GAME2_ESPN_ID, None),
    (GAME2_ROW, None, GAME2_ESPN_ID),
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


def _reads_as_pinned(event_id: int, row: tuple) -> bool:
    kickoff, home, away = PINNED[event_id]
    if (row[1], row[2]) != (home, away):
        return False
    gap = abs(
        (datetime.fromisoformat(row[0]) - datetime.fromisoformat(kickoff)).total_seconds()
    )
    return gap <= KICKOFF_SLACK_S[event_id]


def plan(rows: dict[int, tuple[str, str, str, str | None]], holders: list[int],
         anchored_to: list[int], *, restore: bool) -> list[tuple[int, str | None, str | None]]:
    """Return the ordered writes to make. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(kickoff_iso, home, away, espn_id)``.
    ``holders`` is every event id whose ``espn_id`` is ``GAME2_ESPN_ID``.
    ``anchored_to`` is every event id an ESPN provider anchor binds ``GAME2_ESPN_ID`` to.
    """
    missing = sorted(set(PINNED) - set(rows))
    if missing:
        raise Refused(f"row(s) {missing} missing; refusing")
    for event_id in PINNED:
        if not _reads_as_pinned(event_id, rows[event_id]):
            raise Refused(
                f"row {event_id} reads {rows[event_id][:3]}, pinned {PINNED[event_id]}; refusing"
            )
    foreign = sorted(set(holders) - set(PINNED))
    if foreign:
        raise Refused(f"unpinned row(s) {foreign} hold {GAME2_ESPN_ID}; refusing")
    stray = sorted(set(anchored_to) - {GAME2_ROW})
    if stray:
        raise Refused(
            f"an ESPN anchor binds {GAME2_ESPN_ID} to {stray}, not {GAME2_ROW}; refusing"
        )

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


async def _read(session) -> tuple[dict, list[int], list[int]]:
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
        text("SELECT id FROM events WHERE espn_id = :eid"), {"eid": GAME2_ESPN_ID}
    )
    anchored = await session.execute(
        text(
            "SELECT event_id FROM event_provider_anchors "
            "WHERE source = 'espn' AND source_id = :eid"
        ),
        {"eid": GAME2_ESPN_ID},
    )
    return (
        rows,
        sorted(int(r.id) for r in held),
        sorted(int(r.event_id) for r in anchored),
    )


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
    rows, holders, anchored_to = await _read(session)
    writes = plan(rows, holders, anchored_to, restore=restore)
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
    after_rows, after_holders, after_anchored = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"event_id": e, "espn_id_from": o, "espn_id_to": n} for e, o, n in writes
        ],
        "written": written,
        "now": {str(e): after_rows.get(e, (None,) * 4)[3] for e in PINNED},
        "holders": after_holders,
        "anchored_to": after_anchored,
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
            "python3 scripts/repair_2978_nlcs_game2_espn_id_on_the_game1_row.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
