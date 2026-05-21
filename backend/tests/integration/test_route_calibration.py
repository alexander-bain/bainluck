"""Contract tests for GET /api/calibration — public calibration endpoint.

Tests that the endpoint returns the expected response shape with the correct
top-level keys, nested structure, and field types — even when the DB is empty.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def clear_calibration_cache():
    """Keep the route's in-process cache from coupling contract tests."""
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0


def _mock_result(*, rows=(), scalar=None, one=None):
    result = MagicMock()
    result.all.return_value = list(rows)
    result.scalar.return_value = scalar
    if one is not None:
        result.one.return_value = one
    return result


def _bucket_row(
    *,
    bucket_idx=5,
    source="kalshi",
    category="politics",
    price_moved=True,
    n=4,
    winners=3,
    avg_prob=0.62,
    sum_prob=2.48,
    sum_sq_err=0.91,
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


def _event_bucket_row(
    *,
    bucket_idx=7,
    category="basketball_nba",
    n=10,
    winners=8,
    avg_prob=0.74,
    sum_prob=7.4,
    sum_sq_err=1.6,
):
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source="odds_api",
        category=category,
        n=n,
        winners=winners,
        avg_prob=avg_prob,
        sum_prob=sum_prob,
        sum_sq_err=sum_sq_err,
    )


def _closing_row(*, has_closing=3, needs_closing=2, total=5):
    return SimpleNamespace(
        has_closing=has_closing,
        needs_closing=needs_closing,
        total_completed=total,
    )


def _set_public_calibration_results(
    mock_db,
    *,
    futures_rows=(),
    event_rows=(),
    spreads_rows=(),
    totals_rows=(),
    total_markets=0,
    closing_row=None,
):
    mock_db.execute.side_effect = [
        _mock_result(rows=futures_rows),
        _mock_result(rows=event_rows),
        _mock_result(rows=spreads_rows),
        _mock_result(rows=totals_rows),
        _mock_result(scalar=total_markets),
        _mock_result(one=closing_row or _closing_row(has_closing=0, needs_closing=0, total=0)),
    ]


