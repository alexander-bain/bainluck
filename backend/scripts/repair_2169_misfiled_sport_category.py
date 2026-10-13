"""#2169 — the named markets filed under the wrong sport move to their own category.

THE SHIP: the World Series of Darts matches and the other named markets below stop
being filed under baseball, golf and basketball. On their own pages, in search and
on the accuracy page they sit under darts, esports, entertainment and politics,
which is what they are.

WHY THESE ROWS STAY WRONG WITHOUT A WRITE
-----------------------------------------

F3 (#2161, live since 2026-09-05) fixed ``categorize_by_rules()`` for rows minted
from then on. It touched no stored row. The Polymarket poller only re-categorises
markets it still polls, and these are settled; the Kalshi upsert never overwrites
an existing real tag (``kalshi.py``: ``coalesce(nullif(llm_sport_category,
'other'), ...)``). So nothing in the pipeline will ever move them.

THE RULING (Alex, 2026-08-24, on #2169)
---------------------------------------

"F3 deploy → the bounded backfill as its own cert-flagged apply → F2 shadow
cutover on clean data." **Category only.** ``canonical_market_key`` is NOT
recomputed here; F2 (#2163) owns the key and runs after this, over the data this
corrects. Until then a darts row keyed ``baseball:MLB:championship:2026`` is the
accepted, bounded half-fixed window.

WHAT IT DOES
------------

For each pinned id, in one transaction, a compare-and-set of
``llm_sport_category`` from its pinned ``before`` to its pinned ``after``. No other
column moves on any row; ``updated_at`` is left alone too (the ORM ``onupdate``
does not fire for Core SQL, so stating that is enough).

**No backup table, and that is a proof rather than a habit** (the argument
``repair_8774_far_horizon_hand_boosts`` makes): every write is a compare-and-set
from the pinned value, so a row this changes held EXACTLY its pinned ``before`` a
moment earlier, and the pinned ``before`` restores it. ``PINNED`` is the backup.
No DDL runs, so this is a data write, not notice 47(c) runtime DDL.

``--restore --ids …`` is the inverse compare-and-set (``after`` back to
``before``) and refuses to run without the id list the apply printed. A bare
restore over all of ``PINNED`` would be wrong: two rows had already been repaired
by the pipeline before this script existed, and "undo" must never write a wrong
value the apply did not remove.

THE POPULATION — pinned, not queried at run time
------------------------------------------------

The 23 writes and one no-op named on #2169, measured 2026-08-24 by diffing the
F3-fixed ``categorize_by_rules()`` against the stored value. A re-census at run
time would re-decide the population; ``\\bdarts?\\b`` alone also catches NFL QB
Jaxson Dart and tennis player Harriet Dart, which queue 402 found and rejected.

Production read 2026-10-13 07:35Z: 21 rows still hold their ``before``; 58015857
already reads ``tech`` and 59520510 already reads ``politics`` (both repaired by
the pipeline), so they skip as "already". 20 of the 21 are settled; 59165075 is
open on Kalshi, whose upsert keeps the value once written.

PER-ROW SKIPS (reported, never written)
---------------------------------------

* the row is missing;
* it already holds ``after`` — repaired already, by this or by the pipeline;
* it holds neither ``before`` nor ``after`` — a writer this script does not know
  about has decided since the read, and that is not ours to overwrite;
* the fixed classifier no longer answers ``after`` for the row's live name — the
  name moved since the plan, so the plan's evidence no longer covers the row.

REFUSALS (the whole run stops, nothing is written)
--------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* ``--apply`` whose ``--expect-plan-hash`` is not the hash of the writes decided in
  this run (the dry run prints it), so the attended apply writes exactly the plan
  the reviewer read and not one row more;
* ``--restore`` without ``--ids``, or with an id that is not pinned;
* any statement that changes other than exactly one row — including a row whose
  category OR name moved between the read and its write (the UPDATE re-states
  both, the name null-safely, so the classifier's evidence still covers the row);
* the database stopping a statement: the run carries its own short lock and
  statement budgets, so a contended row refuses in seconds with the whole
  transaction rolled back, never a partial commit and never an unbounded wait.

DELIBERATELY NOT TOUCHED
------------------------

* ``38277227`` "Asia Masters 2026 Winner" — snooker, filed ``golf``. Title-only
  rules cannot tell it from the golf Masters; owed to F2 (#2163) or the LLM
  fallback. Read and reported every run so the no-op is visibly honoured.
* ``canonical_market_key``, ``category_tags``, ``llm_league`` — F2's, or derived.
* the 2,365 ITF rows tagged ``table_tennis`` and ``110568`` (T20 World Cup final,
  ``soccer``) — other writers, other issues.

    python3 scripts/repair_2169_misfiled_sport_category.py                         # dry run
    python3 scripts/repair_2169_misfiled_sport_category.py --apply --expect-plan-hash H
    python3 scripts/repair_2169_misfiled_sport_category.py --restore --ids 1,2,3   # undo
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

#: market id → (``llm_sport_category`` before, after). The #2169 table, verbatim. The backup.
PINNED: dict[int, tuple[str, str]] = {
    59304735: ("baseball", "darts"),  # World Series of Darts: Jonny Clayton vs Ben Robb
    59304736: ("baseball", "darts"),  # World Series of Darts: Damon Heta vs Joe Comito
    59304737: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Gian van Veen vs Raymond Smith
    59304738: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Ross Smith vs Brody Klinge
    59304739: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Stephen Bunting vs Mal Cuming
    59304740: ("baseball", "darts"),  # World Series of Darts: James Wade vs Tim Pusey
    59304741: ("baseball", "darts"),  # World Series of Darts: Josh Rock vs Adam Leek
    59304742: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Gerwyn Price vs Simon Whitlock
    59374602: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Jonny Clayton vs Damon Heta
    59374603: ("baseball", "darts"),  # World Series of Darts: Gerwyn Price vs Josh Rock
    59374604: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Gian van Veen vs Brody Klinge
    59374605: (
        "baseball",
        "darts",
    ),  # World Series of Darts: James Wade vs Stephen Bunting
    59428372: (
        "baseball",
        "darts",
    ),  # World Series of Darts: Gerwyn Price vs James Wade
    58416367: ("golf", "darts"),  # New Zealand Darts Masters: Winner
    35418786: ("golf", "esports"),  # Most kills on a single map at Masters London 2026?
    31169677: (
        "golf",
        "entertainment",
    ),  # "Masters of the Universe" Opening Weekend Box Office
    58015857: (
        "golf",
        "tech",
    ),  # Will Anthropic sign the Open Weights and American AI ... letter?
    58728438: (
        "basketball",
        "entertainment",
    ),  # Practical Magic 2 · Rotten Tomatoes score
    59170844: (
        "basketball",
        "entertainment",
    ),  # "The Magic Faraway Tree" Rotten Tomatoes Score?
    59170845: (
        "basketball",
        "entertainment",
    ),  # Will "The Magic Faraway Tree" score at least 80 ...
    59170847: (
        "basketball",
        "entertainment",
    ),  # Will "The Magic Faraway Tree" score at least 90 ...
    59520510: ("basketball", "politics"),  # Thunder Bay, ON Mayoral Election Winner
    # A CONTROL in the F3 corpus, not an F3 specimen: rules already said politics
    # before the fix and another writer stored basketball. In scope because the
    # criterion is the row (stored value wrong, rules answer right), not the writer.
    59165075: (
        "basketball",
        "politics",
    ),  # Los Angeles L next governor before Jan 1, 2027?
}

#: The documented no-op: read and reported, never written.
NO_OP: dict[int, str] = {
    38277227: "golf",  # Asia Masters 2026 Winner — snooker, unreachable by title-only rules
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


def plan_hash(writes: list[tuple[int, str, str]]) -> str:
    """The identity of a set of writes, order-free. What the apply must be told."""
    canon = json.dumps(sorted([int(i), f, t] for i, f, t in writes))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def plan(
    rows: dict[int, tuple[str | None, str | None]],
    classify,
    *,
    restore_ids: frozenset[int] | None = None,
) -> dict:
    """Decide per pinned market, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each id that EXISTS to ``(llm_sport_category, name)``; a pinned id
    absent from ``rows`` is a missing row. ``classify`` is ``categorize_by_rules``
    (injected so the units can prove the gate bites). ``restore_ids`` set ⇒ undo
    mode, over exactly those ids. Returns ``(id, from, to)`` writes, ``(id,
    reason)`` skips, and the no-op row's observed value.
    """
    restore = restore_ids is not None
    write, skip = [], []
    ids = sorted(restore_ids) if restore else list(PINNED)
    for market_id in ids:
        before, after = PINNED[market_id]
        if market_id not in rows:
            skip.append((market_id, "row missing"))
            continue
        current, name = rows[market_id]
        source, target = (after, before) if restore else (before, after)
        if current == target:
            skip.append((market_id, f"already {target!r}"))
            continue
        if current != source:
            skip.append(
                (
                    market_id,
                    f"holds {current!r}, neither {source!r} nor {target!r} — "
                    "another writer decided since the plan",
                )
            )
            continue
        if not restore:
            answer = classify(name or "")
            if answer != after:
                skip.append(
                    (
                        market_id,
                        f"fixed classifier now answers {answer!r} for the live name, "
                        f"not {after!r} — the plan's evidence no longer covers it",
                    )
                )
                continue
        write.append((market_id, source, target))
    no_op = {
        market_id: (rows[market_id][0] if market_id in rows else None)
        for market_id in NO_OP
    }
    return {"write": write, "skip": skip, "no_op": no_op, "plan_hash": plan_hash(write)}


async def _read(session) -> dict[int, tuple[str | None, str | None]]:
    got = await session.execute(
        text(
            "SELECT id, llm_sport_category, name FROM futures_markets "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": list(PINNED) + list(NO_OP)},
    )
    return {int(r.id): (r.llm_sport_category, r.name) for r in got}


# The WHERE re-states EVERYTHING the plan decided on, so a writer landing between
# the read and the write makes the statement change 0 rows and the run refuses
# rather than overwriting it. Two halves:
#
# * the category — the compare half of the compare-and-set. Plain `=` is enough:
#   every pinned `before`/`after` is a non-null string, and NULL never equals one.
# * the observed NAME — the classifier gate in ``plan()`` judged the name it read,
#   so the write is only covered by that evidence while the name is unchanged. A
#   rename of the open Kalshi row 59165075 between ``_read()`` and its UPDATE, with
#   the category still ``basketball``, would otherwise land ``politics`` on a name
#   nobody classified. Null-safe (`IS NOT DISTINCT FROM`) because ``name`` is the
#   one compared value that can legitimately be NULL: a NULL name read must match
#   a NULL name now, and a name set since must not.
_CAS_SQL = (
    "UPDATE futures_markets SET llm_sport_category = :target "
    "WHERE id = :id AND llm_sport_category = :source "
    "AND name IS NOT DISTINCT FROM :name"
)

#: The attended run's own budgets, per connection (``get_task_session`` kwargs, so
#: they survive a pool reconnect — #4482). Without them the session rests at the
#: 30-minute statement bound and NO lock bound: one contended row would hold the
#: whole transaction open on production. With them a busy row stops the run in
#: seconds, the transaction rolls back, and nothing is committed. Same values as
#: the sibling attended repairs (``repair_10520_keeper_current_anchor``).
LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 10000


def parse_ids(raw: str) -> frozenset[int]:
    ids = frozenset(int(x) for x in raw.split(",") if x.strip())
    stray = sorted(ids - set(PINNED))
    if not ids:
        raise Refused("--ids is empty")
    if stray:
        raise Refused(f"--ids names ids that are not pinned: {stray}")
    return ids


async def run(
    session,
    classify,
    *,
    apply: bool,
    expect_plan_hash: str | None = None,
    restore_ids: frozenset[int] | None = None,
) -> dict:
    rows = await _read(session)
    decided = plan(rows, classify, restore_ids=restore_ids)
    if apply and expect_plan_hash != decided["plan_hash"]:
        raise Refused(
            f"plan hash is {decided['plan_hash']}, expected {expect_plan_hash!r} — "
            "the population moved since the dry run; re-read it"
        )
    written = 0
    if apply or restore_ids is not None:
        for market_id, source, target in decided["write"]:
            result = await session.execute(
                text(_CAS_SQL),
                {
                    "id": market_id,
                    "source": source,
                    "target": target,
                    "name": rows[market_id][1],
                },
            )
            if result.rowcount != 1:
                raise Refused(
                    f"market {market_id}: expected to change 1 row, changed "
                    f"{result.rowcount} — its category or name moved since the read"
                )
            written += 1
        await session.commit()
    return {
        "mode": (
            "restore" if restore_ids is not None else ("apply" if apply else "dry-run")
        ),
        "write": decided["write"],
        "skip": decided["skip"],
        "no_op": decided["no_op"],
        "plan_hash": decided["plan_hash"],
        "written": written,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", action="store_true")
    ap.add_argument("--expect-plan-hash", default=None)
    ap.add_argument(
        "--ids", default=None, help="restore only: the ids the apply printed"
    )
    args = ap.parse_args()

    try:
        refuse_unless_production(dict(os.environ))
        if args.apply and not args.expect_plan_hash:
            raise Refused("--apply needs --expect-plan-hash (printed by the dry run)")
        if args.restore and not args.ids:
            raise Refused("--restore needs --ids (printed by the apply)")
        if args.ids and not args.restore:
            raise Refused("--ids is for --restore only")
        restore_ids = parse_ids(args.ids) if args.restore else None
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2

    from sqlalchemy.exc import DBAPIError

    from app.tasks.base import get_task_session
    from app.utils.futures_categorization import categorize_by_rules

    async with get_task_session(
        statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS
    ) as session:
        try:
            out = await run(
                session,
                categorize_by_rules,
                apply=args.apply,
                expect_plan_hash=args.expect_plan_hash,
                restore_ids=restore_ids,
            )
        except Refused as exc:
            await session.rollback()
            print(f"REFUSED: {exc}")
            return 2
        except DBAPIError as exc:
            # A budget firing (lock_timeout 55P03, statement_timeout 57014) or any
            # other server refusal: the transaction rolls back whole, so no row of
            # the plan is committed, and the run says so rather than tracebacking.
            await session.rollback()
            code = getattr(exc.orig, "sqlstate", None) or getattr(
                exc.orig, "pgcode", None
            )
            print(
                f"REFUSED: the database stopped the run ({type(exc.orig).__name__}, "
                f"sqlstate {code}); rolled back, nothing committed — re-run the dry "
                "run when production is quieter"
            )
            return 2
    print(json.dumps(out, indent=2))
    if out["mode"] == "apply" and out["written"]:
        ids = ",".join(str(i) for i, _, _ in out["write"])
        print(
            "UNDO: heroku run:detached -a bainluck -- "
            f"python3 scripts/repair_2169_misfiled_sport_category.py --restore --ids {ids}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
