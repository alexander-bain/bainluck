#!/usr/bin/env python3
"""#12252 item 4 — a program, not a person, notices that merges have stopped reaching readers.

Nov 7: master went red at midnight PT (a test read the real clock), every deploy behind it
stopped, and production sat 60 commits behind master for hours before a person looked.

Every 30 minutes from 8 AM to 10 PM PT, and whenever a master CI run completes, this reads:
  * the commit production serves (``/health``'s ``commit``),
  * master's tip and how long its OLDEST commit not yet in production has been waiting,
  * master's newest CI run (status, conclusion, id).

When production is more than 2 hours behind AND master's newest CI run is complete (so it is
not simply a deploy in flight), it files — or updates — ONE issue through ``reconcile_issue``:
``Deploy stale: /health at <sha>, master at <sha>, N h``, naming the newest master run so a
person re-runs THAT one (newest only). When production is caught up it posts nothing; an open
stale issue is closed with one recovery note. It never cancels, re-runs or deploys anything.

  python3 scripts/deploy_staleness_alert.py --dry-run   # print the reading, write nothing
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.agent_origin import tagged  # noqa: E402

REPO = "alexander-bain/bainluck"
API = "https://api.github.com"
HEALTH_URL = "https://api.bainluck.com/health"
STALE_AFTER = dt.timedelta(hours=2)
PT = ZoneInfo("America/Los_Angeles")
HOURS_PT = (8, 22)  # 8 AM to 10 PM Pacific
MARKER_KEY = "deploy-stale-fingerprint"
FINGERPRINT = "0deb10a57a1e"  # one issue for the condition, reused across episodes
TITLE_PREFIX = "Deploy stale: "


def _get(url: str, token: str | None = None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bainluck-deploy-staleness"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=tagged(url, headers))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _patch(url: str, token: str, data: dict) -> None:
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PATCH",
                                 headers=tagged(url, headers))
    urllib.request.urlopen(req, timeout=30).close()


def _ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def in_hours(now: dt.datetime) -> bool:
    return HOURS_PT[0] <= now.astimezone(PT).hour < HOURS_PT[1]


def landings(commits: list[dict]) -> list[dict]:
    """The undeployed commits as master GOT them, oldest first: master's first-parent chain
    back from the tip. A PR merged with a merge commit brings commits authored hours earlier;
    their dates are not when master got them, the merge's is."""
    by_sha = {c["sha"]: c for c in commits}
    chain = [commits[-1]]
    while True:
        parents = chain[-1].get("parents") or []
        nxt = by_sha.get(parents[0]["sha"]) if parents else None
        if nxt is None:
            return chain[::-1]
        chain.append(nxt)


def first_landing(commits: list[dict]) -> dt.datetime:
    """When the oldest undeployed change REACHED master."""
    return _ts(landings(commits)[0]["commit"]["committer"]["date"])


