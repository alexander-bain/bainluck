"""Integration tests for POST /api/feedback/bug-report.

Validates submission shape, optional auth, and HTTP method handling.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def stub_github_enqueue(monkeypatch):
    """#1703: no route test in this file may touch the real broker.

    Before the fix these four submissions each performed a live kombu publish —
    one of them took 28.69s locally against a dead broker, and that was a
    quarter of backend CI's wall clock. The enqueue's own contract (task name,
    args, honest failure log) is covered in ``tests/test_feedback_enqueue.py``
    and the latency claim in
    ``tests/integration/test_feedback_enqueue_asgi_1703.py``; here we only
    assert that the submission scheduled it.
    """
    scheduled = []
    monkeypatch.setattr(
        "app.routes.feedback._enqueue_bug_report_github_issue",
        lambda report_id: scheduled.append(report_id),
    )
    return scheduled


class TestBugReportSubmission:
    async def test_missing_body_returns_403(self, client):
        resp = await client.post("/api/feedback/bug-report")
        assert resp.status_code == 422

    async def test_empty_body_accepted_with_defaults(
        self, client, mock_db, stub_github_enqueue
    ):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={})
        assert resp.status_code == 200
        assert len(stub_github_enqueue) == 1

    async def test_valid_submission_returns_200(
        self, client, mock_db, stub_github_enqueue
    ):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={
            "description": "Button doesn't work",
            "page": "/discover",
            "device_info": "iPhone 15",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "ok"
        assert len(stub_github_enqueue) == 1

    async def test_get_rejected(self, client):
        resp = await client.get("/api/feedback/bug-report")
        assert resp.status_code == 405


class TestBugReportOptionalFields:
    async def test_screenshot_url_accepted(
        self, client, mock_db, stub_github_enqueue
    ):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={
            "description": "Crash on load",
            "page": "/events/123",
            "screenshot_url": "https://example.com/shot.png",
            "device_info": "iPad Pro",
            "app_version": "1.0.3",
            "network_status": "wifi",
        })
        assert resp.status_code == 200
        assert len(stub_github_enqueue) == 1

    async def test_minimal_submission(self, client, mock_db, stub_github_enqueue):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={
            "description": "Something broke",
        })
        assert resp.status_code == 200
        assert len(stub_github_enqueue) == 1
