#!/usr/bin/env python3
"""One-shot backfill: give every RAIL-FILED open issue the ``priority:*`` it was
born without.

Q434 closed the forward half — every filing rail now derives a priority at creation
time. This closes the backward half for the issues the rails already filed, using the
SAME canonical mapping (``app.utils.issue_labels``), so the board's history agrees
with its future.

SCOPE IS DELIBERATELY NARROW, and the narrowness is the point.
Only issues carrying a rail SOURCE label are touched:

    alert-intake · bug-report · manus-digest · ci-failure · github-actions ·
    sentry · prod-error

A card with no source label was filed by a person or a lane. It is the same lint
violation, but a mapping cannot derive its priority — that needs a triage judgement,
and stamping P2 on 37 human-filed cards would convert "un-triaged" into
"triaged as P2", which is worse than the violation. Those are reported by this script
under ``skipped_not_rail_filed`` and left alone. Measured on 2026-08-28: 41 open
issues missing a priority, of which **4** are rail-filed.

DERIVATION, per issue, most specific first:
  1. a Browser-audit card (``alert-intake`` + a ``Browser audit:`` title, or
     ``program:ux`` + the sweep fingerprint marker) → P3, the `BOARD-TAXONOMY.md`
     family default;
  2. a ``manus-digest`` roll-up → P3 (digest family);
  3. anything else → P2, the ratified alert-intake birth priority (Alex 2026-07-27:
     "priority is earned at triage, not stamped at birth").

It NEVER removes or replaces a label, never closes, never comments, never edits a
body, and never touches a closed issue. Adding a label is the whole mutation.

Usage
-----
    python3 backend/scripts/backfill_rail_issue_priorities.py            # DRY RUN
    python3 backend/scripts/backfill_rail_issue_priorities.py --apply
    python3 backend/scripts/backfill_rail_issue_priorities.py --apply --limit 5

Dry run is the default and prints the exact per-issue plan plus a before/after
census. ``--apply`` re-reads each issue immediately before writing, so a label added
by a human between the plan and the write is not clobbered.

Needs ``GITHUB_TOKEN`` (or ``GH_TOKEN``) with ``issues: write``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.issue_labels import (  # noqa: E402
    DEFAULT_PRIORITY,
    PRIORITY_PREFIX,
    priority_label,
)

REPO = os.environ.get("BAINLUCK_REPO", "alexander-bain/bainluck")
API = "https://api.github.com"

# A label that identifies an issue as machine-filed. These are the bare SOURCE
# labels `BOARD-TAXONOMY.md` names ("written by filing rails — do not rename, rails
# hardcode them"), plus the two Sentry-intake companions.
RAIL_SOURCE_LABELS = {
    "alert-intake",
    "bug-report",
    "manus-digest",
    "ci-failure",
    "github-actions",
    "sentry",
    "prod-error",
}

BROWSER_AUDIT_TITLE_PREFIX = "Browser audit:"
BROWSER_SWEEP_MARKER = "browser-sweep-fingerprint"


def _request(method: str, path: str, token: str, data: dict | None = None):
    url = path if path.startswith("http") else f"{API}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"GitHub {method} {url} → {exc.code}: {detail}")


def label_names(issue: dict) -> list[str]:
    out = []
    for lab in issue.get("labels") or []:
        if isinstance(lab, dict) and lab.get("name"):
            out.append(lab["name"])
        elif isinstance(lab, str):
            out.append(lab)
    return out


def fetch_open_issues(token: str) -> list[dict]:
    """Every OPEN issue, paginated to exhaustion.

    Pagination is not a detail here: the first census of this defect ran with
    ``--limit 400`` against a 735-issue board and reported 24 missing priorities
    instead of 41, which read as "the directive's number is stale" rather than "the
    read was truncated". A partial read of a completeness check is a wrong answer
    wearing a right answer's shape, so this loops until a short page arrives.
    """
    issues: list[dict] = []
    page = 1
    while True:
        batch = (
            _request(
                "GET",
                f"/repos/{REPO}/issues?state=open&per_page=100&page={page}",
                token,
            )
            or []
        )
        if not batch:
            break
        issues.extend(i for i in batch if "pull_request" not in i)
        if len(batch) < 100:
            break
        page += 1
        if page > 50:  # 5,000 issues — a runaway guard, not an expected bound
            raise RuntimeError("open-issue pagination exceeded 50 pages; refusing")
    return issues


def is_browser_audit(issue: dict, labels: set[str]) -> bool:
    title = str(issue.get("title") or "")
    if title.startswith(BROWSER_AUDIT_TITLE_PREFIX):
        return True
    return "program:ux" in labels and BROWSER_SWEEP_MARKER in str(
        issue.get("body") or ""
    )


def derive_priority(issue: dict, labels: set[str]) -> tuple[str, str]:
    """(priority label, the reason it was chosen) for one rail-filed issue."""
    if is_browser_audit(issue, labels):
        return priority_label(family="browser-audit"), "browser-audit family default"
    if "manus-digest" in labels:
        return priority_label(family="digest"), "digest family default"
    return DEFAULT_PRIORITY, "ratified alert-intake birth priority"


def plan(issues: list[dict]) -> tuple[list[dict], list[dict]]:
    """(actionable, skipped_not_rail_filed) among open issues missing a priority."""
    actionable, skipped = [], []
    for issue in issues:
        labels = set(label_names(issue))
        if "taxonomy-exempt" in labels:
            continue
        if any(name.startswith(PRIORITY_PREFIX) for name in labels):
            continue
        row = {
            "number": issue["number"],
            "title": str(issue.get("title") or "")[:70],
            "labels": sorted(labels),
        }
        if not (labels & RAIL_SOURCE_LABELS):
            skipped.append(row)
            continue
        prio, why = derive_priority(issue, labels)
        row["priority"] = prio
        row["reason"] = why
        actionable.append(row)
    return actionable, skipped


def apply_one(row: dict, token: str) -> str:
    """Add the derived priority to one issue. Re-reads first so a label a human added
    since the plan was built wins — the write is additive either way, but a re-read
    keeps the report honest about what actually changed."""
    fresh = _request("GET", f"/repos/{REPO}/issues/{row['number']}", token)
    current = set(label_names(fresh or {}))
    if any(name.startswith(PRIORITY_PREFIX) for name in current):
        return "already_prioritized"
    _request(
        "POST",
        f"/repos/{REPO}/issues/{row['number']}/labels",
        token,
        {"labels": [row["priority"]]},
    )
    return "labeled"


def build_parser() -> argparse.ArgumentParser:
    """Split out so a test can pin "dry run is the default" behaviourally. The first
    version of that test read the argparse call out of the source and broke the
    moment black reflowed it — a source-string assertion about behaviour that the
    behaviour itself can answer."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually add the labels (default is a dry run)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="cap the number of issues mutated (0 = no cap)",
    )
    return ap


