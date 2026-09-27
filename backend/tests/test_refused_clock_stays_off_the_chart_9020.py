"""#9020 clock half, CERT-3657 repair — a refused clock stays off the chart too.

## what the first cut left open

`update_event_fields_from_espn` refused ESPN's quarter-rollover reading
(`'4:38 - 4th Quarter'` two minutes after `'End of 3rd Quarter'`) from the
`events` row. But the SAME pass then ran `write_espn_win_probability`, which
appended the raw reading to `espn_snapshots` and to the ESPN
`win_prob_snapshots.game_state`. `/history` serves both, the readout under the
hero (`computeLastChartPoint` → `GamePlayCard`) takes the newest snapshot that
carries a clock, and so the page still showed two clocks: the row's
`End of 3rd Quarter 0:00` in the hero and `4:38 - 4th Quarter` below it
(CERT-3657's exact-head reproduction; refusal count 1).

## what is asserted here

The REAL loop — `espn_sync._process_live_sport` with the real matcher, the real
field writer, the real ESPN win-probability writer and the real stat model —
runs one pass against a real (SQLite) database seeded with SMU's board
(`espn_snapshots`, 15316003). Then the rows are read back from the database and
projected exactly as `/history` serves them, and the served tail is compared to
the fixture the frontend readout test renders
(`frontend/__tests__/fixtures/refusedRolloverHistory9020.json`), so the chain
row → snapshot → served JSON → readout is one pinned sequence.

Every refusal has a twin that lands (gotcha #43): the real `14:59 - 4th Quarter`
reading after the break writes its clock to the row, the snapshot and both
`game_state`s; the probability and score of the refused reading still land.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from tests.test_priorless_stat_model_defers_to_market_8522 import (
    _portable_probability_writer,  # noqa: F401 - shared recording/SQLite write seam
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


SPORT = "americanfootball_ncaaf"
ESPN_ID = "401752900"
END_Q3 = ("End of 3rd Quarter", "0:00")
ROLLOVER = ("4:38 - 4th Quarter", "4:38")
REAL_Q4 = ("14:59 - 4th Quarter", "14:59")
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "__tests__" / "fixtures" / "refusedRolloverHistory9020.json"
)


def _ago(seconds: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _board_reading(detail, clock, *, home_score=21, away_score=10, prob=0.83):
    from app.services.espn_api import ESPNEvent, ESPNTeam

    def _team(espn_id, name, abbreviation):
        return ESPNTeam(
            espn_id=espn_id, name=name, abbreviation=abbreviation,
            display_name=name, short_name=name, nickname=None,
            primary_color=None, secondary_color=None, logo_url=None,
            logo_url_dark=None, record=None,
        )

    return ESPNEvent(
        espn_id=ESPN_ID,
        name="Opponent at SMU Mustangs",
        short_name="OPP @ SMU",
        date=_ago(3 * 3600),
        status="in",
        status_detail=detail,
        period=4 if "4th" in detail else 3,
        clock=clock,
        home_team=_team("2567", "SMU Mustangs", "SMU"),
        away_team=_team("9999", "Opponent", "OPP"),
        home_score=home_score,
        away_score=away_score,
        venue=None,
        broadcasts=[],
        home_win_probability=prob,
    )


async def _one_live_pass(reading, *, board=None):
    """One real `_process_live_sport` pass over SMU's row; the DATABASE read back.

    ``board`` seeds `espn_snapshots` as ``(captured_at, period, clock)`` — what
    ESPN published on earlier passes. Default: SMU's own tail before the
    rollover pass.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, ESPNSnapshot, Event, ScoreSnapshot, Sport, Team, WinProbSnapshot,
    )
    from app.tasks import espn_sync
    from app.utils.espn_helpers import (
        compute_and_write_stat_model,
        match_event_to_espn,
        update_event_fields_from_espn,
        write_espn_win_probability,
    )

    if board is None:
        board = [
            (_ago(180), "0:42 - 3rd Quarter", "0:42"),
            (_ago(120), *END_Q3),
            (_ago(60), *END_Q3),
        ]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__, Team.__table__, Event.__table__,
            ScoreSnapshot.__table__, ESPNSnapshot.__table__,
            WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key=SPORT, name=SPORT)
    session.add(sport)
    session.flush()
    row = Event(
        sport_id=sport.id,
        home_team_name="SMU Mustangs",
        away_team_name="Opponent",
        commence_time=_ago(3 * 3600),
        commence_time_source="espn",
        status="live",
        period=END_Q3[0],
        game_clock=END_Q3[1],
        home_score=21,
        away_score=10,
        espn_id=ESPN_ID,
        opening_home_probability=0.7,
        win_probability_sources={},
    )
    session.add(row)
    session.commit()
    event_id = row.id
    for captured_at, period, clock in board:
        session.add(ESPNSnapshot(
            event_id=event_id, captured_at=captured_at, period=period,
            game_clock=clock, home_win_probability=0.8, away_win_probability=0.2,
            home_score=21, away_score=10,
        ))
    session.commit()

    class _Nested:
        def __init__(self, inner):
            self._tx = inner.begin_nested()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if exc_type is None:
                self._tx.commit()
            else:
                self._tx.rollback()
            return False

    class _AsyncShim:
        """The writers are async and this engine is not; nothing else is shimmed."""

        def __init__(self, inner):
            self._s = inner

        async def execute(self, statement, *args, **kwargs):
            return self._s.execute(statement, *args, **kwargs)

        def add(self, obj):
            self._s.add(obj)

        async def flush(self):
            self._s.flush()

        async def commit(self):
            self._s.commit()

        def begin_nested(self):
            return _Nested(self._s)

    async def _no_team(*_a, **_k):
        return None

    async def _noop(*_a, **_k):
        return None

    stats: dict = {"events_synced": 0, "events_updated": 0, "errors": []}
    await espn_sync._process_live_sport(
        _AsyncShim(session), SPORT, [reading], stats,
        _ago(6 * 3600), _ago(5 * 3600),
        espn_sync.espn_team_matches, _no_team, _noop,
        match_event_to_espn, update_event_fields_from_espn,
        write_espn_win_probability, compute_and_write_stat_model, _noop,
    )
    session.commit()

    session.expire_all()
    row = session.execute(select(Event).where(Event.id == event_id)).scalar_one()
    espn_rows = session.execute(
        select(ESPNSnapshot)
        .where(ESPNSnapshot.event_id == event_id)
        .order_by(ESPNSnapshot.captured_at)
    ).scalars().all()
    wp_rows = session.execute(
        select(WinProbSnapshot)
        .where(WinProbSnapshot.event_id == event_id)
        .order_by(WinProbSnapshot.captured_at)
    ).scalars().all()
    return row, espn_rows, wp_rows, stats


