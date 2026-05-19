"""Run the offline social ground-truth pipeline.

This convenience wrapper chains the reviewed social workflow:
capture export -> Manus manifest -> Manus prompt/extraction -> review export.
It performs no scraping. Manus network calls happen only with ``--extract``.

Typical safe dry run:
    python3 scripts/run_social_ground_truth_pipeline.py captures.csv \
        --manifest-output /tmp/social.posts.jsonl \
        --prompt-output /tmp/social.prompt.md \
        --dry-run

Full extraction when MANUS_API_KEY is configured:
    python3 scripts/run_social_ground_truth_pipeline.py captures.csv \
        --manifest-output /tmp/social.posts.jsonl \
        --review-output /tmp/social.review.jsonl \
        --extract
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_social_post_manifest import (  # noqa: E402
    build_manifest_rows,
    build_summary as build_manifest_summary,
    load_capture_rows,
    write_manifest,
)
from scripts.extract_social_ground_truth_with_manus import (  # noqa: E402
    build_prompt,
    parse_extraction_report,
    poll_manus_task,
    submit_manus_task,
    write_review_jsonl,
)
from scripts.review_social_ground_truth import (  # noqa: E402
    accepted_rows,
    apply_review_decisions,
    load_review_rows,
    summarize as summarize_review_rows,
    write_jsonl as write_review_decision_jsonl,
)


def build_pipeline_manifest(
    paths: list[str],
    *,
    formats: list[str] | None = None,
    text_files: bool = False,
    default_handle: str = "",
    allow_non_target_handles: bool = False,
    include_unapproved: bool = False,
) -> list[dict[str, str]]:
    raw_rows = load_capture_rows(
        paths,
        formats=formats,
        text_files=text_files,
        default_handle=default_handle,
    )
    return build_manifest_rows(
        raw_rows,
        default_handle=default_handle,
        require_target_handle=not allow_non_target_handles,
        approved_only=not include_unapproved,
    )


def run_extraction(
    manifest_rows: list[dict[str, str]],
    *,
    api_key: str,
    task_id: str | None = None,
    timeout_seconds: int = 900,
) -> list[dict[str, str]]:
    prompt = build_prompt(manifest_rows)
    resolved_task_id = task_id or submit_manus_task(
        prompt,
        api_key=api_key,
        title="Bain Luck social ground truth extraction",
    )
    report = poll_manus_task(
        resolved_task_id,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    return parse_extraction_report(report)


def apply_optional_review(
    rows: list[dict[str, Any]],
    *,
    accept_names: list[str],
    reject_names: list[str],
    accept_high_confidence: bool,
) -> list[dict[str, str]]:
    if not accept_names and not reject_names and not accept_high_confidence:
        return [{str(key): "" if value is None else str(value) for key, value in row.items()} for row in rows]
    return apply_review_decisions(
        rows,
        accept_names=accept_names,
        reject_names=reject_names,
        accept_high_confidence=accept_high_confidence,
    )


def _load_name_file(path: str | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def _write_manifest_file(rows: list[dict[str, str]], path: str, output_format: str) -> None:
    output = sys.stdout if path == "-" else Path(path).open("w", newline="")
    close = output is not sys.stdout
    try:
        write_manifest(rows, output, output_format=output_format)
    finally:
        if close:
            output.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", nargs="*", help="Approved social capture exports")
    parser.add_argument("--formats", nargs="*", default=None, help="Optional per-capture format hints")
    parser.add_argument("--text-files", action="store_true", help="Treat captures as blank-line-separated text posts")
    parser.add_argument("--default-handle", default="", help="Default handle for rows without one")
    parser.add_argument("--allow-non-target-handles", action="store_true")
    parser.add_argument("--include-unapproved", action="store_true")
    parser.add_argument("--manifest-output", default=None, help="Write normalized Manus manifest JSONL/CSV")
    parser.add_argument("--manifest-format", choices=("jsonl", "csv"), default="jsonl")
    parser.add_argument("--prompt-output", default=None, help="Write Manus prompt for review")
    parser.add_argument("--dry-run", action="store_true", help="Stop after manifest/prompt generation")
    parser.add_argument("--extract", action="store_true", help="Call Manus and write review rows")
    parser.add_argument("--task-id", default=None, help="Poll an existing Manus task instead of creating one")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--review-input", default=None, help="Existing review JSONL to apply decisions to")
    parser.add_argument("--review-output", default=None, help="Pending/reviewed JSONL output path")
    parser.add_argument("--accepted-output", default=None, help="Accepted-only JSONL output path")
    parser.add_argument("--accept-name", action="append", default=[], help="Exact extracted market name to accept")
    parser.add_argument("--reject-name", action="append", default=[], help="Exact extracted market name to reject")
    parser.add_argument("--accept-names-file", default=None)
    parser.add_argument("--reject-names-file", default=None)
    parser.add_argument("--accept-high-confidence", action="store_true")
    parser.add_argument("--summary-json", action="store_true")
    args = parser.parse_args(argv)

    manifest_rows: list[dict[str, str]] = []
    if args.captures:
        manifest_rows = build_pipeline_manifest(
            args.captures,
            formats=args.formats,
            text_files=args.text_files,
            default_handle=args.default_handle,
            allow_non_target_handles=args.allow_non_target_handles,
            include_unapproved=args.include_unapproved,
        )
        if args.manifest_output:
            _write_manifest_file(manifest_rows, args.manifest_output, args.manifest_format)
        if args.prompt_output:
            Path(args.prompt_output).write_text(build_prompt(manifest_rows))

    review_rows: list[dict[str, Any]] = []
    if args.review_input:
        review_rows = load_review_rows(args.review_input)
    elif args.extract:
        api_key = os.getenv("MANUS_API_KEY")
        if not api_key:
            raise SystemExit("MANUS_API_KEY is required with --extract")
        if not manifest_rows:
            raise SystemExit("Capture inputs are required with --extract unless --review-input is used")
        review_rows = run_extraction(
            manifest_rows,
            api_key=api_key,
            task_id=args.task_id,
            timeout_seconds=args.timeout_seconds,
        )

    if review_rows:
        reviewed = apply_optional_review(
            review_rows,
            accept_names=[*args.accept_name, *_load_name_file(args.accept_names_file)],
            reject_names=[*args.reject_name, *_load_name_file(args.reject_names_file)],
            accept_high_confidence=args.accept_high_confidence,
        )
        if args.review_output:
            write_review_decision_jsonl(reviewed, args.review_output)
        if args.accepted_output:
            write_review_decision_jsonl(accepted_rows(reviewed), args.accepted_output)
    else:
        reviewed = []

    if args.summary_json:
        print(
            json.dumps(
                {
                    "manifest": build_manifest_summary(manifest_rows),
                    "review": summarize_review_rows(reviewed) if reviewed else None,
                    "dry_run": args.dry_run,
                    "extracted": bool(args.extract and reviewed),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

    if args.dry_run:
        return 0
    if not args.captures and not args.review_input:
        raise SystemExit("Provide capture inputs or --review-input")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
