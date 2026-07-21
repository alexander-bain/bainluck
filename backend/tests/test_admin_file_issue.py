"""Tests for the cockpit on-demand "File this" rail (L2-142 Item 1/3).

The endpoint files (or dedup-comments) a GitHub issue via the shared rail.
We mock the rail so nothing hits GitHub.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import admin_file_issue

client = TestClient(app)

_AUTH = {"Authorization": "Bearer test-admin-secret"}


@pytest.fixture(autouse=True)
def _admin_ok():
    # Bypass the real secret check for every test in this module.
    with patch.object(admin_file_issue, "_check_admin_secret", return_value=True):
        yield


def _rail(number=4242, node="NODE_abc", existing=None):
    """Patch the rail functions imported inside the endpoint."""
    return patch.multiple(
        "app.tasks.bug_report_github",
        GITHUB_TOKEN="tok",
        create_github_issue=lambda title, body, labels: (number, node),
        add_to_project_board=lambda node_id: None,
        comment_on_issue=lambda n, b: None,
    )


def test_fingerprint_is_stable_and_source_scoped():
    a = admin_file_issue._fingerprint("cockpit_tile", "worker_health")
    b = admin_file_issue._fingerprint("cockpit_tile", "worker_health")
    c = admin_file_issue._fingerprint("system_diagnosis", "worker_health")
    assert a == b
    assert a != c
    assert len(a) == 12


def test_file_issue_files_new_when_no_existing():
    with _rail(number=5150), patch.object(
        admin_file_issue, "_find_open_issue_by_fingerprint", return_value=None
    ):
        r = client.post(
            "/api/admin/file-issue",
            headers=_AUTH,
            json={
                "source": "cockpit_tile",
                "key": "worker_health",
                "title": "Worker health RED",
                "body": "3 tasks failing",
                "severity": "P1",
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "filed"
    assert data["issue"] == 5150
    assert data["url"].endswith("/issues/5150")


def test_file_issue_dedups_to_existing_open_issue():
    with _rail(), patch.object(
        admin_file_issue, "_find_open_issue_by_fingerprint", return_value=999
    ):
        r = client.post(
            "/api/admin/file-issue",
            headers=_AUTH,
            json={"source": "cockpit_tile", "key": "worker_health", "title": "Worker health RED"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "exists"
    assert data["issue"] == 999


def test_file_issue_requires_title():
    with _rail(), patch.object(
        admin_file_issue, "_find_open_issue_by_fingerprint", return_value=None
    ):
        r = client.post(
            "/api/admin/file-issue",
            headers=_AUTH,
            json={"source": "cockpit_tile", "key": "k", "title": "   "},
        )
    assert r.status_code == 400


def test_file_issue_503_without_token():
    with patch("app.tasks.bug_report_github.GITHUB_TOKEN", ""):
        r = client.post(
            "/api/admin/file-issue",
            headers=_AUTH,
            json={"source": "cockpit_tile", "key": "k", "title": "t"},
        )
    assert r.status_code == 503


def test_severity_maps_diagnosis_vocab():
    captured = {}

    def _capture(title, body, labels):
        captured["labels"] = labels
        return (7, "n")

    with patch.multiple(
        "app.tasks.bug_report_github",
        GITHUB_TOKEN="tok",
        create_github_issue=_capture,
        add_to_project_board=lambda node_id: None,
        comment_on_issue=lambda n, b: None,
    ), patch.object(admin_file_issue, "_find_open_issue_by_fingerprint", return_value=None):
        r = client.post(
            "/api/admin/file-issue",
            headers=_AUTH,
            json={
                "source": "system_diagnosis",
                "key": "poly stall",
                "title": "Polymarket creation stalled",
                "severity": "critical",
                "labels": ["area:backend"],
            },
        )
    assert r.status_code == 200, r.text
    assert "priority:p1" in captured["labels"]  # critical -> p1
    assert "area:backend" in captured["labels"]
    assert "alert-intake" in captured["labels"]
