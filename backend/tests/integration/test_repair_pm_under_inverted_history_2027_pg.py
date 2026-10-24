"""#2027 / #10955: the Under-history repair against a real PostgreSQL — the
classifier's SQL, the pinned apply, drift refusal, and a restore that never
overwrites a later writer.

Runs on a disposable database on the local CI service, never production. The
tables carry the columns the rail reads and writes; the SQL under test is the
module's own.

Seeds:

* **31519211**, the specimen: Live's six quoted Under-history/Over-capture
  pairs (Under rows on the hour in the history shape, Over poll captures ~21
  minutes later), the July 12 poll capture on both legs, and an old-rail
  opening copied into the calibration price.
* **ACTIVE CONTROL**: an open O/U whose Under carries its own poll rows and
  rows the FIXED rail wrote (ids above the era bound, the Under token's
  values). Nothing of it may move.
* **COMPLEMENT**: pre-fix history rows that read as the Over price's
  complement (the falsifier). Refused.
* **LONE**: an Under leg with no Over sibling. Refused.
* **FLIPPED**: exact same-second twins on the Over leg, a Phase 0c opening at
  a false row's instant and a calibration price the #137 sign-flip beat
  complemented. Both withdrawn.
* **KEPT**: an inverted leg whose calibration price is also a genuine Under
  row's value. Refused whole.
* **POSTFIX**: an inverted leg that ALSO holds a row above the era bound
  reading as the Over price, which would mean the bound or the fixed rail is
  wrong. Refused whole.

The specimen's Under also carries a settlement-time poll row with no odds and
no book (p = 1), inside the era bound. Only its sub-second stamp separates it
from the history shape, so it must survive the apply.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.tasks.repair_pm_under_inverted_history as rp

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #2027 repair gate"
    ),
]

UTC = timezone.utc
T0 = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)
BOUNDARY = 10_000
POST_FIX_IDS = 20_000

SPECIMEN_PAIRS = [(0.745, 0.745), (0.74, 0.74), (0.47, 0.465),
                  (0.48, 0.455), (0.59, 0.59), (0.0005, 0.0005)]

SPEC, CTRL, COMP, LONE, FLIP, KEPT, POSTFIX = (
    31519211, 40000001, 40000002, 40000003, 40000004, 40000005, 40000006)
SPEC_OVER, SPEC_UNDER = 315192110, 315192111
CTRL_OVER, CTRL_UNDER = 400000010, 400000011
COMP_OVER, COMP_UNDER = 400000020, 400000021
LONE_UNDER = 400000031
FLIP_OVER, FLIP_UNDER = 400000040, 400000041
KEPT_OVER, KEPT_UNDER = 400000050, 400000051
POSTFIX_OVER, POSTFIX_UNDER = 400000060, 400000061
SETTLED_POLL_AT = datetime(2026, 7, 12, 2, 18, 48, 250001, tzinfo=UTC)

MARKETS = {
    SPEC: ("0xvassell", "resolved"), CTRL: ("0xctrl", "open"),
    COMP: ("0xcomp", "resolved"), LONE: ("0xlone", "resolved"),
    FLIP: ("0xflip", "resolved"), KEPT: ("0xkept", "resolved"),
    POSTFIX: ("0xpostfix", "resolved"),
}
LEGS = [
    (SPEC_OVER, SPEC, "0xvassell", "Over"), (SPEC_UNDER, SPEC, "0xvassell_no", "Under"),
    (CTRL_OVER, CTRL, "0xctrl", "Over"), (CTRL_UNDER, CTRL, "0xctrl_no", "Under"),
    (COMP_OVER, COMP, "0xcomp", "Over"), (COMP_UNDER, COMP, "0xcomp_no", "Under"),
    (LONE_UNDER, LONE, "0xlone_no", "Under"),
    (FLIP_OVER, FLIP, "0xflip", "Over"), (FLIP_UNDER, FLIP, "0xflip_no", "Under"),
    (KEPT_OVER, KEPT, "0xkept", "Over"), (KEPT_UNDER, KEPT, "0xkept_no", "Under"),
    (POSTFIX_OVER, POSTFIX, "0xpostfix", "Over"),
    (POSTFIX_UNDER, POSTFIX, "0xpostfix_no", "Under"),
]


def _snapshots():
    """(id or None, outcome_id, probability, captured_at, kind) — kind is
    'history' (the old rail's shape) or 'poll'."""
    rows = []
    hid = 100
    for i, (p, q) in enumerate(SPECIMEN_PAIRS):
        at = T0 + timedelta(hours=i)
        rows.append((hid, SPEC_UNDER, p, at, "history"))
        hid += 1
        rows.append((None, SPEC_OVER, q, at + timedelta(minutes=21, microseconds=102953), "poll"))
    july = datetime(2026, 7, 12, 2, 18, 47, 102953, tzinfo=UTC)
    rows += [(None, SPEC_OVER, 0.1667, july, "poll"), (None, SPEC_UNDER, 0.8333, july, "poll"),
             (199, SPEC_UNDER, 1.0, SETTLED_POLL_AT, "bare_poll")]

    # ACTIVE CONTROL: genuine Under polls + the FIXED rail's rows above the bound.
    for i, (_, q) in enumerate(SPECIMEN_PAIRS):
        at = T0 + timedelta(days=30, hours=i)
        rows.append((None, CTRL_OVER, q, at + timedelta(minutes=21, microseconds=7), "poll"))
        rows.append((None, CTRL_UNDER, round(1 - q, 4),
                     at + timedelta(minutes=22, microseconds=11), "poll"))
        rows.append((POST_FIX_IDS + i, CTRL_UNDER, round(1 - q, 4), at, "history"))

    # COMPLEMENT: pre-fix shape, but the values are the Under token's.
    for i, (_, q) in enumerate(SPECIMEN_PAIRS):
        at = T0 + timedelta(days=2, hours=i)
        rows.append((300 + i, COMP_UNDER, round(1 - q, 4), at, "history"))
        rows.append((None, COMP_OVER, q, at + timedelta(minutes=21, microseconds=3), "poll"))

    # LONE: no Over sibling at all.
    for i, (p, _) in enumerate(SPECIMEN_PAIRS):
        rows.append((400 + i, LONE_UNDER, p, T0 + timedelta(days=3, hours=i), "history"))

    # FLIPPED: the same pass backfilled both legs from the Over token.
    for i, p in enumerate((0.81, 0.77, 0.66)):
        at = T0 + timedelta(days=4, hours=i)
        rows.append((500 + i, FLIP_UNDER, p, at, "history"))
        rows.append((600 + i, FLIP_OVER, p, at, "history"))

    # KEPT: inverted, but its calibration price is also a genuine Under poll.
    for i, (p, q) in enumerate(SPECIMEN_PAIRS):
        at = T0 + timedelta(days=5, hours=i)
        rows.append((700 + i, KEPT_UNDER, p, at, "history"))
        rows.append((None, KEPT_OVER, q, at + timedelta(minutes=21, microseconds=9), "poll"))
    rows.append((None, KEPT_UNDER, 0.59, T0 + timedelta(days=6, microseconds=1), "poll"))

    # POSTFIX: inverted pre-fix rows, and one fixed-rail row that reads as Over.
    for i, (p, q) in enumerate(SPECIMEN_PAIRS):
        at = T0 + timedelta(days=7, hours=i)
        rows.append((800 + i, POSTFIX_UNDER, p, at, "history"))
        rows.append((None, POSTFIX_OVER, q, at + timedelta(minutes=21, microseconds=9), "poll"))
    rows.append((POST_FIX_IDS + 100, POSTFIX_UNDER, 0.745, T0 + timedelta(days=7, minutes=5),
                 "history"))
    return rows


#: outcome -> (opening, opening_source, opening_captured_at, calibration price)
FIELDS = {
    SPEC_UNDER: (0.745, "clob_history", None, 0.745),
    CTRL_UNDER: (0.535, "polymarket_poll",
                 T0 + timedelta(days=30, minutes=22, microseconds=11), None),
    COMP_UNDER: (0.255, "clob_history", None, 0.255),
    LONE_UNDER: (0.745, "clob_history", None, None),
    # Phase 0c promoted the 0.81 row at its instant; #137 complemented both.
    FLIP_UNDER: (0.19, "first_snapshot", T0 + timedelta(days=4), 0.34),
    KEPT_UNDER: (None, None, None, 0.59),
}


@pytest.fixture(scope="session")
def isolated_database():
    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "under_history_2027_" + uuid4().hex
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
    monkeypatch.setattr(rp, "PRE_FIX_MAX_SNAPSHOT_ID", BOUNDARY)
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for t in (rp.BAK_ROWS, rp.BAK_FIELDS, "futures_odds_snapshots",
                  "futures_outcomes", "futures_markets"):
            await s.execute(text(f"DROP TABLE IF EXISTS {t}"))
        await s.execute(text(
            "CREATE TABLE futures_markets (id BIGINT PRIMARY KEY, source TEXT NOT NULL,"
            " external_id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,"
            " mutually_exclusive BOOLEAN NOT NULL, status TEXT NOT NULL,"
            " resolution_date TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL,"
            " updated_at TIMESTAMPTZ NOT NULL)"))
        await s.execute(text(
            "CREATE TABLE futures_outcomes (id BIGINT PRIMARY KEY, market_id BIGINT NOT NULL,"
            " external_id TEXT NOT NULL, name TEXT NOT NULL,"
            " opening_probability NUMERIC(7,6), opening_american_odds INTEGER,"
            " opening_captured_at TIMESTAMPTZ, opening_source VARCHAR(30),"
            " calibration_probability NUMERIC(7,6), is_winner BOOLEAN,"
            " resolution_source TEXT, last_updated TIMESTAMPTZ NOT NULL)"))
        await s.execute(text(
            "CREATE TABLE futures_odds_snapshots (id BIGSERIAL PRIMARY KEY,"
            " outcome_id BIGINT NOT NULL REFERENCES futures_outcomes(id),"
            " bookmaker VARCHAR(50) NOT NULL, probability NUMERIC(7,6) NOT NULL,"
            " american_odds INTEGER, yes_bid NUMERIC(5,4), yes_ask NUMERIC(5,4),"
            " last_price NUMERIC(5,4), captured_at TIMESTAMPTZ NOT NULL,"
            " reading_count INTEGER NOT NULL, valid_until TIMESTAMPTZ)"))
        await s.execute(text(
            "CREATE INDEX ON futures_odds_snapshots (outcome_id, captured_at)"))
        await s.execute(text("ALTER SEQUENCE futures_odds_snapshots_id_seq RESTART WITH 50000"))
        for mid, (cid, status) in MARKETS.items():
            await s.execute(text(
                "INSERT INTO futures_markets (id, source, external_id, name, category,"
                " mutually_exclusive, status, resolution_date, created_at, updated_at)"
                " VALUES (:i, 'polymarket', :x, :n, 'sports', false, :st,"
                " '2026-06-04T00:30:00Z', '2026-06-01T00:00:00Z', '2026-06-01T00:00:00Z')"),
                dict(i=mid, x=f"{cid}-market", n=f"market {mid}", st=status))
        for oid, mid, ext, name in LEGS:
            op, src, at, cp = FIELDS.get(oid, (None, None, None, None))
            await s.execute(text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name,"
                " opening_probability, opening_source, opening_captured_at,"
                " calibration_probability, is_winner, resolution_source, last_updated)"
                " VALUES (:i, :m, :x, :n, :op, :src, :at, :cp, :won, 'clob_authoritative',"
                " '2026-07-12T00:00:00Z')"),
                dict(i=oid, m=mid, x=ext, n=name, op=op, src=src, at=at, cp=cp,
                     won=(name == "Under")))
        for sid, oid, p, at, kind in _snapshots():
            history = kind in ("history", "bare_poll")
            await s.execute(text(
                "INSERT INTO futures_odds_snapshots (id, outcome_id, bookmaker, probability,"
                " american_odds, yes_bid, yes_ask, last_price, captured_at, reading_count)"
                " VALUES (COALESCE(:id, nextval('futures_odds_snapshots_id_seq')), :o,"
                " 'polymarket', :p, :odds, :bid, :ask, :last, :at, 1)"),
                dict(id=sid, o=oid, p=p, at=at, last=round(p, 4),
                     odds=None if history else (-150 if p > 0.5 else 150),
                     bid=None if history else max(p - 0.01, 0.0),
                     ask=None if history else min(p + 0.01, 1.0)))
        await s.commit()
    yield maker
    await engine.dispose()


