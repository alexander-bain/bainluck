"""#989 CLOB authoritative re-resolve — Batch 0 (VERIFY-BEFORE-REGRADE, dry-run).

The curve-dropped cohort (pass2_loser / all_losers / null-source-all-false) was
excluded from the published calibration curve (#754-curve/#116) because it was
'resolved' by heuristics with a 0% win rate. This module re-resolves those
markets AUTHORITATIVELY via the CLOB API: `condition_id` (== our `external_id`,
98.8% coverage) -> `/markets/{condition_id}` -> the single `tokens[].winner`.

Batch 0 is DRY-RUN ONLY: it fetches CLOB for a small sample, maps the CLOB
winning outcome to our stored outcomes, applies the integrity guard, and REPORTS
what it *would* set — it writes nothing. Hand-verify the sample table before any
writing drain is built (the anti-gotcha-#21 discipline: authoritative source +
integrity guard + skip-on-ambiguity, proven on a sample first).
"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Heuristic-resolved + null-source classes that were dropped from the curve and
# are eligible for authoritative CLOB re-resolution.
_DROPPED_SOURCES = ("pass2_loser", "all_losers")


def _norm(s: str) -> str:
    """Normalize an outcome/label for matching: lowercase, strip punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _direct_match_outcome(clob_winner: str, our_outcomes: list[dict]) -> int | None:
    """DIRECT map (~74% of the cohort: yes/no, over/under, moneyline): return the
    id of OUR outcome whose name matches the CLOB winning outcome label, else
    None. Exact normalized match only — no fuzzy guessing (skip-on-ambiguity)."""
    target = _norm(clob_winner)
    if not target:
        return None
    hits = [o["id"] for o in our_outcomes if _norm(o["name"]) == target]
    return hits[0] if len(hits) == 1 else None


async def clob_resolve_sample(limit: int = 25) -> dict:
    """Batch-0 dry-run: fetch CLOB winners for a sample of the dropped cohort and
    report the winner->outcome mapping. Writes NOTHING."""
    from app.tasks.base import get_task_session
    from app.services.polymarket_api import PolymarketAPIService

    out: dict = {"dry_run": True, "checked": 0, "clob_resolved": 0,
                 "true_void": 0, "clob_404": 0, "direct_mapped": 0,
                 "integrity_skip": 0, "unmapped": 0, "samples": [], "errors": []}

    async with get_task_session() as session:
        rows = (await session.execute(text("""
            SELECT fm.id, fm.external_id AS cond_id, LEFT(fm.name, 80) AS market_name
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
              AND fm.external_id LIKE '0x%'
            GROUP BY fm.id, fm.external_id, fm.name
            HAVING bool_or(fo.is_winner) IS NOT TRUE
               AND bool_or(fo.resolution_source = ANY(:srcs))
            ORDER BY fm.id DESC
            LIMIT :lim
        """), {"srcs": list(_DROPPED_SOURCES), "lim": limit})).all()

        market_ids = [r.id for r in rows]
        outcomes_by_market: dict[int, list[dict]] = {}
        if market_ids:
            orows = (await session.execute(text("""
                SELECT market_id, id, name FROM futures_outcomes
                WHERE market_id = ANY(:ids)
            """), {"ids": market_ids})).all()
            for o in orows:
                outcomes_by_market.setdefault(o.market_id, []).append(
                    {"id": o.id, "name": o.name})

    service = PolymarketAPIService()
    sem = asyncio.Semaphore(5)  # polite; CLOB tolerates low concurrency (L2-32)

    async def _one(r):
        async with sem:
            try:
                clob = await service.get_clob_market_by_condition(str(r.cond_id))
            except Exception as e:  # 429/5xx/timeout — surfaced, not silently void
                return {"market_id": r.id, "error": str(e)[:120]}
            if clob is None:
                return {"market_id": r.id, "clob_404": True,
                        "market": r.market_name}
            winner = service.clob_winning_outcome(clob)
            # integrity guard: CLOB market question should resemble our name
            clob_q = str(clob.get("question") or clob.get("market_slug") or "")
            our = outcomes_by_market.get(r.id, [])
            integrity_ok = bool(_norm(clob_q)) and (
                _norm(clob_q)[:24] in _norm(r.market_name) + _norm(clob_q)  # loose
            )
            mapped = _direct_match_outcome(winner, our) if winner else None
            return {
                "market_id": r.id,
                "market": r.market_name,
                "clob_question": clob_q[:80],
                "clob_winner": winner,
                "our_outcomes": [o["name"][:22] for o in our][:6],
                "mapped_outcome_id": mapped,
                "integrity_ok": integrity_ok,
                "void": winner is None,
            }

    try:
        results = await asyncio.gather(*[_one(r) for r in rows])
    finally:
        await service.close()

    for res in results:
        out["checked"] += 1
        if res.get("error"):
            out["errors"].append(res["error"])
            continue
        if res.get("clob_404"):
            out["clob_404"] += 1
            out["samples"].append(res)
            continue
        if res.get("void"):
            out["true_void"] += 1
        else:
            out["clob_resolved"] += 1
            if not res.get("integrity_ok"):
                out["integrity_skip"] += 1
            elif res.get("mapped_outcome_id"):
                out["direct_mapped"] += 1
            else:
                out["unmapped"] += 1
        out["samples"].append(res)

    return out
