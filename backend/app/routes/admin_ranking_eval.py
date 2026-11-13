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
  ten with each card's served payload, for the ``/grade`` page. With
  ``?slate=<YYYY-MM-DD (Pacific) | slate id | row id>`` (#11937): that saved
  slate's deck, its top 20 then 10 spread down the rest of its candidate list,
  the same cards each time, minus those the grader (``X-Grader-Name`` header,
  never the URL) already graded there. Either deck leaves out any card with no
  stored drawing and counts them in ``left_out_no_drawing``.
* ``POST /api/admin/ranking/grades`` — Phase 2: one grader's grade for one card
  of a slate's candidate list, at its list position (served cards keep their
  served position). Refused while ``RANKING_SNAPSHOTS`` is off.
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
import urllib.parse
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


_DATE_REF = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def slate_date_bounds(ref: str) -> tuple[datetime, datetime] | None:
    """#11937: a ``YYYY-MM-DD`` ref names that Pacific day, as UTC bounds; else None.

    The nightly slate is captured at 7:15 AM Pacific, so "the Nov 9 slate" is
    the one captured on Nov 9 Pacific time.
    """
    if not _DATE_REF.match(ref or ""):
        return None
    try:
        day = datetime.strptime(ref, "%Y-%m-%d").replace(tzinfo=TALLY_TZ)
    except ValueError:
        return None
    return day.astimezone(timezone.utc), (day + timedelta(days=1)).astimezone(timezone.utc)


async def _slate_row(db: AsyncSession, ref: str, surface: str):
    stmt = select(RankingSlateSnapshot).where(RankingSlateSnapshot.surface == surface)
    bounds = slate_date_bounds(ref)
    if bounds is not None:
        stmt = stmt.where(
            RankingSlateSnapshot.captured_at >= bounds[0],
            RankingSlateSnapshot.captured_at < bounds[1],
        )
    elif ref != "latest":
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


def has_drawing(card: Any) -> bool:
    """#11937: whether the slate stored a card ``/grade`` can draw. Slates
    captured before every card was kept hold the opening ten only; the rest
    fell back to a title and a bare percent, and a grade on that isn't a grade
    (Fable, Nov 10)."""
    return isinstance(card, Mapping) and bool(card.get("type"))


def drawn_only(items: list[dict]) -> tuple[list[dict], int]:
    """The deck's cards that can be drawn, and how many were left out."""
    kept = [i for i in items if has_drawing(i.get("card"))]
    return kept, len(items) - len(kept)


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


def candidate_order(slate: Mapping[str, Any]) -> list[dict]:
    """#11937: a slate's whole candidate list in one fixed order, with positions.

    Served cards first, in served order, so a served card's position is its
    served position (the opening ten graded before this change keep theirs);
    then every candidate that was not served, best score first, ties by key.
    """
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or () if c.get("item_key")}
    keys = [k for k in (slate.get("served_order") or []) if k]
    served = set(keys)
    rest = sorted(
        (c for k, c in by_key.items() if k not in served),
        key=lambda c: (-(c.get("score") if isinstance(c.get("score"), (int, float)) else float("-inf")),
                       str(c.get("item_key"))),
    )
    keys += [c["item_key"] for c in rest]
    out = []
    for position, key in enumerate(keys, start=1):
        cand = by_key.get(key) or {}
        out.append({
            "position": position,
            "item_key": key,
            "title": cand.get("title"),
            "probability": cand.get("probability"),
            "card": cand.get("card"),
        })
    return out


#: About the cards Alex can grade in one sitting on a phone (Fable, #11937).
SPREAD_DECK_SIZE = 30
#: The top of the slate is dealt whole: the scorer reads a top ten with more
#: than 3 ungraded cards as UNKNOWN, so the served order itself must be graded
#: before any change can be compared with it (Fable's review of #12564; the
#: Nov 8 sheet, positions 1-30 then a spread, is the shape that scored replays).
SPREAD_DECK_HEAD = 20


