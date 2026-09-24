"""#7994 — close the individual stroke-play markets we minted for the Presidents Cup.

THE SHIP: Discover page one stops reading "Presidents Cup - Winner · Jackson
Koivun leads at 6%". The Presidents Cup is 24-player team match play with no
individual winner, and Koivun is not in it. Production, 2026-09-24 04:55Z
(discover/462): `/api/feed?limit=100` serves market 61720777 at position 85.

PREVENTION SHIPPED FIRST (#7985, `3bb412138a`, 2026-09-22): `tasks/datagolf.py`
neither mints nor REOPENS these five types for a team match-play event, and
`/api/golf` withholds them. What #7985 left, on purpose, is the five rows
themselves — still `status='open'`, so every reader that selects open markets
directly (Discover, `/api/futures`, the event page's evolution chart) still
serves them:

    61720777  Presidents Cup - Winner         datagolf:pga:500:win
    61720778  Presidents Cup - Top 5 Finish   datagolf:pga:500:top_5
    61720779  Presidents Cup - Top 10 Finish  datagolf:pga:500:top_10
    61720780  Presidents Cup - Top 20 Finish  datagolf:pga:500:top_20
    61720781  Presidents Cup - Make the Cut   datagolf:pga:500:make_cut

THE WRITE is one column: `status` 'open' -> 'closed'. No delete (#7985's serve
guard keys on source + external_id, so a closed row stays withheld and its
history stays intact), no outcome touched.

THE POPULATION is the mint guard's own vocabulary, imported rather than
restated — `is_team_match_play_name` on the row's name and
`datagolf_market_type` in `INDIVIDUAL_STROKE_PLAY_MARKET_TYPES` — over
`source='datagolf' AND status='open'`. It can only ever select a market we
minted ourselves; Kalshi's Team USA v Team World is out of reach by `source`.

THE PRODUCER IS THE MAIN APP. No golf task is in `HEAVY_TASKS`, so the code that
could reopen these rows runs on `bainluck`, which has carried #7985 since
2026-09-22. A write therefore refuses anywhere but `HEROKU_APP_NAME=bainluck`
(standing notice 47(c): runtime DDL, attended invocation only). A dry run only
reads and runs anywhere.

USAGE (gotcha #48: detached, then verify the side effect ~60s later):

    heroku run:detached -a bainluck python backend/scripts/repair_7994_close_team_matchplay_datagolf_rows.py
    heroku run:detached -a bainluck python backend/scripts/repair_7994_close_team_matchplay_datagolf_rows.py --backup --apply
    heroku run:detached -a bainluck python backend/scripts/repair_7994_close_team_matchplay_datagolf_rows.py --restore   # the undo
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.golf_event_format import (  # noqa: E402
    INDIVIDUAL_STROKE_PLAY_MARKET_TYPES,
    datagolf_market_type,
    is_team_match_play_name,
)

PRODUCER_APP = "bainluck"
BACKUP_TABLE = "backup_7994_team_matchplay_rows"

#: Measured 5 on 2026-09-24. A predicate that matches far more is not this repair.
MAX_EXPECTED_POPULATION = 10

_CANDIDATES_SQL = """
SELECT id, name, external_id, status
  FROM futures_markets
 WHERE source = 'datagolf'
   AND status = 'open'
   AND external_id LIKE 'datagolf:%'
 ORDER BY id
"""


def in_scope(name, external_id) -> bool:
    """An individual stroke-play market on a team match-play event, by the mint guard's rule."""
    return (
        is_team_match_play_name(name)
        and datagolf_market_type(external_id) in INDIVIDUAL_STROKE_PLAY_MARKET_TYPES
    )


def wrong_app_refusal(writes: bool, app) -> str | None:
    """Why this invocation may not write, or None if it may.

    Unset `HEROKU_APP_NAME` means a laptop pointed at production with whatever is
    checked out — refused too, rather than falling through.
    """
    if not writes or app == PRODUCER_APP:
        return None
    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. The DataGolf "
        f"poller that could reopen these rows runs on '{PRODUCER_APP}'; run this "
        f"with `heroku run:detached -a {PRODUCER_APP}`."
    )


async def run(args) -> int:
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    refusal = wrong_app_refusal(
        args.backup or args.apply or args.restore, os.environ.get("HEROKU_APP_NAME")
    )
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        if args.restore:
            exists = (
                await s.execute(text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL"))
            ).scalar()
            if not exists:
                print(f"REFUSING: no {BACKUP_TABLE} — nothing to restore from.")
                return 2
            restored = (
                await s.execute(
                    text(
                        f"UPDATE futures_markets f SET status = b.status "
                        f"FROM {BACKUP_TABLE} b WHERE f.id = b.id "
                        f"AND f.status IS DISTINCT FROM b.status RETURNING f.id"
                    )
                )
            ).all()
            await s.commit()
            print(f"restored status on {len(restored)} rows: {[r.id for r in restored]}")
            return 0

        rows = [r for r in (await s.execute(text(_CANDIDATES_SQL))).all()
                if in_scope(r.name, r.external_id)]
        print("=== #7994 team match-play stroke-play rows (open) ===")
        for r in rows:
            print(f"  {r.id:>9} {r.status:<6} {r.external_id:<32} {r.name}")
        print(f"  population={len(rows)}")
        if not rows:
            print("Nothing to close (idempotent no-op).")
            return 0
        if len(rows) > MAX_EXPECTED_POPULATION:
            print(f"REFUSING: {len(rows)} > MAX_EXPECTED_POPULATION={MAX_EXPECTED_POPULATION}.")
            return 2
        ids = [r.id for r in rows]

        if args.backup:
            await s.execute(
                text(f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} (id bigint PRIMARY KEY, status text)")
            )
            await s.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} (id, status) "
                    "SELECT id, status FROM futures_markets WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status"
                ),
                {"ids": ids},
            )
            await s.commit()
            print(f"backup: copied {len(ids)} rows into {BACKUP_TABLE}")

        if not args.apply:
            print("dry run — nothing written" if not args.backup else "backup only — nothing closed")
            return 0

        exists = (
            await s.execute(text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL"))
        ).scalar()
        unbacked = (
            (
                await s.execute(
                    text(
                        f"SELECT count(*) FROM futures_markets f WHERE f.id = ANY(:ids) "
                        f"AND NOT EXISTS (SELECT 1 FROM {BACKUP_TABLE} b "
                        "WHERE b.id = f.id AND b.status IS NOT DISTINCT FROM f.status)"
                    ),
                    {"ids": ids},
                )
            ).scalar()
            if exists
            else len(ids)
        )
        if unbacked:
            print(f"REFUSING --apply: {unbacked} rows are not backed up at their current status. Run --backup.")
            return 2

        closed = (
            await s.execute(
                text(
                    "UPDATE futures_markets SET status = 'closed' "
                    "WHERE id = ANY(:ids) AND status = 'open' RETURNING id"
                ),
                {"ids": ids},
            )
        ).all()
        await s.commit()
        print(f"closed {len(closed)} rows: {[r.id for r in closed]}")
        print(
            "undo: heroku run:detached -a bainluck python "
            "backend/scripts/repair_7994_close_team_matchplay_datagolf_rows.py --restore"
        )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backup", action="store_true", help="copy in-scope rows' status first")
    p.add_argument("--apply", action="store_true", help="close them (refuses without a matching backup)")
    p.add_argument("--restore", action="store_true", help="the undo: put every backed-up status back")
    sys.exit(asyncio.run(run(p.parse_args())) or 0)


if __name__ == "__main__":
    main()
