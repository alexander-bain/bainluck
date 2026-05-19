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
                "stale": True,
                "stale_after_days": 7,
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
    assert {issue["code"] for issue in health["issues"]} == {
        "low_load_rate",
        "stale",
        "stale_source",
    }


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
