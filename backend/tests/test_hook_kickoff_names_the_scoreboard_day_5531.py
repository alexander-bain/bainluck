"""#5531 — a hook's kickoff evidence names the day the game is played, not the UTC day.

Before #5531 the evidence line formatted the raw instant, so tonight's Falcons at Packers (8:15 PM ET
Thursday Sep 24, stored `2026-09-25T00:15Z`) reached the model as "scheduled for Sep 25, 2026", and
the prompt tells the model to anchor its sentence on that date. The hook queue wrote nothing from
9/13 to 9/24, so no reader saw it; #5531's queue fix is what would have published it on every US
evening game. Fixed instants only: no anchor here depends on the clock (gotcha #44).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.hook_prompt import build_hook_evidence

_BEFORE_ALL = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _kickoff_fact(commence: datetime) -> str:
    (fact, *_rest) = build_hook_evidence(
        market_name="Atlanta vs Green Bay",
        event_commence_time=commence,
        event_home_team="Green Bay Packers",
        event_away_team="Atlanta Falcons",
        now=_BEFORE_ALL,
    )
    return fact.fact


@pytest.mark.parametrize(
    "commence, expected",
    [
        # Thursday night: after midnight UTC, still Thursday on the scoreboard.
        (datetime(2026, 9, 25, 0, 15, tzinfo=timezone.utc), "Sep 24, 2026, 8:15 PM ET"),
        # Sunday afternoon: same day in both zones — the control.
        (datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc), "Sep 27, 2026, 1:00 PM ET"),
        # Winter (EST, UTC-5), late game crossing midnight UTC.
        (datetime(2026, 12, 8, 1, 15, tzinfo=timezone.utc), "Dec 7, 2026, 8:15 PM ET"),
        # A naive instant from a writer that drops the zone is read as UTC, as `_aware` does.
        (datetime(2026, 9, 25, 0, 15), "Sep 24, 2026, 8:15 PM ET"),
    ],
)
def test_kickoff_evidence_names_the_scoreboard_day(commence, expected):
    assert _kickoff_fact(commence) == (
        f"Atlanta Falcons vs Green Bay Packers is scheduled for {expected}."
    )


def test_the_utc_day_is_not_what_the_model_is_given():
    fact = _kickoff_fact(datetime(2026, 9, 25, 0, 15, tzinfo=timezone.utc))
    assert "Sep 25" not in fact, fact
