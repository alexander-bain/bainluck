"""#7355 at the route: `GET /api/events/search?q=kings` stops filling its ANSWERS
card with esports matches.

Production 2026-09-25: `kings` served a hockey headline and FOUR esports members
(Honor of Kings / LoL clubs named "Kings"), `falcons` two, `warriors` two. None
of those queries recalls an esports club from the teams table, and that is the
signal: `_team_evidence_sport_categories` over the uncapped team recall, then
`_demote_teamless_sport` inside `_rerank_search_futures`.

WHY AT THE ROUTE. The helper tests (`tests/test_search_teamless_sport_demotion_
7355.py`) prove the partition. Only the route proves the wiring this ship had to
MOVE: the teams query used to run after the futures were ranked and composed, so
the evidence did not exist yet. These assertions read the served `futures` and
`futures_families` arrays, so a fix that computed the evidence and never reached
the re-rank is red here.

THE CONTROLS. `no_teams` serves the same futures with no team rows — the esports
rows must keep their volume places, which is what proves the harness can see the
order at all (and that the rule disarms without evidence). `teams_shed` makes the
teams statement time out: the page must still answer 200, name `teams` in
`degraded`, and leave the order alone — the stage now runs while the futures rows
are live, so its shed path is a SAVEPOINT rollback, never the session rollback.

RED-FIRST: revert `app/routes/events.py` alone; the esports rows return to the
card and `TestTheCard` reddens.
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


#: Volume-descending, so without the demotion the served order is this order.
#: Every name carries "Kings" and none trips `_story_key`, so they form ONE
#: entity family (`TestTheSeed` pins that). ⚠️ The esports names are LoL-shaped
#: on purpose: "Honor of Kings", "Valorant" or the word "Esports" route a row to
#: `story:niche_low_signal_sports` and split the seed into two families.
KINGS = [
    _market(900_001, "Los Angeles Kings to make the playoffs", "hockey", 9_000_000),
    _market(900_002, "LoL: ZSK vs Kings (BO1) - World Star Challengers Invitational Group D", "esports", 8_000_000),
    _market(900_003, "LoL: Solary vs Kings (BO1)", "esports", 7_000_000),
    _market(900_004, "LoL: Kings vs MVK Academy (BO5)", "esports", 6_000_000),
    _market(900_005, "Sacramento Kings over 38.5 wins", "basketball", 5_000_000),
    _market(900_006, "Los Angeles Kings: Kopitar total points", "hockey", 4_000_000),
    _market(900_007, "Sacramento Kings to make the playoffs", "basketball", 3_000_000),
    _market(900_008, "LoL: Kings vs Rogue (BO3)", "esports", 2_000_000),
    _market(900_009, "Sacramento Kings: Fox total assists", "basketball", 1_000_000),
]
ESPORTS = {m.id for m in KINGS if m.llm_sport_category == "esports"}


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


class _Timeout(Exception):
    sqlstate = "57014"


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


def _seeded_session(window, teams, *, teams_time_out=False):
    session = AsyncMock()
    calls = {"team_recall": 0}

    async def _execute(stmt, *args, **kwargs):
        result = _empty_result()
        try:
            sql = str(stmt)
        except Exception:  # noqa: BLE001
            return result
        if _is_team_recall(sql):
            calls["team_recall"] += 1
            if teams_time_out:
                raise _Timeout("canceling statement due to statement timeout")
            result.all.return_value = list(teams)
            return result
        if "futures_markets" not in sql or "SELECT" not in sql.upper() or "~*" in sql:
            return result
        result.scalars.return_value.unique.return_value.all.return_value = list(window)
        result.scalars.return_value.all.return_value = list(window)
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
    session = _seeded_session(KINGS, KINGS_TEAMS)
    async for ac in _client(session, monkeypatch):
        yield ac, session


@pytest_asyncio.fixture
async def no_teams(monkeypatch):
    session = _seeded_session(KINGS, [])
    async for ac in _client(session, monkeypatch):
        yield ac, session


@pytest_asyncio.fixture
async def teams_shed(monkeypatch):
    session = _seeded_session(KINGS, KINGS_TEAMS, teams_time_out=True)
    async for ac in _client(session, monkeypatch):
        yield ac, session


async def _search(client, q="kings"):
    # A fresh query string per call: the response cache is keyed on it.
    resp = await client.get(f"/api/events/search?q={q}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _flat(body):
    return [m["id"] for m in body.get("futures") or []]


def _card(body):
    fams = body.get("futures_families") or []
    assert len(fams) == 1, [f.get("label") for f in fams]
    return [fams[0]["headline"]["id"]] + [m["id"] for m in fams[0]["members"]]


class TestTheSeed:
    @_asyncio
    async def test_the_team_recall_was_asked_and_one_family_forms(self, kings):
        client, session = kings
        body = await _search(client)
        assert session.calls["team_recall"] == 1
        assert len(_card(body)) == 5
        assert len(_flat(body)) == len(KINGS)


class TestTheCard:
    @_asyncio
    async def test_the_card_carries_no_esports(self, kings):
        client, _ = kings
        card = _card(await _search(client))
        assert not (set(card) & ESPORTS), card

    @_asyncio
    async def test_the_flat_list_puts_esports_last_in_their_own_order(self, kings):
        client, _ = kings
        assert _flat(await _search(client)) == [
            900_001, 900_005, 900_006, 900_007, 900_009,
            900_002, 900_003, 900_004, 900_008,
        ]

    @_asyncio
    async def test_nothing_is_dropped(self, kings):
        client, _ = kings
        assert set(_flat(await _search(client))) == {m.id for m in KINGS}


class TestTheControls:
    @_asyncio
    async def test_no_team_rows_leaves_the_volume_order(self, no_teams):
        """The harness can see the order, and the rule disarms without evidence."""
        client, _ = no_teams
        body = await _search(client)
        assert _flat(body) == [m.id for m in KINGS]
        assert set(_card(body)[1:4]) <= ESPORTS

    @_asyncio
    async def test_a_shed_teams_stage_answers_and_disarms(self, teams_shed):
        client, session = teams_shed
        body = await _search(client)
        assert session.calls["team_recall"] == 1
        assert "teams" in (body.get("degraded") or [])
        assert body.get("teams") == []
        assert _flat(body) == [m.id for m in KINGS]
        session.rollback.assert_not_awaited()
