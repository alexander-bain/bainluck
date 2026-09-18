"""#6921: the row cap on `/api/events/{id}/history` deleted the game, not the tail.

Every odds read on that route was one statement — `ORDER BY captured_at
LIMIT 3000` — and ascending-plus-LIMIT keeps the OLDEST 3,000 rows. On a
marquee fixture the oldest rows are months of pre-season line drift and the
newest rows are the game itself, so the guard that was there to bound work was
deterministically deleting the half a reader came for.

Measured on production 2026-09-18, from the SERVED payload rather than a model
of it (`GET /api/events/{id}/history`, its own `time_domain` as the axis):

    14638896  NFL, completed   6,885 rows, 5,163 of them before kickoff
              -> the 3,000 kept were ALL pre-kickoff. ONE history point inside
                 the rendered axis, and all 18 sportsbook series end
                 2026-08-26 — three weeks before the game.
    14638444  NFL, completed   3,957 rows, 2,211 before kickoff
              -> 79 of 732 points in-axis; DraftKings and FanDuel both stop at
                 01:36Z on a game that ran to 03:30Z. This is the filed shape.
    15297681  EPL, completed   3,164 rows, 2,928 before kickoff
              -> 17 in-axis on a 19:00 kickoff; the line dies at 19:16Z.

And two MLB games in the same four days banked 3,078 and 3,030 rows inside the
48-hour window the event page asks for, so the LIVE branch — where the rows
being dropped are the leading edge of a chart still being drawn — is over the
old cap too.

These tests drive the REAL route against the bound-honouring stub #6390 owns,
rather than re-implementing the windowing: a replicated window is a window that
can agree with the test and disagree with production. The stub's `captured_at`
arm exists because of this ship — see `_captured_at_bounds` there.

🔴 WHAT MAKES THESE NON-VACUOUS. `_snapshots_with_split_budget` was mutated
back to the single shared read it replaced and this file re-run; four of the
six go red, and the two headline ones reproduce the production symptom exactly
rather than merely failing — `assert 0 == 40` on the settled chart and
`assert []` on the live one, i.e. not one point of either game served. The two
that stay green under the mutant are the controls, which is the point of them.
The populations are sized off the constants rather than off literals, so
raising a ceiling cannot silently retire the guard: the fixture grows with it.

Clock-swept 12/12 (`scripts/clock_sweep.py`); the anchor is `_kickoff()`, and
gotcha #44 is why it looks the way it does.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.models.models import Event, OddsSnapshot, Sport
from app.routes.events import (
    EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP,
    EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP,
    get_event_odds_history,
)
from tests.test_price_table_fold_6390 import _HistoryRouteSession

UTC = timezone.utc

EVENT_ID = 14638444
SPORT_ID = 7

#: Enough pre-kickoff rows to exhaust the pre-window budget on their own, which
#: is the whole condition: below it the old shared cap had spare room and the
#: game came through. Production's worst measured pre-kickoff population is
#: 5,163 rows (14638896); this is the smallest number that reproduces it.
PRE_KICKOFF_ROWS = EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP + 200

#: The game. Production's NFL specimens bank 1,722–1,746 in-window rows; a
#: handful is enough to tell "served" from "deleted", and the count is the
#: assertion either way.
IN_GAME_ROWS = 40


def _kickoff():
    """Twelve hours ago, to the minute.

    Gotcha #44: the offset comes FIRST and the truncation second, and the
    anchor carries no `if`. An absolute literal here read `2026-09-18 00:15Z`
    and `clock_sweep.py` caught it at three of twelve faked clocks — at
    2026-09-17 16:00Z that kickoff is in the FUTURE, `_event_is_really_finished`
    says no, and the settled specimen quietly takes the live branch instead.
    Twelve hours is comfortably past `completed_at` (kickoff + 3h15) at every
    point in the sweep.
    """
    return (datetime.now(UTC) - timedelta(hours=12)).replace(
        second=0, microsecond=0
    )


def _sport():
    return Sport(id=SPORT_ID, key="americanfootball_nfl", name="NFL")


def _snapshot(when, *, bookmaker="draftkings", snap_id):
    return OddsSnapshot(
        id=snap_id,
        event_id=EVENT_ID,
        bookmaker=bookmaker,
        captured_at=when,
        home_moneyline=-150,
        away_moneyline=130,
        home_win_probability=0.6,
        away_win_probability=0.4,
        valid_until=None,
    )


def _population(kickoff, *, game_hours=3.0):
    """Months of pre-season drift, then the game — production's shape."""
    rows = []
    for i in range(PRE_KICKOFF_ROWS):
        # Spread back over ~4 months, the span 14638896 actually carries.
        rows.append(
            _snapshot(
                kickoff - timedelta(days=120) + timedelta(minutes=i * 50),
                snap_id=1_000_000 + i,
            )
        )
    step = timedelta(hours=game_hours) / IN_GAME_ROWS
    for j in range(IN_GAME_ROWS):
        rows.append(
            _snapshot(kickoff + step * (j + 1), snap_id=2_000_000 + j)
        )
    return rows


def _finished_event(kickoff):
    event = Event(
        id=EVENT_ID,
        sport_id=SPORT_ID,
        home_team_name="Buffalo Bills",
        away_team_name="Detroit Lions",
        commence_time=kickoff,
        status="completed",
        home_score=24,
        away_score=21,
        completed_at=kickoff + timedelta(hours=3, minutes=15),
    )
    event.sport = _sport()
    return event


