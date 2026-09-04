"""AUTHORITY step 3 (D50) — NBA and NHL read through the authority door.

Step 1 taught `get_schedule_fixtures()` two schedules the shared parser could
not see at all. NBA and NHL are the opposite case, and the difference is the
point of this file: the shared parser reads them fine.

MEASURED AGAINST PRODUCTION, 2026-09-03:

    GET /api/v1/nba/season-schedule   1206 games, 03.10.2026 -> 04.04.2027
    GET /api/v1/nhl/season-schedule   1404 games, 19.09.2026 -> 10.04.2027

    `_parse_fixtures` (the ingestion path) reads 1206 and 1404 of them, with
    every fixture_id and every start_time populated. Nothing is blind.

So what is this for? Three things the ingestion path discards or misreports,
each of which the authority program needs and each of which has an arm below.

  1. THE TOURNAMENT WRAPPER IS THROWN AWAY. `league`, `season` and the
     tournament `id` live one level above the match array, and
     `_extract_match_items` flattens straight to the matches. Every NBA and NHL
     fixture the ingestion path has ever built carries league=None and
     season=None. A fixture that does not know it is NBA 2026/2027 cannot be
     stamped against one.

  2. `stats_id` IS DROPPED, AND IT IS NOT UNIVERSAL. StatPal serves a second id
     beside `id` on these endpoints. NHL fills it on 1404/1404 games; NBA fills
     it on 0/1206. `docs/statpal-capabilities.md` credits both sports with
     "`id` + `stats_id`" — for NBA that is not what the endpoint serves. Which
     id anchors a game is step 5's open question and a reader that discards one
     of them cannot answer it.

  3. A FAILED READ ARRIVES AS AN EMPTY SCHEDULE. `_get` returns None for
     timeout, 401, 404, 429, 500 and for a 200 whose body is an error; the
     ingestion path turns all of that into `[]`, which is also what "no games"
     looks like. That is gotcha #53 exactly, and for a program whose whole
     output is "does StatPal know about this game" it is the difference between
     a finding and a forgery. The authority path raises.

AND THE OTHER DIRECTION (gotcha #43). NBA and NHL are in
STATPAL_SPORT_MAPPING, so `sync_statpal_schedules` already reads and writes
them every cycle. This change must not alter one row of that. TestStillDark
pins the ingestion path against the very same payloads.

WHAT IS NOT PINNED HERE, AND WHY. Every one of the 2,610 games on both
schedules is "Not Started" — neither season has begun (NBA opens 10/3, NHL
9/19). Live and finished state for these two sports is unverifiable until then
and is deliberately unasserted rather than guessed.
"""
import json
import logging
from pathlib import Path

import httpx
import pytest

from app.services.statpal_api import (
    StatPalAPIService,
    StatPalUpstreamError,
    _error_body,
)

FIXTURES = Path(__file__).parent / "fixtures"
NBA_SCHEDULE = FIXTURES / "statpal_nba_season_schedule_20260903.json"
NHL_SCHEDULE = FIXTURES / "statpal_nhl_season_schedule_20260903.json"

# The pinned payloads are a 9-game slice of each real response (opening day,
# quarter/half/three-quarter marks, closing day) so the file stays reviewable.
# The full-corpus numbers in the docstring came from the whole response and are
# recorded in ARTIFACT-AUTHORITY-20260903-NBA-NHL.md.
PINNED_GAMES = 9


@pytest.fixture
def service():
    return StatPalAPIService(api_key="test-key-not-a-real-key")


@pytest.fixture
def nba_payload():
    return json.loads(NBA_SCHEDULE.read_text())


@pytest.fixture
def nhl_payload():
    return json.loads(NHL_SCHEDULE.read_text())


# =============================================================================
# The games themselves
# =============================================================================

