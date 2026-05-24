"""Persisted human-label eval runs for Discover ranking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DiscoverLabelEvalRun, RankingJudgment
from app.utils.discover_reason_tags import canonical_reason_tags
from scripts.evaluate_discover_label_gold_set import evaluate_gold_set

SCALAR_METRIC_KEYS = [
    "tapworthy_at_k",
    "boring_rate_at_k",
    "duplicate_family_rate_at_k",
    "unclear_rate_at_k",
    "bad_explanation_rate_at_k",
    "bad_image_rate_at_k",
    "broad_appeal_at_k",
    "fixable_interest_rate_at_k",
    "tapworthy_recall_at_k",
]


async def snapshot_discover_label_eval_run(
    db: AsyncSession,
    *,
    days: int = 30,
    top_k: int = 20,
    limit: int = 5000,
    surface: str | None = None,
    reviewer: str | None = None,
) -> DiscoverLabelEvalRun:
    """Compute and persist one human-label gold-set eval run."""

    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=days)
    rows = await load_label_eval_rows(
        db,
        window_start=window_start,
        limit=limit,
        surface=surface,
        reviewer=reviewer,
    )
    metric_summary = evaluate_gold_set(rows, top_k=top_k)
    category_breakdowns = build_category_breakdowns(rows)
    previous = await load_previous_run(
        db,
        top_k=top_k,
        surface=surface,
        reviewer=reviewer,
    )
    notable_regressions = detect_regressions(metric_summary, previous)
    run = DiscoverLabelEvalRun(
        run_id=str(uuid4()),
        eval_name="discover_label_gold_set",
        status="ok",
        input_source="ranking_judgments",
        dataset_window_start=window_start,
        dataset_window_end=window_end,
        surface=surface,
        reviewer=reviewer,
        top_k=top_k,
        row_count=len(rows),
        metric_summary=metric_summary,
        category_breakdowns=category_breakdowns,
        notable_regressions=notable_regressions,
        eval_metadata={"days": days, "limit": limit},
        **scalar_metric_values(metric_summary, top_k=top_k),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def load_label_eval_rows(
    db: AsyncSession,
    *,
    window_start: datetime,
    limit: int,
    surface: str | None = None,
    reviewer: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        select(RankingJudgment)
        .where(RankingJudgment.created_at >= window_start)
        .order_by(desc(RankingJudgment.created_at), RankingJudgment.id.desc())
        .limit(limit)
    )
    if surface:
        query = query.where(RankingJudgment.surface == surface)
    if reviewer:
        query = query.where(RankingJudgment.reviewer == reviewer)
    result = await db.execute(query)
    return [judgment_to_eval_row(row) for row in result.scalars().all()]


def judgment_to_eval_row(judgment: RankingJudgment) -> dict[str, Any]:
    metadata = judgment.label_metadata if isinstance(judgment.label_metadata, dict) else {}
    fixable = metadata.get("fixable_interest") if isinstance(metadata, dict) else {}
    if not isinstance(fixable, dict):
        fixable = {}
    return {
        "id": f"{judgment.item_type}:{judgment.market_id or judgment.event_id or judgment.id}",
        "judgment_id": judgment.id,
        "name": judgment.market_name or "",
        "label": judgment.label,
        "rank_seen": judgment.rank_seen,
        "score_at_review": judgment.score_at_review,
        "category": judgment.category_at_review or "unknown",
        "quality_class": judgment.quality_class_at_review or "",
        "reason_tags": ",".join(canonical_reason_tags(judgment.reason_tags)),
        "tapworthy_score": metadata.get("tapworthy_score", ""),
        "boring": metadata.get("boring", ""),
        "clarity": metadata.get("clarity", ""),
        "explanation_quality": metadata.get("explanation_quality", ""),
        "image_fit": metadata.get("image_fit", ""),
        "audience_scope": metadata.get("audience_scope", ""),
        "resolution_importance": metadata.get("resolution_importance", ""),
        "duplicate_severity": metadata.get("duplicate_severity", ""),
        "would_be_interesting_if": fixable.get("would_be_interesting_if", ""),
        "fixable_interest_score": fixable.get("fixable_interest_score", ""),
        "fix_type": fixable.get("fix_type", ""),
        "desired_entity_or_variant": fixable.get("desired_entity_or_variant", ""),
        "current_entity_or_variant": fixable.get("current_entity_or_variant", ""),
        "create_issue_candidate": fixable.get("create_issue_candidate", ""),
    }


def build_category_breakdowns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("category") or "unknown"), []).append(row)

    breakdowns = {}
    for category, category_rows in grouped.items():
        metrics = evaluate_gold_set(category_rows, top_k=min(20, len(category_rows)))
        breakdowns[category] = {
            "row_count": len(category_rows),
            "label_counts": metrics["label_counts"],
            "fixable_interest": metrics["fixable_interest"],
        }
    return dict(sorted(breakdowns.items()))


async def load_previous_run(
    db: AsyncSession,
    *,
    top_k: int,
    surface: str | None,
    reviewer: str | None,
) -> DiscoverLabelEvalRun | None:
    query = (
        select(DiscoverLabelEvalRun)
        .where(
            DiscoverLabelEvalRun.eval_name == "discover_label_gold_set",
            DiscoverLabelEvalRun.top_k == top_k,
        )
        .order_by(desc(DiscoverLabelEvalRun.captured_at))
        .limit(1)
    )
    if surface is None:
        query = query.where(DiscoverLabelEvalRun.surface.is_(None))
    else:
        query = query.where(DiscoverLabelEvalRun.surface == surface)
    if reviewer is None:
        query = query.where(DiscoverLabelEvalRun.reviewer.is_(None))
    else:
        query = query.where(DiscoverLabelEvalRun.reviewer == reviewer)
    result = await db.execute(query)
    return result.scalars().first()


def scalar_metric_values(metrics: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    return {
        key: metrics.get(metric_key_for_column(key, top_k=top_k))
        for key in SCALAR_METRIC_KEYS
    }


def metric_key_for_column(column: str, *, top_k: int) -> str:
    prefix_by_column = {
        "tapworthy_at_k": "tapworthy_at",
        "boring_rate_at_k": "boring_rate_at",
        "duplicate_family_rate_at_k": "duplicate_family_rate_at",
        "unclear_rate_at_k": "unclear_rate_at",
        "bad_explanation_rate_at_k": "bad_explanation_rate_at",
        "bad_image_rate_at_k": "bad_image_rate_at",
        "broad_appeal_at_k": "broad_appeal_at",
        "fixable_interest_rate_at_k": "fixable_interest_rate_at",
        "tapworthy_recall_at_k": "tapworthy_recall_at",
    }
    prefix = prefix_by_column.get(column)
    return f"{prefix}_{top_k}" if prefix else column


def detect_regressions(
    metrics: dict[str, Any],
    previous: DiscoverLabelEvalRun | None,
    *,
    threshold: float = 0.05,
) -> list[dict[str, Any]]:
    if not previous:
        return []
    regressions = []
    current_values = scalar_metric_values(metrics, top_k=previous.top_k)
    for key, current in current_values.items():
        old = getattr(previous, key, None)
        if current is None or old is None:
            continue
        delta = float(current) - float(old)
        lower_is_better = key.endswith("_rate_at_k") and key != "fixable_interest_rate_at_k"
        regressed = delta > threshold if lower_is_better else delta < -threshold
        if regressed:
            regressions.append(
                {
                    "metric": key,
                    "previous": old,
                    "current": current,
                    "delta": round(delta, 6),
                }
            )
    return regressions


def serialize_eval_run(run: DiscoverLabelEvalRun, *, include_details: bool = False) -> dict[str, Any]:
    payload = {
        "run_id": run.run_id,
        "eval_name": run.eval_name,
        "status": run.status,
        "surface": run.surface,
        "reviewer": run.reviewer,
        "top_k": run.top_k,
        "row_count": run.row_count,
        "captured_at": run.captured_at.isoformat() if run.captured_at else None,
        "dataset_window_start": (
            run.dataset_window_start.isoformat() if run.dataset_window_start else None
        ),
        "dataset_window_end": (
            run.dataset_window_end.isoformat() if run.dataset_window_end else None
        ),
        **{key: getattr(run, key) for key in SCALAR_METRIC_KEYS},
        "notable_regressions": run.notable_regressions or [],
    }
    if include_details:
        payload.update(
            {
                "metric_summary": run.metric_summary or {},
                "category_breakdowns": run.category_breakdowns or {},
                "metadata": run.eval_metadata or {},
                "error": run.error,
            }
        )
    return payload
