"""Entertainment & culture markets API endpoint.

Serves prediction-market entertainment data from Kalshi and Polymarket,
organized into sub-themes: movies/box office, TV/streaming, music,
social media, awards, viral/novelty.

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

from app.models import FuturesMarket
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Sub-theme classification
# ---------------------------------------------------------------------------

_THEME_BY_TICKER: list[tuple[str, str]] = [
    ("kxnetflix", "tv_streaming"),
    ("kxdisney", "tv_streaming"),
    ("kxboxoffice", "movies"),
    ("kxoscars", "awards"),
    ("kxemmys", "awards"),
    ("kxgrammys", "awards"),
    ("kxgoldenglobe", "awards"),
    ("kxspotify", "music"),
    ("kxbillboard", "music"),
    ("kxsurvivor", "tv_streaming"),
    ("kxyoutube", "social_media"),
    ("kxtiktok", "social_media"),
    ("kxtwitter", "social_media"),
    ("kxeurovision", "music"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:box\s*office|opening\s*weekend|domestic\s*gross|worldwide\s*gross|film|movie)\b", re.I), "movies"),
    (re.compile(r"\b(?:netflix|hulu|disney\+|hbo|max|streaming|series|show|season\s*\d|episode|sitcom|reality\s*tv|survivor|bachelor|big\s*brother)\b", re.I), "tv_streaming"),
    (re.compile(r"\b(?:spotify|billboard|hot\s*100|album|song|artist|concert|tour|grammy|music|rapper|singer|band)\b", re.I), "music"),
    (re.compile(r"\b(?:oscar|emmy|golden\s*globe|sag\s*award|tony|bafta|cannes|sundance|venice\s*film)\b", re.I), "awards"),
    (re.compile(r"\b(?:youtube|tiktok|instagram|twitter|x\.com|subscriber|follower|views|viral|mrbeast|influencer|streamer|twitch|podcast)\b", re.I), "social_media"),
    (re.compile(r"\b(?:celebrity|kardashian|swift|beyonc|drake|kanye|bieber|selena|rihanna|dua\s*lipa|ariana|kendrick|post\s*malone)\b", re.I), "celebrity"),
    (re.compile(r"\b(?:eurovision|super\s*bowl\s*halftime|world\s*cup\s*ceremony|royal|pope|wedding|baby|engagement|divorce)\b", re.I), "viral"),
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
# Helpers (shared pattern with politics.py)
# ---------------------------------------------------------------------------

_GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party)\s+[A-Z]{1,3}$", re.I
)


def _source(market: FuturesMarket) -> str:
    return (market.source or "").lower()


def _is_resolved(market: FuturesMarket) -> bool:
    for o in market.outcomes:
        if float(o.current_probability or 0) >= 0.99:
            return True
    return False


def _clean_outcomes(outcomes: list) -> list:
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
            {"name": o.name, "prob": round(float(o.current_probability or 0) * 100, 1)}
            for o in top
        ],
        "outcome_count": len(outcomes),
    }


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

_THEME_LABELS = {
    "movies": "Movies & box office",
    "tv_streaming": "TV & streaming",
    "music": "Music",
    "awards": "Awards season",
    "social_media": "Social media & creators",
    "celebrity": "Celebrity",
    "viral": "Viral & novelty",
    "other": "Other entertainment",
}


@router.get("")
async def get_entertainment(db: AsyncSession = Depends(get_db)):
    """Return all entertainment market data organized by sub-theme."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(["entertainment", "culture", "social_media"]),
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

    sections = {}
    for theme_key in ["movies", "tv_streaming", "music", "awards", "social_media", "celebrity", "viral", "other"]:
        markets = themed.get(theme_key, [])
        if not markets:
            continue
        sections[theme_key] = {
            "label": _THEME_LABELS.get(theme_key, theme_key),
            "count": len(markets),
            "markets": build_section(markets, 12),
        }

    total = sum(len(v) for v in themed.values())

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "sections": sections,
        "by_source": {
            "kalshi": sum(1 for m in all_markets if _source(m) == "kalshi" and not _is_resolved(m)),
            "polymarket": sum(1 for m in all_markets if _source(m) == "polymarket" and not _is_resolved(m)),
        },
    }
