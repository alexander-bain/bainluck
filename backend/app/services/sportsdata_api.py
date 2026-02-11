"""SportsDataIO API client for roster and player data."""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# SportsDataIO sport key → API path segment mapping
# Our sport keys use format "basketball_nba", SportsDataIO uses "nba"
# Static abbreviation overrides: SportsDataIO abbrev → our DB abbreviation.
# Only entries where the abbreviations DIFFER need to be listed here.
# If a SportsDataIO abbrev isn't in the override map, it's used as-is.
# Update this if teams move, rebrand, or new expansion teams are added.
SPORTSDATA_ABBREV_OVERRIDES: dict[str, dict[str, str]] = {
    "nfl": {
        "ARI": "AZ",     # Arizona Cardinals
        "JAX": "JAC",    # Jacksonville Jaguars
        "LAR": "LA",     # Los Angeles Rams
        "WAS": "WSH",    # Washington Commanders
    },
}

SPORTSDATA_SPORT_MAPPING = {
    "basketball_nba": "nba",
    "basketball_ncaab": "cbb",
    "basketball_wncaab": "cbb",
    "americanfootball_nfl": "nfl",
    "americanfootball_ncaaf": "cfb",
    "icehockey_nhl": "nhl",
    "baseball_mlb": "mlb",
    "soccer_usa_mls": "soccer",
}

# API version per sport (most use v3)
SPORTSDATA_API_VERSION = {
    "nba": "v3",
    "nfl": "v3",
    "nhl": "v3",
    "mlb": "v3",
    "cbb": "v3",
    "cfb": "v3",
    "soccer": "v4",
}


class SportsDataIOService:
    """Client for SportsDataIO API — rosters, players, injuries, scores."""

    BASE_URL = "https://api.sportsdata.io"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SPORTSDATA_API_KEY")
        if not self.api_key:
            logger.warning("SPORTSDATA_API_KEY not set — SportsDataIO features disabled")
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Ocp-Apim-Subscription-Key": self.api_key or ""},
        )

    async def close(self):
        await self.client.aclose()

    def _url(self, sport: str, path: str) -> str:
        """Build API URL for a given sport and endpoint path."""
        version = SPORTSDATA_API_VERSION.get(sport, "v3")
        return f"{self.BASE_URL}/{version}/{sport}/scores/json/{path}"

    async def _get(self, sport: str, path: str) -> list | dict | None:
        """Make authenticated GET request. Returns parsed JSON or None on error."""
        if not self.api_key:
            return None
        url = self._url(sport, path)
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"SportsDataIO HTTP {e.response.status_code} for {url}")
            return None
        except Exception as e:
            logger.error(f"SportsDataIO error for {url}: {e}")
            return None

    async def fetch_players_by_team(self, sport: str, team_abbrev: str) -> list[dict]:
        """Fetch active players for a specific team.

        Args:
            sport: SportsDataIO sport key (e.g., "nba", "nfl")
            team_abbrev: Team abbreviation (e.g., "BOS", "LAL")

        Returns:
            List of player dicts with keys: name, first_name, last_name, position, jersey
        """
        data = await self._get(sport, f"Players/{team_abbrev}")
        if not data or not isinstance(data, list):
            return []

        players = []
        for p in data:
            if p.get("Status") != "Active":
                continue
            first = p.get("FirstName", "")
            last = p.get("LastName", "")
            if not first or not last:
                continue

            # Use DraftKingsName for ASCII-safe variant (no diacritics)
            dk_name = p.get("DraftKingsName") or ""

            players.append({
                "name": f"{first} {last}",
                "first_name": first,
                "last_name": last,
                "ascii_name": dk_name,
                "position": p.get("Position"),
                "jersey": p.get("Jersey"),
                "sportsdata_id": p.get("PlayerID"),
            })

        return players

    async def fetch_all_players(self, sport: str) -> list[dict]:
        """Fetch all active players for a sport.

        Returns list of dicts with: name, ascii_name, team_abbrev, position
        """
        data = await self._get(sport, "Players")
        if not data or not isinstance(data, list):
            return []

        players = []
        for p in data:
            if p.get("Status") != "Active":
                continue
            first = p.get("FirstName", "")
            last = p.get("LastName", "")
            team = p.get("Team")
            if not first or not last or not team:
                continue

            dk_name = p.get("DraftKingsName") or ""

            players.append({
                "name": f"{first} {last}",
                "ascii_name": dk_name,
                "team_abbrev": team,
                "position": p.get("Position"),
                "sportsdata_id": p.get("PlayerID"),
            })

        return players

    async def fetch_teams(self, sport: str) -> list[dict]:
        """Fetch all teams for a sport.

        Returns list of dicts with: key, city, name, conference, division
        """
        data = await self._get(sport, "AllTeams")
        if not data or not isinstance(data, list):
            return []

        return [
            {
                "team_id": t.get("TeamID"),
                "key": t.get("Key"),
                "city": t.get("City"),
                "name": t.get("Name"),
                "full_name": f"{t.get('City', '')} {t.get('Name', '')}".strip(),
                "conference": t.get("Conference"),
                "division": t.get("Division"),
                "primary_color": t.get("PrimaryColor"),
                "head_coach": t.get("HeadCoach"),
            }
            for t in data
            if t.get("Active")
        ]

    @staticmethod
    def get_sportsdata_sport(our_sport_key: str) -> Optional[str]:
        """Map our sport key to SportsDataIO sport key.

        Returns None if sport is not supported.
        """
        return SPORTSDATA_SPORT_MAPPING.get(our_sport_key)

    @staticmethod
    def supported_sport_keys() -> list[str]:
        """Return list of our sport keys that have SportsDataIO mapping."""
        return list(SPORTSDATA_SPORT_MAPPING.keys())
