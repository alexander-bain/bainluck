"""#5343 — provider event collections, end to end on a real server.

SHIP: a politics or technology event on Polymarket becomes one complete collection
at a stable URL, a correction to it stays corrected, and the next provider event
needs no code. Pillars: MATCHING / DISCOVER / TRUTH.

WHY A REAL DATABASE. The rules are graded against plain data in
``tests/test_provider_event_collections_5343.py``. Only a server can show:

* that a pass waiting on the container's row lock reads a withdrawal committed
  while it waited, and never writes the withdrawn member back;
* that two passes over one event serialize to one container, one edge set and
  one revision bump, with no unique violation;
* that a second pass over unchanged evidence writes nothing and keeps the
  revision, and that ``read_published`` names the revision the pass left;
* that the existing simple hub route serves the collection once — and only
  once — a named decision publishes it.

The rows are real Gamma events turned into what ingestion stores; the roster
key is the PROPOSED ingestion field, supplied by the test (see
``tests/fixtures/provider_event_collections_5343/PROVENANCE.md``). The
correction ledger and the decisions table are created from their own modules'
DDL; no migration runs.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.provider_event_fixtures_5343 import ingested_rows, load_gamma, roster_payload

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall CI job does)"
    ),
)

OBSERVED = datetime(2026, 10, 12, 0, 49, 13, tzinfo=timezone.utc)
NOW = OBSERVED + timedelta(hours=1)
POLITICS = "1038648"
ECONOMICS = "106884"
HELD_OUT = "86832"


@pytest.fixture
async def world(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS as CORRECTIONS_DDL
    from app.utils.theme_definitions import UPGRADE_STATEMENTS as DECISIONS_DDL

    monkeypatch.setenv("PROVIDER_EVENT_COLLECTIONS_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for statement in (*CORRECTIONS_DDL, *DECISIONS_DDL):
            await conn.execute(text(statement))

    Session = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def task_session(**_kwargs):
        async with Session() as session:
            yield session

    monkeypatch.setattr(task_base, "get_task_session", task_session)
    yield {"Session": Session}

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
    await engine.dispose()


async def _seed(
    world,
    event_id: str,
    domain: str,
    *,
    first_id: int,
    roster: bool = True,
    event: dict | None = None,
) -> list[dict]:
    from app.models.models import FuturesMarket

    event = event or load_gamma(event_id)
    rows = ingested_rows(
        event, domain, first_id=first_id, roster_at=OBSERVED if roster else None
    )
    async with world["Session"]() as session:
        for r in rows:
            session.add(FuturesMarket(category=domain or "other", **r))
        await session.commit()
    return rows


async def _run(world=None, **kw):
    from app.tasks.provider_event_collection_assembly import (
        _run_assemble_provider_event_collections,
    )

    return await _run_assemble_provider_event_collections(now=kw.pop("now", NOW), **kw)


async def _scalar(world, sql: str, **params):
    async with world["Session"]() as db:
        return (await db.execute(text(sql), params)).scalar()


async def _container(world, event_id: str):
    async with world["Session"]() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id, name, status, membership_revision, publication_state, kind, category "
                    "FROM containers WHERE slug = :s"
                ),
                {"s": f"polymarket-event-{event_id}"},
            )
        ).fetchone()
    return (
        None
        if row is None
        else {
            "id": int(row[0]),
            "name": row[1],
            "status": row[2],
            "revision": int(row[3]),
            "publication_state": row[4],
            "kind": row[5],
            "category": row[6],
        }
    )


async def _edges(world, container_id: int) -> dict:
    async with world["Session"]() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT child_id, class, source FROM event_edges "
                    "WHERE parent_type = 'container' AND parent_id = :c AND kind = 'contains'"
                ),
                {"c": container_id},
            )
        ).fetchall()
    return {int(r[0]): (r[1], r[2]) for r in rows}


async def _set_roster(world, parent_id: int, payload) -> None:
    async with world["Session"]() as db:
        await db.execute(
            text(
                "UPDATE futures_markets SET market_metadata = "
                "  CASE WHEN CAST(:p AS jsonb) IS NULL "
                "       THEN market_metadata - 'polymarket_event_roster' "
                "       ELSE jsonb_set(market_metadata, '{polymarket_event_roster}', CAST(:p AS jsonb)) END "
                "WHERE id = :id"
            ),
            {"p": None if payload is None else json.dumps(payload), "id": parent_id},
        )
        await db.commit()


async def _agrees(world, event_id: str) -> None:
    """``read_published``'s revision is the container's, its members the edges."""
    from app.utils.container_corrections import read_published

    c = await _container(world, event_id)
    async with world["Session"]() as db:
        read = await read_published(db, f"polymarket-event-{event_id}")
    assert read.revision == c["revision"]
    if read.state in ("published", "empty"):
        assert {m["id"] for m in read.members} == set(await _edges(world, c["id"]))


def _event(report, event_id):
    return next(
        e for e in report["events"] if e["group_id"] == f"polymarket:{event_id}"
    )


# ---------------------------------------------------------------------------


class TestThePass:
    async def test_contrasting_domains_and_a_held_out_event_assemble_with_no_code(
        self, world
    ):
        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _seed(world, HELD_OUT, "tech", first_id=3000)
        await _seed(world, ECONOMICS, "economics", first_id=5000)
        sports = load_gamma(POLITICS)
        sports = {
            **sports,
            "id": "424242",
            "slug": "sports-twin",
            "markets": [
                {**m, "conditionId": "0x" + "5" * 62 + f"{i:02d}"}
                for i, m in enumerate(sports["markets"])
            ],
        }
        await _seed(world, "424242", "basketball", first_id=7000, event=sports)

        report = await _run(world)
        assert report["terminal"] == "complete", report

        politics = await _container(world, POLITICS)
        assert politics["kind"] == "theme" and politics["category"] == "geopolitics"
        assert politics["name"] == "US-Iran ceasefire continues through...?"
        assert politics["publication_state"] == "unpublished"
        assert politics["revision"] == 1
        edges = await _edges(world, politics["id"])
        assert len(edges) == 6
        assert set(edges.values()) == {("unclassified", "venue_grouping")}

        held_out = await _container(world, HELD_OUT)
        assert len(await _edges(world, held_out["id"])) == 19
        assert _event(report, POLITICS)["eligibility"]["eligible"] is True
        assert _event(report, HELD_OUT)["eligibility"]["eligible"] is True
        econ = _event(report, ECONOMICS)
        assert econ["eligibility"]["reasons"] == ["roster_members_unstored"]
        assert econ["roster_unstored"] == 6

        assert (
            await _container(world, "424242") is None
        )  # unsupported domain mints nothing

        decided = await _scalar(
            world,
            "SELECT count(*) FROM container_member_decisions WHERE container_id = :c",
            c=politics["id"],
        )
        assert decided == 7  # six members + the parent anchor, each with provenance
        for event_id in (POLITICS, HELD_OUT, ECONOMICS):
            await _agrees(world, event_id)

    async def test_a_second_pass_writes_nothing_and_keeps_the_revision(self, world):
        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        before = await _container(world, POLITICS)
        attempts = await _scalar(
            world, "SELECT sum(attempt_count) FROM container_member_decisions"
        )
        again = _event(await _run(world), POLITICS)
        assert again["edges_upserted"] == 0 and again["edges_deleted"] == 0
        assert again["decisions_written"] == 0 and again["bumped"] is False
        assert (await _container(world, POLITICS))["revision"] == before["revision"]
        assert (
            await _scalar(
                world, "SELECT sum(attempt_count) FROM container_member_decisions"
            )
            == attempts
        )
        await _agrees(world, POLITICS)

    async def test_a_dry_run_writes_nothing(self, world):
        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        report = await _run(world, apply=False)
        assert _event(report, POLITICS)["would_create"] is True
        assert await _container(world, POLITICS) is None
        assert await _scalar(world, "SELECT count(*) FROM event_edges") == 0

    async def test_the_simple_hub_serves_it_only_after_a_named_publication(self, world):
        from app.routes.containers import get_container
        from app.tasks.provider_event_collection_assembly import (
            evaluate_provider_event_collection,
        )
        from app.utils.container_corrections import publish_container

        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        slug = f"polymarket-event-{POLITICS}"
        c = await _container(world, POLITICS)

        async with world["Session"]() as db:
            body = await get_container(
                slug=slug,
                include_children=True,
                revision=None,
                cursor=None,
                limit=None,
                db=db,
            )
        assert body["state"] == "unpublished" and body["sections"] == []
        assert body["edition"] is None

        async with world["Session"]() as db:
            verdict = await evaluate_provider_event_collection(db, slug, now=NOW)
            assert verdict["eligible"] is True, verdict
            await publish_container(
                db,
                container_id=c["id"],
                reason="#5343 contract test",
                actor="lane1-test",
                expected_revision=verdict["revision"],
            )
            await db.commit()

        async with world["Session"]() as db:
            body = await get_container(
                slug=slug,
                include_children=True,
                revision=None,
                cursor=None,
                limit=None,
                db=db,
            )
        assert body["state"] == "published"
        assert body["container"]["name"] == "US-Iran ceasefire continues through...?"
        assert body["member_count"] + body["withheld_count"] == 6
        await _agrees(world, POLITICS)


class TestStability:
    async def test_arrival_removal_and_a_new_title_keep_the_url_and_move_the_revision_once_each(
        self, world
    ):
        event = load_gamma(POLITICS)
        rows = await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        c = await _container(world, POLITICS)
        assert c["revision"] == 1

        # Removal: a NEWER roster drops one market.
        dropped = event["markets"][2]["conditionId"]
        await _set_roster(
            world,
            1000,
            roster_payload(event, OBSERVED + timedelta(minutes=30), drop=(dropped,)),
        )
        report = _event(await _run(world), POLITICS)
        assert report["edges_deleted"] == 1 and report["bumped"] is True
        assert (await _container(world, POLITICS))["revision"] == 2
        gone = next(r["id"] for r in rows if r["external_id"] == dropped)
        assert gone not in await _edges(world, c["id"])

        # Arrival: the next roster lists it again.
        await _set_roster(
            world, 1000, roster_payload(event, OBSERVED + timedelta(minutes=45))
        )
        report = _event(await _run(world), POLITICS)
        assert report["edges_upserted"] == 1
        assert (await _container(world, POLITICS))["revision"] == 3

        # Title: the label moves, the slug and members do not.
        async with world["Session"]() as db:
            await db.execute(
                text(
                    "UPDATE futures_markets SET market_metadata = jsonb_set(market_metadata, "
                    "'{event_title}', '\"US x Iran: does the ceasefire hold?\"') WHERE id = 1000"
                )
            )
            await db.commit()
        report = _event(await _run(world), POLITICS)
        after = await _container(world, POLITICS)
        assert report["header_changes"] == ["name"]
        assert after["id"] == c["id"] and after["revision"] == 4
        assert after["name"] == "US x Iran: does the ceasefire hold?"
        assert len(await _edges(world, c["id"])) == 6
        await _agrees(world, POLITICS)

    async def test_an_outage_keeps_the_last_good_membership(self, world):
        rows = await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        c = await _container(world, POLITICS)
        await _set_roster(world, 1000, None)
        async with world["Session"]() as db:
            await db.execute(
                text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
                {"ids": [rows[1]["id"], rows[2]["id"]]},
            )
            await db.commit()
        report = _event(await _run(world), POLITICS)
        assert report["edges_deleted"] == 0 and report["bumped"] is False
        assert len(await _edges(world, c["id"])) == 6
        assert report["eligibility"]["eligible"] is False
        assert (await _container(world, POLITICS))["revision"] == c["revision"]

    async def test_an_older_roster_cannot_resurrect_a_removed_member(self, world):
        event = load_gamma(POLITICS)
        rows = await _seed(world, POLITICS, "geopolitics", first_id=1000)
        dropped = event["markets"][3]["conditionId"]
        member = next(r["id"] for r in rows if r["external_id"] == dropped)
        await _set_roster(
            world,
            1000,
            roster_payload(event, OBSERVED + timedelta(hours=2), drop=(dropped,)),
        )
        await _run(world)
        c = await _container(world, POLITICS)
        assert member not in await _edges(world, c["id"])

        await _set_roster(
            world, 1000, roster_payload(event, OBSERVED + timedelta(hours=1))
        )
        for _ in range(2):
            report = _event(await _run(world), POLITICS)
            assert report["roster_state"] == "roster_older_than_applied"
            assert member not in await _edges(world, c["id"])

        await _set_roster(
            world, 1000, roster_payload(event, OBSERVED + timedelta(hours=3))
        )
        await _run(world)
        assert member in await _edges(world, c["id"])


class TestCorrections:
    async def test_a_withdrawn_member_stays_out_until_readmitted(self, world):
        from app.utils.container_corrections import readmit_member, withdraw_member

        rows = await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        c = await _container(world, POLITICS)
        target = rows[3]["id"]
        async with world["Session"]() as db:
            await withdraw_member(
                db,
                container_id=c["id"],
                child_type="market",
                child_id=target,
                reason="wrong event",
                actor="lane1-test",
            )
            await db.commit()
        for _ in range(3):
            report = _event(await _run(world), POLITICS)
            assert target not in await _edges(world, c["id"])
            assert report["edges_upserted"] == 0
        assert await _scalar(world, "SELECT count(*) FROM container_corrections") == 1

        async with world["Session"]() as db:
            await readmit_member(
                db,
                container_id=c["id"],
                child_type="market",
                child_id=target,
                reason="evidence re-checked",
                actor="lane1-test",
            )
            await db.commit()
        assert target not in await _edges(world, c["id"])  # a readmit writes no edge
        await _run(world)
        assert target in await _edges(world, c["id"])  # the next pass re-proves it
        await _agrees(world, POLITICS)

    async def test_a_withdrawn_publication_stays_withdrawn(self, world):
        from app.routes.containers import get_container
        from app.utils.container_corrections import (
            publish_container,
            withdraw_publication,
        )

        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        c = await _container(world, POLITICS)
        async with world["Session"]() as db:
            await publish_container(
                db, container_id=c["id"], reason="t", actor="lane1-test"
            )
            await withdraw_publication(
                db, container_id=c["id"], reason="wrong", actor="lane1-test"
            )
            await db.commit()
        for _ in range(2):
            report = _event(await _run(world), POLITICS)
            assert "publication_withdrawn" in report["eligibility"]["reasons"]
            assert (await _container(world, POLITICS))[
                "publication_state"
            ] == "withdrawn"
        async with world["Session"]() as db:
            body = await get_container(
                slug=f"polymarket-event-{POLITICS}",
                include_children=True,
                revision=None,
                cursor=None,
                limit=None,
                db=db,
            )
        assert body["state"] == "withdrawn" and body["sections"] == []

    async def test_a_withdrawal_committed_while_the_pass_waits_on_the_lock_is_honoured(
        self, world
    ):
        from app.tasks.provider_event_collection_assembly import assemble_provider_event
        from app.utils.container_corrections import (
            lock_container_chain,
            withdraw_member,
        )
        from app.utils.provider_event_collections import identity_from_group_id

        event = load_gamma(POLITICS)
        rows = await _seed(world, POLITICS, "geopolitics", first_id=1000)
        await _run(world)
        c = await _container(world, POLITICS)
        target = rows[2]["id"]
        # New evidence for the waiting pass to act on: a newer roster.
        await _set_roster(
            world, 1000, roster_payload(event, OBSERVED + timedelta(minutes=5))
        )

        identity = identity_from_group_id(f"polymarket:{POLITICS}")
        async with world["Session"]() as holder:
            assert await lock_container_chain(holder, c["id"]) is not None

            async def waiting_pass():
                async with world["Session"]() as s:
                    return await assemble_provider_event(
                        s, identity, apply=True, now=NOW
                    )

            task = asyncio.create_task(waiting_pass())
            await asyncio.sleep(0.5)
            assert not task.done(), "the pass did not wait for the container lock"
            await withdraw_member(
                holder,
                container_id=c["id"],
                child_type="market",
                child_id=target,
                reason="wrong event",
                actor="lane1-test",
            )
            await holder.commit()
        report = await asyncio.wait_for(task, timeout=10)
        assert target not in await _edges(world, c["id"])
        assert report["edges_upserted"] == 0
        await _agrees(world, POLITICS)

    async def test_two_passes_at_once_make_one_collection_and_one_bump(self, world):
        from app.tasks.provider_event_collection_assembly import assemble_provider_event
        from app.utils.provider_event_collections import identity_from_group_id

        await _seed(world, POLITICS, "geopolitics", first_id=1000)
        identity = identity_from_group_id(f"polymarket:{POLITICS}")

        async def one():
            async with world["Session"]() as s:
                return await assemble_provider_event(s, identity, apply=True, now=NOW)

        a, b = await asyncio.gather(one(), one())
        c = await _container(world, POLITICS)
        assert await _scalar(world, "SELECT count(*) FROM containers") == 1
        assert len(await _edges(world, c["id"])) == 6
        assert c["revision"] == 1
        assert sorted([a["bumped"], b["bumped"]]) == [False, True]
        await _agrees(world, POLITICS)
