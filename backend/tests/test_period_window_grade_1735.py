"""#1735 — the closed window gets a RESULT, not just an absence.

## What was owed

#1588 shipped suppression: a window-bounded prop stops quoting a probability
once we can prove its window is over. Its own acceptance criterion is *"shows a
graded result **or** is suppressed"*, and suppression is the second half of an
`or`. On the production specimen the reader is left with nothing at all —
`GET /api/events/15308050/game-markets`, read 2026-09-10 11:5xZ, twice (the
endpoint serves stale once and rebuilds behind it), served **zero**
window-bounded market names across all six buckets.

## The resolution input was already on the row, under a different name

The #1588 handoff pointed at `box_score_data["scoring_plays"]`. Measured before
building anything: over finished MLB events of the trailing 30 days that key is
**EMPTY on 357 of 357** (129 more carry no box score at all), and it is only
ever populated for football — NCAAF 97 rows, NFL 32, MLB 0. A grader built on it
would have been a clean diff that graded nothing.

`home_period_scores` / `away_period_scores` is the key that carries it: present
on **94 of the 96** finished MLB events of the trailing week, holding a real
per-inning line score. That is what this ships on.

## The specimen, end to end

Event 15308050, Braves 2 – Rays 7 (`home [0,0,0,1,0,1,0,0,0]`,
`away [0,3,0,3,0,0,1,0,0]`), carried **19** ungraded window-bounded outcomes,
every one suppressed. Graded off the line score, all 19 agree with the price the
market was quoting: "Tampa Bay wins first 5 innings" was 0.99 and the first five
finished 6–1; "Tie 1st inning" was 0.99 and the first inning was 0–0. Those
0.99s were never wrong numbers — they were unlabelled results.

## What these tests pin

The route, not a copy of it (#4741's lesson: a test that re-declares the rule it
is checking passes whatever the route does). Every route assertion below reads
the assembled payload of `GET /api/events/{id}/game-markets`.

Two directions, both load-bearing:

* the verdict ARRIVES in `props_script` — "6–1 — hit", the site's one settled
  vocabulary, composed by `_build_props_script` and not by #1735;
* the PRICE does not arrive with it. `pregame_mark` and `current` stay null and
  the row stays out of every price bucket. A green tick beside a restored 0.99
  would be #1588 wearing a rosette.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.period_window_grade import grade_period_window
from app.utils.prop_window import prop_window, prop_window_span
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15308050

# The production line score for the specimen, verbatim.
HOME_PERIODS = [0, 0, 0, 1, 0, 1, 0, 0, 0]  # Atlanta Braves
AWAY_PERIODS = [0, 3, 0, 3, 0, 0, 1, 0, 0]  # Tampa Bay Rays
# First five innings: home 1, away 6, combined 7. First inning: 0–0.


# ---------------------------------------------------------------------------
# The grader itself
# ---------------------------------------------------------------------------


def _grade(outcome, *, first=1, last=5, market="Tampa Bay vs Atlanta: First 5 Innings",
           ticker=None, home=None, away=None, unit="inning"):
    return grade_period_window(
        unit,
        first,
        last,
        market,
        ticker,
        outcome,
        HOME_PERIODS if home is None else home,
        AWAY_PERIODS if away is None else away,
        "Atlanta Braves",
        "Tampa Bay Rays",
    )


class TestTheFourShapesKalshiActuallySells:
    """Every outcome name here is copied from production, not invented."""

    def test_the_first_five_winner_reads_the_named_sides_score_first(self):
        assert _grade("Tampa Bay wins first 5 innings") == {"actual": "6–1", "hit": True}
        # The same window, the other side, the other verdict — and the score
        # flips with the name, so neither row needs a legend to be read.
        assert _grade("Atlanta wins first 5 innings") == {"actual": "1–6", "hit": False}

    def test_the_tie_leg_grades_off_the_window_and_not_the_final(self):
        # Atlanta lost the game 2–7 and lost the first five 1–6, but the FIRST
        # INNING was 0–0. A grader reading the final score gets this wrong.
        assert _grade("Tie 1st inning", last=1) == {"actual": "0–0", "hit": True}
        assert _grade("Tie") == {"actual": "1–6", "hit": False}

    def test_the_over_under_ladder_grades_on_the_windows_combined_runs(self):
        # Seven runs in the first five: every rung up to 6.5 hit.
        assert _grade("Over 4.5 runs in the first 5 innings") == {"actual": "7 runs", "hit": True}
        assert _grade("Over 6.5 runs in the first 5 innings") == {"actual": "7 runs", "hit": True}
        assert _grade("Over 7.5 runs in the first 5 innings") == {"actual": "7 runs", "hit": False}
        assert _grade("Under 7.5 runs in the first 5 innings") == {"actual": "7 runs", "hit": True}

    def test_the_spread_applies_the_line_to_the_named_sides_margin(self):
        # Tampa Bay led the first five by five runs.
        assert _grade("Tampa Bay -1.5 first 5 innings") == {"actual": "6–1", "hit": True}
        assert _grade("Tampa Bay -2.5 first 5 innings") == {"actual": "6–1", "hit": True}
        assert _grade("Atlanta -1.5 first 5 innings") == {"actual": "1–6", "hit": False}
        # The sign is read, not assumed: a five-run underdog covers +1.5.
        assert _grade("Atlanta +1.5 first 5 innings") == {"actual": "1–6", "hit": False}
        assert _grade("Atlanta +5.5 first 5 innings") == {"actual": "1–6", "hit": True}

    def test_the_run_question_is_answered_by_the_window_not_the_scoreboard(self):
        # Nine runs were scored in this game. None of them in the first inning,
        # which is the entire question `KXMLBRFI` asks.
        ticker = "KXMLBRFI-26SEP091915TBATL"
        assert _grade("Yes", last=1, market="Rays at Braves", ticker=ticker) == {
            "actual": "0 runs",
            "hit": False,
        }
        assert _grade("No", last=1, market="Rays at Braves", ticker=ticker) == {
            "actual": "0 runs",
            "hit": True,
        }

    def test_one_run_is_singular(self):
        # Prose about a number is still prose; "1 runs" is a tell that nobody
        # read the string.
        assert _grade(
            "Over 0.5 runs in the first inning", last=4, home=[0, 0, 0, 1], away=[0, 0, 0, 0]
        ) == {"actual": "1 run", "hit": True}


class TestTheSpanIsOneClassifierWithTwoViews:
    """`prop_window_span` is `prop_window` plus the start. Both, always."""

    def test_the_end_is_unchanged_for_every_window_shape(self):
        # `prop_window` is now a projection of the span. If it ever disagrees,
        # #1588's suppression and #1735's grading are reading different windows
        # and the page will contradict itself.
        for name, ticker in (
            ("Tampa Bay vs Atlanta: First 5 Innings Total", None),
            ("Tampa Bay vs Atlanta: 6th Inning Winner", None),
            ("Tampa Bay vs Atlanta: 1st Inning Total", None),
            ("Celtics at Warriors: 2nd Quarter Total", None),
            ("Arsenal vs Chelsea: 1st Half Result", None),
            ("Rays at Braves", "KXMLBRFI-26SEP091915TBATL-T0.5"),
            ("Rays at Braves", "KXMLBF5-26SEP091915TBATL"),
            ("Tampa Bay vs Atlanta: Spread", None),
            ("Arsenal vs Chelsea: 1st Half / Fulltime Result", None),
        ):
            span = prop_window_span(name, ticker, "baseball_mlb", None)
            window = prop_window(name, ticker, "baseball_mlb", None)
            expected = None if span is None else (span[0], span[2])
            assert window == expected, f"{name!r}/{ticker!r}: {window} vs span {span}"

    def test_a_leading_window_starts_at_one_and_a_named_period_does_not(self):
        # The whole reason the span exists. Both close after the fifth/sixth;
        # only one of them BEGINS with the game.
        assert prop_window_span("Tampa Bay vs Atlanta: First 5 Innings Total") == ("inning", 1, 5)
        assert prop_window_span("Tampa Bay vs Atlanta: 6th Inning Winner") == ("inning", 6, 6)
        assert prop_window_span("Rays at Braves", "KXMLBRFI-26SEP0919-T0.5") == ("inning", 1, 1)
        assert prop_window_span("Celtics at Warriors: 2nd Quarter Total") == ("quarter", 2, 2)


class TestTheRefusalsAreTheProduct:
    """Every one of these leaves the row suppressed — today's behaviour."""

    def test_a_half_or_quarter_window_is_refused_because_the_array_is_not_halves(self):
        # An NFL line score is QUARTERS, so a "1st half" window spans [0:2] and
        # not [0:1]. Grading it against `closes_after=1` would publish a verdict
        # off one quarter of a two-quarter question. Refuse instead.
        assert _grade("Tampa Bay wins first half", last=1, unit="half") is None
        assert _grade("Over 4.5", last=1, unit="quarter") is None

    def test_a_window_longer_than_the_line_score_is_refused(self):
        # A game called after four innings has no first-five result.
        assert _grade("Tampa Bay wins first 5 innings", home=[0, 0, 0, 1], away=[0, 3, 0, 3]) is None

    def test_a_hole_in_the_line_score_is_not_a_zero(self):
        # A missing inning is a number nobody reported. Summing it as 0 would
        # publish a verdict off a score that was never observed.
        assert _grade("Over 4.5 runs in the first 5 innings", home=[0, None, 0, 1, 0]) is None
        assert _grade("Over 4.5 runs in the first 5 innings", away=[0, "3", 0, 3, 0]) is None

    def test_a_push_is_refused_rather_than_rounded_into_a_miss(self):
        # `_build_props_script` speaks two words. A push rendered as "miss" is a
        # false verdict, so an exact line is left ungraded until that builder
        # learns the third word.
        assert _grade("Over 7 runs in the first 5 innings") is None
        assert _grade("Under 7 runs in the first 5 innings") is None
        # A spread that lands exactly on the margin is the same refusal.
        assert _grade("Tampa Bay -5 first 5 innings") is None

    def test_a_side_that_names_both_clubs_names_neither(self):
        # "New York" on a Yankees/Mets matchup. Picking one would print a
        # verdict under the wrong club's name.
        assert grade_period_window(
            "inning", 1, 5, "New York Y vs New York M: First 5 Innings", None,
            "New York wins first 5 innings",
            HOME_PERIODS, AWAY_PERIODS, "New York Yankees", "New York Mets",
        ) is None

    def test_a_side_that_names_no_club_is_refused(self):
        assert _grade("Chicago WS wins first 5 innings") is None

    def test_a_short_club_name_that_is_a_genuine_prefix_still_resolves(self):
        # The refusal above must not be the whole story, or the ship grades
        # nothing: "Los Angeles A" IS an unambiguous prefix of the Angels here.
        assert grade_period_window(
            "inning", 1, 5, "Los Angeles A vs Boston: First 5 Innings", None,
            "Los Angeles A wins first 5 innings",
            HOME_PERIODS, AWAY_PERIODS, "Los Angeles Angels", "Boston Red Sox",
        ) == {"actual": "1–6", "hit": False}

    def test_a_bare_yes_on_a_question_that_is_not_about_runs_is_refused(self):
        # Production stores "1st Inning Total" with a lone `Yes` outcome and the
        # line nowhere on the row. There is nothing to compare 0 runs against.
        assert _grade("Yes", last=1, market="Tampa Bay vs Atlanta: 1st Inning Total") is None

    def test_a_named_inning_is_not_graded_as_the_innings_before_it(self):
        # The span trap, at the util. Atlanta won the SIXTH inning 1–0 and lost
        # innings 1–6 by 2–6, so reading only the window's end flips the verdict.
        assert _grade("Atlanta wins 6th inning", first=6, last=6) == {"actual": "1–0", "hit": True}
        assert _grade("Atlanta wins 6th inning", first=1, last=6) == {"actual": "2–6", "hit": False}

    def test_a_home_team_that_never_batted_the_ninth_is_refused(self):
        # A home side leading after the top of the 9th does not bat, so its
        # array is one shorter. Production event 15308051 is exactly this
        # (home 8 entries, away 9). Refuse rather than read `[8]` off the end.
        assert _grade(
            "Atlanta wins 9th inning", first=9, last=9,
            home=[3, 3, 1, 0, 0, 1, 0, 0], away=[0, 0, 0, 1, 0, 0, 0, 0, 5],
        ) is None

    def test_an_unrecognised_outcome_shape_is_refused(self):
        assert _grade("Tampa Bay Rays") is None
        assert _grade("") is None


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

