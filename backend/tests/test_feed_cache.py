import pytest

from app.tasks import redis_state
from app.utils.feed_cache import (
    FEED_RESPONSE_STALE_TTL_SECONDS,
    build_feed_cache_metadata,
    invalidate_feed_response_cache,
)


class _FakeAsyncRedis:
    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        self.deleted: list[str] = []
        self.closed = False

    async def scan_iter(self, match: str, count: int = 100):
        assert match == "feed_cache:*"
        assert count == 100
        for key in list(self.keys):
            if key.startswith("feed_cache:"):
                yield key

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)

    async def aclose(self) -> None:
        self.closed = True


def test_build_feed_cache_metadata_exposes_stable_fields():
    assert build_feed_cache_metadata("miss", ttl_seconds=60) == {
        "status": "miss",
        "ttl_seconds": 60,
        "stale_ttl_seconds": FEED_RESPONSE_STALE_TTL_SECONDS,
    }


@pytest.mark.asyncio
async def test_invalidate_feed_response_cache_deletes_fresh_and_stale_keys(
    monkeypatch,
):
    fake = _FakeAsyncRedis(
        [
            "feed_cache:fresh",
            "feed_cache:fresh:stale",
            "other_cache:key",
        ]
    )
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: fake)

    result = await invalidate_feed_response_cache("test")

    assert result == {"status": "ok", "deleted": 2, "reason": "test"}
    assert fake.deleted == ["feed_cache:fresh", "feed_cache:fresh:stale"]
    assert fake.closed is True
