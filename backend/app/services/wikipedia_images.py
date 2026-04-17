"""Fetch wrestler thumbnail images from Wikipedia's pageimages API."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

WIKI_API = "https://en.wikipedia.org/w/api.php"


async def fetch_wikipedia_thumbnail(name: str, size: int = 300) -> Optional[str]:
    """
    Fetch a Wikipedia page thumbnail for a wrestler name.
    Returns the image URL or None if not found.
    """
    params = {
        "action": "query",
        "titles": name,
        "prop": "pageimages",
        "format": "json",
        "pithumbsize": size,
        "redirects": 1,
    }
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "BainLuck/1.0 (https://bainluck.com; bain@bainluck.com)"},
        ) as client:
            r = await client.get(WIKI_API, params=params)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                thumb = page.get("thumbnail", {}).get("source")
                if thumb:
                    return thumb
    except Exception as e:
        logger.warning("Wikipedia image fetch failed for %s: %s", name, e)
    return None


# Lookup overrides for wrestlers whose Wikipedia page title differs from display name
WIKI_NAME_OVERRIDES = {
    "Penta": "Penta El Zero Miedo",
    "Gunther": "Gunther (wrestler)",
    "IShowSpeed": "IShowSpeed",
    "LA Knight": "LA Knight",
    "Rusev": "Rusev (wrestler)",
    "Oba Femi": "Oba Femi",
    "Trick Williams": "Trick Williams",
    "Je'Von Evans": "Je'Von Evans",
    "Dragon Lee": "Dragon Lee (wrestler)",
    "JD McDonagh": "JD McDonagh",
    "Nikki": "Nikki Bella",
}


async def resolve_wrestler_image(name: str) -> Optional[str]:
    wiki_name = WIKI_NAME_OVERRIDES.get(name, name)
    url = await fetch_wikipedia_thumbnail(wiki_name)
    if not url and wiki_name == name:
        url = await fetch_wikipedia_thumbnail(f"{name} (wrestler)")
    return url
