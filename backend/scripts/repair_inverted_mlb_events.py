"""#1201/#1193 — CLI wrapper over the importable MLB inverted-row repair.

The core logic now lives in ``app.tasks.schedule_coverage.repair_inverted_mlb_events``
so the daily beat (``app.tasks.mlb_schedule_coverage``, #1201/#1193/#1202) can
self-heal without manual runs. This script is the one-shot detached-run entry
point for the standing rows (verify via db-query census afterwards):

    python3 scripts/repair_inverted_mlb_events.py            # dry-run (ledger only)
    python3 scripts/repair_inverted_mlb_events.py --apply    # commit the repairs

See the module docstring in ``app/tasks/schedule_coverage.py`` for the full
classification (re-date scored rows via MLB ground truth, void empty/0-0 settles,
skip the unverifiable) and safety notes (MLB-only, evidence-logged, Core SQL,
never touches is_winner — gotcha #21).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _main(apply: bool) -> None:
    from app.tasks.schedule_coverage import repair_inverted_mlb_events

    ledger = await repair_inverted_mlb_events(apply=apply)
    print(
        f"resolved_state-failing MLB events: {ledger['candidates']}\n"
        f"ledger: {ledger['redate']} re-date · {ledger['void']} void · "
        f"{ledger['review']} review-only · applied={ledger['applied']}"
    )
    if not apply and (ledger["redate"] or ledger["void"]):
        print(
            f"\nDRY-RUN — pass --apply to repair "
            f"{ledger['redate'] + ledger['void']} rows. No writes made."
        )


if __name__ == "__main__":
    asyncio.run(_main(apply="--apply" in sys.argv))
