"""
ESPN API client for fetching team data, live scores, and win probabilities.

Uses ESPN's undocumented public API endpoints.
These endpoints are used by many applications but are not officially supported,
so they may change without notice. We implement conservative rate limiting and
graceful fallbacks.

TWO CONTRACTS THIS MODULE NOW HOLDS (lane1/045, Alex ruling 2026-09-01):

1. **We do not name ourselves to ESPN.** ESPN began refusing the
   ``User-Agent: BainLuck/1.0`` this client used to send. Measured 2026-09-01
   21:4x PDT against ``soccer/bra.1/scoreboard``::

       User-Agent: BainLuck/1.0        -> 403
       User-Agent: Mozilla/5.0         -> 403
       (User-Agent header removed)     -> 403
       (httpx default, python-httpx/x) -> 200

   So the client sends the httpx default UA and, on a 403, retries ONCE with
   the User-Agent header removed entirely. The no-UA retry is a belt, not the
   fix — it measured 403 on the day it was written (the earlier Q506 reading of
   200 did not reproduce) and is kept because it costs one request on a path
   that is already failing, and because it is the ruling's letter.

2. **An empty list never means "the request failed"** (gotcha #53). ``_get``
   raises :class:`ESPNAuthorityDark` on a transport failure or any non-2xx that
   is not a 404; every public fetch converts that to ``None``. ``[]``/``{}``
   now means only "ESPN answered, and there is nothing there". A caller that
   receives ``None`` must keep the last known state and must NOT infer or
   fabricate — an authority that did not answer has not said anything.

   Consecutive darkness is counted in module state and, past
   :data:`AUTHORITY_DARK_THRESHOLD`, logged ONCE at ERROR so it reaches Sentry.
   The 403 above went unnoticed for an unknown period precisely because ``[]``
   was silent.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Base URLs for ESPN API
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_CORE_API = "https://sports.core.api.espn.com/v2/sports"

# Mapping from our sport keys to ESPN sport/league paths
from app.utils.sport_keys import SPORT_LEAGUE_MAP  # noqa: E402

#: Which identity served a request. Recorded and logged on change so an
#: operator can see, without a repro, whether we are on the primary path.
PATH_DEFAULT_UA = "default_ua"      # httpx's own User-Agent
PATH_NO_UA = "no_ua"                # User-Agent header removed entirely

#: Consecutive unanswered ESPN requests before the darkness is announced at
#: ERROR. One announcement per dark spell, not one per request.
AUTHORITY_DARK_THRESHOLD = 10


class ESPNAuthorityDark(RuntimeError):
    """ESPN did not answer.

    Raised for a transport failure or any non-2xx that is not a 404. NOT raised
    for "the resource does not exist" (404) and never for an honestly empty
    payload — those are answers. Public methods convert this to ``None`` so a
    caller can tell "ESPN says there are no games" (``[]``) from "ESPN did not
    answer" (``None``).
    """

    def __init__(self, url: str, status: Optional[int] = None, error: Optional[str] = None):
        self.url = url
        self.status = status
        self.error = error
        detail = f"HTTP {status}" if status is not None else (error or "transport failure")
        super().__init__(f"ESPN authority dark ({detail}) for {url}")


@dataclass
class _AuthorityState:
    """Module-level health of the ESPN authority. Process-local by design.

    Not persisted: the question it answers is "is this worker getting answers
    from ESPN right now", and a counter that survives a dyno restart would
    answer a different, staler question.
    """

    consecutive_failures: int = 0
    total_failures: int = 0
    total_answers: int = 0
    announced: bool = False
    dark_since: Optional[str] = None
    last_status: Optional[int] = None
    last_error: Optional[str] = None
    last_url: Optional[str] = None
    served_path: Optional[str] = None
    served_counts: dict[str, int] = field(default_factory=dict)


_AUTHORITY = _AuthorityState()


def espn_authority_state() -> dict:
    """Readable snapshot of ESPN's answering health (admin/tests/reports)."""
    return {
        "consecutive_failures": _AUTHORITY.consecutive_failures,
        "total_failures": _AUTHORITY.total_failures,
        "total_answers": _AUTHORITY.total_answers,
        "is_dark": _AUTHORITY.consecutive_failures >= AUTHORITY_DARK_THRESHOLD,
        "dark_since": _AUTHORITY.dark_since,
        "last_status": _AUTHORITY.last_status,
        "last_error": _AUTHORITY.last_error,
        "last_url": _AUTHORITY.last_url,
        "served_path": _AUTHORITY.served_path,
        "served_counts": dict(_AUTHORITY.served_counts),
    }


def reset_espn_authority_state() -> None:
    """Reset the counter. For tests and for an operator-triggered re-probe."""
    global _AUTHORITY
    _AUTHORITY = _AuthorityState()


def _record_espn_answered(path: str) -> None:
    """ESPN answered — including with a 404, which is an answer, not darkness."""
    was_dark = _AUTHORITY.consecutive_failures >= AUTHORITY_DARK_THRESHOLD
    _AUTHORITY.consecutive_failures = 0
    _AUTHORITY.total_answers += 1
    _AUTHORITY.dark_since = None
    _AUTHORITY.announced = False
    _AUTHORITY.served_counts[path] = _AUTHORITY.served_counts.get(path, 0) + 1
    if _AUTHORITY.served_path != path:
        # Which path served is logged on CHANGE, not per request: ESPN is polled
        # thousands of times a day and a per-request line would be noise.
        logger.info("ESPN API now being served on the %s path", path)
        _AUTHORITY.served_path = path
    if was_dark:
        logger.error(
            "ESPN AUTHORITY RECOVERED — answering again on the %s path after "
            "%d consecutive failures. Update the ESPN item on "
            ".claude/handoff/TOP-PRODUCT-DEFECTS.md.",
            path,
            _AUTHORITY.total_failures,
        )


