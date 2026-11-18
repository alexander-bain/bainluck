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
_REAL_TWIN_PRICE_VIEWS = ep.twin_price_views


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

    def test_226a_a_priced_game_is_never_read_and_its_espn_reading_must_leave(self):
        row = _row({"betting": _entry(0.4, NOW), "espn": _entry(0.2, NOW)})
        assert not ep.wants_reading(row)
        assert ep.must_leave(row)
        assert not ep.must_leave(_row({"espn": _entry(0.2, NOW)}))  # unpriced: stays

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


def _db_row(event_id, sources, commence=None, tags=None):
    return (event_id, "americanfootball_nfl", None, commence or NOW + timedelta(days=20),
            "New England Patriots", "Buffalo Bills", sources, None, None, None, None, tags)


@pytest.fixture(autouse=True)
def _no_duplicate_rows(monkeypatch):
    """The run tests' fake session answers every statement with the candidates,
    so the duplicate fold is pinned to "no duplicates" unless a test says otherwise."""
    async def none(_session, _rows):
        return {}

    monkeypatch.setattr(ep, "twin_price_views", none)


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


@pytest.mark.asyncio
async def test_withdraw_mode_removes_every_reading_and_reads_nothing(monkeypatch):
    """The rollback: a revert alone would leave pregame readings frozen."""
    from contextlib import asynccontextmanager

    rows = [
        _db_row(1, {"espn": _entry(0.2, NOW)}),
        _db_row(2, {"betting": _entry(0.6, NOW), "espn": _entry(0.3, NOW)}),
        _db_row(3, {}),
        _db_row(4, {"betting": _entry(0.6, NOW)}),
    ]
    session = _FakeSession(rows)

    @asynccontextmanager
    async def fake_session(**_kw):
        yield session

    async def must_not_read(*_a, **_k):
        raise AssertionError("withdraw mode must not read ESPN")

    writes = []

    async def fake_write(session_, target, source, value, **kw):
        writes.append((target.id, source, value))

    async def fake_publish(_session):
        return None

    monkeypatch.setenv("ESPN_PREDICTOR_MODE", "withdraw")
    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    monkeypatch.setattr(ep, "_read_espn", must_not_read)
    monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
    monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)

    stats = await ep._run_refresh_espn_predictor()
    assert writes == [(1, "espn", None), (2, "espn", None)]
    assert stats["mode"] == "withdraw" and stats["removed"] == 2


def test_mode_defaults_on_and_only_withdraw_switches_it(monkeypatch):
    monkeypatch.delenv("ESPN_PREDICTOR_MODE", raising=False)
    assert ep.predictor_mode() == "on"
    monkeypatch.setenv("ESPN_PREDICTOR_MODE", "nonsense")
    assert ep.predictor_mode() == "on"
    monkeypatch.setenv("ESPN_PREDICTOR_MODE", " Withdraw ")
    assert ep.predictor_mode() == "withdraw"


