"""Odds snapshot filtering utilities.

Pure functions for filtering odds snapshots before aggregation.
Extracted from routes/events.py for testability (no FastAPI dependency).
"""

from datetime import datetime, timedelta, timezone


def _effective_time(snapshot) -> datetime:
    """Return the most recent confirmation time for a snapshot.

    With write-time dedup, `captured_at` is when the odds value first appeared,
    while `valid_until` gets bumped on each subsequent poll that confirms the
    same value.  Using valid_until (when available) correctly identifies
    bookmakers that are still actively being polled even if their odds haven't
    changed.
    """
    if snapshot.valid_until is not None:
        return snapshot.valid_until
    return snapshot.captured_at


def filter_stale_bookmaker_snapshots(
    snapshots: list, event_status: str, commence_time: datetime = None
) -> list:
    """Filter out stale bookmaker snapshots for games that have started.

    Two layers of filtering for non-scheduled events:

    1. **Pregame filter**: Exclude bookmakers whose odds haven't been confirmed
       since before the game started.  Uses ``_effective_time`` (prefers
       ``valid_until`` over ``captured_at``) so that write-time-deduped
       snapshots with unchanged-but-confirmed odds are correctly kept.

    2. **Recency filter** (live events only): Exclude bookmakers whose last
       confirmation is >10 minutes older than the freshest bookmaker.  This
       catches bookmakers that posted a single live update then stopped.

    For scheduled events or when commence_time is unavailable, returns
    snapshots unchanged.
    """
    if event_status == "scheduled" or not snapshots or commence_time is None:
        return snapshots

    # Sanity check: commence_time should be in the past for started events.
    # If it's in the future, it's likely a bad value from the Odds API.
    now = datetime.now(timezone.utc)
    if commence_time > now:
        return snapshots

    # Layer 1: exclude bookmakers not confirmed since game start
    live_snapshots = [
        s for s in snapshots if _effective_time(s) >= commence_time
    ]

    # Only use filtered list if we have at least one with valid probability
    if not any(s.home_win_probability is not None for s in live_snapshots):
        return snapshots

    # Layer 2 (live only): exclude bookmakers that stopped updating
    # A bookmaker that posted one live update then went silent would pass
    # Layer 1 but contaminate the aggregate with stale odds.
    if event_status == "live" and len(live_snapshots) > 1:
        latest_time = max(_effective_time(s) for s in live_snapshots)
        recency_cutoff = latest_time - timedelta(minutes=10)
        recent_snapshots = [
            s for s in live_snapshots
            if _effective_time(s) >= recency_cutoff
        ]
        # Only apply recency filter if it leaves at least one snapshot
        if any(s.home_win_probability is not None for s in recent_snapshots):
            live_snapshots = recent_snapshots

    return live_snapshots