def _served_espn_history(espn_rows):
    """`/history`'s `espn_history`, projected as the route projects it.

    The route builds this list inline from the same ORM rows; the column → key
    map it uses is pinned by `test_the_route_serves_the_snapshot_columns_verbatim`
    below, so this cannot drift from what a client is served.
    """
    return [
        {
            "timestamp": snap.captured_at.isoformat(),
            "home_probability": (
                float(snap.home_win_probability)
                if snap.home_win_probability is not None else None
            ),
            "away_probability": (
                float(snap.away_win_probability)
                if snap.away_win_probability is not None else None
            ),
            "home_score": snap.home_score,
            "away_score": snap.away_score,
            "game_clock": snap.game_clock,
            "period": snap.period,
        }
        for snap in espn_rows
    ]


def _game_state(wp_rows, source):
    from app.routes.events import _project_served_game_state

    served = {
        source: [
            {"game_state": dict(r.game_state) if r.game_state else None}
            for r in wp_rows if r.source == source
        ]
    }
    _project_served_game_state(served)
    assert served[source], f"no {source} win_prob_snapshots were written"
    return served[source][-1]["game_state"]


class TestTheRolloverStaysOffTheChart:
    @pytest.mark.asyncio
    async def test_the_smu_rollover_reaches_neither_the_row_nor_the_history(self):
        row, espn_rows, wp_rows, stats = await _one_live_pass(_board_reading(*ROLLOVER))

        assert stats["live_clock_outran_wall_refused"] == 1, stats
        assert (row.period, row.game_clock) == END_Q3

        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["period"], newest["game_clock"]) == (None, None), (
            "the refused rollover became the chart's newest ESPN position: "
            f"{newest['period']!r} {newest['game_clock']!r}"
        )
        espn_state = _game_state(wp_rows, "espn")
        assert espn_state.get("period") is None and espn_state.get("clock") is None, (
            espn_state
        )

    @pytest.mark.asyncio
    async def test_the_refused_readings_probability_and_score_still_land(self):
        """Only the position is withheld. A touchdown on the same board is a
        touchdown, and ESPN's probability is still ESPN's probability."""
        row, espn_rows, wp_rows, stats = await _one_live_pass(
            _board_reading(*ROLLOVER, away_score=17, prob=0.61)
        )
        assert stats["live_clock_outran_wall_refused"] == 1, stats
        assert (row.home_score, row.away_score) == (21, 17)
        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["home_score"], newest["away_score"]) == (21, 17)
        assert newest["home_probability"] == pytest.approx(0.61)
        espn_wp = [r for r in wp_rows if r.source == "espn"][-1]
        assert float(espn_wp.home_win_probability) == pytest.approx(0.61)
        assert _game_state(wp_rows, "espn")["away_score"] == 17

    @pytest.mark.asyncio
    async def test_the_stat_model_is_priced_at_the_position_the_row_admitted(self):
        row, _espn_rows, wp_rows, stats = await _one_live_pass(_board_reading(*ROLLOVER))
        assert stats.get("stat_model_computed") == 1, stats
        state = _game_state(wp_rows, "stat_model")
        assert (state["period"], state["clock"]) == END_Q3 == (row.period, row.game_clock)


