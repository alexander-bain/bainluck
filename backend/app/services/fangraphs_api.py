"""
FanGraphs API client for MLB win probability data.

FanGraphs (fangraphs.com) provides real-time MLB win probabilities based on
their sabermetric model using run expectancy, leverage index, and game state.

API: FanGraphs has an undocumented JSON API used by their live game pages.
No API key required. Data updates on every pitch during live games.

Endpoints (undocumented, reverse-engineered):
- https://www.fangraphs.com/api/win-probability/game-data?gameId={id}
- Live scoreboard: https://www.fangraphs.com/livescoreboard.aspx (HTML)
- Game page: https://www.fangraphs.com/livewins.aspx?date=YYYY-MM-DD&team=TeamName

NOTE: This is a stub implementation. The actual API integration requires
research into FanGraphs' current data feed format. Their ToS should be
reviewed before scraping — they may have rate limits or restrictions.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FanGraphsGame:
    """Parsed FanGraphs live game data."""
    game_id: str
    home_team: str
    away_team: str
    home_win_probability: float  # 0.0-1.0
    away_win_probability: float  # 0.0-1.0
    inning: Optional[int] = None
    inning_half: Optional[str] = None  # "top" or "bottom"
    outs: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    runners_on_base: Optional[str] = None  # e.g., "1B,3B"
    leverage_index: Optional[float] = None


class FanGraphsAPIService:
    """
    Client for fetching MLB win probabilities from FanGraphs.

    Usage:
        service = FanGraphsAPIService()
        try:
            games = await service.get_live_games()
            for game in games:
                print(f"{game.home_team} vs {game.away_team}: {game.home_win_probability:.1%}")
        finally:
            await service.close()
    """

    BASE_URL = "https://www.fangraphs.com"

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

    async def get_live_games(self) -> list[FanGraphsGame]:
        """
        Fetch live MLB games with win probabilities.

        Returns list of FanGraphsGame objects for currently live games.

        NOTE: Stub implementation — needs actual FanGraphs API research.
        FanGraphs may serve data via:
        1. Undocumented JSON API (used by their live game pages)
        2. The win probability chart data endpoint
        3. Baseball Savant / MLB Stats API as alternative

        The integration should:
        - Fetch live game data every 2 minutes
        - Parse home/away win probability
        - Include game state (inning, outs, runners, score)
        - Include leverage index (key FanGraphs metric)
        - Handle MLB's complex game states (extras, rain delays)
        """
        logger.warning("FanGraphs API integration not yet implemented — stub returning empty list")
        return []

    async def get_game_by_id(self, game_id: str) -> Optional[FanGraphsGame]:
        """Fetch a specific game by its FanGraphs game ID."""
        logger.warning("FanGraphs get_game_by_id not yet implemented")
        return None