class TestNeverStepBack:
    """Fable 10:04 PM: a read never moves us backwards (Aug 31 vs Nov 16 copies)."""

    def _held(self, modified: datetime, at: datetime = NOW) -> ep.PredictorRow:
        return _row({"espn": {"value": 0.1415, "updated_at": at.isoformat(),
                              "predictor_last_modified": _stamp(modified)}})

    def test_fresh_reading_then_an_older_copy_is_not_a_refresh(self):
        row = self._held(NOW - timedelta(hours=10))
        assert ep.older_copy(row, _nfl_payload(NOW - timedelta(days=77)))

    def test_same_or_newer_copy_is_a_refresh(self):
        row = self._held(NOW - timedelta(hours=10))
        assert not ep.older_copy(row, _nfl_payload(NOW - timedelta(hours=10)))
        assert not ep.older_copy(row, _nfl_payload(NOW - timedelta(hours=1)))

    def test_undated_or_missing_copy_is_not_a_refresh_when_we_hold_a_dated_reading(self):
        row = self._held(NOW - timedelta(hours=10))
        undated = _nfl_payload(NOW)
        undated.pop("lastModified")
        assert ep.older_copy(row, undated)
        assert ep.older_copy(row, None)

    def test_nothing_held_means_nothing_to_step_back_from(self):
        assert not ep.older_copy(_row({}), _nfl_payload(NOW - timedelta(days=77)))

    @pytest.mark.asyncio
    async def test_old_copy_writes_and_withdraws_nothing_then_two_hours_retires_it(self, monkeypatch):
        """The specimen: an 86% from a Nov-16 copy, then ESPN's edge serves Aug 31."""
        from contextlib import asynccontextmanager

        from app.services import espn_api

        when = NOW + timedelta(days=20)
        fresh = _db_row(1, {"espn": {"value": 0.1415, "updated_at": (NOW - timedelta(minutes=15)).isoformat(),
                                     "predictor_last_modified": _stamp(NOW - timedelta(hours=10))}}, when)
        unconfirmed = _db_row(2, {"espn": {"value": 0.1415, "updated_at": (NOW - timedelta(hours=3)).isoformat(),
                                           "predictor_last_modified": _stamp(NOW - timedelta(hours=10))}}, when)
        session = _FakeSession([fresh, unconfirmed])

        @asynccontextmanager
        async def fake_session(**_kw):
            yield session

        class _FakeESPN:
            def __init__(self, *a, **k):
                pass

            async def get_scoreboard(self, *a, **k):
                return [_game(PATS, BILLS, when)]

            async def get_predictor(self, *a, **k):
                return _nfl_payload(NOW - timedelta(days=77))  # the stale edge copy

            async def close(self):
                pass

        writes = []

        async def fake_write(session_, target, source, value, **kw):
            writes.append((target.id, value))

        async def fake_publish(_session):
            return None

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW

        monkeypatch.delenv("ESPN_PREDICTOR_MODE", raising=False)
        monkeypatch.setattr(espn_api, "ESPNAPIService", _FakeESPN)
        monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
        monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
        monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)
        monkeypatch.setattr(ep, "datetime", _Clock)

        stats = await ep._run_refresh_espn_predictor()

        # Row 1: refreshed 15 min ago, older copy -> no write, no withdraw.
        # Row 2: nobody has confirmed it for 3 h -> the 2-hour rule withdraws it.
        assert writes == [(2, None)]
        assert stats["older_copy"] == 2 and stats["kept"] == 1 and stats["removed"] == 1


def test_a_write_carries_espns_last_modified_inside_the_entry(monkeypatch):
    """So the next run can tell an older copy from a refresh."""
    import asyncio
    from contextlib import asynccontextmanager

    session = _FakeSession([_db_row(1, {})])

    @asynccontextmanager
    async def fake_session(**_kw):
        yield session

    async def fake_read(rows, now, stats):
        return {1: ("write", 0.1415, {"basis": "espn_predictor", "espn_id": "401873105",
                                      "last_modified": "2031-03-04T02:00Z"})}

    seen = {}

    async def fake_write(session_, target, source, value, **kw):
        seen.update(kw)

    async def fake_publish(_session):
        return None

    monkeypatch.delenv("ESPN_PREDICTOR_MODE", raising=False)
    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
    monkeypatch.setattr(ep, "_read_espn", fake_read)
    monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
    monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)
    asyncio.run(ep._run_refresh_espn_predictor())
    assert seen["entry_extra"] == {"predictor_last_modified": "2031-03-04T02:00Z"}


def test_the_writer_refuses_an_unlisted_entry_key():
    import asyncio

    from app.utils import nonvenue_live_push as nlp

    assert nlp.ENTRY_EXTRA_KEYS == frozenset({"predictor_last_modified"})
    with pytest.raises(ValueError):
        asyncio.run(nlp.write_nonvenue_probability(
            None, SimpleNamespace(id=1), "espn", 0.4, entry_extra={"value": 0.9},
        ))


