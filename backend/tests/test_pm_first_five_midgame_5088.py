"""#5088 — Polymarket's First-5 questions get their result when the fifth ends.

## What a reader saw

ux, 02:03Z 10/1, `/events/15321907` Red Sox @ Yankees (Wild Card). At Top 4th
the page drew the **First 5 innings runs map**. By Top 6th it was gone:
`period_markets` was `[]` and the payload held no "First 5" anywhere. The first
five finished 2–0 (combined 2 runs) against lines of 2.5 … 6.5, and the reader
never saw that — the question left the page the moment it was answered.

## Why

Every First-5 market on that page was Polymarket's (14 legs: five `O/U` lines and
two spreads, read from production), and Polymarket puts the LINE in the market
name:

    "Boston Red Sox vs. New York Yankees: 1st 5 Innings O/U 2.5" / "Under"
    "1st 5 Innings Spread: New York Yankees (-1.5)"            / "Boston Red Sox"

#1588 correctly suppresses each leg once the fifth is over. `grade_period_window`
then refused every one, because it reads the line from the OUTCOME ("Under 2.5",
"Tampa Bay -1.5", Kalshi's shapes). Nothing replaced the suppressed rows.

## What these tests pin

* mid-game (Top 6th) the legs arrive in `props_script` graded off the line score,
  with the line written into the label so five "Under" rungs read as five;
* the verdicts equal the venue's own settlement of the same markets (production:
  `Under` won on all five lines; NYY −1.5 and NYY +1.5 won);
* a window still being played is not graded (the fifth, at Top 5th);
* the price does not come back with the verdict.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.period_window_grade import grade_period_window, window_outcome_label
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15321907
HOME = "New York Yankees"
AWAY = "Boston Red Sox"

# Production line score for 15321907, verbatim (box_score_data, read 08:1xZ 10/1).
# First five: home 2, away 0 — combined 2.
HOME_PERIODS = [0, 0, 0, 1, 1, 6, 1, 0]
AWAY_PERIODS = [0, 0, 0, 0, 0, 1, 1, 0, 0]

OU = "Boston Red Sox vs. New York Yankees: 1st 5 Innings O/U {line}"
SPREAD_NYY = "1st 5 Innings Spread: New York Yankees (-1.5)"
SPREAD_BOS = "1st 5 Innings Spread: Boston Red Sox (-1.5)"
LINES = ("2.5", "3.5", "4.5", "5.5", "6.5")


def _bos_at_nyy(status: str, period: str | None, line_score_through: int = 9):
    event = _make_event(
        id=EVENT_ID, home_team=HOME, away_team=AWAY, status=status,
        sport_key="baseball_mlb", home_score=2, away_score=0,
    )
    event.llm_league = "MLB"
    event.period = period
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=2)
    event.completed_at = None
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS[:line_score_through],
        "away_period_scores": AWAY_PERIODS[:line_score_through],
    }

    markets, outcomes = [], []
    oid = 1000

    def _market(mid, name):
        m = _make_futures_market(id=mid, name=name, source="polymarket")
        m.status = "open"
        m.event_id = EVENT_ID
        markets.append(m)
        return m

    # Prices as an unsettled venue would quote them mid-game: near the answer,
    # but the venue has not resolved yet (no `resolution_source`).
    for i, line in enumerate(LINES):
        m = _market(63382763 + i, OU.format(line=line))
        oid += 2
        outcomes.append(_make_outcome(id=oid, market_id=m.id, name="Over", probability=0.03))
        outcomes.append(_make_outcome(id=oid + 1, market_id=m.id, name="Under", probability=0.97))
    for mid, name, fav in ((63434311, SPREAD_NYY, HOME), (63434312, SPREAD_BOS, AWAY)):
        m = _market(mid, name)
        oid += 2
        dog = AWAY if fav == HOME else HOME
        outcomes.append(_make_outcome(id=oid, market_id=mid, name=fav, probability=0.9 if fav == HOME else 0.02))
        outcomes.append(_make_outcome(id=oid + 1, market_id=mid, name=dog, probability=0.1 if fav == HOME else 0.98))
    return event, markets, outcomes


async def _payload(status: str, period: str | None, line_score_through: int = 9):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _bos_at_nyy(status, period, line_score_through)
    mock_session = _make_event_detail_session(event=event, futures=futures, outcomes=outcomes)

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/events/{EVENT_ID}/game-markets")
        return response.json()
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()


def _first_five_script_rows(payload) -> dict:
    return {
        r["label"]: r
        for r in (payload.get("props_script") or [])
        if "1st 5 Innings" in r["key"]
    }


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_five_ladder_is_graded_at_top_of_the_sixth():
    """The ship: the specimen's ten O/U legs arrive as ten results, not zero."""
    rows = _first_five_script_rows(await _payload("live", "Top 6th", line_score_through=6))

    for line in LINES:
        under, over = rows.get(f"Under {line}"), rows.get(f"Over {line}")
        assert under is not None and over is not None, (
            f"line {line}: the First-5 O/U legs left the page with no result; "
            f"served First-5 labels = {sorted(rows)}"
        )
        # The venue's own settlement of these markets (production): Under won.
        assert under["graded_result"] == "hit"
        assert under["graded_label"] == "2 runs — hit"
        assert over["graded_result"] == "miss"
        assert under["settled"] is True and over["settled"] is True


