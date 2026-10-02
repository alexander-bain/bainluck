"""#10182 — the reopen repair's apply, drift and undo, against a real PostgreSQL.

The unit file drives the planner with plain values. What the repair DOES is SQL,
and only a server can say whether it is right:

* the parent's ``resolution_gate`` is removed with ``jsonb -`` and every sibling
  metadata key survives, and ``--restore`` puts the exact gate back;
* the bank is written and committed BEFORE any board moves;
* each board sits in its own SAVEPOINT, so a compare-and-swap that misses on one
  board (a concurrent writer between bank and write) rolls back that board alone,
  is counted as ``drift``, and leaves every other board written;
* a derived ``all_losers`` stamp on a leg the venue still trades is cleared, and
  restored by the undo; venue-backed leg verdicts are not touched in either
  direction.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI:

    createdb bl_10182
    SEARCH_TEST_DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost:5432/bl_10182" \\
      python3 -m pytest tests/integration/test_repair_polymarket_false_parent_settlements_10182_pg.py -v -rs
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #10182 "
            "reopen repair apply/drift/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_10182_pg", _SCRIPTS / "repair_polymarket_false_parent_settlements_10182.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec: the script's @dataclass resolves its own module.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


r = _load()

_SCHEMA = "reopen_gate_10182"

WS, WS_EVENT = r.SPECIMEN  # partial field: stored legs all closed-No, all_losers
KF, KF_EVENT = 63049616, "1098408"  # partial field: api_settlement losers
SK, SK_EVENT = 62275323, "1078048"  # a derived stamp sits on a leg still trading
LP, LP_EVENT = 63045536, "1098315"  # venue now closed: no witness, untouched
DP, DP_EVENT = 63049660, "1098369"  # identity drift: a leg not on the venue event
SELECTED = [WS, KF, SK, LP, DP]

GATE = {"at": "2026-10-02T05:34:01.280186+00:00", "task": r.SYNC_TASK, "proof_kind": "winner"}


def _oid(market_id: int, n: int) -> int:
    """A leg id inside int4, unique per (board, n)."""
    return (market_id % 100000) * 100 + n


def _cid(tag: str, n: int) -> str:
    return "0x" + tag + f"{n:060x}"


def _venue(event_id, tag, closed_legs, open_legs, *, closed=False, winners=()):
    markets = [
        {
            "conditionId": _cid(tag, n),
            "closed": True,
            "outcomePrices": '["1", "0"]' if n in winners else '["0", "1"]',
        }
        for n in range(closed_legs)
    ] + [
        {"conditionId": _cid(tag, n), "closed": False, "outcomePrices": '["0.03", "0.97"]'}
        for n in range(closed_legs, closed_legs + open_legs)
    ]
    return {"id": event_id, "closed": closed, "markets": markets}


VENUE = {
    WS_EVENT: _venue(WS_EVENT, "a1", 20, 17),
    KF_EVENT: _venue(KF_EVENT, "b2", 2, 111),
    SK_EVENT: _venue(SK_EVENT, "c3", 3, 12, winners=(0, 1, 2)),
    LP_EVENT: _venue(LP_EVENT, "d4", 121, 0, closed=True),
    DP_EVENT: _venue(DP_EVENT, "e5", 11, 110),
}


async def fetch(event_id):
    return VENUE.get(event_id)


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
    await admin.dispose()

    eng = create_async_engine(DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}})
    async with eng.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE futures_markets (
                id integer PRIMARY KEY,
                source varchar(50) NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                category varchar(50) NOT NULL,
                mutually_exclusive boolean NOT NULL,
                status varchar(20) NOT NULL,
                group_id varchar(200),
                settled_at timestamptz,
                market_metadata jsonb
            )
        """))
        await conn.execute(text("""
            CREATE TABLE futures_outcomes (
                id integer PRIMARY KEY,
                market_id integer NOT NULL REFERENCES futures_markets(id),
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                current_probability numeric(10, 6),
                is_winner boolean,
                resolution_source varchar(40),
                last_updated timestamptz
            )
        """))
        for mid, ev, name in (
            (WS, WS_EVENT, "MLB Playoffs: World Series Exact Matchup"),
            (KF, KF_EVENT, "Korn Ferry Tour: Compliance Solutions Championship Winner"),
            (SK, SK_EVENT, "What will SK hynix (SKHY) hit in October 2026?"),
            (LP, LP_EVENT, "LPGA: LOTTE Championship First Round Leader"),
            (DP, DP_EVENT, "DP World Tour: Alfred Dunhill Links Third Round Leader"),
        ):
            meta = {
                "polymarket_event_id": ev,
                "shape": {"evidence": ["partial_field"]},
                r.GATE_KEY: GATE,
            }
            await conn.execute(
                text(
                    "INSERT INTO futures_markets (id, source, external_id, name, category, "
                    "mutually_exclusive, status, group_id, settled_at, market_metadata) "
                    "VALUES (:id, 'polymarket', :ev, :name, 'sports', true, 'resolved', "
                    ":gid, '2026-10-02T05:34:01.38278+00:00', CAST(:meta AS jsonb))"
                ),
                {"id": mid, "ev": ev, "name": name, "gid": f"polymarket:{ev}",
                 "meta": json.dumps(meta)},
            )
        legs = (
            # WS: 16 of the 20 closed-No legs, re-stamped all_losers by Pass 4.
            [(_oid(WS, n), WS, _cid("a1", n), False, "all_losers") for n in range(16)]
            # KF: both closed legs, venue losers.
            + [(_oid(KF, n), KF, _cid("b2", n), False, "api_settlement") for n in range(2)]
            # SK: three venue winners, plus one leg the venue still trades graded
            # all_losers off the false parent.
            + [(_oid(SK, n), SK, _cid("c3", n), True, "api_settlement") for n in range(3)]
            + [(_oid(SK, 5), SK, _cid("c3", 5), False, "all_losers")]
            + [(_oid(LP, n), LP, _cid("d4", n), False, "api_settlement") for n in range(3)]
            + [(_oid(DP, n), DP, _cid("e5", n), False, "api_settlement") for n in range(2)]
            # DP: a leg whose condition id is on no venue event.
            + [(_oid(DP, 9), DP, _cid("ff", 9), False, "api_settlement")]
        )
        for oid, mid, ext, w, src in legs:
            # A graded leg sits at its terminal price, as production stores it
            # (the specimen's 16 read 0.000000); the open SK leg trades at 3c.
            price = "0.03" if oid == _oid(SK, 5) else ("1" if w else "0")
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "current_probability, is_winner, resolution_source, last_updated) "
                    "VALUES (:id, :mid, :ext, :name, CAST(:price AS numeric), :w, :src, "
                    "'2026-10-02T06:00:00+00:00')"
                ),
                {"id": oid, "mid": mid, "ext": ext, "name": f"leg {oid}", "w": w,
                 "src": src, "price": price},
            )
    yield eng
    await eng.dispose()
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
    await admin.dispose()


