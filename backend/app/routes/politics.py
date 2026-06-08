"""Politics & elections markets API endpoint.

Serves prediction-market political data from Kalshi and Polymarket,
organized into sub-themes: presidential 2028, congressional 2026,
gubernatorial, policy/legislation, Supreme Court, international.

Single endpoint returns the full response consumed by the frontend.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services import get_db
from app.utils.cross_source_matching import (
    clean_outcomes as _clean_outcomes,
    find_cross_source_markets,
    group_markets_by_group_id,
    is_resolved as _is_resolved,
    source as _source,
)

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
    # International FIRST — prevents foreign presidential elections from matching "presidential"
    (re.compile(
        r"\b(?:uk\s*election|france|french|germany|german|canada|canadian|brazil|brazilian|"
        r"mexico|mexican|australia|australian|india|indian|japan|japanese|"
        r"colombia|colombian|chile|chilean|argentina|argentin|nigeria|nigerian|"
        r"south\s*africa|turkey|turkish|poland|polish|ukraine|ukrainian|"
        r"israel|israeli|iran|iranian|taiwan|taiwanese|philippines|filipino|"
        r"indonesia|indonesian|egypt|egyptian|south\s*korea|korean|"
        r"italy|italian|spain|spanish|netherlands|dutch|"
        r"eu\s*election|european|nato|un\s*general|g7|g20|foreign\s*policy)\b", re.I,
    ), "international"),
    (re.compile(r"\b(?:trump|biden|desantis|harris|newsom|haley|ramaswamy|kennedy|rfk)\b", re.I), "presidential"),
    (re.compile(r"\b(?:president|presidential|2028\s*election|white\s*house|nominee|primary)\b", re.I), "presidential"),
    (re.compile(r"\b(?:senate|senator|house\s*(?:of\s*rep|seat)|congress|midterm|2026\s*election)\b", re.I), "congressional"),
    (re.compile(r"\b(?:governor|gubernatorial)\b", re.I), "gubernatorial"),
    (re.compile(r"\b(?:supreme\s*court|scotus|justice|roe|overturn)\b", re.I), "scotus"),
    (re.compile(r"\b(?:bill|legislation|executive\s*order|policy|tariff|immigration|gun|abortion|cannabis|marijuana|legalize|ban|mandate|regulation)\b", re.I), "policy"),
    (re.compile(r"\b(?:approval\s*rating|favorab|popular\s*vote|electoral\s*college)\b", re.I), "presidential"),
    (re.compile(r"\b(?:cabinet|secretary\s*of|attorney\s*general|cia|fbi\s*director|ambassador)\b", re.I), "policy"),
]


_NON_POLITICS_RE = re.compile(
    r"\b(?:billboard|spotify|grammy|oscar|emmy|rotten\s*tomatoes|box\s*office"
    r"|vix|s&p|nasdaq|oil|crude|fed\s*rate|cpi|gdp|unemployment|inflation"
    r"|temperature|weather|hurricane|rainfall"
    r"|nba|nfl|mlb|nhl|pga|ufc|mma|tennis|soccer|cricket)\b",
    re.I,
)


def _is_non_politics(market: FuturesMarket) -> bool:
    return bool(_NON_POLITICS_RE.search(market.name or ""))


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
# Party detection for presidential candidates
# ---------------------------------------------------------------------------

_R_NAMES = {
    "trump", "vance", "desantis", "haley", "ramaswamy", "pence", "scott",
    "youngkin", "christie", "burgum", "rubio", "cotton", "cruz", "noem",
    "lake", "stefanik", "hawley", "paul", "pompeo", "hutchinson", "elder",
    "hurd", "mccarthy", "mcconnell", "ernst", "thune", "sununu", "kemp",
    "abbott", "vivek",
}
_D_NAMES = {
    "biden", "harris", "newsom", "whitmer", "pritzker", "buttigieg",
    "shapiro", "warnock", "booker", "klobuchar", "warren", "sanders",
    "ocasio-cortez", "beshear", "moore", "kelly", "ossoff", "fetterman",
    "schiff", "pelosi", "schumer", "cortez masto", "duckworth", "aoc",
    "pete", "kamala", "gavin", "gretchen", "josh shapiro", "wes moore",
}


def _detect_party(name: str) -> str:
    name_lower = name.lower().strip()
    if "republican" in name_lower or "(r)" in name_lower:
        return "R"
    if "democrat" in name_lower or "(d)" in name_lower:
        return "D"
    for r in _R_NAMES:
        if r in name_lower:
            return "R"
    for d in _D_NAMES:
        if d in name_lower:
            return "D"
    return "I"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_outcome_probs(outcomes: list[dict], key: str = "prob") -> None:
    """Normalize probabilities in-place when independent binary markets sum > 105%.

    Kalshi/Polymarket create separate "Will X win?" binary markets for each
    candidate.  Raw probabilities can sum well over 100%.  When displayed as a
    ranked list, divide each by the sum so they total ~100%.

    See also: feed.py BR27 fix for the same class of bug on the Discover feed.
    """
    prob_sum = sum(o.get(key, 0) or 0 for o in outcomes)
    if prob_sum > 105:  # 105% threshold (same as feed.py's 1.05 on 0-1 scale)
        for o in outcomes:
            if o.get(key):
                o[key] = round(o[key] / prob_sum * 100, 1)


def _market_row(market: FuturesMarket) -> dict | None:
    outcomes = _clean_outcomes(market.outcomes)
    outcomes = sorted(outcomes, key=lambda o: float(o.current_probability or 0), reverse=True)
    if not outcomes:
        return None
    top = outcomes[:3]
    top_outcomes = [
        {
            "name": o.name,
            "prob": round(float(o.current_probability or 0) * 100, 1),
        }
        for o in top
    ]

    # Normalize independent binary market probabilities (BR36 fix)
    # When markets like "Will X win?" are displayed as a ranked list,
    # probabilities from independent contracts can sum well over 100%.
    _normalize_outcome_probs(top_outcomes)

    return {
        "q": market.name,
        "prob": top_outcomes[0]["prob"] if top_outcomes else 0,
        "src": _source(market),
        "market_id": market.id,
        "top_outcomes": top_outcomes,
        "outcome_count": len(outcomes),
    }


_BUCKET_LABEL_RE = re.compile(
    r"^\d+[\-–]\d+%?$|^(?:over|under)\s+\d|^(?:yes|no)$",
    re.I,
)

_NON_US_RE = re.compile(
    r"\b(?:french|france|uk\b|british|canada|canadian|german|germany|brazil|brazilian|"
    r"mexico|mexican|australia|australian|india|indian|japan|japanese|"
    r"colombia|colombian|chile|chilean|argentina|argentin|nigeria|nigerian|"
    r"south\s*africa|turkey|turkish|poland|polish|ukraine|ukrainian|"
    r"israel|israeli|iran|iranian|taiwan|taiwanese|philippines|filipino|"
    r"indonesia|indonesian|egypt|egyptian|south\s*korea|korean|"
    r"italy|italian|spain|spanish|netherlands|dutch|"
    r"eu\b|european|mélenchon|macron|starmer|trudeau|"
    r"modi|scholz|lula|amlo|meloni|milei|petro|boric)\b",
    re.I,
)


def _is_headline_market(name_lower: str) -> bool:
    if _NON_US_RE.search(name_lower):
        return False
    return bool(
        re.search(
            r"\b(?:who\s+win|next\s+president|presidential\s+election|"
            r"win\s+the\s+(?:2028|2032)\s+president|"
            r"president\s+of\s+the\s+united\s+states|"
            r"(?:republican|gop|democratic?)\s+(?:presidential\s+)?nomin)",
            name_lower,
        )
        or ("2028" in name_lower and "president" in name_lower
            and "vp" not in name_lower and "vice" not in name_lower)
    )


# ---------------------------------------------------------------------------
# Presidential — merge candidates across Kalshi + Polymarket
# ---------------------------------------------------------------------------

def _build_presidential(
    pres_markets: list[FuturesMarket],
) -> tuple[dict, dict[int, str]]:
    """Returns (response_dict, outcome_id_to_candidate_key)."""
    kalshi_headline = None
    poly_headline = None
    side_markets: list[dict] = []

    for m in pres_markets:
        name_lower = (m.name or "").lower()
        outcomes = _clean_outcomes(m.outcomes)
        outcomes = sorted(
            outcomes,
            key=lambda o: float(o.current_probability or 0),
            reverse=True,
        )

        if _is_headline_market(name_lower) and len(outcomes) >= 3:
            src = _source(m)
            entry = {"market_id": m.id, "q": m.name, "outcomes": outcomes}
            if src == "kalshi":
                if kalshi_headline is None or len(outcomes) > len(kalshi_headline["outcomes"]):
                    kalshi_headline = entry
            elif src == "polymarket":
                if poly_headline is None or len(outcomes) > len(poly_headline["outcomes"]):
                    poly_headline = entry
        else:
            row = _market_row(m)
            if row and not (row["outcome_count"] <= 2 and row["prob"] > 95):
                side_markets.append(row)

    side_markets.sort(key=lambda r: -abs(r["prob"] - 50))

    # Merge candidates by normalized name + build outcome_id → candidate map
    candidates_by_key: dict[str, dict] = {}
    outcome_id_map: dict[int, str] = {}
    headline_q = None

    for src_key, headline in [("kalshi", kalshi_headline), ("poly", poly_headline)]:
        if not headline:
            continue
        if headline_q is None:
            headline_q = headline["q"]
        for o in headline["outcomes"]:
            name = (o.name or "").strip()
            if _BUCKET_LABEL_RE.match(name):
                continue
            name_key = name.lower()
            prob_val = round(float(o.current_probability or 0) * 100, 1)
            outcome_id_map[o.id] = name_key
            if name_key not in candidates_by_key:
                candidates_by_key[name_key] = {
                    "name": name,
                    "party": _detect_party(name),
                    "kalshi": None,
                    "poly": None,
                }
            candidates_by_key[name_key][src_key] = prob_val

    candidates = []
    for c in candidates_by_key.values():
        probs = [p for p in [c["kalshi"], c["poly"]] if p is not None]
        c["merged"] = round(sum(probs) / len(probs), 1) if probs else 0
        c["change_7d"] = None
        c["history"] = []
        candidates.append(c)

    candidates.sort(key=lambda c: -c["merged"])

    # Normalize candidate probabilities when independent binary markets
    # cause the sum to exceed 105%.  Same pattern as feed.py BR27 fix.
    # Normalize each source independently, then recompute merged.
    for src_key in ("kalshi", "poly"):
        src_sum = sum(c.get(src_key) or 0 for c in candidates)
        if src_sum > 105:
            for c in candidates:
                if c.get(src_key) is not None:
                    c[src_key] = round(c[src_key] / src_sum * 100, 1)

    # Recompute merged from normalized per-source values
    for c in candidates:
        probs = [p for p in [c["kalshi"], c["poly"]] if p is not None]
        c["merged"] = round(sum(probs) / len(probs), 1) if probs else 0

    candidates.sort(key=lambda c: -c["merged"])

    has_dual = kalshi_headline is not None and poly_headline is not None

    response = {
        "count": len(pres_markets),
        "headline_q": headline_q,
        "candidates": candidates[:14],
        "has_dual_source": has_dual,
        "kalshi_market_id": kalshi_headline["market_id"] if kalshi_headline else None,
        "poly_market_id": poly_headline["market_id"] if poly_headline else None,
        "side_markets": side_markets[:8],
    }
    return response, outcome_id_map


# ---------------------------------------------------------------------------
# Chamber control — find Senate/House control binary markets
# ---------------------------------------------------------------------------

_SENATE_CONTROL_RE = re.compile(
    r"\b(?:senate\s+control|control\s+(?:of\s+)?(?:the\s+)?senate|"
    r"republican.*senate|democrat.*senate|gop.*senate)\b", re.I
)
_HOUSE_CONTROL_RE = re.compile(
    r"\b(?:house\s+control|control\s+(?:of\s+)?(?:the\s+)?house|"
    r"republican.*house\b|democrat.*house\b|gop.*house)\b", re.I
)


def _extract_control_probs(market: FuturesMarket) -> dict | None:
    """Extract GOP/Dem probabilities from a control market."""
    outcomes = _clean_outcomes(market.outcomes)
    if not outcomes:
        return None

    gop_prob = None
    dem_prob = None

    for o in outcomes:
        name_lower = (o.name or "").lower()
        prob = round(float(o.current_probability or 0) * 100, 1)
        if any(w in name_lower for w in ["republican", "gop", "red", "(r)"]):
            gop_prob = prob
        elif any(w in name_lower for w in ["democrat", "dem", "blue", "(d)"]):
            dem_prob = prob
        elif name_lower in ("yes", "no"):
            # Binary market: "Will Republicans control the Senate?"
            market_name = (market.name or "").lower()
            if "republican" in market_name or "gop" in market_name:
                gop_prob = prob if name_lower == "yes" else 100 - prob
                dem_prob = 100 - gop_prob
            elif "democrat" in market_name:
                dem_prob = prob if name_lower == "yes" else 100 - prob
                gop_prob = 100 - dem_prob

    result = None
    if gop_prob is not None and dem_prob is not None:
        result = {"gop": gop_prob, "dem": dem_prob, "market_id": market.id}
    elif gop_prob is not None:
        result = {"gop": gop_prob, "dem": round(100 - gop_prob, 1), "market_id": market.id}
    elif dem_prob is not None:
        result = {"gop": round(100 - dem_prob, 1), "dem": dem_prob, "market_id": market.id}
    if result and max(result["gop"], result["dem"]) > 97:
        return None
    return result


def _find_chamber_control(congressional_markets: list[FuturesMarket]) -> dict:
    senate = None
    house = None

    for m in congressional_markets:
        if _is_resolved(m):
            continue
        name = m.name or ""
        if _SENATE_CONTROL_RE.search(name) and senate is None:
            senate = _extract_control_probs(m)
        elif _HOUSE_CONTROL_RE.search(name) and house is None:
            house = _extract_control_probs(m)

    return {
        "senate": senate,
        "house": house,
    }


# ---------------------------------------------------------------------------
# Senate map — per-state Dem win probability
# ---------------------------------------------------------------------------

_STATE_ABBREV: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

_SENATE_STATE_TICKER_RE = re.compile(r"kxsenate[-_]?\d{2}[-_]([a-z]{2})", re.I)

_SENATE_CONTROL_KEYWORDS = re.compile(
    r"\b(?:control|majority|flip|which party)\b", re.I
)


def _extract_senate_state(market: FuturesMarket) -> str | None:
    ext = (market.external_id or "")
    m = _SENATE_STATE_TICKER_RE.search(ext)
    if m:
        return m.group(1).upper()
    name_lower = (market.name or "").lower()
    for full, abbr in _STATE_ABBREV.items():
        if full in name_lower:
            return abbr
    for abbr in _STATE_ABBREV.values():
        if re.search(rf"\b{abbr}\b", market.name or ""):
            return abbr
    return None


def _extract_dem_prob(market: FuturesMarket) -> float | None:
    outcomes = _clean_outcomes(market.outcomes)
    if not outcomes:
        return None
    for o in outcomes:
        name_lower = (o.name or "").lower()
        if "(d)" in name_lower or "democrat" in name_lower:
            return float(o.current_probability or 0)
    market_name = (market.name or "").lower()
    if len(outcomes) <= 2:
        for o in outcomes:
            oname = (o.name or "").lower()
            prob = float(o.current_probability or 0)
            if oname in ("yes", "true"):
                if "republican" in market_name or "gop" in market_name:
                    return 1.0 - prob
                if "democrat" in market_name:
                    return prob
    for o in outcomes:
        party = _detect_party(o.name or "")
        if party == "D":
            return float(o.current_probability or 0)
    for o in outcomes:
        party = _detect_party(o.name or "")
        if party == "R":
            return 1.0 - float(o.current_probability or 0)
    return None


def _build_senate_map(congressional_markets: list[FuturesMarket]) -> dict[str, float]:
    state_probs: dict[str, float] = {}
    for m in congressional_markets:
        if _is_resolved(m):
            continue
        name = (m.name or "").lower()
        if "house" in name:
            continue
        if _SENATE_CONTROL_KEYWORDS.search(name):
            continue
        state = _extract_senate_state(m)
        if not state or state in state_probs:
            continue
        dem_prob = _extract_dem_prob(m)
        if dem_prob is not None:
            state_probs[state] = round(dem_prob * 100, 1)
    return state_probs


# ---------------------------------------------------------------------------
# Cross-source matching — find markets on both Kalshi & Polymarket
# ---------------------------------------------------------------------------

def _cross_source_row_fn(market: FuturesMarket) -> dict | None:
    """Build a row for cross-source matching (politics-specific)."""
    row = _market_row(market)
    if not row:
        return None
    if row["outcome_count"] <= 2 and row["prob"] > 95:
        return None
    row["theme"] = _classify_theme(market)
    return row


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_politics_cached(db: AsyncSession = Depends(get_db)):
    """Return all politics market data (Redis-cached, precomputed hourly)."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:politics")
        await rc.aclose()
        if cached:
            return json.loads(cached)
    except Exception:
        pass  # Fall through to live query

    return await get_politics(db)


