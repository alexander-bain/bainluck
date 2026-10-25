"""#9936 D1b: a correction finishes while theme assembly is stopped.

PILLARS TRUTH / DISCOVER / MATCHING. SHIP: a person can withdraw an incorrect
member from an already published collection while automatic theme assembly is
stopped, and readers can still open the corrected collection without seeing
the withdrawn member.

Before: ``_run_rebuild_theme_snapshot`` returned ``skipped /
theme_assembly_disabled`` whenever ``THEME_ASSEMBLY_ENABLED`` was off, so the
revision a correction moved never got a page and the collection answered 503
"building" ("Couldn't load this collection") until assembly came back.

The contract under test. With the flag off the rebuild still never gathers,
decides, writes an edge, a decision row or a container, and never changes
publication. It writes only for a ``published`` collection whose live revision
has no page: one revision bump and one ``SET NX EX`` page, built from the
members the collection already has, completeness carried only through the
correction lineage. Otherwise it writes nothing and names why:
``assembly_stopped_not_published``, ``assembly_stopped_page_present``,
``assembly_stopped_store_unavailable``.

Doubles: ``_FakeDB`` / ``_FakeRedis`` from ``test_theme_assembly_9935`` and the
clocked store from ``test_theme_snapshot_outlives_producer_silence_9936``. The
route's 200 path runs for real with its card hydration stubbed; the real
Postgres half (real lock, real enqueue, real route) is in
``tests/integration/test_theme_collections_9935_pg.py``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.routes import containers as routes
from app.tasks import theme_assembly as ta
from app.utils.container_corrections import PublishedRead
from app.utils.container_presentation import MEMBER_MARKET
from tests.test_theme_assembly_9935 import (  # noqa: F401 — `db`, `redis` are fixtures
    CLAUDE_6,
    GPT_6,
    OPENAI_IPO,
    _assemble,
    _container,
    _FakeRedis,
    _quality,
    db,
    redis,
)
from tests.test_theme_snapshot_outlives_producer_silence_9936 import (  # noqa: F401
    DAY,
    clocked,
)

AI_EDITION = {"kind": "theme_continuing", "subject": "ai"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reader_reads_the_producer_store(monkeypatch):
    """The route's async GET sees whatever store the producer writes to now."""
    import app.utils.request_cache

    class _Async:
        async def get(self, key):
            client = ta._redis_client()
            if client is None:
                raise ConnectionError("no store")
            return client.get(key)

    async def _shared():
        return _Async()

    monkeypatch.setattr(app.utils.request_cache, "get_shared_async_redis", _shared)


async def _published(db, *rows) -> tuple[int, int]:
    """Assembled with the flag on, published, and its page written."""
    db.add_markets(*rows, slug="ai")
    await _assemble()
    db.publish("ai")
    assert (await ta._run_rebuild_theme_snapshot(db.container_id("ai")))["terminal"] == "complete"
    return db.container_id("ai"), db.revision("ai")


def _stop(monkeypatch) -> None:
    monkeypatch.delenv(ta.THEME_ASSEMBLY_ENABLED_ENV, raising=False)


def _db_writes(db, since: int = 0) -> list[str]:
    """Every statement that writes. ``_FakeDB.writes()`` files the chain-CTE
    revision bump under its ``WITH RECURSIVE`` prefix; this does not."""
    return [s for s, _ in db.statements[since:]
            if "UPDATE containers" in s
            or s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]


def _gathers(db, since: int = 0) -> list:
    return [s for s, _ in db.statements[since:] if s == "GATHER page"]


def _store_writes(client) -> list:
    log = getattr(client, "log", [])
    return [e for e in log if e[0] != "GET"]


async def _route(monkeypatch, db, *, held=None):
    """``routes._serve_theme_page`` for the live published read. Membership is
    the edges as they stand (``read_published``); the cards are stubbed."""
    cid, live = db.container_id("ai"), db.revision("ai")
    members = [{"container_id": cid, "type": MEMBER_MARKET, "id": i, "class": c}
               for i, c in sorted(db.theme_edges("ai").items())]
    published = PublishedRead(state="published" if members else "empty", slug="ai",
                              revision=live, container_id=cid, members=members)

    async def _cards(_db, ids):
        return {i: {"id": i} for i in ids}, {i: None for i in ids}, {}

    monkeypatch.setattr(routes, "_hydrate_market_cards", _cards)

    class _Head:
        async def execute(self, *_args, **_kwargs):
            row = (cid, "theme", "AI", "ai", "tech", "open", None, None, None)
            return SimpleNamespace(fetchone=lambda: row)

    return await routes._serve_theme_page(
        _Head(), published, AI_EDITION, revision=held, cursor=None, limit=None
    )


