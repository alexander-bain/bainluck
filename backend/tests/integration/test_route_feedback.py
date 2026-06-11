"""Integration tests for POST /api/feedback/bug-report.

Validates submission shape, optional auth, and HTTP method handling.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

import pytest
from unittest.mock import AsyncMock


class TestBugReportSubmission:
    async def test_missing_body_returns_403(self, client):
        resp = await client.post("/api/feedback/bug-report")
        assert resp.status_code == 422

    async def test_empty_body_accepted_with_defaults(self, client, mock_db):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={})
        assert resp.status_code == 200

    async def test_valid_submission_returns_200(self, client, mock_db):
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

    async def test_get_rejected(self, client):
        resp = await client.get("/api/feedback/bug-report")
        assert resp.status_code == 405


class TestBugReportOptionalFields:
    async def test_screenshot_url_accepted(self, client, mock_db):
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

    async def test_minimal_submission(self, client, mock_db):
        mock_db.add = lambda x: None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        resp = await client.post("/api/feedback/bug-report", json={
            "description": "Something broke",
        })
        assert resp.status_code == 200