class TestRuling226A:
    """Alex 226: A — ESPN fills in only while nothing else prices the game."""

    async def _run(self, monkeypatch, sources: dict):
        """One run over one game; the fake writer applies its write to the bag."""
        from contextlib import asynccontextmanager

        bag = {k: (dict(v) if isinstance(v, dict) else v) for k, v in sources.items()}
        session = _FakeSession([_db_row(1, bag)])
        read_rows = []

        @asynccontextmanager
        async def fake_session(**_kw):
            yield session

        async def fake_read(rows, now, stats):
            read_rows.extend(r.event_id for r in rows)
            return {r.event_id: ("write", 0.1415, {"basis": "espn_predictor",
                                                   "last_modified": _stamp(NOW)}) for r in rows}

        async def fake_write(session_, target, source, value, **kw):
            if value is None:
                bag.pop(source, None)
            else:
                bag[source] = {"value": value, "updated_at": NOW.isoformat()}

        async def fake_publish(_session):
            return None

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW

        monkeypatch.delenv("ESPN_PREDICTOR_MODE", raising=False)
        monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
        monkeypatch.setattr(ep, "_read_espn", fake_read)
        monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
        monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)
        monkeypatch.setattr(ep, "datetime", _Clock)
        stats = await ep._run_refresh_espn_predictor()
        return bag, read_rows, stats

    @staticmethod
    def _served(bag: dict):
        from app.utils.aggregation import compute_aggregate_probability

        shim = SimpleNamespace(win_probability_sources=bag, espn_win_prob_home=None,
                               opening_home_probability=None, status="scheduled")
        return compute_aggregate_probability(shim, "scheduled")

    @pytest.mark.asyncio
    async def test_a_venue_arrives_and_the_next_run_removes_espn(self, monkeypatch):
        venue = {"kalshi": _entry(0.31, NOW)}
        bag, read_rows, stats = await self._run(
            monkeypatch, {**venue, "espn": _entry(0.1415, NOW - timedelta(minutes=10))},
        )
        assert "espn" not in bag and read_rows == [] and stats["removed"] == 1
        assert self._served(bag) == self._served(venue) == pytest.approx(0.31)

    @pytest.mark.asyncio
    async def test_three_books_arrive_and_the_next_run_removes_espn(self, monkeypatch):
        books = {"betting": _entry(0.38, NOW), "betting_book_count": 3}
        bag, read_rows, stats = await self._run(
            monkeypatch, {**books, "espn": _entry(0.1415, NOW - timedelta(minutes=10))},
        )
        assert "espn" not in bag and read_rows == [] and stats["removed"] == 1
        assert self._served(bag) == self._served(books) == pytest.approx(0.38)

    @pytest.mark.asyncio
    async def test_a_game_that_was_never_unpriced_never_gets_espn(self, monkeypatch):
        priced = {"polymarket": _entry(0.44, NOW)}
        bag, read_rows, stats = await self._run(monkeypatch, priced)
        assert bag == priced and read_rows == []
        assert stats["written"] == 0 and stats["removed"] == 0

    @pytest.mark.asyncio
    async def test_two_books_under_the_floor_still_get_espn(self, monkeypatch):
        bag, read_rows, stats = await self._run(monkeypatch, {"betting_book_count": 2})
        assert read_rows == [1] and bag["espn"]["value"] == 0.1415
        assert self._served(bag) == pytest.approx(0.1415)


