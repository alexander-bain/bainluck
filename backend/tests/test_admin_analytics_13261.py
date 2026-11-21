"""#13261 Row 1: Admin analytics reads live event names, 14d window, platform split,
and proper page sections (events, search, collections, my_stuff, app_screen).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.admin_analytics import (
    _classify_funnel_stage,
    _classify_page_section,
    _is_discover_event,
    _normalize_analytics_platform,
    _period_to_start_date,
    analytics_discover,
    analytics_funnel,
    analytics_overview,
    analytics_pages,
    analytics_retention,
)


def test_period_to_start_date_supports_14d() -> None:
    assert _period_to_start_date("7d") == "7daysAgo"
    assert _period_to_start_date("14d") == "14daysAgo"
    assert _period_to_start_date("30d") == "30daysAgo"
    assert _period_to_start_date("90d") == "90daysAgo"
    assert _period_to_start_date("unknown") == "30daysAgo"


def test_live_event_names_classify_in_discover_and_funnel() -> None:
    # Live event names previously missed (causing 0 taps and 0 guesses)
    assert _is_discover_event("feed_card_action") is True
    assert _is_discover_event("feed_card_impression") is True
    assert _is_discover_event("prediction_submit") is True
    assert _is_discover_event("session_open") is True
    assert _is_discover_event("shared_link_open") is True

    assert _classify_funnel_stage("session_open") == "visit"
    assert _classify_funnel_stage("screen_view") == "visit"
    assert _classify_funnel_stage("feed_card_action") == "interact"
    assert _classify_funnel_stage("feed_card_impression") == "interact"
    assert _classify_funnel_stage("search_result_click") == "interact"
    assert _classify_funnel_stage("prediction_submit") == "guess"
    assert _classify_funnel_stage("prediction_make") == "guess"
    assert _classify_funnel_stage("higher_lower_play") == "guess"
    assert _classify_funnel_stage("sign_up") == "signup"


def test_platform_normalization_splits_web_ios_and_watch() -> None:
    assert _normalize_analytics_platform("web", "feed_card_action") == "web"
    assert _normalize_analytics_platform("iOS", "screen_view") == "ios"
    assert _normalize_analytics_platform("iOS", "watch_action") == "watch"
    assert _normalize_analytics_platform("watchOS", "screen_view") == "watch"
    assert _normalize_analytics_platform("Android", "screen_view") == "android"
    assert _normalize_analytics_platform("", "unknown") == "other"


def test_page_section_classification_separates_events_search_collections_my_stuff_and_app_screen() -> None:
    assert _classify_page_section("/") == "discover"
    assert _classify_page_section("/discover") == "discover"
    assert _classify_page_section("/events/12345") == "events"
    assert _classify_page_section("/event/nba/lakers-celtics") == "events"
    assert _classify_page_section("/search") == "search"
    assert _classify_page_section("/search/nba") == "search"
    assert _classify_page_section("/collections/machinery-fed-and-macro") == "collections"
    assert _classify_page_section("/my-stuff") == "my_stuff"
    assert _classify_page_section("/my-stuff/picks") == "my_stuff"
    assert _classify_page_section("(not set)") == "app_screen"
    assert _classify_page_section("") == "app_screen"
    assert _classify_page_section("/sports") == "sports"
    assert _classify_page_section("/sport/basketball/nba") == "sports"
    assert _classify_page_section("/futures/109435") == "futures"
    assert _classify_page_section("/privacy") == "other"


@pytest.mark.asyncio
async def test_analytics_endpoints_14d_live_events_platform_split_and_sections() -> None:
    fake_req = SimpleNamespace(headers={})
    recorded_start_dates: list[str] = []

    def _fake_run_report(*, dimensions, metrics, start_date, end_date="today", limit=100, order_by_metric=None):
        recorded_start_dates.append(start_date)
        if dimensions == ["eventName"]:
            return [
                {"eventName": "session_open", "eventCount": 120, "totalUsers": 40},
                {"eventName": "feed_card_impression", "eventCount": 500, "totalUsers": 30},
                {"eventName": "feed_card_action", "eventCount": 85, "totalUsers": 18},
                {"eventName": "prediction_submit", "eventCount": 14, "totalUsers": 7},
                {"eventName": "sign_up", "eventCount": 3, "totalUsers": 3},
            ]
        if dimensions == ["platform", "eventName"]:
            return [
                {"platform": "web", "eventName": "session_open", "eventCount": 80, "totalUsers": 25},
                {"platform": "web", "eventName": "feed_card_action", "eventCount": 60, "totalUsers": 12},
                {"platform": "iOS", "eventName": "screen_view", "eventCount": 40, "totalUsers": 15},
                {"platform": "iOS", "eventName": "prediction_submit", "eventCount": 14, "totalUsers": 7},
                {"platform": "iOS", "eventName": "watch_action", "eventCount": 6, "totalUsers": 2},
            ]
        if dimensions == ["deviceCategory", "eventName"]:
            return [
                {"deviceCategory": "mobile", "eventName": "feed_card_action", "eventCount": 60, "totalUsers": 12},
            ]
        if dimensions == ["date", "eventName"]:
            return [
                {"date": "20261119", "eventName": "prediction_submit", "eventCount": 14, "totalUsers": 7},
            ]
        if dimensions == ["pagePath"]:
            return [
                {"pagePath": "/", "screenPageViews": 100, "activeUsers": 30, "averageSessionDuration": 45.0, "bounceRate": 0.2, "engagedSessions": 24},
                {"pagePath": "/events/15350374", "screenPageViews": 70, "activeUsers": 20, "averageSessionDuration": 60.0, "bounceRate": 0.1, "engagedSessions": 18},
                {"pagePath": "/search", "screenPageViews": 25, "activeUsers": 10, "averageSessionDuration": 30.0, "bounceRate": 0.3, "engagedSessions": 7},
                {"pagePath": "/collections/machinery-fed-and-macro", "screenPageViews": 40, "activeUsers": 12, "averageSessionDuration": 50.0, "bounceRate": 0.15, "engagedSessions": 10},
                {"pagePath": "/my-stuff", "screenPageViews": 18, "activeUsers": 6, "averageSessionDuration": 40.0, "bounceRate": 0.2, "engagedSessions": 5},
                {"pagePath": "(not set)", "screenPageViews": 90, "activeUsers": 15, "averageSessionDuration": 55.0, "bounceRate": 0.1, "engagedSessions": 14},
            ]
        if dimensions == ["date", "pagePath"]:
            return [
                {"date": "20261119", "pagePath": "/events/15350374", "screenPageViews": 70, "activeUsers": 20},
                {"date": "20261119", "pagePath": "/collections/machinery-fed-and-macro", "screenPageViews": 40, "activeUsers": 12},
            ]
        return [{"date": "20261119", "screenPageViews": 100, "activeUsers": 30}]

    with (
        patch("app.routes.admin_analytics._check_admin_secret"),
        patch("app.routes.admin_analytics._cache_get", new=AsyncMock(return_value=None)),
        patch("app.routes.admin_analytics._cache_set", new=AsyncMock()),
        patch("app.services.ga4_api.run_report", side_effect=_fake_run_report),
        patch("app.services.ga4_api.get_engagement_metrics", return_value={"activeUsers": 40}) as mock_eng,
        patch("app.services.ga4_api.get_top_pages", return_value=[]),
        patch("app.services.ga4_api.get_user_retention", return_value=[]) as mock_ret,
    ):
        ov = await analytics_overview(fake_req, secret="s", period="14d")
        assert ov["period"] == "14d"
        assert mock_eng.call_args.kwargs["start_date"] == "14daysAgo"

        ret = await analytics_retention(fake_req, secret="s", period="14d")
        assert ret["period"] == "14d"
        assert mock_ret.call_args.kwargs["start_date"] == "14daysAgo"

        disc = await analytics_discover(fake_req, secret="s", period="14d")
        assert disc["period"] == "14d"
        disc_names = {e["eventName"] for e in disc["discoverEvents"]}
        assert {"feed_card_action", "feed_card_impression", "prediction_submit"}.issubset(disc_names)
        assert {p["platform"] for p in disc["byPlatform"]} >= {"web", "ios"}

        fun = await analytics_funnel(fake_req, secret="s", period="14d")
        assert fun["period"] == "14d"
        by_stage = {s["stage"]: s for s in fun["funnel"]}
        assert by_stage["visit"]["users"] == 40
        assert by_stage["interact"]["events"] == 585
        assert by_stage["interact"]["users"] == 30
        assert by_stage["guess"]["events"] == 14
        assert by_stage["guess"]["users"] == 7
        assert by_stage["signup"]["users"] == 3
        plats = {p["platform"]: p for p in fun["byPlatform"]}
        assert plats["web"]["visit"] == 25 and plats["web"]["interact"] == 12
        assert plats["ios"]["visit"] == 15 and plats["ios"]["guess"] == 7

        pg = await analytics_pages(fake_req, secret="s", period="14d")
        assert pg["period"] == "14d"
        sec_map = {s["section"]: s["views"] for s in pg["sections"]}
        assert sec_map["events"] == 70
        assert sec_map["search"] == 25
        assert sec_map["collections"] == 40
        assert sec_map["my_stuff"] == 18
        assert sec_map["app_screen"] == 90
        assert "other" not in sec_map

    assert all(sd == "14daysAgo" for sd in recorded_start_dates)