async def _state(maker, oids=None):
    async with maker() as s:
        rows = (await s.execute(text(
            "SELECT id, outcome_id, probability, captured_at FROM futures_odds_snapshots"
            " ORDER BY id"))).all()
        fields = (await s.execute(text(
            "SELECT id, opening_probability, opening_american_odds, opening_captured_at,"
            " opening_source, calibration_probability, is_winner FROM futures_outcomes"
            " ORDER BY id"))).all()
    pick = (lambda r: r[1] in oids) if oids else (lambda r: True)
    return ([tuple(r) for r in rows if pick(r)],
            [tuple(r) for r in fields if (r[0] in oids if oids else True)])


async def _run(maker, **kw):
    async with maker() as s:
        return await rp.repair(s, **kw)


async def test_the_dry_run_classifies_every_seed_and_writes_nothing(db):
    before = await _state(db)
    out = await _run(db, limit=50)
    assert out["terminal"] == "dry_run" and out["exhausted"] is True
    assert out["verdicts"] == {"INVERTED": 2, "COMPLEMENT": 1, "AMBIGUOUS": 3}
    assert out["ambiguous_reasons"] == {"no_over_sibling": 1, "cp_matches_a_kept_row": 1,
                                        "post_fix_row_reads_as_over": 1}
    assert sorted(out["planned_outcome_ids"]) == [SPEC_UNDER, FLIP_UNDER]
    assert out["rows_planned"] == 6 + 3
    assert out["openings_planned"] == 2 and out["cp_planned"] == 2
    # The control's only history rows are the fixed rail's: never a candidate.
    assert out["legs_with_history_rows"] == 6
    spec = next(e for e in out["examples"]["INVERTED"] if e["outcome_id"] == SPEC_UNDER)
    assert spec["testimony"] == {"kind": "near", "equal": 6, "complement": 0}
    assert spec["withdraw_opening"] == "clob_history_raw"
    assert spec["withdraw_cp"] == "copy_of_withdrawn_opening"
    flip = next(e for e in out["examples"]["INVERTED"] if e["outcome_id"] == FLIP_UNDER)
    assert flip["testimony"]["kind"] == "exact"
    assert flip["withdraw_opening"] == "first_snapshot_complemented"
    assert flip["withdraw_cp"] == "false_row_complemented"
    assert await _state(db) == before


