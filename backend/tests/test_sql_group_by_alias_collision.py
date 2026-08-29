"""`GROUP BY <alias>` is a trap whenever a real column shares the alias's name.

## The defect this file exists to catch

`/api/feed/tag-counts` returned Starlette's plain-text `500` — and therefore
`/categories` rendered `ErrorState("Failed to load categories")` — from the day
the route was written (`c536d738`, 2026-03-01) until LAT-P114. The statement
read:

    SELECT COALESCE(llm_sport_category, 'other') AS category, COUNT(*) AS cnt
    FROM futures_markets
    WHERE ...
    GROUP BY category

which looks like it groups by the alias. It does not. **In PostgreSQL a
`GROUP BY` item that is a bare identifier is resolved against the INPUT columns
first, and only falls back to an output alias when no input column matches.**
`futures_markets` has a real `category` column sitting immediately beside
`llm_sport_category` in `models.py`, so the grouping key was
`futures_markets.category` and the selected expression was left ungrouped:

    GroupingError: column "futures_markets.llm_sport_category" must appear in
    the GROUP BY clause or be used in an aggregate function

The failure is total, permanent and silent to every test that does not execute
the statement against a real PostgreSQL. It is also invisible to the eye: the
statement is valid SQL, it names only real identifiers, and the alias it appears
to use is right there on the line above.

## why this guard is static, and what it does NOT replace

`tests/integration/test_tag_counts_real_postgres.py` executes this route's own
statements against a real server, which is the authoritative check — PostgreSQL
is the thing that decides the ambiguity. But that gate only runs in the
`search-recall` CI job, and it only covers the one route it drives.

This file is the cheap, repo-wide half: it runs in the ordinary suite with no
database at all, and it covers every `text()` statement in `app/`. The two are
complementary — an oracle for one route, and a net for the class.

## the predicate, stated exactly

A statement is a hazard when ALL THREE hold at the SAME select level:

1. it groups by a bare identifier (`GROUP BY foo`, not `GROUP BY t.foo`,
   `GROUP BY 1`, or `GROUP BY <expression>`);
2. that identifier is introduced as an output alias (`... AS foo`);
3. that identifier is also a real column on some table in that level's
   `FROM`/`JOIN`.

All three matter. Dropping (2) flags the overwhelmingly common and correct
`SELECT source, COUNT(*) ... GROUP BY source`. Dropping (3) flags every aliased
grouping key in the repo. Dropping the same-level requirement flags CTEs, where
the alias belongs to the CTE's output and the base table is not in scope at all
— three such statements exist in `app/tasks/precompute_backfill_progress.py`
and `app/routes/admin_data_quality.py`, and all three are correct.
"""

from __future__ import annotations

import pathlib
import re

from app.models.models import Base

APP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"

#: Every table the ORM knows, mapped to its real column names. Read from
#: metadata rather than re-spelled here, so a column added tomorrow is covered
#: without anyone remembering this file exists.
TABLE_COLUMNS: dict[str, set[str]] = {
    table.name: {column.name for column in table.columns}
    for table in Base.metadata.tables.values()
}

#: `text("""...""")` / `text('''...''')`, including f-string forms.
_SQL_LITERAL = re.compile(r"""text\(\s*(?:f)?("{3}|'{3})(.*?)\1""", re.S)

_INNERMOST_PARENS = re.compile(r"\([^()]*\)")
_GROUP_BY_BARE = re.compile(r"GROUP\s+BY\s+([a-z_][a-z0-9_]*)", re.I)
_OUTPUT_ALIAS = re.compile(r"\bAS\s+([a-z_][a-z0-9_]*)", re.I)
_FROM_OR_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.I)