def _live_event(kickoff):
    event = Event(
        id=EVENT_ID,
        sport_id=SPORT_ID,
        home_team_name="Buffalo Bills",
        away_team_name="Detroit Lions",
        commence_time=kickoff,
        status="live",
        home_score=14,
        away_score=10,
        completed_at=None,
    )
    event.sport = _sport()
    return event


def _history(event, rows, *, hours=48):
    session = _HistoryRouteSession(event, [], rows)
    payload = asyncio.run(
        get_event_odds_history(EVENT_ID, hours=hours, db=session)
    )
    return payload, session


def _points_at_or_after(payload, when):
    return [
        p
        for p in payload["history"]
        if datetime.fromisoformat(p["timestamp"]) >= when
    ]


def _book_points_at_or_after(payload, when, book="draftkings"):
    """The SPORTSBOOK series, which is what the production reads measured.

    `history` is the aggregate and carries one appended edge point at
    `completed_at` (the settled chart's right edge), so it runs one longer than
    the rows served. `bookmaker_history` is the raw series per book — it is
    where "DraftKings stops at 01:36Z on a game that ran to 03:30Z" was read,
    and it is the number that moves when the budget does.
    """
    return [
        p
        for p in payload["bookmaker_history"].get(book, [])
        if datetime.fromisoformat(p["timestamp"]) >= when
    ]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_a_settled_games_own_minutes_survive_a_full_pre_kickoff_budget():
    """The filed defect. 3,200 pre-kickoff rows must not delete the game."""
    kickoff = _kickoff()
    payload, _ = _history(_finished_event(kickoff), _population(kickoff))

    in_game = _book_points_at_or_after(payload, kickoff)
    assert len(in_game) == IN_GAME_ROWS, (
        "the chart is a chart of the game; the pre-season drift may not spend "
        "the budget the game needs"
    )
    # The filed symptom stated as the reader met it: the line must reach the
    # end of the game, not stop partway through it.
    assert datetime.fromisoformat(in_game[-1]["timestamp"]) >= kickoff + timedelta(
        hours=2, minutes=55
    )


def test_the_live_branch_keeps_its_leading_edge_too():
    """Two MLB games cleared the old cap inside the 48h window the page asks
    for, so this branch drops the newest rows on a chart still being drawn."""
    kickoff = (datetime.now(UTC) - timedelta(hours=2)).replace(
        second=0, microsecond=0
    )
    payload, _ = _history(
        _live_event(kickoff), _population(kickoff, game_hours=1.5)
    )

    in_game = _book_points_at_or_after(payload, kickoff)
    assert in_game, "a live chart that stops at kickoff is the same defect"


# ---------------------------------------------------------------------------
# The control: additive, never subtractive
# ---------------------------------------------------------------------------


def test_the_pre_kickoff_series_is_not_thinned_to_pay_for_the_game():
    """Splitting the budget must ADD the game, never buy it with the season.

    `OddsChart`'s "All" range renders every point it is handed, so the opening
    line and the pre-match drift are drawn and not dead weight — which is also
    why the fix is not a flip to DESC.
    """
    kickoff = _kickoff()
    payload, _ = _history(_finished_event(kickoff), _population(kickoff))

    pre = [
        p
        for p in payload["history"]
        if datetime.fromisoformat(p["timestamp"]) < kickoff
    ]
    # The pre-window read keeps the same ORDER BY, ceiling and population the
    # single shared cap applied, so it returns exactly what used to be served.
    assert len(pre) == EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP


def test_a_small_event_is_served_whole_and_unchanged():
    """Control. Below either ceiling the split must be invisible."""
    kickoff = _kickoff()
    rows = [
        _snapshot(kickoff - timedelta(minutes=(60 - i) * 3), snap_id=i)
        for i in range(60)
    ] + [
        _snapshot(kickoff + timedelta(minutes=(i + 1) * 2), snap_id=500 + i)
        for i in range(30)
    ]
    payload, _ = _history(_finished_event(kickoff), rows)

    assert payload["snapshot_count"] == 90
    assert len(_book_points_at_or_after(payload, kickoff)) == 30


def test_an_event_with_no_kickoff_has_nothing_to_split_on_and_keeps_more():
    """No `commence_time` means no trustworthy boundary.

    The read degrades to the single statement it replaced, but at the SUM of
    the two ceilings — never back to the old 3,000, which would re-impose the
    defect on exactly the rows with the least metadata to defend them.
    """
    kickoff = _kickoff()
    event = _finished_event(kickoff)
    event.commence_time = None
    event.completed_at = None
    event.status = "completed"

    payload, session = _history(event, _population(kickoff))

    assert payload["snapshot_count"] == PRE_KICKOFF_ROWS + IN_GAME_ROWS
    assert (
        PRE_KICKOFF_ROWS + IN_GAME_ROWS
        <= EVENT_HISTORY_PRE_WINDOW_SNAPSHOT_CAP
        + EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP
    ), "the fixture must sit under the combined ceiling for this to be a read"
    assert session.odds_id_filters, "the route did read odds_snapshots"


# ---------------------------------------------------------------------------
# The ceilings are still ceilings
# ---------------------------------------------------------------------------


def test_the_in_window_budget_is_a_real_bound():
    """A runaway writer must still be bounded — this is a wider guard, not none."""
    kickoff = _kickoff()
    over = EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP + 50
    rows = [
        _snapshot(kickoff + timedelta(seconds=i), snap_id=3_000_000 + i)
        for i in range(over)
    ]
    payload, _ = _history(_finished_event(kickoff), rows)

    assert payload["snapshot_count"] == EVENT_HISTORY_IN_WINDOW_SNAPSHOT_CAP
