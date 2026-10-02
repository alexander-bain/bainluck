"""#1870 consumer half — the receipt-aware trade-evidence rule, on real JSONB.

THE DEFECT
----------
``fo.volume`` is an integer; Polymarket's traded amount is not. Both Polymarket
writers carry the fact in ``market_metadata['volume_evidence']`` and may leave
the scalar NULL beside it — and the recovery rail used to write ``int(0.25)``
== 0 beside a ``traded`` receipt. ``calibration_trade_evidence`` read only the
scalar, so a condition that traded read ``unknown`` (NULL) or ``untraded`` (0).

WHY THIS IS A POSTGRES TEST
---------------------------
The receipt clauses are JSONB (``->``, ``->>``, ``jsonb_typeof``, a guarded
``::numeric`` cast). The SQLite oracle in ``test_calibration_trade_evidence_1530``
executes only the scalar rule and cannot run a byte of this. So here the SQL is
EXECUTED against real JSONB beside the Python twin over a matrix that includes
malformed receipts, non-object metadata and string-typed numbers (a cast PG
might evaluate early would abort the whole census, not one row), and the real
``census()`` callable is driven over seeded windows.

NON-VACUITY: every census arm is paired with the same rows rendered through the
scalar-only rule, which must read them DIFFERENTLY — otherwise a green run would
not prove the receipt clauses ran.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1870 receipt contract",
    ),
]

#: Market ids; outcome ids are BASE + offset so each block is contiguous and
#: the census can walk exactly one block with offset/limit.
MATRIX_BASE = 18_701_000
ZERO_BASE = 18_702_000
FRACTION_BASE = 18_703_000
UNFETCHED_BASE = 18_704_000
BLOCKS = (MATRIX_BASE, ZERO_BASE, FRACTION_BASE, UNFETCHED_BASE)
COHORT_N = 5

_SENTINEL = object()


def _forward(amount):
    from app.tasks.polymarket import polymarket_activity_volume

    out = polymarket_activity_volume(
        amount, observed_at=datetime(2026, 10, 2, 18, tzinfo=timezone.utc)
    )
    return out.scalar, {"volume_evidence": out.receipt}


def _recovery(evidence, **kw):
    from app.utils.polymarket_evidence import PMEvidence, build_evidence_receipt

    return {"volume_evidence": build_evidence_receipt(PMEvidence(evidence), **kw)}


def _matrix():
    """(source, volume, open_interest, market_metadata) — metadata may be any JSON."""
    fwd_frac_scalar, fwd_frac = _forward(0.25)
    fwd_zero_scalar, fwd_zero = _forward(0)
    fwd_big_scalar, fwd_big = _forward(405.9)
    rec_frac = _recovery("traded", n_trades=0, gamma_volume=0.25)
    rec_trades = _recovery("traded", n_trades=3, gamma_volume=0.0)
    rec_zero = _recovery("confirmed_zero", n_trades=0)
    rec_dead = _recovery("unaddressable")
    fwd = "gamma:events:condition-volume"
    rec = "clob:existence+data-api:trades+gamma:events"
    return [
        ("polymarket", fwd_frac_scalar, None, fwd_frac),
        ("polymarket", fwd_zero_scalar, None, fwd_zero),
        ("polymarket", None, None, fwd_zero),
        ("polymarket", 12, None, fwd_zero),
        ("polymarket", None, 40, fwd_zero),
        ("polymarket", fwd_big_scalar, None, fwd_big),
        ("polymarket", 0, None, rec_frac),
        ("polymarket", None, None, rec_frac),
        ("polymarket", 0, None, rec_trades),
        ("polymarket", 0, None, rec_zero),
        ("polymarket", None, None, rec_zero),
        ("polymarket", None, None, rec_dead),
        ("polymarket", None, 7, rec_dead),
        ("polymarket", None, None, None),
        ("polymarket", None, None, {}),
        ("polymarket", None, 7, None),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "traded", "probe": fwd, "grain": "condition", "gamma_volume": "5"}}),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "traded", "probe": fwd, "grain": "condition", "gamma_volume": True}}),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "traded", "probe": fwd, "gamma_volume": 5}}),
        ("polymarket", 0, None, {"volume_evidence": {"verdict": "traded", "probe": "elsewhere", "gamma_volume": 5}}),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "traded", "probe": rec}}),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "confirmed_zero", "probe": rec, "n_trades": 0, "gamma_volume": "0"}}),
        ("polymarket", None, None, {"volume_evidence": {"verdict": "confirmed_zero", "probe": rec, "n_trades": 0, "gamma_volume": None}}),
        ("polymarket", 12, None, {"volume_evidence": {"verdict": "confirmed_zero", "probe": rec, "n_trades": 2}}),
        ("polymarket", None, None, {"volume_evidence": "traded"}),
        ("polymarket", None, None, {"volume_evidence": ["traded"]}),
        ("polymarket", None, None, ["volume_evidence"]),
        ("polymarket", None, None, "a string"),
        ("polymarket", None, None, _SENTINEL),  # JSON null, not SQL NULL
        ("kalshi", None, None, fwd_frac),
        ("kalshi", 0, None, rec_frac),
        ("odds_api", None, None, fwd_frac),
        ("datagolf", 0, None, rec_frac),
        ("datagolf", None, None, None),
    ]


async def _seed(session, market_id, outcome_id, source, volume, oi, meta):
    if meta is _SENTINEL:
        meta_json = "null"
    else:
        meta_json = json.dumps(meta) if meta is not None else None
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, external_id, name, source, status, "
            "category, mutually_exclusive, market_type, llm_sport_category, "
            "open_interest, market_metadata, resolution_date) VALUES "
            "(:id, :xid, :nm, :src, 'resolved', 'test', false, 'binary', 'test', "
            ":oi, CAST(:meta AS jsonb), NOW() - INTERVAL '7 days')"
        ),
        {
            "id": market_id,
            "xid": f"t1870:{market_id}",
            "nm": f"#1870 receipt fixture {market_id}",
            "src": source,
            "oi": oi,
            "meta": meta_json,
        },
    )
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
            "opening_probability, calibration_probability, is_winner, "
            "resolution_source, volume) VALUES "
            "(:id, :mid, :xid, 'Yes', 0.4, 0.4, true, 'date_passed', :vol)"
        ),
        {"id": outcome_id, "mid": market_id, "xid": f"t1870_{outcome_id}", "vol": volume},
    )


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        for base in BLOCKS:
            await s.execute(
                text("DELETE FROM futures_outcomes WHERE id >= :lo AND id < :hi"),
                {"lo": base, "hi": base + 1000},
            )
            await s.execute(
                text("DELETE FROM futures_markets WHERE id >= :lo AND id < :hi"),
                {"lo": base, "hi": base + 1000},
            )
        for i, (src, vol, oi, meta) in enumerate(_matrix()):
            await _seed(s, MATRIX_BASE + i, MATRIX_BASE + i, src, vol, oi, meta)
        zero_scalar, zero_meta = _forward(0)
        frac_scalar, frac_meta = _forward(0.25)
        for i in range(COHORT_N):
            await _seed(s, ZERO_BASE + i, ZERO_BASE + i, "polymarket", zero_scalar, None, zero_meta)
            await _seed(s, FRACTION_BASE + i, FRACTION_BASE + i, "polymarket", frac_scalar, None, frac_meta)
            await _seed(s, UNFETCHED_BASE + i, UNFETCHED_BASE + i, "polymarket", None, None, None)
        await s.commit()
        yield s
    await engine.dispose()


async def _sql_classes(session, base, n, *, receipt_aware=True):
    from app.utils.calibration_trade_evidence import trade_evidence_sql

    case = trade_evidence_sql(metadata="fm.market_metadata") if receipt_aware else trade_evidence_sql()
    rows = await session.execute(
        text(
            f"SELECT fo.id, {case} AS klass FROM futures_outcomes fo "
            "JOIN futures_markets fm ON fm.id = fo.market_id "
            "WHERE fo.id >= :lo AND fo.id < :hi ORDER BY fo.id"
        ),
        {"lo": base, "hi": base + n},
    )
    return [r.klass for r in rows.all()]


async def test_the_jsonb_sql_and_the_python_twin_agree_on_every_row(session):
    from app.utils.calibration_trade_evidence import classify

    matrix = _matrix()
    sql = await _sql_classes(session, MATRIX_BASE, len(matrix))
    py = [classify(src, vol, oi, None if m is _SENTINEL else m) for src, vol, oi, m in matrix]
    assert len(sql) == len(matrix), "every seeded row must come back — a dropped row is a vacuous pass"
    mismatches = [(i, matrix[i][:3], sql[i], py[i]) for i in range(len(matrix)) if sql[i] != py[i]]
    assert not mismatches, mismatches


async def test_the_matrix_exercises_every_receipt_outcome(session):
    """The agreement above is only an oracle if the matrix reaches each clause."""
    classes = await _sql_classes(session, MATRIX_BASE, len(_matrix()))
    assert classes[0] == "traded", "fractional forward receipt beside NULL"
    assert classes[3] == "unknown", "confirmed-zero receipt beside positive scalar"
    assert classes[6] == "traded", "recovery traded receipt beside manufactured 0"
    assert classes[10] == "untraded", "recovery confirmed zero beside NULL"
    assert {"traded", "untraded", "unknown", "traded_open_interest", "not_applicable"} <= set(classes)


async def _census_window(session, base):
    from app.tasks.census_trade_evidence import build_census, census

    window = await census(session, limit=COHORT_N, offset=base - 1)
    assert window["rows_walked"] == COHORT_N
    assert window["window"] == {"lo": base, "hi": base + COHORT_N - 1}, (
        "another fixture's rows sit inside this id block; the window is not ours"
    )
    window["exhausted"] = True  # one deliberate block, read as a whole census
    out = build_census([window])
    (poly,) = [s for s in out["by_source"] if s["source"] == "polymarket"]
    return poly


async def test_the_census_reads_a_fractional_traded_cohort_as_traded(session):
    poly = await _census_window(session, FRACTION_BASE)
    assert poly["traded"] == COHORT_N
    assert poly["traded_share_of_evidenced_pct"] == 100.0
    # Strawman: the scalar-only rule reads the same rows as unknown.
    assert set(await _sql_classes(session, FRACTION_BASE, COHORT_N, receipt_aware=False)) == {"unknown"}


async def test_the_census_reads_a_confirmed_zero_cohort_as_zero_percent(session):
    poly = await _census_window(session, ZERO_BASE)
    assert poly["untraded"] == COHORT_N
    assert poly["evidenced_n"] == COHORT_N
    assert poly["traded_share_of_evidenced_pct"] == 0.0


async def test_the_census_reads_an_unfetched_cohort_as_cannot_say(session):
    poly = await _census_window(session, UNFETCHED_BASE)
    assert poly["unknown"] == COHORT_N
    assert poly["evidenced_n"] == 0
    assert poly["traded_share_of_evidenced_pct"] is None
