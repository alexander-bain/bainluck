"""#9729 — Washington's page stops listing UConn–Lafayette; LSU's stops listing Navy–Towson.

THE SHIP: the Washington Huskies team page no longer shows UConn's 56–7 win
over Lafayette (Sep 5) as a Washington game, and the LSU Tigers page no longer
shows Navy 42 – Towson 15 (Sep 5) as an LSU loss. The UConn Huskies page gains
its own game.

WHY (read from production 2026-09-30 08:50Z)
--------------------------------------------

Both rows were written by the Odds API path before the #1918 write-time guard
(2026-07-27). The names are right; one side's ``team_id`` points at a club that
only shares the mascot, so every surface keyed on ``team_id`` lists the game
under the wrong club:

    events 15181893  "UConn Huskies" v "Lafayette Leopards"   home_team_id 15301 -> Washington Huskies
    events 15181945  "Navy Midshipmen" v "Towson Tigers"      away_team_id     9 -> LSU Tigers

In the event's own sport (americanfootball_ncaaf, sport_id 760) "UConn Huskies"
now has exactly one exact-name row, 19768 (ESPN 41); "Towson Tigers" has none,
so that side points at no team (NULL), which is what the #1798 rail's
re-derivation would say if it were allowed to write a zero-candidate side (it
sends one to review and never writes it, which is why this is a script).

Two ``team_identity_mapping`` rows from before #7188 point "Lafayette" at
Washington for the same sport; the matchup fragment was paired with its
position in the market name instead of the side it names. A same-key re-upsert
refreshes only ``updated_at``, so they stay wrong until moved:

    43874196  kalshi      "Lafayette"  15301 Washington Huskies -> 17115 Lafayette Leopards
    45278383  polymarket  "Lafayette"  15301 Washington Huskies -> 17115 Lafayette Leopards

NOT written, and why: 48836904 (kalshi "Eastern Washington" -> Washington) and
49820694 (espn 331 "Eastern Washington Eagles" -> Eastern Michigan) have no
correct club to move to, and deleting a row a resolver may auto-register again
proves nothing; no game is mis-listed through either today (production read
08:55Z). They stay on #9729.

WHAT IS WRITTEN
---------------

Four compare-and-swap UPDATEs of ONE column each, in one transaction. The run
acts only when every row is exactly BEFORE, still reads as itself (event names
and sport; mapping source, name and sport) and both target clubs still
dereference to the named club in sport 760. All four exactly AFTER is a no-op;
anything else refuses the whole run and prints what it found.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks every written column's BEFORE value in
``backup_9729_team_bindings`` and refuses to write if the bank is short or
banked a different state. ``--restore`` writes BEFORE back, only while all four
rows are exactly AFTER. ``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a
person's invocation on a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_9729_cross_mascot_team_bindings.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_9729_cross_mascot_team_bindings.py --apply    # backup + write
    heroku run:detached -a bainluck -- python3 scripts/repair_9729_cross_mascot_team_bindings.py --restore  # undo

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` or ``bainluck-heavy``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

BACKUP_TABLE = "backup_9729_team_bindings"

NCAAF_SPORT_ID = 760
NCAAF = "americanfootball_ncaaf"

WASHINGTON = 15301
LSU = 9
UCONN = 19768
LAFAYETTE = 17115

#: Target clubs the run writes, and the (name, sport_id) each must still dereference to.
TARGETS: dict[int, tuple[str, int]] = {
    UCONN: ("UConn Huskies", NCAAF_SPORT_ID),
    LAFAYETTE: ("Lafayette Leopards", NCAAF_SPORT_ID),
}


class Write(NamedTuple):
    table: str  # "events" | "team_identity_mapping"
    row_id: int
    column: str
    before: Optional[int]
    after: Optional[int]
    #: What the row must still read as, besides the column being moved.
    identity: tuple


WRITES: tuple[Write, ...] = (
    Write("events", 15181893, "home_team_id", WASHINGTON, UCONN,
          ("UConn Huskies", "Lafayette Leopards", NCAAF_SPORT_ID)),
    Write("events", 15181945, "away_team_id", LSU, None,
          ("Navy Midshipmen", "Towson Tigers", NCAAF_SPORT_ID)),
    Write("team_identity_mapping", 43874196, "team_id", WASHINGTON, LAFAYETTE,
          ("kalshi", "Lafayette", NCAAF)),
    Write("team_identity_mapping", 45278383, "team_id", WASHINGTON, LAFAYETTE,
          ("polymarket", "Lafayette", NCAAF)),
)

Key = tuple[str, int, str]


def key(w: Write) -> Key:
    return (w.table, w.row_id, w.column)


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(identity: dict[Key, tuple], state: dict[Key, Optional[int]],
         targets: dict[int, tuple[str, int]], *, restore: bool) -> list[Write]:
    """Return the writes to make, each oriented (before -> after) for this run.

    Pure, so the unit file drives it. ``identity`` and ``state`` map each
    write's key to what the row reads as and the moving column's value, for
    rows that EXIST; ``targets`` maps each target club that exists to its
    ``(name, sport_id)``.
    """
    missing = sorted(key(w) for w in WRITES if key(w) not in identity)
    if missing:
        raise Refused(f"row(s) {missing} missing; refusing")
    for w in WRITES:
        if identity[key(w)] != w.identity:
            raise Refused(f"row {key(w)} reads {identity[key(w)]}, pinned {w.identity}; refusing")
    for team_id, want in TARGETS.items():
        if targets.get(team_id) != want:
            raise Refused(f"team {team_id} reads {targets.get(team_id)}, pinned {want}; refusing")

    now = {key(w): state[key(w)] for w in WRITES}
    before = {key(w): w.before for w in WRITES}
    after = {key(w): w.after for w in WRITES}
    source, target = (after, before) if restore else (before, after)
    if now == target:
        return []
    if now != source:
        off = {k: v for k, v in now.items() if v not in (before[k], after[k])}
        raise Refused(
            f"state is neither {'AFTER' if restore else 'BEFORE'} nor "
            f"{'BEFORE' if restore else 'AFTER'} (off-plan: {off}, full state {now}); "
            "refusing — read the rows before deciding by hand"
        )
    if restore:
        return [w._replace(before=w.after, after=w.before) for w in reversed(WRITES)]
    return list(WRITES)


def update_sql(w: Write) -> str:
    """One compare-and-swap UPDATE of exactly one column."""
    assert w.table in ("events", "team_identity_mapping") and w.column in (
        "home_team_id", "away_team_id", "team_id"
    ), w
    return (
        f"UPDATE {w.table} SET {w.column} = :after "
        f"WHERE id = :id AND {w.column} IS NOT DISTINCT FROM :before"
    )


async def _read(session) -> tuple[dict, dict, dict]:
    identity: dict[Key, tuple] = {}
    state: dict[Key, Optional[int]] = {}
    event_ids = sorted({w.row_id for w in WRITES if w.table == "events"})
    mapping_ids = sorted({w.row_id for w in WRITES if w.table == "team_identity_mapping"})
    events = {
        int(r.id): r
        for r in await session.execute(
            text(
                "SELECT id, home_team_name, away_team_name, sport_id, home_team_id, away_team_id "
                "FROM events WHERE id = ANY(:ids)"
            ),
            {"ids": event_ids},
        )
    }
    mappings = {
        int(r.id): r
        for r in await session.execute(
            text(
                "SELECT id, source, source_name, sport_key, team_id "
                "FROM team_identity_mapping WHERE id = ANY(:ids)"
            ),
            {"ids": mapping_ids},
        )
    }
    for w in WRITES:
        if w.table == "events" and w.row_id in events:
            r = events[w.row_id]
            identity[key(w)] = (r.home_team_name, r.away_team_name, r.sport_id)
            state[key(w)] = getattr(r, w.column)
        elif w.table == "team_identity_mapping" and w.row_id in mappings:
            r = mappings[w.row_id]
            identity[key(w)] = (r.source, r.source_name, r.sport_key)
            state[key(w)] = r.team_id
    targets = {
        int(r.id): (r.name, r.sport_id)
        for r in await session.execute(
            text("SELECT id, name, sport_id FROM teams WHERE id = ANY(:ids)"),
            {"ids": sorted(TARGETS)},
        )
    }
    return identity, state, targets


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " tbl text NOT NULL,"
            " row_id integer NOT NULL,"
            " col text NOT NULL,"
            " value_before integer,"
            " taken_at timestamptz NOT NULL DEFAULT now(),"
            " PRIMARY KEY (tbl, row_id, col))"
        )
    )
    for w in WRITES:
        # The column name comes from the pinned WRITES, never from input.
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_TABLE} (tbl, row_id, col, value_before) "
                f"SELECT :tbl, id, :col, {w.column} FROM {w.table} WHERE id = :id "
                "ON CONFLICT (tbl, row_id, col) DO NOTHING"
            ),
            {"tbl": w.table, "col": w.column, "id": w.row_id},
        )
    await session.commit()
    banked = await session.execute(
        text(f"SELECT tbl, row_id, col, value_before FROM {BACKUP_TABLE}")
    )
    want = {key(w): w.before for w in WRITES}
    # Count only rows that banked the BEFORE value — a bank of the wrong state
    # would make the undo write the wrong value back.
    return sum(
        1 for r in banked
        if (r.tbl, int(r.row_id), r.col) in want and want[(r.tbl, int(r.row_id), r.col)] == r.value_before
    )


async def run(session, *, apply: bool, restore: bool) -> dict:
    identity, state, targets = await _read(session)
    writes = plan(identity, state, targets, restore=restore)
    written = 0
    if writes and (apply or restore):
        if apply:
            banked = await _backup(session)
            if banked < len(WRITES):
                raise Refused(f"backup holds {banked} of {len(WRITES)} BEFORE values; refusing to write")
        for w in writes:
            result = await session.execute(
                text(update_sql(w)), {"id": w.row_id, "before": w.before, "after": w.after}
            )
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"row {key(w)} changed under the run (no longer {w.before}); "
                    "rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    _, after_state, _ = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [
            {"table": w.table, "id": w.row_id, "column": w.column, "from": w.before, "to": w.after}
            for w in writes
        ],
        "written": written,
        "now": {f"{t}:{i}:{c}": v for (t, i, c), v in after_state.items()},
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
            "python3 scripts/repair_9729_cross_mascot_team_bindings.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
