"""
DataGolf API integration service.

Provides live in-play finish probabilities, pre-tournament model predictions,
tournament schedules, field updates, and outright odds from 11+ sportsbooks.

API docs: https://datagolf.com/api-access
Plan: Scratch Plus ($30/mo)
"""

import logging
import os
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class DataGolfPlayer(BaseModel):
    """A single player's probability and leaderboard data."""
    dg_id: int
    player_name: str  # "Scheffler, Scottie" → normalized to "Scottie Scheffler"

    # Probabilities (0-1 scale, nullable — not all endpoints return all fields)
    win: Optional[float] = None
    top_5: Optional[float] = None
    top_10: Optional[float] = None
    top_20: Optional[float] = None
    make_cut: Optional[float] = None

    # Leaderboard state (only from in-play endpoint)
    position: Optional[str] = None  # "T3", "1", "CUT"
    total_score: Optional[int] = None  # e.g., -12
    today_score: Optional[int] = None  # e.g., -3
    thru: Optional[str] = None  # "F", "12", "—"
    current_round: Optional[int] = None  # 1-4


class DataGolfTournament(BaseModel):
    """A tournament from the schedule endpoint."""
    event_id: str  # DataGolf's internal event ID
    event_name: str
    course: Optional[str] = None
    start_date: Optional[str] = None  # "2026-04-10"
    end_date: Optional[str] = None  # Computed: start_date + 3 days (not in API)
    status: Optional[str] = None  # "completed", "in-progress", "upcoming", etc.
    tour: str  # "pga", "euro", "kft", "liv", etc.
    current_round: Optional[int] = None
    location: Optional[str] = None  # "Honolulu, HI"
    country: Optional[str] = None


class DataGolfOddsPlayer(BaseModel):
    """A single player's odds from the outright-odds endpoint."""
    dg_id: int
    player_name: str
    datagolf_model: Optional[float] = None  # Model-predicted probability
    # Sportsbook odds keyed by book name → probability
    sportsbook_odds: dict[str, Optional[float]] = {}


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_player_name(name: str) -> str:
    """Normalize DataGolf 'Last, First' format to 'First Last'.

    Also strips diacritics for cross-source matching.
    Examples:
        'Scheffler, Scottie' → 'Scottie Scheffler'
        'Hovland, Viktor'    → 'Viktor Hovland'
        'Skarsgård, Gustav'  → 'Gustav Skarsgard'
    """
    if not name:
        return name

    # Split on comma if present
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"

    return strip_diacritics(name).strip()


# Characters that NFD decomposition doesn't handle (e.g., ø, đ, ł)
_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def strip_diacritics(s: str) -> str:
    """Remove diacritical marks and transliterate special letters for cross-source matching."""
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# API service
# ---------------------------------------------------------------------------

