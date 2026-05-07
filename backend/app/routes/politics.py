"""Politics & elections markets API endpoint.

Serves prediction-market political data from Kalshi and Polymarket,
organized into sub-themes: presidential 2028, congressional 2026,
gubernatorial, policy/legislation, Supreme Court, international.

Single endpoint returns the full response consumed by the frontend.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Sub-theme classification
# ---------------------------------------------------------------------------

_THEME_BY_TICKER: list[tuple[str, str]] = [
    ("kxpres", "presidential"),
    ("kxelection", "presidential"),
    ("kxsenate", "congressional"),
    ("kxhouse", "congressional"),
    ("kxcongress", "congressional"),
    ("kxgov", "gubernatorial"),
    ("kxscotus", "scotus"),
    ("kxsupremecourt", "scotus"),
    ("kxtariff", "policy"),
    ("kximpeach", "policy"),
    ("kxbill", "policy"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:president|presidential|2028\s*election|white\s*house|nominee|primary)\b", re.I), "presidential"),
    (re.compile(r"\b(?:senate|senator|house\s*(?:of\s*rep|seat)|congress|midterm|2026\s*election)\b", re.I), "congressional"),
    (re.compile(r"\b(?:governor|gubernatorial)\b", re.I), "gubernatorial"),
    (re.compile(r"\b(?:supreme\s*court|scotus|justice|roe|overturn)\b", re.I), "scotus"),
    (re.compile(r"\b(?:bill|legislation|executive\s*order|policy|tariff|immigration|gun|abortion|cannabis|marijuana|legalize|ban|mandate|regulation)\b", re.I), "policy"),
    (re.compile(r"\b(?:uk\s*election|france|germany|canada|brazil|mexico|australia|india|japan|eu\s*election|european|nato|un\s*general|g7|g20|foreign\s*policy)\b", re.I), "international"),
    (re.compile(r"\b(?:trump|biden|desantis|harris|newsom|haley|ramaswamy|kennedy|rfk)\b", re.I), "presidential"),
    (re.compile(r"\b(?:approval\s*rating|favorab|popular\s*vote|electoral\s*college)\b", re.I), "presidential"),
    (re.compile(r"\b(?:cabinet|secretary\s*of|attorney\s*general|cia|fbi\s*director|ambassador)\b", re.I), "policy"),
]


def _classify_theme(market: FuturesMarket) -> str:
    ext = (market.external_id or "").lower()
    for prefix, theme in _THEME_BY_TICKER:
        if ext.startswith(prefix):
            return theme
    name = market.name or ""
    for pat, theme in _THEME_BY_NAME:
        if pat.search(name):
            return theme
    return "other"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source(market: FuturesMarket) -> str:
    return (market.source or "").lower()


_GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party)\s+[A-Z]{1,3}$", re.I
)


def _is_resolved(market: FuturesMarket) -> bool:
    """A market is effectively resolved if the top outcome is >= 99%."""
    for o in market.outcomes:
        prob = float(o.current_probability or 0)
        if prob >= 0.99:
            return True
    return False


def _clean_outcomes(outcomes: list) -> list:
    """Filter garbage placeholder outcomes."""
    return [o for o in outcomes if not _GARBAGE_OUTCOME_RE.match(o.name or "")]


def _market_row(market: FuturesMarket) -> dict | None:
    outcomes = _clean_outcomes(market.outcomes)
    outcomes = sorted(outcomes, key=lambda o: float(o.current_probability or 0), reverse=True)
    if not outcomes:
        return None
    top = outcomes[:3]
    return {
        "q": market.name,
        "prob": round(float(outcomes[0].current_probability or 0) * 100, 1),
        "src": _source(market),
        "market_id": market.id,
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
            }
            for o in top
        ],
        "outcome_count": len(outcomes),
    }


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_politics(db: AsyncSession = Depends(get_db)):
    """Return all politics market data organized by sub-theme."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(["politics", "geopolitics"]),
                *[FuturesMarket.external_id.ilike(f"{prefix}%")
                  for prefix, _ in _THEME_BY_TICKER],
            ),
            FuturesMarket.status == "open",
        )
    )
    all_markets = result.scalars().unique().all()

    themed: dict[str, list] = defaultdict(list)
    for m in all_markets:
        if _is_resolved(m):
            continue
        theme = _classify_theme(m)
        themed[theme].append(m)

    def build_section(markets: list, limit: int = 10) -> list[dict]:
        rows = []
        for m in markets:
            row = _market_row(m)
            if row and row["prob"] < 99:
                rows.append(row)
        rows.sort(key=lambda r: -abs(r["prob"] - 50))
        return rows[:limit]

    # Presidential — find the headline "who wins 2028" market
    pres_markets = themed.get("presidential", [])
    pres_headline = None
    pres_side = []
    for m in pres_markets:
        name_lower = (m.name or "").lower()
        outcomes = _clean_outcomes(m.outcomes)
        outcomes = sorted(outcomes, key=lambda o: float(o.current_probability or 0), reverse=True)
        if ("2028" in name_lower or "next president" in name_lower or "presidential election" in name_lower) and len(outcomes) >= 3:
            if pres_headline is None or len(outcomes) > (pres_headline.get("outcome_count") or 0):
                pres_headline = {
                    "q": m.name,
                    "market_id": m.id,
                    "src": _source(m),
                    "candidates": [
                        {
                            "name": o.name,
                            "prob": round(float(o.current_probability or 0) * 100, 1),
                        }
                        for o in outcomes[:8]
                    ],
                    "outcome_count": len(outcomes),
                }
        else:
            row = _market_row(m)
            if row and row["prob"] < 99:
                pres_side.append(row)
    pres_side.sort(key=lambda r: -abs(r["prob"] - 50))

    total = len(all_markets)

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "themes": {
            "presidential": {
                "count": len(pres_markets),
                "headline": pres_headline,
                "side_markets": pres_side[:8],
            },
            "congressional": {
                "count": len(themed.get("congressional", [])),
                "markets": build_section(themed.get("congressional", [])),
            },
            "gubernatorial": {
                "count": len(themed.get("gubernatorial", [])),
                "markets": build_section(themed.get("gubernatorial", [])),
            },
            "policy": {
                "count": len(themed.get("policy", [])),
                "markets": build_section(themed.get("policy", []), 12),
            },
            "scotus": {
                "count": len(themed.get("scotus", [])),
                "markets": build_section(themed.get("scotus", [])),
            },
            "international": {
                "count": len(themed.get("international", [])),
                "markets": build_section(themed.get("international", []), 12),
            },
            "other": {
                "count": len(themed.get("other", [])),
                "markets": build_section(themed.get("other", []), 6),
            },
        },
        "by_source": {
            "kalshi": sum(1 for m in all_markets if _source(m) == "kalshi"),
            "polymarket": sum(1 for m in all_markets if _source(m) == "polymarket"),
        },
    }
