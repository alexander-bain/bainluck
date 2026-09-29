"""#9521 — at halftime the model line kept the reading from before the last score.

`/events/14780549` (Eagles at Bears, MNF 2026-09-28): the Bears led 10–0 with
0:19 left in the 2nd, the model wrote 0.8071, the Eagles scored, and the page
went to Halftime at 10–7. ESPN sends no clock at a break, and
`compute_and_write_stat_model` returned early on `not ee.clock` — so 0.8071, the
model's answer for 10–0, sat on the row and on the chart for the whole break
while every market read ~42%.

The fix: a break's position is known without a clock. "Halftime" and
"End of Nth Quarter/Period" are period boundaries `parse_game_clock` already
prices from "0:00", so a live, clockless reading at a break is priced there.
A clockless reading that is NOT at a break still has no position and is still
skipped (the control).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.utils.win_probability import compute_statistical_win_prob
from tests.test_priorless_stat_model_defers_to_market_8522 import (  # noqa: F401 — shared SQLite writer seam + JSONB compilers
    _AsyncShim,
    _portable_probability_writer,
)

SPORT = "americanfootball_nfl"
SPECIMEN_SPREAD = 3.5  # Bears (home) +3.5 — the row's opening_home_spread
BEFORE_THE_LAST_SCORE = 0.8071  # stat_model stored at 01:37:50Z, 10–0, 0:19 Q2
STAMP = "2026-09-29T01:37:50+00:00"


def _team(espn_id, display_name, abbreviation, location):
    return ESPNTeam(
        espn_id=espn_id,
        name=display_name.split()[-1],
        abbreviation=abbreviation,
        display_name=display_name,
        short_name=display_name.split()[-1],
        nickname=location,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
    )


BEARS = _team("3", "Chicago Bears", "CHI", "Chicago")
EAGLES = _team("21", "Philadelphia Eagles", "PHI", "Philadelphia")


def _board_row(status_detail, *, home=10, away=7, clock=None, period=2):
    """ESPN's NFL board row as `_parse_event` returns it — no clock at a break."""
    return ESPNEvent(
        espn_id="401872963",
        name="Philadelphia Eagles at Chicago Bears",
        short_name="PHI @ CHI",
        date=None,
        status="in",
        status_detail=status_detail,
        period=period,
        clock=clock,
        home_team=BEARS,
        away_team=EAGLES,
        home_score=home,
        away_score=away,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


def _nfl_row_on_disk():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, Sport, WinProbSnapshot

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, WinProbSnapshot.__table__]
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key=SPORT, name="NFL")
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Chicago Bears",
        away_team_name="Philadelphia Eagles",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=85),
        status="live",
        espn_id="401872963",
        commence_time_source="espn",
        opening_home_probability=0.37,
        opening_home_spread=SPECIMEN_SPREAD,
        win_probability_sources={
            "stat_model": {"value": BEFORE_THE_LAST_SCORE, "updated_at": STAMP},
        },
    )
    session.add(event)
    session.commit()
    return session, event


async def _run(board_row):
    from sqlalchemy import select

    from app.models.models import Event, WinProbSnapshot
    from app.utils.espn_helpers import compute_and_write_stat_model

    session, event = _nfl_row_on_disk()
    stats: dict = {}
    wrote = await compute_and_write_stat_model(
        _AsyncShim(session), event, board_row, SPORT, stats
    )
    session.commit()
    session.expire_all()
    row = session.execute(select(Event)).scalar_one()
    snaps = session.execute(select(WinProbSnapshot)).scalars().all()
    return wrote, stats, row, snaps


@pytest.mark.asyncio
async def test_halftime_after_a_score_prices_the_halftime_score_9521():
    """THE SHIP: 10–7 at Halftime, no clock → the model's 10–7 halftime number."""
    wrote, stats, row, snaps = await _run(_board_row("Halftime"))

    expected = compute_statistical_win_prob(
        home_score=10, away_score=7, clock="0:00", period="Halftime",
        sport_key=SPORT, pregame_spread=SPECIMEN_SPREAD,
        opening_home_probability=0.37,
    )
    assert wrote is True and "stat_model_no_clock" not in stats
    stored = row.win_probability_sources["stat_model"]["value"]
    assert stored == pytest.approx(round(expected, 4))
    # Not the 10–0 answer, and nowhere near it: a 3-point lead at the half.
    assert stored < BEFORE_THE_LAST_SCORE - 0.15
    # The chart point says where it was priced: the halftime score, at the break.
    [snap] = snaps
    assert snap.source == "stat_model"
    assert snap.game_state["home_score"] == 10 and snap.game_state["away_score"] == 7
    assert snap.game_state["period"] == "Halftime"


@pytest.mark.asyncio
async def test_end_of_a_quarter_is_priced_at_that_boundary_9521():
    """"End of 1st Quarter" sits at 45:00 left — the same rule, another break."""
    wrote, _stats, row, _snaps = await _run(
        _board_row("End of 1st Quarter", home=7, away=0, period=1)
    )

    expected = compute_statistical_win_prob(
        home_score=7, away_score=0, clock="15:00", period="2nd Quarter",
        sport_key=SPORT, pregame_spread=SPECIMEN_SPREAD,
        opening_home_probability=0.37,
    )
    assert wrote is True
    assert row.win_probability_sources["stat_model"]["value"] == pytest.approx(
        round(expected, 4)
    )


@pytest.mark.asyncio
async def test_a_clockless_reading_that_is_not_a_break_is_still_skipped_9521():
    """CONTROL: no clock mid-quarter is no position — skip, keep counting it."""
    wrote, stats, row, snaps = await _run(_board_row("2nd Quarter"))

    assert wrote is False
    assert stats.get("stat_model_no_clock") == 1
    assert row.win_probability_sources["stat_model"]["value"] == BEFORE_THE_LAST_SCORE
    assert snaps == []
