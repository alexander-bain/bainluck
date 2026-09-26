"""#8755 — label ONE named Odds API twin the re-issued sweep can no longer reach.

**SHIP: a WNBA playoff game that hasn't started stops showing as LIVE under a
two-day-old price.** (Pillar: TRUTH.) `/events/15318133` (Lynx v Liberty,
"Sep 26 00:30Z") is a second row for `15318132` (Sep 27 18:00Z, ESPN
401918014): the provider split FanDuel's listing onto a second id for eighteen
minutes on 09-24 and folded it back — the ghost's one line is on the listed row
byte for byte. The #8422 sweep refused it for holding the NEWER id; that arm is
fixed in `app.utils.odds_api_reissued_twins.lines_moved`, but the row is now past
the start the sweep's window requires, so the sweep will never look at it again.

This runs THE SWEEP'S OWN JUDGEMENT over two named ids — no second rule:

    load_rows_by_id → read_schedules (the provider's free /events) →
    load_book_lines → plan_reissue_tags

and writes only if that plan is exactly ``ghost → canonical``. Every other
outcome — a refusal, a different pair, an unread schedule, a missing row —
prints why and exits 2 with nothing written.

D51: the ghost's prior `event_tags` is banked in the sweep's own table
(`bak_8422_odds_api_reissued_tags`), so the existing undo removes exactly this
element and nothing else:

    python3 scripts/restore_8422_odds_api_reissued_tags.py --only 15318133 --apply

and the sweep's relist arm lifts it by itself if the provider ever lists the
ghost's id again.

    python3 scripts/repair_8755_newer_id_twin.py --ghost 15318133 --canonical 15318132          # dry run
    python3 scripts/repair_8755_newer_id_twin.py --ghost 15318133 --canonical 15318132 --apply
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.odds_api_reissued_twin_sweep import (  # noqa: E402
    BAK_TABLE,
    consumer_is_live,
    ensure_backup,
    load_book_lines,
    load_rows_by_id,
    read_schedules,
    tagged_now,
    write_tags,
)
from app.utils.odds_api_reissued_twins import pair_key, plan_reissue_tags  # noqa: E402

REFUSED = 2


def judge(rows, schedules, lines, *, ghost: int, canonical: int):
    """``(tag, reason)``: the one tag to write, or None and why not. Pure."""
    by_id = {r.event_id: r for r in rows}
    missing = [i for i in (ghost, canonical) if i not in by_id]
    if missing:
        return None, f"not an Odds API-anchored row: {missing}"
    g, c = by_id[ghost], by_id[canonical]
    if pair_key(g) != pair_key(c):
        return None, f"not one pair: {pair_key(g)} vs {pair_key(c)}"
    if g.already_tagged:
        return None, "already_tagged"
    plan = plan_reissue_tags([sorted((g, c), key=lambda r: r.event_id)], schedules, lines)
    wanted = [t for t in plan.tags if (t.duplicate_id, t.canonical_id) == (ghost, canonical)]
    if len(plan.tags) != 1 or not wanted:
        reasons = [r["reason"] for r in plan.refusals] or ["planner chose another pair"]
        return None, "; ".join(reasons)
    return wanted[0], "planned"


async def run(*, ghost: int, canonical: int, apply: bool, service=None) -> int:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        rows, current_tags = await load_rows_by_id(session, [ghost, canonical])
        sports = {r.sport_key for r in rows}
        schedules, errors = await read_schedules(sports, service=service)
        if errors:
            print(f"❌ REFUSED — the provider's schedule was not read: {errors}. Nothing written.")
            return REFUSED
        lines = await load_book_lines(session, [ghost, canonical])
        tag, reason = judge(rows, schedules, lines, ghost=ghost, canonical=canonical)
        print(json.dumps({
            "ghost": ghost, "canonical": canonical, "verdict": reason,
            "ghost_lines": sorted(map(list, lines.get(ghost, ()))),
            "canonical_lines_held": len(lines.get(canonical, ())),
        }, indent=2, default=str))
        if reason == "already_tagged":
            print("Nothing to do — the ghost already carries a duplicate-of label.")
            return 0
        if tag is None:
            print(f"❌ REFUSED — {reason}. Nothing written.")
            return REFUSED
        if not consumer_is_live():
            print("❌ REFUSED — search no longer calls not_a_proven_duplicate. Nothing written.")
            return REFUSED
        if not apply:
            print(f"DRY RUN — would bank {ghost} in {BAK_TABLE} and label it "
                  f"duplicate-of:{canonical}. Re-run with --apply.")
            return 0

        banked = await ensure_backup(session, [tag], current_tags)
        written, failed = await write_tags(session, [tag])
        confirmed = await tagged_now(session, [ghost])
        print(f"COMMITTED: banked {banked}, tagged {written}.")
        if failed or ghost not in confirmed:
            print(f"❌ INCOMPLETE — failed {failed}, read back {sorted(confirmed)}")
            return 1
        print(f"✅ {ghost} labelled duplicate-of:{canonical}. Undo: "
              f"scripts/restore_8422_odds_api_reissued_tags.py --only {ghost} --apply")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ghost", type=int, required=True, help="the row to label")
    parser.add_argument("--canonical", type=int, required=True, help="the listed row it duplicates")
    parser.add_argument("--apply", action="store_true", help="write the label")
    args = parser.parse_args()
    if args.ghost == args.canonical:
        parser.error("--ghost and --canonical must differ")
    raise SystemExit(asyncio.run(run(ghost=args.ghost, canonical=args.canonical, apply=args.apply)))


if __name__ == "__main__":
    main()
