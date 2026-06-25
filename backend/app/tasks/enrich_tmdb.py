"""#882 slice 1: server-side TMDB imagery for entertainment markets.

Discover entertainment cards default to generic Pexels stock. For markets whose
subject is a specific movie/TV title, TMDB has the real poster/backdrop. This
enriches ONLY high-confidence single-title markets — the title in QUOTES (e.g.
'"Toy Story 5" Rotten Tomatoes score?') — because most entertainment markets are
awards categories / reality / music where a blanket TMDB lookup would attach the
WRONG artwork (worse than a generic image). Quoted extraction + a TMDB match
that actually returns a movie/TV result with art is the false-positive-safe gate.

Async, cached via a market_metadata['tmdb'] marker (anti-thrash), rate-limited.
"""

from __future__ import annotations

import os
import re
import asyncio
import logging

import httpx
from sqlalchemy import select, update

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"
TMDB_READ_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN")  # v4 bearer (preferred)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # v3 key (fallback)

# A quoted title: "Toy Story 5" / “The Odyssey”. 2–80 chars, no nested quotes.
_QUOTED_TITLE_RE = re.compile(r'["“]([^"”]{2,80})["”]')


def _extract_quoted_title(name: str | None) -> str | None:
    """Return the quoted title in a market name, or None. Reliable, false-positive
    -safe: only markets that explicitly quote a title qualify."""
    if not name:
        return None
    m = _QUOTED_TITLE_RE.search(name)
    if not m:
        return None
    title = m.group(1).strip()
    return title or None


def _pick_tmdb_image(results: list[dict]) -> tuple[str | None, dict | None]:
    """From TMDB /search/multi results, pick the best movie/TV match with art.

    Prefers a landscape backdrop (matches the card aspect Pexels filled); falls
    back to the portrait poster. Returns (image_url, metadata) or (None, None)
    when no movie/TV result has usable art.
    """
    for r in results or []:
        if r.get("media_type") not in ("movie", "tv"):
            continue
        backdrop = r.get("backdrop_path")
        poster = r.get("poster_path")
        path = backdrop or poster
        if not path:
            continue
        size = "w1280" if backdrop else "w780"
        url = f"{TMDB_IMG}/{size}{path}"
        meta = {
            "tmdb_id": r.get("id"),
            "media_type": r.get("media_type"),
            "title": r.get("title") or r.get("name"),
            "poster_path": poster,
            "backdrop_path": backdrop,
        }
        return url, meta
    return None, None


async def _fetch_tmdb_image(title: str) -> tuple[str | None, dict | None]:
    """Search TMDB for a title and return (image_url, metadata) for the best
    movie/TV match, or (None, None)."""
    if not (TMDB_READ_TOKEN or TMDB_API_KEY):
        return None, None
    headers = {}
    params: dict = {"query": title, "include_adult": "false"}
    if TMDB_READ_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"
    else:
        params["api_key"] = TMDB_API_KEY
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{TMDB_BASE}/search/multi", params=params, headers=headers
            )
            if resp.status_code != 200:
                logger.warning("TMDB returned %d for %r", resp.status_code, title)
                return None, None
            return _pick_tmdb_image(resp.json().get("results", []))
    except Exception as e:  # noqa: BLE001
        logger.error("TMDB fetch error for %r: %s", title, e)
        return None, None


def _normalize_title(title: str | None) -> str:
    """Normalize a title for trending-set matching: lowercase, alnum-only."""
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


async def _fetch_tmdb_trending() -> set[str]:
    """Return the set of normalized currently-trending movie + TV titles (week).

    Used by #882 slice 4 (interestingness boost). Empty set on any failure /
    missing creds — a no-op, never an error.
    """
    if not (TMDB_READ_TOKEN or TMDB_API_KEY):
        return set()
    headers = {}
    base_params: dict = {}
    if TMDB_READ_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"
    else:
        base_params["api_key"] = TMDB_API_KEY
    titles: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for media in ("movie", "tv"):
                resp = await client.get(
                    f"{TMDB_BASE}/trending/{media}/week",
                    params=base_params,
                    headers=headers,
                )
                if resp.status_code != 200:
                    continue
                for r in resp.json().get("results", []):
                    norm = _normalize_title(r.get("title") or r.get("name"))
                    if len(norm) >= 3:  # skip ultra-short/ambiguous titles
                        titles.add(norm)
    except Exception as e:  # noqa: BLE001
        logger.error("TMDB trending fetch error: %s", e)
        return set()
    return titles


# #882 slice 3: Apple/iTunes "most-played" RSS — key-free music charts. The
# legacy rss.applemarketingtools.com host 301-redirects to this one; httpx does
# not auto-follow, so hit the final host directly.
_MUSIC_CHARTS_BASE = "https://rss.marketingtools.apple.com/api/v2/us/music/most-played"


async def _fetch_music_charts() -> set[str]:
    """Return normalized currently-charting music titles (track + album names and
    artist names) from Apple's free RSS. Empty set on any failure — a no-op."""
    titles: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for kind in ("songs", "albums"):
                resp = await client.get(f"{_MUSIC_CHARTS_BASE}/50/{kind}.json")
                if resp.status_code != 200:
                    continue
                for r in resp.json().get("feed", {}).get("results", []):
                    for raw in (r.get("name"), r.get("artistName")):
                        norm = _normalize_title(raw)
                        if len(norm) >= 4:  # skip ultra-short/ambiguous
                            titles.add(norm)
    except Exception as e:  # noqa: BLE001
        logger.error("Apple music charts fetch error: %s", e)
        return set()
    return titles


async def enrich_tmdb_images(limit: int = 50):
    """Enrich quoted-title entertainment markets with real TMDB artwork."""
    from app.models.models import FuturesMarket

    if not (TMDB_READ_TOKEN or TMDB_API_KEY):
        logger.info("TMDB credentials not set — skipping TMDB enrichment")
        return {"skipped": True}

    stats = {"checked": 0, "found": 0, "no_match": 0, "skipped_no_title": 0}

    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.market_metadata,
            )
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.llm_sport_category == "entertainment",
                FuturesMarket.name.like('%"%'),  # has a quoted title
            )
            .order_by(FuturesMarket.volume_24h.desc().nullslast())
            .limit(limit)
        )
        rows = result.all()

        for market_id, name, meta in rows:
            meta = meta if isinstance(meta, dict) else {}
            if meta.get("tmdb"):  # already TMDB-checked (anti-thrash)
                continue
            title = _extract_quoted_title(name)
            if not title:
                stats["skipped_no_title"] += 1
                continue

            stats["checked"] += 1
            url, tmeta = await _fetch_tmdb_image(title)

            values: dict = {
                "market_metadata": {**meta, "tmdb": tmeta or {"no_match": True}}
            }
            if url:
                # Prefer real TMDB art over the generic Pexels stock image.
                values["image_url"] = url
                stats["found"] += 1
            else:
                stats["no_match"] += 1

            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == market_id)
                .values(**values)
            )
            await asyncio.sleep(0.3)

        await session.commit()

    logger.info("TMDB enrichment: %s", stats)
    return stats
