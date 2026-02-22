"""
Oscars landing page endpoint.

Aggregates prediction market odds (Polymarket + Kalshi) for the 98th Academy Awards,
groups by award category, merges cross-source nominees, and orders by ceremony presentation.
"""

import logging
import re
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket
from app.services import get_db
from app.utils.odds_math import probability_to_american

logger = logging.getLogger(__name__)

router = APIRouter()

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
    (re.compile(r"best\s+live\s*action\s+short", re.I), "best_live_action_short"),
    (re.compile(r"best\s+documentary\s+short", re.I), "best_documentary_short"),
    (re.compile(r"best\s+animated\s+feature", re.I), "best_animated_feature"),
    (re.compile(r"best\s+international\s+feature", re.I), "best_international_feature"),
    (re.compile(r"best\s+documentary\s+feature", re.I), "best_documentary_feature"),
    (re.compile(r"best\s+documentary(?!\s+short)", re.I), "best_documentary_feature"),
    (re.compile(r"best\s+adapted\s+screenplay", re.I), "best_adapted_screenplay"),
    (re.compile(r"best\s+original\s+screenplay", re.I), "best_original_screenplay"),
    (re.compile(r"best\s+original\s+score", re.I), "best_original_score"),
    (re.compile(r"best\s+original\s+song", re.I), "best_original_song"),
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


def _normalize_category(market_name: str) -> str | None:
    """Extract category key from a market name like 'Oscars 2026: Best Picture'."""
    for pattern, key in _CATEGORY_PATTERNS:
        if pattern.search(market_name):
            return key
    return None


def _normalize_nominee_name(name: str) -> str:
    """
    Normalize a nominee name for cross-source matching.
    Handles formats like "Actor Name - Film Name" (Kalshi) vs "Actor Name" (Polymarket).
    """
    # Strip leading/trailing whitespace
    name = name.strip()
    # Remove common prefixes/suffixes
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    return name


def _match_key(name: str) -> str:
    """
    Create a matching key from a nominee name for cross-source dedup.
    Uses first+last name or first few significant words.
    """
    clean = _normalize_nominee_name(name)
    # Take the part before " - " or " for " (strips film/role info)
    clean = re.split(r"\s+[-–]\s+|\s+for\s+", clean, maxsplit=1)[0]
    # Lowercase, strip non-alphanumeric except spaces
    clean = re.sub(r"[^a-z0-9\s]", "", clean.lower()).strip()
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean)
    return clean


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

    # Group markets by category
    category_markets: dict[str, list] = defaultdict(list)
    trivia_markets: list[dict] = []

    for market in markets:
        cat_key = _normalize_category(market.name)
        if cat_key:
            category_markets[cat_key].append(market)
        else:
            # Non-award market (e.g., "most nominations")
            top_outcomes = sorted(
                [o for o in market.outcomes if o.current_probability is not None],
                key=lambda o: float(o.current_probability),
                reverse=True,
            )[:5]
            trivia_markets.append({
                "id": market.id,
                "name": market.name,
                "source": market.source,
                "top_outcomes": [
                    {
                        "name": o.name,
                        "probability": round(float(o.current_probability), 3) if o.current_probability else None,
                        "american_odds": probability_to_american(float(o.current_probability)) if o.current_probability else None,
                    }
                    for o in top_outcomes
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
                display_name = _normalize_nominee_name(outcome.name)
                key = _match_key(outcome.name)

                if not key:
                    continue

                if key not in nominee_data:
                    nominee_data[key] = {
                        "name": display_name,
                        "sources": {},
                        "probabilities": [],
                        "movement_24h": None,
                    }

                nominee_data[key]["sources"][source] = round(prob, 3)
                nominee_data[key]["probabilities"].append(prob)

                # Use the 24h movement from whichever source has it
                if outcome.probability_change_24h is not None:
                    existing = nominee_data[key]["movement_24h"]
                    change = float(outcome.probability_change_24h)
                    if existing is None or abs(change) > abs(existing):
                        nominee_data[key]["movement_24h"] = round(change, 4)

        # Compute average probability and rank
        nominees = []
        for data in nominee_data.values():
            avg_prob = sum(data["probabilities"]) / len(data["probabilities"])
            american_odds = probability_to_american(avg_prob)

            nominees.append({
                "name": data["name"],
                "probability": round(avg_prob, 3),
                "american_odds": american_odds,
                "movement_24h": data["movement_24h"],
                "sources": data["sources"],
            })

        # Sort by probability descending and assign ranks
        nominees.sort(key=lambda n: n["probability"], reverse=True)
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

    return {
        "ceremony_date": "2026-03-02T00:00:00-08:00",
        "categories": categories,
        "trivia": trivia_markets,
        "total_categories": len(categories),
    }