class DataGolfAPIService:
    """Service for interacting with DataGolf's API."""

    BASE_URL = "https://feeds.datagolf.com"

    # Supported tours
    TOURS = ["pga", "euro", "kft", "liv", "opp", "alt"]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DATAGOLF_API_KEY")
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # -- Core HTTP helper --------------------------------------------------

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        """Authenticated GET request with ?key=API_KEY."""
        if not self.api_key:
            raise ValueError("DATAGOLF_API_KEY not configured")

        params = params or {}
        params["key"] = self.api_key
        params["file_format"] = "json"

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("DataGolf rate limited on %s", endpoint)
            raise
        except httpx.ReadTimeout:
            logger.warning("DataGolf timeout on %s", endpoint)
            raise

    # -- In-play predictions -----------------------------------------------

    async def get_in_play(self, tour: str = "pga") -> list[DataGolfPlayer]:
        """Fetch live in-play finish probabilities + leaderboard positions.

        Returns an empty list when no tournament is in play.
        """
        try:
            data = await self._get("preds/in-play", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []  # No in-play event
            raise

        return self._parse_players(data, in_play=True)

    # -- Pre-tournament predictions ----------------------------------------

    async def get_pre_tournament(self, tour: str = "pga") -> list[DataGolfPlayer]:
        """Fetch pre-tournament model predictions.

        Returns probabilities for all players in the field before the event starts.
        """
        try:
            data = await self._get("preds/pre-tournament", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

        return self._parse_players(data, in_play=False)

    # -- Schedule ----------------------------------------------------------

    async def get_schedule(
        self,
        tour: str = "pga",
        season: Optional[int] = None,
    ) -> list[DataGolfTournament]:
        """Fetch tournament schedule for a tour."""
        params = {"tour": tour}
        if season:
            params["season"] = str(season)

        data = await self._get("get-schedule", params)

        schedule = data.get("schedule", [])
        result = []
        for entry in schedule:
            start = entry.get("start_date")
            # Compute end_date as start + 3 days (standard 4-day PGA event)
            end = None
            if start:
                try:
                    from datetime import timedelta as td
                    end = (datetime.strptime(start, "%Y-%m-%d") + td(days=3)).strftime("%Y-%m-%d")
                except ValueError:
                    pass

            result.append(DataGolfTournament(
                event_id=str(entry.get("event_id", "")),
                event_name=entry.get("event_name", ""),
                course=entry.get("course"),
                start_date=start,
                end_date=end,
                status=entry.get("status"),
                tour=tour,
                current_round=entry.get("current_round"),
                location=entry.get("location"),
                country=entry.get("country"),
            ))
        return result

    # -- Field updates -----------------------------------------------------

    async def get_field_updates(self, tour: str = "pga") -> dict:
        """Fetch field, withdrawals, and tee times for upcoming/in-play event.

        Returns raw dict with 'field' array and event metadata.
        """
        try:
            return await self._get("field-updates", {"tour": tour})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"field": []}
            raise

    # -- Outright odds (sportsbook comparison) -----------------------------

    async def get_outright_odds(
        self,
        tour: str = "pga",
        market: str = "win",
        odds_format: str = "decimal",
    ) -> list[DataGolfOddsPlayer]:
        """Fetch odds from 11+ sportsbooks + DataGolf model.

        market: 'win', 'top_5', 'top_10', 'top_20', 'make_cut'
        """
        data = await self._get("betting-tools/outrights", {
            "tour": tour,
            "market": market,
            "odds_format": odds_format,
        })

        players = []
        odds_data = data.get("odds", [])
        books = data.get("books", [])  # List of sportsbook names

        for entry in odds_data:
            name = normalize_player_name(entry.get("player_name", ""))
            dg_id = entry.get("dg_id", 0)

            # Model prediction
            model_prob = None
            baseline = entry.get("datagolf_base_history_fit")
            if baseline is not None:
                try:
                    model_prob = 1.0 / float(baseline) if float(baseline) > 0 else None
                except (ValueError, ZeroDivisionError):
                    pass

            # Sportsbook odds (decimal → probability)
            sportsbook_odds = {}
            for book in books:
                val = entry.get(book)
                if val is not None:
                    try:
                        decimal_odds = float(val)
                        if decimal_odds > 0:
                            sportsbook_odds[book] = 1.0 / decimal_odds
                    except (ValueError, ZeroDivisionError):
                        pass

            players.append(DataGolfOddsPlayer(
                dg_id=dg_id,
                player_name=name,
                datagolf_model=model_prob,
                sportsbook_odds=sportsbook_odds,
            ))

        return players

    # -- Internal parser ---------------------------------------------------

    def _parse_players(self, data: dict, in_play: bool = False) -> list[DataGolfPlayer]:
        """Parse player data from prediction endpoints.

        The in-play endpoint uses "data" as the key for player entries.
        The pre-tournament endpoint uses "baseline" (or "baseline_history_fit").
        We try all known keys to find the player list.
        """
        players = []
        raw_players = (
            data.get("data", [])
            or data.get("baseline_history_fit", [])
            or data.get("baseline", [])
        )

        # Some endpoints use top-level event info
        event_round = data.get("current_round")

        for entry in raw_players:
            name = normalize_player_name(entry.get("player_name", ""))
            dg_id = entry.get("dg_id", 0)

            player = DataGolfPlayer(
                dg_id=dg_id,
                player_name=name,
                win=_safe_prob(entry, "win_prob") or _safe_prob(entry, "win"),
                top_5=_safe_prob(entry, "top_5_prob") or _safe_prob(entry, "top_5"),
                top_10=_safe_prob(entry, "top_10_prob") or _safe_prob(entry, "top_10"),
                top_20=_safe_prob(entry, "top_20_prob") or _safe_prob(entry, "top_20"),
                make_cut=_safe_prob(entry, "make_cut_prob") or _safe_prob(entry, "make_cut"),
            )

            if in_play:
                player.position = entry.get("current_pos") or entry.get("position")
                player.total_score = _safe_int(entry.get("total"))
                player.today_score = _safe_int(entry.get("today"))
                player.thru = str(entry.get("thru", "")) or None
                player.current_round = event_round or _safe_int(entry.get("current_round"))

            players.append(player)

        return players


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_prob(d: dict, key: str) -> Optional[float]:
    """Safely extract a probability value from a dict entry."""
    val = d.get(key)
    if val is None:
        return None
    try:
        f = float(val)
        return f if 0.0 <= f <= 1.0 else None
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    """Safely parse an integer, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

async def fetch_datagolf_in_play(tour: str = "pga") -> list[DataGolfPlayer]:
    """One-off fetch of live in-play predictions."""
    service = DataGolfAPIService()
    try:
        return await service.get_in_play(tour)
    finally:
        await service.close()
