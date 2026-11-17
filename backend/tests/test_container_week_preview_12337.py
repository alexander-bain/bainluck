"""The default NFL week never hydrates thousands of boards to show its games."""

from collections import Counter
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.routes import containers as route
from app.utils.container_week_preview import (
    MarketSummary,
    decode_cursor,
    encode_cursor,
    ranked_preview,
)
from tests.test_container_hydrated_reader_9636 import (
    _Hub,
    _Result,
    _Session,
    _event,
    _market,
)


class WeekSession(_Session):
    def __init__(self, count=4984):
        events = [_event(i, f"Home {i}", f"Away {i}", hours=48) for i in range(1, 15)]
        hub = _Hub(
            "nfl-2026-week-10",
            edges=[("match_winner", "event", e.id, 70, "statpal", 1.0) for e in events],
        )
        self.summaries = {}
        for index in range(count):
            mid = 1000 + index
            event_id = 1 + index % 14 if index < count - 4 else None
            name = (
                (
                    f"Player {index}: 60+ receiving yards"
                    if index % 2
                    else "1st Quarter Winner"
                )
                if event_id
                else f"Season future {index}"
            )
            self.summaries[mid] = MarketSummary(
                mid, event_id, name, f"fixture-{mid}", count - index, count * 10 - index
            )
            hub.edges.append(
                (
                    "title" if index % 2 == 0 else "unclassified",
                    "market",
                    mid,
                    70,
                    "matcher",
                    1.0,
                )
            )
        self.hydrated = []
        self.descriptors = []
        super().__init__(hub, events=events)

    async def execute(self, sql, params=None):
        statement = str(sql)
        if statement.startswith("SELECT id, event_id, name"):
            self.descriptors.append(list(params["market_ids"]))
            return _Result(
                tuple(vars(self.summaries[mid]).values())
                for mid in params["market_ids"]
                if mid in self.summaries
            )
        if (
            statement.startswith("SELECT futures_markets.")
            and "WHERE futures_markets.id IN" in statement
        ):
            ids = list(sql.compile().params["id_1"])
            self.hydrated.append(ids)
            return _Result(
                _market(
                    mid, self.summaries[mid].name, event_id=self.summaries[mid].event_id
                )
                for mid in ids
                if mid in self.summaries
            )
        return await super().execute(sql, params)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    @asynccontextmanager
    async def references():
        yield _Session()

    monkeypatch.setattr("app.services.database.async_session_maker", references)
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")


def all_members(payload):
    return [m for s in payload["sections"] for m in s["members"]]


async def get(session, **params):
    return await route.get_container(
        slug=session.hub.slug, include_children=True, db=session, **params
    )


async def test_real_default_http_keeps_all_14_games_but_hydrates_only_12_boards():
    session = WeekSession()
    app = FastAPI()
    app.include_router(route.router, prefix="/api/containers")

    async def database():
        yield session

    app.dependency_overrides[route.get_db] = database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid"
    ) as client:
        response = await client.get(f"/api/containers/{session.hub.slug}")
    assert response.status_code == 200
    payload = response.json()
    members = all_members(payload)
    assert len([m for m in members if m["type"] == "event"]) == 14
    assert len([m for m in members if m["type"] == "market"]) == 12
    assert len(session.hydrated) == 1 and len(session.hydrated[0]) == 12
    assert payload["counts"] == {
        "market_count": 4984,
        "selected_market_count": 12,
        "deferred_market_count": 4972,
    }
    assert len(response.content) < 180_000
    assert all(
        m["destination"]["api"] == f"/api/futures/{m['id']}"
        for m in members
        if m["type"] == "market"
    )
    for section in payload["sections"]:
        for member in section["members"]:
            if member["card"].get("name") == "1st Quarter Winner":
                assert section["class"] == "side_question"


async def test_every_remaining_market_is_reachable_once_even_if_activity_changes():
    session = WeekSession(count=45)
    payload = await get(session)
    seen = [m["id"] for m in all_members(payload) if m["type"] == "market"]
    # An unselected member disappears: it stays an explicit refusal on its page.
    gone = next(mid for mid in session.summaries if mid not in seen)
    session.summaries.pop(gone)
    for mid, row in list(session.summaries.items()):
        session.summaries[mid] = MarketSummary(
            row.id, row.event_id, row.name, row.external_id, mid * 100, mid
        )
    while payload["page"]["next_url"]:
        params = {
            k: values[0]
            for k, values in parse_qs(
                urlparse(payload["page"]["next_url"]).query
            ).items()
        }
        params.pop("include_children")
        assert set(params) == {"market_cursor", "market_revision", "market_limit"}
        params["market_limit"] = "7"
        payload = await get(session, **params)
        assert payload["page"]["limit"] == 7
        assert all(m["type"] == "market" for m in all_members(payload))
        assert len(session.hydrated[-1]) <= 7
        seen.extend(m["id"] for m in all_members(payload))
        for item in payload["withheld"]:
            assert item == {"type": "market", "id": gone, "reason": "row_missing"}
            seen.append(item["id"])
    assert len(seen) == len(set(seen)) == 45
    assert set(seen) == set(range(1000, 1045))
    assert all(len(ids) <= 7 for ids in session.descriptors[1:])


