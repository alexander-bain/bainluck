from types import SimpleNamespace

import pytest

from app.routes import calibration
from app.tasks import precompute_calibration


@pytest.fixture(autouse=True)
def _disable_sample_gate(monkeypatch):
    # Queue #257 Item 1: the route delegates to the shared
    # compute_calibration_payload, which applies the #997 min-sample gate to
    # by_sport/by_category. These fake-DB shape tests use small synthetic N, so
    # disable the gate (it is covered by test_calibration_min_sample_gate.py).
    monkeypatch.setattr(
        precompute_calibration, "_get_min_category_outcomes", lambda *_a, **_k: 0
    )


class _FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, one_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._one_value = one_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value

    def one(self):
        return self._one_value


class _FakeDB:
    def __init__(self, *, futures_rows=None, events_rows=None, spreads_rows=None, totals_rows=None, total_markets=0, closing_row=None):
        self.statements = []
        self._results = [
            _FakeResult(rows=futures_rows or []),
            _FakeResult(rows=events_rows or []),
            _FakeResult(rows=spreads_rows or []),
            _FakeResult(rows=totals_rows or []),
            _FakeResult(scalar_value=total_markets),
            _FakeResult(
                one_value=closing_row
                or SimpleNamespace(
                    has_closing=0,
                    needs_closing=0,
                    total_completed=0,
                )
            ),
        ]

    async def execute(self, statement):
        self.statements.append(statement)
        # Queue #257 Item 1: the route now delegates to the shared
        # compute_calibration_payload, which runs more queries than the old
        # route path (void / heuristic / soccer-2way / date_range). Tolerate
        # the extra reads with an empty result so these fake-DB tests exercise
        # the shared payload without hand-seeding every query.
        if not self._results:
            return _FakeResult()
        return self._results.pop(0)


def _bucket_row(
    *,
    bucket_idx,
    source,
    category,
    price_moved=None,
    n,
    winners,
    avg_prob,
    sum_prob,
    sum_sq_err,
):
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source=source,
        category=category,
        price_moved=price_moved,
        n=n,
        winners=winners,
        avg_prob=avg_prob,
        sum_prob=sum_prob,
        sum_sq_err=sum_sq_err,
        # Queue #257 Item 1: the shared compute_calibration_payload reads the
        # per-run transparency counts off the first futures row (CROSS JOIN
        # liq_summary). Real rows always carry them; seed 0 so a fake futures
        # row exercises the full shared path instead of AttributeError-ing.
        kalshi_included=0,
        kalshi_excluded=0,
        poly_placeholder_excluded=0,
        poly_included=0,
        poly_never_traded_total=0,
        poly_never_traded_in_curve=0,
        both_false_excluded=0,
        both_winner_excluded=0,
        golf_placeholder_excluded=0,
        mex_normalized_outcomes=0,
        esports_bundle_excluded=0,
        kalshi_prop_threshold_excluded=0,
        weather_wide_spread_excluded=0,
    )


