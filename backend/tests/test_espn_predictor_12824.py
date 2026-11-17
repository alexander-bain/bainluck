"""#12824 — ESPN's predictor as the chance for scheduled games nobody prices yet.

Bills at Patriots three weeks out showed "No win probability readings for this
game yet" (TestFlight 5757). These pin Fable's (b): the reading (ties excluded,
both ESPN payload shapes), the 7-day age rule, which games want a reading, the
board-day arithmetic, the home = home match, and the run's write / withdraw /
keep decisions. Clocks are a fixed anchor far from today (wall-clock guard).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.tasks import espn_predictor as ep

NOW = datetime(2031, 3, 4, 12, 0, tzinfo=timezone.utc)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _nfl_payload(modified: datetime) -> dict:
    # Bills at Patriots as ESPN served it: home Patriots, away Bills, tie 0.113.
    return {
        "name": "Buffalo Bills at New England Patriots",
        "lastModified": _stamp(modified),
        "homeTeam": {"statistics": [
            {"name": "gameProjection", "value": 14.135},
            {"name": "teamChanceLoss", "value": 85.752},
            {"name": "teamChanceTie", "value": 0.113},
        ]},
        "awayTeam": {"statistics": [
            {"name": "gameProjection", "value": 85.752},
            {"name": "teamChanceLoss", "value": 14.135},
        ]},
    }


def _nba_payload(modified: datetime) -> dict:
    # NBA's shape: statistics on the AWAY side only (Pistons at Hawks).
    return {
        "lastModified": _stamp(modified),
        "homeTeam": {"statistics": []},
        "awayTeam": {"statistics": [
            {"name": "gameProjection", "value": 49.556},
            {"name": "teamChanceLoss", "value": 50.444},
        ]},
    }


class TestReading:
    def test_nfl_ties_excluded_reads_bills_86_patriots_14(self):
        value, why = ep.predictor_home_probability(_nfl_payload(NOW - timedelta(hours=3)), NOW)
        assert why == "ok"
        assert value == pytest.approx(14.135 / (14.135 + 85.752), abs=1e-6)
        assert round(value * 100) == 14 and round((1 - value) * 100) == 86

    def test_nba_away_only_shape_reads_home_from_teamchanceloss(self):
        value, why = ep.predictor_home_probability(_nba_payload(NOW - timedelta(hours=1)), NOW)
        assert why == "ok"
        assert value == pytest.approx(0.50444, abs=1e-6)

    def test_older_than_seven_days_is_absent(self):
        value, why = ep.predictor_home_probability(
            _nfl_payload(NOW - ep.MAX_PREDICTOR_AGE - timedelta(minutes=1)), NOW
        )
        assert (value, why) == (None, "predictor-stale")

    def test_six_days_old_is_shown(self):
        value, why = ep.predictor_home_probability(_nfl_payload(NOW - timedelta(days=6)), NOW)
        assert why == "ok" and value is not None

    def test_no_last_modified_is_absent(self):
        payload = _nfl_payload(NOW)
        payload.pop("lastModified")
        assert ep.predictor_home_probability(payload, NOW) == (None, "no-last-modified")

    def test_missing_projection_is_absent(self):
        payload = {"lastModified": _stamp(NOW), "homeTeam": {}, "awayTeam": {}}
        assert ep.predictor_home_probability(payload, NOW) == (None, "no-projection")

    def test_rail_is_absent(self):
        payload = _nfl_payload(NOW)
        payload["homeTeam"]["statistics"][0]["value"] = 0.0
        assert ep.predictor_home_probability(payload, NOW) == (None, "projection-at-rail")

    def test_no_body_is_absent(self):
        assert ep.predictor_home_probability(None, NOW) == (None, "no-predictor")


def _row(sources=None, **kw) -> ep.PredictorRow:
    base = dict(
        event_id=1, sport_key="americanfootball_nfl", espn_id=None,
        commence_time=NOW + timedelta(days=20), home_team_name="New England Patriots",
        away_team_name="Buffalo Bills", sources=sources or {},
    )
    base.update(kw)
    return ep.PredictorRow(**base)


def _entry(value, at: datetime) -> dict:
    return {"value": value, "updated_at": at.isoformat()}


class TestWhichGames:
    def test_two_books_under_the_051_floor_are_not_a_price(self):
        # The specimen: `betting_book_count: 2` and no `betting` value.
        assert not ep.is_priced({"betting_book_count": 2})
        assert ep.wants_reading(_row({"betting_book_count": 2}))

    def test_a_book_or_venue_value_is_a_price(self):
        for key in ("betting", "kalshi", "polymarket"):
            assert ep.is_priced({key: _entry(0.4, NOW)}), key

    def test_a_model_is_not_a_price(self):
        assert not ep.is_priced({"stat_model": _entry(0.4, NOW)})

    def test_priced_game_without_espn_is_left_alone(self):
        assert not ep.wants_reading(_row({"betting": _entry(0.4, NOW)}))

    def test_priced_game_holding_espn_keeps_being_read_so_it_never_freezes(self):
        assert ep.wants_reading(_row({"betting": _entry(0.4, NOW), "espn": _entry(0.2, NOW)}))

    def test_stored_age(self):
        assert ep.stored_reading_age(_row({}), NOW) is None
        row = _row({"espn": _entry(0.2, NOW - timedelta(minutes=40))})
        assert ep.stored_reading_age(row, NOW) == timedelta(minutes=40)
        bare = _row({"espn": 0.2})  # legacy bare float: nothing says it is recent
        assert ep.stored_reading_age(bare, NOW) > ep.UNREFRESHED_READING_LIMIT


class TestBoards:
    def test_late_eastern_start_reads_the_previous_eastern_day_first(self):
        # 00:15Z on the 7th is 7:15 PM Eastern on the 6th.
        assert ep.board_days(datetime(2031, 3, 7, 0, 15, tzinfo=timezone.utc)) == ["20310306"]

    def test_both_offsets_when_they_straddle_midnight(self):
        assert ep.board_days(datetime(2031, 3, 7, 4, 30, tzinfo=timezone.utc)) == [
            "20310306", "20310307",
        ]

    def test_college_boards_ask_for_the_full_slate(self):
        assert ep.BOARD_GROUPS == {
            "americanfootball_ncaaf": "80",
            "basketball_ncaab": "50",
            "basketball_wncaab": "50",
        }

    def test_every_league_is_one_the_blend_takes_espn_for(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES

        assert set(ep.PREDICTOR_LEAGUES) <= set(WIN_PROB_SOURCES["espn"]["sports"])


def _team(name: str, abbr: str, location: str, nickname: str) -> ESPNTeam:
    return ESPNTeam(
        espn_id=abbr, name=nickname, abbreviation=abbr, display_name=name,
        short_name=nickname, nickname=nickname, primary_color=None,
        secondary_color=None, logo_url=None, logo_url_dark=None, record=None,
        location=location,
    )


PATS = _team("New England Patriots", "NE", "New England", "Patriots")
BILLS = _team("Buffalo Bills", "BUF", "Buffalo", "Bills")


def _game(home, away, when, espn_id="401873105") -> ESPNEvent:
    return ESPNEvent(
        espn_id=espn_id, name=f"{away.display_name} at {home.display_name}",
        short_name=None, date=when, status="scheduled", status_detail=None,
        period=None, clock=None, home_team=home, away_team=away, home_score=None,
        away_score=None, venue=None, broadcasts=[], home_win_probability=None,
    )


class TestMatch:
    def test_same_teams_same_sides_same_kickoff_matches(self):
        when = NOW + timedelta(days=20)
        game, why = ep.match_on_board(_row(commence_time=when), [_game(PATS, BILLS, when)])
        assert why == "ok" and game.espn_id == "401873105"

    def test_sides_reversed_is_never_written(self):
        # ESPN's home is our away: its predictor "home" is the other team.
        when = NOW + timedelta(days=20)
        game, why = ep.match_on_board(_row(commence_time=when), [_game(BILLS, PATS, when)])
        assert game is None

    def test_a_different_day_does_not_match(self):
        when = NOW + timedelta(days=20)
        game, _ = ep.match_on_board(
            _row(commence_time=when), [_game(PATS, BILLS, when + timedelta(days=7))]
        )
        assert game is None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _stmt):
        return SimpleNamespace(all=lambda: self._rows)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _db_row(event_id, sources, commence=None):
    return (event_id, "americanfootball_nfl", None, commence or NOW + timedelta(days=20),
            "New England Patriots", "Buffalo Bills", sources, None, None, None, None)


@pytest.mark.asyncio
async def test_run_writes_withdraws_and_keeps(monkeypatch):
    from contextlib import asynccontextmanager

    rows = [
        _db_row(1, {"betting_book_count": 2}),                                   # unpriced -> write
        _db_row(2, {"espn": _entry(0.5, NOW - timedelta(minutes=10))}),          # stale predictor -> withdraw
        _db_row(3, {"espn": _entry(0.5, NOW - timedelta(minutes=20))}),          # ESPN dark, fresh -> keep
        _db_row(4, {"espn": _entry(0.5, NOW - timedelta(hours=3))}),             # ESPN dark, 3 h -> withdraw
        _db_row(5, {"betting": _entry(0.6, NOW)}),                               # priced, no espn -> untouched
        _db_row(6, {}),                                                          # unpriced, dark, nothing stored -> nothing
    ]
    session = _FakeSession(rows)

    @asynccontextmanager
    async def fake_session(**_kw):
        yield session

    plans = {
        1: ("write", 0.1415, {"basis": "espn_predictor"}),
        2: ("remove", "predictor-stale"),
        3: ("keep", "board-dark"),
        4: ("keep", "predictor-dark"),
        6: ("keep", "board-dark"),
    }

    async def fake_read(read_rows, now, stats):
        assert [r.event_id for r in read_rows] == [1, 2, 3, 4, 6]
        return plans

    writes = []

    async def fake_write(session_, target, source, value, **kw):
        writes.append((target.id, source, value))

    async def fake_publish(_session):
        return None

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    monkeypatch.setattr(ep, "_read_espn", fake_read)
    monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
    monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(ep, "datetime", _Clock)

    stats = await ep._run_refresh_espn_predictor()

    assert writes == [(1, "espn", 0.1415), (2, "espn", None), (4, "espn", None)]
    assert stats["written"] == 1 and stats["removed"] == 2 and stats["kept"] == 2
    assert stats["candidates"] == 6 and stats["wanted"] == 5
    assert session.commits == 3


@pytest.mark.asyncio
async def test_one_failed_write_does_not_cost_the_rest(monkeypatch):
    from contextlib import asynccontextmanager

    rows = [_db_row(1, {}), _db_row(2, {})]
    session = _FakeSession(rows)

    @asynccontextmanager
    async def fake_session(**_kw):
        yield session

    async def fake_read(read_rows, now, stats):
        return {1: ("write", 0.3, {}), 2: ("write", 0.4, {})}

    writes = []

    async def fake_write(session_, target, source, value, **kw):
        if target.id == 1:
            raise RuntimeError("boom")
        writes.append(target.id)

    async def fake_publish(_session):
        return None

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    monkeypatch.setattr(ep, "_read_espn", fake_read)
    monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
    monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)

    stats = await ep._run_refresh_espn_predictor()
    assert writes == [2]
    assert stats["write_errors"] == 1 and session.rollbacks == 1
