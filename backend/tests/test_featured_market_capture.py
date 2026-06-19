"""#964: capture_featured_markets crashed every run with
`type object 'FuturesMarket' has no attribute 'url'` — the select referenced a
non-existent column. FuturesMarket's image column is `image_url`. Guard against
re-introducing a bad attribute on the capture selects.
"""

import inspect

import pytest

from app.models.models import FuturesMarket
from app.utils import featured_market_capture as fmc


def test_futuresmarket_has_image_url_not_url():
    assert hasattr(FuturesMarket, "image_url")
    assert not hasattr(FuturesMarket, "url"), "FuturesMarket.url does not exist — the #964 crash"


def test_capture_selects_use_image_url_not_bare_url():
    src = inspect.getsource(fmc)
    assert "FuturesMarket.url," not in src, "stale FuturesMarket.url reference reintroduced (#964)"
    assert src.count("FuturesMarket.image_url,") >= 2  # kalshi + polymarket selects


class _Result:
    def all(self):
        return []


class _FakeSession:
    """Minimal async session — building/executing the capture select must not
    raise the AttributeError (it would if the select referenced FuturesMarket.url)."""

    async def execute(self, stmt):
        # touching str(stmt) forces SQLAlchemy to resolve the selected columns,
        # which raised AttributeError before the fix.
        str(stmt.compile())
        return _Result()


@pytest.mark.asyncio
async def test_capture_kalshi_featured_does_not_raise_attribute_error():
    stats = await fmc.capture_kalshi_featured(_FakeSession())
    assert stats["captured"] == 0 and stats["skipped"] == 0


@pytest.mark.asyncio
async def test_capture_polymarket_featured_does_not_raise_attribute_error():
    stats = await fmc.capture_polymarket_featured(_FakeSession())
    assert stats["captured"] == 0
