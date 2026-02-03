"""
The Odds API integration service.

Handles fetching odds from the-odds-api.com and transforming
the data for storage.
"""

import os
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel


class OddsSnapshot(BaseModel):
    """Represents a single odds reading for an event."""
    event_id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmaker: str

    # Moneyline
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None

    # Spread
    home_spread: Optional[float] = None
    home_spread_odds: Optional[int] = None
    away_spread_odds: Optional[int] = None

    # Totals
    over_under: Optional[float] = None
    over_odds: Optional[int] = None
    under_odds: Optional[int] = None


class FuturesOutcomeData(BaseModel):
    """Represents a single outcome in a futures market from one bookmaker."""
    name: str  # e.g., "Los Angeles Lakers"
    american_odds: int  # e.g., +1500
    probability: float  # 0.0-1.0 (calculated from odds)


class FuturesMarketData(BaseModel):
    """Represents a futures market with outcomes from one bookmaker."""
    sport_key: str  # e.g., "basketball_nba_championship"
    market_name: str  # e.g., "NBA Championship Winner"
    bookmaker: str  # e.g., "draftkings"
    outcomes: list[FuturesOutcomeData]


class OddsAPIService:
    """Service for interacting with The Odds API."""

    BASE_URL = "https://api.the-odds-api.com/v4"
    
    # Blacklisted sport prefixes - these sports are excluded from API calls
    # All other sports from the API are included
    EXCLUDED_PREFIXES = [
        "rugbyleague_",   # Rugby League
        "rugbyunion_",    # Rugby Union
    ]

    # Additional keywords to exclude (matched anywhere in sport key)
    EXCLUDED_KEYWORDS: list[str] = []
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from env or parameter."""
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise ValueError("ODDS_API_KEY not set")
        
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def get_sports(self) -> list[dict]:
        """
        Get list of available sports.
        
        Returns:
            List of sport objects with keys like:
            - key: "basketball_nba"
            - group: "Basketball"
            - title: "NBA"
            - active: True
        """
        response = await self.client.get(
            f"{self.BASE_URL}/sports",
            params={"apiKey": self.api_key}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_odds(
        self,
        sport_key: str,
        regions: str = "us,us2",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "american",
    ) -> list[dict]:
        """
        Get current odds for a sport.

        Args:
            sport_key: Sport identifier (e.g., "basketball_nba")
            regions: Bookmaker regions - comma-separated. Options:
                     "us" = Primary US bookmakers (DraftKings, FanDuel, BetMGM, etc.)
                     "us2" = Secondary US bookmakers (additional books)
                     "uk" = UK bookmakers
                     "eu" = EU bookmakers
                     "au" = Australian bookmakers
            markets: Bet types ("h2h" for moneyline, "spreads", "totals")
            odds_format: "american" or "decimal"

        Returns:
            List of events with odds from various bookmakers.
        """
        response = await self.client.get(
            f"{self.BASE_URL}/sports/{sport_key}/odds",
            params={
                "apiKey": self.api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_scores(
        self,
        sport_key: str,
        days_from: int = 1,
    ) -> list[dict]:
        """
        Get scores for a sport, including live and recently completed games.

        Args:
            sport_key: Sport identifier (e.g., "basketball_nba")
            days_from: Number of days in the past to return completed games.
                       Default 1 returns games from yesterday onwards.

        Returns:
            List of events with scores. Each event includes:
            - id: Event external ID
            - sport_key: Sport identifier
            - commence_time: Game start time
            - home_team, away_team: Team names
            - completed: Boolean indicating if game is finished
            - scores: List of {name, score} for each team (null if not started)
        """
        response = await self.client.get(
            f"{self.BASE_URL}/sports/{sport_key}/scores",
            params={
                "apiKey": self.api_key,
                "daysFrom": days_from,
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def get_all_odds(
        self, 
        sports: Optional[list[str]] = None
    ) -> list[OddsSnapshot]:
        """
        Fetch odds for multiple sports and flatten to snapshots.
        
        Args:
            sports: List of sport keys, or None for all supported sports.
        
        Returns:
            List of OddsSnapshot objects ready for database storage.
        """
        sports = sports or self.SPORTS
        all_snapshots = []
        
        for sport_key in sports:
            try:
                events = await self.get_odds(sport_key)
                snapshots = self._parse_events(events, sport_key)
                all_snapshots.extend(snapshots)
            except httpx.HTTPStatusError as e:
                # Log but continue with other sports
                print(f"Error fetching {sport_key}: {e}")
                continue
        
        return all_snapshots
    
    def _parse_events(
        self, 
        events: list[dict], 
        sport_key: str
    ) -> list[OddsSnapshot]:
        """
        Parse API response into OddsSnapshot objects.
        
        Takes one snapshot per bookmaker per event.
        """
        snapshots = []
        
        for event in events:
            event_id = event["id"]
            commence_time = datetime.fromisoformat(
                event["commence_time"].replace("Z", "+00:00")
            )
            home_team = event["home_team"]
            away_team = event["away_team"]
            
            for bookmaker in event.get("bookmakers", []):
                snapshot = OddsSnapshot(
                    event_id=event_id,
                    sport_key=sport_key,
                    commence_time=commence_time,
                    home_team=home_team,
                    away_team=away_team,
                    bookmaker=bookmaker["key"],
                )
                
                # Parse markets
                for market in bookmaker.get("markets", []):
                    market_key = market["key"]
                    outcomes = {o["name"]: o for o in market["outcomes"]}
                    
                    if market_key == "h2h":
                        # Moneyline
                        home_outcome = outcomes.get(home_team, {})
                        away_outcome = outcomes.get(away_team, {})
                        snapshot.home_moneyline = home_outcome.get("price")
                        snapshot.away_moneyline = away_outcome.get("price")
                    
                    elif market_key == "spreads":
                        # Point spread
                        home_outcome = outcomes.get(home_team, {})
                        away_outcome = outcomes.get(away_team, {})
                        snapshot.home_spread = home_outcome.get("point")
                        snapshot.home_spread_odds = home_outcome.get("price")
                        snapshot.away_spread_odds = away_outcome.get("price")
                    
                    elif market_key == "totals":
                        # Over/under
                        over_outcome = outcomes.get("Over", {})
                        under_outcome = outcomes.get("Under", {})
                        snapshot.over_under = over_outcome.get("point")
                        snapshot.over_odds = over_outcome.get("price")
                        snapshot.under_odds = under_outcome.get("price")
                
                snapshots.append(snapshot)
        
        return snapshots
    
    async def check_quota(self) -> dict:
        """
        Check remaining API quota.

        The Odds API includes quota info in response headers.
        This makes a lightweight request to check status.

        Returns:
            Dict with 'requests_remaining' and 'requests_used'
        """
        response = await self.client.get(
            f"{self.BASE_URL}/sports",
            params={"apiKey": self.api_key}
        )

        return {
            "requests_remaining": response.headers.get(
                "x-requests-remaining", "unknown"
            ),
            "requests_used": response.headers.get(
                "x-requests-used", "unknown"
            ),
        }

    async def get_sports_with_outrights(self) -> list[dict]:
        """
        Get list of sports that have outrights/futures markets available.

        Returns:
            List of sport objects that have has_outrights=True
        """
        all_sports = await self.get_sports()
        return [s for s in all_sports if s.get("has_outrights", False)]

    async def get_futures_odds(
        self,
        sport_key: str,
        regions: str = "us,us2",
        odds_format: str = "american",
    ) -> list[dict]:
        """
        Get futures/outrights odds for a sport.

        Args:
            sport_key: Sport identifier with futures (e.g., "basketball_nba_championship")
            regions: Bookmaker regions
            odds_format: "american" or "decimal"

        Returns:
            List with market data including outcomes and bookmaker odds
        """
        response = await self.client.get(
            f"{self.BASE_URL}/sports/{sport_key}/odds",
            params={
                "apiKey": self.api_key,
                "regions": regions,
                "markets": "outrights",
                "oddsFormat": odds_format,
            }
        )
        response.raise_for_status()
        return response.json()

    def _parse_futures(
        self,
        api_response: list[dict],
        sport_key: str,
    ) -> list[FuturesMarketData]:
        """
        Parse futures API response into FuturesMarketData objects.

        The Odds API returns futures as a list with one "event" that contains
        all bookmakers and their outcome odds.
        """
        from app.utils.odds_math import american_to_probability

        markets = []

        for event in api_response:
            # For futures, the "event" is actually the market itself
            # Each bookmaker has its own set of outcomes
            for bookmaker in event.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    if market["key"] != "outrights":
                        continue

                    outcomes = []
                    for outcome in market.get("outcomes", []):
                        odds = outcome.get("price")
                        if odds is None:
                            continue

                        prob = american_to_probability(odds)
                        outcomes.append(FuturesOutcomeData(
                            name=outcome["name"],
                            american_odds=odds,
                            probability=prob,
                        ))

                    if outcomes:
                        markets.append(FuturesMarketData(
                            sport_key=sport_key,
                            market_name=event.get("sport_title", sport_key),
                            bookmaker=bookmaker["key"],
                            outcomes=outcomes,
                        ))

        return markets

    async def get_all_futures(
        self,
        sport_keys: Optional[list[str]] = None,
    ) -> list[FuturesMarketData]:
        """
        Fetch futures odds for multiple sports.

        Args:
            sport_keys: List of sport keys with futures, or None to auto-discover

        Returns:
            List of FuturesMarketData objects from all bookmakers
        """
        if sport_keys is None:
            # Auto-discover sports with outrights
            outrights_sports = await self.get_sports_with_outrights()
            sport_keys = [s["key"] for s in outrights_sports]

        all_markets = []
        for sport_key in sport_keys:
            try:
                api_response = await self.get_futures_odds(sport_key)
                markets = self._parse_futures(api_response, sport_key)
                all_markets.extend(markets)
            except httpx.HTTPStatusError as e:
                print(f"Error fetching futures for {sport_key}: {e}")
                continue

        return all_markets


# Convenience function for one-off fetches
async def fetch_current_odds(sport_key: str) -> list[OddsSnapshot]:
    """Fetch current odds for a single sport."""
    service = OddsAPIService()
    try:
        events = await service.get_odds(sport_key)
        return service._parse_events(events, sport_key)
    finally:
        await service.close()
