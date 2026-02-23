"""
Oscars landing page endpoint.

Aggregates prediction market odds (Polymarket + Kalshi) for the 98th Academy Awards,
groups by award category, merges cross-source nominees, and orders by ceremony presentation.
"""

import asyncio
import logging
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket
from app.services import get_db
from app.utils.odds_math import probability_to_american

logger = logging.getLogger(__name__)

router = APIRouter()

# Ceremony start: March 2, 2026 at 8:00 PM ET (01:00 UTC March 3)
_CEREMONY_START = datetime(2026, 3, 3, 1, 0, 0, tzinfo=timezone.utc)
# Ceremony end: ~11:30 PM ET (approximate 3.5h show)
_CEREMONY_END = datetime(2026, 3, 3, 4, 30, 0, tzinfo=timezone.utc)

# Ceremony presentation order (98th Academy Awards, March 2, 2026)
CEREMONY_ORDER = {
    "best_supporting_actor": 1,
    "best_casting": 2,
    "best_animated_short": 3,
    "best_live_action_short": 4,
    "best_makeup_hairstyling": 5,
    "best_costume_design": 6,
    "best_documentary_short": 7,
    "best_sound": 8,
    "best_original_score": 9,
    "best_film_editing": 10,
    "best_visual_effects": 11,
    "best_animated_feature": 12,
    "best_supporting_actress": 13,
    "best_original_song": 14,
    "best_international_feature": 15,
    "best_documentary_feature": 16,
    "best_adapted_screenplay": 17,
    "best_production_design": 18,
    "best_cinematography": 19,
    "best_original_screenplay": 20,
    "best_director": 21,
    "best_actress": 22,
    "best_actor": 23,
    "best_picture": 24,
}

MAJOR_CATEGORIES = {
    "best_picture", "best_director", "best_actor", "best_actress",
    "best_supporting_actor", "best_supporting_actress",
}

# Person categories — these are about people, not films (used for film aggregation)
PERSON_CATEGORIES = {
    "best_actor", "best_actress", "best_supporting_actor",
    "best_supporting_actress", "best_director",
}

# Display names for category keys
CATEGORY_DISPLAY_NAMES = {
    "best_supporting_actor": "Best Supporting Actor",
    "best_casting": "Best Casting",
    "best_animated_short": "Best Animated Short Film",
    "best_live_action_short": "Best Live Action Short Film",
    "best_makeup_hairstyling": "Best Makeup and Hairstyling",
    "best_costume_design": "Best Costume Design",
    "best_documentary_short": "Best Documentary Short Film",
    "best_sound": "Best Sound",
    "best_original_score": "Best Original Score",
    "best_film_editing": "Best Film Editing",
    "best_visual_effects": "Best Visual Effects",
    "best_animated_feature": "Best Animated Feature Film",
    "best_supporting_actress": "Best Supporting Actress",
    "best_original_song": "Best Original Song",
    "best_international_feature": "Best International Feature Film",
    "best_documentary_feature": "Best Documentary Feature Film",
    "best_adapted_screenplay": "Best Adapted Screenplay",
    "best_production_design": "Best Production Design",
    "best_cinematography": "Best Cinematography",
    "best_original_screenplay": "Best Original Screenplay",
    "best_director": "Best Director",
    "best_actress": "Best Actress",
    "best_actor": "Best Actor",
    "best_picture": "Best Picture",
}

