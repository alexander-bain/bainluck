"""#11007: the Fed rate-cut page stops calling its undecided meetings Lost or the
question Settled. Against a real PostgreSQL, on the real ORM schema.

PILLAR: TRUTH. SHIP: the Fed rate-cut page stops calling the still-undecided
October and December 2026 meetings Lost or the whole question Settled, while its
genuinely decided legs keep their results.

The rows start POISONED, exactly as production holds them (read 2026-10-13,
recorded on #11007): parent 113883 (Gamma ``106884``) and its eight decomposed
legs ``status='resolved'``, ``settled_at`` and ``updated_at`` from the 2026-07-21
bulk write, ``resolution_date 2026-06-17``; every parent outcome
``api_settlement``; October ``is_winner=false`` at 0.0095 and December at 0.023.
The venue is its own bytes (``gamma-event-106884.json``, sha256 ``5ce0eea1…``),
served by a fake keyed on event id.

What is graded here, because a session double reads every one of these green:
the exact-id plan bound to every written row's ``xmin``, the ``FOR UPDATE``
compare-and-set, one transaction per parent, the before-images banked in the
write's own transaction, the restore that refuses a later writer even when that
writer changed nothing, and the reader's own route. Then the recurrence: the REAL
poll writer and the REAL (gated) Gamma grader re-run over the repaired rows, and
the REAL sunk-recovery selector, which could not reach the parent before.

Other seeds, each a parent the rail must refuse by name and never move:
**CLOSED_EVENT** (the venue closed the whole event), **GONE** (Gamma 404),
**LIMITED** (the venue read raises 429) and **MALFORMED** (one leg's ``closed``
arrives as the string ``"false"``).
"""

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.polymarket_api as polymarket_api
import app.tasks.repair_pm_open_leg_grade_11007 as rr

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #11007 gate"
    ),
]

UTC = timezone.utc
NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)
STALE = datetime(2026, 6, 17, tzinfo=UTC)
BULK_WRITE = datetime(2026, 7, 21, 20, 15, 2, tzinfo=UTC)

FIXTURE = (Path(__file__).resolve().parent.parent / "fixtures"
           / "polymarket_resolved_zero_legs_5343" / "gamma-event-106884.json")
SPECIMEN = json.loads(FIXTURE.read_bytes())
LEG_BY_TITLE = {m["groupItemTitle"]: m for m in SPECIMEN["markets"]}
STORED_TITLES = [
    "January Meeting", "March Meeting", "April Meeting", "June Meeting",
    "July Meeting", "September 2026 Meeting",
    "October 2026 Meeting", "December 2026 Meeting",
]
OCT = LEG_BY_TITLE["October 2026 Meeting"]["conditionId"]
DEC = LEG_BY_TITLE["December 2026 Meeting"]["conditionId"]
OPEN = (OCT, DEC)
CLOSED = tuple(LEG_BY_TITLE[t]["conditionId"] for t in STORED_TITLES[:6])

PARENT = 113883
#: Leg market ids; October lands on its real row id, 13792808.
CHILD = {LEG_BY_TITLE[t]["conditionId"]: 13792802 + i for i, t in enumerate(STORED_TITLES)}
P_OUT = {LEG_BY_TITLE[t]["conditionId"]: 2054100 + i for i, t in enumerate(STORED_TITLES)}
QUOTE = {OCT: 0.0095, DEC: 0.023}
OPEN_OUTCOMES = (P_OUT[OCT], P_OUT[DEC])

#: Refused parents: id -> (event id, expected reason).
CLOSED_EVENT, GONE, LIMITED, MALFORMED = 7100001, 7100002, 7100003, 7100004
REFUSED = {
    CLOSED_EVENT: ("910001", "event_not_open_at_venue"),
    GONE: ("910002", "venue_absent"),
    LIMITED: ("910003", "venue_error"),
    MALFORMED: ("910004", "leg_flag_malformed"),
}
ALL_PARENTS = sorted([PARENT, *REFUSED])


def _venue_copy(event_id: str) -> dict:
    """The specimen's bytes re-addressed: same legs, another event id. Each
    refused parent then differs from the specimen by the one field it names."""
    ev = copy.deepcopy(SPECIMEN)
    ev["id"] = event_id
    for m in ev["markets"]:
        m["conditionId"] = "0x" + event_id + m["conditionId"][2 + len(event_id):]
    return ev


