"""YouTube Data API v3 integration for Super Bowl commercial tracking."""

import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Cache: (timestamp, results)
_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_TTL = 300  # 5 minutes


class YouTubeAPIService:
    """Service for searching YouTube videos via the Data API v3."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def search_videos(
        self,
        query: str,
        max_results: int = 25,
        order: str = "viewCount",
        published_after: Optional[str] = None,
    ) -> list[dict]:
        """Search YouTube for videos and return ranked results.

        Args:
            query: Search query string
            max_results: Max videos to return (max 50 per API call)
            order: Sort order - viewCount, date, relevance, rating
            published_after: ISO 8601 datetime filter (e.g., "2026-01-01T00:00:00Z")

        Returns:
            List of video dicts with id, title, channel, thumbnails, view_count, etc.
        """
        if not self.api_key:
            logger.warning("YOUTUBE_API_KEY not set")
            return []

        # Check cache
        cache_key = f"{query}:{max_results}:{order}:{published_after}"
        if cache_key in _cache:
            cached_time, cached_results = _cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                logger.info(f"YouTube cache hit for '{query}'")
                return cached_results

        try:
            # Step 1: Search for videos
            search_params = {
                "key": self.api_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "maxResults": min(max_results, 50),
                "order": order,
            }
            if published_after:
                search_params["publishedAfter"] = published_after

            resp = await self.client.get(
                f"{self.BASE_URL}/search", params=search_params
            )
            resp.raise_for_status()
            search_data = resp.json()

            video_ids = [
                item["id"]["videoId"]
                for item in search_data.get("items", [])
                if item.get("id", {}).get("videoId")
            ]

            if not video_ids:
                return []

            # Step 2: Get video statistics (view counts)
            stats_resp = await self.client.get(
                f"{self.BASE_URL}/videos",
                params={
                    "key": self.api_key,
                    "id": ",".join(video_ids),
                    "part": "statistics,snippet,contentDetails",
                },
            )
            stats_resp.raise_for_status()
            stats_data = stats_resp.json()

            # Build results
            results = []
            for item in stats_data.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                thumbnails = snippet.get("thumbnails", {})

                # Pick best thumbnail
                thumb = (
                    thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                    or ""
                )

                results.append(
                    {
                        "video_id": item["id"],
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("channelTitle", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "thumbnail": thumb,
                        "view_count": int(stats.get("viewCount", 0)),
                        "like_count": int(stats.get("likeCount", 0)),
                        "comment_count": int(stats.get("commentCount", 0)),
                    }
                )

            # Sort by view count descending
            results.sort(key=lambda x: x["view_count"], reverse=True)

            # Cache results
            _cache[cache_key] = (time.time(), results)
            logger.info(
                f"YouTube: found {len(results)} videos for '{query}'"
            )
            return results

        except httpx.HTTPStatusError as e:
            logger.error(f"YouTube API error: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return []
