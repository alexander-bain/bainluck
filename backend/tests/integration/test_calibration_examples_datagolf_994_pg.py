"""#994 — a DataGolf bucket drill-in returns the rows the published chain admits.

THE DEFECT
----------
``/calibration/examples`` sampled the canonical population only for Kalshi and
Polymarket; a reader who clicked a DataGolf point got "No examples available for
this source" whatever the bucket held. DataGolf now takes the canonical branch
with ``market_info`` scoped to DataGolf's own markets, so the request evaluates
that source's markets instead of the whole resolved population.

WHAT ONLY POSTGRES CAN SAY
--------------------------
Which rows survive is decided inside the canonical chain: #5355 opening timing,
#762 void (did_not_play / withdrew), the cohort flag. ``tests/test_calibration_
examples_datagolf_994.py`` proves the dispatch and the request budget with a fake
session; it cannot see a population. This executes the REAL route on seeded rows
and checks four things:

  1. NON-VACUITY FIRST: healthy pre-start forecasts in the bucket are returned,
     winners AND losers, with their own market/outcome ids and results.
  2. Every exclusion holds through the drill-in: a post-start opening and a
     void row in the same bucket never appear.
  3. SCOPE PARITY: the scoped sample is exactly the bucket's members in the
     UNSCOPED chain (the one the curve is built from), for both cohorts.
  4. A DataGolf market sharing a group id with another source is refused
     (``examples_scope_not_closed``) rather than sampled from a chain whose
     representatives could differ.

This is source evidence on a fixture. It is not production membership proof,
and it does not show the rows were members of an older published generation.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``: a PG-gated file no
workflow step invokes skips silently while pytest still exits 0.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #994 examples contract",
    ),
]

DG_MID = 994101
POLY_MID = 994102
KALSHI_MID = 994103
ALL_MIDS = (DG_MID, POLY_MID, KALSHI_MID)
BUCKET = 6  # [0.60, 0.70)

# Fixed once per run: offset FIRST, never branch on the clock (gotcha #44).
NOW = datetime.now(timezone.utc).replace(microsecond=0)
COMMENCE = NOW - timedelta(days=10)
PRE = COMMENCE - timedelta(days=3)
LATE_PRE = COMMENCE - timedelta(hours=1)
POST = COMMENCE + timedelta(days=1)

# (name, opening, calibration_probability, is_winner, resolution_source, snapshots)
# A make-the-cut board, not a partition, so one withheld row cannot take its
# neighbours down through field completeness. Prices sit inside 0.005..0.98.
BOARD = [
    # In the bucket, published, the price never moved (all-outcomes cohort only).
    ("Pre 64 made it", 0.64, 0.64, True, "leaderboard", [("datagolf_model", 0.64, PRE)]),
    ("Pre 61 missed", 0.61, 0.61, False, "leaderboard", [("datagolf_model", 0.61, PRE)]),
    # In the bucket, published, moved to a pre-start closing line (both cohorts).
    (
        "Moved to 65",
        0.55,
        0.65,
        True,
        "leaderboard",
        [("datagolf_model", 0.55, PRE), ("datagolf_model", 0.65, LATE_PRE)],
    ),
    # #5355: first read after the start — not a forecast, in the bucket by price.
    ("Post-start 66", 0.66, 0.66, True, "leaderboard", [("datagolf_model", 0.66, POST)]),
    # #762: a void — no outcome to score, in the bucket by price.
    ("DNP 63", 0.63, 0.63, False, "did_not_play", [("datagolf_model", 0.63, PRE)]),
    # Outside the bucket: shape only.
    ("Pre 91", 0.91, 0.91, True, "leaderboard", [("datagolf_model", 0.91, PRE)]),
    ("Pre 36", 0.36, 0.36, False, "leaderboard", [("datagolf_model", 0.36, PRE)]),
    ("Pre 24", 0.24, 0.24, False, "leaderboard", [("datagolf_model", 0.24, PRE)]),
]
EXCLUDED = {"Post-start 66", "DNP 63"}

# Another source with a row in the same bucket: it must never leak into DataGolf.
POLY_BOARD = [
    ("Poly 65", 0.65, True),
    ("Poly 91", 0.91, True),
    ("Poly 36", 0.36, False),
    ("Poly 24", 0.24, False),
]


def _oid(mid: int, idx: int) -> int:
    return mid * 1000 + idx


async def _seed_market(session, mid, *, source, commence, group_id=None):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, volume, "
            "commence_time, resolution_date, group_id) VALUES "
            "(:id, :xid, :nm, :src, 'resolved', 'placement', false, "
            "'participation', 'golf', 100, :ct, :rd, :gid)"
        ),
        {
            "id": mid,
            "xid": f"{source}:pga:994{mid}:make_cut",
            "nm": f"Test Open {mid} - Make the Cut",
            "src": source,
            "ct": commence,
            "rd": NOW - timedelta(days=7),
            "gid": group_id,
        },
    )


async def _seed_outcome(session, oid, mid, name, opening, cp, winner, res_src, snapshots):
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, :nm, :op, :cp, :win, :rs, 10)"
        ),
        {
            "id": oid,
            "mid": mid,
            "xid": f"dg_{oid}",
            "nm": name,
            "op": opening,
            "cp": cp,
            "win": winner,
            "rs": res_src,
        },
    )
    for bookmaker, prob, captured_at in snapshots:
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, "
                "probability, reading_count, last_price, yes_bid, yes_ask, "
                "captured_at) VALUES "
                "(:oid, :bk, :p, 1, :p, :p, :p, :at)"
            ),
            {"oid": oid, "bk": bookmaker, "p": prob, "at": captured_at},
        )


async def _clear(session):
    for mid in ALL_MIDS:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
            ),
            {"mid": mid},
        )
        await session.execute(
            text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid}
        )
        await session.execute(text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.routes import calibration as cal

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        await _seed_market(s, DG_MID, source="datagolf", commence=COMMENCE)
        for idx, (name, op, cp, win, rs, snaps) in enumerate(BOARD):
            await _seed_outcome(s, _oid(DG_MID, idx), DG_MID, name, op, cp, win, rs, snaps)
        await _seed_market(s, POLY_MID, source="polymarket", commence=COMMENCE)
        for idx, (name, p, win) in enumerate(POLY_BOARD):
            await _seed_outcome(
                s, _oid(POLY_MID, idx), POLY_MID, name, p, p, win, "api_settlement",
                [("polymarket", p, POST)],
            )
        await s.commit()
        cal._examples_cache.clear()
        yield s
        cal._examples_cache.clear()
        await s.rollback()
        await _clear(s)
        await s.commit()
    await engine.dispose()


async def _examples(session, *, well_traded: int, source: str = "datagolf"):
    from app.routes import calibration as cal

    cal._examples_cache.clear()
    res = await cal.calibration_examples(
        db=session, source=source, bucket=BUCKET, well_traded=well_traded, limit=10
    )
    # The route arms SET LOCAL inside the session's transaction; end it so the
    # next read starts clean.
    await session.rollback()
    return res


async def _published_bucket(session, *, moved_only: bool) -> dict[int, bool]:
    """The bucket's members in the UNSCOPED chain the curve is built from."""
    from app.tasks.precompute_calibration import _calibration_population_ctes

    moved = "AND d.price_moved = true" if moved_only else ""
    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + f"""
            SELECT d.outcome_id, d.is_winner FROM deduped d
            WHERE d.source = 'datagolf' AND d.market_id = :mid
              AND LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) = :bucket
              {moved}
            """
        ),
        {"mid": DG_MID, "bucket": BUCKET},
    )
    out = {r.outcome_id: bool(r.is_winner) for r in rows.all()}
    await session.rollback()
    return out


