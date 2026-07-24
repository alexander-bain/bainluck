"""Admin endpoints for the team-cluster adjudication flow (L2-173).

Queue #247's systemic team-identity merge (``app/utils/team_merge.py``) is
deliberately precision-over-recall: it auto-folds only the clean bare-location
stubs and SKIPS every ambiguous cluster (espn_id collisions across NCAA schools,
real-team lookalikes, no-current-events ties). That leaves ~189 clusters that
need a human eye — and the merge report is where they go to rot.

This module turns those skipped clusters into an Alex-speed adjudication queue
(the same label-pass velocity pattern): one cluster at a time, three verdicts —
MERGE (fold the chosen stubs into the chosen canonical), KEEP SEPARATE (record so
the cluster never re-surfaces), DEFER (punt).

Zero collision with the merge rail itself:
- The LIST endpoint calls the PUBLIC ``run_team_identity_merge(session, apply=False)``
  and reads its ``skipped_detail`` — no re-implementation of cluster detection.
- MERGE reuses the vetted rail primitive ``team_merge._apply_merge`` per pair
  (FK re-point + alias fold + legacy-slug redirect + delete) — never raw merge SQL.
- Verdicts persist in the existing ``matching_overrides`` table (the Google-Photos
  face-matching adjudication store) under ``override_type='team_cluster'`` — NO
  migration, so this ships fully decoupled from Lane 1's serialized backend work.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import MatchingOverride
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils.team_merge import _apply_merge, _normalize, run_team_identity_merge

router = APIRouter()

# The matching_overrides discriminator for cluster verdicts (a new value on the
# free-text override_type column — no schema change).
OVERRIDE_TYPE = "team_cluster"

# verdict (client) -> decision (matching_overrides.decision). All three suppress
# the cluster from the pending queue; only "merge" mutates team data.
_VERDICT_DECISION = {
    "merge": "merged",
    "keep_separate": "rejected",
    "defer": "deferred",
}


def cluster_key(sport_key: str | None, member_ids: list[int]) -> str:
    """Stable key for a cluster across scans: sport + its sorted member ids.

    Member ids are stable rows, so the same ambiguous cluster keys identically on
    every scan (a KEEP-SEPARATE verdict therefore suppresses it permanently). Long
    clusters fall back to a hash so it always fits ``source_name`` (String(300))."""
    ids = "-".join(str(i) for i in sorted(member_ids))
    base = f"{sport_key or 'unknown'}:{ids}"
    if len(base) <= 290:
        return base
    digest = hashlib.sha1(ids.encode()).hexdigest()[:24]
    return f"{sport_key or 'unknown'}:h{digest}"


def _recommend(status: str, members: list[dict]) -> dict:
    """Advisory verdict when the evidence is lopsided (the human always decides).

    canonical = most current events, then total, then mappings, then longest name
    (mirrors ``team_merge._plan_cluster``'s r258 rule)."""
    canonical = max(
        members,
        key=lambda m: (
            m["recent_events"], m["total_events"], m["mappings"], len(m["name"] or "")
        ),
    )
    non_canon = [m for m in members if m["id"] != canonical["id"]]

    if status == "skip_incoherent":
        return {
            "action": "keep_separate", "canonical_id": canonical["id"], "fold_ids": [],
            "reason": "Names diverge (not a token-prefix) — likely distinct teams that "
                      "share an espn_id (e.g. Kent State vs Ohio State).",
        }
    if status == "skip_no_current":
        return {
            "action": "defer", "canonical_id": canonical["id"], "fold_ids": [],
            "reason": "No member carries any events — can't tell which row is canonical yet.",
        }
    # skip_no_stub: a non-canonical member looked like a real team to the auto-gate.
    thin = [m for m in non_canon if m["recent_events"] == 0 and m["mappings"] == 0]
    if non_canon and len(thin) == len(non_canon) and canonical["recent_events"] > 0:
        return {
            "action": "merge", "canonical_id": canonical["id"],
            "fold_ids": [m["id"] for m in thin],
            "reason": "One live team + thin dead duplicate(s) with no identity of their "
                      "own — safe to fold.",
        }
    return {
        "action": "keep_separate", "canonical_id": canonical["id"], "fold_ids": [],
        "reason": "A non-canonical member has its own events or identity mappings — "
                  "likely a genuinely distinct team.",
    }


async def _resolved_keys(db: AsyncSession) -> set[str]:
    """Cluster keys with a recorded verdict — suppressed from the pending queue."""
    rows = (
        await db.execute(
            select(MatchingOverride.source_name).where(
                MatchingOverride.override_type == OVERRIDE_TYPE
            )
        )
    ).all()
    return {r[0] for r in rows}


async def _pending_clusters(db: AsyncSession) -> list[dict]:
    """Skipped/ambiguous clusters that still need a human, newest scan each call."""
    report = await run_team_identity_merge(db, apply=False)
    resolved = await _resolved_keys(db)

    items: list[dict] = []
    for entry in report.get("skipped_detail", []):
        members = entry.get("members", [])
        member_ids = [m["id"] for m in members]
        key = cluster_key(entry.get("sport_key"), member_ids)
        if key in resolved:
            continue
        items.append({
            "cluster_key": key,
            "sport_key": entry.get("sport_key"),
            "espn_id": entry.get("espn_id"),
            "status": entry.get("status"),
            "reason": entry.get("reason"),
            "members": members,
            "member_ids": member_ids,
            "recommended": _recommend(entry.get("status", ""), members),
        })
    return items


@router.get("/team-clusters/pending")
async def team_clusters_pending(
    request: Request,
    secret: str = Query(None),
    summary: bool = Query(False, description="True returns only the awaiting count (cockpit tile)."),
    db: AsyncSession = Depends(get_db),
):
    """List team-identity clusters awaiting human adjudication.

    Each item carries the candidate members side by side (name/slug/espn_id/event
    counts/mappings), the auto-gate's skip ``reason``/``status``, and an advisory
    ``recommended`` verdict. ``?summary=true`` returns just ``{awaiting}`` for the
    cockpit tile."""
    _check_admin_secret(secret, request=request)

    items = await _pending_clusters(db)
    if summary:
        return {"awaiting": len(items)}
    return {"items": items, "total": len(items)}


class VerdictRequest(BaseModel):
    cluster_key: str
    verdict: str                       # merge | keep_separate | defer
    sport_key: str | None = None
    canonical_id: int | None = None    # required for merge
    fold_ids: list[int] = []           # required (non-empty) for merge
    member_ids: list[int] = []         # the full cluster, for audit context
    reason: str | None = None


async def _load_team_rows(db: AsyncSession, ids: list[int]) -> dict[int, SimpleNamespace]:
    rows = (await db.execute(
        text(
            "SELECT t.id, t.name, t.slug, t.alternate_names, t.sport_id, t.espn_id, "
            "s.key AS sport_key "
            "FROM teams t LEFT JOIN sports s ON s.id = t.sport_id "
            "WHERE t.id = ANY(:ids)"
        ),
        {"ids": ids},
    )).all()
    return {
        r.id: SimpleNamespace(
            id=r.id, name=r.name, slug=r.slug, alternate_names=r.alternate_names,
            sport_id=r.sport_id, espn_id=r.espn_id, sport_key=r.sport_key,
        )
        for r in rows
    }


@router.post("/team-clusters/verdict")
async def team_clusters_verdict(
    request: Request,
    body: VerdictRequest,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Record a human verdict on a cluster.

    - **merge**: fold each ``fold_ids`` team into ``canonical_id`` via the vetted
      ``team_merge._apply_merge`` rail (per-pair FK re-point + alias fold +
      legacy-slug redirect + delete), then persist ``decision='merged'``.
    - **keep_separate** / **defer**: persist the decision so the cluster drops out
      of the pending queue. Reversible via /undo.
    """
    _check_admin_secret(secret, request=request)

    if body.verdict not in _VERDICT_DECISION:
        raise HTTPException(
            status_code=400,
            detail=f"verdict must be one of {sorted(_VERDICT_DECISION)}",
        )

    decision = _VERDICT_DECISION[body.verdict]
    context: dict = {
        "verdict": body.verdict,
        "member_ids": body.member_ids,
        "canonical_id": body.canonical_id,
        "fold_ids": body.fold_ids,
        "reason": body.reason,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "surface": "team_clusters",
    }

    merge_evidence: list[dict] = []
    if body.verdict == "merge":
        if not body.canonical_id or not body.fold_ids:
            raise HTTPException(
                status_code=400,
                detail="merge requires canonical_id and a non-empty fold_ids",
            )
        if body.canonical_id in body.fold_ids:
            raise HTTPException(status_code=400, detail="canonical_id cannot be in fold_ids")

        rows = await _load_team_rows(db, [body.canonical_id, *body.fold_ids])
        canonical = rows.get(body.canonical_id)
        if canonical is None:
            raise HTTPException(status_code=404, detail=f"canonical team {body.canonical_id} not found")

        # Safety gate: only fold a team that is a genuine cluster edge of the
        # canonical (same sport AND shared espn_id OR identical normalized name).
        # This keeps the endpoint from becoming an arbitrary "merge any two teams"
        # tool and rejects stale requests whose rows changed under the scan.
        for fid in body.fold_ids:
            fold = rows.get(fid)
            if fold is None:
                raise HTTPException(status_code=404, detail=f"fold team {fid} not found")
            if fold.sport_id != canonical.sport_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"fold {fid} is a different sport than the canonical — refused",
                )
            same_espn = (
                fold.espn_id and canonical.espn_id
                and str(fold.espn_id) not in ("", "0")
                and str(fold.espn_id) == str(canonical.espn_id)
            )
            same_name = _normalize(fold.name) and _normalize(fold.name) == _normalize(canonical.name)
            if not (same_espn or same_name):
                raise HTTPException(
                    status_code=400,
                    detail=f"fold {fid} is not a cluster member of the canonical "
                           f"(no shared espn_id or name) — refused",
                )

        sport_key = canonical.sport_key
        try:
            for fid in body.fold_ids:
                merge_evidence.append(await _apply_merge(db, canonical, rows[fid], sport_key))
            # Scoped mapping dedup for this canonical (mirrors the rail).
            await db.execute(
                text(
                    "DELETE FROM team_identity_mapping a USING team_identity_mapping b "
                    "WHERE a.id > b.id AND a.team_id = b.team_id AND a.source = b.source "
                    "AND a.source_id IS NOT DISTINCT FROM b.source_id AND a.team_id = :tid"
                ),
                {"tid": canonical.id},
            )
            context["merged"] = merge_evidence
            await _upsert_override(db, body, decision, canonical.name, context)
            await db.commit()
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"merge failed, rolled back: {e}")
    else:
        await _upsert_override(db, body, decision, None, context)
        await db.commit()

    return {
        "status": "ok",
        "verdict": body.verdict,
        "decision": decision,
        "cluster_key": body.cluster_key,
        "merged": merge_evidence,
    }


async def _upsert_override(
    db: AsyncSession, body: VerdictRequest, decision: str,
    target_name: str | None, context: dict,
) -> None:
    """Insert or update the verdict row (unique on league_slug+type+source_name)."""
    league_slug = (body.sport_key or "unknown")[:50]
    existing = (
        await db.execute(
            select(MatchingOverride).where(
                MatchingOverride.league_slug == league_slug,
                MatchingOverride.override_type == OVERRIDE_TYPE,
                MatchingOverride.source_name == body.cluster_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.decision = decision
        existing.target_name = target_name
        existing.context = context
    else:
        db.add(MatchingOverride(
            league_slug=league_slug,
            override_type=OVERRIDE_TYPE,
            source_name=body.cluster_key,
            target_name=target_name,
            decision=decision,
            context=context,
        ))


class UndoRequest(BaseModel):
    cluster_key: str
    sport_key: str | None = None


@router.post("/team-clusters/undo")
async def team_clusters_undo(
    request: Request,
    body: UndoRequest,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Undo the last verdict on a cluster: delete its ``matching_overrides`` row so
    it returns to the pending queue.

    NOTE: a MERGE physically re-points FKs and deletes the stub rows — that data
    change is NOT reversed (the merged cluster can't re-form), we only clear the
    record. ``reversible`` reports whether the underlying action can be undone."""
    _check_admin_secret(secret, request=request)

    row = (
        await db.execute(
            select(MatchingOverride).where(
                MatchingOverride.override_type == OVERRIDE_TYPE,
                MatchingOverride.source_name == body.cluster_key,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No verdict to undo for this cluster")

    reverted = row.decision
    reversible = reverted != "merged"
    await db.delete(row)
    await db.commit()

    return {
        "status": "reverted",
        "cluster_key": body.cluster_key,
        "reverted_decision": reverted,
        "reversible": reversible,
    }
