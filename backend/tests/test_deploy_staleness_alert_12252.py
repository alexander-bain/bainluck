"""#12252 item 4: the deploy-staleness alert files ONE issue when production is more than 2 h
behind master and master's newest CI run is complete, names that run, and posts nothing while
production is caught up. It never cancels, re-runs or deploys."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import yaml

from app.tasks.sentinel_filing import declared_fingerprints

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "deploy_staleness_alert", ROOT / "backend" / "scripts" / "deploy_staleness_alert.py"
)
alert = importlib.util.module_from_spec(SPEC)
sys.modules["deploy_staleness_alert"] = alert
SPEC.loader.exec_module(alert)

NOW = dt.datetime(2026, 11, 7, 18, 0, tzinfo=dt.timezone.utc)  # 10 AM PT
DONE = {"id": 42383304286, "status": "completed", "conclusion": "failure", "head_sha": "a177b62927" + "0" * 30,
        "html_url": "https://github.com/alexander-bain/bainluck/actions/runs/42383304286"}


def _c(sha, landed, parent, extra_parents=()):
    return {"sha": sha, "commit": {"committer": {"date": landed}},
            "parents": [{"sha": parent}] + [{"sha": p} for p in extra_parents]}


def _compare(*commits, status="ahead"):
    return {"status": status, "ahead_by": len(commits), "commits": list(commits)}


def test_more_than_two_hours_behind_with_a_finished_run_is_stale():
    a = alert.assess("e5ee66fb1a", _compare(_c("m1", "2026-11-07T14:00:00Z", "e5ee66fb1a"),
                                            _c("m2", "2026-11-07T17:00:00Z", "m1")), DONE, now=NOW)
    assert a["stale"] and a["waiting"] == dt.timedelta(hours=4)
    assert alert.title(a) == "Deploy stale: /health at e5ee66fb, master at m2, 4 h"
    assert "42383304286" in alert.body(a) and "that run only" in alert.body(a)


def test_under_two_hours_or_a_run_still_going_is_not_stale():
    fresh = _compare(_c("m1", "2026-11-07T16:30:00Z", "h"))
    assert not alert.assess("h", fresh, DONE, now=NOW)["stale"]
    old = _compare(_c("m1", "2026-11-07T12:00:00Z", "h"))
    running = {**DONE, "status": "in_progress", "conclusion": None}
    a = alert.assess("h", old, running, now=NOW)
    assert not a["stale"] and "still running" in a["reason"]


def test_caught_up_is_never_stale():
    a = alert.assess("abc", {"status": "identical", "ahead_by": 0, "commits": []}, DONE, now=NOW)
    assert not a["stale"] and a["reason"] == "caught up"


def test_waiting_starts_when_master_got_the_change_not_when_it_was_authored():
    # A PR merged with a merge commit at 17:00 brings a commit authored at 03:00.
    pr = _c("p1", "2026-11-07T03:00:00Z", "h")
    merge = _c("m1", "2026-11-07T17:00:00Z", "h", extra_parents=("p1",))
    a = alert.assess("h", _compare(pr, merge), DONE, now=NOW)
    assert a["waiting"] == dt.timedelta(hours=1) and not a["stale"]


def test_the_window_is_8_am_to_10_pm_pacific_in_either_offset():
    pst = dt.timezone(dt.timedelta(hours=-8))
    assert alert.in_hours(dt.datetime(2026, 11, 7, 8, 0, tzinfo=pst))
    assert not alert.in_hours(dt.datetime(2026, 11, 7, 7, 59, tzinfo=pst))
    assert not alert.in_hours(dt.datetime(2026, 11, 7, 22, 0, tzinfo=pst))
    pdt = dt.timezone(dt.timedelta(hours=-7))
    assert alert.in_hours(dt.datetime(2026, 7, 1, 21, 59, tzinfo=pdt))


def test_the_body_declares_the_one_fingerprint_the_rail_dedups_on():
    a = alert.assess("h", _compare(_c("m1", "2026-11-07T12:00:00Z", "h")), DONE, now=NOW)
    assert (alert.MARKER_KEY, alert.FINGERPRINT) in declared_fingerprints(alert.body(a))


def test_the_alert_never_cancels_reruns_or_deploys():
    src = (ROOT / "backend" / "scripts" / "deploy_staleness_alert.py").read_text()
    # Heroku is named (CI's release rule reads "what the Heroku dynos serve"), never called:
    # no CLI argv, no Platform API.
    for verb in ("/cancel", "/rerun", "/dispatches", "git push", '"heroku"', "api.heroku.com"):
        assert verb not in src, verb
    # The one subprocess it runs is CI's read-only release rule.
    assert src.count("subprocess.run(") == 1 and "heroku-release-required.sh" in src


def test_the_workflow_checks_on_every_master_ci_completion_and_every_30_minutes():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy-staleness.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert on["workflow_run"] == {"workflows": ["CI"], "types": ["completed"], "branches": ["master"]}
    assert on["schedule"] == [{"cron": "*/30 * * * *"}]
    assert wf["permissions"] == {"actions": "read", "contents": "read", "issues": "write"}
    steps = wf["jobs"]["check"]["steps"]
    plan = next(s for s in steps if s.get("id") == "plan")
    assert "--plan" in plan["run"] and "setup-python" not in str(steps[: steps.index(plan)])
    assert all(s.get("if") == "steps.plan.outputs.act == 'true'" for s in steps[steps.index(plan) + 1:])


# --- a frontend/docs-only landing never deploys to Heroku, so it never starts the clock ---------

def test_frontend_only_landings_are_caught_up():
    """Nov 7: #12326 (Safari banner, frontend only) skipped the Heroku deploy, correctly."""
    a = alert.assess("h", _compare(_c("m1", "2026-11-07T12:00:00Z", "h")), DONE, now=NOW,
                     needs_release=lambda before, after: False)
    assert not a["stale"] and a["reason"].startswith("caught up")


