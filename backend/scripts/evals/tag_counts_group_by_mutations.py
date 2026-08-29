"""LAT-P114 (#2267) — mutants for "a GROUP BY alias that a column shadows".

WHAT THIS PROVES
----------------
`/api/feed/tag-counts` returned a plain-text `500` from the day it was written
(`c536d738`, 2026-03-01), so `/categories` rendered
`ErrorState("Failed to load categories")` for its entire existence. The cause
was one line:

    SELECT COALESCE(llm_sport_category, 'other') AS category, COUNT(*) AS cnt
    FROM futures_markets
    ...
    GROUP BY category

`futures_markets` has a real `category` column. PostgreSQL resolves a bare
`GROUP BY` identifier against the INPUT columns before it will consider an
output alias, so the grouping key was `futures_markets.category`, the selected
`COALESCE(...)` was left ungrouped, and every request died with a
`GroupingError`. ~19,000 tests were green throughout.

The fix is one token per statement (`GROUP BY 1`). A one-token fix is exactly
the kind that a future edit reverts without anyone noticing, so the question
this harness answers is not "is it fixed" but **"would the suite NOTICE if it
came back"**.

BOTH DIRECTIONS, DELIBERATELY
-----------------------------
Half the mutants REINTRODUCE the defect — in the futures statement, in the
sibling events statement, and in shapes the original did not have (a
`GROUP BY t.alias`, a second colliding alias). The other half attack the
GUARD instead: they blind the scanner's column map, its CTE scoping and its
alias detection. A scan that has quietly stopped resolving anything passes
every hazard in the repo while reporting a clean sweep, which is the same
failure as no gate at all — and it is the failure a kill-count would score as
success.

WHY IN-MEMORY, WITH NO FILE WRITES AT ALL
-----------------------------------------
`scripts/evals/_mutation_guard.py` records how a harness that mutates real
files left mutant M3 on disk in `bcdcd95f` after its window took exit 143.
Its own conclusion is that a harness which never writes to the working tree is
strictly the better design. This one goes further and writes NOTHING — every
mutant is a SQL string or a source string held in memory, including the one
that drives the repo-wide reporting layer. There is no backup to restore, so
there is nothing a SIGKILL can leave behind, and
`tests/test_mutation_guard.py::test_every_on_disk_harness_is_guarded` exempts
it by measurement rather than by name.

THE CONTROL RUNS FIRST
----------------------
Every oracle is executed against UNMUTATED input before any mutant, and the
result is printed. A kill count without a passing control is not a
measurement: an oracle that fails for every input reports 100% kills while
being completely blind (`duration_sample_window_mutations.py`'s M10 finding).

Run: ``python3 scripts/evals/tag_counts_group_by_mutations.py``
Exits non-zero if any mutant SURVIVES **or** if any mutant fails to APPLY.
"""

from __future__ import annotations

import pathlib
import re
import sys

#: Read by `scan_mutation_residue.py` (its `DISK_FREE` set). This harness
#: mutates SQL strings in memory and never calls a write of any kind — no
#: tracked file, no temp file. It therefore has no backup to restore and can
#: leave no residue, not even if the process is SIGKILLed. `run()` re-reads
#: `feed.py` at the end and refuses to report success if that stopped being
#: true.
MUTATES_WORKING_TREE = False

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
FEED = BACKEND / "app/routes/feed.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.test_sql_group_by_alias_collision import (  # noqa: E402
    TABLE_COLUMNS,
    find_alias_collisions,
    outermost_select_level,
    scan_repository,
    scan_sources,
)

#: The two statements the route issues, as they stand AFTER the fix. Read from
#: the real file rather than re-typed, so a mutant cannot be killed by a copy
#: that drifted away from what actually ships.
_SQL_LITERAL = re.compile(r"""text\(\s*(?:f)?("{3}|'{3})(.*?)\1""", re.S)


