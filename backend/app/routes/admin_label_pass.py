"""Admin endpoints for the label speed-pass UI.

Serves pending LLM-proposed review decisions with frozen feature vectors,
and records human verdicts (accept/reject/skip).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DiscoverReviewDecision, FuturesMarket
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils.eval_promote import (
    APPLIED_DECISIONS,
    EVAL_DOWNRANK_EXACT,
    EVAL_PROMOTE_ADJ,
    EVAL_PROMOTE_ENABLED_KEY,
    EVAL_PROMOTE_TTL_DAYS,
    is_enabled_value,
)

router = APIRouter()


async def _eval_promote_enabled() -> bool:
    """Read the #222 kill switch (fail-open)."""
    try:
        from app.tasks.redis_state import get_async_redis_client

        rc = get_async_redis_client()
        raw = await rc.get(EVAL_PROMOTE_ENABLED_KEY)
        await rc.aclose()
        return is_enabled_value(raw)
    except Exception:
        return True


@router.post("/eval-promote/toggle")
async def eval_promote_toggle(
    request: Request,
    secret: str = Query(None),
    enabled: bool = Query(
        None,
        description="Desired state: true=engage steers, false=kill. Omit to flip current.",
    ),
):
    """#232 Item 4: flip the eval-promote (#222) kill switch from the cockpit.

    Fail-open flag: enabled writes ``1``, disabled writes ``0`` (an explicit off
    token — see ``is_enabled_value``). L2-154 adds the cockpit button on top."""
    _check_admin_secret(secret, request=request)

    current = await _eval_promote_enabled()
    desired = (not current) if enabled is None else bool(enabled)

    from app.tasks.redis_state import get_async_redis_client

    rc = get_async_redis_client()
    try:
        await rc.set(EVAL_PROMOTE_ENABLED_KEY, "1" if desired else "0")
    finally:
        await rc.aclose()

    return {"enabled": desired, "previous": current, "key": EVAL_PROMOTE_ENABLED_KEY}


@router.get("/label-pass/pending")
async def label_pass_pending(
    request: Request, secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return pending LLM-proposed decisions with frozen features."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    body: VerdictRequest, secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Record a human verdict on an LLM proposal."""
    _check_admin_secret(secret, request=request)

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

    # #222: an Accept applies a bounded, expiring, kill-switchable term to
    # Discover ranking. Stamp the applied term onto the verdict row's features so
    # it is a real audit trail (magnitude, when, whether the switch was live),
    # and report `applied` so the client can log an honest GA `applied:true`.
    applied = False
    features = dict(body.features or proposal.features or {})
    if new_decision in APPLIED_DECISIONS:
        magnitude = EVAL_PROMOTE_ADJ if action == "promote" else -EVAL_DOWNRANK_EXACT
        applied = await _eval_promote_enabled()
        features["eval_promote"] = {
            "magnitude": magnitude,
            "action": action,
            "applied": applied,
            "ttl_days": EVAL_PROMOTE_TTL_DAYS,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "from_proposal": proposal.id,
        }

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
        features=features or None,
    )
    db.add(new_row)
    await db.commit()

    return {
        "status": "ok",
        "decision": new_decision,
        "new_id": new_row.id,
        "applied": applied,
    }


class UndoRequest(BaseModel):
    # Reverse by the verdict row id returned from /verdict (preferred)...
    decision_id: int | None = None
    # ...or by target when the caller only knows the item.
    item_type: str | None = None
    item_id: str | None = None


@router.post("/label-pass/undo")
async def label_pass_undo(
    request: Request,
    body: UndoRequest, secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Server-side undo (#222 Rapid-undo): delete the most recent verdict row for a
    target so any applied ranking boost is reverted AND the proposal returns to the
    pending queue. Reverses accept/reject/skip alike."""
    _check_admin_secret(secret, request=request)

    verdict_decisions = [
        "accepted_promote", "rejected_promote",
        "accepted_downrank", "rejected_downrank",
        "skipped",
    ]

    row = None
    if body.decision_id is not None:
        res = await db.execute(
            select(DiscoverReviewDecision).where(
                DiscoverReviewDecision.id == body.decision_id,
                DiscoverReviewDecision.decision.in_(verdict_decisions),
            )
        )
        row = res.scalar_one_or_none()
    elif body.item_type and body.item_id:
        res = await db.execute(
            select(DiscoverReviewDecision)
            .where(
                DiscoverReviewDecision.item_type == body.item_type,
                DiscoverReviewDecision.item_id == body.item_id,
                DiscoverReviewDecision.decision.in_(verdict_decisions),
            )
            .order_by(DiscoverReviewDecision.created_at.desc())
            .limit(1)
        )
        row = res.scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=400,
            detail="provide decision_id or (item_type and item_id)",
        )

    if not row:
        raise HTTPException(status_code=404, detail="No verdict to undo")

    reverted = row.decision
    reverted_target = (row.item_type, row.item_id)
    await db.delete(row)
    await db.commit()

    return {
        "status": "reverted",
        "reverted_decision": reverted,
        "item_type": reverted_target[0],
        "item_id": reverted_target[1],
    }
