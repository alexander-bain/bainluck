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
        # #9651's ledger is created from its migration's own DDL, not the ORM,
        # and it references `containers` — so `drop_all` cannot drop
        # `containers` while it exists. Dropped first, unconditionally, so a
        # crashed run can never wedge every later gate on this database.
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
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
        # AND NO RECEIPT, because the FK would refuse one. This assertion is
        # here because the first version of this file asserted the opposite and
        # real Postgres refused it: `ForeignKeyViolationError … Key
        # (market_id)=(999999999) is not present in table "futures_markets"`.
        # A ghost market id is reported in `unresolved`, exactly like a ghost
        # event id.
        assert report.receipts_written == 0
        assert [u["child_id"] for u in report.unresolved] == [999_999_999]
        assert report.unresolved[0]["reject_reason"] == "container_child_missing"
        left = (
            await pg_session.execute(text("SELECT count(*) FROM market_match_receipts"))
        ).scalar()
        assert left == 0

    async def test_the_missing_child_leaves_no_receipt_it_cannot_key(self, pg_session):
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
        # The three healthy siblings keep their receipts; the ghost has none to
        # keep. Before the fix this whole pass died on the ghost's FK violation
        # — one bad candidate wiping the pass, in the very test that exists to
        # forbid it.
        assert report.receipts_written == 3
        assert len(report.unresolved) == 1


class TestTheMatchersReceiptIsKept:
    """#9217 (v3): assembly edges a market the matcher linked WITHOUT replacing
    the matcher's receipt. `market_match_receipts` is one row per market and
    last-writer-wins, so before this the container pass erased how the market
    was linked to its game."""

    async def test_a_matcher_receipt_survives_the_pass_and_the_edge_is_written(
        self, pg_session
    ):
        from app.utils.match_receipts import (
            PHASE_PASS1_TICKER,
            REJECT_NO_CANDIDATE,
            MatchReceipt,
            flush_receipts,
        )

        container, market_ids = await _seed(pg_session)
        matched = MatchReceipt(
            market_id=market_ids[0],
            source="kalshi",
            external_id="KXATPMATCH-26SEP02SINALC",
            market_name="Sinner vs Alcaraz",
            phase=PHASE_PASS1_TICKER,
            attempted_at=datetime.now(timezone.utc),
        )
        matched.reject(REJECT_NO_CANDIDATE)
        await flush_receipts(pg_session, [matched])
        await pg_session.commit()

        report = await assemble_container(
            pg_session, container, _candidates(market_ids)
        )
        await pg_session.commit()

        assert report.edges_written == 3
        assert len(await _edge_rows(pg_session, container.id)) == 3
        assert (report.receipts_written, report.receipts_preserved) == (2, 1)
        rows = dict(
            (
                await pg_session.execute(
                    text("SELECT market_id, phase FROM market_match_receipts")
                )
            ).fetchall()
        )
        assert rows[market_ids[0]] == PHASE_PASS1_TICKER
        assert rows[market_ids[1]] == rows[market_ids[2]] == "container_assembly"

    async def test_assemblys_own_receipt_is_still_refreshed(self, pg_session):
        container, market_ids = await _seed(pg_session)
        await assemble_container(pg_session, container, _candidates(market_ids))
        await pg_session.commit()

        report = await assemble_container(
            pg_session, container, _candidates(market_ids)
        )
        await pg_session.commit()

        assert (report.receipts_written, report.receipts_preserved) == (3, 0)


class TestTheCollectionRow:
    """#9217 (v3): an NFL week / MLB postseason gets ONE flat row, and a re-run
    neither doubles it nor rewrites it."""

    async def test_the_flat_bootstrap_creates_once_and_never_rewrites(self, pg_session):
        from app.tasks.container_assembly import _collection_container

        first, how = await _collection_container(
            pg_session,
            "nfl-2026-week-4",
            "NFL 2026 · Week 4",
            "season",
            None,
            None,
            apply=True,
        )
        await pg_session.commit()
        assert how == "created" and first.id is not None

        await pg_session.execute(
            text("UPDATE containers SET name = 'corrected' WHERE id = :id"),
            {"id": first.id},
        )
        again, how = await _collection_container(
            pg_session,
            "nfl-2026-week-4",
            "NFL 2026 · Week 4",
            "season",
            None,
            None,
            apply=True,
        )
        await pg_session.commit()
        assert how == "existing" and again.id == first.id
        rows = (
            await pg_session.execute(
                text("SELECT kind, name FROM containers WHERE slug = 'nfl-2026-week-4'")
            )
        ).fetchall()
        assert [tuple(r) for r in rows] == [("season", "corrected")]

    async def test_a_dry_run_writes_no_row(self, pg_session):
        from app.tasks.container_assembly import _collection_container

        stand_in, how = await _collection_container(
            pg_session,
            "mlb-2026-postseason",
            "MLB 2026 Postseason",
            "tournament",
            None,
            None,
            apply=False,
        )
        assert how == "would_create" and stand_in.id is None
        assert (
            await pg_session.execute(text("SELECT count(*) FROM containers"))
        ).scalar() == 0


