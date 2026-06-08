"""Economics markets API endpoint.

Serves prediction-market economic data from Kalshi and Polymarket,
organized into sub-themes: Fed rates, inflation, jobs, GDP/recession,
markets/indices, energy, housing, trade/tariffs, government/fiscal.

Single endpoint returns the full EconData shape consumed by the frontend.
"""

import json
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
# Sub-theme classification — ticker prefix + name pattern matching
# ---------------------------------------------------------------------------

_THEME_BY_TICKER: list[tuple[str, str]] = [
    # Fed / interest rates
    ("kxfedfunds", "fed"),
    ("kxfedcuts", "fed"),
    ("kxfedhikes", "fed"),
    # Inflation / CPI
    ("kxcpi", "inflation"),
    ("kxpce", "inflation"),
    ("kxinflation", "inflation"),
    # Jobs / employment
    ("kxunemployment", "jobs"),
    ("kxjobless", "jobs"),
    ("kxnonfarm", "jobs"),
    ("kxjobs", "jobs"),
    # GDP / recession
    ("kxgdp", "recession"),
    ("kxrecession", "recession"),
    # Markets / indices
    ("kxnasdaq", "markets"),
    ("kxsp500", "markets"),
    ("kxvix", "markets"),
    ("kxdow", "markets"),
    ("kxstocks", "markets"),
    # Energy / commodities
    ("kxgasprice", "energy"),
    ("kxwti", "energy"),
    ("kxbrent", "energy"),
    ("kxoil", "energy"),
    # Housing
    ("kxmortgage", "housing"),
    ("kxhousing", "housing"),
    ("kxhomeprice", "housing"),
    # Trade / tariffs
    ("kxtariff", "trade"),
    ("kxtrade", "trade"),
    # Government / fiscal
    ("kxshutdown", "government"),
    ("kxdebt", "government"),
    ("kxdoge", "government"),
]

_THEME_BY_NAME: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:fed\s*funds|fomc|rate\s*(?:cut|hike|decision)|federal\s*reserve)\b", re.I), "fed"),
    (re.compile(r"\b(?:cpi|inflation|consumer\s*price|pce|breakeven)\b", re.I), "inflation"),
    (re.compile(r"\b(?:unemployment|jobless|nonfarm|payroll|jobs?\s*report)\b", re.I), "jobs"),
    (re.compile(r"\b(?:gdp|recession|economic\s*growth)\b", re.I), "recession"),
    (re.compile(r"\b(?:nasdaq|s&p|dow\s*jones|vix|stock\s*market|nyse)\b", re.I), "markets"),
    (re.compile(r"\b(?:gas\s*price|oil\s*price|crude|wti|brent|petrol|gasoline)\b", re.I), "energy"),
    (re.compile(r"\b(?:mortgage|home\s*price|housing|case.shiller)\b", re.I), "housing"),
    (re.compile(r"\b(?:tariff|trade\s*war|trade\s*deal|import\s*duty)\b", re.I), "trade"),
    (re.compile(r"\b(?:shutdown|debt\s*ceiling|government\s*spending|doge|deficit)\b", re.I), "government"),
    (re.compile(r"\b(?:ecb|bank\s*of\s*(?:japan|england)|boj|boe)\b", re.I), "fed"),
    (re.compile(r"\b(?:consumer\s*sentiment|confidence)\b", re.I), "inflation"),
    (re.compile(r"\b(?:productivity)\b", re.I), "jobs"),
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


def _outcomes_sorted(market: FuturesMarket) -> list:
    return sorted(market.outcomes, key=lambda o: o.rank or 0)


def _market_row(market: FuturesMarket) -> dict | None:
    """Convert a binary market to a Market row. Returns None for multi-outcome markets."""
    outcomes = list(market.outcomes)
    if len(outcomes) > 5:
        return None
    prob = 0.0
    for o in outcomes:
        p = float(o.current_probability or 0)
        if p > prob:
            prob = p
    return {
        "q": market.name,
        "prob": round(prob * 100, 1),
        "src": _source(market),
        "delta": None,
        "market_id": market.id,
    }


