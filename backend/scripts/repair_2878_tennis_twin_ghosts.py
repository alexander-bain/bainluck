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

WHAT THIS DELIBERATELY DOES NOT FIX, AND WHY THAT IS THE RIGHT CALL
────────────────────────────────────────────────────────────────────
**Unsettled matches are refused.** Before a match is played neither row has a
score, so nothing separates them and `classify_pair` returns REFUSE_AMBIGUOUS.
Eight pairs were in that state on 2026-09-06, including the two semi-finals, and
refusing them is correct rather than merely cautious:

    ghost 15305538 Andreeva/Potapova   13 markets  →  canonical 15305579   0 markets
    ghost 15305553 Cerundolo/Blockx    17 markets  →  canonical 15305578   1 market

Hiding those ghosts would take away nearly all of the market coverage for
tomorrow's matches and leave a card with nothing on it. That half is market
re-attachment — #2693 — not a label, and it is not this script's to force.

So this repair ships the settled half: **a US Open match that has been played
appears once.** Tomorrow's semi-final still prints twice until #2693 lands.

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
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.anchor_channel import (  # noqa: E402
    DUPLICATE_TAG_PREFIX,
    duplicate_tag,
)
from app.utils.tennis_twin_pairs import (  # noqa: E402
    MAX_TWIN_SEPARATION,
    TwinRow,
    is_tournament_key,
    plan_twin_tags,
    row_has_settled_result,
)

#: D51 backup. Holds the ghost's `event_tags` exactly as they were before the
#: append, plus the canonical the tag names — so the undo can be surgical
#: (remove ONE element) rather than a clobber of the whole array.
BAK_TABLE = "bak_2878_twin_ghost_tags"

#: The window the sweep reads. Wide enough to cover a Slam fortnight plus the
#: qualifying week before it; deliberately NOT the whole table, because the
#: block key is a global `(surname, surname)` pair with no time component and a
#: wider read is a wider chance of fusing two meetings between the same players.
DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_LOOKAHEAD_DAYS = 5

#: Sanity band on the PLAN, measured 2026-09-06 at 162 tags over 1,430 rows.
#: The floor exists because a repair that finds nothing and reports success is
#: the worst outcome there is; it is waived when every candidate is already
#: tagged, which is the idempotent re-run.
MIN_EXPECTED_TAGS = 20
MAX_EXPECTED_TAGS = 600

_POPULATION_SQL = """
SELECT e.id,
       s.key                AS sport_key,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.home_score,
       e.away_score,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key LIKE 'tennis%%'
   AND e.commence_time >= now() - make_interval(days => :lookback)
   AND e.commence_time <= now() + make_interval(days => :lookahead)
   AND e.status NOT IN ('voided', 'merged')
   AND e.id > :cursor
 ORDER BY e.id
 LIMIT :page
"""


async def load_rows(session, *, lookback: int, lookahead: int, page: int = 2000):
    """Every tennis row in the window, paged by id.

    Paged because the read is a plain cursor scan and `db-query`-shaped single
    reads cap out; the cursor key IS the sort key, which is the only shape that
    cannot skip or repeat a row.
    """
    from sqlalchemy import text

    out, cursor = [], 0
    while True:
        rows = (
            await session.execute(
                text(_POPULATION_SQL),
                {
                    "lookback": lookback,
                    "lookahead": lookahead,
                    "cursor": cursor,
                    "page": page,
                },
            )
        ).all()
        out.extend(rows)
        if len(rows) < page:
            return out
        cursor = rows[-1].id


