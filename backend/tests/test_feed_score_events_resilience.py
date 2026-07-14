"""Guard: one malformed event must never wipe the whole event feed (#1091).

Regression context: `be747c13` (#187) was blamed for the empty Sports tab, but
the real cause was that `_score_events` had no per-event error guard. A single
malformed row (e.g. a duplicate event with bad data from #1085 — external_id
None esports/NCAA-baseball dups) would raise mid-loop and abort scoring for ALL
events, so `/api/feed` returned zero `type=="event"` cards while thousands of
live games existed. Golf tournaments and UFC/F1 concepts survived because they
are scored in independent try/except blocks — matching the production symptom
("events gone, tournaments still appear").

This test drives `_score_events` directly with one good live event and one
poison event and asserts the good event still surfaces.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.personalization import PersonalizationContext


def _sport(key="basketball_nba", name="NBA"):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _make_event(
    id: int,
    *,
    home="Celtics",
    away="76ers",
    poison=False,
):
    e = MagicMock()
    e.id = id
    e.status = "live"
    e.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    e.home_team_id = 10 + id
    e.away_team_id = 20 + id
    e.home_team_name = home
    e.away_team_name = away
    # A poison row carries an unparseable probability so float() raises mid-loop.
    e.opening_home_probability = "not-a-number" if poison else 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {"betting": {"home_probability": 0.55}}
    e.opening_home_spread = -3.5
    e.opening_over_under = 210.0
    e.opening_favorite = home
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.statpal_end_time = None
    e.period = None
    e.raw_ei = 70.0
    e.ei_metadata = None
    e.home_score = 55
    e.away_score = 52
    e.external_id = f"ext-{id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


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


@pytest.mark.asyncio
async def test_poison_event_does_not_wipe_the_feed():
    now = datetime.now(timezone.utc)
    ctx = PersonalizationContext()
    good = _make_event(1, home="Celtics", away="76ers")
    poison = _make_event(2, home="Yankees", away="Red Sox", poison=True)

    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        # Poison first: proves the loop keeps going past the failing row.
        items = await _score_events(_mock_db([poison, good]), now, None, ctx)

    ids = {i["data"]["id"] for i in items if i["type"] == "event"}
    assert 1 in ids, f"good event dropped by poison neighbor — feed wiped: {ids}"
    assert 2 not in ids, "poison event should have been skipped, not scored"


@pytest.mark.asyncio
async def test_all_good_events_survive():
    now = datetime.now(timezone.utc)
    ctx = PersonalizationContext()
    events = [_make_event(i, home=f"Home{i}", away=f"Away{i}") for i in (1, 2, 3)]

    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(_mock_db(events), now, None, ctx)

    ids = {i["data"]["id"] for i in items if i["type"] == "event"}
    assert ids == {1, 2, 3}, f"expected all 3 events, got {ids}"
