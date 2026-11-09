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
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping
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
        raw_grade = str(r.grade or "")
        grade_out = (
            _DB_TO_GROUPING_GRADE.get(raw_grade, raw_grade)
            if r.surface == SURFACE_GROUPING
            else raw_grade
        )
        latest[(r.slate_id, r.grader, r.item_key)] = {
            "slate_id": r.slate_id,
            "surface": r.surface,
            "grader": r.grader,
            "expert": r.expert,
            "position": r.position,
            "item_key": r.item_key,
            "grade": grade_out,
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
    else:
        stmt = stmt.where(RankingGrade.surface != SURFACE_GROUPING)
    grades = latest_grades((await db.execute(stmt)).scalars().all())
    return {"grades": grades, "tally": family_tally(grades, now)}


# ---------------------------------------------------------------------------
# #12373 (Epic #12288, Plan #12221 row 6): private grading page for proposed
# grouping cards shown beside their best single member.
# ---------------------------------------------------------------------------

SURFACE_GROUPING = "grouping"
DEFAULT_GROUPING_SLATE_ID = "grouping-candidates-2026-11"
GROUPING_GRADES = ("amazing", "fine", "no")
# Lossless 1-to-1 bijection scoped to RankingGrade.surface == "grouping" so
# writes satisfy Postgres ck_ranking_grades_grade ("grade IN ('shareable',
# 'interesting', 'neither')") from ranking_slates_12095.py without adding a
# MIGRATION-CLASS schema migration (Epic #12288 guardrail: schema migrations
# wait for Alex's word).
_GROUPING_TO_DB_GRADE: dict[str, str] = {
    "amazing": "shareable",
    "fine": "interesting",
    "no": "neither",
}
_DB_TO_GROUPING_GRADE: dict[str, str] = {
    "shareable": "amazing",
    "interesting": "fine",
    "neither": "no",
    "amazing": "amazing",
    "fine": "fine",
    "no": "no",
}
_KID_PSEUDONYM_RE = re.compile(r"^kid[1-4]$", re.IGNORECASE)

_GROUPING_CANDIDATES_PATHS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[2] / "data" / "discover" / "grouping-candidates-2026-11.json",
    Path(__file__).resolve().parents[3] / "docs" / "discover" / "grouping-candidates-2026-11.json",
)


def normalize_grouping_grader(raw_grader: str, *, kid: bool = False) -> str:
    """Normalize a grader identifier; enforce pseudonyms (`kid1`..`kid4`) for kids (#12373)."""
    cleaned = " ".join(str(raw_grader or "").split())[:40]
    if not cleaned:
        return "kid1" if kid else ""
    if not kid:
        return cleaned
    if _KID_PSEUDONYM_RE.match(cleaned):
        return cleaned.lower()
    return ""


def select_best_single_member(family: Mapping[str, Any]) -> dict[str, Any]:
    """Select the strongest single member market from a proposed family (#12373, #10355).

    Prefers a priced binary member in ``[0.05, 0.95]`` closest to 50% (highest
    tension as a standalone single card), falling back to any priced member,
    then the first member in the family.
    """
    members = list(family.get("members") or [])
    quotes = family.get("quotes") if isinstance(family.get("quotes"), Mapping) else {}
    quote_by_id: dict[int, str] = {}
    if isinstance(quotes, Mapping):
        for id_key, q_key in (("market_a_id", "market_a_quote"), ("market_b_id", "market_b_quote")):
            mid = quotes.get(id_key)
            q = quotes.get(q_key)
            if isinstance(mid, int) and isinstance(q, str) and q.strip():
                quote_by_id[mid] = q.strip()

    if not members:
        return {
            "id": 0,
            "name": str(family.get("name") or ""),
            "subject": "",
            "source": str(family.get("source") or ""),
            "category": str(family.get("category") or "other"),
            "yes_probability": None,
            "rendered_percent": None,
            "resolution_date": None,
            "rule_quote": "",
        }

    def _member_rank(m: Mapping[str, Any]) -> tuple[int, float, float, int]:
        p = m.get("yes_probability")
        mid = int(m.get("id") or 0)
        if isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(float(p)):
            pf = float(p)
            if 0.05 <= pf <= 0.95:
                return (0, abs(pf - 0.50), -pf, mid)
            if 0.0 < pf < 1.0:
                return (1, abs(pf - 0.50), -pf, mid)
        return (2, 1.0, 0.0, mid)

    best = min(members, key=_member_rank)
    raw_p = best.get("yes_probability")
    prob = (
        float(raw_p)
        if isinstance(raw_p, (int, float)) and not isinstance(raw_p, bool) and math.isfinite(float(raw_p))
        else None
    )
    pct = int(math.floor(prob * 100.0 + 0.5)) if prob is not None else None
    mid = int(best.get("id") or 0)
    return {
        "id": mid,
        "name": str(best.get("name") or ""),
        "subject": str(best.get("subject") or ""),
        "source": str(family.get("source") or ""),
        "category": str(family.get("category") or "other"),
        "yes_probability": prob,
        "rendered_percent": pct,
        "resolution_date": best.get("resolution_date"),
        "rule_quote": quote_by_id.get(mid) or str(quotes.get("market_a_quote") or best.get("name") or ""),
    }


