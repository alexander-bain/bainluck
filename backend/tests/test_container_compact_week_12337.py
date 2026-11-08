"""An NFL week opens with games and accounted-for linked-market summaries."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.routes import containers as route
from app.utils.container_presentation import compact_related_members
from tests.test_container_hydrated_reader_9636 import _Result, _Session, _market, _nfl_week


class CompactSession(_Session):
    async def execute(self, sql, params=None):
        statement = str(sql)
        if statement.startswith("SELECT id, event_id FROM futures_markets"):
            self.statements.append(statement)
            ids = set(params["market_ids"])
            return _Result((market.id, market.event_id) for market in self.markets if market.id in ids)
        if statement.startswith("SELECT futures_markets.") and "WHERE futures_markets.id IN" in statement:
            self.statements.append(statement)
            ids = set(sql.compile().params["id_1"])
            return _Result(market for market in self.markets if market.id in ids)
        return await super().execute(sql, params)


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")


def long_week():
    hub, events, markets = _nfl_week()
    for index in range(11):
        market_id = 9300 + index
        markets.append(_market(market_id, f"Spread: Bills (-{index + 1}.5)", event_id=501))
        hub.edges.append(("unclassified", "market", market_id, hub.id, "matcher", 1.0))
    markets.append(_market(9400, "An NFL season market", event_id=None))
    hub.edges.extend([
        ("title", "market", 9400, hub.id, "matcher", 1.0),
        ("unclassified", "market", 9401, hub.id, "matcher", 1.0),
    ])
    return hub, events, markets


async def read_week(session, *, compact=False):
    return await route.get_container(
        slug=session.hub.slug, include_children=True, compact=compact, db=session
    )


async def test_compact_view_accounts_for_every_member_and_keeps_missing_row_reasons():
    hub, events, markets = long_week()
    full = await read_week(CompactSession(hub, events=events, markets=markets))
    session = CompactSession(hub, events=events, markets=markets)

    compact = await read_week(session, compact=True)

    assert compact["revision"] == full["revision"] == hub.revision
    assert compact["related_summary"] == {"count": 13, "unclassified_count": 11}
    assert compact["member_count"] == 4
    assert compact["member_count"] + compact["related_summary"]["count"] == full["member_count"]
    assert compact["withheld"] == full["withheld"]
    assert {member["id"] for member in compact["withheld"]} == {599, 9401}
    members = {member["id"]: member for section in compact["sections"] for member in section["members"]}
    assert members[501]["related_count"] == 13
    assert members[501]["question_ids"] == []
    assert members[502]["question_ids"] == [9102]
    assert members[9102]["destination"]["web"] == "/futures/9102"
    assert members[9400]["destination"]["web"] == "/futures/9400"
    assert all(reason["reason"] == "row_missing" for reason in compact["withheld"])
    assert sum(statement.startswith("SELECT id, event_id FROM futures_markets") for statement in session.statements) == 1


async def test_compact_http_entry_point_skips_hydration_of_a_long_attached_list(monkeypatch):
    from app.routes import events as event_route

    hub, events, markets = long_week()
    session = CompactSession(hub, events=events, markets=markets)
    formatted_ids = []
    original_format = event_route._format_futures_for_search

    def format_market(market, withheld=None):
        formatted_ids.append(market.id)
        return original_format(market, withheld)

    monkeypatch.setattr(event_route, "_format_futures_for_search", format_market)

    async def database():
        yield session

    app = FastAPI()
    app.include_router(route.router, prefix="/api/containers")
    app.dependency_overrides[route.get_db] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid") as client:
        response = await client.get(f"/api/containers/{hub.slug}?compact=true")

    assert response.status_code == 200
    assert response.json()["related_summary"]["count"] == 13
    assert set(formatted_ids) == {9102, 9400}


async def test_a_failed_game_card_keeps_its_markets_in_the_card_read(monkeypatch):
    from app.routes import events as event_route

    original_format = event_route._format_event_with_aggregated_odds

    def format_event(event, *args, **kwargs):
        if event.id == 501:
            raise ValueError("representative game-card failure")
        return original_format(event, *args, **kwargs)

    monkeypatch.setattr(event_route, "_format_event_with_aggregated_odds", format_event)
    hub, events, markets = long_week()

    payload = await read_week(CompactSession(hub, events=events, markets=markets), compact=True)

    assert payload["related_summary"] == {"count": 0, "unclassified_count": 0}
    members = {member["id"] for section in payload["sections"] for member in section["members"]}
    assert {9101, 9103, *range(9300, 9311)} <= members
    assert {"type": "event", "id": 501, "reason": "unserializable"} in payload["withheld"]


@pytest.mark.parametrize("state", ["withdrawn", "unpublished"])
async def test_nonpublished_compact_reads_expose_no_members_or_summary(state):
    hub, events, markets = long_week()
    hub.publication = state
    session = CompactSession(hub, events=events, markets=markets)

    payload = await read_week(session, compact=True)

    assert payload["state"] == state
    assert payload["sections"] == []
    assert "related_summary" not in payload
    assert not any("FROM futures_markets" in statement for statement in session.statements)


def test_the_4972_market_case_counts_unclassified_members_and_shared_edges_once():
    members = [{"id": event_id, "type": "event", "class": "match_winner"} for event_id in range(1, 16)]
    markets = [
        {"id": 1000 + index, "type": "market", "class": "unclassified" if index % 3 == 0 else "prop"}
        for index in range(4972)
    ]
    members.extend(markets)
    members.append({**markets[0], "container_id": 99})
    market_events = {1000 + index: 1 + index % 15 for index in range(4972)}
    market_events[999999] = 1

    kept, counts, unclassified_count = compact_related_members(members, market_events, set(range(1, 16)))

    assert kept == members[:15]
    assert sum(counts.values()) == 4972
    assert unclassified_count == 1658
    assert len(counts) == 15


def test_short_lists_and_unavailable_game_members_keep_their_cards():
    members = [
        {"id": index, "type": "market", "class": "unclassified"}
        for index in range(1, 27)
    ]
    market_events = {index: 501 if index <= 12 else 502 for index in range(1, 27)}

    kept, counts, unclassified_count = compact_related_members(members, market_events, {501})

    assert kept == members
    assert counts == {}
    assert unclassified_count == 0
