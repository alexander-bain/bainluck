"""#2878 — a settled US Open match stops printing twice on the tour page.

THE SHIP. `/sport/tennis/atp` and `/sport/tennis/wta` hold two cards for one
match: the real one, and a surname-only row stamped at midnight that reads
**"No result reported"** forever. #3677 measured what that cost — the two tour
pages showed no US Open match at all for the whole fortnight, because the rows
they COULD see were these. This script tags the second row so that one match
prints one card.

    /sports             /events/15304938  Tomas Martin Etcheverry vs Alex Michelsen  27% / 73%
    /sport/tennis/atp   /events/15304918  M Michelsen / E Etcheverry                 No result reported

A LABEL, NOT A MERGE — the line ruling 048 draws
────────────────────────────────────────────────
Nothing here deletes a row, repoints a foreign key, or moves a market. The only
write is one element appended to `events.event_tags`:

    provenance:duplicate-of:<canonical event id>

That tag has a shipped reader — `app.utils.proven_duplicates.not_a_proven_duplicate`,
carried by the three league-page rails, the feed candidates, the team pages and
`GET /api/events` — and **no deleter anywhere in the codebase**. So the whole
effect of this repair is "do not print a second card", and `restore_…  --apply`
takes it back with one command (D51).

That distinction is the whole reason this is allowed to exist.
`reconcile_unanchored_events` counts this exact population as
`ANCHORED_TWIN_UNSEEN` and its docstring says of its own predicate: *"That
predicate is a METER and must never become a MERGE"* — because the defect
ruling 048 was written to kill put 5,142 / 540 / 2,097 rows of one game's data
onto another. A reversible label with no deleter is the half of that which is
safe; **the moment anything here DELETEs or repoints on this predicate it has
become the thing 048 banned.**

WHAT SEPARATES THE GHOST FROM THE REAL MATCH — measured, and not what I guessed
──────────────────────────────────────────────────────────────────────────────
Measured on production 2026-09-06 over the 172 candidate pairs in the tennis
window (`app.utils.tennis_twin_pairs.row_has_settled_result` carries the table):

    ghosts carrying a final score                0 / 172
    ghosts that ever reached 'completed'         0 / 172
    ghosts carrying at least one market        110 / 172
    ghosts carrying MORE markets than their
      own canonical                             63 / 172

🔴 **The ghost is not an empty row.** It is Kalshi-minted, it has prices and a
probability, and two times in five it has a BIGGER market book than the odds_api
row that actually gets settled. A sweep written on the intuitive reading of
"which row has substance" tags **zero** of these pairs and exits 0 (gotcha #53).
The final score is the only field that separates them, and it separates them
172/172.

THE UNPLAYED HALF, ADDED 2026-09-07 (#2693) — AND ITS DEPLOY ORDER
───────────────────────────────────────────────────────────────────
The first version of this script refused every unsettled pair, because the
score was the only field that separated ghost from canonical and an unplayed
row has none. Six US Open quarter-finals were sitting in that state on
2026-09-07, each printing twice, and two of them were the reason refusing was
right at the time:

    ghost 15305538 Andreeva/Potapova   13 markets  →  canonical 15305579   0 markets
    ghost 15305553 Cerundolo/Blockx    17 markets  →  canonical 15305578   1 market

Hiding those ghosts would have taken away nearly all of the market coverage and
left a card with nothing on it. Two things changed:

1. `tennis_twin_pairs.row_is_id_anchored` — the PROVIDER ID separates an
   unplayed pair where the score cannot. 250/250 tournament-keyed rows carry
   one, 0/1259 bare rows do, and the shape holds on all 161 settled tags and
   all 6 unplayed pairs.
2. `proven_duplicates.folded_event_ids`, wired into `_build_game_markets` —
   the canonical's page now reads the markets of the rows we decline to print,
   so the 17 markets move to the surviving card instead of disappearing.

🔴 **(2) MUST BE LIVE IN PRODUCTION BEFORE THIS SCRIPT IS RUN AGAINST AN
UNPLAYED PAIR.** They shipped in the same commit, so the check is a deploy
check, not a code check: confirm `/api/events/<canonical>/game-markets` returns
the ghost's markets BEFORE `--apply`. Run it before the fold is live and this
script does not remove a duplicate card, it removes the only card with prices.

Still refused, and still correctly: a bare row that carries a result, a pair
where both or neither row is tournament-keyed, a pair stamped beyond the 96h
fence, and a ghost claimed by two canonicals.

THIS IS NO LONGER THE ONLY WAY THE SWEEP RUNS (#3811)
─────────────────────────────────────────────────────
Being hand-run was itself the defect. On 2026-09-07 a twin formed at 03:03Z, its
canonical landed at 04:35Z, and 92 minutes later a US Open semi-final page was
still rendering with no markets section — because the only two writers of the
tag are `event_registry._proven_duplicates` (which cannot reach this pair: no
shared provider id, and the kickoffs are 3h apart against a 30-minute fence) and
this script, which nobody had run.

The sweep now also runs every 30 minutes as `app.tasks.tennis_twin_sweep`, and
the helpers this file used to define live there. This CLI is unchanged in
behaviour and is still the right tool for a one-off, a dry run, or a widened
window — it just no longer owns the implementation.

Usage — dry run first, always:

    python3 scripts/repair_2878_tennis_twin_ghosts.py
    python3 scripts/repair_2878_tennis_twin_ghosts.py --backup --apply

Heroku one-off (gotcha #48 — `PROJECT_PATH=backend` puts scripts at /app, so NO
`cd backend`, and NEVER a non-detached `heroku run`):

    heroku run:detached -a bainluck "python3 scripts/repair_2878_tennis_twin_ghosts.py --backup --apply"

Undo:

    python3 scripts/restore_2878_tennis_twin_ghosts.py --apply
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# EVERY helper below used to be defined in this file. They now live in
# `app.tasks.tennis_twin_sweep`, which is the same sweep on a 30-minute beat
# (#3811) — because a scheduled copy of a hand-run script is two matchers, and
# two matchers that disagree is the failure ruling 048 exists to end. This file
# is now the CLI face of that module: same population query, same plan floor,
# same backup table, same writer.
from app.tasks.tennis_twin_sweep import (  # noqa: E402
    BAK_TABLE,
    DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    MAX_EXPECTED_TAGS,
    MIN_EXPECTED_TAGS,
    already_tagged_ids,
    build_plan,
    ensure_backup,
    load_rows,
    plan_refusal_reason,
    write_tags,
)

__all__ = [
    "BAK_TABLE",
    "DEFAULT_LOOKAHEAD_DAYS",
    "DEFAULT_LOOKBACK_DAYS",
    "MAX_EXPECTED_TAGS",
    "MIN_EXPECTED_TAGS",
    "already_tagged_ids",
    "build_plan",
    "ensure_backup",
    "load_rows",
    "plan_refusal_reason",
    "write_tags",
]


async def run(*, backup: bool, apply: bool, lookback: int, lookahead: int) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        rows = await load_rows(session, lookback=lookback, lookahead=lookahead)
        plan = build_plan(rows)
        tagged = already_tagged_ids(rows)
        todo = [t for t in plan.tags if t.ghost_id not in tagged]

        print(f"\n=== #2878 twin sweep — {lookback}d back, {lookahead}d ahead ===")
        print(
            json.dumps(
                {
                    "rows_read": len(rows),
                    "blocks_examined": plan.blocks_examined,
                    "pairs_found": len(plan.tags),
                    "already_tagged": len(plan.tags) - len(todo),
                    "tags_to_write": len(todo),
                    "refusals": len(plan.refusals),
                },
                indent=2,
            )
        )

        print(f"\n--- {len(plan.refusals)} refusal(s), the population somebody looks at next ---")
        for reason in plan.refusals[:40]:
            print(f"  {reason}")
        if len(plan.refusals) > 40:
            print(f"  … and {len(plan.refusals) - 40} more")

        if not todo:
            print(
                "\nNothing to write — every pair this sweep can decide is already "
                "labelled (idempotent no-op)."
            )
            return

        print(f"\n--- {len(todo)} tag(s) this run would write ---")
        for tag in todo[:20]:
            print(f"  event {tag.ghost_id} -> duplicate-of:{tag.canonical_id}  ({tag.reason})")
        if len(todo) > 20:
            print(f"  … and {len(todo) - 20} more")

        blocked = plan_refusal_reason(plan, untagged=len(todo))
        if blocked and apply:
            print(f"\nREFUSING TO APPLY: {blocked}")
            sys.exit(1)
        if blocked:
            print(f"\nWOULD REFUSE: {blocked}")

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {len(todo)} row(s) would be tagged. "
                f"Re-run with --backup --apply."
            )
            return
        if not backup:
            print("\nREFUSING: --apply requires --backup in the same run (D51)")
            sys.exit(1)

        current = {r.id: (r.tags_text or "[]") for r in rows}
        banked = await ensure_backup(session, todo, current)
        print(f"\nBACKUP: banked {banked} new row(s) in {BAK_TABLE}")

        print(f"\nTAGGING {len(todo)} ghost(s), one transaction each …")
        written, failed = await write_tags(session, todo)

        after_rows = await load_rows(session, lookback=lookback, lookahead=lookahead)
        still_untagged = [
            t.ghost_id
            for t in plan.tags
            if t.ghost_id not in already_tagged_ids(after_rows)
        ]

        print(f"\nCOMMITTED: {written} tag(s) written.")
        print(
            "\nUndo: python3 scripts/restore_2878_tennis_twin_ghosts.py --apply"
        )

        problems = []
        if failed:
            problems.append(
                f"{len(failed)} row(s) exhausted their retries and are still "
                f"printing: {failed[:20]}{' …' if len(failed) > 20 else ''}"
            )
        if still_untagged:
            problems.append(
                f"{len(still_untagged)} planned ghost(s) carry no tag after the "
                f"run: {still_untagged[:20]} — the sweep is incomplete"
            )
        if problems:
            print("\n❌ #2878 INCOMPLETE — the sweep did NOT finish:")
            for problem in problems:
                print(f"  - {problem}")
            print(
                "\nThe committed tags are durable, so re-running with "
                "--backup --apply resumes from here."
            )
            sys.exit(1)

        print(
            f"\n✅ #2878: {written} settled tennis match(es) now print ONE card. "
            f"{len(plan.refusals)} pair(s) refused and reported above — the "
            f"unsettled ones are #2693's."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup", action="store_true", help="bank current event_tags")
    parser.add_argument(
        "--apply", action="store_true", help="write the tags (requires --backup)"
    )
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--lookahead", type=int, default=DEFAULT_LOOKAHEAD_DAYS)
    args = parser.parse_args()
    asyncio.run(
        run(
            backup=args.backup,
            apply=args.apply,
            lookback=args.lookback,
            lookahead=args.lookahead,
        )
    )


if __name__ == "__main__":
    main()
