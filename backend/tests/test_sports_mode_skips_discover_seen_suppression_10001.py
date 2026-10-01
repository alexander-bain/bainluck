"""Guard: Discover's seen/dismiss suppression never deletes a game from Sports (#10001).

Alex opened iPhone Sports at 04:30–04:42Z 10/1 and tonight's MLB playoff games
were not there. The settling read (issue comment 5927336845) found each of the
five in his own `discover_interactions`: a native Discover `impression` at
03:10–03:26Z, and a left-swipe (`unlike`, a dismissal) on two of them —
CHC@SD 15321946 while it was LIVE, and CWS@HOU 15321836. `_score_events` read
those sets on every request, `mode=sports` included, so the scoreboard dropped
every game he had scrolled past on the swipe deck (48h) and every game he had
swiped (14 days, live or not). KBO, ATP Japan Open and regular-season NHL had
no such rows, so they were what was left.

Both directions are asserted: on `mode=sports` the same rows are served, and on
Discover (default mode) they are still suppressed exactly as before — #10001's
acceptance forbids silently changing Discover's own dismissal behaviour. The
route test proves the flag is actually wired from `mode=sports`; without it the
scorer tests would pass over a parameter no request ever sets.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.routes.feed as feed_mod
from app.routes.feed import _score_events
from app.utils.personalization import PersonalizationContext

NOW = datetime.now(timezone.utc)

SEEN_SCHEDULED = 15322407  # PHI@ATL G3 — impression only
SEEN_COMPLETED = 15321907  # BOS@NYY — impression only, final
DISMISSED_LIVE = 15321946  # CHC@SD — swiped while live
DISMISSED_COMPLETED = 15321836  # CWS@HOU — swiped, final
SEEN_LIVE = 15322638  # seen but live: the seen arm already spares live rows
UNTOUCHED = 15321661  # control: no interaction at all
STUCK_LIVE = 15300001  # "live" 9h after first pitch — a separate guard


def _sport():
    s = MagicMock()
    s.key = "baseball_mlb"
    s.name = "MLB"
    return s


def _event(event_id: int, status: str, *, started_hours_ago: float = 1.0):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = NOW - timedelta(hours=started_hours_ago)
    e.home_team_id = event_id * 10 + 1
    e.away_team_id = event_id * 10 + 2
    e.home_team_name = f"Home {event_id}"
    e.away_team_name = f"Away {event_id}"
    e.opening_home_probability = 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {"betting": {"home_probability": 0.55}}
    e.opening_home_spread = -1.5
    e.opening_over_under = 8.5
    e.opening_favorite = e.home_team_name
    e.llm_importance = "playoff"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.statpal_end_time = None
    e.completed_at = (
        NOW - timedelta(hours=started_hours_ago - 3.0) if status == "completed" else None
    )
    e.period = None
    e.raw_ei = 70.0
    e.ei_metadata = None
    e.home_score = 3 if status != "scheduled" else None
    e.away_score = 2 if status != "scheduled" else None
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


def _events():
    return [
        _event(SEEN_SCHEDULED, "scheduled", started_hours_ago=-1.0),
        _event(SEEN_COMPLETED, "completed", started_hours_ago=3.0),
        _event(DISMISSED_LIVE, "live"),
        _event(DISMISSED_COMPLETED, "completed", started_hours_ago=3.0),
        _event(SEEN_LIVE, "live"),
        _event(UNTOUCHED, "scheduled", started_hours_ago=-2.0),
        _event(STUCK_LIVE, "live", started_hours_ago=9.0),
    ]


def _alex_ctx() -> PersonalizationContext:
    ctx = PersonalizationContext()
    ctx.recent_seen_event_ids = {
        SEEN_SCHEDULED,
        SEEN_COMPLETED,
        DISMISSED_LIVE,
        DISMISSED_COMPLETED,
        SEEN_LIVE,
    }
    ctx.recent_dismissed_event_ids = {DISMISSED_LIVE, DISMISSED_COMPLETED}
    return ctx


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _served_ids(**kwargs) -> set[int]:
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db(_events()), NOW, None, _alex_ctx(), **kwargs
        )
    return {i["data"]["id"] for i in items if i["type"] == "event"}


@pytest.mark.asyncio
async def test_sports_serves_the_games_a_reader_scrolled_past_or_swiped_on_discover():
    ids = await _served_ids(sports_mode=True)
    missing = {
        SEEN_SCHEDULED,
        SEEN_COMPLETED,
        DISMISSED_LIVE,
        DISMISSED_COMPLETED,
    } - ids
    assert not missing, (
        f"Sports dropped {sorted(missing)} because the reader saw or swiped them "
        "on Discover — #10001: Alex's playoff games vanished from Sports this way"
    )
    assert {SEEN_LIVE, UNTOUCHED} <= ids


@pytest.mark.asyncio
async def test_discover_still_suppresses_them__the_control():
    """Same rows, same context, default mode. Proves the rows above are scored
    when allowed (the Sports test is not green on an unscorable fixture) and that
    Discover's own suppression is untouched."""
    ids = await _served_ids()
    assert SEEN_SCHEDULED not in ids
    assert SEEN_COMPLETED not in ids
    assert DISMISSED_LIVE not in ids, "a Discover swipe still hides a live game there"
    assert DISMISSED_COMPLETED not in ids
    assert SEEN_LIVE in ids, "the seen arm still spares a live game on Discover"
    assert UNTOUCHED in ids


@pytest.mark.asyncio
async def test_sports_keeps_the_stuck_live_guard():
    """The exemption covers the two interaction sets only. A row still marked
    live 9h after first pitch is dropped on Sports exactly as before."""
    assert STUCK_LIVE not in await _served_ids(sports_mode=True)
    assert STUCK_LIVE not in await _served_ids()


@pytest.fixture
async def recording_feed_client(monkeypatch):
    """The real route over a mocked DB, with `_score_events` recording the
    `sports_mode` each request hands it."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw
    from app.utils.principal_independent_cache import clear_shared_builds

    clear_shared_builds()
    calls: list = []

    async def _recording(*a, **kw):
        calls.append(kw.get("sports_mode", "ABSENT"))
        return []

    async def _none(*a, **kw):
        return []

    monkeypatch.setattr(feed_mod, "_score_events", _recording)
    monkeypatch.setattr(feed_mod, "_score_golf_tournaments", _none)
    monkeypatch.setattr(feed_mod, "_score_event_concepts", _none)

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    session.execute.return_value = result

    async def _mock_get_db():
        yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, calls
    app.dependency_overrides.clear()
    clear_shared_builds()


@pytest.mark.asyncio
async def test_the_route_hands_sports_mode_to_the_scorer(recording_feed_client):
    client, calls = recording_feed_client
    resp = await client.get(
        "/api/feed",
        params={"mode": "sports", "limit": 50},
        headers={"x-session-id": "t10001-sports"},
    )
    assert resp.status_code == 200, resp.text
    assert calls == [True], f"mode=sports reached the scorer as {calls}"

    calls.clear()
    resp = await client.get(
        "/api/feed",
        params={"limit": 50, "include_futures": "false"},
        headers={"x-session-id": "t10001-discover"},
    )
    assert resp.status_code == 200, resp.text
    assert calls == [False], f"Discover reached the scorer as {calls}"
