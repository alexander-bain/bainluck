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
    "kalshi": {
        "display_name": "Kalshi",
        "source_type": "market",
        "sports": ["*"],
        "color": "#22c55e",
        "dash_pattern": "8 4",
        "description": "Win probability from Kalshi, a CFTC-regulated prediction market where real money is traded on event outcomes. Kalshi odds represent the consensus of market participants betting on game outcomes.",
        "methodology": "The midpoint of the bid/ask spread for the 'Yes' contract on the game outcome market. Kalshi contracts settle at $1 if the event occurs and $0 otherwise, so the price directly represents the market's implied probability.",
        "attribution_url": "https://kalshi.com",
        "attribution_name": "Kalshi",
    },
    "polymarket": {
        "display_name": "Polymarket",
        "source_type": "market",
        "sports": ["*"],
        "color": "#3b82f6",
        "dash_pattern": "8 4",
        "description": "Win probability from Polymarket, the world's largest prediction market by volume. Polymarket prices reflect the consensus of thousands of traders betting real money on game outcomes.",
        "methodology": "The outcome price from Polymarket's CLOB (Central Limit Order Book). Prices range from $0.00 to $1.00 and directly represent implied probability. For binary markets, the 'Yes' price equals the market's probability estimate.",
        "attribution_url": "https://polymarket.com",
        "attribution_name": "Polymarket",
    },
    "moneypuck": {
        "display_name": "MoneyPuck",
        "source_type": "model",
        "sports": ["icehockey_nhl"],
        "color": "#10b981",
        "dash_pattern": "4 4",
        "description": "Hockey win probability from MoneyPuck's statistical model, widely considered the gold standard for NHL analytics. Uses shot metrics, expected goals (xG), and real-time game state.",
        "methodology": "MoneyPuck uses a machine learning model trained on historical NHL play-by-play data. The model incorporates shot quality, expected goals (xG), team strength in various on-ice situations (5v5, power play, penalty kill), score effects, and venue adjustments. Updates in real-time during live games.",
        "attribution_url": "https://moneypuck.com",
        "attribution_name": "MoneyPuck",
    },
    "fangraphs": {
        "display_name": "MLB Model",
        "source_type": "model",
        "sports": ["baseball_mlb"],
        "color": "#06b6d4",
        "dash_pattern": "4 4",
        "description": "Official MLB win probability from the MLB Stats API. Computed from play-by-play data using run expectancy tables, leverage index, and game state (inning, outs, runners, score).",
        "methodology": "MLB's win probability model is based on historical play-by-play data across MLB seasons. It uses run expectancy matrices (based on base/out state), score differential, inning, home-field advantage, and updates on every pitch. Data sourced from the official MLB Stats API (statsapi.mlb.com).",
        "attribution_url": "https://statsapi.mlb.com",
        "attribution_name": "MLB Stats API",
    },
    "bainluck_aggregate": {
        "display_name": "Bain Luck",
        "source_type": "aggregate",
        "sports": ["*"],
        "color": "#1e293b",
        "dash_pattern": None,
        "description": "Bain Luck's aggregate probability, combining sportsbook consensus, prediction markets (Kalshi, Polymarket), and statistical models (ESPN, MLB) via weighted median. Outlier-resistant and staleness-aware.",
        "methodology": "Weighted median across all available sources. Sportsbook consensus (weight 3.0) anchors the aggregate due to deep multi-bookmaker liquidity. Prediction markets (0.8 each) and statistical models (1.0-1.5) provide independent signals. Source weight decays linearly after 2 minutes of staleness and drops to zero after 5 minutes. Light exponential smoothing (α=0.3) prevents jumps when sources appear or disappear.",
        "attribution_url": "https://bainluck.com",
        "attribution_name": "Bain Luck",
    },
}


def get_source_meta(source_key: str) -> dict | None:
    """Get metadata for a source, or None if unknown."""
    return WIN_PROB_SOURCES.get(source_key)


def get_active_sources() -> dict:
    """Get all configured sources."""
    return WIN_PROB_SOURCES