class TestTwinsThatLand:
    @pytest.mark.asyncio
    async def test_the_real_fourth_quarter_reading_lands_everywhere(self):
        row, espn_rows, wp_rows, stats = await _one_live_pass(_board_reading(*REAL_Q4))
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats
        assert (row.period, row.game_clock) == REAL_Q4
        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["period"], newest["game_clock"]) == REAL_Q4
        espn_state = _game_state(wp_rows, "espn")
        assert (espn_state["period"], espn_state["clock"]) == REAL_Q4
        stat_state = _game_state(wp_rows, "stat_model")
        assert (stat_state["period"], stat_state["clock"]) == REAL_Q4

    @pytest.mark.asyncio
    async def test_after_a_refusal_the_next_real_reading_lands(self):
        """The withheld snapshot must not break the row's first-seen run: the
        anchor read skips it, and the real reading one pass later is judged
        against `End of 3rd Quarter`'s first sighting and admitted."""
        row, espn_rows, wp_rows, stats = await _one_live_pass(
            _board_reading(*REAL_Q4),
            board=[
                (_ago(240), *END_Q3),
                (_ago(180), *END_Q3),
                (_ago(120), None, None),  # the rollover, withheld last pass
                (_ago(60), None, None),
            ],
        )
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats
        assert (row.period, row.game_clock) == REAL_Q4
        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["period"], newest["game_clock"]) == REAL_Q4

    @pytest.mark.asyncio
    async def test_a_board_that_sat_still_catches_up_on_the_chart_too(self):
        """Legitimate slow-pass catch-up: ten minutes on `End of 3rd Quarter`
        covers the rollover's ten minutes of game clock, so it is admitted —
        to the row AND to the history."""
        row, espn_rows, _wp_rows, stats = await _one_live_pass(
            _board_reading(*ROLLOVER),
            board=[(_ago(s), *END_Q3) for s in (660, 600, 540, 480, 420, 360, 300, 240, 180, 120, 60)],
        )
        assert stats.get("live_clock_outran_wall_refused", 0) == 0, stats
        assert (row.period, row.game_clock) == ROLLOVER
        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["period"], newest["game_clock"]) == ROLLOVER


class TestTheServedChain:
    @pytest.mark.asyncio
    async def test_the_served_tail_is_the_one_the_readout_test_renders(self):
        """The frontend readout test renders this fixture through the real
        `computeLastChartPoint` and `GamePlayCard`. Its `after` tail must be what
        this pass actually serves — position and score, row for row — so the
        readout assertion is about the real writer's output, not a hand-made one."""
        row, espn_rows, _wp_rows, _stats = await _one_live_pass(_board_reading(*ROLLOVER))
        fixture = json.loads(FIXTURE.read_text())

        def _shape(points):
            return [
                (p["period"], p["game_clock"], p["home_score"], p["away_score"])
                for p in points
            ]

        assert _shape(_served_espn_history(espn_rows)) == _shape(fixture["after"]["espn_history"])
        assert (row.period, row.game_clock) == (
            fixture["row"]["period"], fixture["row"]["game_clock"],
        )
        # The `before` arm is the first cut's output (CERT-3657's reproduction):
        # identical but for the rollover's position on the newest row.
        before, after = fixture["before"]["espn_history"], fixture["after"]["espn_history"]
        assert _shape(before)[:-1] == _shape(after)[:-1]
        assert (before[-1]["period"], before[-1]["game_clock"]) == ROLLOVER

    def test_the_route_serves_the_snapshot_columns_verbatim(self):
        """`_served_espn_history` above mirrors the route; this pins the map."""
        import inspect

        from app.routes import events

        src = inspect.getsource(events)
        assert '"game_clock": snap.game_clock,' in src
        assert '"period": snap.period,' in src
        assert '"game_state": snap.game_state,' in src
