"""
GA4 Data API client.

Authenticates using the Firebase service account JSON from the
FIREBASE_SERVICE_ACCOUNT_JSON env var and queries GA4 analytics data
via the google-analytics-data library.

Property ID is read from the GA4_PROPERTY_ID env var.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_client = None
_PROPERTY_ID: str | None = None


def _get_property_id() -> str:
    """Return the GA4 property ID or raise."""
    global _PROPERTY_ID
    if _PROPERTY_ID is None:
        _PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")
    if not _PROPERTY_ID:
        raise RuntimeError("GA4_PROPERTY_ID env var is not set")
    return _PROPERTY_ID


def _get_client():
    """Lazily initialise the GA4 BetaAnalyticsDataClient."""
    global _client
    if _client is not None:
        return _client

    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account

    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON env var is not set — "
            "cannot authenticate with GA4"
        )

    info = json.loads(sa_json)
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    _client = BetaAnalyticsDataClient(credentials=creds)
    logger.info("GA4 Data API client initialised (property %s)", _get_property_id())
    return _client


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _property() -> str:
    return f"properties/{_get_property_id()}"


def _dim(name: str):
    from google.analytics.data_v1beta.types import Dimension
    return Dimension(name=name)


def _met(name: str):
    from google.analytics.data_v1beta.types import Metric
    return Metric(name=name)


def _date_range(start: str, end: str):
    from google.analytics.data_v1beta.types import DateRange
    return DateRange(start_date=start, end_date=end)


def _rows_to_dicts(response) -> list[dict[str, Any]]:
    """Convert a GA4 RunReportResponse into a list of plain dicts."""
    dim_headers = [h.name for h in response.dimension_headers]
    met_headers = [h.name for h in response.metric_headers]
    rows: list[dict[str, Any]] = []
    for row in response.rows:
        d: dict[str, Any] = {}
        for i, dv in enumerate(row.dimension_values):
            d[dim_headers[i]] = dv.value
        for i, mv in enumerate(row.metric_values):
            d[met_headers[i]] = mv.value
        rows.append(d)
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_report(
    *,
    dimensions: list[str],
    metrics: list[str],
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 100,
    order_by_metric: str | None = None,
    descending: bool = True,
) -> list[dict[str, Any]]:
    """Run an arbitrary GA4 report and return rows as dicts."""
    from google.analytics.data_v1beta.types import RunReportRequest, OrderBy

    client = _get_client()

    order_bys = []
    if order_by_metric:
        order_bys.append(
            OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name=order_by_metric),
                desc=descending,
            )
        )

    request = RunReportRequest(
        property=_property(),
        dimensions=[_dim(d) for d in dimensions],
        metrics=[_met(m) for m in metrics],
        date_ranges=[_date_range(start_date, end_date)],
        limit=limit,
        order_bys=order_bys or None,
    )
    response = client.run_report(request)
    return _rows_to_dicts(response)


def get_realtime() -> dict[str, Any]:
    """Return real-time active users and top pages."""
    from google.analytics.data_v1beta.types import (
        RunRealtimeReportRequest,
        Dimension,
        Metric,
    )

    client = _get_client()

    # Active users total
    total_req = RunRealtimeReportRequest(
        property=_property(),
        metrics=[Metric(name="activeUsers")],
    )
    total_resp = client.run_realtime_report(total_req)
    active_users = 0
    if total_resp.rows:
        active_users = int(total_resp.rows[0].metric_values[0].value)

    # Active users by page
    page_req = RunRealtimeReportRequest(
        property=_property(),
        dimensions=[Dimension(name="unifiedPagePathScreen")],
        metrics=[Metric(name="activeUsers")],
        limit=20,
    )
    page_resp = client.run_realtime_report(page_req)
    top_pages: list[dict[str, Any]] = []
    for row in page_resp.rows:
        top_pages.append({
            "page": row.dimension_values[0].value,
            "activeUsers": int(row.metric_values[0].value),
        })

    return {
        "activeUsers": active_users,
        "topActivePages": top_pages,
    }


def get_top_pages(
    start_date: str = "7daysAgo",
    end_date: str = "today",
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return top pages by screen page views."""
    return run_report(
        dimensions=["pagePath"],
        metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        order_by_metric="screenPageViews",
    )


def get_engagement_metrics(
    start_date: str = "7daysAgo",
    end_date: str = "today",
) -> dict[str, Any]:
    """Return key engagement metrics: DAU, sessions, avg duration, bounce rate."""
    from google.analytics.data_v1beta.types import RunReportRequest

    client = _get_client()
    request = RunReportRequest(
        property=_property(),
        dimensions=[_dim("date")],
        metrics=[
            _met("activeUsers"),
            _met("sessions"),
            _met("averageSessionDuration"),
            _met("bounceRate"),
            _met("screenPageViews"),
            _met("engagedSessions"),
        ],
        date_ranges=[_date_range(start_date, end_date)],
        limit=90,
    )
    response = client.run_report(request)
    daily = _rows_to_dicts(response)

    # Compute totals/averages
    total_users = sum(int(r.get("activeUsers", 0)) for r in daily)
    total_sessions = sum(int(r.get("sessions", 0)) for r in daily)
    total_views = sum(int(r.get("screenPageViews", 0)) for r in daily)
    days = len(daily) or 1
    avg_duration_vals = [float(r.get("averageSessionDuration", 0)) for r in daily if float(r.get("sessions", 0)) > 0]
    avg_duration = sum(avg_duration_vals) / len(avg_duration_vals) if avg_duration_vals else 0
    bounce_vals = [float(r.get("bounceRate", 0)) for r in daily if float(r.get("sessions", 0)) > 0]
    avg_bounce = sum(bounce_vals) / len(bounce_vals) if bounce_vals else 0

    return {
        "period": {"start": start_date, "end": end_date},
        "summary": {
            "totalUsers": total_users,
            "totalSessions": total_sessions,
            "totalPageViews": total_views,
            "avgDailyUsers": round(total_users / days, 1),
            "avgSessionDuration": round(avg_duration, 1),
            "avgBounceRate": round(avg_bounce * 100, 1),
        },
        "daily": daily,
    }


def get_user_retention(
    start_date: str = "30daysAgo",
    end_date: str = "today",
) -> list[dict[str, Any]]:
    """Return cohorted retention data (new vs returning users by day)."""
    return run_report(
        dimensions=["date", "newVsReturning"],
        metrics=["activeUsers", "sessions"],
        start_date=start_date,
        end_date=end_date,
        limit=200,
        order_by_metric="activeUsers",
        descending=True,
    )
