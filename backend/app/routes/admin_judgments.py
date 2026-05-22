"""API endpoints for ranking judgments (Discover feed review)."""

import csv
import io
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RankingJudgment
from fastapi import Depends
from app.services import get_db, get_db_rw

router = APIRouter(prefix="/admin/ranking-judgments", tags=["admin-judgments"])
logger = logging.getLogger(__name__)


from app.routes.admin_utils import _check_admin_secret


@router.post("")
async def create_judgment(
    db: AsyncSession = Depends(get_db_rw),
    secret: str = Query(...),
    surface: str = Query("discover"),
    rank_seen: int | None = Query(None),
    item_type: str = Query("futures"),
    market_id: int | None = Query(None),
    event_id: int | None = Query(None),
    market_name: str | None = Query(None),
    label: str = Query(...),
    reason_tags: str = Query(""),
    better_than: str | None = Query(None),
    worse_than: str | None = Query(None),
    notes: str | None = Query(None),
    score_at_review: float | None = Query(None),
    category_at_review: str | None = Query(None),
    archetype_at_review: str | None = Query(None),
    quality_class_at_review: str | None = Query(None),
    headline_at_review: str | None = Query(None),
    feed_request_id: str | None = Query(None),
    reviewer: str = Query("alex"),
):
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    tags = [t.strip() for t in reason_tags.split(",") if t.strip()] if reason_tags else []

    judgment = RankingJudgment(
            surface=surface,
            rank_seen=rank_seen,
            item_type=item_type,
            market_id=market_id,
            event_id=event_id,
            market_name=market_name,
            label=label,
            reason_tags=tags,
            better_than=better_than,
            worse_than=worse_than,
            notes=notes,
            score_at_review=score_at_review,
            category_at_review=category_at_review,
            archetype_at_review=archetype_at_review,
            quality_class_at_review=quality_class_at_review,
            headline_at_review=headline_at_review,
            feed_request_id=feed_request_id,
            reviewer=reviewer,
        )
    db.add(judgment)
    await db.commit()
    await db.refresh(judgment)
    return {"id": judgment.id, "label": judgment.label}


@router.get("")
async def list_judgments(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    limit: int = Query(50),
    offset: int = Query(0),
    label: str | None = Query(None),
    surface: str | None = Query(None),
):
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

        q = select(RankingJudgment).order_by(desc(RankingJudgment.created_at))
        count_q = select(func.count(RankingJudgment.id))

        if label:
            q = q.where(RankingJudgment.label == label)
            count_q = count_q.where(RankingJudgment.label == label)
        if surface:
            q = q.where(RankingJudgment.surface == surface)
            count_q = count_q.where(RankingJudgment.surface == surface)

        total = (await db.execute(count_q)).scalar() or 0
        rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

        # Summary counts
        summary_q = select(
            RankingJudgment.label,
            func.count(RankingJudgment.id),
        ).group_by(RankingJudgment.label)
        summary_rows = (await db.execute(summary_q)).all()
        summary = {row[0]: row[1] for row in summary_rows}

        return {
            "total": total,
            "summary": summary,
            "judgments": [
                {
                    "id": j.id,
                    "date": str(j.date) if j.date else None,
                    "surface": j.surface,
                    "rank_seen": j.rank_seen,
                    "item_type": j.item_type,
                    "market_id": j.market_id,
                    "market_name": j.market_name,
                    "label": j.label,
                    "reason_tags": j.reason_tags or [],
                    "better_than": j.better_than,
                    "worse_than": j.worse_than,
                    "notes": j.notes,
                    "score_at_review": j.score_at_review,
                    "category_at_review": j.category_at_review,
                    "reviewer": j.reviewer,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in rows
            ],
        }


@router.get("/summary")
async def judgment_summary(db: AsyncSession = Depends(get_db), secret: str = Query(...)):
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

        # Label distribution
        label_q = select(
            RankingJudgment.label,
            func.count(RankingJudgment.id),
        ).group_by(RankingJudgment.label)
        label_rows = (await db.execute(label_q)).all()

        # Category breakdown
        cat_q = select(
            RankingJudgment.category_at_review,
            RankingJudgment.label,
            func.count(RankingJudgment.id),
        ).group_by(RankingJudgment.category_at_review, RankingJudgment.label)
        cat_rows = (await db.execute(cat_q)).all()

        # Score by label
        score_q = select(
            RankingJudgment.label,
            func.avg(RankingJudgment.score_at_review),
            func.min(RankingJudgment.score_at_review),
            func.max(RankingJudgment.score_at_review),
            func.count(RankingJudgment.id),
        ).where(RankingJudgment.score_at_review.isnot(None)).group_by(RankingJudgment.label)
        score_rows = (await db.execute(score_q)).all()

        # Pairwise count
        pairwise_count = (await db.execute(
            select(func.count(RankingJudgment.id)).where(
                (RankingJudgment.better_than.isnot(None)) | (RankingJudgment.worse_than.isnot(None))
            )
        )).scalar() or 0

        total = sum(r[1] for r in label_rows)

        return {
            "total": total,
            "labels": {r[0]: r[1] for r in label_rows},
            "pairwise_count": pairwise_count,
            "score_by_label": [
                {
                    "label": r[0],
                    "avg_score": round(r[1], 1) if r[1] else None,
                    "min_score": round(r[2], 1) if r[2] else None,
                    "max_score": round(r[3], 1) if r[3] else None,
                    "count": r[4],
                }
                for r in score_rows
            ],
            "by_category": {},
        }


@router.get("/export")
async def export_judgments(db: AsyncSession = Depends(get_db), secret: str = Query(...)):
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

        rows = (await db.execute(
            select(RankingJudgment).order_by(RankingJudgment.created_at)
        )).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date", "surface", "rank_seen", "item_type", "market_id",
        "market_name", "label", "reason_tags", "better_than", "worse_than",
        "notes", "score_at_review", "category_at_review", "archetype_at_review",
        "quality_class_at_review", "headline_at_review", "feed_request_id", "reviewer",
    ])
    for j in rows:
        writer.writerow([
            j.date, j.surface, j.rank_seen, j.item_type, j.market_id,
            j.market_name, j.label, ",".join(j.reason_tags or []),
            j.better_than, j.worse_than, j.notes, j.score_at_review,
            j.category_at_review, j.archetype_at_review, j.quality_class_at_review,
            j.headline_at_review, j.feed_request_id, j.reviewer,
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ranking_judgments.csv"},
    )
