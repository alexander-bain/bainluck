"""Review Manus social ground-truth extraction rows.

This helper keeps the social-ground-truth loop offline and review-gated. It
accepts the JSONL output from extract_social_ground_truth_with_manus.py, applies
explicit accept/reject decisions, and can emit an accepted-only file for
EXTERNAL_CURATOR_GROUND_TRUTH_PATHS.

Usage:
    python3 scripts/review_social_ground_truth.py /tmp/social_gt.review.jsonl \
        --accept-name "Will Fed cut rates in June?" \
        --accepted-output /tmp/social_gt.accepted.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.extract_social_ground_truth_with_manus import REVIEW_FIELDS  # noqa: E402

ACCEPTED_STATUSES = {"accepted", "approved", "reviewed"}
REJECTED_STATUSES = {"rejected", "dismissed"}
PENDING_STATUS = "pending"


def load_review_rows(path: str | Path) -> list[dict[str, str]]:
    """Load review JSONL rows and coerce values to strings."""
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL line {line_number} must be an object")
        rows.append({_clean(key): _clean(value) for key, value in payload.items()})
    return rows


def apply_review_decisions(
    rows: Iterable[dict[str, Any]],
    *,
    accept_names: Iterable[str] = (),
    reject_names: Iterable[str] = (),
    accept_high_confidence: bool = False,
) -> list[dict[str, str]]:
    """Return rows with review_status updated by explicit local decisions."""
    accept_set = {_normalize_name(name) for name in accept_names if _normalize_name(name)}
    reject_set = {_normalize_name(name) for name in reject_names if _normalize_name(name)}
    reviewed: list[dict[str, str]] = []

    for row in rows:
        output = {_clean(key): _clean(value) for key, value in row.items()}
        name_key = _normalize_name(output.get("name", ""))
        status = _normalize_status(output.get("review_status"))

        if name_key in reject_set:
            status = "rejected"
        elif name_key in accept_set:
            status = "accepted"
        elif accept_high_confidence and output.get("confidence", "").lower() == "high":
            status = "accepted"

        output["review_status"] = status
        reviewed.append(output)

    return reviewed


def accepted_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Filter rows that the external-curator lane may consume."""
    return [
        {_clean(key): _clean(value) for key, value in row.items()}
        for row in rows
        if _normalize_status(row.get("review_status")) in ACCEPTED_STATUSES
    ]


def write_jsonl(rows: Iterable[dict[str, Any]], output_path: str | Path) -> None:
    """Write rows as JSONL, preserving known review fields first."""
    output = sys.stdout if str(output_path) == "-" else Path(output_path).open("w")
    close = output is not sys.stdout
    try:
        _write_jsonl_to_handle(rows, output)
    finally:
        if close:
            output.close()


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    statuses = Counter(_normalize_status(row.get("review_status")) for row in materialized)
    return {
        "rows": len(materialized),
        "accepted": sum(statuses[status] for status in ACCEPTED_STATUSES),
        "pending": statuses[PENDING_STATUS],
        "rejected": sum(statuses[status] for status in REJECTED_STATUSES),
        "statuses": dict(sorted(statuses.items())),
    }


def _write_jsonl_to_handle(rows: Iterable[dict[str, Any]], output: TextIO) -> None:
    for row in rows:
        payload = _ordered_payload(row)
        output.write(json.dumps(payload, sort_keys=False))
        output.write("\n")


def _ordered_payload(row: dict[str, Any]) -> dict[str, str]:
    cleaned = {_clean(key): _clean(value) for key, value in row.items()}
    ordered = {field: cleaned.get(field, "") for field in REVIEW_FIELDS}
    for key in sorted(cleaned):
        if key not in ordered:
            ordered[key] = cleaned[key]
    return ordered


def _load_name_file(path: str | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def _normalize_status(value: Any) -> str:
    status = _clean(value).lower()
    return status or PENDING_STATUS


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Review JSONL from extract_social_ground_truth_with_manus.py")
    parser.add_argument("--output", default="-", help="Reviewed JSONL output path")
    parser.add_argument(
        "--accepted-output",
        default=None,
        help="Optional accepted-only JSONL output path for curator diagnostics/import",
    )
    parser.add_argument("--accept-name", action="append", default=[], help="Exact market name to accept")
    parser.add_argument("--reject-name", action="append", default=[], help="Exact market name to reject")
    parser.add_argument("--accept-names-file", default=None, help="Newline-delimited market names to accept")
    parser.add_argument("--reject-names-file", default=None, help="Newline-delimited market names to reject")
    parser.add_argument(
        "--accept-high-confidence",
        action="store_true",
        help="Mark all high-confidence rows accepted after reviewing the source file",
    )
    parser.add_argument("--summary-json", action="store_true", help="Print summary JSON to stderr")
    args = parser.parse_args(argv)

    rows = load_review_rows(args.input)
    reviewed = apply_review_decisions(
        rows,
        accept_names=[*args.accept_name, *_load_name_file(args.accept_names_file)],
        reject_names=[*args.reject_name, *_load_name_file(args.reject_names_file)],
        accept_high_confidence=args.accept_high_confidence,
    )
    write_jsonl(reviewed, args.output)
    if args.accepted_output:
        write_jsonl(accepted_rows(reviewed), args.accepted_output)
    if args.summary_json:
        print(json.dumps(summarize(reviewed), sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
