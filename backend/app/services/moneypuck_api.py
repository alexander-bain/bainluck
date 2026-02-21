"""
MoneyPuck API client for NHL win probability data.

MoneyPuck (moneypuck.com) provides real-time NHL win probabilities based on
their statistical model using shot metrics, expected goals (xG), and game state.

API: MoneyPuck publishes live game data as JSON files on their CDN.
No API key required. Data updates every ~30 seconds during live games.

Endpoints:
- https://moneypuck.com/moneypuck/playerData/careers/gameByGame/all_teams.csv (historical)
- Live games: scraped from moneypuck.com/g.htm?id={game_id} or via their data feeds

NOTE: This is a stub implementation. The actual API integration requires
research into MoneyPuck's current data feed format. The structure follows
the established pattern from ESPN and Kalshi integrations.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MoneyPuckGame:
    """Parsed MoneyPuck live game data."""
    game_id: str
    home_team: str
    away_team: str
    home_win_probability: float  # 0.0-1.0
    away_win_probability: float  # 0.0-1.0
    period: Optional[str] = None
    time_remaining: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_xg: Optional[float] = None  # Expected goals
    away_xg: Optional[float] = None


class MoneyPuckAPIService:
    """
    Client for fetching NHL win probabilities from MoneyPuck.

    Usage:
        service = MoneyPuckAPIService()
        try:
            games = await service.get_live_games()
            for game in games:
                print(f"{game.home_team} vs {game.away_team}: {game.home_win_probability:.1%}")
        finally:
            await service.close()
    """

    # MoneyPuck serves data via CDN — no auth required
    BASE_URL = "https://moneypuck.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "BainLuck/1.0 (sports odds visualization)",
            },
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_live_games(self) -> list[MoneyPuckGame]:
        """
        Fetch live NHL games with win probabilities.

        Returns list of MoneyPuckGame objects for currently live games.

        NOTE: Stub implementation — needs actual MoneyPuck API research.
        MoneyPuck may serve data via:
        1. JSON data feed on their CDN
        2. CSV exports updated in real-time
        3. WebSocket or polling endpoint

        The integration should:
        - Fetch live game data every 2 minutes
        - Parse home/away win probability
        - Include game state (period, time, score, xG)
        - Handle timezone differences (games in EST/CST/PST)
        """
        logger.warning("MoneyPuck API integration not yet implemented — stub returning empty list")
        return []

    async def get_game_by_id(self, game_id: str) -> Optional[MoneyPuckGame]:
        """Fetch a specific game by its MoneyPuck game ID."""
        logger.warning("MoneyPuck get_game_by_id not yet implemented")
        return None
