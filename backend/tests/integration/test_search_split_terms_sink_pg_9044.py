"""#9044 — `oregon state` leads with Oregon State's games, not Ducks games vs a "State".

THE DEFECT, read on production 2026-09-27 04:0xZ, `/search?q=oregon%20state`:
GAMES opened with the live UTEP–Oregon State card, then Ohio State Buckeyes vs
Oregon Ducks, and 4 of 8 cards were Ducks games. The multi-word recall ANDs the
words but lets each land on either side (`oregon` -> Oregon Ducks, `state` ->
Ohio State), so neither team was the one the reader named.

Now, when the TEAMS card's leader owns every query word, a game whose words all
land on ONE side sorts above the status tier's split rows — a Ducks game, live
or not, sits under every Beavers game. Recall is untouched: the split rows are
still served, below.

THE STRAWMAN removes the key: the fixture then reproduces the defect as
production served it at 04:2xZ, once the UTEP game had gone final — Ohio State
vs Oregon Ducks, the only upcoming game the words reach, heads the page above
every Oregon State game — so the case testifies.
THE CONTROLS: `ohio state oregon` names both sides of the Nov 7 game — no club
owns all three words, the key stays disarmed and that game is served first;
`oregon` (one word) serves the same order with and without the key.

WHY THE ROUTE AND POSTGRES: the arming reads the teams statement the route
runs first, and the order includes `ts_rank_cd`. SQLite serves neither.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9044 split-"
            "terms gate (CI job `search-recall` provides one)"
        ),
    ),
]

QUERY = "oregon state"
BEAVERS = "Oregon State Beavers"
DUCKS = "Oregon Ducks"
NCAAF = "americanfootball_ncaaf"

# (label, home, away, Eastern day offset, status). Kickoffs at 13:00 Eastern on
# their day, except the live pair, which kicked off two hours ago (gotcha #44:
# offset first, then fix the time — no branch on the clock).
SPECIMEN = [
    ("beavers_live", BEAVERS, "UTEP Miners", 0, "live"),
    ("beavers_final", "Colorado State Rams", BEAVERS, -7, "completed"),
    ("ducks_live", "Michigan State Spartans", DUCKS, 0, "live"),
    ("ducks_ok_state", "Oklahoma State Cowboys", DUCKS, 1, "scheduled"),
    ("ducks_ohio_state", "Ohio State Buckeyes", DUCKS, 3, "scheduled"),
    ("ducks_portland_state", DUCKS, "Portland State Vikings", -2, "completed"),
]
NAMED = ["beavers_live", "beavers_final"]
SPLIT = ["ducks_live", "ducks_ok_state", "ducks_ohio_state", "ducks_portland_state"]


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and the real database.

    Redis raises so the full-response cache is a miss, as in the sibling gates.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _seed(maker) -> dict[int, str]:
    from app.models.models import Event, Sport, Team

    eastern = ZoneInfo("America/New_York")
    now = datetime.now(timezone.utc)
    today = now.astimezone(eastern).date()
    ids: dict[int, str] = {}
    async with maker() as session:
        sport = Sport(key=NCAAF, name=NCAAF)
        session.add(sport)
        await session.flush()
        session.add_all([
            Team(sport_id=sport.id, name=BEAVERS, abbreviation="ORST"),
            Team(sport_id=sport.id, name=DUCKS, abbreviation="ORE"),
            Team(sport_id=sport.id, name="Ohio State Buckeyes", abbreviation="OSU"),
            Team(sport_id=sport.id, name="Oklahoma State Cowboys", abbreviation="OKST"),
        ])
        for label, home, away, day, status in SPECIMEN:
            if status == "live":
                kickoff = now - timedelta(hours=2)
            else:
                kickoff = datetime.combine(
                    today + timedelta(days=day), time(13, 0), tzinfo=eastern
                ).astimezone(timezone.utc)
            settled = status == "completed"
            row = Event(
                sport_id=sport.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=kickoff,
                status=status,
                home_score=3 if status != "scheduled" else None,
                away_score=2 if status != "scheduled" else None,
                completed_at=kickoff + timedelta(hours=3) if settled else None,
            )
            session.add(row)
            await session.flush()
            ids[row.id] = label
        await session.commit()
    return ids


def _labels(payload, ids) -> list[str]:
    """Served game cards, as specimen labels. The key is `results`."""
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [ids[int(e["id"])] for e in payload["results"] if int(e["id"]) in ids]


def _card_leads_with_the_beavers(payload) -> None:
    teams = [t.get("name") for t in payload.get("teams") or []]
    assert teams and teams[0] == BEAVERS, (
        "the specimen needs the TEAMS card to lead with Oregon State — otherwise "
        f"the key is not armed and this tests nothing: {teams}"
    )


def _disarm(monkeypatch) -> None:
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_split_terms_order_key", lambda *_: None)


async def test_every_oregon_state_game_leads_every_split_row(maker, search):
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_beavers(payload)

    labels = _labels(payload, ids)
    last_named = max(labels.index(label) for label in NAMED)
    first_split = min(labels.index(label) for label in SPLIT)
    assert last_named < first_split, (
        "a Ducks game whose words only split across both sides (`oregon` on the "
        f"Ducks, `state` on the opponent) still sits among Oregon State's: {labels}"
    )
    assert labels[: len(NAMED)] == NAMED, labels


async def test_without_the_key_ducks_games_sit_among_the_beavers(
    maker, search, monkeypatch,
):
    """Strawman: the fixture reproduces #9044 with the key removed."""
    _disarm(monkeypatch)
    ids = await _seed(maker)
    payload = await search(QUERY)
    _card_leads_with_the_beavers(payload)

    labels = _labels(payload, ids)
    assert labels.index("ducks_ohio_state") < labels.index("beavers_final"), labels
    assert labels.index("ducks_ok_state") < labels.index("beavers_final"), labels


async def test_a_matchup_query_keeps_the_game_it_names(maker, search):
    """Control: `ohio state oregon` names both sides — no club owns all three words."""
    ids = await _seed(maker)
    labels = _labels(await search("ohio state oregon"), ids)
    assert labels and labels[0] == "ducks_ohio_state", labels


async def test_a_one_word_query_is_unchanged(maker, search, monkeypatch):
    """Control: `oregon` serves the same order with and without the key."""
    ids = await _seed(maker)
    armed = _labels(await search("oregon"), ids)
    _disarm(monkeypatch)
    disarmed = _labels(await search("oregon"), ids)
    assert armed == disarmed and len(armed) == len(SPECIMEN), (armed, disarmed)


async def test_every_seeded_game_is_served(maker, search):
    """A key, never a filter: the split rows are sunk, not dropped."""
    ids = await _seed(maker)
    served = _labels(await search(QUERY), ids)
    assert sorted(served) == sorted(ids.values()), served
