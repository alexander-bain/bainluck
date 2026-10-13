"""#1527: the three-winner soccer repair's guarded apply against a real PostgreSQL —
the exact-id plan, compare-and-set under row locks, per-transaction timeouts,
row-count refusal, the D51 backup, the audit of a stopped run, and a restore that
never overwrites a later writer, including one that left every value the same.

Runs in a throwaway database on the local CI service, never production. The
tables carry the columns the rail reads and writes; the SQL under test is the
module's own. The CLOB is a fake keyed by condition id.

Seeds:

* **SPEC** 55254886, the issue's specimen: Slavia Praha / Anderlecht / Draw all
  crowned at 1.0 with a 1.0 opening and calibration price. The venue says
  Anderlecht.
* **HONEST** a second Europa fixture whose Slavia-side leg holds a GENUINE 0.41
  opening beside an impossible calibration price, and whose Away leg has NULL
  opening and calibration prices. The venue says Draw. Only the impossible
  values may become NULL.
* **VOID** (venue: nobody won), **CONTRA** (venue: two winners), **FOREIGN**
  (one leg already `api_settlement`) and **UNKNOWN** (a source the ladder does
  not know): three-way soccer, refused.
* Cross-cohort **controls**, all incoherent and all naming a "Draw"/"Tie" leg
  where it could matter: a Polymarket GOLF field, a Polymarket FOOTBALL field
  with a Tie leg, a soccer two-leg DUEL, a KALSHI three-way soccer market and a
  three-leg soccer field with NO Draw leg (a top-scorer market).
  None may move even when an operator names it.
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.polymarket_api as polymarket_api
import app.tasks.repair_winner_field as rp

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #1527 repair gate"
    ),
]

UTC = timezone.utc
SEEDED_AT = datetime(2026, 8, 3, 16, 4, tzinfo=UTC)
OPENED_AT = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)

SPEC, HONEST, VOID, CONTRA, FOREIGN, UNKNOWN = (
    55254886, 55254887, 60000001, 60000002, 60000003, 60000004)
GOLF, FOOTBALL, DUEL, KALSHI, NODRAW = 60000011, 60000012, 60000013, 60000014, 60000015
CONTROLS = (GOLF, FOOTBALL, DUEL, KALSHI, NODRAW)
REFUSED = (VOID, CONTRA, FOREIGN, UNKNOWN)

#: market id -> (source, sport, market_type)
MARKETS = {
    SPEC: ("polymarket", "soccer", "field"),
    HONEST: ("polymarket", "soccer", "field"),
    VOID: ("polymarket", "soccer", "field"),
    CONTRA: ("polymarket", "soccer", "duel"),
    FOREIGN: ("polymarket", "soccer", "field"),
    UNKNOWN: ("polymarket", "soccer", "field"),
    GOLF: ("polymarket", "golf", "field"),
    FOOTBALL: ("polymarket", "football", "field"),
    DUEL: ("polymarket", "soccer", "duel"),
    KALSHI: ("kalshi", "soccer", "field"),
    NODRAW: ("polymarket", "soccer", "field"),
}

#: (outcome id, market id, name, venue yes_winner)
LEGS = [
    (205060693, SPEC, "Slavia Praha", False),
    (205060694, SPEC, "Anderlecht", True),
    (205060695, SPEC, "Draw", False),
    (205060700, HONEST, "Real Sociedad", False),
    (205060701, HONEST, "Dynamo Kyiv", False),
    (205060702, HONEST, "Draw (Real Sociedad vs. Dynamo Kyiv)", True),
    (600000011, VOID, "Home", False),
    (600000012, VOID, "Away", False),
    (600000013, VOID, "Draw", False),
    (600000021, CONTRA, "Home", True),
    (600000022, CONTRA, "Away", True),
    (600000023, CONTRA, "Draw", False),
    (600000031, FOREIGN, "Home", True),
    (600000032, FOREIGN, "Away", False),
    (600000033, FOREIGN, "Draw", False),
    (600000041, UNKNOWN, "Home", True),
    (600000042, UNKNOWN, "Away", False),
    (600000043, UNKNOWN, "Draw", False),
    (600000111, GOLF, "Scottie Scheffler", True),
    (600000112, GOLF, "Rory McIlroy", False),
    (600000113, GOLF, "Draw for the lead", False),
    (600000121, FOOTBALL, "Chiefs", True),
    (600000122, FOOTBALL, "Bills", False),
    (600000123, FOOTBALL, "Tie (Draw)", False),
    (600000131, DUEL, "Arsenal", True),
    (600000132, DUEL, "Chelsea", False),
    (600000141, KALSHI, "Home", True),
    (600000142, KALSHI, "Away", False),
    (600000143, KALSHI, "Draw", False),
    (600000151, NODRAW, "Haaland", True),
    (600000152, NODRAW, "Kane", False),
    (600000153, NODRAW, "Mbappe", False),
]

#: outcome id -> (opening_probability, calibration_probability, resolution_source)
FIELDS = {
    205060700: (0.41, 1.0, "clean_resolution"),
    205060701: (None, None, "clean_resolution"),
    600000031: (1.0, 1.0, "api_settlement"),
    600000041: (1.0, 1.0, "mystery_grader"),
}

ALL_IDS = sorted(MARKETS)


def _cid(oid: int) -> str:
    return f"0x{oid:064x}"


VENUE = {_cid(oid): won for oid, _, _, won in LEGS}


class FakeClob:
    """The CLOB, by condition id. ``calls`` counts reads."""

    calls = 0
    answers = VENUE

    async def get_clob_market_by_condition(self, condition_id):
        FakeClob.calls += 1
        won = FakeClob.answers.get(condition_id)
        if won is None:
            return None
        return {"condition_id": condition_id, "closed": True,
                "tokens": [{"outcome": "Yes", "winner": won},
                           {"outcome": "No", "winner": not won}]}


@pytest.fixture(scope="session")
def isolated_database():
    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "winner_field_1527_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        yield url.set(database=database)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def db(isolated_database, monkeypatch):
    monkeypatch.setattr(polymarket_api, "PolymarketAPIService", FakeClob)
    FakeClob.calls = 0
    FakeClob.answers = dict(VENUE)
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for t in (rp.BAK_TABLE, "futures_outcomes", "futures_markets"):
            await s.execute(text(f"DROP TABLE IF EXISTS {t}"))
        await s.execute(text("DROP FUNCTION IF EXISTS skip_one_leg() CASCADE"))
        await s.execute(text(
            "CREATE TABLE futures_markets (id BIGINT PRIMARY KEY,"
            " source VARCHAR(50) NOT NULL, external_id VARCHAR(200) NOT NULL,"
            " name VARCHAR(300) NOT NULL, category VARCHAR(50) NOT NULL,"
            " llm_sport_category VARCHAR(50), market_type VARCHAR(30),"
            " mutually_exclusive BOOLEAN NOT NULL, status VARCHAR(20) NOT NULL)"))
        await s.execute(text(
            "CREATE TABLE futures_outcomes (id BIGINT PRIMARY KEY,"
            " market_id BIGINT NOT NULL REFERENCES futures_markets(id),"
            " external_id VARCHAR(200) NOT NULL, name VARCHAR(300) NOT NULL,"
            " current_probability NUMERIC(7,6), opening_probability NUMERIC(7,6),"
            " opening_american_odds INTEGER, opening_captured_at TIMESTAMPTZ,"
            " opening_source VARCHAR(30), calibration_probability NUMERIC(7,6),"
            " is_winner BOOLEAN DEFAULT false, resolution_source VARCHAR(30),"
            " last_updated TIMESTAMPTZ NOT NULL)"))
        for mid, (source, sport, mtype) in MARKETS.items():
            await s.execute(text(
                "INSERT INTO futures_markets (id, source, external_id, name, category,"
                " llm_sport_category, market_type, mutually_exclusive, status)"
                " VALUES (:i, :src, :x, :n, 'championship', :sp, :mt, true, 'open')"),
                dict(i=mid, src=source, x=f"event-{mid}", n=f"market {mid}", sp=sport,
                     mt=mtype))
        for oid, mid, name, _ in LEGS:
            op, cp, src = FIELDS.get(oid, (1.0, 1.0, "clean_resolution"))
            await s.execute(text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name,"
                " current_probability, opening_probability, opening_american_odds,"
                " opening_captured_at, opening_source, calibration_probability,"
                " is_winner, resolution_source, last_updated)"
                " VALUES (:i, :m, :x, :n, 1.0, :op, :odds, :at, :osrc, :cp, true, :src,"
                " :lu)"),
                dict(i=oid, m=mid, x=_cid(oid), n=name, op=op,
                     odds=None if op is None else -10000,
                     at=None if op is None else OPENED_AT,
                     osrc=None if op is None else "first_snapshot",
                     cp=cp, src=src, lu=SEEDED_AT))
        await s.commit()
    yield maker
    await engine.dispose()


_STATE_COLS = ("id, market_id, is_winner, current_probability, resolution_source,"
               " opening_probability, opening_american_odds, opening_captured_at,"
               " opening_source, calibration_probability")


async def _state(maker, mids=None):
    async with maker() as s:
        rows = (await s.execute(text(
            f"SELECT {_STATE_COLS} FROM futures_outcomes ORDER BY id"))).all()
    return [tuple(r) for r in rows if mids is None or r.market_id in mids]


async def _run(maker, fn=None, **kw):
    async with maker() as s:
        return await (fn or rp.repair)(s, **kw)


def _ids(*mids):
    return ",".join(str(m) for m in mids)


async def _bak(maker):
    async with maker() as s:
        if not (await s.execute(text(rp._EXISTS), {"t": rp.BAK_TABLE})).scalar_one():
            return []
        return [tuple(r) for r in (await s.execute(text(
            f"SELECT outcome_id, market_id, plan_hash FROM {rp.BAK_TABLE}"
            " ORDER BY outcome_id"))).all()]


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

async def test_the_exact_dry_run_plans_only_the_cohort_and_writes_nothing(db):
    before = await _state(db)
    out = await _run(db, only_ids=_ids(*ALL_IDS))
    assert out["terminal"] == "dry_run" and out["mode"] == "exact"
    assert out["planned_market_ids"] == [SPEC, HONEST]
    assert out["outcomes_planned"] == 6
    assert out["skip_reasons"] == {
        "no_winner_void": 1, "multiple_clob_winners": 1, "foreign_authority": 1,
        "unknown_authority": 1, "not_soccer": 2, "not_three_way": 1,
        "not_polymarket": 1, "not_one_draw_leg": 1,
    }
    by_id = {e["market_id"]: e for e in out["ledger"]}
    assert by_id[SPEC]["winner"] == "Anderlecht"
    assert by_id[SPEC]["was_winners"] == 3
    assert by_id[GOLF]["reason"] == "not_soccer"
    assert by_id[FOOTBALL]["reason"] == "not_soccer"
    assert by_id[UNKNOWN]["detail"] == ["mystery_grader"]
    assert by_id[NODRAW]["reason"] == "not_one_draw_leg"
    # Cross-cohort controls are refused before the venue is asked anything.
    assert FakeClob.calls == 3 * 4
    assert len(out["plan_hash"]) == 32
    assert await _state(db) == before
    assert await _bak(db) == []


async def test_the_discovery_walk_finds_the_cohort_and_cannot_write(db):
    before = await _state(db)
    out = await _run(db, limit=100)
    assert out["mode"] == "discovery" and out["exhausted"] is True
    assert out["planned_market_ids"] == [SPEC, HONEST]
    assert out["plan_hash"] is None
    # Golf, football and Kalshi never enter the discovery window at all.
    assert {e["market_id"] for e in out["ledger"]} == {SPEC, HONEST, *REFUSED, DUEL, NODRAW}
    refused = await _run(db, limit=100, apply=True, plan_hash="0" * 32)
    assert refused["terminal"] == "refused_no_exact_ids"
    assert await _state(db) == before


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------

async def test_the_pinned_apply_writes_exactly_the_plan(db):
    untouched = await _state(db, set(REFUSED) | set(CONTROLS))
    plan = await _run(db, only_ids=_ids(*ALL_IDS))
    out = await _run(db, only_ids=_ids(*ALL_IDS), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied"
    assert (out["repaired"], out["outcomes_written"], out["drift_refused"],
            out["backup_refused"], out["rowcount_refused"]) == (2, 6, 0, 0, 0)

    state = {r[0]: r for r in await _state(db, {SPEC, HONEST})}
    winners = {oid for oid, r in state.items() if r[2]}
    assert winners == {205060694, 205060702}
    for oid, r in state.items():
        assert float(r[3]) == (1.0 if oid in winners else 0.0)
        assert r[4] == rp.WRITE_SOURCE
    # The specimen's impossible openings and calibration prices are withdrawn.
    for oid in (205060693, 205060694, 205060695, 205060702):
        assert state[oid][5:] == (None, None, None, None, None)
    # A genuine sub-certain opening survives beside a withdrawn calibration price,
    # and an honest NULL stays NULL.
    assert float(state[205060700][5]) == 0.41
    assert state[205060700][6:9] == (-10000, OPENED_AT, "first_snapshot")
    assert state[205060700][9] is None
    assert state[205060701][5:] == (None, None, None, None, None)
    assert out["openings_nulled"] == 4 and out["cp_nulled"] == 5

    assert await _state(db, set(REFUSED) | set(CONTROLS)) == untouched
    bak = await _bak(db)
    assert [b[0] for b in bak] == sorted(state)
    assert {b[2] for b in bak} == {plan["plan_hash"]}
    # Each leg's bank row carries the version this write left on it.
    async with db() as s:
        pairs = (await s.execute(text(
            f"SELECT b.wrote_row_version, fo.xmin::text FROM {rp.BAK_TABLE} b"
            " JOIN futures_outcomes fo ON fo.id = b.outcome_id"))).all()
    assert len(pairs) == 6 and all(w is not None and w == x for w, x in pairs)


async def test_named_controls_never_move_beside_a_real_repair(db):
    controls = await _state(db, set(CONTROLS))
    named = _ids(SPEC, *CONTROLS)
    plan = await _run(db, only_ids=named)
    assert plan["planned_market_ids"] == [SPEC]
    out = await _run(db, only_ids=named, apply=True, plan_hash=plan["plan_hash"])
    assert out["repaired"] == 1
    assert await _state(db, set(CONTROLS)) == controls
    assert {b[1] for b in await _bak(db)} == {SPEC}


async def test_apply_without_exact_ids_or_hash_is_refused_whole(db):
    before = await _state(db)
    assert (await _run(db, apply=True))["terminal"] == "refused_no_exact_ids"
    assert (await _run(db, apply=True, only_ids=_ids(SPEC)))["terminal"] == \
        "refused_no_plan_hash"
    stale = await _run(db, apply=True, only_ids=_ids(SPEC), plan_hash="0" * 32)
    assert stale["terminal"] == "refused_plan_drift" and stale["repaired"] == 0
    over = await _run(db, apply=True, only_ids=_ids(*range(1, rp.APPLY_MARKET_CAP + 2)),
                      plan_hash="0" * 32)
    assert over["terminal"] == "refused_bad_only_ids"
    assert await _state(db) == before
    assert await _bak(db) == []


async def test_a_plan_reviewed_on_one_id_set_cannot_authorize_another(db):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift"
    assert await _bak(db) == []


# The OLD apply's write, verbatim from origin/master before this change. It was
# keyed on market_id alone and re-read nothing it had planned on.
OLD_APPLY_SQL = """
    UPDATE futures_outcomes
    SET is_winner = (id = :win_id),
        current_probability = CASE WHEN id = :win_id
                                   THEN 1.0 ELSE 0.0 END,
        resolution_source = :src,
        last_updated = NOW()
    WHERE market_id = :mid