class TestSeasonSchedulesParse:

    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    def test_every_game_in_the_slice_parses(self, service, sport, nba_payload, nhl_payload):
        payload = nba_payload if sport == "nba" else nhl_payload
        fixtures = service._parse_v1_season_schedule(payload, sport)
        assert len(fixtures) == PINNED_GAMES

    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    def test_every_game_is_anchorable_and_scheduled_to_a_minute(
        self, service, sport, nba_payload, nhl_payload
    ):
        """A game with no id cannot be stamped; a game with no start cannot be
        matched to ours by kickoff. 8,272 rows once carried '' for the first
        (backend/scripts/repair_statpal_fixture_id_blanks.py)."""
        payload = nba_payload if sport == "nba" else nhl_payload
        fixtures = service._parse_v1_season_schedule(payload, sport)
        assert all(f.fixture_id for f in fixtures)
        assert all(f.start_time for f in fixtures)
        assert all(f.home_team and f.away_team for f in fixtures)

    def test_kickoff_is_read_as_utc_not_as_venue_local(self, service, nba_payload):
        """StatPal serves NBA/NHL `date` + `time` with no `datetime_utc`. The
        Raptors' 03.10.2026 home opener reads 23:00, i.e. 7:00 PM in Toronto —
        so `time` is UTC. Read as venue-local it would be four hours wrong and
        land on the wrong day for every West Coast night game."""
        opener = service._parse_v1_season_schedule(nba_payload, "nba")[0]
        assert opener.home_team == "Toronto Raptors"
        assert opener.start_time.isoformat() == "2026-10-03T23:00:00+00:00"

    def test_the_slice_spans_the_whole_season(self, service, nhl_payload):
        """Pinning only opening night would let a parser that reads one date
        format pass. The slice runs 19.09.2026 to 10.04.2027."""
        fixtures = service._parse_v1_season_schedule(nhl_payload, "nhl")
        assert fixtures[0].start_time.date().isoformat() == "2026-09-19"
        assert fixtures[-1].start_time.date().isoformat() == "2027-04-10"


# =============================================================================
# 1. The tournament wrapper — both arms
# =============================================================================

class TestTournamentWrapperSurvives:

    @pytest.mark.parametrize(
        "sport,league,tournament_id",
        [("nba", "NBA", "2545"), ("nhl", "NHL", "2506")],
    )
    def test_league_season_and_tournament_id_reach_every_fixture(
        self, service, sport, league, tournament_id, nba_payload, nhl_payload
    ):
        payload = nba_payload if sport == "nba" else nhl_payload
        fixtures = service._parse_v1_season_schedule(payload, sport)
        assert {f.league for f in fixtures} == {league}
        assert {f.season for f in fixtures} == {"2026/2027"}
        assert {f.tournament_id for f in fixtures} == {tournament_id}

    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    def test_the_ingestion_parser_loses_all_three(
        self, service, sport, nba_payload, nhl_payload
    ):
        """The other arm. If this ever starts passing league/season through,
        the authority reader's reason to exist shrinks and someone should be
        told rather than left to discover it."""
        payload = nba_payload if sport == "nba" else nhl_payload
        fixtures = service._parse_fixtures(payload, sport)
        assert len(fixtures) == PINNED_GAMES, "the shared parser reads these fine"
        assert {f.league for f in fixtures} == {None}
        assert {f.season for f in fixtures} == {None}
        assert {f.tournament_id for f in fixtures} == {None}


# =============================================================================
# 2. stats_id — carried, and not invented
# =============================================================================

class TestSecondId:

    def test_nhl_serves_a_stats_id_for_every_game(self, service, nhl_payload):
        fixtures = service._parse_v1_season_schedule(nhl_payload, "nhl")
        assert all(f.stats_id for f in fixtures)
        assert fixtures[0].stats_id == "68933"
        # ...and it is a different number from the primary id, not an alias.
        assert all(f.stats_id != f.fixture_id for f in fixtures)

    def test_nba_serves_none_and_we_do_not_manufacture_one(self, service, nba_payload):
        """Measured 0/1206 on the live response. StatPal sends the key with an
        empty string; a reader that stored that would put '' in an id column
        and an empty string is not an id."""
        fixtures = service._parse_v1_season_schedule(nba_payload, "nba")
        assert all(f.stats_id is None for f in fixtures)
        assert all(f.fixture_id for f in fixtures), "the primary id is unaffected"

    def test_the_ingestion_parser_carries_neither(self, service, nhl_payload):
        """The other arm: today's NHL rows have no stats_id at all."""
        fixtures = service._parse_fixtures(nhl_payload, "nhl")
        assert {f.stats_id for f in fixtures} == {None}