class FakeGamma:
    """``GET /events/{id}``, by event id. ``events`` may be replaced per test."""

    events: dict = {}
    raises: set = set()
    calls = 0

    async def get_event_by_id(self, event_id):
        FakeGamma.calls += 1
        if str(event_id) in FakeGamma.raises:
            raise RuntimeError("429 Too Many Requests")
        ev = FakeGamma.events.get(str(event_id))
        return copy.deepcopy(ev) if ev is not None else None

    async def close(self):
        return None


def _default_events():
    closed = _venue_copy("910001")
    closed["closed"] = True
    malformed = _venue_copy("910004")
    for m in malformed["markets"]:
        if m["groupItemTitle"] == "October 2026 Meeting":
            m["closed"] = "false"
    limited = _venue_copy("910003")
    return {"106884": copy.deepcopy(SPECIMEN), "910001": closed,
            "910003": limited, "910004": malformed}


@pytest.fixture(scope="session")
def isolated_database():
    from app.models import models as _registers_every_table  # noqa: F401
    from app.services.database import Base

    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "open_leg_11007_" + uuid4().hex
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


def _seed_parent(s, FuturesMarket, mid, eid, legs, child_ids):
    s.add(FuturesMarket(
        id=mid, source="polymarket", external_id=eid, name="Fed rate cut by...?",
        category="economics", market_type="field", mutually_exclusive=False,
        group_id=f"polymarket:{eid}", status="resolved", settled_at=BULK_WRITE,
        resolution_date=STALE, volume_updated_at=BULK_WRITE,
        market_metadata={"polymarket_event_id": eid}))
    for cid in legs:
        s.add(FuturesMarket(
            id=child_ids[cid], source="polymarket", external_id=cid,
            name=f"Fed rate cut by {cid[:8]}?", category="economics",
            market_type="binary", mutually_exclusive=True,
            group_id=f"polymarket:{eid}", status="resolved", settled_at=BULK_WRITE,
            resolution_date=STALE, volume_updated_at=BULK_WRITE,
            market_metadata={"polymarket_event_id": eid}))


@pytest.fixture
async def db(isolated_database, monkeypatch):
    import app.tasks.base as task_base
    from app.models.models import FuturesMarket, FuturesOutcome

    url = isolated_database.render_as_string(hide_password=False)
    monkeypatch.setattr(task_base, "DATABASE_URL", url)
    monkeypatch.setattr(polymarket_api, "PolymarketAPIService", FakeGamma)
    monkeypatch.setattr(rr, "_now", lambda: NOW)
    FakeGamma.events = _default_events()
    FakeGamma.raises = {"910003"}
    FakeGamma.calls = 0
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for t in (rr.BAK_MARKETS, rr.BAK_OUTCOMES):
            await s.execute(text(f"DROP TABLE IF EXISTS {t}"))
        await s.execute(text("DROP FUNCTION IF EXISTS refuse_one_outcome() CASCADE"))
        await s.execute(text("TRUNCATE futures_markets CASCADE"))
        _seed_parent(s, FuturesMarket, PARENT, "106884", list(CHILD), CHILD)
        for mid, (eid, _) in sorted(REFUSED.items()):
            legs = [m["conditionId"] for m in _venue_copy(eid)["markets"]
                    if m["groupItemTitle"] in STORED_TITLES]
            _seed_parent(s, FuturesMarket, mid, eid, legs,
                         {c: mid * 100 + i for i, c in enumerate(legs)})
            await s.flush()
            for i, c in enumerate(legs):
                s.add(FuturesOutcome(
                    id=800000000 + (mid - 7100000) * 100 + i, market_id=mid,
                    external_id=c, name=c[:10],
                    is_winner=False, current_probability=0.01,
                    resolution_source="api_settlement"))
        await s.flush()
        for cid in CHILD:
            s.add(FuturesOutcome(
                id=P_OUT[cid], market_id=PARENT, external_id=cid,
                name=next(t for t in STORED_TITLES
                          if LEG_BY_TITLE[t]["conditionId"] == cid),
                is_winner=False, current_probability=QUOTE.get(cid, 0.0),
                resolution_source="api_settlement"))
            for i, side in enumerate(("yes", "no")):
                s.add(FuturesOutcome(
                    id=CHILD[cid] * 10 + i, market_id=CHILD[cid],
                    external_id=f"{cid}_{side}", name=side.title(),
                    current_probability=0.5))
        await s.commit()
    yield maker
    await engine.dispose()


