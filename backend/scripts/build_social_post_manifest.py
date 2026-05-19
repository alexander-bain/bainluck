"""Build approved social-post manifests for Manus ground-truth extraction.

This is the capture/export bridge for social ground truth. It normalizes local
CSV/JSON/JSONL exports or copied text files into the manifest shape consumed by
``extract_social_ground_truth_with_manus.py``. It does not scrape Instagram or
make network requests.

Usage:
    python3 scripts/build_social_post_manifest.py posts.csv --output /tmp/posts.jsonl
    python3 scripts/build_social_post_manifest.py captions.txt --text-files --default-handle @kalshi
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.extract_social_ground_truth_with_manus import TARGET_HANDLES  # noqa: E402

MANIFEST_FIELDS = [
    "handle",
    "post_url",
    "published_at",
    "caption",
    "ocr_text",
    "image_url",
    "engagement",
    "capture_notes",
]

HANDLE_ALIASES = ("handle", "account", "username", "source_handle", "author")
URL_ALIASES = ("post_url", "url", "link", "permalink", "source_url")
DATE_ALIASES = ("published_at", "published", "date", "created_at", "timestamp")
CAPTION_ALIASES = ("caption", "description", "text", "post_text", "copy")
OCR_ALIASES = ("ocr_text", "image_text", "alt_text", "visual_text", "screenshot_text")
IMAGE_ALIASES = ("image_url", "media_url", "image", "screenshot_url", "asset_url")
ENGAGEMENT_ALIASES = ("engagement", "likes", "views", "score", "reactions")
APPROVED_ALIASES = ("approved", "include", "reviewed", "use")
NOTES_ALIASES = ("capture_notes", "notes", "comment", "review_notes")


def load_capture_rows(
    paths: Iterable[str | Path],
    *,
    formats: list[str] | None = None,
    text_files: bool = False,
    default_handle: str = "",
    default_platform: str = "instagram",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, path in enumerate(paths):
        source_path = Path(path)
        if text_files:
            rows.extend(
                _rows_from_text_file(
                    source_path,
                    default_handle=default_handle,
                    default_platform=default_platform,
                )
            )
            continue
        input_format = formats[index] if formats and index < len(formats) else None
        rows.extend(_load_structured_rows(source_path, input_format=input_format))
    return rows


def build_manifest_rows(
    rows: Iterable[dict[str, Any]],
    *,
    default_handle: str = "",
    require_target_handle: bool = True,
    approved_only: bool = True,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_row in rows:
        row = normalize_capture_row(raw_row, default_handle=default_handle)
        if approved_only and not _is_approved(raw_row):
            continue
        if require_target_handle and row["handle"] not in TARGET_HANDLES:
            continue
        if not _has_extraction_evidence(row):
            continue
        key = "|".join(
            [
                row["handle"],
                row["post_url"],
                row["published_at"],
                row["caption"],
                row["ocr_text"],
                row["image_url"],
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def normalize_capture_row(
    row: dict[str, Any],
    *,
    default_handle: str = "",
) -> dict[str, str]:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    handle = _clean(_field(normalized, *HANDLE_ALIASES)) or default_handle
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    handle = handle.lower()
    return {
        "handle": handle,
        "post_url": _clean(_field(normalized, *URL_ALIASES)),
        "published_at": _clean(_field(normalized, *DATE_ALIASES)),
        "caption": _clean(_field(normalized, *CAPTION_ALIASES)),
        "ocr_text": _clean(_field(normalized, *OCR_ALIASES)),
        "image_url": _clean(_field(normalized, *IMAGE_ALIASES)),
        "engagement": _clean(_field(normalized, *ENGAGEMENT_ALIASES)),
        "capture_notes": _clean(_field(normalized, *NOTES_ALIASES)),
    }


def write_manifest(rows: list[dict[str, str]], output: TextIO, *, output_format: str) -> None:
    if output_format == "csv":
        writer = csv.DictWriter(output, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})
        return

    for row in rows:
        output.write(json.dumps({field: row.get(field, "") for field in MANIFEST_FIELDS}))
        output.write("\n")


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_handle: dict[str, int] = {}
    with_ocr = 0
    with_image = 0
    with_caption = 0
    for row in rows:
        by_handle[row["handle"]] = by_handle.get(row["handle"], 0) + 1
        if row.get("ocr_text"):
            with_ocr += 1
        if row.get("image_url"):
            with_image += 1
        if row.get("caption"):
            with_caption += 1
    return {
        "rows": len(rows),
        "handles": dict(sorted(by_handle.items())),
        "with_caption": with_caption,
        "with_ocr_text": with_ocr,
        "with_image_url": with_image,
        "target_handles": list(TARGET_HANDLES),
    }


def _load_structured_rows(
    path: Path,
    *,
    input_format: str | None = None,
) -> list[dict[str, Any]]:
    text = path.read_text()
    detected = (input_format or path.suffix.lower().lstrip(".")).lower()
    if detected == "ndjson":
        detected = "jsonl"
    if detected == "csv":
        return list(csv.DictReader(StringIO(text)))
    if detected == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if detected == "json":
        payload = json.loads(text) if text.strip() else []
        if isinstance(payload, dict):
            rows = payload.get("posts") or payload.get("items") or [payload]
        else:
            rows = payload
        return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"Unsupported input format for {path}: {detected}")


def _rows_from_text_file(
    path: Path,
    *,
    default_handle: str,
    default_platform: str,
) -> list[dict[str, str]]:
    text = path.read_text()
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    return [
        {
            "handle": default_handle,
            "caption": block,
            "capture_notes": f"text_file={path.name}; platform={default_platform}",
        }
        for block in blocks
    ]


def _has_extraction_evidence(row: dict[str, str]) -> bool:
    return bool(row.get("caption") or row.get("ocr_text") or row.get("image_url"))


def _is_approved(row: dict[str, Any]) -> bool:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    value = _clean(_field(normalized, *APPROVED_ALIASES)).lower()
    if not value:
        return True
    return value in {"1", "true", "yes", "y", "approved", "accept", "accepted"}


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        key = _normalize_key(name)
        if key in row:
            return row[key]
    return ""


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Approved social capture exports")
    parser.add_argument("--formats", nargs="*", default=None, help="Optional per-path format hints")
    parser.add_argument("--output", default="-", help="Output path, or '-' for stdout")
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    parser.add_argument("--default-handle", default="", help="Default handle for rows without one")
    parser.add_argument("--text-files", action="store_true", help="Treat each blank-line-separated text block as one post")
    parser.add_argument("--allow-non-target-handles", action="store_true")
    parser.add_argument("--include-unapproved", action="store_true")
    parser.add_argument("--summary-json", action="store_true")
    args = parser.parse_args(argv)

    raw_rows = load_capture_rows(
        args.paths,
        formats=args.formats,
        text_files=args.text_files,
        default_handle=args.default_handle,
    )
    rows = build_manifest_rows(
        raw_rows,
        default_handle=args.default_handle,
        require_target_handle=not args.allow_non_target_handles,
        approved_only=not args.include_unapproved,
    )

    output_stream: TextIO
    close_output = False
    if args.output == "-":
        output_stream = sys.stdout
    else:
        output_stream = Path(args.output).open("w", newline="")
        close_output = True

    try:
        write_manifest(rows, output_stream, output_format=args.format)
    finally:
        if close_output:
            output_stream.close()

    if args.summary_json:
        print(json.dumps(build_summary(rows), indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
