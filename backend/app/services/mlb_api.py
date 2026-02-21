"""
MLB Stats API client for live game data and win probability.

The MLB Stats API (statsapi.mlb.com) is MLB's official data API. It provides
free, no-auth-required access to schedules, live game feeds, and — crucially —
play-by-play win probability data.

Key endpoints:
- Schedule: GET /api/v1/schedule?sportId=1&date=YYYY-MM-DD
- Live feed: GET /api/v1.1/game/{gamePk}/feed/live
- Win probability: GET /api/v1/game/{gamePk}/winProbability
- Context metrics: GET /api/v1/game/{gamePk}/contextMetrics

No API key required. Rate limits are generous (~1000+ req/hr).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://statsapi.mlb.com/api"


@dataclass
class MLBGame:
    """A live MLB game with win probability data."""
    game_pk: int
    home_team: str  # e.g., "New York Yankees"
    away_team: str  # e.g., "Boston Red Sox"
    home_team_id: int
    away_team_id: int
    home_win_probability: float  # 0.0-1.0
    away_win_probability: float  # 0.0-1.0
    status: str  # "In Progress", "Final", "Scheduled", etc.
    inning: Optional[int] = None
    inning_half: Optional[str] = None  # "top" or "bottom"
    outs: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    game_datetime: Optional[str] = None  # ISO 8601 UTC


@dataclass
class MLBWinProbEntry:
    """A single point in the win probability timeline."""
    home_win_probability: float  # 0.0-1.0
    away_win_probability: float  # 0.0-1.0
    at_bat_index: int
    inning: int
    inning_half: str  # "top" or "bottom"
    description: Optional[str] = None


class MLBAPIService:
    """
    Client for MLB's Stats API.

    Usage:
        service = MLBAPIService()
        try:
            games = await service.get_live_games()
            for game in games:
                wp = await service.get_win_probability(game.game_pk)
        finally:
            await service.close()
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=15.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "BainLuck/1.0 (sports odds visualization)",
            },
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_todays_games(self, date: Optional[str] = None) -> list[dict]:
        """
        Fetch today's MLB schedule.

        Args:
            date: Optional date in YYYY-MM-DD format. Defaults to today.

        Returns:
            List of raw game dicts from the MLB API schedule response.
        """
        params = {"sportId": 1}
        if date:
            params["date"] = date

        try:
            resp = await self.client.get("/v1/schedule", params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"MLB schedule fetch failed: {e}")
            return []

        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                games.append(game)
        return games

    async def get_live_games(self) -> list[MLBGame]:
        """
        Fetch all currently live MLB games with current win probability.

        Returns list of MLBGame objects for games with status "In Progress".
        Uses the live feed endpoint which includes linescore data.
        """
        raw_games = await self.get_todays_games()

        live_games = []
        for g in raw_games:
            status_code = g.get("status", {}).get("statusCode", "")
            # "I" = In Progress, "IR" = In Review
            if status_code not in ("I", "IR"):
                continue

            game_pk = g.get("gamePk")
            if not game_pk:
                continue

            teams = g.get("teams", {})
            home = teams.get("home", {}).get("team", {})
            away = teams.get("away", {}).get("team", {})

            home_score = teams.get("home", {}).get("score")
            away_score = teams.get("away", {}).get("score")

            # Get win probability from context metrics
            wp_home = None
            try:
                wp_home = await self._get_context_win_probability(game_pk)
            except Exception as e:
                logger.warning(f"Failed to get win prob for game {game_pk}: {e}")

            if wp_home is None:
                continue

            # Get inning info from linescore
            linescore = g.get("linescore", {})
            inning = linescore.get("currentInning")
            inning_half = linescore.get("inningHalf", "").lower() or None

            game = MLBGame(
                game_pk=game_pk,
                home_team=home.get("name", "Unknown"),
                away_team=away.get("name", "Unknown"),
                home_team_id=home.get("id", 0),
                away_team_id=away.get("id", 0),
                home_win_probability=wp_home,
                away_win_probability=round(1.0 - wp_home, 4),
                status="In Progress",
                inning=inning,
                inning_half=inning_half,
                home_score=home_score,
                away_score=away_score,
                game_datetime=g.get("gameDate"),
            )
            live_games.append(game)

        logger.info(f"MLB API: found {len(live_games)} live games with win probability")
        return live_games

    async def _get_context_win_probability(self, game_pk: int) -> Optional[float]:
        """
        Get the current win probability from the context metrics endpoint.

        Returns home team win probability as a float (0.0-1.0), or None.
        """
        try:
            resp = await self.client.get(f"/v1/game/{game_pk}/contextMetrics")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"MLB context metrics failed for {game_pk}: {e}")
            return None

        # The contextMetrics response has a "game" object with win probability
        # Try common paths where win probability is stored
        game_data = data.get("game", data)

        # Try homeWinProbability directly
        home_wp = game_data.get("homeWinProbability")
        if home_wp is not None:
            return float(home_wp) / 100.0  # MLB API returns percentages

        # Fallback: try currentPlay or probabilities
        for key in ("currentPlay", "probabilities"):
            sub = game_data.get(key, {})
            if isinstance(sub, dict):
                home_wp = sub.get("homeWinProbability")
                if home_wp is not None:
                    return float(home_wp) / 100.0

        logger.warning(f"Could not parse win probability from contextMetrics for {game_pk}")
        return None

    async def get_win_probability_history(self, game_pk: int) -> list[MLBWinProbEntry]:
        """
        Get the full play-by-play win probability history for a game.

        Args:
            game_pk: MLB game primary key.

        Returns:
            List of MLBWinProbEntry objects, one per at-bat.
        """
        try:
            resp = await self.client.get(f"/v1/game/{game_pk}/winProbability")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"MLB win probability history failed for {game_pk}: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"Unexpected win probability response type for {game_pk}: {type(data)}")
            return []

        entries = []
        for item in data:
            home_wp = item.get("homeTeamWinProbability")
            away_wp = item.get("awayTeamWinProbability")
            if home_wp is None:
                continue

            about = item.get("about", {})
            entries.append(MLBWinProbEntry(
                home_win_probability=float(home_wp) / 100.0,
                away_win_probability=float(away_wp) / 100.0 if away_wp is not None else round(1.0 - float(home_wp) / 100.0, 4),
                at_bat_index=item.get("atBatIndex", 0),
                inning=about.get("inning", 0),
                inning_half=about.get("halfInning", "top"),
                description=item.get("result", {}).get("description"),
            ))

        return entries

    async def find_game_pk_for_teams(
        self,
        home_team_name: str,
        away_team_name: str,
        date: Optional[str] = None,
    ) -> Optional[int]:
        """
        Find the gamePk for a game by team names.

        Uses fuzzy substring matching on team names.

        Args:
            home_team_name: Home team name (e.g., "Boston Red Sox" or "Red Sox")
            away_team_name: Away team name
            date: Optional date in YYYY-MM-DD format

        Returns:
            gamePk if found, None otherwise.
        """
        raw_games = await self.get_todays_games(date=date)

        home_lower = home_team_name.lower()
        away_lower = away_team_name.lower()

        for game in raw_games:
            teams = game.get("teams", {})
            api_home = teams.get("home", {}).get("team", {}).get("name", "").lower()
            api_away = teams.get("away", {}).get("team", {}).get("name", "").lower()

            # Check both orderings since our home/away might not match MLB's
            if (_name_matches(home_lower, api_home) and _name_matches(away_lower, api_away)):
                return game.get("gamePk")
            if (_name_matches(home_lower, api_away) and _name_matches(away_lower, api_home)):
                return game.get("gamePk")

        return None


def _name_matches(our_name: str, mlb_name: str) -> bool:
    """
    Check if our team name matches the MLB API team name.

    Handles cases like:
    - "Boston Red Sox" matching "Boston Red Sox"
    - "Red Sox" matching "Boston Red Sox"
    - "New York Yankees" matching "New York Yankees"
    """
    if not our_name or not mlb_name:
        return False
    # Exact match
    if our_name == mlb_name:
        return True
    # Our name is a suffix of MLB name (e.g., "Red Sox" in "Boston Red Sox")
    if mlb_name.endswith(our_name):
        return True
    # Our name contains the MLB mascot (last word)
    mlb_parts = mlb_name.split()
    if len(mlb_parts) >= 2:
        mascot = mlb_parts[-1]  # e.g., "Sox", "Yankees"
        if mascot in our_name:
            return True
    # MLB name is contained in our name
    if mlb_name in our_name:
        return True
    return False
