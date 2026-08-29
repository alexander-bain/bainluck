"""LAT-P123 — mutants for "the page scan and the count scan are the same scan".

WHAT THIS PROVES
----------------
`/api/futures/browse` used to answer one request with two statements over one
predicate:

    count_query = select(func.count(FuturesMarket.id)).where(*base_filters)
    query       = select(FuturesMarket).where(*base_filters).order_by(...).limit(...)

The `ORDER BY resolution_date` means the page query already reads every matching
row before it can take fifty. Measured on production 2026-08-29 via
`EXPLAIN (ANALYZE, BUFFERS)`: `category=politics` was **8,410 shared blocks in
each of the two statements**; the uncategorised call was **38,990 blocks twice**,
~305 MB, because the two negated `ILIKE`s are unindexable. `count(*) OVER ()`
rides the scan the sort was already paying for — one `WindowAgg` node, one scan,
both answers, and the SAME integer.

The fix is small and its two halves pull in opposite directions, which is what
makes it worth a battery:

* make it CHEAPER and you are one edit away from an approximate `total`;
* keep it EXACT and you are one edit away from the second scan coming back.

Both counts are RENDERED — `(6,611)` beside the category header and
`Load more (N remaining)` on the button (`CategoryBrowser.tsx:179,229`). So a
mutant that trades precision for speed ships a FORMATTING lie as a latency win,
and would read as a success in every timing chart. Half the mutants below do
exactly that, on purpose.

WHY IN-MEMORY, WITH NO FILE WRITES AT ALL
-----------------------------------------
`scripts/evals/_mutation_guard.py` records how a harness that mutates real files
left a mutant on disk when its window took exit 143. This one writes NOTHING:
each mutant is a source STRING, `exec`'d into a throwaway module namespace, and
the route coroutine is called directly against a mock session. There is no
backup to restore, so a SIGKILL can leave no residue.

THE CONTROL RUNS FIRST, AND THE DENOMINATOR IS PRINTED BEFORE THE FIRST VERDICT
------------------------------------------------------------------------------
Every oracle runs against UNMUTATED source before any mutant. A kill count with
no passing control is not a measurement — an oracle that fails for all input
scores 100% while being blind (`duration_sample_window_mutations.py`'s M10).

FAILING TO APPLY IS NOT A KILL
------------------------------
A mutant whose substitution matched nothing never changed the code, so the
oracle's red is about nothing at all. Those are reported separately and are
just as fatal to the run as a survivor.

Run: ``python3 backend/scripts/evals/browse_single_scan_mutations.py``
Exits non-zero if any mutant SURVIVES **or** fails to APPLY **or** the control
fails.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock
from types import ModuleType, SimpleNamespace

#: Read by `scan_mutation_residue.py` (its `DISK_FREE` set). Every mutant here
#: is a string; no tracked file, no temp file, no backup, no residue.
MUTATES_WORKING_TREE = False

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
ROUTE = BACKEND / "app/routes/futures.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# The subject, read from the real file rather than re-typed, so a mutant can
# never be killed by a copy that has drifted from what ships.
# ---------------------------------------------------------------------------

SOURCE = ROUTE.read_text(encoding="utf-8")


def _load(source: str) -> ModuleType:
    """Exec a variant of `routes/futures.py` into a throwaway module."""
    module = ModuleType("_browse_mutant")
    module.__file__ = str(ROUTE)
    code = compile(source, str(ROUTE), "exec")
    exec(code, module.__dict__)  # noqa: S102 — the whole point of the harness
    return module


# ---------------------------------------------------------------------------
# Fakes. `browse_futures` is called directly, so the `Query(...)` defaults are
# never involved — every argument is passed explicitly.
# ---------------------------------------------------------------------------


def _market(market_id: int):
    return SimpleNamespace(
        id=market_id,
        name=f"Market {market_id}",
        llm_sport_category="politics",
        source="kalshi",
        resolution_date=None,
        outcomes=[],
    )


def _page_result(markets, total):
    result = MagicMock()
    result.unique.return_value.all.return_value = [(m, total) for m in markets]
    # A mutant that drops `list(...)` reaches for these instead; leaving them
    # unstubbed is what lets the empty-page mutant be distinguishable.
    result.all.return_value = [(m, total) for m in markets]
    result.scalars.return_value.unique.return_value.all.return_value = markets
    return result


def _count_result(total):
    result = MagicMock()
    result.scalar.return_value = total
    return result


def _db(results):
    session = AsyncMock()
    session.execute.side_effect = list(results)
    return session


def _call(module, db, **kwargs):
    params = {"category": None, "q": None, "limit": 50, "offset": 0}
    params.update(kwargs)
    return asyncio.run(module.browse_futures(db=db, **params))


def _sql(db, index):
    return str(db.execute.call_args_list[index].args[0].compile()).lower()


# ---------------------------------------------------------------------------
# The oracles. Each returns None when satisfied, or a string saying what broke.
# ---------------------------------------------------------------------------


def o_one_statement_on_a_full_page(module):
    db = _db([_page_result([_market(i) for i in range(50)], 6611)])
    _call(module, db, category="politics", limit=50)
    if db.execute.call_count != 1:
        return f"issued {db.execute.call_count} statements for one page, expected 1"
    return None


def o_the_statement_carries_an_unpartitioned_count_window(module):
    db = _db([_page_result([_market(1)], 6611)])
    _call(module, db, category="politics")
    sql = _sql(db, 0)
    if "count(*) over ()" not in sql:
        return "the page statement has no `count(*) over ()`"
    if "partition by" in sql:
        return "the window is partitioned — `total` would be a per-group count"
    return None


def o_total_is_the_population_not_the_page(module):
    db = _db([_page_result([_market(i) for i in range(50)], 6611)])
    body = _call(module, db, category="politics", limit=50)
    if body["total"] != 6611:
        return f"total={body['total']!r}, expected the population 6611"
    if len(body["items"]) != 50:
        return f"returned {len(body['items'])} items, expected the 50-row page"
    return None


def o_has_more_is_exact_at_the_boundary(module):
    db = _db([_page_result([_market(1)], 12)])
    at = _call(module, db, limit=6, offset=6)
    if at["has_more"] is not False:
        return "has_more is True at offset+limit == total (an empty next page)"
    db = _db([_page_result([_market(1)], 12)])
    below = _call(module, db, limit=5, offset=5)
    if below["has_more"] is not True:
        return "has_more is False one page below the boundary (items unreachable)"
    return None


def o_empty_first_page_costs_one_statement(module):
    db = _db([_page_result([], 0)])
    body = _call(module, db, category="politics")
    if db.execute.call_count != 1:
        return (
            f"an empty first page cost {db.execute.call_count} statements — the "
            "second scan is back on the commonest cold path"
        )
    if body["total"] != 0 or body["items"] != [] or body["has_more"] is not False:
        return f"empty first page reported {body['total']!r}/{body['has_more']!r}"
    return None


def o_empty_past_the_end_still_reports_the_population(module):
    db = _db([_page_result([], 0), _count_result(6611)])
    body = _call(module, db, category="politics", offset=9000)
    if body["total"] != 6611:
        return (
            f"total={body['total']!r} past the end — a reader is told the category "
            "is empty when it holds 6,611 markets"
        )
    return None


def o_the_fallback_selects_the_same_population(module):
    db = _db([_page_result([], 0), _count_result(3)])
    _call(module, db, category="politics", q="Senate", offset=9000)
    if db.execute.call_count != 2:
        return f"fallback issued {db.execute.call_count} statements, expected 2"
    params = db.execute.call_args_list[1].args[0].compile().params.values()
    if "politics" not in params or "%Senate%" not in params:
        return "the fallback count drops a filter — it counts a different population"
    return None


def o_the_envelope_does_not_leak_the_window_column(module):
    db = _db([_page_result([_market(1)], 7)])
    body = _call(module, db)
    expected = {"items", "total", "limit", "offset", "has_more"}
    if set(body) != expected:
        return f"response keys {sorted(body)} != {sorted(expected)}"
    if "browse_total" in body["items"][0]:
        return "the window column leaked into an item"
    return None


def o_an_unstubbed_empty_result_is_still_falsy(module):
    """M10's oracle, and it exists because M10 SURVIVED the first battery run.

    `_page_result` above hands back a real list, so dropping `list(...)` from
    the route changed nothing and every oracle stayed green. That was the
    harness being blind, not the mutant being harmless: the repo's shared
    fixture (`tests/integration/conftest.py::_make_mock_result`) does NOT stub
    `.unique()`, so `result.unique().all()` is an auto-`MagicMock` — TRUTHY,
    and subscriptable into more MagicMocks. Without `list(...)` the empty-DB
    path takes the `if rows:` branch and `int(rows[0][1])` raises, which is a
    500 on every route that has no data yet.

    So this oracle reproduces the SHARED FIXTURE's shape rather than a
    convenient one. `list(MagicMock())` is `[]` because MagicMock's `__iter__`
    defaults to empty — that is precisely the property being relied on.
    """
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None
    result.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = result

    try:
        body = _call(module, session)
    except Exception as exc:  # noqa: BLE001
        return f"an empty unstubbed result raised {type(exc).__name__}: {exc}"
    if body["items"] != [] or body["total"] != 0:
        return f"empty unstubbed result produced items={body['items']!r} total={body['total']!r}"
    return None


def o_the_page_keeps_a_deterministic_order(module):
    """M13's oracle, and it also exists because M13 SURVIVED.

    Dropping the `ORDER BY` does not make this faster — the window still reads
    every matching row — it makes pagination NON-DETERMINISTIC. Postgres is
    free to return a different row order per statement, so "Load more" would
    repeat some markets and skip others while `total` stays reassuringly exact.
    A latency harness that cannot see that is checking the wrong half.
    """
    db = _db([_page_result([_market(1)], 6611)])
    _call(module, db, category="politics")
    sql = _sql(db, 0)
    if "order by futures_markets.resolution_date asc nulls last" not in sql:
        return "the page statement lost its ORDER BY — pagination repeats and skips rows"
    return None


ORACLES = [
    ("one statement on a full page", o_one_statement_on_a_full_page),
    ("unstubbed empty result falsy", o_an_unstubbed_empty_result_is_still_falsy),
    ("page order is deterministic", o_the_page_keeps_a_deterministic_order),
    ("unpartitioned count window", o_the_statement_carries_an_unpartitioned_count_window),
    ("total is the population", o_total_is_the_population_not_the_page),
    ("has_more exact at boundary", o_has_more_is_exact_at_the_boundary),
    ("empty first page costs one", o_empty_first_page_costs_one_statement),
    ("empty past end keeps total", o_empty_past_the_end_still_reports_the_population),
    ("fallback same population", o_the_fallback_selects_the_same_population),
    ("envelope has no window column", o_the_envelope_does_not_leak_the_window_column),
]


# ---------------------------------------------------------------------------
# The mutants. `old` must appear EXACTLY ONCE in the source, or the mutant is
# reported as FAILED TO APPLY rather than silently skipped.
# ---------------------------------------------------------------------------

WINDOW_CALL = 'select(FuturesMarket, func.count().over().label("browse_total"))'
ROWS_LINE = "    rows = list((await db.execute(query)).unique().all())"
TOTAL_BLOCK = """    if rows:
        total = int(rows[0][1])"""

MUTANTS = [
    # --- the defect, restored ------------------------------------------------
    (
        "M1 the separate COUNT comes back before the page query",
        WINDOW_CALL,
        "select(FuturesMarket, func.count().over().label(\"browse_total\"))\n"
        "        .where(*base_filters)\n"
        "    )\n"
        "    _ = (await db.execute(select(func.count(FuturesMarket.id)).where(*base_filters))).scalar()\n"
        "    query = (\n"
        "        select(FuturesMarket, func.count().over().label(\"browse_total\"))",
    ),
    (
        "M2 total is the page size, not the population",
        TOTAL_BLOCK,
        "    if rows:\n        total = len(rows)",
    ),
    (
        "M3 the window is partitioned by category",
        "func.count().over()",
        "func.count().over(partition_by=FuturesMarket.llm_sport_category)",
    ),
    (
        "M4 the window is dropped and total is hardcoded",
        TOTAL_BLOCK,
        "    if rows:\n        total = 0",
    ),
    (
        "M5 has_more is off by one at the boundary",
        '"has_more": (offset + limit) < total,',
        '"has_more": (offset + limit) <= total,',
    ),
    (
        "M6 has_more guesses from the page fill instead of the count",
        '"has_more": (offset + limit) < total,',
        '"has_more": len(items) == limit,',
    ),
    # --- the precision-for-speed trades -------------------------------------
    (
        "M7 past the end reports zero instead of counting",
        "    elif offset:",
        "    elif False:",
    ),
    (
        "M8 the fallback count drops the caller's filters",
        "        count_query = select(func.count(FuturesMarket.id)).where(*base_filters)",
        "        count_query = select(func.count(FuturesMarket.id))",
    ),
    (
        "M9 an empty first page pays for a count anyway",
        "    else:\n        # Offset 0 and no rows: the population really is empty. No query needed.\n        total = 0",
        "    else:\n        total = (await db.execute(\n"
        "            select(func.count(FuturesMarket.id)).where(*base_filters)\n"
        "        )).scalar() or 0",
    ),
    # --- the shape traps -----------------------------------------------------
    (
        "M10 the result is not materialised, so an empty page is truthy",
        ROWS_LINE,
        "    rows = (await db.execute(query)).unique().all()",
    ),
    (
        # `"outcome_count": len(real_outcomes),` alone appears three times in
        # this file. The battery reported the ambiguity as NOT APPLIED rather
        # than mutating an arbitrary one of them — which is the whole reason
        # "failed to apply" is a separate, fatal outcome and not a skip.
        "M11 the window column leaks into the item projection",
        '            "outcome_count": len(real_outcomes),\n'
        "        })\n"
        "\n"
        "    return {\n"
        '        "items": items,',
        '            "outcome_count": len(real_outcomes),\n'
        '            "browse_total": total,\n'
        "        })\n"
        "\n"
        "    return {\n"
        '        "items": items,',
    ),
    (
        "M12 the window value is read from the wrong tuple slot",
        "        total = int(rows[0][1])",
        "        total = int(rows[0][0].id)",
    ),
    (
        "M13 the page loses its ordering, so the window sees a different page",
        "        .order_by(FuturesMarket.resolution_date.asc().nulls_last())\n"
        "        .limit(limit)\n"
        "        .offset(offset)\n"
        "    )\n"
        "    # `list()` and not a bare Result",
        "        .limit(limit)\n"
        "        .offset(offset)\n"
        "    )\n"
        "    # `list()` and not a bare Result",
    ),
]


def _apply(mutant_old: str, mutant_new: str):
    occurrences = SOURCE.count(mutant_old)
    if occurrences != 1:
        return None, f"anchor matched {occurrences} times, expected exactly 1"
    return SOURCE.replace(mutant_old, mutant_new), None


def run() -> int:
    print("browse_single_scan_mutations — LAT-P123")
    print(f"subject : {ROUTE.relative_to(REPO)}")
    print(f"oracles : {len(ORACLES)}")
    print(f"MUTANTS : {len(MUTANTS)}   <- denominator, printed before the first verdict")
    print()

    print("CONTROL (unmutated source must satisfy every oracle)")
    control = _load(SOURCE)
    control_failures = []
    for name, oracle in ORACLES:
        try:
            problem = oracle(control)
        except Exception as exc:  # noqa: BLE001 — a raising oracle is a broken oracle
            problem = f"raised {type(exc).__name__}: {exc}"
        status = "ok" if problem is None else f"FAIL — {problem}"
        print(f"  {name:<34} {status}")
        if problem is not None:
            control_failures.append(name)
    if control_failures:
        print()
        print(f"🔴 CONTROL FAILED on {len(control_failures)} oracle(s). No kill count is")
        print("   meaningful until the control is green — an oracle that fails for every")
        print("   input scores 100% while being blind.")
        return 1
    print("  CONTROL GREEN")
    print()

    killed, survived, not_applied = [], [], []
    print("MUTANTS")
    for label, old, new in MUTANTS:
        source, apply_error = _apply(old, new)
        if source is None:
            print(f"  {label}\n      ⚠️  NOT APPLIED — {apply_error}")
            not_applied.append(label)
            continue

        try:
            module = _load(source)
        except Exception as exc:  # noqa: BLE001
            print(f"  {label}\n      killed at import — {type(exc).__name__}: {exc}")
            killed.append(label)
            continue

        reasons = []
        for name, oracle in ORACLES:
            try:
                problem = oracle(module)
            except Exception as exc:  # noqa: BLE001
                problem = f"raised {type(exc).__name__}: {exc}"
            if problem is not None:
                reasons.append(f"{name}: {problem}")

        if reasons:
            print(f"  {label}\n      killed by {len(reasons)} oracle(s) — {reasons[0]}")
            killed.append(label)
        else:
            print(f"  {label}\n      🔴 SURVIVED — every oracle stayed green")
            survived.append(label)

    print()
    print(f"RESULT: {len(killed)}/{len(MUTANTS)} killed, "
          f"{len(survived)} survived, {len(not_applied)} not applied")
    if survived:
        print("🔴 SURVIVORS:")
        for label in survived:
            print(f"   - {label}")
    if not_applied:
        print("🔴 NOT APPLIED (a mutant that changed nothing proves nothing):")
        for label in not_applied:
            print(f"   - {label}")

    if ROUTE.read_text(encoding="utf-8") != SOURCE:
        print("🔴 THE WORKING TREE MOVED during this run — refusing to report success.")
        return 1

    return 1 if (survived or not_applied) else 0


if __name__ == "__main__":
    sys.exit(run())