def _record_espn_dark(url: str, status: Optional[int], error: Optional[str]) -> None:
    """One unanswered request. Announces at ERROR once per dark spell."""
    _AUTHORITY.consecutive_failures += 1
    _AUTHORITY.total_failures += 1
    _AUTHORITY.last_status = status
    _AUTHORITY.last_error = error
    _AUTHORITY.last_url = url
    if _AUTHORITY.dark_since is None:
        _AUTHORITY.dark_since = datetime.now(timezone.utc).isoformat()
    if (
        _AUTHORITY.consecutive_failures >= AUTHORITY_DARK_THRESHOLD
        and not _AUTHORITY.announced
    ):
        _AUTHORITY.announced = True
        # ERROR, so it reaches Sentry and the /health triage threshold. The
        # durable instrument is the defect board — this line names it so the
        # operator who sees the Sentry issue knows where the status line goes.
        logger.error(
            "ESPN AUTHORITY DARK: %d consecutive unanswered requests "
            "(last %s for %s, error=%s, dark since %s). ESPN-derived scores, "
            "schedules and win probabilities are FROZEN at their last known "
            "state — nothing is being inferred from the silence. File/refresh "
            "the ESPN item's status line on "
            ".claude/handoff/TOP-PRODUCT-DEFECTS.md.",
            _AUTHORITY.consecutive_failures,
            f"HTTP {status}" if status is not None else "transport failure",
            url,
            error,
            _AUTHORITY.dark_since,
        )


@dataclass
class ESPNTeam:
    """Team data from ESPN."""
    espn_id: str
    name: str
    abbreviation: Optional[str]
    display_name: Optional[str]
    short_name: Optional[str]
    nickname: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    logo_url: Optional[str]
    logo_url_dark: Optional[str]
    record: Optional[str]  # e.g., "34-18"
    location: Optional[str] = None  # ESPN "location" field: city, region, or school name


@dataclass
class ESPNVenue:
    """Venue data from ESPN."""
    espn_id: str
    name: str
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    capacity: Optional[int]


@dataclass
class ESPNInjury:
    """Injury data from ESPN summary endpoint."""
    player_name: str
    team_name: str
    status: str           # "Out", "Day-To-Day", "Questionable", "Probable"
    injury_type: str      # "Knee", "Hamstring", etc.
    position: Optional[str] = None


@dataclass
class ESPNNewsHeadline:
    """News headline from ESPN summary endpoint."""
    headline: str
    published: Optional[str] = None


@dataclass
class ESPNEvent:
    """Event/game data from ESPN."""
    espn_id: str
    name: str
    short_name: Optional[str]
    date: datetime
    status: str  # "scheduled", "in", "post"
    status_detail: Optional[str]  # "1st Quarter", "Final", etc.
    period: Optional[int]
    clock: Optional[str]  # "4:32"
    home_team: Optional[ESPNTeam]
    away_team: Optional[ESPNTeam]
    home_score: Optional[int]
    away_score: Optional[int]
    venue: Optional[ESPNVenue]
    broadcasts: list[str]
    home_win_probability: Optional[float]
    season_type: Optional[int] = None  # 1=preseason, 2=regular, 3=postseason


def espn_terminal_state(status_type: dict) -> Optional[str]:
    """``"post"`` when ESPN says this competition is OVER, else ``None``.

    🔴 **WHY THE NAME IS NOT ENOUGH (#2908).** `_parse_event` derived its
    three-valued status from `status.type.name`, and the only terminal name it
    knew was ``STATUS_FINAL``. **Soccer does not use it.** Measured across every
    ESPN-mapped league on 2026-09-02/03:

        baseball/mlb              STATUS_FINAL       state=post  completed=True
        football/college-football STATUS_FINAL       state=post  completed=True
        tennis/atp                STATUS_FINAL       state=post  completed=True
        soccer/fra.1              STATUS_FULL_TIME   state=post  completed=True
        soccer/esp.1              STATUS_FULL_TIME   state=post  completed=True

    So a finished match fell through to the raw name, `update_event_fields_from_espn`'s
    settle branch never fired, and the row stayed ``live`` while the same sync
    wrote ``period = "FT"`` onto it from `status_detail` — one row saying two
    things, and the Live Now rail believing the wrong one.

    THE FIX IS TO READ THE FIELD ESPN PUBLISHES FOR THIS. `status.type.state` is
    already ESPN's own `pre`/`in`/`post`, and `_parse_header_scores` has read it
    (with `completed`) since #980/#981. This is that same rule, applied to the
    scoreboard parser.

    **BOTH conditions, and `completed` is the load-bearing one.** A census of
    5,672 soccer fixtures across 34 ESPN leagues, 2026-02-01 → 2026-09-04
    (`LIVE-060-EVIDENCE-PROVENANCE`), returns exactly five terminal names — and
    ``STATUS_CANCELED``, which the first version of this docstring named, is not
    one of them:

        STATUS_FULL_TIME   5,572  post  completed=True    settles
        STATUS_FINAL_PEN      57  post  completed=True    settles
        STATUS_FINAL_AET       7  post  completed=True    settles
        STATUS_POSTPONED       7  post  completed=False   must NOT settle
        STATUS_ABANDONED       1  post  completed=False   must NOT settle

    So the name-only parser was blind to three names, not one, and ``state``
    alone would settle two that nobody finished. ``STATUS_ABANDONED`` is the
    case that shows why the second half of the rule is load-bearing: it stops
    mid-match, so it arrives with a real clock and a real period, and only
    ``completed=False`` separates it from a result. Settling on `state` alone
    would stamp a Final and a 0-0 on it, which is the CERT-752 class exactly: a
    false LIVE traded for a false FINAL, and only one of the two grades.

    **`state == "in"` is deliberately NOT translated here.** It would newly flip
    soccer rows live from the authority, and ``STATUS_DELAYED`` is ``state="in"``
    before a ball is bowled — a live-flip this bug does not need and this change
    has not measured. One behaviour changes: a match ESPN says is finished ends.
    """
    if not isinstance(status_type, dict):
        return None
    state = str(status_type.get("state") or "").strip().lower()
    if state == "post" and status_type.get("completed") is True:
        return "post"
    return None


