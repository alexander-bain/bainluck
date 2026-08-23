"""Backfill defect routes onto the already-tagged negative judgments (#2094).

UX-P117 made a reasoned Bad land as routable defect evidence: ``defect_route()``
synthesises ``label_metadata.fixable_interest.fix_type`` inside
``structured_label_metadata``, the envelope BOTH write paths share. That is
**forward-only**. The judgments already in the store keep their reason tags and
still route nowhere.

── THE RAIL HAS NEVER HAD AN INPUT ──────────────────────────────────────────────

Measured on production 2026-08-21::

    ranking_judgments                                        88 rows
      carrying `label_metadata.fixable_interest`              0
      label IN (bad, kill) WITH >=1 reason_tag               71
      ...of those, routed to a cluster                        0

``_build_fixable_clusters`` skips any row without a ``fixable_interest`` key, so
both cluster endpoints have returned an empty list for the entire life of the
store. The most-used tag in the corpus is ``stale`` — 35 of 88 rows, 40% — which
is Alex saying thirty-five separate times that the queue serves dead markets
(gotcha #33). Every one was recorded as a label and dropped as a complaint.

── WHY AN ENDPOINT AND NOT A MIGRATION ──────────────────────────────────────────

Same reasoning as ``converge_label_stores``, and it is the reasoning of the whole
repairs rail: an Alembic data migration runs once, unattended, inside the release
phase, and reports what it did to a log nobody reads — gotcha #48's entire family
is repairs that silently no-op'd. This runs in the web dyno, is dry-run by
default, and RETURNS its own before/after census, so the proof that the rows moved
is the same artifact as the instruction that moved them.

── FOUR DECISIONS THAT ARE NOT OBVIOUS ──────────────────────────────────────────

1. **An existing ``fixable_interest`` is NEVER overwritten.** A ``fix_type`` a
   human chose in the ReviewTab select is a considered answer to "what kind of fix
   is this"; one inferred from a chip tap is not. UX-P117 already encodes that
   precedence in ``structured_label_metadata`` and the backfill honours the same
   direction. Rows are counted as ``already_routed``, never re-derived.

2. **The write is Core ``update()``, not ORM attribute assignment** (gotcha #4).
   ``label_metadata`` is JSONB, and assigning to a mutable JSONB attribute is the
   documented silent-failure mode in this codebase: the mutation is invisible to
   the session's change detection and the commit writes nothing. A backfill that
   reports 71 rows written and writes zero is exactly the shape of #683.

3. **No stored tag is rewritten.** Historical rows hold spellings that were
   unregistered when they were written (``boring``, and the ReviewTab's
   ``too_high``/``too_low``). ``reason_fix_type`` canonicalises on READ, so they
   route identically to a row written after the aliases landed. Folding on read is
   what makes the fix retroactive without touching the corpus.

4. **``create_issue_candidate`` is NOT set** — inherited from ``defect_route``,
   which deliberately does not set it. That flag means a human decided this
   deserves a GitHub issue; inferring it from a tap would put 71 auto-candidates
   into the triage list at once, which is the cried-wolf failure the Grid
   Sentinel's REAL/EXPLAINED/WATCH split exists to prevent.

── THE DRY RUN PROJECTS THE CLUSTER LIST, IT DOES NOT PROMISE ONE ───────────────

"Backfill 71 rows" and "the cluster list stops being empty" are different claims,
and only the first is under this module's control. ``_cluster_identity`` keys on
``(fix_type, item_key, …)`` where ``item_key`` falls back to
``item_type:market_id`` when the card snapshot carries no ``group_id`` /
``story_key`` / ``family_key`` — so N complaints about N different markets are N
clusters of one, not one cluster of N, however identical the reason.

The census therefore reports ``projected_clusters`` and ``largest_cluster``,
computed with the REAL ``_cluster_identity`` and ``_cluster_id`` imported from the
route rather than a second copy that agrees today. That is the difference between
knowing what the endpoint will return and hoping.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.models.models import RankingJudgment
from app.routes.admin_judgments import (
    _cluster_id,
    _cluster_identity,
    _fixable_interest,
    _has_fixable_interest,
    _metadata_dict,
)
from app.utils.label_reasons import NEGATIVE_LABELS, defect_route


class _IdentityShim:
    """The five attributes ``_cluster_identity`` reads, with PROPOSED metadata.

    A shim rather than a mutated ORM row: projecting the cluster list must not
    dirty a live instance in a session that is about to be rolled back, and it
    must not depend on flush ordering to stay a projection. Duck-typed on purpose
    — the point is to run the REAL identity function over the metadata this
    backfill is about to write, not to re-express what it computes.
    """

    __slots__ = ("id", "item_type", "market_id", "event_id", "label_metadata")

    def __init__(self, row: RankingJudgment, metadata: dict[str, Any]) -> None:
        self.id = row.id
        self.item_type = row.item_type
        self.market_id = row.market_id
        self.event_id = row.event_id
        self.label_metadata = metadata


def proposed_metadata(
    existing: dict[str, Any] | None, route: dict[str, Any]
) -> dict[str, Any]:
    """``label_metadata`` with the route added, as a NEW dict.

    Copied rather than mutated in place for the gotcha-#4 reason: the value handed
    to Core ``update()`` must be a fresh object, and a caller that mutated the
    ORM row's own dict would additionally leave a half-applied change behind on a
    dry run.

    ``reconstructed`` marks the row as rebuilt from stored tags rather than
    observed at label time — the ``label_origin.reconstructed`` precedent. A
    cluster reader has to be able to tell a reconstruction from an observation;
    they carry different confidence.
    """
    metadata = dict(existing or {})
    metadata["fixable_interest"] = {**route, "reconstructed": True}
    return metadata


async def repair(
    session, apply: bool = False, limit: int | None = None
) -> dict[str, Any]:
    """Route the already-tagged negative judgments into the defect clusters."""

    rows = (
        (
            await session.execute(
                select(RankingJudgment)
                .where(RankingJudgment.label.in_(sorted(NEGATIVE_LABELS)))
                .order_by(RankingJudgment.id)
            )
        )
        .scalars()
        .all()
    )

    # A negative verdict with no tags names no complaint — there is nothing to
    # route and its absence is not a shortfall. Counted separately from
    # "tagged but nothing routable" so the census can tell silence from a
    # vocabulary gap (gotcha #53: an empty answer is a shape, not a fact).
    untagged = [r for r in rows if not (r.reason_tags or [])]
    tagged = [r for r in rows if (r.reason_tags or [])]

    already_routed = [
        r for r in tagged if _has_fixable_interest(_fixable_interest(_metadata_dict(r)))
    ]
    already_ids = {r.id for r in already_routed}
    candidates = [r for r in tagged if r.id not in already_ids]

    planned: list[tuple[RankingJudgment, dict[str, Any], dict[str, Any]]] = []
    unroutable: list[RankingJudgment] = []
    for row in candidates:
        route = defect_route(label=row.label, reason_tags=row.reason_tags)
        if route is None:
            unroutable.append(row)
            continue
        planned.append((row, route, proposed_metadata(row.label_metadata, route)))

    if limit is not None:
        planned = planned[:limit]

    by_fix_type: dict[str, int] = {}
    for _, route, _meta in planned:
        key = str(route.get("fix_type"))
        by_fix_type[key] = by_fix_type.get(key, 0) + 1

    # What the cluster endpoint will actually return, via its own functions.
    cluster_sizes: dict[str, int] = {}
    for row, _route, metadata in planned:
        cid = _cluster_id(_cluster_identity(_IdentityShim(row, metadata)))
        cluster_sizes[cid] = cluster_sizes.get(cid, 0) + 1

    census: dict[str, Any] = {
        "negative_rows_total": len(rows),
        "untagged_no_complaint": len(untagged),
        "tagged_negatives": len(tagged),
        "already_routed_left_alone": len(already_routed),
        "unroutable_no_defect_tag": len(unroutable),
        "unroutable_ids": sorted(r.id for r in unroutable)[:50],
        "writable": len(planned),
        "by_fix_type": dict(sorted(by_fix_type.items(), key=lambda kv: -kv[1])),
        "projected_clusters": len(cluster_sizes),
        "largest_cluster": max(cluster_sizes.values(), default=0),
    }

    if not apply:
        census["applied"] = False
        census["plan"] = [
            {
                "judgment_id": row.id,
                "label": row.label,
                "reason_tags": list(row.reason_tags or []),
                "fix_type": route.get("fix_type"),
                "reason_tags_routed": route.get("reason_tags_routed"),
            }
            for row, route, _meta in planned[:25]
        ]
        return census

    written = 0
    for row, _route, metadata in planned:
        # Core update, NOT `row.label_metadata = metadata` — gotcha #4.
        await session.execute(
            update(RankingJudgment)
            .where(RankingJudgment.id == row.id)
            .values(label_metadata=metadata)
        )
        written += 1

    await session.commit()

    # AFTER-census read back from the database, not from the loop counter. The
    # counter proves the statements were issued; only a re-read proves they
    # landed (the mutation-must-prove-it-applied rule).
    verified = (
        (
            await session.execute(
                select(RankingJudgment).where(
                    RankingJudgment.id.in_([row.id for row, _r, _m in planned])
                )
            )
        )
        .scalars()
        .all()
    ) if planned else []

    census["applied"] = True
    census["written"] = written
    census["verified_carrying_fix_type"] = sum(
        1
        for r in verified
        if _fixable_interest(_metadata_dict(r)).get("fix_type")
    )
    return census
