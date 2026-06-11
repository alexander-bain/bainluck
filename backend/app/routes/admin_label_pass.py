"""Admin endpoints for the label speed-pass UI.

Serves pending LLM-proposed review decisions with frozen feature vectors,
and records human verdicts (accept/reject/skip).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DiscoverReviewDecision, FuturesMarket
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw

router = APIRouter()


@router.get("/label-pass/pending")
async def label_pass_pending(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return pending LLM-proposed decisions with frozen features."""
    _check_admin_secret(secret)

    result = await db.execute(
        select(DiscoverReviewDecision)
        .where(
            DiscoverReviewDecision.decision.in_(
                ["llm_proposed_promote", "llm_proposed_downrank"]
            ),
        )
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(500)
    )
    proposals = result.scalars().all()

    # Filter out already-verdicted ones (check for a matching accepted/rejected row)
    verdicted_ids = set()
    if proposals:
        item_keys = [(p.item_type, p.item_id) for p in proposals]
        verdict_result = await db.execute(
            select(
                DiscoverReviewDecision.item_type,
                DiscoverReviewDecision.item_id,
            ).where(
                DiscoverReviewDecision.decision.in_([
                    "accepted_promote", "rejected_promote",
                    "accepted_downrank", "rejected_downrank",
                    "skipped",
                ]),
            )
        )
        for row in verdict_result.all():
            verdicted_ids.add((row[0], row[1]))

    pending = [
        p for p in proposals
        if (p.item_type, p.item_id) not in verdicted_ids
    ]

    # Build feature vectors for each pending item
    items = []
    for p in pending:
        features = p.features or {}

        # If features not yet frozen, try to build them now
        if not features and p.item_id:
            try:
                market_id = int(p.item_id)
                mkt = await db.execute(
                    select(FuturesMarket).where(FuturesMarket.id == market_id)
                )
                market = mkt.scalar_one_or_none()
                if market:
                    features = {
                        "probability": None,
                        "movement_24h": None,
                        "volume_24h": market.volume_24h,
                        "category": market.llm_sport_category,
                        "market_tier": market.market_tier,
                    }
            except (ValueError, TypeError):
                pass

        items.append({
            "id": p.id,
            "item_type": p.item_type,
            "item_id": p.item_id,
            "item_name": p.item_name,
            "category": p.category,
            "archetype": p.archetype,
            "decision": p.decision,
            "admin_notes": p.admin_notes,
            "features": features,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {"items": items, "total": len(items)}


class VerdictRequest(BaseModel):
    decision_id: int
    verdict: str
    features: dict = {}


@router.post("/label-pass/verdict")
async def label_pass_verdict(
    body: VerdictRequest,
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Record a human verdict on an LLM proposal."""
    _check_admin_secret(secret)

    if body.verdict not in ("accept", "reject", "skip"):
        raise HTTPException(status_code=400, detail="verdict must be accept/reject/skip")

    # Load the original proposal
    original = await db.execute(
        select(DiscoverReviewDecision)
        .where(DiscoverReviewDecision.id == body.decision_id)
    )
    proposal = original.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Determine the new decision label
    action = proposal.decision.replace("llm_proposed_", "")
    if body.verdict == "skip":
        new_decision = "skipped"
    else:
        new_decision = f"{body.verdict}ed_{action}"

    # Write new decision row with frozen features
    new_row = DiscoverReviewDecision(
        item_type=proposal.item_type,
        item_id=proposal.item_id,
        item_name=proposal.item_name,
        category=proposal.category,
        surface="label_pass",
        archetype=proposal.archetype,
        decision=new_decision,
        admin_notes=f"Speed-pass verdict on proposal #{proposal.id}",
        features=body.features or proposal.features,
    )
    db.add(new_row)
    await db.commit()

    return {"status": "ok", "decision": new_decision, "new_id": new_row.id}