async def test_losing_the_era_bound_still_refuses_the_control(db, monkeypatch):
    monkeypatch.setattr(rp, "PRE_FIX_MAX_SNAPSHOT_ID", None)
    out = await _run(db, limit=50)
    assert CTRL_UNDER not in out["planned_outcome_ids"]
    assert any(e["outcome_id"] == CTRL_UNDER for e in out["examples"]["COMPLEMENT"])
    refused = await _run(db, limit=50, apply=True, plan_hash=out["plan_hash"])
    assert refused["terminal"] == "refused_boundary_unpinned"


async def test_the_pinned_apply_withdraws_exactly_the_plan(db):
    untouched = [o for o, *_ in LEGS if o not in (SPEC_UNDER, FLIP_UNDER)]
    before_other = await _state(db, set(untouched))
    plan = await _run(db, limit=50)
    out = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    assert out["terminal"] == "applied"
    assert out["legs_written"] == 2 and out["drift_refused"] == 0

    rows, fields = await _state(db, {SPEC_UNDER, FLIP_UNDER})
    # Only the specimen's own July polls survive (the bare settlement poll by
    # its sub-second stamp alone); Phase 0c / the fixed rail re-derive from
    # them, never this rail.
    assert sorted((r[1], float(r[2])) for r in rows) == [(SPEC_UNDER, 0.8333),
                                                     (SPEC_UNDER, 1.0)]
    for oid, op, odds, at, src, cp, won in fields:
        assert (op, odds, at, src, cp) == (None, None, None, None, None)
        assert won is True  # never read, never written
    assert await _state(db, set(untouched)) == before_other

    async with db() as s:
        backed = (await s.execute(text(
            f"SELECT count(*), count(DISTINCT plan_hash) FROM {rp.BAK_ROWS}"))).one()
    assert tuple(backed) == (9, 1)


