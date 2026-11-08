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
