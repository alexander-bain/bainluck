"""#13261 Row 3: Admin analytics acquisition source/medium, shared_link_open,
first-visit landing paths (query-stripped), and Day-2 / Day-7 cohort retention.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.admin_analytics import (
    _clean_landing_path,
    _split_source_medium,
    _summarize_cohort_retention,
    analytics_acquisition,
    analytics_retention,
)


def test_clean_landing_path_strips_query_and_fragment() -> None:
    assert _clean_landing_path("/collections/machinery-fed-and-macro?utm_source=x&token=secret#top") == "/collections/machinery-fed-and-macro"
    assert _clean_landing_path("/events/15350374?ref=abc") == "/events/15350374"
    assert _clean_landing_path("events/15350374") == "/events/15350374"
    assert _clean_landing_path("(not set)") == "(not set)"
    assert _clean_landing_path("") == "(not set)"
    assert _clean_landing_path("?utm_source=sms") == "/"


def test_split_source_medium_handles_standard_and_direct() -> None:
    assert _split_source_medium("google / organic") == ("google", "organic")
    assert _split_source_medium("(direct) / (none)") == ("(direct)", "(none)")
    assert _split_source_medium("messages/share") == ("messages", "share")
    assert _split_source_medium("") == ("(direct)", "(none)")


def test_summarize_cohort_retention_computes_d2_and_d7_only_for_mature_cohorts() -> None:
    today = date(2026, 11, 20)
    rows = [
        # 7 days old -> mature for both Day 2 (+1d) and Day 7 (+6d)
        {"cohort": "2026-11-13", "cohortNthDay": "0000", "cohortActiveUsers": "20", "cohortTotalUsers": "20"},
        {"cohort": "2026-11-13", "cohortNthDay": "0001", "cohortActiveUsers": "6", "cohortTotalUsers": "20"},
        {"cohort": "2026-11-13", "cohortNthDay": "0006", "cohortActiveUsers": "4", "cohortTotalUsers": "20"},
        # 3 days old -> mature for Day 2 (+1d), NOT mature for Day 7 (+6d)
        {"cohort": "2026-11-17", "cohortNthDay": "0000", "cohortActiveUsers": "10", "cohortTotalUsers": "10"},
        {"cohort": "2026-11-17", "cohortNthDay": "0001", "cohortActiveUsers": "3", "cohortTotalUsers": "10"},
        # Today -> immature for both Day 2 and Day 7 (must NOT dilute denominators)
        {"cohort": "2026-11-20", "cohortNthDay": "0000", "cohortActiveUsers": "50", "cohortTotalUsers": "50"},
    ]

    summary = _summarize_cohort_retention(rows, today=today)
    # Day 2 denominator = 20 + 10 = 30; users = 6 + 3 = 9 -> 30.0%
    assert summary["day2CohortBase"] == 30
    assert summary["day2Users"] == 9
    assert summary["day2RetentionRate"] == 30.0
    # Day 7 denominator = 20 only; users = 4 -> 20.0%
    assert summary["day7CohortBase"] == 20
    assert summary["day7Users"] == 4
    assert summary["day7RetentionRate"] == 20.0

    by_date = {c["cohortDate"]: c for c in summary["cohorts"]}
    assert by_date["2026-11-13"]["day2Eligible"] is True
    assert by_date["2026-11-13"]["day7Eligible"] is True
    assert by_date["2026-11-17"]["day2Eligible"] is True
    assert by_date["2026-11-17"]["day7Eligible"] is False
    assert by_date["2026-11-17"]["day7Rate"] is None
    assert by_date["2026-11-20"]["day2Eligible"] is False
    assert by_date["2026-11-20"]["day2Rate"] is None


@pytest.mark.asyncio
async def test_analytics_acquisition_returns_sources_shared_links_and_first_landings() -> None:
    fake_req = SimpleNamespace(headers={})

    def _fake_run_report(*, dimensions, metrics, start_date, end_date="today", limit=100, order_by_metric=None):
        assert start_date == "14daysAgo"
        if dimensions == ["sessionSourceMedium"]:
            return [
                {"sessionSourceMedium": "messages / share", "newUsers": "14", "activeUsers": "18", "sessions": "22", "engagedSessions": "19"},
                {"sessionSourceMedium": "(direct) / (none)", "newUsers": "9", "activeUsers": "15", "sessions": "25", "engagedSessions": "20"},
            ]
        if dimensions == ["eventName", "sessionSourceMedium"]:
            return [
                {"eventName": "shared_link_open", "sessionSourceMedium": "messages / share", "eventCount": "16", "totalUsers": "12"},
                {"eventName": "page_view", "sessionSourceMedium": "(direct) / (none)", "eventCount": "200", "totalUsers": "30"},
            ]
        if dimensions == ["landingPagePlusQueryString", "newVsReturning"]:
            return [
                {"landingPagePlusQueryString": "/collections/machinery-fed-and-macro?utm_source=messages&token=xyz", "newVsReturning": "new", "sessions": "11", "activeUsers": "10", "engagedSessions": "9"},
                {"landingPagePlusQueryString": "/collections/machinery-fed-and-macro?utm_source=sms", "newVsReturning": "new", "sessions": "4", "activeUsers": "4", "engagedSessions": "3"},
                {"landingPagePlusQueryString": "/events/15350374", "newVsReturning": "returning", "sessions": "50", "activeUsers": "30", "engagedSessions": "45"},
                {"landingPagePlusQueryString": "/", "newVsReturning": "new", "sessions": "8", "activeUsers": "8", "engagedSessions": "6"},
            ]
        if dimensions == ["pagePath", "eventName"]:
            return [
                {"pagePath": "/collections/machinery-fed-and-macro", "eventName": "first_visit", "eventCount": "14", "totalUsers": "14"},
                {"pagePath": "/", "eventName": "session_open", "eventCount": "30", "totalUsers": "20"},
                {"pagePath": "/sports", "eventName": "scroll_depth", "eventCount": "12", "totalUsers": "10"},
            ]
        return []

    with (
        patch("app.routes.admin_analytics._check_admin_secret"),
        patch("app.routes.admin_analytics._cache_get", new=AsyncMock(return_value=None)),
        patch("app.routes.admin_analytics._cache_set", new=AsyncMock()),
        patch("app.services.ga4_api.run_report", side_effect=_fake_run_report),
    ):
        data = await analytics_acquisition(fake_req, secret="s", period="14d")

    assert data["period"] == "14d"
    assert data["summary"]["totalNewUsers"] == 23
    assert data["summary"]["sharedLinkOpens"] == 16
    assert data["summary"]["sharedLinkUsers"] == 12
    assert data["sources"][0]["sourceMedium"] == "messages / share"
    assert len(data["sharedLinks"]["bySourceMedium"]) == 1
    assert data["sharedLinks"]["bySourceMedium"][0]["events"] == 16

    # Query params stripped & merged, returning-user landing excluded
    paths = {r["path"]: r for r in data["firstVisitLandingPaths"]}
    assert "/collections/machinery-fed-and-macro" in paths
    assert paths["/collections/machinery-fed-and-macro"]["sessions"] == 15
    assert paths["/collections/machinery-fed-and-macro"]["section"] == "collections"
    assert "/events/15350374" not in paths
    assert all("?" not in p for p in paths)

    sec_map = {s["section"]: s["sessions"] for s in data["firstLandingBySection"]}
    assert sec_map["collections"] == 15
    assert sec_map["discover"] == 8

    ev_names = {e["eventName"] for e in data["firstVisitEvents"]}
    assert ev_names == {"first_visit", "session_open"}


@pytest.mark.asyncio
async def test_analytics_retention_includes_d2_d7_cohorts_and_degrades_safely() -> None:
    fake_req = SimpleNamespace(headers={})

    cohort_rows = [
        {"cohort": "2026-11-10", "cohortNthDay": "0000", "cohortActiveUsers": "10", "cohortTotalUsers": "10"},
        {"cohort": "2026-11-10", "cohortNthDay": "0001", "cohortActiveUsers": "4", "cohortTotalUsers": "10"},
        {"cohort": "2026-11-10", "cohortNthDay": "0006", "cohortActiveUsers": "2", "cohortTotalUsers": "10"},
    ]

    with (
        patch("app.routes.admin_analytics._check_admin_secret"),
        patch("app.routes.admin_analytics._cache_get", new=AsyncMock(return_value=None)),
        patch("app.routes.admin_analytics._cache_set", new=AsyncMock()),
        patch(
            "app.services.ga4_api.get_user_retention",
            return_value=[
                {"date": "20261118", "newVsReturning": "new", "activeUsers": "10", "sessions": "10"},
                {"date": "20261118", "newVsReturning": "returning", "activeUsers": "5", "sessions": "8"},
            ],
        ),
        patch("app.services.ga4_api.get_cohort_retention", return_value=cohort_rows),
        patch(
            "app.services.ga4_api.run_report",
            return_value=[{"eventName": "return_visit", "eventCount": "12", "totalUsers": "7"}],
        ),
    ):
        res = await analytics_retention(fake_req, secret="s", period="14d")

    assert res["summary"]["totalNewUsers"] == 10
    assert res["summary"]["totalReturningUsers"] == 5
    assert res["summary"]["day2RetentionRate"] == 40.0
    assert res["summary"]["day7RetentionRate"] == 20.0
    assert res["summary"]["returnVisitEvents"] == 12
    assert res["summary"]["returnVisitUsers"] == 7
    assert len(res["cohorts"]) == 1

    # Graceful fallback when GA4 cohort query raises
    with (
        patch("app.routes.admin_analytics._check_admin_secret"),
        patch("app.routes.admin_analytics._cache_get", new=AsyncMock(return_value=None)),
        patch("app.routes.admin_analytics._cache_set", new=AsyncMock()),
        patch("app.services.ga4_api.get_user_retention", return_value=[]),
        patch("app.services.ga4_api.get_cohort_retention", side_effect=RuntimeError("GA4 cohort unavailable")),
        patch("app.services.ga4_api.run_report", side_effect=RuntimeError("GA4 event unavailable")),
    ):
        fallback = await analytics_retention(fake_req, secret="s", period="14d")

    assert fallback["cohorts"] == []
    assert fallback["summary"]["day2RetentionRate"] is None
    assert fallback["summary"]["day7RetentionRate"] is None
    assert fallback["summary"]["returnVisitEvents"] == 0