"""


async def test_the_old_apply_accepted_drift_and_the_guarded_one_refuses(db):
    plan = await _run(db, only_ids=_ids(SPEC))
    # After review, the venue settlement path grades the Slavia leg itself.
    async with db() as s:
        await s.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'api_settlement',"
            " is_winner = false, current_probability = 0.0 WHERE id = 205060693"))
        await s.commit()
    drifted = await _state(db, {SPEC})

    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift" and out["repaired"] == 0
    assert await _state(db, {SPEC}) == drifted
    assert await _bak(db) == []

    # Strawman: the old write runs straight over the venue's own grade.
    async with db() as s:
        n = (await s.execute(text(OLD_APPLY_SQL), {
            "win_id": 205060694, "mid": SPEC, "src": rp.WRITE_SOURCE})).rowcount
        src = (await s.execute(text(
            "SELECT resolution_source FROM futures_outcomes WHERE id = 205060693"
        ))).scalar_one()
        await s.rollback()
    assert n == 3 and src == rp.WRITE_SOURCE


SAME_VALUE_WRITES = {
    # A writer that leaves every reviewed value exactly as it was.
    "same_value_update": "UPDATE futures_outcomes SET is_winner = is_winner,"
                         " current_probability = current_probability WHERE id = :oid",
    # A poll's touch-stamp.
    "touch_stamp": "UPDATE futures_outcomes SET last_updated = NOW() WHERE id = :oid",
}


async def _write_beside(maker, sql, oid):
    async with maker() as s:
        await s.execute(text(sql), {"oid": oid})
        await s.commit()


async def _xmin(maker, oid):
    async with maker() as s:
        return (await s.execute(text(
            "SELECT xmin::text FROM futures_outcomes WHERE id = :o"), {"o": oid})).scalar_one()


def _without_versions(entry):
    return {k: v for k, v in entry.items() if k not in ("row_versions", "prior_last_updated")}


@pytest.mark.parametrize("write", sorted(SAME_VALUE_WRITES))
async def test_a_write_between_the_dry_run_and_the_apply_refuses_the_old_hash(db, write):
    # Root's hold on 9298be4a, point 1: dry run -> a same-value write to ONE
    # exact leg -> apply with the reviewed hash. Every value the operator
    # reviewed still holds; the row version does not, so the apply refuses whole.
    seed = await _state(db)
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _write_beside(db, SAME_VALUE_WRITES[write], 205060695)
    assert await _state(db) == seed

    out = await _run(db, only_ids=_ids(SPEC, HONEST), apply=True,
                     plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift" and out["repaired"] == 0
    assert out["detail"]["reviewed"] == plan["plan_hash"]
    assert await _state(db) == seed
    assert await _bak(db) == []

    # The fresh dry run differs from the reviewed one in that leg's version and
    # in nothing else; it is the plan the operator now reviews, and it applies.
    fresh = await _run(db, only_ids=_ids(SPEC, HONEST))
    old, new = ({e["market_id"]: e for e in x["ledger"]} for x in (plan, fresh))
    assert new[HONEST] == old[HONEST]
    assert _without_versions(new[SPEC]) == _without_versions(old[SPEC])
    moved = {o for o, v in old[SPEC]["row_versions"].items()
             if new[SPEC]["row_versions"][o] != v}
    assert moved == {205060695}
    assert fresh["plan_hash"] != plan["plan_hash"]
    applied = await _run(db, only_ids=_ids(SPEC, HONEST), apply=True,
                         plan_hash=fresh["plan_hash"])
    assert applied["terminal"] == "applied" and applied["repaired"] == 2


async def test_strawman_an_address_without_row_versions_lets_the_old_hash_through(
        db, monkeypatch):
    # The held head's address, which left row versions out: the same sequence
    # applies over a row version nobody reviewed. This is what the test above
    # refuses.
    original = rp.plan_hash_for
    monkeypatch.setattr(rp, "plan_hash_for", lambda named, planned: original(
        named, [{**p, "row_versions": {}} for p in planned]))
    plan = await _run(db, only_ids=_ids(SPEC))
    await _write_beside(db, SAME_VALUE_WRITES["same_value_update"], 205060695)
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied" and out["repaired"] == 1


async def test_a_row_moved_between_the_apply_read_and_its_lock_refuses_that_market(
        db, monkeypatch):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    original = rp._apply_market
    timeouts = []

    async def racing(session, p, digest):
        timeouts.append(((await session.execute(text("SHOW lock_timeout"))).scalar_one(),
                         (await session.execute(text("SHOW statement_timeout"))).scalar_one()))
        if p["market_id"] == SPEC:
            # A concurrent writer touches one leg; no planned value changes, but
            # the row version the apply read is gone.
            async with db() as other:
                await other.execute(text(
                    "UPDATE futures_outcomes SET last_updated = NOW() WHERE id = 205060695"))
                await other.commit()
        return await original(session, p, digest)

    monkeypatch.setattr(rp, "_apply_market", racing)
    spec_before = await _state(db, {SPEC})
    out = await _run(db, only_ids=_ids(SPEC, HONEST), apply=True,
                     plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied"
    assert out["repaired"] == 1 and out["drift_refused"] == 1
    assert out["refused_markets"] == [{"market_id": SPEC, "reason": rp.DRIFT}]
    assert await _state(db, {SPEC}) == spec_before
    assert {b[1] for b in await _bak(db)} == {HONEST}
    # Bounded in EVERY market transaction, not just the first one before a commit.
    assert timeouts == [("2s", "20s"), ("2s", "20s")]


async def test_a_locked_value_that_disagrees_with_the_plan_refuses_its_market(
        db, monkeypatch):
    # In PostgreSQL any change to a planned value also moves the row version, so
    # the version check usually fires first. This pins the value check on its
    # own: same row version, a planned value the locked row does not hold.
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    original = rp._apply_market

    async def misread(session, p, digest):
        if p["market_id"] == SPEC:
            p = {**p, "legs": [{**p["legs"][0], "current_probability": 0.5},
                               *p["legs"][1:]]}
        return await original(session, p, digest)

    monkeypatch.setattr(rp, "_apply_market", misread)
    spec_before = await _state(db, {SPEC})
    out = await _run(db, only_ids=_ids(SPEC, HONEST), apply=True,
                     plan_hash=plan["plan_hash"])
    assert out["refused_markets"] == [{"market_id": SPEC, "reason": rp.DRIFT}]
    assert await _state(db, {SPEC}) == spec_before


async def test_a_short_row_count_rolls_the_market_back_with_its_backup(db):
    async with db() as s:
        await s.execute(text(
            "CREATE FUNCTION skip_one_leg() RETURNS trigger LANGUAGE plpgsql AS $$"
            " BEGIN IF OLD.id = 205060695 AND NEW.resolution_source IS DISTINCT FROM"
            " OLD.resolution_source THEN RETURN NULL; END IF; RETURN NEW; END $$"))
        await s.execute(text(
            "CREATE TRIGGER skip_one BEFORE UPDATE ON futures_outcomes"
            " FOR EACH ROW EXECUTE FUNCTION skip_one_leg()"))
        await s.commit()
    before = await _state(db, {SPEC})
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    out = await _run(db, only_ids=_ids(SPEC, HONEST), apply=True,
                     plan_hash=plan["plan_hash"])
    assert out["rowcount_refused"] == 1 and out["repaired"] == 1
    assert out["refused_markets"] == [{"market_id": SPEC, "reason": rp.ROWCOUNT}]
    assert await _state(db, {SPEC}) == before
    assert {b[1] for b in await _bak(db)} == {HONEST}


# ---------------------------------------------------------------------------
# a stopped run, the audit and the restore
# ---------------------------------------------------------------------------

async def test_a_stopped_run_is_auditable_and_restores_exactly(db, monkeypatch):
    seed = await _state(db)
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    original = rp._apply_market

    async def dies_after_first(session, p, digest):
        if p["market_id"] == HONEST:
            raise asyncio.CancelledError("dyno restarted")
        return await original(session, p, digest)

    monkeypatch.setattr(rp, "_apply_market", dies_after_first)
    with pytest.raises(asyncio.CancelledError):
        await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])

    # The committed market carries its backup; the other carries nothing.
    assert {b[1] for b in await _bak(db)} == {SPEC}
    assert await _state(db, {HONEST}) == [r for r in seed if r[1] == HONEST]

    audit = await _run(db, fn=rp.restore)
    assert audit["terminal"] == "dry_run"
    assert audit["by_plan_hash"] == {plan["plan_hash"]: {"repaired": 1, "restored": 0,
                                                         "moved": 0}}
    assert audit["markets"] == [{"market_id": SPEC, "state": "repaired",
                                 "plan_hash": plan["plan_hash"],
                                 "legs": [205060693, 205060694, 205060695]}]

    done = await _run(db, fn=rp.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["terminal"] == "restored" and done["restored_markets"] == 1
    assert await _state(db) == seed
    again = await _run(db, fn=rp.restore)
    assert again["markets"][0]["state"] == "restored"


async def test_restore_never_overwrites_a_later_writer(db):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    async with db() as s:
        await s.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'api_settlement'"
            " WHERE id = 205060694"))
        await s.commit()
    later = await _state(db, {SPEC})
    audit = await _run(db, fn=rp.restore)
    states = {m["market_id"]: m["state"] for m in audit["markets"]}
    assert states == {SPEC: "moved", HONEST: "repaired"}
    done = await _run(db, fn=rp.restore, apply=True)
    # A moved market is left alone, not attempted and refused.
    assert done["restored_markets"] == 1 and done["refused_markets"] == []
    assert await _state(db, {SPEC}) == later


NO_VERSION = "TRUE"


@pytest.mark.parametrize("write", sorted(SAME_VALUE_WRITES))
async def test_restore_never_overwrites_a_same_value_later_writer(db, write):
    # Root's hold on 9298be4a, point 2: apply -> another writer's same-value
    # write to one leg -> restore. Every value this rail wrote still holds, so
    # a value-only audit would call the market repaired and put it back over
    # the later writer.
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    repaired = await _state(db, {SPEC})
    await _write_beside(db, SAME_VALUE_WRITES[write], 205060694)
    version = await _xmin(db, 205060694)
    assert await _state(db, {SPEC}) == repaired

    audit = await _run(db, fn=rp.restore)
    assert {m["market_id"]: m["state"] for m in audit["markets"]} == {
        SPEC: "moved", HONEST: "repaired"}
    done = await _run(db, fn=rp.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_markets"] == 1 and done["refused_markets"] == []
    assert await _state(db, {SPEC}) == repaired
    assert await _xmin(db, 205060694) == version


async def test_strawman_a_value_only_restore_overwrites_the_same_value_writer(
        db, monkeypatch):
    # The held head's restore, which compared values only: the same sequence
    # puts SPEC back to the three-winner seed over the later writer.
    seed = await _state(db, {SPEC})
    for name in ("_AUDIT_SQL", "_RESTORE_MARKET"):
        monkeypatch.setattr(rp, name, getattr(rp, name).replace(rp._WROTE_VERSION,
                                                                NO_VERSION))
    plan = await _run(db, only_ids=_ids(SPEC))
    await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=plan["plan_hash"])
    await _write_beside(db, SAME_VALUE_WRITES["same_value_update"], 205060694)
    done = await _run(db, fn=rp.restore, apply=True)
    assert done["restored_markets"] == 1
    assert await _state(db, {SPEC}) == seed


async def test_the_restore_write_itself_refuses_a_same_value_writer(db, monkeypatch):
    # The audit under the lock is one guard; the restore's own WHERE is the
    # second. With the audit blinded to versions, the WHERE alone refuses.
    monkeypatch.setattr(rp, "_AUDIT_SQL", rp._AUDIT_SQL.replace(rp._WROTE_VERSION,
                                                                 NO_VERSION))
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    await _write_beside(db, SAME_VALUE_WRITES["same_value_update"], 205060694)
    repaired = await _state(db, {SPEC})
    done = await _run(db, fn=rp.restore, apply=True)
    assert done["restored_markets"] == 1
    assert done["refused_markets"] == [{"market_id": SPEC, "reason": rp.ROWCOUNT}]
    assert await _state(db, {SPEC}) == repaired


async def test_a_same_value_writer_between_the_audit_and_the_lock_refuses_that_restore(
        db, isolated_database, monkeypatch):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    repaired = await _state(db, {SPEC})
    original = rp._market_states
    raced = []

    def audit_then_race(rows):
        out = original(rows)
        if not raced:
            raced.append(True)
            engine = create_engine(isolated_database.set(drivername="postgresql+psycopg2"))
            with engine.begin() as c:
                c.execute(text(SAME_VALUE_WRITES["same_value_update"]), {"oid": 205060694})
            engine.dispose()
        return out

    monkeypatch.setattr(rp, "_market_states", audit_then_race)
    done = await _run(db, fn=rp.restore, apply=True)
    assert done["restored_markets"] == 1
    assert done["refused_markets"] == [{"market_id": SPEC, "reason": rp.DRIFT}]
    assert await _state(db, {SPEC}) == repaired


async def test_a_writer_between_the_audit_and_the_lock_refuses_that_restore(
        db, isolated_database, monkeypatch):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    original = rp._market_states
    raced = []

    def audit_then_race(rows):
        out = original(rows)
        if not raced:
            raced.append(True)
            # The venue grades a SPEC leg after the audit read, before the lock.
            # A sync write from inside the async run: a second connection.
            engine = create_engine(isolated_database.set(drivername="postgresql+psycopg2"))
            with engine.begin() as c:
                c.execute(text("UPDATE futures_outcomes SET resolution_source ="
                               " 'api_settlement' WHERE id = 205060694"))
            engine.dispose()
        return out

    monkeypatch.setattr(rp, "_market_states", audit_then_race)
    done = await _run(db, fn=rp.restore, apply=True)
    assert done["restored_markets"] == 1
    assert done["refused_markets"] == [{"market_id": SPEC, "reason": rp.DRIFT}]
    spec = {r[0]: r for r in await _state(db, {SPEC})}
    assert spec[205060694][4] == "api_settlement"
    assert spec[205060693][4] == rp.WRITE_SOURCE


async def test_a_short_restore_row_count_rolls_that_market_back(db):
    plan = await _run(db, only_ids=_ids(SPEC, HONEST))
    await _run(db, only_ids=_ids(SPEC, HONEST), apply=True, plan_hash=plan["plan_hash"])
    async with db() as s:
        await s.execute(text(
            "CREATE FUNCTION skip_one_leg() RETURNS trigger LANGUAGE plpgsql AS $$"
            " BEGIN IF OLD.id = 205060695 AND OLD.resolution_source = 'clob_field_repair'"
            " AND NEW.resolution_source IS DISTINCT FROM OLD.resolution_source"
            " THEN RETURN NULL; END IF; RETURN NEW; END $$"))
        await s.execute(text(
            "CREATE TRIGGER skip_one BEFORE UPDATE ON futures_outcomes"
            " FOR EACH ROW EXECUTE FUNCTION skip_one_leg()"))
        await s.commit()
    repaired = await _state(db, {SPEC})
    done = await _run(db, fn=rp.restore, apply=True)
    assert done["restored_markets"] == 1
    assert done["refused_markets"] == [{"market_id": SPEC, "reason": rp.ROWCOUNT}]
    assert await _state(db, {SPEC}) == repaired


async def test_a_retry_after_restore_is_valid_and_a_changed_prior_is_refused(db):
    seed = await _state(db, {SPEC})
    first = await _run(db, only_ids=_ids(SPEC))
    await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=first["plan_hash"])
    await _run(db, fn=rp.restore, apply=True)
    assert await _state(db, {SPEC}) == seed

    # An exact bank from the earlier run is a valid retry, re-attributed to it.
    retry = await _run(db, only_ids=_ids(SPEC))
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=retry["plan_hash"])
    assert out["repaired"] == 1
    assert {b[2] for b in await _bak(db)} == {retry["plan_hash"]}
    # The kept bank row carries THIS run's version, so this run restores.
    assert (await _run(db, fn=rp.restore, apply=True))["restored_markets"] == 1
    assert await _state(db, {SPEC}) == seed

    # The prior moved after the restore: the bank no longer describes it, so a
    # restore after this run would put back a state it never removed.
    async with db() as s:
        await s.execute(text(
            "UPDATE futures_outcomes SET opening_probability = 0.98 WHERE id = 205060693"))
        await s.commit()
    moved = await _state(db, {SPEC})
    third = await _run(db, only_ids=_ids(SPEC))
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=third["plan_hash"])
    assert out["backup_refused"] == 1 and out["repaired"] == 0
    assert await _state(db, {SPEC}) == moved


async def test_a_bank_from_the_older_head_gains_the_version_column(db):
    # A bank created by the held head has no version column. The apply adds it,
    # and stamps the legs it writes.
    old_shape = rp._BAK_CREATE.replace("        wrote_row_version TEXT,\n", "")
    assert old_shape != rp._BAK_CREATE
    async with db() as s:
        await s.execute(text(old_shape))
        await s.commit()
    plan = await _run(db, only_ids=_ids(SPEC))
    out = await _run(db, only_ids=_ids(SPEC), apply=True, plan_hash=plan["plan_hash"])
    assert out["repaired"] == 1
    audit = await _run(db, fn=rp.restore)
    assert [m["state"] for m in audit["markets"]] == ["repaired"]


async def test_restore_without_a_backup_is_refused(db):
    out = await _run(db, fn=rp.restore, apply=True)
    assert out["terminal"] == "refused_no_backup"
