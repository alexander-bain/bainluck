#!/usr/bin/env python3
"""Audit drift between docs/backlog.md and the GitHub execution queue.

This script is intentionally read-only. It reports mismatches between backlog
issue references, open GitHub issues, labels, and Project status, but never
creates, closes, labels, or comments on issues.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REPO = "alexander-bain/bainluck"
DEFAULT_BACKLOG = Path("docs/backlog.md")
MUTATION_VERBS = {"create", "edit", "close", "reopen", "comment", "delete", "label"}


@dataclass(frozen=True)
class BacklogRef:
    issue: int
    status: str
    line_no: int
    text: str


@dataclass(frozen=True)
class DriftFinding:
    severity: str
    issue: int | None
    message: str
    detail: str | None = None


def parse_backlog(path: Path) -> dict[int, list[BacklogRef]]:
    refs: dict[int, list[BacklogRef]] = {}
    status_re = re.compile(r"\[(idea|ready|active|blocked|shipped)\]")
    issue_re = re.compile(r"(?:issues/|#)(\d+)\b")

    for line_no, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        status_match = status_re.search(line)
        if not status_match:
            continue
        issues = {int(match.group(1)) for match in issue_re.finditer(line)}
        if not issues:
            continue
        status = status_match.group(1)
        for issue in sorted(issues):
            refs.setdefault(issue, []).append(
                BacklogRef(
                    issue=issue, status=status, line_no=line_no, text=line.strip()
                )
            )
    return refs


def load_issues_from_fixture(path: Path) -> dict[int, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "issues" in data:
        data = data["issues"]
    if not isinstance(data, list):
        raise SystemExit(
            "Issue fixture must be a JSON list or an object with an 'issues' list"
        )
    return {int(issue["number"]): issue for issue in data}


def load_issues_from_github(repo: str, limit: int) -> dict[int, dict[str, Any]]:
    fields = [
        "number",
        "title",
        "state",
        "stateReason",
        "labels",
        "projectItems",
        "url",
    ]
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--limit",
        str(limit),
        "--json",
        ",".join(fields),
    ]
    proc = subprocess.run(
        cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    issues = json.loads(proc.stdout or "[]")
    return {int(issue["number"]): issue for issue in issues}


def issue_labels(issue: dict[str, Any]) -> set[str]:
    labels = set()
    for label in issue.get("labels") or []:
        if isinstance(label, str):
            labels.add(label)
        elif isinstance(label, dict) and label.get("name"):
            labels.add(str(label["name"]))
    return labels


def project_statuses(issue: dict[str, Any]) -> set[str]:
    statuses: set[str] = set()
    for item in issue.get("projectItems") or []:
        status = item.get("status") if isinstance(item, dict) else None
        if isinstance(status, str) and status:
            statuses.add(status)
        elif isinstance(status, dict) and status.get("name"):
            statuses.add(str(status["name"]))

        for field in item.get("fieldValues") or []:
            if not isinstance(field, dict):
                continue
            if field.get("field", {}).get("name") == "Status" and field.get("name"):
                statuses.add(str(field["name"]))
    return statuses


def is_open(issue: dict[str, Any]) -> bool:
    return str(issue.get("state", "")).upper() == "OPEN"


def should_ignore_open_issue(labels: set[str], ignored_labels: set[str]) -> bool:
    return bool(labels & ignored_labels)


def add_status_findings(
    findings: list[DriftFinding],
    issue_number: int,
    ref: BacklogRef,
    issue: dict[str, Any],
) -> None:
    labels = issue_labels(issue)
    statuses = project_statuses(issue)
    state = str(issue.get("state", "")).upper()

    if ref.status == "shipped":
        if state == "OPEN":
            findings.append(
                DriftFinding(
                    "warn",
                    issue_number,
                    "Backlog marks shipped but GitHub issue is still open",
                    f"{ref.line_no}: {ref.text}",
                )
            )
        return

    if state != "OPEN":
        findings.append(
            DriftFinding(
                "warn",
                issue_number,
                f"Backlog marks {ref.status} but GitHub issue is {state.lower()}",
                f"{ref.line_no}: {ref.text}",
            )
        )
        return

    if (
        ref.status == "active"
        and "in-progress" not in labels
        and "In Progress" not in statuses
    ):
        findings.append(
            DriftFinding(
                "warn",
                issue_number,
                "Backlog marks active but issue is not labeled/projected In Progress",
                f"labels={sorted(labels)} project_statuses={sorted(statuses)}",
            )
        )
    elif (
        ref.status == "ready"
        and "needs-agent" not in labels
        and "Ready" not in statuses
    ):
        findings.append(
            DriftFinding(
                "info",
                issue_number,
                "Backlog marks ready but issue lacks needs-agent label and Ready project status",
                f"labels={sorted(labels)} project_statuses={sorted(statuses)}",
            )
        )
    elif (
        ref.status == "blocked"
        and not ({"blocked", "needs-user"} & labels)
        and "Needs User" not in statuses
    ):
        findings.append(
            DriftFinding(
                "warn",
                issue_number,
                "Backlog marks blocked but issue lacks blocked/needs-user label or Needs User project status",
                f"labels={sorted(labels)} project_statuses={sorted(statuses)}",
            )
        )


def audit(
    backlog_refs: dict[int, list[BacklogRef]],
    issues: dict[int, dict[str, Any]],
    *,
    ignored_labels: set[str],
) -> list[DriftFinding]:
    findings: list[DriftFinding] = []

    for issue_number, refs in sorted(backlog_refs.items()):
        if len(refs) > 1:
            locations = ", ".join(f"line {ref.line_no} [{ref.status}]" for ref in refs)
            findings.append(
                DriftFinding(
                    "info",
                    issue_number,
                    "Issue is referenced from multiple backlog lines",
                    locations,
                )
            )

        issue = issues.get(issue_number)
        if not issue:
            findings.append(
                DriftFinding(
                    "warn",
                    issue_number,
                    "Backlog references an issue missing from fetched GitHub data",
                    "Increase --limit if this is an older issue.",
                )
            )
            continue
        add_status_findings(findings, issue_number, refs[0], issue)

    for issue_number, issue in sorted(issues.items()):
        labels = issue_labels(issue)
        if not is_open(issue) or should_ignore_open_issue(labels, ignored_labels):
            continue

        if issue_number not in backlog_refs:
            findings.append(
                DriftFinding(
                    "warn",
                    issue_number,
                    "Open non-ignored issue is not referenced from docs/backlog.md",
                    issue.get("title"),
                )
            )

        if not any(label.startswith("area:") for label in labels):
            findings.append(
                DriftFinding(
                    "info",
                    issue_number,
                    "Open issue is missing an area:* label",
                    issue.get("title"),
                )
            )
        if not any(label.startswith("type:") for label in labels):
            findings.append(
                DriftFinding(
                    "info",
                    issue_number,
                    "Open issue is missing a type:* label",
                    issue.get("title"),
                )
            )

    return findings


def format_findings(findings: list[DriftFinding]) -> str:
    if not findings:
        return "No backlog/GitHub sync drift found."

    lines = ["Backlog/GitHub sync audit findings:"]
    for finding in findings:
        prefix = f"[{finding.severity}]"
        issue = f" #{finding.issue}" if finding.issue is not None else ""
        lines.append(f"- {prefix}{issue} {finding.message}")
        if finding.detail:
            lines.append(f"  {finding.detail}")
    return "\n".join(lines)


def guard_read_only(argv: list[str]) -> None:
    lowered = {arg.lower() for arg in argv}
    forbidden = sorted(MUTATION_VERBS & lowered)
    if forbidden:
        raise SystemExit(
            "This audit is read-only; mutation-like arguments are not supported: "
            + ", ".join(forbidden)
        )


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    guard_read_only(raw_argv)

    parser = argparse.ArgumentParser(
        description="Read-only audit for drift between docs/backlog.md and GitHub issues.",
        epilog=(
            "Examples:\n"
            "  python3 scripts/audit_backlog_github_sync.py --dry-run\n"
            "  python3 scripts/audit_backlog_github_sync.py --issue-fixture issues.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backlog", type=Path, default=DEFAULT_BACKLOG, help="Backlog markdown path"
    )
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help="GitHub repo in OWNER/NAME form"
    )
    parser.add_argument(
        "--limit", type=int, default=300, help="Maximum issues to fetch from gh"
    )
    parser.add_argument(
        "--ignore-label",
        action="append",
        default=["alert-intake"],
        help="Open issue label to exclude from backlog-parent checks; repeatable",
    )
    parser.add_argument(
        "--issue-fixture",
        type=Path,
        help="Read gh-compatible issue JSON from a local fixture instead of calling GitHub",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for normal operation; included to make the advisory behavior explicit",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit 1 when warning-level drift is found; default is advisory exit 0",
    )
    args = parser.parse_args(raw_argv)

    if not args.backlog.exists():
        raise SystemExit(f"Backlog file not found: {args.backlog}")

    backlog_refs = parse_backlog(args.backlog)
    if args.issue_fixture:
        issues = load_issues_from_fixture(args.issue_fixture)
        source = str(args.issue_fixture)
    else:
        issues = load_issues_from_github(args.repo, args.limit)
        source = f"GitHub repo {args.repo}"

    findings = audit(backlog_refs, issues, ignored_labels=set(args.ignore_label or []))
    print(f"Backlog refs: {len(backlog_refs)} issue(s)")
    print(f"Issue source: {source} ({len(issues)} issue(s))")
    print(format_findings(findings))

    if args.fail_on_warn and any(finding.severity == "warn" for finding in findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
