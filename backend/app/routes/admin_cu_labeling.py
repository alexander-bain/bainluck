"""Admin endpoints for Content Understanding dual-rater fact labeling (#13900)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CuFactLabel, FuturesMarket
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils.cu_fact_labeling import (
    VALID_ROLES,
    VALID_SCOPES,
    VALID_SPLITS,
    build_answer_key_bundle,
    compute_cu_fact_agreement,
    extract_subject_candidates,
    frozen_split_exists,
    get_claim_vocabulary,
    load_frozen_split,
    load_repeatability_priority_ids,
    order_queue_markets,
    validate_label_submission,
    visible_labels_for_rater,
)

router = APIRouter()

DEFAULT_DATASET_MISSING_MESSAGE = (
    "The frozen market file for this set is not loaded on this server yet, "
    "so no cards are available to check."
)


def _row_to_dict(row: CuFactLabel) -> dict[str, Any]:
    return {
        "id": row.id,
        "dataset_split": row.dataset_split,
        "market_id": row.market_id,
        "rater": row.rater,
        "role": row.role,
        "subjects_answer": row.subjects_answer,
        "event_date_answer": row.event_date_answer,
        "no_single_day": bool(row.no_single_day),
        "geography_answer": row.geography_answer,
        "structure_answer": row.structure_answer,
        "claim_frame": row.claim_frame,
        "stakes": row.stakes,
        "breadth": row.breadth,
        "evidence_note": row.evidence_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _db_rows_for_split(db: AsyncSession, split: str) -> list[dict[str, Any]]:
    result = await db.execute(
        select(CuFactLabel)
        .where(CuFactLabel.dataset_split == split)
        .order_by(CuFactLabel.id.asc())
    )
    return [_row_to_dict(r) for r in result.scalars().all()]


def _validate_queue_params(split: str, role: str, scope: str, rater: str) -> str:
    if split not in VALID_SPLITS:
        raise HTTPException(status_code=400, detail=f"Invalid split {split!r}")
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role {role!r}")
    if scope not in VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"Invalid scope {scope!r}")
    cleaned_rater = " ".join(rater.split()).strip()
    if not cleaned_rater or len(cleaned_rater) > 64:
        raise HTTPException(
            status_code=400,
            detail="A typed labeler name (1-64 chars) is required",
        )
    return cleaned_rater


class CuFactLabelPayload(BaseModel):
    dataset_split: str
    market_id: int
    rater: str
    role: str
    subjects_answer: dict[str, Any]
    event_date_answer: str | None = None
    no_single_day: bool = False
    geography_answer: str
    structure_answer: str
    claim_frame: dict[str, Any] | None = None
    stakes: int | None = None
    breadth: int | None = None
    evidence_note: str | None = None


class SealedScorecardPayload(BaseModel):
    predictions: list[dict[str, Any]]
    as_of: str | None = None
    writer_rev: int | str | None = None
    model: str | None = None
    cost: dict[str, Any] | None = None
    run_id: str | None = None
    allow_missing_predictions: bool = False


def _run_sealed_scorecard(
    answer_key_rows: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
    *,
    as_of: str,
    writer_rev: int | str | None,
    model: str | None,
    cost: dict[str, Any] | None,
    run_id: str | None,
    withheld_fields: list[str],
) -> dict[str, Any]:
    from app.utils.cu_eval_scorecard import score_cu_eval_run

    return score_cu_eval_run(
        answer_key_rows,
        prediction_rows,
        as_of=as_of,
        writer_rev=writer_rev,
        model=model,
        dataset="sealed",
        cost=cost,
        run_id=run_id,
        withheld_fields=withheld_fields,
    )


def _build_blind_market_payload(
    market: dict[str, Any],
    market_rows: list[dict[str, Any]],
    *,
    role: str,
    rater: str,
) -> dict[str, Any]:
    """Assemble one market card without ever leaking discover_llm or peer answers."""
    vis = visible_labels_for_rater(market_rows, role=role, rater=rater)
    return {
        "market_id": int(market["market_id"]),
        "title": market.get("title") or "",
        "source": market.get("source") or "",
        "category": market.get("llm_sport_category") or market.get("category") or "",
        "draw_bucket": market.get("draw_bucket"),
        "rules_text": market.get("rules_text") or "",
        "resolution_date": market.get("resolution_date"),
        "outcomes": market.get("outcomes") or [],
        "outcome_names": market.get("outcome_names") or [],
        "subject_candidates": extract_subject_candidates(market),
        "own_label": vis["own_label"],
        "pair_complete": vis["pair_complete"],
        "peer_labels": vis["peer_labels"],
        "disagreeing_fact_fields": vis["disagreeing_fact_fields"],
    }


@router.get("/cu-labeling/queue")
async def cu_labeling_queue(
    request: Request,
    secret: str = Query(None),
    split: str = Query("sealed"),
    role: str = Query("primary"),
    scope: str = Query("shared_100"),
    rater: str = Query(...),
    include_completed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Serve one-by-one blind fact-labeling queue for primary, second, or tiebreak."""
    _check_admin_secret(secret, request=request)
    cleaned_rater = _validate_queue_params(split, role, scope, rater)

    file_present = frozen_split_exists(split)
    markets = load_frozen_split(split) if file_present else []
    priority_ids = load_repeatability_priority_ids() if (split == "dev" and file_present) else None
    ordered = order_queue_markets(
        markets,
        split=split,
        scope=scope,
        repeatability_priority_ids=priority_ids,
    )

    all_rows = await _db_rows_for_split(db, split)
    rows_by_market: dict[int, list[dict[str, Any]]] = {}
    for row in all_rows:
        rows_by_market.setdefault(int(row["market_id"]), []).append(row)

    queue_items: list[dict[str, Any]] = []
    completed_by_rater = 0
    for market in ordered:
        mid = int(market["market_id"])
        mrows = rows_by_market.get(mid, [])
        payload = _build_blind_market_payload(market, mrows, role=role, rater=cleaned_rater)
        if payload["own_label"] is not None:
            completed_by_rater += 1
        if role == "tiebreak" and not payload["disagreeing_fact_fields"]:
            continue
        if not include_completed and payload["own_label"] is not None:
            continue
        queue_items.append(payload)

    return {
        "split": split,
        "role": role,
        "scope": scope,
        "rater": cleaned_rater,
        "dataset_file_present": file_present,
        "dataset_file_missing_message": None if file_present else DEFAULT_DATASET_MISSING_MESSAGE,
        "claim_vocabulary": get_claim_vocabulary(),
        "total_in_scope": len(ordered),
        "completed_by_rater": completed_by_rater,
        "remaining": len(queue_items),
        "items": queue_items,
    }


