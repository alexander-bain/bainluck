"""#6025 / #6026 — the settled section stops printing numbers it cannot stand behind.

## The specimen, one page, both directions

`/events/15297724` — Manchester United 0–1 Manchester City, finished 2026-09-13.
The hero is correct: `Final`, `Manchester City WON`. Under **"Additional Markets ·
settled"**, every row is prefixed `last quote`:

    Manchester United vs Manchester City: Correct Score
      Manchester City wins 1-0     last quote 99%     <- the true result
      Manchester City wins 6-1     last quote 50%     <- did not happen
      Manchester City wins 4-1     last quote 17%     <- did not happen
      ... 29 more rows, the 32 summing to 240%

A game that finished 1–0 printed "Manchester City wins 6-1" at 50%, and the true
result was not distinguishable in kind from the false ones — just a row with a
bigger number.

**#6025, decidable from the row.** Market 60780435 is `status='resolved'` with
`is_winner` AND `resolution_source` NULL on every one of its 32 outcomes. Nothing
was ever graded, so the section has no verdict to state and falls back to the last
traded price — and on a settled book that is a settlement artifact, never a
distribution. That is why the numbers cannot sum: they are 32 independent closing
quotes. Same page, same shape: `60780436` First Team to Score 111% (`No Goal` 11%
in a game with a goal) and `60780438` 1st Half Correct Score 148%.

**#6026, the inverse, two cards below.** `59693538` — "Who Will Finish Higher" —
is `status='open'` with `resolution_date 2027-05-31`, a season-long table question
with eight months left to trade, rendered under that same `settled` heading as
`last quote 91%`. That is not a last quote, it is today's live price.

Verified on the row, production 2026-09-14 01:2xZ, `sql_fingerprint
b96a90f055cb8db5`:

    id        status    res_date     n_out  n_src  sum
    60780435  resolved  2026-09-13      32      0  2.400
    60780436  resolved  2026-09-13       3      0  1.110
    59693538  open      2027-05-31       2      0  1.140

## What #5958 did and did not fix

#5958 put the `settled` heading and the `last quote` prefix on this section, and
they work — the page is not claiming these are live. But that framing excuses a
STALE number, not an IMPOSSIBLE one, and it cannot excuse a number that is not
stale at all (#6026). Alex's standing ruling is that a finished question shows its
result graded or shows nothing. These rows have no grade, so they show nothing.

## The two populations, measured

Over the 14-day finished-event window (`sql_fingerprint 85819f6c406fcf4f`,
`b4f67c309d120831`, `5f26ea114496bb98`):

    #6025 withheld: settled, nothing graded            7,444 markets
    #6025 kept:     settled, something graded         11,996 markets
    events losing every settled market                    77 of 1,159
    events losing some                                   652 of 1,159
    events untouched                                     430 of 1,159
    #6026 withheld: open, trading >7d past a finished       6 markets

## The scope claim this file has to defend

The withdrawal is at the `other` section alone, NOT at the top of the market loop
where #5247's empty-book filter and #5771's unstarted-game gate sit. Those two
withdraw a market from every section because no section could print it honestly.
Here the other sections have grading rails that need no `resolution_source` —
`_grade_settled_prop` grades totals and player props off the box score, and #1735
publishes exactly this cohort verdict-only. A top-of-loop withdrawal would delete
the information those rails recover, so
`test_the_player_prop_rescue_still_runs_on_a_withheld_market` is the load-bearing
test in this file, not a nicety.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _event_is_really_finished,
    _open_market_outlives_its_finished_event,
    _settled_market_graded_nothing,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

NOW = datetime(2026, 9, 13, 23, 50, tzinfo=timezone.utc)

# The derby: kicked off 15:30Z, final by 17:40Z.
KICKOFF = NOW - timedelta(hours=8, minutes=20)


def _event(*, commence=KICKOFF, status="completed", completed_at=None):
    event = MagicMock()
    event.commence_time = commence
    event.status = status
    event.completed_at = completed_at if completed_at is not None else NOW - timedelta(hours=6)
    return event


def _market(status="resolved", resolution_date=None):
    market = MagicMock()
    market.status = status
    market.resolution_date = resolution_date
    return market


def _outcome(is_winner=None, resolution_source=None):
    outcome = MagicMock()
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return outcome


# ── #6025: the specimen, and the cohort it must not reach ───────────────────


def test_the_correct_score_specimen_is_withheld():
    """32 outcomes, `status='resolved'`, not one of them graded."""
    assert _settled_market_graded_nothing(
        _event(),
        _market("resolved"),
        [_outcome() for _ in range(32)],
        NOW,
    )


def test_a_fully_graded_settled_market_keeps_its_rows():
    """The 10,405-market cohort: a verdict exists, so the card has something true to say.

    `Total Goals` on the same derby page is this shape — 7 outcomes, 7 sources.
    The opposite direction is the dangerous one: a gate that reaches here deletes
    every settled market on the site (gotcha #43, "settled means settled").
    """
    assert not _settled_market_graded_nothing(
        _event(),
        _market("resolved"),
        [
            _outcome(is_winner=True, resolution_source="api_settlement"),
            _outcome(is_winner=False, resolution_source="api_settlement"),
        ],
        NOW,
    )


def test_one_graded_outcome_is_enough_to_keep_the_whole_card():
    """`all()`, not `any()`. A partially graded card still carries a verdict.

    The 1,591-market cohort — settled, `is_winner` false everywhere, but a source
    present — is the same statement: every side lost, which IS the grade. Holding
    the whole market to "nothing at all was graded" is what keeps this predicate
    from being a second, quieter version of the #2089 false-verdict bug.
    """
    assert not _settled_market_graded_nothing(
        _event(),
        _market("resolved"),
        [_outcome(), _outcome(), _outcome(resolution_source="game_score")],
        NOW,
    )


def test_a_live_games_settled_sub_market_is_untouched():
    """#5771's middle bucket: a first set that finished while the match plays on.

    2,080 events / 8,867 markets. Real information that wants GRADING, not hiding.
    This gate is keyed on the EVENT being finished precisely so it cannot reach
    them.
    """
    assert not _settled_market_graded_nothing(
        _event(commence=NOW - timedelta(minutes=40), status="live", completed_at=None),
        _market("resolved"),
        [_outcome(), _outcome()],
        NOW,
    )


def test_an_unstarted_fixture_belongs_to_5771_not_to_this_gate():
    """The two rails divide cleanly and neither may answer for the other.

    A settled market on a fixture that has not kicked off is #5771's, withdrawn at
    the top of the loop from every section. This predicate abstains, so a reader
    can never find one rail's withdrawal undone by the other's silence.
    """
    assert not _settled_market_graded_nothing(
        _event(commence=NOW + timedelta(hours=2), status="scheduled", completed_at=None),
        _market("resolved"),
        [_outcome()],
        NOW,
    )


def test_an_open_ungraded_market_on_a_finished_event_is_not_this_gates_business():
    """`market_assigned_settled` is the door. An open, ungraded book is #6026's."""
    assert not _settled_market_graded_nothing(
        _event(),
        _market("open"),
        [_outcome(), _outcome()],
        NOW,
    )


def test_a_settled_but_still_open_kalshi_row_is_withheld_too():
    """Gotcha #33: Kalshi leaves settled markets `status='open'`, graded.

    Reached through `market_assigned_settled`'s second arm (`is_winner`), which is
    why this delegates to that predicate rather than testing `status` here — the
    same reason #5771 does.
    """
    assert _settled_market_graded_nothing(
        _event(),
        _market("open"),
        [_outcome(is_winner=True), _outcome(is_winner=False)],
        NOW,
    )


def test_the_corrupt_completed_with_future_kickoff_shape_keeps_its_rows():
    """A row reading `completed` while its kickoff is still ahead (#46 / gotcha #32).

    `_event_is_really_finished` refuses to read that shape as settled, so this gate
    abstains and #5771's — which sees an unstarted event — is the one that acts.
    Pinned because it is the single input where the two could be read as
    disagreeing.
    """
    corrupt = _event(commence=NOW + timedelta(hours=5), status="completed")
    assert not _event_is_really_finished(corrupt, NOW)
    assert not _settled_market_graded_nothing(
        corrupt, _market("resolved"), [_outcome()], NOW
    )


def test_an_empty_outcome_list_gets_no_opinion():
    """`all([])` is True and would withhold a market with nothing to withhold."""
    assert not _settled_market_graded_nothing(_event(), _market("resolved"), [], NOW)


def test_a_winner_with_no_source_is_read_as_ungraded_and_the_cohort_is_empty():
    """The one input where the two authorities could disagree — and nothing rests on it.

    `market_assigned_settled` calls a row with `is_winner` settled;
    `_settled_grade_fields` calls the same row ungraded unless the market status is
    `resolved` AND a `resolution_source` is present (#2089: `is_winner` defaults to
    False, so the column alone cannot tell a loss from an ungraded row). Measured
    over 19,529 markets on finished events, markets carrying a winner with no
    source number **zero** (`sql_fingerprint 85819f6c406fcf4f`). The behaviour is
    pinned anyway so a later reader knows which way it falls rather than deriving
    it, and so the day that cohort stops being empty this test is the one that
    changes.
    """
    assert _settled_market_graded_nothing(
        _event(),
        _market("resolved"),
        [_outcome(is_winner=True), _outcome(is_winner=False)],
        NOW,
    )


# ── #6026: a market that outlives the fixture it hangs off ──────────────────


def test_the_who_will_finish_higher_specimen_is_withheld():
    """`status='open'`, `resolution_date 2027-05-31`, on a game that ended today."""
    assert _open_market_outlives_its_finished_event(
        _event(),
        _market("open", resolution_date=datetime(2027, 5, 31, 2, tzinfo=timezone.utc)),
        [_outcome(), _outcome()],
        NOW,
    )


def test_a_just_finished_fixtures_own_book_still_reading_open_is_kept():
    """The 19-row cohort between three and seven days, and the reason for the margin.

    Almost every unsettled market on a finished event is that fixture's OWN book,
    still `open` because polling stopped seeing it (gotcha #33). Those ARE settled
    in fact and `last quote` is exactly the right framing for them. A rule keyed on
    "is it open" instead of "when does it stop trading" would take all 203 of them.
    """
    assert not _open_market_outlives_its_finished_event(
        _event(),
        _market("open", resolution_date=NOW + timedelta(hours=6)),
        [_outcome(), _outcome()],
        NOW,
    )


def test_a_market_three_days_out_is_inside_the_margin_and_is_kept():
    """The plateau's lower edge. 25 rows sit at +3d and are deliberately untouched."""
    assert not _open_market_outlives_its_finished_event(
        _event(),
        _market("open", resolution_date=NOW + timedelta(days=3)),
        [_outcome(), _outcome()],
        NOW,
    )


def test_a_season_long_market_on_an_event_still_to_play_is_kept():
    """Nothing about this is wrong until a finished event's heading frames it.

    The same market on a scheduled or live fixture renders under a live heading
    and its price is stated as a price. The defect is the FRAMING, so the gate is
    keyed on the event being finished — and 203 is the whole unsettled-on-finished
    population, against many thousands of ordinary open markets this must never
    reach.
    """
    assert not _open_market_outlives_its_finished_event(
        _event(commence=NOW - timedelta(minutes=30), status="live", completed_at=None),
        _market("open", resolution_date=datetime(2027, 5, 31, 2, tzinfo=timezone.utc)),
        [_outcome(), _outcome()],
        NOW,
    )


def test_a_settled_market_with_a_far_future_resolution_date_is_not_this_gates_business():
    """`resolution_date` is a SCHEDULE, and a settled market has left it behind.

    Kalshi writes `max(close_time)` there (CAL-P989 / #2660) and a resolved market
    can still carry a date months out. #6025's predicate owns that row; this one
    abstains, so a graded settled market can never be withheld by the clock.
    """
    assert not _open_market_outlives_its_finished_event(
        _event(),
        _market("resolved", resolution_date=datetime(2027, 5, 31, 2, tzinfo=timezone.utc)),
        [_outcome(is_winner=True, resolution_source="api_settlement")],
        NOW,
    )


def test_a_null_resolution_date_gets_no_opinion():
    """NULL is unknown, not future — the same abstention every clock gate here makes."""
    assert not _open_market_outlives_its_finished_event(
        _event(), _market("open", resolution_date=None), [_outcome()], NOW
    )


def test_a_resolution_date_that_is_not_a_datetime_gets_no_opinion():
    """A lookup must never throw the page, and this one is asked of every market.

    `market_assigned_settled` states the rule for a partially-loaded ORM row and
    this gate needs it harder: it is reached for EVERY market on EVERY finished
    event, so unlike the two clock gates beside it, it meets rows whose
    `resolution_date` was never a datetime at all. `>` against one of those raises
    `TypeError` from inside the page build and the whole response is lost —
    `test_a_venue_id_is_not_a_kalshi_ticker_3198::test_the_settled_games_map_carries_the_match_total`
    found it, exactly as six unrelated tests found #5771's naive-datetime case.
    """
    unset = MagicMock()
    unset.status = "open"
    assert not _open_market_outlives_its_finished_event(
        _event(), unset, [_outcome()], NOW
    )


def test_a_naive_resolution_date_is_read_as_utc_and_never_raises():
    """Both directions, because a page build must never throw on a lookup.

    #5771 shipped this coercion after CI raised `can't compare offset-naive and
    offset-aware datetimes` in six tests built on older fixtures; the unit tests
    there all built aware datetimes and saw nothing. Pinned in both directions so
    the coercion cannot quietly decay into an abstention.
    """
    far = (NOW + timedelta(days=300)).replace(tzinfo=None)
    near = (NOW + timedelta(hours=6)).replace(tzinfo=None)
    assert _open_market_outlives_its_finished_event(
        _event(), _market("open", resolution_date=far), [_outcome()], NOW
    )
    assert not _open_market_outlives_its_finished_event(
        _event(), _market("open", resolution_date=near), [_outcome()], NOW
    )


def test_an_empty_outcome_list_gets_no_opinion_from_the_clock_gate_either():
    assert not _open_market_outlives_its_finished_event(
        _event(),
        _market("open", resolution_date=datetime(2027, 5, 31, 2, tzinfo=timezone.utc)),
        [],
        NOW,
    )


# ── The route actually asks them (a correct helper nobody calls changes nothing) ──


def _derby_seed(*, correct_score_source=None):
    """The derby page: four markets, one of each shape the section can hold.

    * `Correct Score` — resolved, nothing graded. #6025's specimen.
    * `BTTS` — resolved AND graded. Must survive.
    * `Who Will Finish Higher` — open, resolving in 2027. #6026's specimen.
    * `Team Corners` — open, resolving with the fixture. The gotcha-#33 cohort,
      and the control that keeps the two withdrawals from reading as "the section
      emptied for some unrelated reason". The derby's own Team Corners row is
      resolved; it is carried here in the open shape because that is the cohort
      #6026's margin exists to protect and it has to be on the page.

    Every one of the four is `other`-classified, checked rather than assumed:
    `Total Corners` was the first choice for the control and
    `_classify_game_market` routes it to `game_total` on the word "Total", where
    this gate cannot reach it — a control in the wrong section proves nothing.
    """
    event = _make_event(
        id=15297724,
        home_team="Manchester United",
        away_team="Manchester City",
        status="completed",
        sport_key="soccer_epl",
        home_score=0,
        away_score=1,
    )
    # Offset from the clock at call time, never a literal date (gotcha #44).
    now = datetime.now(timezone.utc)
    event.commence_time = now - timedelta(hours=8, minutes=20)
    event.completed_at = now - timedelta(hours=6)

    correct_score = _make_futures_market(
        id=60780435,
        name="Manchester United vs Manchester City: Correct Score",
        source="kalshi",
    )
    correct_score.status = "resolved"
    correct_score.event_id = event.id
    correct_score.resolution_date = now - timedelta(hours=6)

    btts = _make_futures_market(
        id=60482257,
        name="Manchester United vs Manchester City: BTTS",
        source="kalshi",
    )
    btts.status = "resolved"
    btts.event_id = event.id
    btts.resolution_date = now - timedelta(hours=6)

    finish_higher = _make_futures_market(
        id=59693538,
        name="Manchester City vs Manchester United: Who Will Finish Higher",
        source="kalshi",
    )
    finish_higher.status = "open"
    finish_higher.event_id = event.id
    finish_higher.resolution_date = now + timedelta(days=260)

    corners = _make_futures_market(
        id=60482266,
        name="Manchester United vs Manchester City: Team Corners",
        source="kalshi",
    )
    corners.status = "open"
    corners.event_id = event.id
    corners.resolution_date = now - timedelta(hours=6)

    outcomes = [
        # The impossible ladder, trimmed to the rows the issue quoted.
        _make_outcome(
            id=1,
            market_id=correct_score.id,
            name="Manchester City wins 1-0",
            probability=0.99,
            resolution_source=correct_score_source,
        ),
        _make_outcome(
            id=2,
            market_id=correct_score.id,
            name="Manchester City wins 6-1",
            probability=0.50,
            resolution_source=correct_score_source,
        ),
        _make_outcome(
            id=3,
            market_id=correct_score.id,
            name="Manchester City wins 4-1",
            probability=0.17,
            resolution_source=correct_score_source,
        ),
        _make_outcome(
            id=4,
            market_id=btts.id,
            name="Both teams score",
            probability=0.01,
            is_winner=False,
            resolution_source="game_score",
        ),
        _make_outcome(
            id=5,
            market_id=finish_higher.id,
            name="Manchester City finishes higher than Manchester United",
            probability=0.91,
        ),
        _make_outcome(
            id=6,
            market_id=finish_higher.id,
            name="Manchester United finishes higher than Manchester City",
            probability=0.23,
        ),
        _make_outcome(
            id=7,
            market_id=corners.id,
            name="City most corners",
            probability=0.74,
        ),
    ]
    return event, [correct_score, btts, finish_higher, corners], outcomes


async def _served(seed):
    """`GET /api/events/15297724/game-markets` over a seeded page."""
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, markets, outcomes = seed
    mock_session = _make_event_detail_session(
        event=event, futures=markets, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

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
                resp = await ac.get("/api/events/15297724/game-markets")
        assert resp.status_code == 200, resp.text
        return resp.json()
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_the_route_withholds_both_specimens_and_keeps_everything_else():
    payload = await _served(_derby_seed())
    served = {r["market_name"] for r in payload["other"]}

    assert "Manchester United vs Manchester City: Correct Score" not in served, (
        "the 240% ladder is still on the page — a reader sees "
        f"'Manchester City wins 6-1 last quote 50%' on a 1-0 game: {payload['other']}"
    )
    assert (
        "Manchester City vs Manchester United: Who Will Finish Higher" not in served
    ), f"a market trading until 2027 is still labelled settled: {payload['other']}"
    assert "Manchester United vs Manchester City: BTTS" in served, (
        "a GRADED settled market lost its rows — this gate has reached the cohort "
        f"it must never touch: {payload['other']}"
    )
    assert "Manchester United vs Manchester City: Team Corners" in served, (
        "a just-finished fixture's own book, still reading `open` because polling "
        f"stopped seeing it, was withheld: {payload['other']}"
    )


@pytest.mark.asyncio
async def test_the_same_ladder_is_served_the_moment_it_is_graded():
    """The control that makes the assertion above non-vacuous.

    The same four markets, differing only in the thing under test: the Correct
    Score outcomes now carry a `resolution_source`. If this ever goes empty, the
    test above is passing because the builder dropped the card for some unrelated
    reason — a classifier, the empty-book filter, the placeholder regex — and not
    because of this gate at all.
    """
    payload = await _served(_derby_seed(correct_score_source="api_settlement"))
    rows = [
        r
        for r in payload["other"]
        if r["market_name"].endswith("Correct Score")
    ]
    assert sorted(r["outcome_name"] for r in rows) == [
        "Manchester City wins 1-0",
        "Manchester City wins 4-1",
        "Manchester City wins 6-1",
    ], payload["other"]


@pytest.mark.asyncio
async def test_the_player_prop_rescue_still_runs_on_a_withheld_market():
    """THE SCOPE CLAIM. This is why the withdrawal is not at the top of the loop.

    A resolved, ungraded market on a finished event whose outcomes are player-prop
    shaped ("Erling Haaland: 1+") is rescued into `player_props` a few lines above
    the withdrawal, where `_grade_settled_prop` grades it off the BOX SCORE and
    needs no `resolution_source` at all — that rail is #1735's whole ship, and
    #1735's rows are exactly this cohort. Withdrawing the market at the top of the
    loop (where #5247 and #5771 sit) would delete them.

    So the same market must be silent in `other` and present in `player_props` in
    one response, which is what this asserts.
    """
    event, markets, outcomes = _derby_seed()
    now = datetime.now(timezone.utc)
    props = _make_futures_market(
        id=60780500,
        name="Manchester United vs Manchester City",
        source="kalshi",
    )
    props.status = "resolved"
    props.event_id = event.id
    props.resolution_date = now - timedelta(hours=6)
    outcomes = outcomes + [
        _make_outcome(
            id=8,
            market_id=props.id,
            name="Erling Haaland: 1+",
            probability=0.62,
        ),
    ]

    payload = await _served((event, markets + [props], outcomes))

    assert "Erling Haaland: 1+" in {
        p["outcome_name"] for p in payload["player_props"]
    }, (
        "the player-prop rescue was taken out with the withdrawal — #1735's rows "
        f"are gone: {payload['player_props']}"
    )
    assert "Erling Haaland: 1+" not in {
        r["outcome_name"] for r in payload["other"]
    }, payload["other"]
