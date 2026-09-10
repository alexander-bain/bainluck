"""#4771 — a push has a word now, and the page says it.

`PropsSection`'s `GradedValue` has had a muted `push` branch, and
`propResultLabel` has spelled it, for as long as either has existed. The BACKEND
builder spoke two words: `_build_props_script` mapped a bool onto "hit" or
"miss" and had no third arm.

So #1735's grader had to REFUSE an exact line rather than call it — "Over 7 runs
in the first 5 innings" with exactly 7 scored, or "Tampa Bay -5" on a five-run
window. Rendering either as "miss" would be a false verdict (nobody lost that
question), so the row stayed suppressed: honest, and the wrong end state for a
ship whose whole point is that a finished game shows its result.

## What these tests pin, read off the route

* the push ARRIVES as `graded_result: "push"` and `graded_label: "7 runs — push"`
  — composed by `_build_props_script`, in the site's one settled vocabulary;
* it arrives with **no price**, exactly as every other #1735 row does;
* an ordinary hit is untouched — the third arm is additive, not a re-route;
* a row with NO verdict still renders none. Inferring a push from `hit is None`
  would have turned every ungraded row on the page into a push, which is #1650's
  defect wearing a new label; the signal is its own key.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15308050

# The production line score for the specimen, verbatim. The first five innings
# are home 1, away 6: SEVEN combined runs, Tampa Bay by FIVE.
HOME_PERIODS = [0, 0, 0, 1, 0, 1, 0, 0, 0]  # Atlanta Braves
AWAY_PERIODS = [0, 3, 0, 3, 0, 0, 1, 0, 0]  # Tampa Bay Rays

PUSH_TOTAL = "Over 7 runs in the first 5 innings"      # exactly 7 scored
HIT_TOTAL = "Over 4.5 runs in the first 5 innings"     # the untouched control
PUSH_SPREAD = "Tampa Bay -5 first 5 innings"           # exactly a five-run margin
# A row #1735 refuses for a reason that has nothing to do with pushes: a lone
# "Yes" on a market whose line is nowhere on the row. It must keep rendering NO
# verdict — not a push — or the third word has swallowed the ungraded population.
UNGRADABLE = "Yes"


def _rays_at_braves_finished():
    event = _make_event(
        id=EVENT_ID,
        home_team="Atlanta Braves",
        away_team="Tampa Bay Rays",
        status="completed",
        sport_key="baseball_mlb",
        home_score=2,
        away_score=7,
    )
    event.llm_league = "MLB"
    event.period = None
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=10)
    event.completed_at = datetime.now(timezone.utc) - timedelta(hours=7)
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS,
        "away_period_scores": AWAY_PERIODS,
    }

    total = _make_futures_market(
        id=911, name="Tampa Bay vs Atlanta: First 5 Innings Total", source="kalshi"
    )
    spread = _make_futures_market(
        id=912, name="Tampa Bay vs Atlanta: First 5 Spread", source="kalshi"
    )
    lone_yes = _make_futures_market(
        id=913, name="Tampa Bay vs Atlanta: 1st Inning Total", source="kalshi"
    )
    for m in (total, spread, lone_yes):
        m.status = "open"
        m.event_id = EVENT_ID

    outcomes = [
        _make_outcome(id=9601, market_id=911, name=PUSH_TOTAL, probability=0.50),
        _make_outcome(id=9602, market_id=911, name=HIT_TOTAL, probability=0.50),
        _make_outcome(id=9603, market_id=912, name=PUSH_SPREAD, probability=0.50),
        _make_outcome(id=9604, market_id=913, name=UNGRADABLE, probability=0.50),
    ]
    return event, [total, spread, lone_yes], outcomes


@pytest.fixture
async def finished_client():
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves_finished()
    mock_session = _make_event_detail_session(
        event=event, futures=futures, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    _game_markets_cache.clear()


def _script(payload) -> dict:
    return {row["label"]: row for row in payload.get("props_script") or []}


def _all_served_outcome_names(payload) -> set:
    names = set()
    for bucket in ("totals", "player_props", "team_totals", "spreads",
                   "period_markets", "matchups", "other"):
        for row in payload.get(bucket) or []:
            if row.get("outcome_name"):
                names.add(row["outcome_name"])
    return names


@pytest.mark.asyncio
async def test_an_exactly_landed_total_renders_a_push(finished_client):
    """The ship: the row exists, and it says the true thing about itself."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    row = _script(payload).get(PUSH_TOTAL)

    assert row is not None, (
        "the exactly-landed total is still absent from WHAT HIT; "
        f"served: {sorted(_script(payload))}"
    )
    assert row["graded_result"] == "push", row
    assert row["graded_label"] == "7 runs — push", row


@pytest.mark.asyncio
async def test_an_exactly_covered_spread_renders_a_push(finished_client):
    """The second shape, and the one whose 'miss' would have been cruellest.

    Tampa Bay led the first five by exactly five and the line is exactly -5.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    row = _script(payload).get(PUSH_SPREAD)

    assert row is not None, f"served: {sorted(_script(payload))}"
    assert row["graded_result"] == "push", row
    assert row["graded_label"] == "6–1 — push", row


@pytest.mark.asyncio
async def test_the_push_brings_no_price_with_it(finished_client):
    """#1735's standing constraint holds for the third word too."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script(payload)

    for label in (PUSH_TOTAL, PUSH_SPREAD):
        assert script[label]["pregame_mark"] is None, script[label]
        assert script[label]["current"] is None, script[label]

    served = _all_served_outcome_names(payload)
    assert PUSH_TOTAL not in served, "the pushed row re-entered a price bucket"
    assert PUSH_SPREAD not in served, "the pushed row re-entered a price bucket"


@pytest.mark.asyncio
async def test_an_ordinary_verdict_is_untouched(finished_client):
    """Additive, not a re-route: the hit that already worked still says hit."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    row = _script(payload)[HIT_TOTAL]

    assert row["graded_result"] == "hit", row
    assert row["graded_label"] == "7 runs — hit", row


@pytest.mark.asyncio
async def test_an_ungraded_row_is_not_a_push(finished_client):
    """The #1650 direction: the third word must not swallow the ungraded.

    A lone "Yes" with the line nowhere on the row is one of #1735's fifty
    documented refusals. It has no verdict — `hit is None` — which is exactly
    the state a push also carries, and is why the push signal is its own key
    rather than an inference from a missing bool. If this row ever renders
    "push", every ungraded prop on the page has just been declared a tie.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    row = _script(payload).get(UNGRADABLE)

    if row is not None:
        assert row["graded_result"] != "push", row
        assert row["graded_result"] is None, row
        assert row["graded_label"] is None, row
