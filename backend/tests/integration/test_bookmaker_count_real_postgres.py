"""The related-futures liquidity count, executed against a REAL PostgreSQL.

## what is being replaced, and why the old form was slow

`/api/events/{event_id}/related-futures` scored each outcome's liquidity from
`count(DISTINCT bookmaker) GROUP BY outcome_id` over `futures_odds_snapshots`.
The index it needs already existed and was already being chosen —
`ix_fos_outcome_bookmaker (outcome_id, bookmaker)`. The index was never the
problem. PostgreSQL has no index SKIP scan, so that shape reads **every** index
entry belonging to every requested outcome and then sorts them, to report a
number whose observed maximum is 7.

`futures_odds_snapshots` is append-only, 195.6M rows / 51 GB, so "every entry
for this outcome" grows for as long as we keep pricing the market. Measured on
production over 300 outcomes: **365,275 index entries and 68,657 heap fetches
to produce 300 small integers**, 824 ms warm. The cost was a function of how
long we had held the market, not of the answer.

LAT-P163 replaces it with the standard loose-index-scan emulation, which asks
the same index the question it can answer in one probe — "the smallest
bookmaker for this outcome above the last one you gave me". `bookmaker` has 11
distinct values fleet-wide, so the probes are bounded by 12 per outcome and run
at ~2.4. Same index, same answer, 824 ms -> 42.5 ms.

## why this gate needs a real server

The claim is **set equality with the form it replaces**, and the two forms
share no code. Only an executing PostgreSQL can grade that, and it is also the
only thing that can grade the two mechanisms this rewrite actually rests on:

1. **`CAST($1 AS integer[])` resolves the parameter's type.** The list of ids
   is a single bound array now, not an expanded `IN`. If asyncpg or PostgreSQL
   declined to type that parameter, every related-futures build would raise —
   and no mock session has a type resolver.
2. **A `WITH RECURSIVE` correlated to the LATERAL's left side.** Valid SQL that
   a reader has to take on trust; here it is executed.

There is no local PostgreSQL in the agent sandbox, so CI is the environment
that runs this. The `search-recall` job provides the container, and its
"Verify the gate is actually armed" step is what stops a skipped gate from
reading as a passing one.

## the controls, and what each one can actually fail on

The equality assertion is worth nothing unless the seeded corpus can tell the
right answer apart from the plausible wrong ones, so each control below is
paired with the specific defect it would catch:

* `count(*)` instead of `count(DISTINCT bookmaker)` — an outcome carries 5
  snapshot rows across 2 bookmakers.
* a bookmaker set that never needs a second probe — an outcome carries 3
  distinct bookmakers, so the recursion has to iterate rather than terminate on
  the anchor.
* "no rows" silently becoming `0` — an outcome with no snapshots at all must be
  ABSENT from the mapping, because the caller distinguishes the two by
  defaulting to 1 (gotcha #53).
* a filter that does not filter — an outcome with snapshots that is NOT asked
  for must not appear.

`test_the_seeded_corpus_can_distinguish_the_wrong_answers` asserts those shapes
are present in the fixture. Without it a future edit to the seed could quietly
make every assertion below vacuous while leaving them green.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select, text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres bookmaker-count "
        "contract (CI job `search-recall` provides one)"
    ),
)

#: `(outcome key, [bookmaker per snapshot row])`. Duplicates are deliberate —
#: they are what separates `count(*)` from `count(DISTINCT bookmaker)`.
_SEED: dict[str, list[str]] = {
    # 5 rows, 2 distinct: catches counting rows.
    "dupes": ["draftkings", "draftkings", "fanduel", "draftkings", "fanduel"],
    # 3 distinct: forces the recursion to iterate past its anchor.
    "three": ["betmgm", "kalshi", "polymarket"],
    # exactly 1: the overwhelmingly common real shape.
    "single": ["kalshi"],
    # none at all: must be ABSENT from the mapping, never 0.
    "silent": [],
    # has rows but is NOT requested: must not appear.
    "unasked": ["fanduel", "betmgm"],
}

#: Every key except the one that exists to prove the filter is real.
_REQUESTED = [k for k in _SEED if k != "unasked"]


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
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


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{seed key: outcome id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status` and
    `futures_odds_snapshots.reading_count` are NOT NULL carrying a **client-side
    `default=`**, which is applied by the ORM and is invisible to a raw INSERT —
    so omitting them does not silently take the default, it raises
    `NotNullViolation`. The first CI run of this file failed on exactly that.
    The repo already owns this check: `tests/test_pg_gate_seed_completeness.py`
    parses these INSERTs and compares their column lists against the live ORM
    metadata, and its discovery arm fails if a raw-INSERT gate is not registered
    in its `COVERED` tuple. This file is registered there. It parses the real
    statement rather than a copied column list, which is why registering with it
    is strictly better than the local twin this file briefly carried.
    """
    market_id = (
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(source, external_id, name, category, mutually_exclusive, status) "
                "VALUES ('kalshi', 'lat-p163-market', 'LAT-P163 market', "
                "'championship', true, 'open') "
                "RETURNING id"
            )
        )
    ).scalar_one()

    ids: dict[str, int] = {}
    for key, bookmakers in _SEED.items():
        outcome_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name) "
                    "VALUES (:m, :x, :n) RETURNING id"
                ),
                {"m": market_id, "x": f"lat-p163-{key}", "n": key},
            )
        ).scalar_one()
        ids[key] = outcome_id
        for bookmaker in bookmakers:
            await conn.execute(
                text(
                    "INSERT INTO futures_odds_snapshots "
                    "(outcome_id, bookmaker, probability, reading_count) "
                    "VALUES (:o, :b, 0.5, 1)"
                ),
                {"o": outcome_id, "b": bookmaker},
            )
    return ids