# Regex patterns to extract category key from market name
# Order matters: more specific patterns first
_CATEGORY_PATTERNS = [
    (re.compile(r"best\s+supporting\s+actor", re.I), "best_supporting_actor"),
    (re.compile(r"best\s+supporting\s+actress", re.I), "best_supporting_actress"),
    (re.compile(r"best\s+animated\s+short", re.I), "best_animated_short"),
    (re.compile(r"animated\s+short\s+film", re.I), "best_animated_short"),
    (re.compile(r"best\s+live\s*action\s+short", re.I), "best_live_action_short"),
    (re.compile(r"live\s*action\s+short\s+film", re.I), "best_live_action_short"),
    (re.compile(r"best\s+documentary\s+short", re.I), "best_documentary_short"),
    (re.compile(r"documentary\s+short\s+(?:film|subject)", re.I), "best_documentary_short"),
    (re.compile(r"best\s+animated\s+feature", re.I), "best_animated_feature"),
    (re.compile(r"animated\s+feature\s+film", re.I), "best_animated_feature"),
    (re.compile(r"best\s+international\s+feature", re.I), "best_international_feature"),
    (re.compile(r"international\s+feature\s+film", re.I), "best_international_feature"),
    (re.compile(r"best\s+documentary\s+feature", re.I), "best_documentary_feature"),
    (re.compile(r"best\s+documentary(?!\s+short)", re.I), "best_documentary_feature"),
    (re.compile(r"best\s+adapted\s+screenplay", re.I), "best_adapted_screenplay"),
    (re.compile(r"best\s+original\s+screenplay", re.I), "best_original_screenplay"),
    (re.compile(r"best\s+original\s+score", re.I), "best_original_score"),
    (re.compile(r"music\s*\(?\s*original\s+score", re.I), "best_original_score"),
    (re.compile(r"best\s+original\s+song", re.I), "best_original_song"),
    (re.compile(r"music\s*\(?\s*original\s+song", re.I), "best_original_song"),
    (re.compile(r"best\s+production\s+design", re.I), "best_production_design"),
    (re.compile(r"best\s+costume\s+design", re.I), "best_costume_design"),
    (re.compile(r"best\s+makeup", re.I), "best_makeup_hairstyling"),
    (re.compile(r"best\s+visual\s+effects", re.I), "best_visual_effects"),
    (re.compile(r"best\s+film\s+editing", re.I), "best_film_editing"),
    (re.compile(r"best\s+cinematography", re.I), "best_cinematography"),
    (re.compile(r"best\s+sound", re.I), "best_sound"),
    (re.compile(r"best\s+cast(?:ing)?", re.I), "best_casting"),
    (re.compile(r"best\s+picture", re.I), "best_picture"),
    (re.compile(r"best\s+director", re.I), "best_director"),
    (re.compile(r"best\s+actress", re.I), "best_actress"),
    (re.compile(r"best\s+actor", re.I), "best_actor"),
]


