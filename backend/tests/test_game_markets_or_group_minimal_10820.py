"""#10820: the game-markets build drops OR-group name patterns that cannot decide a match.

Each side of the unlinked sweep and the Polymarket parent lookup is
``name ILIKE '%p1%' OR name ILIKE '%p2%' ...``. ``_team_name_patterns`` emits the
full name beside its parts, so ``'%Utah State Aggies%'`` sat next to ``'%Utah%'``:
it can never admit a row ``'%Utah%'`` does not, and it was the costliest probe
(production EXPLAIN ANALYZE, live 15324058: 900 + 1,242 ms of the parent lookup's
2,424 ms). These guards pin (a) that dropping is answer-identical, on real team
names, and (b) that the statements the route executes carry the minimal groups.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.dependencies.auth import get_optional_user
from app.routes.events import _or_group_minimal_patterns, _team_name_patterns
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_futures_market,
)


def _group(name):
    return [p for p in _team_name_patterns(name) if len(p) >= 4]


# ── the helper ──────────────────────────────────────────────────────────────


def test_the_full_name_and_its_supersets_go():
    assert _or_group_minimal_patterns(_group("Utah State Aggies")) == ["Aggies", "Utah"]
    assert _or_group_minimal_patterns(_group("Washington State Cougars")) == [
        "Cougars",
        "Washington",
    ]
    assert _or_group_minimal_patterns(_group("Texas Rangers")) == ["Rangers", "Texas"]


def test_a_group_with_nothing_redundant_is_untouched():
    assert _or_group_minimal_patterns(["Athletics"]) == ["Athletics"]
    assert _or_group_minimal_patterns(["Rangers", "Texas"]) == ["Rangers", "Texas"]


def test_an_escaped_pattern_is_never_dropped_or_used_to_drop():
    # `A\_B` is the text "A_B"; whether "A\_B Club" contains it is not a question
    # about the escaped strings, so neither side moves.
    assert _or_group_minimal_patterns(["A\\_B Club", "A\\_B"]) == ["A\\_B Club", "A\\_B"]
    assert _or_group_minimal_patterns(["Club", "A\\_B Club"]) == ["Club", "A\\_B Club"]


def test_duplicates_and_empty_patterns_cannot_empty_a_group():
    assert _or_group_minimal_patterns(["Utah", "Utah"]) == ["Utah"]
    assert _or_group_minimal_patterns(["", "Utah State"]) == ["", "Utah State"]


TEAMS = [
    "Utah State Aggies", "Washington State Cougars", "Washington Huskies",
    "Iowa Hawkeyes", "Texas Rangers", "Los Angeles Dodgers", "New York Yankees",
    "Kansas City Chiefs", "Arkansas State Red Wolves", "Boston Red Sox",
    "Real Sociedad", "Leeds United", "Atlético Madrid", "Puebla", "León",
    "San Jose State Spartans", "Wyoming Cowboys", "Tampa Bay Lightning",
]
NAMES = [
    "Utah State vs Washington State: Total Points",
    "Will Utah win by over 7.5?", "Aggies vs Cougars spread",
    "Washington Huskies at Iowa Hawkeyes", "Utah State Aggies Winner",
    "Texas Rangers vs Boston Red Sox", "Rangers first inning run",
    "Kansas City Chiefs vs Los Angeles Dodgers", "Red Wolves O/U",
    "Atlético Madrid v Real Sociedad", "Puebla v León", "Leeds to win",
    "San Jose State at Wyoming", "Lightning vs Rangers", "utah state lowercase",
]


@pytest.mark.parametrize("team", TEAMS)
def test_the_minimal_group_admits_exactly_what_the_full_group_admits(team):
    full = _group(team)
    minimal = _or_group_minimal_patterns(full)

    def admits(group, name):  # ILIKE '%p%' on unescaped literal patterns
        return any(p.lower() in name.lower() for p in group)

    probe = NAMES + [p + " extra" for p in full] + [p.upper() for p in full]
    for name in probe:
        assert admits(minimal, name) == admits(full, name), (team, name, full, minimal)


# ── the route executes the minimal groups ──────────────────────────────────


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


def _ilike_params(stmt):
    params = stmt.compile(dialect=postgresql.dialect()).params
    return sorted(v for v in params.values() if isinstance(v, str) and v.startswith("%"))


async def _run_build(event, linked):
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    seen: dict[str, list[str]] = {}

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "odds_snapshots" in s or "futures_outcomes" in s:
            return _result([])
        if "futures_markets" in s:
            if "futures_markets.group_id is not null" in s:
                seen["poly_parent"] = _ilike_params(stmt)
                return _result([])
            if "futures_markets.event_id is null" in s:
                seen["unlinked"] = _ilike_params(stmt)
                return _result([])
            return _result(linked)
        if "events" in s:
            r = _result([event])
            r.scalar_one_or_none.return_value = event
            return r
        return _result([])

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute)

    async def _db():
        yield session

    async def _user():
        return None

    _game_markets_cache.clear()
    _event_detail_cache.clear()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{event.id}/game-markets")
    finally:
        _game_markets_cache.clear()
        _event_detail_cache.clear()
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return seen


@pytest.mark.asyncio
async def test_both_name_sweeps_carry_only_the_minimal_groups():
    event = _make_event(
        id=15324058, home_team="Utah State Aggies", away_team="Washington State Cougars",
        status="live", sport_key="americanfootball_ncaaf",
    )
    event.commence_time = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    event.sport.key = "americanfootball_ncaaf"
    linked = _make_futures_market(
        id=1, name="Utah State vs Washington State Winner", source="kalshi",
        sport_category="football",
    )
    linked.event_id = 15324058

    seen = await _run_build(event, [linked])

    # Strawman: both sweeps were reached, or the assertions below say nothing.
    assert set(seen) == {"poly_parent", "unlinked"}, seen
    expected = sorted(["%Aggies%", "%Utah%", "%Cougars%", "%Washington%"])
    assert seen["poly_parent"] == expected, seen["poly_parent"]
    assert seen["unlinked"] == expected, seen["unlinked"]
