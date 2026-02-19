"""
Win probability source registry.

Each source has metadata used by the API and frontend for display.
Source type determines visual treatment:
  - "market": solid line (betting consensus from real money)
  - "model": dashed line (computed from game state)
"""

WIN_PROB_SOURCES = {
    "betting": {
        "display_name": "Betting Odds",
        "source_type": "market",
        "sports": ["*"],
        "color": "#374151",
        "dash_pattern": None,
        "description": "Consensus win probability derived from sportsbook moneyline odds, aggregated across multiple bookmakers by The Odds API.",
        "methodology": "Moneyline odds from each bookmaker are converted to implied probabilities, then the vig (overround) is removed. The median probability across all reporting bookmakers is used as the consensus.",
        "attribution_url": "https://the-odds-api.com",
        "attribution_name": "The Odds API",
    },
    "espn": {
        "display_name": "ESPN",
        "source_type": "model",
        "sports": [
            "basketball_nba", "basketball_ncaab", "basketball_wncaab",
            "americanfootball_nfl", "americanfootball_ncaaf",
            "icehockey_nhl", "baseball_mlb", "soccer_usa_mls",
            "soccer_epl",
        ],
        "color": "#f97316",
        "dash_pattern": "6 3",
        "description": "ESPN's proprietary predictive model that updates on every play during live games. Uses game situation data including score, field position, down, distance, and time remaining.",
        "methodology": "ESPN's internal win probability model, same data shown on ESPN.com game pages. Methodology is not publicly documented.",
        "attribution_url": "https://www.espn.com",
        "attribution_name": "ESPN",
    },
    "stat_model": {
        "display_name": "Bain Luck Model",
        "source_type": "model",
        "sports": [
            "americanfootball_nfl", "americanfootball_ncaaf",
            "basketball_nba", "basketball_ncaab", "basketball_wncaab",
            "icehockey_nhl",
        ],
        "color": "#8b5cf6",
        "dash_pattern": "4 4",
        "description": "An open win probability model inspired by nflfastR and Pro-Football-Reference. Uses current score, time remaining, and the pregame Vegas spread to estimate win probability via a normal distribution model.",
        "methodology": "Based on the methodology from Hal Stern's research and Wayne Winston's Mathletics. The final margin of victory is modeled as a normal distribution where: (1) the mean equals the current score differential plus the pregame spread scaled by remaining game fraction, and (2) the standard deviation equals a sport-specific base value (NFL: 13.45 points) multiplied by the square root of the remaining game fraction. Win probability is then P(final margin > 0) using the normal CDF. Sport-specific parameters: NFL/NCAAF base_std=13.45, NBA/NCAAB=12.0.",
        "attribution_url": "https://www.pro-football-reference.com/about/win_prob.htm",
        "attribution_name": "nflfastR / PFR methodology",
    },
}


def get_source_meta(source_key: str) -> dict | None:
    """Get metadata for a source, or None if unknown."""
    return WIN_PROB_SOURCES.get(source_key)


def get_active_sources() -> dict:
    """Get all configured sources."""
    return WIN_PROB_SOURCES