class ESPNAPIService:
    """Client for ESPN's public API endpoints."""

    def __init__(
        self,
        timeout: float = 10.0,
        rate_limit_delay: float = 0.5,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        """
        Initialize ESPN API client.

        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests in seconds
            transport: Optional httpx transport. Tests inject a MockTransport
                here; injecting it at CONSTRUCTION (rather than swapping the
                attribute afterwards) is what makes the fake actually serve,
                because a client built with proxy env vars mounts the proxy
                ahead of its default transport and a swapped attribute is
                never consulted.
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._client_no_ua: Optional[httpx.AsyncClient] = None

    def _client_kwargs(self) -> dict:
        kwargs: dict = {
            "timeout": self.timeout,
            "headers": {"Accept": "application/json"},
        }
        if self._transport is not None:
            # mounts={} so an ambient proxy cannot outrank the injected wire.
            kwargs["transport"] = self._transport
            kwargs["mounts"] = {}
        return kwargs

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the primary HTTP client.

        No ``User-Agent`` is set: httpx supplies its own (``python-httpx/x``),
        which is the identity ESPN currently answers. Do not put a product UA
        back here — see the module docstring for the measurement.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(**self._client_kwargs())
        return self._client

    async def _get_no_ua_client(self) -> httpx.AsyncClient:
        """Client that sends NO ``User-Agent`` header at all (403 fallback).

        httpx injects a default UA into every client, so the header is popped
        after construction — passing ``""`` sends an *empty* UA, which is a
        different (and measured-403) thing.
        """
        if self._client_no_ua is None or self._client_no_ua.is_closed:
            client = httpx.AsyncClient(**self._client_kwargs())
            client.headers.pop("user-agent", None)
            self._client_no_ua = client
        return self._client_no_ua

    async def close(self):
        """Close the HTTP clients."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        if self._client_no_ua and not self._client_no_ua.is_closed:
            await self._client_no_ua.aclose()
        self._client_no_ua = None

    def _dark(
        self, url: str, *, status: Optional[int] = None, error: Optional[str] = None
    ) -> ESPNAuthorityDark:
        """Record + log one unanswered request and build the exception to raise."""
        _record_espn_dark(url, status=status, error=error)
        logger.warning(
            "ESPN API did not answer: %s for %s (%d consecutive) — treating as "
            "AUTHORITY DARK, not as an empty result",
            f"HTTP {status}" if status is not None else f"transport error: {error}",
            url,
            _AUTHORITY.consecutive_failures,
        )
        return ESPNAuthorityDark(url, status=status, error=error)

    async def _get(self, url: str) -> Optional[dict]:
        """GET one ESPN URL.

        Returns the decoded body on 200, and ``None`` on a 404 — the resource
        does not exist, which is an answer.

        Raises:
            ESPNAuthorityDark: transport failure, or any other non-2xx. The
                caller must NOT read this as "nothing there".
        """
        try:
            client = await self._get_client()
            response = await client.get(url)
            served_path = PATH_DEFAULT_UA

            if response.status_code == 429:
                logger.warning("ESPN API rate limited, waiting before retry: %s", url)
                await asyncio.sleep(5)
                response = await client.get(url)

            if response.status_code == 403:
                # Refused on identity, not on the resource. One retry with the
                # User-Agent header removed entirely, then we are dark.
                logger.warning(
                    "ESPN API 403 on the %s path for %s — retrying once with no "
                    "User-Agent header",
                    PATH_DEFAULT_UA,
                    url,
                )
                no_ua_client = await self._get_no_ua_client()
                response = await no_ua_client.get(url)
                served_path = PATH_NO_UA

            if response.status_code == 404:
                logger.info("ESPN API 404 (resource absent, authority alive) for %s", url)
                _record_espn_answered(served_path)
                return None

            if response.status_code != 200:
                raise self._dark(url, status=response.status_code)

            await asyncio.sleep(self.rate_limit_delay)
            body = response.json()
            _record_espn_answered(served_path)
            return body

        except ESPNAuthorityDark:
            raise
        except httpx.TimeoutException as e:
            raise self._dark(url, error=f"timeout: {e}") from e
        except Exception as e:
            raise self._dark(url, error=f"{type(e).__name__}: {e}") from e

    def _get_espn_path(self, sport_key: str) -> Optional[tuple[str, str]]:
        """Get ESPN sport/league path from our sport key."""
        return SPORT_LEAGUE_MAP.get(sport_key)

    def _parse_color(self, color: Optional[str]) -> Optional[str]:
        """Parse ESPN color to hex format."""
        if not color:
            return None
        # ESPN returns colors without # prefix
        if not color.startswith("#"):
            return f"#{color}"
        return color

    def _parse_team(self, team_data: dict) -> Optional[ESPNTeam]:
        """Parse ESPN team data into ESPNTeam object."""
        try:
            team = team_data.get("team", team_data)

            # Get logo URL
            # The teams endpoint returns "logos" (array of objects with href/rel)
            # The scoreboard endpoint returns "logo" (single URL string)
            logo_url = None
            logo_url_dark = None
            logos = team.get("logos", [])
            for logo in logos:
                if logo.get("rel", [None])[0] == "default":
                    logo_url = logo.get("href")
                elif logo.get("rel", [None])[0] == "dark":
                    logo_url_dark = logo.get("href")
            if not logo_url and logos:
                logo_url = logos[0].get("href")
            # Fallback: scoreboard uses a single "logo" string
            if not logo_url:
                logo_url = team.get("logo")

            # Get record
            record = None
            records = team_data.get("records", [])
            for rec in records:
                if rec.get("type") == "total":
                    record = rec.get("summary")
                    break

            return ESPNTeam(
                espn_id=str(team.get("id")),
                name=team.get("name"),
                abbreviation=team.get("abbreviation"),
                display_name=team.get("displayName"),
                short_name=team.get("shortDisplayName"),
                nickname=team.get("nickname"),
                primary_color=self._parse_color(team.get("color")),
                secondary_color=self._parse_color(team.get("alternateColor")),
                logo_url=logo_url,
                logo_url_dark=logo_url_dark,
                record=record,
                location=team.get("location"),
            )
        except Exception as e:
            logger.error(f"Error parsing ESPN team: {e}")
            return None

    def _parse_venue(self, venue_data: dict) -> Optional[ESPNVenue]:
        """Parse ESPN venue data into ESPNVenue object."""
        try:
            address = venue_data.get("address", {})
            return ESPNVenue(
                espn_id=str(venue_data.get("id")),
                name=venue_data.get("fullName", venue_data.get("name")),
                city=address.get("city"),
                state=address.get("state"),
                country=address.get("country"),
                capacity=venue_data.get("capacity"),
            )
        except Exception as e:
            logger.error(f"Error parsing ESPN venue: {e}")
            return None

    async def get_teams(self, sport_key: str) -> Optional[list[ESPNTeam]]:
        """
        Get all teams for a sport/league.

        Args:
            sport_key: Our internal sport key (e.g., "basketball_nba")

        Returns:
            List of ESPNTeam objects, ``[]`` when ESPN lists none, or ``None``
            when ESPN did not answer (authority dark — keep last known state).
        """
        path = self._get_espn_path(sport_key)
        if not path:
            logger.warning(f"No ESPN mapping for sport key: {sport_key}")
            return []

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/teams?limit=100"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return []

        teams = []
        for team_data in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
            team = self._parse_team(team_data)
            if team:
                teams.append(team)

        logger.info(f"Fetched {len(teams)} teams for {sport_key}")
        return teams

    async def get_team(self, sport_key: str, team_id: str) -> Optional[ESPNTeam]:
        """
        Get a specific team by ESPN ID.

        Args:
            sport_key: Our internal sport key
            team_id: ESPN team ID

        Returns:
            ESPNTeam object, or None when the team is absent OR ESPN did not
            answer. A single-object lookup cannot distinguish the two; callers
            that need the distinction should read :func:`espn_authority_state`.
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/teams/{team_id}"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return None

        return self._parse_team(data.get("team", data))

    async def get_scoreboard(
        self, sport_key: str, date: Optional[str] = None
    ) -> Optional[list[ESPNEvent]]:
        """
        Get scoreboard (list of games) for a sport/league.

        Args:
            sport_key: Our internal sport key
            date: Optional date in YYYYMMDD format (defaults to today)

        Returns:
            List of ESPNEvent objects, ``[]`` when ESPN's slate is genuinely
            empty, or ``None`` when ESPN did not answer. ``None`` means the
            authority is dark: an event's absence from the board proves
            NOTHING, so no caller may settle, void or complete on it.
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return []

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/scoreboard"
        if date:
            url += f"?dates={date}"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return []

        events = []
        for event_data in data.get("events", []):
            event = self._parse_event(event_data)
            if event:
                events.append(event)

        logger.info(f"Fetched {len(events)} events for {sport_key}")
        return events

    def _parse_event(self, event_data: dict) -> Optional[ESPNEvent]:
        """Parse ESPN event data into ESPNEvent object."""
        try:
            competition = event_data.get("competitions", [{}])[0]
            status_data = event_data.get("status", {})
            status_type = status_data.get("type", {})

            # Parse status
            status_name = status_type.get("name", "").lower()
            if status_name == "status_scheduled":
                status = "scheduled"
            elif status_name == "status_in_progress":
                status = "in"
            elif status_name == "status_final":
                status = "post"
            else:
                status = espn_terminal_state(status_type) or status_name

            # Parse teams
            home_team = None
            away_team = None
            home_score = None
            away_score = None

            for competitor in competition.get("competitors", []):
                team = self._parse_team(competitor)
                raw_score = competitor.get("score")
                if raw_score is not None:
                    try:
                        score = int(raw_score)
                    except (ValueError, TypeError):
                        score = None
                else:
                    score = None

                if competitor.get("homeAway") == "home":
                    home_team = team
                    home_score = score
                else:
                    away_team = team
                    away_score = score

            # Parse venue
            venue = None
            venue_data = competition.get("venue")
            if venue_data:
                venue = self._parse_venue(venue_data)

            # Parse broadcasts
            broadcasts = []
            for broadcast in competition.get("broadcasts", []):
                for name in broadcast.get("names", []):
                    broadcasts.append(name)

            # Parse win probability (if available)
            home_win_prob = None
            situation = competition.get("situation", {})
            if situation:
                home_win_prob = situation.get("lastPlay", {}).get("probability", {}).get("homeWinPercentage")
                # ESPN returns percentage (e.g., 83.1 = 83.1%) — convert to decimal
                if home_win_prob is not None and home_win_prob > 1.0:
                    home_win_prob = home_win_prob / 100.0

            # Parse date
            date_str = event_data.get("date")
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None

            # Parse season type (1=preseason, 2=regular, 3=postseason)
            season_type_val = None
            season_type_raw = event_data.get("season", {}).get("type")
            if isinstance(season_type_raw, int):
                season_type_val = season_type_raw

            return ESPNEvent(
                espn_id=str(event_data.get("id")),
                name=event_data.get("name"),
                short_name=event_data.get("shortName"),
                date=date,
                status=status,
                status_detail=status_type.get("detail"),
                period=status_data.get("period"),
                clock=status_data.get("displayClock"),
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                venue=venue,
                broadcasts=broadcasts,
                home_win_probability=home_win_prob,
                season_type=season_type_val,
            )
        except Exception as e:
            logger.error(f"Error parsing ESPN event: {e}")
            return None

    async def get_event(self, sport_key: str, event_id: str) -> Optional[ESPNEvent]:
        """
        Get a specific event/game by ESPN ID.

        Args:
            sport_key: Our internal sport key
            event_id: ESPN event ID

        Returns:
            ESPNEvent object, or None when the event is absent OR ESPN did not
            answer (read :func:`espn_authority_state` to tell them apart).
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/summary?event={event_id}"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return None

        # The summary endpoint has different structure
        event_data = data.get("header", {}).get("competitions", [{}])[0] if data.get("header") else {}

        # Also get win probability from predictor
        home_win_prob = None
        predictor = data.get("predictor", {})
        if predictor:
            home_team_data = predictor.get("homeTeam", {})
            home_win_prob = home_team_data.get("gameProjection")
            if home_win_prob:
                home_win_prob = float(home_win_prob) / 100  # Convert percentage

        if not event_data:
            return None

        event = self._parse_event({"competitions": [event_data], **data.get("header", {})})
        if event and home_win_prob is not None:
            event.home_win_probability = home_win_prob

        return event

    async def get_win_probability(self, sport_key: str, event_id: str) -> Optional[list[dict]]:
        """
        Get win probability data over time for a game.

        Args:
            sport_key: Our internal sport key
            event_id: ESPN event ID

        Returns:
            List of {time, home_win_probability} dicts, or None when ESPN
            publishes no win-probability series for the game OR did not answer.
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/summary?event={event_id}"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return None

        # Get win probability chart data
        win_prob_data = data.get("winprobability", [])
        if not win_prob_data:
            return None

        result = []
        for point in win_prob_data:
            result.append({
                "play_id": point.get("playId"),
                "seconds_left": point.get("secondsLeft"),
                "home_win_probability": point.get("homeWinPercentage", 0) / 100,
            })

        return result

    async def get_event_context(
        self, sport_key: str, event_id: str
    ) -> Optional[dict]:
        """
        Get injury reports, news headlines, box score, and scoring plays for an event.

        Uses the /summary endpoint (same as get_event) and parses the
        injuries, news, boxscore, and scoringPlays sections.

        Args:
            sport_key: Our internal sport key
            event_id: ESPN event ID

        Returns:
            {"injuries": list[ESPNInjury], "news": list[ESPNNewsHeadline],
             "box_score": dict, "scoring_plays": list[dict]}, or ``None`` when
            ESPN did not answer. An empty context means "ESPN has nothing for
            this game"; ``None`` means we do not know — do not write from it.
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return {"injuries": [], "news": [], "box_score": {}, "scoring_plays": []}

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/summary?event={event_id}"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return {"injuries": [], "news": [], "box_score": {}, "scoring_plays": []}

        injuries = self._parse_injuries(data)
        news = self._parse_news(data)
        box_score = self._parse_boxscore(data)
        scoring_plays = self._parse_scoring_plays(data)

        scores = self._parse_header_scores(data)

        return {
            "injuries": injuries,
            "news": news,
            "box_score": box_score,
            "scoring_plays": scoring_plays,
            "scores": scores,
        }

    @staticmethod
    def _parse_header_scores(data: dict) -> dict:
        """Extract home/away scores and period scores from the summary header.

        Returns ``{"home_score": int, "away_score": int,
        "home_period_scores": [int, ...], "away_period_scores": [int, ...]}``.
        """
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if not competitions:
            return {}
        result: dict = {}
        # #980/#981: expose whether ESPN considers the game FINAL. A
        # prematurely-"completed" event (commence +1day bug #981) can still be
        # in-progress on ESPN; without this, a mid-game score gets written as a
        # final and corrupts calibration. state == "post" / completed == True.
        _stype = (competitions[0].get("status", {}) or {}).get("type", {}) or {}
        result["is_final"] = bool(
            _stype.get("completed") is True
            or _stype.get("state") == "post"
            or _stype.get("name") == "STATUS_FINAL"
        )
        for comp in competitions[0].get("competitors", []):
            raw = comp.get("score")
            try:
                score = int(raw) if raw is not None else None
            except (ValueError, TypeError):
                score = None

            period_scores = []
            for ls in comp.get("linescores", []):
                try:
                    period_scores.append(int(ls.get("displayValue", 0)))
                except (ValueError, TypeError):
                    period_scores.append(0)

            if comp.get("homeAway") == "home":
                result["home_score"] = score
                if period_scores:
                    result["home_period_scores"] = period_scores
            else:
                result["away_score"] = score
                if period_scores:
                    result["away_period_scores"] = period_scores
        return result

    def _parse_injuries(self, summary_data: dict) -> list[ESPNInjury]:
        """Parse injury data from ESPN summary response."""
        injuries = []
        for team_group in summary_data.get("injuries", []):
            team_name = team_group.get("team", {}).get("displayName", "")
            for item in team_group.get("injuries", []):
                athlete = item.get("athlete", {})
                player_name = athlete.get("displayName", "")
                if not player_name:
                    continue
                status = item.get("status", "Unknown")
                injury_type = item.get("details", {}).get("type", "Unknown") if isinstance(item.get("details"), dict) else "Unknown"
                position = athlete.get("position", {}).get("abbreviation") if isinstance(athlete.get("position"), dict) else None
                injuries.append(ESPNInjury(
                    player_name=player_name,
                    team_name=team_name,
                    status=status,
                    injury_type=injury_type,
                    position=position,
                ))
        return injuries

    def _parse_news(self, summary_data: dict) -> list[ESPNNewsHeadline]:
        """Parse news headlines from ESPN summary response."""
        headlines = []
        articles = summary_data.get("news", {}).get("articles", [])
        if not isinstance(articles, list):
            return []
        for article in articles:
            headline = article.get("headline", "")
            if not headline:
                continue
            published = article.get("published")
            headlines.append(ESPNNewsHeadline(
                headline=headline,
                published=published,
            ))
        return headlines

    # Stat name normalization: ESPN abbreviation → canonical name.
    #
    # ⚠️ THIS MAP IS THE LEGACY FALLBACK ONLY (#1990). It is ONE FLAT NAMESPACE
    # shared by every sport AND, worse, by every stat GROUP within a sport — so
    # an abbreviation that means two different quantities in two groups lands in
    # one key. Measured instances, all of them silent wrong-quantity writes:
    #   * baseball  `H`/`R`/`BB`/`HR` mean hits/runs/walks/HR *made* in the
    #     batting group and *allowed* in the pitching group. Shane Baz's
    #     6.1 IP / 4 H / 3 R line was stored as {"hits": 4, "runs": 3, ...} —
    #     indistinguishable from a batter's line except by the absence of AB.
    #   * football  `YDS` and `TD` appear in 7 and 6 groups respectively and
    #     overwrite each other; `INT` is thrown in `passing` and caught in
    #     `interceptions`; `REC` is a catch in `receiving` and a fumble
    #     recovery in `fumbles`.
    #   * hockey    `S` is shotsTotal for a skater — stored as "saves".
    #                `SOG` is shootoutGoals, not shots-on-goal.
    # The fix is `_GROUP_STAT_MAP` below, which resolves per (group, ESPN key).
    # Anything still resolved through THIS map is a group we have not yet
    # audited against a real payload. Do not add a sport here — add a group.
    _STAT_NORMALIZE: dict[str, str] = {
        # Basketball — audited 2026-08-18 against NBA 401859966, WNBA 401857152
        # and NCAAB 401856600: a single unnamed stat group per team, so the flat
        # namespace is safe here and these stay put.
        "PTS": "points", "REB": "rebounds", "AST": "assists",
        "STL": "steals", "BLK": "blocks", "TO": "turnovers",
        "3PT": "three pointers", "OREB": "offensive rebounds",
        "DREB": "defensive rebounds", "FG": "field goals",
        "FT": "free throws", "MIN": "minutes",
        "PF": "personal fouls", "+/-": "plus minus",
        # NOTE — deliberately REMOVED, each verified dead or wrong against a
        # real payload on 2026-08-18 (#1990). Restoring one re-opens a defect:
        #   "SO"                        baseball never emits it; ESPN says "K"
        #   "SACK"                      football emits "SACKS"
        #   "PASS/RUSH/REC YDS"         never emitted; the label is bare "YDS"
        #   "SH"/"SOG" (soccer)         soccer summaries carry NO
        #                               boxscore.players at all — they use
        #                               `rosters` — so these could never fire
        #   "S": "saves"                hockey `S` is a SKATER's shotsTotal
        #   "SOG": "shots on goal"      hockey `SOG` is shootoutGoals
        # Football/baseball/hockey now resolve through _GROUP_STAT_MAP.
    }

    # Group-scoped stat resolution (#1990). Keyed by the ESPN stat group, then
    # by ESPN's OWN `keys` entry rather than its display abbreviation.
    #
    # Why `keys` and not `labels`: `keys` are already near-canonical
    # ("strikeouts", "earnedRuns") instead of abbreviations, so they do not
    # break when ESPN restyles a column header — which is the entire failure
    # mode that made `SO` dead for the lifetime of the map. `labels` remains the
    # fallback via _GROUP_LABEL_MAP when `keys` is absent or misaligned.
    #
    # A column absent from a group's table is DROPPED, deliberately: an
    # unmapped stat is better than a stat under a name that means something
    # else. Every table below was read off a live payload, cited per group.
    _GROUP_STAT_MAP: dict[str, dict[str, str]] = {
        # --- Baseball (MLB 401816574, 2026-08-18) --------------------------
        # Batting keeps the bare names the seven existing stored keys already
        # use — this half must not move or every stored batter row changes
        # shape. `strikeouts` is NEW here and is the batter's K.
        "batting": {
            "atBats": "at bats",
            "runs": "runs",
            "hits": "hits",
            "RBIs": "rbis",
            "homeRuns": "home runs",
            "walks": "walks",
            "strikeouts": "strikeouts",
            "avg": "batting average",
            "onBasePct": "on base percentage",
            "slugAvg": "slugging percentage",
            "pitches": "pitches seen",
        },
        # Pitching is namespaced so it can never again be read as batting.
        # "6.1" IP parses to 6.1 — innings, not a compound.
        "pitching": {
            "fullInnings.partInnings": "innings pitched",
            "strikeouts": "pitching strikeouts",
            "hits": "pitching hits allowed",
            "runs": "pitching runs allowed",
            "earnedRuns": "earned runs",
            "walks": "pitching walks allowed",
            "homeRuns": "pitching home runs allowed",
            "ERA": "era",
            "pitches": "pitch count",
        },
        # --- Hockey (NHL 401803652, 2026-04-15) ----------------------------
        # `forwards`, `defenses` and `skaters` carry an identical column set;
        # they are aliased onto "skaters" below.
        "skaters": {
            "goals": "goals",
            "assists": "assists",
            "blockedShots": "blocked shots",
            "hits": "hits",
            "takeaways": "takeaways",
            "giveaways": "giveaways",
            "penaltyMinutes": "penalty minutes",
            "shotsTotal": "shots",
            "shootoutGoals": "shootout goals",
            "plusMinus": "plus minus",
            "faceoffsWon": "faceoffs won",
        },
        "goalies": {
            "saves": "saves",
            "goalsAgainst": "goals against",
            "shotsAgainst": "shots against",
            "savePct": "save percentage",
            "penaltyMinutes": "penalty minutes",
        },
        # --- Football (NFL 401873272, 2026-08-18) --------------------------
        # Namespaced because YDS/TD/INT/REC each mean different quantities in
        # different groups. No player-prop resolver reads football box scores
        # today, so these names are new rather than moved.
        "passing": {
            "completions/passingAttempts": "completions",
            "passingYards": "passing yards",
            "passingTouchdowns": "passing touchdowns",
            "interceptions": "interceptions thrown",
            "sacks-sackYardsLost": "sacks taken",
        },
        "rushing": {
            "rushingAttempts": "carries",
            "rushingYards": "rushing yards",
            "rushingTouchdowns": "rushing touchdowns",
            "longRushing": "long rush",
        },
        "receiving": {
            "receptions": "receptions",
            "receivingYards": "receiving yards",
            "receivingTouchdowns": "receiving touchdowns",
            "receivingTargets": "targets",
            "longReception": "long reception",
        },
        "fumbles": {
            "fumbles": "fumbles",
            "fumblesLost": "fumbles lost",
            "fumblesRecovered": "fumbles recovered",
        },
        "defensive": {
            "totalTackles": "tackles",
            "soloTackles": "solo tackles",
            "sacks": "sacks",
            "tacklesForLoss": "tackles for loss",
            "passesDefended": "passes defended",
            "QBHits": "qb hits",
            "defensiveTouchdowns": "defensive touchdowns",
        },
        "interceptions": {
            "interceptions": "interceptions caught",
            "interceptionYards": "interception yards",
            "interceptionTouchdowns": "interception touchdowns",
        },
        "kickreturns": {
            "kickReturns": "kick returns",
            "kickReturnYards": "kick return yards",
            "kickReturnTouchdowns": "kick return touchdowns",
        },
        "puntreturns": {
            "puntReturns": "punt returns",
            "puntReturnYards": "punt return yards",
            "puntReturnTouchdowns": "punt return touchdowns",
        },
        "kicking": {
            "fieldGoalsMade/fieldGoalAttempts": "field goals",
            "extraPointsMade/extraPointAttempts": "extra points",
            "totalKickingPoints": "kicking points",
        },
        "punting": {
            "punts": "punts",
            "puntYards": "punt yards",
            "puntsInside20": "punts inside 20",
        },
    }

    # Fallback when a group's `keys` array is missing or misaligned with
    # `stats` (NFL `passing` ships 8 keys for 7 columns — see
    # _resolve_stat_columns). Keyed by group, then by the display label.
    _GROUP_LABEL_MAP: dict[str, dict[str, str]] = {
        "batting": {
            "AB": "at bats", "R": "runs", "H": "hits", "RBI": "rbis",
            "HR": "home runs", "BB": "walks", "K": "strikeouts",
            "AVG": "batting average", "OBP": "on base percentage",
            "SLG": "slugging percentage", "#P": "pitches seen",
        },
        "pitching": {
            "IP": "innings pitched", "K": "pitching strikeouts",
            "H": "pitching hits allowed", "R": "pitching runs allowed",
            "ER": "earned runs", "BB": "pitching walks allowed",
            "HR": "pitching home runs allowed", "ERA": "era",
            "PC": "pitch count",
        },
        "skaters": {
            "G": "goals", "A": "assists", "BS": "blocked shots",
            "HT": "hits", "TK": "takeaways", "GV": "giveaways",
            "PIM": "penalty minutes", "S": "shots",
            "SOG": "shootout goals", "+/-": "plus minus", "FW": "faceoffs won",
        },
        "goalies": {
            "SV": "saves", "GA": "goals against", "SA": "shots against",
            "SV%": "save percentage", "PIM": "penalty minutes",
        },
        "passing": {
            "C/ATT": "completions", "YDS": "passing yards",
            "TD": "passing touchdowns", "INT": "interceptions thrown",
            "SACKS": "sacks taken",
        },
        "rushing": {
            "CAR": "carries", "YDS": "rushing yards",
            "TD": "rushing touchdowns", "LONG": "long rush",
        },
        "receiving": {
            "REC": "receptions", "YDS": "receiving yards",
            "TD": "receiving touchdowns", "TGTS": "targets",
            "LONG": "long reception",
        },
        "fumbles": {
            "FUM": "fumbles", "LOST": "fumbles lost", "REC": "fumbles recovered",
        },
        "defensive": {
            "TOT": "tackles", "SOLO": "solo tackles", "SACKS": "sacks",
            "TFL": "tackles for loss", "PD": "passes defended",
            "QB HTS": "qb hits", "TD": "defensive touchdowns",
        },
        "interceptions": {
            "INT": "interceptions caught", "YDS": "interception yards",
            "TD": "interception touchdowns",
        },
        "kickreturns": {
            "NO": "kick returns", "YDS": "kick return yards",
            "TD": "kick return touchdowns",
        },
        "puntreturns": {
            "NO": "punt returns", "YDS": "punt return yards",
            "TD": "punt return touchdowns",
        },
        "kicking": {"FG": "field goals", "XP": "extra points", "PTS": "kicking points"},
        "punting": {"NO": "punts", "YDS": "punt yards", "In 20": "punts inside 20"},
    }

    # ESPN spells the group under `type` for baseball and under `name` for
    # football and hockey; basketball carries neither. `forwards`/`defenses`
    # duplicate the `skaters` column set.
    _GROUP_ALIASES: dict[str, str] = {
        "forwards": "skaters",
        "defenses": "skaters",
        "defense": "skaters",
    }

    # Stats that count toward double-double / triple-double
    _DD_CATEGORIES = {"points", "rebounds", "assists", "steals", "blocks"}

    @classmethod
    def _group_key(cls, stat_group: dict) -> str:
        """Normalized identity of an ESPN stat group ('batting', 'passing', …).

        Returns "" when ESPN declares no group — basketball, where a single
        unnamed group per team makes the flat map safe.
        """
        raw = stat_group.get("type") or stat_group.get("name") or ""
        if not isinstance(raw, str):
            return ""
        normalized = raw.strip().lower()
        return cls._GROUP_ALIASES.get(normalized, normalized)

    @classmethod
    def _resolve_stat_columns(
        cls, stat_group: dict, group: str, n_values: int
    ) -> list[str | None]:
        """Canonical name per column, positionally aligned with a player's stats.

        `None` marks a column to drop. Resolution order per column:
          1. group-scoped ESPN `keys` entry  — canonical, restyle-proof
          2. group-scoped display label      — when `keys` is unusable
          3. the flat legacy _STAT_NORMALIZE — un-namespaced groups only

        `keys` is used ONLY when it lines up with the value count. ESPN ships 8
        `keys` for the 7 columns of an NFL `passing` group (adjQBR + QBRating
        for one RTG column), and a blind zip there would shift every stat one
        position to the left — silently writing each player's yards under
        completions. Length equality is the whole guard.
        """
        labels = stat_group.get("names") or stat_group.get("labels") or []
        keys = stat_group.get("keys") or []
        key_map = cls._GROUP_STAT_MAP.get(group, {})
        label_map = cls._GROUP_LABEL_MAP.get(group, {})
        use_keys = bool(keys) and len(keys) == n_values and bool(key_map)

        resolved: list[str | None] = []
        for i in range(n_values):
            canonical = None
            if use_keys:
                canonical = key_map.get(keys[i])
            if canonical is None and i < len(labels):
                label = labels[i]
                if isinstance(label, str):
                    canonical = label_map.get(label)
                    if canonical is None and not key_map:
                        # Only fall through to the flat map for groups we have
                        # NOT namespaced. A namespaced group that misses a
                        # column drops it rather than borrowing another
                        # sport's meaning for the abbreviation.
                        canonical = cls._STAT_NORMALIZE.get(label.upper())
            resolved.append(canonical)
        return resolved

    def _parse_boxscore(self, summary_data: dict) -> dict:
        """Parse box score data from ESPN summary response.

        Returns dict of player_name → {stat_name: value, ...}.
        Compound stats like "10-22" (made-attempts) are parsed to extract
        the made value. Double-doubles and triple-doubles are computed.

        Group-aware since #1990: a pitcher's line and a batter's line land
        under different keys, so a consumer can no longer read hits-allowed as
        hits. See _GROUP_STAT_MAP.
        """
        players_data = {}
        boxscore = summary_data.get("boxscore", {})
        if not boxscore:
            return players_data

        for team_group in boxscore.get("players", []):
            for stat_group in team_group.get("statistics", []):
                stat_names = stat_group.get("names", []) or stat_group.get("labels", [])
                if not stat_names:
                    continue
                group = self._group_key(stat_group)
                columns = self._resolve_stat_columns(
                    stat_group, group, len(stat_names)
                )

                for athlete_entry in stat_group.get("athletes", []):
                    athlete = athlete_entry.get("athlete", {})
                    player_name = athlete.get("displayName")
                    if not player_name:
                        continue

                    raw_stats = athlete_entry.get("stats", [])
                    if len(raw_stats) != len(stat_names):
                        continue

                    parsed: dict[str, float] = {}
                    for canonical, value_str in zip(columns, raw_stats):
                        if not canonical:
                            continue

                        # Parse the value
                        val = self._parse_stat_value(value_str)
                        if val is not None:
                            parsed[canonical] = val

                    if not parsed:
                        continue

                    # Compute double-doubles and triple-doubles
                    dd_count = sum(
                        1 for cat in self._DD_CATEGORIES
                        if parsed.get(cat, 0) >= 10
                    )
                    if dd_count >= 2:
                        parsed["double doubles"] = 1
                    if dd_count >= 3:
                        parsed["triple doubles"] = 1

                    # Merge into existing entry (multiple stat groups per player)
                    if player_name in players_data:
                        players_data[player_name].update(parsed)
                    else:
                        players_data[player_name] = parsed

        return players_data

    @staticmethod
    def _parse_stat_value(value_str: str) -> float | None:
        """Parse a single stat value string from ESPN.

        Handles:
        - Simple numbers: "28" → 28.0
        - Compound stats: "10-22" or "13/22" (made-attempts) → 10.0 / 13.0
        - Percentages: ".455" → 0.455
        - Dashes/empty: "--" or "" → None
        """
        if not value_str or value_str.strip() in ("--", "-", ""):
            return None

        value_str = value_str.strip()

        # Compound stat: "10-22" → extract the made value (first number).
        # ESPN uses BOTH separators for the same made/attempted idea and which
        # one you get depends on the sport: basketball FG is "9-16", football
        # C/ATT is "13/22" and kicking FG/XP are "2/2". Only the dash was
        # handled, so every football completion, field goal and extra point
        # parsed to None and was dropped — the column was mapped the whole
        # time, which is why this never looked like a mapping gap (#1990).
        for sep in ("-", "/"):
            if sep in value_str and not value_str.startswith(sep):
                parts = value_str.split(sep)
                if len(parts) == 2:
                    try:
                        return float(parts[0])
                    except ValueError:
                        return None

        try:
            return float(value_str)
        except ValueError:
            return None

    def _parse_scoring_plays(self, summary_data: dict) -> list[dict]:
        """Parse scoring plays from ESPN summary response.

        ESPN's /summary endpoint has a `scoringPlays` key with an array of plays:
        [{
            "type": {"text": "Three Point Jumper"},
            "text": "J. Tatum makes 24-foot three point jumper",
            "shortText": "J. Tatum 24' 3PT",
            "period": {"number": 1},
            "clock": {"displayValue": "9:42"},
            "homeScore": "3",
            "awayScore": "0",
            "team": {"id": "2"}
        }]

        Returns a list of parsed play dicts ready for storage.
        """
        plays = []
        for play in summary_data.get("scoringPlays", []):
            try:
                description = play.get("text", "")
                short_text = play.get("shortText", "")
                play_type = ""
                type_data = play.get("type")
                if isinstance(type_data, dict):
                    play_type = type_data.get("text", "")
                elif isinstance(type_data, str):
                    play_type = type_data

                period_data = play.get("period", {})
                period_num = period_data.get("number") if isinstance(period_data, dict) else None

                clock_data = play.get("clock", {})
                clock_display = clock_data.get("displayValue", "") if isinstance(clock_data, dict) else ""

                home_score_str = play.get("homeScore", "")
                away_score_str = play.get("awayScore", "")
                home_score = int(home_score_str) if home_score_str else None
                away_score = int(away_score_str) if away_score_str else None

                # Team info
                team_data = play.get("team", {})
                team_name = ""
                if isinstance(team_data, dict):
                    team_name = team_data.get("displayName", "") or team_data.get("shortDisplayName", "") or ""

                plays.append({
                    "description": description,
                    "short_text": short_text,
                    "type": play_type,
                    "period": period_num,
                    "clock": clock_display,
                    "home_score": home_score,
                    "away_score": away_score,
                    "team": team_name,
                })
            except Exception as e:
                logger.debug(f"Error parsing scoring play: {e}")
                continue

        return plays

    async def get_team_roster(self, sport_key: str, team_id: str) -> Optional[list[dict]]:
        """
        Fetch roster for an ESPN team.

        Args:
            sport_key: Our internal sport key (e.g., "basketball_nba")
            team_id: ESPN team ID

        Returns:
            List of {"name": str, "position": str|None} dicts, or ``None`` when
            ESPN did not answer (authority dark — keep the stored roster).
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return []

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/teams/{team_id}/roster"

        try:
            data = await self._get(url)
        except ESPNAuthorityDark:
            return None
        if not data:
            return []

        athletes = []
        for group in data.get("athletes", []):
            # Grouped format: {"position": "Guards", "items": [...]}
            if isinstance(group, dict) and "items" in group:
                items = group["items"]
            else:
                # Flat format or single athlete dict
                items = [group] if isinstance(group, dict) else []
            for athlete in items:
                name = athlete.get("fullName") or athlete.get("displayName")
                if name:
                    pos = athlete.get("position", {})
                    pos_abbrev = pos.get("abbreviation") if isinstance(pos, dict) else None
                    entry: dict = {"name": name, "position": pos_abbrev}
                    # Extract ESPN player ID and headshot URL
                    athlete_id = str(athlete.get("id", "")) if athlete.get("id") else None
                    if athlete_id:
                        entry["espn_id"] = athlete_id
                    headshot = athlete.get("headshot", {})
                    headshot_href = headshot.get("href") if isinstance(headshot, dict) else None
                    if headshot_href:
                        entry["headshot"] = headshot_href
                    athletes.append(entry)

        logger.info(f"ESPN roster: {len(athletes)} players for team {team_id} ({sport_key})")
        return athletes

    async def search_teams(
        self,
        query: str,
        sport_key: Optional[str] = None,
    ) -> Optional[list[ESPNTeam]]:
        """
        Search for teams by name.

        Args:
            query: Search query
            sport_key: Optional sport to filter by

        Returns:
            List of matching ESPNTeam objects, or ``None`` when ESPN did not
            answer for the requested sport. In the all-sports case a dark sport
            is skipped rather than failing the whole search — a partial result
            is still an answer for the sports that did reply.
        """
        if sport_key:
            teams = await self.get_teams(sport_key)
            if teams is None:
                return None
            query_lower = query.lower()
            return [
                t for t in teams
                if query_lower in (t.name or "").lower()
                or query_lower in (t.display_name or "").lower()
                or query_lower in (t.nickname or "").lower()
                or query_lower in (t.abbreviation or "").lower()
            ]
        else:
            # Search across multiple sports
            results = []
            for key in SPORT_LEAGUE_MAP.keys():
                teams = await self.get_teams(key)
                if teams is None:
                    continue
                query_lower = query.lower()
                for t in teams:
                    if (
                        query_lower in (t.name or "").lower()
                        or query_lower in (t.display_name or "").lower()
                        or query_lower in (t.nickname or "").lower()
                    ):
                        results.append(t)
            return results


# Singleton instance
_espn_service: Optional[ESPNAPIService] = None


def get_espn_service() -> ESPNAPIService:
    """Get or create the ESPN API service singleton."""
    global _espn_service
    if _espn_service is None:
        _espn_service = ESPNAPIService()
    return _espn_service