async def _old_form(conn, outcome_ids: list[int]) -> dict[int, int]:
    """The pre-LAT-P163 statement, kept as the ORACLE — not as a fallback.

    It is spelled here rather than imported because the point of this file is
    that the shipped helper agrees with a form that no longer exists in the
    route. An import would make the comparison a tautology the moment the
    route changed.
    """
    from app.models import FuturesOddsSnapshot

    result = await conn.execute(
        select(
            FuturesOddsSnapshot.outcome_id,
            func.count(func.distinct(FuturesOddsSnapshot.bookmaker)),
        )
        .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
        .group_by(FuturesOddsSnapshot.outcome_id)
    )
    return {row[0]: row[1] for row in result.all()}


class _RecordingSession:
    """Captures `(statement, params)` without touching a database."""

    def __init__(self):
        self.executed: list[tuple[object, dict]] = []

    async def execute(self, statement, params=None):
        self.executed.append((statement, params or {}))

        class _Empty:
            @staticmethod
            def all():
                return []

        return _Empty()


async def test_the_helper_binds_the_ids_as_one_array_parameter():
    """Armed-check, and it needs no database.

    Two things would make every Postgres assertion below vacuous, and neither
    is visible from a green equality result: the helper issuing no statement at
    all, and the ids arriving as an expanded `IN` list rather than the single
    array parameter whose type resolution this gate exists to prove.
    """
    from app.routes.events import _count_bookmakers_per_outcome

    session = _RecordingSession()
    assert await _count_bookmakers_per_outcome(session, [7, 11, 13]) == {}

    assert len(session.executed) == 1, (
        f"expected exactly 1 statement from _count_bookmakers_per_outcome, "
        f"captured {len(session.executed)}"
    )
    _statement, params = session.executed[0]
    assert list(params) == ["outcome_ids"], (
        f"expected a single bound array parameter, got {sorted(params)}"
    )
    assert params["outcome_ids"] == [7, 11, 13]


async def test_an_empty_id_list_asks_the_database_nothing():
    """The caller reaches this whenever an event has no matching outcomes."""
    from app.routes.events import _count_bookmakers_per_outcome

    session = _RecordingSession()
    assert await _count_bookmakers_per_outcome(session, []) == {}
    assert session.executed == []


