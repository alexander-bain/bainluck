from types import SimpleNamespace

import pytest

from app.routes import calibration


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
    def __init__(self, *, futures_rows=None, events_rows=None, total_markets=0, closing_row=None):
        self.statements = []
        self._results = [
            _FakeResult(rows=futures_rows or []),
            _FakeResult(rows=events_rows or []),
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
    )


@pytest.mark.asyncio
async def test_public_calibration_requires_settled_current_probability():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "COUNT(*) FILTER (WHERE fo.current_probability >= 0.95) AS near_one" in futures_sql
    assert "COUNT(*) FILTER (WHERE fo.current_probability <= 0.05) AS near_zero" in futures_sql
    assert "AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)" in futures_sql
    assert "fo.is_winner IS NOT NULL" not in futures_sql


@pytest.mark.asyncio
async def test_public_calibration_falls_back_to_settled_price_for_winner_status():
    calibration._cache = {"data": None, "timestamp": 0}
    db = _FakeDB()

    await calibration.public_calibration(db=db, bust=1)

    futures_sql = str(db.statements[0])
    assert "(fo.is_winner = true OR fo.current_probability >= 0.95) AS is_winner" in futures_sql


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
        total_markets=9,
        closing_row=SimpleNamespace(
            has_closing=7,
            needs_closing=3,
            total_completed=10,
        ),
    )

    response = await calibration.public_calibration(db=db, bust=1)

    assert response["total_markets"] == 9
    assert response["total_outcomes"] == 11
    assert response["total_winners"] == 6
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
    ]