_MARKET_STATE = ("SELECT id, status, settled_at, resolution_date, xmin::text"
                 " FROM futures_markets ORDER BY id")
_OUTCOME_STATE = ("SELECT id, is_winner, resolution_source, current_probability,"
                  " xmin::text FROM futures_outcomes ORDER BY id")


async def _markets(maker):
    async with maker() as s:
        return {r[0]: tuple(r) for r in (await s.execute(text(_MARKET_STATE))).all()}


async def _outcomes(maker):
    async with maker() as s:
        return {r[0]: tuple(r) for r in (await s.execute(text(_OUTCOME_STATE))).all()}


async def _bak_tables(maker):
    async with maker() as s:
        return [t for t in (rr.BAK_MARKETS, rr.BAK_OUTCOMES)
                if (await s.execute(text("SELECT to_regclass(:t) IS NOT NULL"),
                                    {"t": t})).scalar_one()]


async def _bank(maker):
    async with maker() as s:
        m = [tuple(r) for r in (await s.execute(text(
            f"SELECT market_id, prior_status, wrote_status, plan_hash, wrote_row_version"
            f" FROM {rr.BAK_MARKETS} ORDER BY market_id"))).all()]
        o = [tuple(r) for r in (await s.execute(text(
            f"SELECT outcome_id, prior_is_winner, prior_resolution_source, plan_hash,"
            f" wrote_row_version FROM {rr.BAK_OUTCOMES} ORDER BY outcome_id"))).all()]
    return m, o


async def _run(maker, fn=None, **kw):
    async with maker() as s:
        return await (fn or rr.repair)(s, **kw)


async def _touch(maker, sql):
    async with maker() as s:
        await s.execute(text(sql))
        await s.commit()


def _ids(*mids):
    return ",".join(str(m) for m in mids)


async def _apply_specimen(maker):
    plan = await _run(maker, only_ids=_ids(PARENT))
    out = await _run(maker, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied" and out["repaired_parents"] == 1, out
    return plan, out


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

async def test_the_dry_run_plans_only_the_specimen_and_writes_nothing(db):
    markets, outcomes = await _markets(db), await _outcomes(db)
    out = await _run(db, only_ids=_ids(*ALL_PARENTS))
    assert out["terminal"] == "dry_run"
    assert out["planned_parent_ids"] == [PARENT]
    assert {e["market_id"]: e.get("reason") for e in out["ledger"]
            if e["action"] == "skip"} == {m: r for m, (_, r) in REFUSED.items()}
    assert (out["planned_market_writes"], out["planned_outcome_writes"]) == (3, 2)
    # Not a byte, not a row version, and no backup table.
    assert await _markets(db) == markets and await _outcomes(db) == outcomes
    assert await _bak_tables(db) == []


async def test_dry_run_and_apply_both_need_exact_ids_and_the_reviewed_hash(db):
    markets = await _markets(db)
    assert (await _run(db))["terminal"] == "refused_no_exact_ids"
    assert (await _run(db, apply=True))["terminal"] == "refused_no_exact_ids"
    assert (await _run(db, only_ids=_ids(PARENT), apply=True))["terminal"] == \
        "refused_no_plan_hash"
    over = await _run(db, only_ids=_ids(*range(1, rr.APPLY_PARENT_CAP + 2)))
    assert over["terminal"] == "refused_bad_only_ids"
    wrong = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash="0" * 32)
    assert wrong["terminal"] == "refused_plan_drift"
    assert await _markets(db) == markets
    assert await _bak_tables(db) == []


# ---------------------------------------------------------------------------
# the write: poisoned rows -> open and ungraded, closed legs untouched
# ---------------------------------------------------------------------------

