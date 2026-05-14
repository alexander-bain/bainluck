"""
Shared constants and configuration for Celery tasks.
"""

from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING, STATPAL_PBP_SPORTS  # noqa: F401 — re-exported

# Adaptive polling state keys in Redis
POLL_STATE_KEY = "bainluck:poll_state"
LAST_ODDS_HASH_KEY = "bainluck:last_odds_hash"

# Polling intervals (in seconds)
# Tiered approach based on game proximity (optimized for 5M calls/month)
LIVE_POLL_INTERVAL = 32       # 32 seconds for live games (the main use case!)
SOON_POLL_INTERVAL = 300      # 5 minutes for games starting in 0-1 hours
LATER_POLL_INTERVAL = 3600    # 1 hour for games starting in 1-6 hours

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

# Discovery intervals by league tier (in seconds)
# Tier 1 (NBA, NFL, etc.) gets polled most frequently; tier 4 (minor leagues) least.
# The beat schedule fires discover_events every 15 min, but per-sport Redis gating
# inside the task skips sports that were polled too recently for their tier.
DISCOVER_TIER1_INTERVAL = 1800   # 30 min — doubled from 15min to save quota
DISCOVER_TIER2_INTERVAL = 3600   # 1 hour — doubled from 30min
DISCOVER_TIER3_INTERVAL = 14400  # 4 hours — doubled from 2h
DISCOVER_TIER4_INTERVAL = 28800  # 8 hours — doubled from 4h

# Futures poll less frequently since they change slowly
FUTURES_POLL_INTERVAL = 3600  # 1 hour default

# ---------------------------------------------------------------------------
# Sport polling tiers — controls frequency AND region coverage per sport
# ---------------------------------------------------------------------------
# Tier 1: Core US sports — default intervals, us+us2 regions for live/soon
# Tier 2: Secondary — 2x slower intervals, us region only
# Tier 3: Long tail — 4x slower intervals, us region only (default for unlisted)
SPORT_POLLING_TIERS: dict[str, int] = {
    # Tier 1 — core
    "basketball_nba": 1,
    "basketball_ncaab": 1,
    "icehockey_nhl": 1,
    "baseball_mlb": 1,
    "americanfootball_nfl": 1,
    # Tier 2 — secondary
    "basketball_wnba": 2,
    "americanfootball_ncaaf": 2,
    "soccer_epl": 2,
    "soccer_usa_mls": 2,
    "soccer_uefa_champs_league": 2,
    "mma_mixed_martial_arts": 2,
}

# Per-sport region overrides (temporary or permanent).
# When set, overrides the default tier-based region selection for live/soon polls.
SPORT_REGION_OVERRIDES: dict[str, str] = {}

# Per-sport minimum poll intervals (seconds). Applied as a floor AFTER tier
# multipliers and adaptive slowdown. Useful for high-event-count sports where
# even Tier 3 defaults are too aggressive.
SPORT_MIN_POLL_INTERVALS: dict[str, int] = {
    "aussierules_afl": 600,  # 10 minutes
}
SPORT_POLLING_DEFAULT_TIER = 3

# Interval multipliers: applied to base poll_interval (live/soon/later)
SPORT_TIER_MULTIPLIERS: dict[int, int] = {
    1: 1,    # default intervals  (live=32s, soon=5m, later=1h)
    2: 2,    # 2x slower          (live=64s, soon=10m, later=2h)
    3: 4,    # 4x slower          (live=128s, soon=20m, later=4h)
}

# StatPal polling intervals
STATPAL_SCHEDULE_POLL_INTERVAL = 3600      # 1 hour — fixture/schedule sync
STATPAL_INJURY_POLL_INTERVAL = 900         # 15 min — injury reports
STATPAL_LIVE_PLAY_POLL_INTERVAL = 60       # 1 min — play-by-play for live games
