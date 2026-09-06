"""Assembly writes edges and receipts, and re-running it changes nothing new.

#2927 Phase 2. The pure half of assembly — the register gatherer, the class
computation, the cycle guard, the section ordering — is graded in
`tests/test_container_assembly_2927.py` against the real committed register.
This file grades the half that only a server can answer.

WHY EACH OF THESE NEEDS A REAL DATABASE.

* **Idempotency** is `ON CONFLICT (parent_type, parent_id, child_type,
  child_id, kind) DO UPDATE`. A mock session records the statement the caller
  built and therefore agrees with the caller by construction; only a server can
  say whether the second run produced 458 members or 916. That number is the
  difference between a hub that works and a hub that looks, from outside, like
  it is working unusually well.
* **The receipt upsert** goes through `flush_receipts`, whose whole design is a
  Postgres upsert with `LEAST()` on `first_attempted_at` and an incrementing
  `attempt_count`.
* **`container_id` surviving the round trip** is the new column doing its job.
  #2199 is the standing lesson: a writer that looked correct wrote zero rows of
  10,804 against a real column default, with 19,906 tests green.
* **The dangling-edge check** is a LEFT JOIN against three different tables,
  and its whole purpose is to notice a row that was deleted after its edge was
  written — which requires actually deleting one.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks.container_assembly import (
    Candidate,
    assemble_container,
    find_dangling_edges,
)
from app.utils.container_class import MemberEvidence

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall job's service container)"
    ),
)


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped for the same reason its siblings are: `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async
    fixture would outlive the loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


async def _seed(session):
    """One container, one sport, three markets. Returns (container, ids)."""
    from app.models.models import Container, FuturesMarket, Sport

    sport = Sport(key="tennis_atp", name="ATP", active=True)
    session.add(sport)
    await session.flush()

    container = Container(
        kind="tournament",
        name="US Open 2026",
        slug="us-open-2026",
        sport_id=sport.id,
        status="live",
    )
    session.add(container)
    await session.flush()

    now = datetime.now(timezone.utc)
    markets = []
    for external_id, name in (
        ("KXATPMATCH-26SEP02SINALC", "Sinner vs Alcaraz"),
        ("KXATPGAMES-26SEP02SINALC", "Total Games: Sinner vs Alcaraz"),
        ("KXATPWINNER-26USO", "Winner of the US Open 2026"),
    ):
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            sport_id=sport.id,
            name=name,
            category="sports",
            commence_time=now + timedelta(days=1),
            status="open",
        )
        session.add(market)
        markets.append(market)
    await session.flush()
    return container, [m.id for m in markets]


def _candidates(market_ids):
    """Three members, one per class we expect to see."""
    names = {
        0: ("Sinner vs Alcaraz", "match_winner"),
        1: ("Total Games: Sinner vs Alcaraz", "prop"),
        2: ("Winner of the US Open 2026", "title"),
    }
    return [
        Candidate(
            child_type="market",
            child_id=market_id,
            source="register",
            evidence=MemberEvidence(node_type="market", name=names[i][0]),
            external_id=f"ext-{i}",
            market_source="kalshi",
        )
        for i, market_id in enumerate(market_ids)
    ]


async def _edge_rows(session, container_id):
    result = await session.execute(
        text(
            "SELECT child_id, class, source, confidence, kind "
            "FROM event_edges WHERE parent_type = 'container' "
            "AND parent_id = :id ORDER BY child_id"
        ),
        {"id": container_id},
    )
    return result.fetchall()


class TestOnePass:
    async def test_it_writes_one_edge_per_member_with_a_class(self, pg_session):
        container, market_ids = await _seed(pg_session)
        report = await assemble_container(
            pg_session, container, _candidates(market_ids)
        )
        await pg_session.commit()

        assert report.edges_written == 3
        rows = await _edge_rows(pg_session, container.id)
        assert len(rows) == 3
        assert {r[1] for r in rows} == {"match_winner", "prop", "title"}
        assert {r[2] for r in rows} == {"register"}
        assert {r[4] for r in rows} == {"contains"}
        # Ruling 048: assembly writes `contains` and nothing else.
        other = await pg_session.execute(
            text("SELECT count(*) FROM event_edges WHERE kind <> 'contains'")
        )
        assert other.scalar() == 0

    async def test_it_writes_a_receipt_carrying_the_container(self, pg_session):
        container, market_ids = await _seed(pg_session)
        await assemble_container(pg_session, container, _candidates(market_ids))
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT market_id, container_id, phase, outcome "
                "FROM market_match_receipts ORDER BY market_id"
            )
        )
        rows = result.fetchall()
        assert len(rows) == 3
        for row in rows:
            # The new column survives the round trip — #2199's lesson.
            assert row[1] == container.id
            assert row[2] == "container_assembly"
            assert row[3] == "linked"

    async def test_the_report_counts_by_class(self, pg_session):
        container, market_ids = await _seed(pg_session)
        report = await assemble_container(
            pg_session, container, _candidates(market_ids)
        )
        assert report.by_class == {"match_winner": 1, "prop": 1, "title": 1}


class TestReRunningChangesNothingNew:
    """The property that stops a nightly job doubling the hub every night."""

    async def test_a_second_pass_writes_no_new_edges(self, pg_session):
        container, market_ids = await _seed(pg_session)
        candidates = _candidates(market_ids)

        await assemble_container(pg_session, container, candidates)
        await pg_session.commit()
        first = await _edge_rows(pg_session, container.id)

        await assemble_container(pg_session, container, candidates)
        await pg_session.commit()
        second = await _edge_rows(pg_session, container.id)

        assert len(second) == len(first) == 3
        assert [r[0] for r in second] == [r[0] for r in first]

    async def test_a_reclassified_member_is_updated_in_place(self, pg_session):
        """The upsert must MOVE a member between sections, not duplicate it.

        A member whose class changes — a market renamed by the venue, a fixture
        that turns out to be doubles — has to leave its old section. An
        `ON CONFLICT DO NOTHING` would pass the test above and leave it in both.
        """
        container, market_ids = await _seed(pg_session)
        first = _candidates(market_ids)
        await assemble_container(pg_session, container, first)
        await pg_session.commit()

        moved = [
            Candidate(
                child_type="market",
                child_id=market_ids[0],
                source="register",
                evidence=MemberEvidence(
                    node_type="event",
                    name="Bopanna/Ebden vs Arevalo/Pavic",
                    max_side_size=2,
                ),
                external_id="ext-0",
                market_source="kalshi",
            )
        ]
        await assemble_container(pg_session, container, moved)
        await pg_session.commit()

        rows = await _edge_rows(pg_session, container.id)
        assert len(rows) == 3, "the member must MOVE, not appear twice"
        classes = {r[0]: r[1] for r in rows}
        assert classes[market_ids[0]] == "doubles"

    async def test_the_receipt_attempt_count_increments(self, pg_session):
        container, market_ids = await _seed(pg_session)
        candidates = _candidates(market_ids)
        await assemble_container(pg_session, container, candidates)
        await pg_session.commit()
        await assemble_container(pg_session, container, candidates)
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT attempt_count FROM market_match_receipts "
                "WHERE market_id = :id"
            ),
            {"id": market_ids[0]},
        )
        assert result.scalar() == 2


class TestAMissingChildIsReceiptedNotEdged:
    """A container cannot contain a row that does not exist."""

    async def test_a_market_id_that_does_not_resolve_writes_no_edge(self, pg_session):
        container, market_ids = await _seed(pg_session)
        ghost = Candidate(
            child_type="market",
            child_id=999_999_999,
            source="register",
            evidence=MemberEvidence(node_type="market", name="Ghost vs Nobody"),
            external_id="KXATPMATCH-26SEP02AUGKHA",
            market_source="kalshi",
        )
        report = await assemble_container(pg_session, container, [ghost])
        await pg_session.commit()

        assert report.edges_written == 0
        assert (await _edge_rows(pg_session, container.id)) == []
        assert report.rejected.get("container_child_missing") == 1

    async def test_the_missing_child_leaves_no_receipt_it_cannot_key(
        self, pg_session
    ):
        """The honest asymmetry, asserted rather than discovered later.

        `market_match_receipts.market_id` has a real FK to `futures_markets`,
        so a receipt for a market that does not exist cannot be written at all.
        The row is reported in `report.rejected` and, for non-market types, in
        `report.unresolved` — never silently dropped, but also never faked into
        a table that would refuse it.
        """
        container, _ = await _seed(pg_session)
        ghost_event = Candidate(
            child_type="event",
            child_id=888_888_888,
            source="authority_tournament_id",
            evidence=MemberEvidence(node_type="event", name="Ghost fixture"),
        )
        report = await assemble_container(pg_session, container, [ghost_event])
        await pg_session.commit()

        assert report.edges_written == 0
        assert len(report.unresolved) == 1
        assert report.unresolved[0]["child_id"] == 888_888_888

    async def test_one_bad_candidate_does_not_wipe_the_pass(self, pg_session):
        """Gotcha #42, asserted both ways: the sibling members SURVIVE."""
        container, market_ids = await _seed(pg_session)
        candidates = _candidates(market_ids) + [
            Candidate(
                child_type="market",
                child_id=999_999_999,
                source="register",
                evidence=MemberEvidence(node_type="market", name="Ghost"),
                external_id="ghost",
                market_source="kalshi",
            )
        ]
        report = await assemble_container(pg_session, container, candidates)
        await pg_session.commit()

        assert report.edges_written == 3
        assert len(await _edge_rows(pg_session, container.id)) == 3


