"""#9066 — the D51(b) undo for `repair_9066_draw_complement_chart_rows.py`.

D51 = B(b) (Alex, 2026-09-03): a data repair that writes a backup first and ships
a one-command restore may be applied UNATTENDED by the owning lane. This file is
that one command:

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/restore_9066_draw_complement_chart_rows.py --apply

WHAT IT PUTS BACK. The ``win_prob_snapshots`` rows the repair deleted, under
their ORIGINAL ids, from
:data:`~repair_9066_draw_complement_chart_rows.BACKUP_TABLE`. That is the only
thing the repair ever wrote.

⚠️ WHAT RESTORING MEANS HERE, SAID PLAINLY. It puts the away side's price back
on the home team's chart line — the 23%<->80% square wave on ``/events/15316107``.
That is correct for an undo, but it rolls back a TRUTH repair. Run it because the
repair went wrong, not because it is finished.

WHAT IT WILL NOT DO. Overwrite a row. A snapshot id already present is
``ALREADY_BACK`` and left alone; the insert is ``ON CONFLICT (id) DO NOTHING``.
Idempotent: a second run restores nothing.

The backup table is NOT Alembic-managed. ``alembic revision --autogenerate``
will propose DROPping it — delete that from the generated migration.
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

from app.tasks.base import get_task_session  # noqa: E402
from repair_9066_draw_complement_chart_rows import (  # noqa: E402
    BACKUP_TABLE,
    wrong_app_refusal,
)


async def run(apply: bool) -> int:
    if apply:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

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
                           count(s.id) AS already_back
                      FROM {BACKUP_TABLE} b
                      LEFT JOIN win_prob_snapshots s ON s.id = b.snapshot_id
                """)
            )
        ).mappings().one()
        missing = counts["banked"] - counts["already_back"]
        print(f"#9066 restore — {'APPLY' if apply else 'DRY RUN'}")
        print(f"  banked rows   : {counts['banked']}")
        print(f"  ALREADY_BACK  : {counts['already_back']}")
        print(f"  to restore    : {missing}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0
        if missing == 0:
            print("\nnothing to restore.")
            return 0

        result = await session.execute(
            text(f"""
                INSERT INTO win_prob_snapshots
                    (id, event_id, source, captured_at,
                     home_win_probability, away_win_probability, draw_probability,
                     game_state, reading_count, valid_until)
                SELECT b.snapshot_id, b.event_id, b.source, b.captured_at,
                       b.home_win_probability, b.away_win_probability,
                       b.draw_probability, b.game_state, b.reading_count,
                       b.valid_until
                  FROM {BACKUP_TABLE} b
                  JOIN events e ON e.id = b.event_id
                ON CONFLICT (id) DO NOTHING
            """)
        )
        await session.commit()
        restored = result.rowcount or 0
        print(f"\n  restored      : {restored}")
        if restored != missing:
            print(
                f"  {missing - restored} banked row(s) not restored — their event "
                f"no longer exists (ON DELETE CASCADE)"
            )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
