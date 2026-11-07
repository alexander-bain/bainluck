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
* ``GET  /api/admin/ranking/grade-deck`` — Phase 2: the latest slate's opening
  ten with each card's served payload, for the ``/grade`` page.
* ``POST /api/admin/ranking/grades`` — Phase 2: one grader's grade for one of
  those cards. Refused while ``RANKING_SNAPSHOTS`` is off.
* ``GET  /api/admin/ranking/grades`` — grades (latest per grader and card) and
  today's family tally; ``tools/ranking/grades.py export`` writes them to
  ``evals/ranking/grades/``.

Admin auth on every endpoint. The reads touch only ``ranking_slate_snapshots``
and ``ranking_grades``; the writes go only there.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RankingGrade, RankingSlateSnapshot
from app.routes.admin_utils import _check_admin_secret
from app.services.database import get_db, get_db_rw
from app.utils.ranking_eval import (
    OPENING_CARDS,
    SURFACE_DISCOVER,
    grading_sheet,
    ranking_snapshots_enabled,
    slate_row_dict,
)
from app.utils.ranking_slate_capture import snapshot_ranking_slate

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


GRADES = ("shareable", "interesting", "neither")
#: The family tally counts a grader's cards graded since local midnight here.
TALLY_TZ = ZoneInfo("America/Los_Angeles")


def opening_cards(slate: dict) -> list[dict]:
    """The slate's opening ten as the grading page shows them."""
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or ()}
    out = []
    for position, key in enumerate((slate.get("served_order") or [])[:OPENING_CARDS], start=1):
        cand = by_key.get(key) or {}
        out.append(
            {
                "position": position,
                "item_key": key,
                "title": cand.get("title"),
                "probability": cand.get("probability"),
                "card": cand.get("card"),
            }
        )
    return out


@router.get("/grade-deck")
async def get_grade_deck(
    request: Request,
    surface: str = Query(SURFACE_DISCOVER, max_length=32),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    slate = slate_row_dict(await _slate_row(db, "latest", surface))
    return {
        "switch_on": ranking_snapshots_enabled(),
        "slate_id": slate["slate_id"],
        "surface": slate["surface"],
        "captured_at": slate["captured_at"],
        "ranker_version": slate["ranker_version"],
        "items": opening_cards(slate),
    }


class GradeIn(BaseModel):
    slate_id: str = Field(..., min_length=1, max_length=64)
    surface: str = Field(SURFACE_DISCOVER, max_length=32)
    grader: str = Field(..., min_length=1, max_length=40)
    kid: bool = False
    position: int = Field(..., ge=1, le=OPENING_CARDS)
    item_key: str = Field(..., min_length=1, max_length=120)
    grade: str
    note: str | None = Field(None, max_length=300)


@router.post("/grades")
async def post_grade(
    body: GradeIn,
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
) -> dict:
    _check_admin_secret(secret, request=request)
    if not ranking_snapshots_enabled():
        raise HTTPException(status_code=409, detail="RANKING_SNAPSHOTS is off")
    if body.grade not in GRADES:
        raise HTTPException(status_code=422, detail=f"grade must be one of {GRADES}")
    grader = " ".join(body.grader.split())
    if not grader:
        raise HTTPException(status_code=422, detail="grader needs a name")
    slate = slate_row_dict(await _slate_row(db, body.slate_id, body.surface))
    if slate["slate_id"] != body.slate_id:
        raise HTTPException(status_code=404, detail="no such slate")
    order = slate["served_order"][:OPENING_CARDS]
    if body.position > len(order) or order[body.position - 1] != body.item_key:
        raise HTTPException(status_code=422, detail="that card is not at that position in the slate")
    db.add(
        RankingGrade(
            slate_id=body.slate_id,
            surface=body.surface,
            grader=grader,
            expert=not body.kid,
            position=body.position,
            item_key=body.item_key,
            grade=body.grade,
            note=(body.note or "").strip() or None,
        )
    )
    await db.commit()
    return {"status": "ok"}


def latest_grades(rows) -> list[dict]:
    """One grade per (slate, grader, card): the most recent wins."""
    latest: dict[tuple, dict] = {}
    for r in sorted(rows, key=lambda r: (r.graded_at, r.id or 0)):
        latest[(r.slate_id, r.grader, r.item_key)] = {
            "slate_id": r.slate_id,
            "surface": r.surface,
            "grader": r.grader,
            "expert": r.expert,
            "position": r.position,
            "item_key": r.item_key,
            "grade": r.grade,
            "note": r.note or "",
            "graded_at": r.graded_at.isoformat() if r.graded_at else None,
        }
    return list(latest.values())


def family_tally(grades: list[dict], now: datetime) -> list[dict]:
    """Per grader, the cards they graded since local midnight (Pacific)."""
    midnight = now.astimezone(TALLY_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    counts: dict[str, dict] = {}
    for g in grades:
        at = datetime.fromisoformat(g["graded_at"]) if g["graded_at"] else None
        if at is None or at < midnight:
            continue
        entry = counts.setdefault(g["grader"], {"grader": g["grader"], "kid": not g["expert"], "today": 0})
        entry["today"] += 1
    return sorted(counts.values(), key=lambda e: (-e["today"], e["grader"]))


@router.get("/grades")
async def get_grades(
    request: Request,
    slate_id: str | None = Query(None, max_length=64),
    days: int = Query(14, ge=1, le=90),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    now = datetime.now(timezone.utc)
    stmt = select(RankingGrade).where(RankingGrade.graded_at >= now - timedelta(days=days))
    if slate_id:
        stmt = stmt.where(RankingGrade.slate_id == slate_id)
    grades = latest_grades((await db.execute(stmt)).scalars().all())
    return {"grades": grades, "tally": family_tally(grades, now)}