# Copied from production, and chosen for what the route ACTUALLY serves. A
# scheduled MLB page (`/api/events/15308637/game-markets`, read 2026-09-10)
# carries 62 window-bounded rows in three shapes and no others:
#
#     player_props    51   "Atlanta wins 6th inning" / "Tie 6th inning"
#     period_markets   7   "Over 4.5 runs in the first 5 innings"
#     spreads          4   "Tampa Bay -1.5 first 5 innings"
#
# The "First 5 Innings" MONEYLINE exists in the database and never reaches any
# bucket — dropped upstream of the window filter, in every game state. A fixture
# built on it would assert nothing about this ship, which is how the first cut
# of this file failed. None of the three below is graded by the venue: all carry
# `status='open'` (gotcha #33) and a null `resolution_source`, so #1588
# suppresses all of them today.
#
# ** THE PRICES ARE MID-BAND ON PURPOSE, AND THAT IS A CONSTRAINT ON THE SHIP. **
# Step 9 of the endpoint drops any player-prop leg outside `0.05 <= p <= 0.95` as
# boring, and it runs ~230 lines BEFORE the window filter. So a settled
# inning-winner leg that has drifted to 0.99 never reaches suppression, never
# reaches this grader, and cannot be restored by it — it was already gone for an
# unrelated reason. Production carries "Tampa Bay wins 1st inning" at 0.50 on the
# finished specimen, which is the population this arm actually pays. A fixture
# priced 0.99/0.01 (the first cut of this file) tests nothing: all three legs
# vanish at step 9 and the assertions fail for a reason that has nothing to do
# with #1735. `spreads` and `period_markets` carry no such filter.
#
# ** THE SIXTH INNING IS THE SPECIMEN ON PURPOSE. ** Atlanta won it 1–0 while
# losing the game 2–7 and losing innings 1–6 by 2–6. So a grader that read only
# the window's END and summed from the top — the shape `prop_window` returns for
# suppression — prints MISS on a row that HIT. It is the one inning of this game
# where the two readings disagree, and it is here so that they cannot.
WINNER = "Atlanta wins 6th inning"
LOSER = "Tampa Bay wins 6th inning"
TIE = "Tie 6th inning"
SPREAD = "Tampa Bay -1.5 first 5 innings"
# Not window-bounded — the control that must be untouched in every direction.
FULL_GAME = "Tampa Bay wins by over 1.5 runs"
# A PLAYER PROP, priced outside the interest band, and NOT window-bounded — the
# only row in this fixture that can tell "the closed window is carved out" apart
# from "extreme prices are back" (CERT-2502). It must stay dropped: step 9's
# judgement that a 0.98 leg has stopped being a question is correct for every row
# whose window is still the whole game.
BORING_PROP = "1+ hits"
BORING_PROP_MARKET = "Ronald Acuña Jr. Hits"