class TestTheBootstrap:
    """Creating the tree is idempotent, and its undo cannot delete a live hub."""

    async def test_it_creates_a_root_and_five_draws(self, pg_session):
        from app.tasks.container_assembly import (
            apply_container_tree,
            plan_container_tree,
        )

        plan = plan_container_tree("us-open", "2026", "US Open 2026")
        out = await apply_container_tree(pg_session, plan)
        await pg_session.commit()

        assert len(out["created"]) == 6
        assert out["existing"] == []

        result = await pg_session.execute(
            text(
                "SELECT c.slug, p.slug FROM containers c "
                "LEFT JOIN containers p ON p.id = c.parent_container_id "
                "ORDER BY c.slug"
            )
        )
        rows = dict(result.fetchall())
        assert rows["us-open-2026"] is None
        assert rows["us-open-2026-mens-doubles"] == "us-open-2026"
        assert rows["us-open-2026-mixed-doubles"] == "us-open-2026"

    async def test_a_second_run_creates_nothing(self, pg_session):
        """Idempotent, so it is safe on a schedule and safe to re-run by hand."""
        from app.tasks.container_assembly import (
            apply_container_tree,
            plan_container_tree,
        )

        plan = plan_container_tree("us-open", "2026", "US Open 2026")
        await apply_container_tree(pg_session, plan)
        await pg_session.commit()
        second = await apply_container_tree(pg_session, plan)
        await pg_session.commit()

        assert second["created"] == []
        assert len(second["existing"]) == 6
        count = await pg_session.execute(text("SELECT count(*) FROM containers"))
        assert count.scalar() == 6

    async def test_a_rerun_does_not_stamp_over_an_authority_set_status(
        self, pg_session
    ):
        """D27: the authority owns `status`, not the bootstrap.

        A re-run that "helpfully" reset every draw to `scheduled` would take a
        finished tournament live again on the hub — the exact inference D27
        forbids, arriving from the opposite direction.
        """
        from app.tasks.container_assembly import (
            apply_container_tree,
            plan_container_tree,
        )

        plan = plan_container_tree("us-open", "2026", "US Open 2026")
        await apply_container_tree(pg_session, plan)
        await pg_session.execute(
            text("UPDATE containers SET status = 'final' WHERE slug = :s"),
            {"s": "us-open-2026-mixed-doubles"},
        )
        await pg_session.commit()

        await apply_container_tree(pg_session, plan)
        await pg_session.commit()

        result = await pg_session.execute(
            text("SELECT status FROM containers WHERE slug = :s"),
            {"s": "us-open-2026-mixed-doubles"},
        )
        assert result.scalar() == "final"

    async def test_the_undo_removes_only_what_it_created_and_only_if_empty(
        self, pg_session
    ):
        """D51's undo, exercised — the narrowness is the point.

        An empty draw is removed. A draw assembly has since filled is KEPT,
        because the undo must not be able to delete a working hub when someone
        runs it after a successful assembly rather than after a failed one.
        """
        from app.tasks.container_assembly import (
            BOOTSTRAP_UNDO_LINE,
            apply_container_tree,
            plan_container_tree,
        )

        plan = plan_container_tree("us-open", "2026", "US Open 2026")
        out = await apply_container_tree(pg_session, plan)
        await pg_session.commit()

        populated = out["ids"]["us-open-2026-mens-doubles"]
        await pg_session.execute(
            text(
                "INSERT INTO event_edges (parent_id, parent_type, child_id, "
                " child_type, kind, class, source, confidence) "
                "VALUES (:pid, 'container', 1, 'event', 'contains', "
                " 'doubles', 'venue_grouping', 1.0)"
            ),
            {"pid": populated},
        )
        await pg_session.commit()

        await pg_session.execute(
            text(BOOTSTRAP_UNDO_LINE), {"created_slugs": out["created"]}
        )
        await pg_session.commit()

        remaining = await pg_session.execute(
            text("SELECT slug FROM containers ORDER BY slug")
        )
        assert [r[0] for r in remaining.fetchall()] == ["us-open-2026-mens-doubles"]

    async def test_the_undo_leaves_containers_it_did_not_create(self, pg_session):
        """Scoped to the `created` list, never to everything that is empty.

        A container somebody else made — by hand, or by an earlier bootstrap —
        is not this run's to remove, and passing `existing` would remove it.
        """
        from app.tasks.container_assembly import (
            BOOTSTRAP_UNDO_LINE,
            apply_container_tree,
            plan_container_tree,
        )
        from app.models.models import Container

        pg_session.add(
            Container(kind="award_show", name="The Oscars", slug="oscars-2027")
        )
        await pg_session.flush()

        out = await apply_container_tree(
            pg_session, plan_container_tree("us-open", "2026", "US Open 2026")
        )
        await pg_session.commit()

        await pg_session.execute(
            text(BOOTSTRAP_UNDO_LINE), {"created_slugs": out["created"]}
        )
        await pg_session.commit()

        remaining = await pg_session.execute(text("SELECT slug FROM containers"))
        assert [r[0] for r in remaining.fetchall()] == ["oscars-2027"]


class TestTheSanctionedAnchorWriter:
    """CERT-2006's follow-up, and the reason it is a WRITER not a validator.

    The unique index is `(provider, sport, id_kind, provider_id) NULLS NOT
    DISTINCT`, which makes NULL one namespace — but `''` is not NULL and
    `'Tennis'` is not `'tennis'`, so a caller spelling "no sport" its own way
    reopens the hole the index was widened to close. A validator nobody is
    obliged to call is a validator that gets skipped; `claim_container_anchor`
    is the obligation, and these are the tests that say it folds.
    """

    async def test_an_empty_sport_string_is_stored_as_null(self, pg_session):
        """`''` must not become a THIRD namespace beside NULL and real sports."""
        from app.tasks.container_assembly import claim_container_anchor

        container, _ = await _seed(pg_session)
        assert await claim_container_anchor(
            pg_session,
            container_id=container.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport="   ",
        )
        await pg_session.commit()

        result = await pg_session.execute(
            text("SELECT sport FROM container_provider_anchors")
        )
        assert result.scalar() is None

    async def test_two_spellings_of_no_sport_collide_rather_than_coexist(
        self, pg_session
    ):
        """The defect this writer exists to prevent, end to end.

        Without the fold, `sport=None` and `sport=''` would be two namespaces
        and BOTH claims would succeed — two containers owning one ESPN id, with
        the unique index reporting no problem at all.
        """
        from app.tasks.container_assembly import (
            AnchorCollision,
            claim_container_anchor,
        )

        container, _ = await _seed(pg_session)
        from app.models.models import Container

        other = Container(kind="tournament", name="Other", slug="other-2026")
        pg_session.add(other)
        await pg_session.flush()

        await claim_container_anchor(
            pg_session,
            container_id=container.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport=None,
        )
        with pytest.raises(AnchorCollision):
            await claim_container_anchor(
                pg_session,
                container_id=other.id,
                provider="espn",
                provider_id="1234",
                id_kind="tournament",
                sport="",
            )

    async def test_case_variants_collide_rather_than_coexist(self, pg_session):
        from app.tasks.container_assembly import (
            AnchorCollision,
            claim_container_anchor,
        )
        from app.models.models import Container

        container, _ = await _seed(pg_session)
        other = Container(kind="tournament", name="Other", slug="other-2026")
        pg_session.add(other)
        await pg_session.flush()

        await claim_container_anchor(
            pg_session,
            container_id=container.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport="tennis",
        )
        with pytest.raises(AnchorCollision):
            await claim_container_anchor(
                pg_session,
                container_id=other.id,
                provider="espn",
                provider_id="1234",
                id_kind="tournament",
                sport="  TENNIS  ",
            )

    async def test_two_sports_still_coexist(self, pg_session):
        """The writer must not over-collapse — CERT-2001's finding still holds."""
        from app.tasks.container_assembly import claim_container_anchor
        from app.models.models import Container

        container, _ = await _seed(pg_session)
        other = Container(kind="tournament", name="Golf", slug="golf-2026")
        pg_session.add(other)
        await pg_session.flush()

        assert await claim_container_anchor(
            pg_session,
            container_id=container.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport="tennis",
        )
        assert await claim_container_anchor(
            pg_session,
            container_id=other.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport="Golf",
        )
        await pg_session.commit()
        result = await pg_session.execute(
            text("SELECT count(*) FROM container_provider_anchors")
        )
        assert result.scalar() == 2

    async def test_the_same_owner_reclaiming_is_idempotent_not_a_collision(
        self, pg_session
    ):
        """A nightly re-discovery re-claims its own anchors. That is not a clash.

        Returns False (nothing written) rather than raising, so a re-run does
        not have to distinguish "already mine" from "someone else's" at every
        call site — which is where a caller would be tempted to swallow the
        exception and lose the real collision with it.
        """
        from app.tasks.container_assembly import claim_container_anchor

        container, _ = await _seed(pg_session)
        kwargs = dict(
            container_id=container.id,
            provider="espn",
            provider_id="1234",
            id_kind="tournament",
            sport="tennis",
        )
        assert await claim_container_anchor(pg_session, **kwargs) is True
        assert await claim_container_anchor(pg_session, **kwargs) is False
        await pg_session.commit()
        result = await pg_session.execute(
            text("SELECT count(*) FROM container_provider_anchors")
        )
        assert result.scalar() == 1

    async def test_an_unknown_provider_is_refused_before_the_insert(self, pg_session):
        from app.utils.container_graph import ContainerVocabularyError
        from app.tasks.container_assembly import claim_container_anchor

        container, _ = await _seed(pg_session)
        with pytest.raises(ContainerVocabularyError):
            await claim_container_anchor(
                pg_session,
                container_id=container.id,
                provider="espn_api",
                provider_id="1234",
                id_kind="tournament",
            )


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
            text("SELECT count(*), count(container_id) FROM market_match_receipts")
        )
        total, with_container = result.fetchone()
        assert total == 3, "the receipts must survive their container"
        assert with_container == 0, "and their container_id must be NULL, not stale"


