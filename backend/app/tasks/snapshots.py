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
) -> tuple:
    """
    Create a new WinProbSnapshot or update existing if value unchanged.

    Returns (snapshot, is_new) tuple.
    - If value changed: creates new snapshot, returns (new_snapshot, True)
    - If value same: updates existing snapshot's reading_count/valid_until, returns (existing, False)
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

    # Compare home_win_probability (the primary value)
    is_same = False
    if existing is not None and existing.home_win_probability is not None and home_win_probability is not None:
        is_same = float(existing.home_win_probability) == float(home_win_probability)

    if existing is None or not is_same:
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