def _rays_at_braves_finished(*, box_score_data=..., winner_prices=None,
                             cross_source_copy=False):
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
    event.box_score_data = (
        {
            "players": {},
            "home_period_scores": HOME_PERIODS,
            "away_period_scores": AWAY_PERIODS,
        }
        if box_score_data is ...
        else box_score_data
    )

    winner = _make_futures_market(
        id=901, name="Tampa Bay vs Atlanta: 6th Inning Winner", source="kalshi"
    )
    winner.status = "open"
    winner.event_id = EVENT_ID

    spread = _make_futures_market(
        id=902, name="Tampa Bay vs Atlanta: First 5 Spread", source="kalshi"
    )
    spread.status = "open"
    spread.event_id = EVENT_ID

    full_game = _make_futures_market(
        id=903, name="Tampa Bay vs Atlanta: Spread", source="kalshi"
    )
    full_game.status = "open"
    full_game.event_id = EVENT_ID

    boring = _make_futures_market(id=904, name=BORING_PROP_MARKET, source="kalshi")
    boring.status = "open"
    boring.event_id = EVENT_ID

    # The winner market's full production field — three legs, not one. A
    # single-leg fixture is not merely thinner: a one-outcome field market is
    # dropped upstream of the window filter entirely, so it would have tested
    # nothing about this ship.
    win_p, lose_p, tie_p = winner_prices or (0.30, 0.50, 0.20)
    outcomes = [
        _make_outcome(id=9101, market_id=901, name=WINNER, probability=win_p),
        _make_outcome(id=9102, market_id=901, name=LOSER, probability=lose_p),
        _make_outcome(id=9103, market_id=901, name=TIE, probability=tie_p),
        _make_outcome(id=9201, market_id=902, name=SPREAD, probability=0.99),
        _make_outcome(id=9301, market_id=903, name=FULL_GAME, probability=0.99),
        _make_outcome(id=9401, market_id=904, name=BORING_PROP, probability=0.98),
    ]
    futures = [winner, spread, full_game, boring]

    if cross_source_copy:
        # The SAME sixth inning, from the other venue, MID-BAND — so it takes the
        # other path into the closed collection (CERT-2505). Polymarket spells the
        # market its own way, which is why the input key alone cannot catch it.
        pm = _make_futures_market(
            id=905, name="Rays vs Braves", source="polymarket"
        )
        pm.status = "open"
        pm.event_id = EVENT_ID
        futures.append(pm)
        outcomes.append(
            _make_outcome(id=9501, market_id=905, name=WINNER, probability=0.30)
        )

    return event, futures, outcomes


