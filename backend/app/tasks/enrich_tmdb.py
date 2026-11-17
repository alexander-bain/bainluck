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
from app.utils.image_dimensions import tmdb_declared_width
from app.utils.music_image_guard import (
    is_music_market_ineligible_for_tmdb,
    sanitize_market_image_url,
)

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"
TVMAZE_SINGLE_SEARCH = "https://api.tvmaze.com/singlesearch/shows"
TMDB_READ_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN")  # v4 bearer (preferred)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # v3 key (fallback)

_TV_SERIES_HINT_RE = re.compile(
    r"\b(episode|season\s+\d+|tv\s+series|limited\s+series|netflix\s+(?:show|series)|emmys?)\b",
    re.IGNORECASE,
)

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


def _pick_tvmaze_image(
    payload: dict | None,
    expected_title: str | None = None,
) -> tuple[str | None, dict | None]:
    """Extract a kid-safe (#7461) CC BY-SA 4.0 portrait poster from TVMaze."""
    if not isinstance(payload, dict):
        return None, None
    if expected_title is not None:
        want = _normalize_title(expected_title)
        got = _normalize_title(str(payload.get("name") or ""))
        if not want or got != want:
            return None, None
    genres = [str(g).strip().lower() for g in (payload.get("genres") or [])]
    if "horror" in genres:
        return None, None
    img_obj = payload.get("image") or {}
    if not isinstance(img_obj, dict):
        return None, None
    img_url = str(img_obj.get("original") or img_obj.get("medium") or "").strip()
    if not img_url.startswith("https://static.tvmaze.com/"):
        return None, None
    source_page = str(payload.get("url") or "").strip()
    if not source_page.startswith("https://www.tvmaze.com/"):
        return None, None
    return img_url, {
        "tvmaze_id": payload.get("id"),
        "name": payload.get("name"),
        "genres": payload.get("genres") or [],
        "source_page": source_page,
        "author": "TVMaze contributors",
        "license": "CC BY-SA 4.0",
    }


async def _fetch_tvmaze_image(title: str) -> tuple[str | None, dict | None]:
    """Query key-free TVMaze API for a TV series portrait poster (CC BY-SA 4.0)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(TVMAZE_SINGLE_SEARCH, params={"q": title})
            if resp.status_code != 200:
                return None, None
            return _pick_tvmaze_image(resp.json(), expected_title=title)
    except Exception as e:  # noqa: BLE001
        logger.error("TVMaze fetch error for %r: %s", title, e)
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

    stats = {
        "checked": 0,
        "found": 0,
        "no_match": 0,
        "skipped_no_title": 0,
        "skipped_music": 0,
        "cleared_music_false_positives": 0,
        "found_tvmaze": 0,
    }

    async with get_task_session() as session:
        # #12659: clear any previously attached TMDB film backdrops on music/song/
        # album/chart markets across all categories via keyset pagination so stored
        # rows match serve-time withholding in discover_image_policy.py.
        cleanup_batch_size = 500
        last_seen_id = 0
        while True:
            existing_tmdb_result = await session.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.name,
                    FuturesMarket.image_url,
                    FuturesMarket.market_metadata,
                )
                .where(
                    FuturesMarket.status == "open",
                    FuturesMarket.id > last_seen_id,
                    FuturesMarket.image_url.like("%image.tmdb.org%"),
                )
                .order_by(FuturesMarket.id.asc())
                .limit(cleanup_batch_size)
            )
            batch = existing_tmdb_result.all()
            if not batch:
                break
            for m_id, m_name, m_img, m_meta in batch:
                last_seen_id = int(m_id)
                if m_img and sanitize_market_image_url(m_img, m_name) is None:
                    clean_meta = m_meta if isinstance(m_meta, dict) else {}
                    await session.execute(
                        update(FuturesMarket)
                        .where(FuturesMarket.id == m_id)
                        .values(
                            image_url=None,
                            image_width=None,
                            image_height=None,
                            market_metadata={
                                **clean_meta,
                                "tmdb": {"skipped_music": True},
                            },
                        )
                    )
                    stats["cleared_music_false_positives"] += 1
            if len(batch) < cleanup_batch_size:
                break

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
            if is_music_market_ineligible_for_tmdb(name):
                stats["skipped_music"] += 1
                await session.execute(
                    update(FuturesMarket)
                    .where(FuturesMarket.id == market_id)
                    .values(
                        market_metadata={**meta, "tmdb": {"skipped_music": True}}
                    )
                )
                continue
            title = _extract_quoted_title(name)
            if not title:
                stats["skipped_no_title"] += 1
                continue

            stats["checked"] += 1
            url, tmeta = await _fetch_tmdb_image(title)
            tvmaze_meta = None
            if not url and _TV_SERIES_HINT_RE.search(name or ""):
                url, tvmaze_meta = await _fetch_tvmaze_image(title)

            next_meta = {**meta, "tmdb": tmeta or {"no_match": True}}
            if tvmaze_meta:
                next_meta["tvmaze"] = tvmaze_meta
            values: dict = {"market_metadata": next_meta}
            if url:
                values["image_url"] = url
                values["image_width"] = tmdb_declared_width(url)
                values["image_height"] = None
                stats["found"] += 1
                if tvmaze_meta:
                    stats["found_tvmaze"] += 1
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