def test_the_clock_starts_at_the_oldest_landing_ci_would_release():
    commits = _compare(_c("fe", "2026-11-07T12:00:00Z", "h"), _c("be", "2026-11-07T17:00:00Z", "fe"))
    a = alert.assess("h", commits, DONE, now=NOW, needs_release=lambda before, after: after == "be")
    assert a["waiting"] == dt.timedelta(hours=1) and not a["stale"]
    a = alert.assess("h", commits, DONE, now=NOW, needs_release=lambda before, after: after == "fe")
    assert a["waiting"] == dt.timedelta(hours=6) and a["stale"]


def test_each_landing_is_judged_against_its_own_first_parent():
    seen = []
    pr = _c("p1", "2026-11-07T03:00:00Z", "h")
    merge = _c("m1", "2026-11-07T17:00:00Z", "h", extra_parents=("p1",))
    alert.assess("h", _compare(pr, merge), DONE, now=NOW, needs_release=lambda b, a: seen.append((b, a)) or True)
    assert seen == [("h", "m1")]


def test_the_rule_is_cis_own_script_on_real_commits():
    import subprocess

    import pytest

    frontend_only, backend = "2cbf51e7f6", "cf40a89866"  # #12326 and #12321, both on master Nov 7
    have = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{frontend_only}^{{commit}}"],
                          capture_output=True).returncode == 0
    if not have:
        pytest.skip("shallow checkout: the Nov 7 commits are not present")
    assert alert._release_required(f"{frontend_only}^", frontend_only) is False
    assert alert._release_required(f"{backend}^", backend) is True
    assert alert._release_required("0" * 40, backend) is True  # an unusable base fails toward releasing


# --- Fable, #12328: a recovered episode closes even when master's tip is frontend-only ----------

def _frontend_only_reading():
    return alert.assess("h", _compare(_c("fe", "2026-11-07T12:00:00Z", "h")), DONE, now=NOW,
                        needs_release=lambda before, after: False)


def test_an_open_stale_issue_closes_when_only_frontend_landings_remain(monkeypatch):
    import app.tasks.sentinel_filing as rail

    calls = []
    monkeypatch.setattr(alert, "in_hours", lambda now: True)
    monkeypatch.setattr(alert, "read", lambda token, now: _frontend_only_reading())
    monkeypatch.setattr(alert, "open_stale_issue", lambda token: True)
    monkeypatch.setattr(rail, "reconcile_issue", lambda **kw: calls.append(kw) or {"action": "resolved"})
    out = Path(__import__("tempfile").mkdtemp()) / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert alert.main(["--plan"]) == 0
    assert "act=true" in out.read_text()
    assert alert.main([]) == 0
    assert len(calls) == 1 and calls[0]["red"] is False


def test_a_caught_up_reading_with_no_issue_open_does_nothing(monkeypatch):
    monkeypatch.setattr(alert, "in_hours", lambda now: True)
    monkeypatch.setattr(alert, "read", lambda token, now: _frontend_only_reading())
    monkeypatch.setattr(alert, "open_stale_issue", lambda token: False)
    out = Path(__import__("tempfile").mkdtemp()) / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    alert.main(["--plan"])
    assert "act=false" in out.read_text()


def test_the_open_issue_read_pages_past_100(monkeypatch):
    marker = f"{alert.MARKER_KEY}:{alert.FINGERPRINT}"
    pages = {1: [{"body": "x"}] * 100, 2: [{"body": "x"}] * 100, 3: [{"body": f"... {marker} ..."}]}
    seen = []

    def fake_get(url, token=None):
        page = int(url.rsplit("page=", 1)[1])
        seen.append(page)
        return pages.get(page, [])

    monkeypatch.setattr(alert, "_get", fake_get)
    assert alert.open_stale_issue("t") is True and seen == [1, 2, 3]
    pages[3] = [{"body": "x"}]
    seen.clear()
    assert alert.open_stale_issue("t") is False and seen == [1, 2, 3]


def test_a_stale_comment_keys_its_cadence_on_the_reading_not_the_hour():
    src = (ROOT / "backend" / "scripts" / "deploy_staleness_alert.py").read_text()
    assert "red_digest_basis=f\"{a['health']}|{a['master']}|{run.get('id')}|{run.get('conclusion')}\"" in src
