"""Format the nightly iPhone suite failure issue body/comment with night-over-night diff."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Sequence


_MARKER_RE = re.compile(
    r"<!--\s*nightly-iphone-failures:\s*(\{.*?\})\s*-->", re.DOTALL
)
_DETAILS_ITEM_RE = re.compile(r"^- `([^`]+)`(?:\s*\(timed out\))?\s*$", re.MULTILINE)


def _format_short_date(run_date: str) -> str:
    try:
        dt = datetime.strptime(run_date.strip(), "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}"
    except ValueError:
        return run_date


def extract_prior_failures(
    issue_bodies: Sequence[str],
) -> tuple[set[str] | None, bool]:
    """Return the latest complete baseline failure set from prior issue text.

    Prefers the newest entry marked ``"complete": true`` so a crash before the
    minimum test floor does not make the following full night look like a wall
    of new failures. Falls back to the newest legacy ``<details>`` list or
    incomplete marker if no complete baseline exists.
    """
    fallback: tuple[set[str], bool] | None = None
    for body in reversed(list(issue_bodies)):
        if not body:
            continue
        match = _MARKER_RE.search(body)
        if match:
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                names = {
                    str(n).strip()
                    for n in (
                        list(payload.get("failed_tests") or [])
                        + list(payload.get("timed_out_tests") or [])
                    )
                    if str(n).strip()
                }
                complete = bool(payload.get("complete", False))
                if complete:
                    return names, True
                if fallback is None:
                    fallback = (names, False)
                continue
        legacy_names = {m.group(1).strip() for m in _DETAILS_ITEM_RE.finditer(body)}
        if legacy_names and fallback is None:
            fallback = (legacy_names, True)
    if fallback is not None:
        return fallback
    return None, False


def _format_name_with_status(name: str, timed_out_set: set[str]) -> str:
    return f"`{name}` (timed out)" if name in timed_out_set else f"`{name}`"


def format_issue_comment(
    receipt: dict[str, Any] | None,
    *,
    run_date: str,
    sha: str,
    run_url: str,
    prior_bodies: Sequence[str] = (),
) -> str:
    """Build the markdown body/comment for ``Failed check: nightly iPhone test suite``."""
    date_label = _format_short_date(run_date)

    if receipt is None:
        lead_line = f"{date_label}: 0 run (receipt.json missing), 0 failed, 0 timed out"
        failed_tests: list[str] = []
        timed_out_tests: list[str] = []
        below_min = True
        min_tests = 0
        min_tests_reason = None
        complete = False
    else:
        tests = int(receipt.get("tests") or 0)
        failed_tests = [str(n) for n in (receipt.get("failed_tests") or []) if str(n).strip()]
        timed_out_tests = [
            str(n) for n in (receipt.get("timed_out_tests") or []) if str(n).strip()
        ]
        failed_count = int(receipt.get("failed", len(failed_tests)))
        timed_out_count = int(receipt.get("timed_out", len(timed_out_tests)))
        below_min = bool(receipt.get("below_min_tests", False))
        min_tests = int(receipt.get("min_tests") or 0)
        min_tests_reason = receipt.get("min_tests_reason")
        complete = not below_min
        if below_min and min_tests > 0:
            lead_line = (
                f"{date_label}: {tests:,} run (below {min_tests:,} floor), "
                f"{failed_count:,} failed, {timed_out_count:,} timed out"
            )
        else:
            lead_line = (
                f"{date_label}: {tests:,} run, "
                f"{failed_count:,} failed, {timed_out_count:,} timed out"
            )

    timed_out_set = set(timed_out_tests)
    current_set = set(failed_tests) | timed_out_set
    prior_set, _ = extract_prior_failures(prior_bodies)

    lines: list[str] = [lead_line]
    new_failures: list[str] = []
    now_passing: list[str] = []
    if prior_set is None:
        lines.append("first night")
    else:
        new_failures = sorted(current_set - prior_set)
        now_passing = sorted(prior_set - current_set)
        if below_min:
            floor_note = (
                f"incomplete run below {min_tests:,} floor"
                if min_tests > 0
                else "incomplete run"
            )
            lines.append(
                f"{len(new_failures):,} new ({floor_note}; unexecuted tests not counted as now passing)"
            )
        else:
            lines.append(f"{len(new_failures):,} new, {len(now_passing):,} now pass")

    if new_failures:
        lines.append("")
        lines.append("**New failures:**")
        for name in new_failures:
            lines.append(f"- {_format_name_with_status(name, timed_out_set)}")

    if now_passing and not below_min:
        lines.append("")
        lines.append("**Now passing:**")
        for name in now_passing:
            lines.append(f"- `{name}`")

    lines.append("")
    lines.append(f"- Commit: `{sha}` · Run: {run_url}")
    if min_tests_reason:
        lines.append(f"- Floor check: {min_tests_reason}")

    ordered_all = sorted(failed_tests) + [
        name for name in sorted(timed_out_tests) if name not in set(failed_tests)
    ]
    summary_failed = (
        int(receipt.get("failed", len(failed_tests))) if receipt is not None else 0
    )
    summary_timed_out = (
        int(receipt.get("timed_out", len(timed_out_tests)))
        if receipt is not None
        else 0
    )
    lines.append("")
    lines.append("<details>")
    lines.append(
        f"<summary>All failing and timed-out tests ({len(ordered_all)}: "
        f"{summary_failed} failed, {summary_timed_out} timed out)</summary>"
    )
    lines.append("")
    if ordered_all:
        for name in ordered_all:
            lines.append(f"- {_format_name_with_status(name, timed_out_set)}")
    else:
        lines.append("_No individual test names captured in log._")
    lines.append("")
    lines.append("</details>")

    marker_payload = {
        "complete": complete,
        "failed_tests": sorted(set(failed_tests)),
        "timed_out_tests": sorted(timed_out_set),
    }
    lines.append("")
    lines.append(
        f"<!-- nightly-iphone-failures: {json.dumps(marker_payload, separators=(',', ':'))} -->"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--previous-issue-json", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    receipt: dict[str, Any] | None = None
    if args.receipt.is_file():
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))

    prior_bodies: list[str] = []
    if args.previous_issue_json is not None and args.previous_issue_json.is_file():
        issue_payload = json.loads(
            args.previous_issue_json.read_text(encoding="utf-8")
        )
        if isinstance(issue_payload, dict):
            if issue_payload.get("body"):
                prior_bodies.append(str(issue_payload["body"]))
            for comment in issue_payload.get("comments") or []:
                if isinstance(comment, dict) and comment.get("body"):
                    prior_bodies.append(str(comment["body"]))

    rendered = format_issue_comment(
        receipt,
        run_date=args.run_date,
        sha=args.sha,
        run_url=args.run_url,
        prior_bodies=prior_bodies,
    )
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