def main() -> int:
    args = build_parser().parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN (or GH_TOKEN) is required", file=sys.stderr)
        return 2

    issues = fetch_open_issues(token)
    actionable, skipped = plan(issues)

    print(
        f"BEFORE — {len(issues)} open issues; "
        f"{len(actionable) + len(skipped)} missing priority:* "
        f"({len(actionable)} rail-filed, {len(skipped)} not rail-filed)"
    )
    print()
    print("RAIL-FILED — will be labeled:")
    for row in actionable:
        print(f"  #{row['number']:<6} → {row['priority']:<12} ({row['reason']})")
        print(f"          {row['title']}")
    if not actionable:
        print("  (none)")
    print()
    print(
        f"NOT RAIL-FILED — left alone, they need a human triage pass ({len(skipped)}):"
    )
    for row in skipped:
        print(f"  #{row['number']:<6} {row['title']}")
    if not skipped:
        print("  (none)")

    if not args.apply:
        print()
        print("DRY RUN — nothing written. Re-run with --apply.")
        return 0

    targets = actionable[: args.limit] if args.limit else actionable
    if args.limit and len(actionable) > args.limit:
        print()
        print(
            f"NOTE: --limit {args.limit} caps this run; "
            f"{len(actionable) - args.limit} rail-filed issue(s) NOT processed."
        )

    print()
    results = {"labeled": 0, "already_prioritized": 0, "failed": 0}
    for row in targets:
        try:
            outcome = apply_one(row, token)
        except Exception as exc:
            outcome = "failed"
            print(f"  #{row['number']} FAILED: {exc}")
        results[outcome] = results.get(outcome, 0) + 1
        if outcome != "failed":
            print(f"  #{row['number']} {outcome} ({row.get('priority')})")

    after = fetch_open_issues(token)
    after_actionable, after_skipped = plan(after)
    print()
    print(
        f"AFTER  — {len(after)} open issues; "
        f"{len(after_actionable) + len(after_skipped)} missing priority:* "
        f"({len(after_actionable)} rail-filed, {len(after_skipped)} not rail-filed)"
    )
    print(f"applied: {results}")
    return 1 if results.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
