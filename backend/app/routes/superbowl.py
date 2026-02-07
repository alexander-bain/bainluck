"""Super Bowl commercials API endpoints."""

from typing import Optional

from fastapi import APIRouter, Query

from app.services.youtube_api import YouTubeAPIService

router = APIRouter()

# Default search queries for Super Bowl commercials
DEFAULT_QUERY = "Super Bowl 2026 commercial"
# Only show videos published after Jan 1, 2026
PUBLISHED_AFTER = "2026-01-01T00:00:00Z"


def _format_view_count(count: int) -> str:
    """Format view count for display (e.g., 1.2M, 450K)."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.0f}K"
    return str(count)


@router.get("/commercials")
async def get_superbowl_commercials(
    q: Optional[str] = Query(
        None,
        description="Custom search query (defaults to Super Bowl commercial search)",
    ),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
):
    """Get Super Bowl commercials ranked by YouTube view count.

    Returns videos sorted by view count, which serves as a proxy for
    commercial buzz/popularity during the Super Bowl.
    """
    query = q or DEFAULT_QUERY
    service = YouTubeAPIService()
    try:
        videos = await service.search_videos(
            query=query,
            max_results=limit,
            order="viewCount",
            published_after=PUBLISHED_AFTER,
        )

        ranked = []
        for i, video in enumerate(videos):
            ranked.append(
                {
                    "rank": i + 1,
                    "video_id": video["video_id"],
                    "title": video["title"],
                    "brand": video["channel"],
                    "thumbnail": video["thumbnail"],
                    "view_count": video["view_count"],
                    "view_count_display": _format_view_count(video["view_count"]),
                    "like_count": video["like_count"],
                    "published_at": video["published_at"],
                    "youtube_url": f"https://www.youtube.com/watch?v={video['video_id']}",
                }
            )

        return {
            "query": query,
            "total": len(ranked),
            "commercials": ranked,
        }
    finally:
        await service.close()
