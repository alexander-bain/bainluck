"""AUTHORITY step 1 (D50) — tennis and NFL schedules are readable, and still dark.

StatPal becomes the canonical source of games one sport at a time, built dark.
Step 1 is the read: `get_schedule_fixtures()` can see the two schedules the
shared parser is blind to, and nothing else changes.

WHAT WAS BLIND (measured against production responses, 2026-09-03):

    GET /api/v1/nfl/season-schedule       374 games  ->  parser saw 0
    GET /api/v1/tennis/season-schedule    HTTP 404   ->  parser saw 0
    GET /api/v1/tennis/daily/d1            68 games  ->  never called

Three shape facts caused it, and each has an arm below:

  1. NFL nests its games two levels deeper than the shared extractor walks —
     tournament -> stage -> week -> matches -> match — and `matches` is a LIST of
     day wrappers when a week has several game days, a DICT when it has one.
     Both variants are in the pinned fixture.
  2. NFL games carry NO `id`; the key is `contestid`. A game parsed without one
     is not a game we can anchor — 8,272 rows once carried `''` for exactly this
     reason (backend/scripts/repair_statpal_fixture_id_blanks.py).
  3. Tennis serves `tournament` as a LIST (it is a dict for NBA/NHL/MLB) and puts
     the two sides in a two-element `player` array instead of home/away objects,
     and a not-yet-played match's status is the digit "1", not a word.

AND THE OTHER DIRECTION (gotcha #43 — assert both arms). NFL and tennis are both
in STATPAL_SPORT_MAPPING, so `sync_statpal_schedules` already asks for them every
cycle and writes what it gets back. Step 1 must not turn 374 NFL and 68 tennis
fixtures into event writes on the next beat — that is step 2, and it needs its
own review. So the darkness is pinned too: the shared `_parse_fixtures` path
these tasks use still returns zero from the very same payloads.
"""
import json
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService, _normalize_status

FIXTURES = Path(__file__).parent / "fixtures"
NFL_SCHEDULE = FIXTURES / "statpal_nfl_season_schedule_20260903.json"
TENNIS_DAILY = FIXTURES / "statpal_tennis_daily_20260903.json"


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


@pytest.fixture
def nfl_payload():
    return json.loads(NFL_SCHEDULE.read_text())


@pytest.fixture
def tennis_payload():
    return json.loads(TENNIS_DAILY.read_text())


# =============================================================================
# NFL — season-schedule, keyed by contestid
# =============================================================================

class TestNFLSeasonSchedule:
    """The pinned response is Hall of Fame Weekend (1 game, `matches` a dict) plus
    all 16 games of Week 1 (4 game days, `matches` a list), trimmed out of the 374
    the live endpoint returned on 2026-09-03."""

    def test_all_seventeen_games_parse(self, service, nfl_payload):
        fixtures = service._parse_nfl_season_schedule(nfl_payload)
        assert len(fixtures) == 17

    def test_week_one_is_all_sixteen_games_before_they_are_played(self, service, nfl_payload):
        """The ship this program serves: the game exists before anything lists it.
        Week 1 opens 9/09; this response was recorded 9/03."""
        week_one = [
            f for f in service._parse_nfl_season_schedule(nfl_payload)
            if f.round_info == "Regular Season / Week 1"
        ]
        assert len(week_one) == 16
        assert {f.status for f in week_one} == {"scheduled"}

    def test_every_game_carries_a_contestid_as_its_fixture_id(self, service, nfl_payload):
        """No `id` field exists on any NFL game. A blank id is an unusable
        linkage, not an absence — it must never be what we return."""
        fixtures = service._parse_nfl_season_schedule(nfl_payload)
        assert all(f.fixture_id for f in fixtures)
        assert all(f.fixture_id.isdigit() for f in fixtures)
        # The opener, listed 6 days early.
        opener = min(fixtures, key=lambda f: (f.round_info != "Regular Season / Week 1", f.start_time))
        assert opener.fixture_id == "280445"
        assert opener.home_team == "Seattle Seahawks"
        assert opener.away_team == "New England Patriots"

    def test_kickoff_comes_from_datetime_utc_not_the_local_clock(self, service, nfl_payload):
        """`date` is prose ("Wednesday, September 9, 2026") and `time` is venue-local
        ("7:20 PM"). Only `datetime_utc` is an answer, and it is four hours off the
        local one — a fixture matched on the wrong one lands on the wrong day."""
        fixtures = service._parse_nfl_season_schedule(nfl_payload)
        opener = next(f for f in fixtures if f.fixture_id == "280445")
        assert opener.start_time is not None
        assert opener.start_time.isoformat() == "2026-09-10T00:20:00+00:00"
        assert all(f.start_time is not None for f in fixtures)

    def test_a_finished_game_carries_its_result(self, service, nfl_payload):
        finished = [f for f in service._parse_nfl_season_schedule(nfl_payload)
                    if f.status == "finished"]
        assert len(finished) == 1
        game = finished[0]
        assert game.fixture_id == "280493"
        assert (game.home_team, game.home_score) == ("Arizona Cardinals", 30)
        assert (game.away_team, game.away_score) == ("Carolina Panthers", 33)
        assert game.home_q_scores == {"q1": 0, "q2": 17, "q3": 3, "q4": 10}

    def test_stage_and_week_survive_as_round_info(self, service, nfl_payload):
        fixtures = service._parse_nfl_season_schedule(nfl_payload)
        assert {f.round_info for f in fixtures} == {
            "Pre Season / Hall of Fame Weekend",
            "Regular Season / Week 1",
        }
        assert {f.league for f in fixtures} == {"USA: NFL"}


