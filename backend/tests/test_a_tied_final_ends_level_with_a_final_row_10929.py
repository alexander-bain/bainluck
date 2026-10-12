"""#10929 — a tied final's chart reads Final and ends level, not on a live clock.

Seen on production 2026-10-12 by shopper (pass-0362), ``/events/14780555`` at
390px: Commanders 27-27 Giants, NFL, settled in overtime. The resting readout
under the chart read **"0:55 - OT · 1:45 PM"** (BAL-ATL, a decided game, read
"Final") and the line ended on the Commanders at **72%**. Served history ended
at the 20:45:06Z "0:55 - OT" sighting; ``completed_at`` was 20:46:05Z.

The terminal-result point in ``get_event_odds_history`` fired only when one side
won, so a tie never got its ``espn_history`` row reading ``Final`` — the row the
readout takes its clock from — nor a terminal point for that row to sit on.

The rig executes ``get_event_odds_history`` itself on the 8951 session, with the
event's ESPN rows answered at their row shape.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import get_event_odds_history, scored_tie_ends_level
from tests.test_history_window_stale_open_event import _Result
from tests.test_settled_fight_chart_ends_on_result_8951 import _Session

UTC = timezone.utc
EVENT_ID = 14780555
HOME = "Washington Commanders"
AWAY = "New York Giants"
NFL = "americanfootball_nfl"


def _kickoff():
    """Four hours ago, to the minute. Offset first, truncate second (gotcha #44)."""
    return (datetime.now(UTC) - timedelta(hours=4)).replace(second=0, microsecond=0)


def _event(k, *, home_score=27, away_score=27, sport_key=NFL, completed=True):
    return SimpleNamespace(
        id=EVENT_ID,
        status="completed" if completed else "live",
        commence_time=k,
        completed_at=k + timedelta(hours=3, minutes=26, seconds=5) if completed else None,
        home_team_name=HOME,
        away_team_name=AWAY,
        home_score=home_score,
        away_score=away_score,
        sport=SimpleNamespace(key=sport_key),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.72}},
    )


def _book(bookmaker, captured_at, valid_until, p, snap_id):
    price = round(100 * p / (1 - p))
    return SimpleNamespace(
        id=snap_id,
        event_id=EVENT_ID,
        bookmaker=bookmaker,
        captured_at=captured_at,
        valid_until=valid_until,
        home_moneyline=-price,
        away_moneyline=price,
        home_win_probability=p,
        away_win_probability=round(1 - p, 4),
        draw_probability=None,
        home_spread=None,
        away_spread=None,
        home_spread_odds=None,
        away_spread_odds=None,
        over_under=None,
        over_odds=None,
        under_odds=None,
        projected_home_score=None,
        projected_away_score=None,
    )


def _books(k):
    rows = []
    for i, (book, p) in enumerate(
        (("draftkings", 0.55), ("fanduel", 0.56), ("betmgm", 0.55)), start=1
    ):
        rows.append(_book(book, k - timedelta(minutes=30), k + timedelta(hours=3, minutes=25), p, i))
    return rows


def _kalshi(k):
    """Every two minutes through the game, ending on the Commanders at 72%."""
    rows = []
    for m in range(0, 206, 2):
        rows.append(SimpleNamespace(
            event_id=EVENT_ID,
            captured_at=k + timedelta(minutes=m),
            source="kalshi",
            home_win_probability=0.55 if m < 200 else 0.72,
            away_win_probability=0.45 if m < 200 else 0.28,
            draw_probability=None,
            game_state={"market_name": f"{AWAY} at {HOME}"},
        ))
    return rows