async def test_http_continuation_ignores_theme_params_and_keeps_its_market_page_size():
    session = WeekSession(count=45)
    app = FastAPI()
    app.include_router(route.router, prefix="/api/containers")

    async def database():
        yield session

    app.dependency_overrides[route.get_db] = database
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture.invalid"
    ) as client:
        entry = await client.get(f"/api/containers/{session.hub.slug}")
        next_url = entry.json()["page"]["next_url"]
        params = {k: values[0] for k, values in parse_qs(urlparse(next_url).query).items()}
        assert params["market_limit"] == "50"
        params.update(market_limit="7", revision="invalid", cursor="!!", limit="0")
        response = await client.get(urlparse(next_url).path, params=params)
        assert response.status_code == 200
        page = response.json()
        assert page["member_count"] == 7
        assert all(member["type"] == "market" for member in all_members(page))
        assert len(session.hydrated[-1]) == 7
        following = await client.get(page["page"]["next_url"])
        assert following.status_code == 200
        assert following.json()["page"]["limit"] == 7
        assert following.json()["member_count"] == 7
        assert {m["id"] for m in all_members(page)}.isdisjoint(
            {m["id"] for m in all_members(following.json())}
        )


async def test_cursor_refuses_a_changed_revision_and_another_scope():
    session = WeekSession(count=45)
    payload = await get(session)
    cursor = payload["page"]["next_cursor"]
    session.hub.revision += 1
    with pytest.raises(HTTPException) as error:
        await get(session, market_cursor=cursor)
    assert error.value.status_code == 409
    session.hub.revision -= 1
    wrong_scope = encode_cursor(session.hub.id, session.hub.revision, True, 0, [])
    with pytest.raises(HTTPException) as error:
        await get(session, market_cursor=wrong_scope)
    assert error.value.status_code == 422


@pytest.mark.parametrize("state", ["withdrawn", "unpublished"])
async def test_pagination_never_bypasses_a_withdrawal(state):
    session = WeekSession(count=45)
    payload = await get(session)
    session.hub.publication = state
    session.hydrated.clear()
    result = await get(session, market_cursor=payload["page"]["next_cursor"])
    assert result["state"] == state and result["sections"] == []
    assert session.hydrated == []


@pytest.mark.parametrize("limit", ["0", "101", "-1", "a", "9" * 10000])
async def test_limit_cannot_trigger_an_unbounded_read(limit):
    session = WeekSession(count=45)
    with pytest.raises(HTTPException) as error:
        await get(session, market_limit=limit)
    assert error.value.status_code == 422 and session.hydrated == []


def test_selection_is_deterministic_diverse_and_keeps_published_futures():
    session = WeekSession()
    rows = list(session.summaries.values())
    selected = ranked_preview(rows, set(range(1, 15)))
    assert selected == ranked_preview(list(reversed(rows)), set(range(1, 15)))
    assert len(selected) == len(set(selected)) == 12
    counts = Counter(session.summaries[mid].event_id for mid in selected)
    assert all(count <= 2 for eid, count in counts.items() if eid is not None)
    assert counts[None] == 4
    assert {session.summaries[mid].group(set(range(1, 15))) for mid in selected} == {
        "props",
        "game_markets",
        "futures",
    }


@pytest.mark.parametrize("value", ["garbage", "W10", "a" * 513, "bnVsbA"])
def test_cursor_rejects_malformed_input(value):
    assert decode_cursor(value) is None


async def test_game_only_week_has_an_explicit_end_to_market_paging():
    payload = await get(WeekSession(count=0))
    assert payload["member_count"] == 14
    assert payload["counts"]["market_count"] == 0
    assert (
        payload["page"]["next_cursor"] is None and payload["page"]["next_url"] is None
    )


async def test_explicit_full_inventory_remains_available():
    session = WeekSession(count=45)
    payload = await get(session, compact=False)
    assert payload["member_count"] == 14 + 45
    assert "page" not in payload and "related_summary" not in payload
    assert session.descriptors == []
    assert len(session.hydrated[0]) == 45


async def test_metadata_failure_is_an_error_not_an_empty_market_preview():
    class Failed(WeekSession):
        async def execute(self, sql, params=None):
            if str(sql).startswith("SELECT id, event_id, name"):
                raise RuntimeError("metadata unavailable")
            return await super().execute(sql, params)

    with pytest.raises(RuntimeError, match="metadata unavailable"):
        await get(Failed(count=45))


def test_missing_activity_ties_are_stable_and_duplicate_edges_cannot_use_seats():
    rows = [
        MarketSummary(i, 1 + i % 14, "Player: 60+ receiving yards", None, None, None)
        for i in range(1, 40)
    ]
    picked = ranked_preview(rows + rows, set(range(1, 15)))
    assert picked == ranked_preview(list(reversed(rows)), set(range(1, 15)))
    assert len(picked) == len(set(picked)) == 12