async def test_a_stale_plan_is_refused_whole(db):
    before = await _state(db)
    out = await _run(db, limit=50, apply=True, plan_hash="0" * 32)
    assert out["terminal"] == "refused_plan_drift" and out["legs_written"] == 0
    assert await _state(db) == before


async def test_a_row_that_moved_after_review_refuses_its_leg_only(db):
    plan = await _run(db, limit=50)
    async with db() as s:
        await s.execute(text(
            "UPDATE futures_odds_snapshots SET probability = 0.7401 WHERE id = 101"))
        await s.commit()
    before_spec = await _state(db, {SPEC_UNDER})
    # The page is re-planned at apply, so the moved row changes the address.
    stale = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    assert stale["terminal"] == "refused_plan_drift"
    # Re-review, then move a FIELD between the re-planned read and the write.
    plan2 = await _run(db, limit=50)
    real = rp._apply_leg

    async def move_then_apply(session, p, digest):
        if p["outcome_id"] == SPEC_UNDER:
            async with db() as other:
                await other.execute(text(
                    "UPDATE futures_outcomes SET calibration_probability = 0.5"
                    " WHERE id = :o"), {"o": SPEC_UNDER})
                await other.commit()
        return await real(session, p, digest)

    rp._apply_leg = move_then_apply
    try:
        out = await _run(db, limit=50, apply=True, plan_hash=plan2["plan_hash"])
    finally:
        rp._apply_leg = real
    assert out["legs_written"] == 1 and out["drift_refused"] == 1
    rows, fields = await _state(db, {SPEC_UNDER})
    assert rows == before_spec[0]
    assert float(fields[0][5]) == 0.5 and float(fields[0][1]) == 0.745