class TestCalibrationPublicEndpoint:
    """GET /api/calibration — public calibration data (cached 1h)."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/calibration")
        assert resp.status_code == 200

    async def test_no_auth_required(self, client):
        """Public endpoint — no secret or auth header needed."""
        resp = await client.get("/api/calibration")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body

    async def test_has_buckets_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "buckets" in body
        assert isinstance(body["buckets"], list)

    async def test_has_closing_line_coverage_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "closing_line_coverage" in body
        assert isinstance(body["closing_line_coverage"], dict)

    async def test_has_total_outcomes_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "total_outcomes" in body
        assert isinstance(body["total_outcomes"], int)
        assert body["total_outcomes"] >= 0

    async def test_has_total_markets_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "total_markets" in body

    async def test_has_total_winners_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "total_winners" in body
        assert isinstance(body["total_winners"], int)
        assert body["total_winners"] >= 0

    async def test_has_generated_at_key(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        assert "generated_at" in body
        assert isinstance(body["generated_at"], str)
        assert "T" in body["generated_at"]

    async def test_bust_parameter_accepted(self, client):
        """bust=1 bypasses cache — should still return 200."""
        resp = await client.get("/api/calibration?bust=1")
        assert resp.status_code == 200
        body = resp.json()
        assert "buckets" in body

    async def test_closing_line_coverage_structure(self, client):
        resp = await client.get("/api/calibration")
        body = resp.json()
        coverage = body["closing_line_coverage"]
        assert "has_closing" in coverage
        assert "needs_closing" in coverage
        assert "total" in coverage

    async def test_full_top_level_contract(self, client, mock_db):
        _set_public_calibration_results(mock_db)

        resp = await client.get("/api/calibration?bust=1")
        assert resp.status_code == 200
        body = resp.json()

        assert set(body) == {
            "closing_line_coverage",
            "buckets",
            "total_markets",
            "total_outcomes",
            "total_winners",
            "mce_ci_lower",
            "mce_ci_upper",
            "mce_closing_line",
            "mce_opening_price",
            "generated_at",
        }

    async def test_invalid_bust_parameter_returns_422(self, client, mock_db):
        resp = await client.get("/api/calibration?bust=abc")

        assert resp.status_code == 422
        mock_db.execute.assert_not_called()

    async def test_bust_zero_uses_cached_response(self, client, mock_db):
        _set_public_calibration_results(
            mock_db,
            futures_rows=[_bucket_row(n=2, winners=1, avg_prob=0.55, sum_prob=1.1)],
            total_markets=3,
        )
        first_resp = await client.get("/api/calibration?bust=1")
        assert first_resp.status_code == 200
        first_body = first_resp.json()

        mock_db.execute.reset_mock()
        second_resp = await client.get("/api/calibration")

        assert second_resp.status_code == 200
        assert second_resp.json() == first_body
        mock_db.execute.assert_not_called()

    async def test_bust_one_bypasses_cached_response(self, client, mock_db):
        _set_public_calibration_results(
            mock_db,
            futures_rows=[_bucket_row(n=2, winners=1, avg_prob=0.55, sum_prob=1.1)],
            total_markets=3,
        )
        first_resp = await client.get("/api/calibration?bust=1")
        assert first_resp.status_code == 200

        _set_public_calibration_results(
            mock_db,
            futures_rows=[_bucket_row(n=5, winners=4, avg_prob=0.7, sum_prob=3.5)],
            total_markets=9,
        )
        second_resp = await client.get("/api/calibration?bust=1")
        body = second_resp.json()

        assert second_resp.status_code == 200
        assert body["total_markets"] == 9
        assert body["total_outcomes"] == 5


class TestCalibrationBucketShape:
    """Each bucket object should have the required fields."""

    async def test_bucket_fields_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        required_fields = {"bucket_idx", "source", "category", "n", "winners", "avg_prob"}
        for bucket in body["buckets"]:
            missing = required_fields - set(bucket.keys())
            assert not missing, f"Bucket missing fields: {missing}"

    async def test_bucket_idx_is_int_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["bucket_idx"], int)
            assert 0 <= bucket["bucket_idx"] <= 9

    async def test_bucket_source_is_string_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["source"], str)

    async def test_bucket_category_is_string_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["category"], str)

    async def test_bucket_n_is_positive_int_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["n"], int)
            assert bucket["n"] >= 0

    async def test_bucket_winners_is_int_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["winners"], int)
            assert bucket["winners"] >= 0

    async def test_bucket_avg_prob_is_float_if_present(self, client):
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body["buckets"]:
            assert isinstance(bucket["avg_prob"], (int, float))
            assert 0.0 <= bucket["avg_prob"] <= 1.0

    async def test_empty_db_returns_empty_buckets(self, client):
        """With no resolved markets, buckets list should be empty."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        # Mock DB returns empty results, so buckets should be empty
        assert body["buckets"] == []
        assert body["total_outcomes"] == 0

    async def test_explicit_empty_db_response_values(self, client, mock_db):
        """Empty mocked rows should produce concrete zero/null values."""
        _set_public_calibration_results(
            mock_db,
            total_markets=0,
            closing_row=_closing_row(has_closing=0, needs_closing=0, total=0),
        )

        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()

        assert body["buckets"] == []
        assert body["total_markets"] == 0
        assert body["total_outcomes"] == 0
        assert body["total_winners"] == 0
        assert body["mce_ci_lower"] == 0.0
        assert body["mce_ci_upper"] == 0.0
        assert body["mce_closing_line"] is None
        assert body["mce_opening_price"] is None
        assert body["closing_line_coverage"] == {
            "has_closing": 0,
            "needs_closing": 0,
            "total": 0,
        }

    async def test_populated_response_combines_futures_and_event_buckets(
        self,
        client,
        mock_db,
    ):
        _set_public_calibration_results(
            mock_db,
            futures_rows=[
                _bucket_row(
                    bucket_idx=6,
                    source="kalshi",
                    category="politics",
                    price_moved=True,
                    n=4,
                    winners=3,
                    avg_prob=0.62,
                    sum_prob=2.48,
                    sum_sq_err=0.91,
                ),
                _bucket_row(
                    bucket_idx=4,
                    source="polymarket",
                    category="tech",
                    price_moved=False,
                    n=5,
                    winners=2,
                    avg_prob=0.42,
                    sum_prob=2.1,
                    sum_sq_err=1.2,
                ),
            ],
            event_rows=[
                _event_bucket_row(
                    bucket_idx=7,
                    category="basketball_nba",
                    n=10,
                    winners=8,
                    avg_prob=0.74,
                    sum_prob=7.4,
                    sum_sq_err=1.6,
                ),
            ],
            total_markets=7,
            closing_row=_closing_row(has_closing=3, needs_closing=2, total=5),
        )

        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()

        assert resp.status_code == 200
        assert body["total_markets"] == 7
        assert body["total_outcomes"] == 19
        assert body["total_winners"] == 13
        assert body["closing_line_coverage"] == {
            "has_closing": 3,
            "needs_closing": 2,
            "total": 5,
        }
        assert body["mce_closing_line"] == 13.0
        assert body["mce_opening_price"] == 2.0

        buckets = body["buckets"]
        assert len(buckets) == 3
        assert buckets[0] == {
            "bucket_idx": 6,
            "source": "kalshi",
            "category": "politics",
            "price_moved": True,
            "n": 4,
            "winners": 3,
            "avg_prob": 0.62,
            "sum_prob": 2.48,
            "sum_sq_err": 0.91,
            "ci_lower": 0.3006,
            "ci_upper": 0.9544,
        }
        assert buckets[1]["price_moved"] is False
        assert buckets[2]["source"] == "odds_api"
        assert buckets[2]["price_moved"] is None


