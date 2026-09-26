"""#8906 at the route: `/api/events/search` serves a linked card's kickoff.

The unit file (`tests/test_search_card_serves_linked_kickoff_8906.py`) pins the
helper. This one pins the wiring a unit test cannot see: that the route issues
the keyed `events` read and the kickoff reaches BOTH reader buckets (`futures`
and `futures_families` hold the same dicts).

Rig borrowed from `test_route_search_club_names_6447.py` (same specimen shape:
a Kalshi game market linked to its event); the kickoff read is recognised by its
projection, `SELECT events.id, events.commence_time`.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_search_club_names_6447 import (
    JETS_EVENT_ID,
    _already_correct_market,
    _cards,
    _empty_result,
    _market,
)

_asyncio = pytest.mark.asyncio
KICKOFF = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)
_KICKOFF_SELECT = "SELECT events.id, events.commence_time"


def _session(window, event_rows, seen):
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = " ".join(str(stmt).split())
        except Exception:  # noqa: BLE001
            return result
        if sql.startswith(_KICKOFF_SELECT):
            seen.append("kickoff")
            result.all.return_value = list(event_rows)
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper() or "~*" in sql:
            return result
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


async def _search(monkeypatch, window, event_rows, seen):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    session = _session(window, event_rows, seen)

    async def _db():
        yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                return (await ac.get("/api/events/search?q=Jets")).json()
    finally:
        app.dependency_overrides.clear()


@_asyncio
async def test_linked_card_serves_its_games_kickoff_in_both_buckets(monkeypatch):
    seen: list[str] = []
    body = await _search(
        monkeypatch, [_already_correct_market()], [(JETS_EVENT_ID, KICKOFF)], seen
    )
    cards = _cards(body)
    assert cards
    for card in cards:
        assert card["event_commence_time"] == "2026-09-20T17:00:00+00:00"
        assert card["resolution_date"] is not None  # unmoved, still served
    assert seen.count("kickoff") == 1


@_asyncio
async def test_unlinked_card_serves_no_key_and_pays_no_read(monkeypatch):
    seen: list[str] = []
    market = _market(outcome_names=("Green Bay", "New York Jets"), event_id=None)
    body = await _search(monkeypatch, [market], [(JETS_EVENT_ID, KICKOFF)], seen)
    cards = _cards(body)
    assert cards
    for card in cards:
        assert "event_commence_time" not in card
    assert "kickoff" not in seen
