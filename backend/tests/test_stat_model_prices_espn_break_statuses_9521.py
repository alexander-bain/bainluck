"""#9521 (second half) — ESPN names a real break with its OWN status, not "in".

#9534 priced a break for an "in" reading with no clock. Production never sends
that shape for a real break. `ESPNAPIService._parse_event` maps only
STATUS_IN_PROGRESS to "in"; a break arrives as `status_end_period` or
`status_halftime`, and `compute_and_write_stat_model` returned on
`ee.status != "in"` before it ever looked at the clock. Measured 2026-09-30
00:15Z: MTL @ TOR (/events/15317562) sat at `STATUS_END_PERIOD`, displayClock
"0:00", "End of 1st Period", 1-1, while `stat_model` kept its 23:57Z reading
from 0:38 of the 1st. 15168031 got ONE break reading in three breaks, from the
brief in-progress tick before ESPN switched status.

These fixtures are built by the real parser from board-shaped payloads, so the
status the writer sees is the one production hands it — the #9534 fixture set
`status="in"` by hand and could not see this.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event

from app.services.espn_api import ESPNAPIService
from app.utils.win_probability import compute_statistical_win_prob
from tests.test_priorless_stat_model_defers_to_market_8522 import (  # noqa: F401 — shared SQLite writer seam + JSONB compilers
    _AsyncShim,
    _portable_probability_writer,
)

STAMP = "2026-09-29T23:57:15+00:00"
IN_PERIOD = 0.6893  # 15317562's stat_model at 0:38 of the 1st, 1-1


def _competitor(home_away, espn_id, name, abbreviation, score):
    return {
        "homeAway": home_away,
        "score": str(score),
        "team": {
            "id": espn_id,
            "name": name.split()[-1],
            "abbreviation": abbreviation,
            "displayName": name,
            "shortDisplayName": name.split()[-1],
            "location": " ".join(name.split()[:-1]),
        },
    }


def _board_event(status_name, detail, display_clock, *, period, home, away, state="in"):
    """One scoreboard event as ESPN's board returns it."""
    return {
        "id": "401803001",
        "name": "Montreal Canadiens at Toronto Maple Leafs",
        "shortName": "MTL @ TOR",
        "date": "2026-09-29T23:00Z",
        "status": {
            "displayClock": display_clock,
            "period": period,
            "type": {
                "name": status_name,
                "state": state,
                "detail": detail,
                "completed": False,
            },
        },
        "competitions": [
            {
                "competitors": [
                    _competitor("home", "21", "Toronto Maple Leafs", "TOR", home),
                    _competitor("away", "10", "Montreal Canadiens", "MTL", away),
                ]
            }
        ],
    }


def _parsed(*args, **kwargs):
    ee = ESPNAPIService()._parse_event(_board_event(*args, **kwargs))
    assert ee is not None
    return ee


def _row_on_disk(sport_key):
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

    sport = Sport(key=sport_key, name=sport_key)
    session.add(sport)
    session.flush()
    event = Event(
        sport_id=sport.id,
        home_team_name="Toronto Maple Leafs",
        away_team_name="Montreal Canadiens",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=40),
        status="live",
        espn_id="401803001",
        commence_time_source="espn",
        opening_home_probability=0.6,
        opening_home_spread=-1.5,
        win_probability_sources={"stat_model": {"value": IN_PERIOD, "updated_at": STAMP}},
    )
    session.add(event)
    session.commit()
    return session, event


async def _run(ee, sport_key="icehockey_nhl"):
    from sqlalchemy import select

    from app.models.models import Event, WinProbSnapshot
    from app.utils.espn_helpers import compute_and_write_stat_model

    session, event = _row_on_disk(sport_key)
    stats: dict = {}
    wrote = await compute_and_write_stat_model(_AsyncShim(session), event, ee, sport_key, stats)
    session.commit()
    session.expire_all()
    row = session.execute(select(Event)).scalar_one()
    snaps = session.execute(select(WinProbSnapshot)).scalars().all()
    return wrote, stats, row, snaps


def _expected(sport_key, home, away, period):
    from app.utils.win_probability import model_pregame_spread

    return round(
        compute_statistical_win_prob(
            home_score=home, away_score=away, clock="0:00", period=period,
            sport_key=sport_key, pregame_spread=model_pregame_spread(sport_key, -1.5),
            opening_home_probability=0.6,
        ),
        4,
    )


