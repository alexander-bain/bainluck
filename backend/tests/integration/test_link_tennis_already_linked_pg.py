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
4. **The anchor join must be a LEFT join.** CERT-883 FOLLOW-UP
   `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED` added it, because a scalar with no
   anchor behind it is a half-link and was being counted as a success. An INNER
   join would make every half-link disappear from the result — and disappearing
   sends it straight back to being reported as a miss, which is the bug this
   file was opened to fix, arrived at from the other side. Only a server can be
   asked whether the NULL row survives the join.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.tasks.link_tennis_statpal_fixtures import (
    PRIOR_FOREIGN_SPORT,
    PRIOR_PAIRED,
    PRIOR_STATES_THAT_ARE_A_LINK,
    PRIOR_UNANCHORED,
)

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
    """Four rows, one per state the lookup has to tell apart.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT. `events.home_team_name`,
    `.away_team_name`, `.commence_time` and `.status` are NOT NULL, and `.status`
    carries a **client-side** default the ORM applies and a raw INSERT does not.
    Same for `event_provider_anchors.event_id`, `.source`, `.source_id` and
    `.id_kind`; `.first_seen_at` carries a `server_default` and is excused.
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
        # PAIRED — linked on an earlier pass, anchor below
        (301, 1, "Botic van de Zandschulp", "Alex de Minaur", "2631673"),
        # not linked at all
        (302, 1, "Alex Michelsen", "Daniel Merida Aguilar", None),
        # FOREIGN_SPORT — a DIFFERENT sport carrying a numerically similar scalar
        (303, 2, "Yankees", "Red Sox", "2631674"),
        # UNANCHORED — a tennis half-link: scalar set, no anchor behind it
        (304, 1, "Jannik Sinner", "Lorenzo Musetti", "2631675"),
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

    # Only event 301 gets its pair. Event 303 gets an anchor too — a VALID one,
    # in its own sport's space — so the FOREIGN_SPORT case is not passing merely
    # because the baseball row happens to have no anchors at all.
    anchors = [
        (301, "statpal", "tennis:2631673", "game"),
        (303, "statpal", "baseball_mlb:2631674", "game"),
    ]
    for event_id, source, source_id, id_kind in anchors:
        await conn.execute(
            text(
                "INSERT INTO event_provider_anchors "
                "(event_id, source, source_id, id_kind) "
                "VALUES (:event_id, :source, :source_id, :id_kind)"
            ),
            {
                "event_id": event_id,
                "source": source,
                "source_id": source_id,
                "id_kind": id_kind,
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

        assert set(found) == {"2631673"}, (
            "the linked fixture must be recognised and the unlinked one must not "
            f"appear; got {found}"
        )
        assert found["2631673"]["state"] == PRIOR_PAIRED
        assert found["2631673"]["event_id"] == 301

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

        The lookup is STILL not sport-scoped in its WHERE clause, deliberately:
        a StatPal tennis id sitting on a baseball row is a real anomaly, and
        filtering it out here would make the fixture read as a genuine miss
        forever, with nothing anywhere naming the row that holds its id.

        What CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`
        changed is the VERDICT, not the reach. The row is still found and still
        reported; it is no longer called a link. Those are different claims and
        the old return shape could only make one of them.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(
                session, [_fixture("2631674", "a", "b")]
            )

        assert set(found) == {"2631674"}, "the holder must still be surfaced"
        assert found["2631674"]["state"] == PRIOR_FOREIGN_SPORT
        assert found["2631674"]["event_id"] == 303
        assert found["2631674"]["state"] not in PRIOR_STATES_THAT_ARE_A_LINK

    async def test_a_tennis_scalar_with_no_anchor_is_a_half_link_on_a_real_server(
        self, pg_engine
    ):
        """The join, proved where the join runs.

        Event 304 holds `2631675` and has no anchor row at all. The pure
        classifier is exercised in `tests/test_link_tennis_pair_aware_already_linked.py`;
        what only a server can settle is that the LEFT JOIN returns the holder
        with a NULL `source_id` rather than dropping the row — an INNER JOIN here
        would make every half-link vanish from the batch and be re-reported as an
        ordinary miss, which is a different wrong answer wearing the same face.
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(
                session, [_fixture("2631675", "J. Sinner", "L. Musetti")]
            )

        assert set(found) == {"2631675"}, (
            "a LEFT JOIN that behaved like an INNER JOIN would return {} here "
            f"and the half-link would be reported as a miss; got {found}"
        )
        assert found["2631675"]["state"] == PRIOR_UNANCHORED
        assert found["2631675"]["event_id"] == 304
        assert found["2631675"]["expected_anchor"] == "tennis:2631675"

    async def test_the_anchor_join_matches_on_the_key_not_merely_the_event(
        self, pg_engine
    ):
        """Event 303 HAS a statpal `game` anchor — for its own sport's space.

        If the join checked only "this row has some StatPal game anchor", the
        baseball holder would pair and the cross-sport collision would report as
        a link. Asserted against a real row rather than a fake, because the
        `source_id` comparison is a varchar match the server performs.
        """
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.tasks.link_tennis_statpal_fixtures import _already_linked

        async with pg_engine.begin() as conn:
            await _seed(conn)

        async with AsyncSession(pg_engine) as session:
            present = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM event_provider_anchors "
                        "WHERE event_id = 303 AND source = 'statpal' "
                        "AND id_kind = 'game'"
                    )
                )
            ).scalar()
            assert present == 1, "the seed must actually give 303 an anchor"

            found = await _already_linked(
                session, [_fixture("2631674", "a", "b")]
            )

        assert found["2631674"]["state"] == PRIOR_FOREIGN_SPORT

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

        # 2631600..2631669 — 70 ids that are deliberately NOT seeded, so the
        # batch is mostly misses, which is the real pass shape. ALL THREE seeded
        # ids are then appended explicitly: `range(70)` stops at 2631669 and
        # reaches none of them, so asserting on an id the batch never carried
        # would test the seed rather than the statement (CERT-885 repaired
        # exactly that, for `2631674`, and the third id joins on the same terms).
        batch = [_fixture(str(2631600 + n), "a", "b") for n in range(70)]
        batch.append(_fixture("2631673", "B. Van De Zandschulp", "A. De Minaur"))
        batch.append(_fixture("2631674", "a", "b"))
        batch.append(_fixture("2631675", "J. Sinner", "L. Musetti"))
        assert len(batch) == 73

        async with AsyncSession(pg_engine) as session:
            found = await _already_linked(session, batch)

        # All three states, in one statement, at the real batch size — and the
        # 70 unseeded ids absent, so the anchor LEFT JOIN has not turned the
        # lookup into something that returns rows for fixtures nobody holds.
        assert {k: v["state"] for k, v in found.items()} == {
            "2631673": PRIOR_PAIRED,
            "2631674": PRIOR_FOREIGN_SPORT,
            "2631675": PRIOR_UNANCHORED,
        }
