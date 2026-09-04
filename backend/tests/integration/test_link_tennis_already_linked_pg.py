""""Already linked" is not "unmatched". CERT-871 FOLLOW-UP `AUTHORITY-006-ALREADY-LINKED-RECEIPTS`.

`link_tennis_statpal_fixtures` asks for candidates with
`e.statpal_fixture_id IS NULL`, which is the guard that stops a task running every
10 minutes from re-deciding 30,115 rows to write nothing. The cost of that guard
is that a fixture linked on an EARLIER pass finds no candidate at all — and
`classify_fixture` correctly returns `UNMATCHED`, because from where it stands
there is nothing to match.

Receipted as-is, that reads *"StatPal has this match and we do not hold it"*,
which is the opposite of the truth. It is not a cosmetic mislabel: within a day
of running, nearly every unmatched receipt is a past success, and the handful of
genuine misses — the ones a person should look at — are buried under them.

`_already_linked` is the disambiguation, and this gate is why it needs a server:

1. **`= ANY(:fixture_ids)` is Postgres array binding.** sqlite has no such
   operator and asyncpg binds a Python list to it in a way no mock reproduces. A
   paraphrase of the statement would pass while the real one raised.
2. **The join is `varchar` to a Python `str`.** `statpal_fixture_id` is a
   `VARCHAR`; the ids arrive off `StatPalFixture.fixture_id` as strings. If
   either side were coerced to `int` the lookup would silently miss every row and
   every already-linked fixture would go on being receipted as a miss — a failure
   whose only symptom is a report that looks fine.
3. **It must not match a row in another sport** that happens to carry the same
   scalar. Only the server can be asked whether the predicate is scoped as
   written.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #2867 already-linked lookup gate "
        "(CI job `search-recall` provides one)"
    ),
)


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine.
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


def _fixture(fixture_id: str, home: str, away: str):
    from app.services.statpal_api import StatPalFixture

    return StatPalFixture(
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        home_team_id=None,
        away_team_id=None,
        start_time=datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        status="scheduled",
    )


async def _seed(conn):
    """Three tennis rows and one baseball row.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT. `events.home_team_name`,
    `.away_team_name`, `.commence_time` and `.status` are NOT NULL, and `.status`
    carries a **client-side** default the ORM applies and a raw INSERT does not.
    `tests/test_pg_gate_seed_completeness.py` parses these statements against the
    live ORM metadata; this file is registered there.
    """
    from sqlalchemy import text

    await conn.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            "(1, 'tennis_atp_us_open', 'US Open (ATP)', true), "
            "(2, 'baseball_mlb', 'MLB', true)"
        )
    )
    rows = [
        # linked on an earlier pass
        (301, 1, "Botic van de Zandschulp", "Alex de Minaur", "2631673"),
        # not linked
        (302, 1, "Alex Michelsen", "Daniel Merida Aguilar", None),
        # a DIFFERENT sport carrying a numerically similar scalar
        (303, 2, "Yankees", "Red Sox", "2631674"),
    ]
    for eid, sid, home, away, fixture_id in rows:
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status, statpal_fixture_id) "
                "VALUES (:id, :sid, :home, :away, :ct, 'scheduled', :fid)"
            ),
            {
                "id": eid,
                "sid": sid,
                "home": home,
                "away": away,
                "ct": datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
                "fid": fixture_id,
            },
        )


@needs_postgres
class TestTheAlreadyLinkedLookup:
    async def test_it_finds_the_fixture_a_previous_pass_linked(self, pg_engine):
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(
                session,
                [
                    _fixture("2631673", "B. Van De Zandschulp", "A. De Minaur"),
                    _fixture("2631999", "A. Michelsen", "D. Merida Aguilar"),
                ],
            )

        assert found == {"2631673": 301}, (
            "the linked fixture must be recognised and the unlinked one must not "
            f"appear; got {found}"
        )

    async def test_the_key_is_a_string_because_the_column_is_a_varchar(
        self, pg_engine
    ):
        """The silent failure this gate exists for.

        `fixture.fixture_id` is a `str`. If the lookup returned int keys, every
        `fixture_id in linked_already` test would be False, every already-linked
        fixture would keep being receipted as a miss, and nothing would raise.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(
                session, [_fixture("2631673", "a", "b")]
            )

        assert list(found) == ["2631673"]
        assert all(isinstance(k, str) for k in found)
        # The membership test the caller actually performs.
        assert _fixture("2631673", "a", "b").fixture_id in found

    async def test_a_row_in_another_sport_is_still_reported(self, pg_engine):
        """Scoping note, asserted rather than assumed.

        The lookup is not sport-scoped, deliberately: a StatPal tennis id sitting
        on a baseball row is a real anomaly, and hiding it here would make the
        fixture read as a genuine miss forever. It surfaces as `already_linked`,
        which is the honest answer — *something already holds this id* — and the
        anchor channel refuses the cross-sport absorption separately.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(
                session, [_fixture("2631674", "a", "b")]
            )

        assert found == {"2631674": 303}

    async def test_an_empty_batch_asks_the_database_nothing(self, pg_engine):
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            assert await _already_linked(session, []) == {}

    async def test_the_statement_executes_on_real_postgres_at_batch_size(
        self, pg_engine
    ):
        """`= ANY(:fixture_ids)` with ~70 ids, the real pass size.

        A list bound to `ANY` is the arm that has no sqlite equivalent and no mock
        that can be wrong about it. A batch of one would execute even if the
        binding degenerated to a scalar.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        batch = [_fixture(str(2631600 + n), "a", "b") for n in range(70)]
        batch.append(_fixture("2631673", "B. Van De Zandschulp", "A. De Minaur"))

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(session, batch)

        assert found == {"2631673": 301, "2631674": 303}
