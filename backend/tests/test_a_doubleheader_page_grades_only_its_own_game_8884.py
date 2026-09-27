"""#8884 — a doubleheader's settled page grades only its own game's Kalshi markets.

Cubs @ Red Sox, 2026-09-25, game 2 (`/events/15318545`, Red Sox 2–0) printed
"Will there be a run scored in the first inning? No: Won" beside "Chicago Cubs
vs Boston: Game 1 First Inning Run  Yes: Won". Those game-1 markets have
`event_id IS NULL`; `/game-markets`' unlinked sweep attached them by team names,
a ±6h window and a ticker DATE check — and a doubleheader shares its date.

The id that tells the two games apart is the game number Kalshi suffixes onto
the team-code (`…26SEP251305CHCBOSG1` / `…26SEP251805CHCBOSG2`). The HHMM is
not: production game 2 carried `1735`, `1805` and `1910` as its start moved.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.prediction_market_matching import (
    is_other_doubleheader_game,
    kalshi_doubleheader_game_number,
    own_doubleheader_game_numbers,
)
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_futures_market,
)

GAME_DAY = date(2026, 9, 25)


class _M:
    def __init__(self, external_id):
        self.external_id = external_id


# ── the pure helpers ────────────────────────────────────────────────────────


def test_the_game_number_is_read_off_the_team_code():
    assert kalshi_doubleheader_game_number("KXMLBGAME-26SEP251305CHCBOSG1") == 1
    assert kalshi_doubleheader_game_number("KXMLBF5TOTAL-26SEP251805CHCBOSG2-2") == 2
    assert kalshi_doubleheader_game_number("KXMLBGAME-26SEP251910CHCBOS") is None
    assert kalshi_doubleheader_game_number("0xd9dbffc69a58241") is None
    assert kalshi_doubleheader_game_number(None) is None


def test_own_numbers_count_only_the_events_own_date():
    linked = [
        _M("KXMLBGAME-26SEP251805CHCBOSG2"),
        _M("KXMLBGAME-26SEP251910CHCBOS"),
        _M("KXMLBGAME-26SEP241305CHCBOSG1"),  # yesterday's game 1 is not today's
        _M("0xpolymarketconditionid"),
    ]
    assert own_doubleheader_game_numbers(linked, GAME_DAY) == {2}
    assert own_doubleheader_game_numbers(linked, None) == set()


def test_only_the_other_numbered_game_is_refused():
    assert is_other_doubleheader_game("KXMLBGAME-26SEP251305CHCBOSG1", {2}) is True
    assert is_other_doubleheader_game("KXMLBGAME-26SEP251805CHCBOSG2", {2}) is False
    assert is_other_doubleheader_game("KXMLBGAME-26SEP251910CHCBOS", {2}) is False


def test_fails_open_without_one_anchor():
    g1 = "KXMLBGAME-26SEP251305CHCBOSG1"
    assert is_other_doubleheader_game(g1, set()) is False
    assert is_other_doubleheader_game(g1, {1, 2}) is False


# ── the route ───────────────────────────────────────────────────────────────


def _mkt(mid, name, ticker, linked_to=None):
    m = _make_futures_market(id=mid, name=name, source="kalshi", sport_category="baseball")
    m.external_id = ticker
    m.event_id = linked_to
    m.category = "game_prop"
    m.status = "resolved"
    m.commence_time = datetime(2026, 9, 25, 22, 0, tzinfo=timezone.utc)
    return m


def _result(rows):
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(rows)
    r.scalars.return_value.first.return_value = rows[0] if rows else None
    r.scalar_one_or_none.return_value = None
    r.scalar.return_value = None
    r.fetchall.return_value = []
    r.all.return_value = []
    r.first.return_value = None
    return r


def _session(event, linked, unlinked, loaded):
    """Routes the LINKED read and the UNLINKED sweep to different rows — the
    shared seeded double hands both the same list, which cannot tell them apart.

    ``loaded`` records the market ids the route loads outcomes for (step 4,
    directly after the sweep): that id list IS the set of markets the page is
    built from, so it is read there rather than through the downstream
    grading/price filters, which would drop these bare stubs for reasons of
    their own and make every assertion vacuous."""
    session = AsyncMock()

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "odds_snapshots" in s:
            return _result([])
        if "futures_outcomes" in s:
            if "futures_outcomes.market_id in" in s:
                for v in stmt.compile().params.values():
                    if isinstance(v, (list, tuple)):
                        loaded.extend(v)
            return _result([])
        if "futures_markets" in s:
            if "polymarket_event" in s or "polymarket_sub_market" in s:
                return _result([])
            if "futures_markets.event_id is null" in s:
                return _result(unlinked)
            return _result(linked)
        if "events" in s:
            r = _result([event])
            r.scalar_one_or_none.return_value = event
            return r
        return _result([])

    session.execute = AsyncMock(side_effect=execute)
    return session


async def _markets_on_page(event, linked, unlinked, sport_key="baseball_mlb"):
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    _game_markets_cache.clear()
    _event_detail_cache.clear()
    event.sport.key = sport_key
    event.sport_key = sport_key
    loaded: list[int] = []
    session = _session(event, linked, unlinked, loaded)

    async def _db():
        yield session

    async def _user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(f"/api/events/{event.id}/game-markets")
    finally:
        _game_markets_cache.clear()
        _event_detail_cache.clear()
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    # Strawman: the seam was reached — the linked market is always loaded.
    assert linked[0].id in loaded, loaded
    return set(loaded)


def _game(eid, commence):
    e = _make_event(
        id=eid, home_team="Boston Red Sox", away_team="Chicago Cubs",
        status="completed", sport_key="baseball_mlb", home_score=2, away_score=0,
    )
    e.commence_time = commence
    e.sport.name = "Baseball"
    return e


GAME_2 = datetime(2026, 9, 25, 21, 30, tzinfo=timezone.utc)
G1_FIRST_INNING = "Chicago Cubs vs Boston: Game 1 First Inning Run"
G2_FIRST_INNING = "Chicago Cubs vs Boston: Game 2 First Inning Run"
UNNUMBERED = "Chicago Cubs vs Boston Red Sox: First 5 Innings Total"


@pytest.mark.asyncio
async def test_game_twos_page_drops_game_ones_unlinked_market():
    event = _game(15318545, GAME_2)
    linked = [_mkt(1, "Chicago Cubs vs Boston: Game 2 Winner", "KXMLBGAME-26SEP251805CHCBOSG2", 15318545)]
    unlinked = [
        _mkt(2, G1_FIRST_INNING, "KXMLBRFI-26SEP251305CHCBOSG1"),
        _mkt(3, G2_FIRST_INNING, "KXMLBRFI-26SEP251735CHCBOSG2"),
        _mkt(4, UNNUMBERED, "KXMLBF5TOTAL-26SEP251910CHCBOS"),
    ]
    # Game 1's market is refused; the same sweep still brings its own game's
    # markets whatever HHMM they carry, and an unnumbered ticker is never refused.
    assert await _markets_on_page(event, linked, unlinked) == {1, 3, 4}


@pytest.mark.asyncio
async def test_an_event_with_no_numbered_link_refuses_nothing():
    """Fail-open: nothing to anchor on ⇒ the sweep behaves as it did before."""
    event = _game(15318545, GAME_2)
    linked = [_mkt(1, "Chicago Cubs vs Boston Winner", "KXMLBGAME-26SEP251910CHCBOS", 15318545)]
    unlinked = [_mkt(2, G1_FIRST_INNING, "KXMLBRFI-26SEP251305CHCBOSG1")]
    assert await _markets_on_page(event, linked, unlinked) == {1, 2}


@pytest.mark.asyncio
async def test_game_ones_page_drops_game_twos_unlinked_market():
    """The reverse direction: game 1's page served 7 game-2 markets."""
    event = _game(15318549, datetime(2026, 9, 25, 17, 5, tzinfo=timezone.utc))
    linked = [_mkt(1, "Chicago Cubs vs Boston: Game 1 Winner", "KXMLBGAME-26SEP251305CHCBOSG1", 15318549)]
    unlinked = [
        _mkt(2, G1_FIRST_INNING, "KXMLBRFI-26SEP251305CHCBOSG1"),
        _mkt(3, G2_FIRST_INNING, "KXMLBRFI-26SEP251805CHCBOSG2"),
    ]
    assert await _markets_on_page(event, linked, unlinked) == {1, 2}


@pytest.mark.asyncio
async def test_the_rule_is_baseball_only():
    """Outside baseball a trailing G-digit is a team code (`FNCG2`), not a game."""
    event = _game(15318545, GAME_2)
    linked = [_mkt(1, "Chicago Cubs vs Boston: Game 2 Winner", "KXMLBGAME-26SEP251805CHCBOSG2", 15318545)]
    unlinked = [_mkt(2, G1_FIRST_INNING, "KXMLBRFI-26SEP251305CHCBOSG1")]
    assert await _markets_on_page(event, linked, unlinked, sport_key="basketball_nba") == {1, 2}
