"""`/api/feed/tag-counts` executed against a REAL PostgreSQL.

## the defect, and why nothing cheaper could have caught it

The route returned Starlette's plain-text `500` on every request from the day
it was written (`c536d738`, 2026-03-01) until LAT-P114, so `/categories`
rendered `ErrorState("Failed to load categories")` for its entire existence.
The statement was:

    SELECT COALESCE(llm_sport_category, 'other') AS category, COUNT(*) AS cnt
    FROM futures_markets
    WHERE ...
    GROUP BY category

`futures_markets` has a real `category` column. **PostgreSQL resolves a bare
`GROUP BY` identifier against the input columns before it will consider an
output alias**, so the grouping key was `futures_markets.category`, the
selected `COALESCE(...)` was ungrouped, and every execution raised

    GroupingError: column "futures_markets.llm_sport_category" must appear in
    the GROUP BY clause or be used in an aggregate function

Roughly nineteen thousand tests were green the whole time. They had to be: the
statement is valid SQL, it names only real identifiers, and **the thing that
rejects it is the server's name-resolution rule**. No mock session has one. No
recording double has one. Reading the SQL does not reveal it either — the trap
is that the line looks exactly like the correct version.

So the gate for "this route's statements can actually run" cannot be a unit
test, a source assertion, or a fixture. It needs the service container, which
is what the `search-recall` CI job provides. There is no local Postgres in the
agent sandbox (`initdb` fails on `shmget`), so **CI is the environment that
runs this**, and that job's "Verify the gate is actually armed" step exists so
a skipped gate cannot be mistaken for a passing one.

## why it drives the handler instead of quoting it

The statements are not copied into this file. A recording session captures what
`get_tag_counts` actually issues and those exact strings are executed. A copy
would be a self-oracle the moment the route changed: it would keep proving that
a string in a test file is valid SQL while the shipped route drifted away from
it. Here, a future edit that reintroduces the collision is caught even though
this file never mentions `GROUP BY`.

Empty tables are enough. `GroupingError` is raised while the statement is being
parsed and planned, before a single row is touched — which is also why the
defect was total rather than data-dependent.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

#: Applied per-test rather than to the module. The capture check below needs no
#: database and is worth running in the ordinary suite, where it is the thing
#: that stops the two Postgres gates from silently grading an empty list.
needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres tag-counts "
        "contract (CI job `search-recall` provides one)"
    ),
)


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped, following `test_kalshi_cliff_bind_contract.py`:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


class _RecordedResult:
    """The shape `get_tag_counts` consumes: `.all()` returning nothing."""

    @staticmethod
    def all():
        return []


class _RecordingSession:
    """Captures `(statement, params)` without touching a database."""

    def __init__(self):
        self.executed: list[tuple[object, dict]] = []

    async def execute(self, statement, params=None):
        self.executed.append((statement, params or {}))
        return _RecordedResult()


async def _statements_the_route_issues():
    """Run the real handler and return every statement it executed."""
    from app.routes.feed import get_tag_counts

    session = _RecordingSession()
    payload = await get_tag_counts(db=session)

    # With no rows the handler must still answer, not raise. The empty body is
    # a legitimate response shape here — it is the 500 that was the defect.
    assert payload == {"counts": {}}
    return session.executed


async def test_the_route_issues_the_statements_this_gate_thinks_it_does():
    """A gate that captured zero statements would pass on anything.

    Gotcha #53's discipline applied to this file's own instrument: "it
    returned" is not "it worked". If the handler is refactored to build its
    counts elsewhere, this assertion fails loudly rather than letting the two
    tests below go green over an empty list.
    """
    executed = await _statements_the_route_issues()
    assert (
        len(executed) == 2
    ), f"expected 2 statements from get_tag_counts, captured {len(executed)}"
    rendered = " ".join(str(stmt) for stmt, _ in executed).lower()
    assert "from events" in rendered
    assert "from futures_markets" in rendered


@needs_postgres
async def test_every_tag_counts_statement_executes_on_real_postgres(pg_engine):
    """The gate. Each captured statement runs; PostgreSQL is the oracle.

    Before LAT-P114 the second statement raised
    `GroupingError: column "futures_markets.llm_sport_category" must appear in
    the GROUP BY clause`, which is the 500 the `/categories` page rendered.
    """
    executed = await _statements_the_route_issues()

    async with pg_engine.connect() as conn:
        for index, (statement, params) in enumerate(executed):
            try:
                await conn.execute(statement, params)
            except Exception as exc:  # noqa: BLE001 — the failure IS the finding
                pytest.fail(
                    f"statement {index} from get_tag_counts was rejected by "
                    f"PostgreSQL — this is the shape that returned a 500 on "
                    f"every request to /api/feed/tag-counts:\n\n"
                    f"{statement}\n\n{type(exc).__name__}: {exc}"
                )


@needs_postgres
async def test_the_gate_would_catch_the_original_defect(pg_engine):
    """RED-proof, run against the same server that grades the gate above.

    Without this, a green result is consistent with PostgreSQL having quietly
    stopped caring about the ambiguity — in which case the test above would
    pass for the wrong reason and this whole file would be decorative. The
    original statement is executed here on purpose and is REQUIRED to fail.
    """
    original = text("""
        SELECT
            COALESCE(llm_sport_category, 'other') AS category,
            COUNT(*) AS cnt
        FROM futures_markets
        WHERE status = 'open'
          AND event_id IS NULL
        GROUP BY category
    """)

    async with pg_engine.connect() as conn:
        with pytest.raises(Exception) as caught:
            await conn.execute(original)

    message = str(caught.value)
    assert "llm_sport_category" in message and "GROUP BY" in message, (
        "the pre-fix statement was expected to be rejected for grouping by "
        f"futures_markets.category instead of the alias; got: {message}"
    )
