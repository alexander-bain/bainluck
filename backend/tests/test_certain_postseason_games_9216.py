"""#9216 — a postseason game that must be played gets its row when ESPN schedules it.

SHIP: Braves–Phillies and Astros–White Sox Wild Card Game 2 (Wed 9/30) appear on
/sports/baseball_mlb with their Kalshi price as soon as ESPN schedules them.

  Part A  the certainty rule — arithmetic over ESPN's series object, never the
          "If Necessary" label. Pure.
  Part B  the parser reads the real board shape, and a reshaped series object
          costs the series reading, never the event.
  Part C  the registry's ``same_game_only``: a Game 2 claim never lands on the
          Game 1 row a day earlier (bound or not), still attaches to a same-game
          row we hold, and the default matcher is unchanged.
  Part D  the pass: which boards it reads, what it claims, what it leaves alone.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import Event
from app.services import event_registry as registry
from app.services.espn_api import ESPNAPIService
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.tasks import espn_certain_postseason as task
from app.utils.postseason_series import (
    PlayoffSeries,
    certain_to_be_played,
    game_number_from_headlines,
    parse_playoff_series,
)
from tests.test_event_registry import _FakeRegistrySession

# ════════════════════════════════════════════════════════════════════════════
# Part A — the certainty rule
# ════════════════════════════════════════════════════════════════════════════


def _series(game, total, wins=(0, 0), completed=False):
    return PlayoffSeries(game_number=game, total_games=total, wins=wins, completed=completed)


class TestCertainty:
    @pytest.mark.parametrize(
        ("series", "certain", "reason"),
        [
            # Best of 3 (Wild Card): Games 1 and 2 always happen.
            (_series(1, 3), True, "within_wins_needed"),
            (_series(2, 3), True, "within_wins_needed"),
            # Game 3 at 0-0 is the "if necessary" game — the one a created row
            # would leave on the site as a game that never happens.
            (_series(3, 3), False, "if_necessary"),
            # ...at 1-0 it is still not certain: Game 2 may end it.
            (_series(3, 3, (1, 0)), False, "if_necessary"),
            # ...at 1-1 it is certain, whatever ESPN's label still says.
            (_series(3, 3, (1, 1)), True, "next_game_of_open_series"),
            # Best of 5 (LDS): Games 1-3 always happen.
            (_series(3, 5), True, "within_wins_needed"),
            (_series(4, 5), False, "if_necessary"),
            (_series(4, 5, (2, 1)), True, "next_game_of_open_series"),
            (_series(5, 5, (2, 1)), False, "if_necessary"),
            # Best of 7: Game 4 always; Game 5 at 3-1 yes; Game 6 at 3-1 no.
            (_series(4, 7), True, "within_wins_needed"),
            (_series(5, 7, (3, 1)), True, "next_game_of_open_series"),
            (_series(6, 7, (3, 1)), False, "if_necessary"),
            # A series somebody has won creates nothing.
            (_series(5, 7, (4, 0), completed=True), False, "series_over"),
            (_series(2, 3, (2, 0), completed=False), False, "series_over"),
        ],
    )
    def test_the_arithmetic(self, series, certain, reason):
        assert certain_to_be_played(series) == (certain, reason)

    @pytest.mark.parametrize(
        ("series", "reason"),
        [
            (None, "not_a_series"),
            (_series(None, 3), "no_game_number"),
            (_series(0, 3), "no_game_number"),
            (_series(2, None), "no_series_length"),
            (_series(4, 3), "no_series_length"),
            (_series(2, 3, ()), "no_standings"),
            (_series(2, 3, (0,)), "no_standings"),
            (_series(2, 3, completed=None), "no_completed_flag"),
        ],
    )
    def test_every_gap_refuses(self, series, reason):
        assert certain_to_be_played(series) == (False, reason)

    def test_two_different_game_numbers_are_a_contradiction_not_a_game(self):
        assert game_number_from_headlines(["NLWC - Game 2", "Game 3"]) is None
        assert game_number_from_headlines(["NLWC - Game 2", "NLWC - Game 2"]) == 2
        assert game_number_from_headlines([None, 7, "Wild Card"]) is None


# ════════════════════════════════════════════════════════════════════════════
# Part B — the parser, on the board's own shape
# ════════════════════════════════════════════════════════════════════════════

#: ESPN baseball/mlb/scoreboard?dates=20260930, event 401907972, read
#: 2026-09-28 05:3xZ — trimmed to the keys the parser reads.
PHI_ATL_G2 = {
    "id": "401907972",
    "name": "Philadelphia Phillies at Atlanta Braves",
    "shortName": "PHI @ ATL",
    "date": "2026-09-30T18:00Z",
    "season": {"year": 2026, "type": 3, "slug": "post-season"},
    "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre", "detail": "Wed, September 30th at 2:00 PM EDT"}},
    "competitions": [{
        "timeValid": True,
        "notes": [{"type": "event", "headline": "NLWC - Game 2"}],
        "series": {
            "type": "playoff", "title": "Playoff Series", "summary": "Series starts 9/29",
            "completed": False, "totalCompetitions": 3,
            "competitors": [{"id": "15", "wins": 0, "ties": 0}, {"id": "22", "wins": 0, "ties": 0}],
        },
        "competitors": [
            {"homeAway": "home", "team": {"id": "15", "displayName": "Atlanta Braves", "name": "Braves", "abbreviation": "ATL"}},
            {"homeAway": "away", "team": {"id": "22", "displayName": "Philadelphia Phillies", "name": "Phillies", "abbreviation": "PHI"}},
        ],
    }],
}


def _payload(game_headline="NLWC - Game 2", espn_id="401907972", date="2026-09-30T18:00Z", **series):
    p = copy.deepcopy(PHI_ATL_G2)
    p["id"] = espn_id
    p["date"] = date
    comp = p["competitions"][0]
    comp["notes"][0]["headline"] = game_headline
    comp["series"].update(series)
    return p


class TestParser:
    def test_the_specimen_parses_to_a_certain_game_two(self):
        ee = ESPNAPIService()._parse_event(PHI_ATL_G2)
        assert ee.espn_id == "401907972"
        assert ee.season_type == 3
        assert ee.playoff_series == PlayoffSeries(2, 3, (0, 0), False)
        assert certain_to_be_played(ee.playoff_series) == (True, "within_wins_needed")

    def test_game_three_if_necessary_parses_and_is_refused(self):
        ee = ESPNAPIService()._parse_event(_payload("NLWC - Game 3 If Necessary", "401907973"))
        assert ee.playoff_series.game_number == 3
        assert certain_to_be_played(ee.playoff_series) == (False, "if_necessary")

    def test_a_regular_season_game_has_no_series(self):
        p = copy.deepcopy(PHI_ATL_G2)
        del p["competitions"][0]["series"]
        p["competitions"][0]["notes"] = []
        assert ESPNAPIService()._parse_event(p).playoff_series is None

    @pytest.mark.parametrize(
        "series",
        [
            "not a dict",
            {"type": "playoff", "competitors": "garbage", "totalCompetitions": "3"},
            {"type": "playoff", "competitors": [{"wins": "0"}, {"wins": True}]},
            {"type": "season"},
        ],
    )
    def test_a_reshaped_series_costs_the_series_reading_never_the_event(self, series):
        p = copy.deepcopy(PHI_ATL_G2)
        p["competitions"][0]["series"] = series
        ee = ESPNAPIService()._parse_event(p)
        assert ee is not None and ee.espn_id == "401907972"
        assert certain_to_be_played(ee.playoff_series)[0] is False

    def test_the_parser_guard_catches_a_raising_series_reader(self, monkeypatch):
        import app.services.espn_api as espn_api

        def _boom(_competition):
            raise RuntimeError("reshaped")

        monkeypatch.setattr(espn_api, "parse_playoff_series", _boom)
        ee = ESPNAPIService()._parse_event(PHI_ATL_G2)
        assert ee is not None and ee.playoff_series is None

    def test_parse_playoff_series_ignores_non_dicts(self):
        assert parse_playoff_series(None) is None
        assert parse_playoff_series({"series": None}) is None


# ════════════════════════════════════════════════════════════════════════════
# Part C — the registry's same_game_only
# ════════════════════════════════════════════════════════════════════════════

G1_TIME = datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)
G2_TIME = datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)
G2_ESPN = "401907972"
G1_ESPN = "401907965"


def _row(id, commence_time, *, espn_id=None, source="odds_api"):
    return Event(
        id=id,
        sport_id=1,
        home_team_name="Atlanta Braves",
        away_team_name="Philadelphia Phillies",
        commence_time=commence_time,
        commence_time_source=source,
        status="scheduled",
        espn_id=espn_id,
    )


def _g2_identity(*, same_game_only):
    return EventIdentity(
        sport_key="baseball_mlb",
        home_team_name="Atlanta Braves",
        away_team_name="Philadelphia Phillies",
        commence_time=G2_TIME,
        claim=EventClaim("espn", G2_ESPN, schedule_derived=True),
        commence_time_source="espn",
        status="scheduled",
        same_game_only=same_game_only,
    )


class TestSameGameOnly:
    @pytest.mark.asyncio
    async def test_the_hazard_the_default_matcher_has(self):
        """The reason the flag exists, pinned: with Game 2 rowless, the ±28h
        window hands its claim the UNBOUND Game 1 row 24h earlier, stamps Game 2's
        id on it and drags Game 1's start onto Game 2's. If this ever stops
        being true the flag is no longer load-bearing — re-read #9216."""
        g1 = _row(15320289, G1_TIME)
        session = _FakeRegistrySession(structured_candidates=[g1])
        _sport_id_cache.clear()

        event, created = await find_or_create_event(session, _g2_identity(same_game_only=False))

        assert event is g1 and created is False
        assert g1.espn_id == G2_ESPN
        assert g1.commence_time == G2_TIME

    @pytest.mark.asyncio
    async def test_game_two_is_created_and_the_unbound_game_one_row_is_untouched(self):
        g1 = _row(15320289, G1_TIME)
        session = _FakeRegistrySession(structured_candidates=[g1])
        _sport_id_cache.clear()

        event, created = await find_or_create_event(session, _g2_identity(same_game_only=True))

        assert created is True
        assert event is not g1
        assert event.espn_id == G2_ESPN
        assert event.commence_time == G2_TIME
        assert "provenance:source:espn" in event.event_tags
        assert "provenance:unanchored" not in event.event_tags
        assert session.added == [event]
        # Game 1's row is exactly as it was.
        assert g1.espn_id is None
        assert g1.commence_time == G1_TIME
        assert g1.commence_time_source == "odds_api"

    @pytest.mark.asyncio
    async def test_a_game_one_row_bound_to_its_own_espn_game_is_refused_too(self):
        g1 = _row(15320289, G1_TIME, espn_id=G1_ESPN, source="espn")
        session = _FakeRegistrySession(structured_candidates=[g1])
        _sport_id_cache.clear()

        event, created = await find_or_create_event(session, _g2_identity(same_game_only=True))

        assert created is True and event is not g1
        assert g1.espn_id == G1_ESPN

    @pytest.mark.asyncio
    async def test_a_same_day_row_bound_to_another_espn_game_is_refused(self):
        """Within 12h but holding a different ESPN id: the provider says it is
        another game (``_proven_duplicates`` clause 3)."""
        other = _row(900, G2_TIME + timedelta(hours=1), espn_id="401999999", source="espn")
        session = _FakeRegistrySession(structured_candidates=[other])
        _sport_id_cache.clear()

        event, created = await find_or_create_event(session, _g2_identity(same_game_only=True))

        assert created is True and event is not other
        assert other.espn_id == "401999999"

    @pytest.mark.asyncio
    async def test_the_same_game_row_we_hold_still_takes_the_claim(self):
        """StatPal's Game 2 row sat on a 20:00Z placeholder while ESPN had the
        real start (the Red Sox–Yankees Game 1 shape). It is the same game: the
        claim attaches, stamps the id and corrects the start. Game 1 beside it
        is not chosen, although it is also a name match (gotcha #43: both
        directions)."""
        g1 = _row(15320289, G1_TIME, espn_id=G1_ESPN, source="espn")
        g2 = _row(15319236, G2_TIME - timedelta(hours=4), source="statpal")
        session = _FakeRegistrySession(structured_candidates=[g1, g2])
        _sport_id_cache.clear()

        event, created = await find_or_create_event(session, _g2_identity(same_game_only=True))

        assert event is g2 and created is False
        assert g2.espn_id == G2_ESPN
        assert g2.commence_time == G2_TIME
        assert session.added == []
        assert g1.espn_id == G1_ESPN and g1.commence_time == G1_TIME

    @pytest.mark.asyncio
    async def test_the_flag_defaults_off(self):
        assert EventIdentity(
            sport_key="baseball_mlb", home_team_name="a", away_team_name="b",
            commence_time=G2_TIME, claim=EventClaim("espn", "1", schedule_derived=True),
        ).same_game_only is False

    def test_could_be_this_game_refuses_a_row_with_no_time(self):
        row = _row(1, None)
        claim = EventClaim("espn", G2_ESPN, schedule_derived=True)
        assert registry._could_be_this_game(row, G2_TIME, claim) is False
        row.commence_time = G2_TIME
        assert registry._could_be_this_game(row, G2_TIME, claim) is True
        row.espn_id = G2_ESPN  # its own id is not "another game"
        assert registry._could_be_this_game(row, G2_TIME, claim) is True