def _ours(res) -> dict[int, dict]:
    assert isinstance(res, dict), f"expected a served body, got {res!r}"
    return {e["outcome_id"]: e for e in res["examples"] if e["market_id"] == DG_MID}


async def test_pre_start_forecasts_are_returned_with_ids_and_results(session):
    res = await _examples(session, well_traded=0)
    ours = _ours(res)
    names = {e["outcome_name"] for e in ours.values()}
    assert {"Pre 64 made it", "Pre 61 missed", "Moved to 65"} <= names, sorted(names)
    by_name = {e["outcome_name"]: (oid, e) for oid, e in ours.items()}
    oid, e = by_name["Pre 64 made it"]
    assert oid == _oid(DG_MID, 0) and e["result"] == "Yes"
    assert by_name["Pre 61 missed"][1]["result"] == "No"
    for e in ours.values():
        assert 0.60 <= e["price"] < 0.70, e
    assert res["sampling"]["published_generation_membership"] == "unverified"


async def test_excluded_rows_never_reach_the_drill_in(session):
    for wt in (0, 1):
        names = {e["outcome_name"] for e in _ours(await _examples(session, well_traded=wt)).values()}
        # An empty sample excludes everything; it must also carry the moved row.
        assert "Moved to 65" in names, (wt, sorted(names))
        assert not (EXCLUDED & names), (wt, sorted(EXCLUDED & names))


async def test_another_source_never_leaks_into_datagolf(session):
    res = await _examples(session, well_traded=0)
    assert all(e["market_id"] != POLY_MID for e in res["examples"])
    # Control: Polymarket's own drill-in still serves its row (unscoped path).
    poly = await _examples(session, well_traded=0, source="polymarket")
    assert any(e["market_id"] == POLY_MID for e in poly["examples"])


