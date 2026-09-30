"""#9702 — Chiefs–Chargers and Jets–Vikings come back; Cowboys–Seahawks' sportsbook id reaches its Dec 8 row.

THE SHIP: the Chiefs' home game against the Chargers (Oct 18) and the Jets'
home game against the Vikings (Jan 3) show up again on search, the team pages
and Sports. Today neither game has a row a reader can reach: each one's only
row is dated to an August preseason slot and closed.

WHY (read from production and ESPN 2026-09-30 03:30Z, re-read 04:58Z)
-----------------------------------------------------------------------

On 2026-08-15 ESPN's scoreboard held only preseason games. The ESPN scheduled
pass paired each ``scheduled`` row with the first ESPN game whose team names
fit, with no date check, and moved ``commence_time`` onto it by any amount
(writer fixed by ``caefa947b7``, #1947, 2026-08-18; the live-pass name arm by
#2049). The stale-close pass then closed the moved rows with no score:

    events 14781719  KC v LAC  2026-08-15 20:00Z  closed     espn 401873006  (real: 2026-10-18 20:25Z)
        moved onto 401873283 LAR @ KC preseason — away "Los Angeles" fit
    events 15184679  NYJ v MIN 2026-08-15 17:00Z  closed     espn 401873163  (real: 2027-01-03 18:00Z)
        moved onto 401873280 MIN @ NYG preseason — home "New York" fit
    events 14780590  SEA v DAL 2026-08-16 00:00Z  completed  espn 401873279 (the preseason game)
        holds the Dec 8 game's Odds API id 0db4646c…
    events 15304746  SEA v DAL 2026-12-08 01:15Z  scheduled  espn 401873108  external_id NULL

The two moved rows still hold their real regular-season ESPN id and Odds API
id, so no rail recreates them: every claim for the game resolves to the
closed August row. Both also took ``llm_importance='exhibition'`` from the
preseason game and a ``box_score_data`` stamp ``{"error": "not_available"}``
fetched the night of the move, which would keep the post-game box-score pass
(``box_score_data IS NULL``) off the real game after it is played.

14780590 IS the preseason game in every field but its ``external_id``; the
Dec 8 row 15304746 is a correct, separate row with no sportsbook id.

WHAT IS WRITTEN
---------------

One transaction, in this order:

    14781719  commence 2026-08-15 20:00Z -> 2026-10-18 20:25Z, status closed -> scheduled,
              completed_at -> NULL, llm_importance exhibition -> regular_season,
              box_score_data {"error": "not_available", ...} -> NULL
    15184679  the same five columns; commence -> 2027-01-03 18:00Z
    14780590  external_id 0db4646c… -> NULL        (UNIQUE: the id leaves first)
    15304746  external_id NULL      -> 0db4646c…

Nothing else moves: banked odds snapshots stay where they are, as in #8975b.

The run acts only when all four rows are exactly in the BEFORE state and each
still reads as its game (teams + ESPN id, plus the Odds API id on the two
moved rows); all four exactly AFTER is a no-op; any other state refuses the
whole run and prints what it found. Every UPDATE compare-and-swaps on every
column it writes.

THE BACKUP AND THE UNDO
-----------------------

``--apply`` first banks every written column's BEFORE value in
``backup_9702_nfl_rows`` and refuses to write if the bank is short or banked a
different state. ``--restore`` runs the writes backwards (15304746 back to
NULL first), only while all four rows are exactly AFTER.
``CREATE TABLE IF NOT EXISTS`` is runtime DDL behind a person's invocation on
a named app: notice 47(c), not migration-class.

    heroku run:detached -a bainluck -- python3 scripts/repair_9702_nfl_rows_moved_to_a_preseason_slot.py            # dry run
    heroku run:detached -a bainluck -- python3 scripts/repair_9702_nfl_rows_moved_to_a_preseason_slot.py --apply    # backup + write
    heroku run:detached -a bainluck -- python3 scripts/repair_9702_nfl_rows_moved_to_a_preseason_slot.py --restore  # undo

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

BACKUP_TABLE = "backup_9702_nfl_rows"

KC_LAC = 14781719
NYJ_MIN = 15184679
SEA_DAL_PRESEASON = 14780590
SEA_DAL_DEC8 = 15304746

#: The Odds API's id for the Dec 8 Cowboys @ Seahawks game, today held by the preseason row.
DEC8_ODDS_ID = "0db4646c964ecdff19957373fe707546"

#: The columns this run may write, and how each is read and compared.
COLUMNS = ("commence_time", "status", "completed_at", "llm_importance", "box_score_data", "external_id")
TIMESTAMP_COLUMNS = frozenset({"commence_time", "completed_at"})
JSONB_COLUMNS = frozenset({"box_score_data"})

#: event id -> (home, away, espn_id, external_id or None to leave unpinned).
#: Identity the moving columns cannot vouch for: the run refuses if a row no
#: longer reads as this game.
PINNED: dict[int, tuple[str, str, str, str | None]] = {
    KC_LAC: ("Kansas City Chiefs", "Los Angeles Chargers", "401873006", "20fefae8c296247460ba5773caa42218"),
    NYJ_MIN: ("New York Jets", "Minnesota Vikings", "401873163", "bfe51fa0034c9d22a69ffd80e2d717f5"),
    SEA_DAL_PRESEASON: ("Seattle Seahawks", "Dallas Cowboys", "401873279", None),
    SEA_DAL_DEC8: ("Seattle Seahawks", "Dallas Cowboys", "401873108", None),
}

# ``box_score_data::text`` exactly as Postgres renders the stored jsonb.
_KC_LAC_BOX = '{"error": "not_available", "source": "espn", "fetched_at": "2026-08-16T01:02:10.703871+00:00"}'
_NYJ_MIN_BOX = '{"error": "not_available", "source": "espn", "fetched_at": "2026-08-15T22:00:59.128161+00:00"}'

_SEA_DAL_PRESEASON_FIXED = {
    "commence_time": "2026-08-16T00:00:00+00:00",
    "status": "completed",
    "completed_at": "2026-08-16T03:01:06.853130+00:00",
    "llm_importance": "exhibition",
}
_SEA_DAL_DEC8_FIXED = {
    "commence_time": "2026-12-08T01:15:00+00:00",
    "status": "scheduled",
    "completed_at": None,
    "llm_importance": "regular_season",
    "box_score_data": None,
}

BEFORE: dict[int, dict[str, str | None]] = {
    KC_LAC: {
        "commence_time": "2026-08-15T20:00:00+00:00",
        "status": "closed",
        "completed_at": "2026-08-16T00:08:51.037456+00:00",
        "llm_importance": "exhibition",
        "box_score_data": _KC_LAC_BOX,
        "external_id": PINNED[KC_LAC][3],
    },
    NYJ_MIN: {
        "commence_time": "2026-08-15T17:00:00+00:00",
        "status": "closed",
        "completed_at": "2026-08-15T20:40:30.997331+00:00",
        "llm_importance": "exhibition",
        "box_score_data": _NYJ_MIN_BOX,
        "external_id": PINNED[NYJ_MIN][3],
    },
    SEA_DAL_PRESEASON: {**_SEA_DAL_PRESEASON_FIXED, "external_id": DEC8_ODDS_ID},
    SEA_DAL_DEC8: {**_SEA_DAL_DEC8_FIXED, "external_id": None},
}

AFTER: dict[int, dict[str, str | None]] = {
    KC_LAC: {
        **BEFORE[KC_LAC],
        "commence_time": "2026-10-18T20:25:00+00:00",  # ESPN 401873006, week 6
        "status": "scheduled",
        "completed_at": None,
        "llm_importance": "regular_season",
        "box_score_data": None,
    },
    NYJ_MIN: {
        **BEFORE[NYJ_MIN],
        "commence_time": "2027-01-03T18:00:00+00:00",  # ESPN 401873163, week 17
        "status": "scheduled",
        "completed_at": None,
        "llm_importance": "regular_season",
        "box_score_data": None,
    },
    SEA_DAL_PRESEASON: {**BEFORE[SEA_DAL_PRESEASON], "external_id": None},
    SEA_DAL_DEC8: {**BEFORE[SEA_DAL_DEC8], "external_id": DEC8_ODDS_ID},
}

#: Write order for ``--apply``. The external_id must leave the preseason row
#: before it reaches the Dec 8 row (UNIQUE, not deferrable). ``--restore``
#: walks it backwards.
ORDER: tuple[int, ...] = (KC_LAC, NYJ_MIN, SEA_DAL_PRESEASON, SEA_DAL_DEC8)

Write = tuple[int, dict[str, str | None], dict[str, str | None]]


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def _diff(event_id: int, frm: dict, to: dict) -> Write:
    changed = [c for c in COLUMNS if c in frm and frm[c] != to[c]]
    return (event_id, {c: frm[c] for c in changed}, {c: to[c] for c in changed})


def plan(identity: dict[int, tuple[str, str, str, str | None]],
         state: dict[int, dict[str, str | None]], holders: list[int],
         *, restore: bool) -> list[Write]:
    """Return the ordered writes to make. Pure, so the unit file drives it.

    ``identity`` maps each pinned id that EXISTS to ``(home, away, espn_id, external_id)``;
    ``state`` maps it to its ``COLUMNS`` values; ``holders`` is every event id
    holding ``DEC8_ODDS_ID``. A row's state is compared only on the columns its
    BEFORE pins (the preseason row's real box score is not ours to pin).
    """
    missing = sorted(set(PINNED) - set(identity))
    if missing:
        raise Refused(f"row(s) {missing} missing; refusing")
    for event_id, (home, away, espn_id, xid) in PINNED.items():
        got = identity[event_id]
        if got[:3] != (home, away, espn_id) or (xid is not None and got[3] != xid):
            raise Refused(
                f"row {event_id} reads {got}, pinned {PINNED[event_id]}; refusing"
            )
    foreign = sorted(set(holders) - {SEA_DAL_PRESEASON, SEA_DAL_DEC8})
    if foreign:
        raise Refused(f"unpinned row(s) {foreign} hold {DEC8_ODDS_ID}; refusing")

    now = {event_id: {c: state[event_id][c] for c in BEFORE[event_id]} for event_id in PINNED}
    source, target = (AFTER, BEFORE) if restore else (BEFORE, AFTER)
    if now == target:
        return []
    if now != source:
        drift = {
            e: {c: v for c, v in now[e].items() if v not in (BEFORE[e][c], AFTER[e][c])}
            for e in PINNED
        }
        raise Refused(
            f"state is neither {'AFTER' if restore else 'BEFORE'} nor "
            f"{'BEFORE' if restore else 'AFTER'} (off-plan columns: "
            f"{ {e: d for e, d in drift.items() if d} }, full state {now}); refusing — "
            "read the rows before deciding by hand"
        )
    order = tuple(reversed(ORDER)) if restore else ORDER
    return [_diff(e, source[e], target[e]) for e in order]


def _bind(column: str, value: str | None):
    if value is not None and column in TIMESTAMP_COLUMNS:
        return datetime.fromisoformat(value)
    return value


def update_sql(old: dict, new: dict) -> str:
    """One compare-and-swap UPDATE over exactly the columns this write moves."""
    sets, wheres = [], ["id = :id"]
    for c in new:
        sets.append(f"{c} = CAST(:new_{c} AS jsonb)" if c in JSONB_COLUMNS else f"{c} = :new_{c}")
        lhs = f"{c}::text" if c in JSONB_COLUMNS else c
        wheres.append(f"{lhs} IS NOT DISTINCT FROM :old_{c}")
    assert set(old) == set(new) and new, (old, new)
    return f"UPDATE events SET {', '.join(sets)} WHERE {' AND '.join(wheres)}"


async def _read(session) -> tuple[dict, dict, list[int]]:
    got = await session.execute(
        text(
            "SELECT id, home_team_name, away_team_name, espn_id, commence_time, status, "
            "completed_at, llm_importance, box_score_data::text AS box_score_data, external_id "
            "FROM events WHERE id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    identity, state = {}, {}
    for r in got:
        e = int(r.id)
        identity[e] = (r.home_team_name, r.away_team_name, r.espn_id, r.external_id)
        state[e] = {
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "status": r.status,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "llm_importance": r.llm_importance,
            "box_score_data": r.box_score_data,
            "external_id": r.external_id,
        }
    held = await session.execute(
        text("SELECT id FROM events WHERE external_id = :xid"), {"xid": DEC8_ODDS_ID}
    )
    return identity, state, sorted(int(r.id) for r in held)


async def _backup(session) -> int:
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id integer PRIMARY KEY,"
            " commence_time_before timestamptz,"
            " status_before text,"
            " completed_at_before timestamptz,"
            " llm_importance_before text,"
            " box_score_data_before jsonb,"
            " external_id_before text,"
            " taken_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} (event_id, commence_time_before, status_before, "
            "completed_at_before, llm_importance_before, box_score_data_before, external_id_before) "
            "SELECT id, commence_time, status, completed_at, llm_importance, box_score_data, external_id "
            "FROM events WHERE id = ANY(:ids) ON CONFLICT (event_id) DO NOTHING"
        ),
        {"ids": sorted(PINNED)},
    )
    await session.commit()
    banked = await session.execute(
        text(
            "SELECT event_id, commence_time_before, status_before, completed_at_before, "
            "llm_importance_before, box_score_data_before::text AS box, external_id_before "
            f"FROM {BACKUP_TABLE} WHERE event_id = ANY(:ids)"
        ),
        {"ids": sorted(PINNED)},
    )
    # Count only rows that banked the BEFORE state — a bank of the wrong state
    # would make the undo write the wrong values back.
    good = 0
    for r in banked:
        row = {
            "commence_time": r.commence_time_before.isoformat() if r.commence_time_before else None,
            "status": r.status_before,
            "completed_at": r.completed_at_before.isoformat() if r.completed_at_before else None,
            "llm_importance": r.llm_importance_before,
            "box_score_data": r.box,
            "external_id": r.external_id_before,
        }
        before = BEFORE[int(r.event_id)]
        good += {c: row[c] for c in before} == before
    return good


async def run(session, *, apply: bool, restore: bool) -> dict:
    identity, state, holders = await _read(session)
    writes = plan(identity, state, holders, restore=restore)
    written = 0
    if writes and (apply or restore):
        if apply:
            banked = await _backup(session)
            if banked < len(PINNED):
                raise Refused(f"backup holds {banked} of {len(PINNED)} BEFORE rows; refusing to write")
        for event_id, old, new in writes:
            params = {"id": event_id}
            params.update({f"old_{c}": _bind(c, v) for c, v in old.items()})
            params.update({f"new_{c}": _bind(c, v) for c, v in new.items()})
            result = await session.execute(text(update_sql(old, new)), params)
            if result.rowcount != 1:
                await session.rollback()
                raise Refused(
                    f"row {event_id} changed under the run (no longer {old}); "
                    "rolled back, nothing written"
                )
            written += 1
        await session.commit()
    # Read back from disk rather than trusting rowcount (gotcha #53).
    _, after_state, after_holders = await _read(session)
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "planned": [{"event_id": e, "from": o, "to": n} for e, o, n in writes],
        "written": written,
        "now": {str(e): after_state.get(e) for e in PINNED},
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
            "python3 scripts/repair_9702_nfl_rows_moved_to_a_preseason_slot.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
