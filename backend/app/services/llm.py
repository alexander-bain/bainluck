"""
LLM utility service for smart text processing tasks.

Uses OpenAI's GPT-4o-mini for cost-effective classification and extraction.
"""

import os
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Lazy import to avoid issues if openai isn't installed
_client = None


def _get_client():
    """Get or create OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set - LLM features disabled")
                return None
            _client = OpenAI(api_key=api_key)
        except ImportError:
            logger.warning("openai package not installed - LLM features disabled")
            return None
    return _client


def is_available() -> bool:
    """Check if LLM service is available."""
    return _get_client() is not None


def classify(
    text: str,
    categories: list[str],
    context: str = "",
    model: str = "gpt-4o-mini",
) -> Optional[str]:
    """
    Classify text into one of the provided categories.

    Args:
        text: The text to classify
        categories: List of valid category options
        context: Optional context to help with classification
        model: OpenAI model to use (default: gpt-4o-mini)

    Returns:
        The selected category, or None if classification failed
    """
    client = _get_client()
    if not client:
        return None

    categories_str = ", ".join(categories)

    system_prompt = f"""You are a classification assistant. Your task is to classify text into exactly one of these categories: {categories_str}

Rules:
- Respond with ONLY the category name, nothing else
- Choose the single best matching category
- If uncertain, choose the closest match
{f"Context: {context}" if context else ""}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=50,
            temperature=0,  # Deterministic for classification
        )

        result = response.choices[0].message.content.strip().lower()

        # Validate result is one of the categories
        categories_lower = [c.lower() for c in categories]
        if result in categories_lower:
            # Return the original case version
            return categories[categories_lower.index(result)]

        # Try partial match (e.g., "basketball" matches "basketball")
        for i, cat in enumerate(categories_lower):
            if cat in result or result in cat:
                return categories[i]

        logger.warning(f"LLM returned unexpected category '{result}' for text '{text[:50]}...'")
        return None

    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        return None


# Sport categories for futures classification
SPORT_CATEGORIES = [
    "football",
    "basketball",
    "baseball",
    "hockey",
    "golf",
    "tennis",
    "soccer",
    "mma",
    "motorsports",
    "boxing",
    "cricket",
    "rugby",
    "olympics",
    "esports",
    "entertainment",
    "politics",
    "other",
]


def classify_futures_market(market_name: str) -> Optional[str]:
    """
    Classify a futures market name into a sport category.

    This is a specialized wrapper around classify() for futures categorization.

    Args:
        market_name: The name of the futures market (e.g., "2026 Masters Tournament Winner")

    Returns:
        Sport category string, or None if classification failed
    """
    return classify(
        text=market_name,
        categories=SPORT_CATEGORIES,
        context="This is the name of a betting/prediction market. Classify it by the sport or topic it relates to.",
    )


# Simple in-memory cache for repeated classifications
@lru_cache(maxsize=1000)
def classify_futures_market_cached(market_name: str) -> Optional[str]:
    """
    Cached version of classify_futures_market.

    Uses LRU cache to avoid repeated API calls for the same market names.
    """
    return classify_futures_market(market_name)
