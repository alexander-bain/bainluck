"""Contract tests for GET /api/calibration — public calibration endpoint.

Tests that the endpoint returns the expected response shape with the correct
top-level keys, nested structure, and field types — even when the DB is empty.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


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
