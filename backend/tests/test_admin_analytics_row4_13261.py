"""#13261 Row 4: Admin first-week onboarding funnel stages
(onboarding_start -> onboarding_step -> onboarding_complete / onboarding_skip).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.admin_analytics import _build_onboarding_funnel, analytics_funnel


def test_build_onboarding_funnel_rates_platforms_and_daily_trend() -> None:
    events = [
        {"eventName": "onboarding_start", "eventCount": "40", "totalUsers": "32"},
        {"eventName": "onboarding_step", "eventCount": "84", "totalUsers": "26"},
        {"eventName": "onboarding_complete", "eventCount": "20", "totalUsers": "20"},
        {"eventName": "onboarding_skip", "eventCount": "8", "totalUsers": "8"},
        {"eventName": "page_view", "eventCount": "500", "totalUsers": "100"},
    ]
    platforms = [
        {"platform": "web", "eventName": "onboarding_start", "eventCount": "22", "totalUsers": "20"},
        {"platform": "web", "eventName": "onboarding_complete", "eventCount": "12", "totalUsers": "12"},
        {"platform": "iOS", "eventName": "onboarding_start", "eventCount": "18", "totalUsers": "12"},
        {"platform": "iOS", "eventName": "onboarding_step", "eventCount": "30", "totalUsers": "10"},
        {"platform": "iOS", "eventName": "onboarding_complete", "eventCount": "8", "totalUsers": "8"},
        {"platform": "iOS", "eventName": "onboarding_skip", "eventCount": "4", "totalUsers": "4"},
    ]
    daily = [
        {"date": "20261119", "eventName": "onboarding_start", "eventCount": "15", "totalUsers": "14"},
        {"date": "20261119", "eventName": "onboarding_complete", "eventCount": "9", "totalUsers": "9"},
        {"date": "20261120", "eventName": "onboarding_start", "eventCount": "25", "totalUsers": "18"},
        {"date": "20261120", "eventName": "onboarding_skip", "eventCount": "5", "totalUsers": "5"},
    ]

    ob = _build_onboarding_funnel(events, platforms, daily)
    assert ob["summary"]["startedUsers"] == 32
    assert ob["summary"]["steppedUsers"] == 26
    assert ob["summary"]["completedUsers"] == 20
    assert ob["summary"]["skippedUsers"] == 8
    assert ob["summary"]["leftWithoutFinishingOrSkipping"] == 4
    assert ob["summary"]["completionRate"] == 62.5
    assert ob["summary"]["skipRate"] == 25.0

    # Blended bars compare Start, Complete, and Skip only (`step` lives per platform)
    by_stage = {s["stage"]: s for s in ob["stages"]}
    assert [s["stage"] for s in ob["stages"]] == ["start", "complete", "skip"]
    assert by_stage["start"]["eventName"] == "onboarding_start"
    assert by_stage["start"]["rateFromStart"] == 100.0
    assert by_stage["complete"]["rateFromStart"] == 62.5
    assert by_stage["skip"]["rateFromStart"] == 25.0

    plats = {p["platform"]: p for p in ob["byPlatform"]}
    assert plats["web"]["start"] == 20 and plats["web"]["complete"] == 12
    assert plats["ios"]["start"] == 12 and plats["ios"]["step"] == 10 and plats["ios"]["skip"] == 4
    assert len(ob["dailyTrend"]) == 2
    assert ob["dailyTrend"][0]["date"] == "20261119"
    assert ob["dailyTrend"][0]["complete"] == 9


def test_build_onboarding_funnel_handles_zero_starts_without_div_by_zero() -> None:
    ob = _build_onboarding_funnel([], [], [])
    assert ob["summary"]["startedUsers"] == 0
    assert ob["summary"]["leftWithoutFinishingOrSkipping"] == 0
    assert ob["summary"]["completionRate"] is None
    assert ob["summary"]["skipRate"] is None
    assert all(s["rateFromStart"] is None for s in ob["stages"])


@pytest.mark.asyncio
async def test_analytics_funnel_includes_onboarding_stages_for_14d() -> None:
    fake_req = SimpleNamespace(headers={})

    def _fake_run_report(*, dimensions, metrics, start_date, end_date="today", limit=100, order_by_metric=None):
        assert start_date == "14daysAgo"
        if dimensions == ["eventName"]:
            return [
                {"eventName": "session_open", "eventCount": "50", "totalUsers": "30"},
                {"eventName": "onboarding_start", "eventCount": "20", "totalUsers": "18"},
                {"eventName": "onboarding_step", "eventCount": "45", "totalUsers": "15"},
                {"eventName": "onboarding_complete", "eventCount": "12", "totalUsers": "12"},
                {"eventName": "onboarding_skip", "eventCount": "4", "totalUsers": "4"},
            ]
        if dimensions == ["platform", "eventName"]:
            return [
                {"platform": "web", "eventName": "onboarding_start", "eventCount": "12", "totalUsers": "10"},
                {"platform": "web", "eventName": "onboarding_complete", "eventCount": "7", "totalUsers": "7"},
                {"platform": "iOS", "eventName": "onboarding_start", "eventCount": "8", "totalUsers": "8"},
                {"platform": "iOS", "eventName": "onboarding_complete", "eventCount": "5", "totalUsers": "5"},
            ]
        if dimensions == ["date", "eventName"]:
            return [
                {"date": "20261120", "eventName": "onboarding_start", "eventCount": "20", "totalUsers": "18"},
            ]
        return []

    with (
        patch("app.routes.admin_analytics._check_admin_secret"),
        patch("app.routes.admin_analytics._cache_get", new=AsyncMock(return_value=None)),
        patch("app.routes.admin_analytics._cache_set", new=AsyncMock()),
        patch("app.services.ga4_api.run_report", side_effect=_fake_run_report),
    ):
        res = await analytics_funnel(fake_req, secret="s", period="14d")

    assert res["period"] == "14d"
    assert res["onboarding"]["summary"]["startedUsers"] == 18
    assert res["onboarding"]["summary"]["completedUsers"] == 12
    assert res["onboarding"]["summary"]["completionRate"] == 66.7
    assert res["onboarding"]["summary"]["skippedUsers"] == 4
    assert res["onboarding"]["summary"]["skipRate"] == 22.2