def test_the_parser_hands_a_break_over_under_espns_own_status_9521():
    """The shape the writer must accept: a break is NOT "in"."""
    assert _parsed("STATUS_END_PERIOD", "End of 1st Period", "0:00", period=1, home=1, away=1).status == "status_end_period"
    assert _parsed("STATUS_HALFTIME", "Halftime", "0:00", period=2, home=10, away=7).status == "status_halftime"


@pytest.mark.asyncio
async def test_the_nhl_intermission_is_priced_at_the_break_9521():
    """THE SPECIMEN: MTL @ TOR, STATUS_END_PERIOD, 1-1 → the End-of-1st price."""
    ee = _parsed("STATUS_END_PERIOD", "End of 1st Period", "0:00", period=1, home=1, away=1)
    wrote, stats, row, snaps = await _run(ee)

    assert wrote is True, stats
    stored = row.win_probability_sources["stat_model"]["value"]
    assert stored == pytest.approx(_expected("icehockey_nhl", 1, 1, "End of 1st Period"))
    assert row.win_probability_sources["stat_model"]["updated_at"] != STAMP
    [snap] = snaps
    assert snap.game_state["period"] == "End of 1st Period"
    assert snap.game_state["clock"] == "0:00"


@pytest.mark.asyncio
async def test_a_goal_late_in_the_period_moves_the_break_reading_9521():
    """The ship's case: a late goal is priced at the break, not left behind."""
    ee = _parsed("STATUS_END_PERIOD", "End of 2nd Period", "0:00", period=2, home=1, away=2)
    wrote, _stats, row, _snaps = await _run(ee)

    assert wrote is True
    stored = row.win_probability_sources["stat_model"]["value"]
    assert stored == pytest.approx(_expected("icehockey_nhl", 1, 2, "End of 2nd Period"))
    assert stored < IN_PERIOD - 0.2  # home now trails: nowhere near the 1-1 reading


@pytest.mark.asyncio
async def test_nfl_halftime_under_status_halftime_is_priced_9521():
    """The MNF shape as the parser really returns it: STATUS_HALFTIME, 10–7."""
    ee = _parsed("STATUS_HALFTIME", "Halftime", "0:00", period=2, home=10, away=7)
    wrote, stats, row, snaps = await _run(ee, "americanfootball_nfl")

    assert wrote is True, stats
    assert row.win_probability_sources["stat_model"]["value"] == pytest.approx(
        _expected("americanfootball_nfl", 10, 7, "Halftime")
    )
    [snap] = snaps
    assert snap.game_state["period"] == "Halftime"


@pytest.mark.asyncio
async def test_the_break_is_priced_at_the_boundary_whatever_clock_rides_along_9521():
    """A stale clock on a break status is not a position — the boundary is."""
    ee = _parsed("STATUS_END_PERIOD", "End of 1st Period", "0:38", period=1, home=1, away=1)
    wrote, _stats, _row, snaps = await _run(ee)

    assert wrote is True
    [snap] = snaps
    assert snap.game_state["clock"] == "0:00"


@pytest.mark.asyncio
async def test_a_break_status_outside_the_clock_sports_is_still_skipped_9521(monkeypatch):
    """CONTROL: soccer's halftime is not priced by this rule (no boundary clock).

    The model is never even asked: it happens to return None for soccer "HT",
    which would hide a rule that let soccer through.
    """
    import app.utils.win_probability as wp

    asked = []
    monkeypatch.setattr(
        wp, "compute_statistical_win_prob", lambda **kw: asked.append(kw) or 0.5
    )
    ee = _parsed("STATUS_HALFTIME", "HT", "45'", period=1, home=1, away=0)
    wrote, _stats, row, snaps = await _run(ee, "soccer_epl")

    assert asked == []
    assert wrote is False
    assert row.win_probability_sources["stat_model"]["value"] == IN_PERIOD
    assert snaps == []


@pytest.mark.asyncio
async def test_a_stopped_game_that_is_not_a_break_is_still_skipped_9521():
    """CONTROL: STATUS_DELAYED is not a break — nothing is priced."""
    ee = _parsed("STATUS_DELAYED", "Delayed", "12:00", period=2, home=1, away=1)
    wrote, _stats, row, snaps = await _run(ee)

    assert wrote is False
    assert row.win_probability_sources["stat_model"]["value"] == IN_PERIOD
    assert snaps == []
