"""Pure polling configuration logic for odds API.

Extracted from tasks/odds_polling.py to make polling parameter
selection independently testable.
"""

from app.tasks.config import (
    SPORT_MIN_POLL_INTERVALS,
    SPORT_REGION_OVERRIDES,
    SLOW_POLL_INTERVAL,
    MEDIUM_POLL_INTERVAL,
    SLOW_THRESHOLD,
    MEDIUM_THRESHOLD,
)
from app.tasks.redis_state import QUOTA_GUARD_CONSERVATION_INTERVAL


def determine_api_params(
    tier: str,
    sport_tier: int,
    sport_key: str,
    quota_conservation: bool,
) -> tuple[str, str]:
    """Determine Odds API markets and regions for a polling call.

    Returns (markets, regions) strings for the API request.

    Quota optimization rules:
    - Conservation mode: h2h only, us only
    - Live tier: full markets, Tier 1 gets us+us2
    - Soon tier: full markets, Tier 1 gets us+us2
    - Later tier: h2h only, us only (saves ~83% vs live)
    """
    if quota_conservation:
        return "h2h", "us"

    if tier == "live":
        markets = "h2h,spreads,totals"
        regions = "us,us2" if sport_tier == 1 else "us"
    elif tier == "soon":
        markets = "h2h,spreads,totals"
        regions = "us,us2" if sport_tier == 1 else "us"
    else:
        markets = "h2h"
        regions = "us"

    region_override = SPORT_REGION_OVERRIDES.get(sport_key)
    if region_override and not quota_conservation:
        regions = region_override

    return markets, regions


def compute_effective_interval(
    base_interval: float,
    sport_key: str,
    tier: str,
    unchanged_count: int,
    quota_conservation: bool,
) -> float:
    """Compute the effective polling interval with adaptive slowdown.

    Factors: base interval, per-sport minimums, adaptive slowdown
    (unchanged poll counter), and conservation mode.
    """
    interval = base_interval

    sport_min = SPORT_MIN_POLL_INTERVALS.get(sport_key)
    if sport_min:
        interval = max(interval, sport_min)

    if quota_conservation:
        interval = max(interval, QUOTA_GUARD_CONSERVATION_INTERVAL)

    if tier != "live" and unchanged_count >= SLOW_THRESHOLD:
        interval = max(interval, SLOW_POLL_INTERVAL)
    elif tier != "live" and unchanged_count >= MEDIUM_THRESHOLD:
        interval = max(interval, MEDIUM_POLL_INTERVAL)

    return interval