# =============================================================================
# Tennis — daily/{day}, one id space with livescores
# =============================================================================

class TestTennisDailySchedule:
    """The pinned response is 7 US Open matches trimmed from daily/d1, d-1 and d-2,
    each kept under its real tournament: 3 not-yet-played, 2 Finished, 1 Retired,
    1 Cancelled."""

    def test_every_match_parses_with_both_players(self, service, tennis_payload):
        fixtures = service._parse_tennis_daily(tennis_payload)
        assert len(fixtures) == 7
        assert all(f.home_team and f.away_team for f in fixtures)
        assert all(f.fixture_id for f in fixtures)

    def test_the_digit_one_is_a_scheduled_match(self, service, tennis_payload):
        """daily/{d1} stamps every unplayed match "1" while d-1 and d-2 use words.
        Passed through raw, "1" is a status nothing downstream can read."""
        fixtures = service._parse_tennis_daily(tennis_payload)
        upcoming = [f for f in fixtures if f.status == "scheduled"]
        assert len(upcoming) == 3
        assert all(f.raw_status is None for f in upcoming)
        monfils = next(f for f in fixtures if f.fixture_id == "2631263")
        assert (monfils.home_team, monfils.away_team) == ("G. Monfils", "L. Tien")
        assert monfils.start_time.isoformat() == "2026-09-03T23:00:00+00:00"

    def test_a_finished_match_carries_sets_won_and_per_set_games(self, service, tennis_payload):
        match = next(f for f in service._parse_tennis_daily(tennis_payload)
                     if f.fixture_id == "2629739")
        assert match.status == "finished"
        assert match.home_score is not None and match.away_score is not None
        assert match.home_score + match.away_score >= 2  # a completed best-of-three
        assert match.home_q_scores and match.away_q_scores
        assert set(match.home_q_scores).issubset({"s1", "s2", "s3", "s4", "s5"})

    def test_retired_is_a_result_and_cancelled_is_not(self, service, tennis_payload):
        """Both end the match; only one of them produced a winner. Collapsing them
        into one state is how a settled match shows as abandoned."""
        by_id = {f.fixture_id: f for f in service._parse_tennis_daily(tennis_payload)}
        assert by_id["2629666"].status == "finished"   # Retired
        assert by_id["2629658"].status == "cancelled"  # Cancelled

    def test_each_match_keeps_its_own_tournament(self, service, tennis_payload):
        """`tournament` is a list here, so flattening it loses which draw a match
        belongs to — and the ATP and WTA singles draws share a venue and a day."""
        fixtures = service._parse_tennis_daily(tennis_payload)
        assert {f.tournament_id for f in fixtures} == {"13440", "13442"}
        atp = next(f for f in fixtures if f.tournament_id == "13440")
        assert "Atp" in atp.league
        wta = next(f for f in fixtures if f.tournament_id == "13442")
        assert "Wta" in wta.league

    def test_scheduled_match_has_no_invented_set_scores(self, service, tennis_payload):
        """Unplayed sets arrive as "" — a dict of nothing is not a score."""
        monfils = next(f for f in service._parse_tennis_daily(tennis_payload)
                       if f.fixture_id == "2631263")
        assert monfils.home_q_scores is None
        assert monfils.away_q_scores is None
        assert monfils.home_score is None


