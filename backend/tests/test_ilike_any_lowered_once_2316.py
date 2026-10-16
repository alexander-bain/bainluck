"""#2316: `ilike_any_lowered_once` renders the one-lowercase form, and only that.

The set-equality claim is graded by a real server in
`tests/integration/test_ilike_any_lowered_once_2316_pg.py`; these pin the
rendering the route depends on, where a mock session can grade it:

* the row's text is lowered ONCE (`lower(col) LIKE ANY`), with no `ILIKE` arm
  left to lower it again per pattern;
* the patterns are lowered by the database inside a scalar subquery, wrapped in
  a CAST so `ANY` reads an array expression — the bare subquery renders
  `ANY (SELECT ...)`, which PostgreSQL resolves as `text ~~ text[]` and rejects;
* the patterns reach the database verbatim, in order — never pre-lowered by
  Python, whose case mapping is not the database collation's;
* no ESCAPE clause, so the escape character stays PostgreSQL's default
  backslash, exactly as `.ilike()` without `escape=` left it.
"""

import pytest
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesOutcome
from app.utils.ilike_any import ilike_any_lowered_once

_PATTERNS = ["%Miami Hurricanes%", "%MÜNCHEN%", "%Ja'Marr Chase%", "%A\\_B%"]


def _compiled(patterns):
    return ilike_any_lowered_once(FuturesOutcome.name, patterns).compile(
        dialect=postgresql.dialect()
    )


def test_the_row_text_is_lowered_once_and_no_ilike_arm_remains():
    sql = str(_compiled(_PATTERNS))
    assert sql.startswith("lower(futures_outcomes.name) LIKE ANY (CAST((SELECT ARRAY[")
    assert sql.count("lower(futures_outcomes.name)") == 1, sql
    assert "ILIKE" not in sql.upper(), sql


def test_any_reads_an_array_expression_not_a_row_subquery():
    sql = str(_compiled(_PATTERNS))
    assert "ANY (CAST((SELECT ARRAY[" in sql, sql
    assert sql.rstrip().endswith("AS TEXT[]))"), sql
    assert "ANY (SELECT" not in sql, sql


def test_every_pattern_is_lowered_by_the_database_not_by_python():
    compiled = _compiled(_PATTERNS)
    sql = str(compiled)
    assert sql.count("lower(%(param_") == len(_PATTERNS), sql
    # Verbatim and in order: `MÜNCHEN` still upper-case, the escape intact.
    values = [compiled.params[k] for k in sorted(compiled.params, key=lambda k: int(k.split("_")[1]))]
    assert values == _PATTERNS


def test_the_escape_character_stays_the_default_backslash():
    assert "ESCAPE" not in str(_compiled(_PATTERNS)).upper()


def test_no_patterns_is_refused_rather_than_matching_nothing_silently():
    with pytest.raises(ValueError):
        ilike_any_lowered_once(FuturesOutcome.name, [])
