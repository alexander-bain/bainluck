"""#10009 undo — put back every chart row the token repair flipped.

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_10009_polymarket_wrong_token_chart_rows.py --apply

Restores home, away and ``game_state`` from the banked pre-image, only on rows
still carrying the repair's stamp (a row the rail rewrote since is left alone).
Same app refusal as the repair — notice 47(c).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# …and this script's OWN directory, so the sibling import below resolves however
# the file is loaded (the guard test imports it by path).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from repair_10009_polymarket_wrong_token_chart_rows import (  # noqa: E402
    BACKUP_TABLE,
    REPAIR_STAMP,
    wrong_app_refusal,
)

RESTORE_SQL = f"""
    UPDATE win_prob_snapshots s
       SET home_win_probability = b.home_win_probability,
           away_win_probability = b.away_win_probability,
           game_state = b.game_state
      FROM {BACKUP_TABLE} b
     WHERE s.id = b.snapshot_id
       AND s.game_state->>'token_repair' = :stamp
"""


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        exists = (
            await session.execute(
                text("SELECT to_regclass(CAST(:t AS text)) IS NOT NULL"), {"t": BACKUP_TABLE}
            )
        ).scalar()
        if not exists:
            print(f"NO_BACKUP: {BACKUP_TABLE} does not exist — nothing to restore")
            return 0

        counts = (
            await session.execute(
                text(f"""
                    SELECT count(*) AS banked,
                           count(s.id) FILTER (
                               WHERE s.game_state->>'token_repair' = :stamp
                           ) AS still_flipped
                      FROM {BACKUP_TABLE} b
                      LEFT JOIN win_prob_snapshots s ON s.id = b.snapshot_id
                """),
                {"stamp": REPAIR_STAMP},
            )
        ).mappings().one()
        print(f"#10009 restore — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  banked rows   : {counts['banked']}")
        print(f"  still flipped : {counts['still_flipped']}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0
        if not counts["still_flipped"]:
            print("\nnothing to restore.")
            return 0

        result = await session.execute(text(RESTORE_SQL), {"stamp": REPAIR_STAMP})
        await session.commit()
        print(f"\n  restored      : {result.rowcount or 0}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