@pytest.fixture
def maker(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)


async def _run(maker, mode, only=SELECTED):
    async with maker() as s:
        return await r.run(s, mode=mode, fetch_event=fetch, only=only)


async def _state(maker, mid):
    async with maker() as s:
        m = (await s.execute(text(
            "SELECT status, settled_at, market_metadata FROM futures_markets WHERE id = :id"
        ), {"id": mid})).first()
        legs = {
            int(x.id): (x.is_winner, x.resolution_source)
            for x in await s.execute(text(
                "SELECT id, is_winner, resolution_source FROM futures_outcomes "
                "WHERE market_id = :id"
            ), {"id": mid})
        }
    meta = m.market_metadata if isinstance(m.market_metadata, dict) else json.loads(m.market_metadata)
    return m.status, m.settled_at, meta, legs


async def _tables(maker):
    async with maker() as s:
        return {
            x[0] for x in await s.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :s"
            ), {"s": _SCHEMA})
        }


async def test_the_dry_run_writes_nothing_and_banks_nothing(maker):
    before = {mid: await _state(maker, mid) for mid in SELECTED}
    out = await _run(maker, "dry-run")
    c = out["counts"]
    assert (c[r.REOPEN], c[r.SKIP_NO_WITNESS], c[r.REFUSED]) == (3, 1, 1)
    assert c["written"] == 0
    assert {mid: await _state(maker, mid) for mid in SELECTED} == before
    assert r.BACKUP_MARKETS not in await _tables(maker)