# ---------------------------------------------------------------------------
# The whole declared pass, end to end (#2927 Phase 2)
# ---------------------------------------------------------------------------


async def _seed_tour_markets(session):
    """Six Kalshi rows: four this edition, two the tour after it.

    The dates are the production shapes measured 2026-09-06 — every stored
    `commence_time` sits exactly 14 days after the market's own ticker date,
    because Kalshi's is the CLOSE time. That is what makes this a real test of
    the pass rather than of a fixture that agrees with it: if the window ever
    reads the column again, the two US Open singles rows below leave the
    tournament they were played in.
    """
    from app.models.models import FuturesMarket, Sport

    sport = Sport(key="tennis_atp", name="ATP", active=True)
    session.add(sport)
    await session.flush()

    rows = [
        # (external_id, name, ticker date, stored commence = ticker + 14d)
        (
            "KXWTAMATCH-26SEP06SWIZHE-SWI",
            "Iga Swiatek wins",
            datetime(2026, 9, 20, 15, tzinfo=timezone.utc),
        ),
        (
            "KXWTAMATCH-26SEP06SWIZHE-ZHE",
            "Qinwen Zheng wins",
            datetime(2026, 9, 20, 15, tzinfo=timezone.utc),
        ),
        (
            "KXATPMATCH-26SEP07GEAVAN-GEA",
            "Gea wins",
            datetime(2026, 9, 21, 15, tzinfo=timezone.utc),
        ),
        (
            "KXMIXEDDOUBLESMATCH-26AUG25ABCDEF-A",
            "Mixed pair A wins",
            datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
        ),
        # The tour AFTER the US Open: the 42 KXATPDOUBLES rows measured on
        # production were all 09-18 -> 09-20.
        (
            "KXATPDOUBLES-26SEP18AAABBB-A",
            "Next tour pair A",
            datetime(2026, 10, 2, 15, tzinfo=timezone.utc),
        ),
        (
            "KXATPDOUBLES-26SEP18AAABBB-B",
            "Next tour pair B",
            datetime(2026, 10, 2, 15, tzinfo=timezone.utc),
        ),
    ]
    ids = {}
    for external_id, name, commence in rows:
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            sport_id=sport.id,
            name=name,
            category="sports",
            commence_time=commence,
            resolution_date=commence,
            status="open",
        )
        session.add(market)
        await session.flush()
        ids[external_id] = market.id
    await session.flush()
    return ids


