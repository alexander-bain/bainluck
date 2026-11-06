"""#12095 Decide 37-B: read the ranking eval harness's slates; take one now.

* ``GET  /api/admin/ranking/slates?surface=discover&limit=14`` — newest first,
  one summary line per stored slate.
* ``GET  /api/admin/ranking/slates/{ref}`` — one slate in full (served order +
  candidates), the JSON ``tools/ranking/scorecard.py`` reads. ``ref`` is the
  row id, a slate id (the deck's ``edition``), or ``latest``.
* ``GET  /api/admin/ranking/grading-sheet?slate=latest&top=10`` — the slate's
  opening ten as a grading sheet with empty grades.
* ``POST /api/admin/ranking/slates/capture`` — take one slate now (the nightly
  job's own function). Refused while ``RANKING_SNAPSHOTS`` is off.

Admin auth on every endpoint. The reads touch only ``ranking_slate_snapshots``;
the capture writes only there.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RankingSlateSnapshot
from app.routes.admin_utils import _check_admin_secret
from app.services.database import get_db, get_db_rw
from app.utils.ranking_eval import (
    SURFACE_DISCOVER,
    grading_sheet,
    ranking_snapshots_enabled,
    slate_row_dict,
    snapshot_ranking_slate,
)

router = APIRouter(prefix="/admin/ranking", tags=["admin-ranking-eval"])


async def _slate_row(db: AsyncSession, ref: str, surface: str):
    stmt = select(RankingSlateSnapshot).where(RankingSlateSnapshot.surface == surface)
    if ref != "latest":
        stmt = stmt.where(
            or_(RankingSlateSnapshot.id == ref, RankingSlateSnapshot.slate_id == ref)
        )
    stmt = stmt.order_by(RankingSlateSnapshot.captured_at.desc()).limit(1)
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no {surface} slate for {ref!r}")
    return row


@router.get("/slates")
async def list_ranking_slates(
    request: Request,
    surface: str = Query(SURFACE_DISCOVER, max_length=32),
    limit: int = Query(14, ge=1, le=100),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    rows = (
        await db.execute(
            select(
                RankingSlateSnapshot.id,
                RankingSlateSnapshot.slate_id,
                RankingSlateSnapshot.captured_at,
                RankingSlateSnapshot.ranker_version,
                RankingSlateSnapshot.summary,
            )
            .where(RankingSlateSnapshot.surface == surface)
            .order_by(RankingSlateSnapshot.captured_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "switch_on": ranking_snapshots_enabled(),
        "surface": surface,
        "slates": [
            {
                "id": r.id,
                "slate_id": r.slate_id,
                "captured_at": r.captured_at.isoformat() if r.captured_at else None,
                "ranker_version": r.ranker_version,
                "served_count": (r.summary or {}).get("served_count"),
                "candidate_count": (r.summary or {}).get("candidate_count"),
            }
            for r in rows
        ],
    }


@router.get("/slates/{ref}")
async def get_ranking_slate(
    ref: str,
    request: Request,
    surface: str = Query(SURFACE_DISCOVER, max_length=32),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    return slate_row_dict(await _slate_row(db, ref, surface))


@router.get("/grading-sheet")
async def get_grading_sheet(
    request: Request,
    slate: str = Query("latest", max_length=64),
    surface: str = Query(SURFACE_DISCOVER, max_length=32),
    top: int = Query(10, ge=1, le=50),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    return grading_sheet(slate_row_dict(await _slate_row(db, slate, surface)), top=top)


@router.post("/slates/capture")
async def capture_ranking_slate(
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
) -> dict:
    _check_admin_secret(secret, request=request)
    if not ranking_snapshots_enabled():
        raise HTTPException(status_code=409, detail="RANKING_SNAPSHOTS is off")
    return await snapshot_ranking_slate(db)
