"""#7355 r2 at the route: a window FULL of teamless rows refills from rank 21.

Production 2026-09-25, after r1 (`0dbcde5eab`) went live: `q=kings` served the
NBA champion market and eight Honor of Kings rows, and its ANSWERS card was all
esports. The window was twenty esports rows — their names repeat "king", so they
out-rank every club market on `ts_rank_cd` — and r1's demotion can only reorder
the window, so it had nothing to sink them below. 17 Kings hockey and 4 Kings
basketball markets sat at ranks 21-60, which only the REFILL lane reads, and the
refill's collapse test counted the sunk rows as if they filled the page.

THE FIX UNDER TEST: the collapse test counts ANSWER rows (not teamless), and the
refilled page is re-partitioned so the refill's club rows sit above the window's
sunk ones.

THE CONTROLS. `no_teams` serves the same window with no team rows: the rule is
disarmed, the page is full, and the refill must NOT run — the old gate exactly.
`kings_short` is r1's own shape (a window that is not saturated): no refill,
esports sink to the end of what the window had.

RED-FIRST: revert `app/routes/events.py` alone; `refill` is never asked, the flat
page is one basketball row and nine esports, and `TestTheRefill` reddens.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

_asyncio = pytest.mark.asyncio


def _outcome(name, prob, oid):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, rank=oid % 10, sort_order=oid,
        current_yes_bid=None, current_yes_ask=None,
        external_id=f"OUT-{oid}",
    )


def _market(mid, name, cat, volume):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid, name=name, external_id=f"KX-{mid}",
        llm_sport_category=cat, category=cat, market_tier=5,
        market_type="prop", sport=None, sport_id=None, source="kalshi",
        volume=volume, status="open",
        resolution_date=(now + timedelta(days=20)).date(),
        updated_at=now, canonical_market_key=None, image_url=None,
        hook_description=None, group_id=None, event_id=None,
        outcomes=[_outcome("Yes", 0.55, mid * 10 + 1), _outcome("No", 0.45, mid * 10 + 2)],
    )


_ESPORTS_CLUBS = [
    "ZSK", "Solary", "MVK Academy", "Rogue", "Fnatic", "Vitality", "Heretics",
    "Karmine", "Movistar", "Giants", "BDS", "Excel", "SK Gaming", "Astralis",
    "Mad Lions", "Misfits", "Schalke", "Origen", "Splyce",
]

#: The production shape: one club row, nineteen esports rows, a saturated window.
WINDOW = [_market(910_000, "Sacramento Kings to win the 2027 NBA title", "basketball", 9_900_000)] + [
    _market(910_001 + i, f"LoL: {club} vs Kings (BO{1 + 2 * (i % 2)}) - Group {i}", "esports", 9_000_000 - i)
    for i, club in enumerate(_ESPORTS_CLUBS)
]
#: Ranks 21+: the clubs' own markets, and more esports behind them.
REFILL = [
    _market(920_001, "Los Angeles Kings to make the playoffs", "hockey", 500_000),
    _market(920_002, "Sacramento Kings over 38.5 wins", "basketball", 400_000),
    _market(920_003, "LoL: Kings vs Team Liquid (BO3)", "esports", 350_000),
    _market(920_004, "Los Angeles Kings: Kopitar total points", "hockey", 300_000),
    _market(920_005, "Sacramento Kings to make the playoffs", "basketball", 200_000),
    _market(920_006, "Los Angeles Kings to win the Pacific", "hockey", 100_000),
]
ESPORTS = {m.id for m in WINDOW + REFILL if m.llm_sport_category == "esports"}
CLUB = {m.id for m in WINDOW + REFILL if m.llm_sport_category != "esports"}


def _team(tid, name, sport_key):
    return SimpleNamespace(
        id=tid, name=name, slug=name.lower().replace(" ", "-"), abbreviation=None,
        logo_url_small=None, current_record=None, sport_key=sport_key,
        alternate_names=[], team_rank=0.5,
    )


KINGS_TEAMS = [
    _team(1, "Los Angeles Kings", "icehockey_nhl"),
    _team(2, "Sacramento Kings", "basketball_nba"),
    _team(3, "Punjab Kings", "cricket_ipl"),
]


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.unique.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    result.mappings.return_value.all.return_value = []
    return result


def _is_team_recall(sql):
    return "team_rank" in sql and "FROM teams" in sql


def _seeded_session(window, refill, teams):
    session = AsyncMock()
    calls = {"team_recall": 0, "refill": 0}

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if _is_team_recall(sql):
            calls["team_recall"] += 1
            result.all.return_value = list(teams)
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper() or "~*" in sql:
            return result
        rows = window
        if "OFFSET" in sql.upper():
            calls["refill"] += 1
            rows = refill
        result.scalars.return_value.unique.return_value.all.return_value = list(rows)
        result.scalars.return_value.all.return_value = list(rows)
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.calls = calls
    return session


async def _client(session, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def kings(monkeypatch):
    session = _seeded_session(WINDOW, REFILL, KINGS_TEAMS)
    async for ac in _client(session, monkeypatch):
        yield ac, session


@pytest_asyncio.fixture
async def no_teams(monkeypatch):
    session = _seeded_session(WINDOW, REFILL, [])
    async for ac in _client(session, monkeypatch):
        yield ac, session


@pytest_asyncio.fixture
async def kings_short(monkeypatch):
    session = _seeded_session(WINDOW[:12], REFILL, KINGS_TEAMS)
    async for ac in _client(session, monkeypatch):
        yield ac, session


async def _search(client, q="kings"):
    resp = await client.get(f"/api/events/search?q={q}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _flat(body):
    return [m["id"] for m in body.get("futures") or []]


def _card_ids(body):
    ids = []
    for fam in body.get("futures_families") or []:
        ids.append(fam["headline"]["id"])
        ids.extend(m["id"] for m in fam["members"])
    return ids


class TestTheSeed:
    @_asyncio
    async def test_the_window_is_saturated_and_mostly_teamless(self):
        assert len(WINDOW) == 20
        assert sum(1 for m in WINDOW if m.id in CLUB) == 1


class TestTheRefill:
    @_asyncio
    async def test_the_refill_is_asked(self, kings):
        client, session = kings
        await _search(client)
        assert session.calls["team_recall"] == 1
        assert session.calls["refill"] == 1

    @_asyncio
    async def test_the_page_opens_with_every_club_row(self, kings):
        client, _ = kings
        flat = _flat(await _search(client))
        assert flat[:6] == [910_000, 920_001, 920_002, 920_004, 920_005, 920_006], flat

    @_asyncio
    async def test_esports_only_fill_what_the_clubs_leave(self, kings):
        client, _ = kings
        flat = _flat(await _search(client))
        assert len(flat) == 10
        assert set(flat[6:]) <= ESPORTS, flat

    @_asyncio
    async def test_the_answers_card_carries_no_esports(self, kings):
        client, _ = kings
        card = _card_ids(await _search(client))
        assert card, "no ANSWERS card at all"
        assert not (set(card) & ESPORTS), card


class TestTheControls:
    @_asyncio
    async def test_no_team_rows_keeps_the_old_gate(self, no_teams):
        """Disarmed: a full page of window rows, the refill never asked."""
        client, session = no_teams
        flat = _flat(await _search(client))
        assert session.calls["refill"] == 0
        assert flat == [m.id for m in WINDOW[:10]]

    @_asyncio
    async def test_an_unsaturated_window_does_not_refill(self, kings_short):
        client, session = kings_short
        flat = _flat(await _search(client))
        assert session.calls["refill"] == 0
        assert flat[0] == 910_000
        assert set(flat[1:]) <= ESPORTS