class TestTheDeclaredPass:
    """`run_declared_assembly` against a real schema, from empty."""

    async def test_the_tables_probe_answers_yes_on_a_migrated_database(
        self, pg_session
    ):
        from app.tasks.container_assembly import containers_tables_present

        assert await containers_tables_present(pg_session) is True

    async def test_it_bootstraps_claims_and_assembles_in_one_pass(self, pg_session):
        from app.tasks.container_assembly import run_declared_assembly
        from app.utils.container_tournaments import US_OPEN_2026

        ids = await _seed_tour_markets(pg_session)

        report = await run_declared_assembly(pg_session, US_OPEN_2026, apply=True)

        # The tree exists, with the window that makes membership decidable.
        created = set(report["bootstrap"]["created"])
        assert "us-open-2026" in created
        assert "us-open-2026-mens-doubles" in created
        window = (
            await pg_session.execute(
                text(
                    "SELECT window_start, window_end FROM containers "
                    "WHERE slug = 'us-open-2026-mens-doubles'"
                )
            )
        ).fetchone()
        assert window[0] == US_OPEN_2026.window_start
        assert window[1] == US_OPEN_2026.window_end

        # Every declared id is claimed, once, with its provenance.
        assert report["anchors"]["claimed"] == len(US_OPEN_2026.anchors)
        assert report["anchors"]["collisions"] == []

        # THE MEMBERSHIP ANSWER. The three US Open singles/mixed rows are
        # members; next week's two doubles rows are not.
        edged = {
            int(r[0])
            for r in (
                await pg_session.execute(
                    text(
                        "SELECT child_id FROM event_edges "
                        "WHERE parent_type = 'container' AND kind = 'contains'"
                    )
                )
            ).fetchall()
        }
        assert ids["KXWTAMATCH-26SEP06SWIZHE-SWI"] in edged, (
            "Swiatek-Zheng was played 9/6 and its stored commence_time is 9/20; "
            "the ticker is what keeps it in the tournament it was played in"
        )
        assert ids["KXATPMATCH-26SEP07GEAVAN-GEA"] in edged
        assert ids["KXMIXEDDOUBLESMATCH-26AUG25ABCDEF-A"] in edged
        assert ids["KXATPDOUBLES-26SEP18AAABBB-A"] not in edged
        assert ids["KXATPDOUBLES-26SEP18AAABBB-B"] not in edged

        # And the refusal is COUNTED, not silent.
        doubles = [
            c for c in report["containers"] if c["slug"] == "us-open-2026-mens-doubles"
        ][0]
        assert doubles["venue"]["outside_window"] == 2
        assert doubles["venue"]["candidates"] == 0

        assert report["terminal"] == "complete"
        # Four in-window rows: both Swiatek-Zheng legs, the men's 9/7 leg, and
        # the fan-week mixed row. The two 09-18 doubles rows are the refusal.
        assert report["members"] == 4

    async def test_a_second_pass_converges_instead_of_doubling(self, pg_session):
        """Hourly means idempotent, or the hub grows without bound."""
        from app.tasks.container_assembly import run_declared_assembly
        from app.utils.container_tournaments import US_OPEN_2026

        await _seed_tour_markets(pg_session)
        first = await run_declared_assembly(pg_session, US_OPEN_2026, apply=True)
        second = await run_declared_assembly(pg_session, US_OPEN_2026, apply=True)

        assert second["bootstrap"]["created"] == []
        assert second["anchors"]["claimed"] == 0
        assert second["anchors"]["already"] == len(US_OPEN_2026.anchors)
        assert second["members"] == first["members"]

        total = (
            await pg_session.execute(
                text("SELECT count(*) FROM event_edges WHERE parent_type = 'container'")
            )
        ).scalar()
        assert total == first["members"]

    async def test_a_pass_with_nothing_to_find_is_partial_not_complete(
        self, pg_session
    ):
        """gotcha #53: "it returned" is not "it worked"."""
        from app.tasks.container_assembly import run_declared_assembly
        from app.utils.container_tournaments import US_OPEN_2026

        report = await run_declared_assembly(pg_session, US_OPEN_2026, apply=True)

        assert report["members"] == 0
        assert report["terminal"] == "partial"
        assert report["reason"] == "no_member_found"

    async def test_the_honey_deuce_series_joins_on_its_declared_scope(self, pg_session):
        """A whole-series anchor declared `edition` is not window-tested.

        Its one market's only stored date is a 2027 expiry and its ticker
        (`01JAN27`) is not a game date at all, so every window test refuses it.
        The declaration is what admits it, and this is the test that the
        declaration is actually honoured rather than decorative.
        """
        from app.models.models import FuturesMarket, Sport
        from app.tasks.container_assembly import run_declared_assembly
        from app.utils.container_tournaments import US_OPEN_2026

        sport = Sport(key="tennis_atp", name="ATP", active=True)
        pg_session.add(sport)
        await pg_session.flush()
        market = FuturesMarket(
            source="kalshi",
            external_id="KXHONEYDEUCE-01JAN27-T400000",
            sport_id=sport.id,
            name="Number of Honey Deuces sold at the US Open",
            category="sports",
            commence_time=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            resolution_date=datetime(2027, 1, 1, 4, 59, tzinfo=timezone.utc),
            status="open",
        )
        pg_session.add(market)
        await pg_session.flush()

        report = await run_declared_assembly(pg_session, US_OPEN_2026, apply=True)

        root = [c for c in report["containers"] if c["slug"] == "us-open-2026"][0]
        assert root["venue"]["candidates"] == 1
        assert root["by_anchor"][0]["bounded_by_window"] is False
        edged = (
            await pg_session.execute(
                text("SELECT child_id FROM event_edges WHERE parent_type = 'container'")
            )
        ).scalar()
        assert edged == market.id


# ---------------------------------------------------------------------------
# #9651 — a corrected hub stays corrected
# ---------------------------------------------------------------------------
#
# Only a server can grade these: the non-resurrection guarantee is a row lock
# plus READ COMMITTED re-reading the ledger after the lock is granted, and the
# one-snapshot read is a property of one SQL statement. A session double would
# agree with whatever statement the code built.


@pytest.fixture
async def corrected_session(pg_session):
    """`pg_session` with #9651's migration applied from its own statements."""
    from app.utils.container_corrections import DOWNGRADE_STATEMENTS, UPGRADE_STATEMENTS

    for statement in UPGRADE_STATEMENTS:
        await pg_session.execute(text(statement))
    await pg_session.commit()
    try:
        yield pg_session
    finally:
        await pg_session.rollback()
        for statement in DOWNGRADE_STATEMENTS:
            await pg_session.execute(text(statement))
        await pg_session.commit()


def _plain(container):
    """Gotcha #6: an async rollback expires ORM rows even with
    `expire_on_commit=False`, and these tests roll back after a refusal."""
    from types import SimpleNamespace

    return SimpleNamespace(id=container.id, slug=container.slug)


async def _revision(session, container_id):
    return (
        await session.execute(
            text("SELECT membership_revision FROM containers WHERE id = :id"),
            {"id": container_id},
        )
    ).scalar()


async def _ledger_count(session):
    return (
        await session.execute(text("SELECT count(*) FROM container_corrections"))
    ).scalar()


def _withdraw_kwargs(container_id, market_id, **extra):
    return dict(
        container_id=container_id,
        child_type="market",
        child_id=market_id,
        reason="wrong edition: the 2025 winner market",
        actor="test",
        **extra,
    )


class TestCorrectionsBeforeTheMigration:
    async def test_an_unmigrated_database_runs_the_old_pass(self, pg_session):
        """No ledger, no rule to honour: the pass must be exactly the old one."""
        container, market_ids = await _seed(pg_session)
        report = await assemble_container(
            pg_session, container, _candidates(market_ids)
        )
        await pg_session.commit()

        assert report.corrections == "absent"
        assert report.revision is None
        assert report.edges_written == 3


class TestAWithdrawnMemberStaysWithdrawn:
    async def test_the_next_pass_does_not_resurrect_it(self, corrected_session):
        from app.utils.container_corrections import WITHHELD_WITHDRAWN, withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await assemble_container(s, container, _candidates(market_ids))
        await s.commit()

        result = await withdraw_member(
            s, **_withdraw_kwargs(container.id, market_ids[2])
        )
        await s.commit()
        assert result.applied and result.edges_removed == 1

        for _ in range(2):  # the pass after, and the pass after that
            report = await assemble_container(s, container, _candidates(market_ids))
            await s.commit()
            assert report.corrections == "honoured"
            assert [w["child_id"] for w in report.withdrawn] == [market_ids[2]]
            assert report.rejected[WITHHELD_WITHDRAWN] == 1
            assert [r[0] for r in await _edge_rows(s, container.id)] == market_ids[:2]

    async def test_a_second_withdrawal_is_a_retry_not_a_new_decision(
        self, corrected_session
    ):
        from app.utils.container_corrections import withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await assemble_container(s, container, _candidates(market_ids))
        first = await withdraw_member(
            s, **_withdraw_kwargs(container.id, market_ids[0])
        )
        again = await withdraw_member(
            s, **_withdraw_kwargs(container.id, market_ids[0])
        )
        await s.commit()

        assert first.applied and not again.applied
        assert again.revision == first.revision
        assert await _ledger_count(s) == 1

    async def test_an_edge_written_behind_the_ledgers_back_is_removed(
        self, corrected_session
    ):
        """A legacy writer, an undo replay, a hand insert — the pass cleans it."""
        from app.models.models import EventEdge
        from app.utils.container_corrections import withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await withdraw_member(s, **_withdraw_kwargs(container.id, market_ids[1]))
        s.add(
            EventEdge(
                parent_type="container",
                parent_id=container.id,
                child_type="market",
                child_id=market_ids[1],
                kind="contains",
                edge_class="prop",
                source="register",
                confidence=1,
            )
        )
        await s.commit()

        report = await assemble_container(s, container, _candidates(market_ids))
        await s.commit()

        assert report.purged_withdrawn == 1
        assert market_ids[1] not in [r[0] for r in await _edge_rows(s, container.id)]


