"""#10673 — a model holding still on a live game must keep gaining stored readings.

`/events/15324650` (MIL @ SD, live, 04:17Z Oct 7): the stream re-published the
Bain Luck Model at 0.9262 at 04:15:24 and 04:16:24, but the stored `stat_model`
series ended at 04:11:24. `_create_or_update_win_prob_snapshot` writes a row on a
value change, and since live/035 also once a caller's `max_gap_seconds` has
passed. The venue writers pass that floor. Both `stat_model` writers passed
nothing, so an unchanged model only bumped `reading_count`. A fresh page load
read the 5m57s gap as wider than the #7878 contract's G = 300 s, withdrew the
line and captioned "none in the 5m since".

Each case has its control (same call, floor not yet breached, or the game
over), so a writer that simply stopped deduplicating fails here too.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event as sa_event

from app.tasks.snapshots import STAT_MODEL_LIVE_HEARTBEAT_S
from app.utils.win_probability import compute_statistical_win_prob
from tests.test_priorless_stat_model_defers_to_market_8522 import (  # noqa: F401 — shared SQLite writer seam + JSONB compilers
    _AsyncShim,
    _portable_probability_writer,
)
from tests.test_stat_model_prices_the_break_9521 import (
    SPECIMEN_SPREAD,
    SPORT,
    _board_row,
)

APP = Path(__file__).resolve().parents[1] / "app"

# A mid-quarter reading the 9521 rig already prices: 10–7, 5:00 left in the 2nd.
CLOCK = "5:00"
PERIOD = 2
#: What the writer stores as the period (`_sanitize_period` of ESPN's detail).
#: The stored reading must carry it too, or the pass appends for a PERIOD change
#: and the ship test passes for the wrong reason.
PERIOD_LABEL = "2nd Quarter"


def _model_value() -> float:
    return round(
        compute_statistical_win_prob(
            home_score=10, away_score=7, clock=CLOCK, period=PERIOD_LABEL,
            sport_key=SPORT, pregame_spread=SPECIMEN_SPREAD,
            opening_home_probability=0.37,
        ),
        4,
    )


def _live_row_with_a_stored_reading(*, age_seconds: float, status: str = "live"):
    """The 9521 NFL row, plus the model's own reading stored ``age_seconds`` ago
    at exactly the value this pass will compute — a model holding still."""
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
    value = _model_value()
    stored_at = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    event = Event(
        sport_id=sport.id,
        home_team_name="Chicago Bears",
        away_team_name="Philadelphia Eagles",
        commence_time=datetime.now(timezone.utc) - timedelta(minutes=85),
        status=status,
        espn_id="401872963",
        commence_time_source="espn",
        opening_home_probability=0.37,
        opening_home_spread=SPECIMEN_SPREAD,
        win_probability_sources={
            "stat_model": {"value": value, "updated_at": stored_at.isoformat()},
        },
    )
    session.add(event)
    session.flush()
    session.add(
        WinProbSnapshot(
            event_id=event.id,
            source="stat_model",
            captured_at=stored_at,
            home_win_probability=value,
            away_win_probability=round(1.0 - value, 4),
            game_state={"clock": CLOCK, "period": PERIOD_LABEL, "time_source": "espn"},
            reading_count=3,
        )
    )
    session.commit()
    return session, event, stored_at


async def _one_espn_pass(*, age_seconds: float, status: str = "live"):
    from sqlalchemy import select

    from app.models.models import WinProbSnapshot
    from app.utils.espn_helpers import compute_and_write_stat_model

    session, event, stored_at = _live_row_with_a_stored_reading(
        age_seconds=age_seconds, status=status
    )
    wrote = await compute_and_write_stat_model(
        _AsyncShim(session), event, _board_row(PERIOD_LABEL, clock=CLOCK, period=PERIOD),
        SPORT, {},
    )
    session.commit()
    session.expire_all()
    snaps = (
        session.execute(select(WinProbSnapshot).order_by(WinProbSnapshot.captured_at))
        .scalars()
        .all()
    )
    return wrote, snaps, stored_at


@pytest.mark.asyncio
async def test_an_unchanged_model_past_the_floor_stores_a_new_reading_10673():
    """THE SHIP: 90 s of the model holding still → a second stored reading, now."""
    wrote, snaps, stored_at = await _one_espn_pass(age_seconds=90)

    assert wrote is True
    assert len(snaps) == 2, "a live model holding still must keep gaining stored readings"
    first, heartbeat = snaps
    assert float(heartbeat.home_win_probability) == float(first.home_win_probability)
    assert heartbeat.captured_at > stored_at + timedelta(seconds=60)
    assert heartbeat.reading_count == 1


@pytest.mark.asyncio
async def test_an_unchanged_model_inside_the_floor_still_dedups_10673():
    """CONTROL: inside the floor the reading is counted, not stored again."""
    wrote, snaps, _stored_at = await _one_espn_pass(age_seconds=10)

    assert wrote is True
    [only] = snaps
    assert only.reading_count == 4


@pytest.mark.asyncio
async def test_a_completed_game_gets_no_heartbeat_10673():
    """CONTROL (#922): once OUR row is completed, ESPN still saying "in" must not
    extend the series — the terminal reading is refreshed in place."""
    wrote, snaps, _stored_at = await _one_espn_pass(age_seconds=600, status="completed")

    assert wrote is True
    [only] = snaps
    assert only.reading_count == 4


def _snapshot_calls_by_source():
    found = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "_create_or_update_win_prob_snapshot":
                continue
            kwargs = {k.arg: k.value for k in node.keywords}
            source = kwargs.get("source")
            if isinstance(source, ast.Constant) and source.value == "stat_model":
                gap = kwargs.get("max_gap_seconds")
                found.append(
                    (str(path.relative_to(APP)), None if gap is None else ast.unparse(gap))
                )
    return found


def test_every_stat_model_chart_writer_passes_the_live_floor_10673():
    """Pins the SET of `stat_model` writers, not one file: a third writer added
    without the floor, or either of these losing it, reddens here. The odds-poll
    arm sits deep in a per-sport loop, so this is its guard."""
    assert sorted(_snapshot_calls_by_source()) == [
        ("tasks/odds_polling.py", "STAT_MODEL_LIVE_HEARTBEAT_S"),
        ("utils/espn_helpers.py", "STAT_MODEL_LIVE_HEARTBEAT_S"),
    ]


def test_the_floor_keeps_stored_readings_inside_the_evidence_contract_10673():
    """The floor plus the ESPN pass's measured lap (60 s beat, p95 81 s, #3251)
    must stay inside G, or a quiet stretch still reads as a hole."""
    from app.utils.winprob_evidence import EVIDENCE_RESOLUTION_S

    assert STAT_MODEL_LIVE_HEARTBEAT_S + 81 < EVIDENCE_RESOLUTION_S
