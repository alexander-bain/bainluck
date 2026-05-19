"""DB persistence helpers for reviewed external-curator ground truth."""

from __future__ import annotations

import re
from hashlib import sha256
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ExternalCuratorGroundTruthItem
from app.utils.external_curator_ground_truth import (
    build_external_curator_ground_truth_report,
    normalize_external_curator_ground_truth_rows,
)

ACCEPTED_REVIEW_STATUSES = {"accepted", "approved", "reviewed"}
DEFAULT_LIMIT = 1000


def build_external_curator_dedupe_key(row: dict[str, Any]) -> str:
    """Build the same durable row identity used by the DB import path."""
    name = _normalize_name(str(row.get("name") or ""))
    source = _normalize_name(str(row.get("source") or "external_curator"))
    url = str(row.get("url") or "").strip()
    identity = f"{name}|{url or source}"
    return sha256(identity.encode("utf-8")).hexdigest()


def normalize_persistable_external_curator_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Normalize and keep only rows safe to persist for diagnostics."""
    return [
        {
            **row,
            "review_status": row.get("review_status") or "accepted",
        }
        for row in normalize_external_curator_ground_truth_rows(rows)
        if row.get("name")
    ]


async def import_external_curator_ground_truth_rows(
    db: AsyncSession,
    rows: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """Upsert reviewed curator rows into the persisted audit source table."""
    normalized_rows = normalize_persistable_external_curator_rows(rows)
    inserted = 0
    updated = 0
    skipped = 0

    for row in normalized_rows:
        status = (row.get("review_status") or "").lower()
        if status not in ACCEPTED_REVIEW_STATUSES:
            skipped += 1
            continue

        dedupe_key = build_external_curator_dedupe_key(row)
        existing = await db.scalar(
            select(ExternalCuratorGroundTruthItem).where(
                ExternalCuratorGroundTruthItem.dedupe_key == dedupe_key
            )
        )
        values = _model_values(row, dedupe_key=dedupe_key)
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(ExternalCuratorGroundTruthItem(**values))
            inserted += 1

    await db.commit()
    return {
        "input_rows": len(normalized_rows),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


async def load_persisted_external_curator_ground_truth_report(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Load reviewed persisted curator rows in the external-curator report shape."""
    result = await db.execute(
        select(ExternalCuratorGroundTruthItem)
        .where(ExternalCuratorGroundTruthItem.review_status.in_(ACCEPTED_REVIEW_STATUSES))
        .order_by(ExternalCuratorGroundTruthItem.imported_at.desc())
        .limit(limit)
    )
    items = [_item_from_model(row) for row in result.scalars().all()]
    return build_external_curator_ground_truth_report(
        items,
        configured=bool(items),
        source_paths=["db:external_curator_ground_truth_items"] if items else [],
        raw_row_count=len(items),
        error=None,
        now=now,
    )


def merge_external_curator_ground_truth_reports(
    reports: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Merge file and DB external-curator reports into one normalized report."""
    items: list[dict[str, str]] = []
    source_paths: list[str] = []
    raw_row_count = 0
    errors: list[str] = []
    configured = False

    for report in reports:
        metadata = report.get("metadata") or {}
        configured = configured or bool(metadata.get("configured"))
        raw_row_count += int(metadata.get("raw_row_count") or 0)
        source_paths.extend(metadata.get("source_paths") or [])
        if metadata.get("error"):
            errors.append(str(metadata["error"]))
        items.extend(report.get("items") or [])

    return build_external_curator_ground_truth_report(
        items,
        configured=configured,
        source_paths=source_paths,
        raw_row_count=raw_row_count,
        error="; ".join(errors) if errors else None,
        now=now,
    )


def _model_values(row: dict[str, str], *, dedupe_key: str) -> dict[str, Any]:
    return {
        "dedupe_key": dedupe_key,
        "source": row.get("source") or "external_curator",
        "category": row.get("category") or None,
        "name": row.get("name") or "",
        "probability": row.get("probability") or None,
        "hook": row.get("hook") or None,
        "url": row.get("url") or None,
        "published_at": row.get("published_at") or None,
        "platform": row.get("platform") or None,
        "handle": row.get("handle") or None,
        "engagement": row.get("engagement") or None,
        "evidence": row.get("evidence") or None,
        "confidence": row.get("confidence") or None,
        "extraction_notes": row.get("extraction_notes") or None,
        "review_status": row.get("review_status") or "accepted",
        "raw": row,
    }


def _item_from_model(row: ExternalCuratorGroundTruthItem) -> dict[str, str]:
    return {
        "source": row.source or "external_curator",
        "category": row.category or "?",
        "name": row.name or "",
        "probability": row.probability or "",
        "hook": row.hook or "",
        "url": row.url or "",
        "published_at": row.published_at or "",
        "platform": row.platform or "",
        "handle": row.handle or "",
        "engagement": row.engagement or "",
        "evidence": row.evidence or "",
        "confidence": row.confidence or "",
        "extraction_notes": row.extraction_notes or "",
        "review_status": row.review_status or "accepted",
    }


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))
