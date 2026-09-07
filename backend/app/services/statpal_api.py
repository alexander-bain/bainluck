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

The version is a property of the SPORT, but the endpoint NAME is not: on v2 the
soccer paths are `matches/daily`, `matches/live` and `injuries-suspensions`
where v1 calls the same products `season-schedule`, `livescores` and `injuries`.
Ask through `LIVE_SCORE_ENDPOINTS` / `INJURY_ENDPOINTS` / `_SCHEDULE_ENDPOINTS`
rather than hard-coding a v1 name; a v1 name on v2 is a 404, and a 404 arrives
as an empty list that reads exactly like "nothing is being played" (#3366).

Auth: access_key query parameter on every request.
Rate limits: up to 300k calls/day depending on plan.
Docs: https://statpal.io/quick-start-tutorial/
"""

import logging
import os
import re
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
    # StatPal's THIRD id, served only by `livescores`, and — despite a name that
    # reads like an odds-provider key — it is the `season-schedule` `id` for the
    # same contest. Measured 2026-09-04 over the full MLB census: 13 of 16 live
    # rows carry it and 13/13 dereference to a schedule row.
    #
    # It exists as its own field because on MLB `livescores`, `id` is a FOURTH
    # number in a space `season-schedule` never publishes: 0 of our 222 stored
    # MLB column values dereference to `stats_id`, and 85 dereference to nothing
    # at all. The two look alike — both ten digits, both `1329…`, overlapping
    # ranges — and share not one value, which is precisely why the anchor is
    # named rather than inferred (D55).
    odds_id: Optional[str] = None


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
    # The OTHER side of the fixture this player's team is playing, and the
    # fixture's own ids. Carried so a caller can attach an injury to an event by
    # matching BOTH teams instead of one — a one-sided name match hangs another
    # club's player on the wrong game. Ids are carried, never substituted (D55):
    # `main_id` and the three fallbacks are four distinct id spaces, and which
    # one anchors our soccer events is not yet answered (#2907).
    opponent: str = ""
    opponent_id: Optional[str] = None
    is_home: Optional[bool] = None
    fixture_main_id: Optional[str] = None
    fixture_fallback_ids: tuple[str, ...] = ()
    #: The fixture's own date. Deliberately NOT written to `reported_at`: the
    #: payload carries no per-injury report time, and the day a match is played
    #: is not the day a player got hurt. An invented `reported_at` would read as
    #: freshness we do not have.
    fixture_date: Optional[datetime] = None


#: Availability, read off the BUCKET the vendor files a player under — never
#: off its `status` field, which carries the REASON ("Knee Injury", "Red Card",
#: "Coach's decision"; 49 distinct strings over the 1,004 players served at
#: 2026-09-06 01:47Z). `routes/events.py` keeps only `("Out", "Doubtful")` on a
#: completed game, so writing the vendor's word into our `status` would empty
#: every completed-game injury list while looking like data.
INJURY_BUCKET_STATUS: dict[str, str] = {
    "to_miss": "Out",
    "questionable": "Questionable",
}

#: StatPal sport -> the endpoint that serves injuries for it. Soccer is the
#: whole map, and that is a measured fact about the venue, not a gap in ours.
#:
#: Established two ways on 2026-09-06 (#2907, notice 26a), because an absence
#: needs a second signal (gotcha #53):
#:  1. The venue's own compiled spec (`statpal.io/static/openapi/openapi-compiled.yaml`,
#:     v2.0.0, read 01:44Z) publishes 53 sport paths. Injuries appear twice, both
#:     soccer: `/soccer/injuries-suspensions` (v2) and `/soccer/injuries`
#:     (v1, tagged "Legacy"). No roster or team path exists for any sport.
#:  2. A 32-cell live probe — {nba, nfl, nhl, mlb} x {teams, injuries,
#:     injuries-suspensions, rosters, roster, players, squads, team-list} on v1 —
#:     returned 404 on all 32, while `season-schedule` answered 200 from the same
#:     shell seconds apart. Path-level, not egress and not entitlement (notice 7).
#:
#: The endpoint is version-sensitive and the versions are CROSSED: on v2 the name
#: is `injuries-suspensions` and `injuries` 404s; on v1 it is the other way round.
#: `_base_url` sends soccer to v2, so v2's name is the one that belongs here.
#: Both served the same `updated` stamp at 01:47Z; v2 carries the richer id set.
INJURY_ENDPOINTS: dict[str, str] = {
    "soccer": "injuries-suspensions",
}

#: StatPal sport -> the endpoint that serves live scores for it, where the name
#: is NOT the default `livescores`. Same shape of fact as `INJURY_ENDPOINTS`
#: above, discovered the same way and for the same reason.
#:
#: #3366 filed this as a VERSION defect — "the client routes soccer to v2, but
#: `livescores` only exists on v1" — and the version table it measured is real
#: and still true (re-probed with the production key 2026-09-07 04:22Z):
#:
#:     GET /api/v1/soccer/livescores          200  150,595 B
#:     GET /api/v2/soccer/livescores          404      179 B
#:     GET /api/v1/soccer/matches/daily       404      179 B
#:     GET /api/v2/soccer/matches/daily       200  161,653 B
#:
#: But crossing the versions is the WRONG REPAIR, and the working sibling in
#: this very file says why: on v2 the injury path is not `injuries` either, it
#: is `injuries-suspensions`. Soccer's live board is the same story. The
#: vendor's compiled spec (`statpal.io/static/openapi/openapi-compiled.yaml`,
#: read 04:24Z, 16 soccer paths) publishes `/soccer/matches/live` beside
#: `/soccer/matches/daily`, and it answers on v2 and only on v2:
#:
#:     GET /api/v1/soccer/matches/live        404      179 B
#:     GET /api/v2/soccer/matches/live        200  188,954 B
#:
#: The two boards are the same 195 games one minute apart, so nothing is lost by
#: staying on v2 — and three things are gained. Soccer keeps ONE base URL, so
#: the version stays a property of the sport and `_base_url` does not have to
#: become a per-endpoint table. The envelope is `live_matches -> league[] ->
#: match[]`, which `_extract_match_items` was already written for. And the ids
#: are v2's `main_id` + `fallback_id_1..3` — the SAME four id spaces, under the
#: same names, that `StatPalInjury` already carries. v1's board serves those
#: four as `id` / `alternate_id` / `alternate_id_2` / `static_id`: a fifth
#: vocabulary for an id set we can already name, on the endpoint the vendor's
#: own spec files under "Legacy".
LIVE_SCORE_ENDPOINTS: dict[str, str] = {
    "soccer": "matches/live",
}

#: Sports whose live board the INGESTION path does not read, even though the
#: venue serves one. Not a gap — a fence, and it holds today's behaviour still.
#:
#: `sync_statpal_schedules` calls `get_live_scores(sport)` once per OUR sport
#: key and keys the rows to events by team pair; seven of the fourteen keys in
#: `STATPAL_SPORT_MAPPING` are soccer. Today every one of those calls 404s and
#: returns `[]`, so pointing them at `matches/live` would hand that writer 195
#: rows across 113 leagues on the next beat — a live-ingestion change over the
#: widest team-name space we have, arriving as a side effect of a routing fix.
#:
#: And they would arrive WRONG, which is measured, not feared. Replaying the
#: real `_parse_fixtures` over the real 04:25Z payload:
#:   * soccer scores live under `home.goals`, not `home.totalscore`, so all 195
#:     rows parse with `home_score is None`;
#:   * an unplayed match carries its KICKOFF CLOCK in `status` (`"22:00"`,
#:     equal to its own `time` field on 172 of 172 such rows), which
#:     `_normalize_status` passes through verbatim — so the shared parser would
#:     report a game whose status is a wall clock.
#: The authority door (`get_live_fixtures`) reads both correctly through
#: `_parse_soccer_live_matches`. Teaching the LIVE WRITER soccer is #3348's
#: change and gets its own review; this constant is where that decision is
#: recorded rather than implied by a 404.
LIVESCORES_INGESTION_DARK_SPORTS: frozenset[str] = frozenset({"soccer"})


@dataclass
class StatPalInjuryFetch:
    """What one injury fetch proves, not just what it returned.

    `[]` is the same object for "the venue has no injury product for this
    sport", "we asked and it broke" and "nobody is hurt today" (gotcha #53).
    Those are three different operational facts and the middle one is an alarm,
    so the reason travels with the list.
    """

    injuries: list[StatPalInjury]
    #: One of `ok`, `no_venue_path`, `fetch_failed`, `empty`.
    reason: str
    sport: str
    #: The path actually asked, or None when nothing was asked.
    endpoint: Optional[str] = None

    @property
    def asked(self) -> bool:
        return self.reason != "no_venue_path"

    @property
    def is_alarm(self) -> bool:
        """A supported sport we could not read. `empty` is not an alarm."""
        return self.reason == "fetch_failed"


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
        """Fetch live/in-progress games — the INGESTION door.

        Args:
            sport: Sport identifier

        Returns:
            List of currently live games as StatPalFixture objects. `[]` for a
            sport in `LIVESCORES_INGESTION_DARK_SPORTS`, by decision rather than
            by a 404 — read that constant for which sports and why.
        """
        if sport in LIVESCORES_INGESTION_DARK_SPORTS:
            # Says out loud, once per call, what a 404 used to say by accident.
            # The authority door reads this sport; the live writer does not.
            logger.info(
                "StatPal %s: live board not read on the ingestion path "
                "(LIVESCORES_INGESTION_DARK_SPORTS) — the authority door "
                "`get_live_fixtures` reads it; teaching the live writer this "
                "sport is #3348's change, not a routing side effect",
                sport,
            )
            return []

        data = await self._get(sport, self._live_endpoint(sport))
        if not data:
            return []

        return self._parse_fixtures(data, sport)

    @staticmethod
    def _live_endpoint(sport: str) -> str:
        """The live-board path for a sport. `livescores` unless measured otherwise."""
        return LIVE_SCORE_ENDPOINTS.get(sport, "livescores")

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

    # Sports served as one flat `scores.tournament.match` array — the shape NFL
    # is the exception to. Measured 2026-09-03, and MLB 2026-09-04:
    #   nba  1206 games, 03.10.2026 → 04.04.2027, season "2026/2027"
    #   nhl  1404 games, 19.09.2026 → 10.04.2027, season "2026/2027"
    #   mlb   227 games in a ~17-day ROLLING window, 2026-08-29 → 2026-09-15
    #
    # MLB joined on 2026-09-04 (step 5) once its ids were resolved rather than
    # assumed. The old exclusion said they "do not survive between endpoints";
    # measured, they do — `livescores.oddsid` IS `season-schedule.id` on 13/16
    # live rows, 13/13 dereferencing. See `StatPalFixture.odds_id`.
    #
    # Note what MLB does NOT share with the other two: its schedule is a rolling
    # window, not a season. NBA and NHL publish 1206 and 1404 games on day one
    # and the set does not move; MLB's 227 are the fortnight either side of
    # today. Any denominator taken from this endpoint is a window, and it is a
    # different window tomorrow.
    V1_SEASON_SCHEDULE_SPORTS: frozenset[str] = frozenset({"nba", "nhl", "mlb"})

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

    async def get_live_fixtures(self, sport: str) -> list[StatPalFixture]:
        """`livescores` through the authority door — the half `daily` cannot serve.

        `get_schedule_fixtures("tennis", …)` reaches d-7…d-1 and d1…d7 and there
        is **no d0**: it answers HTTP 500, so today's order of play is
        unobtainable from `daily` (ARTIFACT-AUTHORITY-20260903-TENNIS §1a). Only
        `livescores` knows a match on the day it is played, and today's play is
        exactly what D59's live score line is about.

        Why not fix `get_live_scores` instead: tennis's `tournament` is a LIST
        where every other sport serves a dict, so `_parse_fixtures` returns `[]`
        and tennis livescores has always been dark. Teaching the SHARED parser
        that shape would not add a reader — it would hand 57 tennis fixtures to
        `sync_statpal_live_scores`, which iterates `STATPAL_SPORT_MAPPING` and
        writes what it gets, on the next beat. That is a live-ingestion change
        with its own review, not a side effect of building a linker; the same
        argument that gave `get_schedule_fixtures` its own door applies here
        unchanged.

        **Soccer joined on 2026-09-07 (#3366), and it is half this door's job.**
        `STATPAL_SPORT_MAPPING` has fourteen keys and SEVEN of them are soccer,
        so `espn_sync._read_statpal_standby` — the only caller that asks whether
        the standby could carry a sport ESPN went dark on — read a
        `StatPalUpstreamError` for half its map on every pass, and the live half
        of soccer's readiness could never be anything but DARK. It was not an
        outage: the live board is `matches/live`, not `livescores`
        (`LIVE_SCORE_ENDPOINTS`), and this door reads it through
        `_parse_soccer_live_matches`. The INGESTION door stays dark for soccer
        on purpose (`LIVESCORES_INGESTION_DARK_SPORTS`).

        Raises:
            StatPalUpstreamError: the read failed. "No games are live" and "we
                could not ask" must not arrive as the same empty list (gotcha
                #53) — a linker that treats a 500 as an empty slate reports a
                clean run in which nothing was linked.
        """
        endpoint = self._live_endpoint(sport)
        data = await self._get(sport, endpoint)
        self._require_answer(sport, endpoint, data)
        if sport == "tennis":
            return self._parse_tennis_daily(data)
        if sport == "soccer":
            return self._parse_soccer_live_matches(data)
        return self._parse_fixtures(data, sport)

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

    #: A soccer live status that is a wall clock is the KICKOFF TIME, not a
    #: period. Measured over the whole 04:25Z board: 172 of 195 rows carry one,
    #: and on 172 of 172 it is character-for-character the row's own `time`.
    _SOCCER_KICKOFF_CLOCK = re.compile(r"^\d{1,2}:\d{2}$")
    #: A bare minute, optionally with stoppage time. INFERRED, not measured —
    #: see `_normalize_soccer_status`.
    _SOCCER_MINUTE = re.compile(r"^(\d{1,3})(\+\d{1,2})?'?$")

    @classmethod
    def _normalize_soccer_status(
        cls, raw: str, kickoff_clock: str
    ) -> tuple[str, Optional[str]]:
        """Soccer's live status vocabulary -> (our status, raw_status).

        Returns `raw_status` on the same rule `_parse_single_fixture` uses: it
        is set only when the row is live, because the live writer copies it into
        `event.period` and a period is a thing only a live game has.

        Three tokens, and they are not equally well established — which is said
        here rather than left for a reader to assume:

          * ``FT`` / ``AET`` / ``Pen.`` — MEASURED (23 of 195 rows at 04:25Z).
            Handled by the shared `_normalize_status`, which already knows them.
          * a wall clock — MEASURED, 172 of 195, and it is the kickoff time, not
            a period. Passing it through would report a game whose status is
            ``"22:00"``; reading it as live would put a not-yet-started match on
            the live board. It is `scheduled`, and it carries no `raw_status`.
          * a bare minute (``67``, ``90+3``) — **INFERRED, NOT MEASURED.** The
            04:25Z board had no match in play (Sunday night UTC; the census was
            23 FT and 172 unplayed), so this shape was never seen. It is treated
            as live because the vendor's own siblings say so — every event in
            the payload is keyed by ``minute``, and each match carries
            ``inj_minute``/``inj_time`` — and because #3366's measurement on
            2026-09-05 recorded ``status = "HT"`` on an in-play match, which the
            shared map already reads as live. Should the real token turn out to
            be something else, it falls through to the shared map and passes
            through unchanged, which is the same answer this parser gave before.
        """
        token = (raw or "").strip()
        if not token:
            return "", None
        if cls._SOCCER_KICKOFF_CLOCK.match(token):
            if kickoff_clock and token != kickoff_clock.strip():
                # The invariant that makes a clock readable as a kickoff time.
                # Still scheduled — a clock is not a period either way — but a
                # disagreement is a finding about the venue, so it is said.
                logger.warning(
                    "StatPal soccer: live status %r is a clock but the row's "
                    "own time is %r — reading it as scheduled",
                    token, kickoff_clock,
                )
            return "scheduled", None
        if cls._SOCCER_MINUTE.match(token):
            return "live", token
        status = _normalize_status(token)
        return status, (token if status == "live" else None)

    def _parse_soccer_live_matches(self, data: dict) -> list[StatPalFixture]:
        """Parse a v2 soccer `matches/live` payload for the authority program.

        Shape (measured 2026-09-07 04:25Z — 113 leagues, 195 matches)::

            {"live_matches": {
                "updated": "07.09.2026 04:25:00", "updated_ts": 1788755100,
                "league": [{"id": "2914", "name": "Argentina: Liga …",
                            "country": "argentina", "cup": "False",
                            "match": [ … ] }]}}

        Why this sport gets its own parser rather than a fix to the shared one:
        the same argument `get_live_fixtures` makes for tennis, and for the same
        reason. `_extract_match_items` DOES reach these rows — its generic
        ``"league" in val`` branch matches `live_matches` — so a shared-parser
        change would not add a reader, it would hand 195 rows to
        `sync_statpal_schedules` on the next beat. See
        `LIVESCORES_INGESTION_DARK_SPORTS`.

        And the shared parser reads two fields of this shape wrong, both
        measured over the full board:

          * **scores are `goals`, not `totalscore`** — all 195 rows parse
            scoreless through `_parse_single_fixture`. An unplayed match serves
            the literal string ``"?"`` here, which `_safe_int` correctly refuses;
            a reader that took it for 0 would print 0-0 over a game nobody has
            kicked off.
          * **status is the kickoff clock until the game starts** — see
            `_normalize_soccer_status`.

        Ids are carried, never substituted (D55). `main_id` is StatPal's own
        primary key for the fixture and it is **blank on 7 of the 195 rows**,
        with `fallback_id_1..3` blank on 12 — the same four id spaces
        `StatPalInjury` names. A blank id is emitted as a blank, because this
        door feeds a live READING keyed on the team pair (`espn_sync`'s standby
        check), and dropping the row would under-report StatPal's coverage of
        exactly the games ESPN went dark on. It must never become an anchor:
        #2963 is the 8,272-row repair that happens when a blank id is written as
        one, and no soccer writer exists to do it.
        """
        section = data.get("live_matches") if isinstance(data, dict) else None
        if not isinstance(section, dict):
            return []

        fixtures: list[StatPalFixture] = []
        for league in _as_list(section.get("league")):
            if not isinstance(league, dict):
                continue
            league_name = league.get("name") or None
            # `match` is a bare dict when the league has exactly one game — the
            # same one-item collapse `_extract_match_items` handles for v1.
            for item in _as_list(league.get("match")):
                if not isinstance(item, dict):
                    continue
                try:
                    fixture = self._parse_soccer_live_match(item, league_name)
                except Exception as exc:  # noqa: BLE001 — one bad row, not the board
                    logger.debug("StatPal soccer: skipping live row: %s", exc)
                    continue
                if fixture:
                    fixtures.append(fixture)
        return fixtures

    def _parse_soccer_live_match(
        self, item: dict, league_name: Optional[str]
    ) -> Optional[StatPalFixture]:
        """One row of `live_matches`. See `_parse_soccer_live_matches`."""
        home = item.get("home") if isinstance(item.get("home"), dict) else {}
        away = item.get("away") if isinstance(item.get("away"), dict) else {}
        home_team = str(home.get("name") or "").strip()
        away_team = str(away.get("name") or "").strip()
        if not home_team or not away_team:
            return None

        kickoff_clock = str(item.get("time") or "").strip()
        status, raw_status = self._normalize_soccer_status(
            str(item.get("status") or ""), kickoff_clock
        )

        # `date` + `time` with no `timezone` and no `datetime_utc` sibling is
        # UTC — the tell measured across the v1 endpoints and written up at
        # `_parse_single_fixture`'s start-time block. Confirmed on this board:
        # Racing Club v Atl. Tucuman reads 00:30 on 07.09, and 21:30 Argentine
        # time on the 6th is 00:30Z on the 7th.
        date_str = str(item.get("date") or "").strip()
        start_time = None
        if date_str and kickoff_clock:
            start_time = _parse_datetime(f"{date_str} {kickoff_clock}")
        if not start_time and date_str:
            start_time = _parse_datetime(date_str)

        venue = item.get("venue")
        if isinstance(venue, dict):
            venue = venue.get("name")

        return StatPalFixture(
            fixture_id=str(item.get("main_id") or ""),
            home_team=home_team,
            away_team=away_team,
            home_team_id=str(home.get("id") or "") or None,
            away_team_id=str(away.get("id") or "") or None,
            start_time=start_time,
            status=status,
            raw_status=raw_status,
            home_score=_safe_int(home.get("goals")),
            away_score=_safe_int(away.get("goals")),
            venue=str(venue).strip() or None if venue else None,
            league=league_name,
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
                    # NFL nests two levels deeper than every other v1 sport:
                    #   tournament -> stage[] -> week[] -> matches -> match
                    # where `matches` is a DATE GROUP (or a list of them), each
                    # holding `match`, and both `matches` and `match` are served
                    # as a bare dict when the group has exactly one game. Nothing
                    # above reaches it: `tournament.match` and `tournament.week`
                    # are both absent, so the whole payload fell through to the
                    # catch-all, which handed back the response ENVELOPE as one
                    # item — not empty, which is why a guard asserting emptiness
                    # here would read false while sounding right.
                    #
                    # `sync-statpal-schedules-nfl` therefore ran hourly, reported
                    # success and read 0 of the 17 games in its own recorded
                    # response (#3193). Gotcha #53 exactly: an empty result is
                    # the same shape as "no games this hour", so nothing alerted.
                    for stage in _as_list(tournament.get("stage")):
                        if not isinstance(stage, dict):
                            continue
                        for week_entry in _as_list(stage.get("week")):
                            if not isinstance(week_entry, dict):
                                continue
                            for group in _as_list(week_entry.get("matches")):
                                if not isinstance(group, dict):
                                    continue
                                # Not filtered to dicts here: `_parse_single_fixture`
                                # already returns None for a non-dict item, and
                                # two places rejecting the same thing means one of
                                # them is never exercised by any payload.
                                all_matches.extend(_as_list(group.get("match")))
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

        # ── START TIME: `datetime_utc` FIRST, AND THIS IS LOAD-BEARING ON THE
        #    LIVE PATH. Do not "isolate" it to the authority parser.
        #
        # StatPal's `date` + `time` pair is UTC on SOME endpoints and VENUE-LOCAL
        # on others, for the SAME sport, with nothing in the pair to say which.
        # The tell is two sibling fields: an endpoint that serves a local clock
        # also serves `timezone` and `datetime_utc`. Measured 2026-09-03:
        #
        #   /v1/mlb/season-schedule   time=16:35            no tz, no datetime_utc  -> UTC
        #   /v1/mlb/livescores        time=12:35  tz="ET"   datetime_utc=16:35      -> LOCAL
        #   /v1/nfl/livescores        time="6:00 PM" tz="EST" datetime_utc=23:00    -> LOCAL
        #
        # Same provider, same sport, same game: `season-schedule` says 16:35 and
        # `livescores` says 12:35. **9 of 9 live MLB games and 16 of 16 live NFL
        # games disagree with their own `datetime_utc`, every one of them by the
        # UTC offset.** Reading the pair as UTC on those endpoints writes a
        # commence_time four or five hours early.
        #
        # That is not theoretical and it is not the authority program's problem
        # alone. `sync_statpal_schedules` pairs a live row to a scheduled row
        # with `pair_verdict(fixture.start_time, live_data.start_time)` (#1945),
        # so a live row read four hours off does not merely carry a wrong time —
        # it fails to pair, and the live score never reaches the event.
        #
        # CERT-842 flagged this preference as a dark-lane change reaching the
        # live writer and asked for it to be isolated or fenced. Measurement says
        # fence: isolating it would restore a four-hour error on live MLB today
        # and on live NFL from 9/10. `tests/test_statpal_local_clock_is_not_utc.py`
        # pins the live path's use of it in both directions.
        date_str = item.get("date", "")
        time_str = item.get("time", "")
        start_time = _parse_datetime(item.get("datetime_utc"))
        if not start_time and date_str and time_str:
            if item.get("timezone"):
                # The pair is venue-local and the field that would convert it is
                # missing. Parsing it as UTC is a known-wrong answer, so it is
                # said out loud rather than written silently — this is the shape
                # that would put a game on the wrong day.
                logger.warning(
                    f"StatPal: {item.get('date')} {item.get('time')} carries "
                    f"timezone={item.get('timezone')!r} but no datetime_utc — "
                    f"reading a venue-local clock as UTC "
                    f"({item.get('home', {}).get('name')} v "
                    f"{item.get('away', {}).get('name')})"
                )
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

        # ── `contestid`, AND THIS TOO IS LOAD-BEARING ON THE LIVE PATH.
        #
        # NFL games have no "id" at all — the key is "contestid", on 374/374
        # season-schedule games AND on 16/16 games the LIVE endpoint served on
        # 2026-09-03. A blank fixture_id is not an absence, it is an unusable
        # linkage: 8,272 rows once carried '' for exactly this reason
        # (backend/scripts/repair_statpal_fixture_id_blanks.py).
        #
        # CERT-842's other half. Same verdict as the time field above, for the
        # same measured reason: isolating this to the authority parser gives
        # every live NFL fixture a blank id from 9/10. Fenced, not moved, and
        # pinned in `tests/test_statpal_local_clock_is_not_utc.py`.
        fixture_id = str(
            item.get("id") or item.get("contestid") or item.get("fixture_id") or ""
        )

        # `oddsid`, read here and NEVER preferred over `fixture_id`. Purely
        # additive: the live writers keep the id they have always had, so
        # carrying this one cannot move a score or a clock. The authority reader
        # is the only caller that looks at it, and it is the only caller that
        # needs to, because it is the only one joining two endpoints together.
        odds_id = str(item.get("oddsid") or "").strip() or None

        # Venue — can be a string or a dict
        venue = item.get("venue")
        if isinstance(venue, dict):
            venue = venue.get("name", "")

        return StatPalFixture(
            fixture_id=fixture_id,
            odds_id=odds_id,
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

        Thin wrapper over `get_injuries_result` for callers that only want the
        list. Anything that has to tell "nobody is hurt" from "we could not ask"
        must use the result form — see `StatPalInjuryFetch`.
        """
        return (await self.get_injuries_result(sport)).injuries

    async def get_injuries_result(self, sport: str) -> StatPalInjuryFetch:
        """Fetch current injury reports, carrying WHY the list is the size it is.

        Args:
            sport: StatPal sport identifier (`soccer`, `nfl`, …)

        Returns:
            A `StatPalInjuryFetch`. Never raises: this is the ingestion path, and
            a task that dies on a bad upstream day is worse than one that skips
            a cycle. The alarm is carried in `reason`, not thrown.
        """
        endpoint = INJURY_ENDPOINTS.get(sport)
        if endpoint is None:
            return StatPalInjuryFetch([], "no_venue_path", sport, None)

        data = await self._get(sport, endpoint)
        if not data:
            # `_get` already logged the status code. Everything it turns into
            # None — 404, 401, 429, timeout, an `invalid-request` 200 — is a
            # failure to READ, and none of them mean "no injuries".
            logger.error(
                f"StatPal injuries: could not read {sport}/{endpoint} — "
                "reporting fetch_failed, NOT an empty injury list"
            )
            return StatPalInjuryFetch([], "fetch_failed", sport, endpoint)

        if not _is_injury_envelope(data):
            # A 200 whose body we do not recognise. Before the caller learned to
            # CLEAR on a successful empty snapshot this was harmless — it parsed
            # to `[]` and nothing happened. Now `empty` is an instruction to
            # delete, so an unrecognised shape has to be a failure to read, not
            # an authoritative "nobody is hurt". Same asymmetry as everywhere
            # else here: preserving stale data costs a wrong name on a page,
            # deleting live data costs every injury list on the site.
            logger.error(
                f"StatPal injuries: {sport}/{endpoint} answered 200 with an "
                f"unrecognised envelope (top-level keys: {sorted(data)[:5]}) — "
                "reporting fetch_failed so stored injuries are preserved"
            )
            return StatPalInjuryFetch([], "fetch_failed", sport, endpoint)

        injuries = _parse_injuries_suspensions(data)
        reason = "ok" if injuries else "empty"
        return StatPalInjuryFetch(injuries, reason, sport, endpoint)

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

def _as_list(val) -> list:
    """One-or-many, the way StatPal actually serves it.

    Every level of the NFL schedule nesting collapses to a bare dict when it
    holds exactly one child — `stage`, `week`, `matches` and `match` all do it,
    and which ones collapse depends on the week. Pre Season serves one match as
    a dict where Week 1 serves thirteen as a list, in the same response.

    So a walker that branches on `isinstance(x, list)` reads whichever arm the
    fixture happened to record and drops the other silently. `None` is the empty
    list rather than `[None]`, so a missing level ends the walk instead of
    handing a `None` to the next one.
    """
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _is_injury_envelope(data) -> bool:
    """Is this body the injuries product at all?

    The canonical envelope is `{"injuries_suspensions": {..., "league": [...]}}`.
    `league: []` — nobody sidelined anywhere — IS canonical and must stay a
    successful empty snapshot, because that is the reading the caller acts on
    when it clears stale players.

    Everything else is refused: a missing or non-dict `injuries_suspensions`, a
    section with no `league` key at all, or a `league` whose VALUE the parser
    cannot walk. `{"data": []}` and `{}` both parse to zero injuries and would
    otherwise be indistinguishable from a real empty day, which is now an
    instruction to DELETE stored state.

    Checking that the key is PRESENT is not the same as checking that its value
    is readable, and the gap between the two was itself a deletion bug: a 200
    carrying `{"injuries_suspensions": {"league": null}}` has the key, so a
    key-only check calls it canonical; `_as_list(None)` is `[]`, so it parses to
    zero injuries, reads as a successful empty snapshot and clears every stored
    player. `null` is the vendor's own collapse of "no data" — the shape we are
    least entitled to read as authority. So only the two values the parser
    actually walks are accepted: a `list` of leagues, or the single-league
    `dict` collapse (`_as_list`). Anything else — `null`, a string, a number —
    is `fetch_failed`.

    A section that omits `league` entirely is treated as malformed rather than
    empty on purpose. We have never observed the vendor omit it, so the choice
    is between preserving state on a shape we do not understand and destroying
    it — and only one of those is recoverable on the next good pass.
    """
    if not isinstance(data, dict):
        return False
    section = data.get("injuries_suspensions")
    if not isinstance(section, dict) or "league" not in section:
        return False
    return isinstance(section["league"], (list, dict))


def _parse_injuries_suspensions(data: dict) -> list[StatPalInjury]:
    """Parse the soccer `injuries_suspensions` body into flat injury rows.

    The shape, measured over the full 2026-09-06 01:47Z payload (pinned at
    `tests/fixtures/statpal_soccer_injuries_20260906_fullcensus.json`):

        {"injuries_suspensions": {"updated": ..., "league": [
            {"name": ..., "id": ..., "match": [
                {"main_id": ..., "fallback_id_1..3": ..., "date": ..., "time": ...,
                 "home": {"id": ..., "name": ...,
                          "sidelined": {"to_miss": {"player": [...] | {...} | null},
                                        "questionable": {...}}},
                 "away": {...}}]}]}}

    Two things this parser exists to survive:

    * **Single-element collapse, at two levels.** In that one payload `to_miss`
      held a list 204 times and a bare dict 63 (`questionable`: 30 / 65), and
      `league.match` collapses the same way. `_as_list` at every level or a third
      of the players vanish without an error.
    * **The vendor's `status` is a REASON, not availability** — `Knee Injury`,
      `Red Card`, `Inactive`, `Coach's decision`; 49 distinct strings over 1,004
      players. Availability comes from the bucket (`INJURY_BUCKET_STATUS`) and
      the vendor's word goes to `injury_type`, where a reader can print it.

    A row with no player name is skipped; nothing here raises.
    """
    section = data.get("injuries_suspensions")
    if not isinstance(section, dict):
        return []

    injuries: list[StatPalInjury] = []
    for league in _as_list(section.get("league")):
        if not isinstance(league, dict):
            continue
        for match in _as_list(league.get("match")):
            if not isinstance(match, dict):
                continue
            fallbacks = tuple(
                str(match[key])
                for key in ("fallback_id_1", "fallback_id_2", "fallback_id_3")
                if match.get(key)
            )
            main_id = str(match.get("main_id") or "") or None
            sides = {side: match.get(side) for side in ("home", "away")}
            if not all(isinstance(s, dict) for s in sides.values()):
                continue

            for side, team in sides.items():
                other = sides["away" if side == "home" else "home"]
                sidelined = team.get("sidelined")
                if not isinstance(sidelined, dict):
                    continue
                for bucket, status in INJURY_BUCKET_STATUS.items():
                    entry = sidelined.get(bucket)
                    if not isinstance(entry, dict):
                        continue
                    for player in _as_list(entry.get("player")):
                        if not isinstance(player, dict):
                            continue
                        name = str(player.get("name") or "").strip()
                        if not name:
                            continue
                        injuries.append(StatPalInjury(
                            player_id=str(player.get("id") or ""),
                            player_name=name,
                            team=str(team.get("name") or ""),
                            team_id=str(team.get("id") or "") or None,
                            injury_type=str(player.get("status") or ""),
                            status=status,
                            fixture_date=_parse_datetime(match.get("date")),
                            opponent=str(other.get("name") or ""),
                            opponent_id=str(other.get("id") or "") or None,
                            is_home=(side == "home"),
                            fixture_main_id=main_id,
                            fixture_fallback_ids=fallbacks,
                        ))
    return injuries


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