def _ids(body) -> list:
    return [m["id"] for s in body["sections"] for m in s["members"]]


def _building(response) -> bool:
    return (getattr(response, "status_code", None) == 503
            and json.loads(response.body) == {"detail": {"state": "building"}})


# ---------------------------------------------------------------------------
# S1–S3: the SHIP, its exact write set and its carried completeness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s1_a_withdrawal_while_stopped_is_served_corrected_at_a_new_revision(
    db, redis, monkeypatch
):
    cid, r = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    corrected = db.withdraw("ai", CLAUDE_6.id)
    assert _building(await _route(monkeypatch, db))  # until the rebuild lands

    rebuilt = await ta._run_rebuild_theme_snapshot(cid)
    report = rebuilt["containers"][0]
    assert (rebuilt["terminal"], report["assembly"]) == ("complete", "stopped")
    assert (report["revision_before"], report["revision_after"], report["revision_reason"]) == (
        corrected, corrected + 1, "snapshot_absent")

    body = await _route(monkeypatch, db)
    assert _ids(body) == [OPENAI_IPO.id]
    assert body["counts"]["shown_count"] == 1 and body["revision"] == corrected + 1
    assert body["revision_moved"] is False

    # A reader still holding the page it opened before the correction gets
    # page 1 of the corrected revision, never the old one.
    held = await _route(monkeypatch, db, held=str(r))
    assert held["revision_moved"] is True and _ids(held) == [OPENAI_IPO.id]


@pytest.mark.asyncio
async def test_s2_while_stopped_it_writes_one_revision_and_one_page_and_nothing_else(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    edges, decisions = dict(db.state["edges"]), dict(db.state["decisions"])
    ledger = list(db.state["ledger"])
    since = len(db.statements)
    redis.log.clear()

    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]

    writes = _db_writes(db, since)
    assert len(writes) == 1 and "UPDATE containers SET membership_revision" in writes[0]
    assert _gathers(db, since) == []
    assert _store_writes(redis) == [
        ("SET", ta.snapshot_key(cid, report["revision_after"]), True, ta.SNAPSHOT_TTL_S)]
    assert (db.state["edges"], db.state["decisions"], db.state["ledger"]) == (
        edges, decisions, ledger)
    assert db.state["containers"][cid]["publication"] == "published"

    # The automatic pass stays stopped: not one statement.
    since = len(db.statements)
    pass_report = await _assemble()
    assert (pass_report["terminal"], pass_report["reason"]) == (
        "skipped", "theme_assembly_disabled")
    assert db.statements[since:] == []


@pytest.mark.asyncio
async def test_s3_completeness_is_carried_through_the_correction_lineage(
    db, redis, monkeypatch
):
    cid, r = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)

    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]

    assert report["inventory_complete"] is True
    assert report["completeness_basis"] == {"revision": r, "corrections_since": 1}


# ---------------------------------------------------------------------------
# S4: lineage absent — never assert completeness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s4_a_base_page_gone_is_unproven_never_asserted(db, clocked, monkeypatch):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    clocked.now = ta.SNAPSHOT_TTL_S + DAY  # silence outlived the bound: the base page expired
    db.withdraw("ai", CLAUDE_6.id)

    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]

    assert report["terminal"] == "complete"
    assert report["inventory_complete"] is False
    assert report["completeness_unproven"] == "snapshot_absent"
    body = await _route(monkeypatch, db)
    assert _ids(body) == [OPENAI_IPO.id] and body["counts"]["inventory_complete"] is False


# ---------------------------------------------------------------------------
# S5–S6: a collection that is not published gets no page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s5_a_withdrawn_collection_while_stopped_writes_nothing(db, redis, monkeypatch):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    withdrawn_at = db.withdraw_publication("ai")
    since = len(db.statements)
    redis.log.clear()

    report = await ta._run_rebuild_theme_snapshot(cid)

    assert _db_writes(db, since) == [] and _store_writes(redis) == []
    assert db.revision("ai") == withdrawn_at
    assert db.state["containers"][cid]["publication"] == "withdrawn"
    assert (report["terminal"], report["reason"], report["assembly"]) == (
        "skipped", ta.STOPPED_NOT_PUBLISHED, "stopped")


