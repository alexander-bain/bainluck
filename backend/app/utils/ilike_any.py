"""#2316: an OR of many `col ILIKE p` arms, answered with one lowercase per row.

On a UTF8 database PostgreSQL implements `str ILIKE pat` as `lower(str) LIKE
lower(pat)` under the expression's collation, lowering BOTH sides on every call
(`Generic_Text_IC_like` in `utils/adt/like.c`: "In the multibyte case we don't
have much choice"). An OR of N arms therefore lowercases each candidate row's
text N times. Related-futures step 5 ORs one arm per roster player — 167-210
arms for a college-football game — and the planner answers it with an OR of
that many trigram probes plus a per-row recheck of every arm. Production,
Miami v Florida State (14957338, 210 arms, 970 market ids): the OR form ran
past a 25 s statement timeout; this form returned the same 96 rows in 119-277
ms, 0 disagreements over 3,683 candidate rows and 162 non-ASCII rows.

`lower(col) LIKE ANY (lowered patterns)` is the predicate PostgreSQL already
evaluates, with the row's text lowered once. The patterns are lowered by the
database (same collation, so the same case mapping — never Python's
`str.lower`), inside a scalar subquery so the array is built once per statement
as an InitPlan even under a generic prepared plan. ESCAPE stays the default
backslash, as with `.ilike()`. NULL text gives NULL either way.

The trade: `lower(col)` cannot use the `gin_trgm_ops` index on `col`. Use this
only where another indexed conjunct (here `market_id IN (...)`) bounds the
candidates; a predicate that is the statement's only filter should keep
`.ilike()` and its index.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import String, Text, any_, cast, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY, array
from sqlalchemy.sql.elements import ColumnElement


def ilike_any_lowered_once(
    column: ColumnElement, patterns: Sequence[str]
) -> ColumnElement[bool]:
    """`column ILIKE patterns[0] OR ... OR column ILIKE patterns[-1]`, same rows."""
    if not patterns:
        raise ValueError("ilike_any_lowered_once needs at least one pattern")
    lowered = select(
        array([func.lower(literal(p, String)) for p in patterns])
    ).scalar_subquery()
    # CAST makes `ANY (...)` read an array EXPRESSION; a bare scalar subquery
    # renders `ANY (SELECT ...)`, the row-subquery form, i.e. `text ~~ text[]`.
    return func.lower(column).like(any_(cast(lowered, ARRAY(Text))))
