"""Entertainment & culture markets API endpoint.

Serves prediction-market entertainment data from Kalshi and Polymarket,
organized into themed sections: trending hero, music (Spotify/Billboard/albums),
movies & TV (RT scores/box office/reality), cultural moments, tech & culture.

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
    ("kxrottentomatoes", "movies"),
    ("kxrt", "movies"),
    ("kxbeastgames", "tv_streaming"),
    ("kxbachelor", "tv_streaming"),
    ("kxpodcast", "social_media"),
    ("kxelon", "social_media"),
    ("kxmusk", "social_media"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:box\s*office|opening\s*weekend|domestic\s*gross|worldwide\s*gross|film|movie)\b", re.I), "movies"),
    (re.compile(r"\b(?:rotten\s*tomatoes|RT\s*score|critic\s*score|tomatometer)\b", re.I), "movies"),
    (re.compile(r"\b(?:netflix|hulu|disney\+|hbo|max|streaming|series|show|season\s*\d|episode|sitcom|reality\s*tv|survivor|bachelor|big\s*brother|beast\s*games)\b", re.I), "tv_streaming"),
    (re.compile(r"\b(?:spotify|billboard|hot\s*100|album|song|artist|concert|tour|grammy|music|rapper|singer|band)\b", re.I), "music"),
    (re.compile(r"\b(?:oscar|emmy|golden\s*globe|sag\s*award|tony|bafta|cannes|sundance|venice\s*film)\b", re.I), "awards"),
    (re.compile(r"\b(?:youtube|tiktok|instagram|twitter|x\.com|subscriber|follower|views|viral|mrbeast|influencer|streamer|twitch|podcast|elon|musk|tweet)\b", re.I), "social_media"),
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
# Kind classification — rendering hint for frontend card bodies
# ---------------------------------------------------------------------------

_KIND_BY_TICKER: list[tuple[str, str]] = [
    ("kxspotify", "spotify"),
    ("kxbillboard", "billboard"),
    ("kxboxoffice", "boxoffice"),
    ("kxrottentomatoes", "rt"),
    ("kxrt", "rt"),
    ("kxsurvivor", "reality"),
    ("kxbachelor", "reality"),
    ("kxbeastgames", "reality"),
    ("kxeurovision", "eurovision"),
]

_KIND_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:spotify|#1\s*song|chart\s*race)\b", re.I), "spotify"),
    (re.compile(r"\b(?:billboard|hot\s*100)\b", re.I), "billboard"),
    (re.compile(r"\b(?:box\s*office|opening\s*weekend|domestic\s*gross)\b", re.I), "boxoffice"),
    (re.compile(r"\b(?:rotten\s*tomatoes|RT\s*score|tomatometer|critic\s*score)\b", re.I), "rt"),
    (re.compile(r"\b(?:survivor|bachelor|bachelorette|beast\s*games|big\s*brother|reality)\b", re.I), "reality"),
    (re.compile(r"\b(?:eurovision)\b", re.I), "eurovision"),
]


def _classify_kind(market: FuturesMarket, outcome_count: int) -> str:
    ext = (market.external_id or "").lower()
    for prefix, kind in _KIND_BY_TICKER:
        if ext.startswith(prefix):
            return kind
    name = market.name or ""
    for pat, kind in _KIND_BY_NAME:
        if pat.search(name):
            return kind
    if outcome_count > 2:
        return "multi"
    return "binary"


# ---------------------------------------------------------------------------
# Helpers
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
    """Enriched market row with all available fields."""
    outcomes = _clean_outcomes(market.outcomes)
    outcomes = sorted(
        outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    if not outcomes:
        return None
    top = outcomes[:3]
    outcome_count = len(outcomes)
    return {
        "q": market.name,
        "prob": round(float(outcomes[0].current_probability or 0) * 100, 1),
        "src": _source(market),
        "market_id": market.id,
        "external_id": market.external_id,
        "kind": _classify_kind(market, outcome_count),
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
                "delta_24h": round(
                    float(o.probability_change_24h or 0) * 100, 1
                ),
            }
            for o in top
        ],
        "outcome_count": outcome_count,
        "volume_24h": market.volume_24h,
        "resolution_date": (
            market.resolution_date.isoformat()
            if market.resolution_date
            else None
        ),
        "image_url": market.image_url,
        "hook": market.hook_description,
    }


def _is_interesting(row: dict) -> bool:
    """Filter out boring markets (binary near 100%)."""
    if row["outcome_count"] <= 2 and row["prob"] > 95:
        return False
    return True


# ---------------------------------------------------------------------------
# Threshold grouping — RT scores, box office brackets
# ---------------------------------------------------------------------------

_THRESHOLD_RE = re.compile(
    r"^(.+?)\s*[-–—:]\s*"
    r"(?:(?:rotten\s*tomatoes|RT)\s*(?:score\s*)?)?"
    r"(?:above|over|under|below|≥|>=|>|<|≤|<=)?\s*"
    r"[\$]?\d+[%MmKk]?"
    r"(?:\s*[-–]\s*[\$]?\d+[%MmKk]?)?$",
    re.I,
)


def _normalize_group_key(name: str) -> str | None:
    """Extract the entity name from a threshold market question."""
    m = _THRESHOLD_RE.match(name or "")
    if m:
        return m.group(1).strip().lower()
    return None


def _group_threshold_markets(markets: list[dict]) -> list[dict]:
    """Group markets that share an entity but differ by threshold."""
    by_entity: dict[str, list[dict]] = defaultdict(list)
    ungrouped = []

    for row in markets:
        key = _normalize_group_key(row["q"])
        if key:
            by_entity[key].append(row)
        else:
            ungrouped.append(row)

    groups = []
    for entity_key, rows in by_entity.items():
        if len(rows) >= 2:
            title = rows[0]["q"].split("–")[0].split("—")[0].split(":")[0].strip()
            groups.append({
                "title": title,
                "image_url": next(
                    (r["image_url"] for r in rows if r.get("image_url")), None
                ),
                "thresholds": [
                    {
                        "label": r["q"],
                        "prob": r["prob"],
                        "market_id": r["market_id"],
                    }
                    for r in sorted(rows, key=lambda r: -r["prob"])
                ],
            })
        else:
            ungrouped.extend(rows)

    return groups, ungrouped


# ---------------------------------------------------------------------------
# Trending hero — pick the 5 most interesting markets
# ---------------------------------------------------------------------------

def _score_for_trending(row: dict) -> float:
    score = 0.0
    score += (50 - abs(row["prob"] - 50)) * 2
    if row.get("volume_24h"):
        score += min(row["volume_24h"] / 1000, 50)
    if row["outcome_count"] > 2:
        score += 15
    if row["kind"] not in ("binary", "multi"):
        score += 10
    if row.get("hook"):
        score += 5
    if row.get("image_url"):
        score += 3
    return score


def _build_trending(all_rows: list[dict], limit: int = 5) -> list[dict]:
    """Pick top N trending markets with kind diversity."""
    scored = sorted(all_rows, key=_score_for_trending, reverse=True)
    result = []
    kind_counts: dict[str, int] = defaultdict(int)

    for row in scored:
        if len(result) >= limit:
            break
        if kind_counts[row["kind"]] >= 2:
            continue
        result.append(row)
        kind_counts[row["kind"]] += 1

    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_list(markets: list, limit: int = 12) -> list[dict]:
    rows = []
    for m in markets:
        row = _market_row(m)
        if row and _is_interesting(row):
            rows.append(row)
    rows.sort(key=lambda r: -abs(r["prob"] - 50))
    return rows[:limit]


def _build_music(themed: dict) -> dict:
    music_markets = themed.get("music", [])
    all_rows = []
    spotify_race = []
    billboard_watch = []
    album_drops = []
    artist_streaming = []
    side_markets = []

    for m in music_markets:
        row = _market_row(m)
        if not row or not _is_interesting(row):
            continue
        all_rows.append(row)
        kind = row["kind"]
        if kind == "spotify":
            spotify_race.append(row)
        elif kind == "billboard":
            billboard_watch.append(row)
        else:
            name_lower = (row["q"] or "").lower()
            if any(
                w in name_lower
                for w in ["album", "first-week", "first week", "sales"]
            ):
                album_drops.append(row)
            elif any(
                w in name_lower
                for w in ["stream", "weekly", "monthly"]
            ):
                artist_streaming.append(row)
            else:
                side_markets.append(row)

    spotify_race.sort(key=lambda r: -r["prob"])
    billboard_watch.sort(key=lambda r: -r["prob"])

    return {
        "count": len(music_markets),
        "spotify_race": spotify_race[:8],
        "billboard_watch": billboard_watch[:12],
        "album_drops": album_drops[:6],
        "artist_streaming": artist_streaming[:8],
        "side_markets": side_markets[:10],
    }


def _build_movies_tv(themed: dict) -> dict:
    movies = themed.get("movies", [])
    tv = themed.get("tv_streaming", [])
    combined = movies + tv

    rt_markets = []
    box_office = []
    reality_tv = []
    side_markets = []

    for m in combined:
        row = _market_row(m)
        if not row or not _is_interesting(row):
            continue
        kind = row["kind"]
        if kind == "rt":
            rt_markets.append(row)
        elif kind == "boxoffice":
            box_office.append(row)
        elif kind == "reality":
            reality_tv.append(row)
        else:
            side_markets.append(row)

    rt_groups, rt_ungrouped = _group_threshold_markets(rt_markets)
    box_groups, box_ungrouped = _group_threshold_markets(box_office)

    side_markets.extend(rt_ungrouped)
    side_markets.extend(box_ungrouped)
    side_markets.sort(key=lambda r: -abs(r["prob"] - 50))

    return {
        "count": len(combined),
        "rt_groups": rt_groups,
        "rt_markets": rt_markets[:12],
        "box_office_groups": box_groups,
        "box_office": box_office[:12],
        "reality_tv": reality_tv[:9],
        "side_markets": side_markets[:10],
    }


def _build_cultural(themed: dict) -> list[dict]:
    """Awards + celebrity + viral + other → cultural moments feed."""
    cultural_markets = (
        themed.get("awards", [])
        + themed.get("celebrity", [])
        + themed.get("viral", [])
        + themed.get("other", [])
    )
    rows = []
    for m in cultural_markets:
        row = _market_row(m)
        if row and _is_interesting(row):
            rows.append(row)
    rows.sort(key=lambda r: -abs(r["prob"] - 50))
    return rows[:20]


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_entertainment(db: AsyncSession = Depends(get_db)):
    """Return all entertainment market data organized by themed sections."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(
                    ["entertainment", "culture", "social_media"]
                ),
                *[
                    FuturesMarket.external_id.ilike(f"{prefix}%")
                    for prefix, _ in _THEME_BY_TICKER
                ],
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

    # Build all enriched rows for trending scoring
    all_rows = []
    for m in all_markets:
        if _is_resolved(m):
            continue
        row = _market_row(m)
        if row and _is_interesting(row):
            all_rows.append(row)

    trending = _build_trending(all_rows)
    music = _build_music(themed)
    movies_tv = _build_movies_tv(themed)
    cultural_moments = _build_cultural(themed)
    tech_culture_markets = _build_list(
        themed.get("social_media", []), 15
    )

    total = sum(len(v) for v in themed.values())

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "trending": trending,
        "themes": {
            "music": music,
            "movies_tv": movies_tv,
            "tech_culture": {
                "count": len(themed.get("social_media", [])),
                "markets": tech_culture_markets,
            },
        },
        "cultural_moments": cultural_moments,
        "by_source": {
            "kalshi": sum(
                1
                for m in all_markets
                if _source(m) == "kalshi" and not _is_resolved(m)
            ),
            "polymarket": sum(
                1
                for m in all_markets
                if _source(m) == "polymarket" and not _is_resolved(m)
            ),
        },
    }