async def test_a_row_that_moves_inside_the_apply_refuses_its_leg_only(db):
    plan = await _run(db, limit=50)
    before_spec = await _state(db, {SPEC_UNDER})
    real = rp._apply_leg

    async def move_then_apply(session, p, digest):
        if p["outcome_id"] == SPEC_UNDER:
            async with db() as other:
                await other.execute(text(
                    "UPDATE futures_odds_snapshots SET probability = 0.7401 WHERE id = 101"))
                await other.commit()
        return await real(session, p, digest)

    rp._apply_leg = move_then_apply
    try:
        out = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    finally:
        rp._apply_leg = real
    assert out["legs_written"] == 1 and out["drift_refused"] == 1
    rows, fields = await _state(db, {SPEC_UNDER})
    assert len(rows) == len(before_spec[0]) and float(fields[0][1]) == 0.745
    async with db() as s:
        backed = (await s.execute(text(
            f"SELECT count(*) FROM {rp.BAK_ROWS} WHERE outcome_id = :o"),
            {"o": SPEC_UNDER})).scalar_one()
    assert backed == 0


async def test_only_ids_narrows_the_plan_and_the_apply(db):
    plan = await _run(db, limit=50, only_ids=str(SPEC_UNDER))
    assert plan["planned_outcome_ids"] == [SPEC_UNDER] and plan["withheld_by_only_ids"] == 1
    out = await _run(db, limit=50, only_ids=str(SPEC_UNDER), apply=True,
                     plan_hash=plan["plan_hash"])
    assert out["legs_written"] == 1
    rows, _ = await _state(db, {FLIP_UNDER})
    assert len(rows) == 3


async def test_the_undo_round_trips(db):
    before = await _state(db)
    plan = await _run(db, limit=50)
    await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    async with db() as s:
        census = await rp.restore(s)
    assert census["terminal"] == "dry_run"
    assert census["rows_backed_up"] == 9 and census["rows_restorable"] == 9
    assert census["openings_restorable"] == 2 and census["cp_restorable"] == 2
    async with db() as s:
        out = await rp.restore(s, apply=True)
    assert (out["restored_rows"], out["restored_openings"], out["restored_cp"]) == (9, 2, 2)
    assert await _state(db) == before


async def test_the_undo_never_overwrites_a_later_writer(db):
    plan = await _run(db, limit=50)
    await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    async with db() as s:
        # Phase 0c re-derived the specimen's opening from its surviving poll row,
        # and the FIXED rail refiled the Under token at the first false instant.
        await s.execute(text(
            "UPDATE futures_outcomes SET opening_probability = 0.8333,"
            " opening_source = 'first_snapshot',"
            " opening_captured_at = '2026-07-12T02:18:47.102953Z' WHERE id = :o"),
            {"o": SPEC_UNDER})
        await s.execute(text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability,"
            " american_odds, yes_bid, yes_ask, last_price, captured_at, reading_count)"
            " VALUES (:o, 'polymarket', 0.255, NULL, NULL, NULL, 0.255, :at, 1)"),
            {"o": SPEC_UNDER, "at": T0})
        await s.commit()
    async with db() as s:
        out = await rp.restore(s, apply=True)
    assert out["rows_collide"] == 1 and out["restored_rows"] == 8
    assert out["restored_openings"] == 1 and out["restored_cp"] == 2
    rows, fields = await _state(db, {SPEC_UNDER})
    assert float(fields[0][1]) == 0.8333 and fields[0][4] == "first_snapshot"
    at_t0 = [r for r in rows if r[3] == T0]
    assert len(at_t0) == 1 and float(at_t0[0][2]) == 0.255


# ---------------------------------------------------------------------------
# D51 backup pairing: an older bank kept by ON CONFLICT DO NOTHING must be
# exactly this run's locked prior, or the leg is refused before any write.
# ---------------------------------------------------------------------------

