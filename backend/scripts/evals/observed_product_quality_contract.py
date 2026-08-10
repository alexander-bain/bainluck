"""Replacement measurement contracts for staleness and interestingness."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def observed_staleness(
    impressions: list[dict[str, Any]],
    lifecycle_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Measure observed impressions, never eligible inventory or fixture intent."""
    stale = 0
    unknown = 0
    reasons: Counter[str] = Counter()
    surfaces: Counter[str] = Counter()
    for impression in impressions:
        surfaces[str(impression.get("surface") or "unknown")] += 1
        authority = lifecycle_by_id.get(str(impression.get("card_id")))
        if not authority or authority.get("authoritative_stale") is None:
            unknown += 1
            reasons["missing_authority"] += 1
            continue
        if authority["authoritative_stale"]:
            stale += 1
            reasons[str(authority.get("reason") or "unspecified")] += 1
    total = len(impressions)
    known = total - unknown
    return {
        "impressions": total,
        "known": known,
        "unknown": unknown,
        "stale": stale,
        "stale_rate_known": stale / known if known else None,
        "unknown_rate": unknown / total if total else None,
        "reasons": dict(sorted(reasons.items())),
        "surfaces": dict(sorted(surfaces.items())),
    }


def temporal_interestingness_split(
    rows: list[dict[str, Any]],
    *,
    cutoff: str,
    min_holdout: int = 50,
) -> dict[str, Any]:
    """Split by time and refuse item leakage or unusable holdout evidence."""
    cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    train: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    invalid = 0
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row["labeled_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        (train if observed < cutoff_dt else holdout).append(row)

    train_ids = {str(row.get("item_id")) for row in train}
    holdout_ids = {str(row.get("item_id")) for row in holdout}
    leakage = sorted(train_ids & holdout_ids)
    labels = [row.get("label") for row in holdout if row.get("label") in (0, 1)]
    reasons: list[str] = []
    if invalid:
        reasons.append("INVALID_LABEL_TIMESTAMPS")
    if leakage:
        reasons.append("ITEM_ID_LEAKAGE")
    if len(holdout) < min_holdout:
        reasons.append("HOLDOUT_TOO_SMALL")
    if not labels or len(set(labels)) < 2:
        reasons.append("HOLDOUT_ONE_CLASS")
    if len(labels) != len(holdout):
        reasons.append("HOLDOUT_LABELS_INCOMPLETE")
    return {
        "verdict": "EVALUATE" if not reasons else "REFUSE",
        "reasons": sorted(reasons),
        "train_rows": len(train),
        "holdout_rows": len(holdout),
        "train_item_ids": sorted(train_ids),
        "holdout_item_ids": sorted(holdout_ids),
        "leaked_item_ids": leakage,
        "holdout_positives": sum(labels),
        "holdout_negatives": len(labels) - sum(labels),
        "cutoff": cutoff,
    }


def member_conservation(case: dict[str, Any]) -> dict[str, Any]:
    input_ids = set(case.get("input_member_ids") or [])
    rendered_ids = set(case.get("rendered_member_ids") or [])
    explicitly_refused = set(case.get("explicitly_refused_ids") or [])
    missing = sorted(input_ids - rendered_ids - explicitly_refused)
    return {
        "verdict": "ALLOW" if not missing else "REFUSE",
        "missing_member_ids": missing,
    }