class TestTheDanglingEdgeCheck:
    """Spec §2: part of the ship, because `child_id` carries no foreign key."""

    async def test_a_healthy_graph_reports_nothing(self, pg_session):
        container, market_ids = await _seed(pg_session)
        await assemble_container(pg_session, container, _candidates(market_ids))
        await pg_session.commit()

        assert await find_dangling_edges(pg_session) == []

    async def test_an_edge_whose_child_was_deleted_is_found(self, pg_session):
        """The case assembly's own pre-write check cannot cover.

        Assembly verifies the id before it writes, but a market can be purged
        or a twin cleanup can delete an event afterwards — and nothing in the
        schema would notice, because there is no FK to cascade. This is the
        check that buys that integrity back.
        """
        container, market_ids = await _seed(pg_session)
        await assemble_container(pg_session, container, _candidates(market_ids))
        await pg_session.commit()

        # Drop the edge's FK-free child out from under it. The receipt cascades
        # away with the market; the edge does not, which is the whole point.
        await pg_session.execute(
            text("DELETE FROM futures_markets WHERE id = :id"), {"id": market_ids[0]}
        )
        await pg_session.commit()

        findings = await find_dangling_edges(pg_session)
        assert len(findings) == 1
        assert findings[0]["child_id"] == market_ids[0]
        assert findings[0]["child_type"] == "market"

    async def test_deleting_the_container_keeps_the_receipts(self, pg_session):
        """`ON DELETE SET NULL`, exercised rather than read off the catalogue.

        The migration test asserts `confdeltype = 'n'`. This asserts the
        behaviour that setting buys: a container rebuilt after a bad assembly
        run still has the record of what it refused.
        """
        container, market_ids = await _seed(pg_session)
        await assemble_container(pg_session, container, _candidates(market_ids))
        await pg_session.commit()

        await pg_session.execute(
            text("DELETE FROM containers WHERE id = :id"), {"id": container.id}
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text(
                "SELECT count(*), count(container_id) FROM market_match_receipts"
            )
        )
        total, with_container = result.fetchone()
        assert total == 3, "the receipts must survive their container"
        assert with_container == 0, "and their container_id must be NULL, not stale"
