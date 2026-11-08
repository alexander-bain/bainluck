"""A ceremony's existing market cards and its page share discovered membership."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.routes import containers as route
from app.utils import roundup_containers as roundups
from app.utils.awards_ceremony import build_awards_ceremony_producer
from app.utils.awards_occasion_finder import find_awards_occasions


def discovery(*tickers, label="17th New Film Awards", title="Best Screenplay"):
    return find_awards_occasions(
        [
            {
                "provider": "kalshi",
                "event_ticker": ticker,
                "title": title,
                "markets": [
                    {"rules_primary": f"If the film wins at the {label}, Yes."}
                ],
            }
            for ticker in tickers
        ]
    )


def card(market_id, *, status="open", probability=0.88, winner=None):
    return {
        "id": market_id,
        "name": "A venue category",
        "status": status,
        "source": "kalshi",
        "outcome_count": 2,
        "top_outcomes": [
            {
                "id": market_id * 10,
                "name": "Film A",
                "probability": probability,
                "is_winner": winner,
                "resolution_source": "api_settlement" if winner is not None else None,
            },
            {
                "id": market_id * 10 + 1,
                "name": "Film B",
                "probability": 0.72,
                "is_winner": None,
                "resolution_source": None,
            },
        ],
    }


@pytest.fixture(autouse=True)
def cache_off(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    roundups.reset_roundup_cache_for_tests()
    yield
    roundups.reset_roundup_cache_for_tests()


def setup_members(monkeypatch, found, *, ids=(10, 11)):
    events = found.occasions[0].events
    facts = [
        (market_id, event.provider, event.event_id, False)
        for market_id, event in zip(ids, events)
    ]
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: facts))
    )
    cards = {market_id: card(market_id) for market_id, *_ in facts}
    hydrate = AsyncMock(return_value=(cards, {}, {}))
    monkeypatch.setattr(route, "_hydrate_market_cards", hydrate)

    async def load(db):
        return found

    producer = build_awards_ceremony_producer(
        found.occasions[0].selector, load_occasions=load
    )
    return producer, db, cards, hydrate


async def test_a_new_ceremony_and_its_venue_sections_use_the_same_set(monkeypatch):
    found = discovery("KXNEW-DIR42", "KXNEW-SCR42")
    producer, db, cards, hydrate = setup_members(monkeypatch, found)
    members = await producer.produce(db)
    page = roundups.compose_roundup_container(producer, members)
    feed = roundups.compose_roundup_feed_item(producer, members)

    assert producer.slug == "roundup-awards-17th-new-film-awards"
    assert page["container"]["name"] == "17th New Film Awards"
    assert page["subtitle"] == "Ceremony date unknown · Completion unknown"
    assert page["container"]["window_start"] is page["container"]["window_end"] is None
    assert [section["title"] for section in page["sections"]] == ["Best Screenplay"] * 2
    page_ids = [
        member["id"] for section in page["sections"] for member in section["members"]
    ]
    assert page_ids == feed["data"]["member_ids"] == [10, 11]
    assert feed["data"]["kind"] == "theme"
    assert [item["data"]["id"] for item in feed["data"]["items"]] == page_ids
    assert feed["data"]["collection_ref"]["href"] == "/collections/" + producer.slug
    assert (
        feed["data"]["collection_ref"]["collection_count"] == page["member_count"] == 2
    )
    assert (
        page["sections"][0]["members"][0]["card"]["top_outcomes"]
        == cards[10]["top_outcomes"]
    )
    assert sum(row["probability"] for row in cards[10]["top_outcomes"]) == 1.6
    assert page["sections"][0]["members"][0]["card"]["mutually_exclusive"] is False
    hydrate.assert_awaited_once_with(db, [10, 11])
    sql = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "kalshi_event_ticker" in sql and "polymarket_event_id" in sql
    assert "ILIKE" not in sql and "New Film Awards" not in sql


async def test_the_normal_http_entrypoint_serves_the_shared_ceremony_payload(
    monkeypatch,
):
    found = discovery("KXNEW-SCR42")
    producer, db, _, _ = setup_members(monkeypatch, found)
    monkeypatch.setitem(roundups.ROUNDUP_PRODUCERS, producer.slug, producer)
    app = FastAPI()

    async def database():
        yield db

    app.dependency_overrides[route.get_db] = database
    app.include_router(route.router, prefix="/api/containers")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        response = await client.get("/api/containers/" + producer.slug)
    assert response.status_code == 200
    assert response.json()["member_count"] == 1
    assert response.json()["sections"][0]["members"][0]["id"] == 10


async def test_a_new_category_joins_the_existing_selector_and_both_presentations(
    monkeypatch,
):
    current = [discovery("KXNEW-SCR42")]
    ids = {"KXNEW-SCR42": 10, "KXNEW-DIR42": 11}

    async def execute(statement):
        facts = [
            (ids[event.event_id], event.provider, event.event_id, False)
            for event in current[0].occasions[0].events
        ]
        return SimpleNamespace(all=lambda: facts)

    db = SimpleNamespace(execute=execute)

    async def hydrate(db, market_ids):
        return {market_id: card(market_id) for market_id in market_ids}, {}, {}

    monkeypatch.setattr(route, "_hydrate_market_cards", hydrate)

    async def load(db):
        return current[0]

    producer = build_awards_ceremony_producer(
        current[0].occasions[0].selector, load_occasions=load
    )
    original = roundups.compose_roundup_container(producer, await producer.produce(db))
    current[0] = discovery("KXNEW-SCR42", "KXNEW-DIR42")
    updated_members = await producer.produce(db)
    updated = roundups.compose_roundup_container(producer, updated_members)
    feed = roundups.compose_roundup_feed_item(producer, updated_members)

    assert original["member_count"] == 1
    assert original["slug"] == updated["slug"]
    assert updated["revision"] != original["revision"]
    assert updated["member_count"] == feed["data"]["item_count"] == 2
    page_ids = {
        member["id"] for section in updated["sections"] for member in section["members"]
    }
    assert page_ids == set(feed["data"]["member_ids"]) == {10, 11}


@pytest.mark.parametrize(
    "status,probability,winner",
    [
        ("open", None, None),
        ("resolved", 1.0, True),
        ("open", 1.0, True),
    ],
)
async def test_unpriced_and_settled_member_semantics_stay_with_the_shared_card(
    monkeypatch,
    status,
    probability,
    winner,
):
    found = discovery("KXNEW-SCR42")
    producer, db, cards, hydrate = setup_members(monkeypatch, found)
    cards[10] = card(10, status=status, probability=probability, winner=winner)
    hydrate.return_value = (cards, {}, {})
    members = await producer.produce(db)
    page = roundups.compose_roundup_container(producer, members)
    shown = page["sections"][0]["members"][0]["card"]
    assert shown["status"] == status
    assert shown["top_outcomes"] == cards[10]["top_outcomes"]


async def test_a_missing_stored_category_refuses_with_its_identity(monkeypatch):
    found = discovery("KXNEW-DIR42", "KXNEW-SCR42")
    producer, db, _, hydrate = setup_members(monkeypatch, found, ids=(10,))
    result = await producer.produce(db)
    assert isinstance(result, roundups.RoundupRefusal)
    assert result.reasons == (("kalshi", "KXNEW-SCR42", "stored_category_missing"),)
    hydrate.assert_not_awaited()


async def test_a_failed_card_cannot_turn_into_an_empty_success(monkeypatch):
    producer, db, _, hydrate = setup_members(monkeypatch, discovery("KXNEW-SCR42"))
    hydrate.return_value = ({}, {}, {("market", 10): "unserializable"})
    result = await producer.produce(db)
    assert isinstance(result, roundups.RoundupRefusal)
    assert result.reasons == (("market", 10, "card_unavailable"),)


async def test_missing_category_text_stays_unknown(monkeypatch):
    found = discovery("KXNEW-SCR42", title="")
    producer, db, _, _ = setup_members(monkeypatch, found)
    members = await producer.produce(db)
    assert members.sections[0]["title"] == "Category unknown"


async def test_missing_or_empty_ceremony_evidence_refuses_before_market_reads(
    monkeypatch,
):
    found = discovery("KXNEW-SCR42")
    producer, db, _, hydrate = setup_members(monkeypatch, found)
    selector = found.occasions[0].selector

    async def absent(db):
        return replace(found, occasions=())

    missing = build_awards_ceremony_producer(selector, load_occasions=absent)
    assert isinstance(await missing.produce(db), roundups.RoundupRefusal)

    async def empty(db):
        return replace(found, occasions=(replace(found.occasions[0], events=()),))

    empty_producer = build_awards_ceremony_producer(selector, load_occasions=empty)
    assert isinstance(await empty_producer.produce(db), roundups.RoundupRefusal)
    db.execute.assert_not_awaited()
    hydrate.assert_not_awaited()


def test_conflicting_venue_category_titles_refuse_deterministically():
    first = {
        "provider": "kalshi",
        "event_ticker": "KXNEW-SCR42",
        "title": "Best Screenplay",
        "markets": [{"rules_primary": "At the 17th New Film Awards."}],
    }
    second = {**first, "title": "Best Director"}
    assert find_awards_occasions([first, second]) == find_awards_occasions(
        [second, first]
    )
    assert find_awards_occasions([first, second]).refused == (
        ("kalshi", "KXNEW-SCR42", "conflicting_event_title"),
    )