class TestNotAMove:
    """226: A, Fable's item 4: ESPN's number is never measured as a market move."""

    @staticmethod
    def _event(sources, status="scheduled"):
        return SimpleNamespace(win_probability_sources=sources, status=status,
                               espn_win_prob_home=None, opening_home_probability=0.5)

    def test_the_predicate(self):
        from app.utils.aggregation import pregame_blend_rests_on_espn_alone as alone

        assert alone(self._event({"espn": _entry(0.1415, NOW), "betting_book_count": 2}))
        assert not alone(self._event({"espn": _entry(0.14, NOW), "kalshi": _entry(0.3, NOW)}))
        assert not alone(self._event({"kalshi": _entry(0.3, NOW)}))
        assert not alone(self._event({}))
        assert not alone(self._event({"espn": _entry(0.6, NOW)}, status="live"))  # ESPN's live model is a real input

    def test_the_hazard_the_gate_exists_for(self):
        """Fed ESPN's 14% against a 50% opening, the scorer calls it a major swing."""
        from app.utils.highlights import compute_highlight

        swung = compute_highlight(status="scheduled", commence_time=NOW + timedelta(days=20),
                                  sport_key="americanfootball_nfl", current_home_prob=0.1415,
                                  current_away_prob=0.8585, opening_home_prob=0.5,
                                  opening_away_prob=0.5)
        assert "major_prob_swing" in swung.reasons
        gated = compute_highlight(status="scheduled", commence_time=NOW + timedelta(days=20),
                                  sport_key="americanfootball_nfl", current_home_prob=0.1415,
                                  current_away_prob=0.8585, opening_home_prob=None,
                                  opening_away_prob=None)
        assert "major_prob_swing" not in gated.reasons

    def test_every_current_vs_opening_caller_applies_the_gate(self):
        """The three callers that hand compute_highlight an opening line."""
        import inspect

        from app.routes import events, feed
        from app.tasks import taxonomy

        for module in (feed, events, taxonomy):
            assert "pregame_blend_rests_on_espn_alone(event)" in inspect.getsource(module), module.__name__
        src = inspect.getsource(taxonomy._tag_event)
        assert "pregame_blend_rests_on_espn_alone(event)" in src


