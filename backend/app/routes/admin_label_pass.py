"""Admin endpoints for the label speed-pass UI.

Serves pending LLM-proposed review decisions with frozen feature vectors,
and records human verdicts (accept/reject/skip).

#1542 — lifecycle safety. Accept applies a bounded, expiring, kill-switchable
term to LIVE Discover ranking; Reject trains the scorer. A stale proposal (a
resolved/closed market, one past its resolution date, missing, superseded, or a
premise overtaken by events) therefore contaminates live ranking or training
whichever verdict is chosen. This module resolves every proposal to its
authoritative current market lifecycle before showing it (``/pending``) and
again, transactionally, before writing a verdict (``/verdict``). The decision
grammar is the C143 oracle, ported to ``app.utils.label_pass_lifecycle`` and
proven byte-equivalent by ``tests/test_label_pass_lifecycle.py``. Staleness is
NEVER inferred from title/LLM/news — only from authoritative lifecycle.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
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
    ttl_cutoff,
)
from app.utils.label_pass_lifecycle import (
    classify_pending,
    classify_post,
    read_evidence_generation,
    read_generation,
)

router = APIRouter()

_PROPOSAL_DECISIONS = ["llm_proposed_promote", "llm_proposed_downrank"]
_VERDICT_DECISIONS = [
    "accepted_promote", "rejected_promote",
    "accepted_downrank", "rejected_downrank",
    "skipped",
]


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


def _utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_market_id(item_type, item_id) -> bool:
    """A futures/event proposal keys ``item_id`` to a FuturesMarket PK; an email
    proposal keys it to a name slug that is NOT an authoritative market id."""
    return item_type != "email" and str(item_id).lstrip("-").isdigit()


def _effective_generation(proposal) -> str | None:
    """The proposal's generation, tracked separately from ``created_at``.

    Falls back to ``created_at`` for legacy rows (which predate generation
    stamping). ``created_at`` is no longer mutated by the evaluator (#1542), so
    this is stable across the GET→POST window."""
    gen = read_generation(proposal.features)
    if gen is not None:
        return gen
    return proposal.created_at.isoformat() if proposal.created_at else None


def _build_lifecycle_row(proposal, market, now, *, superseded, posted_generation="__omitted__"):
    """Map a proposal + its resolved market to the C143 contract row dict.

    Uses AUTHORITATIVE lifecycle only. ``authoritative_overtaken`` and
    ``title_or_llm_only_stale`` are intentionally never set True at runtime: the
    route has no authoritative overtaken feed yet, and prose (title/LLM/news)
    must never suppress a proposal on its own (the corpus proves those paths)."""
    features = proposal.features or {}
    gen = _effective_generation(proposal)
    ev_gen = read_evidence_generation(features)
    if ev_gen is None:
        ev_gen = gen  # legacy: evidence generation defaults to the proposal generation

    item_type = proposal.item_type
    market_id = proposal.item_id
    market_exists = market is not None
    if item_type == "email":
        # No authoritative market id until a canonical link exists.
        canonical = features.get("canonical_market_id")
    else:
        canonical = str(market.id) if market else None

    res_past = False
    status = None
    if market is not None:
        status = market.status
        rd = _utc(market.resolution_date)
        res_past = rd is not None and rd < now

    row = {
        "item_type": item_type,
        "market_id": market_id,
        "canonical_market_id": canonical,
        "market_exists": market_exists,
        "status": status,
        "resolution_date_past": res_past,
        "authoritative_overtaken": False,
        "title_or_llm_only_stale": False,
        "authority_available": True,
        "superseded": superseded,
        "proposal_generation": gen,
        "evidence_generation": ev_gen,
    }
    if posted_generation != "__omitted__":
        row["posted_generation"] = posted_generation
    else:
        row["posted_generation"] = gen
    return row


def _partition_candidates(candidates, markets, now):
    """Pure partition of pending proposals into actionable / retired / quarantined.

    Duck-typed (proposals expose ``item_type``/``item_id``/``features``/…;
    markets expose ``id``/``status``/``resolution_date``/…) so it is unit-testable
    without a DB. Poison isolation (gotcha #42): a proposal that fails to resolve
    is quarantined, never allowed to wipe the queue."""
    seen_targets: set[tuple] = set()
    actionable = []
    retired_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    oldest_gen = None
    newest_gen = None

    for p in candidates:
        target = (p.item_type, p.item_id)
        superseded = target in seen_targets  # newest-first order → later dupes are superseded
        seen_targets.add(target)

        try:
            market = markets.get(int(p.item_id)) if _is_market_id(p.item_type, p.item_id) else None
            state, reason = classify_pending(
                _build_lifecycle_row(p, market, now, superseded=superseded)
            )
        except Exception:
            state, reason = "quarantine", "authority_unavailable"

        if state == "retired":
            retired_reasons[reason] = retired_reasons.get(reason, 0) + 1
            continue
        if state == "quarantine":
            quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
            continue

        gen = _effective_generation(p)
        if gen is not None:
            oldest_gen = gen if oldest_gen is None else min(oldest_gen, gen)
            newest_gen = gen if newest_gen is None else max(newest_gen, gen)
        actionable.append((p, gen))

    return {
        "actionable": actionable,
        "retired_reasons": retired_reasons,
        "quarantine_reasons": quarantine_reasons,
        "oldest_gen": oldest_gen,
        "newest_gen": newest_gen,
    }


def _verdict_outcome(proposal, market, now, *, verdict, kill_switch, duplicate, posted_gen):
    """Pure verdict-time decision (classify_post over the resolved lifecycle)."""
    row = _build_lifecycle_row(proposal, market, now, superseded=False, posted_generation=posted_gen)
    row["verdict"] = verdict
    row["kill_switch_enabled"] = kill_switch
    row["duplicate_post"] = duplicate
    row["transaction_ok"] = True
    return classify_post(row)


async def _load_markets(db, targets):
    """Batch-load FuturesMarket rows for the futures/event proposals in targets."""
    ids = set()
    for item_type, item_id in targets:
        if _is_market_id(item_type, item_id):
            try:
                ids.add(int(item_id))
            except (ValueError, TypeError):
                pass
    if not ids:
        return {}
    res = await db.execute(select(FuturesMarket).where(FuturesMarket.id.in_(ids)))
    return {m.id: m for m in res.scalars().all()}


async def _stale_applied_review(db, now):
    """Item 1: identify existing applied verdicts whose market has since gone
    stale, for REVIEW ONLY. Never deletes or re-grades historical verdicts."""
    cutoff = ttl_cutoff(now)
    res = await db.execute(
        select(DiscoverReviewDecision)
        .where(
            DiscoverReviewDecision.decision.in_(list(APPLIED_DECISIONS)),
            DiscoverReviewDecision.created_at >= cutoff,
        )
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(1000)
    )
    rows = res.scalars().all()
    markets = await _load_markets(db, [(r.item_type, r.item_id) for r in rows])
    reasons: dict[str, int] = {}
    for r in rows:
        try:
            market = markets.get(int(r.item_id)) if _is_market_id(r.item_type, r.item_id) else None
            state, reason = classify_pending(
                _build_lifecycle_row(r, market, now, superseded=False)
            )
        except Exception:
            state, reason = "quarantine", "authority_unavailable"
        if state != "actionable":
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "count": sum(reasons.values()),
        "reasons": reasons,
        "note": "review only — historical verdicts are never auto-deleted or re-graded",
    }


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
    """Return pending LLM proposals, lifecycle-revalidated.

    Only current, actionable proposals enter ``items``. Retired and quarantined
    proposals are counted with reason codes (never shown as labelable), and any
    already-applied verdict that has since gone stale is surfaced for review."""
    _check_admin_secret(secret, request=request)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(DiscoverReviewDecision)
        .where(DiscoverReviewDecision.decision.in_(_PROPOSAL_DECISIONS))
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(500)
    )
    proposals = result.scalars().all()

    # Filter out already-verdicted targets (a matching accepted/rejected/skipped row).
    verdicted_ids = set()
    if proposals:
        verdict_result = await db.execute(
            select(
                DiscoverReviewDecision.item_type,
                DiscoverReviewDecision.item_id,
            ).where(DiscoverReviewDecision.decision.in_(_VERDICT_DECISIONS))
        )
        for row in verdict_result.all():
            verdicted_ids.add((row[0], row[1]))

    candidates = [
        p for p in proposals if (p.item_type, p.item_id) not in verdicted_ids
    ]

    markets = await _load_markets(db, [(p.item_type, p.item_id) for p in candidates])
    part = _partition_candidates(candidates, markets, now)

    items = []
    for p, gen in part["actionable"]:
        # Build the feature vector for the card.
        features = dict(p.features or {})
        if not any(k in features for k in ("probability", "movement_24h", "volume_24h")) and p.item_id:
            market = markets.get(int(p.item_id)) if _is_market_id(p.item_type, p.item_id) else None
            if market:
                features.setdefault("probability", None)
                features.setdefault("movement_24h", None)
                features.setdefault("volume_24h", market.volume_24h)
                features.setdefault("category", market.llm_sport_category)
                features.setdefault("market_tier", market.market_tier)
        # Carry the generation in `features` so the client echoes it back on POST,
        # enabling the transactional GET→POST race check without a client change.
        if gen is not None:
            features["generation"] = gen

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
            "generation": gen,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    stale_applied = await _stale_applied_review(db, now)

    return {
        "items": items,
        "total": len(items),
        "retired": {"count": sum(part["retired_reasons"].values()), "reasons": part["retired_reasons"]},
        "quarantined": {"count": sum(part["quarantine_reasons"].values()), "reasons": part["quarantine_reasons"]},
        "generation": {"oldest": part["oldest_gen"], "newest": part["newest_gen"]},
        "stale_applied_review": stale_applied,
    }


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
    """Record a human verdict on an LLM proposal, revalidated atomically.

    Inside the write transaction the proposal is locked/reloaded and its current
    lifecycle re-resolved. A proposal that went stale, was superseded, changed
    generation, or is a duplicate submission is refused with a typed conflict and
    NO ranking/training row is written — including a stale Skip (retirement is
    system work, not a human label)."""
    _check_admin_secret(secret, request=request)

    if body.verdict not in ("accept", "reject", "skip"):
        raise HTTPException(status_code=400, detail="verdict must be accept/reject/skip")

    now = datetime.now(timezone.utc)

    # Lock + reload the proposal inside the write transaction.
    try:
        original = await db.execute(
            select(DiscoverReviewDecision)
            .where(DiscoverReviewDecision.id == body.decision_id)
            .with_for_update()
        )
        proposal = original.scalar_one_or_none()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "reason": "transaction_failed", "applied": False, "writes": 0},
        )
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Re-resolve the current market lifecycle NOW (fresh, not from the GET snapshot).
    market = None
    if _is_market_id(proposal.item_type, proposal.item_id):
        mres = await db.execute(
            select(FuturesMarket).where(FuturesMarket.id == int(proposal.item_id))
        )
        market = mres.scalar_one_or_none()

    # Duplicate detection: a verdict already exists for this target.
    dup_res = await db.execute(
        select(DiscoverReviewDecision.id).where(
            DiscoverReviewDecision.item_type == proposal.item_type,
            DiscoverReviewDecision.item_id == proposal.item_id,
            DiscoverReviewDecision.decision.in_(_VERDICT_DECISIONS),
        ).limit(1)
    )
    duplicate = dup_res.first() is not None

    posted_gen = (body.features or {}).get("generation", "__omitted__")
    kill_switch = await _eval_promote_enabled()

    outcome = _verdict_outcome(
        proposal, market, now,
        verdict=body.verdict, kill_switch=kill_switch,
        duplicate=duplicate, posted_gen=posted_gen,
    )
    if outcome["status"] != "written":
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "status": outcome["status"],
                "reason": outcome["reason"],
                "applied": False,
                "writes": 0,
            },
        )

    # Actionable → apply the verdict. Determine the new decision label.
    action = proposal.decision.replace("llm_proposed_", "")
    if body.verdict == "skip":
        new_decision = "skipped"
    else:
        new_decision = f"{body.verdict}ed_{action}"

    # #222: an Accept applies a bounded, expiring, kill-switchable term to
    # Discover ranking. Stamp the applied term onto the verdict row's features so
    # it is a real audit trail (magnitude, when, whether the switch was live).
    applied = False
    features = dict(body.features or proposal.features or {})
    features.pop("generation", None)  # the round-trip token is not part of the audit trail
    if new_decision in APPLIED_DECISIONS:
        magnitude = EVAL_PROMOTE_ADJ if action == "promote" else -EVAL_DOWNRANK_EXACT
        applied = kill_switch
        features["eval_promote"] = {
            "magnitude": magnitude,
            "action": action,
            "applied": applied,
            "ttl_days": EVAL_PROMOTE_TTL_DAYS,
            "recorded_at": now.isoformat(),
            "from_proposal": proposal.id,
        }

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

    row = None
    if body.decision_id is not None:
        res = await db.execute(
            select(DiscoverReviewDecision).where(
                DiscoverReviewDecision.id == body.decision_id,
                DiscoverReviewDecision.decision.in_(_VERDICT_DECISIONS),
            )
        )
        row = res.scalar_one_or_none()
    elif body.item_type and body.item_id:
        res = await db.execute(
            select(DiscoverReviewDecision)
            .where(
                DiscoverReviewDecision.item_type == body.item_type,
                DiscoverReviewDecision.item_id == body.item_id,
                DiscoverReviewDecision.decision.in_(_VERDICT_DECISIONS),
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