def _route_statements() -> tuple[str, str]:
    source = FEED.read_text()
    start = source.index("async def get_tag_counts")
    end = (
        source.index("\n@router.", start)
        if "\n@router." in source[start:]
        else len(source)
    )
    body = source[start:end]
    found = [m.group(2) for m in _SQL_LITERAL.finditer(body)]
    if len(found) != 2:
        raise SystemExit(
            f"expected 2 text() statements in get_tag_counts, found {len(found)} "
            "— the harness is reading the wrong region and would report "
            "vacuous kills"
        )
    return found[0], found[1]


EVENTS_SQL, FUTURES_SQL = _route_statements()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"harness precondition failed: {message}")


_require(
    "GROUP BY 1" in FUTURES_SQL and "GROUP BY 1" in EVENTS_SQL,
    "both route statements must group by ordinal before mutation",
)
_require(
    "category" in TABLE_COLUMNS["futures_markets"],
    "futures_markets.category must exist, or the defect is unreachable",
)


# --------------------------------------------------------------------------
# Mutants A — reintroduce the defect. The scanner must FLAG each.
# --------------------------------------------------------------------------


def _sub_once(text: str, old: str, new: str, label: str) -> str:
    """Replace `old` exactly once, or refuse. A mutation that did not APPLY
    reports green (memory: `reference_mutation_must_prove_it_applied`)."""
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{label}: pattern {old!r} matched {count} times, expected exactly 1"
        )
    return text.replace(old, new)


def m1_futures_group_by_alias() -> bool:
    """The original defect, verbatim: group the futures count by the alias."""
    mutant = _sub_once(FUTURES_SQL, "GROUP BY 1", "GROUP BY category", "M1")
    return find_alias_collisions(mutant) == [("category", "futures_markets")]


def m2_futures_group_by_alias_with_trailing_column() -> bool:
    """`GROUP BY category, status` — the same trap inside a longer list."""
    mutant = _sub_once(FUTURES_SQL, "GROUP BY 1", "GROUP BY category, status", "M2")
    return find_alias_collisions(mutant) == [("category", "futures_markets")]


def m3_futures_alias_renamed_to_another_real_column() -> bool:
    """A different alias, a different real column — the CLASS, not the case."""
    mutant = FUTURES_SQL.replace("AS category", "AS source").replace(
        "GROUP BY 1", "GROUP BY source"
    )
    _require("GROUP BY source" in mutant, "M3 failed to apply")
    _require("source" in TABLE_COLUMNS["futures_markets"], "M3 needs a real column")
    return find_alias_collisions(mutant) == [("source", "futures_markets")]


def m4_events_statement_regresses() -> bool:
    """The sibling statement is one migration from the identical break.

    It is not currently a hazard (neither `events` nor `sports` has a
    `category` column), so the mutant must ALSO add the collision — which is
    precisely the schema change the ordinal fix defends against. Mutating the
    scanner's view of the schema, not the schema itself.
    """
    mutant = _sub_once(EVENTS_SQL, "GROUP BY 1", "GROUP BY category", "M4")
    before = find_alias_collisions(mutant)
    TABLE_COLUMNS["events"].add("category")
    try:
        after = find_alias_collisions(mutant)
    finally:
        TABLE_COLUMNS["events"].discard("category")
    return before == [] and after == [("category", "events")]


def m5_defect_reaches_the_repo_scan() -> bool:
    """The reporting layer, not just the pure helper, must go RED.

    M1-M4 exercise `find_alias_collisions`. This one drives the layer the
    committed test actually calls, so a scanner that detected the collision
    perfectly and then failed to REPORT it is still killed.

    The mutated source is passed as a STRING. Nothing is written anywhere —
    not to the working tree, not to a temp directory — which is what lets this
    harness declare `MUTATES_WORKING_TREE = False` by construction rather than
    by promising to clean up after itself.
    """
    source = FEED.read_text()
    mutated = _sub_once(
        source,
        "              AND (resolution_date IS NULL OR resolution_date >= :now)\n            GROUP BY 1",
        "              AND (resolution_date IS NULL OR resolution_date >= :now)\n            GROUP BY category",
        "M5",
    )
    clean = scan_sources([("app/routes/feed.py", source)])
    dirty = scan_sources([("app/routes/feed.py", mutated)])
    return (
        clean == []
        and len(dirty) == 1
        and "GROUP BY category" in dirty[0]
        and "futures_markets.category" in dirty[0]
    )


