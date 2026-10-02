"""#10186 — last night's final is still "today's final" the morning after.

#9211 lifted a club's finished game only while its kickoff fell on today's
EASTERN day, so a night game dropped out at midnight ET, minutes after it
ended. Production 2026-10-02 09:55Z: Steelers at Browns (TNF, kickoff 00:15Z =
8:15 PM ET Oct 1, final 27–24) — `steelers` printed 13 upcoming games first and
the result as card 16, and the dropdown left it out.

The window now opens at the earlier of Eastern midnight and `now - 18 h`, for
BOTH /search (`_todays_final_order_key`) and the dropdown
(`_lead_team_todays_final_query`). Pinned at the specimen's clock (fails on
master), with a control past the window and the #9211 afternoon case.
Behaviour on a real Postgres: the #9211 integration file plus the night-game
case added there.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, literal_column
from sqlalchemy.dialects import postgresql

from app.models.models import Event
from app.routes import events as ev

KICKOFF = datetime(2026, 10, 2, 0, 15, tzinfo=timezone.utc)  # 8:15 PM ET Thu 10/1
MORNING_AFTER = datetime(2026, 10, 2, 9, 55, tzinfo=timezone.utc)  # 5:55 AM ET Fri
PAST_WINDOW = KICKOFF + ev._RECENT_FINAL_LOOKBACK + timedelta(minutes=1)
SUNDAY_AFTERNOON = datetime(2026, 9, 27, 21, 15, tzinfo=timezone.utc)  # #9211 chiefs
STATUS = case((literal_column("x") == 1, 7), else_=8)


def _sql(expr) -> str:
    return str(
        expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _in_window(now: datetime, kickoff: datetime) -> bool:
    return ev._recent_final_window_start(now) <= kickoff <= now


class TestTheWindow:
    def test_a_night_game_survives_midnight_eastern(self):
        # The specimen: Eastern midnight (04:00Z 10/2) is AFTER the kickoff.
        assert ev._eastern_day_start(MORNING_AFTER) > KICKOFF
        assert _in_window(MORNING_AFTER, KICKOFF)

    def test_it_lets_go_once_the_lookback_has_passed(self):
        # Control: the next afternoon (18:16Z = 2:16 PM ET) it is old news.
        assert not _in_window(PAST_WINDOW, KICKOFF)

    def test_the_window_only_widens_the_eastern_day(self):
        for now in (MORNING_AFTER, PAST_WINDOW, SUNDAY_AFTERNOON):
            assert ev._recent_final_window_start(now) <= ev._eastern_day_start(now)

    def test_an_afternoon_final_is_still_lifted(self):
        # #9211's case: Chiefs at Miami, kicked off 17:00Z Sunday.
        assert _in_window(SUNDAY_AFTERNOON, datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc))

    def test_the_lookback_covers_the_morning_after_on_the_west_coast(self):
        # 8:15 PM ET kickoff, still lifted at 9 AM PT (16:00Z) the next day.
        assert _in_window(datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc), KICKOFF)


class TestBothSurfacesReadIt:
    def test_search_key_opens_at_the_shared_instant(self):
        sql = _sql(ev._todays_final_order_key(True, STATUS, (Event.id,), MORNING_AFTER))
        assert "events.commence_time >= '2026-10-01 15:55:00+00:00'" in sql, sql
        # The ceiling stays the end of today's Eastern day.
        assert "events.commence_time < '2026-10-03 04:00:00+00:00'" in sql, sql
        assert "timezone" not in sql, sql

    def test_dropdown_query_opens_at_the_shared_instant(self):
        sql = _sql(ev._lead_team_todays_final_query(4, "Pittsburgh Steelers", MORNING_AFTER))
        assert "events.commence_time >= '2026-10-01 15:55:00+00:00'" in sql, sql
        assert "events.commence_time <= '2026-10-02 09:55:00+00:00'" in sql, sql