async def test_the_seeded_corpus_can_distinguish_the_wrong_answers():
    """Harness validity. A corpus of five one-bookmaker outcomes would make the
    equality test below pass for an implementation that counted rows, counted
    only the first bookmaker, or ignored its filter entirely.

    Deliberately NOT gated on Postgres. This asserts a property of the fixture
    itself, so it must run in the ordinary suite too — a control that only
    executes in the one job that also runs the thing it is validating can be
    disarmed by the same edit that disarms the gate.
    """
    row_counts = {k: len(v) for k, v in _SEED.items()}
    distinct_counts = {k: len(set(v)) for k, v in _SEED.items()}

    assert any(
        row_counts[k] > distinct_counts[k] for k in _SEED
    ), "no outcome has duplicate bookmakers — count(*) would score identically"
    assert any(
        distinct_counts[k] >= 3 for k in _SEED
    ), "no outcome needs a second recursion step — the anchor alone would pass"
    assert any(
        distinct_counts[k] == 0 for k in _SEED
    ), "no outcome is silent — absent-vs-zero would be untested"
    assert "unasked" not in _REQUESTED and _SEED["unasked"], (
        "the un-requested outcome must exist and carry rows, or the filter is "
        "never exercised"
    )


@needs_postgres
async def test_the_helper_agrees_with_the_form_it_replaced(pg_engine):
    """The gate. PostgreSQL is the oracle for set equality.

    Both forms run against the same seeded rows in the same connection, so a
    difference can only come from the statements themselves.
    """
    from app.routes.events import _count_bookmakers_per_outcome

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)
        requested = [ids[k] for k in _REQUESTED]

        new = await _count_bookmakers_per_outcome(conn, requested)
        old = await _old_form(conn, requested)

    assert new == old, (
        "the loose-index-scan form disagreed with the aggregate it replaced\n"
        f"  new: {sorted(new.items())}\n  old: {sorted(old.items())}"
    )

    expected = {
        ids[k]: len(set(_SEED[k])) for k in _REQUESTED if _SEED[k]
    }
    assert new == expected, (
        "both forms agreed, but on the wrong answer — the oracle and the "
        f"subject can be wrong together\n  got: {sorted(new.items())}\n"
        f"  want: {sorted(expected.items())}"
    )


@needs_postgres
async def test_a_silent_outcome_is_absent_rather_than_zero(pg_engine):
    """`0` and "we have no snapshots" are different claims (gotcha #53).

    The caller renders `bookmaker_counts.get(outcome.id, 1)`, so publishing a
    `0` here would drive the liquidity term to zero for exactly the outcomes we
    know nothing about, instead of leaving them on the default.
    """
    from app.routes.events import _count_bookmakers_per_outcome

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)
        counts = await _count_bookmakers_per_outcome(
            conn, [ids[k] for k in _REQUESTED]
        )

    assert ids["silent"] not in counts
    assert counts.get(ids["silent"], 1) == 1


@needs_postgres
async def test_an_outcome_that_was_not_asked_for_is_not_returned(pg_engine):
    """The array parameter is a filter, not decoration."""
    from app.routes.events import _count_bookmakers_per_outcome

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)
        counts = await _count_bookmakers_per_outcome(
            conn, [ids[k] for k in _REQUESTED]
        )

    assert ids["unasked"] not in counts, (
        "an outcome outside the requested ids came back — the CAST'd array is "
        "not constraining the scan"
    )


@needs_postgres
async def test_duplicate_bookmakers_are_counted_once(pg_engine):
    """RED-proof for the single most likely wrong implementation.

    `dupes` carries five snapshot rows across two bookmakers. An implementation
    that counted rows would answer 5 here and would still satisfy every other
    assertion in this file.
    """
    from app.routes.events import _count_bookmakers_per_outcome

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)
        counts = await _count_bookmakers_per_outcome(conn, [ids["dupes"]])

    assert counts[ids["dupes"]] == 2, (
        f"expected 2 distinct bookmakers across 5 rows, got {counts}"
    )
