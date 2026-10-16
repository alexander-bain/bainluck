"""#2316: the step-5 outcome lookup the related-futures build executes lowers
each row's name once, and still carries every pattern.

Step 5 used to OR one `futures_outcomes.name ILIKE '%p%'` per pattern, every
roster player included; on UTF8 each arm lowercases the row again, and a 210-arm
college-football build ran past a 25 s statement timeout on production. The
equality of the new form is graded by a real server in
`test_ilike_any_lowered_once_2316_pg.py`; this pins that the route uses it, on
the statement it actually executes, with the roster arms still present.

Step 5 is recognised by the market-name subquery it keeps (`futures_markets.name
ILIKE`), which the old and the new statement both carry — so reverting the
route to the OR form fails the first assertion, not the recogniser.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_related_futures import (
    _MockResult,
    _make_event,
    _make_related_futures_session,
)

pytestmark = pytest.mark.anyio

_HOME, _AWAY = "Boston Celtics", "Philadelphia 76ers"
_ROSTER = ["Jayson Tatum", "Jaylen Brown", "Derrick White"]


@pytest.fixture(autouse=True)
def _clear_memo():
    from app.routes import events as events_route

    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


def _params(stmt) -> dict:
    return stmt.compile(dialect=postgresql.dialect()).params


async def _run_route(status: str):
    from app.main import app

    event = _make_event(id=2316, home_team=_HOME, away_team=_AWAY, status=status)
    session = _make_related_futures_session(event)
    inner = session.execute.side_effect
    step5: list = []

    async def recording(stmt, *a, **k):
        # The PostgreSQL dialect: bare `str()` renders `ilike` as `lower() LIKE`.
        sql = (
            str(stmt.compile(dialect=postgresql.dialect())).lower()
            if hasattr(stmt, "compile")
            else ""
        )
        if "from futures_outcomes" in sql and "futures_markets.name ilike" in sql:
            step5.append(stmt)
        if "from teams" in sql and "roster_players" in sql and "teams.id" in sql:
            if _HOME in _params(stmt).values():
                return _MockResult(
                    first=SimpleNamespace(
                        id=77, alternate_names=[], roster_players=[{"name": n} for n in _ROSTER]
                    )
                )
        return await inner(stmt, *a, **k)

    session.execute = AsyncMock(side_effect=recording)

    async def _db():
        yield session

    async def _user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.services.llm.generate_related_futures_summary", return_value=""),
            patch(
                "app.services.league_context.enrich_event_with_context",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/events/2316/related-futures")
    finally:
        app.dependency_overrides.clear()
    return resp, step5


async def test_step5_lowers_each_name_once_and_keeps_the_roster_arms(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.routes.events import _team_name_patterns

    resp, step5 = await _run_route("live")

    assert resp.status_code == 200, resp.text
    assert len(step5) == 1, step5  # strawman: step 5 ran, so the rest says something
    sql = str(step5[0].compile(dialect=postgresql.dialect()))
    assert "futures_outcomes.name ILIKE" not in sql, sql
    assert sql.count("lower(futures_outcomes.name) LIKE ANY (CAST((SELECT ARRAY[") == 1, sql

    expected = (
        [f"%{p}%" for p in _team_name_patterns(_HOME)]
        + [f"%{n}%" for n in _ROSTER]
        + [f"%{p}%" for p in _team_name_patterns(_AWAY)]
    )
    compiled = step5[0].compile(dialect=postgresql.dialect())
    array_sql = sql.split("SELECT ARRAY[", 1)[1].split("]", 1)[0]
    array_keys = [part.split("%(", 1)[1].split(")s", 1)[0] for part in array_sql.split(", ")]
    assert [compiled.params[k] for k in array_keys] == expected


async def test_a_finished_game_still_matches_on_team_names_only(monkeypatch):
    """Roster names stay out of a finished game's patterns, as before #2316."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.routes.events import _team_name_patterns

    resp, step5 = await _run_route("completed")

    assert resp.status_code == 200, resp.text
    assert len(step5) == 1, step5
    compiled = step5[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "futures_outcomes.name ILIKE" not in sql, sql
    array_sql = sql.split("SELECT ARRAY[", 1)[1].split("]", 1)[0]
    array_keys = [part.split("%(", 1)[1].split(")s", 1)[0] for part in array_sql.split(", ")]
    assert [compiled.params[k] for k in array_keys] == [
        f"%{p}%" for p in _team_name_patterns(_HOME) + _team_name_patterns(_AWAY)
    ]