async def test_the_poisoned_specimen_becomes_open_and_ungraded(db):
    markets, outcomes = await _markets(db), await _outcomes(db)
    plan, out = await _apply_specimen(db)
    assert (out["markets_reopened"], out["outcomes_cleared"]) == (3, 2)
    after_m, after_o = await _markets(db), await _outcomes(db)

    # October and December: no verdict, quote kept.
    for cid in OPEN:
        _, won, src, prob, _ = after_o[P_OUT[cid]]
        assert (won, src) == (None, None)
        assert float(prob) == QUOTE[cid]
    # The parent and the two open legs: open, no settled_at, the venue's dates.
    assert after_m[PARENT][1:4] == ("open", None, datetime(2028, 1, 29, 4, 59, tzinfo=UTC))
    for cid in OPEN:
        assert after_m[CHILD[cid]][1:4] == (
            "open", None, datetime(2027, 1, 29, 4, 59, tzinfo=UTC))
    # The six legs the venue closed keep their results and their rows, byte for byte.
    for cid in CLOSED:
        assert after_o[P_OUT[cid]] == outcomes[P_OUT[cid]]
        assert after_o[P_OUT[cid]][1:3] == (False, "api_settlement")
        assert after_m[CHILD[cid]] == markets[CHILD[cid]]
    # Nothing else anywhere moved: refused parents, their legs, leg outcomes.
    written_m = {PARENT, CHILD[OCT], CHILD[DEC]}
    assert {k: v for k, v in after_m.items() if k not in written_m} == \
        {k: v for k, v in markets.items() if k not in written_m}
    assert {k: v for k, v in after_o.items() if k not in OPEN_OUTCOMES} == \
        {k: v for k, v in outcomes.items() if k not in OPEN_OUTCOMES}

    bank_m, bank_o = await _bank(db)
    assert [(b[0], b[1], b[2], b[3]) for b in bank_m] == [
        (m, "resolved", "open", plan["plan_hash"]) for m in sorted(written_m)]
    assert [b[4] for b in bank_m] == [after_m[m][4] for m in sorted(written_m)]
    assert [(b[0], b[1], b[2], b[3]) for b in bank_o] == [
        (o, False, "api_settlement", plan["plan_hash"]) for o in sorted(OPEN_OUTCOMES)]
    assert [b[4] for b in bank_o] == [after_o[o][4] for o in sorted(OPEN_OUTCOMES)]

    again = await _run(db, only_ids=_ids(PARENT))
    assert again["planned_parent_ids"] == []
    assert again["skip_reasons"] == {"nothing_to_repair": 1}