def build_plan(rows, *, max_separation: timedelta = MAX_TWIN_SEPARATION):
    """Turn database rows into the pure planner's inputs and run it.

    Every field the judgement reads is copied to a scalar here. `events` is
    write-hot and this script commits per row, so a live ORM object read after a
    commit boundary would lazy-load in a sync context (gotcha #6) — and a
    judgement that reads the database is a judgement nobody can test.
    """
    snapshots = [
        TwinRow(
            event_id=r.id,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            sport_key=r.sport_key,
            is_tournament_keyed=is_tournament_key(r.sport_key),
            has_settled_result=row_has_settled_result(
                home_score=r.home_score, away_score=r.away_score
            ),
        )
        for r in rows
    ]
    return plan_twin_tags(
        snapshots,
        commence_times={r.id: r.commence_time for r in rows},
        max_separation=max_separation,
    )


def already_tagged_ids(rows) -> set[int]:
    """Ghosts that already carry SOME `duplicate-of` tag.

    Read off the serialised array with the same prefix the reader matches on, so
    the writer and the reader cannot drift. A row already labelled a duplicate of
    anything is left entirely alone — re-tagging it would be this script
    arbitrating between its own finding and an existing one.
    """
    return {r.id for r in rows if DUPLICATE_TAG_PREFIX in (r.tags_text or "")}


def plan_refusal_reason(plan, *, untagged: int) -> str | None:
    """Why this plan must NOT be applied, or ``None`` if it is safe. Pure."""
    if untagged == 0:
        return None  # idempotent re-run: everything is already labelled
    if untagged < MIN_EXPECTED_TAGS:
        return (
            f"the plan writes {untagged} new tag(s), below the floor "
            f"{MIN_EXPECTED_TAGS}, and some candidates are still untagged — "
            f"either the population has moved or the judgement has stopped "
            f"reaching it. Re-measure before writing."
        )
    if len(plan.tags) > MAX_EXPECTED_TAGS:
        return (
            f"the plan writes {len(plan.tags)} tags, above the ceiling "
            f"{MAX_EXPECTED_TAGS} — the population is far beyond what was "
            f"measured; re-measure before writing."
        )
    return None


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's CURRENT `event_tags` before anything is appended.

    `ON CONFLICT DO NOTHING` keeps the FIRST banked value, which is the
    pre-repair one — a re-run after a partial apply must not overwrite a clean
    banked array with one that already carries the tag we wrote.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  canonical_id bigint NOT NULL,"
            "  old_tags text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = 0
    for tag in tags:
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, canonical_id, old_tags) "
                "VALUES (:eid, :cid, :old) ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": tag.ghost_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.ghost_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def write_tags(session, tags, *, progress_every: int = 25):
    """Append the duplicate tag to each ghost, ONE ROW PER TRANSACTION.

    Core SQL with a server-side `||`, never an ORM assignment: `event_tags` is
    JSONB and gotcha #4 is that a JSONB ORM assignment can silently fail to
    persist, gotcha #5 that mixing the two styles in one session is where flush
    ordering bites. The `NOT @>` makes it idempotent in the DATABASE rather than
    in this process's memory, so a re-run cannot double-append.

    Single-row and patient rather than one batched UPDATE: `events` is write-hot
    (constant poller and backfill locks) and a batched one-off rolls back on
    every row where a patient single-row write succeeds.

    Returns ``(written, failed_ids)``. Failures are RETAINED, not just printed —
    on a detached dyno whose stdout nobody reads, a printed FAILED line that does
    not reach the exit code is indistinguishable from a clean run (gotcha #53).
    """
    from sqlalchemy import text

    written, failed = 0, []
    for index, tag in enumerate(tags, start=1):
        payload = json.dumps([duplicate_tag(tag.canonical_id)])
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events "
                        "SET event_tags = COALESCE(event_tags, '[]'::jsonb) "
                        "                 || CAST(:tag_array AS jsonb) "
                        "WHERE id = :eid "
                        "  AND NOT COALESCE(event_tags, '[]'::jsonb) "
                        "          @> CAST(:tag_array AS jsonb)"
                    ),
                    {"tag_array": payload, "eid": tag.ghost_id},
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {tag.ghost_id} after 3 attempts: {exc}")
                    failed.append(tag.ghost_id)
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(tags)} processed, {written} tagged")
    return written, failed


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
