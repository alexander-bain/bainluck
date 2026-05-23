"""Tests for rage-shake → GitHub Issues pipeline."""

from app.tasks.bug_report_github import (
    build_labels,
    compute_root_cause,
    compute_severity,
    format_issue_body,
    format_issue_title,
)


class TestComputeSeverity:
    def test_data_loss_is_p0(self):
        assert compute_severity("wrong data on Lakers game") == "P0"

    def test_crash_is_p1(self):
        assert compute_severity("app crash on event page") == "P1"

    def test_blank_screen_is_p1(self):
        assert compute_severity("blank screen after tapping") == "P1"

    def test_typo_is_p3(self):
        assert compute_severity("minor typo in header") == "P3"

    def test_generic_is_p2(self):
        assert compute_severity("something looks off") == "P2"

    def test_none_is_p2(self):
        assert compute_severity(None) == "P2"

    def test_empty_is_p2(self):
        assert compute_severity("") == "P2"


class TestComputeRootCause:
    def test_odds_issue(self):
        assert "aggregation" in compute_root_cause("odds show 150%").lower()

    def test_chart_issue(self):
        assert "chart" in compute_root_cause("chart axis is wrong").lower()

    def test_slow_loading(self):
        assert "performance" in compute_root_cause("page loads slowly").lower()

    def test_duplicate(self):
        assert "duplicate" in compute_root_cause("same game appears twice").lower()

    def test_source(self):
        assert "source" in compute_root_cause("kalshi data missing").lower()

    def test_layout(self):
        assert "layout" in compute_root_cause("text is cut off").lower()

    def test_default(self):
        assert "UI" in compute_root_cause("something weird")


class TestFormatIssueTitle:
    def test_normal_description(self):
        title = format_issue_title("The odds page is broken")
        assert title == "[Bug Report] The odds page is broken"

    def test_long_description_truncated(self):
        long_desc = "a" * 100
        title = format_issue_title(long_desc)
        assert len(title) <= 95
        assert title.endswith("...")
        assert title.startswith("[Bug Report]")

    def test_no_description(self):
        assert "screenshot only" in format_issue_title(None).lower()

    def test_empty_description(self):
        assert "screenshot only" in format_issue_title("").lower()

    def test_whitespace_only(self):
        assert "screenshot only" in format_issue_title("   ").lower()

    def test_newlines_stripped(self):
        title = format_issue_title("line one\nline two")
        assert "\n" not in title
        assert "line one line two" in title


class TestBuildLabels:
    def test_ios_category(self):
        labels = build_labels("ios", "P1")
        assert "bug-report" in labels
        assert "needs-agent" in labels
        assert "area:native" in labels
        assert "priority:p1" in labels

    def test_data_quality(self):
        labels = build_labels("data_quality", "P0")
        assert "area:data" in labels
        assert "priority:p0" in labels

    def test_performance(self):
        labels = build_labels("performance", "P2")
        assert "area:backend" in labels

    def test_unknown_category(self):
        labels = build_labels("other", "P2")
        assert "bug-report" in labels
        assert not any(l.startswith("area:") for l in labels)

    def test_none_category(self):
        labels = build_labels(None, "P3")
        assert "bug-report" in labels
        assert "priority:p3" in labels


class TestFormatIssueBody:
    def test_body_contains_severity(self):
        body = format_issue_body(
            report_id=42,
            description="wrong data on page",
            category="data_quality",
            app_state={"platform": "iOS", "device_model": "iPhone 15 Pro"},
            has_screenshot=False,
        )
        assert "P0" in body

    def test_body_contains_category(self):
        body = format_issue_body(42, "test", "data_quality", None, False)
        assert "data_quality" in body

    def test_body_contains_description(self):
        body = format_issue_body(42, "odds are wrong", "ui", None, False)
        assert "odds are wrong" in body

    def test_body_contains_device_context(self):
        body = format_issue_body(
            42, "bug", "ui",
            {"platform": "iOS", "device_model": "iPhone 15 Pro", "os_version": "18.4", "network": "WiFi"},
            False,
        )
        assert "iPhone 15 Pro" in body
        assert "iOS" in body
        assert "WiFi" in body

    def test_body_contains_user(self):
        body = format_issue_body(42, "bug", "ui", {"user_name": "alex"}, False)
        assert "alex" in body

    def test_body_anonymous_user(self):
        body = format_issue_body(42, "bug", "ui", {"platform": "web"}, False)
        assert "anonymous" in body

    def test_body_has_screenshot_link(self):
        body = format_issue_body(42, "bug", "ui", None, True)
        assert "screenshot" in body.lower()
        assert "/admin/bug-reports" in body

    def test_body_no_screenshot_section_when_none(self):
        body = format_issue_body(42, "bug", "ui", None, False)
        assert "### Screenshot" not in body

    def test_body_has_admin_link(self):
        body = format_issue_body(42, "bug", "ui", None, False)
        assert "/admin/bug-reports" in body
        assert "rage shake" in body.lower()

    def test_body_empty_description(self):
        body = format_issue_body(42, None, "ui", None, False)
        assert "(no description)" in body

    def test_body_empty_app_state(self):
        body = format_issue_body(42, "bug", "ui", None, False)
        assert "unknown" in body

    def test_body_contains_report_id(self):
        body = format_issue_body(99, "bug", "ui", None, False)
        assert "report #99" in body
