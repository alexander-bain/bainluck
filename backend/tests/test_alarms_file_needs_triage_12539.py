"""#12539 part 2 (121-A): no alarm files a new issue at ``priority:p1``.

Alex's 121-A (Nov 10, #12538): P1 means "this week", a list of about 15 the
morning triage sets. So every sentinel, watchdog and alert-intake path that would
open an issue labelled ``priority:p1`` opens it labelled ``needs-triage`` instead,
at the ratified P2 birth priority, and the triage promotes it or closes it.

Each rail keeps measuring its own severity. The rule is applied where a NEW issue
is created, and the repo has exactly three such places:

* ``bug_report_github.create_github_issue``: every backend rail goes through it,
  directly or via ``sentinel_filing.reconcile_issue`` (13 rails emit
  ``priority:p1``: grid, schedule, calibration, horizon, settled-concept, anchor,
  matching-drift and flow sentinels, both watchdogs, the board sentinel, the
  deploy-staleness alert and the cockpit filer);
* ``scripts/alert_intake.py``: Sentry and CI failures (a Sentry ``fatal`` is P1);
* ``scripts/daily_health_check.py``: already born P2 + ``needs-triage``.

A ratchet below keeps that list closed, so a fourth filer can't appear unseen.
``priority:p0`` is untouched: 121-A speaks about P1.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

from app.utils.issue_labels import DEFAULT_PRIORITY, ensure_taxonomy

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


class TestTheBirthRule:
    def test_p1_becomes_needs_triage_at_the_p2_floor(self):
        from app.utils.issue_labels import TRIAGE_LABEL, triage_at_birth

        labels = ensure_taxonomy(triage_at_birth(["alert-intake", "needs-agent", "priority:p1"]))
        assert "priority:p1" not in labels
        assert TRIAGE_LABEL == "needs-triage" and "needs-triage" in labels
        assert DEFAULT_PRIORITY in labels

    def test_a_list_without_p1_is_untouched(self):
        from app.utils.issue_labels import triage_at_birth

        assert triage_at_birth(["alert-intake", "priority:p2"]) == ["alert-intake", "priority:p2"]
        assert triage_at_birth(["priority:p0", "area:infra"]) == ["priority:p0", "area:infra"]

    def test_needs_triage_is_never_doubled(self):
        from app.utils.issue_labels import triage_at_birth

        assert triage_at_birth(["needs-triage", "priority:p1"]).count("needs-triage") == 1


class TestTheBackendChokepoint:
    def test_create_github_issue_never_posts_p1(self, monkeypatch):
        import app.tasks.bug_report_github as gh

        sent = {}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"number": 1, "node_id": "n"}

        def _post(url, headers=None, json=None, timeout=None):
            sent.update(json)
            return _Resp()

        monkeypatch.setattr(gh.httpx, "post", _post)
        gh.create_github_issue("t", "b", ["alert-intake", "needs-agent", "area:infra", "priority:p1"])
        assert "priority:p1" not in sent["labels"]
        assert {"needs-triage", "priority:p2", "alert-intake", "area:infra"} <= set(sent["labels"])

    def test_a_p0_still_files_as_p0(self, monkeypatch):
        import app.tasks.bug_report_github as gh

        sent = {}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"number": 1, "node_id": "n"}

        monkeypatch.setattr(gh.httpx, "post", lambda url, **kw: (sent.update(kw["json"]), _Resp())[1])
        gh.create_github_issue("t", "b", ["alert-intake", "priority:p0"])
        assert "priority:p0" in sent["labels"] and "needs-triage" not in sent["labels"]


class TestAlertIntake:
    def test_a_fatal_sentry_alert_is_filed_needs_triage(self, monkeypatch):
        mod = _load("alert_intake_12539", REPO_ROOT / "scripts" / "alert_intake.py")
        assert "priority:p1" in mod.sentry_labels_for("fatal")  # the rail still measures P1
        calls = []
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("GITHUB_TOKEN", "x")
        monkeypatch.setattr(mod, "_search_existing_issue", lambda *a, **k: None)

        def _req(method, path, data=None, token=None, api_url=None, **kw):
            calls.append((method, path, data))
            return {"number": 5}

        monkeypatch.setattr(mod, "_github_request", _req)
        monkeypatch.setattr(mod, "_ensure_labels", lambda repo, labels, **kw: calls.append(("ENSURE", labels, None)))
        alert = mod.AlertIssue(key="k", title="T", body="B", labels=mod.sentry_labels_for("fatal"))
        mod.upsert_issue(alert)
        created = [c for c in calls if c[0] == "POST" and c[1].endswith("/issues")]
        assert len(created) == 1
        assert "priority:p1" not in created[0][2]["labels"]
        assert {"needs-triage", "priority:p2"} <= set(created[0][2]["labels"])
        ensured = [c[1] for c in calls if c[0] == "ENSURE"][0]
        assert "needs-triage" in ensured


class TestTheFilingSitesAreClosed:
    # A NEW issue is created by POSTing to ``/repos/<owner>/<repo>/issues`` (no
    # further path segment). Comments, PATCHes and reads are not filings.
    _CREATE = re.compile(
        r"""(httpx\.post\(\s*f?["']https://api\.github\.com/repos/[^"']*/issues["']"""
        r"""|["']POST["']\s*,\s*f?["']/repos/[^"']*/issues["'])""",
    )

    def test_only_the_three_known_filers_create_issues(self):
        found = set()
        for root in ("backend/app", "backend/scripts", "scripts"):
            for path in (REPO_ROOT / root).rglob("*.py"):
                if "/tests/" in str(path):
                    continue
                if self._CREATE.search(path.read_text(encoding="utf-8", errors="replace")):
                    found.add(str(path.relative_to(REPO_ROOT)))
        assert found == {
            "backend/app/tasks/bug_report_github.py",
            "scripts/alert_intake.py",
            "scripts/daily_health_check.py",
        }, "a new issue-creating path must apply triage_at_birth (121-A) and be added here"

    def test_the_health_filer_is_already_born_needs_triage_at_p2(self):
        mod = _load("daily_health_check_12539", REPO_ROOT / "scripts" / "daily_health_check.py")
        labels = list(mod.COLD_CREATE_LABELS)
        assert "priority:p1" not in labels
        assert "needs-triage" in labels