# =============================================================================
# 3. A failed read is not an empty schedule (gotcha #53)
# =============================================================================

class TestAFailureIsNotAnAbsence:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sport", ["nba", "nhl", "nfl", "tennis"])
    async def test_the_authority_path_raises_when_statpal_does_not_answer(
        self, service, sport, monkeypatch
    ):
        """`_get` returns None for every failure it recognises. Silently
        becoming `[]` here would let the agreement ledger publish "StatPal does
        not know about any of these games" on a day the API was simply down."""
        async def fake_get(sport_, endpoint, params=None):
            return None

        monkeypatch.setattr(service, "_get", fake_get)
        with pytest.raises(StatPalUpstreamError):
            await service.get_schedule_fixtures(
                sport, day_offset=1 if sport == "tennis" else None
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    async def test_an_empty_two_hundred_raises_rather_than_reporting_no_season(
        self, service, sport, monkeypatch
    ):
        """`{"scores": {"sport": "basketball"}}` is a real response — it is what
        /nba/daily/d1 served on 2026-09-03 for a day with no games. Applied to
        a whole SEASON it cannot mean what it says: 1206 games do not go quiet."""
        async def fake_get(sport_, endpoint, params=None):
            return {"scores": {"sport": "basketball"}}

        monkeypatch.setattr(service, "_get", fake_get)
        with pytest.raises(StatPalUpstreamError):
            await service.get_schedule_fixtures(sport)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    async def test_a_real_answer_does_not_raise(
        self, service, sport, monkeypatch, nba_payload, nhl_payload
    ):
        """The control. Both arms of a raise-guard have to be shown, or the
        guard is indistinguishable from a method that always raises."""
        payload = nba_payload if sport == "nba" else nhl_payload

        async def fake_get(sport_, endpoint, params=None):
            assert (sport_, endpoint) == (sport, "season-schedule")
            return payload

        monkeypatch.setattr(service, "_get", fake_get)
        fixtures = await service.get_schedule_fixtures(sport)
        assert len(fixtures) == PINNED_GAMES


# =============================================================================
# The transport: a 200 that carries a complaint is not data
# =============================================================================

class TestErrorBodiesAtHttpTwoHundred:

    @pytest.mark.parametrize(
        "payload",
        [
            "invalid-request",
            "Invalid-Request",
            {"error": "Invalid access key or sport. Must include access_key parameter."},
            {"error": "Internal Server Error."},
        ],
    )
    def test_these_are_complaints(self, payload):
        assert _error_body(payload)

    @pytest.mark.parametrize(
        "payload",
        [
            {"scores": {"sport": "basketball", "tournament": {"match": []}}},
            # An endpoint that answered and has nothing for that day. The
            # transport must NOT call this an error — telling "empty" from
            # "broken" is the parser's job, and it needs the payload to do it.
            {"scores": {"sport": "basketball"}},
            {"livescores": {"sport": "hockey"}},
            {},
            None,
            [],
        ],
    )
    def test_these_are_not(self, payload):
        assert _error_body(payload) is None

    def test_a_real_schedule_is_not_a_complaint(self, nba_payload):
        assert _error_body(nba_payload) is None

    @pytest.mark.asyncio
    async def test_get_refuses_a_two_hundred_whose_body_is_an_error(
        self, service, monkeypatch, caplog
    ):
        """Straight through the transport, not just the helper: the caller must
        receive None, and the operator must see why."""
        async def fake_http_get(url, params=None):
            return httpx.Response(
                200,
                json={"error": "Invalid access key or sport."},
                request=httpx.Request("GET", url),
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        with caplog.at_level(logging.ERROR):
            assert await service._get("nba", "season-schedule") is None
        assert "the body is an error" in caplog.text

    @pytest.mark.asyncio
    async def test_get_refuses_a_two_hundred_that_is_not_json_at_all(
        self, service, monkeypatch
    ):
        """`invalid-request` is served unquoted, so it never survives
        `.json()`. Before this, the ValueError fell through to the catch-all
        and was logged as an 'unexpected error'."""
        async def fake_http_get(url, params=None):
            return httpx.Response(
                200, text="invalid-request", request=httpx.Request("GET", url)
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert await service._get("nba", "season-schedule") is None

    @pytest.mark.asyncio
    async def test_get_still_returns_a_real_payload(self, service, monkeypatch, nba_payload):
        """The control: the new gate does not eat good responses."""
        async def fake_http_get(url, params=None):
            return httpx.Response(
                200, json=nba_payload, request=httpx.Request("GET", url)
            )

        monkeypatch.setattr(service.client, "get", fake_http_get)
        assert await service._get("nba", "season-schedule") == nba_payload


# =============================================================================
# Still dark — the ingestion path sees exactly what it saw before
# =============================================================================

class TestStillDark:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sport", ["nba", "nhl"])
    async def test_get_fixtures_reads_the_same_endpoint_and_the_same_games(
        self, service, sport, monkeypatch, nba_payload, nhl_payload
    ):
        """`sync_statpal_schedules` calls get_fixtures(). Step 3 must be
        invisible to it: same URL, same count, same ids."""
        payload = nba_payload if sport == "nba" else nhl_payload
        seen = []

        async def fake_get(sport_, endpoint, params=None):
            seen.append((sport_, endpoint))
            return payload

        monkeypatch.setattr(service, "_get", fake_get)
        fixtures = await service.get_fixtures(sport)
        assert seen == [(sport, "season-schedule")]
        assert len(fixtures) == PINNED_GAMES
        assert [f.fixture_id for f in fixtures] == [
            m["id"] for m in payload["scores"]["tournament"]["match"]
        ]

    @pytest.mark.asyncio
    async def test_mlb_is_now_routed_here_and_reads_through_the_authority_door(
        self, service, monkeypatch
    ):
        """Step 5 opened this gate, and this test is the record of why.

        It asserted `"mlb" not in V1_SEASON_SCHEDULE_SPORTS` for two named
        reasons, and both were answered rather than waived:

          * *"the anchor is blank on 3 of 16 live rows"* — recovered by (both
            clubs, first pitch within ±1h, unique or refuse), which scores 13/13
            against the rows the anchor already resolves. It recovers 2 of the 3
            and refuses the third, taking coverage to 15/16 with the 16th
            declared. `recover_live_anchor` carries the sweep.
          * *"the (clubs, calendar day) fallback is keyed on the wrong day"* —
            that fallback was never adopted. It is not merely mis-keyed: on the
            one genuinely hard row it fuses the doubleheader's two games onto a
            single schedule row. The time-window rule replaced it outright.

        What the gate now guards is the DOOR, not the sport: MLB must arrive
        through `_parse_v1_season_schedule`, which raises on a vanished season
        and carries `league`, `season`, `tournament_id` and `stats_id`. Falling
        back to `get_fixtures` would return the games and silently drop all four,
        and turn a failed read into an empty schedule (gotcha #53).
        """
        assert "mlb" in StatPalAPIService.V1_SEASON_SCHEDULE_SPORTS

        seen = []

        async def fake_get(sport_, endpoint, params=None):
            seen.append((sport_, endpoint))
            return None

        monkeypatch.setattr(service, "_get", fake_get)
        # The authority door RAISES where `get_fixtures` shrugs into []. That is
        # the whole point of routing MLB here.
        with pytest.raises(StatPalUpstreamError):
            await service.get_schedule_fixtures("mlb")
        assert seen == [("mlb", "season-schedule")]