async def _bank_snapshot(maker):
    async with maker() as s:
        rows = (await s.execute(text(
            f"SELECT {rp._SNAP_COLS}, plan_hash FROM {rp.BAK_ROWS} ORDER BY id"))).all()
        fields = (await s.execute(text(
            f"SELECT outcome_id, withdrew_opening, prior_opening_probability,"
            f" prior_opening_american_odds, prior_opening_captured_at, prior_opening_source,"
            f" withdrew_cp, prior_calibration_probability, plan_hash"
            f" FROM {rp.BAK_FIELDS} ORDER BY outcome_id"))).all()
    return [tuple(r) for r in rows], [tuple(r) for r in fields]


async def _create_banks(maker):
    async with maker() as s:
        await s.execute(text(rp._BAK_ROWS_CREATE))
        await s.execute(text(rp._BAK_FIELDS_CREATE))
        await s.commit()


async def _earlier_bank(maker, *, row_set=None, field_set=None, wo=True, wc=True):
    """Leave the bank an earlier run would have left: move the live row/fields
    to that run's state, copy with the module's own SQL, and move them back."""
    await _create_banks(maker)
    snap = await _state(maker, {SPEC_UNDER})
    async with maker() as s:
        if row_set is not None:
            await s.execute(text(f"UPDATE futures_odds_snapshots SET {row_set} WHERE id = 100"))
            await s.execute(text(rp._BAK_ROWS_COPY),
                            {"ids": [100], "oid": SPEC_UNDER, "plan_hash": "earlier"})
        if field_set is not None:
            await s.execute(text(f"UPDATE futures_outcomes SET {field_set} WHERE id = :o"),
                            {"o": SPEC_UNDER})
            await s.execute(text(rp._BAK_FIELDS_COPY),
                            {"oid": SPEC_UNDER, "wo": wo, "wc": wc, "plan_hash": "earlier"})
        # Put the live leg back exactly as seeded; only the bank keeps the move.
        await s.execute(text(
            "UPDATE futures_odds_snapshots SET probability = 0.745, last_price = 0.745,"
            " captured_at = :t0 WHERE id = 100"), {"t0": T0})
        op, src, at, cp = FIELDS[SPEC_UNDER]
        await s.execute(text(
            "UPDATE futures_outcomes SET opening_probability = :op, opening_source = :src,"
            " opening_captured_at = :at, opening_american_odds = NULL,"
            " calibration_probability = :cp WHERE id = :o"),
            {"op": op, "src": src, "at": at, "cp": cp, "o": SPEC_UNDER})
        await s.commit()
    assert await _state(maker, {SPEC_UNDER}) == snap


async def _assert_spec_refused_flip_written(maker, out, reason, spec_before):
    assert out["terminal"] == "applied"
    assert out["legs_written"] == 1 and out["backup_refused"] == 1
    assert out["drift_refused"] == 0
    assert out["refused_legs"] == [{"outcome_id": SPEC_UNDER, "reason": reason}]
    # Zero snapshot deletion and zero field withdrawal on the refused leg.
    assert await _state(maker, {SPEC_UNDER}) == spec_before
    # The sibling leg is repaired whole.
    rows, fields = await _state(maker, {FLIP_UNDER})
    assert rows == [] and fields[0][1:6] == (None, None, None, None, None)


@pytest.mark.parametrize("stale", [
    "probability = 0.5, last_price = 0.5",
    "captured_at = captured_at - interval '1 day'",
], ids=["different_probability", "different_captured_at"])
async def test_a_stale_row_bank_at_the_same_id_refuses_the_leg(db, stale):
    # A bank row from an earlier run holds id 100 (the specimen's first false
    # row) with a value or instant this run is not about to delete.
    await _earlier_bank(db, row_set=stale)
    spec_before = await _state(db, {SPEC_UNDER})
    bank_before = await _bank_snapshot(db)
    plan = await _run(db, limit=50)
    out = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    await _assert_spec_refused_flip_written(db, out, rp.BACKUP_ROWS_MISMATCH, spec_before)
    rows, fields = await _bank_snapshot(db)
    # The refused leg's transaction left no copy of its own; the stale row stands.
    assert [r for r in rows if r[1] == SPEC_UNDER] == [
        r for r in bank_before[0] if r[1] == SPEC_UNDER]
    assert all(f[0] != SPEC_UNDER for f in fields)