async def get_politics(db: AsyncSession):
    """Build politics response from database (called by precompute task + fallback)."""
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
    all_markets = list(result.scalars().unique().all())

    # Collapse Polymarket sub-markets sharing a group_id into a single
    # representative market with merged outcomes (BR62 / #487).
    all_markets = group_markets_by_group_id(all_markets)

    stale_cutoff = now - timedelta(days=7)
    themed: dict[str, list] = defaultdict(list)
    for m in all_markets:
        if _is_resolved(m):
            continue
        if _is_non_politics(m):
            continue
        if m.resolution_date and m.resolution_date < stale_cutoff:
            continue
        theme = _classify_theme(m)
        themed[theme].append(m)

    def build_section(markets: list, limit: int = 10) -> list[dict]:
        rows = []
        for m in markets:
            row = _market_row(m)
            if not row:
                continue
            if row["outcome_count"] <= 2 and row["prob"] > 95:
                continue
            rows.append(row)
        rows.sort(key=lambda r: -abs(r["prob"] - 50))
        return rows[:limit]

    # Presidential — dual-source merge
    presidential, outcome_id_map = _build_presidential(
        themed.get("presidential", [])
    )

    # ── Presidential candidate history (30d, downsampled to 50pts) ──
    if outcome_id_map:
        cutoff = now - timedelta(days=30)
        hist_result = await db.execute(
            select(FuturesOddsSnapshot)
            .where(
                FuturesOddsSnapshot.outcome_id.in_(list(outcome_id_map.keys())),
                FuturesOddsSnapshot.captured_at >= cutoff,
            )
            .order_by(FuturesOddsSnapshot.captured_at)
        )
        hist_snaps = hist_result.scalars().all()

        cand_raw: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for snap in hist_snaps:
            cand_key = outcome_id_map.get(snap.outcome_id)
            if cand_key and snap.probability is not None:
                cand_raw[cand_key].append(
                    (snap.captured_at, round(float(snap.probability) * 100, 1))
                )

        seven_days_ago = now - timedelta(days=7)
        for c in presidential["candidates"]:
            key = c["name"].lower()
            raw = cand_raw.get(key, [])
            if raw:
                past = [p for t, p in raw if t <= seven_days_ago]
                c["change_7d"] = (
                    round(raw[-1][1] - past[-1], 1) if past else None
                )
                if len(raw) > 50:
                    step = len(raw) / 50
                    idx = sorted(
                        set(int(i * step) for i in range(50)) | {len(raw) - 1}
                    )
                    raw = [raw[i] for i in idx]
                c["history"] = [
                    {"t": t.isoformat(), "p": p} for t, p in raw
                ]

    # Congressional — with chamber control + senate map
    congressional_markets = themed.get("congressional", [])
    chamber_control = _find_chamber_control(congressional_markets)
    senate_map = _build_senate_map(congressional_markets)

    # Cross-source spotlight
    cross_source = find_cross_source_markets(
        list(all_markets), market_row_fn=_cross_source_row_fn
    )

    total = len(all_markets)

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "themes": {
            "presidential": presidential,
            "congressional": {
                "count": len(congressional_markets),
                "markets": build_section(congressional_markets),
                "chamber_control": chamber_control,
                "senate_map": senate_map if senate_map else None,
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
        "cross_source": cross_source,
        "by_source": {
            "kalshi": sum(1 for m in all_markets if _source(m) == "kalshi"),
            "polymarket": sum(1 for m in all_markets if _source(m) == "polymarket"),
        },
    }
