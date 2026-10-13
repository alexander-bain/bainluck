"""#1527: a settled three-way soccer market leaves ``status='open'`` — against a
real PostgreSQL, on the real ORM schema.

PILLAR: TRUTH. SHIP: after a soccer fixture is settled, its market no longer
appears live while its one real winner remains visible.

The attended status transition's exact-id plan (bound to the market's and every
leg's row version), its compare-and-set under ``FOR UPDATE`` / ``FOR SHARE``, the
row-count-checked write, the D51 before-image banked in the write's own
transaction, the audit of a stopped run, and a restore that never overwrites a
later writer, even one that left every value the same. A session double reads
every one of those green, which is why this runs on Postgres.

The schema is ``Base.metadata.create_all`` in a throwaway database (never a
hand-built table: a narrower fixture schema is how the outcome rail's first PG
gate passed 25/25 against columns production does not have). Rows are seeded
through the ORM. The CLOB is a fake keyed by condition id.

Seeds, every one a Polymarket soccer field with one Draw leg and stored ``open``
unless named otherwise:

* **SPEC** 55254886, the issue's specimen AFTER the outcome rail: Anderlecht is
  the one winner (``clob_field_repair``). The venue closed it, Anderlecht.
* **HONEST** a fixture graded by the poller's settlement (``api_settlement``),
  carrying a sibling ``market_metadata`` key the write must keep, its losers
  re-priced to 0.003 the way the poll prices a settled loser it reaches (the
  re-ingest gate measures that). Venue: Draw. The grade says who won.
* **THIRD** a third settled fixture whose ``settled_at`` is already stamped: the
  first observation must survive.
  SPEC's ``market_metadata`` is JSON ``null`` (what an ORM ``None`` stores in this
  JSONB column) and THIRD's is SQL NULL: both must take the stamp as an object,
  never the array ``COALESCE(m, '{}') || stamp`` builds over a JSON null, and the
  restore must put each kind of null back as itself.
* Refused, and never moved even when named: **VENUE_OPEN** (one leg not closed),
  **VOID** (nobody won), **CONTRA** (two winners), **DISAGREE** (the venue names
  a different winner than the one stored), **UNKNOWN** (a grading source the
  authority ladder does not know), **SOURCELESS** (a loss with no
  ``resolution_source``: the column defaults to false, so nobody may have
  graded it), **INCOHERENT** (three stored winners: the
  outcome rail's job first), **UNGRADED** (``is_winner`` NULL), **DUEL** (two
  legs), **KALSHI**, **ALREADY** (already ``resolved``), **CLOB_ERR** (the
  venue read raises) and **ARRAY_META** (metadata an array, which a merge would
  rebuild).
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, null, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.polymarket_api as polymarket_api
import app.tasks.repair_settled_status_1527 as rs

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #1527 status gate"
    ),
]

UTC = timezone.utc
FIRST_SEEN = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)

SPEC, HONEST, THIRD = 55254886, 55254887, 55254888
VENUE_OPEN, VOID, CONTRA, DISAGREE, UNKNOWN = (
    71000001, 71000002, 71000003, 71000004, 71000005)
INCOHERENT, UNGRADED, DUEL, KALSHI, ALREADY, CLOB_ERR, ARRAY_META, SOURCELESS = (
    71000006, 71000007, 71000008, 71000009, 71000010, 71000011, 71000012, 71000013)
SETTLES = (SPEC, HONEST, THIRD)
REFUSALS = {
    VENUE_OPEN: "venue_not_closed",
    VOID: "no_winner_void",
    CONTRA: "multiple_clob_winners",
    DISAGREE: "venue_disagrees_with_stored_winner",
    UNKNOWN: "unknown_authority",
    INCOHERENT: "field_incoherent",
    UNGRADED: "field_ungraded",
    DUEL: "not_three_way",
    KALSHI: "not_polymarket",
    ALREADY: "already_settled",
    CLOB_ERR: "clob_error",
    ARRAY_META: "metadata_not_an_object",
    SOURCELESS: "unknown_authority",
}
ALL_IDS = sorted([*SETTLES, *REFUSALS])

#: SQL NULL, as opposed to the JSON ``null`` an ORM ``None`` stores in this column.
SQL_NULL = object()

#: market id -> (source, status, settled_at, market_metadata)
MARKETS = {
    SPEC: ("polymarket", "open", None, None),
    HONEST: ("polymarket", "open", None, {"polymarket_event_id": "10001"}),
    THIRD: ("polymarket", "open", FIRST_SEEN, SQL_NULL),
    VENUE_OPEN: ("polymarket", "open", None, None),
    VOID: ("polymarket", "open", None, None),
    CONTRA: ("polymarket", "open", None, None),
    DISAGREE: ("polymarket", "open", None, None),
    UNKNOWN: ("polymarket", "open", None, None),
    INCOHERENT: ("polymarket", "open", None, None),
    UNGRADED: ("polymarket", "open", None, None),
    DUEL: ("polymarket", "open", None, None),
    KALSHI: ("kalshi", "open", None, None),
    ALREADY: ("polymarket", "resolved", FIRST_SEEN, None),
    CLOB_ERR: ("polymarket", "open", None, None),
    ARRAY_META: ("polymarket", "open", None, ["not", "an", "object"]),
    SOURCELESS: ("polymarket", "open", None, None),
}

#: (outcome id, market id, name, stored is_winner, stored probability,
#:  resolution_source, venue closed, venue yes_winner)
LEGS = [
    (205060693, SPEC, "Slavia Praha", False, 0.0, "clob_field_repair", True, False),
    (205060694, SPEC, "Anderlecht", True, 1.0, "clob_field_repair", True, True),
    (205060695, SPEC, "Draw", False, 0.0, "clob_field_repair", True, False),
    (205060700, HONEST, "Real Sociedad", False, 0.003, "api_settlement", True, False),
    (205060701, HONEST, "Dynamo Kyiv", False, 0.003, "api_settlement", True, False),
    (205060702, HONEST, "Draw (Real Sociedad vs. Dynamo Kyiv)", True, 1.0,
     "api_settlement", True, True),
    (205060710, THIRD, "Ajax", True, 1.0, "api_settlement", True, True),
    (205060711, THIRD, "PSV", False, 0.0, "api_settlement", True, False),
    (205060712, THIRD, "Draw", False, 0.0, "api_settlement", True, False),
    (710000011, VENUE_OPEN, "Home", True, 1.0, "api_settlement", True, True),
    (710000012, VENUE_OPEN, "Away", False, 0.0, "api_settlement", False, False),
    (710000013, VENUE_OPEN, "Draw", False, 0.0, "api_settlement", True, False),
    (710000021, VOID, "Home", True, 1.0, "api_settlement", True, False),
    (710000022, VOID, "Away", False, 0.0, "api_settlement", True, False),
    (710000023, VOID, "Draw", False, 0.0, "api_settlement", True, False),
    (710000031, CONTRA, "Home", True, 1.0, "api_settlement", True, True),
    (710000032, CONTRA, "Away", False, 0.0, "api_settlement", True, True),
    (710000033, CONTRA, "Draw", False, 0.0, "api_settlement", True, False),
    (710000041, DISAGREE, "Home", True, 1.0, "api_settlement", True, False),
    (710000042, DISAGREE, "Away", False, 0.0, "api_settlement", True, True),
    (710000043, DISAGREE, "Draw", False, 0.0, "api_settlement", True, False),
    (710000051, UNKNOWN, "Home", True, 1.0, "mystery_grader", True, True),
    (710000052, UNKNOWN, "Away", False, 0.0, "api_settlement", True, False),
    (710000053, UNKNOWN, "Draw", False, 0.0, "api_settlement", True, False),
    (710000061, INCOHERENT, "Home", True, 1.0, None, True, True),
    (710000062, INCOHERENT, "Away", True, 1.0, None, True, False),
    (710000063, INCOHERENT, "Draw", True, 1.0, None, True, False),
    (710000071, UNGRADED, "Home", None, 1.0, None, True, True),
    (710000072, UNGRADED, "Away", None, 0.0, None, True, False),
    (710000073, UNGRADED, "Draw", None, 0.0, None, True, False),
    (710000081, DUEL, "Arsenal", True, 1.0, "api_settlement", True, True),
    (710000082, DUEL, "Chelsea (Draw no bet)", False, 0.0, "api_settlement", True, False),
    (710000091, KALSHI, "Home", True, 1.0, "api_settlement", True, True),
    (710000092, KALSHI, "Away", False, 0.0, "api_settlement", True, False),
    (710000093, KALSHI, "Draw", False, 0.0, "api_settlement", True, False),
    (710000101, ALREADY, "Home", True, 1.0, "api_settlement", True, True),
    (710000102, ALREADY, "Away", False, 0.0, "api_settlement", True, False),
    (710000103, ALREADY, "Draw", False, 0.0, "api_settlement", True, False),
    (710000111, CLOB_ERR, "Home", True, 1.0, "api_settlement", True, True),
    (710000112, CLOB_ERR, "Away", False, 0.0, "api_settlement", True, False),
    (710000113, CLOB_ERR, "Draw", False, 0.0, "api_settlement", True, False),
    (710000121, ARRAY_META, "Home", True, 1.0, "api_settlement", True, True),
    (710000122, ARRAY_META, "Away", False, 0.0, "api_settlement", True, False),
    (710000123, ARRAY_META, "Draw", False, 0.0, "api_settlement", True, False),
    (710000131, SOURCELESS, "Home", True, 1.0, "api_settlement", True, True),
    (710000132, SOURCELESS, "Away", False, 0.0, "api_settlement", True, False),
    (710000133, SOURCELESS, "Draw", False, 0.0, None, True, False),
]


def _cid(oid: int) -> str:
    return f"0x{oid:064x}"


VENUE = {_cid(oid): (closed, won) for oid, _, _, _, _, _, closed, won in LEGS}
RAISES = {_cid(710000112)}


class FakeClob:
    """The CLOB, by condition id. ``calls`` counts reads."""

    calls = 0

    async def get_clob_market_by_condition(self, condition_id):
        FakeClob.calls += 1
        if condition_id in RAISES:
            raise RuntimeError("429 Too Many Requests")
        if condition_id not in VENUE:
            return None
        closed, won = VENUE[condition_id]
        return {"condition_id": condition_id, "closed": closed,
                "tokens": [{"outcome": "Yes", "winner": won},
                           {"outcome": "No", "winner": not won}]}


@pytest.fixture(scope="session")
def isolated_database():
    """A throwaway database carrying the real ORM schema."""
    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "settled_status_1527_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"),
                          isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{database}"'))
    schema = create_engine(url.set(drivername="postgresql+psycopg2", database=database))
    Base.metadata.create_all(schema)
    schema.dispose()
    try:
        yield url.set(database=database)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def db(isolated_database, monkeypatch):
    from app.models.models import FuturesMarket, FuturesOutcome

    monkeypatch.setattr(polymarket_api, "PolymarketAPIService", FakeClob)
    FakeClob.calls = 0
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text(f"DROP TABLE IF EXISTS {rs.BAK_TABLE}"))
        await s.execute(text("DROP FUNCTION IF EXISTS refuse_one_market() CASCADE"))
        await s.execute(text("TRUNCATE futures_markets CASCADE"))
        for mid, (source, status, settled_at, meta) in MARKETS.items():
            s.add(FuturesMarket(
                id=mid, source=source, external_id=f"event-{mid}",
                name=f"SYNTHETIC-1527 market {mid}", category="championship",
                llm_sport_category="soccer", market_type="field",
                mutually_exclusive=True, status=status, settled_at=settled_at,
                market_metadata=null() if meta is SQL_NULL else meta))
        await s.flush()
        for oid, mid, name, won, prob, src, _, _ in LEGS:
            s.add(FuturesOutcome(
                id=oid, market_id=mid, external_id=_cid(oid), name=name,
                is_winner=won, current_probability=prob, resolution_source=src))
        await s.commit()
    yield maker
    await engine.dispose()


_MARKET_STATE = ("SELECT id, status, settled_at, market_metadata, xmin::text"
                 " FROM futures_markets ORDER BY id")
_LEG_STATE = ("SELECT id, is_winner, current_probability, resolution_source,"
              " xmin::text FROM futures_outcomes ORDER BY id")


async def _markets(maker, mids=None):
    async with maker() as s:
        rows = (await s.execute(text(_MARKET_STATE))).all()
    return {r[0]: tuple(r) for r in rows if mids is None or r[0] in mids}


async def _legs(maker):
    async with maker() as s:
        return [tuple(r) for r in (await s.execute(text(_LEG_STATE))).all()]


async def _bak(maker):
    async with maker() as s:
        if not (await s.execute(text("SELECT to_regclass(:t) IS NOT NULL"),
                                {"t": rs.BAK_TABLE})).scalar_one():
            return []
        return [tuple(r) for r in (await s.execute(text(
            f"SELECT market_id, prior_status, wrote_status, plan_hash, wrote_row_version"
            f" FROM {rs.BAK_TABLE} ORDER BY market_id"))).all()]


async def _run(maker, fn=None, **kw):
    async with maker() as s:
        return await (fn or rs.repair)(s, **kw)


async def _touch(maker, sql):
    async with maker() as s:
        await s.execute(text(sql))
        await s.commit()


def _ids(*mids):
    return ",".join(str(m) for m in mids)


def _meta(v):
    return json.loads(v) if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

async def test_the_dry_run_plans_only_the_settled_markets_and_writes_nothing(db):
    markets, legs = await _markets(db), await _legs(db)
    out = await _run(db, only_ids=_ids(*ALL_IDS))
    assert out["terminal"] == "dry_run"
    assert out["planned_market_ids"] == list(SETTLES)
    reasons = {e["market_id"]: e.get("reason") for e in out["ledger"]
               if e["action"] == "skip"}
    assert reasons == REFUSALS
    assert {e["market_id"]: e["winner"] for e in out["ledger"]
            if e["action"] == "settle"} == {
        SPEC: "Anderlecht", HONEST: "Draw (Real Sociedad vs. Dynamo Kyiv)", THIRD: "Ajax"}
    # Not a byte, not a row version, and no backup table.
    assert await _markets(db) == markets and await _legs(db) == legs
    assert await _bak(db) == []


async def test_the_dry_run_and_the_apply_both_need_exact_ids(db):
    assert (await _run(db))["terminal"] == "refused_no_exact_ids"
    assert (await _run(db, apply=True))["terminal"] == "refused_no_exact_ids"
    nohash = await _run(db, only_ids=_ids(SPEC), apply=True)
    assert nohash["terminal"] == "refused_no_plan_hash"
    over = await _run(db, only_ids=_ids(*range(1, rs.APPLY_MARKET_CAP + 2)))
    assert over["terminal"] == "refused_bad_only_ids"
    wrong = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash="0" * 32)
    assert wrong["terminal"] == "refused_plan_drift"
    assert {m[1] for m in (await _markets(db, set(SETTLES))).values()} == {"open"}
    assert await _bak(db) == []


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------

async def test_a_settled_market_leaves_open_and_nothing_else_moves(db):
    markets, legs = await _markets(db), await _legs(db)
    plan = await _run(db, only_ids=_ids(*ALL_IDS))
    out = await _run(db, only_ids=_ids(*ALL_IDS), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied" and out["settled"] == 3
    assert out["refused_markets"] == []

    after = await _markets(db)
    for mid in SETTLES:
        _, status, settled_at, meta, ver = after[mid]
        assert status == "resolved"
        assert settled_at is not None
        assert ver != markets[mid][4]
        assert isinstance(_meta(meta), dict), meta
        gate = _meta(meta)["resolution_gate"]
        assert gate["proof_kind"] == "winner"
        assert gate["task"] == rs.TASK and gate["plan_hash"] == plan["plan_hash"]
    # First observation kept; a sibling metadata key kept.
    assert after[THIRD][2] == FIRST_SEEN
    assert _meta(after[HONEST][3])["polymarket_event_id"] == "10001"
    # Every refused market, and every leg everywhere, is byte-identical.
    assert {m: after[m] for m in REFUSALS} == {m: markets[m] for m in REFUSALS}
    assert await _legs(db) == legs
    bank = await _bak(db)
    assert [(b[0], b[1], b[2], b[3]) for b in bank] == [
        (mid, "open", "resolved", plan["plan_hash"]) for mid in SETTLES]
    assert [b[4] for b in bank] == [after[mid][4] for mid in SETTLES]

    # And a second apply of the same plan finds nothing to do.
    again = await _run(db, only_ids=_ids(*SETTLES))
    assert again["planned_market_ids"] == []
    assert {e["reason"] for e in again["ledger"]} == {"already_settled"}


@pytest.mark.parametrize("touch", [
    "UPDATE futures_markets SET status = status WHERE id = 55254886",
    "UPDATE futures_markets SET market_metadata = market_metadata WHERE id = 55254887",
    "UPDATE futures_outcomes SET is_winner = is_winner WHERE id = 205060694",
], ids=["market-same-value", "metadata-same-value", "leg-same-value"])
async def test_a_same_value_write_after_the_dry_run_refuses_the_reviewed_hash(db, touch):
    plan = await _run(db, only_ids=_ids(*SETTLES))
    await _touch(db, touch)
    markets = await _markets(db)
    out = await _run(db, only_ids=_ids(*SETTLES), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift"
    assert out["detail"]["reviewed"] == plan["plan_hash"]
    assert await _markets(db) == markets
    assert await _bak(db) == []


async def test_a_write_between_the_plan_and_the_lock_refuses_that_market(db, monkeypatch):
    plan = await _run(db, only_ids=_ids(*SETTLES))
    original = rs._apply_market

    async def touched_first(session, p, digest):
        if p["market_id"] == SPEC:
            await _touch(db, "UPDATE futures_markets SET status = status WHERE id = 55254886")
        return await original(session, p, digest)

    monkeypatch.setattr(rs, "_apply_market", touched_first)
    out = await _run(db, only_ids=_ids(*SETTLES), apply=True, plan_hash=plan["plan_hash"])
    assert out["settled"] == 2 and out["drift_refused"] == 1
    assert out["refused_markets"] == [{"market_id": SPEC, "reason": rs.DRIFT}]
    assert (await _markets(db, {SPEC}))[SPEC][1] == "open"
    assert [b[0] for b in await _bak(db)] == [HONEST, THIRD]


# ---------------------------------------------------------------------------
# a stopped run, the audit and the restore
# ---------------------------------------------------------------------------

async def test_a_stopped_run_is_banked_auditable_and_restores_exactly(db, monkeypatch):
    seed = await _markets(db, set(SETTLES))
    plan = await _run(db, only_ids=_ids(*SETTLES))
    # HONEST fails at its write, after its bank copy, inside the transaction.
    await _touch(db, (
        "CREATE FUNCTION refuse_one_market() RETURNS trigger LANGUAGE plpgsql AS $$"
        " BEGIN IF NEW.id = 55254887 AND NEW.status = 'resolved' THEN"
        " RAISE EXCEPTION 'dyno lost'; END IF; RETURN NEW; END $$"))
    await _touch(db, (
        "CREATE TRIGGER refuse_one BEFORE UPDATE ON futures_markets"
        " FOR EACH ROW EXECUTE FUNCTION refuse_one_market()"))
    original = rs._apply_market

    async def stops_at_third(session, p, digest):
        if p["market_id"] == THIRD:
            raise asyncio.CancelledError("router timeout")
        return await original(session, p, digest)

    monkeypatch.setattr(rs, "_apply_market", stops_at_third)
    with pytest.raises(asyncio.CancelledError):
        await _run(db, only_ids=_ids(*SETTLES), apply=True, plan_hash=plan["plan_hash"])

    after = await _markets(db, set(SETTLES))
    assert after[SPEC][1] == "resolved"
    assert after[HONEST] == seed[HONEST] and after[THIRD] == seed[THIRD]
    # Only the committed market is banked; HONEST's copy rolled back with its write.
    assert [(b[0], b[4]) for b in await _bak(db)] == [(SPEC, after[SPEC][4])]

    audit = await _run(db, fn=rs.restore)
    assert audit["terminal"] == "dry_run"
    assert audit["by_plan_hash"] == {plan["plan_hash"]: {"settled": 1, "restored": 0,
                                                         "moved": 0}}
    done = await _run(db, fn=rs.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_markets"] == 1 and done["refused_markets"] == []
    back = await _markets(db, set(SETTLES))
    assert {m: back[m][:4] for m in SETTLES} == {m: seed[m][:4] for m in SETTLES}
    again = await _run(db, fn=rs.restore)
    assert again["markets"] == [{"market_id": SPEC, "plan_hash": plan["plan_hash"],
                                 "state": "restored"}]


async def test_restore_puts_back_exactly_the_before_image(db):
    seed = await _markets(db, set(SETTLES))
    plan = await _run(db, only_ids=_ids(*SETTLES))
    await _run(db, only_ids=_ids(*SETTLES), apply=True, plan_hash=plan["plan_hash"])
    done = await _run(db, fn=rs.restore, apply=True)
    assert done["restored_markets"] == 3
    back = await _markets(db, set(SETTLES))
    # status, settled_at (NULL and stamped alike) and metadata, byte for byte.
    assert {m: back[m][:4] for m in SETTLES} == {m: seed[m][:4] for m in SETTLES}
    assert "resolution_gate" not in (_meta(back[HONEST][3]) or {})


@pytest.mark.parametrize("touch", [
    "UPDATE futures_markets SET status = status WHERE id = 55254886",
    "UPDATE futures_markets SET settled_at = settled_at WHERE id = 55254886",
    "UPDATE futures_markets SET market_metadata = market_metadata WHERE id = 55254886",
], ids=["status", "settled_at", "metadata"])
async def test_restore_never_overwrites_a_same_value_later_writer(db, touch):
    plan = await _run(db, only_ids=_ids(*SETTLES))
    await _run(db, only_ids=_ids(*SETTLES), apply=True, plan_hash=plan["plan_hash"])
    await _touch(db, touch)
    later = await _markets(db, {SPEC})
    audit = await _run(db, fn=rs.restore)
    assert {m["market_id"]: m["state"] for m in audit["markets"]} == {
        SPEC: "moved", HONEST: "settled", THIRD: "settled"}
    done = await _run(db, fn=rs.restore, apply=True)
    assert done["restored_markets"] == 2 and done["refused_markets"] == []
    assert await _markets(db, {SPEC}) == later


async def test_a_market_restored_and_planned_again_re_banks_its_true_prior(db):
    seed = await _markets(db, {SPEC})
    first = await _run(db, only_ids=_ids(SPEC))
    await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=first["plan_hash"])
    await _run(db, fn=rs.restore, apply=True)
    second = await _run(db, only_ids=_ids(SPEC))
    assert second["plan_hash"] != first["plan_hash"]  # the row version moved
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=second["plan_hash"])
    assert out["settled"] == 1
    bank = await _bak(db)
    assert bank[0][3] == second["plan_hash"]
    await _run(db, fn=rs.restore, apply=True)
    assert (await _markets(db, {SPEC}))[SPEC][:4] == seed[SPEC][:4]
