"""Provider-independent social ground-truth extraction contract.

UX-P028 (#1497). The capture -> extract -> review -> import -> Discover-recall
pipeline was sound at every step except one: extraction was bound to a single
vendor (Manus), which is permanently retired (Alex ruling 2026-07-31). This module
is the vendor-free home for everything about extraction that is NOT the model call
— manifest parsing, the prompt, and parsing/validating the model's output — so the
provider becomes a thin, swappable edge instead of a dependency woven through the
scripts.

Everything here is PURE: no network, no environment, no clock. That is what lets
the contract be frozen in fixtures and replayed deterministically, which is what
``replay is idempotent`` in the queue's acceptance actually requires.

Two rules the extraction step must never break, both encoded here:

* **Fail closed.** An unparseable or ambiguous model response yields ISOLATED
  rejects, never a silent empty success. A pipeline that returns "0 rows, ok" when
  it is actually broken is the exact failure this program keeps re-learning — a
  green rail shouting into an empty room.
* **Never auto-promote.** Every extracted row leaves here ``review_status:
  "pending"``. Only the explicit review step may accept a row, because accepted
  rows reach a live Discover recall+rank lane.
"""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from app.utils.external_curator_ground_truth import (
    normalize_external_curator_ground_truth_rows,
)

# Bump when the prompt or the output contract changes in a way that makes rows
# from an older run non-comparable. Stored on every row so a corpus can always be
# traced back to the extractor that produced it.
EXTRACTOR_VERSION = "social-gt-extractor/2"

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
    "review_status",
]

MANIFEST_FIELDS = [
    "handle",
    "post_url",
    "published_at",
    "caption",
    "ocr_text",
    "image_url",
    "engagement",
]


class ExtractionUnavailable(RuntimeError):
    """Raised when no extraction provider is configured or reachable.

    Deliberately an exception rather than an empty result: "the provider is gone"
    and "the posts contained no markets" are different facts, and collapsing them
    is how a dead rail reports success.
    """


def load_post_manifest(path: str | Path) -> list[dict[str, str]]:
    """Parse an approved post manifest (CSV / JSON / JSONL / NDJSON)."""
    source_path = Path(path)
    return parse_post_manifest(source_path.read_text(), suffix=source_path.suffix)


def parse_post_manifest(text: str, *, suffix: str) -> list[dict[str, str]]:
    """Parse manifest text. Split from file IO so fixtures can drive it."""
    fmt = suffix.lower().lstrip(".")
    if fmt == "csv":
        rows: list[Any] = list(csv.DictReader(StringIO(text)))
    elif fmt in {"jsonl", "ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif fmt == "json":
        payload = json.loads(text) if text.strip() else []
        if isinstance(payload, dict):
            rows = payload.get("posts") or payload.get("items") or [payload]
        else:
            rows = payload
    else:
        raise ValueError("Manifest must be CSV, JSON, JSONL, or NDJSON")
    return [normalize_post_row(row) for row in rows if isinstance(row, dict)]


def normalize_post_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    handle = _clean(_field(normalized, "handle", "account", "username", "source_handle"))
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
        "engagement": _clean(_field(normalized, "engagement", "likes", "views", "score")),
    }


def build_extraction_prompt(posts: list[dict[str, str]]) -> str:
    """The extraction instruction. Provider-agnostic — any capable model can run it."""
    manifest = json.dumps(posts, indent=2, sort_keys=True)
    handles = ", ".join(TARGET_HANDLES)
    return f"""You are extracting editorial prediction-market ground truth for Bain Luck.

Task:
- Inspect the provided approved social post manifest.
- These posts come from target editorial accounts: {handles}.
- Use the caption/OCR text supplied in the manifest.
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


def parse_extraction_output(
    text: str, *, extractor_version: str = EXTRACTOR_VERSION
) -> dict[str, Any]:
    """Parse a model's JSONL response into review rows, isolating poison lines.

    Returns ``{"rows": [...], "rejected": [...]}``. Malformed lines are RETURNED,
    not dropped: a run that silently discards half the model's output looks
    identical to a run where the model found half as much.
    """
    candidate = _strip_code_fence(text or "")
    parsed: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for lineno, line in enumerate(candidate.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            rejected.append(
                {"line": str(lineno), "reason": f"invalid json: {exc.msg}", "raw": stripped[:300]}
            )
            continue
        if not isinstance(payload, dict):
            rejected.append(
                {"line": str(lineno), "reason": "not a json object", "raw": stripped[:300]}
            )
            continue
        if not _clean(payload.get("name")):
            rejected.append(
                {"line": str(lineno), "reason": "missing market name", "raw": stripped[:300]}
            )
            continue
        parsed.append(payload)

    return {
        "rows": _to_review_rows(parsed, extractor_version=extractor_version),
        "rejected": rejected,
    }


def _to_review_rows(
    rows: Iterable[dict[str, Any]], *, extractor_version: str
) -> list[dict[str, str]]:
    rows = list(rows)
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
        notes = extras.get("extraction_notes", "")
        # Provenance rides ON the row: which extractor produced it, so a corpus
        # can be attributed after the fact without consulting run logs.
        stamped = f"{notes} [{extractor_version}]".strip() if notes else f"[{extractor_version}]"
        output.append(
            {
                **{field: row.get(field, "") for field in REVIEW_FIELDS},
                "platform": row.get("platform") or "instagram",
                "evidence": extras.get("evidence", ""),
                "confidence": extras.get("confidence", ""),
                "extraction_notes": stamped,
                # NEVER auto-promote — only the review step may accept.
                "review_status": "pending",
            }
        )
    return output


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
