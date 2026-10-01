"""#9208 — a called-off game on a team page's Recent Results said "No result reported".

Production, 390px, 2026-10-01 10:38Z, ``/sport/baseball/mlb/team/new-york-yankees-mlb``:
Orioles @ Yankees 15319530 (``status='suspended'``, ``period='Canceled'``, ESPN 401817103
``STATUS_CANCELED``) reads "Canceled · Sep 27" on the web search card and on its own page, and
"vs Baltimore Orioles · Sep 27 · No result reported" one surface over. The team brief carried
no period, so ``RecentGameCard`` had no word to read. ``stoppage`` carries ESPN's exact
stoppage word on a suspended row, and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.routes.teams import _format_event_brief


class _Sport:
    key = "baseball_mlb"


class _Team:
    id = 6610
    name = "New York Yankees"


class _Event:
    """The specimen row's fields as served by ``/api/events/15319530`` (10:3xZ 10/1)."""

    def __init__(self, *, status: str, period: str | None, scores=(None, None)):
        self.id = 15319530
        self.sport = _Sport()
        self.home_team_id = 6610
        self.home_team_name = "New York Yankees"
        self.away_team_name = "Baltimore Orioles"
        self.commence_time = datetime(2026, 9, 27, 17, 5, tzinfo=timezone.utc)
        self.completed_at = None
        self.status = status
        self.period = period
        self.home_score, self.away_score = scores
        self.win_probability_sources = None
        self.espn_win_prob_home = None
        self.opening_home_probability = 0.522
        self.opening_away_probability = 0.478


def test_the_specimen_brief_says_canceled():
    brief = _format_event_brief(_Event(status="suspended", period="Canceled"), _Team())
    assert brief["status"] == "suspended"
    assert brief["stoppage"] == "Canceled"


def test_postponed_and_the_british_spelling_read_through_the_same_allowlist():
    assert (
        _format_event_brief(_Event(status="suspended", period="Postponed"), _Team())[
            "stoppage"
        ]
        == "Postponed"
    )
    assert (
        _format_event_brief(_Event(status="suspended", period="cancelled"), _Team())[
            "stoppage"
        ]
        == "Canceled"
    )


def test_a_live_period_left_on_a_row_that_went_dark_is_not_a_stoppage():
    """Control: the row is suspended but its period is a period of play."""
    brief = _format_event_brief(_Event(status="suspended", period="Top 7th"), _Team())
    assert brief["stoppage"] is None


def test_only_a_suspended_row_carries_the_word():
    """Control: a completed row with a stale stoppage word keeps its result path."""
    brief = _format_event_brief(
        _Event(status="completed", period="Canceled", scores=(6, 3)), _Team()
    )
    assert brief["stoppage"] is None


def test_a_row_without_a_period_attribute_still_formats():
    """The #5382 fakes carry no ``period``; the formatter must not grow a hard read."""
    event = _Event(status="suspended", period=None)
    del event.period
    assert _format_event_brief(event, _Team())["stoppage"] is None
