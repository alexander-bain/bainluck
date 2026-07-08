"""Tests for position-normalized rank-bucketed engagement (#142/RANK-2)."""

from types import SimpleNamespace

import pytest

from app.routes.admin_engagement import (
    _ENGAGEMENT_RANK_BUCKETS,
    _rank_bucketed_engagement,
)


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """Returns one aggregate result per execute() call."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _statement):
        return _AllResult(self._rows)


@pytest.mark.asyncio
async def test_rates_are_action_over_impressions_per_bucket():
    rows = [
        SimpleNamespace(bucket="01-03", impressions=100, opens=40, dismisses=10, likes=5),
        SimpleNamespace(bucket="11-20", impressions=50, opens=5, dismisses=20, likes=1),
    ]
    result = await _rank_bucketed_engagement(_Session(rows), days=7, surface=None)

    by_bucket = {r["rank_bucket"]: r for r in result}
    # every bucket present in canonical order, missing ones zero-filled
    assert [r["rank_bucket"] for r in result] == _ENGAGEMENT_RANK_BUCKETS

    top = by_bucket["01-03"]
    assert top["open_rate"] == 0.40
    assert top["dismiss_rate"] == 0.10
    assert top["like_rate"] == 0.05

    mid = by_bucket["11-20"]
    assert mid["open_rate"] == 0.10
    assert mid["dismiss_rate"] == 0.40

    # no impressions => rates are None (not a divide-by-zero or misleading 0)
    empty = by_bucket["51+"]
    assert empty["impressions"] == 0
    assert empty["open_rate"] is None


@pytest.mark.asyncio
async def test_position_confound_is_visible():
    # Raw opens are higher at the top, but the NORMALIZED open_rate can be lower
    # there — exactly the confound this section exists to expose.
    rows = [
        SimpleNamespace(bucket="01-03", impressions=1000, opens=50, dismisses=5, likes=2),
        SimpleNamespace(bucket="21-50", impressions=100, opens=20, dismisses=1, likes=1),
    ]
    result = await _rank_bucketed_engagement(_Session(rows), days=30, surface=None)
    by_bucket = {r["rank_bucket"]: r for r in result}
    assert by_bucket["01-03"]["opens"] > by_bucket["21-50"]["opens"]  # raw counts
    assert by_bucket["01-03"]["open_rate"] < by_bucket["21-50"]["open_rate"]  # rate