class TestLegitimateReadmission:
    async def test_readmit_writes_no_edge_and_the_next_pass_reproves_it(
        self, corrected_session
    ):
        from app.utils.container_corrections import readmit_member, withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await assemble_container(s, container, _candidates(market_ids))
        await withdraw_member(s, **_withdraw_kwargs(container.id, market_ids[2]))
        await s.commit()

        lifted = await readmit_member(
            s,
            container_id=container.id,
            child_type="market",
            child_id=market_ids[2],
            reason="it was the 2026 market after all",
            actor="test",
        )
        await s.commit()
        assert lifted.applied
        assert len(await _edge_rows(s, container.id)) == 2, "a correction never adds"

        report = await assemble_container(s, container, _candidates(market_ids))
        await s.commit()
        assert report.withdrawn == []
        assert report.added == 1
        assert len(await _edge_rows(s, container.id)) == 3

    async def test_readmit_without_evidence_stays_out(self, corrected_session):
        from app.utils.container_corrections import readmit_member, withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await assemble_container(s, container, _candidates(market_ids))
        await withdraw_member(s, **_withdraw_kwargs(container.id, market_ids[2]))
        await readmit_member(
            s,
            container_id=container.id,
            child_type="market",
            child_id=market_ids[2],
            reason="lifted",
            actor="test",
        )
        await s.commit()

        await assemble_container(s, container, _candidates(market_ids[:2]))
        await s.commit()
        assert [r[0] for r in await _edge_rows(s, container.id)] == market_ids[:2]


class TestStaleRevisions:
    async def test_a_correction_decided_on_an_old_revision_is_refused(
        self, corrected_session
    ):
        from app.utils.container_corrections import StaleRevision, withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        container = _plain(container)
        await assemble_container(s, container, _candidates(market_ids))
        await s.commit()
        seen = await _revision(s, container.id)
        assert seen == 1, "the first pass added members, so it moved the revision"

        await assemble_container(s, container, _candidates(market_ids))
        await s.commit()
        assert await _revision(s, container.id) == seen, "an unchanged pass does not"

        await withdraw_member(s, **_withdraw_kwargs(container.id, market_ids[0]))
        await s.commit()

        with pytest.raises(StaleRevision):
            await withdraw_member(
                s,
                **_withdraw_kwargs(container.id, market_ids[1], expected_revision=seen),
            )
        await s.rollback()
        assert await _ledger_count(s) == 1
        assert market_ids[1] in [r[0] for r in await _edge_rows(s, container.id)]

    async def test_a_pass_that_gathered_before_a_withdrawal_cannot_write_it_back(
        self, corrected_session
    ):
        """THE RACE: a withdrawal holds the lock while a pass is about to write.

        The pass's candidates were gathered before the decision existed. It
        must block on the container lock, then read the committed ledger — not
        write the member back from its stale list.
        """
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.utils.container_corrections import withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await assemble_container(s, container, _candidates(market_ids))
        await s.commit()
        stale_candidates = _candidates(market_ids)  # gathered NOW

        Session = async_sessionmaker(s.bind, expire_on_commit=False)
        async with Session() as decider, Session() as assembler:
            await decider.execute(text("SET lock_timeout = '20s'"))
            await assembler.execute(text("SET lock_timeout = '20s'"))

            await withdraw_member(
                decider, **_withdraw_kwargs(container.id, market_ids[2])
            )
            # The decider holds the lock, uncommitted. The pass must wait.
            pass_task = asyncio.create_task(
                assemble_container(assembler, container, stale_candidates)
            )
            await asyncio.sleep(1.0)
            assert not pass_task.done(), "the pass did not wait for the container lock"

            await decider.commit()
            report = await asyncio.wait_for(pass_task, timeout=20)
            await assembler.commit()

        assert [w["child_id"] for w in report.withdrawn] == [market_ids[2]]
        assert [r[0] for r in await _edge_rows(s, container.id)] == market_ids[:2]

    async def test_a_withdrawal_arriving_mid_pass_waits_then_removes_the_edge(
        self, corrected_session
    ):
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.utils.container_corrections import withdraw_member

        s = corrected_session
        container, market_ids = await _seed(s)
        await s.commit()

        Session = async_sessionmaker(s.bind, expire_on_commit=False)
        async with Session() as decider, Session() as assembler:
            await decider.execute(text("SET lock_timeout = '20s'"))
            await assembler.execute(text("SET lock_timeout = '20s'"))

            await assemble_container(assembler, container, _candidates(market_ids))
            # The pass holds the lock, uncommitted. The withdrawal must wait.
            decision = asyncio.create_task(
                withdraw_member(
                    decider, **_withdraw_kwargs(container.id, market_ids[2])
                )
            )
            await asyncio.sleep(1.0)
            assert not decision.done(), "the withdrawal did not wait for the pass"

            await assembler.commit()
            result = await asyncio.wait_for(decision, timeout=20)
            await decider.commit()

        assert result.applied and result.edges_removed == 1
        assert [r[0] for r in await _edge_rows(s, container.id)] == market_ids[:2]


class TestRevisionsCoverTheDraws:
    async def test_a_change_inside_a_draw_moves_the_hubs_revision(
        self, corrected_session
    ):
        from app.models.models import Container
        from app.utils.container_corrections import withdraw_member

        s = corrected_session
        root, market_ids = await _seed(s)
        draw = Container(
            kind="tournament",
            name="US Open 2026 — Men's Singles",
            slug="us-open-2026-mens-singles",
            status="live",
            parent_container_id=root.id,
        )
        s.add(draw)
        await s.commit()

        before = await _revision(s, root.id)
        await assemble_container(s, draw, _candidates(market_ids[:1]))
        await s.commit()
        assert await _revision(s, root.id) == before + 1

        await withdraw_member(s, **_withdraw_kwargs(draw.id, market_ids[0]))
        await s.commit()
        assert await _revision(s, root.id) == before + 2
        assert await _revision(s, draw.id) == 2