class TestCalibrationBucketValueRanges:
    """Validate bucket value ranges follow mathematical constraints.

    All tests use bust=1 to bypass the in-process cache and ensure
    fresh responses from the mock DB.
    """

    async def test_bucket_idx_range_0_to_9(self, client):
        """Bucket indices should be 0-9 (deciles of probability space)."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert 0 <= bucket["bucket_idx"] <= 9, (
                f"bucket_idx {bucket['bucket_idx']} out of 0-9 range"
            )

    async def test_avg_prob_in_0_to_1(self, client):
        """Average probability must be between 0 and 1."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert 0.0 <= bucket["avg_prob"] <= 1.0, (
                f"avg_prob {bucket['avg_prob']} out of 0-1 range"
            )

    async def test_winners_lte_count(self, client):
        """Winners cannot exceed total count in a bucket."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert bucket["winners"] <= bucket["n"], (
                f"winners ({bucket['winners']}) > n ({bucket['n']})"
            )

    async def test_sum_sq_err_is_non_negative(self, client):
        """Sum of squared errors must be non-negative."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert "sum_sq_err" in bucket
            assert bucket["sum_sq_err"] >= 0, (
                f"sum_sq_err is negative: {bucket['sum_sq_err']}"
            )

    async def test_sum_prob_is_non_negative(self, client):
        """Sum of probabilities must be non-negative."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert "sum_prob" in bucket
            assert bucket["sum_prob"] >= 0, (
                f"sum_prob is negative: {bucket['sum_prob']}"
            )

    async def test_price_moved_field_present(self, client):
        """Each bucket should have a price_moved field (nullable bool)."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        for bucket in body.get("buckets", []):
            assert "price_moved" in bucket

    async def test_total_outcomes_equals_bucket_sum(self, client):
        """Total outcomes should equal sum of all bucket counts."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        bucket_sum = sum(b["n"] for b in body.get("buckets", []))
        assert body.get("total_outcomes", 0) == bucket_sum

    async def test_total_winners_equals_bucket_winner_sum(self, client):
        """Total winners should equal sum of all bucket winners."""
        resp = await client.get("/api/calibration?bust=1")
        body = resp.json()
        winner_sum = sum(b["winners"] for b in body.get("buckets", []))
        assert body.get("total_winners", 0) == winner_sum
