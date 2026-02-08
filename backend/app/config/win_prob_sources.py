"""
Win probability source registry.

Each source has metadata used by the API and frontend for display.
Source type determines visual treatment:
  - "market": solid line (betting consensus from real money)
  - "model": dashed line (computed from game state)
"""

WIN_PROB_SOURCES = {
    "betting": {
        "display_name": "Betting Consensus",
        "source_type": "market",
        "sports": ["*"],
        "color": "#374151",
        "dash_pattern": None,
        "description": "Consensus probability from sportsbook odds",
    },
    "espn": {
        "display_name": "ESPN",
        "source_type": "model",
        "sports": [
            "basketball_nba", "basketball_ncaab", "basketball_wncaab",
            "football_nfl", "football_ncaaf",
            "hockey_nhl", "baseball_mlb", "soccer_usa_mls",
            "soccer_epl",
        ],
        "color": "#f97316",
        "dash_pattern": "6 3",
        "description": "ESPN's predictive win probability model",
    },
    "stat_model": {
        "display_name": "Statistical Model",
        "source_type": "model",
        "sports": [
            "football_nfl", "football_ncaaf",
            "basketball_nba", "basketball_ncaab",
        ],
        "color": "#8b5cf6",
        "dash_pattern": "4 4",
        "description": "Score + time + spread based win probability (nflfastR-inspired)",
    },
}


def get_source_meta(source_key: str) -> dict | None:
    """Get metadata for a source, or None if unknown."""
    return WIN_PROB_SOURCES.get(source_key)


def get_active_sources() -> dict:
    """Get all configured sources."""
    return WIN_PROB_SOURCES
