"""#8774 — D99 = A: zero the hand boosts on markets whose event is over a year out.

THE SHIP: "Canadian Team to Win the Stanley Cup® Before the 2030-31 Season" stops
holding a Discover page-one slot. It resolves June 2030, trades $25 a day and has no
movement evidence; on 2026-09-26 02:25Z it sat at slot 6 of ``/api/feed`` (slot 4 on
the 390px web page) on ``rank_final 121.5``, of which ``curation_adj:+60`` is the
largest single term. #4161 withdrew the +40 postseason boost from this exact market
and was out-voted by that +60.

WHAT THE +60 IS
---------------

Four taps of the boost shortcut. ``admin_judgments.py`` adds +15 per boost tap to
``futures_markets.curation_score_adj`` — an accumulator, with no ceiling and no decay —
so nobody chose +60; the fourth tap simply counted (#4161, discover/017).

THE RULING
----------

**D99 = A (Alex, Wed 2026-09-09 10:05am PT):** zero the hand boosts on markets whose
event is over a year out, with a backup and an undo. Nothing executed it; this does.

WHAT IT DOES
------------

Sets ``curation_score_adj`` to 0 on the eight pinned markets below, in one
transaction, and changes nothing else on any row.

**No backup table, and that is a proof rather than a habit** (the argument
``repair_8308_dangling_duplicate_tags`` makes for its write): each write is a
compare-and-set from the pinned value to 0, so a row this changes held EXACTLY its
pinned value a moment earlier, and the pinned value restores it. ``PINNED`` is the
backup; ``--restore`` is the inverse compare-and-set (0 back to the pinned value).
No DDL runs, so this is a data write, not notice 47(c) runtime DDL.

THE POPULATION (production 2026-09-26 02:3xZ: open, ``curation_score_adj > 0``,
event over a year out)
-----------------------------------------------------------------------------------

Pinned, not queried at run time: a query would re-decide the population on the day it
runs, and a boost someone taps next week is a decision with a ledger line (D99's
second half), not this ruling's residue.

DELIBERATELY NOT TOUCHED (same read)
------------------------------------

* ``5388751`` / ``5165726`` / ``6173044`` (Oscar nominees / winner) and ``108505``
  ("Who will headline Coachella 2027?") resolve 2027-12-31 — past the year by their
  resolution date — but the EVENT each names, the 2027 ceremony / festival, falls
  inside twelve months. The ruling is about the event.
* Demotes (negative adjustments) are not boosts.
* ``1`` / ``86832`` (odds_api World Series / Super Bowl, +75) carry no resolution date
  and their events are inside a year.

PER-ROW SKIPS (reported, never written)
---------------------------------------

* the row is missing, or no longer ``open`` — it left the feed on its own;
* its value is neither the pinned value nor 0 — someone has tapped since the read,
  which is a new decision this script does not own;
* already at the target value — this ran already.

REFUSALS (the whole run stops, nothing is written)
--------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* a write that changes other than exactly one row.

    python3 scripts/repair_8774_far_horizon_hand_boosts.py            # dry run
    python3 scripts/repair_8774_far_horizon_hand_boosts.py --apply    # zero the eight
    python3 scripts/repair_8774_far_horizon_hand_boosts.py --restore  # undo
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

#: market id → the ``curation_score_adj`` it carried on the 2026-09-26 read. The backup.
PINNED: dict[int, int] = {
    171: 60,  # Canadian Team to Win the Stanley Cup® Before the 2030-31 Season (2030-06-30)
    108258: 15,  # Next James Bond film: Actor cast as the villain (2030-01-02)
    108290: 15,  # How much will a Fyre Festival 2 General Admission Ticket cost? (2030-01-01)
    108326: 60,  # 2028 U.S. Presidential Election winner? (2029-01-21)
    108445: 60,  # 2028 Democratic presidential nominee (2028-11-07)
    34274214: 15,  # US real GDP growth in 2027? (2028-02-28)
    108477: 15,  # Will the ban on supersonic flight over land end before 2028? (2028-01-01)
    31833064: 30,  # When will Waymo officially announce an IPO? (2028-01-01)
}


class Refused(RuntimeError):
    """The run stops before any write."""


def refuse_unless_production(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused(
            f"HEROKU_APP_NAME={app!r} is not a production app "
            f"({sorted(PRODUCTION_APPS)}); refusing"
        )


def plan(rows: dict[int, tuple[str | None, int | None]], *, restore: bool) -> dict:
    """Decide per pinned market, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each pinned id that EXISTS to ``(status, curation_score_adj)``; a
    pinned id absent from ``rows`` is a missing row. Returns the ``(id, from, to)``
    writes and the ``(id, reason)`` skips.
    """
    write, skip = [], []
    for market_id, pinned in PINNED.items():
        if market_id not in rows:
            skip.append((market_id, "row missing"))
            continue
        status, adj = rows[market_id]
        current = adj or 0
        if status != "open":
            skip.append((market_id, f"status {status!r}, not open"))
            continue
        source, target = (0, pinned) if restore else (pinned, 0)
        if current == target:
            skip.append((market_id, f"already {target}"))
        elif current != source:
            skip.append(
                (
                    market_id,
                    f"adj {current} is neither {source} nor {target} — tapped since",
                )
            )
        else:
            write.append((market_id, source, target))
    return {"write": write, "skip": skip}


async def _read(session) -> dict[int, tuple[str | None, int | None]]:
    got = await session.execute(
        text(
            "SELECT id, status, curation_score_adj FROM futures_markets "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": list(PINNED)},
    )
    return {int(r.id): (r.status, r.curation_score_adj) for r in got}


# The WHERE re-states the compare half of the compare-and-set, so a tap that lands
# between the read and the write makes the statement change 0 rows and the run refuses
# rather than overwriting it. `COALESCE` because the column is nullable and NULL means 0
# to every reader (`feed.py`: `curation_score_adj ... or 0`).
_CAS_SQL = (
    "UPDATE futures_markets SET curation_score_adj = :target "
    "WHERE id = :id AND COALESCE(curation_score_adj, 0) = :source"
)


async def run(session, *, apply: bool, restore: bool) -> dict:
    rows = await _read(session)
    decided = plan(rows, restore=restore)
    written = 0
    if apply or restore:
        for market_id, source, target in decided["write"]:
            result = await session.execute(
                text(_CAS_SQL), {"id": market_id, "source": source, "target": target}
            )
            if result.rowcount != 1:
                raise Refused(
                    f"market {market_id}: expected to change 1 row, changed {result.rowcount}"
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
            "python3 scripts/repair_8774_far_horizon_hand_boosts.py --restore"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
