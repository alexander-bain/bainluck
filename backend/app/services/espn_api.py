"""
ESPN API client for fetching team data, live scores, and win probabilities.

Uses ESPN's undocumented public API endpoints.
These endpoints are used by many applications but are not officially supported,
so they may change without notice. We implement conservative rate limiting and
graceful fallbacks.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Base URLs for ESPN API
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_CORE_API = "https://sports.core.api.espn.com/v2/sports"

# Mapping from our sport keys to ESPN sport/league paths
SPORT_LEAGUE_MAP = {
    # Football
    "americanfootball_nfl": ("football", "nfl"),
    "americanfootball_ncaaf": ("football", "college-football"),
    "americanfootball_cfl": ("football", "cfl"),
    # Basketball
    "basketball_nba": ("basketball", "nba"),
    "basketball_wnba": ("basketball", "wnba"),
    "basketball_ncaab": ("basketball", "mens-college-basketball"),
    "basketball_wncaab": ("basketball", "womens-college-basketball"),
    # Baseball
    "baseball_mlb": ("baseball", "mlb"),
    # Hockey
    "icehockey_nhl": ("hockey", "nhl"),
    # Soccer
    "soccer_epl": ("soccer", "eng.1"),
    "soccer_usa_mls": ("soccer", "usa.1"),
    "soccer_uefa_champs_league": ("soccer", "uefa.champions"),
    # Golf
    "golf_pga": ("golf", "pga"),
    "golf_lpga": ("golf", "lpga"),
    # Tennis
    "tennis_atp": ("tennis", "atp"),
    "tennis_wta": ("tennis", "wta"),
    # MMA
    "mma_ufc": ("mma", "ufc"),
}


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


class ESPNAPIService:
    """Client for ESPN's public API endpoints."""

    def __init__(self, timeout: float = 10.0, rate_limit_delay: float = 0.5):
        """
        Initialize ESPN API client.

        Args:
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests in seconds
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": "OddsTracker/1.0",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str) -> Optional[dict]:
        """Make a GET request with rate limiting and error handling."""
        try:
            client = await self._get_client()
            response = await client.get(url)

            if response.status_code == 429:
                logger.warning(f"ESPN API rate limited, waiting before retry")
                await asyncio.sleep(5)
                response = await client.get(url)

            if response.status_code != 200:
                logger.warning(f"ESPN API returned {response.status_code} for {url}")
                return None

            await asyncio.sleep(self.rate_limit_delay)
            return response.json()

        except httpx.TimeoutException:
            logger.warning(f"ESPN API timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"ESPN API error: {e}")
            return None

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

    async def get_teams(self, sport_key: str) -> list[ESPNTeam]:
        """
        Get all teams for a sport/league.

        Args:
            sport_key: Our internal sport key (e.g., "basketball_nba")

        Returns:
            List of ESPNTeam objects
        """
        path = self._get_espn_path(sport_key)
        if not path:
            logger.warning(f"No ESPN mapping for sport key: {sport_key}")
            return []

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/teams?limit=100"

        data = await self._get(url)
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
            ESPNTeam object or None
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/teams/{team_id}"

        data = await self._get(url)
        if not data:
            return None

        return self._parse_team(data.get("team", data))

    async def get_scoreboard(self, sport_key: str, date: Optional[str] = None) -> list[ESPNEvent]:
        """
        Get scoreboard (list of games) for a sport/league.

        Args:
            sport_key: Our internal sport key
            date: Optional date in YYYYMMDD format (defaults to today)

        Returns:
            List of ESPNEvent objects
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return []

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/scoreboard"
        if date:
            url += f"?dates={date}"

        data = await self._get(url)
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
                status = status_name

            # Parse teams
            home_team = None
            away_team = None
            home_score = None
            away_score = None

            for competitor in competition.get("competitors", []):
                team = self._parse_team(competitor)
                score = competitor.get("score")
                if score:
                    try:
                        score = int(score)
                    except (ValueError, TypeError):
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

            # Parse date
            date_str = event_data.get("date")
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None

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
            ESPNEvent object or None
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/summary?event={event_id}"

        data = await self._get(url)
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
            List of {time, home_win_probability} dicts, or None
        """
        path = self._get_espn_path(sport_key)
        if not path:
            return None

        sport, league = path
        url = f"{ESPN_API_BASE}/{sport}/{league}/summary?event={event_id}"

        data = await self._get(url)
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

    async def search_teams(
        self,
        query: str,
        sport_key: Optional[str] = None,
    ) -> list[ESPNTeam]:
        """
        Search for teams by name.

        Args:
            query: Search query
            sport_key: Optional sport to filter by

        Returns:
            List of matching ESPNTeam objects
        """
        if sport_key:
            teams = await self.get_teams(sport_key)
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
