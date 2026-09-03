"""
StatPal API client for schedules, rosters, injuries, and play-by-play data.

StatPal (statpal.io) provides structured sports data across 12+ sports and
1,000+ leagues with 5-15 second real-time latency. Key data types:
- Season schedules & fixtures (canonical "what is an event" source)
- Team rosters with player positions and jersey numbers
- Injury reports and player statuses
- Live scores and play-by-play
- Game start/end times (for market open/close windows)
- Team and player statistics

API versions:
- v1: NFL, NBA, MLB, NHL, PGA, Cricket, Esports, F1, etc.
- v2: Soccer only

Auth: access_key query parameter on every request.
Rate limits: up to 300k calls/day depending on plan.
Docs: https://statpal.io/quick-start-tutorial/
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.services.base_api import BaseAPIClient

logger = logging.getLogger(__name__)

# Base URLs (v1 for American sports, v2 for soccer)
STATPAL_V1_BASE = "https://statpal.io/api/v1"
STATPAL_V2_BASE = "https://statpal.io/api/v2"


class StatPalUpstreamError(RuntimeError):
    """StatPal did not answer, or answered with something that is not data.

    Raised only by the authority read path (`get_schedule_fixtures`). The
    ingestion path keeps returning `[]`, because a task that dies on a bad
    upstream day is worse than a task that skips a cycle.

    The authority path is the opposite: it exists to decide whether StatPal
    knows about a game. "StatPal has no games" and "we could not ask StatPal"
    are different answers and an empty list says both (gotcha #53).
    """


@dataclass
class StatPalFixture:
    """A scheduled or completed game from StatPal."""
    fixture_id: str
    home_team: str
    away_team: str
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "scheduled"  # scheduled, live, finished, postponed, cancelled
    raw_status: Optional[str] = None  # original status before normalization (e.g., "Q3", "1H", "HT")
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_q_scores: Optional[dict] = None  # {"q1": 24, "q2": 31, ...}
    away_q_scores: Optional[dict] = None
    venue: Optional[str] = None
    league: Optional[str] = None
    season: Optional[str] = None
    round_info: Optional[str] = None
    tournament_id: Optional[str] = None  # StatPal tournament id (tennis daily/livescores)
    # StatPal's SECOND id for the same game, served alongside "id" by the v1
    # season-schedule endpoints. It is not a synonym and it is not universal:
    # measured 2026-09-03, NHL fills it on 1404/1404 games and NBA on 0/1206.
    # Carried, never substituted — which of the two anchors a game is step 5's
    # question (the MLB three-id problem), and it cannot be answered by a
    # reader that throws one of them away.
    stats_id: Optional[str] = None


@dataclass
class StatPalPlayer:
    """A player from a StatPal team roster."""
    player_id: str
    name: str
    position: Optional[str] = None
    jersey_number: Optional[str] = None
    status: Optional[str] = None  # active, injured, suspended, etc.
    injury_type: Optional[str] = None
    injury_detail: Optional[str] = None


@dataclass
class StatPalInjury:
    """An injury report entry from StatPal."""
    player_id: str
    player_name: str
    team: str
    team_id: Optional[str] = None
    injury_type: str = ""
    status: str = ""  # out, doubtful, questionable, probable, day-to-day
    detail: Optional[str] = None
    reported_at: Optional[datetime] = None
    expected_return: Optional[str] = None


@dataclass
class StatPalPlayEvent:
    """A single play or event from play-by-play data."""
    play_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    period: Optional[str] = None  # Q1, 1st, Top 3rd, etc.
    clock: Optional[str] = None  # "4:32", "12:00"
    description: str = ""
    play_type: Optional[str] = None  # touchdown, field_goal, strikeout, etc.
    team: Optional[str] = None
    player: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


@dataclass
class StatPalTeam:
    """A team from StatPal."""
    team_id: str
    name: str
    short_name: Optional[str] = None
    abbreviation: Optional[str] = None
    logo_url: Optional[str] = None
    venue: Optional[str] = None
    league: Optional[str] = None


@dataclass
class StatPalGameDetail:
    """Detailed game info including start/end times and status."""
    fixture_id: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    home_team: str = ""
    away_team: str = ""
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    period: Optional[str] = None
    clock: Optional[str] = None
    venue: Optional[str] = None
    plays: list[StatPalPlayEvent] = field(default_factory=list)
    injuries: list[StatPalInjury] = field(default_factory=list)


def is_available() -> bool:
    """Check if StatPal API key is configured."""
    return bool(os.getenv("STATPAL_API_KEY"))


class StatPalAPIService(BaseAPIClient):
    """
    Client for the StatPal sports data API.

    Provides access to schedules, rosters, injuries, play-by-play, and
    live scores across NFL, NBA, MLB, NHL, soccer, and more.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("STATPAL_API_KEY", "")
        if not self.api_key:
            logger.warning("STATPAL_API_KEY not set — StatPal API calls will fail")
        super().__init__(
            timeout=20.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "BainLuck/1.0 (sports odds visualization)",
            },
        )

    def _base_url(self, sport: str) -> str:
        """Return the correct base URL for the sport (v2 for soccer, v1 for all else)."""
        if sport == "soccer":
            return STATPAL_V2_BASE
        return STATPAL_V1_BASE

    async def _get(self, sport: str, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make an authenticated GET request to the StatPal API.

        Args:
            sport: Sport identifier (nfl, nba, mlb, nhl, soccer, etc.)
            endpoint: Endpoint path after the sport (e.g., "fixtures", "teams/123/roster")
            params: Additional query parameters

        Returns:
            Parsed JSON response or None on error.
        """
        base = self._base_url(sport)
        url = f"{base}/{sport}/{endpoint}"

        request_params = {"access_key": self.api_key}
        if params:
            request_params.update(params)

        try:
            response = await self.client.get(url, params=request_params)

            if response.status_code == 401:
                logger.error("StatPal API: unauthorized — check STATPAL_API_KEY")
                return None
            if response.status_code == 429:
                logger.warning("StatPal API: rate limited (429)")
                return None
            if response.status_code != 200:
                logger.warning(f"StatPal API {sport}/{endpoint}: HTTP {response.status_code}")
                return None

            try:
                payload = response.json()
            except ValueError:
                # `invalid-request` is served as a bare unquoted body, so it
                # never reaches the JSON branch below.
                logger.error(
                    f"StatPal API {sport}/{endpoint}: HTTP 200 with a "
                    f"non-JSON body: {response.text[:120]!r}"
                )
                return None

            complaint = _error_body(payload)
            if complaint:
                # A 200 that carries a complaint instead of data. Measured
                # 2026-09-03: the vendor's spec documents a bare
                # `invalid-request` body, and its live 401/500 replies are
                # `{"error": "..."}`. Both must reach callers as a failure,
                # never as an empty section a parser reads as "no games".
                logger.error(
                    f"StatPal API {sport}/{endpoint}: HTTP 200 but the body is "
                    f"an error, not data: {complaint}"
                )
                return None
            return payload

        except httpx.TimeoutException:
            logger.warning(f"StatPal API timeout: {sport}/{endpoint}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"StatPal API error: {sport}/{endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"StatPal API unexpected error: {sport}/{endpoint}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Fixtures / Schedules
    # -------------------------------------------------------------------------

    # Correct endpoint names per the StatPal OpenAPI spec.
    # v1 sports (NBA/NFL/NHL/MLB) use "season-schedule".
    # Soccer v2 uses "matches/daily" with an offset param.
    # Golf/F1 use "schedule". Cricket uses "upcoming-schedule".
    # Tennis has NO season-schedule (that path 404s, measured 2026-09-03) — its
    # forward schedule is "daily/{day}", one call per day token (see
    # TENNIS_DAILY_OFFSETS). "{day}" in a value means the endpoint needs a day
    # token, which get_fixtures() cannot supply — get_schedule_fixtures() does.
    _SCHEDULE_ENDPOINTS: dict[str, str] = {
        "nba": "season-schedule",
        "nfl": "season-schedule",
        "nhl": "season-schedule",
        "mlb": "season-schedule",
        "soccer": "matches/daily",
        "golf": "schedule",
        "pga": "schedule",
        "f1": "schedule",
        "cricket": "upcoming-schedule",
        "tennis": "daily/{day}",
    }

    async def get_fixtures(
        self,
        sport: str,
        season: Optional[str] = None,
        date: Optional[str] = None,
        league_id: Optional[str] = None,
    ) -> list[StatPalFixture]:
        """Fetch scheduled and completed games.

        Args:
            sport: Sport identifier (nfl, nba, mlb, nhl, soccer)
            season: Season year/identifier (e.g., "2025", "2025-2026")
            date: Date filter (YYYY-MM-DD)
            league_id: League ID filter (for soccer with multiple leagues)

        Returns:
            List of StatPalFixture objects.
        """
        endpoint = self._SCHEDULE_ENDPOINTS.get(sport, "season-schedule")

        # Day-token endpoints (tennis) cannot be fetched without a day: this
        # method has no offset argument. Return empty rather than requesting a
        # literal "{day}" path — callers that want tennis schedules must use
        # get_schedule_fixtures(sport, day_offset=N).
        if "{day}" in endpoint:
            logger.debug(
                f"StatPal: {sport} schedule needs a day token — "
                f"use get_schedule_fixtures('{sport}', day_offset=N)"
            )
            return []

        params = {}
        if season:
            params["season"] = season
        if league_id:
            params["league"] = league_id

        # Soccer v2 uses "matches/daily" with an offset param (0 = today)
        if sport == "soccer" and endpoint == "matches/daily":
            # Fetch today (offset=0 is not supported, use offset=1 for tomorrow
            # and offset=-1 for yesterday). We'll fetch today's live scores
            # via get_live_scores() instead and fetch tomorrow's schedule here.
            params["offset"] = 1
            data = await self._get(sport, endpoint, params)
            results = self._parse_fixtures(data, sport) if data else []
            # Also fetch +2 days for upcoming
            params["offset"] = 2
            data2 = await self._get(sport, endpoint, params)
            if data2:
                results.extend(self._parse_fixtures(data2, sport))
            return results

        data = await self._get(sport, endpoint, params)
        if not data:
            return []

        return self._parse_fixtures(data, sport)

    async def get_live_scores(self, sport: str) -> list[StatPalFixture]:
        """Fetch live/in-progress games.

        Args:
            sport: Sport identifier

        Returns:
            List of currently live games as StatPalFixture objects.
        """
        data = await self._get(sport, "livescores")
        if not data:
            return []

        return self._parse_fixtures(data, sport)

    # -------------------------------------------------------------------------
    # Authority schedules (D50) — a DARK read path
    # -------------------------------------------------------------------------
    #
    # StatPal-as-canonical is built dark: this method exists so the authority
    # program can READ tennis and NFL schedules that get_fixtures() cannot see,
    # WITHOUT changing what the ingestion tasks receive. Nothing calls it yet.
    #
    # Why a separate method rather than fixing get_fixtures(): both sports are in
    # STATPAL_SPORT_MAPPING, so sync_statpal_schedules() already asks for them
    # every cycle and gets [] back (NFL because season-schedule nests its games
    # three levels deeper than the parser walks; tennis because season-schedule
    # 404s). Teaching the shared parser those two shapes would turn 374 NFL and
    # 68 tennis fixtures into event writes on the next beat — which is step 2 of
    # this program and needs its own review, not a side effect of step 1.
    #
    # NBA and NHL (step 3) joined for a different reason. The shared parser is
    # not blind to them — it reads all 1206 and 1404 games — so they are already
    # ingested and this changes nothing about that. They are here so that every
    # sport the authority program reasons about arrives through one door, with
    # the tournament wrapper (league, season, tournament id) and the second id
    # (`stats_id`) intact, and with a failed read raising instead of arriving as
    # an empty schedule.

    # /v1/tennis/daily/{token}: d-7…d-1 and d1…d7. There is no d0 — today's play
    # lives on livescores. The spec refreshes these every 12h, so a poller gains
    # nothing from a tighter cadence.
    TENNIS_DAILY_REFRESH_SECONDS = 12 * 3600
    TENNIS_DAILY_OFFSETS: tuple[int, ...] = tuple(
        [d for d in range(-7, 0)] + [d for d in range(1, 8)]
    )

    # Sports whose whole season arrives in one flat `scores.tournament.match`
    # array — the shape NFL is the exception to. Measured 2026-09-03:
    #   nba  1206 games, 03.10.2026 → 04.04.2027, season "2026/2027"
    #   nhl  1404 games, 19.09.2026 → 10.04.2027, season "2026/2027"
    # MLB is deliberately absent. It serves the same shape, but its ids do not
    # survive between endpoints (three id spaces, docs/statpal-capabilities.md
    # §2) and program step 5 says resolve that before reading it as authority.
    V1_SEASON_SCHEDULE_SPORTS: frozenset[str] = frozenset({"nba", "nhl"})

    async def get_schedule_fixtures(
        self,
        sport: str,
        day_offset: Optional[int] = None,
    ) -> list[StatPalFixture]:
        """Read a sport's forward schedule for the authority program (D50).

        Dark by construction: no caller writes from this yet.

        Args:
            sport: "tennis" or "nfl" (other sports fall through to get_fixtures).
            day_offset: Required for tennis — a day token in TENNIS_DAILY_OFFSETS
                (-7…-1, 1…7). Ignored by season-schedule sports.

        Returns:
            List of StatPalFixture objects. Empty means StatPal has no games —
            never that we failed to ask.

        Raises:
            ValueError: tennis called with a missing or out-of-range day_offset.
                That is a caller bug, not an upstream absence, and the two must
                not arrive as the same empty list.
            StatPalUpstreamError: StatPal did not answer, or answered with an
                error body. The ingestion path swallows this into `[]`; the
                authority path must not, because "no games" is the finding it
                exists to report and a swallowed failure forges it.
        """
        if sport == "tennis":
            if day_offset not in self.TENNIS_DAILY_OFFSETS:
                raise ValueError(
                    f"tennis day_offset must be one of {self.TENNIS_DAILY_OFFSETS} "
                    f"(there is no d0 — today's play is on livescores); got {day_offset!r}"
                )
            endpoint = f"daily/d{day_offset}"
            data = await self._get(sport, endpoint)
            self._require_answer(sport, endpoint, data)
            return self._parse_tennis_daily(data)

        if sport == "nfl":
            data = await self._get(sport, "season-schedule")
            self._require_answer(sport, "season-schedule", data)
            return self._parse_nfl_season_schedule(data)

        if sport in self.V1_SEASON_SCHEDULE_SPORTS:
            data = await self._get(sport, "season-schedule")
            self._require_answer(sport, "season-schedule", data)
            return self._parse_v1_season_schedule(data, sport)

        return await self.get_fixtures(sport)

    @staticmethod
    def _require_answer(sport: str, endpoint: str, data) -> None:
        """Turn `_get`'s None into a raise on the authority read path.

        `_get` returns None for every failure it knows about — timeout, 401,
        404, 429, 500, and a 200 whose body is an error. Every one of those
        reaching a caller as `[]` is gotcha #53: a response shape read as an
        absence.
        """
        if data is None:
            raise StatPalUpstreamError(
                f"StatPal {sport}/{endpoint} did not answer with data "
                f"(see the preceding StatPal API log line for the cause)"
            )

    def _parse_v1_season_schedule(self, data: dict, sport: str) -> list[StatPalFixture]:
        """Parse an NBA/NHL season-schedule payload for the authority program.

        Shape (measured 2026-09-03):
          {"scores": {"sport": "basketball", "tournament": {
              "country": "usa", "id": "2545", "league": "NBA",
              "season": "2026/2027",
              "match": [{"date": "03.10.2026", "time": "23:00",
                         "id": "1043639", "stats_id": "",
                         "status": "Not Started", "venue": "Scotiabank Arena",
                         "home": {...}, "away": {...}}]}}}

        The shared `_parse_fixtures` already reads the games out of this — NBA
        and NHL were never blind the way NFL and tennis were. What it throws
        away is everything OUTSIDE the match array, and the authority program
        needs all three of those things:

          - `league` and `season`, which name which competition and which year
            the fixture belongs to. `_extract_match_items` flattens the
            tournament wrapper away, so every fixture the ingestion path builds
            for NBA/NHL has league=None and season=None (verified against both
            live payloads).
          - `id`, the tournament id, the same field tennis carries.
          - `stats_id` on the match, StatPal's second id for the same game.

        And it raises where the shared parser shrugs. `time` is UTC on both
        sports (Toronto's 03.10.2026 opener reads 23:00, which is 7:00 PM ET);
        neither serves `datetime_utc`.
        """
        section = data.get("scores") if isinstance(data, dict) else None
        if not isinstance(section, dict):
            raise StatPalUpstreamError(
                f"StatPal {sport}/season-schedule: no 'scores' section in the response"
            )

        tournaments = section.get("tournament")
        if isinstance(tournaments, dict):
            tournaments = [tournaments]
        if not tournaments or not isinstance(tournaments, list):
            # HTTP 200, well-formed, and empty: `{"scores": {"sport":
            # "basketball"}}` is exactly what /nba/daily/d1 served on
            # 2026-09-03. For a DAY that is a legitimate "no games". For a
            # SEASON it is not an answer — 1206 games do not go quiet — so the
            # authority reader treats a vanished season as a failure to read,
            # not as a season that stopped existing.
            raise StatPalUpstreamError(
                f"StatPal {sport}/season-schedule: HTTP 200 with no tournament "
                f"section — an entire season is missing, which is a read "
                f"failure, not an empty schedule"
            )

        fixtures: list[StatPalFixture] = []
        for tournament in tournaments:
            if not isinstance(tournament, dict):
                continue
            league_name = tournament.get("league") or tournament.get("name")
            season = tournament.get("season")
            tournament_id = str(tournament.get("id", "")) or None

            for item in self._season_schedule_matches(tournament):
                try:
                    fixture = self._parse_single_fixture(item)
                except Exception as e:
                    logger.debug(f"StatPal: skipping {sport} match parse error: {e}")
                    continue
                if not fixture:
                    continue
                fixture.league = fixture.league or league_name
                fixture.season = fixture.season or season
                fixture.tournament_id = fixture.tournament_id or tournament_id
                fixture.stats_id = str(item.get("stats_id", "")) or None
                fixtures.append(fixture)

        return fixtures

    @staticmethod
    def _season_schedule_matches(tournament: dict) -> list:
        """Games in one tournament: the flat `match` array plus playoff `week`s.

        Same two places `_extract_match_items` looks, kept here so the authority
        reader does not depend on the ingestion extractor's traversal — the two
        answer different questions and must be free to diverge.
        """
        items: list = []
        matches = tournament.get("match", [])
        if isinstance(matches, dict):
            matches = [matches]
        if isinstance(matches, list):
            items.extend(m for m in matches if isinstance(m, dict))

        weeks = tournament.get("week", [])
        if isinstance(weeks, dict):
            weeks = [weeks]
        if isinstance(weeks, list):
            for week in weeks:
                if not isinstance(week, dict):
                    continue
                week_matches = week.get("match", [])
                if isinstance(week_matches, dict):
                    week_matches = [week_matches]
                if isinstance(week_matches, list):
                    items.extend(m for m in week_matches if isinstance(m, dict))

        return items

    def _parse_tennis_daily(self, data: dict) -> list[StatPalFixture]:
        """Parse a tennis daily/livescores payload into fixtures.

        Shape (measured 2026-09-03):
          {"scores": {"sport": "tennis", "tournament": [
              {"id": "13440", "name": "Atp - Singles: Us Open (Usa), Hard",
               "match": [{"id": "2631263", "date": "03.09.2026", "time": "23:00",
                          "status": "1", "player": [{...}, {...}]}]}]}}

        Note "tournament" is a LIST here (it is a dict for NBA/NHL/MLB), and the
        two sides are a two-element "player" array, not home/away objects — which
        is why the shared fixture parser returns nothing for tennis.
        """
        fixtures: list[StatPalFixture] = []
        if not isinstance(data, dict):
            return fixtures

        section = data.get("scores") or data.get("livescores")
        if not isinstance(section, dict):
            return fixtures

        tournaments = section.get("tournament", [])
        if isinstance(tournaments, dict):
            tournaments = [tournaments]
        if not isinstance(tournaments, list):
            return fixtures

        for tournament in tournaments:
            if not isinstance(tournament, dict):
                continue
            matches = tournament.get("match", [])
            if isinstance(matches, dict):
                matches = [matches]
            if not isinstance(matches, list):
                continue
            for item in matches:
                try:
                    fixture = self._parse_tennis_match(item, tournament)
                    if fixture:
                        fixtures.append(fixture)
                except Exception as e:
                    logger.debug(f"StatPal: skipping tennis match parse error: {e}")
                    continue

        return fixtures

    # Tennis daily codes a not-yet-played match as the digit "1"; every other
    # status it serves is a word ("Not Started", "Finished", "Set 3", "Retired",
    # "Cancelled"). Measured on d1/d-1/d-2 and livescores, 2026-09-03.
    _TENNIS_STATUS_CODES: dict[str, str] = {"1": "scheduled"}

    def _parse_tennis_match(self, item: dict, tournament: dict) -> Optional[StatPalFixture]:
        """Parse one tennis match. The first listed player is the 'home' side."""
        if not isinstance(item, dict):
            return None

        players = item.get("player", [])
        if not isinstance(players, list) or len(players) < 2:
            return None
        home, away = players[0], players[1]
        if not isinstance(home, dict) or not isinstance(away, dict):
            return None

        home_name = home.get("name", "")
        away_name = away.get("name", "")
        if not home_name or not away_name:
            return None

        raw_status = str(item.get("status", ""))
        status = self._TENNIS_STATUS_CODES.get(raw_status) or _normalize_status(raw_status)

        start_time = None
        date_str = item.get("date", "")
        time_str = item.get("time", "")
        if date_str and time_str:
            start_time = _parse_datetime(f"{date_str} {time_str}")
        if not start_time:
            start_time = _parse_datetime(date_str)

        return StatPalFixture(
            fixture_id=str(item.get("id", "")),
            home_team=home_name,
            away_team=away_name,
            home_team_id=str(home.get("id", "")) or None,
            away_team_id=str(away.get("id", "")) or None,
            start_time=start_time,
            status=status,
            raw_status=raw_status if status == "live" else None,
            home_score=_safe_int(home.get("totalscore")),
            away_score=_safe_int(away.get("totalscore")),
            home_q_scores=_tennis_set_scores(home),
            away_q_scores=_tennis_set_scores(away),
            league=tournament.get("name"),
            tournament_id=str(tournament.get("id", "")) or None,
        )

    def _parse_nfl_season_schedule(self, data: dict) -> list[StatPalFixture]:
        """Parse the NFL season-schedule payload into fixtures.

        Shape (measured 2026-09-03 — 374 games, Pre/Regular/Post season):
          {"scores": {"tournament": {"name": "USA: NFL", "stage": [
              {"id": "1501", "name": "Regular Season", "week": [
                  {"name": "Week 1", "matches": [
                      {"date": "Wednesday, September 9, 2026",
                       "match": {"contestid": "280445",
                                 "datetime_utc": "10.09.2026 00:20", ...}}]}]}]}}

        Three differences from NBA/NHL/MLB, all handled here:
          - games hang off stage → week → matches → match, two levels below where
            the shared extractor looks;
          - the day wrapper's "match" can be a dict (one game that day) or a list;
          - the game has NO "id" — its key is "contestid" (Week 1's 16 games were
            listed 6–11 days early as 280445–280460).
        """
        fixtures: list[StatPalFixture] = []
        if not isinstance(data, dict):
            return fixtures

        section = data.get("scores")
        if not isinstance(section, dict):
            return fixtures
        tournament = section.get("tournament")
        if not isinstance(tournament, dict):
            return fixtures

        league_name = tournament.get("name")
        stages = tournament.get("stage", [])
        if isinstance(stages, dict):
            stages = [stages]
        if not isinstance(stages, list):
            return fixtures

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            weeks = stage.get("week", [])
            if isinstance(weeks, dict):
                weeks = [weeks]
            if not isinstance(weeks, list):
                continue
            for week in weeks:
                if not isinstance(week, dict):
                    continue
                days = week.get("matches", [])
                if isinstance(days, dict):
                    days = [days]
                if not isinstance(days, list):
                    continue
                round_info = " / ".join(
                    part for part in (stage.get("name"), week.get("name")) if part
                ) or None
                for day in days:
                    if not isinstance(day, dict):
                        continue
                    games = day.get("match")
                    if isinstance(games, dict):
                        games = [games]
                    if not isinstance(games, list):
                        continue
                    for game in games:
                        try:
                            fixture = self._parse_single_fixture(game)
                        except Exception as e:
                            logger.debug(f"StatPal: skipping NFL match parse error: {e}")
                            continue
                        if not fixture:
                            continue
                        fixture.league = fixture.league or league_name
                        fixture.round_info = fixture.round_info or round_info
                        fixtures.append(fixture)

        return fixtures

    def _parse_fixtures(self, data: dict, sport: str) -> list[StatPalFixture]:
        """Parse fixture/livescore/season-schedule response into StatPalFixture objects.

        StatPal v1 season-schedule returns:
          {"scores": {"tournament": {"match": [...], "league": "NBA", "season": "2025/2026"}}}
        StatPal v1 livescores returns similar nested structure.
        Soccer v2 returns:
          {"matches_DD_MM_YYYY": {"league": [{"match": [...]}]}}
          or {"live_matches": {"league": [{"match": [...]}]}}
        """
        fixtures = []
        items = self._extract_match_items(data)

        for item in items:
            try:
                fixture = self._parse_single_fixture(item)
                if fixture:
                    fixtures.append(fixture)
            except Exception as e:
                logger.debug(f"StatPal: skipping fixture parse error: {e}")
                continue

        return fixtures

    @staticmethod
    def _extract_match_items(data) -> list:
        """Extract the list of match dicts from the various StatPal response formats."""
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return [data] if data else []

        # v1 season-schedule: {"scores": {"tournament": {"match": [...], "week": [...]}}}
        # v1 livescores:     {"livescores": {"tournament": {"match": [...]}}}
        # The "match" array has regular season games. The "week" array has
        # playoff/postseason games nested as: [{"stage": "Play Offs", "match": [...]}]
        for top_key in ("scores", "livescores"):
            section = data.get(top_key)
            if isinstance(section, dict):
                tournament = section.get("tournament")
                if isinstance(tournament, dict):
                    all_matches = []
                    # Regular season matches
                    matches = tournament.get("match", [])
                    if isinstance(matches, list):
                        all_matches.extend(matches)
                    # Playoff/postseason matches from "week" array
                    weeks = tournament.get("week", [])
                    if isinstance(weeks, list):
                        for week_entry in weeks:
                            if isinstance(week_entry, dict):
                                week_matches = week_entry.get("match", [])
                                if isinstance(week_matches, list):
                                    all_matches.extend(week_matches)
                                elif isinstance(week_matches, dict):
                                    all_matches.append(week_matches)
                    if all_matches:
                        return all_matches
                # Alternate: {"scores": {"match": [...]}}
                matches = section.get("match", [])
                if isinstance(matches, list) and matches:
                    return matches

        # Soccer v2 live: {"live_matches": {"league": [{"match": [...]}]}}
        # Soccer v2 daily: {"matches_DD_MM_YYYY": {"league": [{"match": [...]}]}}
        for key, val in data.items():
            if isinstance(val, dict) and "league" in val:
                all_matches = []
                for league_group in val.get("league", []):
                    if isinstance(league_group, dict):
                        league_matches = league_group.get("match", [])
                        if isinstance(league_matches, list):
                            all_matches.extend(league_matches)
                        elif isinstance(league_matches, dict):
                            all_matches.append(league_matches)
                if all_matches:
                    return all_matches

        # Golf/F1: {"fixtures": {"tournament": [...]}}
        fixtures_section = data.get("fixtures")
        if isinstance(fixtures_section, dict):
            tournaments = fixtures_section.get("tournament", [])
            if isinstance(tournaments, list):
                return tournaments

        # Fallback: try "data" wrapper or treat as list
        items = data.get("data", data)
        if isinstance(items, list):
            return items
        if isinstance(items, dict) and items:
            return [items]

        return []

    def _parse_single_fixture(self, item: dict) -> Optional[StatPalFixture]:
        """Parse a single fixture/match from the API response.

        StatPal v1 match format:
          {"id": "988739", "date": "11.10.2025", "time": "00:00",
           "status": "Finished", "venue": "Frost Bank Center",
           "home": {"id": "2689", "name": "San Antonio Spurs", "totalscore": "134", ...},
           "away": {"id": "2679", "name": "Utah Jazz", "totalscore": "130", ...}}
        """
        if not isinstance(item, dict):
            return None

        # Extract team info
        home_team = ""
        away_team = ""
        home_team_id = None
        away_team_id = None
        home_score = None
        away_score = None

        # StatPal format: "home" and "away" are direct objects with name, id, totalscore
        home = item.get("home", {})
        away = item.get("away", {})
        if isinstance(home, dict):
            home_team = home.get("name", "")
            home_team_id = str(home.get("id", "")) or None
            home_score = _safe_int(home.get("totalscore"))
        if isinstance(away, dict):
            away_team = away.get("name", "")
            away_team_id = str(away.get("id", "")) or None
            away_score = _safe_int(away.get("totalscore"))

        # Fallback: nested "teams" object (other API formats)
        if not home_team:
            teams = item.get("teams", {})
            if isinstance(teams, dict):
                h = teams.get("home", {})
                a = teams.get("away", {})
                if isinstance(h, dict):
                    home_team = h.get("name", "")
                    home_team_id = home_team_id or (str(h.get("id", "")) or None)
                if isinstance(a, dict):
                    away_team = a.get("name", "")
                    away_team_id = away_team_id or (str(a.get("id", "")) or None)

        # Fallback: flat fields
        if not home_team:
            home_team = item.get("home_team", item.get("home_name", ""))
        if not away_team:
            away_team = item.get("away_team", item.get("away_name", ""))

        if not home_team or not away_team:
            return None

        # Parse scores — fallback to nested "scores" dict or flat fields
        if home_score is None:
            scores = item.get("scores", item.get("score"))
            if isinstance(scores, dict) and scores:
                home_score = _safe_int(scores.get("home", scores.get("home_score")))
                away_score = _safe_int(scores.get("away", scores.get("away_score")))
        if home_score is None and item.get("home_score") is not None:
            home_score = _safe_int(item.get("home_score"))
        if away_score is None and item.get("away_score") is not None:
            away_score = _safe_int(item.get("away_score"))

        # Parse start time — StatPal uses "date" (DD.MM.YYYY) + "time" (HH:MM).
        # NFL is the exception: its "date" is prose ("Wednesday, September 9,
        # 2026") and its "time" is venue-local ("7:20 PM"), so neither parses and
        # the two together would be an hours-wrong answer if they did. It ships
        # "datetime_utc" (DD.MM.YYYY HH:MM, UTC) instead — prefer it wherever it
        # appears. NBA/NHL/MLB/soccer carry no such field (measured 2026-09-03),
        # so this changes nothing for them.
        date_str = item.get("date", "")
        time_str = item.get("time", "")
        start_time = _parse_datetime(item.get("datetime_utc"))
        if not start_time and date_str and time_str:
            start_time = _parse_datetime(f"{date_str} {time_str}")
        if not start_time:
            start_time = _parse_datetime(
                date_str or item.get("start_time", item.get("datetime"))
            )

        # Parse end time (if available — typically only for finished games)
        end_time = _parse_datetime(item.get("end_time"))

        # Parse status — preserve raw for period/clock extraction
        status_raw_str = item.get("status", "")
        if isinstance(status_raw_str, dict):
            status_raw_str = status_raw_str.get("long", status_raw_str.get("short", ""))
        status_raw_str = str(status_raw_str)
        status = _normalize_status(status_raw_str)

        # Parse quarter/period scores (e.g., q1, q2, q3, q4, ot)
        home_q_scores = None
        away_q_scores = None
        home_data = item.get("home", {})
        away_data = item.get("away", {})
        if isinstance(home_data, dict):
            qs = {}
            for qk in ("q1", "q2", "q3", "q4", "ot"):
                val = _safe_int(home_data.get(qk))
                if val is not None:
                    qs[qk] = val
            if qs:
                home_q_scores = qs
        if isinstance(away_data, dict):
            qs = {}
            for qk in ("q1", "q2", "q3", "q4", "ot"):
                val = _safe_int(away_data.get(qk))
                if val is not None:
                    qs[qk] = val
            if qs:
                away_q_scores = qs

        # NFL games have no "id" at all — the key is "contestid" (374/374 games,
        # measured 2026-09-03). A blank fixture_id is not an absence, it is an
        # unusable linkage: 8,272 rows once carried '' for exactly this reason
        # (backend/scripts/repair_statpal_fixture_id_blanks.py).
        fixture_id = str(
            item.get("id") or item.get("contestid") or item.get("fixture_id") or ""
        )

        # Venue — can be a string or a dict
        venue = item.get("venue")
        if isinstance(venue, dict):
            venue = venue.get("name", "")

        return StatPalFixture(
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
            raw_status=status_raw_str if status == "live" else None,
            home_score=home_score,
            away_score=away_score,
            home_q_scores=home_q_scores,
            away_q_scores=away_q_scores,
            venue=venue,
            league=item.get("league", {}).get("name") if isinstance(item.get("league"), dict) else item.get("league"),
            season=str(item.get("season", "")) or None,
            round_info=item.get("round", item.get("week")),
        )

    # -------------------------------------------------------------------------
    # Teams
    # -------------------------------------------------------------------------

    async def get_teams(self, sport: str, league_id: Optional[str] = None) -> list[StatPalTeam]:
        """Fetch all teams for a sport/league.

        Args:
            sport: Sport identifier
            league_id: Optional league filter

        Returns:
            List of StatPalTeam objects.
        """
        params = {}
        if league_id:
            params["league"] = league_id

        data = await self._get(sport, "teams", params)
        if not data:
            return []

        teams = []
        items = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                teams.append(StatPalTeam(
                    team_id=str(item.get("id", "")),
                    name=item.get("name", ""),
                    short_name=item.get("short_name"),
                    abbreviation=item.get("abbreviation", item.get("code")),
                    logo_url=item.get("logo"),
                    venue=item.get("venue", {}).get("name") if isinstance(item.get("venue"), dict) else None,
                    league=item.get("league", {}).get("name") if isinstance(item.get("league"), dict) else None,
                ))
            except Exception as e:
                logger.debug(f"StatPal: skipping team parse error: {e}")
                continue

        return teams

    # -------------------------------------------------------------------------
    # Rosters
    # -------------------------------------------------------------------------

    async def get_roster(self, sport: str, team_id: str) -> list[StatPalPlayer]:
        """Fetch the roster for a specific team.

        Args:
            sport: Sport identifier
            team_id: StatPal team ID

        Returns:
            List of StatPalPlayer objects with positions and jersey numbers.
        """
        data = await self._get(sport, f"teams/{team_id}/roster")
        if not data:
            return []

        players = []
        items = data.get("data", data.get("players", data))
        if isinstance(items, dict):
            items = items.get("players", [])
        if not isinstance(items, list):
            return []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                name = item.get("name", item.get("player_name", ""))
                if not name:
                    # Some responses nest the player info
                    player_obj = item.get("player", {})
                    if isinstance(player_obj, dict):
                        name = player_obj.get("name", "")

                if not name:
                    continue

                players.append(StatPalPlayer(
                    player_id=str(item.get("id", item.get("player_id", ""))),
                    name=name,
                    position=item.get("position", item.get("pos")),
                    jersey_number=str(item.get("number", item.get("jersey", ""))) or None,
                    status=item.get("status"),
                    injury_type=item.get("injury_type"),
                    injury_detail=item.get("injury_detail"),
                ))
            except Exception as e:
                logger.debug(f"StatPal: skipping player parse error: {e}")
                continue

        return players

    # -------------------------------------------------------------------------
    # Injuries
    # -------------------------------------------------------------------------

    async def get_injuries(self, sport: str) -> list[StatPalInjury]:
        """Fetch current injury reports for a sport.

        Args:
            sport: Sport identifier

        Returns:
            List of StatPalInjury objects with player status and details.
        """
        data = await self._get(sport, "injuries")
        if not data:
            return []

        injuries = []
        items = data.get("data", data.get("injuries", data))
        if not isinstance(items, list):
            return []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                player_name = item.get("player_name", item.get("player", {}).get("name", ""))
                if not player_name and isinstance(item.get("player"), dict):
                    player_name = item["player"].get("name", "")

                team_name = item.get("team", item.get("team_name", ""))
                if isinstance(team_name, dict):
                    team_name = team_name.get("name", "")

                if not player_name:
                    continue

                injuries.append(StatPalInjury(
                    player_id=str(item.get("player_id", item.get("player", {}).get("id", ""))),
                    player_name=player_name,
                    team=team_name,
                    team_id=str(item.get("team_id", "")) or None,
                    injury_type=item.get("type", item.get("injury_type", "")),
                    status=item.get("status", ""),
                    detail=item.get("detail", item.get("description")),
                    reported_at=_parse_datetime(item.get("reported_at", item.get("date"))),
                    expected_return=item.get("expected_return"),
                ))
            except Exception as e:
                logger.debug(f"StatPal: skipping injury parse error: {e}")
                continue

        return injuries

    # -------------------------------------------------------------------------
    # Play-by-Play
    # -------------------------------------------------------------------------

    async def get_play_by_play(self, sport: str, fixture_id: str) -> list[StatPalPlayEvent]:
        """Fetch play-by-play data for a specific game.

        Args:
            sport: Sport identifier
            fixture_id: StatPal fixture/game ID

        Returns:
            List of StatPalPlayEvent objects in chronological order.
        """
        data = await self._get(sport, f"fixtures/{fixture_id}/playbyplay")
        if not data:
            return []

        plays = []
        items = data.get("data", data.get("plays", data.get("events", data)))
        if not isinstance(items, list):
            return []

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                plays.append(StatPalPlayEvent(
                    play_id=str(item.get("id", item.get("play_id", ""))) or None,
                    timestamp=_parse_datetime(item.get("timestamp", item.get("time"))),
                    period=item.get("period", item.get("quarter", item.get("inning"))),
                    clock=item.get("clock", item.get("game_clock")),
                    description=item.get("description", item.get("text", "")),
                    play_type=item.get("type", item.get("play_type")),
                    team=item.get("team", {}).get("name") if isinstance(item.get("team"), dict) else item.get("team"),
                    player=item.get("player", {}).get("name") if isinstance(item.get("player"), dict) else item.get("player_name"),
                    home_score=_safe_int(item.get("home_score")),
                    away_score=_safe_int(item.get("away_score")),
                ))
            except Exception as e:
                logger.debug(f"StatPal: skipping play parse error: {e}")
                continue

        return plays

    # -------------------------------------------------------------------------
    # Game Detail (combines fixture info + plays + injuries)
    # -------------------------------------------------------------------------

    async def get_game_detail(self, sport: str, fixture_id: str) -> Optional[StatPalGameDetail]:
        """Fetch comprehensive game detail including status, times, plays, and injuries.

        This is the primary method for determining game start/end times and
        understanding what happened during a game.

        Args:
            sport: Sport identifier
            fixture_id: StatPal fixture/game ID

        Returns:
            StatPalGameDetail with full game context, or None on error.
        """
        data = await self._get(sport, f"fixtures/{fixture_id}")
        if not data:
            return None

        item = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(item, list):
            item = item[0] if item else {}
        if not isinstance(item, dict):
            return None

        fixture = self._parse_single_fixture(item)
        if not fixture:
            return None

        # Fetch play-by-play and injuries in parallel for live/finished games
        plays = []
        injuries = []
        if fixture.status in ("live", "finished"):
            plays = await self.get_play_by_play(sport, fixture_id)

        detail = StatPalGameDetail(
            fixture_id=fixture.fixture_id,
            status=fixture.status,
            start_time=fixture.start_time,
            end_time=fixture.end_time,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            home_score=fixture.home_score,
            away_score=fixture.away_score,
            venue=fixture.venue,
            plays=plays,
            injuries=injuries,
        )

        # Try to extract period/clock from status or latest play
        if plays:
            latest = plays[-1]
            detail.period = latest.period
            detail.clock = latest.clock

        return detail

    # -------------------------------------------------------------------------
    # Standings
    # -------------------------------------------------------------------------

    async def get_standings(self, sport: str, season: Optional[str] = None) -> Optional[dict]:
        """Fetch league standings.

        Args:
            sport: Sport identifier
            season: Season year (optional)

        Returns:
            Raw standings data dict, or None on error.
        """
        params = {}
        if season:
            params["season"] = season

        return await self._get(sport, "standings", params)

    # -------------------------------------------------------------------------
    # Player / Team Stats
    # -------------------------------------------------------------------------

    async def get_team_stats(self, sport: str, team_id: str, season: Optional[str] = None) -> Optional[dict]:
        """Fetch team statistics.

        Args:
            sport: Sport identifier
            team_id: StatPal team ID
            season: Season year (optional)

        Returns:
            Raw team stats dict, or None on error.
        """
        params = {}
        if season:
            params["season"] = season

        return await self._get(sport, f"teams/{team_id}/stats", params)

    async def get_player_stats(self, sport: str, player_id: str, season: Optional[str] = None) -> Optional[dict]:
        """Fetch individual player statistics.

        Args:
            sport: Sport identifier
            player_id: StatPal player ID
            season: Season year (optional)

        Returns:
            Raw player stats dict, or None on error.
        """
        params = {}
        if season:
            params["season"] = season

        return await self._get(sport, f"players/{player_id}/stats", params)


# =============================================================================
# Helper functions
# =============================================================================

def _safe_int(val) -> Optional[int]:
    """Safely convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# The vendor's documented way of saying "that call was malformed", served as
# the whole body with HTTP 200 (docs/statpal-capabilities.md §1). Twelve probes
# on 2026-09-03 could not make it appear — the live API answered 404, 401 or
# 500 instead — so this is guarded on the vendor's word, not on a reproduction.
_INVALID_REQUEST_BODY = "invalid-request"


def _error_body(payload) -> Optional[str]:
    """Return a complaint string if a 200 body is an error, else None.

    Two shapes, both measured or documented on 2026-09-03:
      - the bare string `invalid-request` (spec; not reproduced live)
      - `{"error": "Invalid access key or sport. ..."}` (live, 401 and 500)

    An empty section such as `{"scores": {"sport": "basketball"}}` is NOT an
    error here — the endpoint answered, it simply has nothing for that day.
    Telling those apart is the schedule parser's job, not the transport's.
    """
    if isinstance(payload, str):
        return payload if _INVALID_REQUEST_BODY in payload.lower() else None
    if isinstance(payload, dict):
        err = payload.get("error")
        if err:
            return str(err)
    return None


def _tennis_set_scores(player: dict) -> Optional[dict]:
    """Per-set games for one tennis player: {"s1": 6, "s2": 4, ...}.

    Unplayed sets come back as "" and are omitted, so a scheduled match yields
    None rather than a dict of nothing.
    """
    sets = {}
    for key in ("s1", "s2", "s3", "s4", "s5"):
        val = _safe_int(player.get(key))
        if val is not None:
            sets[key] = val
    return sets or None


def _parse_datetime(val) -> Optional[datetime]:
    """Parse a datetime string from the API, returning None on failure."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val

    val = str(val).strip()
    # Try ISO 8601 and common formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",       # StatPal: "27.02.2026 19:30"
        "%d.%m.%Y",              # StatPal: "27.02.2026"
    ):
        try:
            dt = datetime.strptime(val, fmt)
            # Ensure timezone-aware (assume UTC if naive)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    logger.debug(f"StatPal: could not parse datetime: {val!r}")
    return None


def _normalize_status(status: str) -> str:
    """Normalize game status strings to our standard statuses."""
    s = status.lower().strip()

    # Map to our status vocabulary
    if s in ("scheduled", "not started", "ns", "tbd", "time tbd"):
        return "scheduled"
    if s in ("live", "in progress", "1h", "2h", "ht", "et", "p", "bt",
             "q1", "q2", "q3", "q4", "ot",
             "s1", "s2", "s3", "s4", "s5", "set 1", "set 2", "set 3", "set 4", "set 5",
             "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th",
             "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10", "r11", "r12",
             "round 1", "round 2", "round 3", "round 4", "round 5", "round 6",
             "round 7", "round 8", "round 9", "round 10", "round 11", "round 12",
             "1st innings", "2nd innings", "3rd innings", "4th innings"):
        return "live"
    # "retired" and "walkover" are tennis's other two ways of saying the match is
    # over and has a winner — a settled result, not an abandonment.
    if s in ("finished", "final", "ft", "aet", "pen", "completed", "game over",
             "after over time", "after overtime", "after extra time",
             "retired", "ret", "walkover", "w.o.", "wo"):
        return "finished"
    if s in ("postponed", "pst", "delayed"):
        return "postponed"
    if s in ("cancelled", "canc", "abandoned", "abn"):
        return "cancelled"
    # "pause" is esports' word for it and the only explicit interrupted state
    # StatPal served on any sport on 2026-09-03 (ARTIFACT-M-20260903-B).
    if s in ("suspended", "susp", "int", "interrupted", "pause", "paused"):
        return "suspended"

    # Default: pass through
    return s


async def get_statpal_request_count(api_key: Optional[str] = None) -> dict | None:
    """Fetch current daily request count from StatPal Usage Monitoring endpoint.

    This endpoint does NOT count toward the daily quota.
    Returns {"access_key": "...", "current_date": "YYYY-MM-DD", "request_count": N}
    or None on failure.
    """
    key = api_key or os.getenv("STATPAL_API_KEY", "")
    if not key:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://statpal.io/api/user-request-count",
                params={"access_key": key},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "current_date": data.get("current_date"),
                "request_count": data.get("request_count", 0),
            }
        except Exception as e:
            logger.warning(f"StatPal request count fetch failed: {e}")
            return None


def get_statpal_service(api_key: Optional[str] = None) -> StatPalAPIService:
    """Factory function to create a StatPal API service instance."""
    return StatPalAPIService(api_key=api_key)