def _brackets_from_outcomes(market: FuturesMarket, normalize: bool = True) -> list[list]:
    """Convert multi-outcome market to [[prob, label], ...] brackets.

    When normalize=True, scale so probabilities sum to 100% (removes
    overround from independent binary markets displayed as distributions).
    """
    result = []
    for o in _outcomes_sorted(market):
        p = float(o.current_probability or 0)
        result.append([round(p * 100, 1), o.name or ""])
    if normalize and result:
        total = sum(b[0] for b in result)
        if total > 105:
            for b in result:
                b[0] = round(b[0] * 100 / total, 1)
    return result


def _modal_bracket(brackets: list[list]) -> tuple[int, float, str]:
    """Return (index, prob, label) of highest-probability bracket."""
    best_idx, best_prob, best_label = 0, 0.0, ""
    for i, (prob, label) in enumerate(brackets):
        if prob > best_prob:
            best_idx, best_prob, best_label = i, prob, label
    return best_idx, best_prob, best_label


def _cumulative_to_discrete(outcomes: list, max_buckets: int = 8) -> list[list]:
    """Convert cumulative 'Above X' outcomes to discrete bracket probabilities.

    Kalshi economics markets use cumulative outcomes (P(above 3%), P(above 3.5%)).
    We need P(exactly in bracket) = P(above lower) - P(above upper).
    Returns [[prob, label], ...] sorted by threshold, at most max_buckets entries.
    """
    import re as _re

    raw = []
    for o in outcomes:
        p = float(o.current_probability or 0) * 100
        label = (o.name or "").strip()
        nums = _re.findall(r'[\d.]+', label)
        sort_val = float(nums[0]) if nums else 0
        # Clean label: remove "Above " prefix
        clean = label.replace("Above ", "").strip()
        raw.append((p, clean, sort_val))

    if not raw:
        return []

    # Sort by threshold ascending (lowest first)
    raw.sort(key=lambda x: x[2])

    # Enforce monotonicity: P(above lower threshold) >= P(above higher threshold)
    for i in range(1, len(raw)):
        if raw[i][0] > raw[i - 1][0]:
            raw[i] = (raw[i - 1][0], raw[i][1], raw[i][2])

    # Convert cumulative to discrete:
    # P(in bracket i) = P(above threshold_i) - P(above threshold_{i+1})
    # P(above highest) stays as-is (the top bracket)
    discrete = []
    for i in range(len(raw)):
        cum_p = raw[i][0]
        next_p = raw[i + 1][0] if i + 1 < len(raw) else 0
        bracket_p = round(cum_p - next_p, 1)
        if bracket_p >= 0.1:
            discrete.append([bracket_p, raw[i][1]])

    # If too many, keep top by probability
    if len(discrete) > max_buckets:
        discrete.sort(key=lambda x: x[0], reverse=True)
        discrete = discrete[:max_buckets]
        discrete.sort(key=lambda x: x[1])

    # Normalize: independent binary markets can sum well over 100%.
    # Same threshold as _brackets_from_outcomes / politics _normalize_outcome_probs.
    if discrete:
        total = sum(b[0] for b in discrete)
        if total > 105:
            for b in discrete:
                b[0] = round(b[0] * 100 / total, 1)

    return discrete


# ---------------------------------------------------------------------------
# Cross-source matching — find markets on both Kalshi & Polymarket
# ---------------------------------------------------------------------------


