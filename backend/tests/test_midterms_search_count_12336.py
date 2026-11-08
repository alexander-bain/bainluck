"""The admitted Midterms page owns the count advertised by search."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import containers
from app.services.container_discovery import DiscoveryRead
from app.utils import search_collections as search


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(search, "search_collections_enabled", lambda: True)
    monkeypatch.setattr(
        search, "_attach_theme_family_refs", AsyncMock(side_effect=lambda p: p)
    )
    monkeypatch.setattr("app.utils.roundup_containers.ROUNDUP_PRODUCERS", {})


def heading(slug="midterms-2026"):
    return {"slug": slug, "question_count": 15, "game_count": 0, "revision": 1}


@pytest.mark.parametrize("count", [14, 13, 1])
async def test_search_uses_the_current_page_count_and_revision(
    enabled, monkeypatch, count
):
    stored = heading()
    monkeypatch.setattr(
        search.container_discovery,
        "discover_collections",
        AsyncMock(return_value=DiscoveryRead(collections=[stored])),
    )
    page = AsyncMock(
        return_value={"state": "published", "member_count": count, "revision": 3}
    )
    monkeypatch.setattr(containers, "get_container", page)
    db = SimpleNamespace(rollback=AsyncMock())
    result = await search.attach_search_collections(db, {"query": "midterms"})
    assert result["collections"][0]["question_count"] == count
    assert result["collections"][0]["revision"] == 3
    assert stored["question_count"] == 15
    page.assert_awaited_once_with("midterms-2026", db=db)


@pytest.mark.parametrize("state,count", [("withdrawn", 14), ("published", 0)])
async def test_unavailable_or_empty_page_cannot_advertise_a_count(
    enabled, monkeypatch, state, count
):
    monkeypatch.setattr(
        search.container_discovery,
        "discover_collections",
        AsyncMock(return_value=DiscoveryRead(collections=[heading()])),
    )
    monkeypatch.setattr(
        containers,
        "get_container",
        AsyncMock(return_value={"state": state, "member_count": count}),
    )
    payload = {"query": "midterms", "futures": [{"id": 1}]}
    result = await search.attach_search_collections(SimpleNamespace(), payload)
    assert result is payload


@pytest.mark.parametrize("midterms_first", [False, True])
async def test_page_failure_keeps_completed_healthy_cards_and_marks_degradation(
    enabled, monkeypatch, midterms_first
):
    healthy = heading("nfl-2026-week-9")
    monkeypatch.setattr(
        search.container_discovery,
        "discover_collections",
        AsyncMock(
            return_value=DiscoveryRead(
                collections=[heading(), healthy]
                if midterms_first
                else [healthy, heading()]
            )
        ),
    )
    monkeypatch.setattr(
        containers, "get_container", AsyncMock(side_effect=RuntimeError("read failed"))
    )
    db = SimpleNamespace(rollback=AsyncMock())
    result = await search.attach_search_collections(db, {"query": "midterms"})
    assert result["collections"] == [healthy]
    assert result["degraded"] == ["collections"]
    db.rollback.assert_awaited_once()


async def test_page_read_uses_the_existing_search_deadline(enabled, monkeypatch):
    monkeypatch.setattr(
        search.container_discovery,
        "discover_collections",
        AsyncMock(return_value=DiscoveryRead(collections=[heading()])),
    )

    async def slow_page(*args, **kwargs):
        await asyncio.sleep(1)

    page = AsyncMock(side_effect=slow_page)
    monkeypatch.setattr(containers, "get_container", page)
    db = SimpleNamespace(rollback=AsyncMock())
    result = await search.attach_search_collections(
        db, {"query": "midterms"}, budget_seconds=0.01
    )
    assert "collections" not in result
    assert result["degraded"] == ["collections"]


async def test_typeahead_headings_do_not_add_a_count_read(enabled, monkeypatch):
    monkeypatch.setattr(
        search.container_discovery,
        "discover_collections",
        AsyncMock(return_value=DiscoveryRead(collections=[heading()])),
    )
    page = AsyncMock()
    monkeypatch.setattr(containers, "get_container", page)
    await search.attach_search_collections(
        SimpleNamespace(), {"query": "midterms"}, titles_only=True
    )
    page.assert_not_awaited()
