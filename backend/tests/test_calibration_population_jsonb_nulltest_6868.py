"""No population predicate is an ``IS NULL`` on a jsonb subscript (#6868, CAL-P1340).

## what it cost

`2caad4905` (#6211, CAL-P1310, 2026-09-16 15:20:45Z) added one clause to
``market_info``::

    AND fm.market_metadata->'datagolf_recovery_unverified' IS NULL

Same rows, different plan. PostgreSQL keeps no statistics for a jsonb subscript,
so ``nulltestsel`` falls through to ``DEFAULT_UNK_SEL`` = 0.005 whenever the
argument of an ``IS NULL`` is not a plain column. Read off the production
planner at a 1,500-market roster (``EXPLAIN``, plan only, 2026-09-23 03:5xZ,
same statistics, same minute, the only difference being this clause):

===============================  =============  =============
estimate for                     without it     with it
===============================  =============  =============
``CTE market_info``              725 rows       **4 rows**
``CTE virtual_market``           1,500 (true)   30
``CTE market_result_shape``      491            3
plan nodes                       135            124
root total cost                  448,472        94,903
===============================  =============  =============

Believing the unit held four markets, the planner rebuilt the chain as per-row
nested loops with index lookups. The per-unit mean went 145,478 ms to ~660,000 ms
between two consecutive beats on 2026-09-16 and ``/api/calibration`` stopped
publishing for a week (#6868).

The estimate was not pessimistic, it was backwards: **0 of 1,120,621 resolved
markets carry the key** (measured 2026-09-23 03:54Z). True selectivity 1.000,
assumed 0.005. The clause excluded nothing and cost everything.

## why the guard is a TEXT scan and the plan read is a script

The fact is the planner's, and the planner's answer here is a property of
STATISTICS: the collapse above is ``DEFAULT_UNK_SEL`` applied to a real
distribution. CI's Postgres container is an empty schema with no statistics at
all, so a CI gate asserting this ratio would be measuring its own fixture. The
plan read therefore lives in ``scripts/probe_staged_unit_plan_shape.py``, which
takes it against production in one command and prints the three arms.

What a test CAN hold is the spelling, and the spelling is how this class comes
back — by typing, not by a planner changing its mind. Note also that the sibling
row-level gate ``integration/test_calibration_datagolf_symmetric_exclusion_pg.py``
was green for the entire week: the regression and the repair select exactly the
same rows, so no test of the rows can ever see it.

Deliberately a CLASS and not this one clause. The next one will be a different
key on a different jsonb column, and `->>`/`IS NOT NULL` fail the same way.
"""

from __future__ import annotations

import re

import pytest

#: Any ``IS NULL`` / ``IS NOT NULL`` whose argument reaches through `->` or `->>`.
#: The optional closing paren catches the parenthesised and cast-wrapped forms
#: (``(md->>'k')::boolean IS NULL``), which have the same estimator problem.
JSONB_NULLTEST = re.compile(
    r"->>?\s*'[^']+'\s*\)*(?:::\s*\w+)?\s*\)*\s*IS\s+(?:NOT\s+)?NULL",
    re.IGNORECASE,
)

#: The exact clause `2caad4905` shipped. The red-first arm feeds this to the
#: scanner: if the scanner ever stops flagging it, the gate above is decoration.
THE_REGRESSION = (
    "AND fm.market_metadata->'datagolf_recovery_unverified' IS NULL"
)

#: What replaced it. `IS NULL` on the real COLUMN keeps that column's statistics,
#: and `NOT (md ? 'k')` is estimated by `contsel` rather than by the null-test
#: default. Equivalent on every row: `md->'k' IS NULL` is true when `md` is SQL
#: NULL or the key is absent, and a JSON `null` VALUE is `'null'::jsonb`, never
#: SQL NULL, so `?` and the subscript cannot disagree.
THE_REPAIR = (
    "AND (fm.market_metadata IS NULL\n"
    "                       OR NOT (fm.market_metadata ? 'datagolf_recovery_unverified'))"
)


def _uncommented(sql: str) -> str:
    """The statement with its ``--`` prose removed.

    The clause this gate was written for is quoted VERBATIM in a comment beside
    its repair (CAL-P150: the wrong sentence is kept and marked, because it is
    what stopped the next reader looking). Scanning the comments would therefore
    fail on the very file that fixed it.
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def _statements() -> dict[str, str]:
    from app.tasks.precompute_calibration import (
        _calibration_population_ctes,
        _main_futures_sql,
    )

    return {
        "staged unit (frozen roster)": _main_futures_sql(frozen=True),
        "monolith": _main_futures_sql(frozen=False),
        "shared population chain": _calibration_population_ctes(),
    }


@pytest.mark.parametrize("name", sorted(_statements()))
def test_no_population_predicate_null_tests_a_jsonb_subscript(name):
    sql = _statements()[name]
    found = JSONB_NULLTEST.findall(_uncommented(sql))
    assert not found, (
        f"{name} null-tests a jsonb subscript: {found}. PostgreSQL has no "
        "statistics for that expression, so the planner charges the clause "
        "DEFAULT_UNK_SEL (0.005) and re-plans the whole unit for a population "
        "~200x smaller than the real one — #6868's week of a stale accuracy "
        "page. Write it as `IS NULL` on the COLUMN plus `NOT (col ? 'key')`, "
        "which is the same rows and keeps the estimate."
    )


def test_the_repair_is_the_clause_that_is_actually_in_the_statement():
    """Premise pin: the gate is aimed at a clause that exists."""
    sql = _main_futures_sql_frozen()
    assert THE_REPAIR in sql, (
        "the DataGolf `unverified` exclusion is not in the built statement in "
        "the repaired spelling. Do not delete this gate — re-aim it. If the "
        "exclusion was removed on purpose, that is a population change and it "
        "owes its own reasoning."
    )
    assert THE_REGRESSION not in _uncommented(sql), (
        "the regressed spelling is back in live SQL (not just quoted in the "
        "comment that explains it)"
    )


def test_the_scanner_still_recognises_the_clause_that_caused_it():
    """Red-first: the instrument is proved against the original defect."""
    assert JSONB_NULLTEST.search(THE_REGRESSION), (
        "the scanner no longer flags `2caad4905`'s own clause, so every "
        "assertion above passes for free"
    )
    assert not JSONB_NULLTEST.search(THE_REPAIR), (
        "the scanner flags the repaired form too, so it cannot tell the two "
        "apart and the gate is unsatisfiable"
    )
    # The class, not the instance: a different key, a different column, `->>`,
    # and the cast-wrapped form all have the same estimator problem.
    for variant in (
        "AND e.win_probability_sources->'kalshi' IS NULL",
        "AND fm.market_metadata->>'anything' IS NOT NULL",
        "AND (fm.market_metadata->>'k')::boolean IS NULL",
    ):
        assert JSONB_NULLTEST.search(variant), f"scanner missed {variant!r}"


def _main_futures_sql_frozen() -> str:
    from app.tasks.precompute_calibration import _main_futures_sql

    return _main_futures_sql(frozen=True)
