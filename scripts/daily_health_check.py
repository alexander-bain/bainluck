#!/usr/bin/env python3
"""Daily production health check for Bain Luck.

Hits admin endpoints, checks thresholds, creates a GitHub issue if anything
is unhealthy. Designed to run as a GitHub Actions workflow with no pip deps
beyond the standard library.

Usage:
    ADMIN_TOKEN=... python3 scripts/daily_health_check.py
    ADMIN_TOKEN=... GITHUB_TOKEN=... python3 scripts/daily_health_check.py --create-issue
    ADMIN_TOKEN=... python3 scripts/daily_health_check.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

API_BASE = "https://api.bainluck.com"
SENTRY_API = "https://us.sentry.io/api/0"


@dataclass
class CheckResult:
    name: str
    status: str  # "pass", "warn", "fail"
    value: str
    threshold: str
    priority: str = ""  # "p0" or "p1" when status == "fail"


@dataclass
class HealthReport:
    timestamp: str
    checks: list[CheckResult] = field(default_factory=list)
    api_reachable: bool = True

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)

    @property
    def worst_priority(self) -> str:
        priorities = [c.priority for c in self.checks if c.priority]
        if "p0" in priorities:
            return "p0"
        if "p1" in priorities:
            return "p1"
        return ""

    def summary_line(self) -> str:
        fails = sum(1 for c in self.checks if c.status == "fail")
        warns = sum(1 for c in self.checks if c.status == "warn")
        passes = sum(1 for c in self.checks if c.status == "pass")
        if fails:
            return f"UNHEALTHY — {fails} failed, {warns} warnings, {passes} passed"
        if warns:
            return f"DEGRADED — {warns} warnings, {passes} passed"
        return f"HEALTHY — {passes} checks passed"

    def to_markdown(self) -> str:
        icon = {"pass": "🟢", "warn": "🟡", "fail": "🔴"}
        lines = [f"## Health Check — {self.timestamp}", ""]
        lines.append(f"**{self.summary_line()}**")
        lines.append("")
        lines.append("| Status | Check | Value | Threshold |")
        lines.append("|--------|-------|-------|-----------|")
        for c in self.checks:
            lines.append(f"| {icon.get(c.status, '⚪')} | {c.name} | {c.value} | {c.threshold} |")
        return "\n".join(lines)


def _fetch_json(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
) -> tuple[dict | None, str]:
    """Fetch JSON from *url*, returning ``(data, error_reason)``.

    *error_reason* is an empty string on success.  On failure it holds a
    short diagnostic such as ``"timeout"`` or ``"403 Forbidden"`` so callers
    can surface it in the health report instead of a generic "UNREACHABLE".
    """
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), ""
    except urllib.error.HTTPError as exc:
        return None, f"{exc.code} {exc.reason}"
    except (TimeoutError, OSError) as exc:
        return None, f"timeout ({timeout}s)"
    except urllib.error.URLError as exc:
        return None, f"unreachable: {exc.reason}"


def check_api_reachable(report: HealthReport) -> None:
    result, err = _fetch_json(f"{API_BASE}/api/auth/health", timeout=10)
    if result is None or not result.get("healthy", False):
        report.api_reachable = False
        value = f"UNREACHABLE ({err})" if result is None else "UNHEALTHY"
        report.checks.append(CheckResult(
            name="API Reachable",
            status="fail",
            value=value,
            threshold="200 OK + healthy=true",
            priority="p0",
        ))
    else:
        report.checks.append(CheckResult(
            name="API Reachable",
            status="pass",
            value="healthy",
            threshold="200 OK",
        ))


def check_dashboard(report: HealthReport, admin_token: str) -> None:
    data, err = _fetch_json(f"{API_BASE}/api/admin/dashboard?secret={admin_token}", timeout=30)
    if data is None:
        report.checks.append(CheckResult(
            name="Admin Dashboard",
            status="fail",
            value=f"UNREACHABLE ({err})" if err else "UNREACHABLE",
            threshold="200 OK",
            priority="p1",
        ))
        return

    # Dashboard itself is reachable — always record this.
    report.checks.append(CheckResult(
        name="Admin Dashboard",
        status="pass",
        value="reachable",
        threshold="200 OK",
    ))

    # Quota
    quota = data.get("quota", {})
    remaining = quota.get("remaining")
    if remaining is not None:
        if remaining < 20_000:
            report.checks.append(CheckResult(
                name="Odds API Quota",
                status="fail",
                value=f"{remaining:,} remaining",
                threshold="> 50,000",
                priority="p0",
            ))
        elif remaining < 50_000:
            report.checks.append(CheckResult(
                name="Odds API Quota",
                status="fail",
                value=f"{remaining:,} remaining",
                threshold="> 50,000",
                priority="p1",
            ))
        elif remaining < 100_000:
            report.checks.append(CheckResult(
                name="Odds API Quota",
                status="warn",
                value=f"{remaining:,} remaining",
                threshold="> 100,000",
            ))
        else:
            report.checks.append(CheckResult(
                name="Odds API Quota",
                status="pass",
                value=f"{remaining:,} remaining",
                threshold="> 100,000",
            ))

    # DB connections
    db = data.get("database", {})
    connections = db.get("connections")
    if connections is not None:
        if connections > 18:
            report.checks.append(CheckResult(
                name="DB Connections",
                status="fail",
                value=str(connections),
                threshold="≤ 18",
                priority="p1",
            ))
        elif connections > 15:
            report.checks.append(CheckResult(
                name="DB Connections",
                status="warn",
                value=str(connections),
                threshold="≤ 15",
            ))
        else:
            report.checks.append(CheckResult(
                name="DB Connections",
                status="pass",
                value=str(connections),
                threshold="≤ 15",
            ))


def check_celery_queue(report: HealthReport, admin_token: str) -> None:
    data, err = _fetch_json(f"{API_BASE}/api/admin/celery-debug?secret={admin_token}", timeout=30)
    if data is None:
        report.checks.append(CheckResult(
            name="Celery Queue",
            status="warn",
            value=f"endpoint unreachable ({err})" if err else "endpoint unreachable",
            threshold="background < 50",
        ))
        return

    bg = data.get("queue_lengths", {}).get("background", 0)
    if bg > 50:
        report.checks.append(CheckResult(
            name="Celery Background Queue",
            status="fail",
            value=str(bg),
            threshold="< 50",
            priority="p1",
        ))
    elif bg > 25:
        report.checks.append(CheckResult(
            name="Celery Background Queue",
            status="warn",
            value=str(bg),
            threshold="< 25",
        ))
    else:
        report.checks.append(CheckResult(
            name="Celery Background Queue",
            status="pass",
            value=str(bg),
            threshold="< 25",
        ))


def check_backfill_coverage(report: HealthReport, admin_token: str) -> None:
    # This endpoint runs a heavy aggregate query; give it extra time.
    data, err = _fetch_json(
        f"{API_BASE}/api/admin/backfill-winners/status?secret={admin_token}",
        timeout=60,
    )
    if data is None:
        report.checks.append(CheckResult(
            name="is_winner Coverage",
            status="warn",
            value=f"endpoint unreachable ({err})" if err else "endpoint unreachable",
            threshold="> 90% all sources",
        ))
        return

    for source_info in data.get("sources", []):
        source = source_info.get("source", "?")
        resolved = source_info.get("resolved", 0)
        has_winner = source_info.get("has_winner", 0)
        if resolved == 0:
            continue
        coverage = round(100 * has_winner / resolved, 1)
        if coverage < 80:
            report.checks.append(CheckResult(
                name=f"is_winner: {source}",
                status="fail",
                value=f"{coverage}% ({has_winner}/{resolved})",
                threshold="> 90%",
                priority="p0",
            ))
        elif coverage < 90:
            report.checks.append(CheckResult(
                name=f"is_winner: {source}",
                status="fail",
                value=f"{coverage}% ({has_winner}/{resolved})",
                threshold="> 90%",
                priority="p1",
            ))
        elif coverage < 95:
            report.checks.append(CheckResult(
                name=f"is_winner: {source}",
                status="warn",
                value=f"{coverage}% ({has_winner}/{resolved})",
                threshold="> 95%",
            ))
        else:
            report.checks.append(CheckResult(
                name=f"is_winner: {source}",
                status="pass",
                value=f"{coverage}% ({has_winner}/{resolved})",
                threshold="> 95%",
            ))


def _sentry_24h_count(issue: dict) -> int:
    """Extract the 24-hour event count from a Sentry issue dict.

    When ``expand=stats`` is present, the response includes a
    ``stats`` dict keyed by stat period with bucketed time-series
    data.  We sum the ``24h`` buckets to get the true 24h count.

    Falls back to the ``count`` field (all-time) if stats are missing,
    which is still directionally useful but may over-count.
    """
    stats = issue.get("stats", {})
    buckets = stats.get("24h")
    if isinstance(buckets, list) and buckets:
        return sum(v for _ts, v in buckets)
    # Fallback: all-time count (may exceed the 24h threshold unfairly
    # but is better than silently ignoring the issue).
    return int(issue.get("count", "0"))


def check_sentry(report: HealthReport, sentry_token: str, sentry_org: str, sentry_project: str) -> None:
    url = (
        f"{SENTRY_API}/projects/{sentry_org}/{sentry_project}/issues/"
        f"?query=is:unresolved&statsPeriod=24h&expand=stats&limit=10&sort=freq"
    )
    data, err = _fetch_json(url, headers={"Authorization": f"Bearer {sentry_token}"})
    if data is None:
        report.checks.append(CheckResult(
            name="Sentry Errors",
            status="warn",
            value=f"API unreachable ({err})" if err else "API unreachable",
            threshold="< 100 events/24h per issue",
        ))
        return

    high_freq: list[tuple[dict, int]] = []
    for issue in data:
        count_24h = _sentry_24h_count(issue)
        if count_24h > 100:
            high_freq.append((issue, count_24h))

    if high_freq:
        names = "; ".join(
            f"{iss['shortId']}({cnt})" for iss, cnt in high_freq[:3]
        )
        report.checks.append(CheckResult(
            name="Sentry High-Frequency",
            status="fail",
            value=f"{len(high_freq)} issues: {names}",
            threshold="< 100 events/24h per issue",
            priority="p1",
        ))
    else:
        total = sum(_sentry_24h_count(i) for i in data)
        report.checks.append(CheckResult(
            name="Sentry Errors",
            status="pass",
            value=f"{total} events across {len(data)} issues (24h)",
            threshold="< 100 events/24h per issue",
        ))


def _github_request(method: str, path: str, *, data: dict = None, token: str) -> dict | None:
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode()
        return json.loads(text) if text else None


def create_or_update_issue(report: HealthReport, repo: str, token: str) -> str | None:
    title_prefix = "[Health Check]"
    search_q = f"repo:{repo} is:issue is:open in:title \"{title_prefix}\""
    search_url = f"/search/issues?q={urllib.parse.quote(search_q)}&per_page=1"
    search_result = _github_request("GET", search_url, token=token)

    priority = report.worst_priority
    labels = ["type:ops", "needs-agent"]
    if priority:
        labels.append(f"priority:{priority}")

    title = f"{title_prefix} {report.summary_line()}"
    body = report.to_markdown()

    existing = search_result.get("items", []) if search_result else []
    if existing:
        issue_number = existing[0]["number"]
        _github_request(
            "PATCH",
            f"/repos/{repo}/issues/{issue_number}",
            data={"title": title, "body": body, "labels": labels},
            token=token,
        )
        _github_request(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            data={"body": f"Updated {report.timestamp}\n\n{body}"},
            token=token,
        )
        return f"https://github.com/{repo}/issues/{issue_number}"
    else:
        result = _github_request(
            "POST",
            f"/repos/{repo}/issues",
            data={"title": title, "body": body, "labels": labels},
            token=token,
        )
        return result.get("html_url") if result else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily health check for Bain Luck")
    parser.add_argument("--create-issue", action="store_true", help="Create/update GitHub issue on failure")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--repo", default="alexander-bain/bainluck")
    args = parser.parse_args()

    admin_token = os.getenv("ADMIN_TOKEN", "")
    sentry_token = os.getenv("SENTRY_AUTH_TOKEN", "")
    sentry_org = os.getenv("SENTRY_ORG", "alexander-bain")
    sentry_project = os.getenv("SENTRY_PROJECT", "bainluck")
    github_token = os.getenv("GITHUB_TOKEN", "")

    report = HealthReport(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    check_api_reachable(report)

    if report.api_reachable and admin_token:
        check_dashboard(report, admin_token)
        check_celery_queue(report, admin_token)
        check_backfill_coverage(report, admin_token)

    if sentry_token:
        check_sentry(report, sentry_token, sentry_org, sentry_project)

    if args.json:
        out = {
            "timestamp": report.timestamp,
            "summary": report.summary_line(),
            "has_failures": report.has_failures,
            "checks": [
                {"name": c.name, "status": c.status, "value": c.value, "threshold": c.threshold}
                for c in report.checks
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(report.to_markdown())

    # Write GitHub Actions step summary if available
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(report.to_markdown() + "\n")

    if report.has_failures and args.create_issue and github_token:
        url = create_or_update_issue(report, args.repo, github_token)
        if url:
            print(f"\nIssue: {url}")

    sys.exit(1 if report.has_failures else 0)


if __name__ == "__main__":
    main()
