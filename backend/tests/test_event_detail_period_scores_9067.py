"""#9067 — the event payload serves the stored line score, only when it adds up.

Rage shake #159 (event 15315948, Georgia Tech @ Stanford, live): the iPhone's
Game Segments printed ``STAN 7 · 3 · 3`` beside a total of 19, because
``GET /api/events/{id}`` served ``box_score_data`` with ``players`` only and the
phone rebuilt each quarter from chart polling. The stored ESPN arrays were on the
row the whole time. Native's consumer (PR #9084) reads them under their stored
names; this file proves they reach the served JSON, and that a line score which
does NOT add up to the served score is withheld rather than reprinting the bug.

Specimens are production rows read 2026-09-27 (read-only db-query).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.served_period_scores import served_period_scores
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
)

# (home_score, away_score, home_periods, away_periods, label)
ADDS_UP = [
    (34, 27, [7, 3, 17, 7], [10, 10, 0, 7], "15315948 GT @ Stanford final"),
    (27, 20, [7, 3, 17, 0], [10, 10, 0, 0], "15315948 at 05:27Z, Q4 in progress"),
    (2, 4, [0, 0, 0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 1, 3, 0, 0], "9 innings"),
    (4, 1, [1, None, 2], [0, 1, 0], "a hole the venue left blank carries the rest"),
]

DOES_NOT_ADD_UP = [
    (21, 40, [7, 6, 8], [14, 9, 0], "15317788 FAMU — box froze in Q3"),
    (82, 100, [18, 18, 24, 20], [32, 33, 12, 14], "15318171 Mercury — froze 2 short"),
    (4, 3, [0, 0, 3, 0, 0], [1, 1, 1, 0, 0], "15314264 Rangers — shootout goal"),
    (34, 27, [7, 3, 17, 0], [10, 10, 0, 0], "15315948 box behind the scoreboard"),
    (27, 20, [10, 10, 0, 0], [7, 3, 17, 0], "arrays swapped against our sides"),
    (3, 1, [3, None, 2], [0, 1, 0], "recorded periods exceed the score"),
]


@pytest.mark.parametrize("home,away,hp,ap,label", ADDS_UP, ids=[s[4] for s in ADDS_UP])
def test_a_line_score_that_adds_up_is_served_verbatim(home, away, hp, ap, label):
    box = {"players": [], "home_period_scores": hp, "away_period_scores": ap}
    assert served_period_scores(box, home, away) == {
        "home_period_scores": hp,
        "away_period_scores": ap,
    }, label


@pytest.mark.parametrize(
    "home,away,hp,ap,label", DOES_NOT_ADD_UP, ids=[s[4] for s in DOES_NOT_ADD_UP]
)
def test_a_line_score_that_does_not_add_up_is_withheld(home, away, hp, ap, label):
    box = {"players": [], "home_period_scores": hp, "away_period_scores": ap}
    assert served_period_scores(box, home, away) is None, label


@pytest.mark.parametrize(
    "box,home,away",
    [
        (None, 1, 0),
        ({"players": []}, 1, 0),
        ({"home_period_scores": [1], "away_period_scores": [0]}, None, 0),
        ({"home_period_scores": [1], "away_period_scores": [0]}, 1, None),
        ({"home_period_scores": [], "away_period_scores": []}, 0, 0),
        ({"home_period_scores": [1, 0], "away_period_scores": [0]}, 1, 0),
        ({"home_period_scores": [1, "0"], "away_period_scores": [0, 0]}, 1, 0),
        ({"home_period_scores": [True], "away_period_scores": [0]}, 1, 0),
        ({"home_period_scores": [1.0], "away_period_scores": [0]}, 1, 0),
    ],
)
def test_a_malformed_line_score_is_withheld(box, home, away):
    assert served_period_scores(box, home, away) is None


# ── The served payload ──────────────────────────────────────────────────────


async def _payload(event):
    from app.main import app
    from app.routes.events import _event_detail_cache

    _event_detail_cache.clear()
    session = _make_event_detail_session(event=event)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(f"/api/events/{event.id}")
        assert response.status_code == 200, response.text[:500]
        return response.json()
    finally:
        app.dependency_overrides.clear()


def _event(home_score, away_score, hp, ap, status="live"):
    event = _make_event(
        id=15315948, status=status, home_score=home_score, away_score=away_score
    )
    event.box_score_data = {
        "source": "espn",
        "players": [{"name": "Haynes King", "team": "Georgia Tech", "passing_yards": 212}],
        "scoring_plays": [{"text": "not served"}],
        "home_period_scores": hp,
        "away_period_scores": ap,
    }
    return event


@pytest.mark.asyncio
async def test_the_live_specimen_serves_its_line_score_beside_players():
    served = (await _payload(_event(27, 20, [7, 3, 17, 0], [10, 10, 0, 0])))[
        "box_score_data"
    ]
    assert served["home_period_scores"] == [7, 3, 17, 0]
    assert served["away_period_scores"] == [10, 10, 0, 0]
    assert served["players"][0]["name"] == "Haynes King"
    # Only the line score was added — the rest of the stored box stays private.
    assert set(served) == {"players", "home_period_scores", "away_period_scores"}


@pytest.mark.asyncio
async def test_the_final_specimen_serves_its_line_score():
    served = (
        await _payload(_event(34, 27, [7, 3, 17, 7], [10, 10, 0, 7], status="completed"))
    )["box_score_data"]
    assert served["home_period_scores"] == [7, 3, 17, 7]
    assert served["away_period_scores"] == [10, 10, 0, 7]


@pytest.mark.asyncio
async def test_a_box_behind_the_scoreboard_serves_players_and_no_line_score():
    """The reader's complaint, from the server: Stanford has 34, the box says 27."""
    payload = await _payload(_event(34, 27, [7, 3, 17, 0], [10, 10, 0, 0]))
    served = payload["box_score_data"]
    assert payload["home_score"] == 34
    assert "home_period_scores" not in served
    assert "away_period_scores" not in served
    assert served["players"][0]["name"] == "Haynes King"