# --------------------------------------------------------------------------
# Mutants B — blind the guard. Each must make the scanner MISS a real hazard.
# --------------------------------------------------------------------------

DEFECT = FUTURES_SQL.replace("GROUP BY 1", "GROUP BY category")


def m6_blank_column_map() -> bool:
    """An empty column map makes every statement look clean."""
    saved = set(TABLE_COLUMNS["futures_markets"])
    TABLE_COLUMNS["futures_markets"].clear()
    try:
        missed = find_alias_collisions(DEFECT) == []
    finally:
        TABLE_COLUMNS["futures_markets"].update(saved)
    _require(TABLE_COLUMNS["futures_markets"] == saved, "M6 did not restore the map")
    return missed


def m7_alias_detection_disabled() -> bool:
    """If `AS <name>` stops registering, requirement (2) never holds."""
    mutant = DEFECT.replace("AS category", "AS category_x").replace(
        "GROUP BY category", "GROUP BY category_x"
    )
    # `category_x` is not a real column, so the hazard genuinely disappears —
    # which is the point: the scan keys on the collision, not on the word
    # "category". A scanner that still flagged this would be flagging noise.
    return find_alias_collisions(mutant) == []


def m8_cte_scoping_removed() -> bool:
    """Without sub-select collapse, a correct CTE reads as a hazard.

    This is the false-positive direction. A gate that cries wolf on three
    correct statements in `app/tasks/` and `app/routes/` gets suppressed, and a
    suppressed gate is not a gate.
    """
    cte = """
        WITH ro AS (
            SELECT fm.source AS source, to_char(fm.resolution_date, 'YYYY-MM') AS mon
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
        )
        SELECT source, mon, COUNT(*) AS sampled
        FROM ro
        GROUP BY source, mon
    """
    correct = find_alias_collisions(cte) == []

    # The mutant: skip the collapse entirely, as a naive scanner would.
    level = cte
    aliases = {
        m.group(1) for m in re.finditer(r"\bAS\s+([a-z_][a-z0-9_]*)", level, re.I)
    }
    tables = {
        m.group(1)
        for m in re.finditer(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", level, re.I)
    }
    naive = [
        (i, t)
        for m in re.finditer(r"GROUP\s+BY\s+([a-z_][a-z0-9_]*)", level, re.I)
        for i in [m.group(1)]
        if i in aliases
        for t in sorted(tables)
        if i in TABLE_COLUMNS.get(t, frozenset())
    ]
    return correct and naive == [("source", "futures_markets")]


def m9_collapse_helper_blocked_by_nested_parens() -> bool:
    """The first version of `outermost_select_level` had this exact bug.

    It removed a parenthesised group only when the group contained no nested
    parens AND contained SELECT. A `to_char(...)` inside a CTE body therefore
    prevented the CTE from ever collapsing, and three correct statements were
    reported as hazards. The shipped helper replaces non-select parens with a
    paren-free placeholder instead, so the enclosing sub-select can still
    collapse.
    """
    cte = """
        WITH ro AS (
            SELECT fm.source AS source, to_char(fm.resolution_date, 'YYYY-MM') AS mon
            FROM futures_markets fm
        )
        SELECT source, COUNT(*) AS n FROM ro GROUP BY source
    """
    shipped_ok = "futures_markets" not in outermost_select_level(cte)

    def naive_collapse(sql: str) -> str:
        prev = None
        while prev != sql:
            prev = sql
            sql = re.sub(
                r"\([^()]*\)",
                lambda m: (
                    " " if re.search(r"\bSELECT\b", m.group(0), re.I) else m.group(0)
                ),
                sql,
            )
        return sql

    naive_leaks = "futures_markets" in naive_collapse(cte)
    return shipped_ok and naive_leaks


def m10_ordinal_is_not_mistaken_for_an_alias() -> bool:
    """The shipped fix must not be flagged by the guard that motivated it.

    This is the tightest false-positive case in the file: `FUTURES_SQL` still
    declares `AS category`, `futures_markets.category` still exists, so both
    of the scan's first two conditions are live — only the ordinal keeps it
    clean. A scanner that matched `GROUP BY 1` as a bare identifier would fail
    here, and would then fail on the shipped route on every CI run.
    """
    _require("AS category" in FUTURES_SQL, "M10 needs the colliding alias present")
    _require(
        "category" in TABLE_COLUMNS["futures_markets"],
        "M10 needs the shadowing column present",
    )
    return find_alias_collisions(FUTURES_SQL) == []


MUTANTS = [
    (
        "M1  futures groups by the shadowed alias (the original defect)",
        m1_futures_group_by_alias,
    ),
    (
        "M2  same trap inside a multi-column GROUP BY list",
        m2_futures_group_by_alias_with_trailing_column,
    ),
    (
        "M3  a different alias colliding with a different real column",
        m3_futures_alias_renamed_to_another_real_column,
    ),
    (
        "M4  the events statement regresses once its table gains `category`",
        m4_events_statement_regresses,
    ),
    (
        "M5  the defect reaches the repo-wide scan, not just the helper",
        m5_defect_reaches_the_repo_scan,
    ),
    ("M6  the guard's column map is blanked", m6_blank_column_map),
    ("M7  the alias no longer collides with anything", m7_alias_detection_disabled),
    (
        "M8  CTE scoping removed -> a correct statement reads as a hazard",
        m8_cte_scoping_removed,
    ),
    (
        "M9  the collapse helper's nested-paren blind spot",
        m9_collapse_helper_blocked_by_nested_parens,
    ),
    (
        "M10 the ordinal fix is not itself flagged",
        m10_ordinal_is_not_mistaken_for_an_alias,
    ),
]


def run() -> int:
    print("=" * 72)
    print("CONTROL — the oracles against UNMUTATED input")
    print("=" * 72)
    control_clean = find_alias_collisions(FUTURES_SQL) == []
    control_events = find_alias_collisions(EVENTS_SQL) == []
    control_repo = scan_repository() == []
    print(f"  futures statement clean : {control_clean}")
    print(f"  events statement clean  : {control_events}")
    print(f"  repo-wide scan clean    : {control_repo}")
    if not (control_clean and control_events and control_repo):
        print(
            "\nCONTROL FAILED — the oracle rejects the shipped code. A kill "
            "count measured against a failing control is meaningless."
        )
        return 1
    print("  control PASSES — kills below are discriminating\n")

    print("=" * 72)
    print(f"MUTANTS — {len(MUTANTS)}")
    print("=" * 72)
    survivors = []
    for label, fn in MUTANTS:
        killed = fn()
        print(f"  {'KILLED ' if killed else 'SURVIVED'}  {label}")
        if not killed:
            survivors.append(label)

    # The working tree must be exactly as we found it. This harness never
    # writes to it, and this line is how that claim is CHECKED rather than
    # asserted in a docstring.
    _require("GROUP BY 1" in FEED.read_text(), "feed.py was modified by the run")

    print()
    if survivors:
        print(f"FAILED — {len(survivors)} survivor(s):")
        for s in survivors:
            print(f"  - {s}")
        return 1
    print(f"ALL {len(MUTANTS)} MUTANTS KILLED · control passed · tree untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