@pytest.mark.parametrize("parent", sorted(REFUSED))
async def test_a_refused_parent_never_moves_even_with_a_hash(db, parent):
    markets, outcomes = await _markets(db), await _outcomes(db)
    plan = await _run(db, only_ids=_ids(parent))
    assert plan["planned_parent_ids"] == []
    out = await _run(db, only_ids=_ids(parent), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied" and out["repaired_parents"] == 0
    assert await _markets(db) == markets and await _outcomes(db) == outcomes


@pytest.mark.parametrize("mutate,reason", [
    (lambda e: e.update(closed=True), "event_not_open_at_venue"),
    (lambda e: next(m for m in e["markets"] if m["conditionId"] == DEC).pop("closed"),
     "leg_flag_malformed"),
    (lambda e: e.update(markets=[m for m in e["markets"] if m["conditionId"] != OCT]),
     "stored_leg_absent_at_venue"),
    (lambda e: e.update(id="999"), "event_identity_mismatch"),
], ids=["closed-event", "absent-leg-flag", "leg-missing", "other-event"])
async def test_the_specimen_refuses_on_a_venue_answer_it_cannot_trust(db, mutate, reason):
    markets, outcomes = await _markets(db), await _outcomes(db)
    mutate(FakeGamma.events["106884"])
    plan = await _run(db, only_ids=_ids(PARENT))
    assert plan["skip_reasons"] == {reason: 1}
    await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert await _markets(db) == markets and await _outcomes(db) == outcomes


async def test_a_venue_change_between_review_and_apply_refuses_the_hash(db):
    plan = await _run(db, only_ids=_ids(PARENT))
    # The venue closes December after the operator read the plan.
    leg = next(m for m in FakeGamma.events["106884"]["markets"] if m["conditionId"] == DEC)
    leg["closed"] = True
    markets = await _markets(db)
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift"
    assert await _markets(db) == markets


@pytest.mark.parametrize("touch", [
    f"UPDATE futures_markets SET status = status WHERE id = {PARENT}",
    f"UPDATE futures_markets SET resolution_date = resolution_date WHERE id = {CHILD[OCT]}",
    f"UPDATE futures_outcomes SET is_winner = is_winner WHERE id = {P_OUT[DEC]}",
], ids=["parent", "open-leg", "open-outcome"])
async def test_a_same_value_write_after_the_dry_run_refuses(db, touch):
    plan = await _run(db, only_ids=_ids(PARENT))
    await _touch(db, touch)
    markets, outcomes = await _markets(db), await _outcomes(db)
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift"
    assert out["detail"]["reviewed"] == plan["plan_hash"]
    assert await _markets(db) == markets and await _outcomes(db) == outcomes
    assert await _bak_tables(db) == []


async def test_a_control_regraded_after_review_refuses_but_a_touch_does_not(db):
    """A control's GRADE is bound, its row version is not: the poll touches a
    closed leg's outcome every hour, and that is no reason to refuse. A changed
    grade on a control is, because the reviewed plan described another field."""
    closed = P_OUT[CLOSED[0]]
    plan = await _run(db, only_ids=_ids(PARENT))
    await _touch(db, f"UPDATE futures_outcomes SET is_winner = is_winner WHERE id = {closed}")
    touched = (await _outcomes(db))[closed]
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["repaired_parents"] == 1
    assert (await _outcomes(db))[closed] == touched  # never written

    await _run(db, fn=rr.restore, apply=True, plan_hash=plan["plan_hash"])
    plan = await _run(db, only_ids=_ids(PARENT))
    await _touch(db, f"UPDATE futures_outcomes SET is_winner = true WHERE id = {closed}")
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "refused_plan_drift"


async def test_a_write_between_the_plan_and_the_lock_refuses_the_whole_parent(db, monkeypatch):
    plan = await _run(db, only_ids=_ids(PARENT))
    original = rr._apply_parent

    async def touched_first(session, p, digest):
        await _touch(db, f"UPDATE futures_outcomes SET is_winner = is_winner"
                         f" WHERE id = {P_OUT[OCT]}")
        return await original(session, p, digest)

    monkeypatch.setattr(rr, "_apply_parent", touched_first)
    markets = await _markets(db)
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["repaired_parents"] == 0 and out["drift_refused"] == 1
    assert out["refused_parents"] == [{"market_id": PARENT, "reason": rr.DRIFT}]
    # Not even the parent's market rows moved: one parent, one transaction.
    assert await _markets(db) == markets
    assert (await _outcomes(db))[P_OUT[DEC]][1:3] == (False, "api_settlement")
    bank_m, bank_o = await _bank(db)
    assert bank_m == [] and bank_o == []


async def test_a_failure_mid_parent_rolls_back_every_row_and_its_bank(db):
    plan = await _run(db, only_ids=_ids(PARENT))
    await _touch(db, (
        "CREATE FUNCTION refuse_one_outcome() RETURNS trigger LANGUAGE plpgsql AS $$"
        f" BEGIN IF NEW.id = {P_OUT[DEC]} AND NEW.resolution_source IS NULL THEN"
        " RAISE EXCEPTION 'dyno lost'; END IF; RETURN NEW; END $$"))
    await _touch(db, (
        "CREATE TRIGGER refuse_one BEFORE UPDATE ON futures_outcomes"
        " FOR EACH ROW EXECUTE FUNCTION refuse_one_outcome()"))
    markets, outcomes = await _markets(db), await _outcomes(db)
    out = await _run(db, only_ids=_ids(PARENT), apply=True, plan_hash=plan["plan_hash"])
    assert out["repaired_parents"] == 0 and out["error_refused"] == 1
    assert await _markets(db) == markets and await _outcomes(db) == outcomes
    bank_m, bank_o = await _bank(db)
    assert bank_m == [] and bank_o == []


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(db, isolated_database, monkeypatch):
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    engine = create_async_engine(isolated_database)

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c
    finally:
        for dep in (get_db, get_db_rw, get_optional_user):
            app.dependency_overrides.pop(dep, None)
        await engine.dispose()


async def _served(client):
    r = await client.get(f"/api/futures/{PARENT}")
    assert r.status_code == 200, r.text
    body = r.json()
    return body["status"], {o["name"]: (o.get("is_winner"), o.get("resolution_source"))
                            for o in body["outcomes"]}


async def test_the_reader_route_stops_serving_settled_and_lost(db, client):
    status, legs = await _served(client)
    # The defect, as the reader's route serves it.
    assert status == "resolved"
    assert legs["October 2026 Meeting"] == (False, "api_settlement")
    assert legs["December 2026 Meeting"] == (False, "api_settlement")

    await _apply_specimen(db)
    status, legs = await _served(client)
    assert status == "open"
    assert legs["October 2026 Meeting"] == (None, None)
    assert legs["December 2026 Meeting"] == (None, None)
    for title in STORED_TITLES[:6]:
        assert legs[title] == (False, "api_settlement"), title


# ---------------------------------------------------------------------------
# audit and restore
# ---------------------------------------------------------------------------

async def test_restore_puts_back_exactly_the_before_image(db):
    markets, outcomes = await _markets(db), await _outcomes(db)
    plan, _ = await _apply_specimen(db)
    audit = await _run(db, fn=rr.restore)
    assert audit["terminal"] == "dry_run"
    assert audit["by_plan_hash"] == {plan["plan_hash"]: {"written": 1, "restored": 0,
                                                         "moved": 0}}
    done = await _run(db, fn=rr.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_parents"] == 1 and done["refused_parents"] == []
    back_m, back_o = await _markets(db), await _outcomes(db)
    assert {k: v[:4] for k, v in back_m.items()} == {k: v[:4] for k, v in markets.items()}
    assert {k: v[:4] for k, v in back_o.items()} == {k: v[:4] for k, v in outcomes.items()}
    again = await _run(db, fn=rr.restore)
    assert [p["state"] for p in again["parents"]] == ["restored"]


@pytest.mark.parametrize("touch", [
    f"UPDATE futures_markets SET status = status WHERE id = {PARENT}",
    f"UPDATE futures_markets SET settled_at = settled_at WHERE id = {CHILD[DEC]}",
    f"UPDATE futures_outcomes SET current_probability = current_probability"
    f" WHERE id = {P_OUT[OCT]}",
], ids=["parent-same-value", "leg-same-value", "outcome-price-touch"])
async def test_restore_never_overwrites_a_later_writer(db, touch):
    plan, _ = await _apply_specimen(db)
    await _touch(db, touch)
    later_m, later_o = await _markets(db), await _outcomes(db)
    audit = await _run(db, fn=rr.restore)
    assert [p["state"] for p in audit["parents"]] == ["moved"]
    done = await _run(db, fn=rr.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_parents"] == 0
    # The WHOLE parent stays as the later state left it: no partial restore.
    assert await _markets(db) == later_m and await _outcomes(db) == later_o


async def test_leg_rows_stored_on_the_parent_are_controls_through_apply_and_restore(db):
    """Production 2026-10-13 21:08Z: 113883 also holds April's ``_yes`` / ``_no``
    rows (84295247/84295248, ungraded, 2026-05-24) and the dry run refused it as
    ``unexpected_parent_outcome``. April is closed at the venue, so both rows are
    controls: the parent repairs, and neither row moves on apply or restore."""
    from app.models.models import FuturesOutcome

    april = LEG_BY_TITLE["April Meeting"]["conditionId"]
    stray = (84295247, 84295248)
    async with db() as s:
        for oid, side in zip(stray, ("yes", "no")):
            s.add(FuturesOutcome(id=oid, market_id=PARENT, external_id=f"{april}_{side}",
                                 name=side.title(), current_probability=0.5))
        await s.commit()
    before = await _outcomes(db)
    assert [before[o][1:3] for o in stray] == [(False, None), (False, None)]
    plan, out = await _apply_specimen(db)
    assert (out["markets_reopened"], out["outcomes_cleared"]) == (3, 2)
    applied = await _outcomes(db)
    assert [applied[o] for o in stray] == [before[o] for o in stray]
    for cid in OPEN:
        assert applied[P_OUT[cid]][1:3] == (None, None)
    done = await _run(db, fn=rr.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_parents"] == 1, done
    restored = await _outcomes(db)
    assert [restored[o] for o in stray] == [before[o] for o in stray]


async def test_restore_apply_needs_a_plan_hash_and_writes_nothing_without_one(db):
    """An unscoped restore apply would put back every group of every historical
    run still in ``written`` state; like the repair apply, it must name the one
    reviewed run. The unscoped dry-run audit stays allowed."""
    plan, _ = await _apply_specimen(db)
    written_m, written_o, bank = await _markets(db), await _outcomes(db), await _bank(db)
    refused = await _run(db, fn=rr.restore, apply=True)
    assert refused["terminal"] == "refused_no_plan_hash"
    assert refused["restored_parents"] == 0
    assert (await _markets(db), await _outcomes(db), await _bank(db)) == \
        (written_m, written_o, bank)
    audit = await _run(db, fn=rr.restore)
    assert audit["terminal"] == "dry_run"
    assert audit["by_plan_hash"] == {plan["plan_hash"]: {"written": 1, "restored": 0,
                                                         "moved": 0}}
    # A hash that names no run restores nothing either.
    other = await _run(db, fn=rr.restore, apply=True, plan_hash="0" * 64)
    assert other["restored_parents"] == 0
    assert (await _markets(db), await _outcomes(db)) == (written_m, written_o)


async def test_the_apply_names_the_restore_for_its_own_run(db):
    _, out = await _apply_specimen(db)
    assert f"plan_hash={out['plan_hash']}" in out["restore_command"]


async def test_restore_refuses_when_the_poll_touched_the_parent(db):
    """The poll's real writer is a later writer: once it has re-priced a leg,
    a restore would overwrite its work, so it refuses."""
    plan, _ = await _apply_specimen(db)
    await _poll()
    later_o = await _outcomes(db)
    done = await _run(db, fn=rr.restore, apply=True, plan_hash=plan["plan_hash"])
    assert done["restored_parents"] == 0
    assert await _outcomes(db) == later_o


# ---------------------------------------------------------------------------
# recurrence: the real writers, re-run over the repaired rows
# ---------------------------------------------------------------------------

_REAL_SERVICE = polymarket_api.PolymarketAPIService


async def _poll(event=None) -> dict:
    """The REAL discovery-poll writer, handed the venue's real event."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting({"errors": []})
    parsed = _REAL_SERVICE()._parse_event(copy.deepcopy(event or SPECIMEN))
    assert parsed is not None and len(parsed.markets) == len(SPECIMEN["markets"])
    await _process_event_batch(
        [parsed], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


async def test_the_real_poll_keeps_the_repaired_rows_open_and_ungraded(db):
    await _apply_specimen(db)
    stats = await _poll()
    assert stats["events_processed"] == 1
    m, o = await _markets(db), await _outcomes(db)
    assert m[PARENT][1] == "open"
    for cid in OPEN:
        assert m[CHILD[cid]][1] == "open"
        assert o[P_OUT[cid]][1:3] == (None, None)
    for cid in CLOSED:
        assert o[P_OUT[cid]][1:3] == (False, "api_settlement")
        assert m[CHILD[cid]][1] == "resolved"


async def test_control_the_real_poll_alone_never_clears_a_false_grade(db):
    """Why the rail writes grades at all: the poll, handed the open event,
    re-opens the parent but leaves October and December Lost."""
    await _poll()
    m, o = await _markets(db), await _outcomes(db)
    assert m[PARENT][1] == "open"
    for cid in OPEN:
        assert o[P_OUT[cid]][1:3] == (False, "api_settlement")


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, *a, **k):
        self.store[key] = str(value)
        return True

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, *keys):
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


async def _grade(monkeypatch, *, gate_open=False):
    """The REAL Gamma winner rail (PR #11008's gated version) against this DB."""
    import app.tasks.backfill_winners as bw
    import app.tasks.redis_state as redis_state
    import app.utils.polymarket_champion_mint as mint_mod

    rc = _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_event_by_id(self, eid):
            return copy.deepcopy(SPECIMEN) if str(eid) == "106884" else None

        async def get_market_by_condition(self, cid):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(polymarket_api, "PolymarketAPIService", _Service)
    if gate_open:
        monkeypatch.setattr(mint_mod, "venue_has_closed_the_leg", lambda closed: True)
        # #698: the negRisk arm also grades only a venue-verified payout now, so
        # "the pre-#11008 grader" needs that second gate replaced by the old
        # quote rule too (`prices[0] >= 0.90`). Forcing `closed` alone would
        # leave October and December refused by #698 and make the paired
        # "not regraded even ungated" control pass for the wrong reason.
        import json as _json

        import app.utils.polymarket_settlement_scan as scan_mod

        def _old_quote_rule(m):
            return float(_json.loads(m["outcomePrices"])[0]) >= 0.90

        monkeypatch.setattr(scan_mod, "venue_terminal_leg_result", _old_quote_rule)
    return await bw._backfill_polymarket_winners_from_api(limit=50)


async def test_the_real_grader_does_not_regrade_the_repaired_legs(db, monkeypatch):
    await _apply_specimen(db)
    await _grade(monkeypatch)
    o = await _outcomes(db)
    for cid in OPEN:
        assert o[P_OUT[cid]][1:3] == (None, None)
    for cid in CLOSED:
        assert o[P_OUT[cid]][1:3] == (False, "api_settlement")


async def test_control_a_grade_only_repair_is_regraded_by_the_ungated_grader(db, monkeypatch):
    """Why the rail re-opens the parent as well as clearing the grades. Clear the
    two grades but leave the July ``resolved`` status, and the pre-#11008 grader
    (gate forced open) selects the parent and writes Lost again. The rig reaches."""
    await _touch(db, "UPDATE futures_outcomes SET is_winner = NULL, resolution_source = NULL"
                     f" WHERE id IN ({P_OUT[OCT]}, {P_OUT[DEC]})")
    await _grade(monkeypatch, gate_open=True)
    o = await _outcomes(db)
    for cid in OPEN:
        assert o[P_OUT[cid]][1:3] == (False, "api_settlement")


async def test_control_the_repaired_parent_is_not_regraded_even_ungated(db, monkeypatch):
    await _apply_specimen(db)
    await _grade(monkeypatch, gate_open=True)
    o = await _outcomes(db)
    for cid in OPEN:
        assert o[P_OUT[cid]][1:3] == (None, None)


# ---------------------------------------------------------------------------
# reachability: the sunk-recovery selector, which never reached the parent
# ---------------------------------------------------------------------------

async def _rotate_ids(maker) -> set[int]:
    from app.tasks.polymarket import (
        SUNK_POLY_IMMINENT_DAYS,
        SUNK_POLY_STALE_HOURS,
        _SUNK_POLY_ROTATE_SQL,
    )

    async with maker() as s:
        rows = (await s.execute(_SUNK_POLY_ROTATE_SQL, {
            "stale_hours": SUNK_POLY_STALE_HOURS, "horizon_days": SUNK_POLY_IMMINENT_DAYS,
            "refused": [], "cursor": 0, "max_rows": 1000})).all()
    return {int(r.id) for r in rows}


async def test_the_repaired_parent_is_reachable_by_the_recovery_pass(db, monkeypatch):
    # Venue dates relative to the database's own clock, so this never expires.
    real_now = datetime.now(UTC)
    ev = FakeGamma.events["106884"]
    ev["endDate"] = (real_now + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in ev["markets"]:
        if m["conditionId"] in OPEN:
            m["endDate"] = (real_now + timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(rr, "_now", lambda: real_now)

    assert PARENT not in await _rotate_ids(db)  # the defect: resolved, stale
    await _apply_specimen(db)
    assert PARENT in await _rotate_ids(db)


async def test_control_a_status_only_flip_stays_unreachable(db):
    """A repair that flipped the status and kept the 2026-06-17 date would leave
    the parent below the pass's floor, unreachable as before."""
    await _touch(db, f"UPDATE futures_markets SET status = 'open' WHERE id = {PARENT}")
    assert PARENT not in await _rotate_ids(db)
