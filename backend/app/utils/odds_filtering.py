"""Odds snapshot filtering utilities.

Pure functions for filtering odds snapshots before aggregation.
Extracted from routes/events.py for testability (no FastAPI dependency).
"""

from datetime import datetime, timezone


def filter_stale_bookmaker_snapshots(
    snapshots: list, event_status: str, commence_time: datetime = None
) -> list:
    """Filter out pregame-only bookmaker snapshots for games that have started.

    During and after live games, some bookmakers stop updating their moneyline
    odds or keep returning unchanged pregame values. Including these pregame
    values contaminates the aggregate (e.g., showing 59% when live books show 2%).

    We include bookmakers whose odds VALUE changed after the game started
    (captured_at >= commence_time), meaning they've posted at least one live
    update. Bookmakers whose last distinct odds value was set before kickoff
    are excluded — they're just echoing pregame lines.

    Runs for live, completed, and closed games. For scheduled events or when
    commence_time is unavailable, returns unchanged.

    Sanity check: if the event has started (status != scheduled) but
    commence_time is in the future, commence_time is likely wrong (known
    Odds API bug where local times are returned as UTC). In this case,
    skip filtering to avoid excluding all snapshots.
    """
    if event_status == "scheduled" or not snapshots or commence_time is None:
        return snapshots

    # Sanity check: commence_time should be in the past for started events.
    # If it's in the future, it's likely a bad value from the Odds API.
    now = datetime.now(timezone.utc)
    if commence_time > now:
        return snapshots

    live_snapshots = [s for s in snapshots if s.captured_at >= commence_time]

    # Only use filtered list if we have at least one with valid probability
    if any(s.home_win_probability is not None for s in live_snapshots):
        return live_snapshots

    return snapshots