@pytest.mark.parametrize("well_traded", [0, 1])
async def test_the_scoped_sample_is_the_published_bucket(session, well_traded):
    expected = await _published_bucket(session, moved_only=bool(well_traded))
    assert expected, "the unscoped chain published nothing here — the fixture is broken"
    res = await _examples(session, well_traded=well_traded)
    assert len(res["examples"]) < 10, "the sample was truncated; parity is not testable"
    ours = _ours(res)
    assert set(ours) == set(expected)
    for oid, won in expected.items():
        assert ours[oid]["result"] == ("Yes" if won else "No")


async def test_the_moved_cohort_is_a_strict_subset(session):
    all_rows = set(_ours(await _examples(session, well_traded=0)))
    moved = set(_ours(await _examples(session, well_traded=1)))
    assert moved and moved < all_rows
    assert _oid(DG_MID, 2) in moved  # "Moved to 65"


async def test_a_group_shared_with_another_source_is_refused(session):
    await session.execute(
        text("UPDATE futures_markets SET group_id = 'shared:994' WHERE id = :mid"),
        {"mid": DG_MID},
    )
    await _seed_market(
        session, KALSHI_MID, source="kalshi", commence=COMMENCE, group_id="shared:994"
    )
    await session.commit()
    res = await _examples(session, well_traded=0)
    assert getattr(res, "status_code", None) == 503
    assert json.loads(res.body)["reason"] == "examples_scope_not_closed"


# ---------------------------------------------------------------------------
# #994 cost: the scoped branch evaluates the chain per frozen roster chunk. The
# union of the chunks must be EXACTLY the bucket the unscoped chain publishes —
# including a same-source group (one ``g:`` question over three markets), which
# a chunk boundary must never cut.
# ---------------------------------------------------------------------------
GROUP_MIDS = (994211, 994212, 994213)
SINGLE_MIDS = (994221, 994222, 994223, 994224)
CHUNK_BOARD = [
    # (name, opening, calibration_probability, is_winner)
    ("in bucket, still", 0.62, 0.62, True),
    ("in bucket, moved", 0.55, 0.66, False),
    ("out of bucket", 0.31, 0.31, False),
]


async def _bucket_in_chain(session, mids, *, moved_only: bool) -> dict[int, bool]:
    from app.tasks.precompute_calibration import _calibration_population_ctes

    moved = "AND d.price_moved = true" if moved_only else ""
    rows = await session.execute(
        text(
            "WITH "
            + _calibration_population_ctes()
            + f"""
            SELECT d.outcome_id, d.is_winner FROM deduped d
            WHERE d.source = 'datagolf' AND d.market_id = ANY(:mids)
              AND LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) = :bucket
              {moved}
            """
        ),
        {"mids": list(mids), "bucket": BUCKET},
    )
    out = {r.outcome_id: bool(r.is_winner) for r in rows.all()}
    await session.rollback()
    return out


async def _chunked_bucket(session, *, moved_only: bool) -> tuple[dict[int, bool], list]:
    """The route's own chunk path, unsampled: roster -> chunks -> union."""
    from app.routes import calibration as cal

    roster = (await session.execute(
        text(cal._examples_roster_sql()), {"source": "datagolf"}
    )).all()
    chunks = cal._examples_roster_chunks(roster)
    out: dict[int, bool] = {}
    for chunk in chunks:
        rows = (await session.execute(
            cal._examples_chunk_sql(moved_only),
            cal._examples_chunk_params(chunk, "datagolf", BUCKET),
        )).all()
        for r in rows:
            assert r.outcome_id not in out, "a row was published by two chunks"
            out[r.outcome_id] = bool(r.is_winner)
    await session.rollback()
    return out, chunks


