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

#1873 / UX-P110 — the DRIFT layer, which is a different question from lifecycle.
A market can be open, un-superseded and future-dated, so every authoritative
lifecycle signal reads "actionable", while the CARD itself has re-priced since
Alex looked at it. The pre-existing GET→POST race check cannot see that: it
compares the proposal's generation, which is stamped once at birth and (by
#1542's own item-5 fix) never mutated again, so for the drift class it is
structurally unable to fire. Every served card therefore carries a
``card_fingerprint`` taken at the resolution the surface renders, and ``/verdict``
re-derives it inside the write transaction. See ``app.utils.graded_card``, which
is shared with the NATIVE judgment write path (#1933) — the gate is one decision,
not one per surface.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DiscoverReviewDecision, FuturesMarket, FuturesOutcome
from app.routes.admin_utils import _check_admin_destructive, _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils.card_integrity import card_defects, field_coherence
from app.utils.eval_promote import (
    APPLIED_DECISIONS,
    EVAL_DOWNRANK_EXACT,
    EVAL_PROMOTE_ADJ,
    EVAL_PROMOTE_ENABLED_KEY,
    EVAL_PROMOTE_TTL_DAYS,
    is_enabled_value,
    ttl_cutoff,
)
from app.utils.graded_card import (
    ABSENT_REFUSE,
    LABEL_PASS_SERVED_OUTCOMES,
    OMITTED,
    card_fingerprint,
    compare_snapshot,
    drift_outcome,
    rendered_card_percents,
)
from app.utils.kalshi_display_names import apply_name_repairs, repair_truncated_names
from app.utils.gold_label_store import (
    gold_label_row,
    label_origin,
    structured_label_metadata,
    verdict_gold_label,
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


#: A proposal older than this is retired unlabelled (#1873). Even when every
#: authoritative lifecycle signal still says "actionable", a months-old proposal
#: is a months-old READING of a market — the reason it was interesting has very
#: likely stopped being true, and Alex's label budget is the scarce resource
#: here. Twelve days covers a full weekly evaluation cycle with slack.
MAX_PROPOSAL_AGE_DAYS = 12


def _proposal_expired(proposal, now) -> bool:
    created = _utc(getattr(proposal, "created_at", None))
    if created is None:
        return False
    return (now - created).days > MAX_PROPOSAL_AGE_DAYS


def _card_suppression(market, outcomes) -> str | None:
    """Why this market cannot be rendered as an honest card, if it cannot.

    Deliberately SEPARATE from ``classify_pending``. That function answers "is
    this proposal still current", is byte-locked to
    ``scripts/evals/label_pass_lifecycle_contract``, and is about the market's
    LIFECYCLE. This answers "can the card be drawn truthfully", which is about
    the market's CONTENT — a live, current, perfectly un-stale market can still
    be unlabelable because its options are all named ``Person K`` (#1872) or
    because they cannot form a probability field (#1874).
    """
    if market is None or not outcomes:
        return None
    defects = card_defects(
        outcome_names=[o.name for o in outcomes],
        outcome_probabilities=[o.current_probability for o in outcomes],
    )
    return defects[0] if defects else None


def _partition_candidates(candidates, markets, now, outcomes_by_market=None):
    """Pure partition of pending proposals into actionable / retired / quarantined.

    Duck-typed (proposals expose ``item_type``/``item_id``/``features``/…;
    markets expose ``id``/``status``/``resolution_date``/…) so it is unit-testable
    without a DB. Poison isolation (gotcha #42): a proposal that fails to resolve
    is quarantined, never allowed to wipe the queue.

    ``outcomes_by_market`` (queue 355) adds the CARD-INTEGRITY gate on top of the
    lifecycle gate. Optional so existing callers keep working, but when omitted
    the anonymized/incoherent suppressions simply do not fire — the caller that
    serves Alex must pass it."""
    outcomes_by_market = outcomes_by_market or {}
    seen_targets: set[tuple] = set()
    actionable = []
    retired_reasons: dict[str, int] = {}
    quarantine_reasons: dict[str, int] = {}
    suppressed_reasons: dict[str, int] = {}
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

        # An age cap the lifecycle gate cannot express: every authoritative
        # signal can still read "current" on a proposal nobody should spend a
        # label on.
        if _proposal_expired(p, now):
            retired_reasons["proposal_expired"] = (
                retired_reasons.get("proposal_expired", 0) + 1
            )
            continue

        try:
            defect = _card_suppression(
                market, outcomes_by_market.get(getattr(market, "id", None)) or []
            )
        except Exception:
            defect = None  # poison isolation: never let one row empty the queue
        if defect:
            suppressed_reasons[defect] = suppressed_reasons.get(defect, 0) + 1
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
        "suppressed_reasons": suppressed_reasons,
        "oldest_gen": oldest_gen,
        "newest_gen": newest_gen,
    }


def _drift_outcome(posted_features: dict | None, live_card: dict) -> dict:
    """This surface's call into the SHARED drift gate (#1933).

    Separate from ``_verdict_outcome`` for the same reason ``_card_suppression``
    is separate from ``classify_pending`` — that one is byte-locked to the C143
    lifecycle oracle, and card CONTENT is not a lifecycle question.

    The DECISION now lives in ``app.utils.graded_card`` because native writes
    judgments too and had no gate at all; what stays here is only this surface's
    two policy choices, stated rather than implied:

    * the posted fingerprint travels inside ``features``, the dict this client
      already round-trips verbatim;
    * an absent fingerprint REFUSES, because a web page is re-served by this
      server on every load (see ``ABSENT_REFUSE`` for why native cannot copy
      that).

    An absent ``features`` dict is ``OMITTED``, not ``None``: a POST that carries
    no features at all is a pre-gate tab, and the gate's own docstring is about
    telling those two apart.
    """
    posted = (
        (posted_features or {}).get("card_fingerprint", OMITTED)
        if posted_features
        else OMITTED
    )
    return drift_outcome(
        posted,
        live_card.get("card_fingerprint"),
        live_card=live_card,
        on_absent=ABSENT_REFUSE,
    )


def _verdict_outcome(proposal, market, now, *, verdict, kill_switch, duplicate, posted_gen):
    """Pure verdict-time decision (classify_post over the resolved lifecycle)."""
    row = _build_lifecycle_row(proposal, market, now, superseded=False, posted_generation=posted_gen)
    row["verdict"] = verdict
    row["kill_switch_enabled"] = kill_switch
    row["duplicate_post"] = duplicate
    row["transaction_ok"] = True
    return classify_post(row)


async def _load_outcomes(db, market_ids):
    """Live outcomes for the candidate markets, ordered by probability desc.

    Queue 355 (#1873): the card is derived from THESE, not from the snapshot
    the proposal was written with. Ordering is stable so the leader is the same
    row on every read."""
    ids = {int(i) for i in market_ids if i is not None}
    if not ids:
        return {}
    res = await db.execute(
        select(FuturesOutcome)
        .where(FuturesOutcome.market_id.in_(ids))
        .order_by(
            FuturesOutcome.market_id,
            FuturesOutcome.current_probability.desc().nullslast(),
            FuturesOutcome.id,
        )
    )
    by_market: dict[int, list] = {}
    for outcome in res.scalars().all():
        by_market.setdefault(outcome.market_id, []).append(outcome)
    return by_market


def _live_title(proposal, market) -> str | None:
    """The card's headline, from the LIVE market where one exists (#1873).

    ``DiscoverReviewDecision.item_name`` is a write-time column, stamped from
    ``data.get("name")`` when the evaluator minted the proposal
    (``enrich_markets.py:1898``) and never revisited. Queue 355 moved the card's
    NUMBERS to live state and left its COPY on the snapshot, which is the half
    Alex actually reported — the exemplar in #1873 is 2024-era text, not a wrong
    percentage.

    Measured on production 2026-08-20 the current cohort drifts on 1 of 39 and
    only in casing (``Oscar winner:`` → ``Oscar Winner:``), because the 12-day age
    cap already retires the old copy before it can rot. So this closes the
    mechanism, not a live fire — and the snapshot title is kept beside it rather
    than overwritten, for the same reason ``snapshot_at_write`` is kept.
    """
    if market is not None and getattr(market, "name", None):
        return market.name
    return getattr(proposal, "item_name", None)


def _live_features(proposal, market, outcomes) -> dict:
    """The card Alex grades, derived from LIVE state (#1873/#1874).

    The write-time snapshot is not discarded — it is nested under
    ``snapshot_at_write`` so a reader can see what the evaluator originally
    thought, and ``snapshot_comparison`` says whether it still holds. That
    distinction is the whole finding: the pool was never stale, the SNAPSHOT
    was, and a fix that silently swapped one for the other would have hidden
    the evidence for its own necessity.

    The probability FIELD is withheld when it cannot be coherent, rather than
    printed as a row of 100%s (honest-empty, ruling 027).

    ** THIS IS ALSO THE VERDICT PATH'S DERIVATION. ** ``/verdict`` re-runs this
    exact function inside its write transaction and re-fingerprints the result,
    so the card the drift gate compares against is the card the queue serves, by
    construction rather than by two implementations agreeing (doctrine clause 5).
    """
    snapshot = dict(proposal.features or {})
    features: dict = {}

    if market is not None:
        features["category"] = market.llm_sport_category
        features["market_tier"] = market.market_tier
        features["volume_24h"] = market.volume_24h
        features["status"] = market.status
        features["resolution_date"] = (
            market.resolution_date.isoformat() if market.resolution_date else None
        )

    coherence = field_coherence([o.current_probability for o in outcomes])
    features["field_coherent"] = coherence["coherent"]
    features["field_sum"] = coherence["sum"]
    if coherence["coherent"]:
        leader = outcomes[0] if outcomes else None
        features["probability"] = (
            float(leader.current_probability)
            if leader is not None and leader.current_probability is not None
            else None
        )
        served = outcomes[:LABEL_PASS_SERVED_OUTCOMES]
        # #2060 items 1 + 3, applied here for the same reason the drift gate itself
        # was lifted into `graded_card` (#1933): a card fix that lands on one
        # surface is a card fix the other surface will not get. Both routes call
        # the same two functions.
        repairs = repair_truncated_names(
            getattr(market, "external_id", None), [o.name for o in served]
        )
        percents = rendered_card_percents(
            [
                float(o.current_probability)
                if o.current_probability is not None
                else None
                for o in served
            ]
        )
        features["outcomes"] = [
            {
                "name": repairs.get(o.name, o.name),
                "name_at_source": o.name,
                "probability": (
                    float(o.current_probability)
                    if o.current_probability is not None
                    else None
                ),
                "rendered_percent": percents[i],
            }
            for i, o in enumerate(served)
        ]
    else:
        repairs = {}
        # Say why, rather than showing a number that cannot be true.
        features["probability"] = None
        features["outcomes"] = None
        features["field_withheld_reason"] = coherence["reason"]

    features["title"] = apply_name_repairs(_live_title(proposal, market), repairs)
    features["title_at_source"] = _live_title(proposal, market)
    features["title_at_write"] = getattr(proposal, "item_name", None)
    # #2060 item 2 — a probability is ungradeable without a when. `resolution_date`
    # above is Kalshi's CLOSE time on a game market (gotcha #14), so it was never
    # the answer to "when is this".
    features["commence_time"] = (
        market.commence_time.isoformat()
        if market is not None and getattr(market, "commence_time", None)
        else None
    )
    features["snapshot_at_write"] = snapshot
    # Three-way, never a boolean — a snapshot that carried no reading is not a
    # snapshot that drifted, and the old boolean counted it as one. See
    # `compare_snapshot` for the production measurement that forced this.
    comparison = compare_snapshot(snapshot.get("probability"), features.get("probability"))
    features["snapshot_comparison"] = comparison
    features["snapshot_disagrees"] = comparison == "drifted"

    # The binding between this read and the verdict that follows it.
    features["card_fingerprint"] = card_fingerprint(
        title=features["title"],
        status=features.get("status"),
        resolution_date=features.get("resolution_date"),
        field_coherent=features.get("field_coherent"),
        outcomes=features.get("outcomes"),
        served_outcomes=LABEL_PASS_SERVED_OUTCOMES,
    )
    return features


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
    outcomes_by_market = await _load_outcomes(db, markets.keys())
    part = _partition_candidates(candidates, markets, now, outcomes_by_market)

    items = []
    snapshot_tally: dict[str, int] = {}
    for p, gen in part["actionable"]:
        # Queue 355 (#1873): derive the card from LIVE state. This used to
        # render `p.features` — the snapshot captured when the proposal was
        # written — so a card served today could be a months-old reading of a
        # market that has since resolved and repriced. That is what put 2024-era
        # copy and a row of 100%s in front of Alex.
        market = (
            markets.get(int(p.item_id))
            if _is_market_id(p.item_type, p.item_id)
            else None
        )
        outcomes = outcomes_by_market.get(getattr(market, "id", None)) or []
        features = _live_features(p, market, outcomes)
        comparison = features.get("snapshot_comparison")
        snapshot_tally[comparison] = snapshot_tally.get(comparison, 0) + 1
        # Carry the generation in `features` so the client echoes it back on POST,
        # enabling the transactional GET→POST race check without a client change.
        # `card_fingerprint` rides the same channel for the same reason — the
        # client already round-trips this dict verbatim, so the drift gate needs
        # no frontend change to arm.
        if gen is not None:
            features["generation"] = gen

        items.append({
            "id": p.id,
            "item_type": p.item_type,
            "item_id": p.item_id,
            # LIVE copy (#1873). `item_name_at_write` keeps the snapshot beside it
            # rather than silently replacing it.
            "item_name": features.get("title"),
            "item_name_at_write": p.item_name,
            "card_fingerprint": features.get("card_fingerprint"),
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
        # Queue 355: content defects, kept apart from lifecycle staleness. A
        # market here is CURRENT and still unlabelable — anonymized at source
        # (#1872) or unable to form a probability field (#1874).
        "suppressed": {
            "count": sum(part["suppressed_reasons"].values()),
            "reasons": part["suppressed_reasons"],
        },
        "card_source": "live",
        # Three-way, and the reason is a measurement: on 2026-08-20 the old
        # boolean reported 33 of 39 served cards as "snapshot no longer matches
        # live" when NOT ONE of those 39 snapshots carried a probability to
        # compare against. It was counting absence as drift, under a note that
        # claimed each one was a card the old behaviour had rendered wrong.
        # `drifted` is now the only value that means what that note said.
        "snapshot_comparison": {
            "drifted": snapshot_tally.get("drifted", 0),
            "agrees": snapshot_tally.get("agrees", 0),
            "no_reading": snapshot_tally.get("no_reading", 0),
            "no_live_reading": snapshot_tally.get("no_live_reading", 0),
            "unreadable": snapshot_tally.get("unreadable", 0),
        },
        "snapshot_disagreements": snapshot_tally.get("drifted", 0),
        "generation": {"oldest": part["oldest_gen"], "newest": part["newest_gen"]},
        "stale_applied_review": stale_applied,
        "note": (
            "Cards are derived from LIVE market state; the write-time snapshot "
            "is preserved per item under features.snapshot_at_write and the "
            "write-time title under item_name_at_write. Each served item carries "
            "a card_fingerprint taken at the resolution the surface renders "
            "(whole percent); /verdict re-derives it inside its write "
            "transaction and refuses a verdict whose card moved since the read. "
            "snapshot_comparison counts drifted / agrees / no_reading "
            "separately — a snapshot that carried no reading never drifted."
        ),
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

    Inside the write transaction the proposal is locked/reloaded, its current
    lifecycle re-resolved, and its CARD re-derived from live state. A proposal
    that went stale, was superseded, changed generation, or is a duplicate
    submission is refused with a typed conflict and NO ranking/training row is
    written — including a stale Skip (retirement is system work, not a human
    label). A proposal whose rendered card moved between the GET and this POST is
    refused the same way (``card_drifted``); the generation check cannot catch
    that, because generation is stamped once at birth and never mutated.

    The row this writes records the card the SERVER verified, never the one the
    request body carried."""
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

    # Re-derive the CARD from live state, inside this transaction, with the same
    # function the queue serves from. This is what the drift gate below compares
    # and what the verdict row records — never the request body.
    live_outcomes = (
        (await _load_outcomes(db, [market.id])).get(market.id, [])
        if market is not None
        else []
    )
    live_card = _live_features(proposal, market, live_outcomes)

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

    # ── THE DRIFT GATE (#1542 / #1873) ───────────────────────────────────────
    #
    # Layered ON TOP of `classify_post`, never folded into it. That function is
    # byte-locked to the C143 oracle and answers "is this proposal still
    # current" — a LIFECYCLE question. This answers "is this still the card he
    # graded" — a CONTENT question. The route already keeps that separation on
    # the GET side (`_card_suppression`), and it is the same separation here.
    #
    # Lifecycle runs FIRST on purpose: if the market resolved between GET and
    # POST, `lifecycle_terminal` is the true and more useful reason, and a drift
    # refusal would mask it behind a weaker one.
    #
    # ** FAIL CLOSED ON AN ABSENT FINGERPRINT, and that is a deliberate break
    # with the fail-open NULL policy #2024 shipped. ** The cases are not alike.
    # There the signal was missing from STORED ROWS, so failing closed would have
    # emptied the queue on deploy day for a reason no operator could fix. Here
    # the fingerprint is minted by the GET in the same request cycle: any client
    # that read the queue after this deploy has one, and the only way to arrive
    # without it is to post from a page loaded before it. That is precisely the
    # stale-tab hazard this gate exists for, and its remedy is a reload.
    #
    # The refusal detail carries the live card so the client can re-render
    # without a second round trip, and so a human can see WHAT moved.
    live_fingerprint = live_card.get("card_fingerprint")
    drift = _drift_outcome(body.features, live_card)
    if drift["status"] != "bound":
        await db.rollback()
        raise HTTPException(status_code=409, detail=drift)

    # Actionable → apply the verdict. Determine the new decision label.
    action = proposal.decision.replace("llm_proposed_", "")
    if body.verdict == "skip":
        new_decision = "skipped"
    else:
        new_decision = f"{body.verdict}ed_{action}"

    # #222: an Accept applies a bounded, expiring, kill-switchable term to
    # Discover ranking. Stamp the applied term onto the verdict row's features so
    # it is a real audit trail (magnitude, when, whether the switch was live).
    #
    # ** THE AUDIT TRAIL IS DERIVED, NOT ACCEPTED. ** This used to be
    # `dict(body.features or proposal.features or {})` — the row that steers
    # Discover for fourteen days recorded whatever the browser posted, with no
    # server check on any of it, and on an empty POST the `or proposal.features`
    # fallback recorded THE WRITE-TIME SNAPSHOT: the exact stale object #1873 is
    # about, written into the applied trail by the code meant to prevent it.
    # `live_card` is the card this transaction verified, so it is the only honest
    # thing to record. The round-trip tokens are dropped — they are transport,
    # not evidence.
    applied = False
    features = dict(live_card)
    features.pop("generation", None)
    features.pop("card_fingerprint", None)
    features["graded_card_fingerprint"] = live_fingerprint
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
        # The title Alex actually graded, not the one the evaluator stamped at
        # birth. This column is the corrective few-shot the judge is re-trained
        # on (`enrich_markets.py:1812`), so a stale headline here teaches the
        # model against a card that was never on screen.
        item_name=live_card.get("title") or proposal.item_name,
        category=proposal.category,
        surface="label_pass",
        archetype=proposal.archetype,
        decision=new_decision,
        admin_notes=f"Speed-pass verdict on proposal #{proposal.id}",
        features=features or None,
    )
    db.add(new_row)

    # ── AND THE SAME VERDICT LANDS IN THE ONE GOLD STORE (#1933 bullet 2) ────
    #
    # Until this line, a label recorded here was invisible to every consumer of
    # "Alex's labels": `/coverage`, `/eval-export`, the already-reviewed dedup,
    # the published `tapworthy_at_k`, the dataset exporter and the replay
    # harness all read `ranking_judgments`, and this route wrote only
    # `discover_review_decisions`. Measured 2026-08-20, that hid 198 of 286
    # gradeable futures verdicts — most of a corpus whose smallness is itself a
    # standing blocker (ruling 016).
    #
    # The lifecycle row above is NOT replaced by this one. It is what `/undo`,
    # the duplicate check, the eval-promote term in `feed.py` and the corrective
    # few-shot in `enrich_markets.py` read. Two rows, two jobs, joined by
    # `label_origin.source_decision_id` — which is also what makes the historical
    # convergence idempotent.
    #
    # Flushed before the judgment is built because the origin records the
    # decision id, and a row that cannot be traced back to its verdict cannot be
    # reconciled with one either. Same transaction throughout: a gold label
    # committed without its lifecycle row, or the reverse, is a split store with
    # extra steps.
    gold = verdict_gold_label(new_decision)
    if gold is not None and _is_market_id(proposal.item_type, proposal.item_id):
        await db.flush()
        gold_label, mapping = gold
        snapshot = {
            "item_type": proposal.item_type,
            "item_id": proposal.item_id,
            "market_id": int(proposal.item_id),
            "category": proposal.category,
            "archetype": proposal.archetype,
            # `/coverage` derives its stratum from this prefix, so the converged
            # rows report which proposal pool they came from instead of piling
            # into "unknown".
            "selection_reason": f"labeling:label_pass_{action}",
        }
        # This surface's card keys are `title`/`outcomes`/`probability`; the
        # envelope's are `name`/`top_outcomes`/`rendered_probability`. Mapped
        # here rather than pre-baked into the snapshot so the derived fields go
        # through the same "server_derived" stamp every other surface's do —
        # a snapshot that is server-derived but not MARKED as such is exactly
        # the ambiguity UX-P110 removed.
        derived_card = {
            "name": live_card.get("title"),
            "top_outcomes": live_card.get("outcomes"),
            "rendered_probability": live_card.get("probability"),
            "field_coherent": live_card.get("field_coherent"),
            "resolution_date": live_card.get("resolution_date"),
        }
        db.add(
            gold_label_row(
                label=gold_label,
                surface="label_pass",
                reviewer="alex",
                item_type="futures",
                market_id=int(proposal.item_id),
                market_name=live_card.get("title") or proposal.item_name,
                category_at_review=proposal.category,
                archetype_at_review=proposal.archetype,
                headline_at_review=live_card.get("title"),
                metadata=structured_label_metadata(
                    {"card_snapshot": snapshot},
                    None,
                    gate=drift,
                    live_card=derived_card,
                    gate_surface="label_pass_verdict",
                    # Passed for completeness of the shared envelope, not because
                    # this path can route today: the label-pass verdict elicits
                    # accept/reject on a proposal and collects no reason tags, so
                    # `defect_route` returns None here every time. Wiring it
                    # anyway is what stops the next person who adds tags to this
                    # surface from having to remember that the route exists.
                    label=gold_label,
                    reason_tags=None,
                ),
                origin=label_origin(
                    surface="label_pass",
                    source_store="discover_review_decisions",
                    source_decision_id=new_row.id,
                    source_decision=new_decision,
                    source_verdict=body.verdict,
                    mapping=mapping,
                ),
            )
        )

    await db.commit()

    return {
        "status": "ok",
        "decision": new_decision,
        "new_id": new_row.id,
        "applied": applied,
        # Reported, not merely stored — the same principle the native route
        # applies to its gate. A caller must be able to see that its label
        # reached the gold store without going to look in the database.
        "gold_label": gold[0] if gold else None,
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
    _check_admin_destructive(secret, request=request)

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
