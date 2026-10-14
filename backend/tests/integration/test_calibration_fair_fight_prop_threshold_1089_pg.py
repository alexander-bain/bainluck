"""#1089 — the source comparison honours the NHL goal-family price-band exclusion, on ROWS.

The Kalshi-vs-Polymarket fair fight (``_query_futures_fair_fight_impl``) grades
``COALESCE(calibration_probability, opening_probability)`` against ``is_winner``.
Queue #188 Item 3 gave it the shared #941/#186 prop-threshold exclusion; the #197
perf rewrite dropped it, and the surviving guard only searched the source for the
truth allowlist and the liquidity predicate. Neither of those proxies covers the
defect: a high-band NHL goal-family row is ``api_settlement`` / ``box_score``
graded AND bid-bearing, so both admit it, while its captured price is
settlement-contaminated (#941). So the corrupt rows were counted as failed Kalshi
forecasts.

WHY THIS IS A POSTGRES TEST
---------------------------
The claim is about which rows the real query selects. This runs the UNMODIFIED
impl through a session proxy that records the rows its one statement returns, and
diffs them against a pre-seed baseline, so leftovers from sibling gates cannot
satisfy or break an assertion.

THE CONTROLS ARE THE POINT
--------------------------
* NHL ``< 0.50`` stays (Queue #194's honest-band recovery), so a rule widened to
  "all hockey thresholds" fails ``test_nhl_honest_low_band_stays``.
* Non-NHL threshold rows below 0.90 stay, and the general ``>= 0.90`` rule still
  excludes, so a hockey-only rule or a dropped degenerate band fails.
* Non-threshold Kalshi rows and Polymarket threshold-shaped rows stay: the rule is
  scoped to Kalshi ``Player: N+`` names.
* The band reads the curve price: cp wins over opening in both directions.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and named in ``ci.yml``.
"""

from __future__ import annotations

import os
from collections import Counter

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1089 fair-fight contract",
    ),
]

# Market ids well clear of anything the sibling PG gates seed.
MID_BASE = 961089
NHL_KEY = "test-1089::hockey::player-goals"
MLB_KEY = "test-1089::baseball::player-hits"

# (label, source, category, key, outcome name, cp, opening, resolution_source, winner)
# Prices are distinct to 4 dp so each specimen is identifiable in the row multiset.
SPECIMENS = [
    # NHL goal-family, high band: graded by independent truth, bid-bearing — both
    # proxies admit them. The exclusion must drop them.
    ("nhl_high_api", "kalshi", "hockey", NHL_KEY, "Auston Matthews: 1+", 0.6213, 0.6213, "api_settlement", False),
    ("nhl_high_box", "kalshi", "hockey", NHL_KEY, "Nathan MacKinnon: 2+", 0.7731, 0.7731, "box_score", False),
    ("nhl_edge_050", "kalshi", "hockey", NHL_KEY, "Cale Makar: 1+", 0.5000, 0.5000, "api_settlement", False),
    # cp NULL: the band reads opening through the COALESCE.
    ("nhl_high_opening_only", "kalshi", "hockey", NHL_KEY, "Jack Hughes: 1+", None, 0.6417, "box_score", False),
    # cp below the band, opening above it: the band reads cp, so it STAYS.
    ("nhl_low_cp_high_opening", "kalshi", "hockey", NHL_KEY, "Kirill Kaprizov: 1+", 0.3119, 0.7023, "api_settlement", True),
    # NHL honest low band: stays.
    ("nhl_low_api", "kalshi", "hockey", NHL_KEY, "Connor Bedard: 1+", 0.2137, 0.2137, "api_settlement", False),
    ("nhl_low_box", "kalshi", "hockey", NHL_KEY, "Matthew Tkachuk: 1+", 0.4499, 0.4499, "box_score", True),
    # NHL non-threshold Kalshi outcome in the high band: not a prop threshold, stays.
    ("nhl_non_threshold", "kalshi", "hockey", NHL_KEY, "Yes", 0.6611, 0.6611, "api_settlement", True),
    # Polymarket threshold-shaped name in the high band: rule is Kalshi-only, stays.
    ("poly_nhl_threshold_shape", "polymarket", "hockey", NHL_KEY, "Auston Matthews: 1+", 0.6521, 0.6521, "api_settlement", True),
    # Non-NHL control: below 0.90 stays; >= 0.90 is the general degenerate band.
    ("mlb_mid_threshold", "kalshi", "baseball", MLB_KEY, "Aaron Judge: 2+", 0.6233, 0.6233, "box_score", True),
    ("mlb_degenerate", "kalshi", "baseball", MLB_KEY, "Aaron Judge: 4+", 0.9512, 0.9512, "box_score", False),
    ("poly_mlb", "polymarket", "baseball", MLB_KEY, "Yes", 0.6044, 0.6044, "api_settlement", True),
]

EXCLUDED = {"nhl_high_api", "nhl_high_box", "nhl_edge_050", "nhl_high_opening_only", "mlb_degenerate"}


