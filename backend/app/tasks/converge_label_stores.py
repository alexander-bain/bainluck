"""Converge the historical label-pass verdicts into the one gold store (#1933).

The forward half of the convergence is in ``admin_label_pass.label_pass_verdict``:
from now on a verdict writes its gold label as it is given. This is the backward
half — the 198 gradeable futures verdicts already sitting in
``discover_review_decisions``, invisible to every consumer of "Alex's labels"
since June.

── WHY AN ENDPOINT AND NOT A MIGRATION ──────────────────────────────────────────

This queue has ``migration_slot: none``, and it would not want one anyway. An
Alembic data migration runs once, unattended, inside the release phase, and
reports what it did to a log nobody reads; gotcha #48's whole family is repairs
that silently no-op'd. The repairs rail runs inside the web dyno, is dry-run by
default, and RETURNS its own before/after census in the response body — so the
proof that 198 rows moved is the same artifact as the instruction that moved
them.

── THREE DECISIONS THAT ARE NOT OBVIOUS ─────────────────────────────────────────

1. **The converged rows keep their original ``created_at``.** Stamping 198 June
   and July verdicts with today's timestamp would not merely lose provenance: it
   would move every one of them inside every trailing-window measurement — the
   eval window, the coverage window, and specifically the 14-day window that
   decides whether the drift gate may be tightened to fail-closed. A backfill
   that makes the flip criterion pass by backdating nothing and forward-dating
   everything is a backfill that breaks the check it is being run alongside.

2. **They carry NO ``drift_gate`` key, so ``/coverage`` counts them
   ``unrecorded`` — not ``unbound``.** That is the existing three-key
   definition applied honestly: unbound is a claim about a client that could
   have declared the gate and did not, and about a June verdict nothing was ever
   asked. Filing them as unbound would put 198 permanently-unfixable rows in
   front of a criterion that requires unbound to reach zero.

3. **A verdict whose market row is gone is SKIPPED and COUNTED, never
   force-written.** ``ranking_judgments.market_id`` is a real FK; a deleted
   market would abort the whole transaction. The census reports the shortfall by
   name so "we converged 191 of 198" cannot read as "we converged them all"
   (ruling 086, and the detector-manifest carry from UX-P111 — a sweep records
   the population it examined).

Idempotent by construction: a row already converged is identifiable by
``label_metadata -> 'label_origin' ->> 'source_decision_id'``, which the forward
path stamps too, so re-invoking after the deploy cannot double-write the
verdicts recorded in between.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text

from app.models.models import DiscoverReviewDecision, FuturesMarket
from app.utils.gold_label_store import (
    VERDICT_GOLD_LABEL,
    gold_label_row,
    label_origin,
    normalize_card_snapshot,
)

#: The decisions this repair converges. Deliberately not "everything that is not
#: a proposal": ``skipped`` is the absence of an opinion, the ``email`` rows are
#: proposals about Polymarket's newsletter rather than feed cards, and the five
#: legacy ``needs_data_fix``/``ignored``/``accepted_promote`` rows from May
#: predate the verdict grammar entirely. Each is excluded by a reason that can be
#: stated, which is the test for whether an exclusion is a decision or a
#: convenience.
CONVERGEABLE_DECISIONS = tuple(VERDICT_GOLD_LABEL)

#: The verdict the human actually pressed, per stored decision. Spelled out
#: rather than derived by trimming the string: a two-character ``replace`` that
#: happens to turn "accepted" into "accept" is a coincidence about English, and
#: the next decision name added would find it out in production.
SOURCE_VERDICT = {
    "accepted_promote": "accept",
    "accepted_downrank": "accept",
    "rejected_promote": "reject",
    "rejected_downrank": "reject",
}


def _reconstructed_snapshot(row: DiscoverReviewDecision) -> dict[str, Any]:
    """The card, rebuilt from the decision row — never claimed as verified.

    A June verdict's live state is months gone, so there is nothing to re-derive
    against. What survives is what the decision row itself recorded, and it is
    marked ``reconstructed`` rather than ``server_derived`` so a reader can tell
    this apart from a card the server actually checked.
    """
    features = row.features if isinstance(row.features, dict) else {}
    snapshot: dict[str, Any] = {
        "item_type": row.item_type,
        "item_id": row.item_id,
        "market_id": int(row.item_id),
        "name": row.item_name,
        "category": row.category,
        "archetype": row.archetype,
        "family_key": row.family_key,
        "selection_reason": f"labeling:label_pass_{row.decision.split('_', 1)[1]}",
    }
    for key in ("probability", "rendered_probability"):
        value = features.get(key)
        if value is not None:
            snapshot["rendered_probability"] = value
            break
    normalized = normalize_card_snapshot(snapshot)
    normalized["card_fields_source"] = "reconstructed_from_decision_row"
    return normalized


async def repair(session, apply: bool = False, limit: int | None = None) -> dict[str, Any]:
    """Converge historical label-pass verdicts into ``ranking_judgments``."""

    # Which source decisions are already represented, from BOTH halves of the
    # convergence — the forward write path stamps the same key.
    converged_rows = (
        await session.execute(
            text(
                "SELECT DISTINCT (label_metadata -> 'label_origin' ->> "
                "'source_decision_id') AS sid FROM ranking_judgments "
                "WHERE label_metadata -> 'label_origin' ->> 'source_decision_id' "
                "IS NOT NULL"
            )
        )
    ).all()
    already = {int(r[0]) for r in converged_rows if r[0] and str(r[0]).isdigit()}

    candidates = (
        (
            await session.execute(
                select(DiscoverReviewDecision)
                .where(
                    DiscoverReviewDecision.decision.in_(CONVERGEABLE_DECISIONS),
                    DiscoverReviewDecision.item_type == "futures",
                )
                .order_by(DiscoverReviewDecision.created_at)
            )
        )
        .scalars()
        .all()
    )

    numeric = [c for c in candidates if str(c.item_id or "").isdigit()]
    non_numeric = len(candidates) - len(numeric)
    pending = [c for c in numeric if c.id not in already]

    # A market that no longer exists cannot take the FK. Resolved in ONE query
    # rather than per row: 198 round trips inside a request is how a repair
    # becomes a timeout.
    target_ids = {int(c.item_id) for c in pending}
    live_ids: set[int] = set()
    if target_ids:
        live_ids = {
            r[0]
            for r in (
                await session.execute(
                    select(FuturesMarket.id).where(FuturesMarket.id.in_(target_ids))
                )
            ).all()
        }
    writable = [c for c in pending if int(c.item_id) in live_ids]
    orphaned = [c for c in pending if int(c.item_id) not in live_ids]

    if limit is not None:
        writable = writable[:limit]

    by_label: dict[str, int] = {}
    by_mapping: dict[str, int] = {}
    for row in writable:
        label, mapping = VERDICT_GOLD_LABEL[row.decision]
        by_label[label] = by_label.get(label, 0) + 1
        by_mapping[mapping] = by_mapping.get(mapping, 0) + 1

    census = {
        "source_decisions_total": len(candidates),
        "non_numeric_item_id": non_numeric,
        "already_converged": len(numeric) - len(pending),
        "orphaned_market_gone": len(orphaned),
        "orphaned_decision_ids": sorted(c.id for c in orphaned)[:50],
        "writable": len(writable),
        "by_label": by_label,
        "by_mapping": by_mapping,
    }

    if not apply:
        census["applied"] = False
        census["plan"] = [
            {
                "decision_id": c.id,
                "market_id": int(c.item_id),
                "decision": c.decision,
                "label": VERDICT_GOLD_LABEL[c.decision][0],
                "mapping": VERDICT_GOLD_LABEL[c.decision][1],
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in writable[:25]
        ]
        return census

    written = 0
    for row in writable:
        label, mapping = VERDICT_GOLD_LABEL[row.decision]
        session.add(
            gold_label_row(
                label=label,
                surface="label_pass",
                # `discover_review_decisions` has no reviewer column, and every
                # row in it is the curator's — the same fact `reviewer_tier`
                # encodes for the rows that predate tiering. Recorded as an
                # assumption on the row rather than left implicit.
                reviewer="alex",
                item_type="futures",
                market_id=int(row.item_id),
                market_name=row.item_name,
                category_at_review=row.category,
                archetype_at_review=row.archetype,
                headline_at_review=row.item_name,
                # No `gate=` — see decision 2 in the module docstring. These rows
                # are `unrecorded`, which is the true statement about them.
                metadata={"card_snapshot": _reconstructed_snapshot(row)},
                origin=label_origin(
                    surface="label_pass",
                    source_store="discover_review_decisions",
                    source_decision_id=row.id,
                    source_decision=row.decision,
                    source_verdict=SOURCE_VERDICT[row.decision],
                    mapping=mapping,
                    reconstructed=True,
                ),
                created_at=row.created_at,
            )
        )
        written += 1

    await session.commit()

    after = (
        await session.execute(text("SELECT COUNT(*) FROM ranking_judgments"))
    ).scalar_one()

    census["applied"] = True
    census["written"] = written
    census["ranking_judgments_after"] = after
    return census