def outermost_select_level(sql: str) -> str:
    """Collapse every parenthesised group, leaving only the outermost query.

    Sub-selects (CTE bodies, scalar sub-queries, derived tables) are erased
    entirely: their aliases and their base tables belong to a different scope,
    and treating them as though they were in scope is what made a first pass at
    this scan report three false positives.

    Parenthesised groups that are NOT sub-selects — `COUNT(*)`,
    `to_char(x, 'YYYY-MM')`, `FILTER (WHERE ...)` — are replaced by a
    paren-free placeholder rather than removed. They must not survive (a
    `FILTER (WHERE ...)` clause would leak stray identifiers into the scan) but
    they also must not block the collapse of the sub-select that encloses them,
    which is precisely the bug the first version of this helper had.
    """
    while True:
        match = _INNERMOST_PARENS.search(sql)
        if match is None:
            return sql
        body = match.group(0)
        replacement = " " if re.search(r"\bSELECT\b", body, re.I) else " __expr__ "
        sql = sql[: match.start()] + replacement + sql[match.end() :]


def find_alias_collisions(sql: str) -> list[tuple[str, str]]:
    """Return `(identifier, table)` pairs where a GROUP BY alias is shadowed."""
    level = outermost_select_level(sql)
    aliases = {m.group(1) for m in _OUTPUT_ALIAS.finditer(level)}
    tables = {m.group(1) for m in _FROM_OR_JOIN.finditer(level)}

    collisions: list[tuple[str, str]] = []
    for group_by in _GROUP_BY_BARE.finditer(level):
        identifier = group_by.group(1)
        if identifier not in aliases:
            # A bare grouping key that is a plain input column. Correct, and by
            # far the most common shape in this repo.
            continue
        for table in sorted(tables):
            if identifier in TABLE_COLUMNS.get(table, frozenset()):
                collisions.append((identifier, table))
    return collisions


def iter_sources(root: pathlib.Path | None = None):
    """Yield `(display_path, source)` for every Python file under `root`."""
    root = root or APP_ROOT
    for path in sorted(root.rglob("*.py")):
        yield str(path.relative_to(root.parent)), path.read_text()


def scan_sources(items) -> list[str]:
    """Every hazard in `(display_path, source)` pairs, as `path:line` findings.

    Split from `scan_repository` so the mutation battery can feed it a mutated
    source STRING. A harness that writes real files is what left mutant M3 on
    disk in `bcdcd95f`; `scripts/evals/_mutation_guard.py` carries that story,
    and its conclusion is that a harness which never writes anywhere is
    strictly the better design. This split is what lets this one be that.
    """
    findings: list[str] = []
    for display, source in items:
        for literal in _SQL_LITERAL.finditer(source):
            line = source[: literal.start()].count("\n") + 1
            for identifier, table in find_alias_collisions(literal.group(2)):
                findings.append(
                    f"{display}:{line} — GROUP BY {identifier} resolves to "
                    f"{table}.{identifier} (a real column), not the "
                    f"'AS {identifier}' output alias it appears to name"
                )
    return findings


def scan_repository(root: pathlib.Path | None = None) -> list[str]:
    """Every hazard under `root` (default `app/`)."""
    return scan_sources(iter_sources(root))


def test_no_group_by_resolves_to_a_shadowed_alias():
    """No `text()` statement in `app/` groups by a shadowed output alias."""
    findings = scan_repository()
    assert not findings, (
        "GROUP BY names an output alias that a real column shadows. PostgreSQL "
        "will group by the COLUMN and reject the statement at execution time "
        "with a GroupingError. Group by the ordinal (GROUP BY 1) or repeat the "
        "full expression.\n\n" + "\n".join(findings)
    )


# ---------------------------------------------------------------------------
# The scanner's own tests. A scanner that cannot fail is not a gate, and this
# one has three ways to be wrong: miss the real defect, flag correct SQL, or
# mis-scope a CTE. All three are pinned below with the actual statements.
# ---------------------------------------------------------------------------