class _RecordingSession:
    """Delegates to a real session and keeps the rows the impl's statement returned."""

    def __init__(self, session):
        self._session = session
        self.rows: list | None = None

    async def execute(self, *args, **kwargs):
        result = await self._session.execute(*args, **kwargs)
        rows = result.all()
        self.rows = rows

        class _Replay:
            def all(self_inner):
                return rows

        return _Replay()


async def _fair_fight_rows(session) -> Counter:
    from app.tasks.precompute_calibration import _query_futures_fair_fight_impl

    rec = _RecordingSession(session)
    await _query_futures_fair_fight_impl(rec)
    assert rec.rows is not None, "the impl never executed its statement"
    return Counter(
        (r.source, r.category, round(float(r.prob), 4), bool(r.is_winner)) for r in rec.rows
    )


def _key(spec) -> tuple:
    _label, source, category, _k, _name, cp, opening, _rs, winner = spec
    prob = cp if cp is not None else opening
    return (source, category, round(prob, 4), winner)


async def _clear(session):
    ids = [MID_BASE + i for i in range(len(SPECIMENS))]
    await session.execute(
        text(
            "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
            "(SELECT id FROM futures_outcomes WHERE market_id = ANY(:ids))"
        ),
        {"ids": ids},
    )
    await session.execute(text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"), {"ids": ids})
    await session.execute(text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ids})
    await session.commit()


async def _seed(session):
    """One resolved market per specimen, so each carries its own category and key.

    ``futures_markets.category`` is NOT NULL with no server default; the cell key
    the fair fight reads is ``llm_sport_category``. Every Kalshi leg gets a real
    ``yes_bid`` snapshot so the liquidity predicate ADMITS it — the subject is the
    price-band rule, not the evidence rule. ``reading_count`` is NOT NULL.
    """
    for i, (label, source, category, key, name, cp, opening, rs, winner) in enumerate(SPECIMENS):
        mid = MID_BASE + i
        await session.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, mutually_exclusive, market_type, llm_sport_category, "
                "canonical_market_key, volume) VALUES "
                "(:id, :xid, :nm, :src, 'resolved', 'championship', false, 'binary', "
                ":cat, :key, 100)"
            ),
            {"id": mid, "xid": f"test-1089-{label}", "nm": f"market-1089-{label}",
             "src": source, "cat": category, "key": key},
        )
        oid = mid * 10
        await session.execute(
            text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                "opening_probability, calibration_probability, is_winner, "
                "resolution_source, volume) VALUES "
                "(:id, :mid, :xid, :nm, :op, :cp, :win, :rs, 10)"
            ),
            {"id": oid, "mid": mid, "xid": f"test-1089-out-{label}", "nm": name,
             "op": opening, "cp": cp, "win": winner, "rs": rs},
        )
        price = cp if cp is not None else opening
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
                "reading_count, last_price, yes_bid, yes_ask) VALUES "
                "(:oid, 'test-1089', :p, 1, :p, :p, :p)"
            ),
            {"oid": oid, "p": price},
        )
    await session.commit()


async def _seeded_delta():
    """Rows the seed contributed: post-seed multiset minus the pre-seed baseline."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            await _clear(session)
            before = await _fair_fight_rows(session)
            await _seed(session)
            try:
                after = await _fair_fight_rows(session)
            finally:
                await _clear(session)
        return after - before
    finally:
        await engine.dispose()


async def test_nhl_high_band_rows_are_excluded_from_the_fair_fight():
    delta = await _seeded_delta()
    # NON-VACUITY FIRST: the seed reaches the query at all (keys pair, truth and
    # liquidity admit), or every "absent" assertion below proves nothing.
    kept = [s for s in SPECIMENS if s[0] not in EXCLUDED]
    assert all(delta[_key(s)] == 1 for s in kept), (
        f"seed did not reach the fair fight: {sorted(delta)}"
    )
    for spec in SPECIMENS:
        if spec[0] in EXCLUDED:
            assert delta[_key(spec)] == 0, f"{spec[0]} leaked into the source comparison"
    assert sum(delta.values()) == len(kept)


async def test_nhl_honest_low_band_stays():
    delta = await _seeded_delta()
    for label in ("nhl_low_api", "nhl_low_box", "nhl_low_cp_high_opening"):
        spec = next(s for s in SPECIMENS if s[0] == label)
        assert delta[_key(spec)] == 1, f"{label} (honest NHL band) was dropped"


async def test_non_nhl_and_non_threshold_controls():
    delta = await _seeded_delta()
    for label in ("mlb_mid_threshold", "poly_mlb", "nhl_non_threshold", "poly_nhl_threshold_shape"):
        spec = next(s for s in SPECIMENS if s[0] == label)
        assert delta[_key(spec)] == 1, f"control {label} was dropped"
    mlb_deg = next(s for s in SPECIMENS if s[0] == "mlb_degenerate")
    assert delta[_key(mlb_deg)] == 0, "general >= 0.90 band no longer excludes"
