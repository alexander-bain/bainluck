"""#8278 — take game 1's in-game rows off game 2 of the Orioles–Blue Jays doubleheader.

THE SHIP: the 2026-09-23 game-2 page (``/events/15317724``, first pitch 22:35Z)
stops drawing game 1's finished journey as its own chart. At 21:14Z it read
"Starts in 1h 17m" above a win-probability line that climbs from 52% to ~92%
Orioles — game 1's in-game odds, played 17:35–20:1xZ.

HOW THEY GOT THERE (read from production rows, 2026-09-23 ~21:15Z)
------------------------------------------------------------------

A twin of game 1 (15317985) was minted by the registry's Step 4 (#8278's root,
PR #8284). StatPal later gave the twin GAME 2's fixture id (366714) and clock,
so ``merge_duplicate_events`` paired it with 15317724 on that shared id,
repointed every child row onto game 2 and deleted the twin. The children it
carried are all game 1's, and every one sits inside game 1's playing window,
hours before game 2 could have produced any in-game row:

    odds_snapshots       1,913  17:30:27 → 20:28:37Z  (19 sportsbooks, 0.49 → 0.954)
    score_snapshots        113  17:34:57 → 20:06:06Z  (0-0 → 4-2, game 1's final)
    win_prob_snapshots      47  17:37:57 → 20:08:06Z  (mlb gamePk 824785 = game 1;
                                                       stat_model on ESPN innings)

Kalshi's series on 15317724 is game 2's own market (``KXMLBGAME-26SEP231835TORBAL``)
and stays. Nothing else in the twelve event-child tables differs.

WHAT THIS DOES AND DELIBERATELY DOES NOT DO
-------------------------------------------

It REMOVES those rows from game 2, after banking every one of them whole. It
does not re-home them onto game 1 (15316846): game 2's own pregame odds rows are
interleaved with game 1's live ones in the same minutes and no stored column
separates them provably, so moving them would paint game 2's flat 52% line into
game 1's chart. Removing the window instead costs game 2 three hours of a flat
pregame line and costs game 1 nothing it shows today. The banked rows can be
re-homed later from the backup if anyone ever wants game 1's live odds.

The population is pinned by EXACT COUNT per table. ``captured_at`` is write
time, so nothing can join a window that closed at 20:30Z; a count that moved
means someone else touched these rows, and the script refuses.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_8278_doubleheader_game1_rows.py            # dry run
    python3 scripts/repair_8278_doubleheader_game1_rows.py --apply    # bank, then delete
    python3 scripts/repair_8278_doubleheader_game1_rows.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402

PRODUCER_APP = "bainluck-heavy"

GAME1_ID = 15316846
GAME2_ID = 15317724
GAME2_COMMENCE = datetime(2026, 9, 23, 22, 35, tzinfo=timezone.utc)
HOME, AWAY = "Baltimore Orioles", "Toronto Blue Jays"

WINDOW_START = "2026-09-23 17:30:00+00"
WINDOW_END = "2026-09-23 20:30:00+00"

#: table -> (extra predicate, pinned count). Every predicate is ANDed with
#: `event_id = GAME2_ID` and the window.
TABLES: dict[str, tuple[str, int]] = {
    "odds_snapshots": ("TRUE", 1913),
    "score_snapshots": ("TRUE", 113),
    "win_prob_snapshots": ("source IN ('mlb', 'stat_model')", 47),
}


def backup_table(table: str) -> str:
    return f"backup_8278_{table}"


def population_where(table: str) -> str:
    extra, _ = TABLES[table]
    return (
        f"event_id = {GAME2_ID} AND captured_at >= '{WINDOW_START}' "
        f"AND captured_at < '{WINDOW_END}' AND ({extra})"
    )


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def rows_refusal(game1: dict | None, game2: dict | None) -> str | None:
    """Both rows must still be the two games this repair was measured on."""
    if game2 is None:
        return f"game 2 row {GAME2_ID} is gone"
    if game1 is None:
        return f"game 1 row {GAME1_ID} is gone"
    for label, row in (("game 1", game1), ("game 2", game2)):
        if (row["home_team_name"], row["away_team_name"]) != (HOME, AWAY):
            return f"{label} row {row['id']} is no longer {AWAY} at {HOME}"
    if game2["commence_time"] != GAME2_COMMENCE:
        return (
            f"game 2 row {GAME2_ID} moved to {game2['commence_time']}; "
            f"the window was derived from a {GAME2_COMMENCE} first pitch"
        )
    if game1["status"] != "completed":
        return f"game 1 row {GAME1_ID} is {game1['status']!r}, expected 'completed'"
    return None


def counts_refusal(counts: dict[str, int]) -> str | None:
    """Exact pinned counts, or refuse — a moved count means another writer."""
    drift = [
        f"{t}: {counts.get(t)} (pinned {TABLES[t][1]})"
        for t in TABLES
        if counts.get(t) != TABLES[t][1]
    ]
    return "population moved — " + "; ".join(drift) if drift else None


async def _read_rows(session) -> tuple[dict | None, dict | None]:
    res = await session.execute(
        text(
            "SELECT id, home_team_name, away_team_name, commence_time, status "
            "FROM events WHERE id IN (:g1, :g2)"
        ),
        {"g1": GAME1_ID, "g2": GAME2_ID},
    )
    rows = {r.id: dict(r._mapping) for r in res}
    return rows.get(GAME1_ID), rows.get(GAME2_ID)


async def _counts(session) -> dict[str, int]:
    out = {}
    for table in TABLES:
        res = await session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {population_where(table)}")
        )
        out[table] = int(res.scalar_one())
    return out


async def _apply(session) -> dict[str, int]:
    deleted = {}
    for table in TABLES:
        bk = backup_table(table)
        await session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {bk} AS SELECT * FROM {table} WHERE FALSE"
            )
        )
        # First pre-image wins: a second run never overwrites the banked rows.
        await session.execute(
            text(
                f"INSERT INTO {bk} SELECT * FROM {table} WHERE {population_where(table)} "
                f"AND id NOT IN (SELECT id FROM {bk})"
            )
        )
        # Delete only rows that are banked AND still on game 2.
        res = await session.execute(
            text(
                f"DELETE FROM {table} WHERE {population_where(table)} "
                f"AND id IN (SELECT id FROM {bk})"
            )
        )
        deleted[table] = res.rowcount
    return deleted


async def _restore(session) -> dict[str, int]:
    restored = {}
    for table in TABLES:
        bk = backup_table(table)
        exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": bk})
        if exists.scalar_one() is None:
            restored[table] = 0
            continue
        res = await session.execute(
            text(
                f"INSERT INTO {table} SELECT * FROM {bk} "
                f"WHERE id NOT IN (SELECT id FROM {table})"
            )
        )
        restored[table] = res.rowcount
    return restored


async def run(apply: bool, restore: bool) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    mode = "RESTORE" if restore else ("APPLY" if apply else "DRY RUN")
    print(f"#8278 doubleheader game-1 rows off game 2 ({GAME2_ID}) — {mode}")
    async with get_task_session() as session:
        if restore:
            restored = await _restore(session)
            await session.commit()
            for t, n in restored.items():
                print(f"  restored {t:<20}: {n}")
            return 0

        game1, game2 = await _read_rows(session)
        refusal = rows_refusal(game1, game2)
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2
        counts = await _counts(session)
        for t, n in counts.items():
            print(f"  {t:<20}: {n} (pinned {TABLES[t][1]})")
        refusal = counts_refusal(counts)
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2
        if not apply:
            print("\ndry run — nothing written.")
            return 0

        deleted = await _apply(session)
        refusal = counts_refusal(deleted)
        if refusal:
            await session.rollback()
            print(f"ROLLED BACK: delete counts did not match — {refusal}")
            return 1
        await session.commit()
        for t, n in deleted.items():
            print(f"  deleted {t:<20}: {n}  (banked in {backup_table(t)})")
        print(
            "\nundo: python3 scripts/repair_8278_doubleheader_game1_rows.py --restore"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply", action="store_true", help="bank, then delete (default: dry run)"
    )
    mode.add_argument(
        "--restore", action="store_true", help="re-insert every banked row"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.apply, args.restore))


if __name__ == "__main__":
    raise SystemExit(main())