@pytest.mark.parametrize("stale", [
    ("opening_probability = 0.5", True, True),
    ("opening_source = 'first_snapshot'", True, True),
    ("calibration_probability = 0.5", True, True),
    ("last_updated = last_updated", True, False),
    ("last_updated = last_updated", False, True),
], ids=["opening_value", "opening_source", "calibration", "cp_flag", "opening_flag"])
async def test_a_stale_field_bank_refuses_the_leg(db, stale):
    field_set, wo, wc = stale
    await _earlier_bank(db, field_set=field_set, wo=wo, wc=wc)
    spec_before = await _state(db, {SPEC_UNDER})
    bank_before = await _bank_snapshot(db)
    plan = await _run(db, limit=50)
    out = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    await _assert_spec_refused_flip_written(db, out, rp.BACKUP_FIELDS_MISMATCH, spec_before)
    rows, fields = await _bank_snapshot(db)
    # The leg's row copy rolled back with it; the stale field bank stands.
    assert all(r[1] != SPEC_UNDER for r in rows)
    assert [f for f in fields if f[0] == SPEC_UNDER] == [
        f for f in bank_before[1] if f[0] == SPEC_UNDER]


async def test_the_exact_bank_strawman_passes_the_pair_check(db):
    """Control for the two falsifiers: a pre-existing bank that IS this run's
    prior (the same seed values) is accepted, so the refusals above are the
    mismatch and not the mere presence of an older bank."""
    await _earlier_bank(db, row_set="probability = probability",
                        field_set="last_updated = last_updated")
    plan = await _run(db, limit=50)
    out = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    assert out["legs_written"] == 2 and out["backup_refused"] == 0
    assert out["refused_legs"] == []


async def test_an_exact_bank_retry_after_restore_applies_and_round_trips(db):
    before = await _state(db)
    plan = await _run(db, limit=50)
    first = await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    assert first["legs_written"] == 2
    bank_after_first = await _bank_snapshot(db)
    async with db() as s:
        await rp.restore(s, apply=True)
    assert await _state(db) == before
    # Same page, same state: the same address, and every kept bank row is exact.
    replan = await _run(db, limit=50)
    assert replan["plan_hash"] == plan["plan_hash"]
    again = await _run(db, limit=50, apply=True, plan_hash=replan["plan_hash"])
    assert again["legs_written"] == 2 and again["backup_refused"] == 0
    assert again["refused_legs"] == []
    assert await _bank_snapshot(db) == bank_after_first
    async with db() as s:
        out = await rp.restore(s, apply=True)
    assert (out["restored_rows"], out["restored_openings"], out["restored_cp"]) == (9, 2, 2)
    assert await _state(db) == before


async def test_a_retry_after_the_state_moved_since_restore_is_refused(db):
    """The audit's scenario end to end: apply, restore, a later writer moves the
    restored opening, re-review, retry. The bank still holds the FIRST prior, so
    the retry would withdraw a value nobody backed up. Refused whole."""
    plan = await _run(db, limit=50)
    await _run(db, limit=50, apply=True, plan_hash=plan["plan_hash"])
    async with db() as s:
        await rp.restore(s, apply=True)
        await s.execute(text(
            "UPDATE futures_outcomes SET calibration_probability = 0.74 WHERE id = :o"),
            {"o": SPEC_UNDER})
        await s.commit()
    spec_before = await _state(db, {SPEC_UNDER})
    replan = await _run(db, limit=50)
    assert SPEC_UNDER in replan["planned_outcome_ids"]
    out = await _run(db, limit=50, apply=True, plan_hash=replan["plan_hash"])
    assert out["backup_refused"] == 1
    assert out["refused_legs"] == [{"outcome_id": SPEC_UNDER,
                                    "reason": rp.BACKUP_FIELDS_MISMATCH}]
    assert await _state(db, {SPEC_UNDER}) == spec_before


# ---------------------------------------------------------------------------
# #11158 — the complete 16-point Vassell specimen through the real _ROWS_SQL
# ---------------------------------------------------------------------------
#
# Values and times are RETAINED SERVED-DERIVED (tests/fixtures/vassell_under_11158,
# history-all.json sha256 312906e7…f4a5); every id is SYNTHETIC. The seed above
# keeps Live's six quoted pairs as component coverage. This adds the sixteen
# points, with the two contrary near readings the six omit, and the SYNTHETIC
# genuine-Under residual, each on its own market so the earned seed and its
# assertions are untouched.

import json as _json
from pathlib import Path as _Path

_VASSELL = _json.loads((_Path(__file__).resolve().parents[1] / "fixtures"
                        / "vassell_under_11158" / "served-points.json").read_text())
