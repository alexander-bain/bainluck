"""Parse advisory external-curator inputs into Discover ground-truth items."""

from __future__ import annotations

import csv
import ipaddress
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SUPPORTED_FORMATS = {"csv", "json", "jsonl"}
ENV_PATHS = "EXTERNAL_CURATOR_GROUND_TRUTH_PATHS"
ENV_FORMATS = "EXTERNAL_CURATOR_GROUND_TRUTH_FORMATS"
DEFAULT_STALE_AFTER_DAYS = 7


def load_external_curator_ground_truth_report_from_env(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load advisory external-curator ground truth from configured local files.

    `EXTERNAL_CURATOR_GROUND_TRUTH_PATHS` is split with `os.pathsep` so several
    local exports can be combined without request-time network or scraping.
    `EXTERNAL_CURATOR_GROUND_TRUTH_FORMATS` can optionally provide matching
    csv/json/jsonl format hints, also split with `os.pathsep`.
    """
    raw_paths = os.getenv(ENV_PATHS, "")
    paths = [part.strip() for part in raw_paths.split(os.pathsep) if part.strip()]
    formats = [
        part.strip().lower().lstrip(".")
        for part in os.getenv(ENV_FORMATS, "").split(os.pathsep)
        if part.strip()
    ]
    if not paths:
        return _report(
            [],
            configured=False,
            source_paths=[],
            raw_row_count=0,
            error=None,
            now=now,
        )

    items: list[dict[str, str]] = []
    errors: list[str] = []
    for index, path in enumerate(paths):
        try:
            input_format = formats[index] if index < len(formats) else None
            items.extend(
                load_external_curator_ground_truth_from_path(
                    path,
                    input_format=input_format,
                )
            )
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    items = normalize_external_curator_ground_truth_rows(items)
    return _report(
        items,
        configured=True,
        source_paths=paths,
        raw_row_count=len(items),
        error="; ".join(errors) if errors else None,
        now=now,
    )


def load_external_curator_ground_truth_from_path(
    path: str | Path,
    *,
    input_format: str | None = None,
) -> list[dict[str, str]]:
    """Load external-curator ground truth from a local CSV, JSON, or JSONL file."""
    source_path = Path(path).expanduser()
    detected_format = input_format or _detect_format(source_path)
    return load_external_curator_ground_truth_from_text(
        source_path.read_text(),
        input_format=detected_format,
    )


def load_external_curator_ground_truth_from_text(
    text: str,
    *,
    input_format: str,
) -> list[dict[str, str]]:
    """Parse local CSV/JSON/JSONL text into normalized ground-truth item dicts.

    This utility intentionally performs no scraping or network requests. URL
    fields are treated only as advisory metadata and retained only when they are
    public http(s) URL strings.
    """
    normalized_format = input_format.strip().lower().lstrip(".")
    if normalized_format not in SUPPORTED_FORMATS:
        raise ValueError(
            "input_format must be one of: " + ", ".join(sorted(SUPPORTED_FORMATS))
        )

    if normalized_format == "csv":
        rows = _read_csv_rows(text)
    elif normalized_format == "json":
        rows = _read_json_rows(text)
    else:
        rows = _read_jsonl_rows(text)

    return normalize_external_curator_ground_truth_rows(rows)


def load_external_curator_ground_truth_from_csv_text(text: str) -> list[dict[str, str]]:
    return load_external_curator_ground_truth_from_text(text, input_format="csv")


def load_external_curator_ground_truth_from_json_text(
    text: str,
) -> list[dict[str, str]]:
    return load_external_curator_ground_truth_from_text(text, input_format="json")


def load_external_curator_ground_truth_from_jsonl_text(
    text: str,
) -> list[dict[str, str]]:
    return load_external_curator_ground_truth_from_text(text, input_format="jsonl")


def normalize_external_curator_ground_truth_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Normalize already-loaded curator rows into the ground-truth item shape."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw_row in rows:
        row = _normalize_row_keys(raw_row)
        name = _clean_text(
            _field(row, "name", "market_name", "question", "title", "market")
        )
        if not name:
            continue

        source = (
            _clean_text(
                _field(
                    row,
                    "source",
                    "curator",
                    "curator_source",
                    "publisher",
                    "publication",
                )
            )
            or "external_curator"
        )
        url = _normalize_public_url(
            _field(row, "url", "market_url", "source_url", "link")
        )
        dedupe_key = _dedupe_key(name=name, source=source, url=url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item = {
            "source": source,
            "category": _clean_text(_field(row, "category", "llm_category", "topic"))
            or "?",
            "name": name,
            "probability": _clean_text(
                _field(
                    row, "probability", "leader_probability", "prob", "chance", "odds"
                )
            ),
            "hook": _clean_text(
                _field(
                    row,
                    "hook",
                    "hook_description",
                    "description",
                    "summary",
                    "rationale",
                )
            ),
            "url": url,
            "published_at": _clean_text(
                _field(row, "published_at", "published", "date", "created_at")
            ),
            "platform": _clean_text(
                _field(row, "platform", "social_platform", "network")
            ),
            "handle": _clean_text(
                _field(row, "handle", "account", "author", "username")
            ),
            "engagement": _clean_text(
                _field(
                    row,
                    "engagement",
                    "engagement_count",
                    "likes",
                    "views",
                    "score",
                )
            ),
            "evidence": _clean_text(
                _field(row, "evidence", "evidence_text", "quote", "visual_evidence")
            ),
            "confidence": _clean_text(
                _field(row, "confidence", "extraction_confidence")
            ),
            "extraction_notes": _clean_text(
                _field(row, "extraction_notes", "notes", "review_notes")
            ),
        }
        items.append(item)

    return items


def _report(
    items: list[dict[str, str]],
    *,
    configured: bool,
    source_paths: list[str],
    raw_row_count: int,
    error: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    latest_date = _latest_item_date(items)
    base = now or datetime.now(timezone.utc)
    stale_after = base.date() - timedelta(days=DEFAULT_STALE_AFTER_DAYS)
    stale = latest_date < stale_after if latest_date else None
    source_counts = Counter(item.get("source") or "external_curator" for item in items)
    source_health = _source_health(items, stale_after=stale_after)
    return {
        "items": items,
        "metadata": {
            "configured": configured,
            "source": "external_curator",
            "source_paths": source_paths,
            "raw_row_count": raw_row_count,
            "loaded_count": len(items),
            "latest_date": latest_date.isoformat() if latest_date else None,
            "stale": stale,
            "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
            "source_counts": dict(sorted(source_counts.items())),
            "source_health": source_health,
            "error": error,
        },
    }


def _source_health(
    items: list[dict[str, str]],
    *,
    stale_after: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_source: dict[str, list[dict[str, str]]] = {}
    for item in items:
        source = item.get("source") or "external_curator"
        by_source.setdefault(source, []).append(item)

    for source, source_items in sorted(by_source.items()):
        latest_date = _latest_item_date(source_items)
        platform_counts = Counter(
            item.get("platform") or "unknown"
            for item in source_items
        )
        rows.append(
            {
                "source": source,
                "count": len(source_items),
                "latest_date": latest_date.isoformat() if latest_date else None,
                "stale": latest_date < stale_after if latest_date else None,
                "platform_counts": dict(sorted(platform_counts.items())),
            }
        )
    return rows


def _latest_item_date(items: list[dict[str, str]]) -> date | None:
    parsed = [
        parsed_date
        for item in items
        if (parsed_date := _parse_date(item.get("published_at")))
    ]
    return max(parsed) if parsed else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _read_csv_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        return []
    return [dict(row) for row in reader]


def _read_json_rows(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    payload = json.loads(text)
    if isinstance(payload, list):
        return [_json_object(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "markets", "ground_truth"):
            value = payload.get(key)
            if isinstance(value, list):
                return [_json_object(row) for row in value if isinstance(row, dict)]
        return [_json_object(payload)]
    raise ValueError("JSON ground-truth input must be an object or list of objects")


def _read_jsonl_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL line {line_number} must be an object")
        rows.append(_json_object(payload))
    return rows


def _json_object(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "ndjson":
        return "jsonl"
    if suffix in SUPPORTED_FORMATS:
        return suffix
    raise ValueError("Cannot detect input format from file extension")


def _normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for key, value in row.items():
        normalized[_normalize_header(key)] = value
    return normalized


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
        normalized_name = _normalize_header(name)
        if normalized_name in row:
            return row[normalized_name]
    return ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_header(header: str | None) -> str:
    return "".join(ch for ch in str(header or "").lower() if ch.isalnum())


def _dedupe_key(*, name: str, source: str, url: str) -> str:
    source_or_url = url or _normalize_name(source)
    return f"{_normalize_name(name)}|{source_or_url}"


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _normalize_public_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    if parts.username or parts.password:
        return ""

    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not _is_public_host(host):
        return ""

    scheme = parts.scheme.lower()
    netloc = host
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, parts.path or "", query, ""))


def _is_public_host(host: str) -> bool:
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
