"""#1201/#1193 — CLI wrapper over the importable MLB inverted-row repair.

The core logic now lives in ``app.tasks.schedule_coverage.repair_inverted_mlb_events``
so the daily beat (``app.tasks.mlb_schedule_coverage``, #1201/#1193/#1202) can
self-heal without manual runs. This script is the one-shot detached-run entry
point for the standing rows (verify via db-query census afterwards):

    python3 scripts/repair_inverted_mlb_events.py            # dry-run (ledger only)
    python3 scripts/repair_inverted_mlb_events.py --apply    # commit the repairs
    python3 scripts/repair_inverted_mlb_events.py --ids 14788546 --apply

``--ids`` (#2018) adds named rows to the candidate set that the invariant
predicate cannot reach: a row can be on the WRONG first pitch without being
INVERTED. Naming a row selects it for CONSIDERATION only — the MLB ground-truth
gate (a Final matching teams AND final score) and the source-priority gate both
still apply, so a named id that cannot be corroborated lands in ``review``.

See the module docstring in ``app/tasks/schedule_coverage.py`` for the full
classification (re-date scored rows via MLB ground truth, void empty/0-0 settles,
skip the unverifiable) and safety notes (MLB-only, evidence-logged, Core SQL,
never touches is_winner — gotcha #21).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_ids(argv: list[str]) -> list[int]:
    """`--ids 1 2 3` / `--ids 1,2,3` — everything until the next flag."""
    if "--ids" not in argv:
        return []
    rest = argv[argv.index("--ids") + 1:]
    out: list[int] = []
    for tok in rest:
        if tok.startswith("--"):
            break
        out.extend(int(p) for p in tok.split(",") if p.strip())
    return out


async def _main(apply: bool, explicit_ids: list[int]) -> None:
    from app.tasks.schedule_coverage import repair_inverted_mlb_events

    if explicit_ids:
        print(f"explicit ids requested: {explicit_ids}")
    ledger = await repair_inverted_mlb_events(apply=apply, explicit_ids=explicit_ids)
    writable = ledger["redate"] + ledger.get("fix_end", 0) + ledger["void"]
    print(
        f"resolved_state-failing MLB events: {ledger['candidates']}\n"
        f"ledger: {ledger['redate']} re-date · {ledger.get('fix_end', 0)} fix-completed_at · "
        f"{ledger['void']} void · {ledger['review']} review-only · applied={ledger['applied']}"
    )
    if not apply and writable:
        print(
            f"\nDRY-RUN — pass --apply to repair {writable} rows. No writes made."
        )


if __name__ == "__main__":
    asyncio.run(_main(apply="--apply" in sys.argv, explicit_ids=_parse_ids(sys.argv)))