class TestDuplicateRows:
    """A price on a proven duplicate row prices the game, as on the page.

    Ole Miss–Wofford and Alabama–Chattanooga, Nov 17: Kalshi sat on each game's
    duplicate row, the page folded it in, and the run, reading only the row,
    wrote ESPN on top every 15 minutes (served hero = ESPN's number).
    """

    async def _run(self, monkeypatch, db_rows, fold):
        from contextlib import asynccontextmanager

        bags = {r[0]: {k: (dict(v) if isinstance(v, dict) else v) for k, v in r[6].items()} for r in db_rows}
        session = _FakeSession(db_rows)
        read_rows, writes = [], []

        @asynccontextmanager
        async def fake_session(**_kw):
            yield session

        async def fake_read(rows, now, stats):
            read_rows.extend(r.event_id for r in rows)
            return {r.event_id: ("write", 0.9965, {"basis": "espn_predictor"}) for r in rows}

        async def fake_write(session_, target, source, value, **kw):
            writes.append((target.id, value, (kw.get("evidence") or {}).get("withdrawn")))
            if value is None:
                bags[target.id].pop(source, None)
            else:
                bags[target.id][source] = {"value": value, "updated_at": NOW.isoformat()}

        async def fake_publish(_session):
            return None

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW

        monkeypatch.delenv("ESPN_PREDICTOR_MODE", raising=False)
        monkeypatch.setattr(ep, "twin_price_views", fold)
        monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)
        monkeypatch.setattr(ep, "_read_espn", fake_read)
        monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", fake_write)
        monkeypatch.setattr("app.utils.nonvenue_live_push.publish_committed_nonvenue_frames", fake_publish)
        monkeypatch.setattr(ep, "datetime", _Clock)
        stats = await ep._run_refresh_espn_predictor()
        return bags, read_rows, writes, stats

    @staticmethod
    def _folding(extra_by_id):
        async def fold(_session, rows):
            return {r.event_id: {**r.sources, **extra_by_id.get(r.event_id, {})}
                    for r in rows if r.duplicate_of is None}
        return fold

    @pytest.mark.asyncio
    async def test_a_venue_on_the_duplicate_takes_espn_off_the_game(self, monkeypatch):
        rows = [_db_row(1, {"espn": _entry(0.9965, NOW - timedelta(minutes=10))})]
        bags, read_rows, writes, stats = await self._run(
            monkeypatch, rows, self._folding({1: {"kalshi": _entry(0.995, NOW)}}))
        assert read_rows == [] and writes == [(1, None, "priced")]
        assert "espn" not in bags[1] and stats["removed"] == 1

    @pytest.mark.asyncio
    async def test_a_venue_on_the_duplicate_means_espn_is_never_written(self, monkeypatch):
        rows = [_db_row(1, {"betting_book_count": 2})]
        bags, read_rows, writes, stats = await self._run(
            monkeypatch, rows, self._folding({1: {"kalshi": _entry(0.995, NOW)}}))
        assert read_rows == [] and writes == [] and "espn" not in bags[1]

    @pytest.mark.asyncio
    async def test_an_unpriced_game_with_an_unpriced_duplicate_still_gets_espn(self, monkeypatch):
        rows = [_db_row(1, {})]
        bags, read_rows, writes, stats = await self._run(monkeypatch, rows, self._folding({}))
        assert read_rows == [1] and bags[1]["espn"]["value"] == 0.9965

    @pytest.mark.asyncio
    async def test_a_duplicate_row_is_never_read_and_its_espn_leaves(self, monkeypatch):
        tag = ["provenance:duplicate-of:1"]
        rows = [
            _db_row(1, {}),
            _db_row(2, {"espn": _entry(0.9965, NOW - timedelta(minutes=10))}, tags=tag),
            _db_row(3, {}, tags=["provenance:duplicate-of:1"]),
        ]
        bags, read_rows, writes, stats = await self._run(monkeypatch, rows, self._folding({}))
        assert read_rows == [1]
        assert (2, None, "duplicate") in writes and "espn" not in bags[2]
        assert not any(w[0] == 3 for w in writes) and stats["duplicates"] == 2

    @pytest.mark.asyncio
    async def test_a_failed_fold_reads_nothing_and_old_readings_still_age_out(self, monkeypatch):
        async def broken(_session, _rows):
            raise RuntimeError("fold exploded")

        rows = [
            _db_row(1, {"espn": _entry(0.5, NOW - timedelta(minutes=10))}),   # fresh: kept
            _db_row(2, {"espn": _entry(0.5, NOW - timedelta(hours=3))}),      # 3 h: leaves
            _db_row(3, {}),                                                   # unpriced: not read
            _db_row(4, {"kalshi": _entry(0.3, NOW), "espn": _entry(0.5, NOW)}),  # priced: leaves
        ]
        bags, read_rows, writes, stats = await self._run(monkeypatch, rows, broken)
        assert read_rows == [] and stats["written"] == 0
        assert sorted(w[0] for w in writes) == [2, 4]
        assert "espn" in bags[1] and stats["kept"] == 1
        assert any(e.startswith("fold:") for e in stats["errors"])

    @pytest.mark.asyncio
    async def test_the_real_fold_sees_the_duplicates_kalshi(self):
        """`twin_price_views` through the page's own fold, orientation check included."""
        from app.services.anchor_channel import duplicate_tag

        kalshi = _entry(0.995, NOW)

        class _FoldSession:
            async def execute(self, _stmt):
                rows = [
                    (9, "New England Patriots", "Buffalo Bills", {"kalshi": kalshi},
                     [duplicate_tag(1)], None, None),
                    (8, "Buffalo Bills", "New England Patriots", {"polymarket": kalshi},
                     [duplicate_tag(2)], None, None),   # inverted: must not fold
                ]
                return SimpleNamespace(all=lambda: rows)

        game = ep.PredictorRow(event_id=1, sport_key="americanfootball_nfl", espn_id=None,
                               commence_time=NOW, home_team_name="New England Patriots",
                               away_team_name="Buffalo Bills", sources={})
        other = ep.PredictorRow(event_id=2, sport_key="americanfootball_nfl", espn_id=None,
                                commence_time=NOW, home_team_name="New England Patriots",
                                away_team_name="Buffalo Bills", sources={})
        folded = await _REAL_TWIN_PRICE_VIEWS(_FoldSession(), [game, other])
        assert folded[1]["kalshi"]["value"] == 0.995
        assert ep.is_priced(folded[1])
        assert folded[2] == {}  # an inverted duplicate is not folded
        dup = ep.PredictorRow(event_id=9, sport_key="americanfootball_nfl", espn_id=None,
                              commence_time=NOW, home_team_name="New England Patriots",
                              away_team_name="Buffalo Bills", sources={"kalshi": kalshi},
                              duplicate_of=1)
        assert 9 not in await _REAL_TWIN_PRICE_VIEWS(_FoldSession(), [game, dup])