# ════════════════════════════════════════════════════════════════════════════
# Part D — the pass
# ════════════════════════════════════════════════════════════════════════════

NOW = datetime(2026, 9, 28, 5, 30, tzinfo=timezone.utc)  # 1:30 AM EDT 9/28


def _board_event(espn_id, game, *, season_type=3, status="scheduled", wins=(0, 0), total=3,
                 completed=False, date=G2_TIME, home="Atlanta Braves", away="Philadelphia Phillies"):
    return SimpleNamespace(
        espn_id=espn_id,
        season_type=season_type,
        status=status,
        date=date,
        time_valid=True,
        home_team=SimpleNamespace(display_name=home, name=""),
        away_team=SimpleNamespace(display_name=away, name=""),
        playoff_series=PlayoffSeries(game, total, wins, completed) if game else None,
    )


class _Session:
    """``held``: ids a row carries. ``unmarked``: held ids whose row is not yet
    marked playoff — the fake answers the #9602 statement from it; the predicate
    itself is proved on real Postgres (``test_certain_postseason_playoff_pg_9602``)."""

    def __init__(self, held=(), unmarked=(), fail_marking=()):
        self.held = set(held)
        self.unmarked = set(unmarked)
        self.fail_marking = set(fail_marking)
        self.commits = 0
        self.rollbacks = 0
        self.marks: list[tuple[str, list, bool]] = []

    async def execute(self, statement, params=None):
        compiled = statement.compile().params
        if "llm_importance" in str(statement):
            sport = next(v for k, v in compiled.items() if k.startswith("key"))
            wanted = next(v for k, v in compiled.items() if k.startswith("espn_id"))
            self.marks.append((sport, list(wanted), statement.is_dml))
            if sport in self.fail_marking:
                raise RuntimeError("lock timeout")
            rows = [(9000 + int(i),) for i in wanted if i in self.unmarked]
            return SimpleNamespace(all=lambda: rows)
        wanted = next(iter(compiled.values()))
        rows = [(i,) for i in wanted if i in self.held]
        return SimpleNamespace(all=lambda: rows)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, boards, *, held=(), fail_ids=(), unmarked=(), fail_marking=()):
    import app.services.espn_api as espn_api
    import app.tasks.base as task_base

    session = _Session(held, unmarked, fail_marking)
    reads, claims = [], []

    class _Espn:
        async def get_scoreboard(self, sport_key, date=None, groups=None):
            reads.append((sport_key, date))
            board = boards.get((sport_key, date), [])
            if isinstance(board, Exception):
                raise board
            return board

        async def close(self):
            pass

    async def _foc(sess, identity):
        claims.append(identity)
        if identity.claim.source_id in fail_ids:
            raise RuntimeError("boom")
        return SimpleNamespace(id=500 + len(claims)), True

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx(session))
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda *a, **kw: _Espn())
    monkeypatch.setattr(registry, "find_or_create_event", _foc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(task, "datetime", _FrozenDatetime)
    return session, reads, claims


def test_board_days_are_eastern_and_start_tomorrow():
    # 05:30Z on 9/28 is still 9/28 in the East (1:30 AM EDT)...
    assert task.board_days(NOW) == ["20260929", "20260930", "20261001"]
    # ...and 03:30Z on 9/28 is 9/27 there, so tomorrow is 9/28.
    assert task.board_days(NOW - timedelta(hours=2)) == ["20260928", "20260929", "20260930"]


@pytest.mark.asyncio
async def test_the_pass_claims_game_two_and_leaves_game_three_alone(monkeypatch):
    boards = {
        ("baseball_mlb", "20260930"): [
            _board_event("401907972", 2),
            _board_event("401907897", 2, home="Houston Astros", away="Chicago White Sox"),
        ],
        ("baseball_mlb", "20261001"): [_board_event("401907973", 3, date=G2_TIME + timedelta(days=1))],
    }
    session, reads, claims = _wire(monkeypatch, boards)

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [c.claim.source_id for c in claims] == ["401907972", "401907897"]
    for identity in claims:
        assert identity.same_game_only is True
        assert identity.claim.source == "espn" and identity.claim.schedule_derived is True
        assert identity.status == "scheduled"
        assert identity.commence_time_source == "espn"
    assert claims[0].home_team_name == "Atlanta Braves"
    assert claims[0].away_team_name == "Philadelphia Phillies"
    assert claims[0].commence_time == G2_TIME
    assert stats["created"] == 2 and stats["created_ids"] == [501, 502]
    assert stats["refused_if_necessary"] == 1
    # One per claimed game, then one for the #9602 playoff mark over both rows.
    assert session.commits == 3
    assert session.marks == [("baseball_mlb", ["401907897", "401907972"], True)]
    # Every lookahead day for every league; empty boards do not stop the read.
    assert [r for r in reads if r[0] == "baseball_mlb"] == [
        ("baseball_mlb", "20260929"), ("baseball_mlb", "20260930"), ("baseball_mlb", "20261001"),
    ]
    assert stats["status"] == "complete"


@pytest.mark.asyncio
async def test_a_game_whose_id_we_hold_is_not_claimed_again(monkeypatch):
    boards = {("baseball_mlb", "20260930"): [_board_event("401907972", 2), _board_event("401907963", 2)]}
    _session, _reads, claims = _wire(monkeypatch, boards, held={"401907963"})

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [c.claim.source_id for c in claims] == ["401907972"]
    assert stats["already_held"] == 1


@pytest.mark.asyncio
async def test_dry_run_plans_and_writes_nothing(monkeypatch):
    boards = {("baseball_mlb", "20260930"): [_board_event("401907972", 2)]}
    session, _reads, claims = _wire(monkeypatch, boards)

    stats = await task._run_create_certain_postseason_games(apply=False)

    assert claims == [] and session.commits == 0
    assert [p["espn_id"] for p in stats["planned"]] == ["401907972"]
    assert stats["planned"][0]["game_number"] == 2


@pytest.mark.asyncio
async def test_one_failing_game_does_not_cost_the_next(monkeypatch):
    boards = {("baseball_mlb", "20260930"): [_board_event("401907972", 2), _board_event("401907897", 2)]}
    session, _reads, claims = _wire(monkeypatch, boards, fail_ids={"401907972"})

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [c.claim.source_id for c in claims] == ["401907972", "401907897"]
    assert stats["created"] == 1 and session.rollbacks == 1
    assert stats["status"] == "partial"


@pytest.mark.asyncio
async def test_a_regular_season_board_stops_that_league_and_a_dark_board_proves_nothing(monkeypatch):
    boards = {
        ("icehockey_nhl", "20260929"): [_board_event("401800001", None, season_type=1)],
        ("basketball_nba", "20260929"): None,  # ESPN did not answer
        ("basketball_nba", "20260930"): RuntimeError("timeout"),
    }
    _session, reads, claims = _wire(monkeypatch, boards)

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [r for r in reads if r[0] == "icehockey_nhl"] == [("icehockey_nhl", "20260929")]
    assert len([r for r in reads if r[0] == "basketball_nba"]) == 3
    assert stats["sports_not_in_postseason"] == 1
    assert stats["boards_dark"] == 1
    assert claims == []
    assert stats["status"] == "no_candidates"


def test_select_certain_games_refuses_what_it_cannot_claim():
    stats: dict = {}
    board = [
        _board_event("1", 2, status="in"),
        _board_event("2", 2, home=""),
        _board_event("", 2),
        _board_event("4", 2, date=None),
        _board_event("5", None),
        _board_event("6", 2, season_type=2),
        _board_event("7", 2),
    ]
    kept = task.select_certain_games(board, stats)
    assert [ee.espn_id for ee in kept] == ["7"]
    assert stats == {
        "refused_not_scheduled": 1,
        "refused_no_teams": 1,
        "refused_no_id": 1,
        "refused_no_date": 1,
        "refused_not_a_series": 1,
    }


def test_the_claim_carries_the_placeholder_flag_for_an_unannounced_start():
    ee = _board_event("401907972", 2)
    ee.time_valid = False
    assert task.claim_identity("baseball_mlb", ee).commence_time_is_placeholder is True
    ee.time_valid = True
    assert task.claim_identity("baseball_mlb", ee).commence_time_is_placeholder is False


# ════════════════════════════════════════════════════════════════════════════
# Part E — #9602: a certain game's row reads as a playoff game before game day
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_held_game_two_that_reads_regular_season_is_marked_playoff(monkeypatch):
    """THE SHIP. Production 9/29 11:05Z: 15320701 / 15320702 hold 401907972 /
    401907897, ESPN's 9/30 board says season.type=3, the rows said
    'regular_season', and the pass counted both `already_held` and moved on."""
    boards = {
        ("baseball_mlb", "20260930"): [
            _board_event("401907972", 2),
            _board_event("401907897", 2, home="Houston Astros", away="Chicago White Sox"),
        ],
    }
    held = {"401907972", "401907897"}
    session, _reads, claims = _wire(monkeypatch, boards, held=held, unmarked=held)

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert claims == [] and stats["already_held"] == 2
    assert session.marks == [("baseball_mlb", ["401907897", "401907972"], True)]
    assert stats["marked_playoff"] == 2
    assert stats["marked_playoff_ids"] == [9000 + 401907897, 9000 + 401907972]
    assert session.commits == 1
    assert stats["status"] == "complete"


@pytest.mark.asyncio
async def test_a_row_the_pass_just_made_is_marked_too_and_a_failed_claim_is_not(monkeypatch):
    boards = {
        ("baseball_mlb", "20260930"): [
            _board_event("401907972", 2),
            _board_event("401907897", 2),
            _board_event("401907898", 2),
        ],
    }
    session, _reads, _claims = _wire(
        monkeypatch, boards, held={"401907897"}, fail_ids={"401907898"}
    )

    stats = await task._run_create_certain_postseason_games(apply=True)

    # 972 was created this run, 897 was held; 898's claim raised — no row, no mark.
    assert session.marks == [("baseball_mlb", ["401907897", "401907972"], True)]
    assert stats["created"] == 1


@pytest.mark.asyncio
async def test_each_league_is_marked_on_its_own_and_one_failure_costs_only_that_league(monkeypatch):
    boards = {
        ("basketball_nba", "20260930"): [_board_event("401800100", 2)],
        ("baseball_mlb", "20260930"): [_board_event("401907972", 2)],
    }
    held = {"401907972", "401800100"}
    session, _reads, _claims = _wire(
        monkeypatch, boards, held=held, unmarked=held, fail_marking={"baseball_mlb"}
    )

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [(m[0], m[1]) for m in session.marks] == [
        ("baseball_mlb", ["401907972"]), ("basketball_nba", ["401800100"]),
    ]
    assert session.rollbacks == 1
    assert stats["marked_playoff_ids"] == [9000 + 401800100]
    assert stats["errors"] == ["baseball_mlb/importance: lock timeout"]
    assert stats["status"] == "partial"


@pytest.mark.asyncio
async def test_a_dry_run_counts_the_rows_it_would_mark_and_writes_nothing(monkeypatch):
    boards = {("baseball_mlb", "20260930"): [_board_event("401907972", 2), _board_event("401907897", 2)]}
    session, _reads, claims = _wire(
        monkeypatch, boards, held={"401907972"}, unmarked={"401907972"}
    )

    stats = await task._run_create_certain_postseason_games(apply=False)

    # Only the row held before the run; the planned one does not exist yet.
    assert session.marks == [("baseball_mlb", ["401907972"], False)]
    assert stats["marked_playoff"] == 1
    assert claims == [] and session.commits == 0


def test_the_statement_marks_playoff_and_never_downgrades_a_championship():
    from sqlalchemy.dialects import postgresql

    sql = str(
        task.mark_playoff_statement("baseball_mlb", ["401907972"]).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "SET llm_importance='playoff'" in sql
    assert "events.llm_importance IS NULL OR (events.llm_importance NOT IN ('playoff', 'championship'))" in sql
    assert "sports.key = 'baseball_mlb'" in sql
    assert "events.espn_id IN ('401907972')" in sql