@pytest.mark.asyncio
async def test_the_first_five_spreads_are_graded_with_the_line_on_the_right_club():
    """A spread's line belongs to the club the MARKET names; the other leg is +.

    2–0 Yankees through five: NYY −1.5 covers (margin 0.5), so BOS +1.5 misses;
    on the BOS −1.5 market, BOS −1.5 misses and NYY +1.5 hits. Production's
    settlement of 63434311 / 63434312 says exactly that.
    """
    rows = _first_five_script_rows(await _payload("live", "Top 6th", line_score_through=6))

    assert rows["New York Yankees -1.5"]["graded_result"] == "hit"
    assert rows["Boston Red Sox +1.5"]["graded_result"] == "miss"
    assert rows["Boston Red Sox -1.5"]["graded_result"] == "miss"
    assert rows["New York Yankees +1.5"]["graded_result"] == "hit"
    assert rows["New York Yankees -1.5"]["graded_label"] == "0–2 — hit"  # away–home


@pytest.mark.asyncio
async def test_the_fifth_is_not_graded_while_it_is_being_played():
    """The guardrail on the same fixture: at Top 5th no First-5 leg is a result.

    "No verdict" alone would pass on a page that dropped the legs entirely, so
    the open window must still be on the page as the live question it is — all
    14 legs priced in `period_markets` — while none is graded.
    """
    payload = await _payload("live", "Top 5th", line_score_through=5)
    rows = _first_five_script_rows(payload)

    graded = {label: r["graded_result"] for label, r in rows.items() if r["graded_result"]}
    assert graded == {}, f"graded a window still being played: {graded}"
    open_legs = [r for r in payload["period_markets"] if "1st 5 Innings" in r["market_name"]]
    assert len(open_legs) == 14, f"the open First-5 window left the page: {open_legs}"


@pytest.mark.asyncio
async def test_the_verdict_carries_no_price():
    rows = _first_five_script_rows(await _payload("live", "Top 6th", line_score_through=6))
    row = rows["Under 2.5"]
    assert row["current"] is None
    assert row["pregame_mark"] is None


# ---------------------------------------------------------------------------
# The label helper
# ---------------------------------------------------------------------------


class TestWindowOutcomeLabel:
    def test_a_bare_over_under_takes_the_markets_line(self):
        assert window_outcome_label(OU.format(line="2.5"), "Under", HOME, AWAY) == "Under 2.5"
        assert window_outcome_label(OU.format(line="6.5"), "over", HOME, AWAY) == "Over 6.5"

    def test_the_spread_leg_of_the_other_club_takes_the_opposite_sign(self):
        assert window_outcome_label(SPREAD_NYY, HOME, HOME, AWAY) == "New York Yankees -1.5"
        assert window_outcome_label(SPREAD_NYY, AWAY, HOME, AWAY) == "Boston Red Sox +1.5"

    def test_an_outcome_that_already_carries_its_line_is_left_alone(self):
        # Kalshi's shapes — the grader already reads these.
        assert window_outcome_label("TB vs ATL: First 5 Innings Total", "Over 4.5", HOME, AWAY) is None
        assert window_outcome_label(SPREAD_NYY, "New York Yankees -1.5", HOME, AWAY) is None

    def test_a_bare_over_with_no_line_anywhere_is_refused(self):
        assert window_outcome_label("TB vs ATL: 1st Inning Total", "Over", HOME, AWAY) is None
        assert window_outcome_label("TB vs ATL: 1st Inning Total", "Yes", HOME, AWAY) is None

    def test_a_club_that_resolves_to_neither_side_is_refused(self):
        assert window_outcome_label(SPREAD_NYY, "Tampa Bay Rays", HOME, AWAY) is None
        assert window_outcome_label(
            "1st 5 Innings Spread: Tampa Bay Rays (-1.5)", HOME, HOME, AWAY
        ) is None

    def test_the_rewritten_label_grades_through_the_existing_shapes(self):
        """End to end on the helper's output: the grader's own Shape B / Shape D."""
        under = window_outcome_label(OU.format(line="2.5"), "Under", HOME, AWAY)
        assert grade_period_window(
            "inning", 1, 5, OU.format(line="2.5"), None, under,
            HOME_PERIODS, AWAY_PERIODS, HOME, AWAY,
        ) == {"actual": "2 runs", "hit": True}
        bos = window_outcome_label(SPREAD_NYY, AWAY, HOME, AWAY)
        assert grade_period_window(
            "inning", 1, 5, SPREAD_NYY, None, bos,
            HOME_PERIODS, AWAY_PERIODS, HOME, AWAY,
        ) == {"actual": "0–2", "hit": False}