@pytest.mark.asyncio
async def test_s6_a_never_published_collection_while_stopped_writes_nothing(
    db, redis, monkeypatch
):
    db.add_markets(OPENAI_IPO, CLAUDE_6, slug="ai")
    await _assemble()  # assembly never publishes
    cid = db.container_id("ai")
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    since = len(db.statements)
    redis.log.clear()

    report = await ta._run_rebuild_theme_snapshot(cid)

    assert _db_writes(db, since) == [] and _store_writes(redis) == []
    assert (report["terminal"], report["reason"]) == ("skipped", ta.STOPPED_NOT_PUBLISHED)


# ---------------------------------------------------------------------------
# S7–S9: duplicates and an unavailable store fail bounded and honest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s7_a_second_rebuild_while_stopped_writes_nothing_even_after_rows_change(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6, GPT_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    assert (await ta._run_rebuild_theme_snapshot(cid))["terminal"] == "complete"
    live = db.revision("ai")
    page = redis.store[ta.snapshot_key(cid, live)]

    # Display inputs move after the page landed. Running, this would publish a
    # content_changed revision; stopped, nothing is refreshed or replaced.
    _quality(monkeypatch, {GPT_6.name: "low_quality"})
    since = len(db.statements)
    redis.log.clear()
    report = await ta._run_rebuild_theme_snapshot(cid)

    assert _db_writes(db, since) == [] and _store_writes(redis) == []
    assert db.revision("ai") == live and redis.store[ta.snapshot_key(cid, live)] == page
    assert (report["terminal"], report["reason"]) == ("skipped", ta.STOPPED_PAGE_PRESENT)