class TestTheReadContract:
    async def test_every_publication_state_reads_safely(self, corrected_session):
        from app.utils.container_corrections import (
            NothingToPublish,
            publish_container,
            read_published,
            withdraw_member,
            withdraw_publication,
        )

        s = corrected_session
        container, market_ids = await _seed(s)
        container = _plain(container)
        await s.commit()

        assert (await read_published(s, "no-such-hub")).state == "unavailable"
        with pytest.raises(NothingToPublish):
            await publish_container(
                s, container_id=container.id, reason="go", actor="test"
            )
        await s.rollback()

        await assemble_container(s, container, _candidates(market_ids))
        await s.commit()
        unpublished = await read_published(s, container.slug)
        assert unpublished.state == "unpublished" and unpublished.members == []

        await publish_container(s, container_id=container.id, reason="go", actor="test")
        await s.commit()
        published = await read_published(s, container.slug)
        assert published.state == "published"
        assert sorted(m["id"] for m in published.members) == sorted(market_ids)
        assert published.revision == await _revision(s, container.id)

        await withdraw_publication(
            s, container_id=container.id, reason="wrong week", actor="test"
        )
        await s.commit()
        withdrawn = await read_published(s, container.slug)
        assert withdrawn.state == "withdrawn" and withdrawn.members == []
        assert len(await _edge_rows(s, container.id)) == 3, "membership is kept"

        await publish_container(
            s, container_id=container.id, reason="fixed", actor="test"
        )
        for market_id in market_ids:
            await withdraw_member(s, **_withdraw_kwargs(container.id, market_id))
        await s.commit()
        assert (await read_published(s, container.slug)).state == "empty"

    async def test_the_upgrade_is_rerunnable(self, corrected_session):
        from app.utils.container_corrections import UPGRADE_STATEMENTS

        for statement in UPGRADE_STATEMENTS:
            await corrected_session.execute(text(statement))
        await corrected_session.commit()


# ---------------------------------------------------------------------------
# #9649 — withdraw a published hub's winner edges, and undo it exactly
# ---------------------------------------------------------------------------
#
# The operator's SQL (row locks, `to_jsonb` preimages, catalog-typed re-insert
# with explicit ids, the FK on receipt_id) is only gradable on a server. Two
# hubs shaped like Week 4/5: game cards, Kalshi + Polymarket winner duels (one
# game with two Polymarket winners), and the controls that must stay — a "1H
# Moneyline" segment winner, a spread duel and the Polymarket field wrapper.


def _member_options(**changes):
    from scripts.collection_publication import Options

    base = dict(operation="withdraw-members")
    base.update(changes)
    return Options(**base)


def _member_apply(manifest_or_backup, revisions, operation="withdraw-members"):
    key = "manifest" if operation == "withdraw-members" else "backup"
    return _member_options(
        operation=operation,
        apply=True,
        restore_from_ledger=operation == "readmit-members",
        hub_revisions=tuple(revisions.items()),
        actor="authority-test",
        reason="#9649 winner duplicates of the game card",
        evidence={"review": "test"},
        **{key: str(manifest_or_backup)},
    )


async def _full_rows(session, edge_ids):
    from scripts.collection_publication import _preimages

    await session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    rows = await _preimages(session, edge_ids)
    await session.rollback()
    return rows


async def _market_edge_ids(session, container_id):
    rows = await session.execute(
        text(
            "SELECT child_id FROM event_edges WHERE parent_type = 'container' "
            "AND parent_id = :cid AND kind = 'contains' AND child_type = 'market' "
            "ORDER BY child_id"
        ),
        {"cid": container_id},
    )
    return [r[0] for r in rows.fetchall()]


async def _event_count(session, container_id):
    return (
        await session.execute(
            text(
                "SELECT count(*) FROM event_edges WHERE parent_type = 'container' "
                "AND parent_id = :cid AND kind = 'contains' AND child_type = 'event'"
            ),
            {"cid": container_id},
        )
    ).scalar()


