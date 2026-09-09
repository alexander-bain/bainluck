"""Guard: the fold reaches the SERVED card, not just the helper (#4100).

`tests/test_event_twin_fold.py` proves the decision. This file proves the
delivery — that `_score_events` emits one card for the twin pair and that the
survivor's payload carries the venue that was stranded on the dropped row.

🔴 REAL `Event` OBJECTS, NOT MagicMock, AND THE TEST IS WORTHLESS WITHOUT THEM.
The union is applied with `sqlalchemy.orm.attributes.set_committed_value`, which
reaches through `_sa_instance_state`. On a MagicMock that whole call chain is
absorbed into auto-attributes: it raises nothing, does nothing, and the assertion
below would pass on a fold that never merged a thing. Detached declarative
instances are the cheapest thing that actually exercises it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.feed import _score_events
from app.utils.personalization import PersonalizationContext

MLB = Sport(id=1, key="baseball_mlb", name="MLB", group="Baseball", active=True)


def _event(id, *, away, home_score=None, away_score=None, espn_id=None, sources=None):
    e = Event(
        id=id,
        sport_id=MLB.id,
        home_team_name="San Francisco Giants",
        away_team_name=away,
        commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        status="live",
        home_score=home_score,
        away_score=away_score,
        espn_id=espn_id,
        external_id=f"ext-{id}" if espn_id else None,
        win_probability_sources=sources,
    )
    e.sport = MLB
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


async def _cards_for(rows):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db(rows), datetime.now(timezone.utc), None, PersonalizationContext()
        )
    return [i for i in items if i["type"] == "event"]


def _twin_pair():
    anchored = _event(
        15307210,
        away="St. Louis Cardinals",
        home_score=2,
        away_score=0,
        espn_id="401764128",
        sources={"betting": 0.76, "espn": 0.74, "mlb": 0.75},
    )
    kalshi = _event(15300848, away="St.Louis Cardinals", sources={"kalshi": 0.62})
    return anchored, kalshi


@pytest.mark.asyncio
async def test_one_game_one_card():
    cards = await _cards_for(list(_twin_pair()))
    assert [c["data"]["id"] for c in cards] == [15307210]


@pytest.mark.asyncio
async def test_the_served_card_carries_the_dropped_rows_venue():
    """Not "a card exists" — the blend. Before this fold the reader could see
    Kalshi's number only on a SECOND card that contradicted the first."""
    cards = await _cards_for(list(_twin_pair()))
    served = cards[0]["data"]["win_probability_sources"]
    assert "kalshi" in served, f"Kalshi was dropped with the row: {sorted(served)}"
    assert served["mlb"] == 0.75, "the survivor's own reading must not be overwritten"


@pytest.mark.asyncio
async def test_the_scoreless_twin_is_the_one_that_goes():
    """Direction guard. Serving 15300848 would put a live MLB game on the page
    with no score, which is the worse of the two cards Alex photographed."""
    cards = await _cards_for(list(_twin_pair()))
    # The length assertion is not decoration: without it this test passes
    # vacuously on an unfolded page, because `cards[0]` is the anchored row
    # either way and the fold's absence never shows.
    assert len(cards) == 1
    assert cards[0]["data"]["home_score"] == 2
    assert cards[0]["data"]["away_score"] == 0


@pytest.mark.asyncio
async def test_a_slate_of_distinct_games_is_untouched():
    """The fold must not thin a normal page. Nine real fixtures, none folded."""
    rows = [
        _event(i, away=f"Team {i}", home_score=1, away_score=0, espn_id=str(i))
        for i in range(1, 10)
    ]
    cards = await _cards_for(rows)
    assert {c["data"]["id"] for c in cards} == set(range(1, 10))
