"""#9935 C1 — a theme collection's page, end to end on a real server.

SHIP: an AI or Oscars preview opens the same complete collection at a stable
URL, every page of it agrees on the count, and a correction rebuilds the page
— even when it removes the last member. Pillars: MATCHING / DISCOVER / TRUTH.

WHY THIS NEEDS A REAL DATABASE. The pieces C1 wires are each graded elsewhere
against doubles (the producer in ``test_theme_assembly_9935.py``, the slug
parser in ``test_theme_definitions_9935.py``). What only a server can say:

* that the correction's slug read happens under the real chain lock and BEFORE
  the edge delete, so a last-member withdrawal still sends its rebuild (the
  mutation "key the enqueue on a surviving edge" turns ``test_the_last_member``
  red), and that the ``after_commit`` listener fires on a real commit and never
  on a real rollback;
* that the reader pairs the snapshot with the revision ``read_published`` names
  in ONE statement, so the page, its cursor and its counts all describe one
  revision, and a stale ``revision`` answers page 1 of the live one;
* that the real producer (A2) and the real reader (C1) agree on the key, the
  bytes and the page order.

The decisions table is created from S0's own DDL (``theme_definitions``); no
migration runs. Redis is a dict both halves share: the producer's sync client
and the reader's async client see the same keys, which is the only property
under test there.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall CI job does)"
    ),
)

AI_SLUG = "ai"
REBUILD = "app.tasks.rebuild_theme_snapshot"


class _SyncRedis:
    """The producer's side: ``SET NX EX`` / ``GET`` / ``EXPIRE`` over a dict."""

    def __init__(self, store: dict):
        self.store = store

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value if isinstance(value, bytes) else str(value).encode()
        return True

    def get(self, key):
        return self.store.get(key)

    def expire(self, key, ttl):
        return 1 if key in self.store else 0


class _AsyncRedis:
    """The reader's side, over the same dict."""

    def __init__(self, store: dict):
        self.store = store

    async def get(self, key):
        return self.store.get(key)