async def _client(**kwargs):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves_finished(**kwargs)
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
    return app, _game_markets_cache


@pytest.fixture
async def finished_client():
    app, cache = await _client()
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


@pytest.fixture
async def settled_price_client():
    """The same game with the winner legs SETTLED at the venue's own extremes.

    0.99 / 0.01 / 0.01 — the shape 859 of the 935 gradable production outcomes
    actually wear (CERT-2502). Everything else about the fixture is identical to
    `finished_client`, so the only variable between the two arms is the price.
    """
    app, cache = await _client(winner_prices=(0.99, 0.01, 0.01))
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


@pytest.fixture
async def mixed_source_client():
    """One sixth inning, two venues, one on each side of the interest band.

    Kalshi 0.99 leaves through the step 9 carve-out; Polymarket 0.30 stays in
    `player_props` and joins the same collection ~180 lines later through
    `_window_open`. The two paths never meet, which is CERT-2505's finding.
    """
    app, cache = await _client(winner_prices=(0.99, 0.01, 0.01), cross_source_copy=True)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


@pytest.fixture
async def no_line_score_client():
    """The same game with the line score missing — 2 of 96 production rows."""
    app, cache = await _client(box_score_data={"players": {}})
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


def _script_by_label(payload) -> dict:
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
async def test_the_suppressed_window_row_comes_back_as_a_verdict(finished_client):
    """The ship: an absence becomes a result. Read off the route's own payload."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script_by_label(payload)

    assert WINNER in script, (
        f"the sixth-inning winner never reached WHAT HIT; labels={sorted(script)}"
    )
    # The composition is `_build_props_script`'s, which is the point — #1650
    # exists because one backend state wore three phrasings.
    #
    # 1–0, not 2–7: the SIXTH inning, graded on the sixth inning. This assertion
    # is the span trap, taken through the route rather than off the util.
    assert script[WINNER]["graded_result"] == "hit"
    assert script[WINNER]["graded_label"] == "1–0 — hit"

    assert script[LOSER]["graded_result"] == "miss"
    assert script[LOSER]["graded_label"] == "0–1 — miss"

    assert script[TIE]["graded_result"] == "miss"
    assert script[TIE]["graded_label"] == "1–0 — miss"

    # The first-five spread, over innings 1–5, on the same page and the same read.
    assert SPREAD in script
    assert script[SPREAD]["graded_result"] == "hit"
    assert script[SPREAD]["graded_label"] == "6–1 — hit"


@pytest.mark.asyncio
async def test_the_price_does_not_come_back_with_the_verdict(finished_client):
    """#1588 must not be undone by its own repair."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    # Still suppressed in every price bucket.
    served = _all_served_outcome_names(payload)
    for label in (WINNER, LOSER, TIE, SPREAD):
        assert label not in served, f"{label}: a suppressed window row is back in a price bucket"

    # And the script row carries a verdict, never a number.
    script = _script_by_label(payload)
    for label in (WINNER, SPREAD):
        assert script[label]["pregame_mark"] is None, f"{label} republished a mark"
        assert script[label]["current"] is None, f"{label} republished a live price"


