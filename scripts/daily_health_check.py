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
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

API_BASE = "https://api.bainluck.com"
SENTRY_API = "https://us.sentry.io/api/0"

# --- Daily Health Check issue-filing ownership (Queue 276) ---------------------
# The filer identifies its OWN canonical card by a stable, versioned hidden body
# marker — NOT by fuzzy-matching ``[Health Check]`` in a title. The old title
# search (GitHub ``in:title`` + ``per_page=1``) hijacked #1477, whose title merely
# CONTAINED the ``[Health Check]`` substring, replacing its title/body/labels.
HEALTH_MARKER = "bainluck-health-check-filer:v1"
HEALTH_MARKER_LINE = (
    f"<!-- {HEALTH_MARKER} · canonical daily production health card · "
    "the Daily Health Check workflow (scripts/daily_health_check.py) updates ONLY "
    "the issue bearing this marker · do not remove -->"
)
TITLE_PREFIX = "[Health Check]"
# Explicit, bounded bootstrap pin: the pre-marker canonical card (#869). On the
# first post-fix run there are zero marker owners, so the filer stamps the marker
# into THIS issue number only — never a title lookalike. Set the env to "" / "0"
# to permit a genuine cold-start create (no canonical card exists yet).
CANONICAL_ISSUE_ENV = "HEALTH_CHECK_CANONICAL_ISSUE"
DEFAULT_CANONICAL_ISSUE = 869
# The only labels the filer OWNS and may ADD on merge. It never removes a label
# and never replaces area:* / type:* (beyond additively ensuring type:ops) /
# routing / human priority — see ``_merge_labels``.
FILER_LIFECYCLE_LABELS = ("type:ops", "needs-agent")
# Bounded, strongly-consistent open-issue scan (oldest-first so the stable
# canonical card is always inside the window). A full final page ⇒ TRUNCATED ⇒
# fail closed, never a false "empty".
_LIST_MAX_PAGES = 10
_LIST_PER_PAGE = 100


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
    bearer_token: str | None = None,
) -> tuple[dict | None, str]:
    """Fetch JSON from *url*, returning ``(data, error_reason)``.

    *error_reason* is an empty string on success.  On failure it holds a
    short diagnostic such as ``"timeout"`` or ``"403 Forbidden"`` so callers
    can surface it in the health report instead of a generic "UNREACHABLE".
    """
    merged = dict(headers or {})
    if bearer_token:
        merged["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(url, headers=merged)
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
    data, err = _fetch_json(f"{API_BASE}/api/admin/dashboard", timeout=30, bearer_token=admin_token)
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
    data, err = _fetch_json(f"{API_BASE}/api/admin/celery-debug", timeout=30, bearer_token=admin_token)
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
        f"{API_BASE}/api/admin/backfill-winners/status",
        timeout=60,
        bearer_token=admin_token,
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


def _declares_health_marker(body: str | None) -> bool:
    """True only when ``HEALTH_MARKER`` appears on a REAL body line — not inside a
    fenced code block, blockquote (``>``), indented code block, or Markdown table
    row. Mirrors ``sentinel_filing.declared_fingerprints`` so a cleanup/meta issue
    that merely QUOTES the marker (e.g. #1477's forensic archive) is never a
    phantom owner. This is the ONE ownership key — no title fallback."""
    in_fence = False
    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):  # blockquote — a quote, not ownership
            continue
        if raw.startswith("    ") or raw.startswith("\t"):  # indented code
            continue
        if stripped.startswith("|"):  # table row — evidence, not ownership
            continue
        if HEALTH_MARKER in raw:
            return True
    return False


def _label_names(issue: dict) -> list[str]:
    """Existing label names on an issue dict (REST list shape: list of
    ``{"name": ...}``; tolerates bare strings for test fixtures)."""
    out: list[str] = []
    for lab in issue.get("labels", []) or []:
        if isinstance(lab, dict) and lab.get("name"):
            out.append(lab["name"])
        elif isinstance(lab, str):
            out.append(lab)
    return out


def _merge_labels(existing: list[str], priority: str) -> list[str]:
    """Additive union: preserve EVERY existing label (``area:*``, ``type:*``,
    routing, human ``priority:*``, ``parked`` …) and add only the filer's owned
    lifecycle labels when absent. Priority is SEEDED only when the issue carries
    no ``priority:*`` label at all, so a human's priority is never overridden or
    duplicated. NEVER removes a label — this is the r306 fix (PATCH must merge,
    not replace)."""
    merged = list(existing)
    seen = set(existing)
    for lab in FILER_LIFECYCLE_LABELS:
        if lab not in seen:
            merged.append(lab)
            seen.add(lab)
    if priority and not any(l.startswith("priority:") for l in existing):
        merged.append(f"priority:{priority}")
    return merged