async def test_apply_reopens_only_the_witnessed_boards(maker):
    ws_before = await _state(maker, WS)
    lp_before = await _state(maker, LP)
    dp_before = await _state(maker, DP)
    out = await _run(maker, "apply")
    c = out["counts"]
    assert (c["written"], c["drift"], c["bank_mismatch"]) == (3, 0, 0)
    assert (c["legs_cleared"], c["legs_promoted"]) == (1, 16)

    for mid in (WS, KF, SK):
        status, settled_at, meta, _legs = await _state(maker, mid)
        assert (status, settled_at) == ("open", None)
        assert r.GATE_KEY not in meta
        # Sibling keys survive the `-` operator.
        assert meta["shape"] == {"evidence": ["partial_field"]}
        assert meta["polymarket_event_id"]

    # The specimen's 16 eliminated matchups still read Lost; only Pass 4's
    # derived label became the venue's own. The SK hynix strikes still read hit.
    assert set(ws_before[3].values()) == {(False, "all_losers")}
    assert (await _state(maker, WS))[3] == {
        oid: (False, "api_settlement") for oid in ws_before[3]
    }
    sk_legs = (await _state(maker, SK))[3]
    assert all(sk_legs[_oid(SK, n)] == (True, "api_settlement") for n in range(3))
    # The derived stamp on the leg the venue still trades is cleared.
    assert sk_legs[_oid(SK, 5)] == (None, None)

    # No witness and wrong identity: not one byte moved.
    assert await _state(maker, LP) == lp_before
    assert await _state(maker, DP) == dp_before

    async with maker() as s:
        banked = {
            int(x.market_id): (x.status, x.resolution_gate)
            for x in await s.execute(text(
                f"SELECT market_id, status, resolution_gate FROM {r.BACKUP_MARKETS}"
            ))
        }
        legs_banked = (await s.execute(text(
            f"SELECT outcome_id, is_winner, resolution_source FROM {r.BACKUP_OUTCOMES}"
        ))).all()
    assert set(banked) == {WS, KF, SK}
    assert all(st == "resolved" for st, _g in banked.values())
    assert sorted(tuple(x) for x in legs_banked) == sorted(
        [(_oid(SK, 5), False, "all_losers")]
        + [(_oid(WS, n), False, "all_losers") for n in range(16)]
    )

    # A second apply finds them repaired.
    again = await _run(maker, "apply")
    assert again["counts"][r.NOOP] == 3 and again["counts"]["written"] == 0


async def test_a_reopened_board_has_no_leg_the_hourly_refresh_would_write(maker):
    """Why the promotion exists. ``polymarket_condition_refresh`` pools every live
    Polymarket market with a leg ``writable_leg_sql`` admits, grades it, and the
    #6919 deferred close then resolves any market whose stored legs are all
    graded. A reopened board with a writable leg would be closed again within
    the hour. Asked with the shipped predicate, not a copy of it."""
    from app.utils.futures_liveness import writable_leg_sql

    probe = text(
        "SELECT fo.market_id, count(*) FROM futures_outcomes fo "
        f"WHERE fo.market_id = ANY(:ids) AND {writable_leg_sql('fo')} "
        "AND fo.external_id LIKE '0x%' GROUP BY 1"
    )
    async with maker() as s:
        before = dict((await s.execute(probe, {"ids": [WS, KF, SK]})).all())
    assert before == {WS: 16, SK: 1}
    await _run(maker, "apply")
    async with maker() as s:
        after = dict((await s.execute(probe, {"ids": [WS, KF, SK]})).all())
    # SK's cleared open leg is writable on purpose: the venue still trades it and
    # the refresh should price it. The settled board halves are not.
    assert after == {SK: 1}


