"""Run the offline social ground-truth pipeline.

This convenience wrapper chains the reviewed social workflow:
capture export -> post manifest -> LLM extraction -> review export.
It performs no scraping. Provider network calls happen only with ``--extract``.
UX-P028: the extraction step is provider-independent (Manus is retired).

Typical safe dry run:
    python3 scripts/run_social_ground_truth_pipeline.py captures.csv \
        --manifest-output /tmp/social.posts.jsonl \
        --prompt-output /tmp/social.prompt.md \
        --dry-run

Full extraction when OPENAI_API_KEY is configured:
    python3 scripts/run_social_ground_truth_pipeline.py captures.csv \
        --manifest-output /tmp/social.posts.jsonl \
        --review-output /tmp/social.review.jsonl \
        --extract
"""

from __future__ import annotations

import argparse
import json
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
from app.utils.social_ground_truth_extraction import (  # noqa: E402
    ExtractionUnavailable,
    build_extraction_prompt,
)
from scripts.extract_social_ground_truth import extract_rows  # noqa: E402
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
    model: str | None = None,
) -> list[dict[str, str]]:
    """Extract review rows from an approved manifest.

    UX-P028: provider-independent. The vendor task-create/poll dance is gone —
    `extract_rows` raises `ExtractionUnavailable` when no provider is configured,
    so a missing key surfaces as a failure instead of an empty success.
    """
    result = extract_rows(manifest_rows, **({"model": model} if model else {}))
    return list(result["rows"])


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
    parser.add_argument("--manifest-output", default=None, help="Write normalized post manifest JSONL/CSV")
    parser.add_argument("--manifest-format", choices=("jsonl", "csv"), default="jsonl")
    parser.add_argument("--prompt-output", default=None, help="Write the extraction prompt for review")
    parser.add_argument("--dry-run", action="store_true", help="Stop after manifest/prompt generation")
    parser.add_argument("--extract", action="store_true", help="Call the extraction provider and write review rows")
    parser.add_argument("--model", default=None, help="Override the extraction model")
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
            Path(args.prompt_output).write_text(build_extraction_prompt(manifest_rows))

    review_rows: list[dict[str, Any]] = []
    if args.review_input:
        review_rows = load_review_rows(args.review_input)
    elif args.extract:
        if not manifest_rows:
            raise SystemExit("Capture inputs are required with --extract unless --review-input is used")
        try:
            review_rows = run_extraction(manifest_rows, model=args.model)
        except ExtractionUnavailable as exc:
            # Fail closed and LOUD: a missing provider is not an empty harvest.
            raise SystemExit(str(exc))

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