@router.post("/cu-labeling/label")
async def cu_labeling_submit(
    request: Request,
    payload: CuFactLabelPayload,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Store one blind label or fact-only tiebreak row into cu_fact_labels."""
    _check_admin_secret(secret, request=request)

    market_exists = (
        await db.execute(
            select(FuturesMarket.id).where(FuturesMarket.id == int(payload.market_id))
        )
    ).scalar_one_or_none()
    if market_exists is None:
        raise HTTPException(
            status_code=404,
            detail=f"Market {payload.market_id} does not exist in futures_markets",
        )

    existing_rows = [
        _row_to_dict(r)
        for r in (
            await db.execute(
                select(CuFactLabel).where(
                    CuFactLabel.dataset_split == payload.dataset_split,
                    CuFactLabel.market_id == int(payload.market_id),
                )
            )
        )
        .scalars()
        .all()
    ]

    try:
        clean = validate_label_submission(
            payload.model_dump(),
            existing_market_rows=existing_rows,
        )
    except ValueError as validation_err:
        raise HTTPException(status_code=422, detail=str(validation_err)) from validation_err

    now = datetime.now(timezone.utc)
    stmt = pg_insert(CuFactLabel).values(
        dataset_split=clean["dataset_split"],
        market_id=clean["market_id"],
        rater=clean["rater"],
        role=clean["role"],
        subjects_answer=clean["subjects_answer"],
        event_date_answer=clean["event_date_answer"],
        no_single_day=clean["no_single_day"],
        geography_answer=clean["geography_answer"],
        structure_answer=clean["structure_answer"],
        claim_frame=clean["claim_frame"],
        stakes=clean["stakes"],
        breadth=clean["breadth"],
        evidence_note=clean["evidence_note"],
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cu_fact_labels_split_market_rater_role",
        set_={
            "subjects_answer": stmt.excluded.subjects_answer,
            "event_date_answer": stmt.excluded.event_date_answer,
            "no_single_day": stmt.excluded.no_single_day,
            "geography_answer": stmt.excluded.geography_answer,
            "structure_answer": stmt.excluded.structure_answer,
            "claim_frame": stmt.excluded.claim_frame,
            "stakes": stmt.excluded.stakes,
            "breadth": stmt.excluded.breadth,
            "evidence_note": stmt.excluded.evidence_note,
            "updated_at": now,
        },
    ).returning(CuFactLabel)

    saved = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return {"saved": True, "label": _row_to_dict(saved)}


@router.get("/cu-labeling/agreement")
async def cu_labeling_agreement(
    request: Request,
    secret: str = Query(None),
    split: str = Query("sealed"),
    db: AsyncSession = Depends(get_db),
):
    """Report per-field dual-rater agreement (exact for facts, +/-1 for taste)."""
    _check_admin_secret(secret, request=request)
    if split not in VALID_SPLITS:
        raise HTTPException(status_code=400, detail=f"Invalid split {split!r}")
    rows = await _db_rows_for_split(db, split)
    return compute_cu_fact_agreement(rows, split=split)


@router.get("/cu-labeling/export-answer-key")
async def cu_labeling_export_answer_key(
    request: Request,
    secret: str = Query(None),
    split: str = Query("dev"),
    db: AsyncSession = Depends(get_db),
):
    """Export development-set answer-key JSON; sealed answers never leave the server."""
    _check_admin_secret(secret, request=request)
    if split not in VALID_SPLITS:
        raise HTTPException(status_code=400, detail=f"Invalid split {split!r}")
    if split == "sealed":
        raise HTTPException(
            status_code=403,
            detail="Sealed answer keys cannot leave the server; POST predictions to /api/admin/cu-labeling/score-sealed instead.",
        )
    markets = load_frozen_split(split)
    markets_by_id = {int(m["market_id"]): m for m in markets}
    rows = await _db_rows_for_split(db, split)
    bundle = build_answer_key_bundle(markets_by_id, rows, split=split)
    return {
        "dataset": split,
        "count": len(bundle["rows"]),
        "withheld_taste_fields": bundle["withheld_taste_fields"],
        "agreement": bundle["agreement"],
        "rows": bundle["rows"],
    }


@router.post("/cu-labeling/score-sealed")
async def cu_labeling_score_sealed(
    request: Request,
    payload: SealedScorecardPayload,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Score predictions against sealed human labels strictly on the server."""
    _check_admin_secret(secret, request=request)
    markets = load_frozen_split("sealed")
    markets_by_id = {int(m["market_id"]): m for m in markets}
    rows = await _db_rows_for_split(db, "sealed")
    bundle = build_answer_key_bundle(markets_by_id, rows, split="sealed")
    answer_rows = bundle["rows"]
    withheld = bundle["withheld_taste_fields"]
    as_of = payload.as_of or datetime.now(timezone.utc).date().isoformat()

    try:
        scorecard = _run_sealed_scorecard(
            answer_rows,
            payload.predictions,
            as_of=as_of,
            writer_rev=payload.writer_rev,
            model=payload.model,
            cost=payload.cost,
            run_id=payload.run_id,
            withheld_fields=withheld,
        )
    except ImportError as import_err:
        raise HTTPException(
            status_code=503,
            detail="Scorecard evaluator is not yet available on this server build.",
        ) from import_err

    missing = int(scorecard.get("missing_predictions", 0) or 0)
    if missing > 0 and not payload.allow_missing_predictions:
        raise HTTPException(
            status_code=422,
            detail=f"Refusing sealed scorecard: {missing} sealed market(s) lack predictions.",
        )

    return {
        "scorecard": scorecard,
        "agreement": bundle["agreement"],
        "withheld_taste_fields": withheld,
    }
