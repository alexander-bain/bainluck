"""Run the daily social ground-truth operator workflow.

This is the high-level wrapper for the current no-scraping loop:
capture export -> Manus manifest/prompt -> Manus extraction -> reviewed rows
-> accepted rows -> optional admin upload.

It intentionally does not scrape Instagram. Feed it local capture exports or a
pre-approved export URL that returns CSV/JSON/JSONL.

Typical review-gated run:
    MANUS_API_KEY=... python3 scripts/run_daily_social_ground_truth.py captures.csv --extract

After reviewing the generated JSONL:
    python3 scripts/run_daily_social_ground_truth.py \
        --review-input /tmp/bainluck_social_ground_truth/20260520/social.review.jsonl \
        --accept-name "Example market" \
        --upload-accepted
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.review_social_ground_truth import (  # noqa: E402
    accepted_rows,
    summarize as summarize_review_rows,
    write_jsonl,
)
from scripts.run_social_ground_truth_pipeline import (  # noqa: E402
    _load_name_file,
    apply_optional_review,
    build_manifest_summary,
    build_pipeline_manifest,
    build_prompt,
    load_review_rows,
    run_extraction,
    write_review_decision_jsonl,
    _write_manifest_file,
)
from scripts.upload_external_curator_ground_truth import upload_rows  # noqa: E402

DEFAULT_OUTPUT_ROOT = Path("/tmp/bainluck_social_ground_truth")
DEFAULT_API_URL = "https://api.bainluck.com"
DEFAULT_TIMEZONE = "America/Los_Angeles"


def resolve_run_date(
    value: str | None, *, timezone_name: str = DEFAULT_TIMEZONE
) -> str:
    if value:
        return value
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y%m%d")


def resolve_output_dir(output_dir: str | None, *, run_date: str) -> Path:
    if output_dir:
        return Path(output_dir)
    return DEFAULT_OUTPUT_ROOT / run_date


def download_capture_urls(
    urls: list[str],
    *,
    output_dir: Path,
    timeout: float = 60.0,
) -> list[str]:
    capture_dir = output_dir / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, url in enumerate(urls, start=1):
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        suffix = _suffix_for_capture_url(url, response.headers.get("content-type", ""))
        path = capture_dir / f"capture_{index}{suffix}"
        path.write_bytes(response.content)
        paths.append(str(path))
    return paths


def build_default_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / "social.posts.jsonl",
        "prompt": output_dir / "social.prompt.md",
        "review": output_dir / "social.review.jsonl",
        "reviewed": output_dir / "social.reviewed.jsonl",
        "accepted": output_dir / "social.accepted.jsonl",
        "summary": output_dir / "social.summary.json",
    }


def build_next_commands(
    paths: dict[str, Path], *, accepted_count: int, pending_count: int
) -> dict[str, str]:
    commands: dict[str, str] = {}
    if pending_count:
        commands["review"] = (
            f"python3 scripts/review_social_ground_truth.py {paths['review']} "
            f"--output {paths['reviewed']} "
            f"--accepted-output {paths['accepted']} "
            '--accept-name "MARKET NAME TO ACCEPT"'
        )
    if accepted_count:
        commands["upload"] = (
            f"ADMIN_TOKEN=... .venv/bin/python "
            f"scripts/upload_external_curator_ground_truth.py {paths['accepted']}"
        )
    return commands


def _suffix_for_capture_url(url: str, content_type: str) -> str:
    path_suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if path_suffix in {".csv", ".json", ".jsonl", ".ndjson"}:
        return ".jsonl" if path_suffix == ".ndjson" else path_suffix
    lowered_type = content_type.lower()
    if "csv" in lowered_type:
        return ".csv"
    if "json" in lowered_type:
        return ".json"
    return ".csv"


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "captures", nargs="*", help="Local approved social capture exports"
    )
    parser.add_argument(
        "--capture-url",
        action="append",
        default=[],
        help="Approved CSV/JSON/JSONL capture export URL",
    )
    parser.add_argument(
        "--date", default=None, help="Run date label, default YYYYMMDD in Pacific time"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory, default /tmp/bainluck_social_ground_truth/YYYYMMDD",
    )
    parser.add_argument(
        "--formats", nargs="*", default=None, help="Optional per-capture format hints"
    )
    parser.add_argument(
        "--text-files",
        action="store_true",
        help="Treat local captures as blank-line-separated text posts",
    )
    parser.add_argument(
        "--default-handle", default="", help="Default handle for rows without one"
    )
    parser.add_argument("--allow-non-target-handles", action="store_true")
    parser.add_argument("--include-unapproved", action="store_true")
    parser.add_argument(
        "--extract", action="store_true", help="Call Manus and write review rows"
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="Poll an existing Manus task instead of creating one",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--review-input", default=None, help="Existing review JSONL to review/upload"
    )
    parser.add_argument(
        "--accept-name",
        action="append",
        default=[],
        help="Exact extracted market name to accept",
    )
    parser.add_argument(
        "--reject-name",
        action="append",
        default=[],
        help="Exact extracted market name to reject",
    )
    parser.add_argument("--accept-names-file", default=None)
    parser.add_argument("--reject-names-file", default=None)
    parser.add_argument("--accept-high-confidence", action="store_true")
    parser.add_argument(
        "--upload-accepted",
        action="store_true",
        help="Upload accepted rows through the admin API",
    )
    parser.add_argument(
        "--api-url", default=os.getenv("BAINLUCK_API_URL", DEFAULT_API_URL)
    )
    parser.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN"))
    parser.add_argument(
        "--summary-json", action="store_true", help="Print summary JSON to stdout"
    )
    args = parser.parse_args(argv)

    run_date = resolve_run_date(args.date)
    output_dir = resolve_output_dir(args.output_dir, run_date=run_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = build_default_paths(output_dir)

    downloaded_captures = download_capture_urls(args.capture_url, output_dir=output_dir)
    capture_paths = [*args.captures, *downloaded_captures]

    manifest_rows: list[dict[str, str]] = []
    if capture_paths:
        manifest_rows = build_pipeline_manifest(
            capture_paths,
            formats=args.formats,
            text_files=args.text_files,
            default_handle=args.default_handle,
            allow_non_target_handles=args.allow_non_target_handles,
            include_unapproved=args.include_unapproved,
        )
        _write_manifest_file(manifest_rows, str(paths["manifest"]), "jsonl")
        paths["prompt"].write_text(build_prompt(manifest_rows))

    review_rows: list[dict[str, Any]] = []
    if args.review_input:
        review_rows = load_review_rows(args.review_input)
        paths["review"] = Path(args.review_input)
    elif args.extract:
        if not capture_paths:
            raise SystemExit(
                "Capture inputs or --capture-url are required with --extract"
            )
        api_key = os.getenv("MANUS_API_KEY")
        if not api_key:
            raise SystemExit("MANUS_API_KEY is required with --extract")
        review_rows = run_extraction(
            manifest_rows,
            api_key=api_key,
            task_id=args.task_id,
            timeout_seconds=args.timeout_seconds,
        )
        write_jsonl(review_rows, paths["review"])

    reviewed_rows: list[dict[str, str]] = []
    accepted: list[dict[str, str]] = []
    if review_rows:
        reviewed_rows = apply_optional_review(
            review_rows,
            accept_names=[*args.accept_name, *_load_name_file(args.accept_names_file)],
            reject_names=[*args.reject_name, *_load_name_file(args.reject_names_file)],
            accept_high_confidence=args.accept_high_confidence,
        )
        write_review_decision_jsonl(reviewed_rows, paths["reviewed"])
        accepted = accepted_rows(reviewed_rows)
        write_review_decision_jsonl(accepted, paths["accepted"])

    upload_result: dict[str, Any] | None = None
    if args.upload_accepted:
        if not accepted:
            raise SystemExit("No accepted rows to upload")
        if not args.admin_token:
            raise SystemExit(
                "ADMIN_TOKEN or --admin-token is required with --upload-accepted"
            )
        upload_result = upload_rows(
            accepted,
            api_url=args.api_url,
            admin_token=args.admin_token,
        )

    review_summary = summarize_review_rows(reviewed_rows) if reviewed_rows else None
    pending_count = int((review_summary or {}).get("pending") or 0)
    accepted_count = int((review_summary or {}).get("accepted") or 0)
    summary = {
        "run_date": run_date,
        "output_dir": str(output_dir),
        "captures": {
            "local": args.captures,
            "downloaded": downloaded_captures,
            "count": len(capture_paths),
        },
        "manifest": build_manifest_summary(manifest_rows),
        "review": review_summary,
        "upload": upload_result,
        "paths": {name: str(path) for name, path in paths.items()},
        "next_commands": build_next_commands(
            paths,
            accepted_count=accepted_count,
            pending_count=pending_count,
        ),
    }
    _write_summary(paths["summary"], summary)
    if args.summary_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Wrote social ground-truth run to {output_dir}")
        if summary["next_commands"]:
            print(json.dumps(summary["next_commands"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