@pytest.fixture
async def week_hubs(corrected_session, tmp_path):
    """Two published NFL-week hubs, their manifest, and a session factory."""
    import json
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import (
        Container,
        Event,
        EventEdge,
        FuturesMarket,
        MarketMatchReceipt,
        Sport,
    )
    from app.utils.container_corrections import publish_container

    s = corrected_session
    sport = Sport(key="americanfootball_nfl", name="NFL", active=True)
    s.add(sport)
    await s.flush()
    now = datetime.now(timezone.utc)
    hubs, targets, controls, games, pins = {}, [], [], {}, {}
    layout = {
        "nfl-2026-week-4": [
            ("PIT Steelers vs CLE Browns", "Steelers vs. Browns", 1),
            ("IND Colts vs WAS Commanders", "Colts vs. Commanders", 1),
        ],
        "nfl-2026-week-5": [("CHI Bears vs GB Packers", "Bears vs. Packers", 2)],
    }
    receipt_market = None
    for slug, fixtures in layout.items():
        hub = Container(
            kind="season", name=slug, slug=slug, sport_id=sport.id, status="scheduled"
        )
        s.add(hub)
        await s.flush()
        hubs[slug] = hub.id
        games[hub.id] = []
        for kalshi_name, poly_name, poly_winners in fixtures:
            game = Event(
                sport_id=sport.id,
                home_team_name=kalshi_name.split(" vs ")[1],
                away_team_name=kalshi_name.split(" vs ")[0],
                commence_time=now + timedelta(days=2),
                status="scheduled",
            )
            s.add(game)
            await s.flush()
            games[hub.id].append(game.id)
            s.add(
                EventEdge(
                    parent_type="container",
                    parent_id=hub.id,
                    child_type="event",
                    child_id=game.id,
                    kind="contains",
                    edge_class="match_winner",
                    source="authority_tournament_id",
                    confidence=1,
                )
            )
            rows = [("kalshi", f"KXNFLGAME-{game.id}", kalshi_name, "duel", True)]
            rows += [
                ("polymarket", f"0xwin{game.id}{n}", poly_name, "duel", True)
                for n in range(poly_winners)
            ]
            rows += [
                (
                    "polymarket",
                    f"0x1h{game.id}",
                    f"1H Moneyline: {poly_name}",
                    "duel",
                    False,
                ),
                ("polymarket", f"0xsp{game.id}", "Spread: Home (-2.5)", "duel", False),
                ("polymarket", f"0xfield{game.id}", poly_name, "field", False),
            ]
            for source, external_id, name, shape, is_target in rows:
                market = FuturesMarket(
                    source=source,
                    external_id=external_id,
                    sport_id=sport.id,
                    name=name,
                    category="sports",
                    market_type=shape,
                    event_id=game.id,
                    commence_time=now + timedelta(days=2),
                    status="open",
                )
                s.add(market)
                await s.flush()
                receipt_id = None
                if is_target and receipt_market is None:
                    receipt = MarketMatchReceipt(
                        market_id=market.id,
                        source=source,
                        phase="container",
                        outcome="linked",
                        first_attempted_at=now,
                        last_attempted_at=now,
                        attempt_count=1,
                    )
                    s.add(receipt)
                    await s.flush()
                    receipt_market, receipt_id = market.id, receipt.id
                edge = EventEdge(
                    parent_type="container",
                    parent_id=hub.id,
                    child_type="market",
                    child_id=market.id,
                    kind="contains",
                    edge_class="match_winner" if is_target else "prop",
                    source="venue_grouping",
                    confidence=0.875,
                    receipt_id=receipt_id,
                )
                s.add(edge)
                await s.flush()
                record = dict(
                    container_id=hub.id,
                    container_slug=slug,
                    edge_id=edge.id,
                    edge_class=edge.edge_class,
                    child_type="market",
                    market_id=market.id,
                    venue=source,
                    market_type=shape,
                    event_id=game.id,
                    external_id=external_id,
                )
                (targets if is_target else controls).append(record)
        await s.commit()
        await publish_container(s, container_id=hub.id, reason="go", actor="test")
        await s.commit()
    ledger = (
        await s.execute(text("SELECT id, container_id FROM container_corrections"))
    ).fetchall()
    for slug, cid in hubs.items():
        hub_targets = [t for t in targets if t["container_id"] == cid]
        for t in hub_targets:
            t["expected_revision"] = await _revision(s, cid)
        pins[str(cid)] = {
            "slug": slug,
            "publication_state": "published",
            "membership_revision": await _revision(s, cid),
            "events": len(games[cid]),
            "market_edges": len(await _market_edge_ids(s, cid)),
            "targets": len(hub_targets),
            "ledger_rows": [r[0] for r in ledger if r[1] == cid],
        }
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"issue": 9649, "pins": pins, "targets": targets}))
    engine = create_async_engine(DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SimpleNamespace(
            session=s,
            factory=factory,
            hubs=hubs,
            games=games,
            pins=pins,
            targets=targets,
            controls=controls,
            manifest=manifest,
            receipt_market=receipt_market,
            tmp=tmp_path,
        )
    finally:
        await engine.dispose()


def _revisions(world, bump=0):
    return {cid: 1 + bump for cid in world.hubs.values()}


class TestMemberWithdrawPreview:
    async def test_default_preview_reads_every_target_and_writes_nothing(
        self, week_hubs
    ):
        from scripts.collection_publication import run_members

        w = week_hubs
        before = await _ledger_count(w.session)
        doc, code = await run_members(
            _member_options(manifest=str(w.manifest)), w.factory
        )
        assert code == 0 and doc["status"] == "preview" and doc["committed_hubs"] == []
        week4, week5 = doc["hubs"]
        assert len(week4["targets"]) == 4 and len(week5["targets"]) == 3
        assert week4["would_be_revision"] == 1 + 4
        assert all(t["preimage"]["confidence"] == "0.875" for t in week4["targets"])
        assert week4["receipt_kind"] == "preview" and week4["undo"] is None
        assert await _ledger_count(w.session) == before
        for cid in w.hubs.values():
            assert await _revision(w.session, cid) == 1
        assert len(await _market_edge_ids(w.session, w.hubs["nfl-2026-week-4"])) == 10


class TestMemberWithdrawApply:
    async def test_apply_removes_exactly_the_targets_and_records_full_preimages(
        self, week_hubs
    ):
        import json

        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        target_ids = [t["edge_id"] for t in w.targets]
        rows_before = await _full_rows(s, target_ids)
        doc, code = await run_members(
            _member_apply(w.manifest, _revisions(w)), w.factory
        )
        assert code == 0 and doc["status"] == "applied", doc
        assert doc["committed_hubs"] == sorted(w.hubs.values())
        for receipt in doc["hubs"]:
            cid = receipt["container_id"]
            n = len(receipt["targets"])
            assert receipt["committed"] is True
            assert receipt["pre_revision"] == 1 and receipt["post_revision"] == 1 + n
            assert [t["revision_after"] for t in receipt["targets"]] == list(
                range(2, 2 + n)
            )
            assert await _revision(s, cid) == 1 + n
            assert await _event_count(s, cid) == len(w.games[cid])
            for t in receipt["targets"]:
                assert t["preimage"] == rows_before[t["edge_id"]]
        assert await _full_rows(s, target_ids) == {}
        kept = {c["market_id"] for c in w.controls}
        for cid in w.hubs.values():
            assert (
                set(await _market_edge_ids(s, cid))
                == {c["market_id"] for c in w.controls if c["container_id"] == cid}
                and kept
            )
        ledger = (
            await s.execute(
                text(
                    "SELECT scope, action, child_id, evidence FROM container_corrections "
                    "WHERE scope = 'member' ORDER BY id"
                )
            )
        ).fetchall()
        assert len(ledger) == len(w.targets)
        evidence = {r[2]: r[3] for r in ledger}
        receipt_target = next(
            t for t in w.targets if t["market_id"] == w.receipt_market
        )
        recorded = evidence[w.receipt_market]
        recorded = json.loads(recorded) if isinstance(recorded, str) else recorded
        assert recorded["preimage"] == rows_before[receipt_target["edge_id"]]
        assert recorded["preimage"]["receipt_id"] is not None
        assert recorded["classifier"]["result"] is True

    async def test_withdrawals_survive_a_recurring_assembly_pass(self, week_hubs):
        """Even a pass from code that still proposes winners cannot re-add them."""
        from types import SimpleNamespace

        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        await run_members(_member_apply(w.manifest, _revisions(w)), w.factory)
        cid = w.hubs["nfl-2026-week-4"]
        proposed = [t for t in w.targets if t["container_id"] == cid]
        candidates = [
            Candidate(
                child_type="market",
                child_id=t["market_id"],
                source="venue_grouping",
                evidence=MemberEvidence(node_type="market", name="Steelers vs. Browns"),
                external_id=t["external_id"],
                market_source=t["venue"],
            )
            for t in proposed
        ]
        report = await assemble_container(
            s, SimpleNamespace(id=cid, slug="nfl-2026-week-4"), candidates
        )
        await s.commit()
        assert report.corrections == "honoured"
        assert sorted(x["child_id"] for x in report.withdrawn) == sorted(
            t["market_id"] for t in proposed
        )
        assert not set(await _market_edge_ids(s, cid)) & {
            t["market_id"] for t in proposed
        }

    async def test_a_failure_rolls_back_that_hub_and_reports_the_earlier_commit(
        self, week_hubs, monkeypatch
    ):
        from app.utils import container_corrections as cc
        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        week4, week5 = w.hubs["nfl-2026-week-4"], w.hubs["nfl-2026-week-5"]
        real = cc.withdraw_member
        calls = {"week5": 0}

        async def flaky(session, **kwargs):
            if kwargs["container_id"] == week5:
                calls["week5"] += 1
                if calls["week5"] == 2:
                    raise RuntimeError("connection lost mid-hub")
            return await real(session, **kwargs)

        monkeypatch.setattr(cc, "withdraw_member", flaky)
        week5_edges = await _market_edge_ids(s, week5)
        doc, code = await run_members(
            _member_apply(w.manifest, _revisions(w)), w.factory
        )
        assert code == 1 and doc["status"] == "partial"
        assert doc["committed_hubs"] == [week4]
        first, second = doc["hubs"]
        assert first["status"] == "applied" and first["committed"] is True
        assert second["status"] == "failed" and second["committed"] is False
        assert await _revision(s, week4) == 1 + 4
        assert await _revision(s, week5) == 1
        assert await _market_edge_ids(s, week5) == week5_edges
        week5_rows = (
            await s.execute(
                text(
                    "SELECT count(*) FROM container_corrections "
                    "WHERE container_id = :cid AND scope = 'member'"
                ),
                {"cid": week5},
            )
        ).scalar()
        assert week5_rows == 0

    async def test_a_stale_hub_refuses_every_hub_before_any_write(self, week_hubs):
        from app.utils.container_corrections import withdraw_member
        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        week5 = w.hubs["nfl-2026-week-5"]
        control = next(c for c in w.controls if c["container_id"] == week5)
        await withdraw_member(s, **_withdraw_kwargs(week5, control["market_id"]))
        await s.commit()
        before = await _ledger_count(s)
        doc, code = await run_members(
            _member_apply(w.manifest, _revisions(w)), w.factory
        )
        assert code == 1 and doc["status"] == "refused" and doc["committed_hubs"] == []
        assert [h["status"] for h in doc["hubs"]] == ["not_attempted", "refused"]
        assert doc["hubs"][1]["current_revision"] == 2
        assert await _ledger_count(s) == before
        assert await _revision(s, w.hubs["nfl-2026-week-4"]) == 1


class TestExactRestore:
    async def _withdrawn(self, w):
        import json

        from scripts.collection_publication import run_members

        doc, code = await run_members(
            _member_apply(w.manifest, _revisions(w)), w.factory
        )
        assert code == 0, doc
        backup = w.tmp / "BACKUP.json"
        backup.write_text(json.dumps(doc))
        posts = {h["container_id"]: h["post_revision"] for h in doc["hubs"]}
        return doc, backup, posts

    async def test_restore_reinserts_the_identical_rows_without_assembly(
        self, week_hubs
    ):
        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        target_ids = [t["edge_id"] for t in w.targets]
        rows_before = await _full_rows(s, target_ids)
        withdrawn, backup, posts = await self._withdrawn(w)

        preview, code = await run_members(
            _member_options(
                operation="readmit-members",
                restore_from_ledger=True,
                backup=str(backup),
            ),
            w.factory,
        )
        assert code == 0 and preview["status"] == "preview"
        assert await _full_rows(s, target_ids) == {}

        doc, code = await run_members(
            _member_apply(backup, posts, "readmit-members"), w.factory
        )
        assert code == 0 and doc["status"] == "applied", doc
        assert await _full_rows(s, target_ids) == rows_before
        for receipt in doc["hubs"]:
            cid, n = receipt["container_id"], len(receipt["targets"])
            assert receipt["receipt_kind"] == "restore_apply"
            assert receipt["post_revision"] == posts[cid] + n == 1 + 2 * n
            assert await _revision(s, cid) == 1 + 2 * n
        latest = (
            await s.execute(
                text(
                    "SELECT DISTINCT ON (child_id) action FROM container_corrections "
                    "WHERE scope = 'member' ORDER BY child_id, id DESC"
                )
            )
        ).fetchall()
        assert {r[0] for r in latest} == {"readmit"}

        # A later pass that (after #9990) never proposes winners leaves them be.
        from types import SimpleNamespace

        week4 = w.hubs["nfl-2026-week-4"]
        controls = [c for c in w.controls if c["container_id"] == week4]
        report = await assemble_container(
            s,
            SimpleNamespace(id=week4, slug="nfl-2026-week-4"),
            [
                Candidate(
                    child_type="market",
                    child_id=c["market_id"],
                    source="venue_grouping",
                    evidence=MemberEvidence(node_type="market", name="Spread"),
                    external_id=c["external_id"],
                    market_source=c["venue"],
                )
                for c in controls
            ],
        )
        await s.commit()
        assert report.withdrawn == []
        assert await _full_rows(s, target_ids) == rows_before

    @pytest.mark.parametrize(
        "drift",
        ["intervening_correction", "silent_ledger_row", "edge_reinserted", "identity"],
    )
    async def test_restore_refuses_drift_before_any_write(self, week_hubs, drift):
        from app.utils.container_corrections import withdraw_member
        from scripts.collection_publication import run_members

        w = week_hubs
        s = w.session
        withdrawn, backup, posts = await self._withdrawn(w)
        week4 = w.hubs["nfl-2026-week-4"]
        target = next(t for t in w.targets if t["container_id"] == week4)
        if drift == "intervening_correction":
            control = next(c for c in w.controls if c["container_id"] == week4)
            await withdraw_member(s, **_withdraw_kwargs(week4, control["market_id"]))
        elif drift == "silent_ledger_row":
            # A decision recorded without its revision bump (a legacy writer).
            from app.utils.container_corrections import _record

            await _record(
                s,
                container_id=week4,
                scope="member",
                action="withdraw",
                child_type="market",
                child_id=1,
                reason="x",
                actor="x",
                revision=posts[week4],
            )
        elif drift == "edge_reinserted":
            await s.execute(
                text(
                    "INSERT INTO event_edges (parent_type, parent_id, child_type, "
                    "child_id, kind, class, source, confidence) VALUES "
                    "('container', :cid, 'market', :mid, 'contains', 'prop', 'human', 1)"
                ),
                {"cid": week4, "mid": target["market_id"]},
            )
        else:
            await s.execute(
                text("UPDATE futures_markets SET name = 'renamed' WHERE id = :id"),
                {"id": target["market_id"]},
            )
        await s.commit()
        edges = await _market_edge_ids(s, week4)
        revision = await _revision(s, week4)
        ledger = await _ledger_count(s)
        doc, code = await run_members(
            _member_apply(backup, posts, "readmit-members"), w.factory
        )
        assert code == 1 and doc["status"] == "refused" and doc["committed_hubs"] == []
        refused = next(h for h in doc["hubs"] if h["container_id"] == week4)
        expected = {
            "intervening_correction": "revision",
            "silent_ledger_row": "intervening correction",
            "edge_reinserted": "already exists",
            "identity": "name is 'renamed'",
        }[drift]
        assert expected in refused["error"] + " ".join(refused["errors"]), refused
        assert await _market_edge_ids(s, week4) == edges
        assert await _revision(s, week4) == revision
        assert await _ledger_count(s) == ledger
