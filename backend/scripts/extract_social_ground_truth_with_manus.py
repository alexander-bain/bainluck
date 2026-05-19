"""Extract Instagram-style social ground truth with Manus.

This script is intentionally offline/advisory. It accepts a local manifest of
approved social posts (CSV, JSON, or JSONL), asks Manus to identify prediction
markets mentioned in the post image/caption, and writes reviewable JSONL rows
compatible with the external-curator ground-truth lane.

It does not scrape Instagram itself. Give it post URLs, captions, OCR text, or
public image URLs that were captured by an approved/manual workflow.

Usage:
    MANUS_API_KEY=... python3 scripts/extract_social_ground_truth_with_manus.py posts.jsonl --output /tmp/social_gt.review.jsonl
    python3 scripts/extract_social_ground_truth_with_manus.py posts.csv --dry-run --prompt-output /tmp/prompt.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.external_curator_ground_truth import (  # noqa: E402
    normalize_external_curator_ground_truth_rows,
)

BASE = "https://api.manus.ai/v2"
TARGET_HANDLES = (
    "@kalshi",
    "@kalshisports",
    "@kalshifacts",
    "@polymarket",
    "@polymarketsports",
)
REVIEW_FIELDS = [
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
    "evidence",
    "confidence",
    "extraction_notes",
]


def load_post_manifest(path: str | Path) -> list[dict[str, str]]:
    source_path = Path(path)
    text = source_path.read_text()
    suffix = source_path.suffix.lower().lstrip(".")
    if suffix == "csv":
        rows = list(csv.DictReader(StringIO(text)))
    elif suffix in {"jsonl", "ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == "json":
        payload = json.loads(text) if text.strip() else []
        if isinstance(payload, dict):
            rows = payload.get("posts") or payload.get("items") or [payload]
        else:
            rows = payload
    else:
        raise ValueError("Manifest must be CSV, JSON, JSONL, or NDJSON")
    return [_normalize_post_row(row) for row in rows if isinstance(row, dict)]


def _normalize_post_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    handle = _clean(
        _field(normalized, "handle", "account", "username", "source_handle")
    )
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    return {
        "handle": handle,
        "post_url": _clean(_field(normalized, "post_url", "url", "link")),
        "published_at": _clean(
            _field(normalized, "published_at", "published", "date", "created_at")
        ),
        "caption": _clean(_field(normalized, "caption", "description", "text")),
        "ocr_text": _clean(_field(normalized, "ocr_text", "image_text", "alt_text")),
        "image_url": _clean(_field(normalized, "image_url", "media_url", "image")),
        "engagement": _clean(
            _field(normalized, "engagement", "likes", "views", "score")
        ),
    }


def build_prompt(posts: list[dict[str, str]]) -> str:
    manifest = json.dumps(posts, indent=2)
    handles = ", ".join(TARGET_HANDLES)
    return f"""You are extracting editorial prediction-market ground truth for Bain Luck.

Task:
- Inspect the provided approved social post manifest.
- These posts come from target editorial accounts: {handles}.
- Use the post URL/image URL if accessible, plus caption/OCR text supplied in the manifest.
- Identify each specific prediction market/question featured by the post.
- Preserve why the post says the market is interesting.
- Output ONLY JSONL. No markdown. One JSON object per extracted market.

Each JSON object must have exactly these keys:
source, category, name, probability, hook, url, published_at, platform, handle, engagement, evidence, confidence, extraction_notes

Rules:
- platform must be "instagram".
- source should be "Instagram " plus the handle, for example "Instagram @kalshi".
- handle must be one of the target account handles when known.
- url should be the post_url.
- name must be a clean prediction-market question or market title, not a vague topic.
- hook should summarize the caption/image reason this is interesting.
- evidence should quote the text or visual cue used to infer the market.
- confidence must be one of: high, medium, low.
- Use category "?" if unsure.
- If a post references no identifiable market, omit it.
- Do not invent probabilities or market names not supported by the post.

