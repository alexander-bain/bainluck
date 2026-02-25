"""
Shared constants and configuration for Celery tasks.
"""

from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING  # noqa: F401 — re-exported

# Adaptive polling state keys in Redis
POLL_STATE_KEY = "bainluck:poll_state"
LAST_ODDS_HASH_KEY = "bainluck:last_odds_hash"

# Polling intervals (in seconds)
# Tiered approach based on game proximity (optimized for 5M calls/month)
LIVE_POLL_INTERVAL = 32       # 32 seconds for live games (the main use case!)
SOON_POLL_INTERVAL = 60       # 1 minute for games starting in 0-2 hours
LATER_POLL_INTERVAL = 120     # 2 minutes for games starting in 2-6 hours

# Adaptive polling thresholds (for when odds aren't changing)
# When odds stay the same, gradually slow down to conserve API calls
FAST_POLL_INTERVAL = 60       # 1 minute when data is changing
MEDIUM_POLL_INTERVAL = 300    # 5 minutes after unchanged polls
SLOW_POLL_INTERVAL = 600      # 10 minutes after many unchanged polls

# Thresholds for slowing down
MEDIUM_THRESHOLD = 3   # Slow to medium after this many unchanged polls
SLOW_THRESHOLD = 6     # Slow to slow after this many unchanged polls

# Sport-specific max durations (in hours) for staleness detection
# Used to infer when a match has likely ended if odds go stale
SPORT_MAX_DURATIONS = {
    # Tennis can go very long, especially Grand Slam 5-setters
    "tennis": 6.0,
    # Most team sports are 2-4 hours
    "basketball": 3.5,
    "baseball": 5.0,  # Extra innings possible
    "americanfootball": 4.5,
    "icehockey": 3.5,
    "mma": 4.0,  # Full card duration
    "boxing": 3.0,
    "golf": 8.0,  # Round can be long
    "lacrosse": 3.0,
    # Default for unknown sports
    "default": 4.0,
}

# Staleness thresholds for marking events as "closed"
ODDS_STALE_MINUTES = 30  # Minutes without odds update to consider stale
MIN_HOURS_BEFORE_STALENESS_CHECK = 1.5  # Don't check staleness until match has been live this long

# Futures poll less frequently since they change slowly
FUTURES_POLL_INTERVAL = 3600  # 1 hour default

# StatPal polling intervals
STATPAL_SCHEDULE_POLL_INTERVAL = 3600      # 1 hour — fixture/schedule sync
STATPAL_INJURY_POLL_INTERVAL = 900         # 15 min — injury reports
STATPAL_LIVE_PLAY_POLL_INTERVAL = 60       # 1 min — play-by-play for live games
