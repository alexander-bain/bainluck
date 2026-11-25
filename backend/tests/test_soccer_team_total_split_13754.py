"""#13754 — soccer named-team O/U markets route to team_totals, never game totals.

Live read of `/api/events/15342710/game-markets` (Atlético Madrid vs. Viking FK)
and 7 other Champions League games showed Polymarket titles of the form
``"A vs. B: <Team> O/U N"`` classifying as ``game_total`` and occupying
``totals[]`` rungs (e.g., ``Viking FK O/U 1.5`` at 14% sitting at 1.5+ ahead
of the full-game 1.5+ line, while ``team_totals[]`` stayed empty).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import _classify_game_market
from app.services.database import get_db, get_db_rw
from app.utils.game_market_class import classify_game_market_class, extract_ou_subject
from app.utils.game_nuggets import rank_game_nuggets
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

ATLETICO_EVENT_ID = 15342710

# Placed intentionally BEFORE the matching full-game lines so any regression
# putting them in `seen_thresholds` evicts the game line (e.g., 1.5+ -> 14%).
ATLETICO_TEAM_TOTALS = [
    (72128901, "Club Atlético de Madrid vs. Viking FK: Club Atlético de Madrid O/U 0.5", 0.952, 0.048),
    (72128928, "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 1.5", 0.14, 0.86),
    (72128929, "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 2.5", 0.0375, 0.9625),
    (72128930, "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 3.5", 0.027, 0.973),
    (72128931, "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 4.5", 0.025, 0.975),
    (72128932, "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 5.5", 0.025, 0.975),
]

ATLETICO_GAME_TOTALS = [
    (72129001, "Club Atlético de Madrid vs. Viking FK: O/U 0.5", 0.99, 0.01),
    (72129002, "Club Atlético de Madrid vs. Viking FK: O/U 1.5", 0.89, 0.11),
    (72129003, "Club Atlético de Madrid vs. Viking FK: O/U 2.5", 0.72, 0.28),
    (72129004, "Club Atlético de Madrid vs. Viking FK: O/U 3.5", 0.51, 0.49),
    (72129005, "Club Atlético de Madrid vs. Viking FK: O/U 4.5", 0.31, 0.69),
    (72129006, "Club Atlético de Madrid vs. Viking FK: O/U 5.5", 0.17, 0.83),
    (72129007, "Club Atlético de Madrid vs. Viking FK: O/U 6.5", 0.025, 0.975),
    (72129008, "Club Atlético de Madrid vs. Viking FK: O/U 7.5", 0.025, 0.975),
    (72129009, "Club Atlético de Madrid vs. Viking FK: O/U 8.5", 0.0195, 0.9805),
]


def _atletico_vs_viking_fixture():
    now = datetime.now(timezone.utc)
    event = _make_event(
        id=ATLETICO_EVENT_ID,
        home_team="Atlético Madrid",
        away_team="Viking FK",
        status="scheduled",
        sport_key="soccer_uefa_champs_league",
        home_score=None,
        away_score=None,
    )
    event.llm_league = "UEFA Champions League"
    event.commence_time = now + timedelta(hours=3)
    event.completed_at = None
    event.box_score_data = {"players": {}}

    futures = []
    outcomes = []
    oid = 950000
    for mid, title, over_p, under_p in ATLETICO_TEAM_TOTALS + ATLETICO_GAME_TOTALS:
        market = _make_futures_market(id=mid, name=title, source="polymarket")
        market.status = "open"
        market.event_id = ATLETICO_EVENT_ID
        market.commence_time = event.commence_time
        futures.append(market)

        for leg_name, prob in (("Over", over_p), ("Under", under_p)):
            oid += 1
            out = _make_outcome(id=oid, market_id=mid, name=leg_name, probability=prob)
            out.current_probability = prob
            out.observed_at = now - timedelta(minutes=5)
            outcomes.append(out)
    return event, futures, outcomes, now


@pytest.mark.asyncio
async def test_atletico_viking_routes_team_totals_out_of_game_totals_and_feeds_callers():
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes, now = _atletico_vs_viking_fixture()
    session = _make_event_detail_session(event=event, futures=futures, outcomes=outcomes)

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
                resp = await ac.get(f"/api/events/{ATLETICO_EVENT_ID}/game-markets")
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    totals = payload["totals"]
    assert [row["threshold"] for row in totals] == [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5]
    assert all(row["market_name"] == f"Club Atlético de Madrid vs. Viking FK: O/U {row['threshold']}" for row in totals)
    assert all("Viking FK O/U" not in row["market_name"] for row in totals)
    assert all("Atlético de Madrid O/U" not in row["market_name"] for row in totals)

    over_probs = [row["over_probability"] for row in totals]
    assert all(b <= a for a, b in zip(over_probs, over_probs[1:])), over_probs
    assert totals[1]["over_probability"] == pytest.approx(0.89, abs=1e-4)

    team_totals = payload["team_totals"]
    assert team_totals
    home_rungs = [r for r in team_totals if r.get("team_side") == "home" and r.get("outcome_name") == "Over"]
    away_rungs = [r for r in team_totals if r.get("team_side") == "away" and r.get("outcome_name") == "Over"]
    assert [(r["team_name"], r["threshold"]) for r in home_rungs] == [("Atlético Madrid", 0.5)]
    assert [(r["team_name"], r["threshold"]) for r in away_rungs] == [
        ("Viking FK", 1.5),
        ("Viking FK", 2.5),
        ("Viking FK", 3.5),
        ("Viking FK", 4.5),
        ("Viking FK", 5.5),
    ]
    assert away_rungs[0]["over_probability"] == pytest.approx(0.14, abs=1e-4)

    # Downstream readers (#13511 game nuggets + Game question matrix) consume clean lists.
    nuggets = rank_game_nuggets(
        event_info={
            "id": ATLETICO_EVENT_ID,
            "sport_key": "soccer_uefa_champs_league",
            "home_team_name": "Atlético Madrid",
            "away_team_name": "Viking FK",
            "status": "scheduled",
            "commence_time": (now + timedelta(hours=3)).isoformat(),
        },
        game_markets=payload,
        related_futures={},
        team_progression={},
        now=now,
    )
    assert nuggets["nuggets"]
    team_nuggets = [n for n in nuggets["nuggets"] if n["kind"] == "teams"]
    assert all("scores" not in n["claim"].lower() or "viking" in n["claim"].lower() or "atlético" in n["claim"].lower() for n in team_nuggets)

    matrix = payload.get("game_question_matrix")
    assert matrix is not None
    assert matrix["coverage"]["build_errors"] == 0
    matrix_questions = matrix.get("questions") or []
    assert sum(1 for q in matrix_questions if q.get("source_array") == "totals") == 9
    assert sum(1 for q in matrix_questions if q.get("source_array") == "team_totals") == 6


UCL_TEAM_OU_FIXTURES = [
    (
        15342704,
        "Sabah FK",
        "Barcelona",
        "Sabah FK vs. FC Barcelona: FC Barcelona O/U 2.5",
        "Sabah FK vs. FC Barcelona: O/U 2.5",
        "away",
    ),
    (
        15342705,
        "Slavia Praha",
        "Villarreal",
        "SK Slavia Praha vs. Villarreal CF: SK Slavia Praha O/U 2.5",
        "SK Slavia Praha vs. Villarreal CF: O/U 2.5",
        "home",
    ),
    (
        15342705,
        "Slavia Praha",
        "Villarreal",
        "SK Slavia Praha vs. Villarreal CF: Villarreal CF O/U 3.5",
        "SK Slavia Praha vs. Villarreal CF: O/U 3.5",
        "away",
    ),
    (
        15342706,
        "Lille",
        "Bayern Munich",
        "Lille OSC vs. FC Bayern München: Lille OSC O/U 0.5",
        "Lille OSC vs. FC Bayern München: O/U 0.5",
        "home",
    ),
    (
        15342710,
        "Atlético Madrid",
        "Viking FK",
        "Club Atlético de Madrid vs. Viking FK: Viking FK O/U 1.5",
        "Club Atlético de Madrid vs. Viking FK: O/U 1.5",
        "away",
    ),
    (
        15342711,
        "Club Brugge",
        "Liverpool",
        "Club Brugge KV vs. Liverpool FC: Liverpool FC O/U 1.5",
        "Club Brugge KV vs. Liverpool FC: O/U 1.5",
        "away",
    ),
    (
        15342712,
        "Shakhtar Donetsk",
        "Fenerbahce",
        "FK Shakhtar Donetsk vs. Fenerbahçe SK: Fenerbahçe SK O/U 5.5",
        "FK Shakhtar Donetsk vs. Fenerbahçe SK: O/U 5.5",
        "away",
    ),
    (
        15342714,
        "Sporting Lisbon",
        "Manchester United",
        "Sporting CP vs. Manchester United FC: Manchester United FC O/U 1.5",
        "Sporting CP vs. Manchester United FC: O/U 1.5",
        "away",
    ),
    (
        15343458,
        "Paris Saint-Germain FC",
        "AS Roma",
        "Paris Saint-Germain FC vs. AS Roma: Paris Saint-Germain FC O/U 0.5",
        "Paris Saint-Germain FC vs. AS Roma: O/U 0.5",
        "home",
    ),
]


@pytest.mark.parametrize(
    "event_id,home,away,team_title,game_title,expected_side",
    UCL_TEAM_OU_FIXTURES,
    ids=[f"{c[0]}:{c[5]}" for c in UCL_TEAM_OU_FIXTURES],
)
def test_all_champions_league_team_ou_titles_classify_as_team_total(
    event_id, home, away, team_title, game_title, expected_side
):
    assert _classify_game_market(team_title, "0xabc") == "team_total"
    assert _classify_game_market(game_title, "0xabc") == "game_total"
    assert classify_game_market_class(team_title, "0xabc", "soccer_uefa_champs_league") == "team_prop"
    assert classify_game_market_class(game_title, "0xabc", "soccer_uefa_champs_league") == "total"

    subj = extract_ou_subject(team_title)
    assert subj is not None
    expected_token = home if expected_side == "home" else away
    # Fold accents just as Step 7 does for Fenerbahçe / Atlético.
    from app.utils.game_market_class import fold_ascii

    subj_f = fold_ascii(subj)
    words = [w for w in fold_ascii(expected_token).split() if len(w) >= 4]
    assert any(w in subj_f for w in words), (subj_f, words)


def test_controls_and_fallback_attribution():
    assert _classify_game_market("Club Atlético de Madrid vs. Viking FK: 1st Half O/U 1.5") == "half_total"
    assert _classify_game_market("Club Atlético de Madrid vs. Viking FK: 1st Half Viking FK O/U 0.5") == "half_total"
    assert _classify_game_market("Atlético vs. Viking: Total Corners O/U 9.5") == "stat_total"
    assert _classify_game_market("Games Total: O/U 2.5") == "game_total"
    assert _classify_game_market("Celtics vs. Lakers: O/U 224.5") == "game_total"
    assert _classify_game_market("Celtics vs. Lakers: Celtics O/U 112.5") == "team_total"


@pytest.mark.asyncio
async def test_step7_fallback_catches_unprefixed_one_club_ou_title():
    """Even if a fixture row lacks ``A vs. B:`` so the title-only helper returns False,
    Step 7's event-team fallback routes ``Viking FK O/U 1.5`` to ``team_totals``."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, _f, _o, now = _atletico_vs_viking_fixture()
    unprefixed_market = _make_futures_market(
        id=72128999, name="Viking FK O/U 1.5", source="polymarket"
    )
    unprefixed_market.status = "open"
    unprefixed_market.event_id = ATLETICO_EVENT_ID
    unprefixed_market.commence_time = event.commence_time
    game_market = _make_futures_market(
        id=72129002, name="Club Atlético de Madrid vs. Viking FK: O/U 1.5", source="polymarket"
    )
    game_market.status = "open"
    game_market.event_id = ATLETICO_EVENT_ID
    game_market.commence_time = event.commence_time
    outcomes = [
        _make_outcome(id=959001, market_id=72128999, name="Over", probability=0.14),
        _make_outcome(id=959002, market_id=72129002, name="Over", probability=0.89),
    ]
    for o, p in zip(outcomes, (0.14, 0.89)):
        o.current_probability = p
        o.observed_at = now - timedelta(minutes=5)

    session = _make_event_detail_session(
        event=event, futures=[unprefixed_market, game_market], outcomes=outcomes
    )

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
                resp = await ac.get(f"/api/events/{ATLETICO_EVENT_ID}/game-markets")
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert len(payload["totals"]) == 1
    assert payload["totals"][0]["over_probability"] == pytest.approx(0.89, abs=1e-4)
    assert len(payload["team_totals"]) == 1
    assert payload["team_totals"][0]["team_side"] == "away"
    assert payload["team_totals"][0]["team_name"] == "Viking FK"
