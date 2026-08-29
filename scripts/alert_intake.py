#!/usr/bin/env python3
"""Create deduped GitHub issues from Sentry and GitHub Actions alerts.

This is intentionally a safe intake loop: it files or updates issues with
agent-ready context. It never edits code, commits, pushes, deploys, or resolves
Sentry issues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import pathlib
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

# --- Canonical taxonomy -------------------------------------------------------
# This script runs on a bare GitHub Actions runner (`python3 scripts/alert_intake.py`
# after a plain checkout — see .github/workflows/alert-intake.yml). Nothing is pip
# installed, so it cannot `from app.utils.issue_labels import ...`: that would run
# `backend/app/utils/__init__.py`, which imports the whole utility surface. The
# canonical module itself imports nothing, so it is loaded DIRECTLY BY PATH — one
# source of truth, zero dependencies.
#
# If the load ever fails, the rail still files, at the ratified default. Losing a
# production alert because a label helper moved would be a far worse trade than
# filing it one tier off, and `_FALLBACK_PRIORITY` is pinned equal to
# `issue_labels.DEFAULT_PRIORITY` by
# backend/tests/test_issue_filing_taxonomy.py::test_alert_intake_fallback_matches_canonical_default.
_FALLBACK_PRIORITY = "priority:p2"


def _load_issue_labels() -> Any | None:
    path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "backend" / "app" / "utils" / "issue_labels.py"
    )
    try:
        spec = importlib.util.spec_from_file_location("bainluck_issue_labels", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"no loader for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # pragma: no cover - defensive, exercised by the test
        print(f"WARNING: canonical issue taxonomy unavailable ({exc}); "
              f"falling back to {_FALLBACK_PRIORITY}", file=sys.stderr)
        return None


_ISSUE_LABELS = _load_issue_labels()


def _priority(severity: object = None) -> str:
    """Never returns an empty string — an alert always gets a priority label."""
    if _ISSUE_LABELS is None:
        return _FALLBACK_PRIORITY
    return _ISSUE_LABELS.priority_label(severity)


# Both intake families are born at the ratified alert-intake default (Alex
# 2026-07-27: "priority is earned at triage, not stamped at birth") rather than at
# whatever their source vocabulary calls itself.
#
# For Sentry that is a deliberate refusal to read `level` as a severity: Sentry's
# DEFAULT level is `error`, so mapping error→P1 would stamp P1 on essentially every
# production alert. That is precisely the "template P1 noise" the Board Sentinel
# caps at a 35% share of open alert-intake issues — the rail would manufacture the
# condition another sentinel exists to flag. Only an explicitly-set `fatal` escalates.
_SENTRY_ESCALATIONS = {"fatal": "priority:p1"}

DEFAULT_LABELS = ["alert-intake", "needs-agent"]
SENTRY_LABELS = DEFAULT_LABELS + [
    "prod-error", "sentry", "area:backend", "type:bug",
]
GITHUB_ACTIONS_LABELS = DEFAULT_LABELS + [
    "ci-failure", "github-actions", "area:infra", "type:ops", _priority(),
]


def sentry_labels_for(level: object) -> list[str]:
    """Labels for one Sentry alert — P1 only for an explicit `fatal`, else P2."""
    priority = _SENTRY_ESCALATIONS.get(str(level or "").strip().lower()) or _priority()
    return SENTRY_LABELS + [priority]


@dataclass(frozen=True)
class AlertIssue:
    key: str
    title: str
    body: str
    labels: list[str]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _github_request(
    method: str,
    path: str,
    *,
    data: dict[str, Any] | None = None,
    token: str,
    api_url: str,
) -> Any:
    url = api_url.rstrip("/") + path
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 204:
                return None
            text = response.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}")


def _ensure_labels(repo: str, labels: list[str], *, token: str, api_url: str) -> None:
    colors = {
        "alert-intake": "5319e7",
        "needs-agent": "fbca04",
        "prod-error": "d73a4a",
        "sentry": "bfd4f2",
        "ci-failure": "d93f0b",
        "github-actions": "c5def5",
    }
    for label in labels:
        path = f"/repos/{repo}/labels/{urllib.parse.quote(label)}"
        try:
            _github_request("GET", path, token=token, api_url=api_url)
        except RuntimeError:
            _github_request(
                "POST",
                f"/repos/{repo}/labels",
                data={
                    "name": label,
                    "color": colors.get(label, "ededed"),
                    "description": "Created by alert intake automation",
                },
                token=token,
                api_url=api_url,
            )


def _search_existing_issue(
    repo: str,
    key: str,
    *,
    token: str,
    api_url: str,
) -> dict[str, Any] | None:
    # Search ALL states, not just open. A chronic alert whose issue was already
    # filed and CLOSED (triaged/fixed) must be found here — otherwise a recurrence
    # gets re-filed as a brand-new "untracked" issue, spamming the board with
    # duplicates of something already handled. When a closed match recurs we
    # reopen + comment (see upsert_issue) instead of creating a duplicate.
    marker = f"alert-intake:key:{key}"
    query = f'repo:{repo} is:issue "{marker}"'
    params = urllib.parse.urlencode({"q": query, "per_page": "1"})
    result = _github_request(
        "GET",
        f"/search/issues?{params}",
        token=token,
        api_url=api_url,
    )
    items = (result or {}).get("items") or []
    return items[0] if items else None


def upsert_issue(alert: AlertIssue, *, dry_run: bool = False) -> str:
    if dry_run:
        return f"dry-run issue: {alert.title}"

    repo = _env("GITHUB_REPOSITORY")
    token = _env("GITHUB_TOKEN")
    api_url = _env("GITHUB_API_URL", "https://api.github.com")
    if not repo or not token:
        raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")

    marker = f"<!-- alert-intake:key:{alert.key} -->"
    body = f"{marker}\n\n{alert.body.strip()}\n"

    _ensure_labels(repo, alert.labels, token=token, api_url=api_url)
    existing = _search_existing_issue(repo, alert.key, token=token, api_url=api_url)
    if existing:
        issue_number = existing["number"]
        was_closed = (existing.get("state") or "").lower() == "closed"
        recurrence_note = (
            " (previously CLOSED — reopening on recurrence)" if was_closed else ""
        )
        comment = textwrap.dedent(f"""
            Alert seen again at {dt.datetime.now(dt.UTC).isoformat()}{recurrence_note}.

            Latest context:
            {alert.body.strip()}
            """).strip()
        # Reopen a closed issue before commenting so the recurrence is visible on
        # the board — but never re-file it as a new "untracked" issue.
        if was_closed:
            _github_request(
                "PATCH",
                f"/repos/{repo}/issues/{issue_number}",
                data={"state": "open"},
                token=token,
                api_url=api_url,
            )
        _github_request(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            data={"body": comment},
            token=token,
            api_url=api_url,
        )
        verb = "reopened" if was_closed else "updated"
        return f"{verb} issue #{issue_number}: {alert.title}"

    created = _github_request(
        "POST",
        f"/repos/{repo}/issues",
        data={"title": alert.title[:240], "body": body, "labels": alert.labels},
        token=token,
        api_url=api_url,
    )
    return f"created issue #{created['number']}: {alert.title}"


def _sentry_request(path: str, *, params: dict[str, str]) -> Any:
    token = _env("SENTRY_AUTH_TOKEN")
    base_url = _env("SENTRY_BASE_URL", "https://sentry.io")
    if not token:
        raise RuntimeError("SENTRY_AUTH_TOKEN is required for Sentry intake")
    query = urllib.parse.urlencode(params)
    url = f"{base_url.rstrip('/')}{path}?{query}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Sentry API failed: {exc.code} {detail}")


def _issue_24h_count(issue: dict[str, Any]) -> int | None:
    """Sum a Sentry issue's last-24h event volume from its stats histogram.

    Returns None when the payload carries no stats histogram (caller falls back
    to the lifetime ``count``). The issues API returns stats as
    ``{"24h": [[unix_ts, count], ...]}`` when statsPeriod=24h is requested.
    """
    stats = issue.get("stats") or {}
    buckets = stats.get("24h")
    if not buckets:
        return None
    total = 0
    for point in buckets:
        try:
            total += int(point[1])
        except (IndexError, TypeError, ValueError):
            continue
    return total


def sentry_alerts() -> list[AlertIssue]:
    org = _env("SENTRY_ORG")
    project = _env("SENTRY_PROJECT")
    if not org or not project:
        print("Skipping Sentry intake: SENTRY_ORG and SENTRY_PROJECT are not set")
        return []

    environment = _env("SENTRY_ENVIRONMENT", "prod")
    query = _env("SENTRY_QUERY", "is:unresolved")
    stats_period = _env("SENTRY_STATS_PERIOD", "24h")
    limit = int(_env("SENTRY_LIMIT", "20") or "20")
    issues = _sentry_request(
        f"/api/0/projects/{org}/{project}/issues/",
        params={
            "environment": environment or "",
            "query": query or "is:unresolved",
            "statsPeriod": stats_period or "24h",
            "per_page": str(min(max(limit, 1), 50)),
        },
    )

    min_events = int(_env("SENTRY_MIN_EVENTS", "50") or "50")

    alerts: list[AlertIssue] = []
    for issue in issues[:limit]:
        # Scope the threshold to the LAST 24h, not lifetime. Sentry's `count`
        # field is the lifetime event total — a chronic error quiet for weeks can
        # still report count>min_events and get (re-)flagged. The real recent
        # volume is the sum of the stats["24h"] histogram (statsPeriod=24h is set
        # on the request above). Fall back to lifetime count only if stats are
        # absent from the payload.
        event_count = _issue_24h_count(issue)
        if event_count is None:
            event_count = int(issue.get("count") or "0")
        if event_count < min_events:
            continue

        short_id = issue.get("shortId") or issue.get("short_id") or str(issue.get("id"))
        title = (
            issue.get("title")
            or issue.get("metadata", {}).get("title")
            or "Sentry issue"
        )
        culprit = issue.get("culprit") or "unknown culprit"
        permalink = issue.get("permalink") or issue.get("url") or ""
        level = issue.get("level") or "error"
        count = issue.get("count") or "unknown"
        count_24h = event_count  # 24h-scoped (what tripped the threshold)
        first_seen = issue.get("firstSeen") or "unknown"
        last_seen = issue.get("lastSeen") or "unknown"
        body = textwrap.dedent(f"""
            ## Sentry Alert

            - Issue: `{short_id}`
            - Level: `{level}`
            - Count (24h): `{count_24h}`
            - Count (lifetime): `{count}`
            - First seen: `{first_seen}`
            - Last seen: `{last_seen}`
            - Culprit: `{culprit}`
            - Link: {permalink}

            ## Agent Prompt

            Investigate and fix the production Sentry issue `{short_id}` in this repo.
            Start by finding the stack owner for `{culprit}` and searching for the
            error title:

            ```text
            {title}
            ```

            Constraints:
            - Keep the fix narrowly scoped to the failing behavior.
            - Add or update a focused regression test when practical.
            - Run the relevant backend/frontend/native verification before pushing.
            - Do not resolve the Sentry issue until the fix is deployed and quiet.
            """)
        alerts.append(
            AlertIssue(
                key=f"sentry:{short_id}",
                title=f"[Alert] Sentry {short_id}: {title}",
                body=body,
                labels=sentry_labels_for(level),
            )
        )
    return alerts


def github_workflow_run_alert() -> list[AlertIssue]:
    event_path = _env("GITHUB_EVENT_PATH")
    if not event_path:
        print("Skipping workflow_run intake: GITHUB_EVENT_PATH is not set")
        return []
    with open(event_path, "r", encoding="utf-8") as handle:
        event = json.load(handle)

    run = event.get("workflow_run") or {}
    conclusion = run.get("conclusion")
    if conclusion not in {"failure", "cancelled", "timed_out", "action_required"}:
        return []

    # Only alert on push-triggered failures on master.
    # Skip: issue_comment (agent work), workflow_run (cascade), schedule (cron).
    trigger_event = run.get("event", "")
    head_branch = run.get("head_branch") or ""
    if trigger_event != "push" or head_branch not in ("master", "main"):
        print(f"Skipping non-push CI failure: event={trigger_event} branch={head_branch}")
        return []

    repo = event.get("repository", {}).get("full_name") or _env("GITHUB_REPOSITORY", "")
    workflow = run.get("name") or "GitHub Actions"
    title = (
        run.get("display_title")
        or run.get("head_commit", {}).get("message")
        or workflow
    )
    run_id = run.get("id")
    url = run.get("html_url") or ""
    head_sha = run.get("head_sha") or ""
    head_branch = run.get("head_branch") or ""
    body = textwrap.dedent(f"""
        ## GitHub Actions Alert

        - Repository: `{repo}`
        - Workflow: `{workflow}`
        - Conclusion: `{conclusion}`
        - Branch: `{head_branch}`
        - SHA: `{head_sha}`
        - Run: {url}

        ## Agent Prompt

        Investigate the failed GitHub Actions run above.

        Suggested first commands:

        ```bash
        gh run view {run_id} --repo {repo} --log-failed
        git show --stat {head_sha}
        ```

        Constraints:
        - Confirm whether a newer commit already fixed this failure before editing.
        - Keep the fix narrowly scoped to the failing check.
        - Run the failing test/check locally when possible.
        - Push only after the relevant verification passes.
        """)
    return [
        AlertIssue(
            key=f"github-actions:{workflow}:{head_branch}",
            title=f"[Alert] CI failed: {title}",
            body=body,
            labels=GITHUB_ACTIONS_LABELS,
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("sentry", "github-workflow-run", "all"),
        default="all",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    alerts: list[AlertIssue] = []
    if args.mode in {"sentry", "all"}:
        try:
            alerts.extend(sentry_alerts())
        except Exception as exc:
            print(f"Sentry intake failed: {exc}", file=sys.stderr)
            return 1
    if args.mode in {"github-workflow-run", "all"}:
        alerts.extend(github_workflow_run_alert())

    if not alerts:
        print("No alert issues to upsert")
        return 0

    for alert in alerts:
        print(upsert_issue(alert, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
