"""
Shared snapshot helpers for write-time deduplication across task modules.
"""

from datetime import datetime, timezone

from sqlalchemy import select


async def _create_or_update_win_prob_snapshot(
    session,
    event_id: int,
    source: str,
    home_win_probability: float,
    away_win_probability: float,
    game_state: dict = None,
    is_completed: bool = False,
) -> tuple:
    """
    Create a new WinProbSnapshot or update existing if value unchanged.

    Returns (snapshot, is_new) tuple.
    - If value changed: creates new snapshot, returns (new_snapshot, True)
    - If value same: updates existing snapshot's reading_count/valid_until, returns (existing, False)

    #922: when ``is_completed`` is True (the event is completed/closed), a value
    change does NOT append a new time-series point — instead the most recent
    snapshot is refreshed in place (value + valid_until). On post-final re-process
    cycles ESPN can keep echoing a value / report the game as "in" for 20-40 min,
    and the stat model drifts; appending those produced the chart "stale tail".
    The terminal value is still captured (in place at the real final, or as a
    single new point if no prior snapshot exists yet for this event+source).
    """
    from app.models.models import WinProbSnapshot

    now = datetime.now(timezone.utc)

    # Find the most recent snapshot for this event+source
    result = await session.execute(
        select(WinProbSnapshot)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.source == source,
        )
        .order_by(WinProbSnapshot.captured_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    # Compare probability AND game period — a new inning/quarter with the same
    # probability is still a distinct observation worth recording, otherwise
    # we lose period markers on charts when short innings don't move the line.
    is_same = False
    if existing is not None and existing.home_win_probability is not None and home_win_probability is not None:
        prob_same = float(existing.home_win_probability) == float(home_win_probability)
        period_same = True
        if prob_same and game_state and existing.game_state:
            old_gs = existing.game_state if isinstance(existing.game_state, dict) else {}
            new_period = game_state.get("period") or game_state.get("inning")
            old_period = old_gs.get("period") or old_gs.get("inning")
            if new_period and old_period and str(new_period) != str(old_period):
                period_same = False
        is_same = prob_same and period_same

    if existing is None or not is_same:
        # #922: completed/closed event — refresh the terminal point in place
        # instead of appending a new late captured_at point. The live snapshots
        # already captured the game through its final; this keeps the terminal
        # value current without extending the time series past the real final.
        if is_completed and existing is not None:
            existing.home_win_probability = home_win_probability
            existing.away_win_probability = away_win_probability
            if game_state is not None:
                existing.game_state = game_state
            existing.valid_until = now
            existing.reading_count = (existing.reading_count or 0) + 1
            return existing, False

        # Value changed — close out the old row and create a new one
        if existing is not None:
            existing.valid_until = now

        snapshot = WinProbSnapshot(
            event_id=event_id,
            source=source,
            home_win_probability=home_win_probability,
            away_win_probability=away_win_probability,
            game_state=game_state,
            reading_count=1,
        )
        return snapshot, True
    else:
        # Same value — bump the counter
        existing.reading_count += 1
        existing.valid_until = now
        return existing, False