def _list_open_issues(repo: str, token: str) -> tuple[list[dict], str | None, bool]:
    """Strongly-consistent REST list of OPEN issues (oldest-first so the stable
    canonical card is always inside the bounded window), NOT the eventually-
    consistent ``/search`` index the old filer used. Returns
    ``(issues, error, truncated)``. A failed read yields ``error`` set; a full
    final page at the cap yields ``truncated=True`` — either way the caller fails
    closed and never files or patches blind (the sentinel-rail C37 contract)."""
    issues: list[dict] = []
    last_full = False
    for page in range(1, _LIST_MAX_PAGES + 1):
        path = (
            f"/repos/{repo}/issues?state=open&per_page={_LIST_PER_PAGE}"
            f"&page={page}&sort=created&direction=asc"
        )
        try:
            batch = _github_request("GET", path, token=token)
        except Exception as exc:  # HTTP/timeout/parse — treat as UNKNOWN
            return issues, f"open-issue list failed: {str(exc)[:160]}", False
        if not isinstance(batch, list) or not batch:
            last_full = False
            break
        issues.extend(i for i in batch if isinstance(i, dict) and "pull_request" not in i)
        if len(batch) < _LIST_PER_PAGE:
            last_full = False
            break
        last_full = True
    if last_full:
        return issues, f"open-issue list truncated at {_LIST_MAX_PAGES} pages", True
    return issues, None, False


def _update_owner(
    issue: dict,
    *,
    title: str,
    body: str,
    priority: str,
    comment: str,
    repo: str,
    token: str,
) -> str:
    """PATCH the canonical card in place, merging labels (never replacing), then
    comment. Skips the write only when the card already declares the marker AND
    the title is unchanged — so a bootstrap PATCH (marker not yet present) always
    runs, and a steady-state run with an unchanged report is a true no-op."""
    number = issue["number"]
    url = f"https://github.com/{repo}/issues/{number}"
    already_owned = _declares_health_marker(issue.get("body"))
    if already_owned and issue.get("title", "") == title:
        print(f"Health check unchanged ({title}); skipping update of #{number}")
        return url
    labels = _merge_labels(_label_names(issue), priority)
    _github_request(
        "PATCH",
        f"/repos/{repo}/issues/{number}",
        data={"title": title, "body": body, "labels": labels},
        token=token,
    )
    _github_request(
        "POST",
        f"/repos/{repo}/issues/{number}/comments",
        data={"body": comment},
        token=token,
    )
    return url


def create_or_update_issue(report: HealthReport, repo: str, token: str) -> str | None:
    """Reconcile the single canonical ``[Health Check]`` card by stable body
    marker, fail-closed on any ambiguity.

    Ownership resolution (no title fallback — that is what hijacked #1477):
      * **1 marker owner**  → update it in place (merge labels).
      * **>1 marker owners** → AMBIGUOUS → no-op with a clear error (never PATCH
        an arbitrary issue).
      * **0 marker owners**  → bootstrap the explicit pin (#869 by NUMBER, gated
        on the ``[Health Check]`` title as a safety check) if it is open; else, if
        the pin is unset, cold-start create; else fail closed (pin set but not an
        open health card → refuse to create a dup or patch a lookalike).

    A failed/truncated open-issue read is an explicit UNKNOWN no-op."""
    priority = report.worst_priority or "p1"
    title = f"{TITLE_PREFIX} {report.summary_line()}"
    body = report.to_markdown() + "\n\n" + HEALTH_MARKER_LINE
    comment = f"Updated {report.timestamp}\n\n{report.to_markdown()}"

    issues, err, truncated = _list_open_issues(repo, token)
    if err:
        print(f"Health filer: open-issue read unavailable ({err}); no-op (fail-closed)")
        return None

    owners = [i for i in issues if _declares_health_marker(i.get("body"))]
    if len(owners) > 1:
        nums = ", ".join(f"#{i.get('number')}" for i in owners)
        print(
            f"Health filer: AMBIGUOUS — {len(owners)} open issues declare the "
            f"marker ({nums}); no-op (fail-closed). Reconcile to a single canonical card."
        )
        return None

    if len(owners) == 1:
        return _update_owner(
            owners[0], title=title, body=body, priority=priority,
            comment=comment, repo=repo, token=token,
        )

    # Zero marker owners → bootstrap the explicit pin, or cold-start create.
    pin_raw = os.getenv(CANONICAL_ISSUE_ENV)
    if pin_raw is None:
        pin_num = DEFAULT_CANONICAL_ISSUE
    else:
        pin_raw = pin_raw.strip()
        pin_num = int(pin_raw) if pin_raw.isdigit() else 0

    if pin_num:
        candidates = [
            i for i in issues
            if i.get("number") == pin_num
            and str(i.get("title") or "").startswith(TITLE_PREFIX)
        ]
        if len(candidates) == 1:
            print(f"Health filer: bootstrapping canonical marker into #{pin_num}")
            return _update_owner(
                candidates[0], title=title, body=body, priority=priority,
                comment=comment, repo=repo, token=token,
            )
        print(
            f"Health filer: canonical pin #{pin_num} not found as an open "
            f"health card ({len(candidates)} candidates); no-op (fail-closed). "
            f"Unset {CANONICAL_ISSUE_ENV} to allow a cold-start create."
        )
        return None

    # Pin explicitly unset → genuine cold start → create a fresh canonical card.
    labels = list(FILER_LIFECYCLE_LABELS)
    if priority:
        labels.append(f"priority:{priority}")
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
