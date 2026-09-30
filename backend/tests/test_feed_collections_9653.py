"""Published hubs compete with visible games without losing pagination cards."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes.feed import _rank_key
from app.services import container_discovery as producer
from app.utils import feed_collections as consumer
from app.utils.feed_cache import feed_edition_token


@pytest.fixture
def card():
    path = (
        Path(__file__).parent / "fixtures/container_discovery_9653/search_by_games.json"
    )
    return json.loads(path.read_text())["response"]["collections"][0]


def event(id, score):
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 1,
        "reason": "Game",
        "headline": None,
        "data": {"id": id},
    }


@pytest.mark.parametrize(
    "discovery,hub", [(False, False), (False, True), (True, False)]
)
def test_either_disabled_flag_preserves_ordinary_feed(monkeypatch, discovery, hub):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", str(discovery))
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", str(hub))
    assert not consumer.feed_collections_enabled(
        mode=None, include_events=True, my_teams_only=False
    )


@pytest.mark.parametrize(
    "shape",
    [
        {"mode": "sports"},
        {"include_events": False},
        {"my_teams_only": True},
        {"debug": True},
    ],
)
def test_other_surfaces_do_not_offer_collections(monkeypatch, shape):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    request = {"mode": None, "include_events": True, "my_teams_only": False}
    assert consumer.feed_collections_enabled(**request)
    request.update(shape)
    assert not consumer.feed_collections_enabled(**request)


async def test_no_visible_game_or_spent_budget_performs_no_read(monkeypatch):
    read = AsyncMock()
    monkeypatch.setattr(producer, "discover_collections", read)
    db = AsyncMock()
    for items, budget in [([], 0.25), ([event(501, 40)], 0)]:
        assert (
            await consumer.add_feed_collections(
                db, items, rank_key=_rank_key, budget_seconds=budget
            )
            is items
        )
    read.assert_not_awaited()
    db.rollback.assert_not_awaited()


async def test_only_canonical_page_games_supply_relevance(monkeypatch, card):
    # The twenty-card page is the existing composition window, independent of
    # caller limit/offset. A game only in the tail cannot introduce a hub.
    items = (
        [event(501, 50)]
        + [{"type": "futures", "score": 40, "data": {"id": i}} for i in range(19)]
        + [event(999, 30)]
    )
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    result = await consumer.add_feed_collections(AsyncMock(), items, rank_key=_rank_key)
    assert list(read.await_args.kwargs["event_ids"]) == [501]
    assert len(result) == len(items) + 1


async def test_card_competes_without_a_slot_or_score_bonus(monkeypatch, card):
    items = [event(100, 95), event(101, 90), event(501, 35), event(102, 20)]
    before = copy.deepcopy(items)
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    result = await consumer.add_feed_collections(AsyncMock(), items, rank_key=_rank_key)
    assert all(item["type"] == "event" for item in result[:2])
    offered = next(item for item in result if item["type"] == "collection")
    assert offered["score"] == offered["_rank_score"] == 35
    assert offered["data"] == card  # exact producer identity + destination
    assert [item for item in result if item["type"] != "collection"] == before
    assert items == before  # no mutation of shared scoring artifacts

    pages = [result[offset : offset + 2] for offset in range(0, len(result), 2)]
    assert [item for page in pages for item in page] == result
    assert {
        item["data"]["id"] for page in pages for item in page if item["type"] == "event"
    } == {100, 101, 501, 102}
    assert feed_edition_token(result) != feed_edition_token(items)


async def test_a_card_without_a_visible_member_is_not_offered(monkeypatch, card):
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    items = [event(999, 80)]
    assert (
        await consumer.add_feed_collections(AsyncMock(), items, rank_key=_rank_key)
        is items
    )


async def test_revocation_is_seen_on_the_next_read(monkeypatch, card):
    read = AsyncMock(
        side_effect=[
            SimpleNamespace(collections=[card]),
            SimpleNamespace(collections=[]),
        ]
    )
    monkeypatch.setattr(producer, "discover_collections", read)
    items = [event(501, 40)]
    assert (
        len(await consumer.add_feed_collections(AsyncMock(), items, rank_key=_rank_key))
        == 2
    )
    assert (
        await consumer.add_feed_collections(AsyncMock(), items, rank_key=_rank_key)
        is items
    )
    assert read.await_count == 2


@pytest.mark.parametrize("failure", ["timeout", "database"])
async def test_failed_optional_read_preserves_ordinary_feed(monkeypatch, failure):
    async def fail(*args, **kwargs):
        if failure == "timeout":
            await asyncio.Event().wait()
        raise RuntimeError("query failed")

    monkeypatch.setattr(producer, "discover_collections", fail)
    db = AsyncMock()
    items = [event(501, 40)]
    assert (
        await consumer.add_feed_collections(
            db, items, rank_key=_rank_key, budget_seconds=0.001
        )
        is items
    )
    db.rollback.assert_awaited_once()
