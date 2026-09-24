"""#8308 — un-hide two MLB doubleheader games whose "duplicate of" tag points at a deleted row.

THE SHIP: Blue Jays @ Orioles game 2 (2026-09-23, ``/events/15317724``) and Rays @
Yankees game 2 (2026-09-22, ``/events/15316870``) appear on the MLB page. Both rows
are the only row we hold for their game, both carry the score MLB's own API gives
(``gamePk 824784`` BAL 4–0 at 23:40Z, then live; ``gamePk 823494`` TB 6 – NYY 1,
Final), and both are on no rail of ``/api/leagues/baseball_mlb`` because
``not_a_proven_duplicate()`` hides them.

WHY THEY ARE HIDDEN (read from production 2026-09-23 23:45Z)
------------------------------------------------------------

Each carries ``provenance:duplicate-of:<N>`` and row N no longer exists — a merge rail
deleted it after the tag was written, and ``repoint_event_children`` moved every
foreign-key child of the deleted row but not this tag, which is not a foreign key. The
code half of #8308 makes the merge rail retarget or clear the tag from now on; this
script heals the two rows already stranded.

WHAT IT DOES
------------

Removes exactly one pinned element from ``event_tags`` on each pinned row, in one
transaction. Nothing else on the row changes.

**No backup table, and that is a proof rather than a habit** (the argument
``reconcile_shared_fixture_ids`` makes for the same write): the only change is
``event_tags - '<tag>'`` on a row that carried ``<tag>`` a moment earlier, so the
inverse, ``event_tags || '["<tag>"]'``, restores the column's membership exactly. The
pinned pairs below ARE the backup, and ``--restore`` is that inverse over them. No DDL
runs, so this is a data write, not notice 47(c) runtime DDL.

DELIBERATELY NOT HEALED (census, same read — five dangling rows in all)
-----------------------------------------------------------------------

* ``14788069`` (Rays @ Yankees 2026-09-22 game 1) — the row carries game 2's 1–6 score;
  MLB ``823543`` is Yankees 2–0. Un-hiding it would print a wrong result. It is #8278's
  makeup class and waits for its score (comment on #8278).
* ``15297966`` (Lazio–AC Milan 9/12), ``15297786`` (Brest–PSG 9/13) — scores not
  verified against a venue (ESPN is unreachable from the lane sandbox).

REFUSALS (the whole run stops, nothing is written)
---------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``) — there is no other database this is about;
* a pinned target id EXISTS — the tag is no longer dangling, so it may be a real
  "duplicate of" claim and removing it would print a second card for one game.

A pinned row that is missing, or already lacks its tag, is reported and skipped: the
first can only mean the row was merged away (its game then lives on the survivor), the
second that this ran already.

    python3 scripts/repair_8308_dangling_duplicate_tags.py            # dry run
    python3 scripts/repair_8308_dangling_duplicate_tags.py --apply    # remove the two tags
    python3 scripts/repair_8308_dangling_duplicate_tags.py --restore  # undo
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

#: row id → the dead canonical its tag names. The tag is derived, never typed twice.
PINNED: dict[int, int] = {
    15317724: 15317957,  # BAL–TOR 2026-09-23 game 2 (MLB 824784)
    15316870: 15317440,  # NYY–TB 2026-09-22 game 2 (MLB 823494)
}

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


def plan(rows: dict[int, list | None], live_targets: set[int], *, restore: bool) -> dict:
    """Decide per pinned row, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to its ``event_tags`` (``None`` for SQL
    NULL); a pinned id absent from ``rows`` is a missing row. ``live_targets`` is the
    subset of pinned target ids that exist.
    """
    alive = sorted(t for t in PINNED.values() if t in live_targets)
    if alive:
        raise Refused(
            f"target row(s) {alive} exist — those tags are not dangling; refusing"
        )
    write, skip = [], []
    for row_id, target in PINNED.items():
        tag = tag_for(target)
        if row_id not in rows:
            skip.append((row_id, "row missing"))
            continue
        has = tag in (rows[row_id] or [])
        if restore and has:
            skip.append((row_id, "tag already present"))
        elif not restore and not has:
            skip.append((row_id, "tag already absent"))
        else:
            write.append((row_id, tag))
    return {"write": write, "skip": skip}


async def _read(session) -> tuple[dict[int, list | None], set[int]]:
    ids = list(PINNED)
    targets = list(PINNED.values())
    got = await session.execute(
        text("SELECT id, event_tags FROM events WHERE id = ANY(:ids)"), {"ids": ids}
    )
    rows = {int(r.id): r.event_tags for r in got}
    live = await session.execute(
        text("SELECT id FROM events WHERE id = ANY(:ids)"), {"ids": targets}
    )
    return rows, {int(r.id) for r in live}


async def run(session, *, apply: bool, restore: bool) -> dict:
    rows, live_targets = await _read(session)
    decided = plan(rows, live_targets, restore=restore)
    written = 0
    if apply or restore:
        for row_id, tag in decided["write"]:
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
                raise Refused(
                    f"row {row_id}: expected to change 1 row, changed {result.rowcount}"
                )
            written += 1
        await session.commit()
    return {
        "mode": "restore" if restore else ("apply" if apply else "dry-run"),
        "write": decided["write"],
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
            "python3 scripts/repair_8308_dangling_duplicate_tags.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