Approved manifest:
{manifest}
"""


def submit_manus_task(prompt: str, *, api_key: str, title: str) -> str:
    response = httpx.post(
        f"{BASE}/task.create",
        json={
            "message": {"content": prompt},
            "title": title,
            "hide_in_task_list": True,
            "agent_profile": "manus-1.6-max",
        },
        headers={"x-manus-api-key": api_key},
        timeout=30,
    )
    response.raise_for_status()
    task_id = response.json().get("task_id")
    if not task_id:
        raise RuntimeError(f"Manus task.create response missing task_id: {response.text[:200]}")
    return task_id


def poll_manus_task(
    task_id: str,
    *,
    api_key: str,
    interval_seconds: int = 15,
    timeout_seconds: int = 900,
) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        detail = httpx.get(
            f"{BASE}/task.detail",
            params={"task_id": task_id},
            headers={"x-manus-api-key": api_key},
            timeout=30,
        )
        detail.raise_for_status()
        task = detail.json().get("task", {})
        status = task.get("status")
        if status == "stopped":
            messages = httpx.get(
                f"{BASE}/task.listMessages",
                params={"task_id": task_id, "order": "asc", "limit": 100},
                headers={"x-manus-api-key": api_key},
                timeout=30,
            )
            messages.raise_for_status()
            return _assistant_text(messages.json())
        if status == "error":
            raise RuntimeError(f"Manus task failed: {task_id}")
        time.sleep(interval_seconds)
    raise TimeoutError(f"Timed out waiting for Manus task {task_id}")


def _assistant_text(messages: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in messages.get("messages", []):
        if message.get("type") == "assistant_message":
            content = message.get("assistant_message", {}).get("content", "")
            if content:
                parts.append(content)
    return "\n".join(parts)


def parse_extraction_report(text: str) -> list[dict[str, str]]:
    candidate = _strip_code_fence(text)
    rows: list[dict[str, Any]] = []
    for line in candidate.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return normalize_review_rows(rows)


def normalize_review_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    normalized = normalize_external_curator_ground_truth_rows(rows)
    by_key = {
        _review_key(row): {
            "evidence": _clean(row.get("evidence")),
            "confidence": _clean(row.get("confidence")),
            "extraction_notes": _clean(row.get("extraction_notes")),
        }
        for row in rows
        if isinstance(row, dict)
    }
    output: list[dict[str, str]] = []
    for row in normalized:
        extras = by_key.get(_review_key(row), {})
        output.append(
            {
                **{field: row.get(field, "") for field in REVIEW_FIELDS},
                "platform": row.get("platform") or "instagram",
                "evidence": extras.get("evidence", ""),
                "confidence": extras.get("confidence", ""),
                "extraction_notes": extras.get("extraction_notes", ""),
            }
        )
    return output


def write_review_jsonl(rows: list[dict[str, str]], output_path: str | Path) -> None:
    output = sys.stdout if str(output_path) == "-" else Path(output_path).open("w")
    close = output is not sys.stdout
    try:
        for row in rows:
            output.write(json.dumps({field: row.get(field, "") for field in REVIEW_FIELDS}))
            output.write("\n")
    finally:
        if close:
            output.close()


def _strip_code_fence(text: str) -> str:
    match = re.search(r"```(?:jsonl|json)?\s*(.*?)\s*```", text, re.DOTALL | re.I)
    return match.group(1) if match else text


def _review_key(row: dict[str, Any]) -> str:
    return f"{_clean(row.get('source'))}|{_clean(row.get('name'))}"


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        normalized = _normalize_key(name)
        if normalized in row:
            return row[normalized]
    return ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="CSV, JSON, or JSONL approved post manifest")
    parser.add_argument("--output", default="-", help="Review JSONL output path")
    parser.add_argument("--prompt-output", default=None, help="Write the Manus prompt to a file")
    parser.add_argument("--dry-run", action="store_true", help="Build prompt but do not call Manus")
    parser.add_argument("--task-id", default=None, help="Poll an existing Manus task instead of creating one")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)

    posts = load_post_manifest(args.manifest)
    prompt = build_prompt(posts)
    if args.prompt_output:
        Path(args.prompt_output).write_text(prompt)
    if args.dry_run:
        print(prompt)
        return 0

    api_key = os.getenv("MANUS_API_KEY")
    if not api_key:
        raise SystemExit("MANUS_API_KEY is required unless --dry-run is used")
    task_id = args.task_id or submit_manus_task(
        prompt,
        api_key=api_key,
        title="Bain Luck social ground truth extraction",
    )
    report = poll_manus_task(task_id, api_key=api_key, timeout_seconds=args.timeout_seconds)
    rows = parse_extraction_report(report)
    write_review_jsonl(rows, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