V16, RESID = 40000007, 40000008
V16_OVER, V16_UNDER = 400000070, 400000071
RES_OVER, RES_UNDER = 400000080, 400000081
#: In-era SYNTHETIC ids (below BOUNDARY), one block.
V16_IDS = range(9000, 9016)
RES_IDS = range(9100, 9104)
_RES_T0 = datetime(2026, 6, 3, 1, 0, 7, tzinfo=UTC)
_RES_PAIRS = [(0.70, 0.70), (0.75, 0.76), (0.80, 0.79), (0.40, 0.60)]


async def _seed_sixteen_and_residual(maker):
    under = [(datetime.fromisoformat(p["captured_at"]), p["probability"])
             for p in _VASSELL["under_history_shape_points"]]
    over = [(datetime.fromisoformat(p["captured_at"]), p["probability"])
            for p in _VASSELL["over_poll_points_within_60_min"]]
    snaps = [(i, V16_UNDER, p, at, True) for i, (at, p) in zip(V16_IDS, under)]
    snaps += [(None, V16_OVER, q, at, False) for at, q in over]
    for i, (u, o) in zip(RES_IDS, _RES_PAIRS):
        at = _RES_T0 + timedelta(hours=i - RES_IDS[0])
        snaps.append((i, RES_UNDER, u, at, True))
        snaps.append((None, RES_OVER, o, at + timedelta(minutes=20, microseconds=123), False))
    async with maker() as s:
        for mid, cid in ((V16, "0xvassell16"), (RESID, "0xresidual")):
            await s.execute(text(
                "INSERT INTO futures_markets (id, source, external_id, name, category,"
                " mutually_exclusive, status, resolution_date, created_at, updated_at)"
                " VALUES (:i, 'polymarket', :x, :n, 'sports', false, 'resolved',"
                " '2026-06-04T00:30:00Z', '2026-06-01T00:00:00Z', '2026-06-01T00:00:00Z')"),
                dict(i=mid, x=f"{cid}-market", n=f"market {mid}"))
        for oid, mid, ext, name in ((V16_OVER, V16, "0xvassell16", "Over"),
                                    (V16_UNDER, V16, "0xvassell16_no", "Under"),
                                    (RES_OVER, RESID, "0xresidual", "Over"),
                                    (RES_UNDER, RESID, "0xresidual_no", "Under")):
            await s.execute(text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name,"
                " is_winner, resolution_source, last_updated)"
                " VALUES (:i, :m, :x, :n, :won, 'clob_authoritative', '2026-07-12T00:00:00Z')"),
                dict(i=oid, m=mid, x=ext, n=name, won=(name == "Under")))
        for sid, oid, p, at, history in snaps:
            await s.execute(text(
                "INSERT INTO futures_odds_snapshots (id, outcome_id, bookmaker, probability,"
                " american_odds, yes_bid, yes_ask, last_price, captured_at, reading_count)"
                " VALUES (COALESCE(:id, nextval('futures_odds_snapshots_id_seq')), :o,"
                " 'polymarket', :p, :odds, :bid, :ask, :last, :at, 1)"),
                dict(id=sid, o=oid, p=p, at=at, last=round(p, 4),
                     odds=None if history else (-150 if p > 0.5 else 150),
                     bid=None if history else max(p - 0.01, 0.0),
                     ask=None if history else min(p + 0.01, 1.0)))
        await s.commit()


async def test_the_sixteen_point_specimen_and_the_genuine_residual_plan_nothing(db):
    earned = await _run(db, limit=50)
    await _seed_sixteen_and_residual(db)
    before = await _state(db, {V16_UNDER, RES_UNDER})
    out = await _run(db, limit=50)
    assert out["terminal"] == "dry_run"
    for key in ("planned_outcome_ids", "rows_planned", "openings_planned",
                "cp_planned", "plan_hash"):
        assert out[key] == earned[key], key
    refused = {e["outcome_id"]: e for e in out["examples"]["AMBIGUOUS"]}
    v16, res = refused[V16_UNDER], refused[RES_UNDER]
    # The real statement pairs the sixteen exactly as served: twelve read as
    # the Over price, two (22:00:08Z, 04:00:05Z) as its complement.
    assert v16["reason"] == "mixed_testimony" and v16["rows"] == 16
    assert v16["testimony"] == {"kind": "near", "equal": 12, "complement": 2}
    assert res["reason"] == "mixed_testimony" and res["rows"] == 4
    assert res["testimony"] == {"kind": "near", "equal": 3, "complement": 1}
    assert V16_UNDER not in out["planned_outcome_ids"]
    assert RES_UNDER not in out["planned_outcome_ids"]
    assert await _state(db, {V16_UNDER, RES_UNDER}) == before
