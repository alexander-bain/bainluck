"""#5088 / T3-2 — a question the third inning answered stops waiting for the ninth.

## What a reader sees

`/events/15308050` mid-game, sixth inning in progress. The first five innings
finished 6–1 and every market bounded to them is over: "Tampa Bay wins first 5
innings", the four first-five spread rungs, the first-inning run question. Today
the page says nothing about any of them — #1588 correctly removes their stale
price, and the result that replaces it does not arrive until the final whistle.

## The three gates, and the order they had to be opened in

1. **The resolution input did not exist mid-game.** `_grade_closed_windows`
   reads `box_score_data.home_period_scores`, and
   `espn_helpers.fetch_live_box_scores` — the pass that runs every 60s over live
   events — read `context["box_score"]` and `context["scoring_plays"]` and
   dropped `context["scores"]`, which is where ESPN's line score is. Measured on
   production 2026-09-11: of 46 MLB events completed in the trailing four days
   carrying `box_score_data`, **46 have period scores and all 46 were fetched
   strictly after `completed_at`; zero at or before it.**
2. **The pass could not reach the games that needed it.** It took the 10 most
   recently STARTED live events, so the games furthest into themselves — the
   ones with the most closed windows — were exactly the tail it never read.
   Peak concurrent live ESPN-linked events over the trailing week: **54**, with
   42 of 166 live hours above 10.
3. **The route refused to compose a verdict before full time.** CERT-2535 gated
   the graded block on `event_is_finished` because a mid-game row would
   otherwise arrive blank in all four fields; the gate's own comment named this
   ship as what lifts it.

## The rule these tests pin

A window's result appears when the WINDOW ends, not when the game does — and an
inning that is still being played is never graded, whatever the line score
happens to contain. Those are the two halves of one fixture below, because a
test that only proves the first is a test that would pass on a grader with no
gate at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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

# The production line score for the specimen, verbatim (same source as #4845's
# fixture): innings 1..9, Atlanta home / Tampa Bay away.
HOME_PERIODS = [0, 0, 0, 1, 0, 1, 0, 0, 0]
AWAY_PERIODS = [0, 3, 0, 3, 0, 0, 1, 0, 0]
# First five: home 1, away 6.  Sixth inning alone: home 1, away 0.

FIRST_FIVE_TB = "Tampa Bay wins first 5 innings"
FIRST_FIVE_ATL = "Atlanta wins first 5 innings"
FIRST_FIVE_TIE = "Tie"
SIXTH_ATL = "Atlanta wins 6th inning"
SIXTH_TB = "Tampa Bay wins 6th inning"


def _rays_at_braves(status: str, period: str | None):
    event = _make_event(
        id=EVENT_ID,
        home_team="Atlanta Braves",
        away_team="Tampa Bay Rays",
        status=status,
        sport_key="baseball_mlb",
        home_score=2,
        away_score=7,
    )
    event.llm_league = "MLB"
    event.period = period
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=3)
    event.completed_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
        if status == "completed"
        else None
    )
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS,
        "away_period_scores": AWAY_PERIODS,
    }

    first_five = _make_futures_market(
        id=902, name="Tampa Bay vs Atlanta: First 5 Innings", source="kalshi"
    )
    first_five.status = "open"
    first_five.event_id = EVENT_ID

    sixth = _make_futures_market(
        id=903, name="Tampa Bay vs Atlanta: 6th Inning Winner", source="kalshi"
    )
    sixth.status = "open"
    sixth.event_id = EVENT_ID

    outcomes = [
        _make_outcome(id=9201, market_id=902, name=FIRST_FIVE_TB, probability=0.99),
        _make_outcome(id=9202, market_id=902, name=FIRST_FIVE_ATL, probability=0.01),
        _make_outcome(id=9203, market_id=902, name=FIRST_FIVE_TIE, probability=0.01),
        _make_outcome(id=9301, market_id=903, name=SIXTH_ATL, probability=0.40),
        _make_outcome(id=9302, market_id=903, name=SIXTH_TB, probability=0.45),
    ]
    return event, [first_five, sixth], outcomes


async def _payload(status: str, period: str | None):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves(status, period)
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
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/events/{EVENT_ID}/game-markets")
        return response.json()
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()


def _script_by_label(payload) -> dict:
    return {r["label"]: r for r in (payload.get("props_script") or [])}


def _served_outcome_names(payload) -> set:
    names = set()
    for bucket in (
        "totals",
        "player_props",
        "team_totals",
        "spreads",
        "period_markets",
        "matchups",
        "other",
    ):
        for row in payload.get(bucket) or []:
            name = row.get("outcome_name")
            if name:
                names.add(name)
    return names


# ---------------------------------------------------------------------------
# The route: a window's result arrives when the WINDOW ends
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_first_five_are_graded_while_the_sixth_is_still_being_played():
    """The ship and its guardrail, on ONE fixture and one line score.

    Sixth inning in progress. The first five are over and every rung bounded to
    them is answered: 6–1, so Tampa Bay hit and both Atlanta and the tie missed.
    The SIXTH is not over — its runs are sitting in the same array, one index
    further along — and no rung bounded to it may carry a verdict.

    Asserting only the first half would pass against a grader that graded
    everything the array could reach, which is the exact failure this ship must
    not ship. `prop_window_closed` is what separates them, and this is the test
    that proves it is still load-bearing after the event gate came off.
    """
    script = _script_by_label(await _payload("live", "6th Inning"))

    assert script[FIRST_FIVE_TB]["graded_result"] == "hit"
    assert script[FIRST_FIVE_TB]["graded_label"] == "6–1 — hit"
    assert script[FIRST_FIVE_ATL]["graded_result"] == "miss"
    assert script[FIRST_FIVE_TIE]["graded_result"] == "miss"

    # The sixth's rungs are on the page — as the LIVE question they still are,
    # priced and unsettled. "Not graded" is the assertion, not "not present":
    # an open window keeps its price, which is #1588's other half.
    for label in (SIXTH_ATL, SIXTH_TB):
        assert script[label]["graded_result"] is None, (
            f"{label!r}: the sixth inning is still being played and must not be graded"
        )
        assert script[label]["graded_label"] is None
        assert script[label]["settled"] is False
        assert script[label]["current"] is not None, (
            f"{label!r} should still be quoting — its window is open"
        )


@pytest.mark.asyncio
async def test_the_sixth_is_graded_once_the_seventh_starts():
    """The other side of the same gate — a positive control for the negative above.

    Without this, `test_..._while_the_sixth_is_still_being_played` is satisfied
    by a grader that can never grade a sixth inning at all: the absence proves
    the window rule only if the presence is reachable on the same fixture.
    Sixth inning alone was 0–1, so Atlanta hit it and Tampa Bay missed.
    """
    script = _script_by_label(await _payload("live", "Top 7th"))

    assert script[SIXTH_ATL]["graded_result"] == "hit"
    assert script[SIXTH_ATL]["graded_label"] == "0–1 — hit"
    assert script[SIXTH_TB]["graded_result"] == "miss"
    # And the first five, closed two innings earlier, are still answered.
    assert script[FIRST_FIVE_TB]["graded_result"] == "hit"


@pytest.mark.asyncio
async def test_a_graded_row_says_so_and_still_publishes_no_price():
    """`settled` is the per-row override, and #1588 is untouched by this ship.

    `PropsSection` renders `rowState = item.settled ? "graded" : state`, so
    without this flag a verdict composed mid-game would be laid out as a live
    script row. And the price stays gone: the whole point of the row is that the
    first five finished 6–1, never what that was worth — republishing 0.99 beside
    a green tick is the original bug wearing a rosette.
    """
    payload = await _payload("live", "6th Inning")
    row = _script_by_label(payload)[FIRST_FIVE_TB]

    assert row["settled"] is True
    assert row["current"] is None
    assert row["pregame_mark"] is None
    # Nor does the rung reappear in any PRICE bucket.
    assert FIRST_FIVE_TB not in _served_outcome_names(payload)


@pytest.mark.asyncio
async def test_the_midgame_verdict_is_the_one_the_final_whistle_would_have_given():
    """Zero false grades, stated as an equality rather than as a spot check.

    Same line score, two game states. Every verdict published mid-game must be
    the verdict the settled page publishes — a result that changes when the game
    ends was never a result. This is the arrival-order property the acceptance
    criterion asks for, in the form a unit test can hold.
    """
    live = _script_by_label(await _payload("live", "Top 7th"))
    final = _script_by_label(await _payload("completed", None))

    graded_live = {
        label: (row["graded_result"], row["graded_label"])
        for label, row in live.items()
        if row["graded_result"] is not None
    }
    assert graded_live, "fixture published no mid-game verdict at all"

    for label, verdict in graded_live.items():
        assert label in final, f"{label!r} was graded mid-game and vanished at full time"
        assert (
            final[label]["graded_result"],
            final[label]["graded_label"],
        ) == verdict, f"{label!r} changed its verdict at the whistle"


@pytest.mark.asyncio
async def test_a_window_with_no_line_score_stays_absent_rather_than_blank():
    """CERT-2535's rule, re-stated where it now lives.

    The gate that used to enforce "a verdict or absent, never blank" was the
    event check this ship removed. The property has to survive it: with no line
    score to read, `_grade_closed_windows` answers nothing, and the rows are
    ABSENT — not present with four null fields, which is what the frontend draws
    as an em-dash line that says nothing.
    """
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves("live", "6th Inning")
    event.box_score_data = {"players": {}}  # no line score at all
    mock_session = _make_event_detail_session(
        event=event, futures=futures, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = lambda: None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = (
                await client.get(f"/api/events/{EVENT_ID}/game-markets")
            ).json()
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()

    blank = [
        r
        for r in (payload.get("props_script") or [])
        if r.get("graded_result") is None
        and r.get("graded_label") is None
        and r.get("pregame_mark") is None
        and r.get("current") is None
    ]
    assert blank == [], f"{len(blank)} row(s) reach the reader with nothing in them: {blank}"


# ---------------------------------------------------------------------------
# The ingestion half: the live pass has to write the line score in the first place
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RecordingSession:
    """Answers the SELECT with `events` and records every later `execute`."""

    def __init__(self, events):
        self._events = events
        self.selects: list = []
        self.writes: list = []

    async def execute(self, statement, params=None):
        if params is None:
            self.selects.append(statement)
            return _FakeResult(self._events)
        self.writes.append((statement, params))
        return _FakeResult([])


def _live_event(event_id: int, sport_key: str = "baseball_mlb"):
    event = MagicMock()
    event.id = event_id
    event.espn_id = f"espn-{event_id}"
    event.status = "live"
    event.box_score_data = None
    event.sport = MagicMock()
    event.sport.key = sport_key
    return event


def _espn_service(context):
    service = MagicMock()
    service.get_event_context = AsyncMock(return_value=context)
    service.close = AsyncMock()
    return service


async def _run_live_pass(context, events=None):
    from app.utils import espn_helpers

    session = _RecordingSession(events or [_live_event(1)])
    stats: dict = {}
    with patch(
        "app.services.espn_api.ESPNAPIService", return_value=_espn_service(context)
    ):
        await espn_helpers.fetch_live_box_scores(session, stats)
    return session, stats


@pytest.mark.asyncio
async def test_a_live_box_score_write_keeps_the_line_score():
    """The dropped key, and the whole reason mid-game grading was impossible.

    `get_event_context` returns `scores` alongside `box_score` and
    `scoring_plays`, and `_backfill_box_scores` has always persisted the two
    period arrays out of it. This pass persisted the other two keys only, so the
    database's only line score was the one written after full time (measured:
    46 of 46 recent MLB events).
    """
    session, _ = await _run_live_pass(
        {
            "box_score": {"Player": {"hits": 1}},
            "scoring_plays": [],
            "scores": {
                "home_period_scores": [0, 1, 0],
                "away_period_scores": [2, 0, 0],
            },
        }
    )

    assert len(session.writes) == 1
    import json

    written = json.loads(session.writes[0][1]["bsd"])
    assert written["home_period_scores"] == [0, 1, 0]
    assert written["away_period_scores"] == [2, 0, 0]
    assert written["live"] is True


@pytest.mark.asyncio
async def test_a_live_write_with_no_line_score_omits_the_keys_rather_than_faking_them():
    """An absent line score is absent, not `[]`.

    `_window_totals` refuses a window the arrays do not cover, so an empty list
    would be refused too — but the two statements are different, and a reader
    (or the settled writer, which overwrites this row later) must be able to
    tell "ESPN reported no line score" from "ESPN reported a line score of
    nothing". Sports with no per-period breakdown take this branch every minute.
    """
    session, _ = await _run_live_pass(
        {
            "box_score": {"Player": {"hits": 1}},
            "scoring_plays": [],
            "scores": {"home_score": 3, "away_score": 1},
        }
    )

    import json

    written = json.loads(session.writes[0][1]["bsd"])
    assert "home_period_scores" not in written
    assert "away_period_scores" not in written


@pytest.mark.asyncio
async def test_a_context_with_no_scores_key_at_all_does_not_raise():
    """`context["scores"]` is read defensively, because a provider payload is not a contract."""
    session, _ = await _run_live_pass(
        {"box_score": {"Player": {"hits": 1}}, "scoring_plays": []}
    )

    import json

    written = json.loads(session.writes[0][1]["bsd"])
    assert "home_period_scores" not in written


@pytest.mark.asyncio
async def test_the_live_refresh_is_ordered_by_staleness_not_by_kickoff():
    """The reach half: 10 slots as a round-robin, not as a fixed window on ten games.

    Ordered by `commence_time DESC` the pass read the same ten most recently
    started games every minute — and the 2-minute staleness filter then dropped
    the ones it had just fetched, so on alternate minutes it did nothing while
    an eleventh live game was never read at all. Peak concurrent live
    ESPN-linked events, measured over the trailing week: 54.

    Ordering by `fetched_at` with nulls first makes every live event reachable
    within `ceil(N/10)` minutes and costs no extra ESPN calls — the limit and
    the staleness rule are unchanged, which the two assertions below pin.
    """
    session, _ = await _run_live_pass(
        {"box_score": {}, "scoring_plays": [], "scores": {}}
    )

    sql = str(session.selects[0].compile(compile_kwargs={"literal_binds": True}))
    normalised = " ".join(sql.split()).lower()

    assert "order by" in normalised
    order_by = normalised.split("order by", 1)[1]
    assert "fetched_at" in order_by, f"ordering is not by staleness: {order_by}"
    assert "nulls first" in order_by, (
        "an event that has never been fetched must sort first, "
        f"not last: {order_by}"
    )
    assert order_by.index("fetched_at") < order_by.index("commence_time"), (
        "kickoff may only break a staleness tie, never lead the ordering"
    )
    assert "limit 10" in normalised, "the ESPN call budget is unchanged by this ship"