def _cross_source_row_fn(market: FuturesMarket) -> dict | None:
    """Build a row for cross-source matching (economics-specific)."""
    outcomes = _clean_outcomes(list(market.outcomes))
    outcomes = sorted(
        outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    if not outcomes:
        return None
    top = outcomes[:3]
    row = {
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
        "theme": _classify_theme(market),
    }
    if row["outcome_count"] <= 2 and row["prob"] > 95:
        return None
    return row


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_economics_cached(db: AsyncSession = Depends(get_db)):
    """Return all economics market data (Redis-cached, precomputed hourly).

    Falls back to a stale cache (24h TTL) when the primary cache is cold,
    and wraps the live DB query with a 25s timeout so Heroku never kills
    the connection.
    """
    import asyncio
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:economics")
        if cached:
            await rc.aclose()
            return json.loads(cached)
        # Primary cache miss — try stale fallback
        stale = await rc.get("bainluck:category:economics:stale")
        await rc.aclose()
        if stale:
            logger.info("Economics: serving stale cache (primary miss)")
            return json.loads(stale)
    except Exception:
        pass  # Fall through to live query

    # Live DB fallback with timeout guard
    try:
        response = await asyncio.wait_for(get_economics(db), timeout=25)
    except asyncio.TimeoutError:
        logger.warning("Economics live query timed out after 25s")
        return {"error": "timeout", "themes": {}}

    # Populate stale cache for future cold-cache resilience
    try:
        rc = get_async_redis_client()
        await rc.set(
            "bainluck:category:economics:stale",
            json.dumps(response, default=str),
            ex=86400,
        )
        await rc.aclose()
    except Exception:
        logger.warning("Economics: failed to write stale cache", exc_info=True)

    return response


async def get_economics(db: AsyncSession):
    """Build economics response from database (called by precompute task + fallback)."""
    now = datetime.now(timezone.utc)

    # Query all open economics markets with outcomes
    econ_categories = ["economics", "finance", "crypto"]
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.llm_sport_category.in_(econ_categories),
                # Also grab Kalshi markets with economics ticker prefixes
                # regardless of llm_sport_category (often misclassified)
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

    # Classify into themes
    themed: dict[str, list] = defaultdict(list)
    for m in all_markets:
        theme = _classify_theme(m)
        themed[theme].append(m)

    # Build response sections
    fed_markets = themed.get("fed", [])
    inflation_markets = themed.get("inflation", [])
    jobs_markets = themed.get("jobs", [])
    recession_markets = themed.get("recession", [])
    markets_markets = themed.get("markets", [])
    energy_markets = themed.get("energy", [])
    housing_markets = themed.get("housing", [])
    trade_markets = themed.get("trade", [])
    gov_markets = themed.get("government", [])

    # --- Fed rates section ---
    _MONTH_ORDER = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    fomc_meetings = []
    rate_cuts = []
    rate_side = []
    for m in fed_markets:
        name_lower = (m.name or "").lower()
        ext_lower = (m.external_id or "").lower()
        outcomes = _outcomes_sorted(m)
        if "fed funds rate after" in name_lower and len(outcomes) >= 3:
            has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
            if has_cumulative:
                discrete = _cumulative_to_discrete(outcomes, max_buckets=10)
                # Reverse so highest rate is first (top of heatmap)
                discrete.reverse()
            else:
                discrete = _brackets_from_outcomes(m)

            date_str = m.name.split("after ")[-1].split("?")[0].strip() if "after" in (m.name or "") else ""
            mo = date_str.split(" ")[0] if date_str else ""
            # Extract year for sorting (e.g., "Jun 2026" → 202606)
            parts = date_str.split()
            sort_key = 0
            if len(parts) >= 2:
                year = int(parts[1]) if parts[1].isdigit() else 2026
                month_num = _MONTH_ORDER.get(mo[:3].lower(), 0)
                sort_key = year * 100 + month_num

            fomc_meetings.append({
                "date": date_str,
                "mo": mo,
                "dist": discrete,
                "resolved": m.status in ("resolved", "closed"),
                "market_id": m.id,
                "sort_key": sort_key,
            })
        elif "how many" in name_lower and ("cut" in name_lower or "hike" in name_lower):
            rate_cuts = _brackets_from_outcomes(m)
        else:
            _row = _market_row(m)
            if _row:
                rate_side.append(_row)

    # Sort FOMC meetings chronologically
    fomc_meetings.sort(key=lambda x: x.get("sort_key", 0))

    # --- Inflation section ---
    cpi_releases = []
    inflation_side = []
    # Filter out past-month CPI markets (e.g., "May 2026" when it's June)
    _current_month = now.month
    _current_year = now.year
    _MONTH_NUMS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                   "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    for m in inflation_markets:
        name_lower = (m.name or "").lower()
        # Skip past-month CPI releases
        _mo_check = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})\b", name_lower)
        if _mo_check:
            _m_num = _MONTH_NUMS.get(_mo_check.group(1)[:3], 0)
            _m_year = int(_mo_check.group(2))
            if (_m_year < _current_year) or (_m_year == _current_year and _m_num < _current_month):
                continue
        outcomes = _outcomes_sorted(m)
        has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
        if ("cpi" in name_lower or "inflation" in name_lower) and len(outcomes) >= 3:
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if not brackets:
                _row = _market_row(m)
                if _row:
                    inflation_side.append(_row)
                continue
            modal_idx, _, _ = _modal_bracket(brackets)
            # Extract short month label from name (e.g. "CPI YoY for May 2026" → "May")
            _mo_match = re.search(
                r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\b",
                m.name or "",
                re.IGNORECASE,
            )
            _cpi_mo = _mo_match.group(0).title()[:3] if _mo_match else m.name[:20]
            cpi_releases.append({
                "mo": _cpi_mo,
                "brackets": brackets,
                "upcoming": True,
                "peakIs": modal_idx,
                "market_id": m.id,
            })
        else:
            _row = _market_row(m)
            if _row:
                inflation_side.append(_row)

    # --- Jobs section ---
    jobs_side = [r for m in jobs_markets if (r := _market_row(m))]

    # --- Recession/GDP section ---
    rec_main_prob = None
    rec_side = []
    gdp_quarters = []
    for m in recession_markets:
        name_lower = (m.name or "").lower()
        outcomes = _outcomes_sorted(m)
        if "recession" in name_lower and len(outcomes) <= 2:
            for o in outcomes:
                if (o.name or "").lower() in ("yes", ""):
                    rec_main_prob = round(float(o.current_probability or 0) * 100, 1)
                    break
            if rec_main_prob is None:
                rec_main_prob = round(float(outcomes[0].current_probability or 0) * 100, 1)
            _row = _market_row(m)
            if _row:
                rec_side.append(_row)
        elif "gdp" in name_lower and len(outcomes) >= 3:
            has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if brackets:
                gdp_quarters.append({
                    "q": m.name,
                    "dist": brackets,
                    "market_id": m.id,
                })
        else:
            _row = _market_row(m)
            if _row:
                rec_side.append(_row)

    # --- Markets/indices section ---
    today_indices = []
    stocks = []
    markets_side = []
    for m in markets_markets:
        name_lower = (m.name or "").lower()
        if any(idx in name_lower for idx in ("nasdaq", "s&p", "dow", "vix")) and ("up or down" in name_lower or "close" in name_lower):
            for o in _outcomes_sorted(m):
                if (o.name or "").lower() in ("up", "yes", ""):
                    today_indices.append({
                        "sym": m.name.split(" Up ")[0].split(" up ")[0].split("?")[0].strip()[:20],
                        "prob": round(float(o.current_probability or 0) * 100, 1),
                        "dir": "up",
                        "range": "",
                        "src": _source(m),
                    })
                    break
        elif any(stock in name_lower for stock in ("meta ", "aapl", "tsla", "nvda", "msft", "googl", "apple", "tesla", "nvidia", "microsoft", "google")):
            for o in _outcomes_sorted(m):
                if (o.name or "").lower() in ("up", "yes", ""):
                    sym = m.name.split("(")[1].split(")")[0] if "(" in m.name else m.name.split(" ")[0]
                    stocks.append({
                        "sym": sym[:6],
                        "prob": round(float(o.current_probability or 0) * 100, 1),
                        "delta": None,
                        "src": _source(m),
                    })
                    break
        else:
            _row = _market_row(m)
            if _row:
                markets_side.append(_row)

    # --- Energy section ---
    gas_markets_list = []
    oil_rows = []
    for m in energy_markets:
        name_lower = (m.name or "").lower()
        outcomes = _outcomes_sorted(m)
        has_cumulative = any("above" in (o.name or "").lower() for o in outcomes)
        if ("gas" in name_lower or "oil" in name_lower or "wti" in name_lower or "brent" in name_lower or "natural gas" in name_lower) and len(outcomes) >= 3:
            if has_cumulative:
                brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
            else:
                brackets = _brackets_from_outcomes(m)
            if not brackets:
                _row = _market_row(m)
                if _row:
                    oil_rows.append(_row)
                continue
            _, modal_prob, modal_label = _modal_bracket(brackets)
            # Shorten the label
            short_label = m.name
            if len(short_label) > 40:
                for trim in [" on ", " at ", " for ", " in "]:
                    if trim in short_label.lower():
                        short_label = short_label[:short_label.lower().index(trim)]
                        break
            if "gas" in name_lower:
                gas_markets_list.append({
                    "label": short_label,
                    "val": modal_label,
                    "prob": modal_prob,
                    "brackets": brackets,
                    "src": _source(m),
                })
            else:
                oil_rows.append({
                    "sym": "WTI" if "wti" in name_lower else "Brent" if "brent" in name_lower else "Oil",
                    "prob": modal_prob,
                    "range": modal_label,
                    "src": _source(m),
                    "q": short_label,
                })
            continue
        else:
            _row = _market_row(m)
            if _row:
                oil_rows.append(_row)

    # --- Housing section ---
    mortgage_brackets = []
    housing_side = []
    for m in housing_markets:
        name_lower = (m.name or "").lower()
        if "mortgage" in name_lower and len(_outcomes_sorted(m)) >= 3:
            mortgage_brackets = _brackets_from_outcomes(m)
        else:
            _row = _market_row(m)
            if _row:
                housing_side.append(_row)

    # --- Trade & Government ---
    trade_rows = [r for m in trade_markets if (r := _market_row(m))]
    gov_rows = [r for m in gov_markets if (r := _market_row(m))]

    # Cross-source spotlight
    cross_source = find_cross_source_markets(
        all_markets, market_row_fn=_cross_source_row_fn
    )

    # Count total active markets
    total = len(all_markets)

    return {
        "total_markets": total,
        "updated_at": now.isoformat(),
        "cross_source": cross_source,
        "themes": {
            "fed": {
                "count": len(fed_markets),
                "fomc_meetings": fomc_meetings[:8],
                "rate_cuts": rate_cuts,
                "side_markets": rate_side[:6],
            },
            "inflation": {
                "count": len(inflation_markets),
                "cpi_releases": cpi_releases[:6],
                "side_markets": inflation_side[:6],
            },
            "jobs": {
                "count": len(jobs_markets),
                "markets": jobs_side[:8],
            },
            "recession": {
                "count": len(recession_markets),
                "main_prob": rec_main_prob,
                "gdp_quarters": gdp_quarters[:4],
                "side_markets": rec_side[:6],
            },
            "markets": {
                "count": len(markets_markets),
                "today": today_indices[:4],
                "stocks": stocks[:6],
                "side_markets": markets_side[:8],
            },
            "energy": {
                "count": len(energy_markets),
                "gas": gas_markets_list[:2],
                "oil": oil_rows[:4],
                "side_markets": [r for m in energy_markets if (r := _market_row(m))][:8],
            },
            "housing": {
                "count": len(housing_markets),
                "mortgage_brackets": mortgage_brackets,
                "markets": housing_side[:6],
            },
            "trade": {
                "count": len(trade_markets),
                "markets": trade_rows[:8],
            },
            "government": {
                "count": len(gov_markets),
                "markets": gov_rows[:8],
            },
        },
        "by_source": {
            "kalshi": sum(1 for m in all_markets if _source(m) == "kalshi"),
            "polymarket": sum(1 for m in all_markets if _source(m) == "polymarket"),
        },
    }