@pytest.mark.parametrize("well_traded", [0, 1])
async def test_the_chunked_bucket_is_the_published_bucket(session, monkeypatch, well_traded):
    from app.routes import calibration as cal

    mids = (DG_MID,) + GROUP_MIDS + SINGLE_MIDS
    try:
        for mid in GROUP_MIDS + SINGLE_MIDS:
            gid = "datagolf:994grp" if mid in GROUP_MIDS else None
            await _seed_market(session, mid, source="datagolf", commence=COMMENCE, group_id=gid)
            for idx, (name, op, cp, win) in enumerate(CHUNK_BOARD):
                snaps = [("datagolf_model", op, PRE)]
                if cp != op:
                    snaps.append(("datagolf_model", cp, LATE_PRE))
                await _seed_outcome(
                    session, _oid(mid, idx), mid, f"{name} {mid}", op, cp, win, "leaderboard", snaps
                )
        await session.commit()
        monkeypatch.setattr(cal, "_EXAMPLES_CHUNK_MARKETS", 2)

        expected = await _bucket_in_chain(session, mids, moved_only=bool(well_traded))
        got, chunks = await _chunked_bucket(session, moved_only=bool(well_traded))
        got = {oid: won for oid, won in got.items() if oid // 1000 in mids}
        # Non-vacuity: the group question and lone markets both publish here.
        assert {oid // 1000 for oid in expected} & set(GROUP_MIDS), expected
        assert {oid // 1000 for oid in expected} & set(SINGLE_MIDS), expected
        assert len(chunks) >= 4, "the cap of 2 must force several chunks"
        holding = [c for c in chunks if {r.market_id for r in c} & set(GROUP_MIDS)]
        assert len(holding) == 1 and {r.market_id for r in holding[0]} >= set(GROUP_MIDS)
        assert {r.vm_id for r in holding[0] if r.market_id in GROUP_MIDS} == {"g:datagolf:994grp"}
        assert got == expected

        # And the served handler draws only from that set.
        res = await _examples(session, well_traded=well_traded)
        served = {e["outcome_id"] for e in res["examples"] if e["market_id"] in mids}
        assert served and served <= set(expected)
    finally:
        await session.rollback()
        for mid in GROUP_MIDS + SINGLE_MIDS:
            await session.execute(
                text(
                    "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                    "(SELECT id FROM futures_outcomes WHERE market_id = :mid)"
                ),
                {"mid": mid},
            )
            await session.execute(text("DELETE FROM futures_outcomes WHERE market_id = :mid"), {"mid": mid})
            await session.execute(text("DELETE FROM futures_markets WHERE id = :mid"), {"mid": mid})
        await session.commit()


# ---------------------------------------------------------------------------
# The request budget and session ownership, on a real server. The closure check
# is swapped for a statement that sleeps, so the only thing under test is who
# stops it and whose session it ran on.
# ---------------------------------------------------------------------------
SLEEP_MARK = "994-owned-sample-probe"
SLEEPING_CLOSURE_SQL = f"SELECT pg_sleep(30) IS NULL AS shares_identity /* {SLEEP_MARK} */"


async def _probe_backends(session) -> int:
    n = (
        await session.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'active' AND query LIKE :mark AND pid <> pg_backend_pid()"
            ),
            {"mark": f"%{SLEEP_MARK}%"},
        )
    ).scalar()
    await session.rollback()
    return int(n)


async def test_the_server_enforces_the_remaining_budget(session, monkeypatch):
    from app.routes import calibration as cal

    monkeypatch.setattr(cal, "_EXAMPLES_SCOPE_CLOSED_SQL", SLEEPING_CLOSURE_SQL)
    monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_STATEMENT_WALL_S", 0.3)
    monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_DEADLINE_S", 5.0)
    cal._examples_cache.clear()
    res = await cal.calibration_examples(
        db=session, source="datagolf", bucket=BUCKET, well_traded=0, limit=10
    )
    # Postgres cancelled it (57014) inside the armed remainder — not the backstop.
    assert getattr(res, "status_code", None) == 503
    assert json.loads(res.body)["reason"] == "examples_query_timeout"
    # And the request's own session was never used: no transaction was begun on it.
    assert not session.in_transaction()
    assert await _probe_backends(session) == 0


async def test_a_cancelled_request_leaves_no_statement_running(session, monkeypatch):
    import asyncio

    from app.routes import calibration as cal

    monkeypatch.setattr(cal, "_EXAMPLES_SCOPE_CLOSED_SQL", SLEEPING_CLOSURE_SQL)
    monkeypatch.setattr(cal, "_EXAMPLES_SCOPED_CLEANUP_S", 3.0)
    cal._examples_cache.clear()
    parent = asyncio.create_task(
        cal.calibration_examples(
            db=session, source="datagolf", bucket=BUCKET, well_traded=0, limit=10
        )
    )
    # Wait until the sample's statement is actually running on the server.
    for _ in range(100):
        await asyncio.sleep(0.05)
        if await _probe_backends(session):
            break
    else:
        parent.cancel()
        pytest.fail("the sleeping closure never reached the server")
    parent.cancel()
    with pytest.raises(asyncio.CancelledError):
        await parent
    assert not [t for t in cal._examples_inflight if not t.done()], (
        "the request exited while its sample task was still running"
    )
    # The statement is gone from the server, not sleeping out its 30 s.
    for _ in range(40):
        if await _probe_backends(session) == 0:
            break
        await asyncio.sleep(0.05)
    assert await _probe_backends(session) == 0