@pytest.mark.asyncio
async def test_public_calibration_uses_is_winner_for_market_resolution():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "has_winner >= 1" in futures_sql
    assert "fo.is_winner AS is_winner" in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_uses_is_winner_for_resolution():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "fo.is_winner AS is_winner" in futures_sql
    assert "has_winner >= 1" in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_excludes_guessed_and_price_derived_resolutions():
    # Queue #261 Item 1: the population moved from a scattered NOT-IN denylist to
    # the resolution-authority calibration-truth ELIGIBILITY allowlist. Guessed
    # resolutions are excluded because they are not eligible (never named in the
    # allowlist), and price-derived truth (clean_resolution / settlement_sync) is
    # now excluded too — a terminal price cannot grade its own forecast.
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    # The eligibility allowlist is present, keyed on independent authority.
    assert "fo.resolution_source IN ('api_settlement'" in futures_sql or (
        "resolution_source IN (" in futures_sql and "'api_settlement'" in futures_sql
    )
    # Guess-family and price-derived sources must NOT appear in the population
    # filter (they are excluded by omission from the allowlist).
    assert "'pass2_guess'" not in futures_sql
    assert "'clean_resolution'" not in futures_sql
    assert "'settlement_sync'" not in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_classifies_only_non_null_changed_prices_as_closing_line():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    # adj_opening_probability derives from cal_prob with an opening fallback.
    # Queue #157 wraps this base in a mex-normalization CASE (cp / per-market
    # sum for inflated single-winner partitions), so the raw COALESCE now lives
    # in the ELSE branch and the alias follows the END.
    assert "COALESCE(fo.calibration_probability, fo.opening_probability)" in futures_sql
    assert "END AS adj_opening_probability" in futures_sql
    # Queue #257 Item 1: the normalization divisor moved from ranked_outcomes into
    # the completeness-gated ``normalized`` CTE (cp / per-market sum only for
    # COMPLETE fields), so the division now reads off the carried raw_cp/mnm_cp_sum.
    assert "ro.raw_cp / ro.mnm_cp_sum" in futures_sql  # the normalization divisor
    # price_moved still keys off the raw cal_prob vs opening comparison, NOT the
    # normalized value — the closing-line classification is unchanged.
    assert "fo.calibration_probability IS NOT NULL" in futures_sql
    assert "fo.calibration_probability IS DISTINCT FROM fo.opening_probability" in futures_sql
    assert "COALESCE(fo.calibration_probability, fo.opening_probability) IS DISTINCT FROM" not in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_keeps_grouped_markets_multi_outcome_only_when_eligible():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "(cv.is_grouped OR cv.eligible >= 3) AS is_multi" in futures_sql
    assert "WHERE is_multi AND eligible >= 3" in futures_sql
    assert "HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)" in futures_sql
    assert "WHEN ro.is_multi" in futures_sql
    assert "ELSE ro.rn = 1" in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_builds_bucket_output_shape_from_futures_and_events():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB(
        futures_rows=[
            _bucket_row(
                bucket_idx=2,
                source="kalshi",
                category="politics",
                price_moved=True,
                n=4,
                winners=1,
                avg_prob=0.27555,
                sum_prob=1.1022,
                sum_sq_err=0.81234,
            ),
            _bucket_row(
                bucket_idx=6,
                source="polymarket",
                category="entertainment",
                price_moved=False,
                n=5,
                winners=3,
                avg_prob=0.61,
                sum_prob=3.05,
                sum_sq_err=1.23456,
            ),
        ],
        events_rows=[
            _bucket_row(
                bucket_idx=7,
                source="odds_api",
                category="basketball_nba",
                n=2,
                winners=2,
                avg_prob=0.74,
                sum_prob=1.48,
                sum_sq_err=0.1352,
            )
        ],
        spreads_rows=[
            _bucket_row(
                bucket_idx=4,
                source="odds_api_spreads",
                category="basketball_nba",
                n=10,
                winners=5,
                avg_prob=0.524,
                sum_prob=5.24,
                sum_sq_err=2.5,
            )
        ],
        totals_rows=[
            _bucket_row(
                bucket_idx=4,
                source="odds_api_totals",
                category="basketball_nba",
                n=8,
                winners=4,
                avg_prob=0.524,
                sum_prob=4.192,
                sum_sq_err=2.0,
            )
        ],
        total_markets=9,
        closing_row=SimpleNamespace(
            has_closing=7,
            needs_closing=3,
            total_completed=10,
        ),
    )

    response = await calibration.public_calibration(db=db, bust=1)

    assert response["total_markets"] == 9
    assert response["total_outcomes"] == 29  # 4+5 futures + 2 events + 10 spreads + 8 totals
    assert response["total_winners"] == 15  # 1+3 futures + 2 events + 5 spreads + 4 totals
    assert response["closing_line_coverage"] == {
        "has_closing": 7,
        "needs_closing": 3,
        "total": 10,
    }
    assert response["mce_closing_line"] == 2.56
    assert response["mce_opening_price"] == 1.0

    assert response["buckets"] == [
        {
            "bucket_idx": 2,
            "source": "kalshi",
            "category": "politics",
            "price_moved": True,
            "n": 4,
            "winners": 1,
            "avg_prob": 0.2756,
            "sum_prob": 1.1022,
            "sum_sq_err": 0.8123,
            "ci_lower": 0.0456,
            "ci_upper": 0.6994,
        },
        {
            "bucket_idx": 6,
            "source": "polymarket",
            "category": "entertainment",
            "price_moved": False,
            "n": 5,
            "winners": 3,
            "avg_prob": 0.61,
            "sum_prob": 3.05,
            "sum_sq_err": 1.2346,
            "ci_lower": 0.2307,
            "ci_upper": 0.8824,
        },
        {
            "bucket_idx": 7,
            "source": "odds_api",
            "category": "basketball_nba",
            "price_moved": None,
            "n": 2,
            "winners": 2,
            "avg_prob": 0.74,
            "sum_prob": 1.48,
            "sum_sq_err": 0.1352,
            "ci_lower": 0.3424,
            "ci_upper": 1.0,
        },
        {
            "bucket_idx": 4,
            "source": "odds_api_spreads",
            "category": "basketball_nba",
            "price_moved": None,
            "n": 10,
            "winners": 5,
            "avg_prob": 0.524,
            "sum_prob": 5.24,
            "sum_sq_err": 2.5,
            "ci_lower": 0.2366,
            "ci_upper": 0.7634,
        },
        {
            "bucket_idx": 4,
            "source": "odds_api_totals",
            "category": "basketball_nba",
            "price_moved": None,
            "n": 8,
            "winners": 4,
            "avg_prob": 0.524,
            "sum_prob": 4.192,
            "sum_sq_err": 2.0,
            "ci_lower": 0.2152,
            "ci_upper": 0.7848,
        },
    ]

    # Verify spreads_summary and totals_summary sections
    spreads = response["spreads_summary"]
    assert spreads["outcomes"] == 10
    assert spreads["winners"] == 5
    assert spreads["mce"] is not None
    assert len(spreads["by_sport"]) == 1
    assert spreads["by_sport"][0]["sport"] == "basketball_nba"
    assert spreads["by_sport"][0]["outcomes"] == 10

    totals = response["totals_summary"]
    assert totals["outcomes"] == 8
    assert totals["winners"] == 4
    assert totals["mce"] is not None
    assert len(totals["by_sport"]) == 1
    assert totals["by_sport"][0]["sport"] == "basketball_nba"
    assert totals["by_sport"][0]["outcomes"] == 8