def _build_proposed_card_preview(family: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 390px proposed card preview shown on `/grade/groupings`."""
    words = family.get("card_words_390px")
    defn = family.get("proposed_definition") if isinstance(family.get("proposed_definition"), Mapping) else {}
    relations = list(defn.get("relations") or ["same_measure", "same_window", "sibling"])
    level = str(defn.get("level") or "member")

    if isinstance(words, Mapping) and words.get("rows"):
        return {
            "kicker": str(words.get("kicker") or defn.get("kicker") or "SIBLING FAMILY"),
            "tag": str(words.get("tag") or defn.get("tag") or "DISCOVER"),
            "title": str(words.get("title") or family.get("name") or ""),
            "rows": list(words.get("rows") or []),
            "count_line": str(words.get("count_line") or ""),
            "footer": str(words.get("footer") or defn.get("footer") or "Each row is its own market. They don't add up to 100%."),
            "relations": relations,
            "level": level,
        }

    # For a refused candidate family, construct the would-be rows from its member list so
    # the grader sees the proposed grouping card alongside its refusal reason and best single.
    members = list(family.get("members") or [])
    priced = [
        m for m in members
        if isinstance(m.get("yes_probability"), (int, float)) and not isinstance(m.get("yes_probability"), bool)
    ]
    ordered = sorted(
        priced,
        key=lambda m: (-float(m["yes_probability"]), str(m.get("subject") or ""), int(m.get("id") or 0)),
    )[:5]
    if not ordered:
        ordered = members[:5]

    rows = []
    for m in ordered:
        p = m.get("yes_probability")
        val = (
            f"{int(math.floor(float(p) * 100.0 + 0.5))}%"
            if isinstance(p, (int, float)) and not isinstance(p, bool)
            else "No number yet"
        )
        rows.append(
            {
                "label": str(m.get("subject") or m.get("name") or ""),
                "value": val,
                "market_id": int(m.get("id") or 0),
            }
        )
    cat = str(family.get("category") or "other").upper()
    return {
        "kicker": str(defn.get("kicker") or cat),
        "tag": str(defn.get("tag") or cat),
        "title": str(defn.get("name") or family.get("name") or ""),
        "rows": rows,
        "count_line": f"Showing {len(rows)} of {int(family.get('member_count') or len(members))} members",
        "footer": str(defn.get("footer") or "Each row is its own market. They don't add up to 100%."),
        "relations": relations,
        "level": level,
    }


def load_grouping_grade_deck(
    *,
    candidates_path: Path | None = None,
    slate_id: str = DEFAULT_GROUPING_SLATE_ID,
) -> dict[str, Any]:
    """Load the proposed grouping deck (20+ cards) for `/grade/groupings`."""
    target_path = candidates_path
    if target_path is None:
        for p in _GROUPING_CANDIDATES_PATHS:
            if p.exists():
                target_path = p
                break
    if target_path is None or not target_path.exists():
        raise HTTPException(status_code=404, detail="grouping candidates file not found")

    raw = json.loads(target_path.read_text(encoding="utf-8"))
    families = list(raw.get("families") or [])
    items: list[dict[str, Any]] = []
    for idx, fam in enumerate(families, start=1):
        if not isinstance(fam, Mapping):
            continue
        slug = str(fam.get("slug") or f"proposed-family-{idx}")
        items.append(
            {
                "position": idx,
                "item_key": slug,
                "title": str(fam.get("name") or slug),
                "source": str(fam.get("source") or ""),
                "category": str(fam.get("category") or "other"),
                "template_key": str(fam.get("template_key") or ""),
                "member_count": int(fam.get("member_count") or len(fam.get("members") or [])),
                "kind_verdict": str(fam.get("kind_verdict") or "refuse"),
                "refusal_reasons": list(fam.get("refusal_reasons") or []),
                "trust_pass": bool(fam.get("trust_pass")),
                "proposed_card": _build_proposed_card_preview(fam),
                "best_single": select_best_single_member(fam),
            }
        )

    return {
        "slate_id": slate_id,
        "surface": SURFACE_GROUPING,
        "generated_at": raw.get("generated_at"),
        "model": raw.get("model"),
        "question": "Is the grouping card worth more than its best single member?",
        "items": items,
    }


class GroupingGradeIn(BaseModel):
    slate_id: str = Field(DEFAULT_GROUPING_SLATE_ID, min_length=1, max_length=64)
    grader: str = Field(..., min_length=1, max_length=40)
    kid: bool = False
    position: int = Field(..., ge=1, le=100)
    item_key: str = Field(..., min_length=1, max_length=120)
    grade: str
    note: str | None = Field(None, max_length=300)


def summarize_grouping_grades(grades: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary counts for #12373 exit check (total grades, distinct graders, per-grade and per-grader counts)."""
    by_grade: dict[str, int] = {g: 0 for g in GROUPING_GRADES}
    by_grader: dict[str, dict[str, Any]] = {}
    cards_graded: set[str] = set()

    for g in grades:
        grade_val = str(g.get("grade") or "")
        if grade_val in by_grade:
            by_grade[grade_val] += 1
        grader_id = str(g.get("grader") or "")
        item_key = str(g.get("item_key") or "")
        if item_key:
            cards_graded.add(item_key)
        entry = by_grader.setdefault(
            grader_id,
            {
                "grader": grader_id,
                "kid": not bool(g.get("expert", True)),
                "count": 0,
                "amazing": 0,
                "fine": 0,
                "no": 0,
            },
        )
        entry["count"] += 1
        if grade_val in ("amazing", "fine", "no"):
            entry[grade_val] += 1

    graders_list = sorted(by_grader.values(), key=lambda e: (-int(e["count"]), str(e["grader"])))
    return {
        "total_grades": len(grades),
        "distinct_graders": len(graders_list),
        "distinct_cards_graded": len(cards_graded),
        "by_grade": by_grade,
        "by_grader": graders_list,
    }


@router.get("/grouping-deck")
async def get_grouping_deck(
    request: Request,
    slate_id: str = Query(DEFAULT_GROUPING_SLATE_ID, max_length=64),
    secret: str = Query(None),
) -> dict:
    _check_admin_secret(secret, request=request)
    return load_grouping_grade_deck(slate_id=slate_id)


@router.post("/grouping-grades")
async def post_grouping_grade(
    body: GroupingGradeIn,
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
) -> dict:
    _check_admin_secret(secret, request=request)
    if body.grade not in GROUPING_GRADES:
        raise HTTPException(status_code=422, detail=f"grade must be one of {GROUPING_GRADES}")
    stored_grader = normalize_grouping_grader(body.grader, kid=body.kid)
    if not stored_grader:
        raise HTTPException(status_code=422, detail="grader needs a name or kid pseudonym")

    deck = load_grouping_grade_deck(slate_id=body.slate_id)
    items = deck["items"]
    if body.position > len(items) or items[body.position - 1]["item_key"] != body.item_key:
        raise HTTPException(status_code=422, detail="that proposed card is not at that position in the deck")

    db.add(
        RankingGrade(
            slate_id=body.slate_id,
            surface=SURFACE_GROUPING,
            grader=stored_grader,
            expert=not body.kid,
            position=body.position,
            item_key=body.item_key,
            grade=_GROUPING_TO_DB_GRADE[body.grade],
            note=(body.note or "").strip() or None,
        )
    )
    await db.commit()
    return {"status": "ok", "grader": stored_grader}


@router.get("/grouping-grades")
async def get_grouping_grades(
    request: Request,
    slate_id: str = Query(DEFAULT_GROUPING_SLATE_ID, max_length=64),
    days: int = Query(30, ge=1, le=90),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    now = datetime.now(timezone.utc)
    stmt = select(RankingGrade).where(
        RankingGrade.surface == SURFACE_GROUPING,
        RankingGrade.slate_id == slate_id,
        RankingGrade.graded_at >= now - timedelta(days=days),
    )
    grades = latest_grades((await db.execute(stmt)).scalars().all())
    return {
        "slate_id": slate_id,
        "surface": SURFACE_GROUPING,
        "grades": grades,
        "tally": family_tally(grades, now),
        "summary": summarize_grouping_grades(grades),
    }


@router.get("/grouping-kind-proposals")
async def get_grouping_kind_proposals(
    request: Request,
    secret: str = Query(None),
) -> dict:
    """Return Alex-only proposed new grouping kinds with five example cards each (#9937)."""
    from app.utils.grouping_kind_proposer import load_committed_kind_proposals

    _check_admin_secret(secret, request=request)
    return load_committed_kind_proposals()


