"""#8278 — put two doubleheader game-1 finals back to the score MLB gives them.

THE SHIP: Rays @ Yankees game 1 (2026-09-22, ``/events/14788069``) reads Yankees
2–0 and appears on the MLB page; Blue Jays @ Orioles game 1 (2026-09-23,
``/events/15316846``) reads Orioles 4–2 on the MLB page's results rail.

WHY THEY ARE WRONG (read from production 2026-09-24 ~02:20Z)
------------------------------------------------------------

The hourly StatPal schedule pass found each game-1 fixture's live row by team
pair, and game 2's live row passed its 12h clock check (the games are ~6h
apart), so game 2's live score was written onto game 1's already-final row.
That path writes no score snapshot, and neither row has a snapshot at the
stored score. The code half of #8278 (same branch) gives this pass an anchor
test and a nearest-fixture test; this script heals the two rows already hit.

=========  ======================  ======  =====  ==================================
row        game                    stored  truth  truth read from
=========  ======================  ======  =====  ==================================
14788069   TB @ NYY 9/22 game 1    1–6     2–0    MLB 823543 Final; ESPN 401873648
15316846   TOR @ BAL 9/23 game 1   4–0     4–2    MLB 824785 Final
=========  ======================  ======  =====  ==================================

(home–away, both rows' home side matches MLB's home side.) 1–6 is game 2's
final (MLB 823494); 4–0 is game 2's score from 23:30Z to 00:56Z (MLB 824784).

14788069 also carries ``provenance:duplicate-of:15316824`` and row 15316824 does
not exist, so ``not_a_proven_duplicate()`` hides the only row for the game. #8308's
repair left it on purpose until the score was right; this removes it.

WHAT IT DOES
------------

In one transaction: for each pinned row, sets ``home_score/away_score`` from the
pinned wrong pair to the pinned right pair, compare-and-write on the wrong pair;
and removes the one pinned tag. Nothing else on either row changes.

**No backup table, by the same argument #8308's repair makes:** every write is a
pinned before→after on a row that held the before a moment earlier, so the
pinned values ARE the backup and ``--restore`` is their exact inverse. No DDL.

NOT DONE HERE: the seven Kalshi team-total outcomes on 14788069 graded from
``game_score`` all read True (including "New York Y over 6.5 runs"), which no
score of this game supports. That is a grading defect filed on its own issue.

REFUSALS (the whole run stops, nothing is written)
---------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* a pinned row holds a score that is neither its wrong nor its right pair — the
  row moved since it was read, and a write would overwrite something unread;
* the pinned tag target EXISTS — the tag may be a real "duplicate of" claim.

A pinned row that is missing, or already holds the target state, is reported and
skipped.

    python3 scripts/repair_8278_doubleheader_game1_scores.py            # dry run
    python3 scripts/repair_8278_doubleheader_game1_scores.py --apply    # correct
    python3 scripts/repair_8278_doubleheader_game1_scores.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

#: row id → (stored wrong (home, away), MLB's final (home, away)).
PINNED_SCORES: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {
    14788069: ((1, 6), (2, 0)),  # TB @ NYY 2026-09-22 game 1 (MLB 823543)
    15316846: ((4, 0), (4, 2)),  # TOR @ BAL 2026-09-23 game 1 (MLB 824785)
}

#: row id → the dead canonical its tag names.
PINNED_TAGS: dict[int, int] = {14788069: 15316824}

TAG_PREFIX = "provenance:duplicate-of:"


def tag_for(target_id: int) -> str:
    return f"{TAG_PREFIX}{target_id}"


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(
    scores: dict[int, tuple],
    tags: dict[int, list | None],
    live_targets: set[int],
    *,
    restore: bool,
) -> dict:
    """Decide per pinned row, from what was read. Pure, so the unit file drives it.

    ``scores`` maps each pinned score row that EXISTS to its ``(home, away)``;
    ``tags`` maps each pinned tag row that exists to its ``event_tags``;
    ``live_targets`` is the subset of pinned tag targets that exist.
    """
    alive = sorted(t for t in PINNED_TAGS.values() if t in live_targets)
    if alive:
        raise Refused(f"tag target row(s) {alive} exist — not dangling; refusing")

    score_writes, tag_writes, skip = [], [], []
    for row_id, (wrong, right) in PINNED_SCORES.items():
        if row_id not in scores:
            skip.append((row_id, "row missing"))
            continue
        have = tuple(scores[row_id])
        before, after = (right, wrong) if restore else (wrong, right)
        if have == after:
            skip.append((row_id, f"score already {after[0]}-{after[1]}"))
        elif have == before:
            score_writes.append((row_id, before, after))
        else:
            raise Refused(
                f"row {row_id} holds {have}, neither {wrong} nor {right}; "
                "it moved since it was read"
            )
    for row_id, target in PINNED_TAGS.items():
        tag = tag_for(target)
        if row_id not in tags:
            skip.append((row_id, "row missing (tag)"))
            continue
        has = tag in (tags[row_id] or [])
        if restore and has:
            skip.append((row_id, "tag already present"))
        elif not restore and not has:
            skip.append((row_id, "tag already absent"))
        else:
            tag_writes.append((row_id, tag))
    return {"scores": score_writes, "tags": tag_writes, "skip": skip}


async def _read(session):
    ids = sorted(set(PINNED_SCORES) | set(PINNED_TAGS))
    got = await session.execute(
        text("SELECT id, home_score, away_score, event_tags FROM events WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    scores, tags = {}, {}
    for r in got:
        if int(r.id) in PINNED_SCORES:
            scores[int(r.id)] = (r.home_score, r.away_score)
        if int(r.id) in PINNED_TAGS:
            tags[int(r.id)] = r.event_tags
    live = await session.execute(
        text("SELECT id FROM events WHERE id = ANY(:ids)"),
        {"ids": list(PINNED_TAGS.values())},
    )
    return scores, tags, {int(r.id) for r in live}


async def run(session, *, apply: bool, restore: bool) -> dict:
    scores, tags, live_targets = await _read(session)
    decided = plan(scores, tags, live_targets, restore=restore)
    written = 0
    if apply or restore:
        for row_id, before, after in decided["scores"]:
            result = await session.execute(
                text(
                    "UPDATE events SET home_score = :h1, away_score = :a1 "
                    "WHERE id = :id AND home_score = :h0 AND away_score = :a0"
                ),
                {"id": row_id, "h0": before[0], "a0": before[1],
                 "h1": after[0], "a1": after[1]},
            )
            if result.rowcount != 1:
                raise Refused(f"row {row_id}: expected 1 score row, changed {result.rowcount}")
            written += 1
        for row_id, tag in decided["tags"]:
            if restore:
                sql = (
                    "UPDATE events SET event_tags = "
                    "COALESCE(event_tags, '[]'::jsonb) || jsonb_build_array(CAST(:tag AS text)) "
                    "WHERE id = :id AND NOT COALESCE(event_tags, '[]'::jsonb) "
                    "@> jsonb_build_array(CAST(:tag AS text))"
                )
            else:
                sql = (
                    "UPDATE events SET event_tags = event_tags - CAST(:tag AS text) "
                    "WHERE id = :id AND event_tags @> jsonb_build_array(CAST(:tag AS text))"
                )
            result = await session.execute(text(sql), {"id": row_id, "tag": tag})
            if result.rowcount != 1:
                raise Refused(f"row {row_id}: expected 1 tag row, changed {result.rowcount}")
            written += 1
        await session.commit()
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "scores": decided["scores"],
        "tags": decided["tags"],
        "skip": decided["skip"],
        "written": written,
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
    print(json.dumps(out, indent=2))
    if out["mode"] == "apply":
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            "python3 scripts/repair_8278_doubleheader_game1_scores.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
