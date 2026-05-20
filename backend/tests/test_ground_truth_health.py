"""Tests for advisory ground-truth health checks."""

from app.utils.ground_truth_health import (
    assess_ground_truth_report_health,
    summarize_ground_truth_health,
)


def test_assess_ground_truth_report_health_reports_unconfigured_as_info():
    health = assess_ground_truth_report_health(
        {"items": [], "metadata": {"configured": False}},
        label="external_curator",
    )

    assert health["severity"] == "info"
    assert health["ok"] is True
    assert health["issues"][0]["code"] == "not_configured"


def test_assess_ground_truth_report_health_escalates_load_errors():
    health = assess_ground_truth_report_health(
        {
            "items": [],
            "metadata": {
                "configured": True,
                "raw_row_count": 0,
                "loaded_count": 0,
                "error": "sheet denied",
            },
        },
        label="polymarket_email",
    )

    assert health["severity"] == "critical"
    assert {issue["code"] for issue in health["issues"]} == {
        "load_error",
        "empty_source",
    }


def test_assess_ground_truth_report_health_detects_zero_loaded_rows():
    health = assess_ground_truth_report_health(
        {
            "items": [],
            "metadata": {
                "configured": True,
                "raw_row_count": 10,
                "loaded_count": 0,
            },
        },
        label="polymarket_email",
    )

    assert health["severity"] == "critical"
    assert health["issues"][0]["code"] == "no_loaded_rows"


def test_assess_ground_truth_report_health_detects_low_load_rate_and_stale_sources():
    health = assess_ground_truth_report_health(
        {
            "items": [],
            "metadata": {
                "configured": True,
                "raw_row_count": 100,
                "loaded_count": 10,
                "latest_date": "2026-05-01",
                "latest_source_date": "2026-05-01",
                "latest_loaded_date": "2026-04-30",
                "stale": True,
                "stale_after_days": 7,
                "min_interestingness": 8,
                "lookback_days": 21,
                "cutoff_date": "2026-04-10",
                "filter_counts": {
                    "csv_rows": 150,
                    "source_rows": 100,
                    "outside_lookback": 20,
                    "non_market_name": 0,
                    "low_interestingness": 60,
                    "duplicate": 10,
                    "loaded": 10,
                },
                "source_health": [
                    {
                        "source": "Instagram @kalshi",
                        "latest_date": "2026-05-01",
                        "stale": True,
                    }
                ],
            },
        },
        label="external_curator",
        min_load_rate=0.25,
    )

    assert health["severity"] == "warning"
    assert health["load_rate"] == 0.1
    assert health["eligible_row_count"] == 20
    assert health["eligible_load_rate"] == 0.5
    assert health["latest_source_date"] == "2026-05-01"
    assert health["latest_loaded_date"] == "2026-04-30"
    assert health["cutoff_date"] == "2026-04-10"
    assert health["filter_counts"]["low_interestingness"] == 60
    assert {issue["code"] for issue in health["issues"]} == {
        "stale",
        "stale_source",
    }


def test_assess_ground_truth_report_health_uses_eligible_rows_for_load_rate():
    health = assess_ground_truth_report_health(
        {
            "items": [],
            "metadata": {
                "configured": True,
                "raw_row_count": 604,
                "loaded_count": 66,
                "latest_date": "2026-05-20",
                "stale": False,
                "filter_counts": {
                    "csv_rows": 604,
                    "source_rows": 604,
                    "outside_lookback": 449,
                    "non_market_name": 0,
                    "low_interestingness": 76,
                    "duplicate": 13,
                    "loaded": 66,
                },
            },
        },
        label="polymarket_email",
        min_load_rate=0.25,
    )

    assert health["severity"] == "ok"
    assert health["load_rate"] == 0.1093
    assert health["eligible_row_count"] == 79
    assert health["eligible_load_rate"] == 0.8354
    assert health["issues"] == []


def test_summarize_ground_truth_health_rolls_up_worst_severity():
    summary = summarize_ground_truth_health(
        [
            {"severity": "ok", "issues": []},
            {"severity": "warning", "issues": [{"code": "stale"}]},
            {"severity": "critical", "issues": [{"code": "load_error"}]},
        ]
    )

    assert summary == {
        "severity": "critical",
        "ok": False,
        "reports": [
            {"severity": "ok", "issues": []},
            {"severity": "warning", "issues": [{"code": "stale"}]},
            {"severity": "critical", "issues": [{"code": "load_error"}]},
        ],
        "issue_count": 2,
    }
