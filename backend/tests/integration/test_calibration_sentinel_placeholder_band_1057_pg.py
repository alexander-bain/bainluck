"""#1057 — the sentinel's placeholder-band candidate and its census, on real Postgres.

PILLAR: TRUTH. SHIP: Accuracy diagnostics identify placeholder-price artifacts
clearly, so a real forecast failure is told apart from missing trading evidence.

The unit tests prove the band's arithmetic and its four diagnostic states over
synthetic scan rows, and run the census on SQLite. Neither runs the futures
MINING scan, which is Postgres-only (window functions, ``split_part``, the
prop-threshold regex). A mistake in the new ``price_band`` column or its extra
GROUP BY key would make that scan fail in production and the sentinel would mine
no futures cohort at all. This runs the real scan and the real census over typed
rows supplied as CTE shadows of the three tables, read-only, nothing written.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1057 placeholder-band gate",
    ),
]

BAND = "placeholder_band_0.45_0.55"

# (market_id, source, [(outcome_id, cp, is_winner, has_bid_or_trade), ...])
_MARKETS = [
    (1, "polymarket", [(11, 0.48, False, False), (12, 0.52, True, False)]),   # no-bid band
    (2, "polymarket", [(21, 0.45, False, True), (22, 0.55, True, True)]),     # traded band, edges
    (3, "polymarket", [(31, 0.44, False, False), (32, 0.56, True, False)]),   # just outside
    (4, "kalshi", [(41, 0.48, False, False), (42, 0.52, True, False)]),       # ineligible source
    (5, "polymarket", [(51, 0.90, True, False), (52, 0.10, False, False)]),   # tails
]


def _prefix() -> str:
    markets = ", ".join(
        f"({mid}, '{src}'::text, 'basketball'::text, 'm-{mid}'::text, TRUE, "
        f"TIMESTAMPTZ '2026-01-01', 'resolved'::text)"
        for mid, src, _ in _MARKETS
    )
    outcomes = ", ".join(
        f"({oid}, {mid}, 'leg {oid}'::text, {str(win).upper()}, 'api_settlement'::text, "
        f"{cp}::float8, {cp}::float8)"
        for mid, _, legs in _MARKETS for oid, cp, win, _ in legs
    )
    snaps = ", ".join(
        f"({oid}, {0.5 if traded else 0.0}::float8, {0.5 if traded else 0.0}::float8)"
        for _, _, legs in _MARKETS for oid, _, _, traded in legs
    )
    return (
        "WITH futures_markets(id, source, llm_sport_category, external_id, "
        f"mutually_exclusive, created_at, status) AS (VALUES {markets}), "
        "futures_outcomes(id, market_id, name, is_winner, resolution_source, "
        f"calibration_probability, opening_probability) AS (VALUES {outcomes}), "
        f"futures_odds_snapshots(outcome_id, yes_bid, last_price) AS (VALUES {snaps}) "
    )


def _cs():
    # The MODULE, not `from app.tasks import calibration_sentinel`: the package
    # re-exports a Celery task under that name.
    return importlib.import_module("app.tasks.calibration_sentinel")


class _ShadowSession:
    """Runs a sentinel statement with the shadow tables prepended."""

    def __init__(self, session):
        self._s = session

    async def execute(self, stmt, params=None):
        sql = str(stmt).lstrip()
        assert sql.startswith("WITH "), sql[:40]
        return await self._s.execute(text(_prefix() + ", " + sql[len("WITH "):]), params or {})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    async with async_sessionmaker(engine)() as s:
        await s.execute(text("SET TRANSACTION READ ONLY"))
        yield s
        await s.rollback()
    await engine.dispose()


async def _scan(session):
    cs = _cs()
    res = await _ShadowSession(session).execute(text(cs._FUTURES_MINING_SQL))
    return [dict(r) for r in res.mappings()]


async def test_the_scan_tags_exactly_the_polymarket_band(session):
    rows = await _scan(session)
    assert sum(int(r["n"]) for r in rows) == 10, "raw accounting is unchanged"
    band = [r for r in rows if r["price_band"] is not None]
    assert {r["price_band"] for r in band} == {BAND}
    assert {r["source"] for r in band} == {"polymarket"}
    # Markets 1 and 2: 0.45, 0.48 in bucket 4; 0.52, 0.55 in bucket 5 (inclusive).
    assert {int(r["bucket"]): int(r["n"]) for r in band} == {4: 2, 5: 2}
    assert sum(int(r["winners"]) for r in band) == 2


async def test_the_band_key_splits_its_bucket_rather_than_merging(session):
    rows = await _scan(session)
    poly_b4 = [r for r in rows if r["source"] == "polymarket" and int(r["bucket"]) == 4]
    # 0.44 shares bucket 4 with 0.45/0.48 but is outside the band: its own row.
    assert sorted((r["price_band"] or "", int(r["n"])) for r in poly_b4) == [("", 1), (BAND, 2)]
    kalshi = [r for r in rows if r["source"] == "kalshi"]
    assert kalshi and all(r["price_band"] is None for r in kalshi)


async def test_the_scan_folds_into_one_band_cohort(session):
    cs = _cs()
    cohorts = {}
    for row in await _scan(session):
        row["series_family"] = cs.series_family(row["series_family"])
        for ck in cs._cohort_views(row):
            c = cohorts.get(ck)
            if c is None:
                c = cohorts[ck] = cs._new_cohort(ck, row)
            cs._fold_row_into_cohort(c, row)
    band = [c for c in cohorts.values() if "price_band" in c["dims"]]
    assert [c["dims"] for c in band] == [
        {"provenance": "futures", "source": "polymarket", "price_band": BAND}
    ]
    assert band[0]["total_n"] == 4


async def test_the_census_confirms_only_the_no_bid_half_of_the_band(session):
    cs = _cs()
    dims = {"provenance": "futures", "source": "polymarket", "price_band": BAND}
    ph = await cs._placeholder_fraction(_ShadowSession(session), dims)
    # Market 1's two legs never traded; market 2's did. Both are candidates.
    assert ph == 0.5
    rows = await cs._sample_rows(_ShadowSession(session), dims)
    assert sorted(r["outcome_id"] for r in rows) == [11, 12, 21, 22]