# =============================================================================
# The day token
# =============================================================================

class TestTennisDayToken:

    def test_offsets_are_minus_seven_to_seven_with_no_zero(self):
        """There is no d0 — today's play is on livescores. Asking for it must not
        look like an empty schedule."""
        assert StatPalAPIService.TENNIS_DAILY_OFFSETS == (
            -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7
        )

    @pytest.mark.parametrize("bad", [0, None, 8, -8, 100])
    @pytest.mark.asyncio
    async def test_an_unusable_day_raises_instead_of_returning_empty(self, service, bad):
        with pytest.raises(ValueError):
            await service.get_schedule_fixtures("tennis", day_offset=bad)

    @pytest.mark.asyncio
    async def test_the_day_token_reaches_the_url(self, service, tennis_payload, monkeypatch):
        seen = {}

        async def fake_get(sport, endpoint, params=None):
            seen["sport"], seen["endpoint"] = sport, endpoint
            return tennis_payload

        monkeypatch.setattr(service, "_get", fake_get)
        fixtures = await service.get_schedule_fixtures("tennis", day_offset=-2)
        assert (seen["sport"], seen["endpoint"]) == ("tennis", "daily/d-2")
        assert len(fixtures) == 7

    def test_twelve_hour_refresh_is_recorded_not_guessed(self):
        """The spec refreshes daily/{day} every 12h; a tighter poll buys nothing."""
        assert StatPalAPIService.TENNIS_DAILY_REFRESH_SECONDS == 12 * 3600


# =============================================================================
# The status words the authority ladder has to tell apart
# =============================================================================

class TestInterruptedAndTerminalStatuses:
    """The event-graph ladder puts authority STATE above scores, so a state that
    passes through as its raw word is a state nothing above can read. These four
    are the ones StatPal actually served on 2026-09-03 (ARTIFACT-M-20260903-B):
    tennis says "Retired" and "Walkover", esports says "Pause" — the only explicit
    interrupted state on any sport that day.

    A fixture payload cannot carry the esports words (we pin tennis and NFL here),
    so the mapping is pinned directly."""

    @pytest.mark.parametrize("raw", ["Retired", "retired", "RET", "Walkover", "W.O."])
    def test_a_match_that_ended_with_a_winner_is_finished(self, raw):
        assert _normalize_status(raw) == "finished"

    @pytest.mark.parametrize("raw", ["Pause", "Paused", "Interrupted", "Suspended"])
    def test_a_match_that_stopped_mid_play_is_suspended(self, raw):
        assert _normalize_status(raw) == "suspended"

    def test_the_two_are_not_collapsed(self):
        """Cancelled is still cancelled: an abandoned match and a retirement do
        not settle the same way."""
        assert _normalize_status("Cancelled") == "cancelled"
        assert _normalize_status("Not Started") == "scheduled"


# =============================================================================
# Still dark — the ingestion path sees exactly what it saw before
# =============================================================================

class TestStillDark:

    def test_shared_parser_still_returns_nothing_for_both_payloads(self, service, nfl_payload, tennis_payload):
        """`sync_statpal_schedules` reads `get_fixtures()`, which reads
        `_parse_fixtures`. If this ever returns rows, NFL and tennis start being
        written to the events table by the next beat, unreviewed."""
        assert service._parse_fixtures(nfl_payload, "nfl") == []
        assert service._parse_fixtures(tennis_payload, "tennis") == []

    @pytest.mark.asyncio
    async def test_get_fixtures_for_tennis_makes_no_request_at_all(self, service):
        """It used to spend a call on /tennis/season-schedule and collect a 404."""
        calls = []

        async def fake_get(sport, endpoint, params=None):
            calls.append((sport, endpoint))
            return None

        monkeypatch_target = fake_get
        service._get = monkeypatch_target
        assert await service.get_fixtures("tennis") == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_other_sports_are_unchanged_by_the_new_entry_point(self, service, monkeypatch):
        """get_schedule_fixtures falls through to get_fixtures for everyone else,
        so the authority path cannot fork a sport's behaviour by accident."""
        seen = []

        async def fake_get(sport, endpoint, params=None):
            seen.append((sport, endpoint))
            return None

        monkeypatch.setattr(service, "_get", fake_get)
        await service.get_schedule_fixtures("nba")
        assert seen == [("nba", "season-schedule")]