@pytest.fixture
async def world(monkeypatch):
    """Real Postgres; #9651's and S0's DDL; producer, reader and Celery wired
    to one shared store and one recorded ``send_task``."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks as tasks_pkg
    import app.tasks.base as task_base
    import app.tasks.redis_state as redis_state
    import app.utils.request_cache as request_cache
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS as CORRECTIONS_DDL
    from app.utils.theme_definitions import UPGRADE_STATEMENTS as DECISIONS_DDL

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("THEME_ASSEMBLY_ENABLED", "true")

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # Both reference `containers`, so they go first or `drop_all` wedges.
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

    store: dict = {}
    sent: list = []
    monkeypatch.setattr(task_base, "get_task_session", task_session)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _SyncRedis(store))

    async def shared_async():
        return _AsyncRedis(store)

    monkeypatch.setattr(request_cache, "get_shared_async_redis", shared_async)
    monkeypatch.setattr(
        tasks_pkg.celery_app,
        "send_task",
        lambda name, args=None, queue=None, **kw: sent.append((name, list(args or []), queue)),
    )

    yield {"Session": Session, "store": store, "sent": sent}

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
        await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
    await engine.dispose()


AI_NAMES = (
    ("KXCLAUDE-27-C6", "kalshi", "Will Anthropic release Claude 6 before 2027?"),
    ("PM-OAI-IPO", "polymarket", "OpenAI IPO before 2027?"),
    ("PM-GEM3", "polymarket", "Google Gemini 3 released before July?"),
    ("PM-GROK5", "polymarket", "Will xAI release Grok 5 by December?"),
)


async def _seed_ai_markets(session) -> dict:
    """Four AI questions with priced Yes/No legs, plus one lexical false friend."""
    from app.models.models import FuturesMarket, FuturesOutcome

    resolves = datetime(2026, 12, 31, tzinfo=timezone.utc)
    ids = {}
    for external_id, source, name in (
        *AI_NAMES,
        ("PM-MONET", "polymarket", "Will a Claude Monet painting sell for $100M?"),
    ):
        m = FuturesMarket(
            source=source, external_id=external_id, name=name, status="open",
            category="tech", llm_sport_category="tech", resolution_date=resolves,
            market_tier=2,
        )
        session.add(m)
        await session.flush()
        for leg, price in (("Yes", 0.41), ("No", 0.59)):
            session.add(FuturesOutcome(
                market_id=m.id, external_id=f"{external_id}-{leg}", name=leg,
                current_probability=price,
            ))
        ids[external_id] = m.id
    await session.commit()
    return ids


async def _get(world, slug, *, revision=None, cursor=None, limit=None):
    from app.routes.containers import get_container

    async with world["Session"]() as db:
        return await get_container(
            slug=slug, include_children=True, revision=revision, cursor=cursor,
            limit=limit, db=db,
        )


async def _container_id(world, slug):
    async with world["Session"]() as db:
        return int((await db.execute(
            text("SELECT id FROM containers WHERE slug = :s"), {"s": slug}
        )).scalar())


async def _live_revision(world, cid):
    async with world["Session"]() as db:
        return int((await db.execute(
            text("SELECT membership_revision FROM containers WHERE id = :c"), {"c": cid}
        )).scalar())


def _page_ids(body) -> list:
    return [m["id"] for s in body["sections"] for m in s["members"]]


def _is_building(resp) -> bool:
    return (
        isinstance(resp, Response)
        and resp.status_code == 503
        and json.loads(resp.body) == {"detail": {"state": "building"}}
    )


async def _assemble_and_publish(world) -> int:
    """Run the real producer pass, publish through the real correction, and run
    the rebuild that correction sent. Returns the container id."""
    from app.tasks.theme_assembly import (
        _run_assemble_theme_collections,
        _run_rebuild_theme_snapshot,
    )
    from app.utils import container_corrections as cc

    report = await _run_assemble_theme_collections(only=AI_SLUG)
    assert report["terminal"] == "complete", report
    cid = await _container_id(world, AI_SLUG)

    async with world["Session"]() as db:
        await cc.publish_container(db, container_id=cid, reason="reviewed", actor="test")
        await db.commit()
    assert world["sent"] == [(REBUILD, [cid], "background")]
    world["sent"].clear()
    rebuilt = await _run_rebuild_theme_snapshot(cid)
    assert rebuilt["terminal"] == "complete", rebuilt
    return cid


@pytest.mark.asyncio
async def test_pages_of_one_revision_share_their_counts_and_tile_the_snapshot(world):
    from app.tasks.theme_assembly import snapshot_key

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    live = await _live_revision(world, cid)
    snap = json.loads(world["store"][snapshot_key(cid, live)])
    assert snap["shown_count"] >= 3, snap  # the fixture must page at limit=2
    assert ids["PM-MONET"] not in snap["shown_ids"]

    first = await _get(world, AI_SLUG, limit="2")
    assert first["state"] == "published" and first["revision"] == live
    assert first["edition"] == {"kind": "theme_continuing", "subject": "ai"}
    assert first["revision_moved"] is False
    assert _page_ids(first) == snap["shown_ids"][:2]
    assert first["page"]["next_cursor"]

    seen, body = list(_page_ids(first)), first
    while body["page"]["next_cursor"]:
        body = await _get(
            world, AI_SLUG, revision=str(live), cursor=body["page"]["next_cursor"], limit="2"
        )
        assert body["counts"] == first["counts"]  # identical on every page
        assert body["revision"] == live and body["revision_moved"] is False
        seen += _page_ids(body)
    assert seen == snap["shown_ids"]  # every shown id once, in snapshot order
    assert first["counts"]["shown_count"] == snap["shown_count"] == len(seen)
    assert first["counts"]["eligible_count"] == snap["eligible_count"]


@pytest.mark.asyncio
async def test_a_stale_revision_answers_page_one_of_the_live_revision(world):
    async with world["Session"]() as db:
        await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    live = await _live_revision(world, cid)
    first = await _get(world, AI_SLUG, limit="2")

    moved = await _get(
        world, AI_SLUG, revision=str(live - 1), cursor=first["page"]["next_cursor"], limit="2"
    )
    assert moved["revision_moved"] is True
    assert moved["revision"] == live
    assert _page_ids(moved) == _page_ids(first)  # page 1, never a page of a mix
    assert moved["counts"] == first["counts"]


@pytest.mark.asyncio
async def test_a_withdrawal_rebuilds_the_page_and_survives_the_next_pass(world):
    from app.tasks.theme_assembly import (
        _run_assemble_theme_collections,
        _run_rebuild_theme_snapshot,
    )
    from app.utils import container_corrections as cc

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    before = await _get(world, AI_SLUG)
    gone = ids["PM-GROK5"]
    assert gone in _page_ids(before)

    async with world["Session"]() as db:
        await cc.withdraw_member(
            db, container_id=cid, child_type="market", child_id=gone,
            reason="not this subject", actor="test",
        )
        await db.commit()
    assert world["sent"] == [(REBUILD, [cid], "background")]
    world["sent"].clear()

    # The correction moved the revision without publishing: "building", never
    # the old page under the new number.
    assert _is_building(await _get(world, AI_SLUG))

    assert (await _run_rebuild_theme_snapshot(cid))["terminal"] == "complete"
    after = await _get(world, AI_SLUG)
    assert gone not in _page_ids(after)
    assert after["counts"]["shown_count"] == before["counts"]["shown_count"] - 1

    report = await _run_assemble_theme_collections(only=AI_SLUG)
    assert report["terminal"] == "complete", report
    async with world["Session"]() as db:
        edge = (await db.execute(text(
            "SELECT 1 FROM event_edges WHERE parent_type = 'container' "
            "AND parent_id = :c AND child_id = :m"), {"c": cid, "m": gone})).fetchone()
        reason = (await db.execute(text(
            "SELECT reason FROM container_member_decisions "
            "WHERE container_id = :c AND child_id = :m"), {"c": cid, "m": gone})).scalar()
    assert edge is None and reason == "container_member_withdrawn"
    assert gone not in _page_ids(await _get(world, AI_SLUG))


@pytest.mark.asyncio
async def test_the_last_member_withdrawn_still_rebuilds_to_an_empty_page(world):
    """Mutation: read the theme identity from a surviving edge after the delete
    → the second transaction sends nothing and this goes red."""
    from app.tasks.theme_assembly import _run_rebuild_theme_snapshot
    from app.utils import container_corrections as cc

    async with world["Session"]() as db:
        await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    async with world["Session"]() as db:
        members = [int(r[0]) for r in (await db.execute(text(
            "SELECT child_id FROM event_edges WHERE parent_type = 'container' "
            "AND parent_id = :c ORDER BY child_id"), {"c": cid})).fetchall()]
    assert len(members) >= 2

    # Every member but the last, in ONE transaction: one rebuild, not N.
    async with world["Session"]() as db:
        for mid in members[:-1]:
            await cc.withdraw_member(db, container_id=cid, child_type="market",
                                     child_id=mid, reason="cleanup", actor="test")
        await db.commit()
    assert world["sent"] == [(REBUILD, [cid], "background")]
    world["sent"].clear()

    async with world["Session"]() as db:
        await cc.withdraw_member(db, container_id=cid, child_type="market",
                                 child_id=members[-1], reason="cleanup", actor="test")
        await db.commit()
    assert world["sent"] == [(REBUILD, [cid], "background")]

    assert (await _run_rebuild_theme_snapshot(cid))["terminal"] == "complete"
    empty = await _get(world, AI_SLUG)
    assert empty["state"] == "empty"
    assert empty["sections"] == [] and empty["page"]["next_cursor"] is None
    assert empty["counts"]["shown_count"] == 0


@pytest.mark.asyncio
async def test_a_rolled_back_correction_sends_nothing_and_a_sports_hub_never_sends(world):
    from app.models.models import Container, EventEdge
    from app.utils import container_corrections as cc

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)

    async with world["Session"]() as db:
        await cc.withdraw_member(db, container_id=cid, child_type="market",
                                 child_id=ids["PM-GROK5"], reason="oops", actor="test")
        await db.rollback()
        await db.commit()  # a later commit on the same session carries nothing
    assert world["sent"] == []

    async with world["Session"]() as db:
        week = Container(kind="season", name="NFL 2026 · Week 5", slug="nfl-2026-week-5",
                         status="scheduled")
        db.add(week)
        await db.flush()
        db.add(EventEdge(parent_type="container", parent_id=week.id, child_type="market",
                         child_id=ids["PM-OAI-IPO"], kind="contains", edge_class="prop",
                         source="register", confidence=1))
        await db.commit()
        await cc.publish_container(db, container_id=week.id, reason="r", actor="test")
        await cc.withdraw_member(db, container_id=week.id, child_type="market",
                                 child_id=ids["PM-OAI-IPO"], reason="r", actor="test")
        await db.commit()
    assert world["sent"] == []


@pytest.mark.asyncio
async def test_a_sports_hub_ignores_the_theme_params_byte_for_byte(world):
    from app.models.models import Container, EventEdge
    from app.routes.containers import _render
    from app.utils import container_corrections as cc

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
        week = Container(kind="season", name="NFL 2026 · Week 5", slug="nfl-2026-week-5",
                         status="scheduled")
        db.add(week)
        await db.flush()
        db.add(EventEdge(parent_type="container", parent_id=week.id, child_type="market",
                         child_id=ids["PM-OAI-IPO"], kind="contains", edge_class="prop",
                         source="register", confidence=1))
        await db.commit()
        await cc.publish_container(db, container_id=week.id, reason="r", actor="test")
        await db.commit()

    plain = await _get(world, "nfl-2026-week-5")
    noisy = await _get(world, "nfl-2026-week-5", revision="x", cursor="!!", limit="0")
    assert plain["sections"]  # the control: a real hub with a card on it
    assert "counts" not in plain and "revision_moved" not in plain
    assert _render(noisy) == _render(plain)


@pytest.mark.asyncio
async def test_theme_slugs_without_a_collection_and_bad_params(world):
    for slug in ("oscars-2031", "nfl-2026-week-04", "ai-2026"):
        with pytest.raises(HTTPException) as err:
            await _get(world, slug)
        assert err.value.status_code == 404

    async with world["Session"]() as db:
        await _seed_ai_markets(db)
    await _assemble_and_publish(world)
    for params, reason in (
        ({"limit": "0"}, "invalid_limit"),
        ({"limit": "101"}, "invalid_limit"),
        ({"revision": "-1"}, "invalid_revision"),
        ({"cursor": "not-a-cursor"}, "invalid_cursor"),
    ):
        with pytest.raises(HTTPException) as err:
            await _get(world, AI_SLUG, **params)
        assert err.value.status_code == 422 and err.value.detail == {"reason": reason}


@pytest.mark.asyncio
async def test_an_unpublished_theme_shows_nothing_and_a_missing_snapshot_is_building(world):
    from app.tasks.theme_assembly import _run_assemble_theme_collections, snapshot_key

    async with world["Session"]() as db:
        await _seed_ai_markets(db)
    assert (await _run_assemble_theme_collections(only=AI_SLUG))["terminal"] == "complete"
    unpublished = await _get(world, AI_SLUG)
    assert unpublished["state"] == "unpublished" and unpublished["sections"] == []

    cid = await _assemble_and_publish(world)
    world["store"].pop(snapshot_key(cid, await _live_revision(world, cid)))
    assert _is_building(await _get(world, AI_SLUG))  # evicted: building, never empty


# ---------------------------------------------------------------------------
# #9936 — an ordinary correction does not degrade the collection or reset the
# reader's page; genuine incomplete refreshes stay visible; a settled answer
# whose time has not arrived keeps its card.
# ---------------------------------------------------------------------------


async def _decision_reason(world, cid, mid):
    async with world["Session"]() as db:
        return (await db.execute(text(
            "SELECT reason FROM container_member_decisions "
            "WHERE container_id = :c AND child_id = :m"), {"c": cid, "m": mid})).scalar()


async def _has_edge(world, cid, mid) -> bool:
    async with world["Session"]() as db:
        return (await db.execute(text(
            "SELECT 1 FROM event_edges WHERE parent_type = 'container' "
            "AND parent_id = :c AND child_id = :m"), {"c": cid, "m": mid})).fetchone() is not None


@pytest.mark.asyncio
async def test_9936_a_correction_keeps_the_claim_and_the_next_pass_keeps_the_page(
    world, monkeypatch
):
    from app.tasks import theme_assembly as ta
    from app.utils import container_corrections as cc

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    published = await _get(world, AI_SLUG)
    assert published["counts"]["inventory_complete"] is True  # the publish rebuild carried it

    # Two withdrawals in ONE transaction: one rebuild, a run of two.
    async with world["Session"]() as db:
        for key in ("PM-GROK5", "PM-GEM3"):
            await cc.withdraw_member(db, container_id=cid, child_type="market",
                                     child_id=ids[key], reason="cleanup", actor="test")
        await db.commit()
    assert world["sent"] == [(REBUILD, [cid], "background")]
    world["sent"].clear()
    rebuilt = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert rebuilt["inventory_complete"] is True
    assert rebuilt["completeness_basis"]["corrections_since"] == 2
    page = await _get(world, AI_SLUG, limit="1")
    assert page["counts"]["inventory_complete"] is True

    # The hourly pass finds the same page: no bump, so the reader's cursor holds.
    report = await ta._run_assemble_theme_collections(only=AI_SLUG)
    ai = report["containers"][0]
    assert (ai["bumped"], ai["revision_reason"]) == (False, "identical"), ai
    nxt = await _get(world, AI_SLUG, revision=str(page["revision"]),
                     cursor=page["page"]["next_cursor"], limit="1")
    assert nxt["revision_moved"] is False

    # Root's counterexample on real rows: a pass that decides nothing publishes
    # False and leaves MAX(decisions.revision) behind it.
    ticks = iter([0] + [10_000] * 50)
    monkeypatch.setattr(ta, "_monotonic", lambda: next(ticks))
    starved = (await ta._run_assemble_theme_collections(only=AI_SLUG))["containers"][0]
    monkeypatch.setattr(ta, "_monotonic", __import__("time").monotonic)
    assert starved["decided"] == 0 and starved["revision_reason"] == "content_changed"
    async with world["Session"]() as db:
        top = (await db.execute(text(
            "SELECT max(revision) FROM container_member_decisions WHERE container_id = :c"),
            {"c": cid})).scalar()
    assert top < starved["revision_after"]
    async with world["Session"]() as db:
        await cc.readmit_member(db, container_id=cid, child_type="market",
                                child_id=ids["PM-GROK5"], reason="undo", actor="test")
        await db.commit()
    honest = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert honest["inventory_complete"] is False
    assert honest["completeness_basis"] == {"revision": starved["revision_after"],
                                            "corrections_since": 1}
    assert (await _get(world, AI_SLUG))["counts"]["inventory_complete"] is False


@pytest.mark.asyncio
async def test_9936_a_vanished_row_is_carried_by_a_truncated_pass_and_retired_by_a_full_one(
    world, monkeypatch
):
    from app.tasks import theme_assembly as ta

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    gone = ids["KXCLAUDE-27-C6"]  # the lowest id: the first page observes it
    async with world["Session"]() as db:
        await db.execute(text("DELETE FROM futures_outcomes WHERE market_id = :m"), {"m": gone})
        await db.execute(text("DELETE FROM futures_markets WHERE id = :m"), {"m": gone})
        await db.commit()

    ticks = iter([0, 0] + [10_000] * 50)
    monkeypatch.setattr(ta, "_monotonic", lambda: next(ticks))
    monkeypatch.setattr(ta, "GATHER_PAGE", 1)
    truncated = (await ta._run_assemble_theme_collections(only=AI_SLUG))["containers"][0]
    assert truncated["inventory_complete"] is False
    assert await _has_edge(world, cid, gone)
    assert truncated["receipt"]["retired"] == {}

    monkeypatch.setattr(ta, "_monotonic", __import__("time").monotonic)
    monkeypatch.setattr(ta, "GATHER_PAGE", 500)
    full = (await ta._run_assemble_theme_collections(only=AI_SLUG))["containers"][0]
    assert full["inventory_complete"] is True
    assert not await _has_edge(world, cid, gone)
    assert await _decision_reason(world, cid, gone) == "member_row_absent"
    receipt = full["receipt"]
    assert receipt["retired"] == {"member_row_absent": 1}
    assert receipt["prior_members"] == (
        receipt["retained"] + sum(receipt["retired"].values()) + receipt["carried_unseen"])


@pytest.mark.asyncio
async def test_9936_a_settled_answer_without_a_time_keeps_its_card_across_passes(world):
    from app.tasks.theme_assembly import _run_assemble_theme_collections

    async with world["Session"]() as db:
        ids = await _seed_ai_markets(db)
    cid = await _assemble_and_publish(world)
    settled = ids["PM-OAI-IPO"]
    before = await _get(world, AI_SLUG)
    assert settled in _page_ids(before)

    async with world["Session"]() as db:
        await db.execute(text(
            "UPDATE futures_markets SET status = 'resolved', settled_at = NULL WHERE id = :m"),
            {"m": settled})
        await db.execute(text(
            "UPDATE futures_outcomes SET is_winner = (name = 'Yes'), resolution_source = "
            "'polymarket' WHERE market_id = :m"), {"m": settled})
        await db.commit()

    for _ in range(2):
        report = await _run_assemble_theme_collections(only=AI_SLUG)
        assert report["terminal"] == "complete", report
        assert await _has_edge(world, cid, settled)
        assert await _decision_reason(world, cid, settled) == "admitted_settle_time_pending"

    after = await _get(world, AI_SLUG)
    assert after["revision"] == before["revision"]  # settling moved nothing a reader holds
    member = next(m for s in after["sections"] for m in s["members"] if m["id"] == settled)
    card = member["card"]
    assert card["status"] == "resolved"
    yes = next(o for o in card["top_outcomes"] if o["name"] == "Yes")
    assert (yes["is_winner"], yes["resolution_source"]) == (True, "polymarket")
