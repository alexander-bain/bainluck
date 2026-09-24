"""#8278 — the hourly StatPal pass stops writing game 2's live score onto game 1.

`_sync_statpal_schedules` finds a schedule fixture's live row by team pair, then
checks `pair_verdict` (the shared 12h constant). A doubleheader's games are ~6h
apart, so game 2's live row passed as game 1's and its score landed on game 1's
already-final row, with no score snapshot. Two production specimens:

* Yankees–Rays 2026-09-22 game 1 (14788069, StatPal 354165) stored 1–6, game
  2's final; MLB 823543 says Yankees 2–0.
* Blue Jays–Orioles 2026-09-23 game 1 (15316846, StatPal 366696) stored 4–0,
  game 2's score from 23:30Z to 00:56Z; MLB 824785 final 4–2.

The helper tests pin the decision; the task tests drive the real hourly pass
and read the row back, so a correct helper that is never called still fails.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks.statpal_sync import (
    LIVE_REFUSED_ANCHOR,
    LIVE_REFUSED_NEARER_SIBLING,
    LIVE_REFUSED_PAIR,
    _live_row_for_schedule_fixture,
    _schedule_starts_by_teams,
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


G1_START = datetime(2026, 9, 22, 17, 5, tzinfo=timezone.utc)
G2_START = datetime(2026, 9, 22, 23, 5, tzinfo=timezone.utc)
HOME, AWAY = "New York Yankees", "Tampa Bay Rays"


class _Row:
    """A StatPal fixture as both boards hand it over (duck-typed, as in prod)."""

    def __init__(
        self,
        start,
        *,
        fixture_id,
        odds_id=None,
        home=HOME,
        away=AWAY,
        status="scheduled",
        scores=(None, None),
        raw_status=None,
    ):
        self.fixture_id = fixture_id
        self.odds_id = odds_id
        self.home_team = home
        self.away_team = away
        self.start_time = start
        self.end_time = None
        self.status = status
        self.raw_status = raw_status
        self.game_clock = None
        self.clock_field_served = False
        self.home_score, self.away_score = scores


def _decide(fixture, live_rows, schedule, sport="mlb"):
    key_starts = _schedule_starts_by_teams(schedule)
    from app.tasks.statpal_sync import _fixture_match_key

    key = _fixture_match_key(fixture.home_team, fixture.away_team)
    return _live_row_for_schedule_fixture(
        fixture, live_rows, sport, key_starts.get(key, ())
    )


# MLB's live board: `id` is its own space; `odds_id` is the schedule id.
G1 = _Row(G1_START, fixture_id="354165")
G2 = _Row(G2_START, fixture_id="366701")
LIVE_G2_ANCHORED = _Row(
    G2_START, fixture_id="1329201999", odds_id="366701", status="live", scores=(1, 6)
)
LIVE_G2_IDLESS = _Row(
    G2_START, fixture_id="1329201999", odds_id=None, status="live", scores=(1, 6)
)


class TestTheSpecimenIsRefused:
    def test_game1_refuses_game2s_anchored_live_row(self):
        row, reason = _decide(G1, [LIVE_G2_ANCHORED], [G1, G2])
        assert row is None
        assert reason == LIVE_REFUSED_ANCHOR

    def test_game1_refuses_game2s_idless_live_row_because_game2_is_nearer(self):
        row, reason = _decide(G1, [LIVE_G2_IDLESS], [G1, G2])
        assert row is None
        assert reason == LIVE_REFUSED_NEARER_SIBLING

    def test_the_six_hour_gap_really_is_inside_the_shared_constant(self):
        # Why the old gate let it through: without a sibling, 6h reads SAME.
        from app.utils.game_pairing import Pairing, pair_verdict

        assert pair_verdict(G1_START, G2_START) is Pairing.SAME

    def test_blue_jays_orioles_makeup_day(self):
        # 9/22 22:35 postponed original, 9/23 17:35 makeup (game 1), 9/23 22:35 game 2.
        orig = _Row(datetime(2026, 9, 22, 22, 35, tzinfo=timezone.utc),
                    fixture_id="366690", home="Baltimore Orioles", away="Toronto Blue Jays")
        g1 = _Row(datetime(2026, 9, 23, 17, 35, tzinfo=timezone.utc),
                  fixture_id="366696", home="Baltimore Orioles", away="Toronto Blue Jays")
        g2 = _Row(datetime(2026, 9, 23, 22, 35, tzinfo=timezone.utc),
                  fixture_id="366714", home="Baltimore Orioles", away="Toronto Blue Jays")
        live = _Row(g2.start_time, fixture_id="1329202001", status="live", scores=(4, 0),
                    home="Baltimore Orioles", away="Toronto Blue Jays")
        schedule = [orig, g1, g2]
        assert _decide(g1, [live], schedule) == (None, LIVE_REFUSED_NEARER_SIBLING)
        assert _decide(g2, [live], schedule) == (live, None)


class TestTheRightGameStillGetsItsScore:
    def test_game2_takes_its_anchored_row(self):
        assert _decide(G2, [LIVE_G2_ANCHORED], [G1, G2]) == (LIVE_G2_ANCHORED, None)

    def test_game2_takes_its_idless_row(self):
        assert _decide(G2, [LIVE_G2_IDLESS], [G1, G2]) == (LIVE_G2_IDLESS, None)

    def test_the_anchor_wins_even_when_the_clock_disagrees(self):
        # The id is identity; a drifted start on the live row does not unseat it.
        drifted = _Row(G2_START + timedelta(hours=20), fixture_id="x",
                       odds_id="366701", status="live")
        assert _decide(G2, [drifted], [G1, G2]) == (drifted, None)

    def test_both_live_rows_listed_each_fixture_gets_its_own(self):
        # A plain dict kept whichever came last; the list keeps both.
        live_g1 = _Row(G1_START, fixture_id="1329201998", odds_id="354165", status="live")
        rows = [live_g1, LIVE_G2_ANCHORED]
        assert _decide(G1, rows, [G1, G2]) == (live_g1, None)
        assert _decide(G2, rows, [G1, G2]) == (LIVE_G2_ANCHORED, None)

    def test_a_single_game_series_day_is_unchanged(self):
        # No sibling: the pre-#8278 rule is the whole rule.
        live = _Row(G1_START + timedelta(minutes=4), fixture_id="1", status="live")
        assert _decide(G1, [live], [G1]) == (live, None)

    def test_the_series_case_1945_still_refuses_on_the_clock(self):
        tomorrow = _Row(G1_START + timedelta(days=2), fixture_id="354200")
        live = _Row(G1_START, fixture_id="1", status="live")
        assert _decide(tomorrow, [live], [G1, tomorrow]) == (None, LIVE_REFUSED_PAIR)

    def test_a_fixture_listed_twice_is_not_its_own_sibling(self):
        live = _Row(G1_START, fixture_id="1", status="live")
        assert _decide(G1, [live], [G1, G1]) == (live, None)


class TestUndeclaredSportsSkipTheAnchorTest:
    def test_nhl_uses_the_nearest_rule_only(self):
        # NHL is not in STATPAL_LIVE_ANCHOR_FIELD, so an `odds_id` there is not
        # read as a schedule id. The nearest rule still applies.
        live = _Row(G2_START, fixture_id="777", odds_id="354165", status="live")
        assert _decide(G2, [live], [G1, G2], sport="nhl") == (live, None)
        assert _decide(G1, [live], [G1, G2], sport="nhl") == (
            None, LIVE_REFUSED_NEARER_SIBLING,
        )


class TestCouldNotCheckIsNotTheGame:
    def test_a_live_row_with_no_start_is_refused(self):
        live = _Row(None, fixture_id="1", status="live")
        assert _decide(G1, [live], [G1]) == (None, LIVE_REFUSED_PAIR)

    def test_an_equidistant_tie_is_refused(self):
        a = _Row(G1_START, fixture_id="a")
        b = _Row(G1_START + timedelta(hours=6), fixture_id="b")
        live = _Row(G1_START + timedelta(hours=3), fixture_id="1", status="live")
        assert _decide(a, [live], [a, b]) == (None, LIVE_REFUSED_NEARER_SIBLING)
        assert _decide(b, [live], [a, b]) == (None, LIVE_REFUSED_NEARER_SIBLING)

    def test_an_anchored_live_row_cannot_be_confirmed_for_an_idless_fixture(self):
        idless = _Row(G2_START, fixture_id="")
        assert _decide(idless, [LIVE_G2_ANCHORED], [G1, idless]) == (
            None, LIVE_REFUSED_ANCHOR,
        )

    def test_no_live_row_for_the_pair_is_no_refusal(self):
        assert _decide(G1, [], [G1, G2]) == (None, None)


# ---------------------------------------------------------------------------
# The real hourly task, on a two-row doubleheader
# ---------------------------------------------------------------------------


class _FixtureFetch:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.reason = "ok"
        self.sport = "mlb"
        self.endpoint = "/v1/mlb/season-schedule"
        self.asked = True
        self.is_alarm = False


async def _run_mlb_schedules(monkeypatch, *, live):
    """Drive the real `_sync_statpal_schedules("baseball_mlb")`; return (g1, g2, result).

    Game 1 is final at 2–0 (its own score), game 2 is live. Both schedule
    fixtures sit in the pass's -1d window. Same sqlite rail as the #6056 file.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    import app.tasks.statpal_sync as statpal_sync
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_schedules

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    s = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(s, "loaded_as_persistent")
    def _utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    g1_start, g2_start = now - timedelta(hours=8), now - timedelta(hours=2)
    sport = Sport(key="baseball_mlb", name="baseball_mlb")
    s.add(sport)
    s.flush()
    g1 = Event(
        sport_id=sport.id, home_team_name=HOME, away_team_name=AWAY,
        commence_time=g1_start, status="completed", completed_at=g1_start + timedelta(hours=2),
        period="Final", game_clock="0:00", home_score=2, away_score=0,
        statpal_fixture_id="354165", home_team_id=1, away_team_id=2,
    )
    g2 = Event(
        sport_id=sport.id, home_team_name=HOME, away_team_name=AWAY,
        commence_time=g2_start, status="live", home_score=1, away_score=4,
        statpal_fixture_id="366701", home_team_id=1, away_team_id=2,
    )
    s.add_all([g1, g2])
    s.commit()
    ids = (g1.id, g2.id)

    class _Shim:
        async def execute(self, stmt):
            return s.execute(stmt)

        def add(self, obj):
            s.add(obj)

        async def commit(self):
            s.commit()

        async def flush(self):
            s.flush()

    class _Ctx:
        async def __aenter__(self):
            return _Shim()

        async def __aexit__(self, *exc):
            s.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    schedule = [
        _Row(g1_start, fixture_id="354165", status="finished"),
        _Row(g2_start, fixture_id="366701", status="live"),
    ]
    for row in live:
        row.start_time = g2_start

    class _Service:
        async def get_fixtures_result(self, sport):
            return _FixtureFetch(list(schedule))

        async def get_live_scores(self, sport):
            return list(live)

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    class _Team:
        id = 1

    async def _resolve_team(session, source, sport_key, source_name=None):
        return _Team()

    from app.services import team_identity

    monkeypatch.setattr(team_identity.team_identity_service, "resolve_team", _resolve_team)
    monkeypatch.setattr(statpal_sync, "accept_team_binding", lambda **kw: False, raising=False)

    result = await _sync_statpal_schedules("baseball_mlb")
    s.expire_all()
    rows = [s.execute(select(Event).where(Event.id == i)).scalar_one() for i in ids]
    return rows[0], rows[1], result


def _live_g2(odds_id):
    # A bare "live" status is unplaceable, so the #6056 reversion guard stands
    # aside, exactly as it did for MLB's live board on the production rows.
    return _Row(None, fixture_id="1329201999", odds_id=odds_id, status="live",
                scores=(1, 6), raw_status="live")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "odds_id, counter",
    [("366701", "live_anchor_refused"), (None, "live_nearer_sibling_refused")],
    ids=["anchored-live-row", "idless-live-row"],
)
async def test_game1_keeps_its_own_final_8278(monkeypatch, odds_id, counter):
    g1, g2, result = await _run_mlb_schedules(monkeypatch, live=[_live_g2(odds_id)])
    assert (g1.home_score, g1.away_score) == (2, 0), "game 2's score reached game 1"
    assert result[counter] == 1
    # Positive control: the same pass still writes game 2's own live score.
    assert (g2.home_score, g2.away_score) == (1, 6)