def spread_deck(
    order: list[dict], *, size: int = SPREAD_DECK_SIZE, head: int = SPREAD_DECK_HEAD, skip=()
) -> list[dict]:
    """#11937: the first ``head`` cards of ``order`` whole, then ``size - head``
    spread evenly over the rest down to the last card; the same cards every
    time for the same list. ``skip`` (item keys already graded) is removed
    afterwards, so the rest of the deck never moves."""
    n = len(order)
    head = min(head, size)
    if n <= size:
        picks = list(range(n))
    else:
        tail = size - head
        rest = n - head
        spread = (
            {head + round(i * (rest - 1) / (tail - 1)) for i in range(tail)} if tail > 1
            else ({n - 1} if tail == 1 else set())
        )
        picks = sorted(set(range(head)) | spread)
    skip = set(skip)
    return [order[i] for i in picks if order[i]["item_key"] not in skip]


#: Carries the grader's name (URL-encoded) on ``GET /grade-deck``.
GRADER_HEADER = "x-grader-name"


@router.get("/grade-deck")
async def get_grade_deck(
    request: Request,
    surface: str = Query(SURFACE_DISCOVER, max_length=32),
    slate: str | None = Query(None, max_length=64),
    size: int = Query(SPREAD_DECK_SIZE, ge=5, le=60),
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_admin_secret(secret, request=request)
    # Called directly (tests, other handlers), unset params arrive as Query objects.
    slate = slate if isinstance(slate, str) and slate.strip() else None
    size = size if isinstance(size, int) else SPREAD_DECK_SIZE
    # The grader's name comes in a header, never the URL: query strings land in
    # request logs, and the family's kids type their names on this page.
    grader = urllib.parse.unquote(request.headers.get(GRADER_HEADER) or "")[:40]
    row = slate_row_dict(await _slate_row(db, slate or "latest", surface))
    out = {
        "switch_on": ranking_snapshots_enabled(),
        "slate_id": row["slate_id"],
        "surface": row["surface"],
        "captured_at": row["captured_at"],
        "ranker_version": row["ranker_version"],
    }
    if not slate:
        items, left_out = drawn_only(opening_cards(row))
        return {**out, "mode": "opening", "items": items, "left_out_no_drawing": left_out}
    order = candidate_order(row)
    name = " ".join((grader or "").split())
    graded: set[str] = set()
    if name:
        rows = (await db.execute(
            select(RankingGrade).where(
                RankingGrade.slate_id == row["slate_id"],
                RankingGrade.surface == row["surface"],
                RankingGrade.grader == name,
            )
        )).scalars().all()
        graded = {r.item_key for r in rows}
    items, left_out = drawn_only(spread_deck(order, size=size, skip=graded))
    return {
        **out,
        "mode": "spread",
        "candidates": len(order),
        "already_graded": len(graded & {c["item_key"] for c in spread_deck(order, size=size)}),
        "left_out_no_drawing": left_out,
        "items": items,
    }


class GradeIn(BaseModel):
    slate_id: str = Field(..., min_length=1, max_length=64)
    surface: str = Field(SURFACE_DISCOVER, max_length=32)
    grader: str = Field(..., min_length=1, max_length=40)
    kid: bool = False
    # #11937: any card of the slate's candidate list (captures keep up to 500).
    position: int = Field(..., ge=1, le=500)
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
    order = candidate_order(slate)
    if body.position > len(order) or order[body.position - 1]["item_key"] != body.item_key:
        raise HTTPException(status_code=422, detail="that card is not at that position in the slate")
    if not has_drawing(order[body.position - 1]["card"]):
        raise HTTPException(status_code=422, detail="that card has no stored drawing, so it can't be graded")
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
EXAM_TEST_GROUPING_SLATE_ID = "sibling-family-exam-test-2026-11"
VISUAL_FORMS_LOOK_SHEET_SLATE_ID = "visual-forms-look-sheet-2026-11"
NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID = "nfl-playoffs-look-sheet-2026-11"
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
        p, _lbl = _extract_member_preview_price(m)
        mid = int(m.get("id") or 0)
        if p is not None:
            if 0.05 <= p <= 0.95:
                return (0, abs(p - 0.50), -p, mid)
            if 0.0 < p < 1.0:
                return (1, abs(p - 0.50), -p, mid)
        return (2, 1.0, 0.0, mid)

    best = min(members, key=_member_rank)
    prob, _best_lbl = _extract_member_preview_price(best)
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


def _extract_member_preview_price(m: Mapping[str, Any]) -> tuple[float | None, str | None]:
    """Return ``(probability, outcome_label)`` from ``yes_probability`` or multi-outcome ``outcomes`` (#12500)."""
    raw_p = m.get("yes_probability")
    raw_lbl = str(m.get("outcome_label") or "").strip() or None
    if isinstance(raw_p, (int, float)) and not isinstance(raw_p, bool) and math.isfinite(float(raw_p)):
        return float(raw_p), raw_lbl
    outs = m.get("outcomes") or m.get("top_outcomes") or ()
    best_p: float | None = None
    best_lbl: str | None = None
    for o in outs:
        if not isinstance(o, Mapping):
            continue
        oname = str(o.get("name") or o.get("label") or "").strip()
        if oname.lower() == "no":
            continue
        p = o.get("probability") if "probability" in o else o.get("current_probability")
        if isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(float(p)):
            fp = float(p)
            if best_p is None or fp > best_p:
                best_p = fp
                best_lbl = oname if oname.lower() != "yes" else None
    return best_p, best_lbl


def _clean_family_preview_title(family: Mapping[str, Any], raw_title: str) -> str:
    """Ensure a family preview title uses grammatical family-level wording (#12500)."""
    from app.utils.sibling_family_proposer import (
        _build_default_heading,
        _infer_subject_unit,
        verify_heading_from_market_words,
    )

    members = list(family.get("members") or [])
    t_key = str(family.get("template_key") or "")
    cat = str(family.get("category") or "other")
    subjects = [str(m.get("subject") or "") for m in members if m.get("subject")]
    defn = family.get("proposed_definition") if isinstance(family.get("proposed_definition"), Mapping) else {}
    rule = defn.get("rule") if isinstance(defn.get("rule"), Mapping) else {}
    unit = str(rule.get("subject_unit") or _infer_subject_unit(cat, t_key, subjects))

    if raw_title and verify_heading_from_market_words(raw_title, members, subject_unit=unit):
        return raw_title
    sample_titles = [str(m.get("name") or "") for m in members if m.get("name")]
    if t_key and sample_titles:
        rebuilt = _build_default_heading(t_key, sample_titles, subject_unit=unit)
        return rebuilt.replace(" {deadline}", "").replace("{deadline}", "").strip()
    return raw_title


def _build_proposed_card_preview(family: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 390px proposed card preview shown on `/grade/groupings`."""
    from app.utils.sibling_family import _clean_subject_display

    words = family.get("card_words_390px")
    defn = family.get("proposed_definition") if isinstance(family.get("proposed_definition"), Mapping) else {}
    relations = list(defn.get("relations") or ["same_measure", "same_window", "sibling"])
    level = str(defn.get("level") or "member")

    if isinstance(words, Mapping) and words.get("rows"):
        raw_title = str(words.get("title") or family.get("name") or "")
        cleaned_rows = []
        for idx_r, r in enumerate(words.get("rows") or [], start=1):
            if not isinstance(r, Mapping):
                continue
            r_copy = dict(r)
            r_copy["label"] = _clean_subject_display(str(r.get("label") or ""), strip_state_suffix=False)
            if not isinstance(r_copy.get("market_id"), int) or int(r_copy.get("market_id") or 0) <= 0:
                r_copy["market_id"] = idx_r
            val_str = str(r_copy.get("value") or "").strip()
            if r_copy.get("probability") is None and val_str.endswith("%"):
                try:
                    pct_int = int(val_str[:-1].lstrip("<>").strip())
                    r_copy["probability"] = round(pct_int / 100.0, 4)
                    r_copy["rendered_percent"] = pct_int
                except ValueError:
                    pass
            cleaned_rows.append(r_copy)
        return {
            "kicker": str(words.get("kicker") or defn.get("kicker") or "SIBLING FAMILY"),
            "tag": str(words.get("tag") or defn.get("tag") or "DISCOVER"),
            "title": _clean_family_preview_title(family, raw_title),
            "rows": cleaned_rows,
            "count_line": str(words.get("count_line") or ""),
            "footer": str(words.get("footer") or defn.get("footer") or "Each row is its own market. They don't add up to 100%."),
            "relations": relations,
            "level": level,
        }

    # For a refused candidate family, construct the would-be rows from its priced members so
    # the grader sees priced rows alongside its refusal reason and best single (#12500).
    members = list(family.get("members") or [])
    priced_pairs = [
        (m, p, o_lbl)
        for m in members
        for p, o_lbl in (_extract_member_preview_price(m),)
        if p is not None
    ]
    ordered = sorted(
        priced_pairs,
        key=lambda item: (-float(item[1]), str(item[0].get("subject") or ""), int(item[0].get("id") or 0)),
    )
    source_rows = ordered if ordered else [(m, None, None) for m in members[:5]]

    rows = []
    seen_labels: set[str] = set()
    for idx_m, (m, p, o_lbl) in enumerate(source_rows, start=1):
        raw_subj = _clean_subject_display(str(m.get("subject") or "").strip(), strip_state_suffix=False)
        raw_name = str(m.get("name") or "").strip()
        # If extracted subject is a bare number (e.g. "5" or "#1") that duplicates across members, disambiguate with market name.
        is_bare_number = raw_subj.lstrip("#").isdigit()
        label = raw_name if (not raw_subj or is_bare_number or raw_subj.lower() in seen_labels) else raw_subj
        if o_lbl and o_lbl.lower() not in label.lower():
            label = f"{label} ({o_lbl})"
        seen_labels.add(label.lower())
        is_valid_prob = isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(float(p))
        pct_val = int(math.floor(float(p) * 100.0 + 0.5)) if is_valid_prob else None
        val = f"{pct_val}%" if pct_val is not None else "Unpriced (refused)"
        mid = int(m.get("id") or 0) or idx_m
        rows.append(
            {
                "label": label,
                "value": val,
                "market_id": mid,
                "probability": round(float(p), 4) if is_valid_prob else None,
                "rendered_percent": pct_val,
            }
        )
        if len(rows) >= 5:
            break
    cat = str(family.get("category") or "other").upper()
    total_members = int(family.get("member_count") or len(members))
    unpriced_count = max(0, len(members) - len(priced_pairs))
    count_line = f"Showing {len(rows)} of {total_members} members"
    if unpriced_count > 0:
        count_line += f" · {unpriced_count} without a live Yes price withheld"
    raw_title = str(defn.get("name") or family.get("name") or "")
    return {
        "kicker": str(defn.get("kicker") or cat),
        "tag": str(defn.get("tag") or cat),
        "title": _clean_family_preview_title(family, raw_title),
        "rows": rows,
        "count_line": count_line,
        "footer": str(defn.get("footer") or "Each row is its own market. They don't add up to 100%."),
        "relations": relations,
        "level": level,
    }


def _card_entry_to_deck_item(
    card: Mapping[str, Any],
    *,
    pos: int,
    kind_slug: str,
    relations: list[str],
    level: str,
    default_as_of: str | None = None,
) -> dict[str, Any]:
    c_slug = str(card.get("slug") or f"{kind_slug}-{pos}")
    raw_rows = list(card.get("rows") or [])
    preview_rows = [
        {
            "label": str(r.get("label") or ""),
            "value": f"{int(r.get('rendered_percent', math.floor(float(r['probability']) * 100.0 + 0.5)))}%",
            "market_id": int(r.get("market_id") or 0),
            "probability": round(float(r["probability"]), 4),
            "rendered_percent": int(r.get("rendered_percent", math.floor(float(r["probability"]) * 100.0 + 0.5))),
            **(
                {"observed_at": str(r["observed_at"])}
                if r.get("observed_at")
                else {}
            ),
        }
        for r in raw_rows
    ]
    single = card.get("stronger_single_alternative") or {}
    s_prob = float(single["probability"])
    s_pct = int(math.floor(s_prob * 100.0 + 0.5))
    as_of_val = card.get("as_of") or default_as_of
    as_of_label = str(card.get("as_of_label") or "")
    sport_cat = str((card.get("selector") or {}).get("sport") or "sports")
    first_source = str((raw_rows[0] if raw_rows else {}).get("source") or "polymarket")
    unit = str(card.get("subject_unit") or "teams")
    total_members = int(card.get("member_count") or len(preview_rows))
    default_count_line = f"Showing {len(preview_rows)} of {total_members} {unit}"
    count_line_val = str(card.get("count_line") or default_count_line)
    subtitle_val = card.get("subtitle")
    selection_type_val = str(card.get("selection_type") or "top_5")
    graded_title_val = str(card.get("graded_title") or "").strip() or None
    tag_val = "BUBBLE · 50%" if selection_type_val == "bubble_50" else sport_cat.split("_")[-1].upper()
    return {
        "position": pos,
        "item_key": c_slug,
        "title": str(card.get("title") or c_slug),
        **(
            {"graded_title": graded_title_val}
            if graded_title_val is not None
            else {}
        ),
        "source": first_source,
        "category": sport_cat,
        "template_key": str((card.get("selector") or {}).get("title_ilike") or ""),
        "member_count": total_members,
        "kind_verdict": "refuse",
        "refusal_reasons": ["not_licensed"],
        "proposed_kind": kind_slug,
        "selection_type": selection_type_val,
        "as_of": as_of_val,
        "as_of_label": as_of_label,
        "proposed_card": {
            "kicker": str(card.get("kicker") or kind_slug.upper()),
            "tag": tag_val,
            "title": str(card.get("title") or c_slug),
            **(
                {"graded_title": graded_title_val}
                if graded_title_val is not None
                else {}
            ),
            "subtitle": str(subtitle_val) if subtitle_val else None,
            "rows": preview_rows,
            "count_line": count_line_val,
            "footer": str(card.get("footer") or ""),
            "relations": relations,
            "level": level,
            "as_of_label": as_of_label,
            "proposed_kind": kind_slug,
            "selection_type": selection_type_val,
        },
        "best_single": {
            "id": int(single.get("market_id") or 0),
            "name": str(single.get("title") or ""),
            "subject": str((raw_rows[0] if raw_rows else {}).get("label") or ""),
            "source": first_source,
            "category": sport_cat,
            "yes_probability": s_prob,
            "rendered_percent": s_pct,
            "resolution_date": None,
            "rule_quote": f"{single.get('title') or ''} ({as_of_label})" if as_of_label else str(single.get("title") or ""),
        },
    }


def _build_new_kind_deck_items(
    *,
    start_position: int = 1,
    proposals_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Build `/grade/groupings` deck items from committed new-kind proposals (#9937)."""
    from app.utils.grouping_kind_proposer import load_committed_kind_proposals

    loaded = load_committed_kind_proposals(path=proposals_path)
    if loaded.get("refused_count", 0) > 0 or loaded.get("accepted_count", 0) == 0:
        raise HTTPException(
            status_code=500,
            detail={
                "reason": "committed_kind_proposals_refused",
                "refused": loaded.get("refused", []),
            },
        )

    deck_items: list[dict[str, Any]] = []
    pos = start_position
    for prop in loaded.get("proposals") or []:
        kind_slug = str(prop.get("kind") or "")
        relations = list(prop.get("relations") or [])
        level = str(prop.get("level") or "member")
        for card in prop.get("example_cards") or []:
            deck_items.append(
                _card_entry_to_deck_item(
                    card,
                    pos=pos,
                    kind_slug=kind_slug,
                    relations=relations,
                    level=level,
                    default_as_of=loaded.get("generated_at"),
                )
            )
            pos += 1
    return deck_items


def _build_new_kinds_exam_deck_items(
    *,
    start_position: int = 1,
    exam_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Build `/grade/groupings` deck items for the 20-card held-out new-kinds exam (#9937)."""
    from app.utils.grouping_kind_proposer import load_new_kinds_exam_cards

    loaded = load_new_kinds_exam_cards(path=exam_path)
    if loaded.get("refused_count", 0) > 0 or loaded.get("accepted_count", 0) == 0:
        raise HTTPException(
            status_code=500,
            detail={
                "reason": "new_kinds_exam_refused",
                "refused": loaded.get("refused", []),
            },
        )

    relations_by_kind = {
        "season_stat_leaders": ["same_measure", "same_window", "sibling"],
        "qualification_stage_board": ["same_event", "same_measure", "path"],
    }
    deck_items: list[dict[str, Any]] = []
    pos = start_position
    for card in loaded.get("cards") or []:
        kind_slug = str(card.get("kind") or "season_stat_leaders")
        deck_items.append(
            _card_entry_to_deck_item(
                card,
                pos=pos,
                kind_slug=kind_slug,
                relations=relations_by_kind.get(kind_slug, ["same_measure", "sibling"]),
                level="member",
                default_as_of=loaded.get("generated_at"),
            )
        )
        pos += 1
    return deck_items


def _build_sibling_exam_test_deck_items(
    *,
    start_position: int = 1,
    dataset_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Build `/grade/groupings` deck items for the 20 fixed set-aside `test` cards (#12374 / #12500)."""
    from app.utils.roundup_containers import RoundupMembers
    from app.utils.sibling_family import select_sibling_family
    from app.utils.sibling_family_exam import (
        DEFAULT_EXAM_DATASET_PATH,
        EXAM_EVAL_NOW_UTC,
    )

    path = dataset_path or DEFAULT_EXAM_DATASET_PATH
    if not path.exists():
        raise HTTPException(status_code=404, detail="sibling-family exam dataset not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    as_of_val = str(raw.get("as_of") or "2026-11-08")
    as_of_label = f"as of {as_of_val[:10]}" if as_of_val else ""

    items: list[dict[str, Any]] = []
    pos = start_position
    for card in raw.get("cards") or []:
        if card.get("split") != "test":
            continue
        rule = card.get("rule") or {}
        candidates = list(card.get("candidate_markets") or [])
        res = select_sibling_family(
            candidates,
            template=str(rule.get("template") or ""),
            title_template=str(rule.get("title_template") or card.get("proposed_title") or ""),
            kicker_prefix=str(rule.get("kicker_prefix") or "SIBLING FAMILY"),
            kicker_include_date=bool(rule.get("kicker_include_date", True)),
            subject_unit=str(rule.get("subject_unit") or "members"),
            outcome_name=str(rule.get("outcome_name") or "Yes"),
            lead_rule=str(rule.get("lead_rule") or "nearest_open_deadline"),
            min_numbered_members=int(rule.get("min_numbered_members", 3)),
            card_rows=int(rule.get("card_rows", 5)),
            footer=str(
                card.get("footer")
                or "Each row is its own market. They don't add up to 100%."
            ),
            now=EXAM_EVAL_NOW_UTC,
        )
        if not isinstance(res, RoundupMembers):
            continue
        preview_rows = [
            {
                "label": str(r.get("label") or ""),
                "value": f"{int(r.get('rendered_percent', round(float(r['probability']) * 100)))}%",
                "market_id": int(r.get("market_id") or 0),
                "probability": round(float(r["probability"]), 4),
                "rendered_percent": int(r.get("rendered_percent", round(float(r["probability"]) * 100))),
            }
            for r in res.rows
        ]
        row_label_by_id = {
            int(r.get("market_id") or 0): str(r.get("label") or "") for r in res.rows
        }
        single_members = []
        for m in candidates:
            mid = int(m.get("id") or 0)
            p_val, _ = _extract_member_preview_price(m)
            single_members.append(
                {
                    "id": mid,
                    "name": str(m.get("name") or ""),
                    "subject": row_label_by_id.get(mid) or str(m.get("name") or ""),
                    "source": str(m.get("source") or card.get("source") or "polymarket"),
                    "category": str(m.get("category") or card.get("category") or "other"),
                    "yes_probability": p_val,
                    "resolution_date": m.get("resolution_date"),
                    "rule_quote": str(m.get("rule_quote") or m.get("description") or ""),
                }
            )
        family_for_single = {
            "name": str(res.title or card.get("proposed_title") or ""),
            "source": str(card.get("source") or "polymarket"),
            "category": str(card.get("category") or "other"),
            "members": single_members,
            "quotes": {},
        }
        cat_upper = str(card.get("category") or "other").upper()
        slug = str(card.get("family_slug") or card.get("card_id"))
        items.append(
            {
                "position": pos,
                "item_key": slug,
                "title": str(res.title or card.get("proposed_title") or slug),
                "source": str(card.get("source") or "polymarket"),
                "category": str(card.get("category") or "other"),
                "template_key": f"{card.get('source')}:{rule.get('template')}",
                "member_count": len(res.members),
                "kind_verdict": "serve",
                "refusal_reasons": [],
                "trust_pass": True,
                "proposed_kind": "sibling_family",
                "as_of": as_of_val,
                "as_of_label": as_of_label,
                "proposed_card": {
                    "kicker": str(res.kicker or rule.get("kicker_prefix") or cat_upper),
                    "tag": cat_upper,
                    "title": str(res.title or card.get("proposed_title") or slug),
                    "rows": preview_rows,
                    "count_line": str(
                        res.count_line
                        or f"Showing {len(preview_rows)} of {len(res.members)} members"
                    ),
                    "footer": str(
                        res.footer
                        or card.get("footer")
                        or "Each row is its own market. They don't add up to 100%."
                    ),
                    "relations": ["sibling_of"],
                    "level": "member",
                    "as_of_label": as_of_label,
                },
                "best_single": select_best_single_member(family_for_single),
            }
        )
        pos += 1
    return items


def load_grouping_grade_deck(
    *,
    candidates_path: Path | None = None,
    slate_id: str = DEFAULT_GROUPING_SLATE_ID,
) -> dict[str, Any]:
    """Load the proposed grouping deck (sibling-family + new-kind proposals) for `/grade/groupings`."""
    from app.utils.grouping_kind_proposer import (
        DEFAULT_KIND_PROPOSER_MODEL,
        NEW_KINDS_EXAM_SLATE_ID,
    )

    if slate_id == "new-kind-proposals-2026-11":
        nk_items = _build_new_kind_deck_items(start_position=1)
        return {
            "slate_id": slate_id,
            "surface": SURFACE_GROUPING,
            "generated_at": nk_items[0].get("as_of") if nk_items else None,
            "model": DEFAULT_KIND_PROPOSER_MODEL,
            "question": "Is the grouping card worth more than its best single member?",
            "items": nk_items,
        }
    if slate_id == NEW_KINDS_EXAM_SLATE_ID:
        exam_items = _build_new_kinds_exam_deck_items(start_position=1)
        return {
            "slate_id": slate_id,
            "surface": SURFACE_GROUPING,
            "generated_at": exam_items[0].get("as_of") if exam_items else None,
            "model": DEFAULT_KIND_PROPOSER_MODEL,
            "question": "Is the grouping card worth more than its best single member?",
            "items": exam_items,
        }
    if slate_id == EXAM_TEST_GROUPING_SLATE_ID:
        from app.utils.sibling_family_exam import DEFAULT_PROPOSER_MODEL

        test_items = _build_sibling_exam_test_deck_items(start_position=1)
        return {
            "slate_id": slate_id,
            "surface": SURFACE_GROUPING,
            "generated_at": test_items[0].get("as_of") if test_items else None,
            "model": DEFAULT_PROPOSER_MODEL,
            "question": "Is the grouping card worth more than its best single member?",
            "items": test_items,
        }
    if slate_id == VISUAL_FORMS_LOOK_SHEET_SLATE_ID:
        look_sheet_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "groupings"
            / "visual-forms-look-sheet.json"
        )
        if not look_sheet_path.exists():
            raise HTTPException(
                status_code=404, detail="visual forms look sheet file not found"
            )
        raw_sheet = json.loads(look_sheet_path.read_text(encoding="utf-8"))
        active_items = [
            item
            for item in raw_sheet.get("items", [])
            if not item.get("retired")
        ]
        return {
            **raw_sheet,
            "items": active_items,
        }
    if slate_id == NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID:
        nfl_sheet_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "groupings"
            / "nfl-playoffs-look-sheet.json"
        )
        if not nfl_sheet_path.exists():
            raise HTTPException(
                status_code=404, detail="nfl playoffs look sheet file not found"
            )
        raw_nfl_sheet = json.loads(nfl_sheet_path.read_text(encoding="utf-8"))
        active_nfl_items = [
            item
            for item in raw_nfl_sheet.get("items", [])
            if not item.get("retired")
        ]
        return {
            **raw_nfl_sheet,
            "items": active_nfl_items,
        }

    target_path = candidates_path
    if target_path is None:
        for p in _GROUPING_CANDIDATES_PATHS:
            if p.exists():
                target_path = p
                break
    if target_path is None or not target_path.exists():
        raise HTTPException(status_code=404, detail="grouping candidates file not found")

    raw = json.loads(target_path.read_text(encoding="utf-8"))
    generated_at = str(raw.get("generated_at") or "")
    families = list(raw.get("families") or [])
    items: list[dict[str, Any]] = []
    for idx, fam in enumerate(families, start=1):
        if not isinstance(fam, Mapping):
            continue
        slug = str(fam.get("slug") or f"proposed-family-{idx}")
        as_of_val = str(fam.get("as_of") or generated_at or "")
        as_of_label = f"as of {as_of_val[:10]}" if as_of_val else ""
        preview = _build_proposed_card_preview(fam)
        preview["as_of_label"] = as_of_label
        items.append(
            {
                "position": idx,
                "item_key": slug,
                "title": str(preview.get("title") or fam.get("name") or slug),
                "source": str(fam.get("source") or ""),
                "category": str(fam.get("category") or "other"),
                "template_key": str(fam.get("template_key") or ""),
                "member_count": int(fam.get("member_count") or len(fam.get("members") or [])),
                "kind_verdict": str(fam.get("kind_verdict") or "refuse"),
                "refusal_reasons": list(fam.get("refusal_reasons") or []),
                "trust_pass": bool(fam.get("trust_pass")),
                "proposed_kind": "sibling_family",
                "as_of": as_of_val or None,
                "as_of_label": as_of_label or None,
                "proposed_card": preview,
                "best_single": select_best_single_member(fam),
            }
        )

    if candidates_path is None:
        items.extend(_build_new_kind_deck_items(start_position=len(items) + 1))

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
    try:
        data = load_committed_kind_proposals()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="new-kind proposals file not found"
        ) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail="invalid new-kind proposals payload"
        ) from exc

    if data.get("refused_count", 0) > 0 or data.get("accepted_count", 0) == 0:
        raise HTTPException(
            status_code=500,
            detail={
                "reason": "committed_kind_proposals_refused",
                "refused": data.get("refused", []),
            },
        )
    return data