def _strip_diacritics(s: str) -> str:
    """Remove accent marks: e->e, a->a, u->u, etc."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _is_oscars_market(name: str) -> bool:
    """Filter out false positives like boxing matches containing 'Oscar' as a name."""
    name_lower = name.lower()
    if " vs " in name_lower or " vs." in name_lower:
        return False
    return True


def _normalize_category(market_name: str) -> str | None:
    """Extract category key from a market name like 'Oscars 2026: Best Picture'."""
    for pattern, key in _CATEGORY_PATTERNS:
        if pattern.search(market_name):
            return key
    return None


def _normalize_nominee_name(name: str) -> str:
    """Normalize a nominee name for display."""
    name = name.strip()
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    return name


def _match_key(name: str) -> str:
    """
    Create a matching key from a nominee name for cross-source dedup.
    Strips diacritics, "The " prefix, subtitle after colon, and normalizes whitespace.
    """
    clean = _normalize_nominee_name(name)
    # Take the part before " - " or " for " (strips film/role info)
    clean = re.split(r"\s+[-\u2013]\s+|\s+for\s+", clean, maxsplit=1)[0]
    # Strip diacritics (e->e, n->n, etc.)
    clean = _strip_diacritics(clean)
    # Lowercase
    clean = clean.lower()
    # Strip "the " prefix
    clean = re.sub(r"^the\s+", "", clean)
    # Strip subtitle after colon ("F1: The Movie" -> "F1")
    clean = clean.split(":")[0].strip()
    # Strip non-alphanumeric except spaces
    clean = re.sub(r"[^a-z0-9\s]", "", clean).strip()
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _get_ceremony_status() -> str:
    """Determine ceremony status based on current time."""
    now = datetime.now(timezone.utc)
    if now < _CEREMONY_START:
        return "pre"
    elif now <= _CEREMONY_END:
        return "live"
    else:
        return "post"


# ============================================================================
# LLM preview cache (in-memory, 4h TTL)
# ============================================================================

_LLM_CACHE: dict[str, tuple[str, float]] = {}  # key -> (text, timestamp)
_LLM_CACHE_TTL = 4 * 3600  # 4 hours


def _get_cached(key: str) -> str | None:
    entry = _LLM_CACHE.get(key)
    if entry and time.time() - entry[1] < _LLM_CACHE_TTL:
        return entry[0]
    return None


def _set_cached(key: str, value: str) -> None:
    _LLM_CACHE[key] = (value, time.time())


# Max nominees to return per category
_MAX_NOMINEES = 10


@router.get("")
async def get_oscars(
    db: AsyncSession = Depends(get_db),
):
    """
    Get all Oscar award categories with aggregated prediction market odds.

    Returns categories ordered by ceremony presentation, with nominees
    merged across Polymarket and Kalshi sources.
    """
    # Query all Oscar-related futures markets
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.name.ilike("%oscar%"),
                FuturesMarket.name.ilike("%academy award%"),
            ),
        )
    )

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    # Filter out false positives (e.g., boxing matches with "Oscar" as a fighter name)
    markets = [m for m in markets if _is_oscars_market(m.name)]

    # Group markets by category
    category_markets: dict[str, list] = defaultdict(list)
    trivia_markets: list[dict] = []

    for market in markets:
        cat_key = _normalize_category(market.name)
        if cat_key:
            category_markets[cat_key].append(market)
        else:
            # Non-award market (e.g., "most nominations", "how many Oscars")
            top_outcomes = sorted(
                [o for o in market.outcomes if o.current_probability is not None],
                key=lambda o: float(o.current_probability),
                reverse=True,
            )[:5]

            # Skip markets where all outcomes have the same name
            # (Polymarket NegRisk: outcomes named "Sinners" x5 instead of counts)
            unique_names = set(
                _normalize_nominee_name(o.name) for o in top_outcomes
            )
            if len(unique_names) <= 1 and len(top_outcomes) > 1:
                continue

            # Filter out Kalshi 0.5 noise from trivia outcomes too
            filtered_outcomes = [
                o for o in top_outcomes
                if not (market.source == "kalshi" and o.current_probability is not None
                        and float(o.current_probability) == 0.5)
            ]
            if not filtered_outcomes:
                filtered_outcomes = top_outcomes  # Fallback if all were 0.5

            trivia_markets.append({
                "id": market.id,
                "name": market.name,
                "source": market.source,
                "top_outcomes": [
                    {
                        "name": _normalize_nominee_name(o.name),
                        "probability": round(float(o.current_probability), 3) if o.current_probability else None,
                        "american_odds": probability_to_american(float(o.current_probability)) if o.current_probability else None,
                    }
                    for o in filtered_outcomes
                ],
            })

    # Build category response with cross-source aggregation
    categories = []

    for cat_key, cat_markets in category_markets.items():
        # Merge nominees across sources
        nominee_data: dict[str, dict] = {}  # match_key -> aggregated data

        market_ids = []
        for market in cat_markets:
            market_ids.append(market.id)
            source = market.source or "unknown"

            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue

                prob = float(outcome.current_probability)

                # Skip Kalshi entries at exactly 0.5 -- illiquid binary markets with no signal
                if source == "kalshi" and prob == 0.5:
                    continue

                # Skip "Tie" outcomes -- not useful for the landing page
                raw_name = outcome.name.strip()
                if raw_name.lower() == "tie":
                    continue

                display_name = _normalize_nominee_name(raw_name)
                key = _match_key(raw_name)

                if not key:
                    continue

                if key not in nominee_data:
                    nominee_data[key] = {
                        "name": display_name,
                        "sources": {},
                        "probabilities": [],
                        "movement_24h": None,
                        "opening_probability": None,
                        "is_winner": False,
                        "last_updated": None,
                    }

                nominee_data[key]["sources"][source] = round(prob, 3)
                nominee_data[key]["probabilities"].append(prob)

                # Use the 24h movement from whichever source has it
                if outcome.probability_change_24h is not None:
                    existing = nominee_data[key]["movement_24h"]
                    change = float(outcome.probability_change_24h)
                    if existing is None or abs(change) > abs(existing):
                        nominee_data[key]["movement_24h"] = round(change, 4)

                # Track opening probability (take the first non-null one)
                if outcome.opening_probability is not None and nominee_data[key]["opening_probability"] is None:
                    nominee_data[key]["opening_probability"] = round(float(outcome.opening_probability), 3)

                # Track winner status (any source marking it as winner)
                if outcome.is_winner:
                    nominee_data[key]["is_winner"] = True

                # Track most recent last_updated
                if outcome.last_updated is not None:
                    existing_ts = nominee_data[key]["last_updated"]
                    if existing_ts is None or outcome.last_updated > existing_ts:
                        nominee_data[key]["last_updated"] = outcome.last_updated

        # Compute average probability
        nominees = []
        for data in nominee_data.values():
            avg_prob = sum(data["probabilities"]) / len(data["probabilities"])
            last_updated = data["last_updated"]
            nominees.append({
                "name": data["name"],
                "probability": avg_prob,
                "movement_24h": data["movement_24h"],
                "sources": data["sources"],
                "opening_probability": data["opening_probability"],
                "is_winner": data["is_winner"],
                "last_updated": last_updated.isoformat() if last_updated else None,
            })

        # Sort by probability descending, cap at max nominees
        nominees.sort(key=lambda n: n["probability"], reverse=True)
        nominees = nominees[:_MAX_NOMINEES]

        # Normalize probabilities so they sum to ~100%
        total_prob = sum(n["probability"] for n in nominees)
        if total_prob > 0:
            for nom in nominees:
                nom["probability"] = round(nom["probability"] / total_prob, 3)
                nom["american_odds"] = probability_to_american(nom["probability"])
        else:
            for nom in nominees:
                nom["probability"] = round(nom["probability"], 3)
                nom["american_odds"] = probability_to_american(nom["probability"])

        # Assign ranks
        for i, nom in enumerate(nominees):
            nom["rank"] = i + 1

        ceremony_order = CEREMONY_ORDER.get(cat_key, 99)
        display_name = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key.replace("_", " ").title())

        categories.append({
            "key": cat_key,
            "name": display_name,
            "ceremony_order": ceremony_order,
            "is_major": cat_key in MAJOR_CATEGORIES,
            "market_ids": market_ids,
            "nominees": nominees,
        })

    # Sort categories by ceremony order
    categories.sort(key=lambda c: c["ceremony_order"])

    # ========================================================================
    # Biggest movers — top 5 nominees across all categories by |movement_24h|
    # ========================================================================
    all_movers = []
    for cat in categories:
        for nom in cat["nominees"]:
            if nom["movement_24h"] is not None and abs(nom["movement_24h"]) >= 0.005:
                all_movers.append({
                    "name": nom["name"],
                    "category_key": cat["key"],
                    "category_name": cat["name"],
                    "movement_24h": nom["movement_24h"],
                    "probability": nom["probability"],
                })
    all_movers.sort(key=lambda m: abs(m["movement_24h"]), reverse=True)
    biggest_movers = all_movers[:5]

    # ========================================================================
    # Film-centric aggregation — group nominees across non-person categories
    # ========================================================================
    film_map: dict[str, list] = {}
    for cat in categories:
        if cat["key"] in PERSON_CATEGORIES:
            continue
        for nom in cat["nominees"]:
            # Use the part before " - " as the film name
            film_name = nom["name"].split(" - ")[0].strip()
            film_map.setdefault(film_name, []).append({
                "category_key": cat["key"],
                "category_name": cat["name"],
                "probability": nom["probability"],
                "rank": nom["rank"],
            })

    film_nominations = [
        {
            "film_name": name,
            "nominations": noms,
            "total_nominations": len(noms),
            "expected_wins": round(sum(n["probability"] for n in noms), 2),
        }
        for name, noms in film_map.items()
        if len(noms) >= 2  # Only show films with 2+ nominations
    ]
    film_nominations.sort(key=lambda f: f["expected_wins"], reverse=True)

    # ========================================================================
    # LLM previews — generate for major categories (async, cached)
    # ========================================================================
    llm_previews: dict[str, str] = {}

    async def _generate_preview(cat: dict) -> tuple[str, str | None]:
        """Generate or retrieve cached LLM preview for a category."""
        cache_key = f"oscars_preview_{cat['key']}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cat["key"], cached

        try:
            from app.services.llm import generate_oscars_category_preview
            top_nominees = [
                {
                    "name": n["name"],
                    "probability": n["probability"],
                    "movement_24h": n["movement_24h"],
                    "opening_probability": n["opening_probability"],
                }
                for n in cat["nominees"][:5]
            ]
            result = generate_oscars_category_preview(cat["name"], top_nominees)
            if result:
                _set_cached(cache_key, result)
            return cat["key"], result
        except Exception as e:
            logger.warning("LLM preview failed for %s: %s", cat["key"], e)
            return cat["key"], None

    # Generate previews for major categories only
    major_cats = [c for c in categories if c["is_major"]]
    if major_cats:
        preview_tasks = [_generate_preview(c) for c in major_cats]
        results = await asyncio.gather(*preview_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple) and r[1] is not None:
                llm_previews[r[0]] = r[1]

    # Generate movers summary
    if biggest_movers:
        movers_cache_key = "oscars_movers_summary"
        cached_movers = _get_cached(movers_cache_key)
        if cached_movers:
            llm_previews["biggest_movers"] = cached_movers
        else:
            try:
                from app.services.llm import generate_oscars_movers_summary
                movers_text = generate_oscars_movers_summary(biggest_movers)
                if movers_text:
                    _set_cached(movers_cache_key, movers_text)
                    llm_previews["biggest_movers"] = movers_text
            except Exception as e:
                logger.warning("LLM movers summary failed: %s", e)

    return {
        "ceremony_date": "2026-03-02T00:00:00-08:00",
        "ceremony_status": _get_ceremony_status(),
        "categories": categories,
        "trivia": trivia_markets,
        "total_categories": len(categories),
        "biggest_movers": biggest_movers,
        "film_nominations": film_nominations,
        "llm_previews": llm_previews,
    }
