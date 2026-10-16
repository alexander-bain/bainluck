"""#2316: one lowercase per row returns exactly the rows of the ILIKE OR.

Related-futures step 5 used to OR one `name ILIKE '%p%'` arm per pattern, every
roster player included. On a UTF8 database PostgreSQL lowers BOTH sides of
each ILIKE on every call, so a 210-arm college-football build ran past a 25 s
statement timeout on production; `lower(name) LIKE ANY (lowered patterns)` ran
the same specimen in 119-277 ms with 0 disagreements over 3,683 rows.

Why a real server: the claim is that two different SQL texts select the same
rows, and that rests on PostgreSQL's own case mapping and LIKE escape rules,
plus asyncpg typing `lower($n)` inside `CAST((SELECT ARRAY[...]) AS TEXT[])`.
No mock can grade any of that. The corpus is a VALUES list, so no table, seed
or migration is involved.

Each corpus row is there to catch a specific wrong answer:

* accented and non-ASCII case pairs (`MÜNCHEN` / `München`, `ØDEGAARD`,
  `İstanbul`, `ß`): a form that lowered patterns with Python, or not at all;
* `_` and `%` inside names with escaped patterns: a form that lost the default
  backslash escape (`A\\_B` must not match `AxB`);
* a NULL name: must be selected by neither form;
* rows that match nothing: a form that matched everything.

`test_the_corpus_can_tell_the_wrong_answers_apart` proves those shapes are
live, so the equality below cannot pass vacuously.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import String, column, or_, select, values

from app.utils.ilike_any import ilike_any_lowered_once

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2316 "
            "one-lowercase contract (CI job `search-recall` provides one)"
        ),
    ),
]

_NAMES = [
    "Miami Hurricanes",
    "MIAMI HURRICANES to win the ACC",
    "Ja'Marr Chase: 100+ receiving yards",
    "FC Bayern München",
    "MARTIN ØDEGAARD",
    "Galatasaray (İstanbul)",
    "Straße Kickers",
    "A_B United",
    "AxB United",
    "100% Club",
    "1000 Club",
    "Florida State Seminoles",
    "Philadelphia 76ers",
    None,
]

_PATTERNS = [
    "%miami%",
    "%Ja'Marr Chase%",
    "%MÜNCHEN%",
    "%ødegaard%",
    "%İSTANBUL%",
    "%STRASSE%",
    "%straße%",
    "%A\\_B%",
    "%100\\%%",
    "%Seminoles%",
]


def _corpus():
    return values(column("id", String), column("name", String), name="corpus").data(
        [(str(i), n) for i, n in enumerate(_NAMES)]
    )


async def _ids(conn, predicate_for) -> set[str]:
    corpus = _corpus()
    result = await conn.execute(
        select(corpus.c.id).where(predicate_for(corpus.c.name))
    )
    return {row[0] for row in result.all()}


@pytest.fixture
async def conn():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as c:
        yield c
    await engine.dispose()


async def test_one_lowercase_selects_exactly_the_rows_of_the_ilike_or(conn):
    old = await _ids(conn, lambda col: or_(*[col.ilike(p) for p in _PATTERNS]))
    new = await _ids(conn, lambda col: ilike_any_lowered_once(col, _PATTERNS))
    assert new == old


async def test_each_single_pattern_agrees_too(conn):
    """A pooled set can hide two compensating errors; one pattern at a time cannot."""
    for p in _PATTERNS:
        old = await _ids(conn, lambda col, p=p: col.ilike(p))
        new = await _ids(conn, lambda col, p=p: ilike_any_lowered_once(col, [p]))
        assert new == old, p


async def test_the_corpus_can_tell_the_wrong_answers_apart(conn):
    by_name = {n: str(i) for i, n in enumerate(_NAMES) if n is not None}
    old = await _ids(conn, lambda col: or_(*[col.ilike(p) for p in _PATTERNS]))
    # Case folding is exercised: these match only case-insensitively.
    for name in ("MIAMI HURRICANES to win the ACC", "FC Bayern München", "MARTIN ØDEGAARD"):
        assert by_name[name] in old, name
    # The escape is exercised: `A\_B` matches the underscore, not any character.
    assert by_name["A_B United"] in old
    assert by_name["AxB United"] not in old
    assert by_name["100% Club"] in old
    assert by_name["1000 Club"] not in old
    # Something is rejected, so "match everything" fails.
    assert by_name["Philadelphia 76ers"] not in old
    # NULL is selected by neither form.
    null_id = str(_NAMES.index(None))
    new = await _ids(conn, lambda col: ilike_any_lowered_once(col, _PATTERNS))
    assert null_id not in old and null_id not in new


async def test_the_server_runs_the_configuration_the_claim_is_about(conn):
    """Production is UTF8 with a libc `en_US.UTF-8` ctype; CI's `postgres:15` is
    `en_US.utf8`. Under a C ctype `lower()` folds ASCII only and the corpus
    checks above would grade a different case mapping. Fail, never skip."""
    from sqlalchemy import text

    encoding, ctype = (
        await conn.execute(
            text(
                "SELECT pg_encoding_to_char(encoding), datctype FROM pg_database "
                "WHERE datname = current_database()"
            )
        )
    ).one()
    assert encoding == "UTF8"
    assert ctype not in ("C", "POSIX") and not ctype.startswith("C."), ctype


async def test_python_lowering_would_be_a_different_answer(conn):
    """Why the patterns are lowered by the database: the strawman is observable.

    The database lowers `İ` to `i` (production read 2026-10-16:
    `lower('%İSTANBUL%') = '%istanbul%'`); Python lowers it to `i̇`, two code
    points, which matches nothing the database lowered. A Python-lowered
    implementation would drop `Galatasaray (İstanbul)`.
    """
    from sqlalchemy import func, literal

    db_lower = (
        await conn.execute(select(func.lower(literal("%İSTANBUL%", String))))
    ).scalar_one()
    assert db_lower == "%istanbul%"
    assert "%İSTANBUL%".lower() != db_lower