class _UnreadableStore(_FakeRedis):
    def get(self, key):
        self.log.append(("GET", key))
        raise ConnectionError("store unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize("outage", ["no_client", "read_error"])
async def test_s8_an_unreadable_store_while_stopped_moves_no_revision(
    db, redis, monkeypatch, outage
):
    cid, r = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    corrected = db.withdraw("ai", CLAUDE_6.id)
    down = None if outage == "no_client" else _UnreadableStore()
    monkeypatch.setattr(ta, "_redis_client", lambda: down)
    since = len(db.statements)

    report = await ta._run_rebuild_theme_snapshot(cid)

    assert _db_writes(db, since) == [] and db.revision("ai") == corrected
    assert down is None or _store_writes(down) == []
    assert (report["terminal"], report["reason"]) == ("skipped", ta.STOPPED_STORE_UNAVAILABLE)

    # The store comes back and the rebuild is sent again: the correction's
    # revision was never burned, so its lineage — and its claim — survive.
    monkeypatch.setattr(ta, "_redis_client", lambda: redis)
    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (report["terminal"], report["revision_after"]) == ("complete", corrected + 1)
    assert report["completeness_basis"] == {"revision": r, "corrections_since": 1}


class _UnwritableStore(_FakeRedis):
    def set(self, key, value, nx=False, ex=None, **kwargs):
        self.log.append(("SET", key, bool(nx), ex))
        raise ConnectionError("store refuses writes")


@pytest.mark.asyncio
async def test_s9_a_page_write_that_fails_after_the_bump_is_building_until_a_resend(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    corrected = db.withdraw("ai", CLAUDE_6.id)
    unwritable = _UnwritableStore()
    unwritable.store = redis.store  # same keys; reads work, writes fail
    monkeypatch.setattr(ta, "_redis_client", lambda: unwritable)

    rebuilt = await ta._run_rebuild_theme_snapshot(cid)
    assert (rebuilt["terminal"], rebuilt["reason"]) == ("partial", "snapshot_write_failed")
    assert db.revision("ai") == corrected + 1
    assert _building(await _route(monkeypatch, db))  # honest: never the old page

    # Writes recover; a person re-sends the rebuild. The page returns without
    # the member, but the failed bump has no ledger row and no page, so the
    # lineage stops there and the claim is unproven until a full pass.
    monkeypatch.setattr(ta, "_redis_client", lambda: redis)
    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (report["terminal"], report["revision_after"]) == ("complete", corrected + 2)
    assert report["inventory_complete"] is False
    assert report["completeness_unproven"] == "snapshot_absent"
    assert _ids(await _route(monkeypatch, db)) == [OPENAI_IPO.id]


# ---------------------------------------------------------------------------
# S10–S12: empty is not building; concurrent corrections; readmission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s10_the_last_member_while_stopped_is_an_empty_collection_not_building(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO)
    _stop(monkeypatch)
    db.withdraw("ai", OPENAI_IPO.id)
    assert _building(await _route(monkeypatch, db))

    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (report["terminal"], report["shown_count"], report["eligible_count"]) == (
        "complete", 0, 0)

    body = await _route(monkeypatch, db)
    assert body["state"] == "empty" and body["sections"] == []
    assert body["counts"]["shown_count"] == 0 and body["page"]["next_cursor"] is None


@pytest.mark.asyncio
async def test_s11_two_corrections_before_their_rebuilds_publish_one_page(
    db, redis, monkeypatch
):
    cid, r = await _published(db, OPENAI_IPO, CLAUDE_6, GPT_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    second = db.withdraw("ai", GPT_6.id)

    first = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (first["terminal"], first["revision_after"]) == ("complete", second + 1)
    assert first["completeness_basis"] == {"revision": r, "corrections_since": 2}
    since = len(db.statements)
    redis.log.clear()
    again = await ta._run_rebuild_theme_snapshot(cid)  # the second correction's rebuild
    assert _db_writes(db, since) == [] and _store_writes(redis) == []
    assert again["reason"] == ta.STOPPED_PAGE_PRESENT
    assert _ids(await _route(monkeypatch, db)) == [OPENAI_IPO.id]


@pytest.mark.asyncio
async def test_s12_readmission_while_stopped_adds_no_member_until_assembly_resumes(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    await ta._run_rebuild_theme_snapshot(cid)
    readmitted = db.readmit("ai", CLAUDE_6.id)

    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (report["terminal"], report["revision_after"]) == ("complete", readmitted + 1)
    assert _ids(await _route(monkeypatch, db)) == [OPENAI_IPO.id]  # no correction adds one
    assert CLAUDE_6.id not in db.theme_edges("ai")

    monkeypatch.setenv(ta.THEME_ASSEMBLY_ENABLED_ENV, "1")  # assembly resumes
    resumed = _container(await _assemble(), "ai")
    assert resumed["revision_reason"] == "membership_changed"
    assert _ids(await _route(monkeypatch, db)) == sorted([OPENAI_IPO.id, CLAUDE_6.id])


# ---------------------------------------------------------------------------
# S13: assembly resumes over a page written while stopped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s13_the_first_pass_after_resuming_keeps_the_stopped_page(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    db.withdraw("ai", CLAUDE_6.id)
    await ta._run_rebuild_theme_snapshot(cid)
    live = db.revision("ai")

    monkeypatch.setenv(ta.THEME_ASSEMBLY_ENABLED_ENV, "1")
    resumed = _container(await _assemble(), "ai")

    assert (resumed["bumped"], resumed["revision_reason"], resumed["snapshot"]) == (
        False, "identical", "refreshed")
    assert db.revision("ai") == live
    assert db.decision("ai", CLAUDE_6.id)["reason"] == "container_member_withdrawn"
    assert _ids(await _route(monkeypatch, db)) == [OPENAI_IPO.id]


# ---------------------------------------------------------------------------
# S14: the rebuild never re-publishes; a person's publish gets its page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s14_only_a_persons_publish_brings_a_withdrawn_collection_back(
    db, redis, monkeypatch
):
    cid, _ = await _published(db, OPENAI_IPO, CLAUDE_6)
    _stop(monkeypatch)
    db.withdraw_publication("ai")
    for _ in range(2):  # however often it runs, the rebuild never re-publishes
        held = await ta._run_rebuild_theme_snapshot(cid)
        assert held["reason"] == ta.STOPPED_NOT_PUBLISHED
    assert db.state["containers"][cid]["publication"] == "withdrawn"

    republished = db.publish("ai")  # a person's decision, through the correction
    report = (await ta._run_rebuild_theme_snapshot(cid))["containers"][0]
    assert (report["terminal"], report["revision_after"]) == ("complete", republished + 1)
    assert _ids(await _route(monkeypatch, db)) == sorted([OPENAI_IPO.id, CLAUDE_6.id])