@pytest.mark.asyncio
async def test_the_full_game_control_is_untouched_in_both_directions(finished_client):
    """Not window-bounded: keeps its price, and is never invented into WHAT HIT."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    assert FULL_GAME in _all_served_outcome_names(payload)
    assert FULL_GAME not in _script_by_label(payload)


@pytest.mark.asyncio
async def test_without_a_line_score_the_page_is_exactly_as_it_was(no_line_score_client):
    """The fail-safe, proven through the route rather than asserted of the util.

    2 of the 96 finished MLB events measured carried no line score. Those pages
    must keep #1588's behaviour precisely: suppressed, and not grading anything
    off an absence.
    """
    payload = (await no_line_score_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script_by_label(payload)
    assert WINNER not in script
    assert SPREAD not in script
    served = _all_served_outcome_names(payload)
    assert WINNER not in served
    assert SPREAD not in served
    assert FULL_GAME in served


# ---------------------------------------------------------------------------
# CERT-2502 — the settled-extreme cohort, which is most of the ship
# ---------------------------------------------------------------------------
#
# The first cut of this file wrote the mid-band prices above as a CONSTRAINT on
# the ship and moved on. It is not a constraint, it is the ship: step 9 of the
# endpoint drops any player-prop leg outside `0.05 <= p <= 0.95` as "boring",
# ~180 lines before the window filter could collect it, and on 1,000 production
# outcome rows **859 of the 935 gradable ones sit outside that band**. So the
# grader worked, its tests were green, and the dominant cohort of finished-page
# rows still showed the reader nothing.
#
# "Boring" means the market has stopped being a question. On a closed window
# that is not a reason to drop the row — it is the reason the row has an answer.


@pytest.mark.asyncio
async def test_a_settled_inning_row_comes_back_as_a_verdict(settled_price_client):
    """0.99 / 0.01 — the cohort the interest filter used to eat."""
    payload = (await settled_price_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script_by_label(payload)

    assert WINNER in script, (
        "a 0.99 settled inning row never reached WHAT HIT — the interest filter "
        f"ate it before the window filter could collect it; labels={sorted(script)}"
    )
    # Graded on the SIXTH inning (1–0 Atlanta), not the 2–7 final.
    assert script[WINNER]["graded_result"] == "hit"
    assert script[WINNER]["graded_label"] == "1–0 — hit"

    # The 0.01 legs are the same cohort at the other end of the band.
    assert script[LOSER]["graded_result"] == "miss"
    assert script[TIE]["graded_result"] == "miss"


@pytest.mark.asyncio
async def test_the_settled_row_arrives_price_free(settled_price_client):
    """A verdict, never a rehabilitated 0.99. #1588 is not undone by its repair."""
    payload = (await settled_price_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    served = _all_served_outcome_names(payload)
    for label in (WINNER, LOSER, TIE, SPREAD):
        assert label not in served, f"{label}: a settled window row is back in a price bucket"

    script = _script_by_label(payload)
    for label in (WINNER, LOSER, TIE):
        assert script[label]["pregame_mark"] is None, f"{label} republished a mark"
        assert script[label]["current"] is None, f"{label} republished a live price"


@pytest.mark.asyncio
async def test_a_boring_prop_whose_window_is_the_whole_game_stays_dropped(
    settled_price_client,
):
    """The other direction, which is what stops this becoming "extremes are back".

    `BORING_PROP` is a player prop at 0.98 whose window is the whole game. Step 9
    is RIGHT about it — a 0.98 leg on an open-ended question has stopped being a
    question — and this ship must not rehabilitate it. It is the one row in the
    fixture that separates "closed windows are carved out" from "the interest
    filter was weakened", so it is the row that fails if the carve-out ever grows
    to mean the latter.

    Both directions asserted: it must not come back as a PRICE (a served bucket)
    and it must not come back as a VERDICT (a WHAT HIT row it has no answer for).
    """
    payload = (await settled_price_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    assert BORING_PROP not in _all_served_outcome_names(payload), (
        "a boring full-game prop is back in a price bucket — the interest filter "
        "was widened, not carved out"
    )
    assert BORING_PROP not in _script_by_label(payload), (
        "a boring full-game prop reached WHAT HIT — the line score cannot answer it"
    )


@pytest.mark.asyncio
async def test_the_extreme_priced_control_keeps_its_price(settled_price_client):
    """`FULL_GAME` is 0.99 and not window-bounded: a real price on a real market.

    It reaches neither the carve-out nor the suppression filter, which is the
    proof that this ship is scoped to closed windows and not to settled-looking
    numbers in general.
    """
    payload = (await settled_price_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    assert FULL_GAME in _all_served_outcome_names(payload)
    assert FULL_GAME not in _script_by_label(payload)


@pytest.mark.asyncio
async def test_mixed_source_prices_produce_one_price_free_verdict(mixed_source_client):
    """CERT-2505: the two price paths feed one collection, so they need one dedupe.

    Kalshi has the sixth inning at 0.99 and Polymarket at 0.30. One leaves through
    the step 9 carve-out, the other through `_window_open`, and before this repair
    the reader got `1–0 — hit` twice — a set living inside either path is blind to
    the other.
    """
    payload = (await mixed_source_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    rows = [r for r in (payload.get("props_script") or []) if r["label"] == WINNER]
    assert len(rows) == 1, (
        f"the same sixth inning produced {len(rows)} WHAT HIT rows — the dedupe "
        "does not span both price paths"
    )
    assert rows[0]["graded_result"] == "hit"
    assert rows[0]["graded_label"] == "1–0 — hit"

    # And neither copy came back as a price, from either venue or either path.
    assert WINNER not in _all_served_outcome_names(payload)
    assert rows[0]["pregame_mark"] is None
    assert rows[0]["current"] is None


def test_one_label_bounded_to_two_windows_stays_two_verdicts():
    """The safety direction of CERT-2505's dedupe: it must not over-merge.

    "Over 4.5" is a bare outcome whose window lives in the MARKET name, so the
    same label legitimately binds two different questions — innings 1–5 and the
    first inning alone. They are not duplicates and both are owed a verdict. This
    is why the key is the SPAN plus the outcome and not the outcome alone; drop
    the span from the key and this test is what fails.
    """
    from app.routes.events import _grade_closed_windows

    event = _make_event(
        id=EVENT_ID, home_team="Atlanta Braves", away_team="Tampa Bay Rays",
        status="completed", sport_key="baseball_mlb", home_score=2, away_score=7,
    )
    event.llm_league = "MLB"
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS,
        "away_period_scores": AWAY_PERIODS,
    }
    items = [
        {"market_name": "Tampa Bay vs Atlanta: First 5 Innings Total",
         "outcome_name": "Over 4.5", "_market_id": 801},
        {"market_name": "Tampa Bay vs Atlanta: 1st Inning Total",
         "outcome_name": "Over 4.5", "_market_id": 802},
    ]
    graded = _grade_closed_windows(items, event, {})

    assert len(graded) == 2, (
        "two windows sharing one label were merged into one verdict; "
        f"graded={graded}"
    )
    # Innings 1–5 scored 7 combined (over 4.5); the first inning scored 0 (under).
    by_market = {g["market_name"]: g for g in graded}
    assert by_market["Tampa Bay vs Atlanta: First 5 Innings Total"]["hit"] is True
    assert by_market["Tampa Bay vs Atlanta: 1st Inning Total"]["hit"] is False


@pytest.mark.parametrize("ungradable_first", [True, False], ids=["refusal-first", "refusal-second"])
def test_ungradable_same_span_yes_does_not_hide_gradable_run_verdict(ungradable_first):
    """CERT-2509: a refusal must not consume the question key.

    Two production rows share span `(inning, 1, 1)` AND the outcome "Yes", so they
    share the dedupe key:

        "…: 1st Inning Total" / "Yes"                  -> refused (a lone Yes with
                                                          the line nowhere on the
                                                          row; 14 of this ship's 50
                                                          documented refusals)
        "Will there be a run in the first inning?" /
        "Yes"                                          -> "0 runs — miss"

    Claiming the key before the verdict made whichever arrived FIRST exclusive, so
    the reader lost a settled verdict in one input order and not the other. Both
    orders are asserted because a single order passes under the bug half the time.
    """
    from app.routes.events import _grade_closed_windows

    event = _make_event(
        id=EVENT_ID, home_team="Atlanta Braves", away_team="Tampa Bay Rays",
        status="completed", sport_key="baseball_mlb", home_score=2, away_score=7,
    )
    event.llm_league = "MLB"
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS,
        "away_period_scores": AWAY_PERIODS,
    }
    refusal = {"market_name": "Tampa Bay vs Atlanta: 1st Inning Total",
               "outcome_name": "Yes", "_market_id": 811}
    gradable = {"market_name": "Will there be a run in the first inning?",
                "outcome_name": "Yes", "_market_id": 812}
    items = [refusal, gradable] if ungradable_first else [gradable, refusal]

    graded = _grade_closed_windows(items, event, {})

    assert len(graded) == 1, (
        f"expected the one gradable row; got {graded} "
        f"(ungradable_first={ungradable_first})"
    )
    # The first inning was 0–0, so the run question is a miss — a REAL verdict, not
    # the silence a consumed key produces.
    assert graded[0]["market_name"] == "Will there be a run in the first inning?"
    assert graded[0]["actual"] == "0 runs"
    assert graded[0]["hit"] is False


@pytest.mark.asyncio
async def test_the_mid_band_arm_is_unchanged_by_the_carve_out(finished_client):
    """The regression direction: the rows that already worked still work.

    Same four labels, same verdicts, priced 0.30/0.50/0.20. A carve-out that
    re-routed the mid-band rows through the new path — rather than leaving them to
    the suppression filter that already collected them — would show up here as a
    duplicate or a vanished row, not as a wrong verdict.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    rows = [r for r in (payload.get("props_script") or []) if r["label"] == WINNER]
    assert len(rows) == 1, f"the mid-band winner row appears {len(rows)}× in WHAT HIT"
    assert rows[0]["graded_label"] == "1–0 — hit"