async def test_a_concurrent_write_after_the_bank_is_drift_for_that_board_alone(maker, monkeypatch):
    real_bank = r._bank

    async def bank_then_race(session, plans):
        good = await real_bank(session, plans)
        # Another writer re-stamps the Korn Ferry parent between bank and write.
        await session.execute(text(
            "UPDATE futures_markets SET settled_at = now() WHERE id = :id"
        ), {"id": KF})
        await session.commit()
        return good

    monkeypatch.setattr(r, "_bank", bank_then_race)
    out = await _run(maker, "apply")
    c = out["counts"]
    assert (c["written"], c["drift"]) == (2, 1)
    kf = next(m for m in out["markets"] if m["market_id"] == KF)
    assert kf["written"] is False and "changed under the run" in kf["not_written_because"]

    status, _settled, meta, _legs = await _state(maker, KF)
    assert status == "resolved" and meta[r.GATE_KEY] == GATE
    # The savepoint confined the miss: both siblings are written.
    assert (await _state(maker, WS))[0] == "open"
    sk = await _state(maker, SK)
    assert sk[0] == "open" and sk[3][_oid(SK, 5)] == (None, None)


async def test_a_leg_that_moved_after_the_bank_rolls_its_whole_board_back(maker, monkeypatch):
    real_bank = r._bank

    async def bank_then_race(session, plans):
        good = await real_bank(session, plans)
        await session.execute(text(
            "UPDATE futures_outcomes SET resolution_source = 'clob_resolve' WHERE id = :id"
        ), {"id": _oid(SK, 5)})
        await session.commit()
        return good

    monkeypatch.setattr(r, "_bank", bank_then_race)
    out = await _run(maker, "apply")
    assert (out["counts"]["written"], out["counts"]["drift"]) == (2, 1)
    status, _s, meta, legs = await _state(maker, SK)
    # The parent update inside the same savepoint rolled back with the leg.
    assert status == "resolved" and meta[r.GATE_KEY] == GATE
    assert legs[_oid(SK, 5)] == (False, "clob_resolve")


async def test_a_promoted_legs_price_moving_after_the_bank_is_drift(maker, monkeypatch):
    real_bank = r._bank

    async def bank_then_race(session, plans):
        good = await real_bank(session, plans)
        # A price write lands on one specimen leg: promoting it now would stamp
        # the venue label over a non-terminal price.
        await session.execute(text(
            "UPDATE futures_outcomes SET current_probability = 0.02 WHERE id = :id"
        ), {"id": _oid(WS, 7)})
        await session.commit()
        return good

    monkeypatch.setattr(r, "_bank", bank_then_race)
    out = await _run(maker, "apply")
    assert (out["counts"]["written"], out["counts"]["drift"]) == (2, 1)
    status, _s, meta, legs = await _state(maker, WS)
    assert status == "resolved" and meta[r.GATE_KEY] == GATE
    assert set(legs.values()) == {(False, "all_losers")}


async def test_restore_puts_back_exactly_what_was_banked(maker):
    before = {mid: await _state(maker, mid) for mid in SELECTED}
    await _run(maker, "apply")
    out = await _run(maker, "restore")
    assert out["counts"]["restored"] == 3 and out["counts"]["drift"] == 0
    assert {mid: await _state(maker, mid) for mid in SELECTED} == before
    # Restoring twice is a no-op, never a second write.
    again = await _run(maker, "restore")
    assert again["counts"]["restored"] == 0
    assert {m["market_id"]: m["restore"] for m in again["markets"]}[WS] == "noop"
    # And the repair can be re-applied from the same bank.
    reapply = await _run(maker, "apply")
    assert reapply["counts"]["written"] == 3 and reapply["counts"]["bank_mismatch"] == 0


async def test_restore_refuses_a_row_that_moved_after_the_apply(maker):
    await _run(maker, "apply")
    async with maker() as s:
        await s.execute(text(
            "UPDATE futures_outcomes SET is_winner = false, resolution_source = 'api_settlement' "
            "WHERE id = :id"
        ), {"id": _oid(SK, 5)})
        await s.commit()
    out = await _run(maker, "restore")
    assert (out["counts"]["restored"], out["counts"]["drift"]) == (2, 1)
    status, _s, _m, legs = await _state(maker, SK)
    # The parent restore rolled back with the leg it could not restore.
    assert status == "open" and legs[_oid(SK, 5)] == (False, "api_settlement")
