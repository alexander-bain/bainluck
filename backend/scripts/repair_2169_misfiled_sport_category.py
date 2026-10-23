"""#2169 — the named markets filed under the wrong sport move to their own category.

THE SHIP: the World Series of Darts matches and the other named markets below stop
being filed under baseball, golf and basketball. On their own pages, in search and
on the accuracy page they sit under darts, esports, entertainment and politics,
which is what they are. The Lakers' next-owner question (59165075) stays in
basketball: it was on this list by mistake, and is now held OFF it (below).

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
F3-fixed ``categorize_by_rules()`` against the stored value — 22 of those writes
stay in ``PINNED``; the 23rd was wrong and lives in ``REVERSED`` (next section),
so every run still reads the same 24 ids. A re-census at run
time would re-decide the population; ``\\bdarts?\\b`` alone also catches NFL QB
Jaxson Dart and tennis player Harriet Dart, which queue 402 found and rejected.

Production read 2026-10-13 07:35Z: 21 rows still hold their ``before``; 58015857
already reads ``tech`` and 59520510 already reads ``politics`` (both repaired by
the pipeline), so they skip as "already". 20 of the 21 are settled; 59165075 is
open on Kalshi, whose upsert keeps the value once written.

THE ROW THAT WAS WRONG — 59165075, applied then reversed
--------------------------------------------------------

``KXNBANEXTGOVERNOR-27JAN01LAL``, "Los Angeles L next governor before Jan 1,
2027?" — the next owner ("governor") of the Lakers; its roster is Josh Kushner,
Bob Iger, Mark Walter, Linda Rambis, Todd Boehly and "any other person (excluding
Jeanie Buss)". It is basketball, and its stored ``basketball`` was right.

How it got on the list: the 2026-08-24 diff ran the rules over the TITLE ALONE,
and a bare "governor" with no other context answers ``politics``. The Kalshi
ingest never asks that question that way: ``_categorize_kalshi_market`` reads the
ticker first, and ``KXNBA…`` maps to ``basketball_nba``. The plan's gate repeated
the title-only call, so it agreed with the mistake, and so did the C1 corpus.

History, kept rather than erased: the attended apply ``run.3172`` (2026-10-18,
plan ``190cf0e461b3a687``, 21 written) moved it basketball → politics with the
other 20; the attended one-row inverse ``--restore --ids 59165075`` ``run.6083``
(19:55:53Z, plan ``419f15edac6ddbba``, 1 written) moved it back. Its pair now sits
in ``REVERSED``: no forward run ever plans it again, every run reads it and
reports the value it holds, and ``--restore`` still accepts it, so the UNDO line
``run.3172`` printed (all 21 ids) stays a valid command.

And a gate, so the next row of this shape cannot get through the way this one
did: a forward write whose own provider ticker names a sport other than its
``after`` is skipped. A title-only answer never overrides league context the
provider already gave. The gate reads the venue's ticker map
(``sport_keys.get_sport_key_from_ticker``, the map the Kalshi ingest itself uses),
not a city or team-name list, so a real governor's race keeps its politics answer.

PER-ROW SKIPS (reported, never written)
---------------------------------------

* the row is missing;
* it already holds ``after`` — repaired already, by this or by the pipeline;
* it holds neither ``before`` nor ``after`` — a writer this script does not know
  about has decided since the read, and that is not ours to overwrite;
* the row's own provider ticker names a sport other than ``after`` — the venue
  already said what league the row is in, and a title-only answer must not
  overrule it (how 59165075 got onto the list);
* the fixed classifier no longer answers ``after`` for the row's live name — the
  name moved since the plan, so the plan's evidence no longer covers the row.

REFUSALS (the whole run stops, nothing is written)
--------------------------------------------------

* not on a production app (``HEROKU_APP_NAME`` must be ``bainluck`` or
  ``bainluck-heavy``);
* ``--apply`` whose ``--expect-plan-hash`` is not the hash of the writes decided in
  this run (the dry run prints it), so the attended apply writes exactly the plan
  the reviewer read and not one row more;
* ``--restore`` without ``--ids``, or with an id that is neither pinned nor reversed;
* any statement that changes other than exactly one row — including a row whose
  category, name, ``source`` OR ``external_id`` moved between the read and its
  write (the UPDATE re-states all four, the last three null-safely, so both the
  classifier's evidence and the provider gate's still cover the row);
* the database stopping a statement: the run carries its own short lock and
  statement budgets, so a contended row refuses in seconds with the whole
  transaction rolled back, never a partial commit and never an unbounded wait.

A COMMIT THAT DOES NOT RETURN IS NEITHER (exit 3)
-------------------------------------------------

The server can make the COMMIT durable and its acknowledgement still be lost
(SQLSTATE 08006), so once an apply or restore COMMIT has been sent and not
acknowledged, "nothing was written" is not knowable from the client, and a
rollback issued afterwards proves nothing about it. The run then prints
``"outcome": "UNKNOWN"`` with its mode, plan hash and the exact writes the
transaction carried, and stops: no rollback claim, no retry, no reconnect-write,
no restore. A cancel or interrupt that lands on the COMMIT prints the same report
and keeps propagating as itself. The readback is a dry run: every id of an apply
that landed reads ``already`` its ``after``; one that did not is a write again.

``get_task_session`` COMMITs again on a normal exit, so the run leaves it by the
exception path instead: the wrapper then rolls back, closes and disposes, which is
cleanup on a dead connection and evidence of nothing. A failure in that cleanup
is noted on stderr and changes neither the report, the exit 3, nor the type of a
cancel or interrupt.

DELIBERATELY NOT TOUCHED
------------------------

* ``38277227`` "Asia Masters 2026 Winner" — recorded as snooker on 2026-08-24,
  filed ``golf``. Title-only rules cannot tell it from the golf Masters; owed to
  F2 (#2163) or the LLM fallback. Read and reported every run so the no-op is
  visibly honoured. (2026-10-18: its served roster — Dplus, KT, NS Challengers, T1
  Esports Academy — does not support "snooker" either; what it is needs the venue's
  own word under #2163, not a rewrite here.)
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

from app.utils.sport_keys import (  # noqa: E402
    SPORT_PREFIX_TO_LLM_CATEGORY,
    get_sport_key_from_ticker,
)

PRODUCTION_APPS = frozenset({"bainluck", "bainluck-heavy"})

#: market id → (``llm_sport_category`` before, after). The #2169 table, verbatim, less its
#: wrong 23rd row (``REVERSED``). The backup.
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
}

#: The #2169 table's 23rd row, which was WRONG: applied by ``run.3172``, reversed by
#: ``run.6083`` (module docstring). Same ``(before, after)`` shape as ``PINNED`` so
#: the record and ``--restore`` keep working; the forward plan never writes it. The
#: stored ``basketball`` (``before``) is the truth — the Lakers' next owner.
REVERSED: dict[int, tuple[str, str]] = {
    59165075: (
        "basketball",
        "politics",
    ),  # Los Angeles L next governor before Jan 1, 2027? — KXNBANEXTGOVERNOR
}

#: The documented no-op: read and reported, never written.
NO_OP: dict[int, str] = {
    38277227: "golf",  # Asia Masters 2026 Winner — recorded as snooker, UNVERIFIED; owed to #2163
}


class Refused(RuntimeError):
    """The run stops before any write."""


class Unknown(RuntimeError):
    """The COMMIT was sent and never acknowledged: its writes may or may not be durable."""

    def __init__(self, report: dict):
        super().__init__(report["unknown"])
        self.report = report


def _unknown_report(decided: dict, mode: str, written: int, exc: BaseException) -> dict:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return {
        "outcome": "UNKNOWN",
        "mode": mode,
        "plan_hash": decided["plan_hash"],
        "write": decided["write"],
        "statements_changed": written,
        "unknown": (
            f"the {mode} COMMIT was sent and not acknowledged "
            f"({type(orig or exc).__name__}, sqlstate {code}); these writes may or may "
            "not be durable. Not retried, not restored — read the pinned rows back "
            "with the dry run before any further step"
        ),
    }


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


def provider_category(source: str | None, external_id: str | None) -> str | None:
    """The sport the row's own provider id names, or None when it names none.

    Kalshi only: its tickers carry the league (``KXNBA…`` → ``basketball``), read
    through the same ``sport_keys`` map ``_categorize_kalshi_market`` applies at
    ingest before any name rule. Polymarket ids are opaque numbers or hashes and
    name nothing, so they answer None and the title stays the only evidence.
    """
    if source != "kalshi" or not external_id:
        return None
    sport_key = get_sport_key_from_ticker(external_id)
    if not sport_key:
        return None
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_key.split("_")[0])


def plan(
    rows: dict[int, tuple[str | None, str | None, str | None, str | None]],
    classify,
    *,
    restore_ids: frozenset[int] | None = None,
) -> dict:
    """Decide per pinned market, from what was read. Pure, so the unit file drives it.

    ``rows`` maps each id that EXISTS to ``(llm_sport_category, name, source,
    external_id)``; a pinned id absent from ``rows`` is a missing row. ``classify``
    is ``categorize_by_rules`` (injected so the units can prove the gate bites).
    ``restore_ids`` set ⇒ undo mode, over exactly those ids (pinned or reversed).
    Returns ``(id, from, to)`` writes, ``(id, reason)`` skips, and the observed
    value of the no-op row and of the reversed row.
    """
    restore = restore_ids is not None
    write, skip = [], []
    ids = sorted(restore_ids) if restore else list(PINNED)
    for market_id in ids:
        before, after = (
            PINNED[market_id] if market_id in PINNED else REVERSED[market_id]
        )
        if market_id not in rows:
            skip.append((market_id, "row missing"))
            continue
        current, name, source_name, external_id = rows[market_id]
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
            league = provider_category(source_name, external_id)
            if league is not None and league != after:
                skip.append(
                    (
                        market_id,
                        f"its provider id {external_id!r} names {league!r}, not "
                        f"{after!r} — a title-only answer never overrides the league "
                        "the venue gave",
                    )
                )
                continue
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
    reversed_ = {
        market_id: (rows[market_id][0] if market_id in rows else None)
        for market_id in REVERSED
    }
    return {
        "write": write,
        "skip": skip,
        "no_op": no_op,
        "reversed": reversed_,
        "plan_hash": plan_hash(write),
    }


async def _read(
    session,
) -> dict[int, tuple[str | None, str | None, str | None, str | None]]:
    got = await session.execute(
        text(
            "SELECT id, llm_sport_category, name, source, external_id "
            "FROM futures_markets WHERE id = ANY(:ids)"
        ),
        {"ids": list(PINNED) + list(REVERSED) + list(NO_OP)},
    )
    return {
        int(r.id): (r.llm_sport_category, r.name, r.source, r.external_id) for r in got
    }


# The WHERE re-states EVERYTHING the plan decided on, so a writer landing between
# the read and the write makes the statement change 0 rows and the run refuses
# rather than overwriting it. Three parts:
#
# * the category — the compare half of the compare-and-set. Plain `=` is enough:
#   every pinned `before`/`after` is a non-null string, and NULL never equals one.
# * the observed NAME — the classifier gate in ``plan()`` judged the name it read,
#   so the write is only covered by that evidence while the name is unchanged. A
#   rename between ``_read()`` and its UPDATE, with the category still ``before``,
#   would otherwise land ``after`` on a name nobody classified. Null-safe
#   (`IS NOT DISTINCT FROM`), so a NULL name read must match a NULL name now, and a
#   name set since must not.
# * the observed PROVIDER IDENTITY — ``source`` and ``external_id``. The provider
#   gate in ``plan()`` judged the ticker it read, so the write is only covered by
#   that verdict while the identity is unchanged. An identity-only change between
#   ``_read()`` and its UPDATE (``KXRT-PRA`` → a ``KXNBA…`` ticker, category and
#   name intact) would otherwise land ``after`` on a row whose own provider now
#   names another league — Root's witness on #2169. Nothing at the database
#   boundary makes either column immutable (no migration adds a trigger on this
#   table), so the CAS states them rather than assuming no writer moves them.
#   Null-safe like the name: the model declares both NOT NULL, but ``plan()`` and
#   ``provider_category()`` accept None, and a NULL read must match a NULL now.
#   (``:source`` is the category the row moves FROM; the column ``source`` binds
#   as ``:provider``.)
_CAS_SQL = (
    "UPDATE futures_markets SET llm_sport_category = :target "
    "WHERE id = :id AND llm_sport_category = :source "
    "AND name IS NOT DISTINCT FROM :name "
    "AND source IS NOT DISTINCT FROM :provider "
    "AND external_id IS NOT DISTINCT FROM :external_id"
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
    stray = sorted(ids - set(PINNED) - set(REVERSED))
    if not ids:
        raise Refused("--ids is empty")
    if stray:
        raise Refused(f"--ids names ids that are neither pinned nor reversed: {stray}")
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
    mode = "restore" if restore_ids is not None else ("apply" if apply else "dry-run")
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
                    "provider": rows[market_id][2],
                    "external_id": rows[market_id][3],
                },
            )
            if result.rowcount != 1:
                raise Refused(
                    f"market {market_id}: expected to change 1 row, changed "
                    f"{result.rowcount} — its category, name or provider identity moved "
                    "since the read"
                )
            written += 1
        try:
            await session.commit()
        except Exception as exc:
            raise Unknown(_unknown_report(decided, mode, written, exc)) from exc
        except BaseException as exc:
            # A cancel or interrupt landing on the COMMIT is just as unknowable. It
            # keeps its own type and propagates; the report rides it to main().
            exc.commit_unknown = _unknown_report(decided, mode, written, exc)
            raise
    return {
        "mode": mode,
        "write": decided["write"],
        "skip": decided["skip"],
        "no_op": decided["no_op"],
        "reversed": decided["reversed"],
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

    readback = (
        f"heroku run:detached -a {os.environ['HEROKU_APP_NAME']} -- "
        "python3 scripts/repair_2169_misfiled_sport_category.py"
    )
    # After an unacknowledged COMMIT the session must leave ``get_task_session``
    # ABNORMALLY. A ``return`` inside the ``async with`` is a normal exit, and the
    # wrapper's normal exit runs ``await session.commit()`` again — a second COMMIT
    # after the one nobody heard back from. So the UNKNOWN report is printed and
    # the exception that carried it is re-raised out of the block; the wrapper's
    # exception path (rollback, close, dispose) is cleanup on a dead connection and
    # says nothing about the COMMIT. If that cleanup fails too, its failure must not
    # turn exit 3 into a traceback, nor a cancel into some other exception.
    unknown: dict | None = None
    carried: BaseException | None = None
    try:
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
                # A budget firing (lock_timeout 55P03, statement_timeout 57014) or
                # any other server refusal BEFORE the COMMIT was sent (``run`` turns
                # a failure at the COMMIT into ``Unknown``): the transaction rolls
                # back whole, so no row of the plan is committed, and the run says so.
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
            except BaseException as exc:
                # ``Unknown`` (a failure at the COMMIT), or a cancel/interrupt that
                # landed on it and carries the same report. Anything else is not ours.
                report = (
                    exc.report
                    if isinstance(exc, Unknown)
                    else getattr(exc, "commit_unknown", None)
                )
                if report is not None:
                    unknown, carried = dict(report, readback=readback), exc
                    print(json.dumps(unknown, indent=2))
                raise
    except BaseException as exc:
        if unknown is None:
            raise
        if exc is not carried:
            print(
                f"note: the session's cleanup after the UNKNOWN report raised "
                f"{type(exc).__name__}; it proves nothing about the COMMIT above",
                file=sys.stderr,
            )
        if isinstance(carried, Unknown):
            if not isinstance(exc, Exception):
                raise  # an interrupt during the cleanup keeps propagating as itself
            return 3
        if exc is carried:
            raise
        # A cancel or interrupt on the COMMIT keeps its own type even when the
        # cleanup raised something else on the way out.
        raise carried
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