def _release_required(before: str, after: str) -> bool:
    """CI's own rule (`.github/scripts/heroku-release-required.sh`, #4456): does this landing
    change anything the Heroku dynos serve? A frontend/docs-only merge never deploys to
    Heroku, so `/health` rightly stays behind it. Every failure reads as True, as the
    script itself fails toward releasing."""
    import subprocess

    script = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "scripts", "heroku-release-required.sh")
    try:
        out = subprocess.run(["bash", script, before, after], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    return out.stdout.strip() != "false"


def assess(health_sha: str, compare: dict, newest_run: dict | None, now: dt.datetime,
           needs_release=_release_required) -> dict:
    """Pure decision. ``compare`` is GitHub's ``compare/{health}...{master}`` payload.

    The clock starts at the oldest undeployed landing that CI would release. Nov 7: a Safari
    banner merge (#12326, frontend only) skipped the Heroku deploy, correctly, and `/health`
    stayed at the commit before it; counting it would have filed a false alarm 2 h later.
    """
    status = compare.get("status")
    commits = compare.get("commits") or []
    master = (commits[-1]["sha"] if commits else compare.get("merge_base_commit", {}).get("sha")) or ""
    out = {"health": health_sha[:8], "master": master[:8], "behind": compare.get("ahead_by", 0),
           "waiting": None, "run": newest_run, "stale": False, "reason": ""}
    if status in ("identical", "behind") or not commits:
        out["reason"] = "caught up"
        return out
    pending = []
    for landing in landings(commits):
        parents = landing.get("parents") or []
        before = parents[0]["sha"] if parents else health_sha
        if needs_release(before, landing["sha"]):
            pending.append(landing)
    if not pending:
        out["reason"] = "caught up (everything since is frontend/docs only, which Heroku never serves)"
        return out
    out["waiting"] = now - _ts(pending[0]["commit"]["committer"]["date"])
    if out["waiting"] <= STALE_AFTER:
        out["reason"] = "behind, under 2 h"
        return out
    if not newest_run or newest_run.get("status") != "completed":
        out["reason"] = "behind over 2 h, but master's newest CI run is still running"
        return out
    out["stale"] = True
    out["reason"] = "stale"
    return out


def title(a: dict) -> str:
    hours = a["waiting"].total_seconds() / 3600
    return f"{TITLE_PREFIX}/health at {a['health']}, master at {a['master']}, {hours:.0f} h"


def body(a: dict) -> str:
    run = a["run"] or {}
    hours = a["waiting"].total_seconds() / 3600
    return (
        f"PILLAR: TRUTH. **Ship:** a merge reaches readers within hours, and when it doesn't, "
        f"a person hears about it from a program instead of noticing.\n\n"
        f"Production (`/health`) serves `{a['health']}`. Master is at `{a['master']}`, "
        f"**{a['behind']} commits ahead**, and its oldest commit not yet in production has waited "
        f"**{hours:.1f} h** (the bar is {STALE_AFTER.total_seconds() / 3600:.0f} h).\n\n"
        f"Master's newest CI run: [{run.get('id')}]({run.get('html_url')}) — {run.get('status')}, "
        f"**{run.get('conclusion')}**, on `{(run.get('head_sha') or '')[:10]}`. If that run failed "
        f"on a flake, re-run **that run only** (the newest; an older run deploys an older commit). "
        f"If it failed on a real break, master needs a fix first.\n\n"
        f"This alert never cancels, re-runs or deploys anything. It updates this issue while "
        f"production stays behind and closes it, once, when production catches up.\n\n"
        f"Filed by `backend/scripts/deploy_staleness_alert.py` (#12252 item 4).\n\n"
        f"<sub>`{MARKER_KEY}:{FINGERPRINT}`  (dedupe key — do not remove)</sub>"
    )


def read(token: str, now: dt.datetime) -> dict:
    health = _get(HEALTH_URL)["commit"]
    compare = _get(f"{API}/repos/{REPO}/compare/{health}...master", token)
    runs = _get(f"{API}/repos/{REPO}/actions/workflows/ci.yml/runs?branch=master&event=push&per_page=1", token)
    newest = (runs.get("workflow_runs") or [None])[0]
    return assess(health, compare, newest, now)


def caught_up(a: dict) -> bool:
    """Production serves everything CI would release: either no commit is behind, or every one
    behind is frontend/docs only. Both readings close an open stale issue (Fable, #12328)."""
    return a["reason"].startswith("caught up")


def open_stale_issue(token: str, pages: int = 5) -> bool:
    """Whether the one stale issue is open. Paged like the rail (at most 5 x 100), so a busy
    alert-intake list cannot hide it from the close path."""
    marker = f"{MARKER_KEY}:{FINGERPRINT}"
    for page in range(1, pages + 1):
        issues = _get(f"{API}/repos/{REPO}/issues?state=open&labels=alert-intake&per_page=100&page={page}", token)
        if any(marker in (i.get("body") or "") for i in issues):
            return True
        if len(issues) < 100:
            return False
    return True  # more than 500 open: cannot rule it out, so let the rail decide


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--any-hour", action="store_true", help="ignore the 8 AM-10 PM PT window (a drill)")
    ap.add_argument("--plan", action="store_true",
                    help="standard library only: write act=true|false to $GITHUB_OUTPUT and stop")
    args = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    if not (args.any_hour or in_hours(now)):
        print(f"outside 8 AM-10 PM PT ({now.astimezone(PT):%-I:%M %p}); nothing read")
        return 0
    token = os.environ.get("GITHUB_TOKEN", "")
    a = read(token, now)
    run = a["run"] or {}
    print(f"/health {a['health']} · master {a['master']} · {a['behind']} behind · "
          f"waiting {a['waiting']} · newest master run {run.get('id')} {run.get('status')}/"
          f"{run.get('conclusion')} → {a['reason']}")
    if args.plan:
        # Most runs are caught up with no issue open: they stop here, before any dependency
        # install, so a quiet day costs a checkout and three reads per run.
        act = a["stale"] or (caught_up(a) and open_stale_issue(token))
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"act={'true' if act else 'false'}\n")
        print(f"act={act}")
        return 0
    if args.dry_run:
        return 0
    from app.tasks.sentinel_filing import reconcile_issue

    if a["stale"]:
        result = reconcile_issue(
            red=True, fingerprint=FINGERPRINT, marker_key=MARKER_KEY,
            labels=["alert-intake", "needs-agent", "area:infra", "type:bug", "priority:p1"],
            title=title(a), body=body(a), red_body=body(a), title_prefix=None,
            red_comment=f"Still stale: {title(a)[len(TITLE_PREFIX):]}. Newest master run "
                        f"{run.get('id')} ({run.get('conclusion')}).",
            add_to_board=False,
            # Comment when the reading changes (or daily), not because "N h" ticked over.
            red_digest_basis=f"{a['health']}|{a['master']}|{run.get('id')}|{run.get('conclusion')}",
        )
        if result.get("action") in ("commented", "comment_skipped_unchanged") and result.get("issue"):
            _patch(f"{API}/repos/{REPO}/issues/{result['issue']}", token, {"title": title(a)})
    elif caught_up(a):
        result = reconcile_issue(
            red=False, fingerprint=FINGERPRINT, marker_key=MARKER_KEY,
            green_comment=f"Caught up: production (`{a['health']}`) serves every change CI would release "
                          f"from master (tip `{a['master']}`; {a['reason']}). Closing.",
        )
    else:
        result = {"action": "none", "note": a["reason"]}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
