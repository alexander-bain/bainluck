#!/usr/bin/env python3
"""Render a bounded, timestamped progress/your-turn snapshot from exact issues.

Run on a work transition with explicit issue numbers; no timer, inference or
board-wide mutation. This creates a view, never a competing priority record.
A failed read leaves the previous output untouched (with its original timestamp).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from claim_issue import read_issue


def _cell(value: str | None) -> str:
    return (
        str(value or "Not recorded")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render(issues: list[dict], as_of: str) -> str:
    rows = sorted(issues, key=lambda issue: issue["number"])
    if len({i["number"] for i in rows}) != len(rows):
        raise ValueError("Duplicate issue numbers in snapshot")
    waiting = [
        i
        for i in rows
        if i["state"] == "OPEN"
        and (i["fields"].get("Status") == "Needs User" or "needs-user" in i["labels"])
    ]
    lines = [
        "# Work progress",
        "",
        f"Read from GitHub: {_cell(as_of)}",
        "",
        "Scope: only the issues listed below. Status and delivery stage are separate; missing fields are not inferred.",
        "",
        "## Waiting on you",
        "",
    ]
    if not waiting:
        lines += [
            "No listed open issue is marked Needs User. This does not cover issues outside this snapshot.",
            "",
        ]
    else:
        for issue in waiting:
            lines += [
                f"- [#{issue['number']}]({issue['url']}): {_cell(issue['fields'].get('Next step'))}"
            ]
        lines += [""]
    lines += [
        "## Progress",
        "",
        "| Issue | Issue state | Work status | Delivery stage | Owner | Next step |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for issue in rows:
        fields = issue["fields"]
        lines.append(
            f"| [#{issue['number']}]({issue['url']}) {_cell(issue['title'])} | "
            + " | ".join(
                _cell(value)
                for value in [
                    issue["state"],
                    fields.get("Status"),
                    fields.get("Delivery stage"),
                    fields.get("Delivery owner"),
                    fields.get("Next step"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "issues", type=int, nargs="*", help="Exact issue numbers to include"
    )
    parser.add_argument(
        "--fixture", type=Path, help="Offline list of read_issue snapshots"
    )
    parser.add_argument("--as-of", help="Snapshot timestamp; mandatory with --fixture")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Generated view; do not target a hand-maintained file",
    )
    args = parser.parse_args()
    if args.fixture and (args.issues or not args.as_of):
        parser.error(
            "--fixture needs --as-of and cannot be combined with issue numbers"
        )
    if not args.fixture and not args.issues:
        parser.error("Specify issues or --fixture")
    issues = (
        json.loads(args.fixture.read_text())
        if args.fixture
        else [read_issue(n) for n in sorted(set(args.issues))]
    )
    as_of = args.as_of or datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = render(issues, as_of)
    # Complete all reads/rendering before replacing the old view.
    output = args.output.resolve()
    with tempfile.NamedTemporaryFile(
        mode="w", dir=output.parent, prefix=".issue-progress-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Wrote {len(issues)} issues to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