def test_scanner_catches_the_original_defect():
    """The exact statement that 500'd `/api/feed/tag-counts` is a hazard."""
    original = """
        SELECT
            COALESCE(llm_sport_category, 'other') AS category,
            COUNT(*) AS cnt
        FROM futures_markets
        WHERE status = 'open'
          AND event_id IS NULL
          AND (resolution_date IS NULL OR resolution_date >= :now)
        GROUP BY category
    """
    assert find_alias_collisions(original) == [("category", "futures_markets")]


def test_scanner_accepts_the_ordinal_fix():
    """Grouping by the ordinal cannot be captured by any column name."""
    fixed = """
        SELECT
            COALESCE(llm_sport_category, 'other') AS category,
            COUNT(*) AS cnt
        FROM futures_markets
        WHERE status = 'open'
        GROUP BY 1
    """
    assert find_alias_collisions(fixed) == []


def test_scanner_accepts_a_repeated_expression():
    """The other correct fix — spelling the expression out — is also clean."""
    fixed = """
        SELECT COALESCE(llm_sport_category, 'other') AS category, COUNT(*) AS cnt
        FROM futures_markets
        GROUP BY COALESCE(llm_sport_category, 'other')
    """
    assert find_alias_collisions(fixed) == []


def test_scanner_does_not_flag_a_plain_input_column():
    """`GROUP BY source` where `source` is simply selected is correct SQL."""
    plain = """
        SELECT source, COUNT(*) AS cnt
        FROM futures_markets
        GROUP BY source
    """
    assert find_alias_collisions(plain) == []


def test_scanner_does_not_flag_an_alias_with_no_matching_column():
    """The sibling events statement was never broken — nothing shadows it."""
    events = """
        SELECT
            CASE WHEN s.key LIKE 'soccer_%' THEN 'soccer' ELSE 'other' END AS category,
            COUNT(*) AS cnt
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        GROUP BY category
    """
    assert "category" not in TABLE_COLUMNS["events"]
    assert "category" not in TABLE_COLUMNS["sports"]
    assert find_alias_collisions(events) == []


def test_scanner_scopes_ctes_correctly():
    """A CTE's alias is its own output; the base table is out of scope.

    Modelled on `app/tasks/precompute_backfill_progress.py`, which a naive
    version of this scan reported as a hazard. `futures_markets` is joined
    inside the CTE only; the outer `GROUP BY source` groups the CTE's column.
    Note the non-select parens (`COUNT(*)`, `to_char(...)`) nested inside the
    CTE body — those are what defeated the first collapse helper.
    """
    cte = """
        WITH ro AS (
            SELECT fm.source AS source,
                   to_char(fm.resolution_date, 'YYYY-MM') AS mon
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
        )
        SELECT source, mon, COUNT(*) AS sampled
        FROM ro
        GROUP BY source, mon
    """
    assert "source" in TABLE_COLUMNS["futures_markets"]
    assert find_alias_collisions(cte) == []


def test_metadata_actually_loaded():
    """A scanner reading an empty column map would pass on anything."""
    assert len(TABLE_COLUMNS) > 20
    assert "category" in TABLE_COLUMNS["futures_markets"]
    assert "llm_sport_category" in TABLE_COLUMNS["futures_markets"]


def test_the_scan_examines_a_real_denominator():
    """A clean sweep over nothing prints the same line as a clean sweep.

    `test_no_group_by_resolves_to_a_shadowed_alias` asserts an EMPTY finding
    list, which is exactly what a scan that walked zero files, or read zero
    statements, would also produce. Measured at LAT-P114: 393 files, 487
    `text()` statements. The floors are set well below that so ordinary churn
    does not trip them, and well above zero so a broken walk cannot pass.
    """
    sources = list(iter_sources())
    assert len(sources) > 250, f"only {len(sources)} files walked under app/"
    statements = sum(len(_SQL_LITERAL.findall(source)) for _, source in sources)
    assert statements > 300, f"only {statements} text() statements read"