def _espn(k, score):
    """ESPN's sightings, the last one the specimen's '0:55 - OT' at 27-27."""
    rows = []
    for m, clock, period, h, a in (
        (10, "10:12", "10:12 - 1st Quarter", 0, 0),
        (90, "2:00", "2:00 - 2nd Quarter", 14, 10),
        (170, "0:00", "0:00 - 4th Quarter", 24, 24),
        (205, "0:55", "0:55 - OT", score[0], score[1]),
    ):
        rows.append(SimpleNamespace(
            event_id=EVENT_ID,
            captured_at=k + timedelta(minutes=m, seconds=6),
            home_win_probability=None,
            away_win_probability=None,
            home_score=h,
            away_score=a,
            game_clock=clock,
            period=period,
        ))
    return rows


class _EspnSession(_Session):
    def __init__(self, event, books, kalshi, espn):
        super().__init__(event, books, kalshi, [])
        self.espn = espn

    async def execute(self, statement, *a, **kw):
        if "espn_snapshots" in str(statement):
            return _Result(self.espn)
        return await super().execute(statement, *a, **kw)


def _serve(event, score=(27, 27)):
    k = event.commence_time
    session = _EspnSession(event, _books(k), _kalshi(k), _espn(k, score))
    return asyncio.run(
        get_event_odds_history(
            event_id=EVENT_ID, hours=24, response=MagicMock(headers={}), db=session
        )
    )


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_tied_finals_last_state_row_reads_final_with_the_level_score():
    payload = _serve(_event(_kickoff()))

    last = payload["espn_history"][-1]
    assert last["period"] == "Final", f"the readout still ends on {last['period']!r}"
    assert last["game_clock"] == "Final"
    assert (last["home_score"], last["away_score"]) == (27, 27)


def test_the_tied_finals_line_ends_level_on_the_final_rows_minute():
    payload = _serve(_event(_kickoff()))

    final_row = payload["espn_history"][-1]
    tail = payload["aggregate_line"][-1]
    assert tail["home_probability"] == 0.5, (
        f"the line still ends on the Commanders at {tail['home_probability']}"
    )
    # The readout takes its state from the point at the Final row's minute; a
    # Final row with no drawn point under it is dropped by the chart.
    assert tail["timestamp"] == final_row["timestamp"]
    assert payload["win_prob_history"]["kalshi"][-1]["home_probability"] == 0.5
    assert payload["history"][-1]["home_probability"] == 0.5
    assert payload["history"][-1]["away_probability"] == 0.5
    assert payload["history"][-1]["bookmaker_count"] == 0


# ---------------------------------------------------------------------------
# Controls — what must not move
# ---------------------------------------------------------------------------


def test_a_decided_final_still_ends_on_its_winner():
    k = _kickoff()
    payload = _serve(_event(k, home_score=30, away_score=27), score=(30, 27))

    assert payload["aggregate_line"][-1]["home_probability"] == 1.0
    assert payload["espn_history"][-1]["period"] == "Final"


def test_a_live_tie_is_not_ended():
    payload = _serve(_event(_kickoff(), completed=False))

    assert payload["espn_history"][-1]["period"] == "0:55 - OT"
    assert all(h.get("bookmaker_count") != 0 for h in payload["history"])


def test_a_soccer_draw_keeps_its_line():
    """Draw-priced: the line is "the home side wins", not a two-way split."""
    payload = _serve(_event(_kickoff(), sport_key="soccer_epl"))

    assert payload["espn_history"][-1]["period"] == "0:55 - OT"
    assert all(h.get("bookmaker_count") != 0 for h in payload["history"])


def test_a_scoreless_final_is_not_called_final():
    payload = _serve(_event(_kickoff(), home_score=0, away_score=0), score=(0, 0))

    assert payload["espn_history"][-1]["period"] == "0:55 - OT"
    assert all(h.get("bookmaker_count") != 0 for h in payload["history"])


def test_the_level_rule():
    assert scored_tie_ends_level(27, 27, NFL) is True
    assert scored_tie_ends_level(27, 24, NFL) is False
    assert scored_tie_ends_level(0, 0, NFL) is False
    assert scored_tie_ends_level(1, 1, "soccer_epl") is False
    assert scored_tie_ends_level(None, 27, NFL) is False
    assert scored_tie_ends_level(27, 27, None) is True
