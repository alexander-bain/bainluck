from types import SimpleNamespace

import pytest

from app.routes.feedback import BugReportSubmission, categorize_bug_report, submit_bug_report


@pytest.mark.parametrize(
    ("description", "app_state", "expected"),
    [
        (
            "The Lakers game has the wrong score and stale odds.",
            None,
            "data_quality",
        ),
        (
            "Discover is slow and the spinner stays up forever.",
            None,
            "performance",
        ),
        (
            "Please add a way to filter pinned markets.",
            None,
            "feature_request",
        ),
        (
            "Text overlaps the chart and the button is cut off.",
            None,
            "ui",
        ),
        (
            "Apple Sign-In fails after TestFlight update.",
            None,
            "ios",
        ),
        (
            None,
            {"platform": "iOS", "screen": "Discover", "device": "iPhone 15"},
            "ios",
        ),
        (
            "Something weird happened.",
            {"screen": "Discover"},
            "other",
        ),
    ],
)
def test_categorize_bug_report_uses_deterministic_keyword_rules(
    description,
    app_state,
    expected,
):
    assert categorize_bug_report(description, app_state) == expected


def test_categorize_bug_report_prefers_clear_data_issue_over_ios_context():
    category = categorize_bug_report(
        "The Knicks probability is wrong and the score is stale.",
        {"platform": "iOS", "device": "iPhone"},
    )

    assert category == "data_quality"


class _FakeDB:
    def __init__(self):
        self.report = None
        self.committed = False

    def add(self, report):
        self.report = report

    async def commit(self):
        self.committed = True
        self.report.id = 456

    async def refresh(self, _report):
        return None


@pytest.mark.asyncio
async def test_submit_bug_report_persists_auto_category():
    db = _FakeDB()
    request = SimpleNamespace(headers={"x-session-id": "session-123"})
    body = BugReportSubmission(
        description="The market has the wrong team and stale probability.",
        app_state={"screen": "EventDetail", "platform": "iOS"},
    )

    response = await submit_bug_report(
        body=body,
        request=request,
        db=db,
        user=None,
    )

    assert response == {"status": "ok", "id": 456, "category": "data_quality"}
    assert db.committed is True
    assert db.report.category == "data_quality"
    assert db.report.session_id == "session-123"
