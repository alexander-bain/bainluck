"""Normalize external curator/social exports into Discover ground-truth rows.

This is an offline helper for turning manually collected public curator exports
into the canonical CSV/JSONL shape accepted by
``EXTERNAL_CURATOR_GROUND_TRUTH_PATHS``. It performs no scraping or network
requests; URL fields are treated as metadata and sanitized by the shared parser.

Usage:
    python3 scripts/normalize_external_curator_ground_truth.py curators.csv --output /tmp/curators.normalized.csv
    python3 scripts/normalize_external_curator_ground_truth.py x.jsonl newsletter.json --formats jsonl json --format jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.external_curator_ground_truth import (  # noqa: E402
    DEFAULT_STALE_AFTER_DAYS,
    load_external_curator_ground_truth_from_path,
)


CANONICAL_FIELDS = [
    "source",
    "category",
    "name",
    "probability",
    "hook",
    "url",
    "published_at",
    "platform",
    "handle",
    "engagement",
]


def load_inputs(
    paths: Iterable[str],
    *,
    formats: list[str] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, path in enumerate(paths):
        input_format = formats[index] if formats and index < len(formats) else None
        rows.extend(
            load_external_curator_ground_truth_from_path(
                path,
                input_format=input_format,
            )
        )
    return rows


def write_csv(rows: list[dict[str, str]], output: TextIO) -> None:
    writer = csv.DictWriter(output, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in CANONICAL_FIELDS})


def write_jsonl(rows: list[dict[str, str]], output: TextIO) -> None:
    for row in rows:
        output.write(json.dumps({field: row.get(field, "") for field in CANONICAL_FIELDS}))
        output.write("\n")


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    for row in rows:
        source = row.get("source") or "external_curator"
        platform = row.get("platform") or "unknown"
        by_source[source] = by_source.get(source, 0) + 1
        by_platform[platform] = by_platform.get(platform, 0) + 1
    return {
        "rows": len(rows),
        "sources": dict(sorted(by_source.items())),
        "platforms": dict(sorted(by_platform.items())),
        "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="CSV, JSON, or JSONL export paths")
    parser.add_argument(
        "--formats",
        nargs="*",
        default=None,
        help="Optional per-path format hints: csv, json, jsonl",
    )
    parser.add_argument("--output", default="-", help="Output path, or '-' for stdout")
    parser.add_argument(
        "--format",
        choices=("csv", "jsonl"),
        default="csv",
        help="Normalized output format",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Print a compact source/platform summary to stderr",
    )
    args = parser.parse_args(argv)

    rows = load_inputs(args.paths, formats=args.formats)
    output_stream: TextIO
    close_output = False
    if args.output == "-":
        output_stream = sys.stdout
    else:
        output_stream = Path(args.output).open("w", newline="")
        close_output = True

    try:
        if args.format == "jsonl":
            write_jsonl(rows, output_stream)
        else:
            write_csv(rows, output_stream)
    finally:
        if close_output:
            output_stream.close()

    if args.summary_json:
        print(json.dumps(build_summary(rows), indent=2), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
